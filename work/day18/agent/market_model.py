"""Market Model + Buyer Profile (PIPELINE.md ข้อ S3).

ผลแต่ละซองบอก "ขอบ" ไม่ใช่ "ค่า" (ratio r = ราคา ÷ TV ที่เราใช้ตั้งราคา):
    ACCEPTED    → เพดาน ≥ r · จุดตัด ≥ r (ชนะได้ที่ r)
    PARTIAL     → เพดาน ≥ r · จุดตัด ≈ r
    OUTBID      → เพดาน ≥ r · จุดตัด < r
    ABOVE_LIMIT → เพดาน < r
    SPEC_MISMATCH → คุณภาพจริงไม่ผ่านสเปกนั้น → ห้ามส่งล็อตนี้ให้สเปกที่ "เข้มเท่ากันหรือเข้มกว่า" อีกทั้งเกม
                    (สเปกที่หลวมกว่ายังส่งได้ เช่น ตกบางกอกบลูม screen≥17 ยังส่งดอยช้าง screen≥16 ได้)

เก็บเป็นช่วง (lo, hi) + จำนวนข้อมูล (n) = ความมั่นใจ · เพดานแกว่งราย RFQ → ข้อมูลขัดกันไม่ลบ แต่ลดความมั่นใจ
ราคาตลาด (18 พ.ย. หลังแข่งด่าน 2): ใช้ market_summary ของทุกรอบที่ผ่านมา (รวมรอบซ้อมของตลาดเดียวกัน)
    ทุกทีมได้ล็อตชุดเดียวกัน → ราคาสูงสุดที่ผู้ซื้อรับ ÷ TV สูงสุดของล็อตที่ผ่านสเปก RFQ นั้น
    = ขอบล่างของ "ratio สุดท้ายที่ยังชนะ" (ตรวจกับซองจริงด่าน 2: ซองที่ ≤ ค่านี้ขายได้ 10/10 · เกินค่านี้ 4/12)
    เป้า = ค่าต่ำสุดของผู้ซื้อรายนั้นใน 2 รอบล่าสุด − MKT_MARGIN (0.02) · backtest ด่าน 2: ชนะแน่ 85% เฉลี่ย ×0.943
ค่าเริ่ม (PRIOR) ใช้แค่ก่อนมีผลตลาดรอบแรก: start = ราคาที่ชนะในตลาดแข่ง 18 พ.ย. · เพดาน = นิสัยผู้ซื้อจากตลาดฝึก
"""
import json
import math
import os
from collections import defaultdict
from pathlib import Path

from inventory import spec_ok

BAG = 60

NOINFO = {"COMMERCIAL": 0.97, "INSTANT": 0.87, "SPECIALTY": 0.97}   # ราคา R1 เมื่อยังไม่มีผลตลาด (NOINFO_SURE)
PRIOR_TYPE = {      # start = ตลาดแข่งด่าน 2 (Commercial ~1.02–1.05 · Instant ~0.92–0.95 · Specialty ~0.98–1.03)
    "COMMERCIAL": {"ceil": 1.06, "start": 1.020},
    "INSTANT": {"ceil": 0.96, "start": 0.920},
    "SPECIALTY": {"ceil": 1.22, "start": 1.000},
}
# เพดานโดยประมาณรายผู้ซื้อ (จับคู่ด้วยชื่อบางส่วน) · Specialty จาก 46 เกมตลาดฝึกแบบใหม่: ขายได้ ~1.18 · เกินเพดานตั้งแต่ ~1.24 / ~1.18–1.22
PRIOR_BUYER = {"ชุมพรคั่วบด": 1.09, "สยามคอมเมิร์ซ": 1.04, "ทรีอินวัน": 0.98, "อินสแตนท์ไทย": 0.945,
               "ดอยช้าง": 1.24, "บางกอกบลูม": 1.20}
DEFAULT_PRIOR = {"ceil": 1.00, "start": 0.95}
CLEAR_WINDOW = 2          # จุดตัดการแข่งเปลี่ยนตามรอบ → ใช้แค่ 2 รอบล่าสุดที่มีข้อมูล
MKT_WINDOW = 2            # ราคาตลาด: ต่ำสุดของ 2 รอบล่าสุดที่ผู้ซื้อรายนั้นซื้อ


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


class Bounds:
    def __init__(self):
        self.lo = None    # ค่าที่ "รู้ว่า ≥"
        self.hi = None    # ค่าที่ "รู้ว่า <"
        self.n = 0

    def at_least(self, r):
        self.lo = r if self.lo is None else max(self.lo, r)
        self.n += 1

    def below(self, r):
        self.hi = r if self.hi is None else min(self.hi, r)
        self.n += 1

    def as_dict(self):
        return {"lo": self.lo, "hi": self.hi, "n": self.n}


def _buyer_prior(buyer: str, btype: str, learned: dict) -> dict:
    p = dict(PRIOR_TYPE.get(btype, DEFAULT_PRIOR))
    for name, ceil in PRIOR_BUYER.items():
        if name in (buyer or ""):
            p["ceil"] = ceil
    lt = (learned or {}).get(btype)
    if lt:   # เกมก่อนในตลาดฝึก: ผสม 50/50 กับ prior (ตลาดแข่งอาจต่าง)
        if lt.get("ceil"):
            p["ceil"] = round((p["ceil"] + lt["ceil"]) / 2, 3)
        if lt.get("clear"):
            p["start"] = round((p["start"] + min(lt["clear"], p["ceil"] - 0.01)) / 2, 3)
    p["start"] = min(p["start"], p["ceil"] - 0.01)
    return p


def spec_stricter_or_equal(spec: dict, than: dict) -> bool:
    """spec เข้มเท่ากันหรือเข้มกว่า than ทุกข้อ (ล็อตที่ตก than ย่อมตก spec ด้วย)"""
    return (spec["max_defect_pct"] <= than["max_defect_pct"]
            and spec["max_moisture_pct"] <= than["max_moisture_pct"]
            and (spec.get("min_screen") or 0) >= (than.get("min_screen") or 0))


class MarketModel:
    def __init__(self, memory, learned: dict | None = None):
        self.learned = learned or {}
        self.ceil_buyer = defaultdict(Bounds)     # buyer name -> Bounds
        self.ceil_type = defaultdict(Bounds)      # buyer type -> Bounds
        self.clear_type = defaultdict(Bounds)     # buyer type -> Bounds (2 รอบล่าสุด)
        self.status = defaultdict(lambda: defaultdict(int))   # type -> status -> count (ทั้งเกม)
        self.last = defaultdict(lambda: defaultdict(int))     # type -> status -> count (รอบล่าสุด)
        self.fill = defaultdict(list)             # type -> [(round_idx, bought/wanted, offers per bag)]
        self.banned = set()                       # {(lot_id, buyer_type)} · ใช้เมื่อไม่รู้สเปก (log รุ่นเก่า)
        self.banned_specs = defaultdict(list)     # lot_id -> [spec ที่ตกด้วยคุณภาพจริง]
        self.accepted_max = {}
        self.rounds_seen = 0
        self.offered_bags = 0                     # ทั้งเกม: กระสอบที่เสนอ / ที่ขายได้จริง → อัตราขายได้ (ใช้ตั้งงบ)
        self.filled_bags = 0
        self.rounds = []
        self.lot_samples, self.lot_tv = {}, {}
        if memory is not None:
            self._read(memory)

    def set_lots(self, lots: list[dict], tv: dict) -> None:
        """ล็อตของเรา (= ล็อตชุดเดียวกับทุกทีม) ใช้แปลงราคาใน market_summary เป็น ratio"""
        self.lot_samples = {l["lot_id"]: l["sample"] for l in lots if l.get("sample")}
        self.lot_tv = dict(tv or {})

    def market_info(self, buyer: str, spec: dict | None, k: float | None = None) -> dict | None:
        """ผลตลาดแข่งของผู้ซื้อรายนี้ (ratio = ราคาสูงสุดที่รับ ÷ TV สูงสุดของล็อตที่ผ่านสเปก = ขอบล่างของจุดตัด)
        คืน safe (ต่ำสุด 2 รอบล่าสุด) · median · top (สูงสุดรอบล่าสุด) · trend (คาดรอบหน้าถ้าราคาลงต่อเนื่อง) · fill"""
        if not spec or not self.lot_samples or os.environ.get("MARKET_PRICE", "1") == "0":
            return None
        elig = [self.lot_tv[i] for i, smp in self.lot_samples.items() if i in self.lot_tv and spec_ok(smp, spec)]
        if not elig:
            return None
        top_tv = max(elig)
        per_round = []                 # ใหม่ → เก่า: (ค่าต่ำสุด, มัธยฐาน, สูงสุด, ซื้อได้/ต้องการ)
        for rnd in reversed(self.rounds):
            rows = [row for row in rnd.get("market_summary", []) if row.get("buyer") == buyer]
            vals = sorted(row["price_max"] / top_tv for row in rows if row.get("bought_kg") and row.get("price_max"))
            if vals:
                fill = sum(r.get("bought_kg") or 0 for r in rows) / max(sum(r.get("wanted_kg") or 0 for r in rows), 1)
                per_round.append((vals[0], vals[len(vals) // 2], vals[-1], fill))
            if len(per_round) >= 3:
                break
        if not per_round:
            return None
        safe = min(v[0] for v in per_round[:MKT_WINDOW])
        # ค่าเริ่ม MKT_MODE=vol, MKT_K=1.5 · ทดสอบ 18 พ.ย.: replay ตลาดแข่ง PR 0.964 (safe 0.946) · จำลองด่าน 3 0.948 (safe 0.941)
        #   · จำลอง 8 รอบ 0.934 (safe 0.935) · MKT_MODE=safe = ต่ำสุด 2 รอบ − MKT_MARGIN แบบเดิม
        # MKT_MODE=vol: ราคาเหมือนหุ้น → ค่ากลางของราคาตัด (มัธยฐานต่อรอบ) − k × ความผันผวน
        #   ผู้ซื้อราคานิ่ง (Commercial) เว้นน้อย · ราคาแกว่ง/ขาลง (Specialty) เว้นมาก · ไม่สูงกว่ารอบล่าสุด
        meds = [v[1] for v in per_round]
        mean = sum(meds) / len(meds)
        sd = (sum((x - mean) ** 2 for x in meds) / len(meds)) ** 0.5 if len(meds) > 1 else 0.02
        within = per_round[0][1] - per_round[0][0]           # ส่วนต่างระหว่าง RFQ ในรอบเดียวกัน
        k = _env_f("MKT_K", 1.5) if k is None else k
        vol = min(per_round[0][1], mean) - k * max(sd, within / 2) - _env_f("MKT_VOL_MARGIN", 0.005)
        trend = None
        if len(per_round) >= 3 and per_round[0][1] < per_round[1][1] < per_round[2][1]:
            # มัธยฐานลด 2 รอบติด (เหมือนราคาหุ้นขาลง) → คาดรอบหน้า = ล่าสุด − ความชันเฉลี่ย
            slope = (per_round[0][1] - per_round[2][1]) / 2
            trend = per_round[0][0] + slope
        if os.environ.get("MKT_MODE", "vol") == "vol":
            safe = vol
        return {"safe": round(safe, 4), "low": round(min(v[0] for v in per_round), 4),
                "median": round(per_round[0][1], 4), "top": round(per_round[0][2], 4),
                "fill2": round(max(v[3] for v in per_round[:2]), 3) if len(per_round) >= 2 else None,
                "trend": round(trend, 4) if trend is not None else None, "fill": round(per_round[0][3], 3)}

    def market_ratio(self, buyer: str, spec: dict | None, tight: bool = True) -> float | None:
        mi = self.market_info(buyer, spec)
        if mi is None:
            return None
        return mi["safe"] if tight else mi["median"]

    def spec_banned(self, lot_id: str, btype: str, spec: dict) -> bool:
        if (lot_id, btype) in self.banned:
            return True
        return any(spec_stricter_or_equal(spec, b) for b in self.banned_specs.get(lot_id, []))

    # ---------- อ่านผลทั้งเกม ----------
    def _read(self, memory):
        rounds = memory.rounds
        self.rounds = list(rounds)
        self.rounds_seen = len(rounds)
        recent_with_data = defaultdict(int)
        for idx in range(len(rounds) - 1, -1, -1):          # ใหม่ → เก่า
            rnd = rounds[idx]
            sent = {(o["rfq_id"], o["lot_id"]): o for o in memory.sent.get(rnd["round_id"], [])}
            seen_types = set()
            practice = rnd.get("kind") == "practice"
            for o in rnd.get("my_offers", []):
                if not practice:            # รอบซ้อมตั้งราคาหยั่ง (สูง/ต่ำกว่าปกติ) → ไม่นับเป็นอัตราขายได้
                    self.offered_bags += (o.get("kg") or 0) // BAG
                    self.filled_bags += (o.get("filled_kg") or 0) // BAG
                s = sent.get((o["rfq_id"], o["lot_id"]))
                if not s or not s.get("markup"):
                    continue
                t, r, st = s["buyer_type"], float(s["markup"]), o["status"]
                buyer = s.get("buyer", "")
                self.status[t][st] += 1
                if idx == len(rounds) - 1:
                    self.last[t][st] += 1
                if st == "SPEC_MISMATCH":
                    if s.get("spec"):
                        self.banned_specs[o["lot_id"]].append(s["spec"])
                    else:
                        self.banned.add((o["lot_id"], t))
                    continue
                if st in ("ACCEPTED", "PARTIAL", "OUTBID"):
                    self.ceil_buyer[buyer].at_least(r)
                    self.ceil_type[t].at_least(r)
                elif st == "ABOVE_LIMIT":
                    self.ceil_buyer[buyer].below(r)
                    self.ceil_type[t].below(r)
                if recent_with_data[t] < CLEAR_WINDOW:
                    seen_types.add(t)
                    if st == "ACCEPTED":
                        self.clear_type[t].at_least(r)
                        self.accepted_max[t] = max(self.accepted_max.get(t, 0), r)
                    elif st == "PARTIAL":
                        self.clear_type[t].at_least(r - 0.002)
                        self.clear_type[t].below(r + 0.002)
                    elif st == "OUTBID":
                        self.clear_type[t].below(r)
            for t in seen_types:
                recent_with_data[t] += 1
            for row in rnd.get("market_summary", []):
                w = max(row.get("wanted_kg") or 0, 1)
                self.fill[row["buyer_type"]].append((idx, row.get("bought_kg", 0) / w, row.get("offers", 0) / max(w / BAG, 1)))

    def sell_rate(self, prior: float = 0.6) -> float:
        """สัดส่วนกระสอบที่เสนอแล้วขายได้จริง (ทั้งเกม) · ข้อมูลน้อย (< 4 กระสอบ) = prior
        ค่าเริ่ม 0.6 = ตลาดฝึกแบบใหม่ (TestNew 36 เกม: ขายได้ ~59% ของซอง)"""
        if self.offered_bags < 4:
            return prior
        return self.filled_bags / self.offered_bags

    # ---------- สรุปตลาดต่อประเภท ----------
    def market_state(self, btype: str) -> dict:
        rows = self.fill.get(btype, [])
        if not rows:
            return {"mode": "unknown", "fill": None, "crowd": None, "crowd_trend": 0.0}
        last_idx = max(r[0] for r in rows)
        last = [r for r in rows if r[0] == last_idx]
        earlier = [r for r in rows if r[0] < last_idx]
        fill = sum(r[1] for r in last) / len(last)
        crowd = sum(r[2] for r in last) / len(last)
        crowd_prev = sum(r[2] for r in earlier) / len(earlier) if earlier else crowd
        mode = "ceiling" if fill < 0.9 else ("competitive" if crowd >= 1.2 else "mixed")
        return {"mode": mode, "fill": round(fill, 2), "crowd": round(crowd, 2),
                "crowd_trend": round(crowd - crowd_prev, 2)}

    # ---------- ราคาเป้าหมาย ----------
    def ceiling(self, buyer: str, btype: str) -> dict:
        prior = _buyer_prior(buyer, btype, self.learned)
        b = self.ceil_buyer.get(buyer) if buyer in self.ceil_buyer else None
        if b is None or b.n == 0:
            b = self.ceil_type.get(btype) or Bounds()
        lo, hi, n = b.lo, b.hi, b.n
        conflict = False
        if lo is not None and hi is not None:
            conflict = lo >= hi
            est, width = (lo + hi) / 2, abs(hi - lo)
        elif lo is not None:
            est, width = max(prior["ceil"], lo + 0.01), 0.08
        elif hi is not None:
            est, width = min(prior["ceil"], hi - 0.015), 0.08
        else:
            est, width = prior["ceil"], 0.12
        conf = n / (n + 3) * (0.5 if conflict else 1.0)
        return {"est": round(est, 4), "lo": lo, "hi": hi, "n": n, "width": round(width, 3),
                "conf": round(conf, 2), "conflict": conflict, "prior": prior}

    def target(self, buyer: str, btype: str, spec: dict | None = None, tight: bool = True,
               phase: str | None = None) -> dict:
        """ratio ที่ควรเสนอ (ก่อนบันได/สุ่ม) + เพดานบนของส่วนหยั่ง + ความมั่นใจ
        มีราคาตลาด (market_summary) → ใช้ราคาตลาด − MKT_MARGIN ก่อนทุกอย่าง (ขายออกแน่และได้ราคาเต็มที่ตลาดให้)"""
        c = self.ceiling(buyer, btype)
        m1 = 0.01 + 0.02 * (1 - c["conf"])                 # ยิ่งไม่มั่นใจ ยิ่งเว้นห่างเพดาน
        cap = c["est"] - m1
        if c["hi"] is not None:
            cap = min(cap, c["hi"] - 0.005)
        cb = self.clear_type.get(btype) or Bounds()
        ms = self.market_state(btype)
        step = 0.02 if cb.n < 3 else (0.01 if cb.n < 8 else 0.005)
        if cb.lo is not None and cb.hi is not None:
            comp, src = (cb.lo + cb.hi) / 2 if cb.lo < cb.hi else cb.hi - 0.005, "clear-between"
        elif cb.hi is not None:
            comp, src = cb.hi - step, "clear-below-outbid"
        elif cb.lo is not None:
            comp, src = cb.lo + step / 2, "clear-push-up"       # ขายได้หมดทุกซอง = อาจตั้งต่ำไป
        else:
            comp, src = c["prior"]["start"], "prior"
        if ms["mode"] == "ceiling" and cb.hi is None:
            comp, src = max(comp, cap), "ceiling-bound"           # ผู้ซื้อซื้อไม่ครบ → ไม่ต้องตัดราคาแข่ง
        ratio = min(cap, comp)
        # k (ระยะเว้นราคา × ความผันผวน): MKT_K_<TYPE> แยกประเภท · MKT_K_EARLY ใช้ช่วงซ้อม/R1–R2 (ไม่ตั้ง = MKT_K)
        k = _env_f("MKT_K_" + (btype or "").upper(), _env_f("MKT_K", 1.5))
        if phase == "early" and os.environ.get("MKT_K_EARLY"):
            k = _env_f("MKT_K_EARLY", k)
        mi = self.market_info(buyer, spec, k)
        rm = None
        if mi is not None:
            rm = mi["safe"] if tight else mi["median"]
            mt = rm - (0.0 if os.environ.get("MKT_MODE", "vol") == "vol"
                       else _env_f("MKT_MARGIN", 0.02) if tight else _env_f("MKT_MARGIN_SLACK", 0.005))
            src = "market"
            # MKT_TREND / MKT_SHORTAGE ค่าเริ่มปิด · ทดสอบ 18 พ.ย.: replay ตลาดแข่ง PR 0.946 (ปิด) · 0.946 (trend) · 0.943 (short)
            #   · 0.938 (ทั้งคู่) · ตลาดจำลอง 0.924–0.934 (ต่างกันไม่เกิน noise) → ข้อมูลจริงไม่ได้บอกว่าดีกว่า
            if mi["trend"] is not None and os.environ.get("MKT_TREND", "0") != "0":
                if mi["trend"] - 0.01 < mt:                # ขาลง → ตั้งตามราคาที่คาดว่าจะเป็นรอบหน้า
                    mt, src = mi["trend"] - 0.01, "market-trend"
            if mi["fill"] < _env_f("MKT_SHORT_FILL", 0.9) and os.environ.get("MKT_SHORTAGE", "0") != "0":
                # ผู้ซื้อซื้อไม่ครบ = ของไม่พอ → คู่แข่งไม่ได้กดราคา · ตั้งใกล้ราคาสูงสุดที่รับได้ (ไม่เกินเพดานจากตลาดฝึก)
                short = min(mi["top"] - 0.01, c["est"] - 0.01)
                if short > mt:
                    mt, src = short, "market-short"
            # EARLY_SURE (ช่วงซ้อม/R1–R2): ขายออกแน่ตอนราคายังสูง → ไม่เกินราคาตัดต่ำสุดที่ผู้ซื้อรายนี้เคยรับ (≤ 3 รอบ) − EARLY_MARGIN
            #   ด่าน 2: R2 ชุมพรลดราคาตัดกะทันหัน 1.045 → 1.003 · k × ความผันผวนเว้นไม่พอเพราะ Commercial ราคานิ่ง
            if phase == "early" and os.environ.get("EARLY_SURE", "1") != "0":   # ค่าเริ่มเปิด (19 พ.ย.)
                sure = mi["low"] - _env_f("EARLY_MARGIN", 0.005)
                if sure < mt:
                    mt, src = sure, "market-sure"
            # SHORT_CEIL (ค่าเริ่ม 0 = ปิด): ผู้ซื้อซื้อไม่ครบ 2 รอบติด (fill < SHORT_FILL) = คนขายน้อย ราคาติดเพดานไม่ใช่การแข่ง
            #   → ตั้งใกล้เพดานที่ประเมินไว้ (ไม่ใช่ราคาตลาด) · ตลาดฝึก 19 พ.ย.: Commercial ซื้อได้ ~85% Specialty ~20% แต่เราขาย ~0.97 (เพดาน ~1.06)
            if (os.environ.get("SHORT_CEIL", "0") != "0" and mi.get("fill2") is not None
                    and mi["fill2"] < _env_f("SHORT_FILL", 0.95) and phase != "final"):
                sc = c["est"] - _env_f("SHORT_CEIL_MARGIN", 0.02)
                if sc > mt:
                    mt, src = sc, "market-ceil"
            if cb.hi is not None:                 # เราเพิ่งแพ้ราคาที่ต่ำกว่านั้น → ต่ำกว่าที่แพ้
                mt = min(mt, cb.hi - 0.005)
            ratio, cap = mt, max(cap, mt)
        elif phase == "early" and os.environ.get("NOINFO_SURE", "0") != "0":
            # NOINFO_SURE (ค่าเริ่มปิด · ค่ามาจากตลาดฝึกซึ่งไม่มีการตัดราคาแบบตลาดแข่ง · ไม่มีข้อมูล = ใช้ prior จากด่าน 2 จริง): ช่วงต้นยังไม่มีผลตลาดของผู้ซื้อรายนี้ (ไม่มีรอบซ้อม/รอบซ้อมถูกตัด) → ราคาขายออกแน่
            #   ตลาดฝึก 2,904 เกม (ไม่มีรอบซ้อม): R1 ชนะแค่ 58% · ราคาตัด R1 มัธยฐาน C 1.00 / I 0.90 / S 1.01 (ต่ำสุด 10%: 0.91 / 0.80 / 0.90)
            #   ด่าน 2 จริง R1: C ≥ 1.025 · I ≥ 0.94 · S ≥ 1.02 → ค่าเริ่มเท่านี้ขายออกทั้งสองตลาด
            ni = _env_f("NOINFO_" + (btype or "").upper(), NOINFO.get(btype, 0.9))
            if ni < ratio:
                ratio, src = ni, "market-noinfo"
        explore_max = (c["hi"] - 0.005) if c["hi"] is not None else c["est"] + max(0.02, c["width"] / 2)
        return {"ratio": round(ratio, 4), "cap": round(cap, 4), "explore_max": round(explore_max, 4),
                "conf": c["conf"], "source": src, "ceil": c, "clear": cb.as_dict(), "market": ms,
                "market_ratio": rm, "market_info": mi}

    def p_sell(self, t: dict, ratio: float) -> float:
        """โอกาสขายได้โดยประมาณ (ใช้จัดลำดับ ไม่ใช่ค่าจริง)"""
        hi = t["ceil"]["hi"]
        if hi is not None and ratio >= hi:
            return 0.05
        ref = min(t["cap"] + 0.01, t["ratio"] + 0.01)
        return 0.05 + 0.9 / (1 + math.exp((ratio - ref) / 0.01))

    def summary(self) -> dict:
        """สรุปต่อประเภท ให้ LLM และ log"""
        out = {}
        for t in set(self.status) | set(self.fill):
            ct, cl = self.ceil_type.get(t) or Bounds(), self.clear_type.get(t) or Bounds()
            out[t] = {"ceil": ct.as_dict(), "clear": cl.as_dict(), "accepted_max": self.accepted_max.get(t),
                      "status": dict(self.status.get(t, {})), "last": dict(self.last.get(t, {})),
                      **self.market_state(t)}
        return out

    def learned_snapshot(self) -> dict:
        """ค่าที่เรียนได้ทั้งเกม เก็บไว้เป็น prior เกมหน้า (ตลาดฝึก)"""
        out = {}
        for t in PRIOR_TYPE:
            c = self.ceiling("", t)
            cl = self.clear_type.get(t)
            clear = None
            if cl and cl.lo is not None:
                clear = (cl.lo + cl.hi) / 2 if cl.hi is not None and cl.hi > cl.lo else cl.lo
            out[t] = {"ceil": c["est"] if c["n"] else None, "clear": round(clear, 4) if clear else None}
        return out


def load_learned(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_learned(path: Path, snap: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass

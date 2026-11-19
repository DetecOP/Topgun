"""ตลาดจำลองแบบออฟไลน์ (ไม่ต่อเน็ต ไม่ส่งอะไรไปตลาดจริง) — ใช้ทดสอบว่า agent ทำงานครบเกมไม่ล้ม และเทียบกับ starter

    python mock_market.py                 # v2 กับ starter อย่างละ 6 seed
    python mock_market.py --seeds 20
    python mock_market.py --noise 0.6     # ตัวอย่างคลาดมากขึ้น

⚠️ ตัวเลขในโลกจำลองนี้ (เพดานผู้ซื้อ, จำนวนคู่แข่ง, พฤติกรรมคู่แข่ง, สเปก Specialty, noise) เป็น **ค่าสมมติ**
อิงข้อมูลตลาดฝึก 17 พ.ย. บางส่วน · PR ที่ได้ใช้เทียบ "แบบไหนดีกว่าในโลกสมมติ" เท่านั้น ไม่ใช่ทำนายผลจริง
"""
import json
import math
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import appraisal                        # noqa: E402
from market import MarketError          # noqa: E402

RULES = {
    "bag_kg": 60, "salvage_ratio": 0.8, "p0": 120.0,
    "defect_steps": [{"max_defect_pct": 1.0, "step": 1.08, "grade": "PREMIUM"},
                     {"max_defect_pct": 3.0, "step": 1.04, "grade": "GRADE_1"},
                     {"max_defect_pct": 5.0, "step": 1.0, "grade": "GRADE_2"},
                     {"max_defect_pct": 7.0, "step": 0.96, "grade": "GRADE_3"},
                     {"max_defect_pct": 15.0, "step": 0.85, "grade": "BELOW_STANDARD"},
                     {"max_defect_pct": 100.0, "step": 0.6, "grade": "REJECT"}],
    "moisture": {"ref": 12.5, "penalty_per_pp": 0.02, "hard_limit": 15.0, "hard_factor": 0.6},
    "screen_factors": {"12": 0.92, "13": 0.97, "14": 1.0, "15": 1.0, "16": 1.03, "17": 1.03, "18": 1.06},
    "scoring": {"pr_points": 80.0, "appraisal_points": 20.0, "appraisal_zero_at_mape": 0.1},
    "timeline": {"appraisal_s": 600, "practice_rounds": 0, "rounds": 8, "open_s": 240, "clearing_s": 10},
    "round_capacity_factor": 1.5,
}
CALENDAR = [{"rounds": "1-3", "label": "ปกติ", "demand_weight": 1.0, "specialty_share": None},
            {"rounds": "4-5", "label": "เทศกาล", "demand_weight": 1.4, "specialty_share": 0.3},
            {"rounds": "6-8", "label": "ปกติ", "demand_weight": 1.0, "specialty_share": None}]
SPEC = {"COMMERCIAL": {"max_defect_pct": 7.0, "max_moisture_pct": 12.5, "min_screen": None},
        "INSTANT": {"max_defect_pct": 15.0, "max_moisture_pct": 14.0, "min_screen": None},
        "SPECIALTY": {"max_defect_pct": 3.0, "max_moisture_pct": 12.5, "min_screen": 16}}      # สมมติ
BUYERS = [("B1", "1 สเปเชียลตี้จำลอง", "SPECIALTY", 1.25), ("B3", "3 สยามคอมเมิร์ซ", "COMMERCIAL", 1.04),
          ("B4", "4 ชุมพรคั่วบด", "COMMERCIAL", 1.09), ("B5", "5 อินสแตนท์ไทย", "INSTANT", 0.945),
          ("B6", "6 ทรีอินวันฟู้ดส์", "INSTANT", 0.98)]
CROWD = {"COMMERCIAL": 1.6, "INSTANT": 1.3, "SPECIALTY": 0.9}       # ข้อเสนอคู่แข่งต่อกระสอบที่ผู้ซื้อต้องการ
# MOCK_STYLE=competition: ใกล้ตลาดแข่งด่าน 2 (18 พ.ย.) · Commercial ขาดของ ~×1.02 · Instant ~×0.92 แน่น ·
# Specialty แน่นมาก ~×0.98 แล้วตัดราคาลงช่วงท้าย
CROWD_COMP = {"COMMERCIAL": 0.95, "INSTANT": 1.15, "SPECIALTY": 2.2}
BASE_COMP = {"COMMERCIAL": 1.02, "INSTANT": 0.92, "SPECIALTY": 0.98}


def _style() -> str:
    import os
    return os.environ.get("MOCK_STYLE", "practice")


def _env_f(name: str, default: float) -> float:
    import os
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# MOCK_STAGE=3: แบบด่าน 3 (สไลด์วันที่ 20) · 15 รอบ · 5 ล็อต ~45 กระสอบ · เทศกาล R6–8 Specialty ต้องการมาก ·
# R13–14 ความต้องการลด · R15 ต่ำสุด · ใช้กับ MOCK_STYLE=competition · FEST_CROWD = คู่แข่ง Specialty ช่วงเทศกาล (×ปกติ)
CALENDAR_S3 = [{"rounds": "1-5", "label": "ปกติ", "demand_weight": 1.0, "specialty_share": 0.15},
               {"rounds": "6-8", "label": "เทศกาลกาแฟ", "demand_weight": 1.3, "specialty_share": 0.4},
               {"rounds": "9-12", "label": "ปกติ", "demand_weight": 1.0, "specialty_share": 0.15},
               {"rounds": "13-14", "label": "ใกล้ปิดตลาด", "demand_weight": 0.7, "specialty_share": 0.15},
               {"rounds": "15", "label": "รอบสุดท้าย", "demand_weight": 0.5, "specialty_share": 0.1}]


# MOCK_STYLE=real: เทียบตลาดแข่งด่าน 2 จริง (mock_real_rounds.json จาก log 18 พ.ย.) · RFQ จริงทุกรอบ (ผู้ซื้อ กระสอบ สเปก) ·
# จำนวนซองคู่แข่งต่อ RFQ ตามจริง · ราคาคู่แข่ง ~ ราคาตัดจริงของประเภทนั้นในรอบนั้น (เช่น Specialty ×1.03 → ×0.95) ·
# ไม่มีล็อตไหนผ่านสเปก = ไม่มีคู่แข่ง (แบบบางกอกบลูม) · 15 รอบ (ด่าน 3) = ยืดรอบจริง 8 รอบตามสัดส่วนเวลา
# ปรับให้ซื้อได้ใกล้จริง: ซองคู่แข่ง 1.5 กระสอบ · ราคาแกว่ง SD 0.02 → Commercial 93% (จริง 92%) · Instant 91% (จริง 85%)
REAL_CEIL = {"1 ดอยช้างโรสเตอร์": 1.24, "2 บางกอกบลูม": 1.18, "3 สยามคอมเมิร์ซ": 1.047, "4 ชุมพรคั่วบด": 1.071,
             "5 อินสแตนท์ไทย": 0.942, "6 ทรีอินวันฟู้ดส์": 0.961}     # เพดานจากตลาดฝึก (ใช้เป็นขีดบนเท่านั้น)
_REAL = None


def real_data() -> dict:
    global _REAL
    if _REAL is None:
        _REAL = json.loads((HERE / "mock_real_rounds.json").read_text(encoding="utf-8"))
    return _REAL


def real_idx(n: int, total: int) -> int:
    k = len(real_data()["rounds"])
    return min(k - 1, round((n - 1) * (k - 1) / max(total - 1, 1)))


def stage3() -> bool:
    import os
    return os.environ.get("MOCK_STAGE") == "3"


def cal_row(cal: list, n: int) -> dict:
    for c in cal:
        lo, hi = int(c["rounds"].split("-")[0]), int(c["rounds"].split("-")[-1])
        if lo <= n <= hi:
            return c
    return cal[-1]


def competitor_ratio(rng: random.Random, t: str, late: bool) -> float:
    u = rng.random()
    if _style() == "competition":
        b = BASE_COMP[t] - (0.04 if late else 0.0)
        return rng.gauss(b, 0.025)
    base = {"COMMERCIAL": 0.985, "INSTANT": 0.95, "SPECIALTY": 1.15}[t]
    if u < 0.35:
        r = 1.00                                         # starter
    elif u < 0.65:
        r = rng.gauss(base, 0.01)                        # รู้ประเภท
    elif u < 0.85:
        r = rng.gauss(base - 0.02, 0.01)                 # ตัดราคา
    else:
        r = rng.uniform(0.90, 1.12)                      # มั่ว
    return r - (0.012 if late else 0.0)


class FakeMarket:
    def __init__(self, seed: int, noise: float = 0.3):
        self.rng = random.Random(seed)
        r = self.rng
        self.lots, self.true = [], {}
        self.rules = dict(RULES, timeline=dict(RULES["timeline"], rounds=15 if stage3() else RULES["timeline"]["rounds"]))
        self.cal = CALENDAR_S3 if stage3() else CALENDAR
        for i in range(1, 6 if stage3() else 5):
            true = {"defect_pct": round(r.choice([r.uniform(0.3, 3.2), r.uniform(4.5, 7.4), r.uniform(6.5, 10)]), 2),
                    "moisture_pct": round(r.uniform(10.5, 13.2), 2), "screen": r.randint(13, 18)}
            if stage3() and i == 1:          # ด่าน 3: มีล็อตเกรด Specialty อย่างน้อย 1 ล็อต (ให้ทดสอบการเก็บรอเทศกาล)
                true = {"defect_pct": round(r.uniform(0.8, 2.4), 2), "moisture_pct": round(r.uniform(10.5, 11.9), 2),
                        "screen": r.randint(16, 18)}
            sample = {"defect_pct": round(max(0, true["defect_pct"] + r.gauss(0, noise)), 2),
                      "moisture_pct": round(true["moisture_pct"] + r.gauss(0, noise * 0.6), 2),
                      "screen": true["screen"] + (r.choice([-1, 1]) if r.random() < noise * 0.4 else 0)}
            lid = f"LOT-T13-{i}"
            kg = r.choice([480, 540, 600]) if stage3() else r.choice([420, 480, 540, 600])
            self.lots.append({"lot_id": lid, "kg_total": kg, "kg_remaining": kg, "kg_in_open_offers": 0,
                              "kg_available": kg, "sample": sample})
            self.true[lid] = {"q": true, "tv": appraisal.true_value(RULES, true)}
        total = sum(l["kg_total"] for l in self.lots)
        n = self.rules["timeline"]["rounds"]
        self.cap = math.ceil(RULES["round_capacity_factor"] * total / n / 60) * 60
        self.phase, self.round_no, self.calls = "APPRAISAL", 0, 0
        self.appraised, self.open, self.rfqs, self.last = None, [], [], None
        self.revenue, self.kg_sold = 0.0, 0
        self.kg_early = 0          # ขายได้ใน R1–R2 (วัดเป้า 'ขายออกตั้งแต่สองรอบแรก')
        self.spec_mis_real = 0     # SPEC_MISMATCH ในรอบจริง (กระสอบ) · วัดว่าการตรวจสเปกทำให้ส่งผิดเพิ่มไหม
        # รอบซ้อม (ด่าน 3 มี P1–P2 · ไม่นับคะแนน ไม่เสียของ) · MOCK_PRACTICE = จำนวนรอบซ้อม (ค่าเริ่ม 2 ถ้าด่าน 3)
        self.n_practice = int(os.environ.get("MOCK_PRACTICE", "2" if stage3() else "0"))
        self.practice = 0          # รอบซ้อมที่กำลังเปิด (0 = รอบจริง)

    # ---------- API ----------
    def calendar(self):
        return {"rules": self.rules, "calendar": self.cal}

    def appraise(self, items):
        self.appraised = items
        return {"ok": True}

    def call(self, method, path, json=None, params=None):
        if path == "/v1/version":
            return {"mode": "mock"}
        if path == "/v1/sandbox/reveal" and self.phase == "CLOSED":
            return {"lots": [{"lot_id": l["lot_id"], "true": self.true[l["lot_id"]]["q"], "sample": l["sample"]}
                             for l in self.lots], "score": self.score()}
        raise MarketError(404, {"error": {"code": "NOT_FOUND", "message": path}})

    def state(self):
        self.calls += 1
        if self.phase == "APPRAISAL" and (self.appraised or self.calls > 2):
            self._open(1, practice=1 if self.n_practice else 0)
        elif self.phase == "ROUND_OPEN" and (self.open or self.calls > 3) and self.calls > 1:
            self._clear()
            if self.practice:
                k = self.practice
                self._open(1, practice=k + 1 if k < self.n_practice else 0)
            elif self.round_no >= self.rules["timeline"]["rounds"]:
                self.phase = "CLOSED"
            else:
                self._open(self.round_no + 1)
        return self._state()

    def offer_batch(self, offers, replace_existing=True):
        if self.phase != "ROUND_OPEN":
            raise MarketError(409, {"error": {"code": "ROUND_CLOSED", "message": "no round"}})
        lots = {l["lot_id"]: l for l in self.lots}
        rfqs = {r["rfq_id"]: r for r in self.rfqs}
        used, total = {}, 0
        for o in offers:
            if o["kg"] % 60 or o["kg"] <= 0 or o["rfq_id"] not in rfqs or o["lot_id"] not in lots:
                raise MarketError(400, {"error": {"code": "BATCH_REJECTED", "message": f"bad {o}"}})
            if o["kg"] > rfqs[o["rfq_id"]]["kg"] or not (0 < o["price_per_kg"] <= 1000):
                raise MarketError(400, {"error": {"code": "BATCH_REJECTED", "message": f"bad {o}"}})
            used[o["lot_id"]] = used.get(o["lot_id"], 0) + o["kg"]
            total += o["kg"]
        if any(used[i] > lots[i]["kg_remaining"] for i in used) or total > self.cap:
            raise MarketError(400, {"error": {"code": "BATCH_REJECTED", "message": "over remaining/capacity"}})
        self.open = [{**o, "round_id": self.rfqs[0]["rfq_id"].split("-")[0]} for o in offers]
        return {"offers": self.open}

    def offer(self, o):
        raise MarketError(400, {"error": {"code": "NOT_IN_MOCK", "message": "single offers not simulated"}})

    # ---------- ภายใน ----------
    def _rid(self):
        return f"P{self.practice}" if self.practice else f"R{self.round_no}"

    def _open(self, n, practice=0):
        r = self.rng
        self.phase, self.round_no, self.calls, self.open = "ROUND_OPEN", n, 0, []
        self.practice = practice           # รอบซ้อมใช้ RFQ แบบ R1 (ปฏิทินปกติ)
        row = cal_row(self.cal, n)
        w, spec_share = row["demand_weight"], row["specialty_share"]
        self.rfqs = []
        if _style() == "real":
            fest = "เทศกาล" in (row.get("label") or "")
            for i, t in enumerate(real_data()["rounds"][real_idx(n, self.rules["timeline"]["rounds"])], 1):
                bags = max(1, round(t["bags"] * w * (_env_f("FEST_DEMAND", 1.6) if fest and t["buyer_type"] == "SPECIALTY" else 1.0)))
                self.rfqs.append({"rfq_id": f"{self._rid()}-{i:02d}", "buyer": t["buyer"], "buyer_id": t["buyer"][:1],
                                  "buyer_type": t["buyer_type"], "kg": bags * 60, "bags": bags, "spec": dict(t["spec"]),
                                  "_ceil": REAL_CEIL.get(t["buyer"], 1.0) * r.gauss(1, 0.01), "_offers": t["offers"]})
            return
        for i in range(1, 9):
            pool = BUYERS if spec_share else BUYERS[1:]
            b = r.choice(pool)
            if stage3():                     # ด่าน 3: Specialty มาทุกรอบตามสัดส่วนในปฏิทิน
                b = BUYERS[0] if r.random() < spec_share else r.choice(BUYERS[1:])
            bags = int(r.randint(6, 15) * w)
            self.rfqs.append({"rfq_id": f"{self._rid()}-{i:02d}", "buyer": b[1], "buyer_id": b[0], "buyer_type": b[2],
                              "kg": bags * 60, "bags": bags, "spec": dict(SPEC[b[2]]),
                              "_ceil": b[3] * r.gauss(1, 0.015)})

    def _clear(self):
        r, n = self.rng, self.rules["timeline"]["rounds"]
        late = self.round_no >= n - 2
        fest = "เทศกาล" in (cal_row(self.cal, self.round_no).get("label") or "")
        mine = {(o["rfq_id"], o["lot_id"]): o for o in self.open}
        results, summary = [], []
        lots = {l["lot_id"]: l for l in self.lots}
        for rfq in self.rfqs:
            t, ceil = rfq["buyer_type"], rfq["_ceil"]
            crowd = (CROWD_COMP if _style() == "competition" else CROWD)[t] + (0.6 if late else 0.0)
            if fest and t == "SPECIALTY":
                crowd *= _env_f("FEST_CROWD", 1.0)
            elig = [self.true[i]["tv"] for i, x in self.true.items()
                    if x["q"]["defect_pct"] <= rfq["spec"]["max_defect_pct"] and x["q"]["moisture_pct"] <= rfq["spec"]["max_moisture_pct"]
                    and (rfq["spec"]["min_screen"] is None or x["q"]["screen"] >= rfq["spec"]["min_screen"])]
            top_tv = max(elig) if elig else 110.0      # คู่แข่งได้ล็อตชุดเดียวกัน → ราคาคิดจากล็อตที่ผ่านสเปก
            if _style() == "real":
                k = round(rfq["_offers"] * _env_f("REAL_BAGS_PER_OFFER", 1.5) * (_env_f("FEST_CROWD", 1.0) if fest and t == "SPECIALTY" else 1.0))
                if not elig:
                    k = 0
                base = real_data()["clear"][t][real_idx(self.round_no, n)] or 1.0
                book = [(r.gauss(base, _env_f("REAL_SD", 0.02)), 60, None) for _ in range(k)]
            else:
                book = [(competitor_ratio(r, t, late), 60, None) for _ in range(int(rfq["bags"] * crowd))]
            for (rid, lid), o in mine.items():
                if rid != rfq["rfq_id"]:
                    continue
                q = self.true[lid]["q"]
                sp = rfq["spec"]
                if not (q["defect_pct"] <= sp["max_defect_pct"] and q["moisture_pct"] <= sp["max_moisture_pct"]
                        and (sp["min_screen"] is None or q["screen"] >= sp["min_screen"])):
                    results.append({**o, "status": "SPEC_MISMATCH", "filled_kg": 0})
                    if not self.practice:
                        self.spec_mis_real += o["kg"] // 60
                    continue
                book.append((o["price_per_kg"] / self.true[lid]["tv"] + r.uniform(0, 1e-6), o["kg"], o))
            book.sort(key=lambda x: x[0])
            left, bought, prices = rfq["kg"], 0, []
            for ratio, kg, o in book:
                if ratio > ceil:
                    if o:
                        results.append({**o, "status": "ABOVE_LIMIT", "filled_kg": 0})
                    continue
                fill = min(kg, left)
                left -= fill
                bought += fill
                if fill:
                    prices.append(o["price_per_kg"] if o else ratio * top_tv)
                if o:
                    st = "ACCEPTED" if fill == kg else ("PARTIAL" if fill > 0 else "OUTBID")
                    results.append({**o, "status": st, "filled_kg": fill})
                    if fill:
                        if not self.practice:          # รอบซ้อม: ไม่เสียของ ไม่ได้เงิน
                            self.revenue += fill * o["price_per_kg"]
                            self.kg_sold += fill
                            if self.round_no <= 2:
                                self.kg_early += fill
                            lots[o["lot_id"]]["kg_remaining"] -= fill
            summary.append({"rfq_id": rfq["rfq_id"], "buyer": rfq["buyer"], "buyer_type": t, "wanted_kg": rfq["kg"],
                            "bought_kg": bought, "offers": len(book),
                            "price_min": round(min(prices), 2) if prices else None,
                            "price_max": round(max(prices), 2) if prices else None,
                            "price_avg": round(sum(prices) / len(prices), 2) if prices else None})
        for l in self.lots:
            l["kg_available"] = l["kg_remaining"]
            l["kg_in_open_offers"] = 0
        self.last = {"round_id": self._rid(), "kind": "practice" if self.practice else "real", "my_offers": results, "market_summary": summary}
        self.open = []

    def _state(self):
        rnd = None
        if self.phase in ("ROUND_OPEN",):
            label = cal_row(self.cal, self.round_no)["label"]
            rnd = {"round_id": f"R{self.round_no}", "kind": "real", "number": self.round_no,
                   "of": self.rules["timeline"]["rounds"], "counts_for_score": True, "calendar": label}
            if self.practice:
                rnd = {"round_id": self._rid(), "kind": "practice", "number": self.practice,
                       "of": self.n_practice, "counts_for_score": False, "calendar": "ปกติ"}
        used = sum(o["kg"] for o in self.open)
        lots = []
        for l in self.lots:
            inopen = sum(o["kg"] for o in self.open if o["lot_id"] == l["lot_id"])
            lots.append({**l, "kg_in_open_offers": inopen, "kg_available": l["kg_remaining"] - inopen})
        return {"market": "mock", "phase": self.phase, "paused": False, "round": rnd, "seconds_left": 200,
                "lots": lots, "rfqs": [{k: v for k, v in x.items() if not k.startswith("_")} for x in self.rfqs]
                if self.phase == "ROUND_OPEN" else [],
                "my_open_offers": [dict(o) for o in self.open], "round_capacity_kg": self.cap,
                "capacity_left_kg": self.cap - used, "appraisal_submitted": self.appraised is not None,
                "last_results": self.last,
                "standings": {"revenue_thb": round(self.revenue, 2), "kg_sold": self.kg_sold,
                              "kg_remaining": sum(l["kg_remaining"] for l in self.lots),
                              "kg_total": sum(l["kg_total"] for l in self.lots)},
                "salvage_ratio": 0.8}

    def score(self):
        tot = sum(l["kg_total"] * self.true[l["lot_id"]]["tv"] for l in self.lots)
        rem = sum(l["kg_remaining"] * self.true[l["lot_id"]]["tv"] for l in self.lots)
        pr = (self.revenue + 0.8 * rem) / tot
        errs = []
        for it in self.appraised or []:
            tv = self.true[it["lot_id"]]["tv"]
            errs.append(abs(it["est_value_per_kg"] - tv) / tv)
        mape = sum(errs) / len(errs) if errs else None
        return {"pr": round(pr, 4), "mape": round(mape, 4) if mape is not None else None}


class StopTest(BaseException):
    """หยุดลูป --forever ในการทดสอบ (main จับแค่ Exception)"""


class FakeSandbox(FakeMarket):
    """จำลองตลาดฝึกที่มีปุ่มข้ามช่วง/เริ่มใหม่: ช่วงจะไม่เดินเองเลย ต้องกด advance เท่านั้น"""

    def __init__(self, seed, noise=0.3, max_games=2):
        super().__init__(seed, noise)
        self.seed0, self.noise, self.max_games = seed, noise, max_games
        self.games, self.advances, self.resets, self.n_calls, self.scores = 1, 0, 0, 0, []

    def state(self):
        self.n_calls += 1
        if self.n_calls > 3000:
            raise StopTest("agent ไม่กดข้ามช่วง (ค้าง)")
        s = self._state()
        s["market"] = "sandbox"
        return s

    def call(self, method, path, json=None, params=None):
        if path == "/v1/version":
            return {"mode": "sandbox"}
        if path == "/v1/sandbox/advance" and method == "POST":
            self.advances += 1
            if self.phase == "APPRAISAL":
                self._open(1)
            elif self.phase == "ROUND_OPEN":
                self._clear()
                if self.round_no >= self.rules["timeline"]["rounds"]:
                    self.phase = "CLOSED"
                else:
                    self._open(self.round_no + 1)
            return {"ok": True}
        if path == "/v1/sandbox/reset" and method == "POST":
            self.scores.append(self.score())
            self.resets += 1
            if self.games >= self.max_games:
                raise StopTest("ครบจำนวนเกมที่ทดสอบ")
            self.games += 1
            fresh = FakeMarket(self.seed0 + self.games, self.noise)
            for k in ("lots", "true", "cap", "phase", "round_no", "appraised", "open", "rfqs", "last",
                      "revenue", "kg_sold"):
                setattr(self, k, getattr(fresh, k))
            return {"ok": True}
        return super().call(method, path, json, params)


def run(seeds: list[int], noise: float) -> list[dict]:
    import main as agent_main
    logs = Path(tempfile.mkdtemp(prefix="mock-v2-"))
    agent_main.LOGS = logs
    agent_main.time.sleep = lambda s: None
    out = []
    for s in seeds:
        m = FakeMarket(s, noise)
        agent_main.play(m, None, forever=False)
        out.append({"seed": s, **m.score(), "sold_pct": round(m.kg_sold / sum(l["kg_total"] for l in m.lots) * 100),
                    "early_bags": m.kg_early // 60, "spec_mis": m.spec_mis_real})
    out.append({"logs": str(logs)})
    return out


def main():
    n = int(sys.argv[sys.argv.index("--seeds") + 1]) if "--seeds" in sys.argv else 6
    noise = float(sys.argv[sys.argv.index("--noise") + 1]) if "--noise" in sys.argv else 0.3
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        res = run(list(range(101, 101 + n)), noise)
    print(f"ตลาดจำลอง (ค่าสมมติ) · {n} seed · noise {noise}")
    for r in res[:-1]:
        print(f"  seed {r['seed']}: PR {r['pr']:.4f} · ขาย {r['sold_pct']}% · MAPE {r['mape']}")
    prs = [x["pr"] for x in res[:-1]]
    print(f"เฉลี่ย v2: PR {sum(prs) / len(prs):.4f} · ต่ำสุด {min(prs):.4f} · log: {res[-1]['logs']}")


if __name__ == "__main__":
    main()

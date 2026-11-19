"""Decide this round's offers — ModEngi v2 (PIPELINE.md).

ลำดับต่อรอบ:
  1. MarketModel   อ่านผลทั้งเกม → ช่วงเพดาน/จุดตัด/ความมั่นใจ ต่อผู้ซื้อ (market_model.py)
  2. classify      จัดล็อต UNSELLABLE/RISKY/HIGH/NORMAL/LOW + cliff risk (inventory.py)
  3. phase+scenario ช่วงเกม + สถานการณ์ตลาดต่อประเภท (playbook.py)
  4. budget        กระสอบรอบนี้ = ของเหลือ × (w_now ÷ Σw รอบที่เหลือ) × pace · บีบด้วย capacity
  5. candidates    คู่ (ล็อต, RFQ) ที่ผ่านสเปกแบบเว้นระยะ + ราคาเป้า + คะแนนโอกาส
  6. allocate      สุ่มถ่วงคะแนน · ล็อตทางเลือกน้อยก่อน · ส่วนต่อ RFQ ตามสถานการณ์
  7. ladder        บันไดราคา + ส่วนหยั่ง + สุ่มเล็กน้อย + เลี่ยงเลขกลม · พื้นราคา
  8. guard         ตรวจทุกซองก่อนส่ง (ไม่เชื่อตัวเลขจาก LLM หรือจากโค้ดส่วนอื่น)

ถ้าส่วนไหนพัง main.py จะใช้ fallback_plan() (ตัวคูณ prior ล้วน) แทน — agent ไม่หยุด
"""
import math
import os
import random
from dataclasses import dataclass, field

import flags
import playbook as pb
from inventory import P_MIN, classify, pass_prob, spec_ok
from market_model import PRIOR_TYPE, MarketModel

BAG = 60
MIN_RATIO, MAX_RATIO = 0.84, 1.40     # guard ชั้นสุดท้าย (เทียบกับ TV ที่ใช้ตั้งราคา)
SMALL_STOCK = 12                      # กระสอบที่ขายได้เหลือ ≤ นี้ = ของน้อยมาก
RISKY_DROP = 10.0                    # % ที่ TV อาจร่วงถ้าค่าจริงข้ามขอบ → เกินนี้ตั้งราคาเผื่อ (ขอบ defect 7/15, moisture 15)
PREMIUM_TYPES = ("SPECIALTY", "COMMERCIAL")
TYPE_RANK = {"SPECIALTY": 0, "COMMERCIAL": 1, "INSTANT": 2}


@dataclass
class Context:
    rules: dict
    calendar: list
    tv: dict
    rng: random.Random
    memory: object = None
    llm: object = None
    seconds_left: float = 999
    notes: list = field(default_factory=list)
    learned: dict = field(default_factory=dict)
    adjust: dict = field(default_factory=dict)     # จาก LLM: type -> ±0.03 (บีบแล้ว)
    volume: float = 1.0                            # จาก LLM: hold 0.77 / normal 1 / push 1.23
    meta: dict = field(default_factory=dict)       # ข้อมูลไว้ลง log


def rounds_left(state: dict, ctx: Context) -> int:
    rnd, total = state["round"], ctx.rules["timeline"]["rounds"]
    return total if rnd["kind"] == "practice" else total - rnd["number"] + 1


def _weighted_order(items: list, weight, rng: random.Random) -> list:
    keyed = [(rng.random() ** (1 / max(weight(x), 1e-6)), x) for x in items]
    return [x for _, x in sorted(keyed, key=lambda k: -k[0])]


def _avoid_round(price: float) -> float:
    """เลี่ยงราคาเลขกลม (.00 / .50) ที่คนอื่นมักตั้ง"""
    p = round(price, 2)
    cents = round(p * 100) % 50
    return round(p - 0.03, 2) if cents == 0 else p


PROBE_OFFSETS = [-0.03, 0.0, 0.03, 0.06]     # รอบซ้อม: กระจายราคารอบราคาเป้า เพื่อหาเพดาน/จุดตัดจริง


def _env_share() -> float:
    try:
        return float(os.environ.get("SPEC_MAX_SHARE", "0.4"))
    except ValueError:
        return 0.4


def pb_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def pb_market_floor() -> float:
    try:
        return max(0.81, float(os.environ.get("MARKET_FLOOR", "0.82")))
    except ValueError:
        return 0.82


def _sell_shift(t: str) -> float:
    try:
        return float(os.environ.get(f"SELL_SHIFT_{t}", "0"))
    except ValueError:
        return 0.0


def is_practice(state: dict) -> bool:
    rnd = state.get("round") or {}
    return rnd.get("kind") == "practice" or rnd.get("counts_for_score") is False


def practice_probe(state: dict, ctx: Context, model: MarketModel, inv: dict) -> list[dict]:
    """รอบซ้อม (ไม่นับคะแนน · ไม่เสียของ): เสนอ RFQ ละ 1 กระสอบ ไล่หลายราคา (−0.03 … +0.06 จากเป้า)
    ได้ข้อมูลเพดาน (ABOVE_LIMIT) และราคาที่ชนะได้ (ACCEPTED/OUTBID) ของตลาดจริงก่อนรอบ 1 ฟรี
    Specialty ก่อน · ล็อตที่ผ่านสเปก (โอกาสผ่าน ≥ P_MIN) และ TV สูงก่อน · ไม่เกิน capacity"""
    room = state["capacity_left_kg"] // BAG if state.get("capacity_left_kg") is not None else 8
    lots = {l["lot_id"]: l for l in state["lots"]}
    used = {i: 0 for i in lots}
    rfqs = sorted(state["rfqs"], key=lambda r: (TYPE_RANK.get(r["buyer_type"], 3), ctx.rng.random()))
    out, i = [], 0
    for rfq in rfqs:
        if room <= 0:
            break
        t = rfq["buyer_type"]
        ok = [l for lid, l in lots.items()
              if inv[lid]["cls"] != "UNSELLABLE" and l["kg_available"] // BAG - used[lid] >= 1
              and not model.spec_banned(lid, t, rfq["spec"]) and pass_prob(l["sample"], rfq["spec"]) >= P_MIN]
        if not ok:
            continue
        lot = max(ok, key=lambda l: ctx.tv[l["lot_id"]])
        tg = model.target(rfq.get("buyer", ""), t, rfq["spec"])
        off = PROBE_OFFSETS[i % len(PROBE_OFFSETS)]
        i += 1
        r = max(pb.floor_for(t, "early"), tg["ratio"] + off)
        basis = ctx.tv[lot["lot_id"]]
        price = _avoid_round(r * basis)
        out.append({"lot_id": lot["lot_id"], "rfq_id": rfq["rfq_id"], "bags": 1, "price": price, "basis": basis,
                    "meta": {"type": t, "ratio": round(price / basis, 4), "rung": f"probe{off:+.2f}",
                             "src": "practice-probe", "conf": tg["conf"], "cls": inv[lot["lot_id"]]["cls"]}})
        used[lot["lot_id"]] += 1
        room -= 1
    return out


def plan(state: dict, ctx: Context) -> list[dict]:
    rules = ctx.rules
    total = rules["timeline"]["rounds"]
    model = MarketModel(ctx.memory, ctx.learned)
    model.set_lots(state["lots"], ctx.tv)
    inv = classify(rules, state["lots"], state["rfqs"], model.spec_banned)
    if is_practice(state) and os.environ.get("PRACTICE_PROBE", "1") != "0":
        rows = practice_probe(state, ctx, model, inv)
        ctx.basis = {r["lot_id"]: r["basis"] for r in rows}
        ctx.meta = {"phase": "practice", "code": flags.CODE_VERSION, "budget_bags": len(rows), "probe": True,
                    "lots": {i: {"cls": v["cls"], "edges": v["risk"]["edges"], "drop_pct": v["risk"]["drop_pct"]}
                             for i, v in inv.items()}}
        ctx.model_summary = model.summary()
        ctx.notes.append(f"practice round: probe {len(rows)} RFQs x 1 bag")
        return rows
    ph = pb.phase(state, total)
    cal = pb.calendar_weights(ctx.calendar, total)
    n_now = state["round"].get("number") or 1
    sc = pb.scenarios(model, ph, cal.get(n_now, {"w": 1.0}))
    P = pb.phase_params(ph)

    # ---------- 4. budget ----------
    share = pb.round_share(state, cal, total)
    avail = {l["lot_id"]: l["kg_available"] // BAG for l in state["lots"] if inv[l["lot_id"]]["cls"] != "UNSELLABLE"}
    # เก็บล็อตเกรด Specialty ไว้ขายช่วงเทศกาล (สไลด์วันที่ 20 หน้า 5) · FESTIVAL_HOLD = สัดส่วนที่เก็บ (ค่าเริ่ม 0 = ไม่เก็บ)
    hold = pb_env("FESTIVAL_HOLD", 0.0)
    fest_rounds = [k for k, v in cal.items() if "เทศกาล" in (v.get("label") or "")]
    if hold > 0 and fest_rounds and n_now < min(fest_rounds):
        for l in state["lots"]:
            lid = l["lot_id"]
            if lid in avail and inv[lid]["cls"] == "HIGH":
                keep = math.ceil(hold * (l.get("kg_total") or l["kg_available"]) / BAG)
                if avail[lid] > 0 and keep:
                    ctx.notes.append(f"festival hold {lid}: keep {min(keep, avail[lid])} bags until R{min(fest_rounds)}")
                avail[lid] = max(0, avail[lid] - keep)
    sellable = sum(avail.values())
    pace = P["pace"] * ctx.volume * max(s["pace"] for k, s in sc.items() if k != "_global")
    # แรงกดดันกระสอบ (ข้อ 4.8): ของเหลือเทียบกับ capacity ของรอบที่เหลือ
    cap_b = pb.capacity_bags(state, total)
    pres, pmode = pb.pressure(sellable, cap_b, rounds_left(state, ctx), ph)
    PM = pb.PRESSURE_MODES[pmode]
    pace *= PM["pace"]
    floor_phase = "late" if PM.get("late_floor") and ph in ("early", "mid") else ph

    def floor_of(t, tg=None):
        # มีราคาตลาดจริง → พื้น = MARKET_FLOOR (0.82 เหนือของเหลือ 0.80) · พื้นเดิม (Specialty 1.00) มาจากตลาดฝึก
        # ด่าน 2: ดอยช้างชนะที่ ×0.95–0.98 → พื้นเดิมทำให้แพ้ทุกรอบ
        if tg is not None and str(tg.get("source", "")).startswith("market"):
            return pb_market_floor()
        return pb.floor_for(t, floor_phase) + (PM["floor_add"] if ph != "final" else 0.0)

    # งบตามอัตราขายได้จริง (pace3 · 18 พ.ย.): ซองขายได้แค่ ~60% (ที่เหลือแพ้ราคา/เกินเพดาน) ถ้าเสนอตามส่วนเฉลี่ย
    # ของจะกองไปท้ายเกมแล้วติดเพดานกระสอบต่อรอบ (TestNew: ใช้ capacity แค่ 80% · เกม 6 ล็อตของเหลือ 0.024 PR)
    # → เสนอ = กระสอบที่อยากให้ขายได้ ÷ อัตราขายได้ · ถ้าของเหลือ ÷ อัตราขายได้ เกิน 85% ของ capacity รอบที่เหลือ → ใช้ capacity เต็ม
    pace_on = os.environ.get("PACE_BY_SELLRATE", "1") != "0"          # 0 = งบแบบเดิม (spec2) ไว้ทดลองเทียบ
    sr = max(0.4, min(1.0, model.sell_rate())) if pace_on else 1.0
    r_left = rounds_left(state, ctx)
    at_risk = pace_on and model.offered_bags >= 4 and sellable / sr > 0.85 * cap_b * r_left
    # PACE_MODE=midpush (ทดลอง): ผล pace3 vs เดิม → ขายเพิ่มช่วงต้นได้ราคาต่ำลง (×1.01 vs ×1.04) ·
    # ช่วงท้ายทั้งสองแบบขาย ~10 กระสอบที่ ×0.93–0.95 ขณะช่วงกลางได้ ×0.97–0.99
    # → ช่วงต้นขายแบบเดิม (ให้โมเดลเรียนราคา) · ช่วงกลางใช้ capacity เต็ม (ขายตอนราคายังดี) · ช่วงท้าย/สุดท้ายตาม pace3
    if pace_on and os.environ.get("PACE_MODE", "sellrate") == "midpush":
        if ph == "early":
            sr, at_risk = 1.0, False
        elif ph == "mid":
            at_risk = sellable > 0
    # 18 พ.ย. หลังแข่ง: capacity ที่ไม่ใช้หายไปเลย (ด่าน 2 เสีย 10 กระสอบใน R1–R2 → ค้าง 5) → ค่าเริ่มใช้ capacity เต็มทุกรอบ
    full_cap = os.environ.get("FULL_CAPACITY", "1") != "0"
    if full_cap:
        at_risk = True
    # ราคาชัวร์ทุกรอบ (ค่าเริ่ม MKT_TIGHT=0) · ทดสอบ 18 พ.ย.: ตั้งใกล้ราคาตลาดตอน capacity เหลือ (MKT_TIGHT=0.6)
    # แย่กว่า — replay ตลาดแข่ง PR 0.931 vs 0.946 · ตลาดจำลองแบบแข่ง 0.928 vs 0.931 (แพ้รอบเดียว = capacity หาย)
    tight = ph in ("late", "final") or sellable > pb_env("MKT_TIGHT", 0.0) * cap_b * max(r_left, 1)
    if ph == "final" or at_risk:
        total_bags = sellable
    else:
        total_bags = min(sellable, max(1, math.ceil(sellable * share * pace / sr))) if sellable else 0
    if state.get("capacity_left_kg") is not None:
        total_bags = min(total_bags, state["capacity_left_kg"] // BAG)
    lot_cap = {i: (a if (ph == "final" or at_risk) else min(a, max(1, math.ceil(a * share * pace * 1.5 / sr))))
               for i, a in avail.items()}
    if at_risk:
        ctx.notes.append(f"full capacity: {sellable} bags · sell rate {sr:.2f} · cap {cap_b}x{r_left} · {ph}")

    # ---------- 5. candidates ----------
    allow_plain = ph == "final"      # รอบสุดท้าย ยอมเสี่ยงล็อตชิดขอบสเปก (ของเหลือได้แค่ 0.80 อยู่แล้ว)
    # สงวนล็อตเกรด Specialty: ช่วงต้น/กลาง ถ้าตลาดมี Specialty (รอบนี้หรือรอบก่อน) ไม่ขายล็อต HIGH ให้ประเภทอื่น
    # (Specialty จ่าย ~1.18 · Commercial ~1.00) · ปล่อยเมื่อช่วงท้าย/รอบสุดท้าย หรือของล้น capacity
    specialty_seen = any(r["buyer_type"] == "SPECIALTY" for r in state["rfqs"]) or bool(model.fill.get("SPECIALTY"))
    reserve_high = (specialty_seen and ph in ("early", "mid") and pmode != "flood"
                    and os.environ.get("RESERVE_SPECIALTY", "0") != "0")   # ค่าเริ่มปิด: ตลาดแข่ง Specialty ไม่ได้จ่ายแพงกว่า       # ปิดได้ใน .env เพื่อทดลองเทียบ
    targets, cands = {}, []
    ctx.basis = {}
    for lot in state["lots"]:
        lid, info = lot["lot_id"], inv[lot["lot_id"]]
        if lid not in avail or avail[lid] < 1:
            continue
        ok_types = set(info["types"]) | (set(info["types_plain"]) if allow_plain else set())
        # TV ที่ใช้ตั้งราคา: ล็อตชิดขอบที่ร่วงแรง (≥ RISKY_DROP%) ใช้ค่ากลางระหว่าง TV กับ tv_lo
        # ratio ทุกตัว (เป้า/พื้น/ที่เรียนรู้) เทียบกับ basis นี้ → หน่วยเดียวกันทั้งระบบ
        basis = ctx.tv[lid]
        if info["cls"] == "RISKY" and info["risk"]["drop_pct"] >= RISKY_DROP:
            basis = round((ctx.tv[lid] + info["risk"]["tv_lo"]) / 2, 2)
        ctx.basis[lid] = basis
        for rfq in state["rfqs"]:
            t = rfq["buyer_type"]
            if t not in ok_types or model.spec_banned(lid, t, rfq["spec"]) or not spec_ok(lot["sample"], rfq["spec"]):
                continue
            if reserve_high and info["cls"] == "HIGH" and t != "SPECIALTY":
                continue
            pp = pass_prob(lot["sample"], rfq["spec"])       # โอกาสผ่านสเปก RFQ นี้ด้วยคุณภาพจริง
            if not allow_plain and pp < P_MIN:
                continue
            key = (rfq.get("buyer", ""), t)
            if key not in targets:
                targets[key] = model.target(*key, spec=rfq["spec"], tight=tight, phase=ph)
            tg = targets[key]
            ratio = tg["ratio"] + sc[t]["shift"] + ctx.adjust.get(t, 0.0)
            if tg["source"].startswith("market"):            # ราคาตลาดจริง = เพดานที่ยังขายออก → ไม่บวกเพิ่ม
                ratio = min(ratio, tg["ratio"])
            ratio = min(ratio, tg["cap"])
            floor = floor_of(t, tg)
            if ratio < floor:
                # ไม่ "เก็บของ" เฉยๆ: เสนอที่พื้นราคา (ชนะได้ = ราคาที่เรายอมรับ · แพ้ = ได้ข้อมูล · ไม่เสียอะไร)
                ctx.notes.append(f"floor {t} {rfq['rfq_id']}: target {ratio:.3f} -> {floor}")
                ratio = floor
            p = model.p_sell(tg, ratio)
            score = p * pp * (ratio - 0.80) * basis
            cands.append({"lot_id": lid, "rfq": rfq, "type": t, "ratio": ratio, "basis": basis, "tg": tg,
                          "score": max(score, 1e-3), "n_types": len(ok_types), "cls": info["cls"]})

    # Opportunity cost: ล็อตที่มีทางเลือกจ่ายดีกว่า ไม่ควรเทให้ประเภทที่จ่ายต่ำ → ไปรอบสอง
    best = {}
    for c in cands:
        best[c["lot_id"]] = max(best.get(c["lot_id"], 0), c["score"])
    primary = [c for c in cands if c["score"] >= 0.85 * best[c["lot_id"]]]
    secondary = [c for c in cands if c["score"] < 0.85 * best[c["lot_id"]]]

    # ---------- 6. allocate ----------
    rfq_left = {r["rfq_id"]: max(1, int(r["bags"] * sc[r["buyer_type"]]["share"])) for r in state["rfqs"]}
    if full_cap:   # ใช้ capacity เต็ม + ราคาตลาด → ไม่จำกัดส่วนต่อ RFQ (ล็อตมูลค่าสูงได้ผู้ซื้อที่จ่ายดีก่อน)
        rfq_left = {r["rfq_id"]: r["bags"] for r in state["rfqs"]}
    lot_left = dict(lot_cap)
    left = total_bags
    alloc, used = [], set()
    # SPREAD (ค่าเริ่ม 0.6): ผู้ซื้อรายเดียวได้ไม่เกิน ceil(SPREAD × งบรอบ) กระสอบ → แพ้รายเดียวไม่เสียทั้งรอบ
    #   ด่าน 2 R2: ส่ง 5/5 กระสอบให้ชุมพรรายเดียว แล้วชุมพรลดราคาตัด 1.045 → 1.003 = ขาย 0 · ไม่มีคู่อื่นแล้วยอมเกิน (รอบเติม)
    spread = pb_env("SPREAD", 0.6)   # ค่าเริ่ม 0.6 (19 พ.ย.) · 0 = ปิด
    buyer_cap = max(1, math.ceil(spread * total_bags)) if spread > 0 else None
    buyer_used = {}
    # กระจายได้เฉพาะผู้ซื้อที่ราคาไม่ต่ำกว่าผู้ซื้อดีสุดของล็อตนั้นเกิน SPREAD_GAP (ค่าเริ่ม 0.02) · ต่ำกว่านั้น = ไม่คุ้ม รอรอบเติม
    spread_gap = pb_env("SPREAD_GAP", 0.02)   # 19 พ.ย. จูนกลางคืน: 0.02 ผ่าน 2 รอบ (เดิม 0.03)
    lot_top = {}
    for c in cands:
        lot_top[c["lot_id"]] = max(lot_top.get(c["lot_id"], 0.0), c["ratio"])
    def spread_ok(c):
        return buyer_cap is None or c["ratio"] >= lot_top[c["lot_id"]] - spread_gap
    def buyer_room(c):
        if buyer_cap is None:
            return 10 ** 6
        if not spread_ok(c):
            return 0
        return buyer_cap - buyer_used.get(c["rfq"].get("buyer", ""), 0)
    def use_buyer(c, n):
        b = c["rfq"].get("buyer", "")
        buyer_used[b] = buyer_used.get(b, 0) + n
    weight = lambda c: c["score"] * (1 + 0.5 / max(c["n_types"], 1))   # ทางเลือกน้อย = ก่อน
    # FRONT_LOW (ค่าเริ่ม 0 = ปิด): ล็อตที่ขายได้แค่ผู้ซื้อราคาต่ำ (เช่น Instant) ขายก่อน
    #   ด่าน 2 ตลาดแข่ง: Instant ราคาตัดลด ×0.95 → ×0.87 ตลอดเกม · Commercial นิ่ง ×1.02–1.04 → ขายล็อตราคาตกก่อน
    fl = pb_env("FRONT_LOW", 0.0)
    if fl > 0 and ph != "final" and cands:
        lot_best = {}
        for c in cands:
            lot_best[c["lot_id"]] = max(lot_best.get(c["lot_id"], 0.0), c["ratio"])
        top_best = max(lot_best.values())
        base_w = weight
        weight = lambda c: base_w(c) * (1 + fl * (top_best - lot_best[c["lot_id"]]) / 0.10)

    # 6a. Specialty ก่อน (สไลด์ 18 หน้า 21–22: ผู้ซื้อที่จ่ายแพงได้ของดีก่อน) · RFQ Specialty ใบเล็ก (1–6 กระสอบ)
    #     → เสนอได้เต็มใบ และไม่ติดเพดานต่อล็อตของรอบ · ใบที่คะแนนดีก่อน (สุ่มถ่วง)
    spec_added = 0
    # 18 พ.ย. ตลาดแข่ง: Specialty แพ้ราคาแล้วกิน capacity ทั้งรอบ → ล็อตอื่นไม่ได้ส่ง
    # จำกัด Specialty ไม่เกิน SPEC_MAX_SHARE ของงบ (ค่าเริ่ม 0.4 · 1 = ไม่จำกัด) · ล็อตอื่นรับไม่หมด → รอบเติม (6b) ให้ Specialty เติมได้
    spec_cap = total_bags if _env_share() >= 1 else max(1, int(total_bags * _env_share()))
    # มีราคาตลาดแล้ว → ไม่ให้ Specialty ได้คิวก่อน (ให้คะแนนจริงตัดสิน: ผู้ซื้อที่รับราคาสูงกว่าได้ของ)
    spec_first = [c for c in cands if c["type"] == "SPECIALTY" and not c["tg"]["source"].startswith("market")]
    for c in _weighted_order(spec_first, weight, ctx.rng):
        if left <= 0 or spec_added >= spec_cap:
            break
        k = (c["lot_id"], c["rfq"]["rfq_id"])
        lot_room = avail[c["lot_id"]] - sum(a["bags"] for a in alloc if a["lot_id"] == c["lot_id"])
        rfq_room = c["rfq"]["bags"] - sum(a["bags"] for a in alloc if a["rfq"]["rfq_id"] == k[1])
        bags = min(lot_room, rfq_room, left, spec_cap - spec_added)
        bags = min(bags, buyer_room(c))
        if k in used or bags <= 0:
            continue
        use_buyer(c, bags)
        alloc.append({**c, "bags": bags})
        used.add(k)
        rfq_left[k[1]] = 0
        lot_left[c["lot_id"]] -= bags
        left -= bags
        spec_added += bags
    if spec_added:
        ctx.notes.append(f"specialty first {spec_added} bags")

    groups = (primary,) if (not PM["secondary"] and ph in ("early", "mid")) else (primary, secondary)
    for group in groups:
        for c in _weighted_order(group, weight, ctx.rng):
            if left <= 0:
                break
            k = (c["lot_id"], c["rfq"]["rfq_id"])
            if k in used:
                continue
            bags = min(rfq_left[c["rfq"]["rfq_id"]], lot_left[c["lot_id"]], left, buyer_room(c))
            if c["type"] == "SPECIALTY":
                bags = min(bags, spec_cap - spec_added)
            if bags <= 0:
                continue
            use_buyer(c, bags)
            alloc.append({**c, "bags": bags})
            used.add(k)
            rfq_left[c["rfq"]["rfq_id"]] -= bags
            lot_left[c["lot_id"]] -= bags
            left -= bags
            if c["type"] == "SPECIALTY":
                spec_added += bags

    # ---------- 6b. เติมให้ถึงงบ (แก้บั๊ก 18 พ.ย.: ตลาด 8 รอบ + capacity + ล็อตได้แค่ Instant → ส่งรอบละ 2 จากงบ 5) ----------
    # ส่วนต่อ RFQ (12–45%) และเพดานต่อล็อตมีไว้กระจายความเสี่ยง แต่ถ้าทำให้ส่งไม่ถึงงบ ของจะค้างจนเหลือ 0.80
    # → รอบสอง: ยอมเต็ม RFQ และเต็มล็อต จนกว่าจะถึงงบหรือไม่มีคู่ให้ส่ง · ช่วงต้น/กลางใช้แค่คู่หลัก (ผู้ซื้อจ่ายดีของล็อตนั้น)
    if left > 0 and cands:
        idx = {(a["lot_id"], a["rfq"]["rfq_id"]): a for a in alloc}
        rfq_room = {r["rfq_id"]: r["bags"] - sum(a["bags"] for a in alloc if a["rfq"]["rfq_id"] == r["rfq_id"])
                    for r in state["rfqs"]}
        lot_room = {i: avail[i] - sum(a["bags"] for a in alloc if a["lot_id"] == i) for i in avail}
        pool = cands if ph in ("late", "final") else primary
        added = 0
        # ล็อตอื่นก่อน แล้วค่อยให้ Specialty เติมส่วนที่เหลือ (capacity ไม่ว่าง)
        order = (_weighted_order([c for c in pool if c["type"] != "SPECIALTY"], weight, ctx.rng)
                 + _weighted_order([c for c in pool if c["type"] == "SPECIALTY"], weight, ctx.rng))
        passes = ([order, [c for c in order if spread_ok(c)] + [c for c in order if not spread_ok(c)]]
                  if buyer_cap is not None else [order])
        for pi, c in ((pi, c) for pi, seq in enumerate(passes) for c in seq):
            if left <= 0:
                break
            k = (c["lot_id"], c["rfq"]["rfq_id"])
            add = min(rfq_room[k[1]], lot_room[k[0]], left)
            if pi == 0 and len(passes) > 1:
                add = min(add, buyer_room(c))
            if add <= 0:
                continue
            if k in idx:
                idx[k]["bags"] += add
            else:
                idx[k] = {**c, "bags": add}
                alloc.append(idx[k])
            use_buyer(c, add)
            rfq_room[k[1]] -= add
            lot_room[k[0]] -= add
            left -= add
            added += add
        if added:
            ctx.notes.append(f"fill pass +{added} bags (budget {total_bags})")

    # ---------- 7. ladder ----------
    total_alloc = sum(a["bags"] for a in alloc)
    explore_bags = int(round(total_alloc * P["explore"] * PM["explore_mult"]))
    if PM["explore_max_bags"] is not None:
        explore_bags = min(explore_bags, PM["explore_max_bags"])
    if sellable <= SMALL_STOCK:          # ของน้อยมาก (นับกระสอบได้): ทุกกระสอบมีค่า หยั่งไม่เกิน 1 กระสอบ
        explore_bags = min(explore_bags, 1)
    ladder = PM["ladder"] or pb.LADDER
    order = list(alloc)
    ctx.rng.shuffle(order)
    out, rung_i = [], 0
    for a in order:
        tg = a["tg"]
        if (explore_bags > 0 and a["bags"] <= max(explore_bags, 1) and not tg["source"].startswith("market")
                and os.environ.get("NO_EXPLORE", "1") != "1"):
            rung, explore_bags = "explore", explore_bags - a["bags"]
            # ยิ่งไม่มั่นใจ (เช่น Specialty ที่ยังไม่มีข้อมูล) ยิ่งหยั่งไกล
            step = max(pb.EXPLORE_STEP, 0.06 * (1 - tg["conf"]))
            r = min(a["ratio"] + step, tg["explore_max"])
        else:
            off = ladder[rung_i % len(ladder)] if len(alloc) >= len(ladder) else 0.0
            rung, rung_i = f"{off:+.3f}", rung_i + 1
            r = min(a["ratio"] + off, tg["cap"])
        if tg["source"].startswith("market"):                # ราคาตลาด: ไม่ขึ้นเกินเป้า (บันได/สุ่มลงได้อย่างเดียว)
            r = min(r, a["ratio"]) - abs(ctx.rng.uniform(-pb.JITTER, pb.JITTER))
        else:
            r += ctx.rng.uniform(-pb.JITTER, pb.JITTER)
        r = max(r + _sell_shift(a["type"]), floor_of(a["type"], tg))   # SELL_SHIFT_<TYPE>: เน้นขายออก (ค่าลบ = ลดราคา)
        price = _avoid_round(r * a["basis"])
        out.append({"lot_id": a["lot_id"], "rfq_id": a["rfq"]["rfq_id"], "bags": a["bags"], "price": price,
                    "basis": a["basis"], "meta": {"type": a["type"], "ratio": round(price / a["basis"], 4),
                                                  "rung": rung, "src": tg["source"], "conf": tg["conf"],
                                                  "cls": a["cls"]}})
    ctx.meta = {"phase": ph, "share": round(share, 3), "pace": round(pace, 2), "budget_bags": total_bags, "tight": tight,
                "code": flags.CODE_VERSION, "sell_rate": round(sr, 3), "at_risk": at_risk, "planned_bags": sum(a["bags"] for a in alloc), "sellable_bags": sellable, "pressure": pres, "pressure_mode": pmode, "cap_bags": cap_b,
                "scenarios": {k: v["tags"] for k, v in sc.items()},
                "targets": {f"{b}|{t}": {"ratio": v["ratio"], "cap": v["cap"], "conf": v["conf"], "src": v["source"]}
                            for (b, t), v in targets.items()},
                "lots": {i: {"cls": v["cls"], "edges": v["risk"]["edges"], "drop_pct": v["risk"]["drop_pct"]}
                         for i, v in inv.items()},
                "banned": sorted(map(list, model.banned)), "banned_specs": dict(model.banned_specs),
                "reserve_high": reserve_high, "adjust": ctx.adjust, "volume": ctx.volume}
    ctx.model_summary = model.summary()
    return out


def guard(state: dict, ctx: Context, plan_rows: list[dict]) -> list[dict]:
    """Turn a plan into offers the market will accept."""
    lots = {l["lot_id"]: l for l in state["lots"]}
    rfqs = {r["rfq_id"]: r for r in state["rfqs"]}
    room = state["capacity_left_kg"] if state.get("capacity_left_kg") is not None else 10**9
    lot_left = {i: l["kg_available"] for i, l in lots.items()}
    rfq_left = {i: r["kg"] for i, r in rfqs.items()}
    offers, seen = [], set()
    for p in plan_rows:
        lot, rfq = lots.get(p["lot_id"]), rfqs.get(p["rfq_id"])
        if lot is None or rfq is None or (p["lot_id"], p["rfq_id"]) in seen or not spec_ok(lot["sample"], rfq["spec"]):
            ctx.notes.append(f"guard dropped {p.get('lot_id')}->{p.get('rfq_id')}")
            continue
        kg = min(int(p["bags"]) * BAG, lot_left[lot["lot_id"]], rfq_left[rfq["rfq_id"]], room) // BAG * BAG
        if kg < BAG:
            continue
        basis = p.get("basis") or ctx.tv[lot["lot_id"]]
        price = p["price"] if "price" in p else p["markup"] * ctx.tv[lot["lot_id"]]
        if not (isinstance(price, (int, float)) and math.isfinite(price)):
            continue
        price = min(max(price, MIN_RATIO * basis), MAX_RATIO * ctx.tv[lot["lot_id"]], 1000)
        offers.append({"rfq_id": rfq["rfq_id"], "lot_id": lot["lot_id"], "kg": kg, "price_per_kg": round(price, 2)})
        seen.add((p["lot_id"], p["rfq_id"]))
        lot_left[lot["lot_id"]] -= kg
        rfq_left[rfq["rfq_id"]] -= kg
        room -= kg
    return offers


def fallback_plan(state: dict, ctx: Context) -> list[dict]:
    """ใช้เมื่อ plan() พัง: ตัวคูณ prior ต่อประเภท แบ่งเท่าๆ กันแบบ starter"""
    left = rounds_left(state, ctx)
    out = []
    room = (state["capacity_left_kg"] // BAG) if state.get("capacity_left_kg") is not None else 10**6
    for lot in sorted(state["lots"], key=lambda l: -ctx.tv[l["lot_id"]]):
        a = lot["kg_available"] // BAG
        bags = a if left <= 1 else min(a, max(1, math.ceil(a / left * 1.3)))
        for rfq in sorted(state["rfqs"], key=lambda r: TYPE_RANK.get(r["buyer_type"], 3)):
            if bags <= 0 or room <= 0:
                break
            if not spec_ok(lot["sample"], rfq["spec"]):
                continue
            b = min(bags, rfq["bags"], room)
            m = PRIOR_TYPE.get(rfq["buyer_type"], {"start": 0.95})["start"]
            out.append({"lot_id": lot["lot_id"], "rfq_id": rfq["rfq_id"], "bags": b, "markup": m})
            bags -= b
            room -= b
    return out


def decide(state: dict, ctx: Context) -> tuple[list[dict], str]:
    """Returns (offers, source)."""
    rows = plan(state, ctx)
    ctx.notes.append({"plan": [{k: r[k] for k in ("lot_id", "rfq_id", "bags", "price")} | r["meta"] for r in rows]})
    src = "model+llm" if (ctx.adjust or ctx.volume != 1.0) else "model"
    return guard(state, ctx, rows), src

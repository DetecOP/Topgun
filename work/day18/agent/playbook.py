"""ช่วงเกม (Phase) + Scenario Playbook + calendar (PIPELINE.md ข้อ 3.5, 4.6, 4.7).

ทุกค่าในไฟล์นี้เป็น "ค่าเริ่มสำหรับทดลอง" ไม่ใช่กติกา — ปรับหลังเทียบ PR ในตลาดฝึก
"""
import re

# pace = คูณกับส่วนเฉลี่ยต่อรอบ · explore = สัดส่วนกระสอบที่ใช้หยั่งราคาสูง
PHASES = {
    "early": {"pace": 1.15, "explore": 0.30},
    "mid": {"pace": 1.35, "explore": 0.15},
    "late": {"pace": 1.60, "explore": 0.0},
    "final": {"pace": 99.0, "explore": 0.0},     # ขายทั้งหมด (บีบด้วย capacity)
}
LADDER = [-0.010, 0.0, 0.010]      # บันไดราคารอบราคาเป้า (ข้อ 4.7 ค.1)
EXPLORE_STEP = 0.025               # ส่วนหยั่ง = เป้า + ค่านี้ (ไม่เกินเพดานที่รู้)
JITTER = 0.004                     # สุ่ม ± ต่อซอง (ข้อ 4.7 ค.2)
FLOOR = {"SPECIALTY": 1.00, "COMMERCIAL": 0.95, "INSTANT": 0.88}
FLOOR_DEFAULT, FLOOR_FINAL = 0.90, 0.86
RFQ_SHARE = {"ceiling": 0.45, "mixed": 0.25, "unknown": 0.25, "competitive": 0.12}


def phase_params(ph: str) -> dict:
    """ค่าของช่วงเกม (สวิตช์ V2_EARLY_SELL / V2_LATE_PUSH ตัดออกแล้ว: ไม่ดีกว่า baseline)"""
    return dict(PHASES[ph])


def phase(state: dict, total: int) -> str:
    rnd = state["round"]
    if rnd.get("kind") == "practice":
        return "early"
    n = rnd.get("number") or 1
    if n >= total:
        return "final"
    if n >= total - 2:
        return "late"
    return "early" if n <= 2 else "mid"


def calendar_weights(calendar: list, total: int) -> dict:
    """{round_number: {"w": demand_weight, "label", "specialty_share"}} · ไม่มีข้อมูล = 1.0"""
    out = {n: {"w": 1.0, "label": "", "specialty_share": None} for n in range(1, total + 1)}
    for row in calendar or []:
        nums = [int(x) for x in re.findall(r"\d+", str(row.get("rounds", "")))]
        if not nums:
            continue
        lo, hi = nums[0], nums[-1]
        try:
            w = float(row.get("demand_weight") or 1.0)
        except (TypeError, ValueError):
            w = 1.0
        for n in range(lo, hi + 1):
            if n not in out:
                continue
            out[n] = {"w": w, "label": str(row.get("label") or ""),
                      "specialty_share": row.get("specialty_share")}
    return out


def round_share(state: dict, cal: dict, total: int) -> float:
    """ส่วนของของที่เหลือที่ควรขายรอบนี้ = w_now ÷ Σ w ของรอบที่เหลือ (วางแผนทุกรอบที่เหลือ ส่งจริงแค่รอบนี้)"""
    rnd = state["round"]
    n = rnd.get("number") or 1 if rnd.get("kind") != "practice" else 1
    ws = [cal.get(k, {"w": 1.0})["w"] for k in range(n, total + 1)] or [1.0]
    return ws[0] / sum(ws)


def scenarios(model, ph: str, cal_now: dict) -> dict:
    """ต่อประเภทผู้ซื้อ: สถานการณ์ที่ตรวจพบ (A–F ในข้อ 4.6) → ปรับ ratio / ส่วนต่อ RFQ / ปริมาณ"""
    out = {}
    for t in ("SPECIALTY", "COMMERCIAL", "INSTANT"):
        ms = model.market_state(t)
        tags, shift, pace = [], 0.0, 1.0
        last = model.last.get(t, {})
        if ms["mode"] == "competitive":
            tags.append("A-competitive")
            shift -= 0.003
        if ms["mode"] == "ceiling":
            tags.append("B-ceiling")
        # C: กอง starter ที่ ×1.00 — แพ้ที่ ≥ 0.995 แต่ชนะต่ำกว่า (ตรวจจากผลเราเอง · สมมติฐาน)
        cb = model.clear_type.get(t)
        if t == "COMMERCIAL" and cb is not None and cb.hi is not None and 0.995 <= cb.hi <= 1.01:
            tags.append("C-starter-pile")
        # D: คนเทของ — ข้อเสนอต่อกระสอบเพิ่มขึ้นชัดเทียบรอบก่อนๆ
        if ms["crowd_trend"] and ms["crowd_trend"] > 0.3 and ph in ("mid", "late"):
            tags.append("D-dumping")
            shift -= 0.005
            pace *= 1.15
        if last.get("OUTBID", 0) >= 2 and not last.get("ACCEPTED"):
            tags.append("A-lost-all")
            shift -= 0.005
        out[t] = {"tags": tags, "shift": shift, "pace": pace, "share": RFQ_SHARE.get(ms["mode"], 0.25), "market": ms}
    w = cal_now.get("w", 1.0)
    glob = []
    if w < 0.95:
        glob.append("E-low-demand")
    if w > 1.05:
        glob.append("F-festival")
    if cal_now.get("specialty_share"):
        glob.append("F-specialty")
    out["_global"] = {"tags": glob, "w": w}
    return out


# ---------- แรงกดดันกระสอบ (PIPELINE ข้อ 4.8) ----------
PRESSURE_LOW, PRESSURE_HIGH = 0.40, 0.80
PRESSURE_MODES = {
    "scarce": {"ladder": [0.0, 0.010], "explore_max_bags": 1, "explore_mult": 1.0, "floor_add": 0.02,
               "pace": 0.8, "secondary": False},
    "normal": {"ladder": None, "explore_max_bags": None, "explore_mult": 1.0, "floor_add": 0.0,
               "pace": 1.0, "secondary": True},
    "flood": {"ladder": [-0.015, -0.005, 0.005], "explore_max_bags": None, "explore_mult": 0.5, "floor_add": 0.0,
              "pace": 1.2, "secondary": True, "late_floor": True},
}


def capacity_bags(state: dict, total_rounds: int) -> int:
    """capacity ต่อรอบ (กระสอบ) · ตลาดไม่จำกัด → 1.5 × ส่วนเฉลี่ย (ตามสไลด์ 18) เป็นตัวแทน"""
    if state.get("round_capacity_kg"):
        return max(1, state["round_capacity_kg"] // 60)
    kg_total = sum(l.get("kg_total", l.get("kg_available", 0)) for l in state["lots"])
    return max(1, -(-int(1.5 * kg_total / max(total_rounds, 1)) // 60))


def pressure(sellable_bags: int, cap_bags: int, rounds_left: int, ph: str) -> tuple[float, str]:
    p = sellable_bags / max(cap_bags * max(rounds_left, 1), 1)
    if ph == "final":
        return round(p, 3), "normal"
    mode = "scarce" if p < PRESSURE_LOW else ("flood" if p > PRESSURE_HIGH else "normal")
    return round(p, 3), mode


FLOOR_LATE = 0.90      # ช่วงท้าย: เวลาขายเหลือน้อย capacity ต่อรอบจำกัด → ยอมลงได้มากขึ้น (ยังเหนือของเหลือ 0.80)


def floor_for(btype: str, ph: str) -> float:
    if ph == "final":
        return FLOOR_FINAL
    base = FLOOR.get(btype, FLOOR_DEFAULT)
    return min(base, FLOOR_LATE) if ph == "late" else base

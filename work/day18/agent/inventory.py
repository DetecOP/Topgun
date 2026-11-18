"""Inventory Manager + cliff risk (PIPELINE.md ข้อ 3.5, 4.5).

- cliff_risk(): ล็อตไหนค่าตัวอย่างชิดขอบเกรด/ขอบสเปก ถ้าค่าจริงเลื่อนไป ±DELTA แล้ว TV เปลี่ยนเท่าไร (tv_lo, tv_hi)
- spec_ok():   ผ่านสเปกแบบเว้นระยะ (margin) สำหรับล็อตที่เสี่ยง
- classify():  จัดล็อตเป็นกลุ่ม UNSELLABLE / RISKY / HIGH / NORMAL / LOW

DELTA = ระยะเผื่อความคลาดของตัวอย่าง ≈ 2 × SD ที่วัดได้จริง (ตลาดฝึกแบบใหม่ 46 เกม: defect SD 0.48 · ชื้น SD 0.38 ·
screen คลาด ±1 ใน 19% ของล็อต) → ค่าเริ่ม 1.0 / 0.75 / 1 · แก้ได้ใน .env: DELTA_DEFECT, DELTA_MOISTURE, DELTA_SCREEN
อ่านค่าทุกครั้งที่เรียก (main.py โหลด .env หลัง import) · pass_prob ใช้ SD = DELTA/2 · cliff_risk ใช้ ±1 SD
"""
import os

from appraisal import grade, true_value


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def delta() -> dict:
    return {"defect_pct": _f("DELTA_DEFECT", 1.0), "moisture_pct": _f("DELTA_MOISTURE", 0.75),
            "screen": _f("DELTA_SCREEN", 1)}


# สเปกที่เห็นในตลาดฝึก (ใช้เมื่อรอบนี้ยังไม่มี RFQ ของประเภทนั้นให้ดู) · Specialty = ดอยช้าง (หลวมสุด screen ≥16)
KNOWN_SPECS = {
    "SPECIALTY": {"max_defect_pct": 3.0, "max_moisture_pct": 12.5, "min_screen": 16},
    "COMMERCIAL": {"max_defect_pct": 7.0, "max_moisture_pct": 12.5, "min_screen": None},
    "INSTANT": {"max_defect_pct": 15.0, "max_moisture_pct": 14.0, "min_screen": None},
}


def spec_ok(sample: dict, spec: dict, margin: dict | None = None) -> bool:
    m = margin or {"defect_pct": 0, "moisture_pct": 0, "screen": 0}
    return (sample["defect_pct"] <= spec["max_defect_pct"] - m["defect_pct"]
            and sample["moisture_pct"] <= spec["max_moisture_pct"] - m["moisture_pct"]
            and (spec.get("min_screen") is None or sample["screen"] >= spec["min_screen"] + m["screen"]))


P_MIN = _f("SPEC_P_MIN", 0.6)       # ส่งให้ผู้ซื้อเมื่อโอกาสผ่านสเปกจริง ≥ ค่านี้ (ก่อนรอบสุดท้าย)
SCREEN_EDGE_P = 0.90                 # screen เท่ากับขั้นต่ำพอดี: คลาด ±1 ใน 19% ของล็อต → ต่ำลง 1 ราว 10%


def _phi(z: float) -> float:
    import math
    return 0.5 * (1 + math.erf(z / 2 ** 0.5))


def pass_prob(sample: dict, spec: dict, delta: dict | None = None) -> float:
    """โอกาสที่คุณภาพจริงผ่านสเปก · สมมติ noise ปกติ SD = DELTA/2 (DELTA ≈ 2 SD) · ค่าตัวอย่างไม่ผ่าน = 0"""
    d = delta or globals()["delta"]()
    if not spec_ok(sample, spec):
        return 0.0
    p = _phi((spec["max_defect_pct"] - sample["defect_pct"]) / max(d["defect_pct"] / 2, 1e-6))
    p *= _phi((spec["max_moisture_pct"] - sample["moisture_pct"]) / max(d["moisture_pct"] / 2, 1e-6))
    if spec.get("min_screen") is not None:
        gap = sample["screen"] - spec["min_screen"]
        p *= 1.0 if gap >= d["screen"] or d["screen"] == 0 else SCREEN_EDGE_P
    return round(p, 3)


def _shifted(sample: dict, dd: float, dm: float, ds: float) -> dict:
    return {"defect_pct": max(0.0, sample["defect_pct"] + dd), "moisture_pct": max(0.0, sample["moisture_pct"] + dm),
            "screen": int(round(sample["screen"] + ds))}


def cliff_risk(rules: dict, sample: dict, delta: dict | None = None) -> dict:
    """TV ถ้าค่าจริงอยู่ไหนก็ได้ใน sample ± 1 SD (= DELTA/2 · screen ±1) → tv_lo/tv_hi และขอบที่อยู่ใกล้"""
    if delta is None:
        full = globals()["delta"]()
        delta = {"defect_pct": full["defect_pct"] / 2, "moisture_pct": full["moisture_pct"] / 2, "screen": full["screen"]}
    d = delta
    tv = true_value(rules, sample)
    tvs = []
    for dd in (-d["defect_pct"], 0, d["defect_pct"]):
        for dm in (-d["moisture_pct"], 0, d["moisture_pct"]):
            for ds in (-d["screen"], 0, d["screen"]):
                tvs.append(true_value(rules, _shifted(sample, dd, dm, ds)))
    edges = []
    for step in rules["defect_steps"][:-1]:
        if abs(sample["defect_pct"] - step["max_defect_pct"]) <= d["defect_pct"]:
            edges.append(f"defect {step['max_defect_pct']}")
    mo = rules["moisture"]
    for edge in (mo["ref"], mo["hard_limit"], 14.0):
        if abs(sample["moisture_pct"] - edge) <= d["moisture_pct"]:
            edges.append(f"moisture {edge}")
    tv_lo, tv_hi = min(tvs), max(tvs)
    return {"tv": round(tv, 2), "tv_lo": round(tv_lo, 2), "tv_hi": round(tv_hi, 2),
            "drop_pct": round((tv - tv_lo) / tv * 100, 1) if tv else 0.0, "edges": edges,
            "grade": grade(rules, sample["defect_pct"])[0]}


def spec_book(rfqs: list[dict]) -> dict:
    """สเปกต่อประเภทผู้ซื้อ: ที่เห็นในรอบนี้ (หลวมสุดของแต่ละประเภท) + ที่รู้จากเมื่อวาน"""
    book = {k: dict(v) for k, v in KNOWN_SPECS.items()}
    for r in rfqs:
        book.setdefault(r["buyer_type"], dict(r["spec"]))
        s, b = r["spec"], book[r["buyer_type"]]
        b["max_defect_pct"] = max(b["max_defect_pct"], s["max_defect_pct"])
        b["max_moisture_pct"] = max(b["max_moisture_pct"], s["max_moisture_pct"])
        if b.get("min_screen") is not None:
            b["min_screen"] = None if s.get("min_screen") is None else min(b["min_screen"], s["min_screen"])
    return book


def classify(rules: dict, lots: list[dict], rfqs: list[dict], banned=None) -> dict:
    """lot_id -> {cls, types (โอกาสผ่าน ≥ P_MIN), types_plain (ค่าตัวอย่างผ่าน), risk}
    banned = set{(lot, type)} หรือฟังก์ชัน (lot_id, type, spec) -> True ถ้าห้ามส่ง"""
    book = spec_book(rfqs)
    if banned is None:
        is_banned = lambda lid, t, sp: False                              # noqa: E731
    elif callable(banned):
        is_banned = banned
    else:
        is_banned = lambda lid, t, sp: (lid, t) in banned                 # noqa: E731
    out = {}
    for lot in lots:
        s = lot["sample"]
        risk = cliff_risk(rules, s)
        plain = [t for t, sp in book.items() if spec_ok(s, sp) and not is_banned(lot["lot_id"], t, sp)]
        probs = {t: pass_prob(s, book[t]) for t in plain}
        safe = [t for t in plain if probs[t] >= P_MIN]
        if not plain:
            cls = "UNSELLABLE"
        elif "SPECIALTY" in safe:
            cls = "HIGH"
        elif risk["drop_pct"] >= 10 or any(p < 0.9 for p in probs.values()):
            cls = "RISKY"
        elif safe == ["INSTANT"]:
            cls = "LOW"
        else:
            cls = "NORMAL"
        out[lot["lot_id"]] = {"cls": cls, "types": safe, "types_plain": plain, "risk": risk, "pass_prob": probs}
    return out

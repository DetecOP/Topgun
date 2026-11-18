"""Estimate a lot's True Value (TV) from its Sample, using the formula the market publishes.

The formula and its numbers come from GET /v1/calendar -> "rules", so nothing is hard-coded here.
"""


def grade(rules: dict, defect_pct: float) -> tuple[str, float]:
    for step in rules["defect_steps"]:
        if defect_pct <= step["max_defect_pct"]:
            return step["grade"], step["step"]
    last = rules["defect_steps"][-1]
    return last["grade"], last["step"]


def moisture_factor(rules: dict, m: float) -> float:
    mo = rules["moisture"]
    if m <= mo["ref"]:
        return 1.0
    if m <= mo["hard_limit"]:
        return (1 - m / 100) / (1 - mo["ref"] / 100) - mo["penalty_per_pp"] * (m - mo["ref"])
    return mo["hard_factor"]


def screen_factor(rules: dict, screen: int) -> float:
    factors = {int(k): v for k, v in rules["screen_factors"].items()}
    codes = sorted(factors)
    return factors[min(max(int(screen), codes[0]), codes[-1])]


def true_value(rules: dict, sample: dict) -> float:
    """TV = P0 × G(d) × M(m) × S(s), baht per kg."""
    d, m = sample["defect_pct"], sample["moisture_pct"]
    g = (1 - d / 100) * grade(rules, d)[1]
    return rules["p0"] * g * moisture_factor(rules, m) * screen_factor(rules, sample["screen"])


_PRIOR = None
HYBRID_MAX = 0.08     # hybrid: ใช้ค่า Bayes เมื่อห่างจากค่าตัวอย่างไม่เกิน 8% (ไม่กระโดดข้ามหน้าผาเกรด)


def _prior():
    """ค่าจริงที่เคยเจอ (reveal ตลาดฝึกแบบใหม่ 246 เกม) + ขนาด noise ที่วัดได้ · appraisal_prior.json"""
    global _PRIOR
    if _PRIOR is None:
        import json
        from pathlib import Path
        p = json.loads((Path(__file__).with_name("appraisal_prior.json")).read_text(encoding="utf-8"))
        p["hd"] = {int(k): v for k, v in p["defect_hist"].items()}
        p["hm"] = {int(k): v for k, v in p["moisture_hist"].items()}
        _PRIOR = p
    return _PRIOR


def bayes_tv(rules: dict, sample: dict) -> float:
    """TV ที่ทำให้ % คลาดคาดหวังต่ำสุด (มัธยฐานถ่วง 1/TV ของค่าจริงที่เป็นไปได้)
    โอกาสของค่าจริง = (ค่าจริงแบบนี้พบบ่อยแค่ไหน) × (ตัวอย่างจะออกมาแบบที่เห็นได้แค่ไหน)
    noise วัดจากเฉลย: defect SD = 0.258 + 0.032×defect · ชื้น SD 0.385 · screen คลาด ±1 ราว 21%
    ผล: ตัวอย่างชื้นต่ำ → ค่าจริงมักสูงกว่า · ตัวอย่างชื้นสูง → ค่าจริงมักต่ำกว่า (ถอยเข้าหาค่าทั่วไป)"""
    import math
    p = _prior()
    step, nz = p["step"], p["noise"]
    sdd = lambda d: nz["sd_defect_a"] + nz["sd_defect_b"] * d   # noqa: E731
    sdm = nz["sd_moisture"]

    def dens(h, v):
        k = round(v / step)
        return sum(h.get(j, 0) * math.exp(-((j - k) / 1.5) ** 2 / 2) for j in range(k - 3, k + 4)) + 0.05

    ds, ms, ss = sample["defect_pct"], sample["moisture_pct"], int(sample["screen"])
    n = int(4 * sdd(ds) / step) + 2
    wd = [(d, dens(p["hd"], d) * math.exp(-((ds - d) / sdd(d)) ** 2 / 2) / sdd(d))
          for d in (max(0.0, ds + i * step) for i in range(-n, n + 1))]
    wm = [(m, dens(p["hm"], m) * math.exp(-((ms - m) / sdm) ** 2 / 2)) for m in (ms + i * step for i in range(-32, 33))]
    ws = {t: p["screen_pairs"].get(f"{ss}>{t}", 0) + 0.01 for t in (ss - 1, ss, ss + 1)}
    pts = []
    for d, a in wd:
        for m, b in wm:
            for t, c in ws.items():
                tv = true_value(rules, {"defect_pct": d, "moisture_pct": m, "screen": t})
                pts.append((tv, a * b * c / max(tv, 1e-6)))
    pts.sort()
    half, acc = sum(w for _, w in pts) / 2, 0.0
    for tv, w in pts:
        acc += w
        if acc >= half:
            return tv
    return pts[-1][0]


def estimate_one(rules: dict, sample: dict, mode: str) -> float:
    tv0 = true_value(rules, sample)
    if mode == "sample":
        return tv0
    try:
        b = bayes_tv(rules, sample)
    except Exception:          # ไฟล์ prior หาย/ข้อมูลแปลก → ใช้ค่าตัวอย่าง
        return tv0
    if mode == "bayes" or abs(b - tv0) <= HYBRID_MAX * tv0:
        return b
    return tv0


def estimate_lots(rules: dict, lots: list[dict]) -> dict[str, float]:
    """TV ที่ใช้ทั้งส่งประเมินและตั้งราคา · APPRAISAL_MODE = hybrid (ค่าเริ่ม) | sample | bayes
    ทดสอบกับเฉลย 246 เกม (1,222 ล็อต) แบบตัดเกมตัวเองออกจาก prior · คะแนน = 20 × (1 − MAPE/10%):
      sample 14.75/20 (เกมได้ 0: 10) · hybrid 14.90 (+0.15 ± 0.04, 0: 11) · bayes 15.08 (+0.32 ± 0.21, 0: 13)
    hybrid = ขยับค่าเล็กน้อยตาม noise แต่ไม่ข้ามหน้าผาเกรด → ได้เพิ่มแน่นอนกว่า"""
    import os
    mode = os.environ.get("APPRAISAL_MODE", "hybrid")
    if mode not in ("hybrid", "sample", "bayes"):
        mode = "hybrid"
    return {lot["lot_id"]: round(estimate_one(rules, lot["sample"], mode), 2) for lot in lots}


def appraisal_items(rules: dict, lots: list[dict], tv: dict[str, float]) -> list[dict]:
    return [{"lot_id": lot["lot_id"], "grade": grade(rules, lot["sample"]["defect_pct"])[0],
             "est_value_per_kg": tv[lot["lot_id"]]} for lot in lots]

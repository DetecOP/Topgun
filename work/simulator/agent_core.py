# agent_core.py · สมองของ agent: ในแต่ละรอบ ตัดสินว่าจะเสนอขายล็อตไหน ให้ใคร ราคาเท่าไร
#
# คอนเซ็ปต์ทีม: "ขายอัตโนมัติ ขายเร็ว ขายล่วงหน้าได้ก่อนข้อมูลเซ็นเซอร์มา"
#   → ล็อตที่ยังไม่มีผลวัดก็เสนอขายได้เลย โดยใช้มูลค่าที่ประเมินไว้ (valuation.estimate)
#
# ไฟล์นี้ "ไม่ส่งอะไรออกไปจริง" ฟังก์ชัน submit() จะใช้ได้หลังผู้ใช้อนุญาตและรู้ API จริงแล้วเท่านั้น
#
# รูปแบบข้อมูล (สมมติ รอเปลี่ยนตาม API จริง):
#   buyer = {"id": "B1", "max_moisture": 12.5, "max_defect": 5}   (เงื่อนไขที่ตลาดเปิดเผย ถ้ามี)
#   offer = {"lot_id", "buyer_id", "price_per_kg", "markup", "weight", "value_est", "is_estimate", "expected"}

import config
from scoring import score_sold


def eligible(lot, buyer):
    """เช็กเงื่อนไขผู้ซื้อ เฉพาะค่าที่วัดแล้ว ค่าที่ยังไม่รู้ถือว่าผ่าน (เป็นความเสี่ยงของการขายล่วงหน้า)"""
    if lot.get("moisture") is not None and buyer.get("max_moisture") is not None:
        if lot["moisture"] > buyer["max_moisture"]:
            return False
    if lot.get("defect_pct") is not None and buyer.get("max_defect") is not None:
        if lot["defect_pct"] > buyer["max_defect"]:
            return False
    return True


def plan_offers(lots, buyers, valuator, learner, mode, rounds_left,
                wait_for_data=False, fixed_markup=None):
    """คืน list ของข้อเสนอในรอบนี้ (ยังไม่ส่ง)

    rounds_left         → จำนวนรอบที่เหลือ รวมรอบนี้ (1 = รอบสุดท้าย)
    wait_for_data=True  → แบบเปรียบเทียบ: รอให้มีผลวัดก่อนค่อยขาย (ไม่ใช่คอนเซ็ปต์ทีม)
    fixed_markup=0.08   → แบบเปรียบเทียบ: บวกราคาคงที่ ไม่เรียนรู้
    "expected" ในข้อเสนอ = คะแนนที่ได้เพิ่มจากการเสนอรอบนี้ เทียบกับการรอ (ใช้จัดลำดับเมื่อชนเพดาน)
    """
    best_per_lot = []
    spread = valuator.value_spread() if hasattr(valuator, "value_spread") else 0.0
    for lot in lots:
        value, is_est = valuator.estimate(lot)                 # มูลค่าต่อ กก. (จริงหรือประเมิน)
        if wait_for_data and is_est:
            continue                                           # แบบรอข้อมูล: ข้ามล็อตที่ยังไม่ได้วัด
        # กัน winner's curse: ล็อตที่ขายล่วงหน้าตั้งราคาจากฐานที่บวกระยะเผื่อความไม่แน่นอน
        # และให้ตัวเรียนราคาเก็บสถิติแยก (คีย์ "ผู้ซื้อ|ล่วงหน้า")
        base = value * (1 + config.PRESELL_MARGIN_Z * spread) if is_est else value
        best = None
        for b in buyers:
            if not eligible(lot, b):
                continue
            key = f"{b['id']}|ล่วงหน้า" if (is_est and config.PRESELL_SEPARATE_STATS) else b["id"]
            if fixed_markup is not None:
                m = fixed_markup
                exp = score_sold(mode, value * (1 + m), value, lot["weight"])
                base = value                                   # แบบคงที่ไม่ใช้ระยะเผื่อ (ไว้เทียบ)
            else:
                m, exp, wait_value = learner.choose(key, base, lot["weight"], mode, rounds_left)
                exp = exp - wait_value                         # ได้เพิ่มเท่าไรเมื่อเทียบกับการรอ
            if best is None or exp > best["expected"]:
                best = {"lot_id": lot["id"], "buyer_id": b["id"], "learn_key": key,
                        "price_per_kg": round(base * (1 + m), 2), "markup": m,
                        "weight": lot["weight"], "value_est": round(value, 2),
                        "is_estimate": is_est, "expected": exp}
        if best is not None:
            best_per_lot.append(best)

    # เรียงจากคะแนนที่คาดมากไปน้อย แล้วตัดตามเพดานความปลอดภัย
    best_per_lot.sort(key=lambda o: o["expected"], reverse=True)
    offers, kg = [], 0
    for o in best_per_lot:
        if len(offers) >= config.MAX_OFFERS_PER_ROUND:
            break
        if kg + o["weight"] > config.MAX_KG_PER_ROUND:
            continue
        offers.append(o)
        kg += o["weight"]
    return offers


def submit(offers):
    """ส่งข้อเสนอไปที่ API ผู้จัด ← ยังไม่ได้เขียน (รอ endpoint จริง และรอผู้ใช้อนุญาต)"""
    if config.DRY_RUN:
        for o in offers:                                       # DRY_RUN: แค่พิมพ์ให้ดู
            tag = "ประเมินล่วงหน้า" if o["is_estimate"] else "มีผลวัด"
            print(f"[DRY_RUN] ล็อต {o['lot_id']} → {o['buyer_id']} "
                  f"ราคา {o['price_per_kg']}/กก. (มูลค่า {o['value_est']}, {tag})")
        return []
    raise NotImplementedError("ยังไม่ได้เชื่อม API จริง ต้องได้ endpoint และคำอนุญาตจากผู้ใช้ก่อน")

# scoring.py · สูตรคะแนน 3 แบบที่เป็นไปได้ (ยังไม่ทราบว่าผู้จัดใช้แบบไหน)
#
# Track 3.pdf หน้า 3 บอกแค่ "คะแนนดูว่าขายได้คุ้มแค่ไหน เทียบกับมูลค่าจริงของของตัวเอง"
# พอรู้สูตรจริง ให้เพิ่มหรือแก้ฟังก์ชันในไฟล์นี้ แล้วตั้ง config.SCORE_MODE

import config

MODES = ("diff", "ratio", "penalty")


def score_sold(mode, price_per_kg, value_per_kg, weight):
    """คะแนนของล็อตที่ขายได้"""
    if mode in ("diff", "penalty"):
        return (price_per_kg - value_per_kg) * weight          # กำไรเทียบมูลค่า (บาท)
    if mode == "ratio":
        return price_per_kg / value_per_kg                     # 1.10 = ขายแพงกว่ามูลค่า 10%
    raise ValueError(f"ไม่รู้จักโหมดคะแนน {mode}")


def score_unsold(mode, value_per_kg, weight):
    """คะแนนของล็อตที่จบเกมแล้วยังขายไม่ได้"""
    if mode == "penalty":
        return -config.UNSOLD_PENALTY * value_per_kg * weight
    return 0.0


def total_score(mode, lot_scores, n_lots):
    """รวมคะแนนทั้งเกม: ratio ใช้ค่าเฉลี่ยต่อล็อต แบบอื่นใช้ผลรวม"""
    s = sum(lot_scores)
    return s / n_lots if mode == "ratio" and n_lots else s

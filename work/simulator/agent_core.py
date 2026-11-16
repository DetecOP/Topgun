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
from scoring import score_sold, score_unsold


def eligible(lot, buyer):
    """เช็กเงื่อนไขผู้ซื้อ เฉพาะค่าที่วัดแล้ว ค่าที่ยังไม่รู้ถือว่าผ่าน (เป็นความเสี่ยงของการขายล่วงหน้า)"""
    if lot.get("moisture") is not None and buyer.get("max_moisture") is not None:
        if lot["moisture"] > buyer["max_moisture"]:
            return False
    if lot.get("defect_pct") is not None and buyer.get("max_defect") is not None:
        if lot["defect_pct"] > buyer["max_defect"]:
            return False
    return True


def explain(lot, value, base, markup, is_est, moist_limit=None):
    """เหตุผลของข้อเสนอเป็นภาษาคน + ธง "ควรตรวจซ้ำ"
    (ผู้จัดเน้นวันที่ 16: ให้ผู้ซื้อเห็นข้อมูลคุณภาพ พร้อมเหตุผลว่าควรรับหรือขอตรวจซ้ำ)"""
    parts, recheck = [], False
    if is_est:
        parts.append(f"ยังไม่มีผลวัด ใช้ค่าประเมิน {value:.1f}/กก. เผื่อความไม่แน่นอนเป็นฐาน {base:.1f}")
        recheck = True
    else:
        m, d, s = lot.get("moisture"), lot.get("defect_pct"), lot.get("size")
        parts.append(f"ผลวัด: ความชื้น {m}% เมล็ดเสีย {d}% ขนาด {s} → มูลค่า {value:.1f}/กก.")
        if moist_limit is not None and m is not None:
            if m > moist_limit:
                parts.append(f"ความชื้นเกินเกณฑ์ {moist_limit}% (เสี่ยงเชื้อรา)")
                recheck = True
            elif m > moist_limit - 0.5:
                parts.append(f"ความชื้นใกล้เกณฑ์ {moist_limit}%")
                recheck = True
    parts.append(f"เสนอ {markup:+.0%} จากฐาน")
    return " · ".join(parts), recheck


class LotMemory:
    """จำราคาที่แต่ละล็อตเคยขายไม่ออก → รอบหน้าเสนอให้ต่ำลง (เรียนจากคู่แข่งแบบ 'ลดเมื่อขายไม่ออก')"""

    def __init__(self, step=None, mode=None):
        if step is None:                                       # ไม่ระบุ → ใช้ค่าตามสูตรคะแนนใน config
            step = config.LOT_DECAY_STEP_BY_MODE.get(mode or config.SCORE_MODE)
        self.step = step
        self.caps = {}                                         # ล็อต → markup สูงสุดที่ยอมให้เสนอ

    def cap(self, lot_id):
        return self.caps.get(lot_id) if self.step else None

    def update(self, results):
        for res in results:
            o = res["offer"]
            if not res["sold"] and self.step:
                self.caps[o["lot_id"]] = min(self.caps.get(o["lot_id"], 9.9), o["markup"] - self.step)


def plan_offers(lots, buyers, valuator, learner, mode, rounds_left,
                wait_for_data=False, fixed_markup=None, lot_memory=None):
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
        if (wait_for_data or not config.PRESELL_ENABLED) and is_est:
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
                cap = lot_memory.cap(lot["id"]) if lot_memory else None
                m, exp, wait_value = learner.choose(key, base, lot["weight"], mode, rounds_left,
                                                    max_markup=cap)
                exp = exp - wait_value                         # ได้เพิ่มเท่าไรเมื่อเทียบกับการรอ
                if config.SKIP_NEGATIVE_GAIN:
                    # ห้ามขายถ้าได้คะแนนน้อยกว่า "ไม่ขายเลยจนจบเกม" (diff: ห้ามขาดทุน, penalty: ห้ามต่ำกว่าค่าปรับ)
                    s = score_sold(mode, base * (1 + m), base, lot["weight"])
                    if s < score_unsold(mode, base, lot["weight"]):
                        continue
            if best is None or exp > best["expected"]:
                best = {"lot_id": lot["id"], "buyer_id": b["id"], "learn_key": key,
                        "price_per_kg": round(base * (1 + m), 2), "markup": m,
                        "weight": lot["weight"], "value_est": round(value, 2),
                        "is_estimate": is_est, "expected": exp}
        if best is not None:
            moist_limit = getattr(valuator, "params", {}).get("moist_max")
            best["reason"], best["recheck"] = explain(lot, value, base, best["markup"], is_est, moist_limit)
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
            flag = " ⚠️ควรตรวจซ้ำ" if o.get("recheck") else ""
            print(f"[DRY_RUN] ล็อต {o['lot_id']} → {o['buyer_id']} ราคา {o['price_per_kg']}/กก.{flag}")
            print(f"          เหตุผล: {o.get('reason', '')}")
        return []
    raise NotImplementedError("ยังไม่ได้เชื่อม API จริง ต้องได้ endpoint และคำอนุญาตจากผู้ใช้ก่อน")

# valuation.py · ส่วน "รู้ค่าของ": ประเมินมูลค่าต่อ กก. ของแต่ละล็อต
#
# ออกแบบให้ถอดเปลี่ยนได้: ถ้าผู้จัดให้สูตรจริงมา ให้เขียนคลาสใหม่ที่มีเมธอด
#   estimate(lot) -> (มูลค่าต่อกก., เป็นค่าประเมินหรือไม่)
#   observe(lot)  -> เรียนจากล็อตที่มีผลวัดแล้ว
# แล้วส่งคลาสใหม่เข้าไปแทน PlaceholderValuator โดยส่วนอื่นไม่ต้องแก้
#
# lot คือ dict เช่น {"id": "A", "weight": 120, "moisture": 11.4, "defect_pct": 6, "size": "กลาง"}
# ถ้ายังไม่มีผลวัด ช่องนั้นเป็น None

from collections import Counter

import config

# ค่าเดียวกับชีท "ตั้งค่า" ใน Excel (ใช้เมื่ออ่าน Excel ไม่ได้) ทั้งหมดเป็นค่าสมมติ
DEFAULT_PARAMS = {
    "base_price": 100.0,        # B4 ราคาฐานต่อ กก.
    "moist_min": 10.0,          # B5 ความชื้นต่ำสุดที่เหมาะ
    "moist_max": 12.5,          # B6 ความชื้นสูงสุดที่เหมาะ
    "ded_over": 0.04,           # B7 หักต่อ 1 จุดที่ชื้นเกิน
    "ded_under": 0.02,          # B8 หักต่อ 1 จุดที่แห้งเกิน
    "ded_defect": 0.015,        # B9 หักต่อ 1% เมล็ดเสีย
    "ded_cap": 0.60,            # B10 เพดานการหักรวม
    "size_mult": {"ติดเปลือก": 0.85, "เล็ก": 0.95, "กลาง": 1.0, "ใหญ่": 1.08},  # A14:B17
}


def load_params(path=config.PREP_XLSX):
    """อ่านค่าสูตรจากชีท 'ตั้งค่า' คืน (params, ที่มา) ถ้าอ่านไม่ได้ใช้ค่าเริ่มต้น"""
    try:
        import openpyxl                                         # import ข้างในเพื่อให้ไฟล์นี้ใช้ได้แม้ไม่มี openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb["ตั้งค่า"]
        p = {
            "base_price": float(ws["B4"].value), "moist_min": float(ws["B5"].value),
            "moist_max": float(ws["B6"].value), "ded_over": float(ws["B7"].value),
            "ded_under": float(ws["B8"].value), "ded_defect": float(ws["B9"].value),
            "ded_cap": float(ws["B10"].value),
            "size_mult": {ws[f"A{r}"].value: float(ws[f"B{r}"].value) for r in range(14, 18)},
        }
        wb.close()
        return p, f"ชีท ตั้งค่า ใน {path.name}"
    except Exception as e:                                       # ไฟล์หาย ชีทเปลี่ยน ฯลฯ
        return dict(DEFAULT_PARAMS), f"ค่าเริ่มต้นในโค้ด (อ่าน Excel ไม่ได้: {e})"


# น้ำหนักของเมล็ดเสียแต่ละชนิด เทียบเป็น "ข้อบกพร่องเต็ม" (full defect equivalent)
# อ้างอิง: FAO "Coffee quality" (ระบบ Brazil/New York และค่าสัมประสิทธิ์เชิงพาณิชย์) ดู RESEARCH.md
# ชื่อคลาสตรงกับ 7 คลาสของ Track 2 (Track 2.pdf หน้า 4) · ค่าเป็นค่าประมาณจากงานวิจัย ไม่ใช่กติกาการแข่ง
DEFECT_WEIGHTS = {
    "Good": 0.0,
    "Full Black": 1.0,      # เมล็ดดำ = 1 ข้อบกพร่องเต็ม
    "Hull/Husk": 1.0,       # ผลแห้ง/เปลือก (dried cherry, pod) = 1
    "Parchment": 0.5,       # เมล็ดกะลา = 1/2
    "Shell": 1 / 3,         # หูช้าง = 3 เมล็ดต่อ 1 ข้อบกพร่องเต็ม
    "Broken": 0.2,          # แตกหัก = 5 เมล็ดต่อ 1
    "Immature": 0.2,        # ดิบ/อ่อน (green/immature) = 5 เมล็ดต่อ 1
    # เพิ่มจากข้อมูลชี้แจงวันที่ 16 (notes/day16_briefing.md ข้อ 3) ← ยังไม่ทราบว่าเกมแยกคลาสเหล่านี้ไหม
    "Peaberry": 0.0,        # พีเบอร์รี = ชนิดเมล็ด ไม่ใช่ตำหนิ
    "Insect": 0.1,          # มอดเจาะ = 10 เมล็ดต่อ 1 (FAO), มกษ. 5700 ยอม ≤4%
    "Mold": 1.0,            # ขึ้นรา = นับเต็มเท่าเมล็ดดำ (มกษ. 5700 ยอมแค่ ≤0.5%, เสี่ยงสารพิษ OTA)
}


def defect_equivalent_pct(class_counts):
    """แปลงจำนวนเมล็ดต่อคลาส (ผลจาก Track 2) เป็น % เมล็ดเสียแบบถ่วงน้ำหนัก
    เช่น {"Good": 90, "Full Black": 2, "Broken": 8} → (2×1 + 8×0.2) / 100 × 100 = 3.6"""
    total = sum(class_counts.values())
    if total == 0:
        return None                                            # ไม่มีข้อมูล → ให้ valuator เดาแทน
    weighted = sum(DEFECT_WEIGHTS.get(k, 1.0) * n for k, n in class_counts.items())  # คลาสไม่รู้จักนับเต็ม
    return 100.0 * weighted / total


def placeholder_value_per_kg(p, moisture, defect_pct, size):
    """สูตรสมมติ (ตรงกับชีท คำนวณมูลค่าล็อต) ← แทนด้วยสูตรจริงพรุ่งนี้"""
    ded_moist = (max(0.0, moisture - p["moist_max"]) * p["ded_over"]
                 + max(0.0, p["moist_min"] - moisture) * p["ded_under"])
    ded_def = defect_pct * p["ded_defect"]
    mult = p["size_mult"].get(size, 1.0)                        # ไม่รู้จักขนาด → ตัวคูณ 1
    return p["base_price"] * mult * (1 - min(p["ded_cap"], ded_moist + ded_def))


class PlaceholderValuator:
    """ประเมินมูลค่า: มีผลวัดก็ใช้ผลวัด ยังไม่มีก็เติมค่าที่คาด (ขายล่วงหน้าได้ทันที)"""

    def __init__(self, params=None):
        self.params = params or load_params()[0]
        self.seen = {"moisture": [], "defect_pct": [], "size": []}   # ผลวัดจริงที่เคยเห็น
        self._seen_ids = set()

    def observe(self, lot):
        """จำผลวัดของล็อตที่วัดแล้ว เพื่อใช้เดาล็อตที่ยังไม่ได้วัด (ล็อตละครั้ง)"""
        if lot["id"] in self._seen_ids or lot.get("moisture") is None:
            return
        self._seen_ids.add(lot["id"])
        for k in self.seen:
            if lot.get(k) is not None:
                self.seen[k].append(lot[k])

    def _guess(self, key, prior):
        """ค่าที่เดาให้ช่องที่ยังไม่มีผลวัด: ค่าเฉลี่ยที่เห็นจริง ถ้ายังไม่เห็นเลยใช้ prior"""
        vals = self.seen[key]
        if not vals:
            return prior
        if key == "size":                                       # ขนาดเป็นข้อความ → ใช้ค่าที่พบบ่อยสุด
            return Counter(vals).most_common(1)[0][0]           # เสมอกัน → เลือกตัวที่เห็นก่อน (ผลคงที่ทุกครั้ง)
        return sum(vals) / len(vals)

    def value_spread(self, default=0.10):
        """ความต่างของมูลค่าระหว่างล็อตที่วัดแล้ว (ส่วนเบี่ยงเบน ÷ ค่าเฉลี่ย) ใช้เป็นขนาดความไม่แน่นอน
        ตอนขายล่วงหน้า ถ้ายังเห็นไม่ถึง 2 ล็อต ใช้ค่า default"""
        n = len(self.seen["moisture"])
        if n < 2:
            return default
        vals = [placeholder_value_per_kg(self.params, self.seen["moisture"][i],
                                         self.seen["defect_pct"][i], self.seen["size"][i])
                for i in range(n)]
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / (n - 1)
        return (var ** 0.5) / mean if mean else default

    def estimate(self, lot):
        """คืน (มูลค่าต่อ กก., True ถ้ามีช่องไหนเป็นค่าเดา)"""
        m = lot.get("moisture")
        d = lot.get("defect_pct")
        s = lot.get("size")
        is_estimate = m is None or d is None or s is None
        m = m if m is not None else self._guess("moisture", config.PRIOR_MOISTURE)
        d = d if d is not None else self._guess("defect_pct", config.PRIOR_DEFECT_PCT)
        s = s if s is not None else self._guess("size", config.PRIOR_SIZE)
        return placeholder_value_per_kg(self.params, m, d, s), is_estimate

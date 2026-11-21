# step3_agent_loop.py · agent ฉบับเขียนมือ: วน "ดู → คิด → ทำ" จนจบเกม (Track 3.pdf หน้า 4)
# ต้องเปิด practice\mock_market.py ไว้ก่อน · ตั้ง DRY_RUN = False ได้เฉพาะกับตลาดจำลองในเครื่อง
# รัน: .venv\Scripts\python.exe practice\step3_agent_loop.py

import sys
import time

import requests

sys.path.insert(0, ".")                       # ให้ import log_template จากโฟลเดอร์ work ได้
from log_template import log_exchange         # บันทึกทุกคำขอ/คำตอบลง logs/

BASE_URL = "http://127.0.0.1:8000"
HEADERS = {"Authorization": "Bearer practice-token"}
DRY_RUN = False                               # True = คิดอย่างเดียว ไม่ส่ง · ใช้ False ได้เฉพาะ 127.0.0.1
MARKUP = 0.08                                 # เริ่มบวกราคา 8% จากมูลค่าประเมิน
STEP_DOWN = 0.04                              # ขายไม่ออก → รอบหน้าลดลง 4% (เรียนจากผล = "ดูผลแล้วปรับ")
FLOOR = -0.05                                 # ลดได้ต่ำสุดถึง −5% ของมูลค่า
fails = {}                                    # ล็อต → จำนวนครั้งที่ขายไม่ออก
MAX_OFFERS = 5                                # เพดานจำนวนข้อเสนอต่อรอบ
assert DRY_RUN or BASE_URL.startswith("http://127.0.0.1"), "ห้ามปิด DRY_RUN กับ server จริงในไฟล์ฝึก"


def estimate_value(lot):
    """คิด: มูลค่าต่อ กก. (สูตรสมมติเดียวกับ Excel) · ยังไม่มีผลวัด → ใช้ค่าเดา"""
    m = lot["moisture"] if lot["moisture"] is not None else 12.0
    d = lot["defect_pct"] if lot["defect_pct"] is not None else 8.0
    size = lot["size"] or "กลาง"
    mult = {"ติดเปลือก": 0.85, "เล็ก": 0.95, "กลาง": 1.0, "ใหญ่": 1.08}[size]
    ded = max(0, m - 12.5) * 0.04 + max(0, 10 - m) * 0.02 + d * 0.015
    return 100 * mult * (1 - min(0.6, ded))


def pick_buyer(lot, buyers):
    """คิด: ผู้ซื้อคนแรกที่เงื่อนไขผ่าน (ถ้ายังไม่มีผลวัด เลือกคนที่รับกว้างสุด)"""
    for b in sorted(buyers, key=lambda b: -b["max_moisture"]):
        if lot["moisture"] is None or (lot["moisture"] <= b["max_moisture"] and lot["defect_pct"] <= b["max_defect"]):
            return b["id"]
    return None


def call(method, path, **kw):
    """เรียก API 1 ครั้ง + บันทึก log + ลองใหม่ถ้าโดน 429"""
    for attempt in range(3):
        r = requests.request(method, f"{BASE_URL}{path}", headers=HEADERS, timeout=10, **kw)
        log_exchange(method, BASE_URL + path, request_body=kw.get("json"), status=r.status_code,
                     response_body=r.json() if r.content else None, headers=HEADERS)
        if r.status_code != 429:
            return r
        time.sleep(1 + attempt)                               # โดนจำกัดความถี่ → รอแล้วลองใหม่
    return r


requests.post(f"{BASE_URL}/reset", headers=HEADERS, timeout=10)   # เริ่มเกมใหม่ทุกครั้งที่ฝึก
sold_total = 0
while True:
    market = call("GET", "/market").json()                   # 1) ดู
    if market["game_over"] or not market["lots"]:
        break
    offers = []                                               # 2) คิด
    for lot in market["lots"]:
        buyer = pick_buyer(lot, market["buyers"])
        if buyer:
            m = max(FLOOR, MARKUP - STEP_DOWN * fails.get(lot["id"], 0))   # ขายไม่ออกกี่ครั้ง ลดเท่านั้นขั้น
            price = round(estimate_value(lot) * (1 + m), 2)
            offers.append({"lot_id": lot["id"], "buyer_id": buyer, "price_per_kg": price})
        else:
            print(f"   ล็อต {lot['id']} ไม่มีผู้ซื้อรับ (ความชื้น {lot['moisture']}% / เมล็ดเสีย {lot['defect_pct']}% เกินเงื่อนไข)")
    offers = offers[:MAX_OFFERS]
    print(f"\nรอบ {market['round']}: เสนอ {len(offers)} ข้อ")
    for o in offers:
        print(f"   ล็อต {o['lot_id']} → {o['buyer_id']} ราคา {o['price_per_kg']}")
    if DRY_RUN:                                               # 3) ทำ
        print("   [DRY_RUN] ไม่ส่งจริง")
        break
    r = call("POST", "/offers", json={"offers": offers})
    if r.status_code != 200:
        print("   ❌", r.status_code, r.json())
        break
    for res in r.json()["results"]:
        sold_total += res["sold"]
        if not res["sold"]:
            fails[res["lot_id"]] = fails.get(res["lot_id"], 0) + 1          # จำไว้ รอบหน้าลดราคา
        print(f"   ผล: ล็อต {res['lot_id']} {'✅ ขายได้' if res['sold'] else '❌ ไม่ขาย'}")
    time.sleep(0.3)                                           # เว้นจังหวะ ไม่ยิงถี่เกิน rate limit

print(f"\nจบเกม: ขายได้ {sold_total} ล็อต · log อยู่ในโฟลเดอร์ logs/")

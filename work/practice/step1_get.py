# step1_get.py · ฝึก GET: ขอดูข้อมูลจาก API แล้วอ่าน JSON
# ต้องเปิด practice\mock_market.py ไว้ก่อน (อีกหน้าต่าง)
# รัน: .venv\Scripts\python.exe practice\step1_get.py

import json                                   # ไว้จัด JSON ให้อ่านง่ายตอนพิมพ์

import requests                               # ไลบรารีส่งคำขอ HTTP

BASE_URL = "http://127.0.0.1:8000"            # ที่อยู่ server (วันแข่งเปลี่ยนเป็นของผู้จัด)
TOKEN = "practice-token"                      # token ฝึก (วันแข่งใช้ของทีม ห้าม commit)
HEADERS = {"Authorization": f"Bearer {TOKEN}"}  # แนบ token ไปกับคำขอทาง header

# 1) GET แบบไม่ต้องใช้ token
r = requests.get(f"{BASE_URL}/health", timeout=10)   # timeout=10 กันโปรแกรมค้างถ้า server ไม่ตอบ
print("1) /health status:", r.status_code, "→", r.json())

# 2) GET แบบลืมใส่ token → ควรได้ 401
r = requests.get(f"{BASE_URL}/market", timeout=10)
print("2) /market ไม่ใส่ token:", r.status_code, "→", r.json()["error"])

# 3) GET แบบใส่ token → ได้ข้อมูลตลาด
r = requests.get(f"{BASE_URL}/market", headers=HEADERS, timeout=10)
print("3) /market ใส่ token:", r.status_code)
if r.status_code != 200:                      # ⚠️ เช็ก status ก่อนอ่านข้อมูลเสมอ (เช่น 429 เรียกถี่เกิน)
    print("   ผิดพลาด:", r.json().get("error"), "→ รอ 1–2 วินาทีแล้วรันใหม่")
    raise SystemExit(1)
data = r.json()                               # แปลง JSON เป็น dict ของ Python
print(json.dumps(data, ensure_ascii=False, indent=2)[:600], "...")   # พิมพ์ 600 ตัวอักษรแรก

# 4) หยิบข้อมูลจาก dict/list มาใช้
print("\n4) รอบที่", data["round"], "จาก", data["rounds_total"])
for lot in data["lots"]:                      # วนทีละล็อต
    if lot["moisture"] is None:               # None = ยังไม่มีผลวัด (JSON เขียนว่า null)
        print(f"   ล็อต {lot['id']} หนัก {lot['weight']} กก. · ยังไม่มีผลวัด")
    else:
        print(f"   ล็อต {lot['id']} หนัก {lot['weight']} กก. · ความชื้น {lot['moisture']}% "
              f"เมล็ดเสีย {lot['defect_pct']}% ขนาด {lot['size']}")
for b in data["buyers"]:
    print(f"   ผู้ซื้อ {b['id']} ({b['type']}) รับความชื้น ≤{b['max_moisture']}% เมล็ดเสีย ≤{b['max_defect']}%")

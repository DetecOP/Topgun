# เฉลยข้อ 5: requests กับเซิร์ฟเวอร์ฝึก (ต้องรัน practice_server.py ค้างไว้ก่อน)
import requests  # ไลบรารีสำหรับส่งคำขอ HTTP

BASE = "http://127.0.0.1:8000"  # เซิร์ฟเวอร์ฝึกบนเครื่องตัวเอง (ไม่ใช่ API จริง)

# 1) GET /lots
r = requests.get(f"{BASE}/lots", timeout=10)  # ส่ง GET
print("1) จำนวนล็อต:", len(r.json()["lots"]))  # แปลง JSON แล้วนับจำนวน

# 2) GET /me โดยไม่ใส่ token
r = requests.get(f"{BASE}/me", timeout=10)
print("2) ไม่มี token ได้ status:", r.status_code)  # ควรได้ 401

# 3) GET /me โดยใส่ token
headers = {"Authorization": "Bearer practice-token"}  # header สำหรับยืนยันตัวตน
r = requests.get(f"{BASE}/me", headers=headers, timeout=10)
print("3) ทีม:", r.json()["team"])

# 4) POST /echo
r = requests.post(f"{BASE}/echo", json={"lot_id": "A1", "price": 85}, timeout=10)  # json= แปลง dict ให้อัตโนมัติ
print("4) ได้กลับมา:", r.json())

# 5) GET /error แล้วจับ error
try:
    r = requests.get(f"{BASE}/error", timeout=10)
    r.raise_for_status()  # ถ้า status เป็น 4xx/5xx จะโยน HTTPError
    print("5) สำเร็จ (ไม่ควรมาถึงตรงนี้)")
except requests.exceptions.HTTPError:
    print("5) เซิร์ฟเวอร์ตอบ error", r.status_code, "→", r.json().get("error"))
except requests.exceptions.ConnectionError:
    print("5) ต่อเซิร์ฟเวอร์ไม่ได้ ลืมเปิด practice_server.py หรือเปล่า?")

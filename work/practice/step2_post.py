# step2_post.py · ฝึก POST: ส่งข้อเสนอขาย 1 ข้อ และจัดการ error ทุกแบบ
# ต้องเปิด practice\mock_market.py ไว้ก่อน · ส่งไปที่ตลาดจำลองในเครื่องเท่านั้น
# รัน: .venv\Scripts\python.exe practice\step2_post.py

import requests

BASE_URL = "http://127.0.0.1:8000"
HEADERS = {"Authorization": "Bearer practice-token"}


def post_offers(offers):
    """ส่งข้อเสนอ แล้วคืน dict ผลลัพธ์ หรือ None ถ้าพลาด (พิมพ์สาเหตุให้อ่านง่าย)"""
    try:
        r = requests.post(f"{BASE_URL}/offers", json={"offers": offers},   # json= แปลง dict เป็น JSON ให้เอง
                          headers=HEADERS, timeout=10)
    except requests.exceptions.ConnectionError:
        print("❌ ต่อ server ไม่ได้ (ลืมเปิด mock_market.py หรือ URL ผิด)")
        return None
    except requests.exceptions.Timeout:
        print("❌ server ตอบช้าเกิน 10 วินาที")
        return None
    if r.status_code == 200:
        return r.json()
    msg = r.json().get("error", r.text) if r.content else ""
    hints = {400: "ข้อมูลที่ส่งผิดรูปแบบ", 401: "token ผิด", 404: "path ผิด",
             409: "สถานะเกมไม่ให้ทำ", 429: "เรียกถี่เกิน รอแล้วลองใหม่"}
    print(f"❌ {r.status_code} {hints.get(r.status_code, '')}: {msg} {r.json().get('details', '') if r.content else ''}")
    return None


# 1) ดูตลาดก่อน
market = requests.get(f"{BASE_URL}/market", headers=HEADERS, timeout=10).json()
lot = market["lots"][0]                       # หยิบล็อตแรกที่ยังไม่ขาย
print("จะเสนอขายล็อต", lot["id"], "ให้ B2")

# 2) ส่งแบบผิดก่อน เพื่อดูว่า error หน้าตาเป็นอย่างไร
print("\nลองส่งราคาเป็นข้อความ (ผิด):")
post_offers([{"lot_id": lot["id"], "buyer_id": "B2", "price_per_kg": "แพงๆ"}])

# 3) ส่งแบบถูก
print("\nส่งแบบถูก:")
result = post_offers([{"lot_id": lot["id"], "buyer_id": "B2", "price_per_kg": 95.0}])
if result:
    for res in result["results"]:
        print(f"✅ รอบ {res['round']} ล็อต {res['lot_id']} → {res['buyer_id']} "
              f"ราคา {res['price_per_kg']} : {'ขายได้' if res['sold'] else 'ขายไม่ได้'}")

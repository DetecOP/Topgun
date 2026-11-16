# api_test.py · ทดสอบเรียก API ของผู้จัด (อ่านอย่างเดียว ด้วย GET)
#
# ไฟล์นี้ "ไม่ส่งข้อเสนอขาย" (ไม่มี POST) เพื่อกันส่งคำสั่งจริงโดยไม่ตั้งใจ
# วิธีใช้:
#   1) กรอก BASE_URL, TOKEN, AUTH_HEADER และ ENDPOINTS ตามเอกสาร API ที่ได้วันที่ 17 พ.ย.
#   2) รัน: .venv\Scripts\python.exe api_test.py
# ทุกคำขอและคำตอบถูกบันทึกลง logs/ ด้วย log_template.py

import json                                   # จัดรูป JSON ให้อ่านง่าย
import sys                                    # ตั้งการแสดงผลภาษาไทย และส่งรหัสออก
import time                                   # จับเวลาที่ใช้ต่อคำขอ

import requests                               # ไลบรารีเรียก HTTP (ติดตั้งใน .venv แล้ว)

from log_template import log_exchange         # ฟังก์ชันบันทึก log ที่เราเขียนเอง

sys.stdout.reconfigure(encoding="utf-8")      # ให้พิมพ์ภาษาไทยได้บน Windows

# ===================== กรอกตรงนี้ (ยังไม่ทราบค่าจริง) =====================
BASE_URL = ""          # ที่อยู่หลักของ API เช่น "http://..." ไม่ต้องมี / ท้าย  ← ยังไม่ทราบ
TOKEN = ""             # token ของทีม ห้ามแชร์ ห้าม commit ลง Git           ← ยังไม่ทราบ
AUTH_HEADER = "Authorization"   # ชื่อ header ที่ใช้ส่ง token                ← ยังไม่ทราบ (อาจเป็น X-API-Key)
AUTH_PREFIX = "Bearer "         # คำนำหน้า token ถ้า API ไม่ใช้ ให้แก้เป็น ""  ← ยังไม่ทราบ
ENDPOINTS = [          # รายการ path ที่จะลองเรียกด้วย GET               ← ยังไม่ทราบ
    # "/market",       # ตัวอย่างรูปแบบเท่านั้น ใส่ path จริงตามเอกสารผู้จัด
]
TIMEOUT = 10           # วินาทีสูงสุดที่ยอมรอคำตอบต่อ 1 คำขอ
# =====================================================================


def build_headers():
    """สร้าง header ที่จะแนบไปกับทุกคำขอ"""
    headers = {"Accept": "application/json"}                # บอกเซิร์ฟเวอร์ว่าอยากได้ JSON
    if TOKEN:                                               # แนบ token เฉพาะเมื่อกรอกไว้แล้ว
        headers[AUTH_HEADER] = f"{AUTH_PREFIX}{TOKEN}"
    return headers


def explain_status(code):
    """แปลรหัส HTTP เป็นภาษาไทยสั้นๆ"""
    table = {
        200: "สำเร็จ", 201: "สร้างสำเร็จ",
        400: "ข้อมูลที่ส่งผิดรูปแบบ", 401: "ไม่มี token หรือ token ผิด",
        403: "ไม่มีสิทธิ์", 404: "ไม่พบ URL นี้ (ตรวจ BASE_URL / endpoint)",
        429: "เรียกถี่เกิน (rate limit) ให้รอแล้วลองใหม่",
    }
    if code in table:
        return table[code]
    if 500 <= code < 600:
        return "เซิร์ฟเวอร์ผู้จัดมีปัญหา"
    return "ไม่ทราบความหมาย"


def test_get(path):
    """เรียก GET ไปที่ BASE_URL + path แล้วพิมพ์ผลแบบอ่านง่าย คืน True ถ้าสำเร็จ"""
    url = BASE_URL + path                                   # ต่อที่อยู่เต็ม
    headers = build_headers()
    print("-" * 60)
    print(f"GET {url}")
    start = time.perf_counter()                             # เริ่มจับเวลา
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)   # ส่งคำขอจริง
    except requests.exceptions.Timeout as e:                # รอนานเกิน TIMEOUT
        print(f"❌ รอเกิน {TIMEOUT} วินาที ไม่มีคำตอบ")
        log_exchange("GET", url, headers=headers, error=e, note="timeout")
        return False
    except requests.exceptions.ConnectionError as e:        # ต่อไม่ได้เลย
        print("❌ เชื่อมต่อไม่ได้: เน็ตหลุด, URL ผิด หรือเซิร์ฟเวอร์ปิดอยู่")
        log_exchange("GET", url, headers=headers, error=e, note="connection error")
        return False
    except requests.exceptions.RequestException as e:       # error อื่นของ requests (เช่น URL รูปแบบผิด)
        print(f"❌ ส่งคำขอไม่สำเร็จ: {e}")
        log_exchange("GET", url, headers=headers, error=e)
        return False

    ms = (time.perf_counter() - start) * 1000               # เวลาที่ใช้ (มิลลิวินาที)
    print(f"สถานะ : {r.status_code} ({explain_status(r.status_code)}) · {ms:.0f} ms")

    try:
        body = r.json()                                     # ลองแปลงคำตอบเป็น JSON
        pretty = json.dumps(body, ensure_ascii=False, indent=2)
        print("คำตอบ (JSON):")
        print(pretty[:2000] + ("\n... (ตัดเหลือ 2000 ตัวอักษร)" if len(pretty) > 2000 else ""))
    except ValueError:                                      # ไม่ใช่ JSON
        body = r.text
        print("คำตอบ (ไม่ใช่ JSON):", body[:500])

    log_exchange("GET", url, headers=headers, status=r.status_code,
                 response_body=body, note=f"{ms:.0f} ms")   # บันทึกทุกครั้ง
    return r.ok                                             # True เมื่อรหัส 200-399


def main():
    """จุดเริ่มโปรแกรม: ตรวจค่าที่กรอก แล้วทดสอบทีละ endpoint"""
    if not BASE_URL:                                        # ยังไม่ได้กรอก BASE_URL
        print("⚠️  ยังไม่ได้กรอก BASE_URL ในไฟล์ api_test.py")
        print("   กรอก BASE_URL, TOKEN, AUTH_HEADER และ ENDPOINTS ตามเอกสาร API วันที่ 17 พ.ย. แล้วรันใหม่")
        print("   (ไม่มีการส่งคำขอใดๆ ออกไป)")
        return 0                                            # ไม่ถือว่าผิดพลาด
    if not TOKEN:
        print("⚠️  TOKEN ว่างอยู่ จะลองเรียกโดยไม่แนบ token (ถ้าได้ 401 แปลว่าต้องใส่)")
    if not ENDPOINTS:
        print("⚠️  ENDPOINTS ว่าง จะลองเรียก BASE_URL เปล่าๆ แทน")

    paths = ENDPOINTS or [""]                               # ไม่มี endpoint ก็เรียก BASE_URL ตรงๆ
    results = [test_get(p) for p in paths]                  # ทดสอบทีละ path
    print("=" * 60)
    print(f"สรุป: ผ่าน {sum(results)}/{len(results)} · log อยู่ในโฟลเดอร์ logs/")
    return 0 if all(results) else 1


if __name__ == "__main__":                                  # รันเมื่อเรียกไฟล์นี้ตรงๆ
    sys.exit(main())

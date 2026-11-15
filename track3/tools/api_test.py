# api_test.py — ตัวทดสอบเรียก API (ยังไม่ใช่ agent และยังไม่มีกลยุทธ์)
# ⚠️ BASE_URL, TOKEN และ ENDPOINTS ยังว่างไว้ เพราะยังไม่ทราบค่าจริง (จะรู้ในวันอบรม 17 พ.ย.)
# 🔒 repo นี้เป็น PUBLIC: ห้ามพิมพ์ token ลงในไฟล์นี้ ให้ใส่ในไฟล์ .env ที่ root ของ repo แทน (.env ไม่ถูกอัปโหลด)
#     TGR_BASE_URL=...
#     TGR_TOKEN=...
# ถ้าอยากลองก่อน: เปิด tools/practice_server.py ไว้ แล้วใส่ TGR_BASE_URL=http://127.0.0.1:8000 และ TGR_TOKEN=practice-token
# วิธีรัน:  .\.venv\Scripts\python.exe tools\api_test.py

import json  # ใช้จัดรูป JSON ให้อ่านง่ายตอนพิมพ์
import os  # ใช้อ่านค่าจาก environment variable
import sys  # ใช้ออกจากโปรแกรมเมื่อยังกรอกค่าไม่ครบ
from pathlib import Path  # ใช้หาที่อยู่ไฟล์ .env

import requests  # ไลบรารีส่งคำขอ HTTP

from log_template import logged_request  # ฟังก์ชันส่งคำขอที่บันทึก log ให้อัตโนมัติ


def load_dotenv():  # อ่านไฟล์ .env (บรรทัดละ KEY=VALUE) แล้วใส่เข้า environment
    for folder in [Path.cwd(), *Path(__file__).resolve().parents]:  # หา .env จากโฟลเดอร์ปัจจุบันไล่ขึ้นไป
        env = folder / ".env"  # ที่อยู่ไฟล์ .env ในโฟลเดอร์นั้น
        if env.is_file():  # ถ้าเจอไฟล์
            for line in env.read_text(encoding="utf-8").splitlines():  # อ่านทีละบรรทัด
                line = line.strip()  # ตัดช่องว่างหัวท้าย
                if line and not line.startswith("#") and "=" in line:  # ข้ามบรรทัดว่างและคอมเมนต์
                    key, value = line.split("=", 1)  # แยกชื่อกับค่าที่เครื่องหมาย = ตัวแรก
                    os.environ.setdefault(key.strip(), value.strip().strip('"'))  # ไม่ทับค่าที่ตั้งไว้แล้ว
            return  # เจอไฟล์แรกแล้วหยุด


load_dotenv()  # โหลด .env ตอนเริ่มโปรแกรม

# ========== ส่วนที่ต้องกรอกเอง (ใน .env) ==========
BASE_URL = os.environ.get("TGR_BASE_URL", "")  # ที่อยู่ API ของผู้จัด (ยังไม่ทราบ ห้ามเดา)
TOKEN = os.environ.get("TGR_TOKEN", "")  # token ของทีม (ยังไม่ทราบ) ห้ามแชร์ใน LINE หรือ GitHub
AUTH_HEADER_NAME = "Authorization"  # ชื่อ header ที่ใช้ส่ง token (ต้องตรวจกับเอกสารจริงอีกที)
AUTH_PREFIX = "Bearer "  # คำนำหน้า token (บาง API ไม่มี ให้แก้เป็น "" ถ้าเอกสารบอก)

# รายการคำขอที่จะทดสอบ: (วิธี, path, ข้อมูลที่ส่ง)
# ใส่ตามเอกสาร API จริง เช่น ("GET", "/xxx", None) หรือ ("POST", "/yyy", {"key": "value"})
ENDPOINTS = [
    # ("GET", "/lots", None),          # ← ตัวอย่างสำหรับ practice_server.py เท่านั้น
    # ("POST", "/echo", {"hello": 1}), # ← ตัวอย่างสำหรับ practice_server.py เท่านั้น
]
TIMEOUT = 10  # รอคำตอบนานสุดกี่วินาที
# =======================================


def build_headers():  # สร้าง header สำหรับทุกคำขอ
    headers = {"Accept": "application/json"}  # บอกเซิร์ฟเวอร์ว่าอยากได้คำตอบเป็น JSON
    if TOKEN:  # ใส่ token เฉพาะเมื่อกรอกไว้
        headers[AUTH_HEADER_NAME] = AUTH_PREFIX + TOKEN  # เช่น Authorization: Bearer xxx
    return headers  # ส่ง dict ของ header กลับไป


def show(title, text):  # พิมพ์หัวข้อและเนื้อหาให้อ่านง่าย
    print("-" * 60)  # เส้นคั่น
    print(title)  # หัวข้อ
    print(text)  # เนื้อหา


def call(method, path, body=None):  # ส่งคำขอ 1 ครั้ง แล้วพิมพ์ผลแบบอ่านง่าย
    url = BASE_URL.rstrip("/") + path  # ต่อ BASE_URL กับ path (ตัด / ที่ซ้ำออก)
    try:
        r = logged_request(method, url, headers=build_headers(), json=body, timeout=TIMEOUT)  # ส่งคำขอและบันทึก log
    except requests.exceptions.Timeout:  # เซิร์ฟเวอร์ไม่ตอบภายในเวลาที่กำหนด
        show(f"❌ {method} {path}", f"หมดเวลา ({TIMEOUT} วินาที) เซิร์ฟเวอร์ไม่ตอบ")
        return None  # คืน None เพื่อบอกว่าไม่สำเร็จ
    except requests.exceptions.ConnectionError:  # ต่อไม่ได้เลย
        show(f"❌ {method} {path}", "ต่อเซิร์ฟเวอร์ไม่ได้ ให้ตรวจ BASE_URL, Wi-Fi หรือดูว่าเซิร์ฟเวอร์เปิดอยู่ไหม")
        return None
    except requests.exceptions.RequestException as e:  # error อื่นๆ ของ requests
        show(f"❌ {method} {path}", f"error: {e}")
        return None

    ok = 200 <= r.status_code < 300  # status 2xx ถือว่าสำเร็จ
    hint = {  # คำแนะนำตาม status code ที่พบบ่อย
        400: "ส่งข้อมูลผิดรูปแบบ ให้ตรวจ body",
        401: "token ผิดหรือไม่ได้ใส่",
        403: "ไม่มีสิทธิ์",
        404: "path ผิด ให้ตรวจ URL",
        429: "ส่งถี่เกินไป ให้เว้นจังหวะ",
    }.get(r.status_code, "เซิร์ฟเวอร์มีปัญหา" if r.status_code >= 500 else "")  # 5xx = ปัญหาฝั่งเซิร์ฟเวอร์
    try:
        content = json.dumps(r.json(), ensure_ascii=False, indent=2)  # ถ้าเป็น JSON จัดรูปให้สวย
    except ValueError:
        content = r.text[:1000]  # ถ้าไม่ใช่ JSON แสดงข้อความ 1000 ตัวแรก
    mark = "✅" if ok else "⚠️"  # สัญลักษณ์บอกผล
    show(f"{mark} {method} {path} → {r.status_code} {hint}  ({r.elapsed.total_seconds():.2f}s)", content)  # พิมพ์ผล
    return r  # ส่งผลลัพธ์กลับไป เผื่อใช้ต่อ


def main():  # จุดเริ่มต้นของโปรแกรม
    if not BASE_URL:  # ถ้ายังไม่ได้กรอก BASE_URL
        print("ยังไม่ได้กรอก TGR_BASE_URL ให้คัดลอก .env.example เป็น .env ที่ root ของ repo แล้วใส่ค่า")
        sys.exit(1)  # ออกจากโปรแกรม (1 = มีปัญหา)
    if not ENDPOINTS:  # ถ้ายังไม่ได้ใส่ endpoint
        print("ยังไม่มี ENDPOINTS ให้เพิ่มตามเอกสาร API จริง")
        sys.exit(1)
    print(f"ทดสอบ {BASE_URL}  (token: {'มี' if TOKEN else 'ไม่มี'})")  # ไม่พิมพ์ token ออกจอ
    results = [call(m, p, b) for (m, p, b) in ENDPOINTS]  # เรียกทุก endpoint ตามลำดับ
    passed = sum(1 for r in results if r is not None and r.ok)  # นับว่าสำเร็จกี่ตัว
    print("=" * 60)  # เส้นคั่นท้าย
    print(f"สำเร็จ {passed}/{len(results)} · log อยู่ในโฟลเดอร์ logs/")  # สรุป


if __name__ == "__main__":  # ทำงานเมื่อรันไฟล์นี้โดยตรง
    main()  # เรียก main

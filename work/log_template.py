# log_template.py · บันทึกทุกคำขอและคำตอบของ API ลงไฟล์
#
# วิธีใช้ในไฟล์อื่น:
#     from log_template import log_exchange
#     log_exchange("GET", url, request_body=None, status=200, response_body=data)
#
# ผลลัพธ์: ไฟล์ logs/api_YYYY-MM-DD.jsonl เก็บ 1 บรรทัดต่อ 1 ครั้งที่เรียก (รูปแบบ JSON Lines)
# ไม่ต้องกลัวไฟล์พังถ้าโปรแกรมหยุดกลางคัน เพราะเขียนทีละบรรทัดแล้วปิดไฟล์ทันที

import json                                  # แปลง dict -> ข้อความ JSON
import sys                                   # ใช้ตั้งการแสดงผลภาษาไทย
from datetime import datetime                # เวลาปัจจุบัน
from pathlib import Path                     # จัดการ path ไฟล์แบบปลอดภัยทุกระบบ

LOG_DIR = Path(__file__).parent / "logs"     # โฟลเดอร์ logs ข้างไฟล์นี้ (work/logs)

SECRET_KEYS = {"authorization", "token", "api_key", "x-api-key", "password"}  # ชื่อช่องที่ห้ามบันทึกค่าจริง


def _hide_secrets(obj):
    """แทนค่าของช่องลับด้วย *** ก่อนเขียนลงไฟล์ (กัน token หลุดไปอยู่ใน log)"""
    if isinstance(obj, dict):                                   # ถ้าเป็น dict ให้ตรวจทีละ key
        return {k: ("***" if str(k).lower() in SECRET_KEYS else _hide_secrets(v))
                for k, v in obj.items()}
    if isinstance(obj, list):                                   # ถ้าเป็น list ให้ตรวจทีละตัว
        return [_hide_secrets(v) for v in obj]
    return obj                                                  # ค่าธรรมดา คืนค่าเดิม


def log_exchange(method, url, request_body=None, status=None, response_body=None,
                 error=None, headers=None, note=""):
    """บันทึกคำขอและคำตอบ 1 ครั้ง ต่อท้ายไฟล์ของวันนี้ แล้วคืน path ของไฟล์"""
    LOG_DIR.mkdir(exist_ok=True)                                # สร้างโฟลเดอร์ logs ถ้ายังไม่มี
    now = datetime.now()                                        # เวลาตอนบันทึก
    record = {                                                  # ข้อมูล 1 บรรทัด
        "time": now.isoformat(timespec="milliseconds"),         # เวลาละเอียดระดับมิลลิวินาที
        "method": method,                                       # GET / POST
        "url": url,                                             # ที่อยู่ที่เรียก
        "headers": _hide_secrets(headers or {}),                # header (ซ่อน token แล้ว)
        "request": _hide_secrets(request_body),                 # ข้อมูลที่ส่งไป
        "status": status,                                       # รหัสผลลัพธ์ เช่น 200
        "response": _hide_secrets(response_body),               # ข้อมูลที่ได้กลับมา
        "error": str(error) if error else None,                 # ข้อความ error (ถ้ามี)
        "note": note,                                           # หมายเหตุเพิ่มเติม เช่น "รอบ 3"
    }
    path = LOG_DIR / f"api_{now:%Y-%m-%d}.jsonl"                 # ไฟล์แยกตามวัน
    with open(path, "a", encoding="utf-8") as f:                # "a" = เขียนต่อท้าย
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")  # default=str กันค่าแปลกๆ แปลงไม่ได้
    return path


def read_log(path):
    """อ่านไฟล์ log กลับมาเป็น list ของ dict (ใช้วิเคราะห์ย้อนหลัง)"""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:                                          # อ่านทีละบรรทัด
            line = line.strip()
            if line:                                            # ข้ามบรรทัดว่าง
                records.append(json.loads(line))
    return records


if __name__ == "__main__":                                      # ส่วนนี้ทำงานเมื่อรันไฟล์นี้ตรงๆ เท่านั้น (ทดสอบ)
    sys.stdout.reconfigure(encoding="utf-8")
    p = log_exchange("GET", "http://example.invalid/test",      # ข้อมูลทดสอบ ไม่ได้ส่งไปไหนจริง
                     headers={"Authorization": "Bearer ลองซ่อน"},
                     status=200, response_body={"ok": True}, note="ทดสอบ log_template")
    last = read_log(p)[-1]                                      # อ่านบรรทัดล่าสุดกลับมา
    print("บันทึกที่:", p)
    print("บรรทัดล่าสุด:", json.dumps(last, ensure_ascii=False))
    print("token ถูกซ่อนแล้ว:", last["headers"]["Authorization"] == "***")

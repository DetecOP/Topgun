# log_template.py — บันทึกทุกคำขอและคำตอบ API ลงไฟล์ ไว้ตรวจย้อนหลังระหว่างแข่ง
# วิธีใช้ในไฟล์อื่น:
#     from log_template import logged_request
#     r = logged_request("GET", url, headers=headers)
# ไฟล์ log จะอยู่ที่ logs/api_YYYY-MM-DD.jsonl (หนึ่งบรรทัดต่อหนึ่งคำขอ เปิดดูด้วย VS Code หรือ pandas ได้)

import json  # แปลงข้อมูลเป็นข้อความ JSON
import time  # จับเวลาว่าคำขอใช้เวลานานแค่ไหน
from datetime import datetime  # เวลาปัจจุบันสำหรับบันทึก
from pathlib import Path  # จัดการที่อยู่ไฟล์และโฟลเดอร์

import requests  # ไลบรารีส่งคำขอ HTTP

LOG_DIR = Path(__file__).parent / "logs"  # โฟลเดอร์ logs อยู่ข้างไฟล์นี้
SECRET_HEADERS = {"authorization", "x-api-key", "api-key", "token"}  # header ที่เป็นความลับ ห้ามบันทึกค่าจริง


def _mask_headers(headers):  # ซ่อน token ก่อนบันทึกลงไฟล์ กันหลุดเวลาส่ง log ให้คนอื่นดู
    out = {}  # dict ใหม่สำหรับเก็บผล
    for k, v in (headers or {}).items():  # วนทุก header
        if k.lower() in SECRET_HEADERS:  # ถ้าเป็น header ลับ
            out[k] = "***"  # ใส่ดาวแทนค่าจริง
        else:
            out[k] = v  # header ทั่วไปบันทึกตามจริง
    return out  # ส่ง dict ที่ซ่อนแล้วกลับไป


def write_log(entry):  # เขียนข้อมูล 1 รายการต่อท้ายไฟล์ log ของวันนี้
    LOG_DIR.mkdir(exist_ok=True)  # สร้างโฟลเดอร์ logs ถ้ายังไม่มี
    path = LOG_DIR / f"api_{datetime.now():%Y-%m-%d}.jsonl"  # ชื่อไฟล์ตามวันที่
    with open(path, "a", encoding="utf-8") as f:  # "a" = เขียนต่อท้าย ไม่ลบของเดิม
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")  # 1 บรรทัด = 1 รายการ


def logged_request(method, url, **kwargs):  # ใช้แทน requests.request โดยบันทึก log ให้อัตโนมัติ
    kwargs.setdefault("timeout", 10)  # ถ้าไม่ได้กำหนด timeout ให้ใช้ 10 วินาที
    entry = {  # ข้อมูลที่จะบันทึก
        "time": datetime.now().isoformat(timespec="milliseconds"),  # เวลาที่ส่ง
        "method": method,  # GET / POST / ...
        "url": url,  # ที่อยู่ที่เรียก
        "headers": _mask_headers(kwargs.get("headers")),  # header ที่ซ่อน token แล้ว
        "params": kwargs.get("params"),  # ค่าที่ต่อท้าย URL (ถ้ามี)
        "body": kwargs.get("json"),  # ข้อมูลที่ส่งไป (ถ้ามี)
    }
    start = time.perf_counter()  # เริ่มจับเวลา
    try:
        r = requests.request(method, url, **kwargs)  # ส่งคำขอจริง
        entry["status"] = r.status_code  # บันทึก status code
        try:
            entry["response"] = r.json()  # ถ้าคำตอบเป็น JSON ให้บันทึกเป็นโครงสร้าง
        except ValueError:
            entry["response"] = r.text[:2000]  # ถ้าไม่ใช่ JSON เก็บข้อความ 2000 ตัวแรก
        return r  # ส่งผลลัพธ์กลับไปให้โค้ดที่เรียกใช้
    except requests.exceptions.RequestException as e:  # error ฝั่งการเชื่อมต่อ (timeout, เน็ตหลุด ฯลฯ)
        entry["error"] = f"{type(e).__name__}: {e}"  # บันทึกชนิดและข้อความของ error
        raise  # โยน error ต่อไปให้โค้ดที่เรียกใช้ตัดสินใจเอง
    finally:  # ส่วนนี้ทำเสมอ ไม่ว่าสำเร็จหรือ error
        entry["ms"] = round((time.perf_counter() - start) * 1000)  # เวลาที่ใช้ (มิลลิวินาที)
        write_log(entry)  # เขียนลงไฟล์


def read_logs(date=None):  # อ่าน log กลับมาเป็น list ของ dict ไว้ตรวจย้อนหลัง
    date = date or f"{datetime.now():%Y-%m-%d}"  # ถ้าไม่ระบุวัน ใช้วันนี้
    path = LOG_DIR / f"api_{date}.jsonl"  # ไฟล์ของวันนั้น
    if not path.exists():  # ถ้ายังไม่มีไฟล์
        return []  # ส่ง list ว่างกลับไป
    with open(path, encoding="utf-8") as f:  # เปิดอ่าน
        return [json.loads(line) for line in f if line.strip()]  # แปลงทีละบรรทัดกลับเป็น dict


if __name__ == "__main__":  # ทดลองเมื่อรันไฟล์นี้ตรงๆ (ต้องเปิด practice_server.py ไว้ก่อน)
    try:
        logged_request("GET", "http://127.0.0.1:8000/lots")  # เรียกเซิร์ฟเวอร์ฝึก
        logged_request("POST", "http://127.0.0.1:8000/echo", json={"test": 1},
                       headers={"Authorization": "Bearer practice-token"})  # token จะถูกซ่อนใน log
    except requests.exceptions.ConnectionError:
        print("ต่อ practice_server.py ไม่ได้ (แต่ error นี้ก็ถูกบันทึกลง log แล้ว)")
    for row in read_logs()[-3:]:  # แสดง 3 รายการล่าสุด
        print(row["time"], row["method"], row["url"], row.get("status"), row.get("error", ""), f'{row["ms"]}ms')

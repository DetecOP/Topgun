# ติดตั้งแพ็กเกจแบบออฟไลน์ (ไม่ต้องใช้อินเทอร์เน็ต)

สร้างเมื่อ 2026-11-14 · ทดสอบบน Windows 11 + Python 3.14.8 แล้ว ✅

## มีอะไรอยู่ในโฟลเดอร์นี้

| ไฟล์/โฟลเดอร์ | คืออะไร |
|---|---|
| `wheelhouse\` | ไฟล์แพ็กเกจ (.whl) 62 ไฟล์ ราว 115 MB ใช้ติดตั้งได้โดยไม่ต้องต่อเน็ต |
| `requirements.txt` | รายชื่อแพ็กเกจหลัก 7 ตัว: requests, pandas, openpyxl, gradio, ollama, paho-mqtt, opencv-python |
| `.venv\` | virtual environment ที่ติดตั้งแพ็กเกจครบแล้ว |

> ⚠️ ไฟล์ใน wheelhouse ใช้ได้กับ **Python 3.14 บน Windows 64-bit** เท่านั้น
> ถ้าเปลี่ยนเครื่องหรือเปลี่ยนเวอร์ชัน Python ต้องดาวน์โหลดใหม่ตอนที่ยังมีเน็ต

## กรณีที่ 1: ใช้ .venv ที่มีอยู่แล้ว (ใช้บ่อยที่สุด)

เปิด PowerShell แล้วพิมพ์:

```powershell
cd track3
.\.venv\Scripts\Activate.ps1
```

- `cd "..."` ย้ายเข้าไปในโฟลเดอร์ work (ต้องใส่เครื่องหมาย " เพราะชื่อโฟลเดอร์มีช่องว่าง)
- `.\.venv\Scripts\Activate.ps1` เปิดใช้ virtual environment ถ้าสำเร็จ หน้าบรรทัดจะมีคำว่า `(.venv)` ขึ้นมา

ถ้าขึ้น error เรื่อง "running scripts is disabled" ให้ข้ามการ Activate แล้วเรียก Python ของ .venv ตรงๆ แทน:

```powershell
.\.venv\Scripts\python.exe toolspi_test.py
```

## กรณีที่ 2: สร้าง .venv ใหม่แล้วติดตั้งแบบออฟไลน์

ใช้ตอนที่ .venv เสีย หรือย้ายโฟลเดอร์ไปที่อื่น

```powershell
cd track3
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse -r requirements.txt
```

ความหมายของแต่ละส่วน:
- `python -m venv .venv` สร้าง virtual environment ชื่อ `.venv` ซึ่งเป็นกล่อง Python แยกเฉพาะงานนี้ ไม่ปนกับเครื่อง
- `-m pip install` ติดตั้งแพ็กเกจด้วย pip
- `--no-index` ห้ามไปหาแพ็กเกจบนอินเทอร์เน็ต (PyPI)
- `--find-links wheelhouse` ให้หาไฟล์แพ็กเกจในโฟลเดอร์ `wheelhouse` แทน
- `-r requirements.txt` อ่านรายชื่อแพ็กเกจจากไฟล์นี้

## ตรวจว่าติดตั้งครบ

```powershell
.\.venv\Scripts\python.exe -c "import requests, pandas, openpyxl, gradio, ollama, paho.mqtt.client, cv2; print('OK')"
```

- `-c "..."` รันโค้ด Python สั้นๆ ที่เขียนต่อท้าย
- `import ...` โหลดแพ็กเกจทุกตัว ถ้าตัวไหนไม่มีจะขึ้น `ModuleNotFoundError`
- ถ้าเห็น `OK` แปลว่าครบ

## ถ้าต้องการแพ็กเกจเพิ่ม (ต้องทำตอนที่ยังมีเน็ต)

```powershell
.\.venv\Scripts\python.exe -m pip download --dest wheelhouse --only-binary=:all: ชื่อแพ็กเกจ
```

- `pip download` ดาวน์โหลดไฟล์มาเก็บไว้เฉยๆ ยังไม่ติดตั้ง
- `--dest wheelhouse` บอกให้เก็บไฟล์ไว้ในโฟลเดอร์ wheelhouse
- `--only-binary=:all:` เอาเฉพาะไฟล์สำเร็จรูป (.whl) ซึ่งติดตั้งได้ทันทีโดยไม่ต้อง compile

จากนั้นเพิ่มชื่อแพ็กเกจลงใน `requirements.txt` ด้วย

## ผลการทดสอบ (2026-11-14)

- `pip install --no-index --find-links wheelhouse -r requirements.txt` ✅ สำเร็จ
- import ทุกตัวได้: requests 2.34.2, pandas 3.1.1, openpyxl 3.1.5, gradio 6.32.0, opencv 5.0.0, ollama 0.6.3, paho-mqtt 2.2.0

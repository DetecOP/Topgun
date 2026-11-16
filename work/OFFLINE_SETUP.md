# ติดตั้งแบบไม่มีอินเทอร์เน็ต (Offline Setup)

> ใช้ตอนเน็ตที่สนามแข่งล่ม หรือต้องสร้าง `.venv` ใหม่บนเครื่องเดิม
> ทดสอบแล้วว่าใช้ได้จริงเมื่อ 16 พ.ย. 2026

## สิ่งที่อยู่ในโฟลเดอร์ work/

| ไฟล์/โฟลเดอร์ | คืออะไร |
|---|---|
| `.venv/` | virtual environment คือที่แยกเก็บแพ็กเกจของงานนี้ ไม่ปนกับ Python หลักของเครื่อง |
| `wheelhouse/` | ไฟล์แพ็กเกจ (.whl) 11 ไฟล์ รวมประมาณ 24 MB ที่ดาวน์โหลดเก็บไว้ล่วงหน้า |
| `requirements.txt` | รายชื่อแพ็กเกจพร้อมเวอร์ชันที่ล็อกไว้ |

แพ็กเกจที่มี: requests 2.34.2, pandas 3.1.1, openpyxl 3.1.5 และตัวที่แพ็กเกจเหล่านี้ต้องใช้ (numpy, urllib3, certifi, idna, charset-normalizer, python-dateutil, tzdata, et-xmlfile)

## ⚠️ ข้อจำกัด
ไฟล์ `numpy` `pandas` `charset_normalizer` เป็นแบบ **`cp314-win_amd64`** แปลว่าใช้ได้กับ **Python 3.14 บน Windows 64 บิต** เท่านั้น
ถ้าเพื่อนร่วมทีมใช้ Python เวอร์ชันอื่นหรือใช้ Mac ไฟล์ชุดนี้ใช้ไม่ได้ เครื่องนั้นต้องดาวน์โหลดใหม่ตอนที่ยังมีเน็ต

## วิธีติดตั้ง (เปิด PowerShell ที่โฟลเดอร์ work/)

### 1. สร้าง .venv (ข้ามได้ถ้ามีอยู่แล้ว)
```powershell
py -m venv .venv
```
- `py` คือตัวเรียก Python ของ Windows
- `-m venv` สั่งให้รันโมดูล venv ซึ่งมีหน้าที่สร้าง virtual environment
- `.venv` คือชื่อโฟลเดอร์ที่จะสร้าง

### 2. ติดตั้งจาก wheelhouse โดยไม่ใช้เน็ต
```powershell
.venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse -r requirements.txt
```
- `.venv\Scripts\python.exe` เรียก Python ตัวที่อยู่ใน .venv (ไม่ใช่ตัวหลักของเครื่อง)
- `-m pip install` สั่งติดตั้งแพ็กเกจ
- `--no-index` ห้ามไปค้นแพ็กเกจบนอินเทอร์เน็ต (pypi.org)
- `--find-links wheelhouse` ให้หาไฟล์แพ็กเกจในโฟลเดอร์ wheelhouse แทน
- `-r requirements.txt` ติดตั้งทุกตัวตามรายชื่อและเวอร์ชันในไฟล์นี้

### 3. ทดสอบว่าใช้ได้
```powershell
.venv\Scripts\python.exe -c "import requests, pandas, openpyxl; print('ผ่าน')"
```
- `-c "..."` รันโค้ด Python สั้นๆ ที่อยู่ในเครื่องหมายคำพูด
- ถ้าขึ้นว่า `ผ่าน` แปลว่าพร้อมใช้งาน

## ถ้ามีเน็ตและอยากดาวน์โหลด wheelhouse ใหม่
```powershell
.venv\Scripts\python.exe -m pip download requests pandas openpyxl -d wheelhouse --only-binary=:all:
```
- `download` ดาวน์โหลดไฟล์มาเก็บอย่างเดียว ยังไม่ติดตั้ง
- `-d wheelhouse` บอกว่าให้เก็บไว้ในโฟลเดอร์ wheelhouse
- `--only-binary=:all:` เอาเฉพาะไฟล์สำเร็จรูป (.whl) ไม่เอาซอร์สโค้ดที่ต้องคอมไพล์เอง

## ปัญหาที่อาจเจอ
| อาการ | สาเหตุ | วิธีแก้ |
|---|---|---|
| `No matching distribution found` | Python คนละเวอร์ชันกับไฟล์ใน wheelhouse | ตรวจด้วย `py --version` ซึ่งต้องเป็น 3.14 |
| `running scripts is disabled` ตอน activate | Windows ไม่อนุญาตให้รันสคริปต์ | ไม่ต้อง activate ให้เรียก `.venv\Scripts\python.exe` ตรงๆ แบบในคู่มือนี้แทน |
| ข้อความ `[notice] A new release of pip` | แค่แจ้งว่ามี pip เวอร์ชันใหม่ | ไม่ต้องทำอะไร |

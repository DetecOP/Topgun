# Track 3 — The Next-Gen Market (ห้อง 3 · Python & AI)

พื้นที่งานของทีมสำหรับ TESA Top Gun Rally 2026 Track 3: ให้ AI Agent ขายเมล็ดกาแฟโรบัสตาดิบแทนเรา

> 🔒 **repo นี้เป็น PUBLIC** ทีมอื่นเปิดดูได้ ห้าม commit token, URL ลับ, ไฟล์ `.env` และไฟล์ PDF/เอกสารของผู้จัด

## โครงสร้าง

| โฟลเดอร์/ไฟล์ | ใช้ทำอะไร |
|---|---|
| `docs/CHECKLIST.md` | ของที่ต้องเตรียม · สิ่งที่ Track 3 ต้องทำ · กำหนดการ · คำถามที่ยังไม่รู้คำตอบ (ระบุหน้า PDF ทุกข้อ) |
| `docs/PYTHON_CHEATSHEET.md` | Python พื้นฐาน + requests/JSON ภาษาไทย |
| `docs/OFFLINE_SETUP.md` | วิธีติดตั้งแพ็กเกจตอนไม่มีเน็ต |
| `exercises/` | แบบฝึก 5 ข้อ + เฉลย (ไม่ต้องใช้เน็ต) |
| `tools/practice_server.py` | เซิร์ฟเวอร์ฝึกบนเครื่องตัวเอง (**ไม่ใช่ API จริง**) |
| `tools/api_test.py` | ทดสอบเรียก API จริง โดยอ่าน URL และ token จาก `.env` |
| `tools/log_template.py` | บันทึกทุกคำขอ/คำตอบลง `logs/` และซ่อน token ให้ |
| `starter_agent/` | รอ starter agent จากผู้จัด (เก็บต้นฉบับ ไม่แก้) |
| `agent/` | agent ของทีม (ยังว่าง รอรู้กติกาจริง) |
| `requirements.txt` | รายชื่อแพ็กเกจ Python |

## เริ่มใช้ (Windows, PowerShell, ที่ root ของ repo)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r track3\requirements.txt
Copy-Item .env.example .env
```
- บรรทัด 1 สร้าง virtual environment ชื่อ `.venv` (git ignore ไว้แล้ว)
- บรรทัด 2 ติดตั้งแพ็กเกจ requests, pandas, openpyxl, gradio, ollama, paho-mqtt, opencv-python
- บรรทัด 3 สร้างไฟล์ `.env` จากตัวอย่าง แล้วใส่ `TGR_BASE_URL` และ `TGR_TOKEN` เมื่อได้รับจากผู้จัด

ลองกับเซิร์ฟเวอร์ฝึก:
```powershell
.\.venv\Scripts\python.exe track3\tools\practice_server.py
```
จากนั้นเปิด Terminal อีกหน้าต่าง ใส่ `TGR_BASE_URL=http://127.0.0.1:8000` และ `TGR_TOKEN=practice-token` ใน `.env` แล้วเพิ่ม ENDPOINTS ใน `api_test.py` ก่อนรัน

## กำหนดการ [Track 3.pdf น.5–6]

| วัน | เช้า | บ่าย | คะแนน |
|---|---|---|---|
| 17 พ.ย. | อบรม: เข้าใจตลาด | ช่วง 1 · ขายด้วยมือ | 20% |
| 18 พ.ย. | อบรม: สร้าง Agent | ช่วง 2 · Agent ขายแทน | 30% |
| 20 พ.ย. | ช่วง 3 · แข่งจริง | – | 50% |

## วิธีทำงานร่วมกัน
ทำตาม [CONTRIBUTING.md](../CONTRIBUTING.md): แยก branch จาก `develop` แล้วเปิด PR เข้า `develop`

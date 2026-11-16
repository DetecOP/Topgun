# AGENTS.md: กติกาสำหรับ AI (Claude Code และ Codex)

ไฟล์นี้คือกติกากลางที่ AI ทุกตัวต้องอ่านก่อนทำงานใน repo นี้ Codex อ่านไฟล์นี้อัตโนมัติ ส่วน Claude อ่านผ่าน `CLAUDE.md`

## โปรเจกต์

ทีมแข่ง TESA Top Gun Rally 2026 (#20) โจทย์ "Chumphon Robusta AIoT Platform: Toward the Next-Gen Market"
งานหลักคือ edge AI บนบอร์ด, IoT (MQTT), backend/dashboard บนเว็บ และงาน ML (vision, audio, time-series, LLM)

## โครงสร้างโฟลเดอร์

| โฟลเดอร์ | เนื้อหา |
|---|---|
| `firmware/` | โค้ดบนบอร์ด (ModusToolbox / MicroPython / ESP-IDF) |
| `ml/` | สคริปต์เทรน, export โมเดล (ONNX → TFLite int8 → Vela), notebook |
| `web/` | backend (FastAPI), MQTT bridge, dashboard, `docker-compose.yml` |
| `docs/` | บันทึกโจทย์ การออกแบบ และผลการทดลอง |
| `scripts/` | สคริปต์ช่วยงาน |

สร้างโฟลเดอร์เมื่อเริ่มใช้จริงเท่านั้น

## กฎที่ AI ต้องทำตาม

1. **ทำงานตาม `PLAN.md`** แก้เฉพาะไฟล์ที่ระบุในข้อนั้น ติ๊ก `[x]` เมื่อผ่านขั้น verify แล้วเท่านั้น
2. **ห้าม commit** dataset, model weights (`*.pt`, `*.onnx`, `*.tflite`, `*.h5`, ...), ไฟล์ `.env` หรือข้อมูลลับ เก็บไว้บนเครื่องเทรนแทน
3. **ห้ามแก้ไฟล์เดียวกับ AI อีกตัวพร้อมกัน** ถ้าต้องทำขนานกันให้แยก branch หรือ `git worktree`
4. ทำงานบน branch `feature/*` หรือ `fix/*` แยกจาก `develop` ห้าม commit ตรงเข้า `main` หรือ `develop` และห้าม force-push
5. ข้อความ commit ใช้ Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:` ...) ดู [CONTRIBUTING.md](CONTRIBUTING.md)
6. ค่า config ใหม่ให้เพิ่มลง `.env.example` พร้อมค่าตัวอย่าง
7. Python: ใช้ virtualenv (`.venv/`) และระบุ dependency ใน `requirements.txt` ของแต่ละโฟลเดอร์
8. ถ้าไม่แน่ใจหรือ verify ไม่ผ่าน ให้หยุดและเขียนเหตุผลไว้ใต้ข้อนั้นใน `PLAN.md` อย่าเดา

## รูปแบบ PLAN.md

```
- [ ] งาน | ไฟล์ที่แก้ | วิธีเช็กว่าเสร็จ
```

ตัวอย่าง:

```
- [ ] FastAPI รับข้อมูลเซนเซอร์ | web/app/main.py | `curl -X POST localhost:8000/telemetry` ได้ 200
```

## โหมดการทำงานของ AI สองตัว

ดู `scripts/ai.sh` (ทุก OS ผ่าน Git Bash/Linux) หรือ skill `/codex` ใน Claude Code

| โหมด | คนคิด | คนทำ |
|---|---|---|
| `cc` | Claude | Codex |
| `xc` | Codex | Claude |
| `claude` / `codex` | ตัวเดียวทำทั้งหมด | |

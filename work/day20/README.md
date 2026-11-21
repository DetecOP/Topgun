# วันที่ 20 พ.ย. 2026 · ด่าน 3 แข่งจริง · ทีม ModEngi (T13) · สารบัญ

**ทุกอย่างของวันแข่งอยู่ในโฟลเดอร์นี้** · รัน agent จาก `agent/` · ไม่ใช้ `work/day18/` แล้ว (เก็บเป็นประวัติด่าน 2)

| โฟลเดอร์/ไฟล์ | คืออะไร | ใช้ตอนไหน |
|---|---|---|
| **`DAY3.md`** | แผนวันแข่ง · คำสั่งรัน · เช็กลิสต์ · ตารางตัดสินใจระหว่างแข่ง · ลำดับงาน | **อ่านก่อน** |
| **`agent/`** | โค้ดแข่ง (รุ่น `market3`) · `logs/` ใหม่ (มีแค่ `learned.json`) · `.env.competition` (ไม่ commit) | รันแข่ง · `pack.py` ส่งกรรมการ |
| `agent/RUN.md` | ค่าตั้งทุกตัว + ผลทดสอบ | เปลี่ยนค่าระหว่างแข่ง |
| `design/` | สเปกจาก Session B (ผู้ออกแบบ): `raceday_protocol.md` (ขั้นตอนวันแข่ง) · `pr_plan.md` · `llm_plan.md` · `llm_behavior_test.md` · `llm_trend_plan.md` | วันแข่ง: `raceday_protocol.md` |
| `data/stage2_competition/` | log ตลาดแข่งด่าน 2 จริง (ใช้ replay) | ทดสอบ |
| `data/sandbox_rules.json` | กติกาตลาดฝึก (ใช้คิด TV) | ทดสอบประเมินมูลค่า |
| `data/sandbox_*` | log ตลาดฝึก (ใหญ่ · ไม่ commit) | ทดสอบประเมินมูลค่า |
| `tools/round_digest.py` | **วันแข่ง:** สรุปผลรอบจาก log ให้ B (อ่านอย่างเดียว) · `--round R5` · `--trend` | ทุกรอบ |
| `tools/` | สคริปต์ทดสอบ: `replay*.py` (ข้อมูลด่าน 2) · `ab.py` / `tune.py` (ตลาดจำลอง) · `build_prior.py` / `appraisal_eval.py` (ประเมินมูลค่า) · `check.py` `pooled.py` `unsold_breakdown.py` ฯลฯ | ทดสอบก่อนแข่ง |
| `llm_eval/` | ทดสอบ LLM ผู้จัด: prompt v1–v3 · ผล · ชุดแนวโน้มราคา · K0 | อ้างอิง |
| `results/` | ผลทดสอบ: `NIGHT_LOG.md` (บันทึกกลางคืน + บทเรียน) · `RESULTS_1500.md` · ผล A/B · ไฟล์สำรอง (`backups/` ไม่ commit) | อ้างอิง |

## คำสั่ง (PowerShell · ในโฟลเดอร์ `work/day20/agent`)
```powershell
$env:PYTHONIOENCODING="utf-8"; $env:AGENT_ENV=".env.competition"; $env:USE_LLM="0"; $env:LLM_LABEL="shadow"
& "C:\Users\guttj\Documents\TGR2026\starter\Coffee-TESA-starter\.venv\Scripts\python.exe" main.py
```
ทดสอบก่อนแข่ง: `python test_agent.py` (72 ข้อ) · `python llm_ping.py` · `python pack.py` (ไม่ใส่ --send)
สคริปต์ใน `tools/` และ `llm_eval/` รันจากโฟลเดอร์ `agent/` เช่น `python ../tools/replay_probe.py`

## ชุดแข่ง (ตรึงแล้ว)
market3 = ราคาจากตลาดแข่งจริง (ค่ากลาง − 1.5 × ความผันผวน) · R1–R2 ขายออกแน่ · capacity เต็ม · กระจายผู้ซื้อ ≤ 60% · ตรวจสเปกล็อตชิดขอบในรอบซ้อม · ประเมินมูลค่า hybrid 0.2 · ตัวช่วยกฎ `rule_advisor` (พิมพ์อย่างเดียว) · LLM ผู้จัด `LLM_LABEL=shadow` · ทดสอบ 72/72 · replay ด่าน 2 PR 0.966 (ถ้าล็อตชิดขอบผ่านสเปก 0.975)

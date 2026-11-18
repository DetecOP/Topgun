# Agent ModEngi — วิธีรัน (โค้ดรุ่น market1 · 18 พ.ย. หลังแข่งด่าน 2)
ตลาดแข่ง: 9 รอบ = รอบซ้อม 1 (ไม่นับคะแนน · ไม่เสียของ · ทดสอบการส่ง) + รอบจริง 8

โฟลเดอร์หลักที่ใช้แข่ง · ไม่มี key ในโฟลเดอร์นี้ (main.py อ่าน `.env` ของโฟลเดอร์นี้ก่อน ไม่มีจะอ่าน `.env` ของ starter)
ความรู้และผลทดลองทั้งหมด: `../KNOWLEDGE.md` · แผน: `../PIPELINE.md` ข้อ 4.13

## ไฟล์
| ไฟล์ | หน้าที่ |
|---|---|
| `main.py` | ลูปหลัก · ประเมินครั้งเดียว · ส่งซองทุกรอบ · LLM (ถ้าเปิด) · ตลาดฝึก: กดข้ามช่วง/เริ่มเกมใหม่เอง · log |
| `strategy.py` | ตัดสินใจทุกรอบ: งบกระสอบ → **Specialty ก่อน** → คู่อื่นตามคะแนน → เติมให้ถึงงบ → บันไดราคา → guard |
| `market_model.py` | เรียนเพดาน/จุดตัดเป็นช่วงต่อผู้ซื้อ · ค่าเริ่มรายผู้ซื้อ (รวม Specialty 2 ราย) · SPEC_MISMATCH ห้ามส่งตามความเข้มสเปก |
| `inventory.py` | โอกาสผ่านสเปก (ระยะเผื่อจากความคลาดจริง) · ล็อตชิดขอบเกรด · จัดกลุ่มล็อต |
| `playbook.py` | ช่วงเกม · สถานการณ์ตลาด · ปฏิทิน · พื้นราคา · แรงกดดันกระสอบ |
| `advisor.py` · `llm.py` | LLM (ปิดไว้จนได้ gateway) |
| `appraisal.py` · `appraisal_prior.json` | ประเมินมูลค่า · ค่าจริงที่เคยเจอ + ขนาด noise (จาก reveal 246 เกม) |
| `analyze_logs.py` | สรุปผล/เทียบชุดทดลองจาก log ทุกไฟล์ |
| `experiments.py` | รันหลายชุดในตลาดฝึกแบบเร่ง |
| `llm_ping.py` | ทดสอบ LLM gateway 1 ครั้ง (ไม่แตะตลาด) |
| `test_agent.py` · `mock_market.py` | ทดสอบออฟไลน์ (35 ข้อ) |
| `ดูตลาด.ipynb` | ดูตลาดแบบอ่านอย่างเดียว |
| `PROMPTS.md` | prompt LLM แต่ละรอบ (ร่าง v2) · `คู่มือ-API.md` = คู่มือผู้จัด |

ย้ายออกแล้ว (`../archive/`): evaluate.py (ซ้ำกับ analyze_logs) · strategy_starter.py · README ของ starter · compete.py · sweep.py

## คำสั่ง (Terminal ของ VS Code ในโฟลเดอร์นี้)
```
$env:PYTHONIOENCODING="utf-8"
& "C:\Users\guttj\Documents\TGR2026\starter\Coffee-TESA-starter\.venv\Scripts\python.exe" test_agent.py     # ทดสอบออฟไลน์
& "C:\Users\guttj\Documents\TGR2026\starter\Coffee-TESA-starter\.venv\Scripts\python.exe" main.py --forever  # ตลาดฝึก
& "C:\Users\guttj\Documents\TGR2026\starter\Coffee-TESA-starter\.venv\Scripts\python.exe" analyze_logs.py    # สรุป/เทียบชุด
& "C:\Users\guttj\Documents\TGR2026\starter\Coffee-TESA-starter\.venv\Scripts\python.exe" experiments.py --only baseline no-reserve --games 40
```

## ค่าที่ปรับได้ (.env หรือ `$env:ชื่อ="ค่า"` ก่อนรัน · ไม่ใส่ = ค่าเริ่ม)
| ค่า | ค่าเริ่ม | ทำอะไร |
|---|---|---|
| `DELTA_DEFECT` · `DELTA_MOISTURE` · `DELTA_SCREEN` | 1.0 · 0.75 · 1 | ระยะเผื่อความคลาดของตัวอย่าง (≈ 2 SD ที่วัดได้) |
| `SPEC_P_MIN` | 0.6 | ส่งเมื่อโอกาสผ่านสเปกจริง ≥ ค่านี้ |
| `MARKET_PRICE` | 1 | **ราคาจากผลตลาดจริง** (market_summary รอบก่อน รวมรอบซ้อมของตลาดเดียวกัน) · 0 = แบบเดิม |
| `MKT_MODE` | vol | **vol** = ค่ากลางราคาตัด − 1.5 × ความผันผวน (ผู้ซื้อราคานิ่งเว้นน้อย ขาลงเว้นมาก) · replay ตลาดแข่ง PR 0.964 · `safe` = ต่ำสุด 2 รอบ − MKT_MARGIN (0.946) |
| `MKT_K` | 1.5 | ตัวคูณความผันผวน (ทดสอบ 1.0 / 1.5 / 2.0) |
| `MKT_MARGIN` | 0.02 | ตั้งต่ำกว่าราคาตลาด (ต่ำสุดของ 2 รอบล่าสุด) เท่านี้ · backtest ด่าน 2 ชนะแน่ 85% |
| `MKT_TIGHT` | 0 | 0 = ราคาชัวร์ทุกรอบ · 0.6 = ตั้งใกล้ราคาตลาดตอน capacity เหลือ (ทดสอบแล้วแย่กว่า) |
| `MKT_TREND` | 0 | 1 = ราคาลง 2 รอบติด → ตั้งตามราคาที่คาดรอบหน้า (ทดสอบแล้วไม่ดีกว่า) |
| `MKT_SHORTAGE` | 0 | 1 = ผู้ซื้อซื้อไม่ครบ (<90%) → ตั้งใกล้ราคาสูงสุดที่รับ ไม่เกินเพดานจากตลาดฝึก (ทดสอบแล้วไม่ดีกว่า) |
| `MARKET_FLOOR` | 0.82 | พื้นราคาเมื่อมีราคาตลาด (ไม่ต่ำกว่า 0.81 · ของค้างได้ 0.80) |
| `FULL_CAPACITY` | 1 | ใช้ capacity เต็มทุกรอบ ไม่กั๊กของ · 0 = แบ่งตามรอบแบบเดิม |
| `SPEC_MAX_SHARE` | 0.4 | Specialty ได้ไม่เกินสัดส่วนนี้ของงบ (เมื่อยังไม่มีราคาตลาด) · 1 = ไม่จำกัด |
| `NO_EXPLORE` | 1 | 1 = ไม่ส่งซองหยั่งราคาสูง · 0 = เปิด |
| `SELL_SHIFT_<TYPE>` | 0 | เลื่อนราคาประเภทนั้น (เช่น −0.03) · ใช้กลางแข่งด่าน 2 |
| `RESERVE_SPECIALTY` | 0 | 1 = ช่วงต้น/กลางไม่ขายล็อตเกรด Specialty ให้ประเภทอื่น · 0 = ปิด (ค่าเริ่ม: ตลาดแข่ง Specialty ไม่ได้จ่ายแพงกว่า) |
| `PRACTICE_PROBE` | 1 | รอบซ้อม (ไม่นับคะแนน): หยั่งราคา RFQ ละ 1 กระสอบหลายราคา · 0 = เล่นเหมือนรอบปกติ |
| `PACE_MODE` | sellrate | `midpush` = ต้นเกมขายแบบเดิม · กลางเกม (R3–R5) ใช้ capacity เต็ม · ท้ายเกมตาม pace3 (ทดลอง) |
| `PACE_BY_SELLRATE` | 1 | 1 = งบกระสอบ ÷ อัตราขายได้จริง + ใช้ capacity เต็มเมื่อของเสี่ยงขายไม่ทัน (pace3) · 0 = แบบเดิม |
| `APPRAISAL_MODE` | hybrid | วิธีประเมินมูลค่า: `hybrid` = ปรับตาม noise จริงแต่ไม่ข้ามหน้าผาเกรด (14.90/20 จากเฉลย 246 เกม) · `sample` = ค่าตัวอย่างตรงๆ (14.75) · `bayes` = ปรับเต็มที่ (15.08 แต่เสี่ยงกว่า) |
| `USE_LLM` | (จาก .env) | 1 = ใช้ LLM (ต้องมี LLM_BASE_URL) |
| `SANDBOX_FAST` | 1 | ตลาดฝึก: กดข้ามช่วง + เริ่มเกมใหม่เอง · 0 = เล่นตามเวลาจริง |
| `MAX_GAMES` | 0 | ตลาดฝึก: หยุดเมื่อครบ N เกม |
| `FREEZE_LEARNED` | 0 | 1 = ไม่อัปเดต logs/learned.json (ใช้ตอนเทียบชุด) |
| `AGENT_TAG` | baseline | ชื่อชุดใน log |
| `LOG_PER_RUN` | 1 | ตลาดฝึก: log ไฟล์ใหม่ทุกรัน (logs/runs/) |

## log
- ตลาดฝึก: `logs/runs/decisions-<วันเวลา>-<ชุด>.jsonl` (ไฟล์ใหม่ทุกรัน) · ตลาดแข่ง: `logs/decisions.jsonl` ไฟล์เดียว
- `memory-*.json` และ `learned.json` อยู่ที่ `logs/` เสมอ
- `logs_ab/` = ข้อมูลทดลองของทีม (ไม่ได้ใช้ในโค้ด)

## ตลาดแข่ง
1. Ctrl+C ทุกอย่างที่รันตลาดฝึก · เปิด Terminal ใหม่ (ล้างค่า `$env:` ที่ตั้งไว้)
2. ย้าย `logs/` และ `logs_ab/` ออกไปไว้นอกโฟลเดอร์นี้ · สร้าง `logs/` ใหม่แล้วคัดลอก `learned.json` กลับ
3. แก้ `MARKET_URL` / `TEAM_KEY` ใน `.env` ของ starter เป็นของตลาดแข่ง
4. `python main.py` (ไม่ใส่ `--forever`) ตัวเดียว · หน้าเว็บ/ดูตลาด.ipynb ดูอย่างเดียว
5. ห้ามส่ง/แก้/ยกเลิกซอง หรือส่งประเมินด้วยมือ (ตัดสิทธิ์)

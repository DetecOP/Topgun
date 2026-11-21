# สเปก `tools/round_digest.py` · สรุปผลรอบให้ B (Session B · 19 พ.ย. 2026)

**ปัญหา:** ทุกรอบ A ต้องก๊อป `round_results` (~3 KB JSON) + `rule_advice` + ของเหลือ/capacity มาวางเอง · ช้าและตกหล่นได้ในรอบละ 6 นาที
**ทางแก้:** สคริปต์อ่าน log อย่างเดียว · พิมพ์สรุป ≤ 25 บรรทัด ตามลำดับที่ B ตรวจ (`raceday_protocol.md` หัวข้อ "สิ่งที่ B ตรวจทุกรอบ") · A ก๊อปทั้งก้อนส่ง B

## กติกาความปลอดภัย (ต้องผ่านทุกข้อ)
- **อ่านไฟล์อย่างเดียว** · ไม่ import `market.py` / `httpx` / `llm*.py` · ไม่เรียกเครือข่าย · ไม่อ่าน `.env*`
- วางที่ `work/day20/tools/round_digest.py` (นอก `agent/` → ไม่เข้า handin.zip · ไม่กระทบ agent)
- log กำลังถูกเขียนต่อท้ายระหว่างอ่าน → บรรทัดสุดท้ายที่ JSON ไม่ครบ = ข้ามเงียบๆ
- ใช้ได้ด้วย `python` ธรรมดา (ไม่ต้องติดตั้งอะไรเพิ่ม)

## วิธีเรียก (จากโฟลเดอร์ `work/day20/agent`)
```powershell
$env:PYTHONIOENCODING="utf-8"; python ../tools/round_digest.py            # รอบล่าสุดที่มี round_results
python ../tools/round_digest.py --round R5                                 # รอบที่ระบุ
python ../tools/round_digest.py --trend                                    # ตารางทุกรอบ (ใช้ตัดสิน "ซ้ำ ≥ 2 รอบ")
python ../tools/round_digest.py --log ../data/stage2_competition/decisions.jsonl --round R3   # ทดสอบกับด่าน 2
```
ค่าเริ่ม `--log logs/decisions.jsonl` · ถ้า log มีหลาย `new_game` ใช้เกมล่าสุด

## ข้อมูลที่ใช้ (event ใน log · รูปแบบดูจาก `data/stage2_competition/decisions.jsonl`)
| event | ใช้ field |
|---|---|
| `new_game` | `tv` (TV ต่อกระสอบรายล็อต) · `samples` · `calendar` · `timeline.rounds` |
| `round_open` | `round` (round_id, kind, number, of, calendar) · `capacity_left_kg` · `round_capacity_kg` · `lots_kg` · `rfqs` (buyer_type, kg, spec) |
| `offers_sent` | `meta.probe` · `notes[].plan[]` (`src` ที่มีคำว่า probe = ซองตรวจ · `type` · `ratio`) · `seconds` |
| `round_results` | `data.my_offers[]` (lot_id, rfq_id, kg, price_per_kg, status, filled_kg) · `data.market_summary[]` (rfq_id, buyer_type, wanted_kg, bought_kg, offers, price_max) |
| `rule_advice` | `labels` · `reasons` · `recs` (ไม่มีในด่าน 2 → แสดง "ไม่มี") |
| `llm_label` | `labels[*].llm/final/guard` |
| ทุก event ที่ชื่อลงท้าย `_error` / `crashed` / `rejected` | นับ + แสดงชื่อ 3 อันแรก ตั้งแต่ round_results รอบก่อน |

## ผลลัพธ์ (ลำดับตายตัว · ตัวเลขทศนิยม 3 ตำแหน่งสำหรับอัตราส่วน)
```
== R5 (จริง 5/15 · ปฏิทิน: ปกติ) · ถัดไป R6: เทศกาลกาแฟ ==
[1 ตรวจสเปก] LOT-3→COMMERCIAL: ผ่าน (ACCEPTED) · LOT-2→SPECIALTY: ไม่ผ่าน (SPEC_MISMATCH) · LOT-4→COMMERCIAL: ไม่ชัด (ABOVE_LIMIT)
[2 ขาย] ส่ง 5 ซอง 300 kg · ขาย 240 kg (80%) · ACCEPTED 4 · OUTBID 1 · ABOVE_LIMIT 0 · SPEC_MISMATCH 0
    COMMERCIAL: ขาย 3/3 · เรา ×1.012–1.020 · ตัด ×1.031
    INSTANT   : ขาย 1/2 · OUTBID ×0.905 (ตัด ×0.898 · ห่าง +0.007)
[3 ของ] เหลือ 600 kg · capacity เหลือ 10 รอบ × 300 = 3000 kg · ตึง 0.20 (flood ถ้า > 1.0)
[4 shortage] RFQ ที่ซื้อไม่ครบ: P? COMMERCIAL 420/660 · เราขายครบใบนั้น: ใช่
[5 เทศกาล] Specialty: 2 ใบ รวม 660 kg · ตัด ×1.18 · Commercial ตัด ×1.03   (พิมพ์เมื่อรอบปัจจุบันคือ R3–R8)
[6 ผิดปกติ] error 0 · ส่งซองใช้ 0.6 วิ · ซองครบ capacity: ใช่
[ตัวช่วยกฎ] COMMERCIAL=normal · INSTANT=undercut (เหตุผล…) · LLM: COMM=normal INST=undercut guard=–
```

### นิยาม (ต้องตรงตามนี้)
- **อัตราส่วนของเรา** = `price_per_kg ÷ new_game.tv[lot]` (TV เป็นบาท/kg: ด่าน 2 P1 ล็อต 1 TV 125.46 · ซอง 143.02 = ×1.14 ตรงกับ `ratio` ใน plan)
- **ราคาตัดต่อใบ (×)** = `price_max ÷ TV สูงสุดในล็อตของเราที่ค่าตัวอย่างผ่านสเปกใบนั้น` (ทุกทีมได้ล็อตชุดเดียวกัน) · ไม่มีล็อตผ่าน → แสดง `–` · ต้องใช้ฟังก์ชันเดิมใน agent ถ้ามี (ห้ามเขียนสูตรใหม่ให้ต่างจากที่ agent ใช้ตั้งราคา) · ถ้าต้อง import ฟังก์ชันจาก agent ให้ import เฉพาะโมดูลที่ไม่เรียกเครือข่าย
- **ตามประเภทผู้ซื้อ**: ราคาตัด = ค่าต่ำสุดของใบประเภทนั้นที่ `bought_kg ≥ wanted_kg` (ใบที่ซื้อไม่ครบ = ไม่มีราคาตัด แสดงแยกใน [4])
- **ผลตรวจสเปก**: เฉพาะซองตรวจ (`src` มีคำว่า probe หรือ P1–P2) · ACCEPTED/PARTIAL/OUTBID = ผ่าน · SPEC_MISMATCH = ไม่ผ่าน · ABOVE_LIMIT = ไม่ชัด · ไม่มีซองตรวจ = ไม่พิมพ์บรรทัด [1]
- **ตึง** = ของเหลือ kg ÷ (รอบจริงที่เหลือ × `round_capacity_kg`) · รอบซ้อมไม่นับ
- **ซองครบ capacity**: kg ที่ส่งรอบนี้ ≥ min(`capacity_left_kg`, ของเหลือ) − 60
- ปฏิทินรอบถัดไปจาก `new_game.calendar` (ถ้าอ่านไม่ได้ พิมพ์ "ปฏิทิน: อ่านไม่ได้")

### `--trend` (1 บรรทัดต่อรอบ)
```
รอบ  ขาย%  COMM ตัด/เรา   INST ตัด/เรา   SPEC ตัด/เรา   ของเหลือ  ป้าย(C/I/S)
P1   20%   1.031/1.040   0.898/0.905   –/1.140        1500      –
R1   100%  1.035/1.020   ...
```

## ทดสอบที่ A ต้องรันก่อนใช้ (คืนนี้)
1. รันกับ log ด่าน 2 ทุกรอบ P1, R1–R8 + `--trend` → ไม่ล้ม · แต่ละรอบ ≤ 25 บรรทัด · ใช้เวลา < 2 วิ
2. **ตัวเลขตรง:** สุ่ม 2 รอบ เทียบ "ขาย kg" และ "ราคาตัด COMMERCIAL" กับสคริปต์เดิม (`replay.py` / `unsold_breakdown.py`) ต้องเท่ากัน · ไม่เท่า = สูตรผิด ห้ามใช้
3. log ไม่มี `rule_advice` / `llm_label` (ด่าน 2) → แสดง "ไม่มี" ไม่ล้ม
4. ใส่บรรทัดตัดครึ่งท้ายไฟล์ (สำเนาใน scratchpad) → ข้ามได้ ไม่ล้ม
5. hash ของ log ก่อน/หลังรันเท่ากัน (อ่านอย่างเดียว)
6. `python test_agent.py` ยัง 72/72 · `python pack.py` ยัง 29 ไฟล์ (สคริปต์อยู่นอก agent)
7. ส่งผล `--round R3` + `--trend` ของด่าน 2 ให้ B ดูรูปแบบ 1 ครั้ง

ไม่ผ่านข้อไหน = ไม่ใช้วันแข่ง · กลับไปก๊อป `round_results` ตามเดิม (agent ไม่เกี่ยว)

## วันแข่ง
หลังบรรทัด `round_results` ขึ้น (จับคู่เสร็จ) → A รัน `round_digest.py` → ก๊อปผลทั้งก้อนส่ง B · ถ้า B ขอ → ส่ง `--trend` · ถ้าสคริปต์ล้มกลางแข่ง → ส่ง `round_results` ดิบแทน **ห้ามแก้สคริปต์นี้กลางแข่ง**

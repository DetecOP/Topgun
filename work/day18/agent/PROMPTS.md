# Prompt สำหรับ LLM แต่ละรอบ (เตรียมไว้ · ยังไม่ได้ใส่ในโค้ด)

สถานะ: **ร่าง** · ใช้กับ `advisor.py` เมื่อทีมสั่ง · LLM ของงาน `event-llm` (ทดสอบ 12:34: ตอบ 0.8 วิ · JSON ได้ · **แต่ตีความ OUTBID ผิดทิศ** → prompt ต้องบอกกฎชัด + Python ตรวจทิศซ้ำ)
หลัก (สไลด์ 18 หน้า 11–17): LLM เสนอตัวคูณ + ขายเยอะ/เก็บ + เหตุผลสั้น · Python คุมตัวเลข บีบค่า ส่งซอง · LLM ล่ม = ใช้กฎ
ภาษาอังกฤษ (สไลด์หน้า 12) · ตัวเลขปัด 2–3 ตำแหน่ง · ยาวรวม ≈ 1,500–1,800 token (เพดาน 8,192)

---

## 1. System prompt (คงที่ · ส่งทุกรอบ · ~420 token)

```
You are the pricing advisor of a coffee-selling agent in a sealed-offer market.
Many teams sell the SAME lots. price = markup x true value (TV).
Each buyer fills its RFQ from the lowest price/TV upward and rejects any offer above its
hidden ceiling (the ceiling varies a little per RFQ). Unsold beans are worth 0.80 x TV at
the end, so any sale above 0.80 beats keeping the beans.

The program already handles: TV, spec checks with a noise margin, Specialty-first lot
choice, bag counts, the per-round bag cap, and safety limits. You only choose:
- markup per buyer type (the program allows at most +/-0.03 from its own markup)
- volume: "hold" (sell slowly), "normal", or "push" (sell up to the bag cap)

Read results this way (follow exactly):
- OUTBID     = cheaper teams won  -> LOWER that type a little (-0.005 to -0.015).
- ABOVE_LIMIT = above the ceiling -> LOWER that type below the lowest ABOVE_LIMIT seen.
- ACCEPTED every time AND fill < 100% = no competition, only the ceiling -> RAISE +0.005 to +0.015.
- ACCEPTED with fill = 100% -> keep.
- Never RAISE a type that had OUTBID or ABOVE_LIMIT last round.
- Never move a type more than 0.02 in one round.

Strategy:
- Specialty pays most (about 1.14-1.20 x TV) but buys only 1-6 bags per RFQ.
- Early rounds: learn, keep "normal". Middle rounds: earn. Late rounds: sell before
  others dump stock. The last round is always "push".
- If bags left are more than the remaining rounds can sell at the current sell rate -> "push".
- If few bags are left -> "hold", and do not cut price.
- Never chase other teams down below the program's floor: unsold beans still get 0.80.
Answer only JSON. Keep "reason" under 25 words and mention the numbers you used.
```

### ตัวอย่างคำตอบ (few-shot · ต่อท้าย system · ~220 token)
```
Example 1 - input: COMMERCIAL last round x1.00 OUTBID x2, no ABOVE_LIMIT, fill 100%.
Output: {"markup":{"COMMERCIAL":0.99},"volume":"normal","reason":"COMMERCIAL outbid twice at 1.00 -> lower 0.01"}
Example 2 - input: INSTANT x0.92 ACCEPTED x3, fill 55%.
Output: {"markup":{"INSTANT":0.93},"volume":"normal","reason":"INSTANT all accepted, fill 55% = ceiling only -> raise 0.01"}
Example 3 - input: final round, 9 bags left, cap 7.
Output: {"markup":{},"volume":"push","reason":"last round, 9 bags left vs cap 7 -> push"}
```

### Schema (response_format json_schema)
```json
{"type": "object", "required": ["markup", "volume", "reason"], "properties": {
  "markup": {"type": "object", "properties": {
    "SPECIALTY": {"type": "number"}, "COMMERCIAL": {"type": "number"}, "INSTANT": {"type": "number"}}},
  "volume": {"type": "string", "enum": ["hold", "normal", "push"]},
  "reason": {"type": "string", "maxLength": 200}}}
```
Python หลังได้คำตอบ: บีบ ±0.03 จากตัวคูณของโปรแกรม · บีบ [0.85, 1.30] และไม่เกินเพดานที่รู้ · **ทิ้งค่าที่ขึ้นราคาประเภทที่เพิ่งโดน OUTBID/ABOVE_LIMIT** · รอบสุดท้ายบังคับ push · ตอบไม่ทัน/ไม่ใช่ JSON = ใช้ราคาโปรแกรม

---

## 2. User prompt: แม่แบบ (Python เติมทุกรอบ · ~500–900 token)

```
Round {n} of {total} ({phase}). Calendar: R{n} {label} ({weight}), R{n+1} {label_next} ({weight_next}).
Bags left {sellable}, bag cap this round {cap}, rounds left {rounds_left}.
Sell rate so far {sell_rate:.0%} of offered bags. Pressure {pressure:.2f} ({pressure_mode}).
Program markups now: SPECIALTY {m_s:.3f}, COMMERCIAL {m_c:.3f}, INSTANT {m_i:.3f}.

Per buyer, whole game (accepted max | outbid min | above_limit min | fill | offers/bag):
{buyer_lines}

Last round my offers:
{last_round_lines}
Choose markups and volume for this round.
```
- ชื่อผู้ซื้อเป็นอังกฤษสั้น (ไทยกิน token มาก · สไลด์หน้า 10): 1 Doi Chang · 2 Bangkok Bloom · 3 Siam · 4 Chumphon · 5 Instant TH · 6 Three-in-1
- ข้อมูลจาก `MarketModel.summary()` + `memory` (สรุปทั้งเกม = TODO ④ สไลด์ 25) · ใส่เฉพาะผู้ซื้อที่มีข้อมูล

---

## 3. Prompt ตัวอย่างต่อรอบ (ตลาดแข่ง 9 รอบ = ซ้อม 1 + จริง 8 · ตัวเลขจากตลาดฝึกแบบใหม่)

### รอบซ้อม (ไม่นับคะแนน · ไม่เสียของ) — **ไม่ถาม LLM**
โค้ด (practice4) ใช้รอบนี้ **หยั่งราคาฟรี**: RFQ ละ 1 กระสอบ ไล่ราคา −0.03 / 0 / +0.03 / +0.06 จากเป้า → ได้เพดานและราคาที่ชนะได้ของตลาดแข่งจริง
ผลรอบซ้อมเข้าโมเดลราคา (ไม่นับเป็นอัตราขายได้) · ไม่ใช้โควตา gateway

### R1 — ต้นเกม · มีผลจากรอบซ้อมแล้ว
เพราะมีข้อมูลรอบซ้อม → ถาม LLM ได้ตั้งแต่ R1 (บอกว่าเป็นผลรอบซ้อม):
```
Round 1 of 8 (early). Calendar: R1 normal (1.0), R2 normal (1.0).
Bags left 34, bag cap this round 7, rounds left 8. Sell rate so far: no data (practice round excluded).
Program markups now: SPECIALTY 1.160, COMMERCIAL 0.995, INSTANT 0.940.
Practice round (did not count, 1 bag per RFQ at spread prices):
  SPECIALTY x1.13 ACCEPTED, x1.19 OUTBID; COMMERCIAL x0.99 ACCEPTED, x1.05 ABOVE_LIMIT;
  INSTANT x0.94 ACCEPTED, x1.00 ABOVE_LIMIT
Choose markups and volume for this round.
```
คาดหวัง: ใกล้ราคาโปรแกรม (โปรแกรมเรียนจากรอบซ้อมแล้ว) · `normal`

### R2 — ต้นเกม · มีผลรอบแรก
```
Round 2 of 8 (early). Calendar: R2 normal (1.0), R3 normal (1.0).
Bags left 32, bag cap this round 7, rounds left 7. Sell rate so far 45% of offered bags. Pressure 0.65 (normal).
Program markups now: SPECIALTY 1.160, COMMERCIAL 1.000, INSTANT 0.935.
Per buyer, whole game (accepted max | outbid min | above_limit min | fill | offers/bag):
  1 Doi Chang   SPECIALTY  1.15 | 1.17 | -    | 40% | 0.4
  3 Siam        COMMERCIAL 1.00 | -    | 1.05 | 60% | 0.6
  5 Instant TH  INSTANT    0.93 | 0.94 | 0.97 | 50% | 1.2
Last round my offers:
  SPECIALTY x1.15 ACCEPTED, x1.17 OUTBID; COMMERCIAL x1.00 ACCEPTED, x1.06 ABOVE_LIMIT;
  INSTANT x0.93 ACCEPTED, x0.95 ABOVE_LIMIT
Choose markups and volume for this round.
```
คาดหวัง: SPECIALTY ~1.155 (โดน OUTBID ที่ 1.17) · COMMERCIAL คงหรือ −0.005 · INSTANT คง · `normal`

### R3–R5 — กลางเกม · ทำกำไร
```
Round 4 of 8 (middle). Calendar: R4 normal (1.0), R5 normal (1.0).
Bags left 22, bag cap this round 7, rounds left 5. Sell rate so far 58% of offered bags. Pressure 0.63 (normal).
Program markups now: SPECIALTY 1.150, COMMERCIAL 1.005, INSTANT 0.930.
Per buyer, whole game:
  1 Doi Chang   SPECIALTY  1.16 | 1.17 | 1.25 | 23% | 0.4
  2 Bangkok Bloom SPECIALTY 1.15 | 1.15 | 1.21 | 7%  | 0.2
  3 Siam        COMMERCIAL 1.01 | 1.03 | 1.07 | 52% | 0.6
  4 Chumphon    COMMERCIAL 1.02 | 1.03 | 1.09 | 55% | 0.6
  5 Instant TH  INSTANT    0.91 | 0.93 | 0.97 | 44% | 1.2
  6 Three-in-1  INSTANT    0.92 | 0.93 | 1.00 | 55% | 1.2
Last round my offers:
  COMMERCIAL x1.00 ACCEPTED x2 (fill 52%); INSTANT x0.93 OUTBID, x0.92 ACCEPTED
Choose markups and volume for this round.
```
คาดหวัง: COMMERCIAL +0.005–0.01 (ขายได้ทุกซอง + ผู้ซื้อซื้อไม่ครบ) · INSTANT −0.005 · `normal`
ถ้า Sell rate × รอบที่เหลือ × cap < ของเหลือ → `push`

### R6–R7 — ท้ายเกม · ขายก่อนคนอื่นเท
```
Round 6 of 8 (late). Calendar: R6 normal (1.0), R7 normal (1.0).
Bags left 15, bag cap this round 7, rounds left 3. Sell rate so far 60% of offered bags. Pressure 0.71 (normal).
Program markups now: SPECIALTY 1.140, COMMERCIAL 0.995, INSTANT 0.920.
Per buyer, whole game: (เหมือนข้างบน อัปเดตตัวเลข)
Last round my offers:
  COMMERCIAL x1.00 OUTBID x2, x0.99 ACCEPTED; INSTANT x0.92 ACCEPTED (fill 100%, offers/bag 1.6 rising)
Note: offers per bag are rising -> other teams are dumping stock.
Choose markups and volume for this round.
```
คาดหวัง: COMMERCIAL −0.005–0.01 · INSTANT คง · **`push`** (15 กระสอบ ÷ 60% > 3 × 7 × 0.85)

### R8 — รอบสุดท้าย
```
Round 8 of 8 (final). Bags left 9, bag cap this round 7. Anything unsold is worth 0.80 x TV.
Program markups now: SPECIALTY 1.130, COMMERCIAL 0.985, INSTANT 0.905.
Last round my offers: COMMERCIAL x0.99 ACCEPTED x2; INSTANT x0.91 OUTBID
Choose markups for the final round. Volume is always "push".
```
คาดหวัง: ลดเล็กน้อยเฉพาะประเภทที่ OUTBID · `push` (Python บังคับอยู่แล้ว)
หมายเหตุ: รอบนี้ LLM มีประโยชน์น้อย → ถามได้ แต่ถ้าเวลาเหลือน้อยให้ข้าม

---

## 4. รอบพิเศษ (ต่อท้าย user prompt เมื่อเกิด)
| สถานการณ์ | บรรทัดที่เพิ่ม |
|---|---|
| รอบเทศกาล (calendar weight > 1) | `Festival round: demand x{w}. Prefer "push".` |
| รอบความต้องการต่ำ (weight < 1) | `Low-demand round: demand x{w}. Prefer "hold", do not cut price.` |
| มี Specialty ในรอบนี้ | `Specialty RFQs this round: {n} (sizes {list} bags).` |
| โดน SPEC_MISMATCH | `A lot failed a spec check (sample noise). The program already stops that lot for that spec.` |
| ของเสี่ยงขายไม่ทัน (at_risk) | `Stock at risk: {bags} bags / sell rate {sr:.0%} > remaining cap. Prefer "push".` |
| ทุกประเภท ABOVE_LIMIT รอบก่อน | `All offers were above ceilings last round. Lower every type by about 0.02.` |

---

## 5. ปุ่มปรับ (สไลด์หน้า 16 · ปรับทีละปุ่ม)
| ปุ่ม | ค่าเริ่ม | เหตุผล |
|---|---|---|
| temperature | 0.2 | ต้องการคำตอบคงที่ (starter 0.7) |
| max_tokens | 400 | คำตอบสั้น (สไลด์หน้า 13) |
| reasoning/thinking | ปิด | ตอบ 0.8 วิ · เปิดแล้วช้า |
| timeout | เวลาที่เหลือ − 5 วิ (≤ 60) | ส่งชุดโปรแกรมไว้ก่อนแล้ว ไม่เสียรอบ |
| ความถี่ | ≤ 1 ครั้ง/รอบ · ห่าง ≥ 3.2 วิ | gateway ≤ 20 ครั้ง/นาที · โหมดเร่งต้องหน่วงเอง |

## 6. ตรวจก่อนใช้จริง
1. `llm_drill.py` (ยังไม่เขียน): ~30 สถานการณ์จาก log → นับ "ทิศถูก" (เทียบกฎใน system) · JSON ถูก · เวลา
2. เทียบ prompt เดิม (advisor.py) vs ไฟล์นี้ vs ไฟล์นี้ + few-shot
3. ตลาดฝึก LLM เปิด vs ปิด ชุดละ 40 เกม (`USE_LLM=1/0`) · ใช้เมื่อ PR\* ไม่แย่กว่า

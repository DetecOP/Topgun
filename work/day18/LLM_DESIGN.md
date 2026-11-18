# ออกแบบส่วน LLM ของ agent (รอแจก gateway)

สถานะ: **ออกแบบอย่างเดียว ยังไม่เขียนโค้ด** · รอทีมงานแจกที่อยู่ LLM gateway แล้วทีมสั่งให้ลงมือ
อ้างอิง: สไลด์วันที่ 18 หน้า 6, 10–18, 28 · starter `llm.py`, `strategy.py` (llm_plan) · แผนหลัก [PIPELINE.md](PIPELINE.md)

---

## 1. กติกาที่ตายตัว (ห้ามพลาด)
- ใช้ได้เฉพาะ gateway ของงาน · model `event-llm` · key เดียวกับตลาด (TEAM_KEY)
- ใช้ LLM อื่น (cloud หรือ Ollama บนเครื่อง) ในด่าน 2–3 = **ตัดสิทธิ์ทั้งการแข่ง**
- gateway ล่ม → agent เล่นต่อด้วยกฎของเรา **ห้ามสลับไป LLM อื่น**
- context รวม 8,192 token ต่อครั้ง · ทุกทีมใช้ GPU ร่วมกัน → prompt สั้น = ตอบทัน
- ถามรอบละครั้ง ห้ามวนถามซ้ำทันที (429 = รอแล้วส่งใหม่ ไม่ผิดกติกา)
- ขีดจำกัด gateway (จาก starter/คู่มือ-API.md): พร้อมกันได้ **2 คำขอ/ทีม** · **≤ 20 คำขอ/นาที** · `max_tokens` สูงสุด 2,000 ·
  thinking ปิดเป็นค่าเริ่มต้น (เปิดด้วย `reasoning_effort="medium"` ช้ามาก) · error: `BAD_KEY` 401, `TOO_MANY_CONCURRENT` 429, `RATE_LIMIT` 429 + `Retry-After`
  → รอบละ 1 คำขอ ใช้โควตาแค่ 1/20 ต่อนาที ปลอดภัย

## 2. ให้ LLM ทำอะไร (ขอบเขตแคบโดยตั้งใจ)

| | starter เดิม | แบบของเรา |
|---|---|---|
| LLM เลือก | ทุกซอง: candidate ไหน กี่กระสอบ ตัวคูณเท่าไร | **ปรับตัวคูณต่อประเภทผู้ซื้อ ±0.03** + **โหมดปริมาณ** รอบนี้ |
| ขนาด prompt | 2,200–2,600 token (ตาราง candidate ทั้งหมด) | ~600–900 token (ตารางสรุปต่อผู้ซื้อ) |
| ถ้า LLM พลาด | ซองผิด/ขาด กฎต้องเติม | แค่ไม่ได้ปรับ ราคาจากโมเดลยังใช้ได้ทั้งชุด |

เหตุผล: ตัวเลขทุกตัว (TV, สเปก, กระสอบ, เพดาน, จุดตัด) Python คำนวณแม่นกว่า · LLM ช่วยตรงที่ "อ่านแนวโน้มหลายรอบแล้วตัดสินใจเชิงคุณภาพ"
(เช่น "ประเภทนี้ OUTBID 2 รอบติด ตลาดเริ่มเทของ ลดอีกหน่อย" หรือ "รอบหน้าเทศกาล เก็บของไว้")

ทางเลือกสำรองไว้ทดลองเทียบ: แบบ starter (LLM เลือก candidate) → เทียบ PR ในตลาดฝึก แล้วเก็บแบบที่ดีกว่า

## 3. ร่าง prompt

### system (คงที่ ~150 token · ภาษาอังกฤษตามคำแนะนำสไลด์ 12)
```
You tune prices for a coffee seller agent in a sealed-offer market with 56 competing teams.
price = ratio x true value (TV). Buyers take the lowest price/TV first and reject offers above
their hidden ceiling. Unsold beans are worth 0.80 x TV at the end.
Signals: ABOVE_LIMIT = above that buyer's ceiling. OUTBID = other teams were cheaper.
fill < 100% with many offers = most offers were above the ceiling.
The program already computed a safe ratio per buyer type. You may move each by at most 0.03,
and choose the volume mode for this round. Answer only JSON.
```

### user (สร้างใหม่ทุกรอบ · ตัวเลขปัด 2–3 ตำแหน่ง)
```
Round 5 of 8 (calendar: normal, demand_weight 1.0). Next: R6 festival (1.4), R7 normal.
Bags left: 18 sellable, capacity this round 6 bags. Rounds left incl. this: 4.
Per buyer type (whole game so far):
  COMMERCIAL  model 0.985 | accepted max 0.98 | outbid min 1.01 | above_limit min 1.10 | fill 100%, offers/bag 2.1
  INSTANT     model 0.950 | accepted max 0.96 | above_limit min 0.98 | fill 62%, offers/bag 1.6
  SPECIALTY   model 1.150 | accepted max - | above_limit min 1.30 | fill 40%
Last round: COMMERCIAL x0.99 OUTBID, x0.98 ACCEPTED; INSTANT x0.95 ACCEPTED.
Choose adjustments.
```
ข้อมูลทั้งหมดมาจาก `market_model` (สรุปทั้งเกม ไม่ใช่แค่ 3 รอบล่าสุด ตาม TODO ในสไลด์ 25 ข้อ ④)

### schema คำตอบ
```json
{"type": "object", "required": ["adjust", "volume", "reason"], "properties": {
  "adjust": {"type": "object", "properties": {
    "SPECIALTY": {"type": "number"}, "COMMERCIAL": {"type": "number"}, "INSTANT": {"type": "number"}}},
  "volume": {"type": "string", "enum": ["hold", "normal", "push"]},
  "reason": {"type": "string", "maxLength": 200}}}
```

## 4. Python คุมผล (guard ของส่วน LLM)
| ค่าจาก LLM | Python ทำ |
|---|---|
| `adjust[type]` | บีบเป็น [−0.03, +0.03] · ratio สุดท้ายบีบอีกชั้นใน [พื้นราคา, เพดานประมาณ − 0.01] |
| ประเภทที่ไม่ตอบ | ใช้ 0 (ราคาโมเดล) |
| `volume` | hold = PACE 1.0 · normal = 1.3 · push = 1.6 → แล้วบีบด้วย capacity_left_kg เสมอ · **รอบสุดท้ายบังคับ push** |
| ตอบไม่ทัน / ไม่ใช่ JSON / ค่าแปลก (NaN, เกิน) | ทิ้งทั้งคำตอบ ใช้ราคาโมเดล + normal |
| `reason` | ตัดให้ ≤ 200 ตัวอักษร ลง log |

## 5. ค่าปุ่มปรับ (สไลด์ 16)
| ปุ่ม | starter | ของเรา | เหตุผล |
|---|---|---|---|
| temperature | 0.7 | 0.2 | ต้องการคำตอบคงที่ ตรวจย้อนได้ |
| max_tokens | 1,500 | 400 | คำตอบสั้น (schema เล็ก) · ไม่ต่ำกว่านี้กัน JSON ขาด |
| reasoning/thinking | ปิด | ปิด | ช้าและกิน token · ลองเปิดเทียบได้ในตลาดฝึกถ้ามีเวลา |
| timeout | เวลาเหลือ − 5 วิ (≤ 60) | เหมือนเดิม + ส่งราคาโมเดลไว้ก่อน | ดูข้อ 6 |

## 6. ลำดับเวลาในหนึ่งรอบ (รอบละ 4 นาที)
1. รอบเปิด → Python คำนวณราคาโมเดล → **ส่ง batch ชุดแรกทันที** (มีข้อเสนอในตลาดแน่นอนแม้ LLM ล่ม)
2. ถาม LLM (timeout ≤ 60 วิ)
3. ได้คำตอบที่ผ่าน guard และต่างจากชุดแรก → ส่ง batch ใหม่ด้วย `replace_existing: true` (แทนชุดเดิมทั้งชุด)
4. ไม่ได้คำตอบ → ชุดแรกคงอยู่ ไม่ต้องทำอะไร
(การแก้ข้อเสนอโดย agent เองถูกกติกา · ที่ห้ามคือคนแก้ด้วยมือ)

## 7. log ทุกครั้งที่ถาม (กรรมการตรวจ 5 ทีมแรก)
`llm_call {round, prompt_tokens, latency_s, ok, raw_adjust, clamped_adjust, volume, reason, used}` → `logs/decisions.jsonl`

## 8. เช็กลิสต์วันแจก gateway (ทำตามลำดับ)
1. ใส่ `LLM_BASE_URL` ใน starter `.env` · `USE_LLM=1` · key = TEAM_KEY (มีอยู่แล้ว ห้ามพิมพ์ออกจอ)
2. ถามคำถามสั้นๆ 1 ครั้ง (notebook ข้อ 2) → ต้องได้คำตอบ · จด latency
3. ทดสอบ `response_format: json_schema` ว่า gateway รองรับไหม (llm.py ของ starter รับมือ thinking switch ไว้แล้ว)
4. รัน agent กับตลาดฝึก 1 เกม: LLM ปิด (baseline) → 1 เกม: LLM เปิด → เทียบ PR + ดู log ว่าคำตอบถูกบีบบ่อยไหม
5. เกณฑ์ตัดสิน: LLM ไม่ทำให้ PR ดีขึ้นชัด หรือ timeout บ่อย → **ปิด LLM ในตลาดแข่ง** (ใช้กฎล้วนได้ ไม่ผิดกติกา)

## 9. ยังไม่ทราบ
- ที่อยู่ gateway · latency จริงตอน 56 ทีมเรียกพร้อมกัน (rate limit รู้แล้ว: 2 พร้อมกัน, 20/นาที)
- gateway รองรับ json_schema และปิด thinking แบบไหน (ทดสอบตามข้อ 8)
- calendar วันแข่งมีรอบพิเศษอะไรบ้าง (ใช้ใส่ใน user prompt)

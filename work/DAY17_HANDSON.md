# คู่มือฝึกปฏิบัติ 17 พ.ย. · Track 3 (เขียนมือได้ทุกขั้น)

> อิงจาก Track 3.pdf หน้า 4 (starter agent / LLM ผู้จัด) และหน้า 7 (เตรียม 4 อย่าง)
> ฝึกได้คืนนี้เลยด้วย **ตลาดจำลองในเครื่อง** `practice/mock_market.py` ไม่ต้องใช้เน็ต ไม่แตะ server ผู้จัด
> ⚠️ path, ชื่อช่อง JSON และ token ในตลาดจำลองแต่งขึ้นเพื่อฝึก ของจริงต้องดูจากเอกสารผู้จัด

---

## ส่วน A · กติกาจากหน้า 4 แปลว่าอะไรในทางปฏิบัติ

### A1. "ทุกทีมได้ starter agent ที่เล่นจนจบเกมได้ตั้งแต่แรก งานของคุณคือทำให้มันเก่งขึ้น"
| ความหมาย | สิ่งที่ต้องทำ |
|---|---|
| ผู้จัดให้โปรแกรมที่**เล่นได้อยู่แล้ว** ไม่ต้องเขียนใหม่ทั้งหมด | ได้มาแล้ว **คัดลอกเก็บต้นฉบับไว้ก่อน** ไปแก้ในสำเนาเสมอ |
| ส่วนที่ต้องเก่งขึ้นคือ "คิด" (เลือกล็อต ผู้ซื้อ ราคา) | หาฟังก์ชันที่ตัดสินราคาในโค้ด starter แล้วค่อยเปลี่ยนตรงนั้นทีละน้อย |
| ส่วน "ดู" กับ "ทำ" (เรียก API) ของ starter ใช้ได้แล้ว | **อย่าแก้ส่วนเรียก API** ถ้าไม่จำเป็น ส่วนนี้พังง่ายที่สุด |

**ขั้นตอนเมื่อได้ starter (ทำตามลำดับ):**
```powershell
# 1) คัดลอก starter ที่ได้ ไปไว้ใน work\starter\original (ห้ามแก้)
# 2) คัดลอกอีกชุดเป็น work\starter\ours (แก้ในนี้)
# 3) รันชุดเดิมให้ได้ก่อน 1 รอบ (ตามวิธีที่ผู้จัดบอก) → ยืนยันว่าเครื่องเราใช้ได้
# 4) หาเลขราคาในโค้ด: ค้นคำว่า price, offer, bid, markup
```
- ใน VS Code กด `Ctrl+Shift+F` แล้วพิมพ์ `price` จะเห็นทุกบรรทัดที่เกี่ยวกับราคา

### A2. "ใช้ LLM ที่ผู้จัดเตรียมให้เท่านั้น"
| ความหมาย | สิ่งที่ต้องทำ |
|---|---|
| ถ้า agent จะใช้ LLM ต้องเรียก **LLM ของผู้จัด** เท่านั้น | จด URL, ชื่อโมเดล, วิธีส่ง key ลง `notes/day1_rules.md` |
| ไม่ต้องมี GPU และไม่ต้องติดตั้ง LLM เอง (หน้า 7) | ollama ในเครื่องเราใช้ซ้อมได้ แต่ใช้แข่งไม่ได้จนกว่าผู้จัดอนุญาต |
| LLM ไม่จำเป็นต้องใช้ทุกส่วน | **ราคาให้โค้ดคำนวณ** · LLM ใช้กับงานภาษา เช่น อ่านข้อความผู้ซื้อ |

เตรียมไว้แล้ว: ตั้งค่า `simulator/config.py` → `LLM_PROVIDER = "organizer"` แล้วกรอก `ORGANIZER_LLM_BASE_URL`, `ORGANIZER_LLM_MODEL`, `ORGANIZER_LLM_API_KEY` จากนั้นรัน:
```powershell
.venv\Scripts\python.exe simulator\llm_check.py
```

**รูปแบบการเรียก LLM ที่พบบ่อย (แบบ OpenAI) เขียนมือได้แบบนี้:**
```python
import requests
r = requests.post(
    "URL_ที่ผู้จัดให้/chat/completions",              # ← ยังไม่ทราบ ดูเอกสารผู้จัด
    headers={"Authorization": "Bearer KEY_ของทีม"},    # ← ยังไม่ทราบชื่อ header จริง
    json={"model": "ชื่อโมเดล",
          "messages": [{"role": "user", "content": "สรุปความต้องการผู้ซื้อนี้: ..."}]},
    timeout=20)
print(r.json()["choices"][0]["message"]["content"])    # ข้อความที่ LLM ตอบ
```
- `messages` คือรายการบทสนทนา `role` มีได้ `system` (คำสั่งหลัก), `user` (คำถาม), `assistant` (คำตอบเก่า)
- ถ้า API ผู้จัดเป็นแบบอื่น โครงจะคล้ายกัน ต่างแค่ path และชื่อช่อง

---

## ส่วน B · โน้ตบุ๊กพร้อม Python (หน้า 7: "Python 3.10 ขึ้นไป สร้าง venv และ pip install ได้")

### B1. เช็กเวอร์ชัน
```powershell
py --version                  # ต้องได้ 3.10 ขึ้นไป (เครื่องนี้ 3.14.8)
py -m pip --version           # pip = ตัวติดตั้งแพ็กเกจ
```

### B2. venv คืออะไร ทำไมต้องมี
- **venv = กล่องแยกเก็บแพ็กเกจของงานนี้** ไม่ปนกับงานอื่นในเครื่อง ถ้าพังก็ลบกล่องสร้างใหม่ได้
- เครื่องนี้มีแล้วที่ `work\.venv`

```powershell
cd C:\Users\guttj\Documents\GitHub\team-project\.claude\worktrees\tesa-top-gun-rally-track3-11632c\work
py -m venv .venv              # สร้างกล่องชื่อ .venv (ทำครั้งเดียว)
.venv\Scripts\python.exe --version
```
- **ไม่ต้อง activate** ก็ได้ เรียก `.venv\Scripts\python.exe` ตรงๆ ทุกครั้ง (กันปัญหา Windows ไม่ให้รันสคริปต์)
- ถ้าอยาก activate: `.venv\Scripts\Activate.ps1` → ถ้าขึ้น "running scripts is disabled" ไม่ต้องแก้ ใช้วิธีเรียกตรงแทน (อย่าเปลี่ยนการตั้งค่าความปลอดภัยของ Windows)

### B3. pip install
```powershell
.venv\Scripts\python.exe -m pip install requests                       # มีเน็ต
.venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse requests   # ไม่มีเน็ต
.venv\Scripts\python.exe -m pip list                                     # ดูว่ามีอะไรบ้าง
```
- ถ้าผู้จัดแจก `requirements.txt` มากับ starter: `.venv\Scripts\python.exe -m pip install -r requirements.txt`
- เช็กเครื่องรวดเดียว: `.venv\Scripts\python.exe check_env.py`

---

## ส่วน C · VS Code ที่รัน Python ได้

| ทำอะไร | วิธี |
|---|---|
| เปิดโฟลเดอร์งาน | terminal: `code .` ในโฟลเดอร์ work |
| เลือก Python ของ .venv | `Ctrl+Shift+P` → `Python: Select Interpreter` → เลือกตัวที่มี `.venv` (ตั้งไว้ให้แล้ว) |
| รันไฟล์ที่เปิดอยู่ | ปุ่ม ▶ มุมขวาบน หรือ `Ctrl+F5` |
| เปิด terminal ใน VS Code | `` Ctrl+` `` |
| รัน task ที่ตั้งไว้ | `Ctrl+Shift+P` → `Run Task` → "เช็กเครื่อง" / "ทดสอบ API" |
| ค้นทั้งโฟลเดอร์ | `Ctrl+Shift+F` |
| หยุดดูค่าตัวแปรกลางทาง (debug) | คลิกซ้ายของเลขบรรทัดให้มีจุดแดง → `F5` → โปรแกรมหยุดที่บรรทัดนั้น ดูค่าตัวแปรทางซ้าย → `F10` ไปบรรทัดถัดไป |
| หยุดโปรแกรมที่ค้าง | คลิกใน terminal แล้วกด `Ctrl+C` |
| บันทึกไฟล์ | `Ctrl+S` (ตั้งให้บันทึกเองเมื่อสลับหน้าต่างแล้ว) |

---

## ส่วน D · REST API + JSON (หน้า 7: "ส่ง GET/POST ด้วย Python และอ่าน JSON ได้")

### D1. คำศัพท์ 6 คำที่ต้องรู้
| คำ | ความหมาย | ตัวอย่างในตลาดจำลอง |
|---|---|---|
| **URL / BASE_URL** | ที่อยู่ server | `http://127.0.0.1:8000` |
| **endpoint / path** | ส่วนท้ายที่บอกว่าจะทำอะไร | `/market`, `/offers` |
| **GET** | ขอดูข้อมูล (ไม่เปลี่ยนอะไร) | ดูล็อตและผู้ซื้อ |
| **POST** | ส่งข้อมูลไปให้ server ทำ | ส่งข้อเสนอขาย |
| **header** | ข้อมูลแนบ เช่น token ยืนยันตัวตน | `Authorization: Bearer practice-token` |
| **status code** | ผลลัพธ์เป็นตัวเลข | 200 สำเร็จ · 400 ส่งผิด · 401 token ผิด · 404 path ผิด · 429 ถี่เกิน · 5xx server พัง |

### D2. JSON กับ Python คือของเดียวกัน
| JSON | Python |
|---|---|
| `{"id": "A", "weight": 120}` | dict `{"id": "A", "weight": 120}` |
| `[1, 2, 3]` | list `[1, 2, 3]` |
| `true` / `false` / `null` | `True` / `False` / `None` |
- `r.json()` แปลงคำตอบ JSON → dict/list · `requests.post(..., json=ข้อมูล)` แปลง dict → JSON ให้เอง

### D3. ฝึกจริง 3 ขั้น (เปิด 2 หน้าต่าง terminal)
**หน้าต่างที่ 1** เปิดตลาดจำลองทิ้งไว้:
```powershell
.venv\Scripts\python.exe practice\mock_market.py
```
**หน้าต่างที่ 2** รันทีละขั้น อ่านโค้ดคู่กัน (มีคอมเมนต์ไทยทุกบรรทัดสำคัญ):

| ขั้น | ไฟล์ | ได้ฝึก | ผลที่ควรเห็น |
|---|---|---|---|
| 1 | `practice\step1_get.py` | GET, ใส่ token, อ่าน dict/list, เจอ None | 200 → 401 (ไม่ใส่ token) → 200 + รายการล็อตและผู้ซื้อ |
| 2 | `practice\step2_post.py` | POST JSON, จัดการ error 400/401/429, ต่อไม่ได้ | ❌ 400 (ส่งราคาเป็นข้อความ) → ✅ ส่งสำเร็จ ขายได้/ไม่ได้ |
| 3 | `practice\step3_agent_loop.py` | **agent เต็มวง** ดู→คิด→ทำ จนจบเกม, ลดราคาเมื่อขายไม่ออก, log, รอเมื่อโดน 429 | ขายได้ทีละล็อต ล็อตที่ชื้นเกินไม่มีใครรับ |

```powershell
.venv\Scripts\python.exe practice\step1_get.py
.venv\Scripts\python.exe practice\step2_post.py
.venv\Scripts\python.exe practice\step3_agent_loop.py
```
- ถ้าขึ้น 429: เรียกถี่เกิน 5 ครั้ง/วินาที → รอ 1–2 วินาทีแล้วรันใหม่ (นี่คือสิ่งที่ API จริงอาจทำ)
- ถ้าขึ้น "ต่อ server ไม่ได้": ลืมเปิดหน้าต่างที่ 1

### D4. แม่แบบเขียนมือ (จำ 4 บรรทัดนี้ = ทำได้ 80%)
```python
import requests
H = {"Authorization": "Bearer TOKEN"}                                       # 1) header + token
r = requests.get("BASE_URL/path", headers=H, timeout=10)                    # 2) GET
r = requests.post("BASE_URL/path", json={"key": "value"}, headers=H, timeout=10)   # 3) POST
if r.status_code == 200: data = r.json()                                     # 4) เช็ก status ก่อนอ่าน JSON เสมอ
```

### D5. โจทย์ฝึกต่อ (ทำเองในตลาดจำลอง)
1. แก้ step1 ให้พิมพ์เฉพาะล็อตที่**มีผลวัดแล้ว**
2. แก้ step3 ให้เลือกผู้ซื้อ **B1 ก่อน** ถ้าล็อตผ่านเงื่อนไข (B1 ยอมจ่ายสูงสุดในตลาดจำลอง) แล้วดูว่าขายได้มากขึ้นไหม
3. เพิ่ม GET `/results` ตอนจบเกม แล้วนับว่าขายได้ราคาเฉลี่ยเท่าไร
4. ลอง `STEP_DOWN = 0.02` กับ `0.08` แล้วเทียบจำนวนที่ขายได้

---

## ส่วน E · เช็กลิสต์ก่อนส่งของจริง (ช่วง 2–3 agent ต้องส่งเอง)
- [ ] รัน starter ต้นฉบับได้ 1 รอบ
- [ ] `DRY_RUN = True` ก่อนเสมอ ดูว่าข้อเสนอที่จะส่งสมเหตุสมผล (ราคาไม่ติดลบ ไม่ใช่ 0 ไม่ใช่ล้าน)
- [ ] มีเพดานจำนวนข้อเสนอต่อรอบ และ `time.sleep` กันโดน rate limit
- [ ] มี `try/except` + `timeout` ทุกครั้งที่เรียก API → agent ไม่ตายกลางเกม
- [ ] log ทุกคำขอ/คำตอบ (`log_template.py`) → พังแล้วย้อนดูได้
- [ ] token ไม่อยู่ในไฟล์ที่ commit

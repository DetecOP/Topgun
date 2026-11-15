# Python Cheatsheet สำหรับ Track 3 (ฉบับเริ่มจากศูนย์)

เนื้อหาตรงกับที่ PDF ขอให้เตรียมไว้: "ส่ง GET/POST ด้วย Python และอ่าน JSON ได้" [Track 3.pdf น.7]

## 0. วิธีรันโค้ด

1. เปิด VS Code แล้วไปที่ **File → Open Folder** เลือก `track3` ใน repo
2. สร้างไฟล์ เช่น `test.py` แล้ววางโค้ด
3. กด ▶ ที่มุมขวาบน หรือพิมพ์คำสั่งนี้ใน Terminal:

```powershell
.\.venv\Scripts\python.exe test.py
```
- `.\.venv\Scripts\python.exe` คือ Python ที่อยู่ใน .venv ซึ่งติดตั้งแพ็กเกจไว้ครบแล้ว
- `test.py` คือชื่อไฟล์ที่ต้องการรัน

> เครื่องหมาย `#` คือคอมเมนต์ Python จะไม่อ่านข้อความหลัง `#`

---

## 1. ตัวแปร (variable)

```python
team = "ทีมกาแฟ"
price = 85.5
lots = 3
print(team, price * lots)
```
| บรรทัด | ความหมาย |
|---|---|
| 1 | เก็บข้อความ (string) ไว้ในชื่อ `team` ข้อความต้องอยู่ใน `"..."` |
| 2 | เก็บเลขทศนิยม (float) ไว้ใน `price` |
| 3 | เก็บเลขจำนวนเต็ม (int) ไว้ใน `lots` |
| 4 | `print` แสดงผลออกจอ ได้ `ทีมกาแฟ 256.5` |

แปลงชนิดข้อมูล: `int("5")` ได้ 5 · `float("8.5")` ได้ 8.5 · `str(10)` ได้ "10"
แทรกค่าลงในข้อความ: `f"ราคา {price} บาท"` (ต้องมี `f` นำหน้า)

---

## 2. list (รายการ) และ dict (พจนานุกรม)

```python
lots = ["A1", "A2", "B1"]
lots.append("B2")
lot = {"id": "A1", "moisture": 12.5, "grade": "G1"}
print(lots[0], len(lots), lot["moisture"], lot.get("price", 0))
```
| บรรทัด | ความหมาย |
|---|---|
| 1 | list คือของหลายชิ้นเรียงกันใน `[ ]` |
| 2 | `.append(...)` เพิ่มของต่อท้าย list |
| 3 | dict คือคู่ `กุญแจ: ค่า` ใน `{ }` หน้าตาเหมือน JSON |
| 4 | `lots[0]` คือตัวแรก (นับจาก 0) · `len(...)` คือจำนวน · `lot["moisture"]` ดึงค่าตามกุญแจ · `.get("price", 0)` ถ้าไม่มีกุญแจนี้ให้ได้ 0 แทน error |

> **JSON จาก API ส่วนใหญ่จะกลายเป็น dict และ list ใน Python** หัวข้อนี้จึงสำคัญที่สุด

---

## 3. if (เงื่อนไข)

```python
moisture = 13.2
if moisture <= 12:
    print("แห้งดี")
elif moisture <= 14:
    print("พอใช้")
else:
    print("ชื้นเกิน")
```
| บรรทัด | ความหมาย |
|---|---|
| 2 | ถ้าเงื่อนไขเป็นจริง ให้ทำบรรทัดที่ย่อหน้าอยู่ข้างใต้ ต้องมี `:` ท้ายบรรทัด |
| 3 | **ย่อหน้า 4 ช่อง** คือสิ่งที่บอกว่าบรรทัดนี้อยู่ใต้ if |
| 4 | `elif` = "ไม่งั้นถ้า..." ใช้ตรวจเงื่อนไขถัดไป |
| 6 | `else` = ทุกกรณีที่เหลือ |

ตัวเปรียบเทียบ: `==` เท่ากับ · `!=` ไม่เท่ากับ · `<` `<=` `>` `>=` · รวมเงื่อนไขด้วย `and` / `or` / `not`

---

## 4. for (วนซ้ำ)

```python
prices = [80, 95, 70]
total = 0
for p in prices:
    total = total + p
print("รวม", total)
```
| บรรทัด | ความหมาย |
|---|---|
| 3 | หยิบของใน `prices` ทีละตัวมาใส่ในชื่อ `p` แล้วทำบรรทัดที่ย่อหน้าอยู่ |
| 4 | บวกเข้า `total` ไปเรื่อยๆ |
| 5 | บรรทัดนี้ไม่ย่อหน้า จึงทำครั้งเดียวหลังวนเสร็จ ได้ `รวม 245` |

วนใน dict: `for key, value in lot.items():` · วนตามจำนวนครั้ง: `for i in range(5):` (ได้ 0–4)

---

## 5. def (ฟังก์ชัน)

```python
def total_value(kg, price_per_kg):
    return kg * price_per_kg

print(total_value(100, 85))
```
| บรรทัด | ความหมาย |
|---|---|
| 1 | `def` สร้างฟังก์ชันชื่อ `total_value` ที่รับค่า 2 ตัว |
| 2 | `return` ส่งผลลัพธ์กลับไปให้คนที่เรียก |
| 4 | เรียกใช้ฟังก์ชัน ได้ 8500 |

ฟังก์ชันช่วยให้ไม่ต้องเขียนโค้ดซ้ำ และแก้ทีเดียวได้ทุกที่ที่เรียกใช้

---

## 6. import (เรียกใช้โมดูล)

```python
import json
import time
from datetime import datetime
print(datetime.now(), json.dumps({"a": 1}))
time.sleep(1)
```
| บรรทัด | ความหมาย |
|---|---|
| 1–2 | โหลดโมดูล `json` และ `time` ที่มากับ Python อยู่แล้ว |
| 3 | ดึงมาเฉพาะ `datetime` จากโมดูล `datetime` |
| 4 | `datetime.now()` คือเวลาปัจจุบัน · `json.dumps(...)` แปลง dict เป็นข้อความ JSON |
| 5 | หยุดรอ 1 วินาที (ใช้กันยิง API ถี่เกินไป) |

`requests` ไม่ได้มากับ Python ต้อง pip install ก่อน (ใน .venv ติดตั้งไว้แล้ว)

---

## 7. อ่านและเขียนไฟล์

```python
with open("note.txt", "w", encoding="utf-8") as f:
    f.write("รอบ 1 ขายได้\n")
with open("note.txt", "r", encoding="utf-8") as f:
    text = f.read()
print(text)
```
| บรรทัด | ความหมาย |
|---|---|
| 1 | เปิดไฟล์โหมด `"w"` (เขียนทับ) ส่วน `encoding="utf-8"` ทำให้ภาษาไทยไม่เพี้ยน และ `with` จะปิดไฟล์ให้อัตโนมัติ |
| 2 | เขียนข้อความลงไฟล์ `\n` คือขึ้นบรรทัดใหม่ |
| 3 | เปิดไฟล์โหมด `"r"` (อ่าน) |
| 4 | อ่านทั้งไฟล์มาเก็บใน `text` |

โหมดอื่น: `"a"` เขียนต่อท้ายไฟล์เดิม ซึ่งเหมาะกับการเก็บ log

**JSON กับไฟล์:**
```python
import json
with open("data.json", "w", encoding="utf-8") as f:
    json.dump({"lot": "A1", "price": 85}, f, ensure_ascii=False, indent=2)
with open("data.json", encoding="utf-8") as f:
    data = json.load(f)
```
- `json.dump(ข้อมูล, ไฟล์)` บันทึก dict ลงไฟล์ · `ensure_ascii=False` ให้ภาษาไทยอ่านออก · `indent=2` จัดย่อหน้าให้อ่านง่าย
- `json.load(ไฟล์)` อ่านไฟล์กลับมาเป็น dict

---

## 8. try / except (จัดการ error)

```python
text = "abc"
try:
    price = float(text)
except ValueError as e:
    print("แปลงเป็นตัวเลขไม่ได้:", e)
    price = 0
```
| บรรทัด | ความหมาย |
|---|---|
| 2 | `try:` ลองทำโค้ดข้างใต้ |
| 3 | บรรทัดนี้จะ error เพราะ "abc" ไม่ใช่ตัวเลข |
| 4 | ถ้าเกิด `ValueError` ให้กระโดดมาที่นี่แทนที่โปรแกรมจะหยุด โดย `e` คือรายละเอียดของ error |
| 5–6 | แจ้งเตือนแล้วใช้ค่าสำรอง |

**สำคัญมากสำหรับ agent:** ถ้า agent ล่มกลางเกมจะเสียรอบไป จึงควรครอบส่วนที่เรียก API ด้วย try/except เสมอ

---

## 9. requests และ JSON (หัวใจของ Track 3)

> ตัวอย่างนี้ใช้ `http://127.0.0.1:8000` ซึ่งเป็น **เซิร์ฟเวอร์ฝึก** บนเครื่องเราเอง (`practice_server.py`) **ไม่ใช่ API ของการแข่งขัน** API จริงจะรู้ในวันที่ 17
> วิธีเปิดเซิร์ฟเวอร์ฝึก: เปิด Terminal อีกหน้าต่างแล้วรัน `.\.venv\Scripts\python.exe toolspractice_server.py`

### 9.1 GET: ขอข้อมูล
```python
import requests
r = requests.get("http://127.0.0.1:8000/lots", timeout=10)
print(r.status_code)
data = r.json()
print(data["lots"][0]["id"])
```
| บรรทัด | ความหมาย |
|---|---|
| 2 | ส่งคำขอแบบ GET ไปที่ URL และ `timeout=10` คือถ้า 10 วินาทีไม่ตอบให้ยอมแพ้ (**ใส่ทุกครั้ง** ไม่งั้นโปรแกรมอาจค้างไปเลย) |
| 3 | `status_code` คือรหัสผล เช่น 200 = สำเร็จ |
| 4 | `.json()` แปลงคำตอบ JSON เป็น dict/list |
| 5 | ดึง id ของล็อตแรก |

### 9.2 POST: ส่งข้อมูล
```python
payload = {"lot_id": "A1", "price": 85}
r = requests.post("http://127.0.0.1:8000/echo", json=payload, timeout=10)
print(r.json())
```
- `json=payload` ให้ requests แปลง dict เป็น JSON และใส่ header `Content-Type: application/json` ให้เอง

### 9.3 ใส่ header และ token
```python
TOKEN = "practice-token"
headers = {"Authorization": f"Bearer {TOKEN}"}
r = requests.get("http://127.0.0.1:8000/me", headers=headers, timeout=10)
```
- `headers` คือ dict ที่ส่งไปพร้อมคำขอ
- รูปแบบ `Bearer <token>` เป็นแบบที่ใช้กันบ่อย แต่ **API จริงอาจใช้รูปแบบอื่น** (ยังไม่ทราบ ดูคำถามข้อ 6 ใน CHECKLIST)
- **ห้ามแชร์ token** ใน LINE หรือ GitHub สาธารณะ

### 9.4 ตรวจ status code

| รหัส | ความหมาย | ควรทำอะไร |
|---|---|---|
| 200, 201 | สำเร็จ | อ่าน `.json()` ได้เลย |
| 400 | ส่งข้อมูลผิดรูปแบบ | อ่าน `r.text` ดูว่าผิดตรงไหน |
| 401, 403 | token ผิดหรือไม่มีสิทธิ์ | ตรวจ TOKEN และ header |
| 404 | URL ผิด | ตรวจ BASE_URL และ path |
| 429 | ส่งถี่เกินไป | `time.sleep(...)` แล้วค่อยลองใหม่ |
| 500 ขึ้นไป | เซิร์ฟเวอร์มีปัญหา | รอแล้วลองใหม่ |

```python
if r.status_code == 200:
    data = r.json()
else:
    print("ผิดพลาด", r.status_code, r.text[:200])
```
- `r.text[:200]` ดูข้อความตอบกลับแค่ 200 ตัวอักษรแรก

### 9.5 จัดการ error แบบครบ
```python
try:
    r = requests.get("http://127.0.0.1:8000/lots", timeout=10)
    r.raise_for_status()
    data = r.json()
except requests.exceptions.Timeout:
    print("รอนานเกินไป")
except requests.exceptions.ConnectionError:
    print("ต่อเซิร์ฟเวอร์ไม่ได้ (เน็ตหลุด หรือ URL ผิด)")
except requests.exceptions.HTTPError as e:
    print("เซิร์ฟเวอร์ตอบ error:", e)
except ValueError:
    print("คำตอบไม่ใช่ JSON")
```
- `raise_for_status()` ถ้า status เป็น 4xx/5xx จะโยน `HTTPError` ออกมาให้ except จับ
- แต่ละ `except` จับ error คนละแบบ ทำให้รู้ว่าพังเพราะอะไร

---

## 10. โครงของ Agent (ดู → คิด → ทำ) [Track 3.pdf น.4]

```python
import time
while True:
    state = look()
    action = think(state)
    act(action)
    time.sleep(2)
```
- `while True:` วนไปเรื่อยๆ จนกว่าจะหยุดเอง (กด Ctrl+C)
- `look / think / act` คือฟังก์ชันที่เราจะเขียนหลังรู้ API จริง
- **ส่วน `think` (กลยุทธ์) ยังไม่เขียน** จนกว่าจะได้กติกาและ API จริงในวันที่ 17–18
- starter agent ของผู้จัดน่าจะมีโครงแบบนี้ให้แล้ว [น.4]

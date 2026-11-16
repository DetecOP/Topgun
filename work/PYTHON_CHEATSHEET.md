# Python Cheatsheet สำหรับ Track 3

> เฉพาะเรื่องที่ต้องใช้เขียน agent ขายกาแฟ ทุกตัวอย่างลองรันได้
> วิธีรัน: บันทึกโค้ดเป็นไฟล์ `.py` ในโฟลเดอร์ `work/` แล้วรันด้วยคำสั่ง
> `.venv\Scripts\python.exe ชื่อไฟล์.py`

---

## 1. ตัวแปร (variable)
```python
lot_name = "A"          # ข้อความ (str) ต้องอยู่ในเครื่องหมายคำพูด
weight = 120            # จำนวนเต็ม (int)
moisture = 11.4         # ทศนิยม (float)
is_sold = False         # จริง/เท็จ (bool) ต้องขึ้นต้นด้วยตัวใหญ่ True / False
print(lot_name, weight * moisture)
```
- บรรทัด 1: สร้างกล่องชื่อ `lot_name` แล้วเก็บข้อความ "A" ไว้
- บรรทัด 2–3: เก็บตัวเลข เครื่องหมาย `#` คือคอมเมนต์ Python ไม่อ่านส่วนนี้
- บรรทัด 4: เก็บค่าจริง/เท็จ ใช้จำว่าขายแล้วหรือยัง
- บรรทัด 5: `print` แสดงผลบนจอ `*` คือคูณ (บวก `+` ลบ `-` หาร `/`)

**f-string** ใช้ใส่ตัวแปรลงในข้อความ:
```python
print(f"ล็อต {lot_name} หนัก {weight} กก. ความชื้น {moisture:.1f}%")
```
- ตัว `f` หน้าคำพูด ทำให้ `{...}` ถูกแทนด้วยค่าของตัวแปร ส่วน `:.1f` แปลว่าแสดงทศนิยม 1 ตำแหน่ง

---

## 2. list (รายการเรียงลำดับ)
```python
prices = [100, 95, 110]
prices.append(120)
print(prices[0], prices[-1], len(prices))
```
- บรรทัด 1: list ใช้วงเล็บเหลี่ยม `[]` เก็บหลายค่าเรียงกัน
- บรรทัด 2: `.append()` เพิ่มค่าต่อท้าย
- บรรทัด 3: `[0]` คือตัวแรก (Python เริ่มนับที่ 0) `[-1]` คือตัวสุดท้าย `len()` นับจำนวน → `100 120 4`

## 3. dict (คู่ ชื่อ → ค่า) ← หน้าตาเหมือน JSON
```python
lot = {"id": "A", "weight": 120, "moisture": 11.4}
lot["price"] = 105
print(lot["id"], lot.get("defect", 0))
```
- บรรทัด 1: dict ใช้วงเล็บปีกกา `{}` เก็บเป็นคู่ `"ชื่อ": ค่า`
- บรรทัด 2: เพิ่มหรือแก้ค่าด้วย `lot["ชื่อ"] = ค่า`
- บรรทัด 3: `lot["id"]` อ่านค่า ถ้าไม่มี key นี้จะ error ส่วน `.get("defect", 0)` ถ้าไม่มี key จะคืนค่า 0 แทน **ปลอดภัยกว่า**

---

## 4. if (ถ้า…ให้…)
```python
if moisture > 12.5:
    print("ชื้นเกิน เสี่ยงเชื้อรา")
elif moisture < 10:
    print("แห้งเกิน")
else:
    print("ความชื้นพอดี")
```
- บรรทัด 1: ถ้าเงื่อนไขจริง ให้ทำบรรทัดที่**ย่อหน้าเข้าไป** (4 ช่องว่าง) และต้องมี `:` ท้ายบรรทัด
- บรรทัด 3: `elif` = "ไม่งั้นถ้า" ตรวจเงื่อนไขถัดไป
- บรรทัด 5: `else` = ไม่ตรงเงื่อนไขไหนเลย
- ตัวเปรียบเทียบ: `>` `<` `>=` `<=` `==` (เท่ากับ) `!=` (ไม่เท่ากับ) และเชื่อมเงื่อนไขด้วย `and` `or` `not`

> ตัวเลข 10 และ 12.5 ในตัวอย่างเป็นค่าสมมติ ไม่ใช่กติกาจริง

## 5. for (วนซ้ำ)
```python
lots = [{"id": "A", "w": 120}, {"id": "B", "w": 80}]
total = 0
for lot in lots:
    total = total + lot["w"]
    print(lot["id"], lot["w"])
print("รวม", total)
```
- บรรทัด 1: list ที่ข้างในเป็น dict ซึ่งเป็นรูปแบบที่ API มักตอบกลับมา
- บรรทัด 3: `for lot in lots:` หยิบทีละตัวมาใส่ตัวแปร `lot` แล้วทำส่วนที่ย่อหน้า
- บรรทัด 4: บวกน้ำหนักสะสมไว้
- บรรทัด 6: ไม่ย่อหน้า จึงทำครั้งเดียวหลังวนเสร็จ → `รวม 200`
- นับรอบด้วย `for i in range(3):` จะได้ i = 0, 1, 2

## 6. def (สร้างฟังก์ชัน)
```python
def estimate_value(weight, price_per_kg):
    """คืนมูลค่ารวมของล็อต"""
    return weight * price_per_kg

print(estimate_value(120, 100))
```
- บรรทัด 1: `def ชื่อ(ตัวรับค่า):` สร้างฟังก์ชันเพื่อใช้ซ้ำ
- บรรทัด 2: ข้อความอธิบายฟังก์ชัน (docstring) ไม่บังคับ
- บรรทัด 3: `return` ส่งผลลัพธ์กลับไปให้คนที่เรียก
- บรรทัด 5: เรียกใช้ฟังก์ชัน → `12000`

## 7. import (เรียกใช้โมดูล)
```python
import json
import time
from datetime import datetime
print(datetime.now().isoformat())
```
- `import json` นำโมดูล json มาใช้ (มีมากับ Python อยู่แล้ว)
- `from datetime import datetime` หยิบมาเฉพาะชื่อ `datetime` ใช้ได้เลยโดยไม่ต้องพิมพ์ชื่อโมดูลนำหน้า
- `requests` และ `pandas` ต้องติดตั้งก่อน (มีใน `.venv` แล้ว)
- **ห้ามตั้งชื่อไฟล์ของเราซ้ำกับโมดูล** เช่น `json.py` หรือ `requests.py` เพราะ Python จะ import ไฟล์ของเราแทนโมดูลจริง

---

## 8. อ่าน/เขียนไฟล์
```python
with open("log.txt", "a", encoding="utf-8") as f:
    f.write("รอบ 1 ขายได้\n")

with open("log.txt", "r", encoding="utf-8") as f:
    for line in f:
        print(line.strip())
```
- บรรทัด 1: `open(ชื่อไฟล์, โหมด)` โหมด `"w"` = เขียนทับ, `"a"` = เขียนต่อท้าย, `"r"` = อ่าน
  - `encoding="utf-8"` **ต้องใส่เสมอบน Windows** ไม่งั้นภาษาไทยจะเพี้ยน
  - `with ... as f:` ปิดไฟล์ให้อัตโนมัติเมื่อจบบล็อก
- บรรทัด 2: `\n` คือขึ้นบรรทัดใหม่
- บรรทัด 5–6: วนอ่านทีละบรรทัด `.strip()` ตัดช่องว่างและ `\n` ที่หัวและท้ายออก

**JSON ↔ ไฟล์:**
```python
import json
data = {"lot": "A", "price": 105}
with open("state.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open("state.json", encoding="utf-8") as f:
    loaded = json.load(f)
print(loaded["price"])
```
- `json.dump` เขียน dict ลงไฟล์ JSON ส่วน `ensure_ascii=False` ทำให้ภาษาไทยอ่านออก และ `indent=2` จัดย่อหน้าให้อ่านง่าย
- `json.load` อ่านไฟล์ JSON กลับมาเป็น dict

## 9. try / except (จัดการ error ไม่ให้โปรแกรมพัง)
```python
try:
    price = float("abc")
except ValueError as e:
    print("แปลงตัวเลขไม่ได้:", e)
    price = 0
finally:
    print("ทำงานต่อได้")
```
- บรรทัด 1–2: ลองทำในบล็อก `try` ซึ่งอาจเกิด error
- บรรทัด 3: ถ้าเกิด error ชนิด `ValueError` ให้มาทำบล็อกนี้แทนการพัง `e` คือรายละเอียดของ error
- บรรทัด 6: `finally` ทำทุกครั้ง ไม่ว่าจะเกิด error หรือไม่
- **สำคัญมากสำหรับ agent:** ถ้าเน็ตหลุดแล้วไม่มี try/except agent จะหยุดทำงานกลางการแข่ง

---

## 10. requests: GET
```python
import requests
r = requests.get("https://httpbin.org/get", params={"lot": "A"}, timeout=10)
print(r.status_code)
data = r.json()
print(data["args"])
```
- บรรทัด 2: ส่งคำขอ **GET** (ขอดูข้อมูล)
  - `params=` จะต่อท้าย URL ให้เป็น `?lot=A`
  - `timeout=10` ถ้า 10 วินาทีไม่ตอบให้เลิกรอ **ใส่ทุกครั้ง** ไม่งั้นโปรแกรมอาจค้างตลอดไป
- บรรทัด 3: `status_code` คือรหัสผลลัพธ์ (ดูตารางข้อ 13)
- บรรทัด 4: `.json()` แปลงคำตอบที่เป็น JSON ให้กลายเป็น dict หรือ list
- (httpbin.org เป็นเว็บทดสอบสาธารณะ ใช้ฝึกเท่านั้น ไม่ใช่ API ของผู้จัด)

## 11. requests: POST (ส่งข้อมูล เช่น ส่งข้อเสนอขาย)
```python
offer = {"lot_id": "A", "buyer_id": "B1", "price": 105}
r = requests.post("https://httpbin.org/post", json=offer, timeout=10)
print(r.status_code, r.json()["json"])
```
- บรรทัด 1: dict ของข้อมูลที่จะส่ง (**ชื่อช่องจริงยังไม่ทราบ** ต้องรอเอกสาร API วันที่ 17)
- บรรทัด 2: `json=offer` แปลง dict เป็น JSON และตั้ง header `Content-Type: application/json` ให้อัตโนมัติ
- บรรทัด 3: httpbin ตอบกลับเป็นข้อมูลที่เราส่งไป ใช้ตรวจว่าส่งถูกต้อง

## 12. ใส่ header และ token
```python
TOKEN = ""   # เว้นว่าง กรอกเองวันแข่ง ห้าม commit ลง Git
headers = {"Authorization": f"Bearer {TOKEN}"}
r = requests.get("https://httpbin.org/headers", headers=headers, timeout=10)
print(r.json()["headers"].get("Authorization"))
```
- บรรทัด 1: ช่องเก็บ token ปล่อยว่างไว้
- บรรทัด 2: header คือข้อมูลแนบไปกับคำขอ รูปแบบ `Bearer <token>` นิยมใช้กันมาก **แต่ API ของผู้จัดอาจใช้ชื่ออื่น** เช่น `X-API-Key` ยังไม่ทราบ
- บรรทัด 3: `headers=` แนบ header ไปกับคำขอ

## 13. ตรวจ status code
| รหัส | ความหมาย | ทำอย่างไร |
|---|---|---|
| 200, 201 | สำเร็จ | อ่าน `r.json()` |
| 400 | ข้อมูลที่ส่งผิดรูปแบบ | ตรวจชื่อช่องและชนิดข้อมูล |
| 401 / 403 | token ผิด ไม่มี token หรือไม่มีสิทธิ์ | ตรวจ TOKEN และชื่อ header |
| 404 | URL ผิด | ตรวจ BASE_URL และ endpoint |
| 429 | เรียกถี่เกิน (rate limit) | รอสักพักแล้วค่อยลองใหม่ |
| 500–599 | เซิร์ฟเวอร์ผู้จัดมีปัญหา | รอแล้วลองใหม่ ไม่ใช่ความผิดเรา |

```python
if r.ok:                      # จริงเมื่อรหัสอยู่ระหว่าง 200–399
    data = r.json()
elif r.status_code == 429:
    time.sleep(2)             # หยุดรอ 2 วินาที
else:
    print("ผิดพลาด", r.status_code, r.text[:200])
```
- `r.text[:200]` คือข้อความดิบที่เซิร์ฟเวอร์ตอบมา ตัดเหลือ 200 ตัวอักษรแรก ช่วยให้เห็นสาเหตุ

## 14. จัดการ error ของ requests
```python
try:
    r = requests.get(URL, timeout=10)
    r.raise_for_status()
    data = r.json()
except requests.exceptions.Timeout:
    print("รอนานเกิน")
except requests.exceptions.ConnectionError:
    print("ต่อเซิร์ฟเวอร์ไม่ได้ (เน็ตหลุดหรือ URL ผิด)")
except requests.exceptions.HTTPError as e:
    print("เซิร์ฟเวอร์ตอบ error:", e)
except ValueError:
    print("คำตอบไม่ใช่ JSON")
```
- `raise_for_status()` ถ้ารหัสเป็น 4xx หรือ 5xx จะโยน `HTTPError` ทำให้หลุดไปบล็อก except
- แยก except ตามชนิดของ error จะรู้ทันทีว่าปัญหาอยู่ที่เน็ต ที่ token หรือที่ข้อมูล

---

## แบบฝึก
ทำ 5 ข้อใน [EXERCISES.md](EXERCISES.md) ไม่ต้องใช้อินเทอร์เน็ต เฉลยอยู่ที่ [exercises/solutions.py](exercises/solutions.py)

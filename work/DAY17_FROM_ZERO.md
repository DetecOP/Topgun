# เริ่มจาก 0 · เตรียมอบรม Track 3 วันที่ 17 พ.ย. (ทำเองทุกขั้น)

> โฟลเดอร์ใหม่อยู่**นอก** repo: `C:\Users\guttj\Documents\TGR2026_Day17` (เปลี่ยนชื่อได้ แต่ต้องเปลี่ยนให้ตรงทุกคำสั่ง)
> งานเดิมทั้งหมดใน `work\` และ `work\Ass1` เก็บไว้เหมือนเดิม ไม่ต้องลบ
> ⚠️ โฟลเดอร์นอก repo **ไม่มี Git** ช่วยสำรองให้ จบวันให้คัดลอกเก็บใส่ USB หรือ Drive
> คำสั่งทั้งหมดพิมพ์ใน **PowerShell** (กด Start → พิมพ์ PowerShell)

---

## ภาพรวม: วันนี้ต้องเตรียมอะไร (ตาม Track 3.pdf หน้า 7)
| ของที่ต้องพร้อม | ทำในขั้นไหน |
|---|---|
| โน้ตบุ๊กพร้อม Python 3.10+ สร้าง venv และ pip install ได้ | ขั้น 1–3 |
| โปรแกรมแก้โค้ด (VS Code) ที่รัน Python ได้ | ขั้น 4–5 |
| พื้นฐาน REST API + JSON: GET/POST และอ่าน JSON | ขั้น 6–8 |
| ที่จดกติกาและผลแต่ละรอบ | ขั้น 9 |

---

## ขั้น 1 · เช็ก Python ในเครื่อง
```powershell
py --version
```
- `py` คือตัวเรียก Python ของ Windows · `--version` คือขอดูเลขรุ่น
- ✅ ต้องได้ `Python 3.10` ขึ้นไป (เครื่องนี้ได้ 3.14.8)
- ❌ ขึ้น "not recognized" = ยังไม่ได้ติดตั้ง Python

## ขั้น 2 · สร้างโฟลเดอร์ใหม่แล้วเข้าไป
```powershell
mkdir C:\Users\guttj\Documents\TGR2026_Day17
cd C:\Users\guttj\Documents\TGR2026_Day17
mkdir starter, logs
```
- `mkdir` = สร้างโฟลเดอร์ · `cd` = เข้าไปทำงานในโฟลเดอร์นั้น
- `starter` = ไว้วาง starter agent ที่ผู้จัดแจก · `logs` = ไว้เก็บบันทึกการเรียก API
- ✅ พิมพ์ `pwd` ต้องเห็น `C:\Users\guttj\Documents\TGR2026_Day17`
- 💡 ทุกครั้งที่เปิด PowerShell ใหม่ ต้อง `cd` เข้ามาที่นี่ก่อน

## ขั้น 3 · สร้าง venv (กล่องแยกของงานนี้) แล้วติดตั้งแพ็กเกจ
```powershell
py -m venv .venv
```
- สร้างกล่องชื่อ `.venv` ข้างในมี Python ของตัวเองที่ `.venv\Scripts\python.exe`

ติดตั้ง `requests` (ใช้ส่ง GET/POST) เลือกได้ 1 ทาง:

**ทาง A · มีเน็ต**
```powershell
.venv\Scripts\python.exe -m pip install requests
```
**ทาง B · ไม่มีเน็ต** (ใช้ไฟล์สำรองที่โหลดไว้แล้ว)
```powershell
.venv\Scripts\python.exe -m pip install --no-index --find-links C:\Users\guttj\Documents\GitHub\team-project\.claude\worktrees\tesa-top-gun-rally-track3-11632c\work\wheelhouse requests
```
- `-m pip install` = ติดตั้งแพ็กเกจลงกล่องนี้
- `--no-index` = ห้ามไปหาบนเน็ต · `--find-links` = หาในโฟลเดอร์ที่ระบุแทน
- ✅ บรรทัดท้ายต้องขึ้น `Successfully installed ... requests-...`
- 💡 ใช้ `.venv\Scripts\python.exe` เรียกตรงๆ เสมอ ไม่ต้อง activate (กันปัญหา "running scripts is disabled")

## ขั้น 4 · เปิด VS Code ที่โฟลเดอร์นี้
```powershell
code .
```
- `.` = โฟลเดอร์ปัจจุบัน
- ถ้า VS Code ถาม "Do you trust the authors?" → เลือก **Trust** (เป็นโฟลเดอร์ที่เราสร้างเอง)
- เลือก Python ของกล่อง: `Ctrl+Shift+P` → พิมพ์ `Python: Select Interpreter` → เลือกตัวที่มีคำว่า `TGR2026_Day17\.venv`
- ✅ มุมขวาล่างต้องขึ้น `.venv`

## ขั้น 5 · ไฟล์แรก `check.py` (พิมพ์เอง)
`Ctrl+N` → พิมพ์ → `Ctrl+S` บันทึกชื่อ `check.py`
```python
import sys                                   # ข้อมูลของ Python ที่กำลังรัน
print("Python:", sys.version.split()[0])     # ต้อง 3.10 ขึ้นไป
print("อยู่ที่:", sys.executable)             # ต้องมีคำว่า TGR2026_Day17\.venv
import requests                              # error ตรงนี้ = ขั้น 3 ยังไม่สำเร็จ
print("requests พร้อม", requests.__version__)
```
กด ▶ มุมขวาบน หรือใน terminal พิมพ์ `.venv\Scripts\python.exe check.py`
- ✅ 3 บรรทัด และบรรทัด "อยู่ที่" มี `TGR2026_Day17`
- ❌ `ModuleNotFoundError: requests` = VS Code ใช้ Python ผิดตัว → ทำขั้น 4 เลือก interpreter ใหม่

---

## ความรู้ก่อนขั้น 6: REST API + JSON ใน 1 หน้า
| คำ | ความหมาย |
|---|---|
| **BASE_URL** | ที่อยู่ server เช่น `http://127.0.0.1:8000` |
| **endpoint** | ส่วนท้าย บอกว่าจะทำอะไร เช่น `/market` |
| **GET** | ขอดูข้อมูล |
| **POST** | ส่งข้อมูลไปให้ทำ เช่น ส่งข้อเสนอขาย |
| **header** | ข้อมูลแนบ เช่น token: `Authorization: Bearer xxx` |
| **status code** | 200 สำเร็จ · 400 ส่งผิด · 401 token ผิด · 404 path ผิด · 429 ถี่เกิน · 5xx server พัง |

| JSON | Python |
|---|---|
| `{"id": "A"}` | dict |
| `[1, 2]` | list |
| `true` `false` `null` | `True` `False` `None` |

- `r.json()` = แปลงคำตอบเป็น dict/list · `json={...}` ตอน POST = แปลง dict เป็น JSON ให้เอง

## ขั้น 6 · เปิดตลาดจำลองไว้ซ้อม (คืนนี้เท่านั้น)
เปิด PowerShell **อีกหน้าต่าง** ทิ้งไว้:
```powershell
C:\Users\guttj\Documents\GitHub\team-project\.claude\worktrees\tesa-top-gun-rally-track3-11632c\work\.venv\Scripts\python.exe C:\Users\guttj\Documents\GitHub\team-project\.claude\worktrees\tesa-top-gun-rally-track3-11632c\work\practice\mock_market.py
```
- ✅ ขึ้น `ตลาดจำลองเปิดแล้วที่ http://127.0.0.1:8000`
- ⚠️ path, ชื่อช่อง JSON และ token (`practice-token`) ของตลาดจำลองแต่งขึ้นเพื่อซ้อม พรุ่งนี้ของจริงจะต่างไป
- ปิด: `Ctrl+C` ในหน้าต่างนั้น

## ขั้น 7 · `api_get.py` ดูข้อมูลตลาด (พิมพ์เอง)
```python
import requests

# ===== 4 จุดที่พรุ่งนี้ต้องเปลี่ยนตามเอกสารผู้จัด =====
BASE_URL = "http://127.0.0.1:8000"            # 1) ที่อยู่ server
ENDPOINT = "/market"                          # 2) path ดูตลาด
TOKEN = "practice-token"                      # 3) token ทีม (ห้ามแชร์)
HEADERS = {"Authorization": f"Bearer {TOKEN}"}  # 4) ชื่อ header + รูปแบบ
# ================================================

r = requests.get(BASE_URL + ENDPOINT, headers=HEADERS, timeout=10)   # timeout กันค้าง
print("status:", r.status_code)
if r.status_code != 200:                      # เช็กก่อนอ่านทุกครั้ง
    print("ผิดพลาด:", r.text)
else:
    data = r.json()                           # JSON → dict
    print("ทั้งก้อน:", data)                    # ดูโครงก่อน แล้วค่อยหยิบทีละช่อง
    for lot in data["lots"]:                  # ชื่อช่องของจริงอาจไม่ใช่ "lots"
        print(lot["id"], lot["moisture"])
```
- ✅ เห็น `status: 200` แล้วตามด้วยรายการล็อต
- ลองลบบรรทัด `headers=HEADERS` ออกแล้วรัน → ต้องได้ `401` แปลว่าเข้าใจเรื่อง token แล้ว

## ขั้น 8 · `api_post.py` ส่งข้อเสนอขาย (พิมพ์เอง)
```python
import requests

BASE_URL = "http://127.0.0.1:8000"
HEADERS = {"Authorization": "Bearer practice-token"}

offer = {"offers": [                          # ข้อมูลที่จะส่ง (ชื่อช่องของจริงรอเอกสาร)
    {"lot_id": "A", "buyer_id": "B2", "price_per_kg": 95.0}
]}
try:
    r = requests.post(BASE_URL + "/offers", json=offer, headers=HEADERS, timeout=10)
except requests.exceptions.ConnectionError:
    print("ต่อ server ไม่ได้: ลืมเปิดตลาด หรือ URL ผิด")
else:
    print("status:", r.status_code)
    print(r.json())                           # ผลขายได้/ไม่ได้ หรือข้อความ error
```
- ✅ `200` พร้อม `"sold": true/false`
- ลองเปลี่ยน `95.0` เป็น `"แพง"` → ต้องได้ `400` แปลว่าเข้าใจการส่งผิดรูปแบบ
- ⚠️ **พรุ่งนี้ห้ามรันไฟล์นี้กับ server จริง** จนกว่าผู้จัดบอกว่าให้ส่ง (ช่วง 1 ขายผ่านหน้าเว็บ)

## ขั้น 9 · ไฟล์จดของพรุ่งนี้
**`notes.md`**
```
# อบรม 17 พ.ย.
ห้อง/เวลาจริง:
## สูตรมูลค่าล็อต (หน่วย)
## สูตรคะแนน (ขายไม่ได้ได้เท่าไร)
## ปิดซอง: ผู้ซื้อเลือกใคร จ่ายราคาไหน
## ผู้ซื้อ (เป็น AI) แต่ละแบบต้องการอะไร
## ความชื้น: เกณฑ์ 11 หรือ 12.5 · ค่าที่ให้มาเป็นความชื้นเมล็ดไหม
## API: BASE_URL / endpoint / ชื่อ header token / ลิมิต
## LLM ผู้จัด: URL / โมเดล / วิธีส่ง key
## starter agent: ได้มาทางไหน รันอย่างไร
## ใช้ AI ช่วยเขียนโค้ดตอนแข่งได้ไหม
```
**`rounds.csv`** (บรรทัดแรกเป็นหัวตาราง จดทุกข้อเสนอตอนขายมือ)
```
รอบ,ล็อต,ผู้ซื้อ,ราคาที่เสนอ,ขายได้,ราคาที่ขายได้,หมายเหตุ
```
- ห้ามจด token จริงลงไฟล์ · ถ่ายรูปสไลด์ที่มีสูตรทุกหน้า

---

## พรุ่งนี้ทำตามเวลา
| เวลา | ทำอะไร |
|---|---|
| ก่อนเริ่ม | `cd C:\Users\guttj\Documents\TGR2026_Day17` → รัน `check.py` ผ่าน → เปิด `notes.md` |
| อบรม | จด `notes.md` · ได้ starter → คัดลอกไปไว้ใน `starter\` **ไม่แก้** |
| ลงมือในห้อง | เปลี่ยน 4 จุดใน `api_get.py` ตามเอกสาร → รัน → ได้ 200 = ต่อ server ผู้จัดได้แล้ว |
| พักเที่ยง | ส่งสูตร / รูปสไลด์ให้ Claude ช่วยทำตัวคำนวณราคา |
| 13:00 ขายมือ | ขายผ่านหน้าเว็บ · จดทุกข้อเสนอใน `rounds.csv` |
| จบวัน | สำรองโฟลเดอร์ · ส่ง `notes.md`, `rounds.csv`, starter ให้ Claude เตรียมวันที่ 18 |

## ถ้าเจอปัญหา
| อาการ | ทำอะไร |
|---|---|
| `401` | เช็กชื่อ header กับรูปแบบ token ตามเอกสาร (อาจเป็น `X-API-Key: ...`) |
| `404` | เช็ก BASE_URL + endpoint ทีละตัวอักษร รวม `/` |
| `KeyError` | `print(r.json())` ดูชื่อช่องจริง แล้วแก้ชื่อในโค้ด |
| `429` | ใส่ `import time` แล้ว `time.sleep(1)` ระหว่างเรียก |
| `ConnectionError` | เน็ตหลุด / URL ผิด → ลองเปิด URL ในเบราว์เซอร์ |
| `ModuleNotFoundError` | รันด้วย `.venv\Scripts\python.exe` หรือเลือก interpreter ใหม่ |

## หลักที่ใช้ปรับเองได้ทุก API
โค้ดเรียก API มีแค่ **4 จุดที่เปลี่ยนตามผู้จัด**: BASE_URL · endpoint · ชื่อ header ของ token · ชื่อช่องใน JSON
ได้เอกสารจริงแล้ว เปลี่ยน 4 จุดนี้ → `print(r.json())` ดูโครง → ปรับชื่อช่อง → เสร็จ

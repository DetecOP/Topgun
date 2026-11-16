# เฉลยแบบฝึก 5 ข้อ (EXERCISES.md)
# รัน: .venv\Scripts\python.exe exercises\solutions.py
# ตัวเลขทุกตัวเป็นค่าสมมติเพื่อฝึก

import json                      # โมดูลแปลงข้อความ JSON <-> dict
import os                        # โมดูลจัดการไฟล์ (ใช้ลบไฟล์ทดสอบ)

print("=== ข้อ 1 ===")
moisture = 13.2                  # ความชื้น (%)
if moisture > 12.5:              # มากกว่า 12.5 -> ชื้นเกิน
    print("ชื้นเกิน")
elif moisture < 10:              # น้อยกว่า 10 -> แห้งเกิน
    print("แห้งเกิน")
else:                            # อยู่ระหว่างนั้น -> พอดี
    print("พอดี")

print("=== ข้อ 2 ===")
prices = [98, 105, 110, 92, 101]
total = 0                        # ตัวสะสมผลรวม
highest = prices[0]              # เริ่มจากตัวแรกเป็นค่าสูงสุดชั่วคราว
for p in prices:                 # หยิบราคาทีละตัว
    total = total + p            # บวกสะสม
    if p > highest:              # ถ้าเจอตัวที่มากกว่า
        highest = p              # จำไว้เป็นค่าสูงสุดใหม่
average = total / len(prices)    # ค่าเฉลี่ย = ผลรวม / จำนวน
print(f"เฉลี่ย {average} สูงสุด {highest}")

print("=== ข้อ 3 ===")
def lot_value(lot, base_price):
    """คืนมูลค่ารวมของล็อต (สูตรสมมติ)"""
    discount = lot["defect_pct"] * 0.015          # หัก 1.5% ต่อเมล็ดเสีย 1%
    return lot["weight"] * base_price * (1 - discount)

lot = {"id": "A", "weight": 120, "defect_pct": 6}
print(round(lot_value(lot, 100), 2))              # round ปัดทศนิยมกันเศษจากการคำนวณ -> 10920.0

print("=== ข้อ 4 ===")
text = '{"round": 3, "results": [{"lot": "A", "sold": true, "price": 105}, {"lot": "B", "sold": false, "price": 90}, {"lot": "C", "sold": true, "price": 112}]}'
data = json.loads(text)          # แปลงข้อความ JSON เป็น dict (true -> True)
sold_lots = []                   # เก็บชื่อล็อตที่ขายได้
sold_total = 0                   # เก็บยอดรวม
for item in data["results"]:     # วนทีละผลลัพธ์
    if item["sold"]:             # ถ้าขายได้
        sold_lots.append(item["lot"])
        sold_total += item["price"]   # += คือ sold_total = sold_total + ...
print(f"รอบ {data['round']} ขายได้: {sold_lots} รวม {sold_total}")

print("=== ข้อ 5 ===")
def save_log(path, round_no, lot, price, result):
    """เขียนต่อท้ายไฟล์ CSV หนึ่งบรรทัด"""
    with open(path, "a", encoding="utf-8") as f:  # "a" = เขียนต่อท้าย
        f.write(f"{round_no},{lot},{price},{result}\n")

def count_sold(path):
    """นับจำนวนบรรทัดที่ผลเป็น 'ขายได้' ถ้าไม่มีไฟล์คืน 0"""
    try:
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")    # แยกด้วยจุลภาค -> list
                if len(parts) == 4 and parts[3] == "ขายได้":
                    count += 1
        return count
    except FileNotFoundError:                     # ไฟล์ไม่มี -> ไม่พัง
        return 0

log_path = "exercise5_log.csv"
if os.path.exists(log_path):     # ลบไฟล์เก่า (ถ้ามี) ให้ผลเหมือนเดิมทุกครั้งที่รัน
    os.remove(log_path)
save_log(log_path, 1, "A", 105, "ขายได้")
save_log(log_path, 1, "B", 90, "ขายไม่ได้")
save_log(log_path, 2, "C", 112, "ขายได้")
print(f"ขายได้ {count_sold(log_path)} ครั้ง")
print(f"ไฟล์ไม่มี: {count_sold('ไม่มีไฟล์นี้.csv')}")
os.remove(log_path)              # ลบไฟล์ทดสอบทิ้ง

# เฉลยข้อ 1: list และ dict
lots = [  # list ที่มี dict อยู่ข้างใน 3 ตัว
    {"id": "A1", "kg": 100, "moisture": 12.1},
    {"id": "A2", "kg": 80, "moisture": 13.4},
    {"id": "B1", "kg": 120, "moisture": 11.8},
]

total = 0  # ตัวแปรเก็บน้ำหนักรวม เริ่มที่ 0
for lot in lots:  # หยิบทีละล็อต
    print(lot["id"], lot["kg"], "kg")  # พิมพ์ id และ kg
    total = total + lot["kg"]  # บวกน้ำหนักเข้าไป
print("รวม", total, "kg")  # พิมพ์ผลรวมหลังวนเสร็จ

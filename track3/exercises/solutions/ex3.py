# เฉลยข้อ 3: เขียนและอ่านไฟล์ JSON
import json  # โมดูลสำหรับ JSON

lots = [
    {"id": "A1", "kg": 100, "moisture": 12.1},
    {"id": "A2", "kg": 80, "moisture": 13.4},
    {"id": "B1", "kg": 120, "moisture": 11.8},
]

with open("lots.json", "w", encoding="utf-8") as f:  # เปิดไฟล์เพื่อเขียน
    json.dump(lots, f, ensure_ascii=False, indent=2)  # บันทึก list ลงไฟล์

with open("lots.json", "r", encoding="utf-8") as f:  # เปิดไฟล์เพื่ออ่าน
    data = json.load(f)  # อ่านกลับมาเป็น list

heaviest = data[0]  # สมมติก่อนว่าตัวแรกหนักสุด
for lot in data:  # ไล่ดูทุกตัว
    if lot["kg"] > heaviest["kg"]:  # ถ้าเจอตัวที่หนักกว่า
        heaviest = lot  # จำตัวนั้นไว้แทน
print(f"หนักที่สุด: {heaviest['id']} ({heaviest['kg']} kg)")  # พิมพ์ผล
# วิธีสั้น: heaviest = max(data, key=lambda x: x["kg"])

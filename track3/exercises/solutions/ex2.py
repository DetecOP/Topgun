# เฉลยข้อ 2: def และ if
lots = [
    {"id": "A1", "kg": 100, "moisture": 12.1},
    {"id": "A2", "kg": 80, "moisture": 13.4},
    {"id": "B1", "kg": 120, "moisture": 11.8},
]


def moisture_label(m):  # รับค่าความชื้น m
    if m < 12:  # น้อยกว่า 12
        return "แห้ง"
    elif m <= 13:  # 12 ถึง 13
        return "ปกติ"
    else:  # มากกว่า 13
        return "ชื้น"


for lot in lots:  # วนทุกล็อต
    print(lot["id"], moisture_label(lot["moisture"]))  # เรียกฟังก์ชันแล้วพิมพ์

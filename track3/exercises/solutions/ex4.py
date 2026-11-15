# เฉลยข้อ 4: try/except
raw = ["85", "90.5", "abc", "", "77"]  # ข้อมูลที่บางตัวพิมพ์ผิด

prices = []  # list เก็บราคาที่แปลงได้
for text in raw:  # วนทีละตัว
    try:
        prices.append(float(text))  # ลองแปลงเป็นตัวเลขแล้วเก็บ
    except ValueError:  # ถ้าแปลงไม่ได้
        print(f"เตือน: '{text}' ไม่ใช่ตัวเลข ข้ามไป")  # แจ้งเตือนแล้วไปตัวถัดไป

if prices:  # กันกรณีไม่มีตัวไหนแปลงได้เลย (หารด้วย 0)
    print("เฉลี่ย", round(sum(prices) / len(prices), 2))  # sum = ผลรวม, len = จำนวน

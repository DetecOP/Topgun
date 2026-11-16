# load_prep.py · อ่านชีท "คำนวณมูลค่าล็อต" และ "บันทึกรอบ" จาก TGR2026_Track3_Prep.xlsx แล้วพิมพ์สรุป
#
# ยังไม่มีกลยุทธ์ราคา แค่อ่านและแสดงผล
# ตัวเลขในไฟล์ Excel เป็นค่าสมมติเพื่อซ้อม ไม่ใช่กติกาจริง
# รัน: .venv\Scripts\python.exe load_prep.py
#
# หมายเหตุสำคัญ: pandas อ่าน "ค่าที่ Excel คำนวณแล้วบันทึกไว้" ไม่ได้คำนวณสูตรเอง
# ถ้าแก้ไฟล์ด้วยโปรแกรมอื่นที่ไม่ใช่ Excel ช่องสูตรอาจว่าง → ให้เปิดไฟล์ใน Excel แล้วกดบันทึกหนึ่งครั้ง

import sys                                   # ตั้งการแสดงผลภาษาไทย
from pathlib import Path                     # จัดการ path ไฟล์

import pandas as pd                          # ไลบรารีตาราง (ใช้ openpyxl อ่าน .xlsx เบื้องหลัง)

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 200)          # ให้ตารางกว้างพอ ไม่ขึ้นบรรทัดใหม่
pd.set_option("display.max_columns", 20)     # แสดงได้สูงสุด 20 คอลัมน์

XLSX = Path(__file__).parent / "TGR2026_Track3_Prep.xlsx"   # ไฟล์ที่คัดลอกไว้ใน work/


def read_sheet(sheet_name, key_column):
    """อ่านชีท โดยหัวตารางอยู่แถว 4 ของ Excel แล้วตัดแถวที่ไม่มีข้อมูลในคอลัมน์หลักออก"""
    df = pd.read_excel(XLSX, sheet_name=sheet_name, header=3)  # header=3 = แถวที่ 4 (นับจาก 0)
    df = df.dropna(how="all")                                   # ตัดแถวที่ว่างทั้งแถว
    df = df[df[key_column].notna()]                             # เก็บเฉพาะแถวที่มีชื่อล็อต (แถวสูตรเปล่าถูกตัด)
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]  # ตัดคอลัมน์ที่ไม่มีหัว
    return df


def main():
    if not XLSX.exists():                                       # กันกรณีไฟล์หาย
        print(f"❌ ไม่พบไฟล์ {XLSX}")
        return 1

    print("=" * 70)
    print("ชีท: คำนวณมูลค่าล็อต (ค่าสมมติเพื่อซ้อม)")
    print("=" * 70)
    lots = read_sheet("คำนวณมูลค่าล็อต", "ล็อต")
    cols = ["ล็อต", "น้ำหนัก (กก.)", "ความชื้น (%)", "เกรดขนาด", "เมล็ดเสีย (%)",
            "ราคาประเมิน/กก.", "มูลค่ารวม", "ราคาเสนอแนะ/กก."]
    print(lots[cols].round(2).to_string(index=False))           # round(2) = ทศนิยม 2 ตำแหน่ง

    if lots["ราคาประเมิน/กก."].isna().any():                     # ช่องสูตรว่าง = ไฟล์ยังไม่ถูกคำนวณใน Excel
        print("⚠️  บางช่องสูตรว่าง: เปิดไฟล์ใน Excel แล้วบันทึกหนึ่งครั้ง")
    print(f"\nจำนวนล็อต {len(lots)} · น้ำหนักรวม {lots['น้ำหนัก (กก.)'].sum():,.0f} กก. · "
          f"มูลค่ารวม {pd.to_numeric(lots['มูลค่ารวม'], errors='coerce').sum():,.2f}")

    print()
    print("=" * 70)
    print("ชีท: บันทึกรอบ")
    print("=" * 70)
    rounds = read_sheet("บันทึกรอบ", "ล็อต")
    print(rounds.round(3).to_string(index=False))

    sold = rounds[rounds["ผลขาย"] == "ขายได้"]                  # กรองเฉพาะแถวที่ขายได้
    print(f"\nเสนอทั้งหมด {len(rounds)} ครั้ง · ขายได้ {len(sold)} ครั้ง"
          + (f" ({len(sold) / len(rounds):.0%})" if len(rounds) else ""))
    if len(rounds) < 20:
        print("หมายเหตุ: ข้อมูลน้อยกว่า 20 รอบ ใช้ดูแนวโน้มเท่านั้น (ตามชีท วิธีใช้)")

    print("\nสรุปตามผู้ซื้อ:")
    by_buyer = rounds.groupby("ผู้ซื้อ").agg(                    # จัดกลุ่มตามผู้ซื้อ แล้วนับ
        เสนอ=("ล็อต", "count"),
        ขายได้=("ผลขาย", lambda s: (s == "ขายได้").sum()),
    )
    print(by_buyer.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())

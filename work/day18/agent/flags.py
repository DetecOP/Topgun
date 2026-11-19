"""ป้ายรุ่นโค้ด + ชื่อชุดทดลอง (ใช้แยกผลใน analyze_logs.py)

สวิตช์ทดลอง V2_* ถูกตัดออกแล้ว (18 พ.ย. ~11:00): ไม่มีตัวไหนดีกว่า baseline จริงใน 200+ เกม ·
V2_EARLY_SELL แย่กว่า · ผลอยู่ใน work/day18/KNOWLEDGE.md
ทดลองค่าอื่นได้ด้วยตัวแปร .env (เช่น DELTA_DEFECT) + ตั้งชื่อชุดด้วย AGENT_TAG
"""
import os

# เปลี่ยนเมื่อแก้โค้ดที่กระทบผล · analyze_logs เทียบเฉพาะเกมโค้ดรุ่นเดียวกัน
# fill1 = เติมซองให้ถึงงบ · spec2 = Specialty ก่อน + ระยะเผื่อจากความคลาดจริง + ห้ามส่งตามความเข้มสเปก
# pace3 = งบกระสอบหารด้วยอัตราขายได้จริง + ใช้ capacity เต็มเมื่อของเสี่ยงขายไม่ทัน
# practice4 (รอบซ้อมหยั่งราคา · ไม่ถาม LLM ในรอบซ้อม) มีผลเฉพาะรอบซ้อม · ตลาดฝึกไม่มีรอบซ้อม → พฤติกรรมเท่า pace3
# จึงใช้ป้าย pace3 ต่อ ให้ชุด baseline/mid-push ที่กำลังทดลองอยู่ตารางเดียวกัน
CODE_VERSION = "market3"   # 18 พ.ย. หลังแข่ง: ราคาจาก market_summary + ใช้ capacity เต็ม


def active() -> list[str]:
    return []


def tag() -> str:
    return os.environ.get("AGENT_TAG") or "baseline"

# llm_check.py · ทดสอบ LLM ทั้ง 3 แบบ (ollama ในเครื่อง / ผู้จัด / ปิด) และทางสำรองแบบกฎ
# รัน: .venv\Scripts\python.exe simulator\llm_check.py
# วันแข่ง: กรอก ORGANIZER_LLM_* ใน config.py แล้วรันใหม่ ดูบรรทัด "organizer"

import sys

from llm_client import LLMClient
from llm_tasks import parse_buyer_request, pitch_for_buyer

sys.stdout.reconfigure(encoding="utf-8")

OFFER = {"lot_id": "A", "price_per_kg": 104.65, "weight": 120, "recheck": True,
         "reason": "ผลวัด: ความชื้น 12.4% เมล็ดเสีย 6% ขนาด กลาง → มูลค่า 91.0/กก. · ความชื้นใกล้เกณฑ์ 12.5% · เสนอ +15% จากฐาน"}
REQUESTS = [
    "โรงคั่วของเราต้องการเมล็ดขนาดใหญ่ ความชื้นไม่เกิน 12% และเมล็ดเสียไม่เกิน 5%",
    "We buy medium beans, moisture max 13.5 percent, defects up to 15%.",
    "ต้องการของสะอาด ไม่มีกลิ่นรา",                         # ไม่มีตัวเลข → ควรได้ null
]

for provider in ("ollama", "organizer", "off"):
    c = LLMClient(provider)
    print("=" * 70)
    print(f"[{provider}] {c.describe()}")
    text, src = pitch_for_buyer(OFFER, c, force_llm=True)    # บังคับลอง LLM เพื่อดูคุณภาพ (วันแข่งปิดไว้เป็นค่าเริ่มต้น)
    ms = f"{c.last_ms:.0f} ms" if c.last_ms else "-"
    print(f"  ข้อความเสนอขาย ({src}, {ms}): {text}")
    if src == "rule" and c.last_error:
        print(f"  (ใช้ทางสำรองเพราะ: {c.last_error})")
    for req in REQUESTS:
        d, src = parse_buyer_request(req, c)
        print(f"  อ่านความต้องการ ({src}): {req[:40]}… → {d}")

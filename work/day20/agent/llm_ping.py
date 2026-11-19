"""ทดสอบ LLM gateway 1 ครั้ง (ไม่ส่งซอง · ไม่แตะตลาด): python llm_ping.py

อ่าน LLM_BASE_URL / LLM_API_KEY / LLM_MODEL จาก .env (โฟลเดอร์นี้ → AGENT_ENV → starter) · ไม่พิมพ์ key
บอก: พอร์ตเปิดไหม · ตอบเป็น JSON ไหม · ใช้เวลากี่วินาที
"""
import json
import os
import socket
import time
from urllib.parse import urlparse

import main
from llm import LLM

main.load_env(main.HERE / ".env")
if os.environ.get("AGENT_ENV"):
    main.load_env(main.Path(os.environ["AGENT_ENV"]))
main.load_env(main.STARTER_ENV)

base, key, model = os.environ.get("LLM_BASE_URL", ""), os.environ.get("LLM_API_KEY", ""), os.environ.get("LLM_MODEL", "event-llm")
print("LLM_BASE_URL:", base, "· model:", model, "· มี key:", bool(key))
u = urlparse(base)
s = socket.socket()
s.settimeout(4)
try:
    s.connect((u.hostname, u.port or 80))
    print(f"พอร์ต {u.port}: เปิด")
except OSError as e:
    print(f"พอร์ต {u.port}: ต่อไม่ได้ ({type(e).__name__}) → gateway ยังไม่เปิด หรือที่อยู่ผิด · ถามทีมงาน")
    raise SystemExit(1)
finally:
    s.close()

llm = LLM(base, model, key, timeout=60, thinking=False, max_tokens=400, temperature=0.2)
schema = {"type": "object", "required": ["markup", "volume", "reason"], "properties": {
    "markup": {"type": "object", "properties": {"COMMERCIAL": {"type": "number"}}},
    "volume": {"type": "string", "enum": ["hold", "normal", "push"]},
    "reason": {"type": "string", "maxLength": 120}}}
t = time.time()
ans = llm.ask_json("You tune prices for a coffee seller. Answer only JSON.",
                   "Round 3 of 8. COMMERCIAL: x1.00 OUTBID twice, x0.98 ACCEPTED. Choose COMMERCIAL markup and volume.",
                   schema, timeout=60)
print(f"ใช้เวลา {time.time() - t:.1f} วิ · คำตอบ: {json.dumps(ans, ensure_ascii=False)} · error: {llm.last_error}")
print("ผ่าน ✓" if isinstance(ans, dict) and "markup" in ans else "ไม่ผ่าน ✗ (ดู error ข้างบน)")

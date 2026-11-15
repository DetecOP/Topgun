# practice_server.py — เซิร์ฟเวอร์ฝึกที่รันบนเครื่องตัวเอง ไม่ต้องใช้อินเทอร์เน็ต
# ⚠️ ใช้ฝึกเรียก GET/POST เท่านั้น ไม่ใช่ API ของการแข่งขัน ทั้ง URL, ข้อมูล และ token ในไฟล์นี้เป็นของสมมติทั้งหมด
# วิธีรัน:  .\.venv\Scripts\python.exe practice_server.py   (กด Ctrl+C เพื่อหยุด)

import json  # ใช้แปลง dict <-> ข้อความ JSON
from http.server import BaseHTTPRequestHandler, HTTPServer  # เครื่องมือทำเว็บเซิร์ฟเวอร์ที่มากับ Python

PRACTICE_TOKEN = "practice-token"  # token สมมติ ใช้ฝึกใส่ header เท่านั้น

# ข้อมูลล็อตสมมติ (ตัวเลขแต่งขึ้นเพื่อฝึก ไม่เกี่ยวกับโจทย์จริง)
LOTS = [
    {"id": "P1", "kg": 100, "moisture": 12.1},
    {"id": "P2", "kg": 80, "moisture": 13.4},
    {"id": "P3", "kg": 120, "moisture": 11.8},
]


class Handler(BaseHTTPRequestHandler):  # คลาสที่บอกว่าจะตอบแต่ละคำขออย่างไร
    def _send(self, code, body):  # ฟังก์ชันช่วยส่งคำตอบ JSON
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")  # แปลง dict เป็นข้อความ JSON แบบ bytes
        self.send_response(code)  # ส่ง status code
        self.send_header("Content-Type", "application/json; charset=utf-8")  # บอกว่าเป็น JSON
        self.send_header("Content-Length", str(len(data)))  # บอกความยาว
        self.end_headers()  # จบส่วน header
        self.wfile.write(data)  # ส่งเนื้อหา

    def do_GET(self):  # ถูกเรียกเมื่อมีคำขอแบบ GET
        if self.path == "/lots":  # GET /lots ส่งรายการล็อต
            self._send(200, {"lots": LOTS})
        elif self.path == "/me":  # GET /me ต้องมี token
            auth = self.headers.get("Authorization", "")  # อ่าน header Authorization
            if auth == f"Bearer {PRACTICE_TOKEN}":
                self._send(200, {"team": "practice-team"})
            else:
                self._send(401, {"error": "missing or wrong token"})
        elif self.path == "/error":  # GET /error จำลองเซิร์ฟเวอร์พัง
            self._send(500, {"error": "simulated server error"})
        else:  # path อื่นๆ
            self._send(404, {"error": "not found", "path": self.path})

    def do_POST(self):  # ถูกเรียกเมื่อมีคำขอแบบ POST
        length = int(self.headers.get("Content-Length", 0))  # ความยาวของข้อมูลที่ส่งมา
        raw = self.rfile.read(length)  # อ่านข้อมูลดิบ
        try:
            body = json.loads(raw or b"{}")  # แปลง JSON เป็น dict
        except ValueError:
            self._send(400, {"error": "body is not valid JSON"})  # ถ้าไม่ใช่ JSON ตอบ 400
            return
        if self.path == "/echo":  # POST /echo ส่งสิ่งที่ได้รับกลับไป
            self._send(200, {"received": body})
        else:
            self._send(404, {"error": "not found", "path": self.path})

    def log_message(self, fmt, *args):  # แสดงบรรทัดสั้นๆ ทุกครั้งที่มีคำขอเข้ามา
        print("[server]", self.command, self.path)


if __name__ == "__main__":  # ทำงานเมื่อรันไฟล์นี้โดยตรง
    print("Practice server: http://127.0.0.1:8000  (Ctrl+C เพื่อหยุด)")
    HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()  # เปิดเซิร์ฟเวอร์ที่พอร์ต 8000 เฉพาะเครื่องนี้

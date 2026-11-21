# mock_market.py · ตลาดจำลองในเครื่อง ไว้ฝึกเรียก REST API ด้วย Python (ไม่ใช่ server ผู้จัด)
#
# ⚠️ ทุกอย่างในไฟล์นี้แต่งขึ้นเพื่อฝึก: path, ชื่อช่อง JSON, token, กติกา ไม่ใช่ของจริง
#    API จริงของผู้จัดจะรู้วันที่ 17–18 แต่หลักการ GET/POST/header/JSON/status code เหมือนกัน
#
# เปิด server (หน้าต่าง terminal ที่ 1, ทิ้งไว้):
#   .venv\Scripts\python.exe practice\mock_market.py
# ปิด server: กด Ctrl+C ในหน้าต่างนั้น
#
# Endpoint (ที่อยู่) ทั้งหมด · BASE_URL = http://127.0.0.1:8000
#   GET  /health    ไม่ต้องใช้ token → {"ok": true}
#   GET  /market    ต้องใช้ token   → รอบปัจจุบัน ล็อตของเรา ผู้ซื้อ
#   POST /offers    ต้องใช้ token   → ส่งข้อเสนอขาย {"offers": [{"lot_id","buyer_id","price_per_kg"}]}
#   GET  /results   ต้องใช้ token   → ผลทุกข้อเสนอที่ผ่านมา
#   POST /reset     ต้องใช้ token   → เริ่มเกมใหม่
# Token ฝึก: ส่ง header  Authorization: Bearer practice-token
# เรียกเกิน 5 ครั้งต่อวินาที → 429 (จำลอง rate limit)

import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRACTICE_TOKEN = "practice-token"          # token สำหรับฝึกในเครื่องเท่านั้น
ROUNDS = 8
LOCK = threading.Lock()                    # กันคำขอพร้อมกันแก้ข้อมูลชนกัน
STATE = {}
HITS = []                                  # เวลาที่ถูกเรียก (ใช้นับ rate limit)


def value_per_kg(m, d, size):
    """สูตรสมมติเดียวกับชีท ตั้งค่า ใน Excel"""
    mult = {"ติดเปลือก": 0.85, "เล็ก": 0.95, "กลาง": 1.0, "ใหญ่": 1.08}[size]
    ded = max(0, m - 12.5) * 0.04 + max(0, 10 - m) * 0.02 + d * 0.015
    return 100 * mult * (1 - min(0.6, ded))


def new_game(seed=None):
    rng = random.Random(seed)
    lots = []
    for i in range(6):
        m, d = round(rng.uniform(10, 14.5), 1), round(rng.uniform(2, 18), 1)
        size = rng.choice(["ติดเปลือก", "เล็ก", "กลาง", "ใหญ่"])
        lots.append({"id": chr(65 + i), "weight": rng.choice([50, 80, 100, 120, 150]),
                     "moisture": m, "defect_pct": d, "size": size,
                     "reveal_round": rng.randint(1, 3), "sold": False,
                     "_value": value_per_kg(m, d, size)})
    buyers = [{"id": "B1", "type": "โรงคั่วเน้นคุณภาพ", "max_moisture": 12.5, "max_defect": 8, "_mult": 1.20},
              {"id": "B2", "type": "โรงงานเน้นปริมาณ", "max_moisture": 13.5, "max_defect": 15, "_mult": 1.05},
              {"id": "B3", "type": "ผู้ซื้อทั่วไป", "max_moisture": 13.0, "max_defect": 12, "_mult": 1.10}]
    STATE.clear()
    STATE.update({"round": 1, "lots": lots, "buyers": buyers, "results": []})


def public_market():
    r = STATE["round"]
    lots = []
    for l in STATE["lots"]:
        if l["sold"]:
            continue
        known = r >= l["reveal_round"]                         # ผลวัดมาถึงตามรอบ (จำลองเซนเซอร์มาช้า)
        lots.append({"id": l["id"], "weight": l["weight"],
                     "moisture": l["moisture"] if known else None,
                     "defect_pct": l["defect_pct"] if known else None,
                     "size": l["size"] if known else None})
    return {"round": r, "rounds_total": ROUNDS, "game_over": r > ROUNDS,
            "lots": lots, "buyers": [{k: v for k, v in b.items() if not k.startswith("_")}
                                     for b in STATE["buyers"]]}


def resolve(offers):
    """ผู้ซื้อแต่ละรายรับล็อตที่คุ้มสุด 1 ล็อตต่อรอบ ถ้าราคาไม่เกินราคาลับ และผ่านเงื่อนไข"""
    lots = {l["id"]: l for l in STATE["lots"]}
    buyers = {b["id"]: b for b in STATE["buyers"]}
    out, best = [], {}
    for o in offers:
        lot, b = lots[o["lot_id"]], buyers[o["buyer_id"]]
        reserve = lot["_value"] * b["_mult"]
        ok = lot["moisture"] <= b["max_moisture"] and lot["defect_pct"] <= b["max_defect"]
        surplus = reserve - o["price_per_kg"]
        if ok and surplus >= 0 and surplus > best.get(b["id"], (None, -1))[1]:
            best[b["id"]] = (o["lot_id"], surplus)
    winners = {v[0] for v in best.values()}
    for o in offers:
        sold = o["lot_id"] in winners
        if sold:
            lots[o["lot_id"]]["sold"] = True
        res = {"round": STATE["round"], "lot_id": o["lot_id"], "buyer_id": o["buyer_id"],
               "price_per_kg": o["price_per_kg"], "sold": sold}
        STATE["results"].append(res)
        out.append(res)
    STATE["round"] += 1
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, need_token=True):
        now = time.time()
        HITS[:] = [t for t in HITS if now - t < 1.0] + [now]
        if len(HITS) > 5:
            self._send(429, {"error": "rate limit: เรียกได้ไม่เกิน 5 ครั้งต่อวินาที"})
            return False
        if need_token and self.headers.get("Authorization") != f"Bearer {PRACTICE_TOKEN}":
            self._send(401, {"error": "ไม่มี token หรือ token ผิด (header Authorization: Bearer ...)"})
            return False
        return True

    def do_GET(self):
        with LOCK:
            if self.path == "/health":
                if self._guard(need_token=False):
                    self._send(200, {"ok": True})
            elif self.path == "/market":
                if self._guard():
                    self._send(200, public_market())
            elif self.path == "/results":
                if self._guard():
                    self._send(200, {"results": STATE["results"]})
            else:
                self._send(404, {"error": f"ไม่มี path {self.path}"})

    def do_POST(self):
        with LOCK:
            if self.path not in ("/offers", "/reset"):
                return self._send(404, {"error": f"ไม่มี path {self.path}"})
            if not self._guard():
                return
            if self.path == "/reset":
                new_game()
                return self._send(200, {"ok": True, "round": 1})
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "body ไม่ใช่ JSON"})
            if STATE["round"] > ROUNDS:
                return self._send(409, {"error": "เกมจบแล้ว เรียก POST /reset เพื่อเริ่มใหม่"})
            offers, errors = [], []
            open_lots = {l["id"] for l in STATE["lots"] if not l["sold"]}
            buyer_ids = {b["id"] for b in STATE["buyers"]}
            for i, o in enumerate(data.get("offers", []) if isinstance(data, dict) else []):
                if not isinstance(o, dict) or o.get("lot_id") not in open_lots:
                    errors.append(f"ข้อ {i}: lot_id ไม่ถูกต้องหรือขายไปแล้ว")
                elif o.get("buyer_id") not in buyer_ids:
                    errors.append(f"ข้อ {i}: buyer_id ไม่ถูกต้อง")
                elif not isinstance(o.get("price_per_kg"), (int, float)) or o["price_per_kg"] <= 0:
                    errors.append(f"ข้อ {i}: price_per_kg ต้องเป็นตัวเลขมากกว่า 0")
                else:
                    offers.append(o)
            if errors and not offers:
                return self._send(400, {"error": "ข้อมูลผิด", "details": errors})
            results = resolve(offers)
            self._send(200, {"round_done": STATE["round"] - 1, "results": results, "warnings": errors})

    def log_message(self, fmt, *args):                         # พิมพ์ log สั้นๆ ภาษาอ่านง่าย
        print(f"[ตลาดจำลอง] {self.command} {self.path} → {args[1] if len(args) > 1 else ''}")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    new_game(seed=17)
    print("ตลาดจำลองเปิดแล้วที่ http://127.0.0.1:8000  (token ฝึก: practice-token) · ปิดด้วย Ctrl+C")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()

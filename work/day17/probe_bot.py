# probe_bot.py · เล่นตลาดฝึก (sandbox) อัตโนมัติผ่าน API เพื่อเก็บสถิติ "เพดานลับ" ของผู้ซื้อแต่ละราย
#
# ⚠️ ใช้กับตลาดฝึกเท่านั้น (สไลด์ 35 ให้ฝึกด้วย Python ได้) · ตัวกันพลาด:
#   1) เช็ก /v1/version mode และ /v1/state market ต้องเป็น "sandbox" ทุกครั้ง ไม่ใช่ → หยุดทันที ไม่ส่งอะไร
#   2) หยุดเองตามเวลา --until (ค่าเริ่มต้น 13:55 ก่อนทีมไปแข่ง 14:00) · ตั้งช่วงห้ามได้ด้วย --blackout-from/--blackout-to (ค่าเริ่มต้นปิด)
#   3) อ่าน key จาก .env ของ starter (ไม่พิมพ์ key ออกจอ ไม่เขียนลง log)
#
# รัน (จากโฟลเดอร์ work):
#   .venv\Scripts\python.exe day17\probe_bot.py                  (หยุดเอง 13:55 · กด Ctrl+C หยุดก่อนได้)
#   .venv\Scripts\python.exe day17\probe_bot.py --until 17:00 --no-reset     (ไม่กดเริ่มเกมใหม่เอง)
# ผล: day17\probe_data\offers.jsonl (ทุกซองของเรา) · market.jsonl (ข้อมูลตลาดทุกรอบ) · reveal-*.json
#     แล้วรัน probe_report.py ดูสรุป
#
# วิธีหาเพดาน: ต่อผู้ซื้อแต่ละราย เก็บช่วง [ขายได้สูงสุด, เกินเพดานต่ำสุด] เป็นเท่าของ TV
#   แล้วเสนอ "กึ่งกลางช่วง" ทีละ 1 กระสอบ (ใช้ของน้อย ลองได้หลายครั้ง) · ช่วงแคบแล้วสุ่มรอบๆ เพื่อดูว่าเพดานเปลี่ยนไหม

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
STARTER = Path(r"C:\Users\guttj\Documents\TGR2026\starter\Coffee-TESA-starter")
DATA = HERE / "probe_data"
BAG = 60
LO0, HI0 = 0.85, 1.30                     # ช่วงค้นหาเริ่มต้น (starter ผู้จัดใช้ 0.85–1.30)


def load_env():
    env = {}
    for line in (STARTER / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


class Api:
    def __init__(self, url, key):
        self.url, self.h = url.rstrip("/"), {"Authorization": f"Bearer {key}"}
        self.last = 0.0

    def call(self, method, path, **kw):
        """คืน Response หรือ None ถ้าต่อไม่ได้ทั้ง 4 ครั้ง (ผู้เรียกต้องเช็ก None)"""
        r = None
        for attempt in range(4):
            wait = 0.25 - (time.time() - self.last)         # ≤ 4 ครั้ง/วินาที (ลิมิต 5)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                r = requests.request(method, self.url + path, headers=self.h, timeout=10, **kw)
            except requests.RequestException as e:
                print("  เน็ต/เซิร์ฟเวอร์มีปัญหา:", type(e).__name__)
                time.sleep(2 + attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(float(r.headers.get("Retry-After", 1 + attempt)))
                continue
            return r
        return r


def code(r):
    """รหัสผลลัพธ์แบบไม่ล้มเมื่อ r เป็น None"""
    return r.status_code if r is not None else "ต่อไม่ได้"


# ---------- สูตร TV จาก /v1/calendar → rules (เหมือน starter/appraisal.py) ----------
def tv(rules, s):
    d, m = s["defect_pct"], s["moisture_pct"]
    step = next((x for x in rules["defect_steps"] if d <= x["max_defect_pct"]), rules["defect_steps"][-1])
    g = (1 - d / 100) * step["step"]
    mo = rules["moisture"]
    if m <= mo["ref"]:
        mf = 1.0
    elif m <= mo["hard_limit"]:
        mf = (1 - m / 100) / (1 - mo["ref"] / 100) - mo["penalty_per_pp"] * (m - mo["ref"])
    else:
        mf = mo["hard_factor"]
    f = {int(k): v for k, v in rules["screen_factors"].items()}
    sf = f[min(max(int(s["screen"]), min(f)), max(f))]
    return rules["p0"] * g * mf * sf, step["grade"]


def spec_ok(s, spec):
    return (s["defect_pct"] <= spec["max_defect_pct"] and s["moisture_pct"] <= spec["max_moisture_pct"]
            and (spec["min_screen"] is None or s["screen"] >= spec["min_screen"]))


# ---------- ความรู้เรื่องเพดาน (จากทุกเกมที่เก็บมา) ----------
def load_history():
    rows = []
    p = DATA / "offers.jsonl"
    if p.exists():
        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return rows


def bracket(rows, buyer):
    acc = [r["ratio"] for r in rows if r["buyer"] == buyer and r["filled_kg"] > 0]
    lim = [r["ratio"] for r in rows if r["buyer"] == buyer and r["status"] == "ABOVE_LIMIT"]
    lo = max(acc) if acc else LO0
    hi = min(lim) if lim else HI0
    return lo, hi, len(acc), len(lim)


def probe_markup(rows, buyer, rng):
    lo, hi, na, nl = bracket(rows, buyer)
    if hi <= lo + 0.02:                                     # ช่วงแคบแล้ว (หรือขัดกัน) → สุ่มรอบๆ เพื่อดูการเปลี่ยนแปลง
        mid = (lo + hi) / 2
        return round(min(HI0, max(LO0, mid + rng.uniform(-0.04, 0.04))), 3)
    return round((lo + hi) / 2 + rng.uniform(-0.01, 0.01), 3)


# ---------- ตัวกันพลาด ----------
def guard(api, args):
    now = datetime.now().strftime("%H:%M")
    if args.blackout_from <= now < args.blackout_to:
        return f"อยู่ในช่วงห้าม {args.blackout_from}–{args.blackout_to} (รอบเก็บคะแนน)"
    if now >= args.until:
        return f"ถึงเวลาหยุด {args.until}"
    v = api.call("GET", "/v1/version")
    if v is None or v.status_code != 200 or v.json().get("mode") != "sandbox":
        return f"server ไม่ใช่ sandbox ({None if v is None else v.text[:80]})"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="13:55")
    ap.add_argument("--blackout-from", default="99:99")   # ปิดไว้ (ทีมแข่ง 14:00 ใช้ --until แทน)
    ap.add_argument("--blackout-to", default="99:99")
    ap.add_argument("--no-reset", action="store_true", help="ไม่กดเริ่มเกมใหม่เองเมื่อเกมจบ")
    args = ap.parse_args()
    env = load_env()
    if not env.get("TEAM_KEY"):
        sys.exit("ยังไม่ได้ใส่ TEAM_KEY ใน starter\\.env (key ตลาดฝึก)")
    api = Api(env["MARKET_URL"], env["TEAM_KEY"])
    DATA.mkdir(exist_ok=True)
    rng = random.Random()
    rules, game, acted, sent, tvs, games = None, None, set(), {}, {}, 0
    logged = set()                                          # round_id ที่บันทึกผลตลาดแล้ว
    print(f"เริ่ม {datetime.now():%H:%M:%S} · ตลาด {env['MARKET_URL']} · หยุด {args.until}")
    while True:
        why = guard(api, args)
        if why:
            print("หยุด:", why)
            break
        st = api.call("GET", "/v1/state")
        if st is None:                                      # เน็ตหลุดหลายครั้งติดกัน → รอแล้วลองใหม่ ไม่ล้ม
            time.sleep(5)
            continue
        if st.status_code != 200:
            print("อ่าน state ไม่ได้:", st.status_code, st.text[:120])
            if st.status_code == 401:
                break
            time.sleep(3)
            continue
        st = st.json()
        if st.get("market") != "sandbox":
            print("หยุด: state.market ไม่ใช่ sandbox"); break
        key = tuple(sorted((l["lot_id"], json.dumps(l["sample"], sort_keys=True)) for l in st["lots"]))
        if key != game:                                     # เกมใหม่
            cal = api.call("GET", "/v1/calendar")
            if cal is None or cal.status_code != 200:
                time.sleep(3)
                continue
            game, acted, sent = key, set(), {}
            rules = cal.json()["rules"]
            tvs = {l["lot_id"]: tv(rules, l["sample"]) for l in st["lots"]}
            games += 1
            log_market({"kind": "game", "game": games, "lots": st["lots"],
                        "tv": {k: round(v[0], 3) for k, v in tvs.items()},
                        "grade": {k: v[1] for k, v in tvs.items()}, "rules": rules,
                        "calendar": {k: v for k, v in cal.json().items() if k != "rules"}})
            print(f"\n=== เกม {games} · ล็อต:", {k: round(v[0], 2) for k, v in tvs.items()})
        phase = st["phase"]

        if phase == "APPRAISAL" and not st["appraisal_submitted"]:
            items = [{"lot_id": k, "est_value_per_kg": round(v[0], 2), "grade": v[1]} for k, v in tvs.items()]
            r = api.call("POST", "/v1/appraisals", json={"items": items})
            print("  ส่งผลประเมิน:", code(r))

        elif phase == "ROUND_OPEN" and not st["paused"] and st["round"]["round_id"] not in acted:
            rid = st["round"]["round_id"]
            acted.add(rid)
            record(st.get("last_results"), sent, st)
            market_results(st.get("last_results"), logged, games)
            log_market({"kind": "round", "game": games, "round": st["round"], "rfqs": st["rfqs"],
                        "capacity_left_kg": st.get("capacity_left_kg"),
                        "lots_kg": {l["lot_id"]: l["kg_available"] for l in st["lots"]}})
            rows = load_history()
            cap = st["capacity_left_kg"] if st["capacity_left_kg"] is not None else 10 ** 9
            avail = {l["lot_id"]: l["kg_available"] for l in st["lots"]}
            offers = []
            rfqs = st["rfqs"][:]
            rng.shuffle(rfqs)
            for q in rfqs:                                  # 1 กระสอบต่อ RFQ ต่อรอบ = จุดทดลอง 1 จุด
                lots = [l for l in st["lots"] if avail[l["lot_id"]] >= BAG and spec_ok(l["sample"], q["spec"])]
                if not lots or cap < BAG:
                    continue
                lot = rng.choice(lots)
                m = probe_markup(rows, q["buyer"], rng)
                offers.append({"rfq_id": q["rfq_id"], "lot_id": lot["lot_id"], "kg": BAG,
                               "price_per_kg": round(m * tvs[lot["lot_id"]][0], 2)})
                sent[(rid, q["rfq_id"], lot["lot_id"])] = {"buyer": q["buyer"], "type": q["buyer_type"], "markup": m,
                                                           "tv": tvs[lot["lot_id"]][0], "round": rid,
                                                           "calendar": st["round"].get("calendar")}
                avail[lot["lot_id"]] -= BAG
                cap -= BAG
            if offers:
                r = api.call("POST", "/v1/offers:batch", json={"offers": offers, "replace_existing": True})
                print(f"  {rid}: ส่ง {len(offers)} ซอง →", code(r),
                      "" if r is not None and r.status_code < 300 else (r.text[:160] if r is not None else ""))

        elif phase == "CLOSED":
            record(st.get("last_results"), sent, st)
            market_results(st.get("last_results"), logged, games)
            rv = api.call("GET", "/v1/sandbox/reveal")
            if rv is not None and rv.status_code == 200:
                (DATA / f"reveal-{datetime.now():%H%M%S}.json").write_text(rv.text, encoding="utf-8")
                log_market({"kind": "reveal", "game": games, "data": rv.json()})
                print("  เกมจบ · บันทึกเฉลยแล้ว")
            if args.no_reset:
                print("หยุด: เกมจบ (--no-reset)"); break
            r = api.call("POST", "/v1/sandbox/reset")
            print("  เริ่มเกมใหม่:", code(r))
            game = None
            time.sleep(3)
            continue

        left = st.get("seconds_left") or 3
        time.sleep(min(3.0, max(0.5, left + 0.2)))
    print(f"จบ {datetime.now():%H:%M:%S} · เล่น {games} เกม · ข้อมูลอยู่ใน {DATA}")


def log_market(row):
    """เขียนข้อมูลตลาด 1 แถวลง market.jsonl (ไม่มี key ในข้อมูลนี้)"""
    row = {"time": datetime.now().isoformat(timespec="seconds"), **row}
    with open(DATA / "market.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def market_results(results, logged, games):
    """ผลรอบที่ปิดแล้ว (ภาพรวมตลาดของทุก RFQ + ผลซองเรา) · บันทึกครั้งเดียวต่อรอบ"""
    if not results or not results.get("round_id"):
        return
    k = (games, results["round_id"])
    if k in logged:
        return
    logged.add(k)
    log_market({"kind": "results", "game": games, "round_id": results["round_id"], "data": results})
    for x in results.get("market_summary", []):
        print("    ตลาด", str(x.get("rfq_id"))[:14], {kk: v for kk, v in x.items() if kk != "rfq_id"})


def record(results, sent, st):
    """เขียนผลของซองที่เราส่ง (ครั้งเดียวต่อซอง) ลง offers.jsonl พร้อมภาพรวมตลาดของ RFQ นั้น"""
    if not results or not results.get("round_id"):
        return
    rid = results["round_id"]
    summ = {x["rfq_id"]: x for x in results.get("market_summary", [])}
    with open(DATA / "offers.jsonl", "a", encoding="utf-8") as f:
        for o in results.get("my_offers", []):
            k = (rid, o["rfq_id"], o["lot_id"])
            meta = sent.pop(k, None)
            if meta is None:
                continue
            row = {**meta, "rfq_id": o["rfq_id"], "lot_id": o["lot_id"], "price": o["price_per_kg"],
                   "ratio": round(o["price_per_kg"] / meta["tv"], 4), "status": o["status"],
                   "filled_kg": o.get("filled_kg", 0), "market": summ.get(o["rfq_id"]),
                   "time": datetime.now().isoformat(timespec="seconds")}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"    {row['buyer'][:16]:<16} ×{row['ratio']:.3f} → {row['status']}")


if __name__ == "__main__":
    main()

"""สถิติตลาดฝึก (ชุด AGENT_TAG เดียว) · ต่อเกม / ต่อรอบ / แนวโน้มตามลำดับเกม
python sandbox_stats.py m3_100      (รันจากที่ไหนก็ได้ · อ่าน data/sandbox_agent/logs/runs/*-<tag>.jsonl)"""
import collections
import glob
import json
import math
import os
import statistics as st
import sys

H = os.path.dirname(os.path.abspath(__file__))
TAG = sys.argv[1] if len(sys.argv) > 1 else "m3_100"
files = sorted(glob.glob(os.path.join(H, "..", "data", "sandbox_agent", "logs", "runs", f"decisions-*-{TAG}.jsonl")))
games, cur = [], None
for f in files:
    for line in open(f, encoding="utf-8"):
        e = json.loads(line)
        ev = e["event"]
        if ev == "new_game":
            cur = {"rounds": collections.OrderedDict(), "closed": None}
        elif cur is None:
            continue
        elif ev == "round_results":
            cur["rounds"].setdefault(e["round"], e["data"])
        elif ev == "market_closed":
            cur["closed"] = e["standings"]
        elif ev == "reveal" and e["data"].get("score"):
            cur["reveal"] = e["data"]
            games.append(cur)
            cur = None


def mean(x):
    x = [v for v in x if v is not None]
    return st.mean(x) if x else float("nan")


def se(x):
    return st.stdev(x) / math.sqrt(len(x)) if len(x) > 1 else 0.0


rows = []
per_round = collections.defaultdict(lambda: collections.defaultdict(list))
status = collections.Counter()
for g in games:
    s = g["reveal"]["score"]
    tv = {l["lot_id"]: l["true_value_per_kg"] for l in g["reveal"]["lots"]}
    grades = collections.Counter(l["true_grade"] for l in g["reveal"]["lots"])
    gr_ok = sum(l["true_grade"] == l["your_estimate"]["grade"] for l in g["reveal"]["lots"]) / len(g["reveal"]["lots"])
    real = [(r, d) for r, d in g["rounds"].items() if d.get("kind") == "real"]
    for r, d in g["rounds"].items():
        mine = d.get("my_offers", [])
        sent = sum(o["kg"] for o in mine)
        filled = sum(o.get("filled_kg", 0) for o in mine)
        for o in mine:
            status[o["status"]] += 1
        ratio = [o["price_per_kg"] / tv[o["lot_id"]] for o in mine if o.get("filled_kg") and o["lot_id"] in tv]
        ms = d.get("market_summary", [])
        want = sum(m["wanted_kg"] for m in ms)
        got = sum(m["bought_kg"] for m in ms)
        offers = sum(m.get("offers") or 0 for m in ms)
        pr = per_round[r]
        pr["fill_mine"].append(filled / sent if sent else None)
        pr["ratio"].append(mean(ratio) if ratio else None)
        pr["mkt_fill"].append(got / want if want else None)
        pr["offers_per_rfq"].append(offers / len(ms) if ms else None)
        pr["kg_sold"].append(filled)
    r1 = g["rounds"].get("R1", {}).get("my_offers", [])
    c = g["closed"] or {}
    rows.append({"pr": s["pr"], "rank": s["rank"], "ap": s["appraisal_score"], "mape": s["mape"], "total": s["total"],
                 "sold": c.get("kg_sold", 0) / max(c.get("kg_total", 1), 1), "grade_ok": gr_ok,
                 "r1": (sum(o.get("filled_kg", 0) > 0 for o in r1) / len(r1)) if r1 else None,
                 "spec_lots": grades.get("SPECIALTY", 0) + grades.get("PREMIUM", 0), "n_real": len(real)})

n = len(rows)
print(f"ชุด {TAG} · เกมที่จบ {n} · ไฟล์ {len(files)}")
if not n:
    sys.exit()
P = [r["pr"] for r in rows]
print("\n== ภาพรวม ==")
print(f"PR เฉลี่ย {mean(P):.4f} ±{se(P):.4f} · มัธยฐาน {st.median(P):.4f} · ต่ำสุด {min(P):.4f} · สูงสุด {max(P):.4f} · SD {st.pstdev(P):.4f}")
print(f"อันดับเฉลี่ย {mean([r['rank'] for r in rows]):.2f} · ที่ 1 {sum(r['rank'] == 1 for r in rows) / n:.0%} · "
      f"Top3 {sum(r['rank'] <= 3 for r in rows) / n:.0%} · Top5 {sum(r['rank'] <= 5 for r in rows) / n:.0%}")
print(f"คะแนนประเมินมูลค่า {mean([r['ap'] for r in rows]):.2f}/20 ±{se([r['ap'] for r in rows]):.2f} · MAPE เฉลี่ย {mean([r['mape'] for r in rows]):.2%} · "
      f"เกรดถูก {mean([r['grade_ok'] for r in rows]):.0%} · เต็ม 20 ใน {sum(r['ap'] >= 19.95 for r in rows)}/{n} เกม")
print(f"คะแนนรวม (เกมฝึก) {mean([r['total'] for r in rows]):.2f} · ขายหมด {sum(r['sold'] >= 0.999 for r in rows) / n:.0%} ของเกม · ขายได้เฉลี่ย {mean([r['sold'] for r in rows]):.1%} ของ kg")
print(f"R1 ซองชนะ {mean([r['r1'] for r in rows]):.0%} · สถานะซองทั้งหมด {dict(status)}")
qs = sorted(P)
print("การกระจาย PR: " + " · ".join(f"P{p} {qs[min(n - 1, int(p / 100 * n))]:.4f}" for p in (10, 25, 50, 75, 90)))

print("\n== รายรอบ (เฉลี่ยทุกเกม) ==")
print(f"{'รอบ':5} {'เกม':>4} {'ขายkg':>7} {'ซองเรา fill':>11} {'ราคา/TVจริง':>12} {'ตลาด fill':>9} {'ซอง/RFQ':>8}")
for r, d in per_round.items():
    print(f"{r:5} {len(d['kg_sold']):4} {mean(d['kg_sold']):7.0f} {mean(d['fill_mine']):11.0%} {mean(d['ratio']):12.4f} "
          f"{mean(d['mkt_fill']):9.0%} {mean(d['offers_per_rfq']):8.1f}")

print("\n== แนวโน้มตามลำดับเกม (ช่วงละ 20 เกม) ==")
print(f"{'เกม':9} {'PR':>7} {'±SE':>6} {'อันดับ':>6} {'ที่1':>5} {'ประเมิน':>7} {'ขาย%':>5}")
for i in range(0, n, 20):
    b = rows[i:i + 20]
    p = [x["pr"] for x in b]
    print(f"{i + 1:3}-{i + len(b):<5} {mean(p):7.4f} {se(p):6.4f} {mean([x['rank'] for x in b]):6.2f} "
          f"{sum(x['rank'] == 1 for x in b) / len(b):5.0%} {mean([x['ap'] for x in b]):7.2f} {mean([x['sold'] for x in b]):5.0%}")
if n >= 10:
    xs = list(range(n))
    mx, my = mean(xs), mean(P)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, P)) / sum((x - mx) ** 2 for x in xs)
    print(f"ความชัน PR ต่อเกม {slope:+.6f} (×100 เกม = {slope * 100:+.4f})")

print("\n== PR ตามจำนวนล็อตเกรดสูง (SPECIALTY/PREMIUM) ==")
by = collections.defaultdict(list)
for r in rows:
    by[r["spec_lots"]].append(r["pr"])
for k in sorted(by):
    print(f"{k} ล็อต: {len(by[k]):3} เกม · PR {mean(by[k]):.4f} · อันดับ {mean([r['rank'] for r in rows if r['spec_lots'] == k]):.2f}")

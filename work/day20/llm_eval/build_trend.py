"""ชุดข้อมูลแนวโน้มราคาข้ามรอบ จาก log ตลาดแข่งด่าน 2 จริง → trend_cases.jsonl
ต่อ (ผู้ซื้อ, รอบ t): ประวัติราคาตัดทุกรอบก่อนหน้า (รวม P1) · เฉลย = ราคาตัดรอบ t+1 ของผู้ซื้อรายเดียวกัน
ราคาตัดต่อใบ = price_max ÷ TV สูงสุดของล็อตที่ผ่านสเปกใบนั้น (ขอบล่าง เหมือน market_model) · ต่อรอบ = ต่ำสุด/มัธยฐาน/สูงสุด
baseline: (a) คงที่ = มัธยฐานรอบล่าสุด (b) ตามแนวโน้ม = ล่าสุด + ความชันเฉลี่ย 2 รอบ (c) market_model vol = min(ล่าสุด, เฉลี่ย) − 1.5×sd
รันในโฟลเดอร์ work/day18/agent"""
import json
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())
from inventory import spec_ok  # noqa: E402

HERE = Path(__file__).parent
ev = [json.loads(x) for x in open("logs/decisions.jsonl", encoding="utf-8")]
ng = [e for e in ev if e["event"] == "new_game"][0]
samples = ng["samples"]
tv = next(e["tv"] for e in ev if e["event"] == "appraisal_sent")
spec, order, res = {}, [], {}
for e in ev:
    if e["event"] == "round_open":
        rid = e["round"]["round_id"]
        for r in e["rfqs"]:
            spec[r["rfq_id"]] = r["spec"]
        if rid not in order:
            order.append(rid)
    elif e["event"] == "round_results" and e["round"] not in res:
        res[e["round"]] = e["data"]
series = {}      # buyer -> [(round, low, median, high, fill, offers_per_bag, buyer_type)]
for rid in order:
    rows = res.get(rid, {}).get("market_summary", [])
    by = {}
    for row in rows:
        el = [tv[l] for l in tv if spec_ok(samples[l], spec.get(row["rfq_id"], {}))]
        if not el or not row.get("price_max") or not row.get("bought_kg"):
            continue
        by.setdefault(row["buyer"], {"r": [], "w": 0, "b": 0, "o": 0, "t": row.get("buyer_type")})
        d = by[row["buyer"]]
        d["r"].append(row["price_max"] / max(el))
        d["w"] += row["wanted_kg"]
        d["b"] += row["bought_kg"]
        d["o"] += row.get("offers") or 0
    for b, d in by.items():
        v = sorted(d["r"])
        series.setdefault(b, []).append({"round": rid, "low": round(v[0], 4), "median": round(v[len(v) // 2], 4),
                                         "high": round(v[-1], 4), "fill": round(d["b"] / max(d["w"], 1), 2),
                                         "offers_per_bag": round(d["o"] / max(d["w"] / 60, 1), 2), "type": d["t"]})
cases = []
for b, s in series.items():
    for i in range(1, len(s) - 1):          # มีประวัติ ≥ 2 รอบ และมีรอบถัดไปเป็นเฉลย
        hist, nxt = s[:i + 1], s[i + 1]
        meds = [h["median"] for h in hist]
        last = meds[-1]
        slope = (meds[-1] - meds[-3]) / 2 if len(meds) >= 3 else meds[-1] - meds[-2]
        m3 = meds[-3:]
        mean = sum(m3) / len(m3)
        sd = (sum((x - mean) ** 2 for x in m3) / len(m3)) ** 0.5 if len(m3) > 1 else 0.02
        within = hist[-1]["median"] - hist[-1]["low"]
        vol = min(last, mean) - 1.5 * max(sd, within / 2) - 0.005
        d = nxt["median"] - last
        cases.append({"id": f"{hist[-1]['round']}-{b[:10]}", "buyer": b, "buyer_type": hist[-1]["type"], "history": hist,
                      "next": nxt, "gold_dir": "up" if d > 0.005 else ("down" if d < -0.005 else "flat"),
                      "gold_next_median": nxt["median"], "gold_next_low": nxt["low"],
                      "base_flat": last, "base_trend": round(last + slope, 4), "base_vol": round(vol, 4)})
with open(HERE / "trend_cases.jsonl", "w", encoding="utf-8") as f:
    for c in cases:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
print(f"{len(cases)} จุด · ผู้ซื้อ {len(series)} ราย · เฉลยทิศ:", {k: sum(c["gold_dir"] == k for c in cases) for k in ("up", "flat", "down")})
for name in ("base_flat", "base_trend", "base_vol"):
    err = [abs(c[name] - c["gold_next_median"]) for c in cases]
    safe = sum(c[name] <= c["gold_next_low"] for c in cases)   # ราคาที่ทำนาย ≤ ราคาตัดต่ำสุดรอบหน้า = ตั้งราคานี้แล้วชนะทุกใบ
    print(f"{name:10} คลาดจากมัธยฐานรอบหน้า เฉลี่ย {st.mean(err):.4f} · ตั้งราคานี้แล้วชนะทุกใบ {safe}/{len(cases)} · "
          f"เว้นจากราคาตัดต่ำสุดเฉลี่ย {st.mean([c['gold_next_low'] - c[name] for c in cases if c[name] <= c['gold_next_low']] or [0]):.4f}")

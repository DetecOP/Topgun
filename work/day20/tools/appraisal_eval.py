"""วัดคะแนนประเมินมูลค่า (20 × (1 − MAPE/10%) ตัดที่ 0 · ต่อเกม) บนเกมตลาดฝึกที่ prior ปัจจุบันไม่เคยเห็น (หลัง 01:33 19 พ.ย.)
เทียบ: sample · hybrid (HYBRID_MAX ต่างๆ) · bayes · เพดาน "oracle" (รู้ค่าจริง defect/ชื้น ไม่รู้ screen ฯลฯ)
รันในโฟลเดอร์ work/day20/agent"""
import json
import math
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())
import appraisal  # noqa: E402

HERE = Path(__file__).parent
RULES = json.loads((HERE.parent / "data" / "sandbox_rules.json").read_text(encoding="utf-8"))
SINCE = sys.argv[1] if len(sys.argv) > 1 else "2026-11-19T01:34"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 600

games = []
for f in sorted((HERE.parent / "data" / "sandbox_agent" / "logs" / "runs").glob("*.jsonl")):
    for line in open(f, encoding="utf-8"):
        if '"reveal"' not in line[:80]:
            continue
        e = json.loads(line)
        if e["time"] < SINCE:
            continue
        lots = e["data"]["lots"]
        if any(l["sample"] != l["true"] for l in lots):
            games.append(lots)
OFFSET = int(sys.argv[3]) if len(sys.argv) > 3 else 0
games = games[OFFSET:OFFSET + LIMIT]
print(f"เกมที่ใช้วัด {len(games)} (หลัง {SINCE})")


def score(errs):
    return max(0.0, 20 * (1 - (sum(errs) / len(errs)) / 0.10))


def run(fn):
    sc = [score([abs(fn(l) - l["true_value_per_kg"]) / l["true_value_per_kg"] for l in g]) for g in games]
    lot_err = [abs(fn(l) - l["true_value_per_kg"]) / l["true_value_per_kg"] for g in games for l in g]
    return st.mean(sc), st.stdev(sc) / math.sqrt(len(sc)), sum(s == 0 for s in sc), st.mean(lot_err), sc


res = {}
res["sample"] = run(lambda l: appraisal.true_value(RULES, l["sample"]))
if os.environ.get("SKIP_BAYES") != "1":
    res["bayes"] = run(lambda l: appraisal.estimate_one(RULES, l["sample"], "bayes"))
for hm in [float(x) for x in os.environ.get("HMS", "0.04,0.08,0.12,0.2").split(",")]:
    appraisal.HYBRID_MAX = hm
    res[f"hybrid {hm}"] = run(lambda l: appraisal.estimate_one(RULES, l["sample"], "hybrid"))
appraisal.HYBRID_MAX = 0.08
# เพดาน: ถ้ารู้ defect/ชื้นจริง แต่ screen ยังเป็นค่าตัวอย่าง (แยกว่าความคลาดมาจากตรงไหน)
res["oracle: รู้ defect+ชื้นจริง"] = run(lambda l: appraisal.true_value(RULES, {**l["sample"], "defect_pct": l["true"]["defect_pct"],
                                                                              "moisture_pct": l["true"]["moisture_pct"]}))
res["oracle: รู้ screen จริง"] = run(lambda l: appraisal.true_value(RULES, {**l["sample"], "screen": l["true"]["screen"]}))
base = res["hybrid 0.08"][4]
print(f"{'วิธี':32} {'คะแนน/20':>9} {'±SE':>6} {'เกมได้0':>7} {'คลาดต่อล็อต':>11} {'ต่างจาก hybrid 0.08':>20}")
for k, (m, se, z, le, sc) in res.items():
    d = [a - b for a, b in zip(sc, base)]
    print(f"{k:32} {m:9.2f} {se:6.2f} {z:7d} {le:10.2%} {st.mean(d):+10.3f} ± {st.stdev(d) / math.sqrt(len(d)):.3f}")

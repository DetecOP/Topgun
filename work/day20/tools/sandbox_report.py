"""สรุปผลตลาดฝึกแยกตามชุด (AGENT_TAG ในชื่อไฟล์ log) · python sandbox_report.py [เวลาเริ่ม HHMMSS]"""
import collections
import glob
import json
import math
import os
import statistics as st
import sys

H = os.path.dirname(os.path.abspath(__file__))
since = sys.argv[1] if len(sys.argv) > 1 else "000000"
by = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(H, "..", "data", "sandbox_agent", "logs", "runs", "decisions-*.jsonl"))):
    parts = os.path.basename(f)[:-6].split("-")      # decisions-YYYYMMDD-HHMMSS-tag
    if parts[1] + parts[2] < "20261119" + since:
        continue
    tag = "-".join(parts[3:])
    r1 = [0, 0]
    rfq = {}
    for line in open(f, encoding="utf-8"):
        e = json.loads(line)
        if e["event"] == "new_game":
            r1 = [0, 0]
        elif e["event"] == "round_results" and e["round"] == "R1":
            for o in e["data"].get("my_offers", []):
                r1[0] += 1
                r1[1] += o.get("filled_kg", 0) > 0
        elif e["event"] == "market_closed":
            sold = e["standings"]["kg_sold"] / max(e["standings"]["kg_total"], 1)
        elif e["event"] == "reveal" and e["data"].get("score"):
            s = e["data"]["score"]
            by[tag].append({"pr": s["pr"], "rank": s["rank"], "ap": s["appraisal_score"], "sold": sold,
                            "r1": r1[1] / r1[0] if r1[0] else None})
print(f"{'ชุด':14} {'เกม':>4} {'PR':>7} {'±SE':>6} {'อันดับ':>6} {'ที่1':>5} {'Top3':>5} {'ขาย%':>5} {'R1ชนะ':>6}")
for tag, g in sorted(by.items()):
    pr = [x["pr"] for x in g]
    se = st.stdev(pr) / math.sqrt(len(pr)) if len(pr) > 1 else 0
    r1 = [x["r1"] for x in g if x["r1"] is not None]
    print(f"{tag:14} {len(g):4} {st.mean(pr):7.4f} {se:6.4f} {st.mean(x['rank'] for x in g):6.1f} "
          f"{sum(x['rank'] == 1 for x in g) / len(g):5.0%} {sum(x['rank'] <= 3 for x in g) / len(g):5.0%} "
          f"{st.mean(x['sold'] for x in g):5.0%} {st.mean(r1) if r1 else 0:6.0%}")

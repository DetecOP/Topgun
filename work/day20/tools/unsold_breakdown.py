"""ขั้น 3.0 (สเปก B pr_plan.md หัวข้อ 10): แตกสาเหตุของค้างตอนจบในตลาดจำลองด่าน 3 · python unsold_breakdown.py [จำนวนเกม]
ต่อล็อตที่ค้าง ดูทุกรอบจริงที่ยังมีของ: ถูกเสนอไหม · สถานะ · ratio เทียบราคาตัด · ที่พื้น · ถ้าไม่ถูกเสนอเพราะอะไร · pressure_mode"""
import collections
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.getcwd())
os.environ.update(MOCK_STYLE="real", MOCK_STAGE="3", USE_LLM="0")
import main as agent_main  # noqa: E402
import mock_market as mm  # noqa: E402
from inventory import classify, spec_ok  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
agent_main.LOGS = Path(tempfile.mkdtemp(prefix="unsold-"))
agent_main.time.sleep = lambda s: None
cat_rounds = collections.Counter()      # (สาเหตุ) -> จำนวน "ล็อต-รอบ" ถ่วงด้วยกระสอบค้างตอนจบ
group_bags = collections.Counter()
last_status = collections.Counter()
late = collections.Counter()
gaps = collections.defaultdict(list)
games_left = 0
total_left = 0
pos = 0
for s in range(70001, 70001 + N):
    m = mm.FakeMarket(s, 0.3)
    with contextlib.redirect_stdout(io.StringIO()):
        agent_main.play(m, None, forever=False)
    log = agent_main.LOGS / "decisions.jsonl"
    lines = open(log, encoding="utf-8").read().splitlines()[pos:]
    pos += len(lines)
    ev = [json.loads(x) for x in lines]
    left = {l["lot_id"]: l["kg_remaining"] // 60 for l in m.lots if l["kg_remaining"] > 0}
    if not left:
        continue
    games_left += 1
    samples = {l["lot_id"]: l["sample"] for l in m.lots}
    inv = classify(m.rules, m.lots, [], None)
    opens = {e["round"]["round_id"]: e for e in ev if e["event"] == "round_open" and e["round"].get("kind") == "real"}
    sents = {e["round"]: e for e in ev if e["event"] == "offers_sent"}
    res = {e["round"]: e["data"] for e in ev if e["event"] == "round_results"}
    est = next(e["tv"] for e in ev if e["event"] == "appraisal_sent")
    for lid, bags in left.items():
        total_left += bags
        types = inv[lid]["types"]
        g = "ไม่มีกลุ่มผ่าน" if not types else ("Instant อย่างเดียว" if types == ["INSTANT"] else "หลายกลุ่ม/Specialty")
        group_bags[g] += bags
        if os.environ.get("ONLY_MULTI") and g != "หลายกลุ่ม/Specialty":
            continue
        last = None
        for rid, op in opens.items():
            n = op["round"]["number"]
            if op.get("lots_kg", {}).get(lid, 1) <= 0:
                continue
            se = sents.get(rid, {})
            mine = [o for o in se.get("offers", []) if o["lot_id"] == lid]
            pm = (se.get("meta") or {}).get("pressure_mode", "?")
            if mine:
                st = {(o["rfq_id"], o["lot_id"]): o["status"] for o in res.get(rid, {}).get("my_offers", [])}
                for o in mine:
                    r = o["price_per_kg"] / est[lid]
                    status = st.get((o["rfq_id"], lid), "?")
                    floor = r <= 0.826
                    rf = next((x for x in op["rfqs"] if x["rfq_id"] == o["rfq_id"]), None)
                    row = next((x for x in res.get(rid, {}).get("market_summary", []) if x["rfq_id"] == o["rfq_id"]), None)
                    el = [est[i] for i in est if rf and spec_ok(samples[i], rf["spec"])]
                    if row and row.get("price_max") and el:
                        gaps[(n >= 13, status)].append(r - row["price_max"] / max(el))
                    key = f"เสนอแล้ว {status}" + (" ·ที่พื้น" if floor else "")
                    cat_rounds[(key, pm)] += bags
                    last = (n, status, floor)
            else:
                cap_full = se.get("kg", 0) >= op.get("capacity_left_kg", 0) > 0
                has_rfq = any(spec_ok(samples[lid], r["spec"]) for r in op["rfqs"])
                why = "capacity เต็ม" if cap_full else ("ไม่มี RFQ ที่ล็อตผ่าน" if not has_rfq else "ไม่ถูกเลือก (คู่รอง/SPREAD/pace)")
                cat_rounds[(why, pm)] += bags
        if last:
            last_status[f"เสนอครั้งสุดท้าย R{last[0]} {last[1]}" if last[0] >= 13 else f"เสนอครั้งสุดท้ายก่อน R13 ({last[1]})"] += bags
            late["ที่พื้น" if last[2] else "เหนือพื้น"] += bags
        else:
            last_status["ไม่เคยถูกเสนอเลย"] += bags

print(f"{N} เกม · เกมมีของค้าง {games_left} · กระสอบค้างรวม {total_left} (เฉลี่ย {total_left / N:.2f}/เกม)")
print("\nกลุ่มล็อตที่ค้าง (กระสอบ):", dict(group_bags))
print("\nครั้งสุดท้ายที่เสนอ (กระสอบ):", dict(last_status.most_common()))
print("ราคาครั้งสุดท้าย:", dict(late))
tot = sum(cat_rounds.values())
by = collections.Counter()
for (k, pm), v in cat_rounds.items():
    by[k] += v
print("\nสาเหตุต่อรอบที่ล็อตค้างยังมีของ (ถ่วงด้วยกระสอบค้าง):")
for k, v in by.most_common():
    pms = {pm: cat_rounds[(k, pm)] for (kk, pm) in cat_rounds if kk == k}
    print(f"  {k:38} {v / tot:6.1%}  pressure: " + ", ".join(f"{p} {c / v:.0%}" for p, c in sorted(pms.items(), key=lambda x: -x[1])))

import statistics as st
print("\nratio ที่ยื่น − ราคาตัด (ขอบล่าง) แยกช่วง/สถานะ:")
for (lt, stt), v in sorted(gaps.items()):
    print(f"  {'R13–15' if lt else 'R1–12'} {stt:12} n={len(v):4} เฉลี่ย {st.mean(v):+.3f} · มัธยฐาน {st.median(v):+.3f}")

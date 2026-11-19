"""G2 (สเปก B llm_behavior_test.md): ชุดข้อมูลสอบ LLM จาก log ตลาดแข่งด่าน 2 จริง → work/day20/llm_eval/cases.jsonl
จุดตัดสินใจ = (รอบ R1–R8, ประเภท C/I/S) · ข้อมูลเข้า = ข้อเท็จจริงที่ Python ตีความแล้ว (รูปแบบ B) ณ เปิดรอบ
ป้ายเฉลยมองย้อน = replay ด่าน 2 (ซองตรวจสเปก = ตก) ใช้ค่าตั้งของป้ายนั้นเฉพาะรอบนั้น → ป้ายที่ PR สูงสุด · ต่างจาก normal < 0.001 = normal
P1 ไม่มีในชุด (replay ไม่ตัดสินใจรอบซ้อม) · เทียบป้ายของ rule_advisor ไว้ด้วย
รันในโฟลเดอร์ work/day18/agent: python ../../day20/overnight/build_cases.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())
import rule_advisor  # noqa: E402
from inventory import spec_ok  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE.parent / "llm_eval"
OUT.mkdir(exist_ok=True)
REPLAY = HERE / "replay_label.py"
LABEL_ENV = {
    "normal": {},
    "undercut": lambda t: {f"MKT_K_{t}": "2.0"},
    "flood": lambda t: {f"SELL_SHIFT_{t}": "-0.03", "MKT_K": "2.0"},
    "shortage": lambda t: {"SHORT_CEIL": "1", "SHORT_FILL": "0.5"},
}


def replay_pr(rid: str, env: dict) -> float:
    e = {**os.environ, "PYTHONIOENCODING": "utf-8", "USE_LLM": "0", "LABEL_ROUND": rid, "LABEL_ENV": json.dumps(env)}
    out = subprocess.run([sys.executable, str(REPLAY)], env=e, capture_output=True, text=True, encoding="utf-8").stdout
    line = [x for x in out.splitlines() if "PR ≈" in x][-1]
    return float(line.split("PR ≈ ")[1].split()[0])


class Mem:
    def __init__(self, sent, rounds):
        self.sent, self.rounds = sent, rounds


ev = [json.loads(x) for x in open("logs/decisions.jsonl", encoding="utf-8")]
ng = [e for e in ev if e["event"] == "new_game"][0]
samples = ng["samples"]
opens, results, sent, order = {}, {}, {}, []
for e in ev:
    if e["event"] == "round_open":
        rid = e["round"]["round_id"]
        if rid not in opens:
            opens[rid] = e
            order.append(rid)
    elif e["event"] == "round_results" and e["round"] not in results:
        results[e["round"]] = e["data"]
types_of = {}
for rid, o in opens.items():
    for r in o["rfqs"]:
        types_of[r["rfq_id"]] = r["buyer_type"]
for rid, d in results.items():     # "sent" แบบที่ rule_advisor ใช้ (ประเภทผู้ซื้อของซองเรา)
    sent[rid] = [{"rfq_id": o["rfq_id"], "lot_id": o["lot_id"], "buyer_type": types_of.get(o["rfq_id"])} for o in d.get("my_offers", [])]
stock0 = {"LOT-T13-1": 9, "LOT-T13-2": 2, "LOT-T13-3": 9, "LOT-T13-4": 5}

base = {}
cases = []
for i, rid in enumerate(order):
    if rid == "P1":
        continue
    o = opens[rid]
    hist = [results[r] for r in order[:i] if r in results]
    lots = [{"lot_id": l, "sample": samples[l], "kg_available": (o.get("lots_kg") or {}).get(l, stock0[l] * 60)} for l in samples]
    state = {"round": o["round"], "lots": lots, "rfqs": o["rfqs"], "round_capacity_kg": o["round_capacity_kg"]}
    rl = rule_advisor.rule_labels(Mem(sent, hist), state, 8, o["round"].get("calendar", ""))
    if rid not in base:
        base[rid] = replay_pr(rid, {})
    for t in ("COMMERCIAL", "INSTANT", "SPECIALTY"):
        last = hist[-1] if hist else {}
        mine = [x for x in last.get("my_offers", []) if types_of.get(x["rfq_id"]) == t]
        fills = []
        for h in hist[-2:]:
            rows = [x for x in h.get("market_summary", []) if x.get("buyer_type") == t]
            w = sum(x["wanted_kg"] for x in rows)
            fills.append(round(sum(x["bought_kg"] for x in rows) / w, 2) if w else None)
        facts = {
            "round": rid, "rounds_total": 8, "buyer_type": t, "calendar": o["round"].get("calendar", ""),
            "we_offered_last_round": bool(mine),
            "we_lost_last_round_outbid": any(x["status"] == "OUTBID" for x in mine),
            "we_above_limit_last_round": any(x["status"] == "ABOVE_LIMIT" for x in mine),
            "we_sold_all_last_round": bool(mine) and all(x.get("filled_kg", 0) >= x.get("kg", 1) for x in mine),
            "buyer_fill_last_2_rounds": fills,
            "rfq_bags_this_round": sum(r["bags"] for r in o["rfqs"] if r["buyer_type"] == t),
            "we_have_lot_passing_spec": any(spec_ok(samples[l], r["spec"]) for l in samples for r in o["rfqs"] if r["buyer_type"] == t),
            "capacity_bags_per_round": o["round_capacity_kg"] // 60,
        }
        prs = {"normal": base[rid]}
        for lab in ("undercut", "flood", "shortage"):
            prs[lab] = replay_pr(rid, LABEL_ENV[lab](t))
        best = max(prs, key=prs.get)
        gold = best if prs[best] - prs["normal"] >= 0.001 else "normal"
        cases.append({"id": f"{rid}-{t[:4]}", "facts": facts, "rule_label": rl[t]["label"], "gold": gold,
                      "pr_by_label": {k: round(v, 4) for k, v in prs.items()}})
        print(cases[-1]["id"], "gold", gold, "rule", rl[t]["label"], prs, flush=True)

with open(OUT / "cases.jsonl", "w", encoding="utf-8") as f:
    for c in cases:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
agree = sum(c["rule_label"] == c["gold"] for c in cases)
print(f"\n{len(cases)} จุด · rule_advisor ตรงเฉลย {agree}/{len(cases)} · เฉลย:",
      {g: sum(c["gold"] == g for c in cases) for g in ("normal", "undercut", "flood", "shortage")})

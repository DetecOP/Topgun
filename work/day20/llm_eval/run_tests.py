"""ชุดทดสอบพฤติกรรม LLM ผู้จัด (สเปก B llm_behavior_test.md G3: T1 รูปแบบ · T2 เข้าใจสัญญาณ · T3 จำแนก + ผิดทิศ · T6 เวลา)
ใช้ gateway ช่วงฝึก (LLM_BASE_URL จาก .env ของ starter) · ไม่แตะตลาด · ≤ 19 คำขอ/นาที · ทีละคำขอ
python ../../day20/llm_eval/run_tests.py v1   (รันในโฟลเดอร์ work/day18/agent)"""
import json
import os
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, os.getcwd())
import main  # noqa: E402
from llm import LLM  # noqa: E402

os.environ.pop("AGENT_ENV", None)
main.load_env(main.HERE / ".env")
main.load_env(main.STARTER_ENV)
HERE = Path(__file__).parent
VER = sys.argv[1] if len(sys.argv) > 1 else "v1"
SYSTEM = (HERE / "prompts" / f"{VER}.txt").read_text(encoding="utf-8")
llm = LLM(os.environ["LLM_BASE_URL"], os.environ.get("LLM_MODEL", "event-llm"), os.environ["LLM_API_KEY"],
          timeout=40, thinking=False, max_tokens=200, temperature=0.0)
LABELS = ["normal", "undercut", "flood", "shortage", "festival_surge"]
SCHEMA = {"type": "object", "required": ["label", "reason"], "properties": {
    "label": {"type": "string", "enum": LABELS}, "reason": {"type": "string", "maxLength": 120}}}
if VER >= "v3":   # ตอบผลตรวจทีละข้อก่อนใส่ป้าย (structured)
    SCHEMA = {"type": "object", "required": ["check_flood", "check_undercut", "check_shortage", "check_festival", "label", "reason"],
              "properties": {"check_flood": {"type": "boolean"}, "check_undercut": {"type": "boolean"},
                             "check_shortage": {"type": "boolean"}, "check_festival": {"type": "boolean"},
                             "label": {"type": "string", "enum": LABELS}, "reason": {"type": "string", "maxLength": 120}}}
OUT = open(HERE / f"results_{VER}.jsonl", "w", encoding="utf-8")
lat = []
fails = 0


def ask(system, user, schema):
    global fails
    t = time.time()
    a = llm.ask_json(system, user, schema, timeout=40)
    dt = time.time() - t
    lat.append(dt)
    if not isinstance(a, dict):
        fails += 1
    OUT.write(json.dumps({"user": user[:400], "answer": a, "s": round(dt, 2), "err": llm.last_error}, ensure_ascii=False) + "\n")
    OUT.flush()
    time.sleep(max(0.0, 3.2 - dt))
    return a


def facts(**k):
    base = dict(round="R5", rounds_total=15, buyer_type="COMMERCIAL", calendar="normal", we_offered_last_round=True,
                we_lost_outbid_last_2_rounds=[False, False], we_above_limit_last_round=False, we_sold_all_last_round=True,
                buyer_fill_last_2_rounds=[1.0, 1.0], we_have_lot_passing_spec=True, unsold_bags=20,
                capacity_left_bags=50, specialty_demand_vs_early_avg=1.0)
    base.update(k)
    return base


def derived(f):
    """ข้อเท็จจริงที่ Python ตีความแล้ว (รูปแบบ B) · LLM ไม่ต้องเทียบตัวเลขเอง"""
    lost = f["we_lost_outbid_last_2_rounds"]
    fill = f["buyer_fill_last_2_rounds"]
    return {"buyer_type": f["buyer_type"], "round": f["round"], "calendar": f["calendar"],
            "unsold_bags_exceed_capacity_left": f["unsold_bags"] > f["capacity_left_bags"],
            "we_lost_outbid_both_last_2_rounds": all(lost),
            "we_lost_outbid_last_round": bool(lost[-1]),
            "we_above_limit_last_round": f["we_above_limit_last_round"],
            "we_sold_all_last_round": f["we_sold_all_last_round"],
            "buyer_bought_under_50pct_both_last_2_rounds": all(x < 0.5 for x in fill),
            "we_have_lot_passing_spec": f["we_have_lot_passing_spec"],
            "specialty_festival_demand_surge": f["buyer_type"] == "SPECIALTY" and f["calendar"] == "festival"
                                               and f["specialty_demand_vs_early_avg"] >= 1.5}


def user_for(f):
    if os.environ.get("FACTS", "B") == "raw":
        return "Facts:\n" + json.dumps(f, ensure_ascii=False) + "\nLabel this buyer type."
    return "Facts (computed by the program):\n" + json.dumps(derived(f), ensure_ascii=False) + "\nLabel this buyer type."


# T3: กรณีที่เฉลยชัดตามนิยาม (รวมกรณีหลอก เช่น ของขาดแต่เราแพ้ราคา = undercut)
T3 = [
    ("normal", facts()), ("normal", facts(round="R2")),
    ("normal", facts(buyer_type="INSTANT", buyer_fill_last_2_rounds=[0.9, 0.8])),
    ("undercut", facts(we_lost_outbid_last_2_rounds=[True, True], we_sold_all_last_round=False)),
    ("undercut", facts(buyer_type="INSTANT", we_lost_outbid_last_2_rounds=[True, True], we_sold_all_last_round=False)),
    ("undercut", facts(we_lost_outbid_last_2_rounds=[True, True], we_sold_all_last_round=False, buyer_fill_last_2_rounds=[0.4, 0.3])),
    ("undercut", facts(buyer_type="SPECIALTY", we_lost_outbid_last_2_rounds=[True, True], we_sold_all_last_round=False,
                       calendar="festival", specialty_demand_vs_early_avg=2.0)),
    ("flood", facts(unsold_bags=30, capacity_left_bags=20)),
    ("flood", facts(round="R13", unsold_bags=12, capacity_left_bags=10)),
    ("flood", facts(unsold_bags=25, capacity_left_bags=15, we_lost_outbid_last_2_rounds=[True, True], we_sold_all_last_round=False)),
    ("shortage", facts(buyer_fill_last_2_rounds=[0.4, 0.3])),
    ("shortage", facts(buyer_type="SPECIALTY", buyer_fill_last_2_rounds=[0.2, 0.25])),
    ("normal", facts(buyer_fill_last_2_rounds=[0.4, 0.9])),
    ("normal", facts(buyer_fill_last_2_rounds=[0.3, 0.2], we_have_lot_passing_spec=False)),
    ("normal", facts(we_lost_outbid_last_2_rounds=[False, True], we_sold_all_last_round=False)),
    ("festival_surge", facts(buyer_type="SPECIALTY", calendar="festival", round="R6", specialty_demand_vs_early_avg=2.0)),
    ("normal", facts(buyer_type="SPECIALTY", calendar="festival", round="R7", specialty_demand_vs_early_avg=1.1)),
    ("normal", facts(buyer_type="COMMERCIAL", calendar="festival", round="R6", specialty_demand_vs_early_avg=2.0)),
    ("normal", facts(unsold_bags=5, capacity_left_bags=40)),
    ("normal", facts(we_above_limit_last_round=True, we_sold_all_last_round=False)),
]
UP, DOWN = {"shortage"}, {"undercut", "flood"}

T2 = [  # (คำถาม, ตัวเลือก, เฉลย, เป็นข้อทิศราคาหลัง OUTBID)
    ("Last round we offered at 1.00 x value and the result was OUTBID. What does it mean?",
     ["a: another team offered cheaper", "b: above the buyer's hidden ceiling", "c: failed the spec"], "a", False),
    ("We were OUTBID last round. What should our price do this round?", ["a: go up", "b: go down or stay"], "b", True),
    ("We were OUTBID twice in a row by the same buyer. What should our price do?",
     ["a: go up to signal strength", "b: go down or stay"], "b", True),
    ("Result ABOVE_LIMIT means?", ["a: exceeded the buyer's hidden ceiling, lower the price", "b: strong demand, raise the price"], "a", False),
    ("Buyer bought 40% of wanted for 2 rounds, few offers came in, and we sold all our bags. Is it a shortage for us?",
     ["a: yes, price may rise a little", "b: no"], "a", False),
    ("Buyer bought 40% of wanted, but our offers were OUTBID. Should we raise the price?", ["a: yes", "b: no"], "b", True),
    ("We hold 20 unsold bags and only 15 bags of capacity remain. Is it a flood?", ["a: yes", "b: no"], "a", False),
    ("Unsold bags are worth 0.80 x value at the end. Is selling at 0.79 x value better than keeping?", ["a: yes", "b: no"], "b", False),
]


def run():
    print(f"== prompt {VER}", flush=True)
    t1 = [ask(SYSTEM, user_for(T3[5][1]), SCHEMA) for _ in range(10)]
    ok_json = sum(isinstance(a, dict) for a in t1)
    ok_enum = sum(isinstance(a, dict) and a.get("label") in LABELS for a in t1)
    labs = [a.get("label") for a in t1 if isinstance(a, dict)]
    same = max((labs.count(x) for x in set(labs)), default=0)
    t1_pass = ok_json >= 10 and ok_enum == 10 and same >= 9
    print(f"T1 JSON {ok_json}/10 · enum {ok_enum}/10 · ตอบเหมือนกัน {same}/10 ({labs[:1]}) · {'ผ่าน' if t1_pass else 'ไม่ผ่าน'}", flush=True)
    sch2 = {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string", "enum": ["a", "b", "c"]}}}
    sys2 = SYSTEM + "\nYou also answer multiple-choice questions about market signals with one letter."
    t2_scores, dir_ok, wrong = [], 0, []
    for _ in range(3):
        sc = 0
        for i, (q, opts, gold, is_dir) in enumerate(T2):
            a = ask(sys2, q + "\nOptions: " + " | ".join(opts), sch2)
            got = a.get("answer") if isinstance(a, dict) else None
            sc += got == gold
            dir_ok += is_dir and got == gold
            if got != gold:
                wrong.append(i + 1)
        t2_scores.append(sc)
    n_dir = 3 * sum(x[3] for x in T2)
    t2_pass = min(t2_scores) >= 7 and dir_ok == n_dir
    print(f"T2 คะแนน {t2_scores} /8 · ข้อทิศราคาหลัง OUTBID ถูก {dir_ok}/{n_dir} · ข้อที่ผิด {sorted(set(wrong))} · "
          f"{'ผ่าน' if t2_pass else 'ไม่ผ่าน'}", flush=True)
    hit, wrong_dir, miss = 0, 0, []
    for gold, f in T3:
        a = ask(SYSTEM, user_for(f), SCHEMA)
        got = a.get("label") if isinstance(a, dict) else None
        hit += got == gold
        if (got in UP and (gold in DOWN or gold == "normal")) or (got in DOWN and gold in UP):
            wrong_dir += 1
        if got != gold:
            miss.append((gold, got))
    t3_pass = wrong_dir == 0 and hit >= len(T3) - 2
    print(f"T3 ตรงเฉลย {hit}/{len(T3)} · ผิดทิศ {wrong_dir} · ผิด (เฉลย, ตอบ) {miss} · {'ผ่าน' if t3_pass else 'ไม่ผ่าน'}", flush=True)
    if os.environ.get("T5", "1") == "1":   # ความนิ่ง: สลับลำดับข้อมูล + ใส่บรรทัดไม่เกี่ยว
        base_l, changed = [], 0
        for gold, f in T3:
            d = derived(f)
            d2 = dict(reversed(list(d.items())))
            u = ("Facts (computed by the program):\n" + json.dumps(d2, ensure_ascii=False)
                 + "\nNote: server_time 10:42, team T13, 56 teams online.\nLabel this buyer type.")
            a = ask(SYSTEM, u, SCHEMA)
            got = a.get("label") if isinstance(a, dict) else None
            base_l.append(got)
        prev = [m for m in miss]
        hits5 = sum(g == x for (g, _), x in zip(T3, base_l))
        print(f"T5 สลับลำดับ+บรรทัดไม่เกี่ยว: ตรงเฉลย {hits5}/{len(T3)} (เดิม {hit}) · {'ผ่าน' if abs(hits5 - hit) <= 1 else 'ไม่ผ่าน'}", flush=True)
    p95 = sorted(lat)[int(0.95 * (len(lat) - 1))]
    print(f"T6 latency เฉลี่ย {st.mean(lat):.2f} วิ · p95 {p95:.2f} วิ · ล้ม {fails}/{len(lat)}", flush=True)
    json.dump({"ver": VER, "T1": t1_pass, "T2": t2_pass, "t2": t2_scores, "dir": [dir_ok, n_dir], "T3": [hit, len(T3), wrong_dir],
               "T3_pass": t3_pass, "miss": miss, "p95": p95, "fails": fails},
              open(HERE / f"summary_{VER}.json", "w", encoding="utf-8"), ensure_ascii=False)


run()

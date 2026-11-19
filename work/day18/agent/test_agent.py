"""ทดสอบออฟไลน์ (ไม่ต่อเน็ต): python test_agent.py

1. cliff_risk / classify ทำงานกับล็อตชิดขอบ
2. MarketModel อ่านผลแบบขอบเขตถูกทิศ
3. LLM ปลอม: ตอบดี / ตอบมั่ว / ตอบไม่ทัน → agent ไม่ล้ม และค่าถูกบีบ ±0.03
4. strategy พัง → main ใช้ fallback แล้วเล่นจนจบ
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import advisor                      # noqa: E402
import main as agent_main           # noqa: E402
import mock_market as mm            # noqa: E402
import strategy                     # noqa: E402
from inventory import classify, cliff_risk   # noqa: E402
from market_model import MarketModel         # noqa: E402

agent_main.time.sleep = lambda s: None
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("  ✓", msg)


print("1. cliff risk")
r = cliff_risk(mm.RULES, {"defect_pct": 6.9, "moisture_pct": 11.0, "screen": 15})
check("defect 7.0" in r["edges"] and r["drop_pct"] > 10, f"defect 6.9 ชิดขอบ 7 ร่วงได้ {r['drop_pct']}%")
r = cliff_risk(mm.RULES, {"defect_pct": 2.0, "moisture_pct": 11.0, "screen": 15})
check(r["edges"] == [] and r["drop_pct"] < 5, "defect 2.0 ไม่ชิดขอบ")
lots = [{"lot_id": "A", "sample": {"defect_pct": 16, "moisture_pct": 11, "screen": 15}},
        {"lot_id": "B", "sample": {"defect_pct": 6.95, "moisture_pct": 11, "screen": 15}},
        {"lot_id": "C", "sample": {"defect_pct": 2.0, "moisture_pct": 13.5, "screen": 15}}]
c = classify(mm.RULES, lots, [], set())
check(c["A"]["cls"] == "UNSELLABLE", "defect 16 = ขายไม่ได้ (REJECT)")
check("COMMERCIAL" not in c["B"]["types"] and "COMMERCIAL" in c["B"]["types_plain"], f"defect 6.95: โอกาสผ่าน Commercial {c['B']['pass_prob']['COMMERCIAL']} < {0.6} → ไม่ส่ง")
check(c["C"]["types"] == ["INSTANT"], "moisture 13.5: ได้แค่ Instant")


print("2. market model")


class Mem:
    def __init__(self, sent, rounds):
        self.sent, self.rounds = sent, rounds


sent = {"R1": [{"rfq_id": "R1-01", "lot_id": "L", "buyer_type": "COMMERCIAL", "buyer": "4 ชุมพรคั่วบด", "markup": 0.98},
               {"rfq_id": "R1-02", "lot_id": "L", "buyer_type": "COMMERCIAL", "buyer": "4 ชุมพรคั่วบด", "markup": 1.02},
               {"rfq_id": "R1-03", "lot_id": "L", "buyer_type": "INSTANT", "buyer": "5 อินสแตนท์ไทย", "markup": 0.97}]}
rounds = [{"round_id": "R1", "my_offers": [{"rfq_id": "R1-01", "lot_id": "L", "status": "ACCEPTED"},
                                           {"rfq_id": "R1-02", "lot_id": "L", "status": "OUTBID"},
                                           {"rfq_id": "R1-03", "lot_id": "L", "status": "ABOVE_LIMIT"}],
           "market_summary": [{"buyer_type": "COMMERCIAL", "wanted_kg": 600, "bought_kg": 600, "offers": 20},
                              {"buyer_type": "INSTANT", "wanted_kg": 600, "bought_kg": 300, "offers": 15}]}]
m = MarketModel(Mem(sent, rounds))
tc = m.target("4 ชุมพรคั่วบด", "COMMERCIAL")
check(0.98 <= tc["ratio"] < 1.02, f"Commercial: ชนะ 0.98 แพ้ 1.02 → เป้า {tc['ratio']}")
ti = m.target("5 อินสแตนท์ไทย", "INSTANT")
check(ti["cap"] < 0.97, f"Instant: เกินเพดานที่ 0.97 → เพดานบน {ti['cap']}")
check(m.market_state("INSTANT")["mode"] == "ceiling", "Instant ซื้อได้ 50% = ติดเพดาน")


print("3. LLM ปลอม")


class FakeLLM:
    def __init__(self, answer, delay_fail=False):
        self.answer, self.last_error = answer, None

    def ask_json(self, system, user, schema, timeout=None):
        if self.answer == "timeout":
            self.last_error = "Timeout"
            return None
        return self.answer


for name, ans in [("ตอบดี", {"adjust": {"COMMERCIAL": 0.01, "INSTANT": -0.08}, "volume": "push", "reason": "x" * 500}),
                  ("ตอบมั่ว", {"adjust": "lots", "volume": 3}),
                  ("ไม่ทัน", "timeout")]:
    a = advisor.ask(FakeLLM(ans), {"round": {"number": 3}}, {"phase": "mid"}, {}, {}, 8, 120)
    if name == "ตอบดี":
        check(a["ok"] and a["adjust"]["INSTANT"] == -0.03 and len(a["reason"]) <= 200, "ค่าเกินถูกบีบเหลือ −0.03 · reason ≤ 200")
    else:
        check(not a["ok"] and a["adjust"] == {}, f"{name} → ไม่ใช้ LLM (ใช้ราคาโมเดล)")

agent_main.LOGS = Path(__import__("tempfile").mkdtemp(prefix="test-agent-"))
m1 = mm.FakeMarket(7)
agent_main.play(m1, FakeLLM({"adjust": {"COMMERCIAL": -0.01}, "volume": "normal", "reason": "test"}), forever=False)
check(m1.phase == "CLOSED", f"เล่นครบเกมโดยเปิด LLM ปลอม · PR {m1.score()['pr']}")


print("4. strategy พัง → fallback")
orig = strategy.plan
strategy.plan = lambda *a, **k: 1 / 0
try:
    m2 = mm.FakeMarket(8)
    agent_main.play(m2, None, forever=False)
    check(m2.phase == "CLOSED" and m2.kg_sold > 0, f"fallback เล่นจนจบและขายได้ {m2.kg_sold} กก.")
finally:
    strategy.plan = orig

print("5. ตลาดฝึกแบบเร่ง (ข้ามช่วง + เริ่มเกมใหม่)")
sb = mm.FakeSandbox(21, max_games=3)
try:
    agent_main.play(sb, None, forever=True)
except mm.StopTest as e:
    stop = str(e)
check(stop == "ครบจำนวนเกมที่ทดสอบ", f"เล่นครบ 3 เกมด้วยการกดข้าม · กดข้าม {sb.advances} ครั้ง · reset {sb.resets} ครั้ง")
check(len(sb.scores) == 3 and all(s["pr"] > 0.8 for s in sb.scores), f"PR แต่ละเกม {[s['pr'] for s in sb.scores]}")
check(agent_main.LOG_FILE is not None and agent_main.LOG_FILE.parent.name == "runs",
      f"ตลาดฝึก: log ไฟล์ใหม่ต่อรัน → {agent_main.LOG_FILE.name}")
events = [__import__("json").loads(l)["event"] for l in open(agent_main.LOG_FILE, encoding="utf-8")]
check(events.count("reveal") >= 3 and events.count("round_open") >= 24 and events.count("round_results") >= 21,
      f"log ครบ: reveal {events.count('reveal')} · round_open {events.count('round_open')} · round_results {events.count('round_results')}")

print("6. ตลาดแข่ง (mode ไม่ใช่ sandbox) ต้องไม่กดข้าม/reset")


class FakeComp(mm.FakeMarket):
    def call(self, method, path, json=None, params=None):
        if path.startswith("/v1/sandbox/") and method == "POST":
            raise AssertionError(f"เรียก {path} ในตลาดแข่ง!")
        if path == "/v1/version":
            return {"mode": "competition"}
        return super().call(method, path, json, params)


mc = FakeComp(31)
agent_main.play(mc, None, forever=False)
check(mc.phase == "CLOSED", "ตลาดแข่ง: เล่นจบโดยไม่เรียก advance/reset")
check(agent_main.LOG_FILE == agent_main.LOGS / "decisions.jsonl",
      "ตลาดแข่ง: log ไฟล์เดียว logs/decisions.jsonl (pack.py หาไฟล์นี้ · รีสตาร์ทต่อไฟล์เดิม)")

print("7. แรงกดดันกระสอบ")
import playbook as pb   # noqa: E402
check(pb.pressure(5, 6, 8, "mid")[1] == "scarce", "ของ 5 กระสอบ · capacity 6×8 = ของน้อย")
check(pb.pressure(60, 6, 8, "mid")[1] == "flood", "ของ 60 กระสอบ · capacity 6×8 = ของล้น")
check(pb.pressure(60, 6, 1, "final")[1] == "normal", "รอบสุดท้ายไม่ใช้โหมด pressure")

print("8. SPEC_MISMATCH ห้ามส่งตามความเข้มของสเปก")
bloom = {"max_defect_pct": 3.0, "max_moisture_pct": 12.5, "min_screen": 17}
doi = {"max_defect_pct": 3.0, "max_moisture_pct": 12.5, "min_screen": 16}
com = {"max_defect_pct": 7.0, "max_moisture_pct": 12.5, "min_screen": None}
sent = {"R1": [{"rfq_id": "R1-01", "lot_id": "L", "buyer_type": "SPECIALTY", "buyer": "2 บางกอกบลูม", "markup": 1.18,
                "spec": bloom}]}
rounds = [{"round_id": "R1", "my_offers": [{"rfq_id": "R1-01", "lot_id": "L", "status": "SPEC_MISMATCH"}],
           "market_summary": []}]
m = MarketModel(Mem(sent, rounds))
check(m.spec_banned("L", "SPECIALTY", bloom), "ตกบางกอกบลูม (screen ≥17) → ห้ามส่งบางกอกบลูมอีก")
check(not m.spec_banned("L", "SPECIALTY", doi), "ยังส่งดอยช้าง (screen ≥16 หลวมกว่า) ได้")
check(not m.spec_banned("L", "COMMERCIAL", com), "ยังส่ง Commercial ได้")

print("9. Specialty ก่อน + สงวนล็อตเกรด Specialty")
state = {"round": {"round_id": "R2", "kind": "real", "number": 2, "of": 8, "calendar": "ปกติ"},
         "lots": [{"lot_id": "HI", "kg_total": 600, "kg_available": 600, "sample": {"defect_pct": 1.5, "moisture_pct": 11.0, "screen": 18}},
                  {"lot_id": "NO", "kg_total": 600, "kg_available": 600, "sample": {"defect_pct": 5.0, "moisture_pct": 11.0, "screen": 14}}],
         "rfqs": [{"rfq_id": "R2-01", "buyer": "1 ดอยช้างโรสเตอร์", "buyer_type": "SPECIALTY", "kg": 180, "bags": 3, "spec": doi},
                  {"rfq_id": "R2-02", "buyer": "4 ชุมพรคั่วบด", "buyer_type": "COMMERCIAL", "kg": 1200, "bags": 20, "spec": com}],
         "capacity_left_kg": 360, "round_capacity_kg": 360, "my_open_offers": [], "seconds_left": 90}
tv = {"HI": 125.0, "NO": 112.0}
import os  # noqa: E402
os.environ["RESERVE_SPECIALTY"] = "1"                 # ทดสอบโหมดสงวน (ค่าเริ่มปิดแล้ว หลังแข่งด่าน 2)
ctx = strategy.Context(mm.RULES, mm.CALENDAR, tv, random.Random(3), None, None, 90)
offers, _ = strategy.decide(state, ctx)
os.environ.pop("RESERVE_SPECIALTY")
spec_kg = sum(o["kg"] for o in offers if o["rfq_id"] == "R2-01")
hi_to_com = sum(o["kg"] for o in offers if o["rfq_id"] == "R2-02" and o["lot_id"] == "HI")
check(spec_kg == 120, f"Specialty ได้ไม่เกิน 40% ของงบ 6 = 2 กระสอบ ({spec_kg // 60}) ที่เหลือไปล็อตอื่น")
check(hi_to_com == 0, "ช่วงต้น: ล็อตเกรด Specialty ไม่ถูกขายให้ Commercial")
check(sum(o["kg"] for o in offers) <= 360, f"ไม่เกิน capacity ({sum(o['kg'] for o in offers) // 60}/6 กระสอบ)")
sp = next(o for o in offers if o["rfq_id"] == "R2-01")
check(0.95 <= sp["price_per_kg"] / tv["HI"] <= 1.05, f"ราคา Specialty ×{sp['price_per_kg'] / tv['HI']:.3f} (ค่าเริ่มจากตลาดแข่ง ~1.00)")

print("10. รอบซ้อม (ไม่นับคะแนน) = หยั่งราคา")
pstate = dict(state)
pstate["round"] = {"round_id": "P1", "kind": "practice", "number": 0, "of": 8, "counts_for_score": False, "calendar": "ซ้อม"}
pstate["rfqs"] = state["rfqs"] + [{"rfq_id": "P1-03", "buyer": "5 อินสแตนท์ไทย", "buyer_type": "INSTANT", "kg": 600, "bags": 10,
                                   "spec": {"max_defect_pct": 15.0, "max_moisture_pct": 14.0, "min_screen": None}},
                                  {"rfq_id": "P1-04", "buyer": "3 สยามคอมเมิร์ซ", "buyer_type": "COMMERCIAL", "kg": 600, "bags": 10, "spec": com}]
ctx = strategy.Context(mm.RULES, mm.CALENDAR, tv, random.Random(5), None, None, 90)
offers, _ = strategy.decide(pstate, ctx)
check(ctx.meta.get("probe") and all(o["kg"] == 60 for o in offers), f"รอบซ้อม: หยั่ง RFQ ละ 1 กระสอบ ({len(offers)} RFQ)")
ratios = sorted({round(o["price_per_kg"] / tv[o["lot_id"]], 2) for o in offers})
check(len(ratios) >= 3, f"หยั่งหลายราคา {ratios}")
check(sum(o["kg"] for o in offers) <= 360, "ไม่เกิน capacity")
sent = {"P1": [{"rfq_id": "P1-04", "lot_id": "NO", "buyer_type": "COMMERCIAL", "buyer": "3 สยามคอมเมิร์ซ", "markup": 1.05}]}
rounds = [{"round_id": "P1", "kind": "practice", "my_offers": [{"rfq_id": "P1-04", "lot_id": "NO", "kg": 60, "filled_kg": 0,
                                                              "status": "ABOVE_LIMIT"}], "market_summary": []}]
m = MarketModel(Mem(sent, rounds))
check(m.offered_bags == 0 and m.ceiling("3 สยามคอมเมิร์ซ", "COMMERCIAL")["hi"] == 1.05,
      "ผลรอบซ้อม: ใช้เรียนเพดาน แต่ไม่นับเป็นอัตราขายได้")

print("11. ตลาดฝึกแบบเร่ง: เปิดมาเจอเกมกลางทาง → เริ่มเกมใหม่ · ประเมินด้วยค่าตัวอย่าง")
sb = mm.FakeSandbox(41, max_games=2)                 # reset ครั้งแรก = ทิ้งเกมกลางทาง · เกมใหม่เล่นจนจบ
sb._open(5)                                          # จำลองเกมที่เดินไปถึง R5 แล้ว ยังไม่ได้ประเมิน
try:
    agent_main.play(sb, None, forever=True)
except mm.StopTest:
    pass
ev = [__import__("json").loads(l)["event"] for l in open(agent_main.LOG_FILE, encoding="utf-8")]
check(ev[:5].count("sandbox_reset_midgame") == 1 and "appraisal_sent" in ev, "เจอเกมกลางทาง → reset แล้วเล่นเกมใหม่ตั้งแต่ประเมิน")
from appraisal import estimate_lots, true_value  # noqa: E402
lot = {"lot_id": "X", "sample": {"defect_pct": 3.1, "moisture_pct": 15.1, "screen": 15}}
import os  # noqa: E402
os.environ["APPRAISAL_MODE"] = "sample"
check(estimate_lots(mm.RULES, [lot])["X"] == round(true_value(mm.RULES, lot["sample"]), 2), "APPRAISAL_MODE=sample = ค่าตัวอย่างตรงๆ")
os.environ.pop("APPRAISAL_MODE")
sv = true_value(mm.RULES, lot["sample"])
hy = estimate_lots(mm.RULES, [lot])["X"]
check(abs(hy - sv) <= 0.08 * sv + 0.01, f"hybrid (ค่าเริ่ม): ชื้น 15.1 ชิดหน้าผา → ไม่กระโดดข้ามหน้าผา ({sv:.2f} → {hy})")


print("12. LLM guard: ทิ้งค่าผิดทิศ / ค่าราคาเต็ม")


class _LLM:
    last_error = None

    def __init__(self, ans):
        self.ans = ans

    def ask_json(self, *a, **k):
        return self.ans


_st = {"round": {"number": 4, "calendar": None}, "seconds_left": 60}
_sum = {"COMMERCIAL": {"last": {"OUTBID": 3, "ACCEPTED": 1}}, "INSTANT": {"last": {"ACCEPTED": 2}},
        "SPECIALTY": {"last": {"ABOVE_LIMIT": 1}}}
a = advisor.ask(_LLM({"adjust": {"COMMERCIAL": 0.03, "INSTANT": 0.93, "SPECIALTY": 0.02}, "volume": "normal", "reason": "x"}),
                _st, {"phase": "mid"}, _sum, {}, 8, 60)
check(a["adjust"] == {} and set(a["dropped"]) == {"COMMERCIAL", "INSTANT", "SPECIALTY"},
      f"ขึ้นราคาหลัง OUTBID/ABOVE_LIMIT + ค่า 0.93 ถูกทิ้งหมด {a['dropped']}")
a = advisor.ask(_LLM({"adjust": {"COMMERCIAL": -0.05, "INSTANT": 0.02}, "volume": "push", "reason": "x"}),
                _st, {"phase": "mid"}, _sum, {}, 8, 60)
check(a["adjust"] == {"COMMERCIAL": -0.03, "INSTANT": 0.02} and not a["dropped"],
      f"ลดราคาหลังแพ้ได้ (บีบเหลือ -0.03) · ขึ้นราคาประเภทที่ขายหมดได้ {a['adjust']}")

print("13. ราคาจากผลตลาดจริง (market_summary) + ใช้ capacity เต็ม")
mrounds = [{"round_id": "R1", "kind": "real", "my_offers": [], "market_summary": [
    {"rfq_id": "R1-01", "buyer": "1 ดอยช้างโรสเตอร์", "buyer_type": "SPECIALTY", "wanted_kg": 300, "bought_kg": 300, "offers": 15,
     "price_min": 120.0, "price_max": 124.0},
    {"rfq_id": "R1-02", "buyer": "4 ชุมพรคั่วบด", "buyer_type": "COMMERCIAL", "wanted_kg": 1200, "bought_kg": 1200, "offers": 20,
     "price_min": 100.0, "price_max": 130.0}]}]
mstate = dict(state)
os.environ["MKT_MODE"] = "safe"                      # ข้อ 13 ตรวจสูตรราคาชัวร์ (ต่ำสุด − 0.02)
ctx = strategy.Context(mm.RULES, mm.CALENDAR, tv, random.Random(3), Mem({}, mrounds), None, 90)
offers, _ = strategy.decide(mstate, ctx)
mm_model = MarketModel(Mem({}, mrounds))
mm_model.set_lots(mstate["lots"], tv)
check(abs(mm_model.market_ratio("1 ดอยช้างโรสเตอร์", doi) - 124 / 125) < 1e-3, "ดอยช้าง: ราคาตลาด = 124 ÷ TV ล็อตเดียวที่ผ่านสเปก (125)")
check(abs(mm_model.market_ratio("4 ชุมพรคั่วบด", com) - 130 / 125) < 1e-3, "ชุมพร: ราคาตลาด = 130 ÷ TV สูงสุดที่ผ่านสเปก (ขอบล่าง)")
r_hi = {o["rfq_id"]: round(o["price_per_kg"] / tv[o["lot_id"]], 3) for o in offers if o["lot_id"] == "HI"}
check("R2-01" not in r_hi, f"ล็อตเกรด Specialty ไม่ถูกส่งให้ดอยช้างที่จ่ายต่ำกว่า (ชุมพร ~1.02 > ดอยช้าง ~0.97) {r_hi}")
check(all(o["price_per_kg"] / tv[o["lot_id"]] <= 130 / 125 - 0.02 + 1e-3 for o in offers), "ไม่มีซองแพงกว่าราคาตลาด − 0.02")
check(sum(o["kg"] for o in offers) == 360, f"ใช้ capacity เต็ม ({sum(o['kg'] for o in offers) // 60}/6 กระสอบ)")
os.environ.pop("MKT_MODE")

print("14. ราคาแบบความผันผวน (ค่าเริ่ม): ผู้ซื้อราคานิ่ง เว้นน้อยกว่า")
vr = [{"round_id": f"R{k}", "kind": "real", "my_offers": [], "market_summary": [
    {"rfq_id": f"R{k}-01", "buyer": "4 ชุมพรคั่วบด", "buyer_type": "COMMERCIAL", "wanted_kg": 600, "bought_kg": 600, "offers": 10,
     "price_min": 100.0, "price_max": 128.0},
    {"rfq_id": f"R{k}-02", "buyer": "1 ดอยช้างโรสเตอร์", "buyer_type": "SPECIALTY", "wanted_kg": 300, "bought_kg": 300, "offers": 15,
     "price_min": 110.0, "price_max": p}]} for k, p in ((1, 128.0), (2, 124.0), (3, 120.0))]
vm = MarketModel(Mem({}, vr))
vm.set_lots(mstate["lots"], tv)
tc, ts = vm.target("4 ชุมพรคั่วบด", "COMMERCIAL", com)["ratio"], vm.target("1 ดอยช้างโรสเตอร์", "SPECIALTY", doi)["ratio"]
check(abs(tc - (128 / 125 - 1.5 * 0.0 - 0.005)) < 0.02, f"ชุมพรราคานิ่ง 1.024 → เว้นน้อย ({tc})")
check(ts < 120 / 125 - 0.02, f"ดอยช้างขาลง 1.02→0.96 → เว้นมากกว่า ({ts})")

print("15. ปฏิทินด่าน 3 รูปแบบไม่คุ้น → agent ไม่ล้ม")
ni = agent_main.norm_info([{"rounds": [6, 7, 8], "label": "เทศกาลกาแฟ", "demand_weight": "มาก"}])
check(ni["rules"]["timeline"]["rounds"] == 15 and len(ni["calendar"]) == 1, "ได้ list เปล่า → rounds สำรอง 15 · เก็บแถวปฏิทิน")
ni2 = agent_main.norm_info({"items": [{"rounds": "13-14", "label": "ใกล้ปิดตลาด", "demand_weight": 0.7}],
                            "rules": {"timeline": {"rounds": "15"}}})
check(ni2["rules"]["timeline"]["rounds"] == 15 and ni2["calendar"][0]["rounds"] == "13-14", "calendar อยู่ใต้ items · rounds เป็นข้อความ")
cw = pb.calendar_weights(ni["calendar"] + [{"rounds": "14-20", "demand_weight": None}], 15)
check(cw[7]["label"] == "เทศกาลกาแฟ" and cw[7]["w"] == 1.0 and 20 not in cw, "demand_weight ไม่ใช่ตัวเลข → 1.0 · รอบเกินไม่เพิ่ม")
ctx15 = strategy.Context(dict(mm.RULES), ni["calendar"], tv, random.Random(1), Mem({}, []), None, 200)
check(isinstance(strategy.decide(mstate, ctx15)[0], list), "decide() ทำงานกับปฏิทินแปลก")

print("16. ตรวจสเปกล็อตชิดขอบในรอบซ้อม (SPEC_PROBE)")
edge = {"lot_id": "ED", "kg_total": 540, "kg_available": 540, "sample": {"defect_pct": 3.9, "moisture_pct": 12.6, "screen": 18}}
inst = {"max_defect_pct": 15.0, "max_moisture_pct": 14.0, "min_screen": None}
tv16 = {"ED": 122.0}
ps = {"round": {"round_id": "P1", "kind": "practice", "number": 1, "of": 2, "counts_for_score": False, "calendar": "ปกติ"},
      "lots": [edge], "capacity_left_kg": 300, "round_capacity_kg": 300, "my_open_offers": [], "seconds_left": 90,
      "rfqs": [{"rfq_id": "P1-01", "buyer": "3 สยามคอมเมิร์ซ", "buyer_type": "COMMERCIAL", "kg": 600, "bags": 10, "spec": com},
               {"rfq_id": "P1-02", "buyer": "5 อินสแตนท์ไทย", "buyer_type": "INSTANT", "kg": 600, "bags": 10, "spec": inst}]}
ctx16 = strategy.Context(mm.RULES, mm.CALENDAR, tv16, random.Random(1), None, None, 90)
off16, _ = strategy.decide(ps, ctx16)
probe = [o for o in off16 if o["rfq_id"] == "P1-01"]
check(len(probe) == 1 and probe[0]["kg"] == 60 and abs(probe[0]["price_per_kg"] / 122.0 - 0.85) < 0.01
      and ctx16.probe_tags.get(("P1-01", "ED")) == "spec",
      f"(i) รอบซ้อม: ชื้น 12.6 (ขอบ Commercial 12.5) → ส่ง 1 กระสอบตรวจสเปก ราคา ×0.85 {probe}")
rs = dict(ps, round={"round_id": "R1", "kind": "real", "number": 1, "of": 15, "counts_for_score": True, "calendar": "ปกติ"},
          rfqs=[dict(r, rfq_id=r["rfq_id"].replace("P1", "R1")) for r in ps["rfqs"]])
sent16 = {"P1": [{"rfq_id": "P1-01", "lot_id": "ED", "buyer_type": "COMMERCIAL", "buyer": "3 สยามคอมเมิร์ซ", "markup": 0.85,
                  "spec": com, "probe": "spec"}]}
for st, want in (("OUTBID", True), ("SPEC_MISMATCH", False)):
    rd = [{"round_id": "P1", "kind": "practice", "market_summary": [],
           "my_offers": [{"rfq_id": "P1-01", "lot_id": "ED", "kg": 60, "filled_kg": 0, "status": st}]}]
    mod = MarketModel(Mem(sent16, rd))
    c16 = strategy.Context(mm.RULES, mm.CALENDAR, tv16, random.Random(2), Mem(sent16, rd), None, 90)
    o16, _ = strategy.decide(rs, c16)
    to_com = sum(o["kg"] for o in o16 if o["rfq_id"] == "R1-01")
    if want:
        check(mod.spec_verified("ED", com) and to_com > 0,
              f"(ii) รอบซ้อมได้ OUTBID = ผ่านสเปกแล้ว → รอบจริงขาย Commercial ได้ ({to_com // 60} กระสอบ)")
        check(mod.ceiling("3 สยามคอมเมิร์ซ", "COMMERCIAL")["lo"] is None, "ซองตรวจสเปก (ราคาต่ำตั้งใจ) ไม่ถูกใช้เป็นข้อมูลราคา")
    else:
        check(not mod.spec_verified("ED", com) and mod.spec_banned("ED", "COMMERCIAL", com) and to_com == 0,
              "(iii) SPEC_MISMATCH → ห้ามส่ง Commercial ทั้งเกม")
os.environ["SPEC_PROBE"] = "0"
c0 = strategy.Context(mm.RULES, mm.CALENDAR, tv16, random.Random(1), None, None, 90)
o0, _ = strategy.decide(ps, c0)
os.environ.pop("SPEC_PROBE")
check(not any(o["rfq_id"] == "P1-01" for o in o0), "(iv) SPEC_PROBE=0 → ไม่ตรวจ (พฤติกรรมเดิม)")

print("17. ตรวจสเปกในรอบจริง R1–R2 เมื่อไม่มีผลรอบซ้อม (SPEC_PROBE_REAL)")
c17 = strategy.Context(mm.RULES, mm.CALENDAR, tv16, random.Random(4), None, None, 90)
o17, _ = strategy.decide(rs, c17)
pr17 = [o for o in o17 if o["rfq_id"] == "R1-01"]
check(1 <= len(pr17) <= 2 and all(o["kg"] == 60 for o in pr17) and pr17[0]["price_per_kg"] / 122.0 >= 0.95
      and c17.probe_tags.get(("R1-01", "ED")) == "spec_real",
      f"(i) ไม่มีรอบซ้อม → R1 ตรวจ Commercial 1 กระสอบ ราคาปกติ ×{pr17[0]['price_per_kg'] / 122.0:.3f}" if pr17 else "(i) ไม่พบซองตรวจ")
rd_ok = [{"round_id": "P1", "kind": "practice", "market_summary": [],
          "my_offers": [{"rfq_id": "P1-01", "lot_id": "ED", "kg": 60, "filled_kg": 0, "status": "OUTBID"}]}]
c17b = strategy.Context(mm.RULES, mm.CALENDAR, tv16, random.Random(4), Mem(sent16, rd_ok), None, 90)
strategy.decide(rs, c17b)
check(not any(v == "spec_real" for v in (getattr(c17b, "probe_tags", None) or {}).values()),
      "(ii) รอบซ้อมยืนยันแล้ว → R1 ไม่ตรวจซ้ำ (ขายปกติ)")
far = dict(rs, lots=[dict(edge, sample={"defect_pct": 3.9, "moisture_pct": 12.8, "screen": 18})])
c17c = strategy.Context(mm.RULES, mm.CALENDAR, tv16, random.Random(4), None, None, 90)
o17c, _ = strategy.decide(far, c17c)
check(not any(o["rfq_id"] == "R1-01" for o in o17c), "(iii) ชื้น 12.8 (โอกาสผ่าน < 0.25) → ไม่ตรวจในรอบจริง")
r3 = dict(rs, round={"round_id": "R3", "kind": "real", "number": 3, "of": 15, "counts_for_score": True, "calendar": "ปกติ"},
          rfqs=[dict(r, rfq_id=r["rfq_id"].replace("R1", "R3")) for r in rs["rfqs"]])
c17d = strategy.Context(mm.RULES, mm.CALENDAR, tv16, random.Random(4), None, None, 90)
o17d, _ = strategy.decide(r3, c17d)
check(not any(o["rfq_id"] == "R3-01" for o in o17d), "(iv) R3 ขึ้นไป → ไม่ตรวจ")

print("18. ตัวช่วยกฎ (rule_advisor · ไม่ใช้ LLM · ไม่เปลี่ยนซอง)")
import rule_advisor  # noqa: E402
lot18 = {"lot_id": "L", "kg_total": 600, "kg_available": 600, "sample": {"defect_pct": 4.0, "moisture_pct": 11.0, "screen": 15}}
def st18(n, cap_kg=300, lots=None, rfqs=None):  # noqa: E302
    return {"round": {"round_id": f"R{n}", "kind": "real", "number": n, "of": 15, "calendar": "ปกติ"},
            "lots": lots or [lot18], "round_capacity_kg": cap_kg, "capacity_left_kg": cap_kg,
            "rfqs": rfqs or [{"rfq_id": f"R{n}-01", "buyer": "3 สยามคอมเมิร์ซ", "buyer_type": "COMMERCIAL", "kg": 600,
                              "bags": 10, "spec": com}]}
def rnd18(rid, status, fill=1.0, t="COMMERCIAL"):  # noqa: E302
    return {"round_id": rid, "kind": "real",
            "my_offers": [{"rfq_id": f"{rid}-01", "lot_id": "L", "kg": 120, "filled_kg": 120 if status == "ACCEPTED" else 0,
                           "status": status}],
            "market_summary": [{"rfq_id": f"{rid}-01", "buyer": "x", "buyer_type": t, "wanted_kg": 600,
                                "bought_kg": int(600 * fill), "offers": 5, "price_max": 120.0}]}
sent18 = {f"R{k}": [{"rfq_id": f"R{k}-01", "lot_id": "L", "buyer_type": "COMMERCIAL"}] for k in range(1, 6)}
lab = rule_advisor.rule_labels(Mem(sent18, [rnd18("R1", "OUTBID"), rnd18("R2", "OUTBID")]), st18(3), 15)
check(lab["COMMERCIAL"]["label"] == "undercut" and "MKT_K_COMMERCIAL" in lab["COMMERCIAL"]["rec"], "แพ้ 2 รอบติด → undercut · MKT_K_COMMERCIAL=2.0")
lab = rule_advisor.rule_labels(Mem(sent18, [rnd18("R1", "ACCEPTED", 0.4), rnd18("R2", "ACCEPTED", 0.3)]), st18(3), 15)
check(lab["COMMERCIAL"]["label"] == "shortage" and "SHORT_CEIL" in lab["COMMERCIAL"]["rec"], "ผู้ซื้อได้ < 50% 2 รอบ + เราขายได้ → shortage")
lab = rule_advisor.rule_labels(Mem(sent18, [rnd18("R1", "OUTBID", 0.4), rnd18("R2", "OUTBID", 0.3)]), st18(3), 15)
check(lab["COMMERCIAL"]["label"] == "undercut", "ผู้ซื้อได้ < 50% แต่เราแพ้ราคา → ไม่ใช่ shortage (ห้ามขึ้นราคา)")
lab = rule_advisor.rule_labels(Mem(sent18, [rnd18("R1", "ACCEPTED")]), st18(14, cap_kg=120), 15)
check(lab["COMMERCIAL"]["label"] == "flood", "ของ 10 กระสอบ > capacity ที่เหลือ 2×2 → flood")
fest_state = st18(6, rfqs=[{"rfq_id": "R6-01", "buyer": "1 ดอยช้างโรสเตอร์", "buyer_type": "SPECIALTY", "kg": 600, "bags": 10, "spec": doi}])
spec_hist = [rnd18(f"R{k}", "ACCEPTED", 1.0, "SPECIALTY") for k in range(1, 6)]
for r in spec_hist:
    r["market_summary"][0]["wanted_kg"] = 240
lab = rule_advisor.rule_labels(Mem(sent18, spec_hist), fest_state, 15, "เทศกาลกาแฟ")
check(lab["SPECIALTY"]["label"] == "festival_surge", "เทศกาล: Specialty 10 กระสอบ ≥ 1.5 × ค่าเฉลี่ย R1–R5 (4) → festival_surge")
lab = rule_advisor.rule_labels(Mem(sent18, [rnd18("R1", "ACCEPTED"), rnd18("R2", "ACCEPTED")]), st18(3), 15)
check(all(v["label"] == "normal" and v["rec"] == "" for v in lab.values()), "ไม่มีสัญญาณ → normal ไม่แนะนำอะไร")
ca, cb = (strategy.Context(mm.RULES, mm.CALENDAR, tv16, random.Random(9), None, None, 90) for _ in range(2))
oa, _ = strategy.decide(rs, ca)
rule_advisor.rule_labels(Mem({}, []), rs, 15)
ob, _ = strategy.decide(rs, cb)
check(oa == ob, "เรียกตัวช่วยกฎแล้ว ซองที่ส่งเหมือนเดิมทุกตัว")

print(f"\nผ่านทั้งหมด {ok} ข้อ · log ทดสอบ: {agent_main.LOGS}")

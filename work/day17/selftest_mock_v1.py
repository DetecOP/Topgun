# selftest_mock.py · ทดสอบ sell_helper ครบวงจรกับตลาดจำลอง (เรียกฟังก์ชันตรง ไม่ผ่านเน็ต ไม่ใช่ server ผู้จัด)
# จำลองวันพรุ่งนี้: ดูตลาด → กรอก state → suggest → "ส่ง" → บันทึกผล → วนจนจบเกม
# เทียบกับ agent ง่าย (บวก 8% แล้วลด 4% เมื่อขายไม่ออก) บนเกมชุดเดียวกัน (seed เดียวกัน)
# รัน: .venv\Scripts\python.exe day17\selftest_mock.py

import copy
import json
import statistics as st_
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "practice"))
import mock_market as mk  # noqa: E402
import sell_helper as sh  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def true_score(sales):
    """คะแนนแบบส่วนต่าง (สมมติ): Σ (ราคาขาย − มูลค่าจริง) × น้ำหนัก · มูลค่าจริงเอาจากตลาดจำลอง"""
    lots = {l["id"]: l for l in mk.STATE["lots"]}
    return sum((p - lots[i]["_value"]) * lots[i]["weight"] for i, p in sales)


def play_helper(template, seed):
    mk.new_game(seed)
    st = copy.deepcopy(template)
    st["settings"]["rounds_csv"] = None                         # ทดสอบไม่เขียน rounds.csv ของผู้ใช้
    m = mk.public_market()
    st["buyers"] = [dict(b) for b in m["buyers"]]
    sales = []
    while not m["game_over"] and m["lots"]:
        sold_before = {l["id"] for l in st["lots"] if l.get("sold")}
        st["lots"] = [dict(l, sold=False) for l in m["lots"]] + [{"id": i, "sold": True} for i in sold_before]
        _, offers = sh.suggest(st, m["round"])
        res = mk.resolve([{"lot_id": o["lot"], "buyer_id": o["buyer"], "price_per_kg": o["price"]} for o in offers])
        if offers:
            sh.record(st, [f"{x['lot_id']}={'y' if x['sold'] else 'n'}" for x in res])
        sales += [(x["lot_id"], x["price_per_kg"]) for x in res if x["sold"]]
        m = mk.public_market()
    return sales


def play_simple(seed):
    mk.new_game(seed)
    m, fails, sales = mk.public_market(), {}, []
    while not m["game_over"] and m["lots"]:
        offers = []
        for l in m["lots"]:
            ok = [b for b in m["buyers"] if l["moisture"] is None or
                  (l["moisture"] <= b["max_moisture"] and l["defect_pct"] <= b["max_defect"])]
            if ok:
                v = mk.value_per_kg(l["moisture"] or 12.0, l["defect_pct"] or 8.0, l["size"] or "กลาง")
                k = max(-0.05, 0.08 - 0.04 * fails.get(l["id"], 0))
                offers.append({"lot_id": l["id"], "buyer_id": ok[0]["id"], "price_per_kg": round(v * (1 + k), 2)})
        for x in mk.resolve(offers):
            if x["sold"]:
                sales.append((x["lot_id"], x["price_per_kg"]))
            else:
                fails[x["lot_id"]] = fails.get(x["lot_id"], 0) + 1
        m = mk.public_market()
    return sales


if __name__ == "__main__":
    template = json.load(open(HERE / "state_template.json", encoding="utf-8"))
    N = 200
    res = {"ผู้ช่วย sell_helper": [], "agent ง่าย บวก8%แล้วลด": []}
    sold = {k: 0 for k in res}
    for seed in range(N):
        s = play_helper(template, seed)
        res["ผู้ช่วย sell_helper"].append(true_score(s)); sold["ผู้ช่วย sell_helper"] += len(s)
        s = play_simple(seed)
        res["agent ง่าย บวก8%แล้วลด"].append(true_score(s)); sold["agent ง่าย บวก8%แล้วลด"] += len(s)
    d = [a - b for a, b in zip(*res.values())]
    print(f"ตลาดจำลอง {N} เกม (6 ล็อต, 8 รอบ, ผู้ซื้อ 3 ราย รับรอบละ 1) · คะแนนแบบส่วนต่าง (สมมติ)")
    for k, v in res.items():
        print(f"  {k:<26} คะแนนเฉลี่ย {st_.mean(v):>8.1f} · ขายได้เฉลี่ย {sold[k] / N:.1f} ล็อต/เกม")
    print(f"  ผู้ช่วย − agent ง่าย = {st_.mean(d):+.1f} ±{st_.stdev(d) / N ** 0.5:.1f}")
    print("\nตัวอย่างหน้าจอที่ผู้ใช้จะได้ (เกม seed 0 รอบแรก):")
    mk.new_game(0)
    st = copy.deepcopy(template)
    st["settings"]["rounds_csv"] = None
    m = mk.public_market()
    st["buyers"], st["lots"] = [dict(b) for b in m["buyers"]], [dict(l, sold=False) for l in m["lots"]]
    rows, offers = sh.suggest(st, 1)
    sh.print_suggest(rows, offers, 1)

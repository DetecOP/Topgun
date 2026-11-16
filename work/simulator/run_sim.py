# run_sim.py · เปรียบเทียบกลยุทธ์ในตลาดจำลอง ภายใต้สูตรคะแนนทั้ง 3 แบบ
#
# รัน (จากโฟลเดอร์ work):
#   .venv\Scripts\python.exe simulator\run_sim.py            ← เปรียบเทียบ 300 เกม
#   .venv\Scripts\python.exe simulator\run_sim.py --demo     ← ดูทีละรอบ 1 เกม (DRY_RUN)
#
# ⚠️ ตลาดจำลองแต่งขึ้นเอง ผลลัพธ์บอก "แนวโน้ม" เท่านั้น ไม่ใช่ผลจริงวันแข่ง

import sys

import config
from agent_core import plan_offers, submit
from market_sim import Market
from pricer import BuyerPriceLearner
from scoring import MODES, score_sold, score_unsold, total_score
from valuation import PlaceholderValuator, load_params

sys.stdout.reconfigure(encoding="utf-8")

# ชื่อ → (รอข้อมูลไหม, บวกราคาคงที่, รุ่นตัวเรียนราคา)
# v1 = รุ่นแรก (ดูแค่รอบสุดท้าย ไม่ยืมข้อมูล) · v2 = ปรับตามงานวิจัย (คิดล่วงหน้าหลายรอบ + ยืมข้อมูล)
STRATEGIES = {
    "ขายล่วงหน้า+เรียนรู้ v2 (ทีม)": (False, None, "v2"),
    "ขายล่วงหน้า+เรียนรู้ v1": (False, None, "v1"),
    "รอผลวัดก่อน+เรียนรู้ v2": (True, None, "v2"),
    "รอผลวัดก่อน+เรียนรู้ v1": (True, None, "v1"),
    "ขายล่วงหน้า บวก 8% คงที่": (False, 0.08, None),
}
TEAM_STRATEGY = "ขายล่วงหน้า+เรียนรู้ v2 (ทีม)"


def make_learner(version, seed):
    if version == "v1":
        return BuyerPriceLearner(seed=seed, pool_weight=0.0, horizon_aware=False,
                                 informative_prior=False)
    return BuyerPriceLearner(seed=seed)                        # v2 ใช้ค่าใน config


def play(params, strategy, mode, seed, verbose=False):
    """เล่น 1 เกม คืน (คะแนนรวม, จำนวนที่ขายได้, รอบเฉลี่ยที่ขายได้, จำนวนล็อต)"""
    wait, fixed, version = STRATEGIES[strategy]
    market = Market(params, seed)
    valuator = PlaceholderValuator(params)
    learner = make_learner(version, seed)
    lot_scores, sold_rounds = [], []

    for r in range(1, market.n_rounds + 1):
        lots = market.visible_lots(r)
        if not lots:
            break                                              # ขายหมดแล้ว
        for lot in lots:
            valuator.observe(lot)                              # เรียนผลวัดที่เพิ่งมาถึง
        rounds_left = market.n_rounds - r + 1                  # รวมรอบนี้
        offers = plan_offers(lots, market.public_buyers(), valuator, learner, mode, rounds_left,
                             wait_for_data=wait, fixed_markup=fixed)
        if verbose:
            print(f"\n--- รอบ {r} --- ล็อตเหลือ {len(lots)} (ยังไม่มีผลวัด {sum(l['moisture'] is None for l in lots)})")
            submit(offers)                                     # DRY_RUN: แค่พิมพ์
        for res in market.resolve(offers):
            o = res["offer"]
            if fixed is None:
                learner.update(o["learn_key"], o["markup"], res["sold"])
            if res["sold"]:
                lot_scores.append(score_sold(mode, o["price_per_kg"], res["true_value"], o["weight"]))
                sold_rounds.append(r)
            if verbose:
                print(f"   ผล: ล็อต {o['lot_id']} → {o['buyer_id']} "
                      f"{'✅ ขายได้' if res['sold'] else '❌ ไม่ขาย'} (มูลค่าจริง {res['true_value']:.1f})")

    for lot in market.lots:                                    # จบเกม: ล็อตที่เหลือ
        if not lot["sold"]:
            lot_scores.append(score_unsold(mode, lot["true_value"], lot["weight"]))
    n = len(market.lots)
    avg_round = sum(sold_rounds) / len(sold_rounds) if sold_rounds else float("nan")
    return total_score(mode, lot_scores, n), len(sold_rounds), avg_round, n


def compare(params, n_games=300):
    for mode in MODES:
        print(f"\n=== สูตรคะแนนแบบ '{mode}' · {n_games} เกม ===")
        print(f"{'กลยุทธ์':<38}{'คะแนนเฉลี่ย':>12}{'ขายได้':>9}{'รอบที่ขาย':>11}")
        for name in STRATEGIES:
            tot = sold = rnd = lots = 0.0
            for g in range(n_games):
                s, k, ar, n = play(params, name, mode, seed=config.RANDOM_SEED + g)
                tot += s; sold += k; lots += n
                rnd += 0 if ar != ar else ar                   # ar != ar คือ NaN (เกมที่ขายไม่ได้เลย)
            print(f"{name:<38}{tot / n_games:>12.2f}{sold / lots:>9.0%}{rnd / n_games:>11.1f}")


if __name__ == "__main__":
    params, source = load_params()
    print(f"ค่าสูตรมูลค่ามาจาก: {source}")
    print(f"DRY_RUN = {config.DRY_RUN} (ไม่มีการส่งอะไรออกไปจริง)")
    if "--demo" in sys.argv:
        s, k, ar, n = play(params, TEAM_STRATEGY, config.SCORE_MODE,
                           seed=config.RANDOM_SEED, verbose=True)
        print(f"\nสรุป: ขายได้ {k}/{n} ล็อต · คะแนน ({config.SCORE_MODE}) = {s:.2f}")
    else:
        compare(params)

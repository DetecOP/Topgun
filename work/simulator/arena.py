# arena.py · สนามแข่งหลายทีม: เรา 1 ทีม + คู่แข่งจำลองที่สุ่มมาจาก 86 กลยุทธ์ ขายให้ผู้ซื้อกลุ่มเดียวกัน
#
# รัน (จากโฟลเดอร์ work):
#   .venv\Scripts\python.exe simulator\arena.py              ← 200 ทัวร์นาเมนต์ต่อสูตรคะแนน
#   .venv\Scripts\python.exe simulator\arena.py 50           ← จำนวนทัวร์นาเมนต์ที่ต้องการ
#
# ⚠️ กติกาสนามแต่งเอง (ยังไม่ทราบของจริง):
# - 16 ทีมต่อตลาด, ทีมละ 6 ล็อต, 8 รอบ, ผู้ซื้อ 4 ราย รับได้รายละ 1–3 ล็อตต่อรอบ (ของมากกว่าที่ผู้ซื้อรับได้)
# - ปิดซองแบบผู้ชนะจ่ายตามราคาที่เสนอ: ผู้ซื้อรับข้อเสนอที่ "ราคาลับของตัวเอง − ราคาเสนอ" สูงสุดก่อน
# - ผลวัดของแต่ละล็อตมาถึงตอนรอบสุ่ม 2–5 (ทุกทีมเจอเหมือนกัน)
# - ทุกทีมเสนอได้ล็อตละ 1 ข้อเสนอต่อรอบ (เพดานเท่ากันทุกทีม)

import random
import statistics as st
import sys

import config
from agent_core import LotMemory, plan_offers
from competitors import FAMILY_WEIGHT, POOL
from market_sim import SIZES
from pricer import BuyerPriceLearner
from scoring import MODES, score_sold, score_unsold, total_score
from valuation import PlaceholderValuator, load_params, placeholder_value_per_kg

N_TEAMS, N_LOTS, N_ROUNDS, N_BUYERS = 16, 6, 8, 4


class LearnerAgent:
    """agent ที่ใช้โมเดลแบบของเรา (ใช้ทั้งเป็น 'เรา' และเป็นคู่แข่งทีมเก่ง)"""

    def __init__(self, name, family, version="v2", wait=False, fixed=None, mode=None,
                 lot_step=None, presell_z=None, skip_negative=None, **learner_kw):
        self.skip_negative = skip_negative                     # None = ใช้ค่าใน config
        self.name, self.family = name, family
        self.version, self.wait, self.fixed, self.mode = version, wait, fixed, mode
        self.lot_step = lot_step                               # None = ใช้ค่าใน config
        self.presell_z = presell_z                             # None = ใช้ค่าใน config
        self.learner_kw = learner_kw

    def setup(self, params, seed, n_rounds):
        self.valuator = PlaceholderValuator(params)
        self.lot_memory = LotMemory(0 if self.version == "v1" else self.lot_step, mode=self.mode)
        if self.version == "v1":
            self.learner = BuyerPriceLearner(seed=seed, pool_weight=0.0, horizon_aware=False,
                                             informative_prior=False)
        else:
            self.learner = BuyerPriceLearner(seed=seed, **self.learner_kw)

    def decide(self, lots, buyers, round_no, rounds_left):
        for lot in lots:
            self.valuator.observe(lot)
        old = (config.PRESELL_MARGIN_Z, config.SKIP_NEGATIVE_GAIN)
        if self.presell_z is not None:
            config.PRESELL_MARGIN_Z = self.presell_z           # ใช้ค่าเฉพาะของ agent นี้ชั่วคราว
        if self.skip_negative is not None:
            config.SKIP_NEGATIVE_GAIN = self.skip_negative
        try:
            return plan_offers(lots, buyers, self.valuator, self.learner, self.mode, rounds_left,
                               wait_for_data=self.wait, fixed_markup=self.fixed,
                               lot_memory=self.lot_memory)
        finally:
            config.PRESELL_MARGIN_Z, config.SKIP_NEGATIVE_GAIN = old

    def feedback(self, results):
        if self.fixed is not None:
            return
        self.lot_memory.update(results)
        for res in results:
            o = res["offer"]
            self.learner.update(o.get("learn_key", o["buyer_id"]), o["markup"], res["sold"])


def full_pool():
    """คู่แข่งทั้งหมด = กฎ 81 ตัว + ทีมที่ใช้โมเดลเรียนรู้ 5 ตัว"""
    pool = [(n, f, mk) for n, f, mk in POOL]
    extra = [
        ("bandit-v1-คิดแบบกำไร", "bandit", dict(version="v1", mode="diff")),
        ("bandit-v1-คิดแบบอัตราส่วน", "bandit", dict(version="v1", mode="ratio")),
        ("bandit-v1-รอวัด", "bandit", dict(version="v1", mode="diff", wait=True)),
        ("ทีมเก่งแบบเรา-v2", "mirror", dict(version="v2", mode="diff")),
        ("ทีมเก่งแบบเรา-v2-รอวัด", "mirror", dict(version="v2", mode="diff", wait=True)),
    ]
    for n, f, kw in extra:
        pool.append((n, f, lambda n=n, f=f, kw=kw: LearnerAgent(n, f, **kw)))
    return pool


def weights(pool):
    """น้ำหนักสุ่มของแต่ละตัว = น้ำหนักกลุ่ม ÷ จำนวนตัวในกลุ่ม"""
    count = {}
    for _, f, _ in pool:
        count[f] = count.get(f, 0) + 1
    return [FAMILY_WEIGHT[f] / count[f] for _, f, _ in pool]


def make_lots(rng, params, team):
    lots = []
    for i in range(N_LOTS):
        true = {"moisture": rng.uniform(10.0, 14.5), "defect_pct": rng.uniform(2, 18),
                "size": rng.choice(SIZES)}
        lots.append({
            "id": f"{team}-{chr(65 + i)}", "weight": rng.choice([50, 80, 100, 120, 150, 200]),
            "true_value": placeholder_value_per_kg(params, **true),
            "measured": {"moisture": round(true["moisture"] + rng.gauss(0, 0.3), 1),
                         "defect_pct": round(max(0, true["defect_pct"] + rng.gauss(0, 1.5)), 1),
                         "size": true["size"]},
            "reveal_round": rng.randint(2, 5), "sold": False, "team": team})
    return lots


def visible(lots, r):
    out = []
    for l in lots:
        if l["sold"]:
            continue
        k = r >= l["reveal_round"]
        m = l["measured"]
        out.append({"id": l["id"], "weight": l["weight"],
                     "moisture": m["moisture"] if k else None,
                     "defect_pct": m["defect_pct"] if k else None,
                     "size": m["size"] if k else None})
    return out


def run_tournament(params, agents, seed, modes=MODES):
    """เล่น 1 ตลาด คืน {mode: [คะแนนของทีม 0..n-1]}"""
    rng = random.Random(seed)
    team_lots = [make_lots(rng, params, t) for t in range(len(agents))]
    lot_by_id = {l["id"]: l for lots in team_lots for l in lots}
    buyers = [{"id": f"B{j + 1}", "max_moisture": rng.choice([None, 13.0, 13.5]),
               "max_defect": rng.choice([None, 12, 15]),
               "_mult": rng.uniform(0.95, 1.25), "_cap": rng.choice([1, 2, 3])}
              for j in range(N_BUYERS)]
    public = [{k: v for k, v in b.items() if not k.startswith("_")} for b in buyers]
    for t, ag in enumerate(agents):
        ag.setup(params, seed * 100 + t, N_ROUNDS)
    sold_price = {}

    for r in range(1, N_ROUNDS + 1):
        rounds_left = N_ROUNDS - r + 1
        bids = {b["id"]: [] for b in buyers}
        offers_of = []
        for t, ag in enumerate(agents):
            seen = set()
            offers = []
            for o in ag.decide(visible(team_lots[t], r), public, r, rounds_left):
                if o["lot_id"] in seen or lot_by_id[o["lot_id"]]["team"] != t:
                    continue                                   # ล็อตละ 1 ข้อเสนอ และต้องเป็นล็อตของตัวเอง
                seen.add(o["lot_id"])
                offers.append(o)
            offers_of.append(offers)
            for o in offers:
                lot = lot_by_id[o["lot_id"]]
                b = next(x for x in buyers if x["id"] == o["buyer_id"])
                ok = ((b["max_moisture"] is None or lot["measured"]["moisture"] <= b["max_moisture"]) and
                      (b["max_defect"] is None or lot["measured"]["defect_pct"] <= b["max_defect"]))
                bids[b["id"]].append({"o": o, "ok": ok, "price": o["price_per_kg"],
                                      "reserve": lot["true_value"] * b["_mult"], "tie": rng.random()})
        won = set()
        for b in buyers:
            ok = [x for x in bids[b["id"]] if x["ok"] and x["price"] <= x["reserve"]]
            ok.sort(key=lambda x: (x["reserve"] - x["price"], x["tie"]), reverse=True)
            for x in ok[: b["_cap"]]:
                won.add(x["o"]["lot_id"])
                lot_by_id[x["o"]["lot_id"]]["sold"] = True
                sold_price[x["o"]["lot_id"]] = x["price"]
        for t, ag in enumerate(agents):
            ag.feedback([{"offer": o, "sold": o["lot_id"] in won} for o in offers_of[t]])

    out = {}
    for mode in modes:
        scores = []
        for lots in team_lots:
            s = [score_sold(mode, sold_price[l["id"]], l["true_value"], l["weight"]) if l["sold"]
                 else score_unsold(mode, l["true_value"], l["weight"]) for l in lots]
            scores.append(total_score(mode, s, len(lots)))
        out[mode] = scores
    return out


def rank_of(scores, i):
    """อันดับของทีม i (1 = ดีที่สุด)"""
    return 1 + sum(1 for s in scores if s > scores[i])


def evaluate(params, our_factories, n_tour, modes=MODES, seed0=1000):
    """ให้ "เรา" หลายแบบลงแข่งกับชุดคู่แข่งเดียวกัน (จับคู่) คืนสถิติอันดับ + ตารางคู่แข่ง"""
    pool = full_pool()
    w = weights(pool)
    stats = {name: {m: [] for m in modes} for name in our_factories}
    rival = {}                                                # ชื่อคู่แข่ง → (family, [อันดับ])
    for k in range(n_tour):
        rng = random.Random(seed0 + k)
        picks = []
        while len(picks) < N_TEAMS - 1:                       # สุ่มคู่แข่งไม่ซ้ำตามน้ำหนัก
            i = rng.choices(range(len(pool)), weights=w)[0]
            if i not in picks:
                picks.append(i)
        for name, make_ours in our_factories.items():
            for mode in modes:
                agents = [make_ours(mode)] + [pool[i][2]() for i in picks]
                res = run_tournament(params, agents, seed0 + k, modes=(mode,))[mode]
                stats[name][mode].append(rank_of(res, 0))
                if name == next(iter(our_factories)):        # เก็บอันดับคู่แข่งจากสนามของ "เรา" ตัวแรก
                    for j, i in enumerate(picks, start=1):
                        rival.setdefault(pool[i][0], (pool[i][1], {m: [] for m in modes}))[1][mode].append(
                            rank_of(res, j))
    return stats, rival


def ours(mode, **kw):
    return LearnerAgent("เรา", "เรา", mode=mode, **kw)


OUR_VARIANTS = {
    "เรา v2 (ขายล่วงหน้า)": lambda mode: ours(mode),
    "เรา v1": lambda mode: ours(mode, version="v1"),
    "เรา v2 รอผลวัด": lambda mode: ours(mode, wait=True),
    "เรา บวก 8% คงที่": lambda mode: ours(mode, fixed=0.08),
}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    config.MAX_OFFERS_PER_ROUND, config.MAX_KG_PER_ROUND = 99, 10 ** 9   # เพดานเท่ากันทุกทีม (ล็อตละ 1 ข้อเสนอ)
    params, src = load_params()
    pool = full_pool()
    print(f"คู่แข่งทั้งหมด {len(pool)} กลยุทธ์ · สนามละ {N_TEAMS} ทีม · {n} ทัวร์นาเมนต์ต่อสูตร · ค่าสูตรจาก {src}")
    stats, rival = evaluate(params, OUR_VARIANTS, n)
    for mode in MODES:
        print(f"\n=== สูตรคะแนน '{mode}' · อันดับของเรา (เต็ม {N_TEAMS} ทีม, 1 = ชนะ) ===")
        print(f"{'แบบของเรา':<24}{'อันดับเฉลี่ย':>12}{'ติดท็อป3':>10}{'ที่ 1':>8}")
        for name, s in stats.items():
            rk = s[mode]
            print(f"{name:<24}{st.mean(rk):>12.2f}{sum(r <= 3 for r in rk) / len(rk):>10.0%}"
                  f"{sum(r == 1 for r in rk) / len(rk):>8.0%}")
        fam = {}
        for nm, (f, d) in rival.items():
            fam.setdefault(f, []).extend(d[mode])
        print("  กลุ่มคู่แข่ง (อันดับเฉลี่ย, น้อย = เก่ง):",
              " · ".join(f"{f} {st.mean(v):.1f}" for f, v in sorted(fam.items(), key=lambda x: st.mean(x[1]))))
        top = sorted(((st.mean(d[mode]), nm, len(d[mode])) for nm, (f, d) in rival.items() if len(d[mode]) >= 10))[:5]
        print("  คู่แข่งที่เก่งที่สุด 5 อันดับ:", " · ".join(f"{nm} ({a:.1f})" for a, nm, _ in top))


if __name__ == "__main__":
    main()

"""ทดสอบหลายกลยุทธ์พร้อมกัน (ออฟไลน์ · ไม่ต่อเน็ต · ใช้ทุก CPU)

    python sweep.py                      # ทั้ง 2 โหมด · 20 seed
    python sweep.py --seeds 40 --noise 0.5
    python sweep.py --mode solo          # หรือ arena

โหมด
  solo  : แต่ละกลยุทธ์ลงตลาดคนเดียว (+ คู่แข่งจำลอง) · seed เดียวกัน → เทียบกันตรงๆ
  arena : ทุกกลยุทธ์ลงตลาดเดียวกันพร้อมกัน แย่งผู้ซื้อกันเอง (+ คู่แข่งจำลอง) · ล็อตเดียวกันทุกทีม (เหมือนกติกาวันที่ 18)
          → ตอบคำถาม "ถ้ามีทีมคิดเหมือนเรา / ลอกกลยุทธ์เรา จะเป็นอย่างไร"

เพิ่มกลยุทธ์: แก้ VARIANTS ด้านล่าง (ปรับค่าใน playbook / ตัวคูณ / ปริมาณ)
⚠️ โลกจำลองเป็นค่าสมมติ (ดู mock_market.py) — ใช้จัดอันดับแนวคิด ไม่ใช่ทำนาย PR จริง
"""
import copy
import random
import statistics as st
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import market_model as mmod          # noqa: E402
import mock_market as mm             # noqa: E402
import playbook as pb                # noqa: E402
import strategy                      # noqa: E402
import strategy_starter              # noqa: E402
from appraisal import estimate_lots, true_value   # noqa: E402
from memory import Memory            # noqa: E402

TYPES = ("SPECIALTY", "COMMERCIAL", "INSTANT")

# name -> {"patch": {(module, attr): value}, "shift": ±ratio ทุกประเภท, "volume": ตัวคูณปริมาณ, "starter": True}
VARIANTS = {
    "v2 (ปัจจุบัน)": {},
    "starter เดิม": {"starter": True},
    "ตั้งสูง +0.02": {"shift": +0.02},
    "ตัดราคา −0.02": {"shift": -0.02},
    "ยัดที่เดียว": {"patch": {(pb, "RFQ_SHARE"): {k: 1.0 for k in pb.RFQ_SHARE}}},
    "ไม่มีบันได/สุ่ม": {"patch": {(pb, "LADDER"): [0.0], (pb, "JITTER"): 0.0}},
    "หยั่งมาก 50%": {"patch": {(pb, "PHASES"): {**pb.PHASES, "early": {"pace": 1.15, "explore": 0.5},
                                                "mid": {"pace": 1.35, "explore": 0.3}}}},
    "ขายเร็ว ×1.3": {"volume": 1.3},
    "ขายช้า ×0.8": {"volume": 0.8},
    "ไม่มีโหมดแรงกดดัน": {"patch": {(pb, "PRESSURE_MODES"): {k: pb.PRESSURE_MODES["normal"] for k in pb.PRESSURE_MODES}}},
    "พื้นราคาต่ำ": {"patch": {(pb, "FLOOR"): {"SPECIALTY": 0.95, "COMMERCIAL": 0.90, "INSTANT": 0.86}}},
}


@contextmanager
def patched(v: dict):
    saved = []
    for (mod, attr), val in (v.get("patch") or {}).items():
        saved.append((mod, attr, getattr(mod, attr)))
        setattr(mod, attr, copy.deepcopy(val))
    try:
        yield
    finally:
        for mod, attr, val in reversed(saved):
            setattr(mod, attr, val)


class Team:
    def __init__(self, name, v, fm, rules, tmp):
        self.name, self.v = name, v
        self.lots = copy.deepcopy(fm.lots)
        self.tv = estimate_lots(rules, self.lots)
        self.memory = Memory(Path(tmp) / f"{abs(hash(name))}.json")
        self.memory.save = lambda: None                    # ไม่ต้องเขียนไฟล์ระหว่างจำลอง
        self.last, self.revenue, self.basis = None, 0.0, {}
        self.salt = random.Random(name).random()

    def state(self, fm, n, cap):
        label = next(c["label"] for c in mm.CALENDAR if int(c["rounds"].split("-")[0]) <= n <= int(c["rounds"].split("-")[-1]))
        return {"market": "mock", "phase": "ROUND_OPEN", "paused": False, "seconds_left": 200,
                "round": {"round_id": f"R{n}", "kind": "real", "number": n, "of": mm.RULES["timeline"]["rounds"],
                          "counts_for_score": True, "calendar": label},
                "lots": [{**l, "kg_available": l["kg_remaining"], "kg_in_open_offers": 0} for l in self.lots],
                "rfqs": [{k: x for k, x in r.items() if not k.startswith("_")} for r in fm.rfqs],
                "my_open_offers": [], "round_capacity_kg": cap, "capacity_left_kg": cap,
                "last_results": self.last, "appraisal_submitted": True, "salvage_ratio": 0.8}

    def decide(self, state):
        rid = state["round"]["round_id"]
        rng = random.Random(f"{self.salt}-{rid}")
        self.memory.record_results(self.last)
        if self.v.get("starter"):
            ctx = strategy_starter.Context(mm.RULES, mm.CALENDAR, self.tv, rng, self.memory, None, 200)
            with patched(self.v):
                offers, _ = strategy_starter.decide(state, ctx)
            basis = self.tv
        else:
            shift = self.v.get("shift", 0.0)
            ctx = strategy.Context(mm.RULES, mm.CALENDAR, self.tv, rng, self.memory, None, 200,
                                   adjust={t: shift for t in TYPES} if shift else {},
                                   volume=self.v.get("volume", 1.0))
            with patched(self.v):
                offers, _ = strategy.decide(state, ctx)
            basis = {**self.tv, **getattr(ctx, "basis", {})}
        self.memory.record_sent(rid, offers, state, basis)
        return offers

    def pr(self, true):
        tot = sum(l["kg_total"] * true[l["lot_id"]]["tv"] for l in self.lots)
        rem = sum(l["kg_remaining"] * true[l["lot_id"]]["tv"] for l in self.lots)
        return (self.revenue + 0.8 * rem) / tot


def play(seed: int, names: list[str], noise: float) -> dict:
    """หนึ่งตลาด: ทีมใน names เล่นพร้อมกัน → {name: PR}"""
    fm = mm.FakeMarket(seed, noise)
    tmp = tempfile.mkdtemp(prefix="sweep-")
    teams = [Team(n, VARIANTS[n], fm, mm.RULES, tmp) for n in names]
    rng = random.Random(seed * 7919)
    total = mm.RULES["timeline"]["rounds"]
    for n in range(1, total + 1):
        fm._open(n)
        late = n >= total - 2
        offers = {t.name: t.decide(t.state(fm, n, fm.cap)) for t in teams}
        results = {t.name: [] for t in teams}
        summary = []
        for rfq in fm.rfqs:
            ty, ceil = rfq["buyer_type"], rfq["_ceil"]
            book = [(mm.competitor_ratio(rng, ty, late), 60, None, None)
                    for _ in range(int(rfq["bags"] * (mm.CROWD[ty] + (0.6 if late else 0))))]
            for t in teams:
                for o in offers[t.name]:
                    if o["rfq_id"] != rfq["rfq_id"]:
                        continue
                    q, sp = fm.true[o["lot_id"]]["q"], rfq["spec"]
                    if not (q["defect_pct"] <= sp["max_defect_pct"] and q["moisture_pct"] <= sp["max_moisture_pct"]
                            and (sp["min_screen"] is None or q["screen"] >= sp["min_screen"])):
                        results[t.name].append({**o, "status": "SPEC_MISMATCH", "filled_kg": 0})
                        continue
                    book.append((o["price_per_kg"] / fm.true[o["lot_id"]]["tv"] + rng.uniform(0, 1e-6), o["kg"], o, t))
            book.sort(key=lambda x: x[0])
            left, bought = rfq["kg"], 0
            for ratio, kg, o, t in book:
                if ratio > ceil:
                    if o:
                        results[t.name].append({**o, "status": "ABOVE_LIMIT", "filled_kg": 0})
                    continue
                fill = min(kg, left)
                left -= fill
                bought += fill
                if o:
                    stt = "ACCEPTED" if fill == kg else ("PARTIAL" if fill > 0 else "OUTBID")
                    results[t.name].append({**o, "status": stt, "filled_kg": fill})
                    if fill:
                        t.revenue += fill * o["price_per_kg"]
                        next(l for l in t.lots if l["lot_id"] == o["lot_id"])["kg_remaining"] -= fill
            summary.append({"rfq_id": rfq["rfq_id"], "buyer": rfq["buyer"], "buyer_type": ty, "wanted_kg": rfq["kg"],
                            "bought_kg": bought, "offers": len(book)})
        for t in teams:
            t.last = {"round_id": f"R{n}", "kind": "real", "my_offers": results[t.name], "market_summary": summary}
    for t in teams:
        t.memory.record_results(t.last)
    return {t.name: round(t.pr(fm.true), 4) for t in teams}


def _job(args):
    return args, play(*args)


def table(title: str, per_seed: list[dict]):
    names = list(per_seed[0])
    rows = []
    for n in names:
        prs = [s[n] for s in per_seed]
        wins = sum(1 for s in per_seed if s[n] == max(s.values()))
        rows.append((st.mean(prs), n, min(prs), st.pstdev(prs), wins))
    print(f"\n{title}")
    print(f"  {'อันดับ':<6}{'กลยุทธ์':<20}{'PR เฉลี่ย':>10}{'แย่สุด':>9}{'SD':>8}{'ชนะ(seed)':>11}")
    for i, (mean, n, mn, sd, w) in enumerate(sorted(rows, reverse=True), 1):
        print(f"  {i:<6}{n:<20}{mean:>10.4f}{mn:>9.4f}{sd:>8.4f}{w:>11}")
    se = st.mean(r[3] for r in rows) / len(per_seed) ** 0.5
    print(f"  (ความต่างของค่าเฉลี่ยที่น้อยกว่า ~{2 * se:.4f} ถือว่ายังแยกไม่ออก)")


def main():
    arg = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
    n, noise, mode = arg("--seeds", 20), arg("--noise", 0.3), arg("--mode", "both")
    seeds = list(range(301, 301 + n))
    names = list(VARIANTS)
    print(f"ตลาดจำลอง (ค่าสมมติ) · {len(names)} กลยุทธ์ · {n} seed · noise {noise}")
    with ProcessPoolExecutor() as ex:
        if mode in ("both", "solo"):
            jobs = [(s, [name], noise) for s in seeds for name in names]
            got = {}
            for (s, nm, _), res in ex.map(_job, jobs):
                got.setdefault(s, {}).update(res)
            table("โหมดเดี่ยว: แต่ละกลยุทธ์ลงตลาดคนเดียว", [got[s] for s in seeds])
        if mode in ("both", "arena"):
            res = [r for _, r in ex.map(_job, [(s, names, noise) for s in seeds])]
            table("โหมดสนามรวม: ทุกกลยุทธ์แย่งผู้ซื้อในตลาดเดียวกัน", res)


if __name__ == "__main__":
    main()

"""จำลองตลาดแข่งวันที่ 18: 56 ทีม · ล็อตเดียวกันทุกทีม · มี Specialty · จำกัด capacity ต่อรอบ (ออฟไลน์)

    python compete.py                       # ทุกสถานการณ์คู่แข่ง × เพดาน Specialty 3 แบบ · 12 seed
    python compete.py --seeds 20

ทีมคู่แข่งเป็น "agent ที่คนเขียน" หลายแบบ (สัดส่วนเป็นสมมติฐาน) ไม่มีบอทตลาดฝึกปน:
  starter เดิม (×1.00) · starter แก้ตัวคูณต่อประเภท (สไลด์ 25 ข้อ ①) · ตัดราคา · ตั้งสูง · ขายเร็ว · ลอกแบบเรา (v2)
ความต้องการรวมของผู้ซื้อ ≈ DEMAND × ของที่ทุกทีมมีต่อรอบ

⚠️ ทุกตัวเลขในโลกนี้เป็นค่าสมมติ (เพดาน, สเปก Specialty, สัดส่วนทีม, ความต้องการ) — ใช้ดูว่ากลยุทธ์ "ทนทาน" แค่ไหน
   ในหลายแบบของคู่แข่ง ไม่ใช่ทำนายอันดับจริง
"""
import copy
import random
import statistics as st
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import mock_market as mm             # noqa: E402
import strategy_starter              # noqa: E402
from sweep import VARIANTS, Team     # noqa: E402

VARIANTS = dict(VARIANTS)
VARIANTS["starter แก้ตัวคูณ"] = {"starter": True, "patch": {(strategy_starter, "MARKUP"):
                                                             {"SPECIALTY": 1.15, "COMMERCIAL": 0.985, "INSTANT": 0.95}}}

# สัดส่วนคู่แข่ง 55 ทีม (สมมติฐาน) — เราคือ "v2 (ปัจจุบัน)" อีก 1 ทีม
FIELDS = {
    "คนส่วนใหญ่ใช้ starter": {"starter เดิม": 30, "starter แก้ตัวคูณ": 15, "ตัดราคา −0.02": 4, "ตั้งสูง +0.02": 3, "ขายเร็ว ×1.3": 3},
    "คนแก้ตัวคูณเป็นส่วนใหญ่": {"starter เดิม": 10, "starter แก้ตัวคูณ": 30, "ตัดราคา −0.02": 8, "ตั้งสูง +0.02": 4, "ขายเร็ว ×1.3": 3},
    "คู่แข่งเก่งเหมือนเรา": {"starter เดิม": 10, "starter แก้ตัวคูณ": 15, "ตัดราคา −0.02": 10, "ขายเร็ว ×1.3": 5,
                            "v2 (ปัจจุบัน)": 15},
}
SPECIALTY_CEILING = {"Specialty จ่ายต่ำ ×1.10": 1.10, "Specialty กลาง ×1.25": 1.25, "Specialty สูง ×1.40": 1.40}
DEMAND = 0.9          # ผู้ซื้อต้องการรวม ≈ 90% ของที่ทุกทีมมีต่อรอบ (สมมติ)


def play(seed: int, field: dict, spec_ceil: float, noise: float = 0.3) -> dict:
    buyers = [b if b[2] != "SPECIALTY" else (b[0], b[1], b[2], spec_ceil) for b in mm.BUYERS]
    mm.BUYERS[:] = buyers
    fm = mm.FakeMarket(seed, noise)
    rules = copy.deepcopy(mm.RULES)
    total_kg = sum(l["kg_total"] for l in fm.lots)
    n_rounds = rules["timeline"]["rounds"]
    cap = -(-int(1.5 * total_kg / n_rounds) // 60) * 60
    tmp = tempfile.mkdtemp(prefix="compete-")
    names = ["เรา"] + [f"{k}#{i}" for k, n in field.items() for i in range(n)]
    teams = []
    for nm in names:
        base = "v2 (ปัจจุบัน)" if nm == "เรา" else nm.split("#")[0]
        t = Team(nm, VARIANTS[base], fm, rules, tmp)
        teams.append(t)
    n_teams = len(teams)
    rng = random.Random(seed * 104729)
    team_bags_per_round = total_kg / 60 / n_rounds * n_teams
    for n in range(1, n_rounds + 1):
        fm._open(n)
        # ขยาย RFQ ให้ความต้องการรวม ≈ DEMAND × ของทุกทีมต่อรอบ (× demand_weight ของ calendar ที่ _open ใส่แล้ว)
        base_bags = sum(r["bags"] for r in fm.rfqs) or 1
        scale = DEMAND * team_bags_per_round / base_bags * (base_bags / 8 / 10.5)
        for r in fm.rfqs:
            r["bags"] = max(1, int(round(r["bags"] * scale)))
            r["kg"] = r["bags"] * 60
        offers = {}
        for t in teams:
            st_ = t.state(fm, n, cap)
            offers[t.name] = t.decide(st_)
        results = {t.name: [] for t in teams}
        summary = []
        by_rfq = {}
        for t in teams:
            for o in offers[t.name]:
                by_rfq.setdefault(o["rfq_id"], []).append((o, t))
        for rfq in fm.rfqs:
            ty, ceil = rfq["buyer_type"], rfq["_ceil"]
            book = []
            for o, t in by_rfq.get(rfq["rfq_id"], []):
                q, sp = fm.true[o["lot_id"]]["q"], rfq["spec"]
                if not (q["defect_pct"] <= sp["max_defect_pct"] and q["moisture_pct"] <= sp["max_moisture_pct"]
                        and (sp["min_screen"] is None or q["screen"] >= sp["min_screen"])):
                    results[t.name].append({**o, "status": "SPEC_MISMATCH", "filled_kg": 0})
                    continue
                book.append((o["price_per_kg"] / fm.true[o["lot_id"]]["tv"] + rng.uniform(0, 1e-6), o, t))
            book.sort(key=lambda x: x[0])
            left, bought = rfq["kg"], 0
            for ratio, o, t in book:
                if ratio > ceil:
                    results[t.name].append({**o, "status": "ABOVE_LIMIT", "filled_kg": 0})
                    continue
                fill = min(o["kg"], left)
                left -= fill
                bought += fill
                stt = "ACCEPTED" if fill == o["kg"] else ("PARTIAL" if fill > 0 else "OUTBID")
                results[t.name].append({**o, "status": stt, "filled_kg": fill})
                if fill:
                    t.revenue += fill * o["price_per_kg"]
                    next(l for l in t.lots if l["lot_id"] == o["lot_id"])["kg_remaining"] -= fill
            summary.append({"rfq_id": rfq["rfq_id"], "buyer": rfq["buyer"], "buyer_type": ty, "wanted_kg": rfq["kg"],
                            "bought_kg": bought, "offers": len(book)})
        for t in teams:
            t.last = {"round_id": f"R{n}", "kind": "real", "my_offers": results[t.name], "market_summary": summary}
    prs = sorted(((round(t.pr(fm.true), 4), t.name) for t in teams), reverse=True)
    rank = next(i for i, (_, nm) in enumerate(prs, 1) if nm == "เรา")
    by_kind = {}
    for pr, nm in prs:
        by_kind.setdefault("เรา" if nm == "เรา" else nm.split("#")[0], []).append(pr)
    return {"rank": rank, "n": n_teams, "pr": dict((nm, pr) for pr, nm in prs)["เรา"],
            "kinds": {k: st.mean(v) for k, v in by_kind.items()}}


def _job(a):
    return a, play(*a)


def main():
    n = int(sys.argv[sys.argv.index("--seeds") + 1]) if "--seeds" in sys.argv else 12
    seeds = list(range(501, 501 + n))
    jobs = [(s, field, ceil) for fname, field in FIELDS.items() for cname, ceil in SPECIALTY_CEILING.items() for s in seeds]
    out = {}
    with ProcessPoolExecutor() as ex:
        for (s, field, ceil), r in ex.map(_job, jobs):
            fname = next(k for k, v in FIELDS.items() if v is field or v == field)
            cname = next(k for k, v in SPECIALTY_CEILING.items() if v == ceil)
            out.setdefault((fname, cname), []).append(r)
    print(f"จำลองตลาดแข่ง (ค่าสมมติ) · 56 ทีม · ล็อตเดียวกัน · 8 รอบ · capacity 1.5× · {n} seed ต่อช่อง")
    for fname in FIELDS:
        print(f"\n■ คู่แข่ง: {fname}")
        print(f"  {'เพดาน Specialty':<24}{'PR เรา':>8}{'อันดับเฉลี่ย':>13}{'ดีสุด':>7}{'แย่สุด':>7}{'Top5':>6}   PR เฉลี่ยของแต่ละแบบ")
        for cname in SPECIALTY_CEILING:
            rs = out[(fname, cname)]
            kinds = {}
            for r in rs:
                for k, v in r["kinds"].items():
                    kinds.setdefault(k, []).append(v)
            ks = " · ".join(f"{k} {st.mean(v):.3f}" for k, v in sorted(kinds.items(), key=lambda kv: -st.mean(kv[1])))
            ranks = [r["rank"] for r in rs]
            print(f"  {cname:<24}{st.mean(r['pr'] for r in rs):>8.3f}{st.mean(ranks):>13.1f}{min(ranks):>7}{max(ranks):>7}"
                  f"{sum(1 for x in ranks if x <= 5):>6}   {ks}")


if __name__ == "__main__":
    main()

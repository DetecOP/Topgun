"""วิเคราะห์ log หลายเกม (ตลาดฝึก) → เทียบชุดทดลอง (สวิตช์ใน flags.py) · PR หายไปตรงไหน · ผู้ซื้อ/รอบ/ขั้นบันได

    python analyze_logs.py                        # ตารางเทียบทุกชุดทดลอง + รายละเอียดเมื่อมีชุดเดียว
    python analyze_logs.py --detail               # รายละเอียดทุกชุด
    python analyze_logs.py --variant baseline     # รายละเอียดเฉพาะชุดนั้น
    python analyze_logs.py --dir PATH

ชุดทดลองแยกด้วยป้าย variant ใน log (ตั้งจากสวิตช์ที่เปิด หรือ AGENT_TAG) · เกมก่อนมีสวิตช์ = "ไม่มีป้าย"

แยก PR ที่หาย (1 − PR) เป็น:
  ขายต่ำกว่ามูลค่าจริง = Σ กก.ที่ขาย × (TV จริง − ราคา) ÷ TV รวม
  ของเหลือ          = 0.20 × Σ กก.ที่เหลือ × TV จริง ÷ TV รวม   (แยก: ล็อตขายไม่ได้ / ล็อตที่ขายได้แต่เหลือ)
"""
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path


def log_files(logs: Path) -> list[Path]:
    """logs/decisions.jsonl (รุ่นเก่า/ตลาดแข่ง) + logs/runs/*.jsonl (ตลาดฝึก รันละไฟล์) เรียงตามเวลา"""
    files = [logs / "decisions.jsonl"] if (logs / "decisions.jsonl").exists() else []
    return files + sorted((logs / "runs").glob("*.jsonl"))


def load(logs: Path):
    games = []
    for fp in log_files(logs):
        games += load_file(fp)
    return games


def load_file(fp: Path):
    ev = []
    for l in fp.read_text(encoding="utf-8").splitlines():
        try:
            ev.append(json.loads(l))
        except ValueError:
            pass                                  # บรรทัดที่เขียนค้างตอนกด Ctrl+C
    games, cur = [], None
    for e in ev:
        if e["event"] == "new_game":
            cur = {"new": e, "offers": {}, "results": {}, "opens": {}, "closed": None, "reveal": None,
                   "variant": e.get("variant") or "ไม่มีป้าย", "appraised": False}
            games.append(cur)
        elif cur is None:
            continue
        elif e["event"] in ("offers_sent", "offers_replaced"):
            plan = {}
            for n in e.get("notes") or []:
                if isinstance(n, dict) and "plan" in n:
                    plan = {(p["lot_id"], p["rfq_id"]): p for p in n["plan"]}
            cur["offers"][e["round"]] = {"offers": e.get("offers", []), "plan": plan, "meta": e.get("meta", {})}
        elif e["event"] == "round_results":
            cur["results"][e["round"]] = e["data"]
        elif e["event"] == "round_open":
            cur["opens"][e["round"]["round_id"]] = e
        elif e["event"] == "appraisal_sent":
            cur["appraised"] = True
        elif e["event"] == "market_closed":
            cur["closed"] = e
        elif e["event"] == "reveal":
            cur["reveal"] = e.get("data")
    # ใช้เฉพาะเกมที่จบ มีเฉลย และมี log รอบแบบใหม่ (round_open)
    # ไม่นับเกมที่ agent เข้ามากลางเกม (ไม่ได้ส่งประเมิน = ได้คะแนนประเมิน 0 และเล่นไม่ครบรอบ → สถิติเพี้ยน)
    games = [g for g in games if g["reveal"] and g["closed"] and g["opens"].get("R1") and g["appraised"]]
    for g in games:
        g["config"] = market_config(g)
    return games


def market_config(g) -> str:
    """ป้ายการตั้งค่าตลาด (ตลาดฝึกเปลี่ยนได้กลางวัน · เทียบได้เฉพาะเกมที่ตั้งค่าเหมือนกัน)"""
    tl = g["new"].get("timeline") or {}
    cap = g["opens"]["R1"].get("round_capacity_kg")
    code = g["new"].get("code") or "ก่อน fill1"
    return f"{tl.get('rounds', '?')} รอบ × {tl.get('open_s', '?')} วิ · capacity {'จำกัด' if cap else 'ไม่จำกัด'} · โค้ด {code}"


def game_stats(g) -> dict:
    """ตัวเลขต่อเกม: PR, อันดับ, PR ที่หาย 3 ส่วน, PR ไม่นับล็อตขายไม่ได้"""
    true = {l["lot_id"]: l["true_value_per_kg"] for l in g["reveal"]["lots"]}
    first = next(iter(g["offers"].values()), {"meta": {}})
    cls = {k: v["cls"] for k, v in (first["meta"].get("lots") or {}).items()}
    kg_total = dict(g["opens"]["R1"]["lots_kg"])
    tot = sum(kg_total[i] * true[i] for i in kg_total) or 1
    sold, gp = defaultdict(int), 0.0
    for res in g["results"].values():
        for o in res.get("my_offers", []):
            f = o.get("filled_kg", 0)
            if f:
                gp += f * (true[o["lot_id"]] - o["price_per_kg"])
                sold[o["lot_id"]] += f
    dead = live = 0.0
    for i, kg in kg_total.items():
        loss = 0.2 * max(kg - sold[i], 0) * true[i]
        if cls.get(i) == "UNSELLABLE":
            dead += loss
        else:
            live += loss
    sc = g["reveal"]["score"]
    return {"pr": sc["pr"], "rank": sc.get("rank"), "price": gp / tot, "dead": dead / tot, "live": live / tot,
            "pr_ctrl": sc["pr"] + dead / tot}


def compare(groups: dict):
    """ตารางเทียบชุดทดลอง · ตัวชี้วัดหลัก = PR ไม่นับล็อตขายไม่ได้ (ตัดโชคเรื่องล็อตออก)"""
    rows = {}
    for v, gs in groups.items():
        s = [game_stats(g) for g in gs]
        n = len(s)
        pc = [x["pr_ctrl"] for x in s]
        rows[v] = {"n": n, "pr": st.mean(x["pr"] for x in s), "pc": st.mean(pc),
                   "se": (st.pstdev(pc) / n ** 0.5) if n > 1 else 0.0,
                   "r1": sum(1 for x in s if x["rank"] == 1) / n, "t5": sum(1 for x in s if x["rank"] and x["rank"] <= 5) / n,
                   "rank": st.mean(x["rank"] for x in s if x["rank"]), "price": st.mean(x["price"] for x in s),
                   "live": st.mean(x["live"] for x in s), "dead": st.mean(x["dead"] for x in s)}
    base_name = "baseline" if "baseline" in rows else ("ไม่มีป้าย" if "ไม่มีป้าย" in rows else None)
    base = rows.get(base_name) if base_name else None   # ไม่มีชุด baseline → ใช้ 160 เกมเดิม (โค้ดเท่ากับปิดสวิตช์ทั้งหมด)
    print(f"\n=== เทียบชุดทดลอง (ตลาดฝึก) · ตัวเทียบ = {base_name or 'ไม่มี'} ===")
    print("PR* = PR ไม่นับล็อตขายไม่ได้ (ตัดโชคเรื่องล็อต) · ใช้ตัดสิน · ±SE · ดีกว่า baseline จริง = ต่าง > 2×SE รวม")
    print(f"  {'ชุด':<34}{'เกม':>5}{'PR':>8}{'PR*':>8}{'±SE':>7}{'vs base':>9}{'ที่1':>6}{'Top5':>6}{'อันดับ':>7}"
          f"{'หาย:ราคา':>10}{'หาย:เหลือ':>10}{'สรุป':>12}")
    for v, r in sorted(rows.items(), key=lambda kv: -kv[1]["pc"]):
        diff, verdict = "", ""
        if base and v != base_name:
            d = r["pc"] - base["pc"]
            se2 = (r["se"] ** 2 + base["se"] ** 2) ** 0.5
            diff = f"{d:+.4f}"
            verdict = "ดีกว่าจริง" if d > 2 * se2 else ("แย่กว่าจริง" if d < -2 * se2 else "แยกไม่ออก")
            if r["n"] < 30 or base["n"] < 30:
                verdict += "*"
        print(f"  {v:<34}{r['n']:>5}{r['pr']:>8.4f}{r['pc']:>8.4f}{r['se']:>7.4f}{diff:>9}{100 * r['r1']:>5.0f}%{100 * r['t5']:>5.0f}%"
              f"{r['rank']:>7.1f}{r['price']:>10.4f}{r['live']:>10.4f}{verdict:>12}")
    if not base:
        print("  (ยังไม่มีชุด baseline = รันโดยไม่เปิดสวิตช์ใดเลย → ยังตัดสินไม่ได้)")
    print("  * เกมน้อยกว่า 30 · ผลยังไม่นิ่ง")


def pct(a, b):
    return f"{100 * a / b:5.1f}%" if b else "   - "


def main():
    logs = Path(sys.argv[sys.argv.index("--dir") + 1]) if "--dir" in sys.argv else Path(__file__).parent / "logs"
    games = load(logs)
    print(f"ไฟล์ log: {len(log_files(logs))} ไฟล์ (logs/decisions.jsonl + logs/runs/)")
    groups = defaultdict(list)
    for g in games:
        groups[g["variant"]].append(g)
    print(f"เกมที่วิเคราะห์: {len(games)} · ชุดทดลอง: " + ", ".join(f"{k} ({len(v)})" for k, v in groups.items()))
    if not games:
        return
    by_cfg = defaultdict(lambda: defaultdict(list))
    for g in games:
        by_cfg[g["config"]][g["variant"]].append(g)
    # ตลาดตั้งค่าล่าสุดก่อน (ใกล้วันแข่งที่สุด)
    latest = {c: max(g["new"]["time"] for vs in d.values() for g in vs) for c, d in by_cfg.items()}
    for cfg in sorted(by_cfg, key=lambda c: latest[c], reverse=True):
        print(f"\n################ ตลาด: {cfg} ################")
        compare(by_cfg[cfg])
    if "--variant" in sys.argv:
        pick = [sys.argv[sys.argv.index("--variant") + 1]]
    elif "--detail" in sys.argv or len(groups) == 1:
        pick = list(groups)
    else:
        print("\nรายละเอียดรายชุด: python analyze_logs.py --variant <ชื่อชุด>   หรือ --detail")
        return
    for v in pick:
        for cfg, d in by_cfg.items():
            if v in d:
                print(f"\n################ รายละเอียด: {v} · ตลาด {cfg} ################")
                report(d[v])


def report(games):
    print(f"เกมที่วิเคราะห์: {len(games)}")

    # ---------- 1. PR / อันดับ ----------
    prs = [g["reveal"]["score"]["pr"] for g in games]
    ranks = [g["reveal"]["score"].get("rank") for g in games]
    rc = Counter(ranks)
    print("\n1) ผลรวม")
    print(f"   PR เฉลี่ย {st.mean(prs):.4f} · มัธยฐาน {st.median(prs):.4f} · SD {st.pstdev(prs):.4f} · ต่ำสุด {min(prs):.4f} · สูงสุด {max(prs):.4f}")
    print(f"   อันดับ 1: {rc[1]} เกม ({pct(rc[1], len(games))}) · Top3: {sum(rc[r] for r in (1, 2, 3))} · Top5: {sum(v for r, v in rc.items() if r and r <= 5)}"
          f" · อันดับเฉลี่ย {st.mean(r for r in ranks if r):.1f}")
    by_rank = defaultdict(list)
    for p, r in zip(prs, ranks):
        by_rank[r].append(p)
    print("   PR เฉลี่ยตามอันดับ:", " · ".join(f"#{r}: {st.mean(v):.3f} (n={len(v)})" for r, v in sorted(by_rank.items())[:8]))

    # ---------- 2. PR หายไปตรงไหน ----------
    gap_price, gap_unsold_dead, gap_unsold_live = [], [], []
    for g in games:
        true = {l["lot_id"]: l["true_value_per_kg"] for l in g["reveal"]["lots"]}
        kg_total = {}
        first = next(iter(g["offers"].values()), {"meta": {}})
        cls = {k: v["cls"] for k, v in (first["meta"].get("lots") or {}).items()}
        tot = 0
        sold = defaultdict(int)
        gp = 0.0
        for rid, res in g["results"].items():
            for o in res.get("my_offers", []):
                f = o.get("filled_kg", 0)
                if f:
                    gp += f * (true[o["lot_id"]] - o["price_per_kg"])
                    sold[o["lot_id"]] += f
        # kg รวมต่อล็อต: จาก round_open แรก (kg_available ตอนต้นเกม)
        o1 = g["opens"].get("R1") or next(iter(g["opens"].values()), None)
        if o1:
            kg_total = dict(o1["lots_kg"])
        tot = sum(kg_total[i] * true[i] for i in kg_total) or 1
        dead = live = 0.0
        for i, kg in kg_total.items():
            rem = max(kg - sold[i], 0)
            loss = 0.2 * rem * true[i]
            if cls.get(i) == "UNSELLABLE":
                dead += loss
            else:
                live += loss
        gap_price.append(gp / tot)
        gap_unsold_dead.append(dead / tot)
        gap_unsold_live.append(live / tot)
    tg = st.mean(gap_price) + st.mean(gap_unsold_dead) + st.mean(gap_unsold_live)
    print("\n2) PR หายไปตรงไหน (เฉลี่ยต่อเกม · รวม ≈ 1 − PR)")
    print(f"   ขายต่ำกว่ามูลค่าจริง (ratio < 1)      {st.mean(gap_price):.4f}  ({pct(st.mean(gap_price), tg)})")
    print(f"   ของเหลือ: ล็อตขายใครไม่ได้ (แก้ไม่ได้)  {st.mean(gap_unsold_dead):.4f}  ({pct(st.mean(gap_unsold_dead), tg)})")
    print(f"   ของเหลือ: ล็อตขายได้แต่ขายไม่หมด       {st.mean(gap_unsold_live):.4f}  ({pct(st.mean(gap_unsold_live), tg)})")
    print(f"   เกมที่มีล็อตขายไม่ได้: {sum(1 for x in gap_unsold_dead if x > 0)} · เกมที่ขายได้แต่เหลือ: {sum(1 for x in gap_unsold_live if x > 0.001)}")

    # ---------- 3. ต่อผู้ซื้อ ----------
    rows = []
    for g in games:
        true = {l["lot_id"]: l["true_value_per_kg"] for l in g["reveal"]["lots"]}
        for rid, res in g["results"].items():
            plan = g["offers"].get(rid, {}).get("plan", {})
            rfqs = {r["rfq_id"]: r for r in (g["opens"].get(rid) or {}).get("rfqs", [])}
            fills = {m["rfq_id"]: m["bought_kg"] / max(m["wanted_kg"], 1) for m in res.get("market_summary", [])}
            n = int(rid[1:]) if rid[1:].isdigit() else 0
            for o in res.get("my_offers", []):
                p = plan.get((o["lot_id"], o["rfq_id"]), {})
                rf = rfqs.get(o["rfq_id"], {})
                rows.append({"buyer": rf.get("buyer", "?"), "type": rf.get("buyer_type", p.get("type", "?")),
                             "round": n, "status": o["status"], "rung": p.get("rung", "?"),
                             "r": o["price_per_kg"] / true[o["lot_id"]], "fill": fills.get(o["rfq_id"]),
                             "kg": o["kg"], "filled": o.get("filled_kg", 0), "src": p.get("src", "?")})
    print("\n3) ต่อผู้ซื้อ (ratio = ราคา ÷ TV จริง)")
    print(f"   {'ผู้ซื้อ':<20}{'ซอง':>5}{'ขายได้':>8}{'แพ้ราคา':>8}{'เกินเพดาน':>10}{'ratio ขายได้':>14}{'ratio แพ้ราคา':>14}{'ratio เกินเพดาน':>16}")
    for b in sorted({r["buyer"] for r in rows}):
        rs = [r for r in rows if r["buyer"] == b]
        c = Counter(r["status"] for r in rs)
        acc = [r["r"] for r in rs if r["status"] in ("ACCEPTED", "PARTIAL")]
        out = [r["r"] for r in rs if r["status"] == "OUTBID"]
        abv = [r["r"] for r in rs if r["status"] == "ABOVE_LIMIT"]
        f = lambda v: f"{st.mean(v):.3f}±{st.pstdev(v):.3f}" if v else "-"
        print(f"   {b:<20}{len(rs):>5}{pct(c['ACCEPTED'] + c['PARTIAL'], len(rs)):>8}{pct(c['OUTBID'], len(rs)):>8}"
              f"{pct(c['ABOVE_LIMIT'], len(rs)):>10}{f(acc):>14}{f(out):>14}{f(abv):>16}")
    sm = Counter(r["status"] for r in rows)
    print(f"   รวม {len(rows)} ซอง: " + " · ".join(f"{k} {v} ({pct(v, len(rows)).strip()})" for k, v in sm.most_common()))

    # ซองที่ขายได้ใน RFQ ที่ผู้ซื้อยังซื้อไม่ครบ = ตั้งราคาสูงกว่านี้ได้ (ไม่มีคนแข่ง ติดแค่เพดาน)
    under = [r for r in rows if r["status"] == "ACCEPTED" and r["fill"] is not None and r["fill"] < 0.999]
    print(f"   ขายได้ใน RFQ ที่ผู้ซื้อซื้อไม่ครบ (แปลว่าอาจตั้งสูงกว่านี้ได้): {len(under)} ซอง ({pct(len(under), sm['ACCEPTED'])} ของที่ขายได้)")

    # ---------- 4. ต่อรอบ ----------
    print("\n4) ต่อรอบ")
    for n in sorted({r["round"] for r in rows}):
        rs = [r for r in rows if r["round"] == n]
        c = Counter(r["status"] for r in rs)
        acc = [r["r"] for r in rs if r["status"] in ("ACCEPTED", "PARTIAL")]
        sold = sum(r["filled"] for r in rs)
        print(f"   R{n}: ซอง {len(rs):>4} · ขายได้ {pct(c['ACCEPTED'] + c['PARTIAL'], len(rs))} · แพ้ราคา {pct(c['OUTBID'], len(rs))}"
              f" · เกินเพดาน {pct(c['ABOVE_LIMIT'], len(rs))} · ratio ขายได้ {st.mean(acc) if acc else 0:.3f} · ขาย {sold / 60 / len(games):.1f} กระสอบ/เกม")

    # ---------- 5. ขั้นบันได ----------
    print("\n5) ขั้นบันไดราคา")
    for k in sorted({r["rung"] for r in rows}):
        rs = [r for r in rows if r["rung"] == k]
        c = Counter(r["status"] for r in rs)
        acc = [r["r"] for r in rs if r["status"] in ("ACCEPTED", "PARTIAL")]
        print(f"   {k:<8} ซอง {len(rs):>4} · ขายได้ {pct(c['ACCEPTED'] + c['PARTIAL'], len(rs))} · แพ้ราคา {pct(c['OUTBID'], len(rs))}"
              f" · เกินเพดาน {pct(c['ABOVE_LIMIT'], len(rs))} · ratio ขายได้ {st.mean(acc) if acc else 0:.3f}")

    # ---------- 6. แรงกดดัน / ช่วงเกม ----------
    pm = Counter()
    for g in games:
        for v in g["offers"].values():
            pm[(v["meta"].get("phase"), v["meta"].get("pressure_mode"))] += 1
    print("\n6) ช่วงเกม × โหมดแรงกดดัน (จำนวนรอบ):", dict(pm))


if __name__ == "__main__":
    main()

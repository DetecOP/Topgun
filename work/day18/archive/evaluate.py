"""Performance Evaluator — อ่าน logs/ หลังจบเกม แล้วสรุปผลแยกส่วน (ไม่อยู่ในลูปของ agent)

    python evaluate.py               # เกมใน log ของรันล่าสุด
    python evaluate.py --all         # ทุกไฟล์ log (logs/decisions.jsonl + logs/runs/)
    python evaluate.py --file PATH   # ไฟล์ log ที่ระบุ
    python evaluate.py --dir PATH    # โฟลเดอร์ log อื่น

แสดง: PR (จาก reveal ถ้ามี) · ขายได้กี่ % · ratio เฉลี่ยที่ขายได้ต่อประเภท · สถานะต่อประเภท · ของเหลือ ·
ความคลาดของตัวอย่าง (sample − true) จาก reveal → ใช้ตั้ง DELTA_* ใน .env
"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def split_games(events: list[dict]) -> list[list[dict]]:
    games, cur = [], None
    for e in events:
        if e["event"] == "new_game":
            cur = [e]
            games.append(cur)
        elif cur is not None:
            cur.append(e)
    return games


def offers_by_round(game: list[dict]) -> dict:
    """round -> ซองสุดท้ายที่ส่ง (ถ้ามี offers_replaced ใช้ชุดนั้น) พร้อม meta ของแต่ละซอง"""
    out = {}
    for e in game:
        if e["event"] in ("offers_sent", "offers_replaced"):
            plan = {}
            for n in e.get("notes") or []:
                if isinstance(n, dict) and "plan" in n:
                    plan = {(p["lot_id"], p["rfq_id"]): p for p in n["plan"]}
            out[e["round"]] = {"offers": e.get("offers", []), "plan": plan}
    return out


def evaluate_game(game: list[dict], logs: Path) -> dict:
    start = game[0]
    tv = start.get("tv", {})
    closed = next((e for e in game if e["event"] == "market_closed"), None)
    reveal = next((e for e in game if e["event"] == "reveal"), None)
    res = {"time": start["time"], "market": start.get("market"), "closed": closed is not None}
    # ผลรายซอง: memory ไฟล์ของเกมนี้ (เลือกไฟล์ที่ sent ตรงกับ log)
    sent = offers_by_round(game)
    rounds, mem_sent = [], {}
    samples = start.get("samples") or {}
    if samples:   # ชื่อไฟล์ memory เดียวกับที่ main.py ตั้ง: hash ของ (lot_id, sample)
        key = tuple(sorted((i, json.dumps(s, sort_keys=True)) for i, s in samples.items()))
        mem = logs / f"memory-{start.get('market')}-{hashlib.sha1(repr(key).encode()).hexdigest()[:8]}.json"
        if mem.exists():
            data = json.loads(mem.read_text(encoding="utf-8"))
            rounds, mem_sent = data.get("rounds", []), data.get("sent", {})
    by_type = defaultdict(lambda: defaultdict(int))
    ratios = defaultdict(list)
    rungs = defaultdict(lambda: defaultdict(int))
    for rnd in rounds:
        s = {(o["rfq_id"], o["lot_id"]): o for o in mem_sent.get(rnd["round_id"], [])}
        plan = sent.get(rnd["round_id"], {}).get("plan", {})
        for o in rnd.get("my_offers", []):
            m = s.get((o["rfq_id"], o["lot_id"]), {})
            t = m.get("buyer_type", "?")
            by_type[t][o["status"]] += 1
            if o["status"] in ("ACCEPTED", "PARTIAL") and m.get("markup"):
                ratios[t].append(m["markup"])
            p = plan.get((o["lot_id"], o["rfq_id"]))
            if p:
                rungs[p.get("rung", "?")][o["status"]] += 1
    res["status_by_type"] = {t: dict(v) for t, v in by_type.items()}
    res["avg_sold_ratio"] = {t: round(sum(v) / len(v), 4) for t, v in ratios.items() if v}
    res["status_by_rung"] = {k: dict(v) for k, v in rungs.items()}
    if closed:
        st = closed["standings"]
        res["sold_pct"] = round(st["kg_sold"] / max(st["kg_total"], 1) * 100, 1)
        res["revenue"] = st["revenue_thb"]
        res["kg_remaining"] = st["kg_remaining"]
    if reveal and isinstance(reveal.get("data"), dict):
        d = reveal["data"]
        score = d.get("score") or {}
        res["pr"], res["mape"], res["rank"] = score.get("pr"), score.get("mape"), score.get("rank")
        err = defaultdict(list)
        for lot in d.get("lots", []):
            for k in ("defect_pct", "moisture_pct", "screen"):
                if k in lot.get("true", {}) and k in lot.get("sample", {}):
                    err[k].append(lot["sample"][k] - lot["true"][k])
        res["sample_error"] = {k: {"mean": round(sum(v) / len(v), 3), "max_abs": round(max(map(abs, v)), 3)}
                               for k, v in err.items() if v}
    return res


def main():
    logs = Path(sys.argv[sys.argv.index("--dir") + 1]) if "--dir" in sys.argv else Path(__file__).parent / "logs"
    # ค่าเริ่ม = log ของรันล่าสุด (logs/runs/ ตลาดฝึก หรือ logs/decisions.jsonl ตลาดแข่ง) · --all = ทุกไฟล์
    runs = sorted((logs / "runs").glob("*.jsonl")) if (logs / "runs").exists() else []
    main_log = logs / "decisions.jsonl"
    if "--file" in sys.argv:
        files = [Path(sys.argv[sys.argv.index("--file") + 1])]
    elif "--all" in sys.argv:
        files = ([main_log] if main_log.exists() else []) + runs
    else:
        cands = runs + ([main_log] if main_log.exists() else [])
        files = [max(cands, key=lambda p: p.stat().st_mtime)] if cands else []
    games = []
    for fp in files:
        games += split_games(read_events(fp))
    print("ไฟล์ log:", ", ".join(str(f.relative_to(logs.parent)) if f.is_relative_to(logs.parent) else str(f) for f in files))
    if not games:
        print(f"ไม่มี log ใน {logs}")
        return
    for i, g in enumerate(games, 1):
        r = evaluate_game(g, logs)
        print(f"\n=== เกม {i} ({r['time']}) ตลาด {r['market']} {'จบแล้ว' if r['closed'] else 'ยังไม่จบ'} ===")
        for k in ("pr", "rank", "mape", "sold_pct", "revenue", "kg_remaining"):
            if k in r:
                print(f"  {k}: {r[k]}")
        print("  สถานะต่อประเภท:", json.dumps(r["status_by_type"], ensure_ascii=False))
        print("  ratio เฉลี่ยที่ขายได้:", json.dumps(r["avg_sold_ratio"], ensure_ascii=False))
        print("  สถานะต่อขั้นบันได:", json.dumps(r["status_by_rung"], ensure_ascii=False))
        if r.get("sample_error"):
            print("  ตัวอย่างคลาด (sample − true):", json.dumps(r["sample_error"], ensure_ascii=False))
            print("  → ตั้ง DELTA_DEFECT / DELTA_MOISTURE / DELTA_SCREEN ใน .env ≈ max_abs ที่เห็นบ่อย")


if __name__ == "__main__":
    main()

# probe_report.py · สรุปสถิติเพดานผู้ซื้อจาก probe_data\offers.jsonl
# รัน: .venv\Scripts\python.exe day17\probe_report.py
# ผล: ตารางบนจอ + probe_data\ceiling_summary.csv (เปิดด้วย Excel ได้)

import csv
import json
import statistics as stt
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
DATA = Path(__file__).resolve().parent / "probe_data"


def summarize(rows, key):
    out = []
    for name in sorted({r[key] for r in rows}):
        rs = [r for r in rows if r[key] == name]
        acc = [r["ratio"] for r in rs if r["filled_kg"] > 0]
        lim = [r["ratio"] for r in rs if r["status"] == "ABOVE_LIMIT"]
        outb = [r["ratio"] for r in rs if r["status"] == "OUTBID"]
        lo, hi = (max(acc) if acc else None), (min(lim) if lim else None)
        est = (lo + hi) / 2 if lo and hi and hi > lo else (lo or hi)
        consistent = "สอดคล้อง" if (lo is None or hi is None or hi > lo) else "ขัดกัน → เพดานเปลี่ยนตามเกม/รอบ"
        out.append({"ชื่อ": name, "ประเภท": rs[0]["type"], "ซอง": len(rs), "ขายได้": len(acc),
                    "เกินเพดาน": len(lim), "แพ้ข้อเสนอ": len(outb),
                    "ขายได้สูงสุด×TV": lo, "เกินเพดานต่ำสุด×TV": hi, "เพดานประมาณ×TV": est,
                    "ขายได้เฉลี่ย×TV": stt.mean(acc) if acc else None, "หมายเหตุ": consistent})
    return out


def fmt(v):
    return f"{v:.3f}" if isinstance(v, float) else ("-" if v is None else str(v))


def main():
    p = DATA / "offers.jsonl"
    if not p.exists():
        sys.exit("ยังไม่มีข้อมูล → รัน probe_bot.py ก่อน")
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    print(f"ข้อมูล {len(rows)} ซอง\n")
    for key, title in (("buyer", "ต่อผู้ซื้อแต่ละราย"), ("type", "ต่อประเภท")):
        res = summarize(rows, key)
        print(f"=== {title} ===")
        cols = list(res[0].keys())
        print(" | ".join(cols))
        for r in res:
            print(" | ".join(fmt(r[c]) for c in cols))
        print()
        with open(DATA / f"ceiling_summary_{key}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(res)
    print("บันทึก CSV ไว้ใน", DATA)
    market_report()


def market_report():
    """สรุป market.jsonl: ภาพรวมตลาดต่อ RFQ ทุกรอบ → market_summary.csv (เปิด Excel ได้)"""
    p = DATA / "market.jsonl"
    if not p.exists():
        print("\n(ยังไม่มี market.jsonl)")
        return
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    rfq_info = {}                                           # (game, rfq_id) → ผู้ซื้อ/ประเภท/สเปก
    for r in rows:
        if r["kind"] == "round":
            for q in r.get("rfqs", []):
                rfq_info[(r["game"], q.get("rfq_id"))] = q
    flat = []
    for r in rows:
        if r["kind"] != "results":
            continue
        for x in r["data"].get("market_summary", []):
            q = rfq_info.get((r["game"], x.get("rfq_id")), {})
            row = {"game": r["game"], "round": r["round_id"], "buyer": q.get("buyer"),
                   "type": q.get("buyer_type"), "spec": json.dumps(q.get("spec"), ensure_ascii=False)}
            row.update({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                        for k, v in x.items()})
            flat.append(row)
    games = len({r["game"] for r in rows if r["kind"] == "game"})
    print(f"\n=== ข้อมูลตลาด: {games} เกม · {len(flat)} แถว (RFQ×รอบ) ===")
    if not flat:
        return
    cols = list(dict.fromkeys(k for r in flat for k in r))
    with open(DATA / "market_summary.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(flat)
    print("คอลัมน์:", ", ".join(cols))
    for r in flat[-8:]:
        print(" | ".join(fmt(r.get(c)) for c in cols))
    print("บันทึก", DATA / "market_summary.csv")


if __name__ == "__main__":
    main()

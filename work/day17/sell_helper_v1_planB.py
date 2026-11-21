# sell_helper.py · ผู้ช่วยขายมือวันที่ 17: ประเมินมูลค่า (สูตรของเราจากความรู้กาแฟ) → เสนอผู้ซื้อ+ราคา → เรียนจากผล
#
# Claude เป็นคนรัน: ผู้ใช้ส่งภาพหน้าจอ/ข้อมูลมา → Claude กรอก state.json → รัน suggest → ตอบตาราง
# รัน (จากโฟลเดอร์ work):
#   .venv\Scripts\python.exe day17\sell_helper.py suggest           ← เสนอรอบนี้
#   .venv\Scripts\python.exe day17\sell_helper.py result A=n B=y C=y@94.5   ← บันทึกผล (y=ขายได้ n=ไม่ได้ @ราคาจริงถ้าต่าง)
#   .venv\Scripts\python.exe day17\sell_helper.py status            ← สรุปสิ่งที่เรียนรู้แล้ว
#
# ⚠️ สูตรมูลค่าเป็น "สูตรของเราเอง" อิงความรู้กาแฟ (RESEARCH.md) ไม่ใช่สูตรผู้จัด · ตัวเลขทุกตัวปรับได้ใน state.json → settings
# ⚠️ เครื่องมือนี้ไม่ส่งอะไรไปที่ server ผู้จัด (ช่วง 1 คนเป็นผู้ส่งผ่านหน้าเว็บเอง)

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "simulator"))
from valuation import DEFECT_WEIGHTS, defect_equivalent_pct  # noqa: E402  น้ำหนักตำหนิแบบ FAO

STATE = HERE / "state.json"

# ---------------- 1) รู้ค่าของ: สูตรของเรา ----------------
SIZE_MULT_DEFAULT = {"ใหญ่": 1.08, "กลาง": 1.0, "เล็ก": 0.93, "ติดเปลือก": 0.85}


def lot_defect_pct(lot):
    """% ตำหนิ: ถ้ามีจำนวนเมล็ดแยกชนิด → ถ่วงน้ำหนักแบบ FAO, ไม่งั้นใช้ % ที่ให้มา"""
    if lot.get("defect_counts"):
        return defect_equivalent_pct(lot["defect_counts"])
    return lot.get("defect_pct")


def value_per_kg(lot, st):
    """คืน (มูลค่าต่อ กก., เป็นค่าประเมินไหม, คำอธิบาย)"""
    s = st["settings"]
    known = [l for l in st["lots"] if l.get("moisture") is not None]
    m = lot.get("moisture")
    d = lot_defect_pct(lot)
    size = lot.get("size")
    est = m is None or d is None or size is None
    k = s.get("prior_weight", 2)                               # shrinkage: ค่าเริ่มต้นหนักเท่ากับ k ล็อต
    if m is None:                                              # ยังไม่มีผลวัด → ผสมค่าเฉลี่ยล็อตที่วัดแล้วกับค่าเริ่มต้น
        ms = [l["moisture"] for l in known]                    # (เห็นล็อตเดียวไม่ควรเชื่อ 100%)
        m = (sum(ms) + k * s["prior_moisture"]) / (len(ms) + k)
    if d is None:
        ds = [lot_defect_pct(l) for l in st["lots"] if lot_defect_pct(l) is not None]
        d = (sum(ds) + k * s["prior_defect_pct"]) / (len(ds) + k)
    lim, low = s["moisture_limit"], s["moisture_low"]
    ded_m = 0.0
    if m > lim:                                                # ชื้นเกิน → เสี่ยงเชื้อรา หักแรง
        ded_m = (m - lim) * s["ded_per_moist_point_over"]
        if m > lim + 1:
            ded_m += s["mold_risk_extra"]
    elif m < low:                                              # แห้งเกิน → น้ำหนักหาย หักเบา
        ded_m = (low - m) * s["ded_per_moist_point_under"]
    ded_d = d * s["ded_per_defect_pct"]
    mult = s["size_mult"].get(size, 1.0) if size else 1.0
    v = s["base_price"] * mult * (1 - min(s["ded_cap"], ded_m + ded_d))
    why = f"ชื้น {m:.1f}% (หัก {ded_m:.0%}) · ตำหนิ {d:.1f}% (หัก {ded_d:.0%}) · ขนาด {size or '?'} ×{mult}"
    return v, est, why


# ---------------- 2) เสนอขาย: เลือกผู้ซื้อ + ราคา ----------------
def eligible(lot, b):
    """ผ่านเงื่อนไขผู้ซื้อไหม (ค่าที่ยังไม่รู้ถือว่าผ่าน แต่เตือน)"""
    m, d = lot.get("moisture"), lot_defect_pct(lot)
    if m is not None and b.get("max_moisture") is not None and m > b["max_moisture"]:
        return False
    if d is not None and b.get("max_defect") is not None and d > b["max_defect"]:
        return False
    if b.get("sizes") and lot.get("size") and lot["size"] not in b["sizes"]:
        return False
    return True


def ratio(st, h):
    """ราคา ÷ มูลค่าเรา โดยใช้มูลค่า "ล่าสุด" ของล็อต (ถ้าผลวัดเพิ่งมา จะคำนวณใหม่ให้เทียบกันได้)"""
    lot = next((l for l in st["lots"] if l["id"] == h["lot"] and "weight" in l), None)
    v = value_per_kg(lot, st)[0] if lot else h["value"]
    return h["price"] / v


def buyer_bounds(st, buyer_id):
    """จากประวัติผู้ซื้อคนนี้ คืน (สูงสุดที่ขายได้, ต่ำสุดที่ขายไม่ได้, จำนวนครั้ง) เป็นสัดส่วนต่อมูลค่าเรา"""
    hs = [h for h in st["history"] if h["buyer"] == buyer_id]
    acc = [ratio(st, h) for h in hs if h["sold"]]
    rej = [ratio(st, h) for h in hs if not h["sold"] and h.get("eligible", True)]
    return (max(acc) if acc else None), (min(rej) if rej else None), len(hs)


def lot_refused(st, lot_id, buyer_id):
    """ล็อตนี้เคยถูกผู้ซื้อคนนี้ปฏิเสธที่สัดส่วนต่ำสุดเท่าไร (None = ไม่เคย)"""
    r = [ratio(st, h) for h in st["history"] if h["lot"] == lot_id and h["buyer"] == buyer_id and not h["sold"]]
    return min(r) if r else None


def target_ratio(st, buyer_id, est, lot_id=None):
    """ราคาเป้าหมาย (เท่าของมูลค่าเรา) สำหรับผู้ซื้อคนนี้ · หาช่องระหว่าง ขายได้ ↔ ขายไม่ได้ แบบแบ่งครึ่ง"""
    s = st["settings"]
    acc, rej, n = buyer_bounds(st, buyer_id)
    if acc is not None and rej is not None and rej > acc:
        r, how = (acc + rej) / 2, f"กึ่งกลางระหว่างขายได้ {acc - 1:+.0%} กับไม่ได้ {rej - 1:+.0%}"
    elif acc is not None and rej is not None:                  # ข้อมูลขัดกัน (เช่น ล็อตต่างกัน) → ระวังไว้ก่อน
        r, how = (acc + rej) / 2 - s["step_down"] / 2, f"ข้อมูลขัดกัน (ได้ {acc - 1:+.0%} / ไม่ได้ {rej - 1:+.0%}) → ใช้ค่ากลางแบบระวัง"
    elif acc is not None:
        r, how = acc + s["step_up"], f"เคยขายได้ที่ {acc - 1:+.0%} → ลองสูงขึ้น"
    elif rej is not None:
        r, how = rej - s["step_down"], f"เคยไม่ได้ที่ {rej - 1:+.0%} → ลดลง"
    else:
        r, how = 1 + s["start_markup"], "ยังไม่มีข้อมูลผู้ซื้อคนนี้ → เริ่มที่ค่าเริ่มต้น"
    if est:                                                    # ยังไม่มีผลวัด → เผื่อ กัน winner's curse
        r += s["presell_extra"]
        how += " · เผื่อเพราะยังไม่มีผลวัด"
    refused = lot_refused(st, lot_id, buyer_id) if lot_id else None
    if refused is not None and r > refused - s["step_down"]:   # ล็อตนี้เคยโดนคนนี้ปฏิเสธ → ต้องถูกกว่าเดิม
        r = refused - s["step_down"]
        how += f" · ล็อตนี้เคยโดนปฏิเสธที่ {refused - 1:+.0%} → ลดลง"
    floor = 1 + s["min_markup"]
    if r < floor:
        r, how = floor, how + f" · ไม่ต่ำกว่า {s['min_markup']:+.0%} ของมูลค่า"
    return r, how, acc


def nice_price(p):
    """หลบเลขกลม (ทีมอื่น/LLM ชอบ 90, 95, 100) → ถ้าใกล้เลขลงท้าย 0 หรือ 5 ลดลง 0.5"""
    p = round(p, 2)
    if abs(p / 5 - round(p / 5)) * 5 < 0.3:
        p -= 0.5
    return round(p, 2)


def suggest(st, rnd=None):
    s = st["settings"]
    rows, per_buyer = [], {}
    open_lots = [l for l in st["lots"] if not l.get("sold")]
    plans = []
    for lot in open_lots:
        v, est, why = value_per_kg(lot, st)
        cands = [b for b in st["buyers"] if eligible(lot, b)]
        if not cands:
            rows.append({"lot": lot["id"], "skip": True, "value": v, "why": why,
                         "note": "ไม่มีผู้ซื้อรับ (เกินเงื่อนไขทุกคน) → ไม่ต้องเสนอ"})
            continue
        opts = []
        for b in cands:
            r, how, acc = target_ratio(st, b["id"], est, lot["id"])
            _, _, n = buyer_bounds(st, b["id"])
            fresh = lot_refused(st, lot["id"], b["id"]) is None        # ยังไม่เคยปฏิเสธล็อตนี้
            opts.append((fresh, acc if acc is not None else -1, -n, r, b, how))
        # ลำดับ: ผู้ซื้อที่ยังไม่เคยปฏิเสธล็อตนี้ก่อน → มีหลักฐานขายได้สูงสุด → ลองน้อยสุด (สำรวจ)
        opts.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        opts = [o[1:] for o in opts]
        plans.append((lot, v, est, why, opts))
    plans.sort(key=lambda p: -p[1] * p[0].get("weight", 1))   # ล็อตมูลค่ารวมสูงได้เลือกผู้ซื้อก่อน
    for lot, v, est, why, opts in plans:
        cap = s.get("max_lots_per_buyer_per_round")
        chosen = next((o for o in opts if not cap or per_buyer.get(o[3]["id"], 0) < cap), opts[0])
        acc, _, r, b, how = chosen
        per_buyer[b["id"]] = per_buyer.get(b["id"], 0) + 1
        price = nice_price(v * r)
        rows.append({"lot": lot["id"], "buyer": b["id"], "price": price, "value": round(v, 2),
                     "markup": price / v - 1, "est": est, "why": why, "how": how,
                     "weight": lot.get("weight")})
    lim = s.get("max_offers_per_round")
    offers = [r for r in rows if not r.get("skip")]
    if lim:
        offers = offers[:lim]
    st["pending"] = {"round": rnd or (max([h["round"] for h in st["history"]], default=0) + 1),
                     "offers": offers}
    return rows, offers


def print_suggest(rows, offers, rnd):
    print(f"\n=== ข้อเสนอรอบ {rnd} (สูตรของเรา · ยังไม่ส่งจริง) ===")
    print(f"{'ล็อต':<6}{'ผู้ซื้อ':<8}{'ราคา/กก.':>10}{'มูลค่าเรา':>11}{'บวก':>7}  เหตุผล")
    for r in offers:
        tag = " ⚠️ยังไม่มีผลวัด" if r["est"] else ""
        print(f"{r['lot']:<6}{r['buyer']:<8}{r['price']:>10.2f}{r['value']:>11.2f}{r['markup']:>+7.0%}  {r['how']}{tag}")
        print(f"{'':<14}มูลค่ามาจาก: {r['why']}")
    for r in rows:
        if r.get("skip"):
            print(f"{r['lot']:<6}—  {r['note']} ({r['why']})")


# ---------------- 3) ดูผลแล้วปรับ ----------------
def record(st, tokens):
    pend = st.get("pending")
    if not pend:
        raise SystemExit("ยังไม่มีข้อเสนอค้าง → รัน suggest ก่อน")
    res = {}
    for t in tokens:                                            # รูปแบบ A=y  B=n  C=y@94.5  D=n:win=97
        lot, val = t.split("=", 1)
        sold = val[0].lower() == "y"
        price = float(val.split("@")[1].split(":")[0]) if "@" in val else None
        win = float(val.split("win=")[1]) if "win=" in val else None
        res[lot.strip()] = (sold, price, win)
    rows_csv = []
    for o in pend["offers"]:
        if o["lot"] not in res:
            continue
        sold, price, win = res[o["lot"]]
        price = price or o["price"]
        st["history"].append({"round": pend["round"], "lot": o["lot"], "buyer": o["buyer"], "price": price,
                              "value": o["value"], "sold": sold, "win_price": win, "est": o["est"]})
        lot = next(l for l in st["lots"] if l["id"] == o["lot"])
        if sold:
            lot["sold"] = True
        rows_csv.append([pend["round"], datetime.now().strftime("%H:%M"), o["lot"], lot.get("moisture"),
                         lot_defect_pct(lot), lot.get("size"), o["value"], o["buyer"], price,
                         "ได้" if sold else "ไม่", win or (price if sold else ""), "ประเมินล่วงหน้า" if o["est"] else ""])
    st["pending"] = None
    path = st["settings"].get("rounds_csv")
    if path and rows_csv:
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["รอบ", "เวลา", "ล็อต", "ความชื้น", "เมล็ดเสีย", "ขนาด", "มูลค่าประเมิน",
                            "ผู้ซื้อ", "ราคาที่เสนอ", "ขายได้", "ราคาที่ขายได้", "หมายเหตุ"])
            w.writerows(rows_csv)
    return len(rows_csv)


def status(st):
    print("\n=== สิ่งที่เรียนรู้แล้ว (ราคา ÷ มูลค่าเรา) ===")
    for b in st["buyers"]:
        acc, rej, n = buyer_bounds(st, b["id"])
        a = f"{acc - 1:+.0%}" if acc else "-"
        r = f"{rej - 1:+.0%}" if rej else "-"
        print(f"  {b['id']:<5} เสนอ {n} ครั้ง · ขายได้สูงสุดที่ {a} · ขายไม่ได้ต่ำสุดที่ {r}")
    left = [l["id"] for l in st["lots"] if not l.get("sold")]
    sold = [h for h in st["history"] if h["sold"]]
    print(f"  ขายแล้ว {len(sold)} ล็อต · เหลือ {left}")
    if sold:
        avg = sum(h["price"] / h["value"] for h in sold) / len(sold) - 1
        print(f"  ขายได้เฉลี่ย {avg:+.1%} จากมูลค่าเรา (ใช้สูตรของเรา ไม่ใช่มูลค่าจริงของผู้จัด)")


def load():
    with open(STATE, encoding="utf-8") as f:
        return json.load(f)


def save(st):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("suggest")
    p.add_argument("--round", type=int)
    p = sub.add_parser("result")
    p.add_argument("tokens", nargs="+")
    sub.add_parser("status")
    a = ap.parse_args()
    st = load()
    if a.cmd == "suggest":
        rows, offers = suggest(st, a.round)
        print_suggest(rows, offers, st["pending"]["round"])
    elif a.cmd == "result":
        n = record(st, a.tokens)
        print(f"บันทึกผล {n} ข้อเสนอแล้ว")
        status(st)
    else:
        status(st)
    save(st)

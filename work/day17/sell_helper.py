# sell_helper.py v2 · ผู้ช่วยขายมือวันที่ 17 ตามกติกาจริง (สไลด์วันที่ 17 + คู่มือ-API.md ของผู้จัด)
#
# ⚠️ กติกาช่วง 1: ยื่นซองด้วยสคริปต์/โค้ด = คะแนน 0 → ไฟล์นี้ "คำนวณและแนะนำ" อย่างเดียว คนกดยื่นในหน้า /trade เอง
#
# Claude รัน (จากโฟลเดอร์ work):
#   .venv\Scripts\python.exe day17\sell_helper.py tv                ← ตาราง TV สำหรับ "ส่งผลประเมิน" (คะแนน 20)
#   .venv\Scripts\python.exe day17\sell_helper.py suggest           ← ซองที่แนะนำรอบนี้
#   .venv\Scripts\python.exe day17\sell_helper.py result R1-03=A R1-04=P2 R1-05=O R1-06=L
#        A=ขายได้ทั้งหมด  P<n>=ขายได้บางส่วน n กระสอบ  O=OUTBID  L=ABOVE_LIMIT  S=SPEC_MISMATCH
#   .venv\Scripts\python.exe day17\sell_helper.py status
#
# หลักการ (จากสไลด์):
#   คะแนน 80 = PR = (เงินขายได้ + 0.8×TV ของเหลือ) ÷ TV ทั้งหมด · ผู้ซื้อตัดซองเกินเพดานลับ (เท่าของ TV)
#   แล้วเรียง ราคา÷TV ต่ำสุดก่อน → markup (ราคา÷TV) คือสิ่งเดียวที่ต้องหา ต่อผู้ซื้อแต่ละราย
#   ขายต่ำกว่า 0.80×TV แย่กว่าไม่ขาย

import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
OK_STATUS = {"A": "ACCEPTED", "P": "PARTIAL", "O": "OUTBID", "L": "ABOVE_LIMIT", "S": "SPEC_MISMATCH"}


# ---------------- 1) มูลค่าจริง TV (สูตรเปิดเผย สไลด์ 5–11) ----------------
def grade(s, d):
    for max_d, mult, name in s["defect_steps"]:
        if d <= max_d:
            return name, mult
    return s["defect_steps"][-1][2], s["defect_steps"][-1][1]


def tv(lot, s):
    d, m, sc = lot["defect"], lot["moisture"], lot["screen"]
    gname, gm = grade(s, d)
    G = (1 - d / 100) * gm
    if m <= s["moisture_ref"]:
        M = 1.0
    elif m <= s["moisture_hard"]:
        M = (1 - m / 100) / (1 - s["moisture_ref"] / 100) - s["moisture_penalty"] * (m - s["moisture_ref"])
    else:
        M = s["moisture_hard_factor"]
    codes = sorted(int(k) for k in s["screen"])
    S = s["screen"][str(min(max(int(sc), codes[0]), codes[-1]))]
    return s["p0"] * G * M * S, gname, G, M, S


def spec_ok(lot, rfq):
    return (lot["defect"] <= rfq["max_defect"] and lot["moisture"] <= rfq["max_moisture"]
            and (rfq.get("min_screen") is None or lot["screen"] >= rfq["min_screen"]))


# ---------------- 2) markup ต่อผู้ซื้อ: หาเพดานลับแบบแบ่งครึ่ง ----------------
def knowledge(st, key, val):
    """จากประวัติ (กรองด้วย key=buyer หรือ type) คืน (ขายได้สูงสุด, เกินเพดานต่ำสุด, OUTBID ล่าสุด)"""
    hs = [h for h in st["history"] if h.get(key) == val]
    acc = [h["markup"] for h in hs if h["status"] in ("ACCEPTED", "PARTIAL") and h.get("filled", 0) > 0]
    lim = [h["markup"] for h in hs if h["status"] == "ABOVE_LIMIT"]
    out = [h for h in hs if h["status"] == "OUTBID"]
    return (max(acc) if acc else None), (min(lim) if lim else None), (out[-1]["markup"] if out else None)


def target_markup(st, rfq):
    s = st["settings"]
    acc, lim, out = knowledge(st, "buyer", rfq["buyer"])
    src = "ผู้ซื้อรายนี้"
    if acc is None and lim is None:                            # ยังไม่เคยเจอรายนี้ → ใช้ข้อมูลประเภทเดียวกัน
        acc, lim, out2 = knowledge(st, "type", rfq["type"])
        out = out if out is not None else out2
        src = f"ประเภท {rfq['type']}"
    if acc is not None and lim is not None and lim > acc + 0.01:
        m, why = (acc + lim) / 2, f"{src}: ขายได้ ×{acc:.2f} / เกินเพดาน ×{lim:.2f} → กึ่งกลาง"
    elif lim is not None and acc is not None:
        m, why = acc, f"{src}: เพดานอยู่ราว ×{acc:.2f}"
    elif lim is not None:
        m, why = lim - s["step_down"], f"{src}: เกินเพดานที่ ×{lim:.2f} → ลด"
    elif acc is not None:
        m, why = acc + s["step_up"], f"{src}: ขายได้ที่ ×{acc:.2f} → ลองสูงขึ้น"
    else:
        m, why = s["start_markup"].get(rfq["type"], 1.0), f"ยังไม่มีข้อมูล → ค่าเริ่มต้น {rfq['type']}"
    if out is not None and m >= out:                           # แพ้ซองอื่นที่ราคานี้ → ต้องถูกกว่าเดิม
        m, why = out - s["outbid_step"], why + f" · เคย OUTBID ที่ ×{out:.2f} → ลด"
    left = s["rounds_total"] - st["round"] + 1
    if left == 1:                                              # รอบสุดท้าย: ของเหลือได้แค่ 0.8 → ยอมลดให้ขายออก
        m, why = min(m, (acc or m) - s["step_down"]), why + " · รอบสุดท้าย ลดให้ขายออก"
    m = min(max(m, s["min_markup"]), s["max_markup"])
    return round(m, 3), why


# ---------------- 3) จัดซองรอบนี้ ----------------
def suggest(st):
    s = st["settings"]
    left = s["rounds_total"] - st["round"] + 1
    lots = {l["id"]: l for l in st["lots"]}
    # ปริมาณที่ยอมเสนอรอบนี้ต่อล็อต: pace เท่าของส่วนเฉลี่ย (ซองที่ขายไม่ได้คืนกระสอบ จึงเสนอเยอะได้) · 2 รอบสุดท้ายเสนอหมด
    budget = {i: (l["bags_left"] if left <= 2 else min(l["bags_left"], math.ceil(l["bags_left"] / left * s["pace"])))
              for i, l in lots.items()}
    plans, fresh_seen = [], {}
    for r in st["rfqs"]:
        m, why = target_markup(st, r)
        if why.startswith("ยังไม่มีข้อมูล"):                   # ผู้ซื้อใหม่ประเภทเดียวกัน → ลองคนละราคา เรียนเพดานเร็วขึ้น
            k = fresh_seen.get(r["type"], 0)
            if k:
                m = round(max(s["min_markup"], m - s["explore_step"] * k), 3)
                why += f" · ลองต่ำกว่าอีกราย {s['explore_step'] * k:.0%} (สำรวจ)"
            fresh_seen[r["type"]] = k + 1
        plans.append((m, r, why))
    plans.sort(key=lambda x: -x[0])                            # RFQ ที่จ่ายสูงได้เลือกล็อตก่อน
    n_ok = {i: sum(spec_ok(l, r) for r in st["rfqs"]) for i, l in lots.items()}
    # แบ่งกระสอบของล็อตให้ทุก RFQ ที่ markup ใกล้ระดับสูงสุดของล็อตนั้น (ไม่เทให้รายแรกหมด → ได้ลองหลายผู้ซื้อ)
    per_offer = {}
    for i, l in lots.items():
        ms = [m for m, r, _ in plans if spec_ok(l, r)]
        k = sum(1 for m in ms if m >= max(ms) - 0.05) if ms else 1
        per_offer[i] = max(1, math.ceil(budget[i] / k)) if budget[i] else 0
    offers, skipped = [], []
    for m, r, why in plans:
        need = r["bags"]
        elig = [l for l in lots.values() if spec_ok(l, r) and budget[l["id"]] > 0]
        elig.sort(key=lambda l: (n_ok[l["id"]], -tv(l, s)[0]))  # ล็อตที่มีทางไปน้อยได้ก่อน (เช่น ไป Instant ได้ทางเดียว)
        for l in elig:
            if need <= 0:
                break
            bags = min(need, budget[l["id"]], per_offer[l["id"]])
            v = tv(l, s)[0]
            offers.append({"rfq": r["id"], "buyer": r["buyer"], "type": r["type"], "lot": l["id"], "bags": bags,
                           "markup": m, "tv": round(v, 2), "price": round(m * v, 2), "why": why})
            budget[l["id"]] -= bags
            need -= bags
        if not elig:
            skipped.append(f"{r['id']} ({r['buyer']}, {r['type']}): ไม่มีล็อตผ่านสเปก/เหลือขาย")
    st["pending"] = offers
    return offers, skipped


def print_tv(st):
    s = st["settings"]
    print("\n=== ส่งผลประเมิน (คะแนน 20) · ใส่ช่อง TV ของแต่ละล็อต ===")
    print(f"{'ล็อต':<12}{'ชื้น':>6}{'เสีย':>7}{'ตะแกรง':>7}  {'เกรด':<15}{'G':>7}{'M':>7}{'S':>6}{'TV':>9}{'0.8×TV':>8}  ไปได้กับ")
    for l in st["lots"]:
        v, g, G, M, S = tv(l, s)
        where = [t for t, r in s["buyer_specs"].items() if spec_ok(l, r)] or ["ไม่มีใครรับ → เหลือขายที่ 0.8×TV"]
        print(f"{l['id']:<12}{l['moisture']:>6}{l['defect']:>7}{l['screen']:>7}  {g:<15}{G:>7.4f}{M:>7.4f}{S:>6.2f}"
              f"{v:>9.2f}{0.8 * v:>8.2f}  {', '.join(where)}")


def print_suggest(st, offers, skipped):
    print(f"\n=== รอบ {st['round']}/{st['settings']['rounds_total']} · ซองที่แนะนำ (กดยื่นเองในหน้า /trade) ===")
    print(f"{'RFQ':<8}{'ผู้ซื้อ':<16}{'ประเภท':<12}{'ล็อต':<12}{'กระสอบ':>7}{'ราคา/กก.':>10}{'×TV':>7}  เหตุผล")
    for o in offers:
        print(f"{o['rfq']:<8}{o['buyer'][:15]:<16}{o['type']:<12}{o['lot']:<12}{o['bags']:>7}{o['price']:>10.2f}"
              f"{o['markup']:>7.2f}  {o['why']}")
    for x in skipped:
        print("  ข้าม:", x)
    unsold = {l["id"]: l["bags_left"] - sum(o["bags"] for o in offers if o["lot"] == l["id"]) for l in st["lots"]}
    rest = {k: v for k, v in unsold.items() if v > 0}
    if rest:
        print("  ยังไม่เสนอรอบนี้ (เก็บไว้รอบหน้า):", rest)


def record(st, tokens):
    pend = {o["rfq"] + "|" + o["lot"]: o for o in st.get("pending") or []}
    by_rfq = {}
    for o in pend.values():
        by_rfq.setdefault(o["rfq"], []).append(o)
    rows = []
    for t in tokens:
        key, code = t.split("=", 1)                            # R1-03=A หรือ R1-03:LOT-T05-1=P2
        rfq, lot = (key.split(":") + [None])[:2]
        targets = [pend[f"{rfq}|{lot}"]] if lot else by_rfq.get(rfq, [])
        for o in targets:
            status = OK_STATUS[code[0].upper()]
            filled = o["bags"] if status == "ACCEPTED" else (int(code[1:]) if status == "PARTIAL" and code[1:] else 0)
            st["history"].append({**{k: o[k] for k in ("rfq", "buyer", "type", "lot", "bags", "markup", "price", "tv")},
                                  "round": st["round"], "status": status, "filled": filled})
            lt = next(l for l in st["lots"] if l["id"] == o["lot"])
            lt["bags_left"] -= filled
            rows.append([st["round"], datetime.now().strftime("%H:%M"), o["lot"], lt["moisture"], lt["defect"],
                         lt["screen"], o["tv"], f"{o['buyer']} ({o['type']})", o["price"],
                         f"{status} {filled}/{o['bags']}", o["price"] if filled else "", f"×{o['markup']}"])
    st["pending"] = None
    st["round"] += 1
    path = st["settings"].get("rounds_csv")
    if path and rows:
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
    return len(rows)


def status(st):
    s = st["settings"]
    tv_total = sum(tv(l, s)[0] * l["bags_total"] * 60 for l in st["lots"])
    revenue = sum(h["price"] * h["filled"] * 60 for h in st["history"])
    left_val = sum(tv(l, s)[0] * l["bags_left"] * 60 for l in st["lots"])
    print(f"\n=== สถานะหลังรอบ {st['round'] - 1} ===")
    print(f"  ขายแล้ว {revenue:,.0f} บาท · ของเหลือ {sum(l['bags_left'] for l in st['lots'])} กระสอบ")
    if tv_total:
        print(f"  PR ถ้าปิดตลาดตอนนี้ = {(revenue + s['salvage'] * left_val) / tv_total:.3f}  (0.80 = 0 คะแนน)")
    for b in sorted({h["buyer"] for h in st["history"]}):
        acc, lim, out = knowledge(st, "buyer", b)
        f = lambda x: f"×{x:.2f}" if x else "-"
        print(f"  {b[:18]:<18} ขายได้สูงสุด {f(acc)} · เกินเพดานต่ำสุด {f(lim)} · OUTBID ล่าสุด {f(out)}")


def load():
    return json.load(open(STATE, encoding="utf-8"))


def save(st):
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tv")
    sub.add_parser("suggest")
    p = sub.add_parser("result")
    p.add_argument("tokens", nargs="+")
    sub.add_parser("status")
    a = ap.parse_args()
    st = load()
    if a.cmd == "tv":
        print_tv(st)
    elif a.cmd == "suggest":
        offers, skipped = suggest(st)
        print_suggest(st, offers, skipped)
    elif a.cmd == "result":
        print(f"บันทึก {record(st, a.tokens)} ซอง")
        status(st)
    else:
        status(st)
    save(st)

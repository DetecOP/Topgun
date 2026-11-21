"""สรุปผลรอบให้ B · อ่าน log อย่างเดียว (สเปก design/round_digest_spec.md)
ไม่เรียกเครือข่าย · ไม่อ่าน .env · ใช้ spec_ok / calendar_weights จาก agent (สูตรเดียวกับที่ agent ใช้ตั้งราคา)
รันในโฟลเดอร์ work/day20/agent:
  python ../tools/round_digest.py                 รอบล่าสุดที่มี round_results
  python ../tools/round_digest.py --round R5      รอบที่ระบุ
  python ../tools/round_digest.py --trend         ตารางทุกรอบ
  python ../tools/round_digest.py --log ../data/stage2_competition/decisions.jsonl --round R3"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from inventory import spec_ok          # noqa: E402  (ไม่เรียกเครือข่าย)
from playbook import calendar_weights  # noqa: E402

TYPES = ("COMMERCIAL", "INSTANT", "SPECIALTY")
BAD = ("_error", "crashed", "rejected")


def read_log(path):
    """อ่านทุกบรรทัด · บรรทัด JSON ไม่ครบ (กำลังเขียน) = ข้าม · ใช้เกมล่าสุด"""
    ev = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and "event" in e:
                ev.append(e)
    # รีสตาร์ท agent กลางแข่ง = new_game ซ้ำในไฟล์เดิม (ล็อตชุดเดิม) → นับเป็นเกมเดียวกัน
    # เกมใหม่จริง = new_game ที่ค่าตัวอย่างล็อตต่างจาก new_game ก่อนหน้า (ตลาดฝึกรีเซ็ต)
    start, prev = 0, None
    for i, e in enumerate(ev):
        if e["event"] == "new_game":
            key = json.dumps(e.get("samples"), sort_keys=True)
            if key != prev:
                start = i
            prev = key
    return ev[start:]


class Game:
    def __init__(self, ev):
        self.ev = ev
        ng = next((e for e in ev if e["event"] == "new_game"), {})
        self.tv = ng.get("tv") or next((e["tv"] for e in ev if e["event"] == "appraisal_sent"), {})
        self.samples = ng.get("samples") or {}
        self.calendar = ng.get("calendar")
        self.opens, self.results, self.sent, self.advice, self.llm, self.order = {}, {}, {}, {}, {}, []
        for i, e in enumerate(ev):
            k, r = e["event"], e.get("round")
            if k == "round_open":
                rid = e["round"]["round_id"]
                self.opens.setdefault(rid, e)
                if rid not in self.order:
                    self.order.append(rid)
            elif k == "round_results" and r not in self.results:
                self.results[r] = (i, e["data"])
            elif k == "offers_sent":
                self.sent.setdefault(r, e)
            elif k == "rule_advice":
                self.advice[r] = e
            elif k == "llm_label":
                self.llm[r] = e
        self.real = [r for r in self.order if (self.opens[r]["round"].get("kind") != "practice")]

    def spec(self, rid, rfq_id):
        for q in self.opens.get(rid, {}).get("rfqs", []):
            if q["rfq_id"] == rfq_id:
                return q.get("spec") or {}
        return None

    def cut(self, rid, row):
        """ราคาตัดต่อใบ = price_max ÷ TV สูงสุดของล็อตที่ผ่านสเปก (เหมือน market_model.market_info)"""
        sp = self.spec(rid, row["rfq_id"])
        if sp is None or not row.get("price_max") or not row.get("bought_kg"):
            return None
        el = [self.tv[l] for l, s in self.samples.items() if l in self.tv and spec_ok(s, sp)]
        return row["price_max"] / max(el) if el else None

    def by_type(self, rid):
        """{type: {"cut": ต่ำสุดของใบที่ซื้อครบ, "ours": [ratio ที่ขายได้], "lost": [ratio ที่แพ้], "sold": n, "n": n}}"""
        data = self.results[rid][1]
        rows = {r["rfq_id"]: r for r in data.get("market_summary", [])}
        out = {}
        for r in rows.values():
            t = r.get("buyer_type")
            d = out.setdefault(t, {"cuts": [], "ours": [], "lost": [], "sold": 0, "n": 0})
            c = self.cut(rid, r)
            if c is not None and r["bought_kg"] >= r["wanted_kg"]:
                d["cuts"].append(c)
        for o in data.get("my_offers", []):
            t = (rows.get(o["rfq_id"]) or {}).get("buyer_type")
            d = out.setdefault(t, {"cuts": [], "ours": [], "lost": [], "sold": 0, "n": 0})
            ratio = o["price_per_kg"] / self.tv[o["lot_id"]] if self.tv.get(o["lot_id"]) else None
            d["n"] += 1
            if o.get("filled_kg"):
                d["sold"] += 1
                if ratio:
                    d["ours"].append(ratio)
            elif ratio:
                d["lost"].append((ratio, o["status"], self.cut(rid, rows.get(o["rfq_id"]) or {"rfq_id": o["rfq_id"]})))
        for d in out.values():
            d["cut"] = min(d["cuts"]) if d["cuts"] else None
        return out

    def stock_after(self, rid):
        """ของเหลือหลังรอบนี้ = lots_kg ตอนเปิดรอบ − kg ที่ขายได้รอบนี้"""
        o = self.opens.get(rid, {})
        left = sum((o.get("lots_kg") or {}).values())
        sold = sum(x.get("filled_kg", 0) for x in self.results[rid][1].get("my_offers", []))
        return left - sold


def f3(x):
    return "–" if x is None else f"{x:.3f}"


def cal_label(g, n):
    try:
        total = len(g.real) or 15
        ts = (g.opens[g.real[0]]["round"].get("of") if g.real else None) or total
        cw = calendar_weights(g.calendar, max(ts, n))
        return cw[n]["label"] or "ปกติ"
    except Exception:       # noqa: BLE001
        return None


def digest(g, rid):
    out = []
    o = g.opens[rid]
    rd = o["round"]
    i_res, data = g.results[rid]
    practice = rd.get("kind") == "practice"
    num, of = rd.get("number"), rd.get("of")
    head = f"== {rid} ({'ซ้อม' if practice else 'จริง'} {num}/{of} · ปฏิทิน: {rd.get('calendar') or 'ปกติ'})"
    if not practice and num:
        nxt = cal_label(g, num + 1) if num < (of or 0) else None
        head += f" · ถัดไป R{num + 1}: {nxt if nxt else 'อ่านไม่ได้'}" if num < (of or 0) else " · รอบสุดท้าย"
    out.append(head + " ==")
    mine = data.get("my_offers", [])
    rows = {r["rfq_id"]: r for r in data.get("market_summary", [])}

    # [1] ตรวจสเปก: ซองที่ src มีคำว่า probe หรือรอบซ้อม
    sent = g.sent.get(rid) or {}
    plan = []
    for n in sent.get("notes") or []:
        if isinstance(n, dict):
            plan += n.get("plan") or []
    probe_keys = {(p.get("lot_id"), p.get("rfq_id")) for p in plan if "probe" in str(p.get("src", ""))}
    res_word = {"ACCEPTED": "ผ่าน", "PARTIAL": "ผ่าน", "OUTBID": "ผ่าน", "SPEC_MISMATCH": "ไม่ผ่าน", "ABOVE_LIMIT": "ไม่ชัด"}
    checks = {}
    for x in mine:
        if practice or (x["lot_id"], x["rfq_id"]) in probe_keys:
            t = (rows.get(x["rfq_id"]) or {}).get("buyer_type", "?")
            key = f"{x['lot_id'].split('-')[-1]}→{t}"
            # ผลชัดสุดต่อคู่ล็อต-ประเภท: ไม่ผ่าน > ผ่าน > ไม่ชัด
            w = res_word.get(x["status"], "ไม่ชัด")
            rank = {"ไม่ผ่าน": 2, "ผ่าน": 1, "ไม่ชัด": 0}
            if key not in checks or rank[w] > rank[checks[key][0]]:
                checks[key] = (w, x["status"])
    if checks:
        out.append("[1 ตรวจสเปก] " + " · ".join(f"LOT-{k}: {w} ({s})" for k, (w, s) in sorted(checks.items())))

    # [2] ขาย
    kg_sent = sum(x["kg"] for x in mine)
    kg_sold = sum(x.get("filled_kg", 0) for x in mine)
    st = {s: sum(x["status"] == s for x in mine) for s in ("ACCEPTED", "PARTIAL", "OUTBID", "ABOVE_LIMIT", "SPEC_MISMATCH")}
    out.append(f"[2 ขาย] ส่ง {len(mine)} ซอง {kg_sent} kg · ขาย {kg_sold} kg ({kg_sold / kg_sent:.0%})" if kg_sent else "[2 ขาย] ไม่ได้ส่งซอง")
    if kg_sent:
        out[-1] += " · " + " · ".join(f"{s} {n}" for s, n in st.items())
    bt = g.by_type(rid)
    for t in TYPES:
        d = bt.get(t)
        if not d:
            continue
        line = f"    {t:10}: "
        if d["n"]:
            line += f"ขาย {d['sold']}/{d['n']} ซอง"
            if d["ours"]:
                line += f" · เรา ×{min(d['ours']):.3f}" + (f"–{max(d['ours']):.3f}" if max(d["ours"]) - min(d["ours"]) > 5e-4 else "")
            for ratio, s, c in d["lost"][:2]:
                line += f" · {s} ×{ratio:.3f} (ตัด {f3(c)}" + (f" · ห่าง {ratio - c:+.3f})" if c is not None else ")")
        else:
            line += "ไม่ได้ส่ง"
        cs = d["cuts"]
        if not cs:
            line += " · ตัด ×–"
        elif len(cs) == 1 or max(cs) - min(cs) < 5e-4:
            line += f" · ตัด ×{min(cs):.3f} ({len(cs)} ใบ)"
        else:
            line += f" · ตัด ×{min(cs):.3f}–{max(cs):.3f} ({len(cs)} ใบ)"
        out.append(line)

    # [3] ของ / capacity
    left = g.stock_after(rid)
    cap = o.get("round_capacity_kg") or 0
    rem_real = len([r for r in g.real if r not in g.results or g.results[r][0] > i_res]) if not practice else None
    if practice:
        tot_real = (g.opens[g.real[0]]["round"].get("of") if g.real else None) or 15
        rem_real = tot_real
    else:
        rem_real = max((of or 0) - (num or 0), 0)
    tight = left / (rem_real * cap) if rem_real and cap else None
    out.append(f"[3 ของ] เหลือ {left} kg · capacity เหลือ {rem_real} รอบ × {cap} = {rem_real * cap} kg · ตึง {f3(tight)}"
               + (" (flood ถ้า > 1.0)" if tight is None or tight <= 1.0 else " ⚠ flood"))

    # [4] shortage
    short = [r for r in rows.values() if r["bought_kg"] < r["wanted_kg"]]
    if short:
        mine_rfq = {x["rfq_id"]: x for x in mine}
        parts = []
        for r in short[:4]:
            x = mine_rfq.get(r["rfq_id"])
            parts.append(f"{r['rfq_id']} {r.get('buyer_type', '?')} {r['bought_kg']}/{r['wanted_kg']}"
                         + (f" (เรา {x['status']})" if x else ""))
        out.append(f"[4 shortage] {len(short)} ใบซื้อไม่ครบ: " + " · ".join(parts) + (" …" if len(short) > 4 else ""))
    else:
        out.append("[4 shortage] ไม่มี (ทุกใบซื้อครบ)")

    # [5] เทศกาล (R3–R8)
    if not practice and num and 3 <= num <= 8:
        sp = [r for r in rows.values() if r.get("buyer_type") == "SPECIALTY"]
        d_s, d_c = bt.get("SPECIALTY") or {}, bt.get("COMMERCIAL") or {}
        out.append(f"[5 เทศกาล] Specialty: {len(sp)} ใบ รวม {sum(r['wanted_kg'] for r in sp)} kg · ซื้อ {sum(r['bought_kg'] for r in sp)} kg"
                   f" · ตัด ×{f3(d_s.get('cut'))} · Commercial ตัด ×{f3(d_c.get('cut'))}")

    # [6] ผิดปกติ: error ตั้งแต่ round_results รอบก่อน
    prev = max((g.results[r][0] for r in g.results if g.results[r][0] < i_res), default=-1)
    errs = [e["event"] for e in g.ev[prev + 1:i_res + 1] if any(e["event"].endswith(b) for b in BAD)]
    lots_left_open = sum((o.get("lots_kg") or {}).values())
    need = min(o.get("capacity_left_kg") or 0, lots_left_open)
    full = kg_sent >= need - 60
    out.append(f"[6 ผิดปกติ] error {len(errs)}" + (f" ({', '.join(errs[:3])})" if errs else "")
               + f" · ส่งซองใช้ {sent.get('seconds', '–')} วิ · ซองครบ capacity: {'ใช่' if full else f'ไม่ ({kg_sent}/{need} kg)'}")

    # ตัวช่วยกฎ + LLM
    a = g.advice.get(rid)
    if a:
        line = "[ตัวช่วยกฎ] " + " · ".join(
            f"{t[:4]}={a['labels'].get(t)}" + (f" ({a['reasons'].get(t)})" if a["labels"].get(t) != "normal" else "")
            for t in TYPES if t in a.get("labels", {}))
        recs = [f"{t[:4]}: {r}" for t, r in (a.get("recs") or {}).items() if r]
        if recs:
            line += " · แนะนำ " + " · ".join(recs)
    else:
        line = "[ตัวช่วยกฎ] ไม่มี"
    ll = g.llm.get(rid)
    if ll:
        line += " · LLM: " + " ".join(f"{t[:4]}={v.get('llm')}" + (f"[{v.get('guard')}]" if v.get("guard") else "")
                                      for t, v in (ll.get("labels") or {}).items())
    else:
        line += " · LLM: ไม่มี"
    out.append(line)
    return out


def trend(g):
    out = [f"{'รอบ':4} {'ขาย%':>5}  {'COMM ตัด/เรา':>13}  {'INST ตัด/เรา':>13}  {'SPEC ตัด/เรา':>13}  {'ของเหลือ':>8}  ป้าย(C/I/S)"]
    for rid in g.order:
        if rid not in g.results:
            continue
        mine = g.results[rid][1].get("my_offers", [])
        ks = sum(x["kg"] for x in mine)
        sold = sum(x.get("filled_kg", 0) for x in mine)
        bt = g.by_type(rid)
        cells = []
        for t in TYPES:
            d = bt.get(t) or {}
            ours = (d.get("ours") or []) + [x[0] for x in d.get("lost") or []]
            cells.append(f"{f3(d.get('cut'))}/{f3(min(ours) if ours else None)}")
        a = g.advice.get(rid)
        short = {"normal": "ปกติ", "undercut": "undercut", "flood": "flood", "shortage": "shortage", "festival_surge": "festival"}
        lab = "/".join(short.get(a["labels"].get(t), a["labels"].get(t) or "–") for t in TYPES) if a else "–"
        out.append(f"{rid:4} {(f'{sold / ks:.0%}' if ks else '–'):>5}  {cells[0]:>13}  {cells[1]:>13}  {cells[2]:>13}  {g.stock_after(rid):8}  {lab}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="logs/decisions.jsonl")
    ap.add_argument("--round")
    ap.add_argument("--trend", action="store_true")
    a = ap.parse_args(argv)
    if not os.path.exists(a.log):
        print(f"ยังไม่มีไฟล์ log: {a.log} (agent ยังไม่เริ่ม หรือรันผิดโฟลเดอร์ · ต้องอยู่ใน work/day20/agent)")
        return
    g = Game(read_log(a.log))
    if not g.results:
        print("ยังไม่มี round_results ใน log")
        return
    if a.trend:
        print("\n".join(trend(g)))
        return
    rid = a.round or max(g.results, key=lambda r: g.results[r][0])
    if rid not in g.results or rid not in g.opens:
        print(f"ไม่มีผลรอบ {rid} ใน log · มี: {', '.join(r for r in g.order if r in g.results)}")
        return
    print("\n".join(digest(g, rid)))


if __name__ == "__main__":
    main()

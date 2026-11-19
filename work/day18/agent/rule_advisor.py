"""ตัวตรวจแบบกฎ (ไม่ใช้ LLM) · สเปก Session B `work/day20/design/llm_behavior_test.md` G0
ทำตาราง DAY3 หัวข้อ 6 เป็นโค้ด: ทุกรอบพิมพ์ "ป้าย" ต่อประเภทผู้ซื้อ + ค่าตั้งที่แนะนำ ลงจอและ log (rule_advice)
**ไม่เปลี่ยนค่าเองและไม่ยุ่งกับซอง** — คนเฝ้าจอตัดสินใจ (วันแข่งห้ามใช้ LLM อื่น · ใช้ตัวนี้แทน)
ป้าย (ลำดับความสำคัญ): flood → undercut → shortage → festival_surge → normal"""
from inventory import spec_ok

TYPES = ("COMMERCIAL", "INSTANT", "SPECIALTY")
BAG = 60
REC = {
    "flood": lambda t: f"$env:SELL_SHIFT_{t}='-0.03' และ $env:MKT_K='2.0'",
    "undercut": lambda t: f"$env:MKT_K_{t}='2.0'",
    "shortage": lambda t: "$env:SHORT_CEIL='1'",
    "festival_surge": lambda t: "ไม่ต้องเปลี่ยน (agent ตามราคาตลาดเทศกาลเอง) · ดูราคาตัด Specialty รอบหน้า",
    "normal": lambda t: "",
}


def _real(rounds: list) -> list:
    return [r for r in rounds if r.get("kind") != "practice"]


def _type_of(memory, rid: str) -> dict:
    return {(o["rfq_id"], o["lot_id"]): o.get("buyer_type") for o in (memory.sent or {}).get(rid, [])}


def _fill(rnd: dict, t: str) -> float | None:
    rows = [x for x in rnd.get("market_summary", []) if x.get("buyer_type") == t]
    want = sum(x.get("wanted_kg") or 0 for x in rows)
    return (sum(x.get("bought_kg") or 0 for x in rows) / want) if want else None


def rule_labels(memory, state: dict, total: int, calendar_label: str = "") -> dict:
    """{type: {"label", "reason", "rec"}} จากผลรอบก่อนๆ (memory) + สถานะรอบนี้"""
    rounds = list(getattr(memory, "rounds", []) or [])
    real = _real(rounds)
    n = (state.get("round") or {}).get("number") or 1
    left = max(1, total - n + 1)
    cap = (state.get("round_capacity_kg") or 0) // BAG
    sellable = sum(l["kg_available"] // BAG for l in state["lots"])
    out = {}
    for t in TYPES:
        lost = []
        sold_all = None
        for r in real[-2:]:
            ty = _type_of(memory, r["round_id"])
            mine = [o for o in r.get("my_offers", []) if ty.get((o["rfq_id"], o["lot_id"])) == t]
            lost.append(any(o["status"] == "OUTBID" for o in mine))
            if r is real[-1]:
                sold_all = bool(mine) and all((o.get("filled_kg") or 0) >= (o.get("kg") or 0) for o in mine)
        lost2 = len(lost) == 2 and all(lost)
        fills = [f for f in (_fill(r, t) for r in rounds[-2:]) if f is not None]
        eligible = any(spec_ok(l["sample"], q["spec"]) for l in state["lots"] if l["kg_available"] >= BAG
                       for q in state.get("rfqs", []) if q["buyer_type"] == t)
        short2 = len(fills) == 2 and all(f < 0.5 for f in fills) and eligible
        flood = cap > 0 and sellable > cap * left
        fest = False
        if t == "SPECIALTY" and "เทศกาล" in (calendar_label or ""):
            now = sum(q.get("bags", 0) for q in state.get("rfqs", []) if q["buyer_type"] == t)
            early = [sum((x.get("wanted_kg") or 0) for x in r.get("market_summary", []) if x.get("buyer_type") == t) / BAG
                     for r in real[:5]]
            base = sum(early) / len(early) if early else 0
            fest = base > 0 and now >= 1.5 * base
        if flood:
            label, why = "flood", f"ของ {sellable} กระสอบ > capacity ที่เหลือ {cap}×{left}"
        elif lost2:
            label, why = "undercut", "เราแพ้ราคา (OUTBID) 2 รอบติด"
        elif short2 and not (lost and lost[-1]):
            label, why = "shortage", f"ผู้ซื้อซื้อได้ {fills[0]:.0%}/{fills[1]:.0%} (<50%) 2 รอบติด และเรามีล็อตผ่านสเปก"
        elif fest:
            label, why = "festival_surge", "เทศกาล: Specialty ต้องการ ≥ 1.5 เท่าของ R1–R5"
        else:
            label, why = "normal", ("รอบก่อนขายครบ" if sold_all else "ไม่มีสัญญาณ")
        out[t] = {"label": label, "reason": why, "rec": REC[label](t), "sold_all": bool(sold_all),
                  "lost_last": bool(lost and lost[-1]), "sellable": sellable, "cap_left": cap * left,
                  "facts": {"buyer_type": t, "round": (state.get("round") or {}).get("round_id"), "calendar": calendar_label or "",
                            "unsold_bags_exceed_capacity_left": bool(flood), "we_lost_outbid_both_last_2_rounds": bool(lost2),
                            "we_lost_outbid_last_round": bool(lost and lost[-1]), "we_sold_all_last_round": bool(sold_all),
                            "buyer_bought_under_50pct_both_last_2_rounds": len(fills) == 2 and all(f < 0.5 for f in fills),
                            "we_have_lot_passing_spec": bool(eligible), "specialty_festival_demand_surge": bool(fest)}}
    return out


def format_line(rid: str, labels: dict) -> str:
    parts = [f"{t[:4]}={v['label']}" for t, v in labels.items()]
    recs = [f"{t[:4]}: {v['rec']} ({v['reason']})" for t, v in labels.items() if v["label"] != "normal"]
    return f"[ตัวช่วยกฎ {rid}] " + " · ".join(parts) + ("\n    แนะนำ → " + "\n    แนะนำ → ".join(recs) if recs else " · ไม่ต้องเปลี่ยน")


# ---------- ทดสอบเท่านั้น: ทำตามคำแนะนำอัตโนมัติ (RULE_AUTO=1 · ค่าเริ่มปิด · วันแข่งคนทำตามตาราง DAY3 หัวข้อ 6) ----------
_AUTO = {"streak": {}, "owned": set(), "on": {}}


def auto_apply(labels: dict, round_no: int) -> list:
    """ตั้ง/ถอด os.environ ตามตาราง DAY3 หัวข้อ 6 (มีผลรอบถัดไป) · คืนรายการที่เปลี่ยน"""
    import os
    if round_no <= 1:                          # เกมใหม่ → ล้างสิ่งที่ตั้งไว้
        for k in _AUTO["owned"]:
            os.environ.pop(k, None)
        _AUTO.update(streak={}, owned=set(), on={})
    changes = []

    def put(k, v):
        if os.environ.get(k) != v:
            os.environ[k] = v
            _AUTO["owned"].add(k)
            changes.append(f"{k}={v}")

    def drop(k):
        if k in _AUTO["owned"] and k in os.environ:
            os.environ.pop(k)
            changes.append(f"-{k}")

    any_flood = False
    for t, v in labels.items():
        lab = v["label"]
        st = _AUTO["streak"].get(t, ("", 0))
        _AUTO["streak"][t] = (lab, st[1] + 1 if st[0] == lab else 1)
        n = _AUTO["streak"][t][1]
        if lab == "flood":
            any_flood = True
            put(f"SELL_SHIFT_{t}", "-0.03")
        else:
            drop(f"SELL_SHIFT_{t}")
        if lab == "undercut" and n >= 2 and v["sellable"] > 0.6 * max(v["cap_left"], 1):
            put(f"MKT_K_{t}", "2.0")
        elif v["sold_all"] and _AUTO["on"].get(("sold", t), 0) >= 1:
            drop(f"MKT_K_{t}")
        _AUTO["on"][("sold", t)] = _AUTO["on"].get(("sold", t), 0) + 1 if v["sold_all"] else 0
        if lab == "shortage" and n >= 2 and v["sold_all"]:
            put("SHORT_CEIL", "1")
            put("SHORT_FILL", "0.5")
        elif v["lost_last"] and "SHORT_CEIL" in _AUTO["owned"]:
            drop("SHORT_CEIL")
    if any_flood:
        put("MKT_K", "2.0")
    else:
        drop("MKT_K")
    return changes

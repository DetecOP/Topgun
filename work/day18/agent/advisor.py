"""LLM Advisor (LLM_DESIGN.md) — ปรับตัวคูณต่อประเภท ±0.03 + โหมดปริมาณ · Python บีบทุกค่า

ใช้ได้เฉพาะ gateway ของงาน (model event-llm) · ตอบไม่ทัน/ผิดรูป = คืน None แล้ว agent ใช้ราคาโมเดลต่อ
"""
import json
import math
import time

MAX_ADJ = 0.03
ABS_CONFUSED = 0.1   # |adjust| เกินนี้ = LLM สับสนส่งราคาเต็ม ไม่ใช่ค่าปรับ
VOLUME = {"hold": 1.0 / 1.3, "normal": 1.0, "push": 1.6 / 1.3}

SYSTEM = """You tune prices for a coffee seller agent in a sealed-offer market with 56 competing teams.
price = ratio x true value (TV). Buyers take the lowest price/TV first and reject offers above
their hidden ceiling. Unsold beans are worth 0.80 x TV at the end.
Signals: ABOVE_LIMIT = above that buyer's ceiling. OUTBID = other teams were cheaper.
fill < 100% with many offers = most offers were above the ceiling.
The program already computed a safe ratio per buyer type. You may move each by at most 0.03,
and choose the volume mode for this round. Answer only JSON."""

SCHEMA = {"type": "object", "required": ["adjust", "volume", "reason"], "properties": {
    "adjust": {"type": "object", "properties": {
        "SPECIALTY": {"type": "number"}, "COMMERCIAL": {"type": "number"}, "INSTANT": {"type": "number"}}},
    "volume": {"type": "string", "enum": ["hold", "normal", "push"]},
    "reason": {"type": "string", "maxLength": 200}}}


def _r(x, nd=3):
    return "-" if x is None else round(x, nd)


def build_user(state: dict, meta: dict, summary: dict, cal: dict, total: int) -> str:
    rnd = state["round"]
    n = rnd.get("number") or 0
    ahead = ", ".join(f"R{k} {cal[k]['label'] or 'normal'} ({cal[k]['w']})" for k in range(n + 1, min(total, n + 2) + 1) if k in cal)
    lines = [f"Round {n} of {total} (phase {meta.get('phase')}, calendar {rnd.get('calendar')}). Next: {ahead or 'none'}.",
             f"Bags left sellable: {meta.get('sellable_bags')}, planned this round: {meta.get('budget_bags')}.",
             "Per buyer type (whole game so far):"]
    tgt = {}
    for k, v in (meta.get("targets") or {}).items():
        tgt.setdefault(k.split("|")[1], v["ratio"])
    for t in ("COMMERCIAL", "INSTANT", "SPECIALTY"):
        s = summary.get(t)
        if not s and t not in tgt:
            continue
        s = s or {}
        st = s.get("status", {})
        lines.append(f"  {t} model {_r(tgt.get(t))} | accepted max {_r(s.get('accepted_max'))} | "
                     f"outbid min {_r((s.get('clear') or {}).get('hi'))} | above_limit min {_r((s.get('ceil') or {}).get('hi'))} | "
                     f"fill {_r(s.get('fill'), 2)} offers/bag {_r(s.get('crowd'), 2)} | "
                     f"counts A{st.get('ACCEPTED', 0)} O{st.get('OUTBID', 0)} L{st.get('ABOVE_LIMIT', 0)}")
    lines.append(f"Detected: {json.dumps(meta.get('scenarios'), ensure_ascii=False)}")
    lines.append("Choose adjustments.")
    return "\n".join(lines)


def ask(llm, state: dict, meta: dict, summary: dict, cal: dict, total: int, seconds_left: float) -> dict:
    """คืน {"ok", "adjust", "volume", "reason", "raw", "latency_s"} เสมอ (ไม่ raise)"""
    out = {"ok": False, "adjust": {}, "volume": 1.0, "reason": "", "raw": None, "latency_s": None}
    budget = min(60.0, (seconds_left or 0) - 5)
    if llm is None or budget < 3:
        out["reason"] = "no llm / no time"
        return out
    user = build_user(state, meta, summary, cal, total)
    t0 = time.time()
    ans = llm.ask_json(SYSTEM, user, SCHEMA, timeout=budget)
    out["latency_s"] = round(time.time() - t0, 1)
    out["raw"] = ans
    out["prompt_chars"] = len(SYSTEM) + len(user)
    if not isinstance(ans, dict) or not isinstance(ans.get("adjust"), dict):
        out["reason"] = f"llm failed: {getattr(llm, 'last_error', None)}"
        return out
    adj, dropped = {}, {}
    for t, v in ans["adjust"].items():
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if t not in ("SPECIALTY", "COMMERCIAL", "INSTANT") or not math.isfinite(v):
            continue
        # guard 1: ค่าเกิน 0.1 = LLM ส่ง "ราคาเต็ม" (เช่น 0.93) มาแทน "ค่าปรับ" → ทิ้ง
        if abs(v) > ABS_CONFUSED:
            dropped[t] = f"{v} (absolute?)"
            continue
        # guard 2: รอบที่แล้วประเภทนี้โดน OUTBID/ABOVE_LIMIT แต่ LLM สั่งขึ้นราคา = ผิดทิศ → ทิ้ง
        last = (summary.get(t) or {}).get("last") or {}
        if v > 0 and (last.get("OUTBID", 0) or last.get("ABOVE_LIMIT", 0)):
            dropped[t] = f"+{v} after O{last.get('OUTBID', 0)} L{last.get('ABOVE_LIMIT', 0)}"
            continue
        adj[t] = max(-MAX_ADJ, min(MAX_ADJ, v))
    out["dropped"] = dropped
    vol = VOLUME.get(ans.get("volume"), 1.0)
    if meta.get("phase") == "final":
        vol = VOLUME["push"]
    out.update(ok=True, adjust={k: round(v, 4) for k, v in adj.items() if abs(v) >= 0.001}, volume=vol,
               reason=str(ans.get("reason", ""))[:200])
    return out

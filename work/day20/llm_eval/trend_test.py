"""LLM ทำนายทิศราคาตัดรอบหน้า (up/flat/down) จากประวัติข้ามรอบ · ข้อมูลตลาดแข่งด่าน 2 จริง (trend_cases.jsonl)
แบบ raw = ประวัติราคาตัดรายรอบ · แบบ feat = + ข้อเท็จจริงที่ Python คำนวณ (เปลี่ยนรอบล่าสุด · ห่างจากค่าเฉลี่ย · fill · ซองต่อกระสอบ)
เทียบกับ baseline: down เสมอ 19/34 · กลับทิศรอบล่าสุด 22/34 · gateway :4000 · ห่าง 4 วิ/คำขอ · ไม่แตะตลาด
python ../../day20/llm_eval/trend_test.py raw|feat   (รันในโฟลเดอร์ work/day18/agent)"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.getcwd())
import main  # noqa: E402
from llm import LLM  # noqa: E402

os.environ.pop("AGENT_ENV", None)
main.load_env(main.HERE / ".env")
main.load_env(main.STARTER_ENV)
HERE = Path(__file__).parent
MODE = sys.argv[1] if len(sys.argv) > 1 else "raw"
llm = LLM(os.environ["LLM_BASE_URL"], os.environ.get("LLM_MODEL", "event-llm"), os.environ["LLM_API_KEY"],
          timeout=40, thinking=False, max_tokens=200, temperature=0.0)
SCHEMA = {"type": "object", "required": ["direction", "reason"], "properties": {
    "direction": {"type": "string", "enum": ["up", "flat", "down"]}, "reason": {"type": "string", "maxLength": 150}}}
SYSTEM = ("You forecast next round's clearing price ratio for ONE buyer in a sealed-bid coffee market with 56 competing sellers. "
          "Clearing ratio = highest accepted price / true value. Predict whether next round's median clearing ratio will be "
          "up (> +0.005), flat (within 0.005) or down (< -0.005) versus the latest round. Answer only JSON.")
C = [json.loads(x) for x in open(HERE / "trend_cases.jsonl", encoding="utf-8")]


def prompt(c):
    hist = [{k: h[k] for k in ("round", "low", "median", "high", "fill", "offers_per_bag")} for h in c["history"]]
    u = {"buyer_type": c["buyer_type"], "history_oldest_first": hist}
    if MODE == "feat":
        m = [h["median"] for h in c["history"]]
        u["facts"] = {"change_last_round": round(m[-1] - m[-2], 4), "latest_minus_history_mean": round(m[-1] - sum(m) / len(m), 4),
                      "rounds_of_history": len(m), "latest_fill": c["history"][-1]["fill"],
                      "latest_offers_per_bag": c["history"][-1]["offers_per_bag"]}
    return json.dumps(u, ensure_ascii=False)


hit, out, last = 0, [], 0.0
for c in C:
    w = last + 4.0 - time.time()
    if w > 0:
        time.sleep(w)
    last = time.time()
    a = llm.ask_json(SYSTEM, prompt(c), SCHEMA, timeout=40)
    d = a.get("direction") if isinstance(a, dict) else None
    hit += d == c["gold_dir"]
    out.append({"id": c["id"], "gold": c["gold_dir"], "llm": d, "reason": (a or {}).get("reason") if isinstance(a, dict) else llm.last_error})
with open(HERE / f"trend_results_{MODE}.jsonl", "w", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
dist = {k: sum(r["llm"] == k for r in out) for k in ("up", "flat", "down", None)}
print(f"[{MODE}] LLM ทิศถูก {hit}/{len(C)} · ตอบ {dist} · baseline: down เสมอ 19/34 · กลับทิศรอบล่าสุด 22/34")

"""ต้องใช้ market_model_experimental.py (มี hook MKT_K_BUYER) แทน market_model.py ของ agent · ไม่อยู่ในชุดแข่ง
K0 (สเปก B llm_trend_plan.md): เพดาน oracle ของการเลือก k รายผู้ซื้อ-รายรอบ บน replay ด่าน 2 (ไม่ใช้ LLM)
ต่อจุด (ผู้ซื้อ, รอบถัดไป) ลอง k ∈ {1.0, 2.0} โดยจุดอื่นคง 1.5 → ผลต่าง PR · oracle ≈ ผลรวมส่วนที่บวก (ขอบบนแบบประมาณ)
แล้วยืนยันด้วยการใช้ k ที่ดีสุดทุกจุดพร้อมกันในการรันเดียว · replay (ซองตรวจสเปก = ตก)
รันในโฟลเดอร์ work/day20/agent"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPLAY = HERE.parent / "tools" / "replay_label.py"
C = [json.loads(x) for x in open(HERE / "trend_cases.jsonl", encoding="utf-8")]


def pr(label_round=None, env=None, extra=None):
    e = {**os.environ, "PYTHONIOENCODING": "utf-8", "USE_LLM": "0", **(extra or {})}
    if label_round:
        e.update(LABEL_ROUND=label_round, LABEL_ENV=json.dumps(env))
    out = subprocess.run([sys.executable, str(REPLAY)], env=e, capture_output=True, text=True, encoding="utf-8").stdout
    return float([x for x in out.splitlines() if "PR ≈" in x][-1].split("PR ≈ ")[1].split()[0])


base = pr()
print(f"B0 (k=1.5 ทุกจุด) replay PR {base:.4f}")
best = {}
gain = 0.0
for c in C:
    rnd = c["next"]["round"]
    if rnd in ("P1", "R1", "R2"):
        continue                    # สเปก: ไม่ใช้ในรอบซ้อม/R1–R2
    row = {}
    for k in (1.0, 2.0):
        row[k] = pr(rnd, {"MKT_K_BUYER": json.dumps({c["buyer"]: k}, ensure_ascii=False)}) - base
    kb = max(row, key=row.get)
    if row[kb] > 0:
        best.setdefault(rnd, {})[c["buyer"]] = kb
        gain += row[kb]
    print(f"{rnd} {c['buyer'][:12]:12} k1.0 {row[1.0]:+.4f} · k2.0 {row[2.0]:+.4f} · gold_dir {c['gold_dir']}", flush=True)
print(f"\noracle (ผลรวมส่วนบวกแยกจุด) ≈ +{gain:.4f}")
# ยืนยัน: ใช้ k ที่ดีสุดทุกจุดพร้อมกัน → ต้องตั้ง env ต่างกันต่อรอบ · replay_label รองรับรอบเดียว จึงรวมทีละรอบแบบสะสม (ประมาณ)
print("จุดที่ k อื่นดีกว่า 1.5:", {r: {b[:10]: k for b, k in v.items()} for r, v in best.items()})

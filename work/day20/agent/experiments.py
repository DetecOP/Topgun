"""รันชุดทดลองต่อกันในตลาดฝึกแบบเร่ง (ทีมรันเอง) แล้วสรุปด้วย analyze_logs.py

    python experiments.py                      # ทุกชุดใน PLAN · ชุดละ 40 เกม
    python experiments.py --games 30
    python experiments.py --only baseline delta-wide

แต่ละชุด = ค่า .env ที่เปลี่ยน (ไม่เปลี่ยน = ใช้ค่าเริ่มในโค้ด) · ชื่อชุดลง log ด้วย AGENT_TAG
ทุกชุด: SANDBOX_FAST=1 · FREEZE_LEARNED=1 (เริ่มจาก learned.json เดียวกัน) · MAX_GAMES=N · USE_LLM=0
ทำงานเฉพาะตลาดฝึก: main.py กดข้าม/reset เฉพาะเมื่อ /v1/version = sandbox · ห้ามรันตอนตลาดแข่ง
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
# ชื่อชุด -> ค่า .env ที่ต่างจากค่าเริ่ม (แก้/เพิ่มได้)
PLAN = {
    "baseline": {},                                                   # ค่าเริ่มในโค้ด (DELTA 1.0/0.75/1)
    "delta-narrow": {"DELTA_DEFECT": "0.6", "DELTA_MOISTURE": "0.45"},  # ระยะเผื่อแคบ = ส่งล็อตชิดขอบมากขึ้น
    "delta-wide": {"DELTA_DEFECT": "1.4", "DELTA_MOISTURE": "1.0"},     # ระยะเผื่อกว้าง = ระวัง SPEC_MISMATCH มากขึ้น
    "no-reserve": {"RESERVE_SPECIALTY": "0"},                         # ไม่สงวนล็อตเกรด Specialty
    "old-pacing": {"PACE_BY_SELLRATE": "0"},                          # งบกระสอบแบบเดิม (ก่อน pace3)
    "mid-push": {"PACE_MODE": "midpush"},                             # ต้นเกมขายแบบเดิม · กลางเกมใช้ capacity เต็ม
}
CLEAR = ["DELTA_DEFECT", "DELTA_MOISTURE", "DELTA_SCREEN", "SPEC_P_MIN", "RESERVE_SPECIALTY", "PACE_BY_SELLRATE",
         "PACE_MODE", "AGENT_TAG"]


def main():
    games = int(sys.argv[sys.argv.index("--games") + 1]) if "--games" in sys.argv else 40
    plan = PLAN
    if "--only" in sys.argv:
        want = sys.argv[sys.argv.index("--only") + 1:]
        plan = {k: v for k, v in PLAN.items() if k in want}
    print(f"จะรัน {len(plan)} ชุด × {games} เกม (ประมาณ {len(plan) * games * 10 // 60} นาที)", flush=True)
    for name, extra in plan.items():
        env = {k: v for k, v in os.environ.items() if k not in CLEAR}
        env.update(extra)
        env.update(AGENT_TAG=name, SANDBOX_FAST="1", FREEZE_LEARNED="1", MAX_GAMES=str(games), USE_LLM="0",
                   PYTHONIOENCODING="utf-8")
        print(f"\n===== ชุด {name} {extra or ''} =====", flush=True)
        r = subprocess.run([sys.executable, str(HERE / "main.py"), "--forever"], env=env, cwd=HERE)
        if r.returncode != 0:
            print(f"ชุด {name} จบด้วยรหัส {r.returncode} · หยุดการทดลอง", flush=True)
            break
    print("\n===== สรุป =====", flush=True)
    subprocess.run([sys.executable, str(HERE / "analyze_logs.py")], env={**os.environ, "PYTHONIOENCODING": "utf-8"}, cwd=HERE)


if __name__ == "__main__":
    main()

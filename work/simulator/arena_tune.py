# arena_tune.py · ลองปรับค่าโมเดลของเราในสนามหลายทีม (arena.py) แล้วดูว่าแบบไหนได้อันดับดีสุด
# รัน: .venv\Scripts\python.exe simulator\arena_tune.py 200
# ทุกแบบเจอคู่แข่งชุดเดียวกัน (จับคู่) · ± = ค่าคลาดเคลื่อนของ "อันดับต่างจากแบบแรกในรายการ"
import statistics as st
import sys

import arena
import config
from scoring import MODES
from valuation import load_params

sys.stdout.reconfigure(encoding="utf-8")
n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
config.MAX_OFFERS_PER_ROUND, config.MAX_KG_PER_ROUND = 99, 10 ** 9
o = arena.ours
VARIANTS = {
    "v2 (ค่าปัจจุบัน)": lambda m: o(m),
    "รอวัด + บวก 8% คงที่": lambda m: o(m, wait=True, fixed=0.08),
    "v2 สำรวจน้อย (ไม่สุ่ม)": lambda m: o(m, explore=False),
    "v2 ระดับราคาแคบ 0–15%": lambda m: o(m, levels=[0.0, 0.03, 0.06, 0.08, 0.10, 0.12, 0.15]),
    "v2 รอวัด ระดับแคบ": lambda m: o(m, wait=True, levels=[0.0, 0.03, 0.06, 0.08, 0.10, 0.12, 0.15]),
    "v2 ระดับแคบ + ไม่สุ่ม": lambda m: o(m, explore=False, levels=[0.0, 0.03, 0.06, 0.08, 0.10, 0.12, 0.15]),
}
params, _ = load_params()
stats, _ = arena.evaluate(params, VARIANTS, n)
base = next(iter(stats.values()))   # แบบแรกในรายการ = ตัวเทียบ
for mode in MODES:
    print(f"\n== {mode} ({n} ทัวร์นาเมนต์, อันดับเฉลี่ย น้อย = ดี)")
    for name, s in stats.items():
        d = [a - b for a, b in zip(s[mode], base[mode])]
        se = st.stdev(d) / len(d) ** 0.5 if any(d) else 0.0
        print(f"  {name:<24}{st.mean(s[mode]):>6.2f}   ท็อป3 {sum(r <= 3 for r in s[mode]) / len(d):>4.0%}"
              f"   ต่างจากแบบแรก {st.mean(d):+.2f} ±{se:.2f}")

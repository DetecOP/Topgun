# ablation.py · ทดสอบว่าแต่ละส่วนของตัวเรียนราคาช่วยจริงไหม (เปิด/ปิดทีละส่วน เทียบกับ v1)
# รัน: .venv\Scripts\python.exe simulator\ablation.py   (~1 นาที)
# ใช้ seed เดียวกันทุกแบบ แล้วเทียบแบบจับคู่ → ± คือค่าคลาดเคลื่อน ส่วนต่าง > 2 เท่าของ ± ถือว่าเชื่อได้
import sys, statistics as st
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import run_sim, config
from pricer import BuyerPriceLearner
from valuation import load_params
params, _ = load_params()
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
variants = {
  "v1 (เดิม)":                 dict(pool_weight=0.0, horizon_aware=False, informative_prior=False),
  "pool":                      dict(pool_weight=0.3, horizon_aware=False, informative_prior=False),
  "pool+prior":                dict(pool_weight=0.3, horizon_aware=False, informative_prior=True),
  "pool+prior+horizon":        dict(pool_weight=0.3, horizon_aware=True,  informative_prior=True),
  "prior+horizon":             dict(pool_weight=0.0, horizon_aware=True,  informative_prior=True),
}
for mode in ("diff","ratio","penalty"):
    print("==", mode, f"({N} เกม, ±=ค่าคลาดเคลื่อนของค่าเฉลี่ยเทียบ v1 แบบจับคู่)")
    base = None
    for name, kw in variants.items():
        run_sim.make_learner = lambda v, seed, kw=kw: BuyerPriceLearner(seed=seed, **kw)
        xs=[]; sold=0; lots=0
        for g in range(N):
            s,k,ar,n = run_sim.play(params, run_sim.TEAM_STRATEGY, mode, seed=config.RANDOM_SEED+g)
            xs.append(s); sold+=k; lots+=n
        if base is None: base = xs
        d = [a-b for a,b in zip(xs, base)]
        se = st.stdev(d)/N**0.5 if any(d) else 0
        print(f"  {name:<22}{st.mean(xs):>10.2f}{sold/lots:>7.0%}   ต่างจาก v1 {st.mean(d):>+9.2f} ±{se:.2f}")

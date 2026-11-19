"""A/B แบบจับคู่ seed: python ab.py '<markets json>' '<configs json>' [seeds]
markets = {"ชื่อ": {env ตลาด}} · configs = {"ชื่อ": {env}} (ชุดแรก = ฐาน)"""
import json, math, statistics as st, sys
from concurrent.futures import ThreadPoolExecutor
import tune
markets = json.loads(sys.argv[1]); configs = json.loads(sys.argv[2]); n = int(sys.argv[3]) if len(sys.argv) > 3 else 200
tune.MARKETS.update(markets)
seeds = {m: list(range(50001 + 1000 * i, 50001 + 1000 * i + n)) for i, m in enumerate(markets)}
jobs = [(c, m) for c in configs for m in markets]
with ThreadPoolExecutor(4) as ex:
    res = dict(zip(jobs, ex.map(lambda j: tune.run_mock(configs[j[0]], j[1], seeds[j[1]]), jobs)))
base = list(configs)[0]
for m in markets:
    print(f"== {m}")
    for c in configs:
        a = res[(c, m)]; line = f"  {c:22} PR {st.mean(a):.4f} (ต่ำสุด {min(a):.3f})"
        if c != base:
            d = [x - y for x, y in zip(a, res[(base, m)])]
            line += f" · ต่าง {st.mean(d):+.4f} ± {st.stdev(d) / math.sqrt(len(d)):.4f}"
        print(line, flush=True)

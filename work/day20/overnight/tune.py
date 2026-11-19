"""จูนค่าตั้งราคาด้วยตลาดจำลองทั้งคืน (ไม่แตะ API ผู้จัด)

ทำซ้ำไปเรื่อยๆ: แต่ละรอบใช้ seed ชุดใหม่ (กันจูนพอดีกับ seed เดิม) · ลองเปลี่ยนค่าทีละตัวจาก "ชุดดีสุด" ปัจจุบัน
เทียบแบบจับคู่ seed ต่อ seed กับชุดดีสุด (ตลาดเดียวกัน เกมเดียวกัน) ใน 2 ตลาด:
  S3 = จำลองด่าน 3 (15 รอบ + ซ้อม P1–P2 + เทศกาล ×1.6) · R8 = จำลองแบบตลาดแข่งด่าน 2 (8 รอบ)
  + replay log ตลาดแข่งจริงด่าน 2 (เกมเดียว ใช้เป็นตัวกัน ไม่ใช่ตัวเลือก)
รับค่าใหม่เมื่อ: S3 ดีกว่า > 2 SE · R8 ไม่แย่กว่า 1 SE · replay ไม่แย่กว่า 0.003
ผล: tune_results.jsonl (ทุกการทดลอง) · best_env.json (ชุดดีสุด) · tune_summary.md (อ่านง่าย)
ไม่แก้โค้ด agent เอง — Claude อ่านผลแล้วแก้ค่าเริ่ม + รันชุดทดสอบเอง
"""
import json
import math
import os
import statistics as st
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
AGENT = HERE.parent.parent / "day18" / "agent"
PY = sys.executable
SCRATCH_REPLAY = Path(os.environ.get("REPLAY_PY", ""))
N_SEEDS = int(os.environ.get("TUNE_SEEDS", "60"))
WORKERS = int(os.environ.get("TUNE_WORKERS", "4"))

GRID = {
    "MKT_K": ["1.25", "1.75"],
    "MKT_VOL_MARGIN": ["0", "0.01"],
    "EARLY_MARGIN": ["0.0025", "0.01"],
    "SPREAD": ["0.5", "0.8"],
    "SPREAD_GAP": ["0.02", "0.05"],
    "MARKET_FLOOR": ["0.84", "0.86"],
    "MKT_K_COMMERCIAL": ["1.0", "1.25"],
    "MKT_K_SPECIALTY": ["2.0"],
    "MKT_K_INSTANT": ["1.25", "2.0"],
    "MKT_K_EARLY": ["1.0", "2.0"],
    "FRONT_LOW": ["1"],
    "MKT_SHORTAGE": ["1"],
    "FESTIVAL_HOLD": ["0.3"],
}
BASE_ENV = {"USE_LLM": "0", "PYTHONIOENCODING": "utf-8"}
MARKETS = {
    "S3": {"MOCK_STYLE": "real", "MOCK_STAGE": "3", "FEST_DEMAND": "1.6", "FEST_CROWD": "1.0"},
    "R8": {"MOCK_STYLE": "real"},
}

RUNNER = r'''
import os, sys, io, json, contextlib
sys.path.insert(0, os.getcwd())
import mock_market as mm
seeds = json.loads(sys.argv[1])
with contextlib.redirect_stdout(io.StringIO()):
    res = mm.run(seeds, float(os.environ.get("MOCK_NOISE", "0.3")))[:-1]
print(json.dumps([r["pr"] for r in res]))
print(json.dumps([r.get("spec_mis", 0) for r in res]), file=sys.stderr)
'''


def run_mock(env: dict, market: str, seeds: list[int]) -> list[float]:
    e = {**os.environ, **BASE_ENV, **MARKETS[market], **env}
    out = subprocess.run([PY, "-c", RUNNER, json.dumps(seeds)], cwd=AGENT, env=e, capture_output=True,
                         text=True, encoding="utf-8", timeout=3600)
    return json.loads(out.stdout.strip().splitlines()[-1])


def run_replay(env: dict) -> float | None:
    if not SCRATCH_REPLAY.exists():
        return None
    e = {**os.environ, **BASE_ENV, **env}
    out = subprocess.run([PY, str(SCRATCH_REPLAY)], cwd=AGENT, env=e, capture_output=True, text=True,
                         encoding="utf-8", timeout=600)
    line = out.stdout.strip().splitlines()[-1]
    try:
        return float(line.split("PR ≈ ")[1].split()[0])
    except Exception:
        return None


def evaluate(env: dict, seeds: dict) -> dict:
    return {"S3": run_mock(env, "S3", seeds["S3"]), "R8": run_mock(env, "R8", seeds["R8"]), "replay": run_replay(env)}


def paired(a: list[float], b: list[float]) -> tuple[float, float]:
    d = [x - y for x, y in zip(a, b)]
    return st.mean(d), st.stdev(d) / math.sqrt(len(d))


def log(row: dict) -> None:
    with open(HERE / "tune_results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def summary(best: dict, history: list[str]) -> None:
    lines = [f"# จูนตลาดจำลองทั้งคืน · อัปเดต {datetime.now():%H:%M}", "",
             f"ชุดดีสุดตอนนี้ (เทียบค่าเริ่มของโค้ด): `{json.dumps(best, ensure_ascii=False)}`", "",
             "| รอบ | ค่าที่ลอง | S3 ต่าง (±SE) | R8 ต่าง (±SE) | replay | ผล |", "|---|---|---|---|---|---|"] + history[-80:]
    (HERE / "tune_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    best_path = HERE / "best_env.json"
    best = json.loads(best_path.read_text(encoding="utf-8")) if best_path.exists() else {}
    history = []
    it = int(os.environ.get("TUNE_START_ITER", "1"))
    while True:
        seeds = {m: list(range(10000 * it + 101 + k * 1000, 10000 * it + 101 + k * 1000 + N_SEEDS))
                 for k, m in enumerate(MARKETS)}
        t0 = time.time()
        base = evaluate(best, seeds)
        log({"iter": it, "kind": "base", "env": best, "S3": st.mean(base["S3"]), "R8": st.mean(base["R8"]),
             "replay": base["replay"], "time": datetime.now().isoformat(timespec="seconds")})
        cands = []
        for k, vals in GRID.items():
            for v in vals:
                if best.get(k) == v:
                    continue
                cands.append({**best, k: v})
        with ThreadPoolExecutor(WORKERS) as ex:
            results = list(ex.map(lambda env: (env, evaluate(env, seeds)), cands))
        accepted = None
        best_gain = 0.0
        for env, r in results:
            ch = {k: v for k, v in env.items() if best.get(k) != v}
            m3, se3 = paired(r["S3"], base["S3"])
            m8, se8 = paired(r["R8"], base["R8"])
            rp = None if r["replay"] is None or base["replay"] is None else r["replay"] - base["replay"]
            ok = m3 > 2 * se3 and m8 > -se8 and (rp is None or rp >= -0.003)
            log({"iter": it, "kind": "cand", "change": ch, "S3_d": round(m3, 5), "S3_se": round(se3, 5),
                 "R8_d": round(m8, 5), "R8_se": round(se8, 5), "replay_d": rp, "ok": ok})
            history.append(f"| {it} | `{json.dumps(ch, ensure_ascii=False)}` | {m3:+.4f} ±{se3:.4f} | {m8:+.4f} ±{se8:.4f} | "
                           f"{'–' if rp is None else f'{rp:+.4f}'} | {'**รับ**' if ok else ''} |")
            if ok and m3 > best_gain:
                accepted, best_gain = env, m3
        if accepted is not None:
            best = accepted
            best_path.write_text(json.dumps(best, ensure_ascii=False, indent=1), encoding="utf-8")
            history.append(f"| {it} | → ชุดดีสุดใหม่ `{json.dumps(best, ensure_ascii=False)}` | | | | |")
        history.append(f"| {it} | (base S3 {st.mean(base['S3']):.4f} · R8 {st.mean(base['R8']):.4f} · "
                       f"replay {base['replay']} · {time.time() - t0:.0f} วินาที) | | | | |")
        summary(best, history)
        it += 1


if __name__ == "__main__":
    main()

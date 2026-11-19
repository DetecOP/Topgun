import json, glob, os, time, collections
H = os.path.dirname(os.path.abspath(__file__))
out = open(os.path.join(H, "..", "results", "sandbox_run.out"), encoding="utf-8").read().splitlines()
print("sandbox first:", out[0][:50], "| last:", out[-1][:30], "| file age s:", int(time.time() - os.path.getmtime(os.path.join(H, "..", "results", "sandbox_run.out"))))
n = sum(1 for f in glob.glob(os.path.join(H, "..", "data", "sandbox_agent", "logs", "runs", "*.jsonl")) for l in open(f, encoding="utf-8") if '"event": "reveal"' in l[:80])
print("reveals:", n, "| tune_summary age s:", int(time.time() - os.path.getmtime(os.path.join(H, "..", "results", "tune_summary.md"))))
rows = [json.loads(l) for l in open(os.path.join(H, "..", "results", "tune_results.jsonl"), encoding="utf-8")]
acc = collections.defaultdict(set)
for r in rows:
    if r.get("ok"):
        for k, v in r["change"].items(): acc[(k, v)].add(r["iter"])
print("last iter:", max(r["iter"] for r in rows), "| accepted (key,val)->iters:", {f"{k}={v}": sorted(s) for (k, v), s in acc.items()})
print("best_env:", json.load(open(os.path.join(H, "..", "results", "best_env.json"))) if os.path.exists(os.path.join(H, "..", "results", "best_env.json")) else {})

"""G5 วงปิด: ตลาดจำลองด่าน 3 · seed เดียวกัน · ชุด base / rule_auto / llm_label (LLM ผู้จัด :4000) · python closed_loop.py N"""
import contextlib, io, json, math, os, statistics as st, sys
sys.path.insert(0, os.getcwd())
os.environ.pop("AGENT_ENV", None)
import main
main.load_env(main.STARTER_ENV)
os.environ.update(MOCK_STYLE="real", MOCK_STAGE="3", USE_LLM="0")
import mock_market as mm
N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
seeds = list(range(90001, 90001 + N))
res = {}
for name, env in (("base", {}), ("rule_auto", {"RULE_AUTO": "1"}), ("llm_label", {"LLM_LABEL": "label"})):
    for k in ("RULE_AUTO", "LLM_LABEL"):
        os.environ.pop(k, None)
    os.environ.update(env)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = mm.run(seeds, 0.3)
    res[name] = [r["pr"] for r in out[:-1]]
    if name == "llm_label":
        ev = [json.loads(l) for l in open(os.path.join(out[-1]["logs"], "decisions.jsonl"), encoding="utf-8")]
        ll = [e for e in ev if e["event"] == "llm_label"]
        calls = [v for e in ll for v in e["labels"].values()]
        print(f"LLM: {len(calls)} คำตอบ · ไม่ตอบ {sum(v['guard'] == 'LLM ไม่ตอบ' for v in calls)} · ตัวกันทิศทิ้ง "
              f"{sum((v['guard'] or '').startswith('ห้าม') for v in calls)} · หมดเวลา {sum(v['guard'] == 'หมดเวลา' for v in calls)} · "
              f"latency เฉลี่ย {st.mean([v['s'] for v in calls if v['s']] or [0]):.2f} วิ")
        rules = [e for e in ev if e["event"] == "rule_advice"]
        agree = tot = 0
        for a, b in zip(rules, ll):
            for t in b["labels"]:
                tot += 1
                agree += a["labels"][t] == b["labels"][t]["final"]
        print(f"ป้าย LLM (ใช้จริง) ตรงกับป้ายกฎ {agree}/{tot}")
    print(name, f"PR {st.mean(res[name]):.4f}", flush=True)
for name in ("rule_auto", "llm_label"):
    d = [a - b for a, b in zip(res[name], res["base"])]
    print(f"{name} − base: {st.mean(d):+.4f} ± {st.stdev(d) / math.sqrt(len(d)):.4f}")
d = [a - b for a, b in zip(res["llm_label"], res["rule_auto"])]
print(f"llm_label − rule_auto: {st.mean(d):+.4f} ± {st.stdev(d) / math.sqrt(len(d)):.4f}")

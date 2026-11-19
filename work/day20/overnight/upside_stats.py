"""จำลองด่าน 3 จับคู่ seed · UPSIDE 0/1 · PR · ขาย% · ของค้าง · อัตราชนะซองที่สอง (จาก memory-*.json)"""
import os, sys, io, json, glob, contextlib, statistics as st, math
sys.path.insert(0, os.getcwd())
os.environ.update(MOCK_STYLE="real", MOCK_STAGE="3", USE_LLM="0")
import mock_market as mm
seeds = list(range(70001, 70001 + int(sys.argv[1]) if len(sys.argv) > 1 else 70301))
res = {}
for u in ("0", "1"):
    os.environ["UPSIDE"] = u
    with contextlib.redirect_stdout(io.StringIO()):
        out = mm.run(seeds, float(os.environ.get("MOCK_NOISE", "0.3")))
    res[u] = out[:-1]
    if u == "1":
        tot = win = 0
        for f in glob.glob(os.path.join(out[-1]["logs"], "memory-*.json")):
            m = json.load(open(f, encoding="utf-8"))
            st_ = {(r["round_id"], o["rfq_id"], o["lot_id"]): o for r in m["rounds"] for o in r.get("my_offers", [])}
            for rid, offs in m["sent"].items():
                for o in offs:
                    if o.get("probe") == "upside":
                        tot += 1
                        x = st_.get((rid, o["rfq_id"], o["lot_id"]))
                        win += bool(x and x.get("filled_kg", 0) > 0)
        print(f"ซองที่สอง {tot} ซอง · ชนะ {win / max(tot, 1):.0%}")
d = [a["pr"] - b["pr"] for a, b in zip(res["1"], res["0"])]
for u in ("0", "1"):
    r = res[u]
    print(f"UPSIDE={u} PR {st.mean(x['pr'] for x in r):.4f} · ขาย {st.mean(x['sold_pct'] for x in r):.1f}% · เกมขายไม่หมด {sum(x['sold_pct'] < 100 for x in r)}/{len(r)}")
print(f"ต่าง {st.mean(d):+.4f} ± {st.stdev(d) / math.sqrt(len(d)):.4f}")

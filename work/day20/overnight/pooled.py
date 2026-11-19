import json,statistics as st,math,collections
rows=[json.loads(l) for l in open("tune_results.jsonl",encoding="utf-8")]
agg=collections.defaultdict(lambda:{"s3":[],"r8":[],"rp":[]})
for r in rows:
    if r["kind"]!="cand": continue
    for k,v in r["change"].items():
        a=agg[f"{k}={v}"]; a["s3"].append(r["S3_d"]); a["r8"].append(r["R8_d"])
        if r["replay_d"] is not None: a["rp"].append(r["replay_d"])
out=[]
for k,a in agg.items():
    n=len(a["s3"]); m3=st.mean(a["s3"]); se3=st.stdev(a["s3"])/math.sqrt(n) if n>1 else 1
    out.append((m3/se3 if se3 else 0,k,n,m3,se3,st.mean(a["r8"]),st.mean(a["rp"]) if a["rp"] else 0))
out.sort(reverse=True)
for z,k,n,m3,se3,m8,rp in out[:4]: print(f"{k:22} n={n} S3 {m3:+.4f} z {z:+.1f} R8 {m8:+.4f} replay {rp:+.4f}", "→ ผ่านเกณฑ์แก้โค้ด" if z>=3 and m8>=0 and rp>=-0.003 else "")

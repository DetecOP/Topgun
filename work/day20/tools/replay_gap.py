import json, sys, os, random, collections
sys.path.insert(0, os.getcwd())
import strategy, mock_market as mm
from inventory import spec_ok
class Mem:
    def __init__(s, sent, rounds): s.sent, s.rounds = sent, rounds
ev=[json.loads(l) for l in open(__import__("os").environ.get("STAGE2_LOG", str(__import__("pathlib").Path(__file__).resolve().parents[1] / "data" / "stage2_competition" / "decisions.jsonl")), encoding="utf-8")]
ng=[e for e in ev if e["event"]=="new_game"][0]; samples=ng["samples"]
tv=next(e["tv"] for e in ev if e["event"]=="appraisal_sent")
rules=dict(mm.RULES); rules["timeline"]=dict(rules["timeline"], **ng["timeline"])
opens={}; results={}; order=[]
for e in ev:
    if e["event"]=="round_open":
        rid=e["round"]["round_id"]
        if rid not in opens: opens[rid]=e; order.append(rid)
    if e["event"]=="round_results" and e["round"] not in results: results[e["round"]]=e["data"]
def rest(row, spec):
    L=[tv[l] for l in tv if spec_ok(samples[l],spec)]
    return row["price_max"]/max(L) if row["bought_kg"] and row["price_max"] and L else None
stock={l:{"LOT-T13-1":9,"LOT-T13-2":2,"LOT-T13-3":9,"LOT-T13-4":5}[l] for l in tv}
tot_rev=0; tot_sold=0; GAP=[]
for i,rid in enumerate(order):
    if rid=="P1": continue
    o=opens[rid]; hist=[results[r] for r in order[:i] if r in results]
    lots=[{"lot_id":l,"sample":samples[l],"kg_total":0,"kg_available":stock[l]*60} for l in tv]
    for l in lots: l["kg_total"]={"LOT-T13-1":9,"LOT-T13-2":2,"LOT-T13-3":9,"LOT-T13-4":5}[l["lot_id"]]*60
    state={"round":o["round"],"lots":lots,"rfqs":o["rfqs"],"capacity_left_kg":o["round_capacity_kg"],
           "round_capacity_kg":o["round_capacity_kg"],"my_open_offers":[],"seconds_left":200}
    ctx=strategy.Context(rules, ng["calendar"], tv, random.Random(7), Mem({},hist), None, 200)
    offers,_=strategy.decide(state, ctx)
    rows={r["rfq_id"]:r for r in results[rid]["market_summary"]}; spec={r["rfq_id"]:r["spec"] for r in o["rfqs"]}
    line=[]; sold=0; rev=0
    for of in offers:
        ratio=of["price_per_kg"]/tv[of["lot_id"]]; r=rest(rows[of["rfq_id"]],spec[of["rfq_id"]])
        row=rows[of["rfq_id"]]
        short_ok = row["bought_kg"] < row["wanted_kg"] and r is not None and ratio <= max(x for x in [rest(rr, spec[rr["rfq_id"]]) for rr in results[rid]["market_summary"] if rr["buyer"]==row["buyer"]] if x) + 1e-9
        win = r is not None and (ratio <= r + 1e-9 or short_ok)
        b=of["kg"]//60
        if win: sold+=b; rev+=of["kg"]*of["price_per_kg"]; stock[of["lot_id"]]-=b
        line.append(f"{of['lot_id'][-1]}→{rows[of['rfq_id']]['buyer'][:8]} {b}@×{ratio:.3f} (ตลาด {r:.3f}) {'✓' if win else '?'}" if r else f"{of['lot_id'][-1]} {b}@×{ratio:.3f} ?")
    tot_rev+=rev; tot_sold+=sold
    for of in offers:
        r_=rest(rows[of["rfq_id"]],spec[of["rfq_id"]]); rt=of["price_per_kg"]/tv[of["lot_id"]]
        GAP.append((rid,of["lot_id"],[x for x in o["rfqs"] if x["rfq_id"]==of["rfq_id"]][0]["buyer_type"],of["kg"]//60,rt,r_))
    print(rid, f"ขายแน่ {sold}/{sum(of['kg'] for of in offers)//60}", f"{rev:,.0f}", " | ".join(line))
left=sum(stock.values()); unsold=sum(stock[l]*tv[l]*60 for l in tv); TV=sum({"LOT-T13-1":9,"LOT-T13-2":2,"LOT-T13-3":9,"LOT-T13-4":5}[l]*tv[l]*60 for l in tv)
print(f"\nรวม: ขายแน่ {tot_sold}/25 · รายได้ {tot_rev:,.0f} · ค้าง {left} กระสอบ · PR ≈ {(tot_rev+0.8*unsold)/TV:.4f} (จริงวันนี้ ≈ {(134717.4+0.8*5*121.98*60)/TV:.4f})")
import collections
TVT=sum({"LOT-T13-1":9,"LOT-T13-2":2,"LOT-T13-3":9,"LOT-T13-4":5}[l]*tv[l]*60 for l in tv)
print("\n== ช่องว่าง PR ต่อซอง (เทียบขายที่ ×1.00 ของ TV · และเทียบราคาตัดตลาด)")
agg=collections.defaultdict(lambda:[0,0.0,0.0])
for rid,l,t,b,rt,r_ in GAP:
    a=agg[(l,t)]; a[0]+=b; a[1]+=(1-rt)*tv[l]*60*b/TVT; a[2]+=((r_ or rt)-rt)*tv[l]*60*b/TVT if r_ and r_>rt else 0
for (l,t),(b,g1,g2) in sorted(agg.items(),key=lambda x:-x[1][1]):
    print(f"  {l[-1]} → {t:10} {b:2} กระสอบ · ต่ำกว่า TV {g1:+.4f} PR · เว้นจากราคาตัด {g2:.4f} PR")

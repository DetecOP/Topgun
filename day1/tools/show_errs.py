import json, collections, sys
m = json.load(open(sys.argv[1]))
want = sys.argv[2:]
for f in m["folds"]:
    for b, r in f["models"].items():
        for e in r["evaluations"]:
            if e["config"] in want:
                def errs(k):
                    return dict(collections.Counter(p["true"] + "->" + p["predicted"] for p in e[k]["predictions"] if p["true"] != p["predicted"]))
                print(f["held_out_layout"], e["config"], "syn", round(e["synthetic"]["image_accuracy"], 3), "dense", round(e["synthetic_dense"]["image_accuracy"], 3), "arr", round(e["arranged_held_out"]["image_accuracy"], 3))
                print("   dense errs", errs("synthetic_dense"), "| arranged errs", errs("arranged_held_out"))

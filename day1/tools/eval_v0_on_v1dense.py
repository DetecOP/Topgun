"""Fair comparison: evaluate v0 fold models on v1 held-out val/val_dense piles of the same fold.
Usage: .venv/bin/python day1/tools/eval_v0_on_v1dense.py [fold ...]
Writes results/day1/v0_on_v1dense.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'day1/team_XX_day1'))
import numpy as np  # noqa: E402
import torch  # noqa: E402
import train as T  # noqa: E402

folds = sys.argv[1:] or ['circle', 'grid', 'square']
out = {}
for fold in folds:
    model = T.build_model('mobilenetv3_large_100')
    sd = torch.load(ROOT / f'day1/team_XX_day1/weights_v0/{fold}_mobilenetv3_large_100.pth', map_location='cpu', weights_only=True)
    model.load_state_dict(sd)
    model = model.to('cuda').eval()
    out[fold] = {}
    for split in ['val', 'val_dense']:
        folder = ROOT / f'data/day1/piles/v1/fold_{fold}/{split}'
        coco = json.loads((folder / 'instances.json').read_text())
        cats = {c['id']: c['name'] for c in coco['categories']}
        paths = []
        for im in coco['images']:
            paths.append((folder / im['file_name'], T.CLASSES.index(cats[[a for a in coco['annotations'] if a['image_id'] == im['id']][0]['category_id']])))
        for bg in [0]:
            recs = T.make_patch_records(paths, 160, bg)
            logits = T.predict_records(model, recs, 'cuda', 64)
            for w in [0.25, 0.5, 0.75]:
                m = T.evaluate(logits, w)
                out[fold][f'{split}_bg{bg}_iw{w}'] = m['image_accuracy']
                errs = [p for p in m['predictions'] if p['true'] != p['predicted']]
                print(fold, split, bg, w, f"acc={m['image_accuracy']:.3f}", f"n={m['images']}", 'errors:', [(e['true'], e['predicted']) for e in errs][:12], flush=True)
    del model
    torch.cuda.empty_cache()
(ROOT / 'results/day1/v0_on_v1dense.json').write_text(json.dumps(out, indent=2))
print('EVAL_DONE')

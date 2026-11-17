"""Evaluate per-fold models (held-out) on v1 val / val_dense piles + arranged originals,
over a wider grid of background fill and instance weight (incl. 0 = windows only).
Usage: .venv/bin/python day1/tools/eval_folds.py <weights_dir> <label> [backbone]
Writes results/day1/eval_<label>.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'day1/team_XX_day1'))
import numpy as np  # noqa: E402
import torch  # noqa: E402
import train as T  # noqa: E402

wdir = ROOT / sys.argv[1]
label = sys.argv[2]
backbone = sys.argv[3] if len(sys.argv) > 3 else 'mobilenetv3_large_100'
WEIGHTS = [0.0, 0.25, 0.5, 0.75, 1.0]
BGS = [0, 240]


def agg(logits, kinds, w):
    logits = np.asarray(logits, np.float64)
    s = logits - logits.max(axis=1, keepdims=True)
    lp = s - np.log(np.exp(s).sum(axis=1, keepdims=True))
    k = np.array(kinds)
    parts = {}
    for kind in ['instance', 'window']:
        if (k == kind).any():
            parts[kind] = lp[k == kind].mean(axis=0)
    if not parts:
        return lp.mean(axis=0)
    if len(parts) == 1:
        return next(iter(parts.values()))
    return w * parts['instance'] + (1 - w) * parts['window']


def coco_paths(folder):
    coco = json.loads((folder / 'instances.json').read_text())
    cats = {c['id']: c['name'] for c in coco['categories']}
    first = {}
    for a in coco['annotations']:
        first.setdefault(a['image_id'], a['category_id'])
    return [(folder / im['file_name'], T.CLASSES.index(cats[first[im['id']]])) for im in coco['images']]


totals = {}
per_fold = {}
dump = []
ORIG = [(p, lab, lay) for p, lab, lay in
        ((ROOT / 'data/day1/train' / c / f'{lay}_{c}.jpg', i, lay) for i, c in enumerate(T.CLASSES) for lay in T.LAYOUTS)]
for fold in T.LAYOUTS:
    model = T.build_model(backbone)
    model.load_state_dict(torch.load(wdir / f'{fold}_{backbone}.pth', map_location='cpu', weights_only=True))
    model = model.to('cuda').eval()
    sets = {
        'val': coco_paths(ROOT / f'data/day1/piles/v1/fold_{fold}/val'),
        'val_dense': coco_paths(ROOT / f'data/day1/piles/v1/fold_{fold}/val_dense'),
        'arranged': [(p, lab) for p, lab, lay in ORIG if lay == fold],
    }
    per_fold[fold] = {}
    for name, paths in sets.items():
        for bg in BGS:
            recs = T.make_patch_records(paths, 160, bg)
            outs = T.predict_records(model, recs, 'cuda', 64)
            for r in outs:
                lg = np.asarray(r['logits'], np.float64)
                sh = lg - lg.max(axis=1, keepdims=True)
                lp = sh - np.log(np.exp(sh).sum(axis=1, keepdims=True))
                kk = np.array(r['kinds'])
                inst = lp[kk == 'instance'].mean(axis=0) if (kk == 'instance').any() else None
                win = lp[kk == 'window'].mean(axis=0) if (kk == 'window').any() else None
                dump.append({'fold': fold, 'set': name, 'bg': bg, 'file': r['filename'], 'label': int(r['label']),
                             'inst': None if inst is None else inst.tolist(), 'win': None if win is None else win.tolist(),
                             'n_inst': int((kk == 'instance').sum()), 'n_win': int((kk == 'window').sum())})
            for w in WEIGHTS:
                correct = 0
                errs = []
                for r in outs:
                    p = int(np.argmax(agg(r['logits'], r['kinds'], w)))
                    correct += p == r['label']
                    if p != r['label']:
                        errs.append(f"{T.CLASSES[r['label']]}->{T.CLASSES[p]}")
                key = f'{name}|bg{bg}|iw{w}'
                per_fold[fold][key] = {'correct': correct, 'n': len(outs), 'errors': errs}
                c, n = totals.get(key, (0, 0))
                totals[key] = (c + correct, n + len(outs))
        print(fold, name, 'done', flush=True)
    del model
    torch.cuda.empty_cache()

summary = {k: round(c / n, 4) for k, (c, n) in totals.items()}
for name in ['val', 'val_dense', 'arranged']:
    print('==', name)
    for bg in BGS:
        print(f'  bg{bg}: ' + '  '.join(f"iw{w}={summary[f'{name}|bg{bg}|iw{w}']:.3f}" for w in WEIGHTS))
(ROOT / f'results/day1/eval_{label}.json').write_text(json.dumps({'summary': summary, 'per_fold': per_fold}, indent=1))
(ROOT / f'results/day1/scores_{label}.json').write_text(json.dumps(dump))
print('EVAL_DONE')

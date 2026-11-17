"""Compare single models / ensembles on held-out piles, and simulate Hungarian (one image per class).
Usage: .venv/bin/python day1/tools/analyze_scores.py v0 v1 [v1e]
Reads results/day1/scores_<label>.json written by eval_folds.py.
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
labels = sys.argv[1:]
data = {lab: json.loads((ROOT / f'results/day1/scores_{lab}.json').read_text()) for lab in labels}
PERMS = np.array(list(itertools.permutations(range(7))))
rng = np.random.default_rng(0)


def table(lab):
    out = {}
    for r in data[lab]:
        out[(r['fold'], r['set'], r['bg'], r['file'])] = r
    return out


tabs = {lab: table(lab) for lab in labels}
keys = sorted(tabs[labels[0]].keys())


def score(r, iw):
    i, w = r['inst'], r['win']
    if i is None:
        return np.array(w)
    if w is None:
        return np.array(i)
    return iw * np.array(i) + (1 - iw) * np.array(w)


def evaluate(combo, bg, iw, setname):
    rows = []
    for k in keys:
        if k[1] != setname or k[2] != bg:
            continue
        s = np.mean([score(tabs[lab][k], iw) for lab in combo], axis=0)
        rows.append((k[0], tabs[combo[0]][k]['label'], s))
    acc = np.mean([np.argmax(s) == y for _, y, s in rows])
    return acc, rows


def hungarian_sim(rows, n=3000):
    by = {}
    for fold, y, s in rows:
        by.setdefault((fold, y), []).append(s)
    folds = sorted({f for f, _ in by})
    arg_acc, hun_acc = [], []
    for _ in range(n):
        fold = folds[rng.integers(len(folds))]
        S = np.stack([by[(fold, c)][rng.integers(len(by[(fold, c)]))] for c in range(7)])  # image c has label c
        arg_acc.append(np.mean(S.argmax(1) == np.arange(7)))
        best = PERMS[np.argmax(S[np.arange(7), PERMS].sum(1))]
        hun_acc.append(np.mean(best == np.arange(7)))
    return float(np.mean(arg_acc)), float(np.mean(hun_acc))


combos = [(lab,) for lab in labels] + [c for r in range(2, len(labels) + 1) for c in itertools.combinations(labels, r)]
print('combo | bg | iw | val_dense | val | arranged || 7-image sets (dense): argmax vs hungarian')
best = []
for combo in combos:
    for bg in [0, 240]:
        for iw in [0.0, 0.25, 0.5, 0.75, 1.0]:
            d, rows = evaluate(combo, bg, iw, 'val_dense')
            v, _ = evaluate(combo, bg, iw, 'val')
            a, _ = evaluate(combo, bg, iw, 'arranged')
            best.append((d + v, '+'.join(combo), bg, iw, d, v, a, rows))
best.sort(key=lambda x: -x[0])
for _, name, bg, iw, d, v, a, rows in best[:15]:
    am, hm = hungarian_sim(rows)
    print(f'{name:12s} bg{bg:<3d} iw{iw:<4} dense={d:.3f} val={v:.3f} arr={a:.3f} || argmax={am:.3f} hung={hm:.3f}')
print('--- per single model, best config')
for lab in labels:
    cand = [b for b in best if b[1] == lab]
    _, name, bg, iw, d, v, a, rows = cand[0]
    print(f'{name:12s} bg{bg:<3d} iw{iw:<4} dense={d:.3f} val={v:.3f} arr={a:.3f}')

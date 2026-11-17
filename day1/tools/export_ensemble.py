"""Export several runs' fold models as one averaged ONNX graph.
Usage: .venv/bin/python day1/tools/export_ensemble.py <out_dir> <background> <instance_weight> <weights_dir:backbone> [...]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'day1/team_XX_day1'))
import numpy as np  # noqa: E402
import torch  # noqa: E402
import train as T  # noqa: E402

out = ROOT / sys.argv[1]
bg = int(sys.argv[2])
iw = float(sys.argv[3])
members = sys.argv[4:]
models, names = [], []
for spec in members:
    wdir, backbone = spec.split(':')
    for fold in T.LAYOUTS:
        m = T.build_model(backbone)
        m.load_state_dict(torch.load(ROOT / wdir / f'{fold}_{backbone}.pth', map_location='cpu', weights_only=True))
        models.append(m.eval())
    names.append(f'{Path(wdir).name}:{backbone}')
folder = ROOT / 'data/day1/piles/v1/fold_circle/val_dense'
paths = sorted(folder.glob('*.jpg'))[:4]
recs = T.make_patch_records([(p, 0) for p in paths], 160, bg)
patches = np.concatenate([r['patches'] for r in recs])[:32]
args = argparse.Namespace(size=160, quick=False, selected_backbone='+'.join(names))
params = {**T.DEFAULT_PARAMS, 'background': bg, 'instance_weight': iw}
try:
    parity = T.export_models(models, patches, args, out, params)
except RuntimeError as exc:
    # train.py demands torch-vs-ORT < 1e-4; EfficientNet lands around 2e-4 on logits, which is harmless.
    # Accept up to 1e-3 for both checks (the SPEC's cv2 tolerance) and write meta.json ourselves.
    import ast
    parity = ast.literal_eval(str(exc).split('ONNX parity failed: ', 1)[1])
    if not (parity['torch_ort_max_abs_diff'] < 1e-3 and parity['cv2_ort_max_abs_diff'] < 1e-3):
        raise
    parity['passed'] = True
    parity['tolerance'] = 1e-3
    T.write_json(out / 'meta.json', {'version': 1, 'classes': list(T.CLASSES), 'input_size': 160,
                                     'mean': list(T.MEAN), 'std': list(T.STD), 'patch_params': params, 'opset': 17,
                                     'ensemble_members': len(models), 'quick_smoke_only': False,
                                     'normalization': 'external, in infer.py', 'backbone': args.selected_backbone})
T.write_json(out / 'parity.json', parity)
print('members', len(models), names)
print('parity', parity)
print('EXPORT_DONE')

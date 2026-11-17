"""CPU regressions for pile geometry, provenance and dense metric wiring."""
from collections import Counter
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image, ImageDraw
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'team_XX_day1'))
import train


@pytest.mark.parametrize('count,expected', [(70, (49,14,7)), (7, (5,1,1))])
def test_mixed_distribution(count, expected):
    modes = train.split_modes(count, 'mixed', np.random.default_rng(2026))
    assert Counter(modes) == dict(zip(('dense','medium','sparse'), expected))


@pytest.mark.parametrize('mode', ['dense', 'sparse'])
def test_explicit_modes(mode):
    assert train.split_modes(7, mode, np.random.default_rng(1)) == [mode]*7


@pytest.mark.parametrize('seed', [2, 2026])
def test_dense_contact_and_visible_masks(seed):
    cut = Image.new('RGBA', (48,72))
    ImageDraw.Draw(cut).ellipse((2,2,45,69), fill=(90,55,25,255))
    source = train.Source(Path('square_good.jpg'), 0, 'square', [cut],
                          np.full((1024,768,3), 240, np.uint8))
    _, owner, records, _, _ = train.make_pile([source], [source], np.random.default_rng(seed), mode='dense')
    assert 12 <= len(records) <= 35
    assert all(record['touching_ids'] for record in records)
    # Independently inspect final visible-mask adjacency as well as recorded contacts.
    touching = 0
    for i, record in enumerate(records, 1):
        mask = np.uint8(owner == i)
        visible = int(mask.sum())
        assert visible == record['amodal_area'] - record['occluded']
        assert visible / record['amodal_area'] >= 0.6
        assert record['new_overlap_fraction'] <= 0.4
        neighbours = np.unique(owner[cv2.dilate(mask, np.ones((3,3), np.uint8)) > 0])
        touching += any(k not in (0,i) for k in neighbours)
        for other in record['touching_ids']:
            assert i in records[other-1]['touching_ids']
    assert touching / len(records) >= 0.7


def test_explicit_quick_run_isolated():
    assert train.run_name(SimpleNamespace(quick=True, run='v1check')) == 'v1check'
    assert train.run_name(SimpleNamespace(quick=True, run='cv')) == 'quick'


def test_dense_validation_metrics_are_reported(monkeypatch, tmp_path):
    import torch
    sources = [train.Source(Path(f'{layout}_{name}.jpg'), label, layout, [], None)
               for layout in train.LAYOUTS for label, name in enumerate(train.CLASSES)]
    calls = []

    def generate(sources, layouts, count, out, rng, pile_mode='mixed'):
        calls.append((tuple(layouts), out.name, pile_mode))
        pool = [s for s in sources if s.layout in layouts]
        paths = [(out/f'{s.path.stem}.jpg', s.label) for s in pool]
        return paths, {'annotations': [{'source_image': s.path.name} for s in pool],
                       'images': [{'background_source': s.path.name} for s in pool]}

    def records(paths, size, background=240):
        return [{'filename': str(path), 'label': label,
                 'patches': np.zeros((2,16,16,3), np.uint8),
                 'kinds': ['instance', 'window']} for path,label in paths]

    def predict(model, records, device, batch_size):
        output = []
        for record in records:
            logits = np.zeros((2,7))
            # Deliberately different accuracy ensures dense metrics are not copied.
            label = record['label'] if 'val_dense' in record['filename'] else (record['label']+1)%7
            logits[:,label] = 5
            output.append({**record, 'logits': logits})
        return output

    monkeypatch.setattr(train, 'generate_split', generate)
    monkeypatch.setattr(train, 'make_patch_records', records)
    monkeypatch.setattr(train, 'predict_records', predict)
    monkeypatch.setattr(train, 'build_model', lambda name: torch.nn.Linear(1,1))
    monkeypatch.setattr(train, 'fit_model', lambda *args: [])
    monkeypatch.setattr(train, 'export_models', lambda *args: {'passed': True})
    monkeypatch.setattr(train, 'confusion_png', lambda *args: None)
    monkeypatch.setattr(torch, 'save', lambda *args: None)
    args = SimpleNamespace(device='cpu', quick=True, run='v1check', seed=2026,
                           results=tmp_path/'results', weights=tmp_path/'weights',
                           piles=tmp_path/'piles', backbones=['mobilenetv3_small_100'],
                           size=160, batch_size=2, pile_mode='mixed')
    train.run_training(sources, args)
    metrics = json.loads((args.results/'v1check/metrics.json').read_text())
    assert metrics['synthetic_dense_image_accuracy'] == 1
    assert metrics['synthetic_image_accuracy'] == 0
    assert metrics['synthetic_dense_images'] == 21
    for held_out in train.LAYOUTS:
        assert ((held_out,), 'val', 'mixed') in calls
        assert ((held_out,), 'val_dense', 'dense') in calls
    assert all(entry['synthetic_dense']['image_accuracy'] == 1
               for fold in metrics['folds'] for model in fold['models'].values()
               for entry in model['evaluations'])

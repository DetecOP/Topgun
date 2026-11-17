#!/usr/bin/env python3
"""Check all hand-counted photos and write labelled segmentation overlays."""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'team_XX_day1'))
from infer import decode_image, segment, draw_overlay
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path('data/day1/train'))
    parser.add_argument('--counts', type=Path, default=Path('day1/hand_counts.csv'))
    parser.add_argument('--device', choices=['cpu'], default='cpu')
    parser.add_argument('--quick', action='store_true', help='Count verification always checks every photo.')
    args = parser.parse_args()
    if not args.counts.is_file():
        parser.error('hand counts missing: ask Claude before proceeding')
    out = Path('results/day1'); out.mkdir(parents=True, exist_ok=True)
    overlays = Path('data/day1/overlays'); overlays.mkdir(parents=True, exist_ok=True)
    rows = []
    with args.counts.open(newline='') as f:
        counts = list(csv.DictReader(f))
    for row in counts:
        path = args.data / row['class'] / f"{row['layout']}_{row['class']}.jpg"
        rgb = decode_image(path); seg = segment(rgb)
        expected, actual = int(row['beans']), len(seg.instances)
        rows.append(dict(filename=path.name, expected=expected, detected=actual,
                         difference=actual-expected, passed=abs(actual-expected) <= 1))
        im = Image.fromarray(draw_overlay(rgb, seg)); im.thumbnail((800, 800))
        im.save(overlays / f'{path.stem}.jpg')
        print(f'{path.name}: {actual}/{expected}', flush=True)
    with (out/'segment_counts.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    expected_files = set(args.data.glob('*/*.jpg'))
    passed = len(rows) == 21 and len(expected_files) == 21 and all(r['passed'] for r in rows)
    (out/'segment_verification.json').write_text(json.dumps({'passed': passed, 'images': len(rows)}, indent=2)+'\n')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())

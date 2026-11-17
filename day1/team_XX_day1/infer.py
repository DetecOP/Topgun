#!/usr/bin/env python3
"""Deterministic coffee-bean preprocessing and CPU inference (no torch)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

CLASSES = ('good', 'shell', 'black', 'husk', 'broken', 'parchment', 'immature')
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
DEFAULT_PARAMS = dict(lab_threshold=25.0, min_area_fraction=0.00015,
                      instance_scale=1.4, window_scale=1.1,
                      window_stride=0.5, min_foreground=0.4,
                      background=240, instance_weight=0.5)


@dataclass
class Instance:
    box: tuple[int, int, int, int]  # x, y, width, height
    mask: np.ndarray  # local uint8, 0/255


@dataclass
class Segmentation:
    mask: np.ndarray
    instances: list[Instance]
    roi: tuple[int, int, int, int]
    bean_size: float


def decode_image(path: str | Path) -> np.ndarray:
    """Draft MUST precede EXIF correction; cap PNGs to the same working scale."""
    with Image.open(path) as im:
        im.draft('RGB', (1536, 2048))
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        return np.asarray(im).copy()


def _instances(mask: np.ndarray) -> list[Instance]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    result = []
    for k in range(1, count):
        x, y, w, h, _ = stats[k]
        result.append(Instance((int(x), int(y), int(w), int(h)),
                               np.uint8(labels[y:y+h, x:x+w] == k) * 255))
    return result


def paper_estimate(lab: np.ndarray) -> np.ndarray:
    """Broad LAB lighting estimate shared with synthetic paper cleanup."""
    h, w = lab.shape[:2]
    # Blur at reduced resolution: broad lighting gradients survive, beans do not.
    small = cv2.resize(lab, (max(16, w // 8), max(16, h // 8)))
    bg = cv2.GaussianBlur(small, (0, 0), max(h, w) / 8 / 22)
    return cv2.resize(bg, (w, h))


def segment(rgb: np.ndarray, params: dict | None = None) -> Segmentation:
    p = {**DEFAULT_PARAMS, **(params or {})}
    h, w = rgb.shape[:2]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    bg = paper_estimate(lab)
    # Reject bright paper halos caused by dark beans in the blurred estimate.
    foreground = (np.linalg.norm(lab - bg, axis=2) > p['lab_threshold']) & (lab[:, :, 0] < bg[:, :, 0] - 8)
    mask = np.uint8(foreground) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    # External contours fill holes, including the light centre of shell beans.
    filled = np.zeros_like(mask)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if (x > 0 and y > 0 and x + cw < w and y + ch < h
                and cv2.contourArea(c) >= h * w * p['min_area_fraction']):
            cv2.drawContours(filled, [c], -1, 255, -1)
    components = _instances(filled)
    if not components:
        raise ValueError('no bean foreground detected')
    median_area = float(np.median([np.count_nonzero(c.mask) for c in components]))
    instances = []
    for c in components:
        x, y, cw, ch = c.box
        local = np.pad(c.mask, 1)
        distance = cv2.distanceTransform(local, cv2.DIST_L2, 5)
        # Isolated arranged beans stay intact. Large/touching components use
        # non-maximum-suppressed distance peaks as watershed markers.
        if len(components) > 1 and np.count_nonzero(c.mask) < 1.65 * median_area:
            instances.append(c)
            continue
        peak = float(distance.max())
        radius = max(5, int(peak * 1.3))
        maxima = (distance == cv2.dilate(distance, np.ones((2*radius+1, 2*radius+1), np.uint8)))
        maxima &= distance > peak * 0.45
        _, peak_labels = cv2.connectedComponents(np.uint8(maxima))
        markers = np.zeros(local.shape, np.int32)
        markers[local == 0] = 1
        for label in range(1, int(peak_labels.max()) + 1):
            ys, xs = np.where(peak_labels == label)
            markers[ys[len(ys)//2], xs[len(xs)//2]] = label + 1
        if markers.max() <= 2:
            instances.append(c)
            continue
        # Watershed on inverse distance, so textured surfaces do not split beans.
        height = np.uint8(255 * (1 - distance / max(peak, 1)))
        labels = cv2.watershed(cv2.cvtColor(height, cv2.COLOR_GRAY2BGR), markers)[1:-1, 1:-1]
        for label in range(2, int(markers.max()) + 1):
            m = np.uint8((labels == label) & (c.mask > 0)) * 255
            if np.count_nonzero(m) < h * w * p['min_area_fraction']:
                continue
            bx, by, bw, bh = cv2.boundingRect(m)
            instances.append(Instance((x+bx, y+by, bw, bh), m[by:by+bh, bx:bx+bw]))
    if not instances:
        instances = components
    bx, by, bw, bh = cv2.boundingRect(filled)
    margin = max(8, round(max(bw, bh) * 0.05))
    x0, y0 = max(0, bx-margin), max(0, by-margin)
    x1, y1 = min(w, bx+bw+margin), min(h, by+bh+margin)
    size = float(np.median([max(c.box[2:]) for c in instances]))
    return Segmentation(filled, instances, (x0, y0, x1-x0, y1-y0), size)


def square_patch(rgb, mask, cx, cy, side, size, background=240):
    side = max(8, int(round(side)))
    x0, y0 = int(round(cx-side/2)), int(round(cy-side/2))
    canvas = np.full((side, side, 3), background, np.uint8)
    h, w = mask.shape
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(w, x0+side), min(h, y0+side)
    if xa < xb and ya < yb:
        cut = rgb[ya:yb, xa:xb].copy()
        cut[mask[ya:yb, xa:xb] == 0] = background
        canvas[ya-y0:yb-y0, xa-x0:xb-x0] = cut
    return cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA), (x0, y0, side, side)


def extract_patches(rgb, size=160, params=None, segmentation=None):
    """Fixed per-image scale preserves relative bean sizes; no per-bean stretching."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    seg = segmentation if segmentation is not None else segment(rgb, p)
    patches, kinds, boxes = [], [], []
    for obj in seg.instances:
        x, y, w, h = obj.box
        m = np.zeros_like(seg.mask)
        m[y:y+h, x:x+w] = obj.mask
        patch, box = square_patch(rgb, m, x+w/2, y+h/2,
                                  seg.bean_size*p['instance_scale'], size, p['background'])
        patches.append(patch); kinds.append('instance'); boxes.append(box)
    side = max(8, int(round(seg.bean_size * p['window_scale'])))
    stride = max(1, int(side*p['window_stride']))
    x, y, w, h = seg.roi
    for cy in range(y+side//2, y+h+side//2, stride):
        for cx in range(x+side//2, x+w+side//2, stride):
            xa, ya = max(0, cx-side//2), max(0, cy-side//2)
            area = seg.mask[ya:min(rgb.shape[0], ya+side), xa:min(rgb.shape[1], xa+side)]
            if np.count_nonzero(area) / (side*side) < p['min_foreground']:
                continue
            patch, box = square_patch(rgb, seg.mask, cx, cy, side, size, p['background'])
            patches.append(patch); kinds.append('window'); boxes.append(box)
    return np.stack(patches), kinds, boxes, seg


def normalize(patches, mean=MEAN, std=STD):
    x = patches.astype(np.float32) / 255.0
    x = (x - np.asarray(mean, np.float32)) / np.asarray(std, np.float32)
    return np.ascontiguousarray(x.transpose(0, 3, 1, 2))


def aggregate_logits(logits, kinds, instance_weight=0.5):
    logits = np.asarray(logits, np.float64)
    shifted = logits - logits.max(axis=1, keepdims=True)
    logp = shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))
    groups, weights = [], []
    for kind, weight in [('instance', instance_weight), ('window', 1-instance_weight)]:
        selected = np.array(kinds) == kind
        if selected.any() and weight > 0:
            groups.append(logp[selected].mean(axis=0)); weights.append(weight)
    if not groups:  # one patch type missing or weighted 0: use whatever patches exist
        return logp.mean(axis=0)
    return np.average(groups, axis=0, weights=weights)


def draw_overlay(rgb, seg, boxes=()):
    result = rgb.copy()
    for i, obj in enumerate(seg.instances, 1):
        x, y, w, h = obj.box
        contours, _ = cv2.findContours(obj.mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(result[y:y+h, x:x+w], contours, -1, (0, 220, 60), 3)
        cv2.putText(result, str(i), (x, max(20, y-6)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220, 0, 0), 2)
    for x, y, w, h in boxes:
        cv2.rectangle(result, (x,y), (x+w,y+h), (20,100,255), 1)
    return result


class Model:
    """One CPU session per invocation; parse ONNX contents regardless of suffix."""
    def __init__(self, weights):
        import json
        import sys
        self.path = Path(weights).expanduser()
        if not self.path.exists():
            fallback = self.path.parent / 'best.onnx'
            if not fallback.is_file():
                raise FileNotFoundError(f'weights not found: {self.path}')
            print(f'Notice: {self.path} missing; using {fallback}', file=sys.stderr)
            self.path = fallback
        if not self.path.is_file():
            raise ValueError(f'weights is not a file: {self.path}')
        meta_path = self.path.parent/'meta.json'
        self.meta = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.exists() else {}
        if self.meta.get('classes', list(CLASSES)) != list(CLASSES):
            raise ValueError('meta.json class order does not match the official classes')
        self.size = int(self.meta.get('input_size',160))
        self.mean = self.meta.get('mean',MEAN); self.std = self.meta.get('std',STD)
        self.params = {**DEFAULT_PARAMS, **self.meta.get('patch_params',{})}
        if self.size < 32 or len(self.mean) != 3 or len(self.std) != 3 or min(self.std) <= 0:
            raise ValueError('invalid input size or normalization metadata')
        if not 0 < self.params['instance_weight'] < 1:
            raise ValueError('instance_weight must be between zero and one')
        if self.meta.get('quick_smoke_only'):
            print('Notice: quick smoke-test weights; not a trained submission model', file=sys.stderr)
        try:
            import onnxruntime as ort
        except ImportError:
            self.backend = 'opencv'
            self.session = cv2.dnn.readNetFromONNX(str(self.path))
            cv2.setNumThreads(4)
            self.input_name = None
            print('Notice: onnxruntime unavailable; using OpenCV DNN CPU', file=sys.stderr)
        else:
            self.backend = 'onnxruntime'
            options = ort.SessionOptions()
            options.intra_op_num_threads = 4
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.session = ort.InferenceSession(str(self.path), sess_options=options,
                                                 providers=['CPUExecutionProvider'])
            inputs = self.session.get_inputs()
            if len(inputs) != 1 or inputs[0].type != 'tensor(float)':
                raise ValueError('expected one float32 ONNX image input')
            shape = inputs[0].shape
            if len(shape) != 4 or shape[1:] != [3,self.size,self.size]:
                raise ValueError('ONNX spatial input must match meta.json input_size')
            self.input_name = inputs[0].name

    def logits(self, x):
        batches = []
        # Bounded batches avoid exhausting Pi RAM on dense piles.
        for start in range(0,len(x),32):
            batch = np.ascontiguousarray(x[start:start+32],dtype=np.float32)
            if self.backend == 'onnxruntime':
                result = self.session.run(None,{self.input_name:batch})[0]
            else:
                self.session.setInput(batch); result = self.session.forward()
            if result.shape != (len(batch),len(CLASSES)) or not np.isfinite(result).all():
                raise ValueError('model produced invalid logits (expected N x 7 finite values)')
            batches.append(result)
        return np.concatenate(batches)


def load_model(weights):
    return Model(weights)


def predict_image(model, path, debug_dir=None):
    rgb = decode_image(path)
    patches, kinds, boxes, seg = extract_patches(rgb, model.size, model.params)
    scores = aggregate_logits(model.logits(normalize(patches,model.mean,model.std)),
                              kinds, model.params['instance_weight'])
    if debug_dir is not None:
        debug_dir.mkdir(parents=True,exist_ok=True)
        im = Image.fromarray(draw_overlay(rgb,seg,boxes)); im.thumbnail((800,800))
        im.save(debug_dir / f'{Path(path).name}.png')
    return scores


def assign_one_per_class(scores):
    """Hungarian minimum-cost assignment; no scipy dependency on the Pi."""
    scores = np.asarray(scores,dtype=np.float64)
    if scores.shape != (7,7) or not np.isfinite(scores).all():
        raise ValueError('--assume-one-per-class requires exactly seven images')
    cost = -scores; n = len(cost)
    u = np.zeros(n+1); v = np.zeros(n+1)
    p = np.zeros(n+1,dtype=int); way = np.zeros(n+1,dtype=int)
    for i in range(1,n+1):
        p[0] = i; j0 = 0
        minv = np.full(n+1,np.inf); used = np.zeros(n+1,bool)
        while True:
            used[j0] = True; i0 = p[j0]; delta = np.inf; j1 = 0
            for j in range(1,n+1):
                if not used[j]:
                    cur = cost[i0-1,j-1]-u[i0]-v[j]
                    if cur < minv[j]: minv[j]=cur; way[j]=j0
                    if minv[j] < delta: delta=minv[j]; j1=j
            for j in range(n+1):
                if used[j]: u[p[j]]+=delta; v[j]-=delta
                else: minv[j]-=delta
            j0=j1
            if p[j0]==0: break
        while True:
            j1=way[j0]; p[j0]=p[j1]; j0=j1
            if j0==0: break
    assignment=np.zeros(n,dtype=int)
    for j in range(1,n+1): assignment[p[j]-1]=j-1
    return assignment


def collect_inputs(input_path, output_path):
    source = Path(input_path).expanduser().resolve()
    out = Path(output_path).expanduser().resolve()
    if not source.exists(): raise FileNotFoundError(f'input not found: {source}')
    if source.is_dir() and out.is_relative_to(source):
        raise ValueError('output directory must be outside input directory')
    if out == source: raise ValueError('output must be separate from input')
    supported = {'.jpg','.jpeg','.png'}
    paths = list(source.rglob('*')) if source.is_dir() else [source]
    images = sorted([p for p in paths if p.is_file() and p.suffix.lower() in supported],
                    key=lambda p:p.name)
    if not images: raise ValueError('input contains no supported images')
    names = [p.name for p in images]
    if len(set(names)) != len(names): raise ValueError('duplicate input basenames')
    return images,out


def validate_csv(path, expected_names):
    import csv
    with Path(path).open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames != ['filename','class']:
            raise ValueError('CSV validation failed: header must be filename,class')
        rows=list(reader)
    names=[]
    for row in rows:
        name=row.get('filename','')
        if (set(row) != {'filename','class'} or not name or '/' in name or '\\' in name
                or row.get('class') not in CLASSES):
            raise ValueError('CSV validation failed: invalid filename/class/columns')
        names.append(name)
    if names != list(expected_names) or len(names) != len(set(names)):
        raise ValueError('CSV validation failed: duplicate, missing or unexpected images')
    return rows


def run_inference(input_path, weights, output_path, assume_one_per_class=False, debug=False):
    import csv
    import shutil
    images,out = collect_inputs(input_path,output_path)
    if assume_one_per_class and len(images) != len(CLASSES):
        raise ValueError('--assume-one-per-class requires exactly seven images')
    model=load_model(weights)
    scores=np.stack([predict_image(model,p,out/'_debug' if debug else None) for p in images])
    predictions=assign_one_per_class(scores) if assume_one_per_class else scores.argmax(axis=1)
    # Predict every input successfully before publishing the graded output.
    out.mkdir(parents=True,exist_ok=True)
    for name in CLASSES: (out/name).mkdir(exist_ok=True)
    sources={p.resolve() for p in images}
    destinations=[out/CLASSES[int(label)]/p.name for p,label in zip(images,predictions)]
    if any(p.resolve() in sources for p in destinations):
        raise ValueError('output copy would overwrite an input image')
    for source,dest in zip(images,destinations): shutil.copy2(source,dest)
    temporary=out/'predictions.csv.tmp'
    with temporary.open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f); writer.writerow(['filename','class'])
        writer.writerows((p.name,CLASSES[int(label)]) for p,label in zip(images,predictions))
    validate_csv(temporary,[p.name for p in images])
    temporary.replace(out/'predictions.csv')
    validate_csv(out/'predictions.csv',[p.name for p in images])
    return out/'predictions.csv'


def main(argv=None):
    import argparse
    import sys
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True)
    p.add_argument('--weights','--weight',dest='weights',required=True)
    p.add_argument('--out','--output',dest='out',required=True)
    p.add_argument('--assume-one-per-class',action='store_true',default=False)
    p.add_argument('--debug',action='store_true')
    p.add_argument('--device',choices=['cpu'],default='cpu',help='Inference always uses CPU.')
    p.add_argument('--quick',action='store_true',help='CLI compatibility; never skips input images.')
    args=p.parse_args(argv)
    try:
        run_inference(args.input,args.weights,args.out,args.assume_one_per_class,args.debug)
    except Exception as exc:
        print(f'Error: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

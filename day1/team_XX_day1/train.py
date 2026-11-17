#!/usr/bin/env python3
"""Offline PileSynth, source-disjoint layout CV, fine-tuning and ONNX export.

Training dependencies belong to the existing training venv. Submission inference
uses only the separate requirements.txt beside infer.py.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
from pathlib import Path
import random

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from infer import (CLASSES, DEFAULT_PARAMS, MEAN, STD, aggregate_logits,
                   decode_image, extract_patches, normalize, paper_estimate, segment)

LAYOUTS = ('circle', 'grid', 'square')
ROOT = Path(__file__).resolve().parents[2]


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


@dataclass
class Source:
    path: Path
    label: int
    layout: str
    cutouts: list
    paper: np.ndarray


def clean_paper(rgb, seg):
    # Remove shadows as well as foreground before estimating broad paper lighting.
    radius = max(1, round(0.3 * seg.bean_size))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1, 2*radius+1))
    mask = cv2.dilate(seg.mask, kernel)
    filled = cv2.inpaint(rgb, mask, 5, cv2.INPAINT_TELEA)
    lab = cv2.cvtColor(filled, cv2.COLOR_RGB2LAB).astype(np.float32)
    smooth = cv2.cvtColor(np.uint8(np.clip(paper_estimate(lab), 0, 255)), cv2.COLOR_LAB2RGB)
    # Fully replace the removed region, with a feather outside it to avoid seams.
    blend = cv2.GaussianBlur(mask.astype(np.float32)/255, (0, 0), max(1, radius/3))
    blend[mask > 0] = 1
    paper = rgb * (1-blend[:,:,None]) + smooth * blend[:,:,None]
    return cv2.resize(np.uint8(np.clip(paper, 0, 255)), (768, 1024))


def load_sources(data):
    sources = []
    for label, name in enumerate(CLASSES):
        for layout in LAYOUTS:
            path = data / name / f'{layout}_{name}.jpg'
            rgb = decode_image(path)
            rgb = cv2.resize(rgb, (rgb.shape[1]//2, rgb.shape[0]//2), interpolation=cv2.INTER_AREA)
            seg = segment(rgb)
            cutouts = []
            for obj in seg.instances:
                x, y, w, h = obj.box
                cutouts.append(Image.fromarray(np.dstack((rgb[y:y+h, x:x+w], obj.mask)), 'RGBA'))
            paper = clean_paper(rgb, seg)
            sources.append(Source(path, label, layout, cutouts, paper))
    return sources


def rle_encode(mask):
    """COCO uncompressed RLE, column-major, starting with the zero run."""
    flat = np.asarray(mask, np.uint8).ravel(order='F')
    boundaries = np.flatnonzero(np.diff(np.r_[0, flat, 0]))
    counts = np.diff(np.r_[0, boundaries, len(flat)]).astype(int).tolist()
    # The trailing sentinel can produce an extra zero; this is legal COCO RLE.
    return {'size': list(mask.shape), 'counts': counts}


def rle_decode(rle):
    flat = np.zeros(sum(rle['counts']), np.uint8)
    offset = 0
    for i, count in enumerate(rle['counts']):
        if i % 2:
            flat[offset:offset+count] = 1
        offset += count
    return flat.reshape(rle['size'], order='F')


def make_pile(class_sources, backgrounds, rng, size=768, mode='mixed'):
    if mode == 'mixed':
        mode = str(rng.choice(['dense', 'medium', 'sparse'], p=[0.7, 0.2, 0.1]))
    if mode not in ('dense', 'medium', 'sparse'):
        raise ValueError(f'unknown pile mode: {mode}')
    paper_source = backgrounds[int(rng.integers(len(backgrounds)))]
    paper = paper_source.paper
    offset = int(rng.integers(paper.shape[0]-size+1))
    canvas = paper[offset:offset+size, :size].astype(np.float32).copy()
    owner = np.zeros((size,size), np.uint16)
    records = []
    target = int(rng.integers(12,36) if mode == 'dense' else rng.integers(10,31))
    for bean in range(1, target+1):
        src = class_sources[int(rng.integers(len(class_sources)))]
        cut = src.cutouts[int(rng.integers(len(src.cutouts)))].copy()
        if rng.random() < 0.5: cut = ImageOps.mirror(cut)
        if rng.random() < 0.5: cut = ImageOps.flip(cut)
        scale = float(rng.uniform(0.9,1.1))
        cut = cut.resize((max(1,round(cut.width*scale)), max(1,round(cut.height*scale))), Image.Resampling.BICUBIC)
        bean_length = max(cut.size)
        cut = cut.rotate(float(rng.uniform(0,360)), Image.Resampling.BICUBIC, expand=True)
        rgba = np.asarray(cut)
        h, w = rgba.shape[:2]
        mask = rgba[:,:,3] > 127
        area = int(mask.sum())
        # A one-pixel dilation measures actual mask contact, not bbox proximity.
        contact_mask = cv2.dilate(np.pad(np.uint8(mask), 1), np.ones((3,3), np.uint8)) > 0
        # Reject placements hiding >40% of either this bean or any older bean.
        for attempt in range(2000):
            if mode == 'dense' and records:
                anchor = records[int(rng.integers(len(records)))]
                angle = float(rng.uniform(0, 2*np.pi))
                length = (bean_length + anchor['bean_length']) / 2
                distance = float(rng.uniform(0.5, 1.0)) * length
                centre = np.asarray(anchor['centre']) + distance*np.array([np.cos(angle), np.sin(angle)])
            elif mode == 'dense':
                centre = rng.normal(size/2, 0.1*bean_length, 2)
            else:
                sigma = min(0.26, 0.13 + attempt / 10000) * size
                if mode == 'medium': sigma *= 0.55
                centre = rng.normal(size/2, sigma, 2)
            x, y = np.rint(centre - [w/2,h/2]).astype(int)
            if x < 4 or y < 4 or x+w >= size-4 or y+h >= size-4: continue
            region = owner[y:y+h, x:x+w]
            hidden = region[mask]
            overlap = int(np.count_nonzero(hidden))
            if overlap > 0.4 * area: continue
            neighbours = np.unique(owner[y-1:y+h+1, x-1:x+w+1][contact_mask])
            neighbours = neighbours[neighbours > 0]
            if mode == 'dense' and records and not len(neighbours): continue
            valid = True
            for old_id in np.unique(hidden[hidden > 0]):
                old = records[int(old_id)-1]
                newly_hidden = int(np.count_nonzero(hidden == old_id))
                if old['occluded'] + newly_hidden > 0.4 * old['amodal_area']:
                    valid = False; break
            if valid: break
        else:
            raise RuntimeError('cannot place pile within overlap bounds')
        for old_id in np.unique(hidden[hidden > 0]):
            records[int(old_id)-1]['occluded'] += int(np.count_nonzero(hidden == old_id))
        for old_id in neighbours:
            records[int(old_id)-1]['touching_ids'].append(bean)
        # Soft shadow followed by alpha compositing, all in image coordinates.
        shadow = np.zeros((size,size), np.float32)
        shadow[y+3:y+h+3, x+3:x+w+3] = rgba[:,:,3].astype(np.float32)/255
        shadow = cv2.GaussianBlur(shadow, (0,0), 2.2)
        canvas *= (1 - 0.15*shadow[:,:,None])
        alpha = rgba[:,:,3:4].astype(np.float32)/255
        canvas[y:y+h,x:x+w] = canvas[y:y+h,x:x+w]*(1-alpha) + rgba[:,:,:3]*alpha
        owner[y:y+h,x:x+w][mask] = bean
        records.append({'source_image': src.path.name, 'source_layout': src.layout,
                        'amodal_area': area, 'occluded': 0, 'new_overlap_fraction': overlap/area,
                        'pile_mode': mode, 'centre': [float(x+w/2), float(y+h/2)],
                        'bean_length': bean_length, 'touching_ids': [int(k) for k in neighbours]})
    canvas *= rng.uniform(0.95,1.05) * rng.uniform(0.97,1.03, (1,1,3))
    im = Image.fromarray(np.uint8(np.clip(canvas,0,255)))
    quality = int(rng.integers(30,96))
    encoded = io.BytesIO(); im.save(encoded, format='JPEG', quality=quality)
    return encoded.getvalue(), owner, records, paper_source.path.name, quality


def split_modes(count, mode, rng):
    if mode != 'mixed': return [mode] * count
    # Largest-remainder allocation keeps even quick splits close to 70/20/10.
    quotas = np.array([0.7, 0.2, 0.1]) * count
    counts = np.floor(quotas).astype(int)
    for i in np.argsort(-(quotas-counts), kind='stable')[:count-int(counts.sum())]:
        counts[i] += 1
    modes = np.repeat(['dense', 'medium', 'sparse'], counts)
    rng.shuffle(modes)
    return modes.tolist()


def generate_split(sources, layouts, count_per_class, out, rng, pile_mode='mixed'):
    out.mkdir(parents=True, exist_ok=True)
    pool = [s for s in sources if s.layout in layouts]
    coco = {'images': [], 'annotations': [], 'categories': [
        {'id': i+1, 'name': name} for i,name in enumerate(CLASSES)],
        'source_layouts': list(layouts), 'mask_semantics': 'visible instance masks; uncompressed COCO RLE'}
    paths = []
    modes = iter(split_modes(len(CLASSES)*count_per_class, pile_mode, rng))
    for label, name in enumerate(CLASSES):
        class_sources = [s for s in pool if s.label == label]
        for j in range(count_per_class):
            mode = next(modes)
            encoded, owner, records, paper, quality = make_pile(class_sources, pool, rng, mode=mode)
            filename = f'{name}_{j:04d}.jpg'; path = out / filename
            path.write_bytes(encoded)
            Image.fromarray(owner).save(out / f'{path.stem}_instances.png')
            image_id = len(coco['images'])+1
            coco['images'].append({'id': image_id, 'file_name': filename, 'height': owner.shape[0],
                                   'width': owner.shape[1], 'background_source': paper,
                                   'jpeg_quality': quality, 'class_id': label, 'pile_mode': mode,
                                   'instance_mask': f'{path.stem}_instances.png'})
            for k, record in enumerate(records, 1):
                mask = owner == k
                rle = rle_encode(mask)
                if not np.array_equal(rle_decode(rle), mask):
                    raise AssertionError('COCO RLE failed round-trip')
                x,y,w,h = cv2.boundingRect(np.uint8(mask))
                coco['annotations'].append({'id': len(coco['annotations'])+1, 'image_id': image_id,
                    'category_id': label+1, 'bbox': [x,y,w,h], 'area': int(mask.sum()),
                    'iscrowd': 0, 'segmentation': rle, 'instance_id': k, **record})
            paths.append((path,label))
    write_json(out/'instances.json', coco)
    return paths, coco


def run_name(args):
    # Preserve the legacy default quick path, but honour explicit run isolation.
    return 'quick' if args.quick and args.run == 'cv' else args.run


def background_check(sources, results):
    def count_beans(rgb):
        try:
            return len(segment(rgb).instances)
        except ValueError as error:
            if str(error) != 'no bean foreground detected': raise
            return 0

    checks = []
    for source in sources[:20]:
        check = {'source_image': source.path.name, 'detected_beans': count_beans(source.paper),
                 'jpeg_crop_detected_beans': {}}
        # Check empty paper after the same square crop and JPEG pipeline too.
        for quality in (30, 95):
            buffer = io.BytesIO()
            Image.fromarray(source.paper[128:896]).save(buffer, format='JPEG', quality=quality)
            with Image.open(io.BytesIO(buffer.getvalue())) as im:
                check['jpeg_crop_detected_beans'][str(quality)] = count_beans(np.asarray(im.convert('RGB')))
        checks.append(check)
    passed = len(checks) == 20 and all(c['detected_beans'] == 0 and
        not any(c['jpeg_crop_detected_beans'].values()) for c in checks)
    report = {'passed': passed, 'backgrounds_checked': len(checks), 'checks': checks,
              'empty_segment_behavior': 'ValueError: no bean foreground detected means zero beans'}
    write_json(results/'background_check.json', report)
    if not passed: raise RuntimeError('empty paper has detected beans; see background_check.json')
    return report


def pile_statistics(coco, split):
    rows = []
    for im in coco['images']:
        beans = [a for a in coco['annotations'] if a['image_id'] == im['id']]
        rows.append({'split': split, 'filename': im['file_name'], 'mode': im['pile_mode'],
                     'beans': len(beans), 'touching_beans': sum(bool(a['touching_ids']) for a in beans),
                     'touching_fraction': sum(bool(a['touching_ids']) for a in beans)/len(beans),
                     'mean_visible_fraction': float(np.mean([a['area']/a['amodal_area'] for a in beans])),
                     'min_visible_fraction': min(a['area']/a['amodal_area'] for a in beans),
                     'max_new_overlap_fraction': max(a['new_overlap_fraction'] for a in beans)})
    return rows


def preview_synth(sources, args):
    root = args.piles / run_name(args) / 'preview'
    rng = np.random.default_rng(args.seed)
    samples = args.results / 'pile_samples_v1'; samples.mkdir(parents=True, exist_ok=True)
    image_count = 0; ann_count = 0; classes = set(); max_dimension = 0
    stats = []; split_counts = {}
    for split, layouts in [('train', ('circle','grid')), ('val', ('square',))]:
        paths, coco = generate_split(sources, layouts, 1, root/split, rng, args.pile_mode)
        stats.extend(pile_statistics(coco, split))
        split_counts[split] = {mode: sum(im['pile_mode'] == mode for im in coco['images'])
                               for mode in ('dense', 'medium', 'sparse')}
        for path,label in paths:
            im = Image.open(path); im.thumbnail((800,800))
            im.save(samples/f'{split}_{CLASSES[label]}.jpg')
            # Exercise exactly the preprocessing used for real inference.
            patches, _, _, _ = extract_patches(decode_image(path), args.size)
            assert len(patches) > 0
            max_dimension = max(max_dimension, *im.size)
            classes.add(CLASSES[label]); image_count += 1
        ann_count += len(coco['annotations'])
    verification = {'passed': image_count == 14 and len(classes) == 7 and max_dimension <= 800,
                    'samples': image_count, 'classes': sorted(classes), 'max_dimension': max_dimension,
                    'annotations': ann_count, 'rle_roundtrip': True, 'source_disjoint': True,
                    'coco_root': str(root), 'sample_dir': str(samples)}
    dense = [s for s in stats if s['mode'] == 'dense']
    total = sum(s['beans'] for s in dense)
    contact = sum(s['touching_beans'] for s in dense)/total if total else None
    visible = sum(s['mean_visible_fraction']*s['beans'] for s in dense)/total if total else None
    passed = (not dense or all(s['touching_fraction'] >= 0.7 for s in dense)) and all(
        s['min_visible_fraction'] >= 0.6 and s['max_new_overlap_fraction'] <= 0.4 for s in stats)
    report = {'passed': passed, 'requested_mode': args.pile_mode, 'seed': args.seed,
              'split_counts': split_counts, 'piles': stats,
              'contact_definition': 'amodal mask overlap or 8-neighbour pixel contact at placement; symmetric instance IDs in COCO',
              'dense': {'piles': len(dense), 'beans': total, 'touching_fraction': contact,
                        'mean_visible_fraction': visible, 'target_touching_fraction': 0.7},
              'dense_only_validation_accuracy': 'not evaluated by synth stage; training writes synthetic_dense metrics'}
    verification['passed'] = verification['passed'] and passed
    write_json(args.results/'pile_stats_v1.json', report)
    write_json(args.results/'pile_verification_v1.json', verification)
    if not verification['passed']: raise RuntimeError('pile verification failed; see pile_stats_v1.json')
    print(json.dumps(verification), flush=True)


# Training imports stay inside this path; importing preprocessing never needs torch.
def build_model(name):
    import torch
    from torchvision import models
    registry = {
        'mobilenetv3_large_100': (models.mobilenet_v3_large, 'mobilenet_v3_large-8738ca79.pth'),
        'efficientnet_b0': (models.efficientnet_b0, 'efficientnet_b0_rwightman-7f5810bc.pth'),
        'mobilenetv3_small_100': (models.mobilenet_v3_small, 'mobilenet_v3_small-047dcff4.pth'),
    }
    constructor, filename = registry[name]
    cached = Path(torch.hub.get_dir())/'checkpoints'/filename
    if not cached.is_file():
        raise FileNotFoundError(f'Offline ImageNet weights missing: {cached}; ask Claude to supply them')
    model = constructor(weights=None)
    model.load_state_dict(torch.load(cached, map_location='cpu', weights_only=True))
    last = model.classifier[-1]
    model.classifier[-1] = torch.nn.Linear(last.in_features, len(CLASSES))
    return model


def make_patch_records(paths, size, background=240):
    records = []
    for path,label in paths:
        patches, kinds, _, _ = extract_patches(decode_image(path), size, {'background': background})
        records.append({'filename': path.name, 'label': label, 'patches': patches, 'kinds': kinds})
    return records


def fit_model(model, records, args):
    import torch
    from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
    from torchvision import transforms

    class Patches(Dataset):
        def __init__(self):
            self.patches = np.concatenate([r['patches'] for r in records])
            self.labels = np.concatenate([np.full(len(r['patches']), r['label']) for r in records])
            self.augment = transforms.Compose([
                transforms.RandomAffine(180, scale=(0.9,1.1), fill=240),
                transforms.RandomHorizontalFlip(), transforms.RandomVerticalFlip(),
                transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.1, hue=0.02),
                transforms.RandomApply([transforms.GaussianBlur(3, (0.1,1.0))], p=0.2)])
        def __len__(self): return len(self.labels)
        def __getitem__(self, i):
            patch = self.patches[i].copy()
            # Expose both constant fills during training; choose the deployed
            # fill using source-disjoint CV, never using test images.
            fill = 0 if random.random() < 0.5 else 240
            patch[np.all(patch == 240, axis=2)] = fill
            self.augment.transforms[0].fill = fill
            im = self.augment(Image.fromarray(patch))
            buffer = io.BytesIO(); im.save(buffer, format='JPEG', quality=random.randint(30,95))
            with Image.open(io.BytesIO(buffer.getvalue())) as restored:
                x = normalize(np.asarray(restored.convert('RGB'))[None])[0]
            return torch.from_numpy(x), int(self.labels[i])

    dataset = Patches()
    frequencies = np.bincount(dataset.labels, minlength=len(CLASSES))
    sampler = WeightedRandomSampler(torch.as_tensor(1/frequencies[dataset.labels], dtype=torch.double),
        num_samples=min(len(dataset), args.batch_size*2) if args.quick else len(dataset), replacement=True)
    loader = DataLoader(dataset, batch_size=args.batch_size, sampler=sampler, num_workers=0)
    model.to(args.device)
    head_ids = {id(p) for p in model.classifier.parameters()}
    history = []
    amp = str(args.device).startswith('cuda')
    scaler = torch.amp.GradScaler('cuda', enabled=amp)
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=0.1)
    for stage, epochs in [('head', 1 if args.quick else args.head_epochs),
                          ('finetune', 1 if args.quick else args.finetune_epochs)]:
        for p in model.parameters(): p.requires_grad = stage != 'head' or id(p) in head_ids
        groups = [{'params': list(model.classifier.parameters()), 'lr': 1e-3}]
        if stage == 'finetune':
            groups.append({'params': [p for p in model.parameters() if id(p) not in head_ids], 'lr': 1e-4})
        optimizer = torch.optim.AdamW(groups, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1,epochs))
        for epoch in range(epochs):
            model.train()
            if stage == 'head': model.features.eval()  # freeze BN as well as gradients
            total_loss = 0.; total = 0
            for x,y in loader:
                x,y = x.to(args.device),y.to(args.device)
                optimizer.zero_grad(set_to_none=True)
                with torch.autocast(device_type='cuda' if amp else 'cpu', enabled=amp):
                    loss = loss_fn(model(x),y)
                scaler.scale(loss).backward(); scaler.step(optimizer); scaler.update()
                total_loss += float(loss.detach())*len(y); total += len(y)
            scheduler.step()
            history.append({'stage':stage,'epoch':epoch+1,'loss':total_loss/total})
            print(f'{stage} {epoch+1}/{epochs}: loss={total_loss/total:.5f}', flush=True)
    return history


def predict_records(model, records, device, batch_size):
    import torch
    model.eval(); result = []
    with torch.no_grad():
        for record in records:
            x = normalize(record['patches'])
            logits = np.concatenate([model(torch.from_numpy(x[i:i+batch_size]).to(device)).cpu().numpy()
                                     for i in range(0,len(x),batch_size)])
            result.append({**{k:v for k,v in record.items() if k != 'patches'}, 'logits': logits})
    return result


def evaluate(records, weight):
    confusion = np.zeros((len(CLASSES),len(CLASSES)), int)
    patch_correct = 0; patches = 0; predictions = []
    for r in records:
        scores = aggregate_logits(r['logits'], r['kinds'], weight)
        prediction = int(np.argmax(scores))
        confusion[r['label'],prediction] += 1
        patch_correct += int((r['logits'].argmax(axis=1) == r['label']).sum())
        patches += len(r['logits'])
        predictions.append({'filename':r['filename'],'true':CLASSES[r['label']],
                            'predicted':CLASSES[prediction]})
    return {'image_accuracy': float(np.trace(confusion)/confusion.sum()),
            'patch_accuracy': patch_correct/patches, 'images': int(confusion.sum()),
            'patches': patches, 'confusion':confusion.tolist(), 'predictions':predictions}


def confusion_png(matrix, path):
    # Pillow keeps plotting optional on the offline training host.
    from PIL import ImageDraw
    m = np.asarray(matrix); cell=70; left=120; top=80
    im = Image.new('RGB',(left+7*cell,top+7*cell+30),'white'); draw = ImageDraw.Draw(im)
    draw.text((left,8),'Predicted class (columns); true class (rows)',fill='black')
    for i,name in enumerate(CLASSES):
        draw.text((left+i*cell,top-25),name[:9],fill='black')
        draw.text((4,top+i*cell+25),name,fill='black')
        for j in range(7):
            value = int(m[i,j]); shade = 255-round(180*value/max(1,int(m.max())))
            xy=(left+j*cell,top+i*cell,left+(j+1)*cell,top+(i+1)*cell)
            draw.rectangle(xy,fill=(shade,shade,255),outline='gray')
            draw.text((xy[0]+28,xy[1]+27),str(value),fill='black')
    im.save(path)


def export_models(models, parity_patches, args, destination, params):
    import torch
    import onnx
    import onnxruntime as ort

    class Ensemble(torch.nn.Module):
        def __init__(self):
            super().__init__(); self.models = torch.nn.ModuleList([m.cpu().eval() for m in models])
        def forward(self, x):
            return sum(m(x) for m in self.models)/len(self.models)

    graph = Ensemble().eval()
    destination.mkdir(parents=True, exist_ok=True)
    path = destination/'best.onnx'
    x = normalize(parity_patches[:32])
    if len(x) < 32: x = np.tile(x, (int(np.ceil(32/len(x))),1,1,1))[:32]
    with torch.no_grad():
        torch.onnx.export(graph, torch.from_numpy(x[:2]), str(path), input_names=['images'],
            output_names=['logits'], opset_version=17,
            dynamic_axes={'images':{0:'batch'},'logits':{0:'batch'}}, dynamo=False)
        expected = graph(torch.from_numpy(x)).numpy()
    onnx.checker.check_model(onnx.load(str(path)))
    options = ort.SessionOptions(); options.intra_op_num_threads=4
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    runtime = ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
    actual = runtime.run(None, {'images':x})[0]
    net = cv2.dnn.readNetFromONNX(str(path)); net.setInput(x); fallback = net.forward()
    torch_error = float(np.max(np.abs(expected-actual)))
    cv_error = float(np.max(np.abs(fallback-actual)))
    # Check a different batch size too, including the single-file tail batch.
    net.setInput(x[:1]); fallback_one = net.forward()
    ort_one = runtime.run(None, {'images':x[:1]})[0]
    cv_error = max(cv_error,float(np.max(np.abs(fallback_one-ort_one))))
    parity = {'patches':len(x),'torch_ort_max_abs_diff':torch_error,'cv2_ort_max_abs_diff':cv_error,
              'passed':torch_error < 1e-4 and cv_error < 1e-3, 'opset':17,
              'dynamic_batch_checked':[1,32], 'weights':str(path)}
    if not parity['passed']: raise RuntimeError(f'ONNX parity failed: {parity}')
    write_json(destination/'meta.json', {'version':1,'classes':list(CLASSES),'input_size':args.size,
        'mean':list(MEAN),'std':list(STD),'patch_params':params,'opset':17,
        'ensemble_members':len(models),'quick_smoke_only':args.quick,
        'normalization':'external, in infer.py', 'backbone':args.selected_backbone})
    return parity


def run_training(sources, args):
    import torch
    torch.set_num_threads(4); torch.manual_seed(args.seed)
    if str(args.device).startswith('cuda'):
        if not torch.cuda.is_available(): raise RuntimeError('CUDA requested but unavailable; smoke-test with --device cpu --quick')
        torch.cuda.manual_seed_all(args.seed)
    run = run_name(args)
    out = args.results/run; out.mkdir(parents=True, exist_ok=True)
    weights = args.weights/run if args.quick else args.weights
    weights.mkdir(parents=True, exist_ok=True)
    backbones = args.backbones or (['mobilenetv3_small_100'] if args.quick else
        ['mobilenetv3_large_100','efficientnet_b0','mobilenetv3_small_100'])
    rng = np.random.default_rng(args.seed)
    folds = []; model_bank = {b:[] for b in backbones}; candidates = []
    parity_patches = None
    for held_out in LAYOUTS:
        training_layouts = [x for x in LAYOUTS if x != held_out]
        folder = args.piles/run/f'fold_{held_out}'
        train_paths, train_coco = generate_split(sources, training_layouts,
            1 if args.quick else args.train_piles_per_class, folder/'train', rng, args.pile_mode)
        val_paths, val_coco = generate_split(sources, [held_out],
            1 if args.quick else args.val_piles_per_class, folder/'val', rng, args.pile_mode)
        dense_paths, dense_coco = generate_split(sources, [held_out],
            1 if args.quick else args.val_piles_per_class, folder/'val_dense', rng, 'dense')
        train_sources = {s.path.name for s in sources if s.layout in training_layouts}
        val_sources = {s.path.name for s in sources if s.layout == held_out}
        assert not train_sources & val_sources
        for coco, permitted in [(train_coco,train_sources),(val_coco,val_sources),(dense_coco,val_sources)]:
            assert all(a['source_image'] in permitted for a in coco['annotations'])
            assert all(im['background_source'] in permitted for im in coco['images'])
        originals = [(s.path,s.label) for s in sources if s.layout == held_out]
        train_paths += [(s.path,s.label) for s in sources if s.layout in training_layouts]
        train_records = make_patch_records(train_paths,args.size)
        val_records = {bg:make_patch_records(val_paths,args.size,bg) for bg in [0,240]}
        dense_records = {bg:make_patch_records(dense_paths,args.size,bg) for bg in [0,240]}
        arranged_records = {bg:make_patch_records(originals,args.size,bg) for bg in [0,240]}
        parity_patches = np.concatenate([r['patches'] for r in val_records[240]])[:32]
        fold = {'held_out_layout':held_out,'train_sources':sorted(train_sources),
                'val_sources':sorted(val_sources),'source_disjoint':True,'models':{}}
        for backbone in backbones:
            print(f'fold={held_out} backbone={backbone}',flush=True)
            model = build_model(backbone)
            history = fit_model(model,train_records,args)
            entries = []
            for background in [0,240]:
                val_logits = predict_records(model,val_records[background],args.device,args.batch_size)
                dense_logits = predict_records(model,dense_records[background],args.device,args.batch_size)
                orig_logits = predict_records(model,arranged_records[background],args.device,args.batch_size)
                for weight in [0.25,0.5,0.75]:
                    metric = evaluate(val_logits,weight); arranged = evaluate(orig_logits,weight)
                    dense_metric = evaluate(dense_logits, weight)
                    key = f'{backbone}_bg{background}_iw{weight}'
                    confusion_png(metric['confusion'],out/f'{held_out}_{key}_confusion.png')
                    confusion_png(dense_metric['confusion'],out/f'{held_out}_{key}_dense_confusion.png')
                    entry = {'config':key,'backbone':backbone,'background':background,
                        'instance_weight':weight,'synthetic':metric,'synthetic_dense':dense_metric,
                        'arranged_held_out':arranged}
                    entries.append(entry); candidates.append({'fold':held_out,**entry})
            fold['models'][backbone] = {'history':history,'evaluations':entries}
            torch.save(model.cpu().state_dict(), weights/f'{held_out}_{backbone}.pth')
            model_bank[backbone].append(model.cpu().eval())
        folds.append(fold)
        write_json(out/'progress.json', {'smoke_only':args.quick,'folds':folds})
    scores = {}
    for entry in candidates:
        scores.setdefault(entry['config'],[]).append(entry['synthetic']['image_accuracy'])
    best_key = max(sorted(scores),key=lambda k:float(np.mean(scores[k])))
    selected = next(c for c in candidates if c['config']==best_key)
    args.selected_backbone = selected['backbone']
    params = {**DEFAULT_PARAMS,'background':selected['background'],'instance_weight':selected['instance_weight']}
    selected_folds = [c for c in candidates if c['config']==best_key]
    synthetic_cm = np.sum([c['synthetic']['confusion'] for c in selected_folds],axis=0)
    arranged_cm = np.sum([c['arranged_held_out']['confusion'] for c in selected_folds],axis=0)
    dense_cm = np.sum([c['synthetic_dense']['confusion'] for c in selected_folds],axis=0)
    confusion_png(synthetic_cm,out/'synthetic_confusion.png')
    confusion_png(arranged_cm,out/'arranged_oof_confusion.png')
    confusion_png(dense_cm,out/'synthetic_dense_confusion.png')
    parity = export_models(model_bank[args.selected_backbone],parity_patches,args,weights,params)
    metrics = {'smoke_only':args.quick,'seed':args.seed,'folds':folds,'selected_config':best_key,
        'cv_candidate_scores':{k:float(np.mean(v)) for k,v in scores.items()},
        'synthetic_image_accuracy':float(np.trace(synthetic_cm)/synthetic_cm.sum()),
        'synthetic_images':int(synthetic_cm.sum()),
        'pile_mode': args.pile_mode,
        'synthetic_dense_image_accuracy':float(np.trace(dense_cm)/dense_cm.sum()),
        'synthetic_dense_images':int(dense_cm.sum()),
        'arranged_oof_image_accuracy':float(np.trace(arranged_cm)/arranged_cm.sum()),
        'arranged_oof_images':int(arranged_cm.sum()),'parity':parity,
        'evaluation_note':'Every prediction uses a model trained on other source layouts. Hyperparameters selected on these folds; no independent test estimate.',
        'training_versions':{'torch':torch.__version__,'opencv':cv2.__version__,'numpy':np.__version__}}
    write_json(out/'metrics.json',metrics)
    decision = ('# Day 1 model decision\n\n' +
        ('CPU QUICK SMOKE ONLY: these scores do not establish model quality. Run full GPU CV before submission.\n\n' if args.quick else '') +
        f'Selected `{best_key}` by mean held-out synthetic image accuracy; all candidates and per-fold evidence are in `{run}/metrics.json`. '
        'Both black and paper fills were exposed during augmentation and compared on held-out piles; instance/window weights were also selected there.\n\n'
        'Export averages the three layout-fold models into one ONNX graph. This retains the validated fold training procedure and uses every source in two members; '
        'an all-layout retrain has no held-out estimate in this dataset. The ensemble itself has no unbiased score on these source photos, so the reported metrics are fold predictions only. '
        'Architecture/config selection uses CV and is exploratory, not an independent test result.\n\n'
        'FP32 retained. No INT8 accuracy claim or unvalidated quantization.\n')
    decision_path = out/'decision.md' if args.quick else args.results/'decision.md'
    decision_path.write_text(decision,encoding='utf-8')
    if args.quick and not (args.results/'decision.md').exists():
        (args.results/'decision.md').write_text(decision,encoding='utf-8')
    print(f'Completed {out / "metrics.json"}',flush=True)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, default=ROOT/'data/day1/train')
    p.add_argument('--piles', type=Path, default=ROOT/'data/day1/piles')
    p.add_argument('--results', type=Path, default=ROOT/'results/day1')
    p.add_argument('--weights', type=Path, default=Path(__file__).resolve().parent/'weights')
    p.add_argument('--device', default='cpu')
    p.add_argument('--quick', action='store_true')
    p.add_argument('--stage', choices=['synth', 'all'], default='all')
    p.add_argument('--pile-mode', choices=['mixed', 'dense', 'sparse'], default='mixed')
    p.add_argument('--seed', type=int, default=2026)
    p.add_argument('--size', type=int, default=160)
    p.add_argument('--run', default='cv')
    p.add_argument('--backbones', nargs='+', choices=['mobilenetv3_large_100','efficientnet_b0','mobilenetv3_small_100'])
    p.add_argument('--batch-size', type=int, default=32)
    p.add_argument('--head-epochs', type=int, default=5)
    p.add_argument('--finetune-epochs', type=int, default=30)
    p.add_argument('--train-piles-per-class', type=int, default=20)
    p.add_argument('--val-piles-per-class', type=int, default=10)
    args = p.parse_args()
    if not args.quick and args.val_piles_per_class < 10:
        p.error('full CV requires at least 10 validation piles per class')
    if args.size < 32 or args.batch_size < 2 or min(args.head_epochs,args.finetune_epochs,args.train_piles_per_class) < 1:
        p.error('invalid image size, batch size, epoch count or pile count')
    return args


def main():
    args = parse_args()
    random.seed(args.seed); np.random.seed(args.seed)
    cv2.setNumThreads(4)
    sources = load_sources(args.data)
    background_check(sources, args.results)
    preview_synth(sources, args)
    if args.stage != 'synth':
        run_training(sources, args)


if __name__ == '__main__':
    main()

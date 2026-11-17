# Day 1 coffee-bean classifier

> **Update 2026-11-17:** the judges' Pi 4 runs Raspberry Pi OS **32-bit** (armhf) with Python 3.13.5. onnxruntime has no wheel there, so `requirements.txt` now pins numpy 2.5.4, pillow 13.0.0 and opencv-python-headless 5.0.0.93 from piwheels, and inference runs on OpenCV DNN. The README shipped in the zip is `day1/dist_README.md`; packaging/eval tools are in `day1/tools/`.

CPU inference for the official class order: `good, shell, black, husk, broken,
parchment, immature`. Each image receives one class. The official
`day1/INFER_SPEC.md` takes precedence over slide examples.

## Status and required handoff

The CPU quick run exercises training, source-disjoint layout CV, export and
backend parity. Its weights in `weights/quick/` are **smoke-test weights only**.
Do not submit them. Evidence is in `results/day1/quick/metrics.json`,
`results/day1/segment_counts.csv`, `results/day1/pile_verification.json` and
`results/day1/pytest.xml`, relative to the repository root.

Full GPU CV and a fresh inference-only Pi installation are still required.
The inference dependency ranges allow pip to select releases for Python 3.9–3.13.
An AST regression checks Python 3.9 syntax and deferred annotations. A fresh
aarch64 installation on the judges' OS has not been verified. Do not claim D5
passed until that verification succeeds.
No packages were installed or downloaded in the offline sandbox.

## Install and run on Pi (Claude)

Use a 64-bit OS and Python 3.9–3.13. From the extracted `team_XX_day1/` folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python infer.py --input test/ --weights weights/best.onnx --out outputs/
```

Use the installed compatible Python interpreter (for example Bookworm's Python
3.11 or Trixie's Python 3.13). Repeat clean-environment verification before submission.

The official command with a `.pt` path also works when `best.onnx` is beside it:

```sh
.venv/bin/python infer.py --input test/ --weights weights/best.pt --out outputs/
```

If the requested path exists, it must contain a valid ONNX model, regardless of
its extension. If it is missing, `best.onnx` in the same directory is used with a
notice on stderr. A present invalid file is never silently replaced.

`--weight` and `--output` are aliases. Inputs may be one file or a directory
(recursively scanned); `.jpg`, `.jpeg`, and `.png` extensions are case-insensitive.
Files are sorted by basename. Basenames must be unique. Use a fresh output folder
outside the input tree. Outputs are UTF-8 `predictions.csv` with exactly
`filename,class` columns, plus every class directory and unchanged copies of
source images in their predicted directory. CSV rows are validated before and
after publication. Missing/empty/invalid input, invalid weights, duplicate names,
unsafe output paths, and invalid CSV produce stderr errors and nonzero exit.

`--debug` optionally adds labelled preprocessing overlays under `_debug/`.
`--assume-one-per-class` is OFF by default. Enable it only with permission from
judges and exactly seven input images; it uses Hungarian assignment on mean
log-probabilities. Ordinary inference predicts each image independently.
`--device cpu --quick` is accepted for smoke-test command compatibility;
inference remains deterministic and processes every image with the supplied model.

## Preprocessing and inference

JPEG draft decoding targets 1536 x 2048, then EXIF orientation is applied, including
support for files without EXIF. Large non-JPEG images are capped to the same
working maximum dimension. A heavily blurred LAB estimate models paper lighting.
LAB distance, a darker-than-background check, morphology and hole filling isolate
foreground; small and border components are discarded.

A distance-transform watershed splits touching components. ROI sliding windows
provide a second patch source when instance segmentation is uncertain. All bean
crops in an image use the same median-size scale, preserving relative size rather
than stretch-fitting each bean. Square crops use the selected constant background;
windows require foreground coverage. Both are resized to the size in `meta.json`.

RGB float32 inputs are normalized outside the graph with the mean/std in
`meta.json`. Instances and windows each contribute their mean log-softmax score,
combined with the CV-selected weight. The class with the largest score wins.
There is no random augmentation, TTA, adaptation or training at inference.

One ONNX Runtime CPU session uses four intra-op threads and all graph
optimizations. Patches are processed in bounded batches. If importing ONNX Runtime
fails, OpenCV DNN loads the same ONNX bytes automatically. A corrupt model is an
error rather than a fallback trigger. No torch, torchvision, timm, scipy or onnx
Python package is needed for inference.

## Training and verification from repository root (Claude)

Use the existing `.venv/bin/python`. The prepared training environment includes
torch, torchvision, onnx, onnxruntime, OpenCV, NumPy, Pillow and pytest. The
submission requirements intentionally exclude training dependencies. Training
loads local torchvision ImageNet cache files and never downloads weights:

- `mobilenet_v3_large-8738ca79.pth`
- `efficientnet_b0_rwightman-7f5810bc.pth`
- `mobilenet_v3_small-047dcff4.pth`

The accepted CLI backbone names map to torchvision equivalents of the architectures
listed in `SPEC.md`. Missing cache files cause a clear error. Full GPU command:

```sh
.venv/bin/python day1/team_XX_day1/train.py \
  --device cuda --run cv \
  --backbones mobilenetv3_large_100 efficientnet_b0 mobilenetv3_small_100 \
  --head-epochs 5 --finetune-epochs 30 \
  --train-piles-per-class 20 --val-piles-per-class 10 --batch-size 32
```

Then verify the full model and generate submission sanity outputs:

```sh
.venv/bin/python -m pytest day1/tests -q --junitxml=results/day1/pytest.xml
.venv/bin/python day1/team_XX_day1/infer.py \
  --input data/day1/train --weights day1/team_XX_day1/weights/best.onnx \
  --out day1/team_XX_day1/outputs
```

The GPU command writes per-fold metrics and confusion images under
`results/day1/cv/`, the model decision under `results/day1/decision.md`, and full
weights plus metadata under `day1/team_XX_day1/weights/`. Review the full metrics,
per-class errors and masks before selecting the submission. Quick results do not
establish accuracy on hidden test piles.

Offline CPU smoke commands (already exercised):

```sh
.venv/bin/python day1/tools/segment_check.py --device cpu --quick
.venv/bin/python day1/team_XX_day1/train.py --device cpu --quick --stage synth
.venv/bin/python day1/team_XX_day1/train.py --device cpu --quick
.venv/bin/python -m pytest day1/tests -q --junitxml=results/day1/pytest.xml
.venv/bin/python day1/team_XX_day1/infer.py \
  --input data/day1/train --weights day1/team_XX_day1/weights/quick/best.onnx \
  --out results/day1/quick/infer_outputs --device cpu --quick
```

## PileSynth, CV and export

PileSynth extracts masked cut-outs, dilates their masks by 0.3 bean length and
inpaints paper with TELEA. Removed areas are replaced with the same broad LAB
lighting estimate used by segmentation, feathered into the surrounding paper.
`background_check.json` records segmentation on empty backgrounds and JPEG crops.

`--pile-mode {mixed,dense,sparse}` defaults to `mixed`: each train/val split has
70% dense, 20% medium and 10% sparse piles, rounded by largest remainder and
shuffled. Dense heaps contain 12–35 beans. Each bean after the first is placed
0.5–1.0 average bean length from an existing bean and must make actual mask
contact. Cumulative occlusion of each bean and the new bean's overlap both stay
at or below 40%. Medium piles use a narrower Gaussian; sparse retains the old
placement. Piles also receive rotation, mild scaling, flips, soft shadows,
global brightness jitter ±5%, channel white-balance jitter ±3%, and JPEG
recompression. JPEG augmentation also applies to training patches to suppress
source compression shortcuts. Every synthetic image is preprocessed using the
same functions imported from `infer.py`.

Synthetic images, visible-instance PNG masks and `instances.json` live under
`data/day1/piles/<run>/fold_<layout>/{train,val}/`. COCO uses category IDs starting
at one, visible-instance bounding boxes/areas and uncompressed column-major RLE.
`source_image`, `source_layout`, background provenance, amodal area and occlusion
are recorded. Masks are generated by the same compositing ownership map and RLE
is checked by round-trip decoding. Preview images live in
`results/day1/pile_samples_v1/`, with dimensions in `pile_verification_v1.json`.
`pile_stats_v1.json` records dense contact and mean visible fractions, per-pile
occlusion bounds and actual mode counts. Contact means mask overlap or adjacent
pixels at placement, with symmetric touching instance IDs recorded in COCO.

V1 synthesis verification, isolated from the active v0 run:

```sh
.venv/bin/python day1/team_XX_day1/train.py \
  --device cpu --quick --stage synth --pile-mode mixed --run v1check
.venv/bin/python -m pytest day1/tests -q --junitxml=results/day1/v1check/pytest.xml
```

An explicit `--run` is honoured even with `--quick`; this command writes piles
under `data/day1/piles/v1check/preview/`. The legacy quick command without an
explicit run still uses `quick/`. Synthesis does not train or write weights.
For a later full V1 GPU run, Claude can use the full training command above with
`--run v1 --pile-mode mixed --weights day1/team_XX_day1/weights_v1`.

Each CV fold holds out one entire layout. Both its foreground cut-outs and paper
backgrounds are excluded from training. Validation piles use only held-out
sources. An additional dense-only validation set under `val_dense/` uses only
held-out sources, with the same per-class image count as ordinary validation.
Per-config `synthetic_dense` metrics, dense confusion PNGs, and aggregate
`synthetic_dense_image_accuracy` are written by training. The synth-only stage
does not report model accuracy. Arranged-photo evaluation uses the corresponding held-out fold
model. Full CV requires at least ten validation piles per class per fold. Quick
mode reduces this and the training schedule solely for execution checks.

Fine-tuning freezes backbone and its BN statistics for the head stage, then
unfreezes it with separate head/backbone learning rates, AdamW, cosine scheduling,
label smoothing, balanced sampling and CUDA mixed precision. CV compares
background fill and instance/window weighting as well as requested backbones.
Metrics used for model selection are exploratory CV, not an independent test
estimate. No bean from the same source image appears in both train and validation.

The selected backbone's fold models are averaged into a single FP32 ONNX graph;
normalization stays in `infer.py`. The ensemble itself has no unbiased arranged
training-photo accuracy claim. Export checks opset 17, dynamic batch with static
spatial size, Torch/ORT logits within 1e-4 and OpenCV/ORT within 1e-3 using held-out
patches. Details are recorded under `parity` in the run's `metrics.json`. Full runs
must pass these checks too; no INT8 model is exported.

## Submission files

Package `README.md`, this inference-only `requirements.txt`, `infer.py`,
`train.py`, `weights/best.onnx`, `weights/meta.json` and the generated `outputs/`
under `team_XX_day1/`, then ZIP that folder as required by the official rules.
Metadata records class order, input size, normalization, patch parameters, model
version and ensemble details. Keep the model and its matching metadata together.
Exclude quick weights, intermediate fold checkpoints, training data, piles,
virtualenvs and caches from the ZIP. Do not commit datasets, generated images or
weights. No commit or submission archive was created by this task.

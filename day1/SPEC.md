# SPEC (for Codex): Day 1 coffee-bean image classifier

Owner of plan/review: Claude. Implementer: Codex on the GPU server.
Background, data findings and decisions: `docs/problem/day1-bean-image-classification.md` (read it).
Official rules: `day1/INFER_SPEC.md` (copied from organisers, Thai). **When anything conflicts, INFER_SPEC wins.**

## Task

7 classes, lowercase, fixed order: `good, shell, black, husk, broken, parchment, immature`.
- Train: `data/day1/train/<class>/{circle,grid,square}_<class>.jpg`, 21 photos 3072x4096. White paper, 8–9 beans of ONE class per photo, beans not touching.
- Hidden test: 7 photos (one per class), same paper/camera, but beans **piled naturally, touching and partly overlapping**.
- Output one class per image. Scored on accuracy only (15 x correct/7). Runs on judges' **Raspberry Pi 4 (64-bit OS), CPU only**.

## Deliverable layout (everything for submission lives here)

```
day1/team_XX_day1/
  README.md          install + exact command + preprocessing + weights files
  requirements.txt   INFER ONLY, pinned: onnxruntime, numpy, pillow, opencv-python-headless (NO torch)
  infer.py           self-contained: preprocessing, segmentation, patching, ONNX inference, outputs
  train.py           imports preprocessing from infer.py (single source of truth); torch/timm allowed here
  weights/best.onnx  single ONNX graph (may internally average several fold models)
  weights/meta.json  class order, input size, normalisation, patch params, version
  outputs/           result of running infer.py on the 21 train photos (sanity)
```

## infer.py contract (INFER_SPEC sections 1–5)

- `python infer.py --input <dir|file> --weights <path> --out <dir>`; also accept aliases `--weight`, `--output`.
- Weights: load whatever path is given (detect ONNX by content, not extension). If that path does not exist but `best.onnx` exists in the same folder, use it and print a notice to stderr. Otherwise exit non-zero.
- Inputs: `.jpg/.jpeg/.png` case-insensitive, sorted by filename; a single file also works. Apply EXIF orientation (`ImageOps.exif_transpose`) **after** `Image.draft("RGB", (1536, 2048))` fast decode; must work for files without EXIF.
- No randomness, no TTA, no training at inference. Deterministic.
- Outputs: create `<out>/`, `<out>/predictions.csv` (UTF-8, header `filename,class`, basename only, one row per image, no duplicates), and `<out>/<class>/` for all 7 classes (create even if empty); **copy** each input image into its predicted class folder. Never modify input.
- Errors → message on stderr + non-zero exit: missing input/weights, no images, unreadable image (do not skip silently), duplicate basenames, output dir inside input dir, CSV validation failure. Validate CSV after writing.
- Backend: `onnxruntime` (`intra_op_num_threads=4`, `ORT_ENABLE_ALL`, session created once). If `import onnxruntime` fails, fall back to `cv2.dnn.readNetFromONNX` with the same file (export must be cv2.dnn-compatible: opset 17, static spatial size, dynamic batch OK; verify).
- `--assume-one-per-class` flag, **default OFF**: Hungarian assignment of images↔classes on mean log-probs, only when the number of images equals 7. Do not enable by default.
- Optional `--debug` writes overlays of detected beans/patches to `<out>/_debug/` (off by default, not part of graded output).

## Preprocessing (shared by train and infer, in infer.py)

1. Decode at ~1536x2048 (draft). Foreground = LAB distance from a heavily blurred background estimate (handles vignetting) > threshold, morphology, fill holes. Ignore components touching the image border or smaller than a min area.
2. ROI = bbox of foreground (+margin).
3. Two patch sources, both returned:
   a. **instances**: distance-transform + watershed to split touching beans → one crop per bean.
   b. **windows**: sliding windows of ~1.1x median bean size, stride 0.5 window, keep windows with ≥40% foreground. Robust when piles defeat watershed.
4. Each patch: square, centred, background outside the bean mask replaced by a constant (choose white paper colour or black; justify by CV), resized to `S` (start 160). **Do not stretch-fit each bean**: scale is fixed per image from the median bean size so that absolute size stays a feature (broken beans are smaller, husks larger).
5. Image score = mean of per-patch log-softmax (instances and windows weighted; tune weight by CV). Argmax → class.

Acceptance for step 1–3a on train photos: bean count per photo equals the hand count ±1 on all 21 (write `results/day1/segment_counts.csv` and overlays). Hand counts: Claude will fill `day1/hand_counts.csv`; if missing, stop and ask.

## PileSynth (train.py) — the key to bridging arranged train → piled test

- From each train photo extract bean cut-outs with alpha masks (step 1 + 3a; beans don't touch, so this is clean). Also extract a clean paper background by inpainting beans out.
- Generate synthetic single-class piles: 10–30 beans of the image's class, random rotation 0–360°, scale ±10%, flips, positions clustered (2D Gaussian blob), overlap 0–40%, soft drop shadows, paper background from any train photo, global brightness/white-balance jitter ±5%, JPEG re-encode quality 30–95.
- Save piles + instance masks (Day 2 will reuse them for detection/segmentation training): `data/day1/piles/<split>/...` with COCO-style JSON.
- Run the **same** infer.py preprocessing on the synthetic pile images to produce training patches, labelled with the pile's class.

## Training

- Backbones (timm or torchvision, ImageNet weights pre-downloaded by Claude; **no network in your sandbox**): `mobilenetv3_large_100`, `efficientnet_b0`, `mobilenetv3_small_100`. Optional teacher: frozen DINOv2-S/14 + logistic regression.
- Two-stage fine-tune (freeze backbone 5 epochs lr 1e-3 head; then unfreeze, backbone lr 1e-4, head 1e-3, AdamW wd 1e-4, cosine, 30 epochs), CE with label smoothing 0.1, class-balanced sampling, mixed precision on GPU.
- Augment (train only): rotation 0–360, flips, scale ±10%, ColorJitter brightness/contrast 0.15 saturation 0.1 hue ≤0.02, Gaussian blur, JPEG quality 30–95 (**important**: husk/broken/black-circle source files are ~130 KB re-compressed JPEGs while others are ~2.5 MB; the model must not learn compression as a class cue).
- **CV: leave-one-layout-out, 3 folds** (train on cut-outs from 2 layouts, validate on synthetic piles built ONLY from the held-out layout's cut-outs). Never let a source photo's beans appear in both train and val. Report per fold: patch accuracy, **image-level accuracy on ≥70 synthetic val piles (≥10 per class)**, confusion matrix PNG. Also report image-level accuracy on the 21 original arranged photos (held-out fold only).
- Final model: retrain on all 3 layouts, or average the 3 fold models into one ONNX graph — pick by CV and write the reasoning to `results/day1/decision.md`.
- Save `results/day1/<run>/metrics.json` (+ PNGs). Results are committed; weights/data/piles are not.

## Export & checks

- Export ONNX opset 17, input `[N,3,S,S]` float32 with dynamic N; fold ImageNet normalisation into infer.py (not the graph) and record it in `weights/meta.json`.
- Parity: onnxruntime vs torch max abs diff of logits < 1e-4 on 32 patches; cv2.dnn vs onnxruntime < 1e-3.
- Optional INT8 (static, 200 calibration patches): only keep if image-level CV accuracy drops ≤1 point. FP32 is fine because speed is not scored.

## Tests (`day1/tests/`, pytest, CPU)

Empty dir → non-zero; unreadable file → non-zero; uppercase `.JPG`; single-file input; EXIF-rotated copy predicts same class as original; CSV header/rows/uniqueness/basename/class-set; all 7 class folders exist; input untouched; `--weight/--output` aliases; weights path fallback to `best.onnx`; output inside input → non-zero.

## Rules

- Follow AGENTS.md. Do not pip install (ask Claude). Do not commit images, piles, weights.
- GPU runs are done by Claude outside your sandbox: make every script runnable as `--device cpu --quick` for your smoke tests (tiny epochs, few piles) and document the full GPU command in README/PLAN.
- Every number in a summary must point to a file under `results/day1/`.

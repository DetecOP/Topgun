# SPEC: Robusta green-bean defect classifier + MCP server

Owner of plan/review: Claude. Implementer/trainer: Codex on the GPU server.
Background and economics: `docs/research/bean-defect-research.md`.

## Goal

Given a photo of green robusta beans (single beans in hand, sparse beans on a tray, or a full tray), return per-bean defect class, a sample grade, and the estimated money lost. Expose it as an MCP server so an AI agent / dashboard can call it.

## Classes (v1)

`normal`, `black` (full or partial), `sour_brown`, `insect_damage`, `immature_pale`, `broken`, `mold`, `other` (husk, foreign, roasted, unsure).
Keep the list in `ml/bean_classifier/classes.yaml`; it may change after the team labels data.

## Data

- Team photos: `python scripts/fetch_bean_photos.py --out data/beans/raw` (68 photos, Drive manifest in `ml/bean_classifier/drive_manifest.csv`). Exclude `IMG_20261116_160854` (roasted).
- New photos will arrive later as `data/beans/labeled/<class>/*.jpg` (one class per photo). Code must accept both.
- Public pretraining: USK-Coffee (4 classes, 256×256, Roboflow mirror `norak/usk-coffe-qiph1`, BY-NC-SA). Optional, only if it improves group-CV macro-F1.
- All data lives under `data/` (git-ignored). Never commit images or weights.

## Pipeline

1. **Bean segmentation** `ml/bean_classifier/segment.py`
   - Grounding DINO or YOLO-World prompt "coffee bean" for boxes, then SAM2 (small/base) for masks. Fallback: SAM2 automatic mask generator with area filters.
   - Verified by Claude: plain OpenCV Otsu + watershed is NOT acceptable (misses grey beans on stainless steel, over-splits beans).
   - Output: square crops (mask-applied, black background, 224×224, padding 10%) to `data/beans/crops/<source_stem>/<idx>.png` + `crops.csv` (source, idx, bbox, area, mask_area).
   - Write an overlay PNG per source to `data/beans/overlays/` for visual QA.
   - Acceptance: on 5 sparse-tray photos chosen by Claude, ≥90% of visible beans get exactly one crop (count manually from overlay; report numbers).
2. **Fast labeling** `ml/bean_classifier/cluster_label.py`
   - DINOv2-S/14 embeddings of crops → k-means (k≈24) → write an HTML contact sheet per cluster to `data/beans/clusters/`.
   - A `labels.csv` (crop_path,label,source) is created from a small `cluster_map.yaml` that a human fills (cluster id → class), plus per-photo labels for the hand close-up photos.
   - Do NOT invent labels; leave `cluster_map.yaml` with `TODO` and stop for human input if no labels exist.
3. **Train** `ml/bean_classifier/train.py`
   - Split: `StratifiedGroupKFold(n_splits=5)` grouped by source photo. Never mix crops from one photo across train/val.
   - Baseline A: frozen DINOv2-S/14 features + logistic regression.
   - Model B: timm `convnext_tiny.fb_in22k` (or `efficientnetv2_s`) fine-tune, 224px, AdamW, cosine, label smoothing 0.1, class-balanced sampler, aug: RandomResizedCrop(0.7–1), flips, rotation 0–360, ColorJitter (brightness/contrast small, hue ≤0.02 since color IS the signal), blur, JPEG compression. Mixed precision.
   - Edge model C: `mobilenetv3_large_100` or `efficientnet_lite0` at 128–160px, knowledge-distilled from B.
   - Log to TensorBoard under `runs/`; save `ml/bean_classifier/results/<run>/metrics.json` (macro-F1, per-class recall, confusion matrix PNG) — results folder is committed, weights are not.
4. **Export** `ml/bean_classifier/export.py`: ONNX for server; TFLite int8 (representative set = 200 train crops) + `vela --accelerator-config ethos-u55-128` for the board. Report int8 vs fp32 accuracy drop.
5. **Grade + money** `ml/bean_classifier/grading.py`
   - Per sample: defect counts and % by count, grade per a configurable table in `grading.yaml` (start from TAS 5700-2561 placeholders; mark `VERIFY` until checked against the standard).
   - `estimate_loss(defect_ratio, lot_kg, price_thb_per_kg=150, grade_discount=0.20)` → THB lost from removal and downgrade, as in research doc section 2.
6. **MCP server** `ml/bean_classifier/mcp_server.py` using the official `mcp` Python SDK (FastMCP), stdio + optional streamable HTTP.
   - Tools: `classify_beans(image_path|image_base64) -> {beans:[{bbox,class,confidence}], counts, defect_ratio}`; `grade_sample(counts) -> {grade, reasons}`; `estimate_loss(defect_ratio, lot_kg, price_thb_per_kg?) -> {thb_removed, thb_downgrade, total}`.
   - Also a FastAPI `POST /classify` for the web dashboard, sharing the same inference code.
   - README snippet showing `claude mcp add bean-classifier -- python ml/bean_classifier/mcp_server.py`.

## Acceptance / reporting

- Report group-CV macro-F1 for A, B, C, plus per-class recall for `black` and `insect_damage` (most money-relevant).
- Expected: with <150 crops/class, A may beat B; do not claim >90% unless group-CV shows it.
- Every claim in the final summary must point to a file under `ml/bean_classifier/results/`.

## Environment

Python 3.10–3.12 venv at `.venv/`, `ml/bean_classifier/requirements.txt` pinned. Must run headless on Linux with one CUDA GPU; check `nvidia-smi` first and fall back to CPU for tests.

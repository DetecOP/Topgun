# Codex task V1: make synthetic piles look like the real test piles

Claude reviewed `results/day1/pile_samples/*.jpg`. A v0 GPU training run is IN PROGRESS using `data/day1/piles/v0` and `day1/team_XX_day1/weights_v0/`. **Do not touch those two paths, and do not start GPU work.**

## Problems found (from the 14 sample images)

1. **Piles are too sparse.** Beans are scattered with clear gaps and almost never touch. But the test set is "วางกองตามธรรมชาติ ชิดและซ้อนกันบางส่วน" (natural heaps, beans touching and partly overlapping). Cause: placement uses `normal(size/2, sigma>=0.13*size)`, which is much larger than the bean length, and random placement almost never produces contact.
2. **Ghost marks in the background.** Faint grey bean-shaped blobs are left where beans were removed from the paper. The foreground threshold may pick these up as beans, and the model then learns from noise patches.
3. (Minor) The per-channel white-balance jitter gives visibly pink/green paper. Keep it, but cap the per-channel jitter at ±3% and the global brightness at ±5%.

## Changes (train.py; keep the CLI backward compatible)

- **Dense pile mode.** Place the first bean near the centre. Place each following bean at a distance of 0.5–1.0 bean length from a randomly chosen already-placed bean, in a random direction, with real overlap allowed up to 40% (keep the existing occlusion bookkeeping).
  - Mix per split: 70% dense heaps (12–35 beans, often 2 layers deep in the middle), 20% medium, 10% sparse (current behaviour).
  - Expose this as `--pile-mode {mixed,dense,sparse}` with default `mixed`.
- **Clean paper backgrounds.**
  1. Dilate the bean mask by about 0.3 bean length, then `cv2.inpaint(TELEA)`.
  2. Replace the inpainted region with a very blurred estimate of the paper (the same estimate the segmentation uses), so no texture ghosts remain.
  3. Verify by running `segment()` on 20 empty backgrounds. Expect 0 detected beans; write the result to `results/day1/background_check.json`.
- **Validation must also be dense.** Val piles use the same mixed distribution. In addition, report image-level accuracy on dense-only val piles.
- **Pile previews.** Write 14 new samples to `results/day1/pile_samples_v1/` (one train and one val per class, ≤ 800 px).
- **Contact check.** Write `results/day1/pile_stats_v1.json`. For dense piles, report the fraction of beans touching or overlapping another bean (target ≥ 70%) and the mean visible fraction.

## Also fix: requirements for the judges' Pi 4 (64-bit OS; Python version unknown, likely 3.11 on Bookworm or 3.13 on Trixie)

Replace the exact pins with ranges that have aarch64 wheels for Python 3.9–3.13:

```
onnxruntime>=1.17,<2
numpy>=1.24,<3
pillow>=10
opencv-python-headless>=4.8,<5.1
```

infer.py must not use syntax or stdlib features newer than Python 3.9:
- no `X | Y` type unions at runtime without `from __future__ import annotations`
- no `match`
- no `tomllib`

Add a test that runs `python -m py_compile` with `--target-version` semantics, or uses an AST check for 3.9 compatibility.

## Verify (CPU, quick)

1. `--device cpu --quick --stage synth --pile-mode mixed --run v1check` produces the previews and stats above.
2. `pytest day1/tests` still passes.
3. Write a short note under a new PLAN item **D6** and tick it only if all checks pass.

Do not commit.

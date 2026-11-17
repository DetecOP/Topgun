# PLAN.md

ใบส่งงานระหว่าง AI ที่วางแผนกับ AI ที่ลงมือทำ รูปแบบตาม [AGENTS.md](AGENTS.md)

```
- [ ] งาน | ไฟล์ที่แก้ | วิธีเช็กว่าเสร็จ
```

## งานปัจจุบัน: Day 1 classifier 7 คลาส บน Pi 4 (ผู้วางแผน: Claude / ผู้ทำ: Codex บน GPU server)

ต้องอ่านก่อนเริ่ม:
- `day1/SPEC.md`
- `day1/INFER_SPEC.md` (กติกาทางการ ถ้าขัดกับไฟล์อื่นให้ยึดไฟล์นี้)
- `docs/problem/day1-bean-image-classification.md`

ข้อมูลอยู่ที่ `data/day1/train/<class>/*.jpg` (21 ภาพ) ส่วน `.venv` ลง onnx, onnxruntime, timm และ torchvision ไว้แล้ว และมี ImageNet weights อยู่ใน cache แล้ว
sandbox ของคุณไม่มี GPU และไม่มีเน็ต ให้ทดสอบด้วย `--device cpu --quick` ส่วนการรันเต็มบน GPU Claude จะรันเอง

- [x] D1. preprocessing + segmentation ใน infer.py | `day1/team_XX_day1/infer.py`, `day1/tools/segment_check.py` | ใน `results/day1/segment_counts.csv` จำนวนเมล็ดตรงกับ `day1/hand_counts.csv` ±1 ครบทั้ง 21 ภาพ และมี overlay ใน `data/day1/overlays/`
  - Verified with `.venv/bin/python day1/tools/segment_check.py --device cpu --quick`; evidence: `results/day1/segment_counts.csv`, `results/day1/segment_verification.json`, and `data/day1/overlays/`.
- [x] D2. PileSynth + COCO masks | `day1/team_XX_day1/train.py` (หรือ `day1/pilesynth.py` ถ้าแยกไฟล์ แต่ไฟล์ส่งงานต้องรันได้เอง) | `--quick` สร้างกองจำลองครบ 7 คลาส มีภาพตัวอย่าง 14 ภาพใน `results/day1/pile_samples/` (commit ได้เพราะเล็ก ต้องย่อเหลือ ≤ 800 px)
  - Verified with `.venv/bin/python day1/team_XX_day1/train.py --device cpu --quick --stage synth`; `results/day1/pile_verification.json` records samples, COCO RLE round-trips, dimensions and split provenance.
- [x] D3. train + CV แบบ leave-one-layout-out + export ONNX | `day1/team_XX_day1/train.py` | `--device cpu --quick` จบโดยไม่ error, มี `results/day1/quick/metrics.json`, ไฟล์ ONNX ผ่าน parity check และเขียนคำสั่ง GPU แบบเต็มไว้ใต้ข้อนี้
  - Verified: `.venv/bin/python day1/team_XX_day1/train.py --device cpu --quick` completed; `results/day1/quick/metrics.json` includes Torch/ORT and OpenCV/ORT parity. Quick weights are isolated in `day1/team_XX_day1/weights/quick/`; these are not submission weights.
  - Claude GPU: `.venv/bin/python day1/team_XX_day1/train.py --device cuda --run cv --backbones mobilenetv3_large_100 efficientnet_b0 mobilenetv3_small_100 --head-epochs 5 --finetune-epochs 30 --train-piles-per-class 20 --val-piles-per-class 10 --batch-size 32`
- [x] D4. infer.py ครบตามสเปก + tests | `day1/team_XX_day1/infer.py`, `day1/tests/` | `pytest day1/tests` ผ่าน (ถ้า pytest ค้างใน sandbox ให้จดไว้ แล้ว Claude จะรันเอง)
  - Verified: `.venv/bin/python -m pytest day1/tests -q --junitxml=results/day1/pytest.xml` passed. Parent pytest configuration produced warnings only; no hang.
- [ ] D5. README + requirements (เฉพาะ infer) | `day1/team_XX_day1/README.md`, `day1/team_XX_day1/requirements.txt`, `requirements.txt` | สร้าง venv ใหม่ที่ลงแค่ requirements แล้วรันคำสั่งมาตรฐานผ่าน (Claude ทดสอบบน Pi)

  - README and inference-only requirements written; D6 replaces the original pins with the requested Python-compatible ranges. Verification pending: sandbox has no network, installation is prohibited by `day1/SPEC.md`, and no Pi is available. Claude must create a fresh Pi venv, install the submission requirements, and run the standard command using full GPU weights. Aarch64 installation is not verified.
  - 2026-11-17 (Claude): judges confirmed Pi OS **32-bit** + Python 3.13.5. onnxruntime has no armv7l wheel, so requirements now pin piwheels versions (numpy 2.5.4, pillow 13.0.0, opencv-python-headless 5.0.0.93) and inference uses cv2.dnn (identical predictions to ORT on all 21 photos; also tested with OpenCV 4.10/numpy 2.2). Fresh-venv x86 test passes for v0.1/v1/v2 (`day1/tools/clean_venv_test.sh`). Still unverified on a real 32-bit Pi.

- [x] D6. V1 dense piles, clean paper, dense-only validation and Pi compatibility | `day1/team_XX_day1/train.py`, `day1/team_XX_day1/infer.py`, `day1/team_XX_day1/requirements.txt`, `day1/team_XX_day1/README.md`, `day1/tests/test_infer.py`, `day1/tests/test_synth.py`, `data/day1/piles/v1check/`, `results/day1/background_check.json`, `results/day1/pile_samples_v1/`, `results/day1/pile_stats_v1.json`, `results/day1/pile_verification_v1.json`, `results/day1/v1check/` | `.venv/bin/python day1/team_XX_day1/train.py --device cpu --quick --stage synth --pile-mode mixed --run v1check` and `.venv/bin/python -m pytest day1/tests -q --junitxml=results/day1/v1check/pytest.xml`; clean backgrounds detect no beans and dense contact fraction >= 70%.
  - Both commands passed with CUDA hidden and CPU threads limited. `results/day1/background_check.json`: 20 empty papers plus JPEG crop checks detected zero beans. `results/day1/pile_stats_v1.json`: dense contact 100%, mean visible fraction 86.94%; both splits use rounded mixed allocation. `results/day1/pile_verification_v1.json`: 14 previews, source-disjoint COCO and RLE round-trips passed; previews visually reviewed in `results/day1/v1check/*_contact_sheet.jpg`.
  - `results/day1/v1check/pytest.xml`: 34 tests passed, including Python 3.9 AST compatibility, dense mask/contact bounds and dense-only validation metric wiring. Three non-failing warnings came from parent pytest configuration/cache permissions. This synth-only check does not measure trained-model accuracy; full training now writes dense-only held-out metrics. Pi installation remains D5. No GPU work, no access to active v0 data/weights, and no commit.

## ข้อห้าม

- ห้าม commit รูป, กองจำลอง, crop, weights
- ห้ามรายงาน accuracy จาก split ที่เอาเมล็ดจากภาพเดียวกันไปไว้ทั้งฝั่ง train และ val
- ห้ามเปิด `--assume-one-per-class` เป็นค่าเริ่มต้น

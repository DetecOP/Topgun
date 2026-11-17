# Day 1: Coffee bean image classification (7 classes)

One class per image: `good, shell, black, husk, broken, parchment, immature`.
Target: Raspberry Pi 4, **Raspberry Pi OS 32-bit (armhf)**, Python 3.13.5, CPU only.
The ONNX model runs with **OpenCV DNN** (`cv2.dnn`). Neither PyTorch nor onnxruntime is needed: onnxruntime has no wheel for 32-bit ARM.
If onnxruntime happens to be installed, `infer.py` uses it; otherwise it uses OpenCV DNN. Both give identical predictions.

## 1. Install (ติดตั้ง)

```sh
cd team_XX_day1
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` (inference only) pins `numpy==2.5.4`, `pillow==13.0.0` and `opencv-python-headless==5.0.0.93`.
It adds `--extra-index-url https://www.piwheels.org/simple`, so pip downloads prebuilt armv7l wheels for Python 3.13 from piwheels. Nothing is compiled.

If `import numpy` or `import cv2` reports a missing `.so` file (usually only on Lite images), install the runtime libraries:

```sh
sudo apt install -y libopenblas0-pthread libgfortran5
```

Alternative without pip: use Debian's packages and the system Python. This was tested with the Trixie versions OpenCV 4.10, NumPy 2.2 and Pillow 11.

```sh
sudo apt install -y python3-opencv python3-numpy python3-pil
python3 infer.py --input test/ --weights weights/best.pt --out outputs/
```

## 2. Run (คำสั่งรัน)

```sh
python infer.py --input test/ --weights weights/best.onnx --out outputs/
```

The official command also works unchanged:

```sh
python infer.py --input test/ --weights weights/best.pt --out outputs/
```

Our model file is ONNX (`weights/best.onnx`). If the path given to `--weights` does not exist,
`infer.py` uses `best.onnx` from the same folder and prints a notice on stderr.
The aliases `--weight` and `--output` are also accepted.

Output (`outputs/`):
- `predictions.csv`: UTF-8, header `filename,class`, one row per image, sorted by filename.
- `good/ shell/ black/ husk/ broken/ parchment/ immature/`: each input image is **copied** into its predicted class folder. Input files are not changed.

Exit code is 0 on success. It is non-zero with a message on stderr if the input or weights are missing, there are no images, an image cannot be read, or the CSV fails validation. No image is skipped silently.

## 3. Weights files (ไฟล์ประกอบ weights)

| File | Content |
|---|---|
| `weights/best.onnx` | One ONNX graph (opset 17, input `[N,3,160,160]` float32, output `[N,7]` logits). It averages the logits of 6 models: 3 MobileNetV3-Large and 3 EfficientNet-B0, one of each per cross-validation fold. |
| `weights/meta.json` | Class order, input size, normalisation mean/std and segmentation/patch parameters. **Required** and must stay next to `best.onnx`. |

## 4. Preprocessing (fixed, deterministic; no TTA and no random augmentation)

1. Decode the JPEG at about 1536x2048 (`Image.draft`), then apply EXIF orientation (`ImageOps.exif_transpose`).
2. Find the beans (foreground): LAB colour distance from a heavily blurred paper-background estimate, then morphology and hole filling. Small specks and objects touching the image border are removed.
3. Make two kinds of patches:
   - **Instances:** split touching beans with a distance transform and watershed, then take one square crop per bean.
   - **Windows:** sliding windows about 1.1x the median bean size, stride 0.5, keeping windows that are at least 40% bean.

   One scale per image is set from the median bean size, so bean size stays a usable feature. The area outside the bean mask is filled with a constant colour. Patches are resized to 160x160, converted to RGB float32 and normalised with ImageNet mean/std (values in `meta.json`).
4. Score the image: the model gives a log-softmax for each patch. Average them within instances and within windows, then combine the two averages with weight `instance_weight` from `meta.json`. The class with the highest score is the image's class.

The `--assume-one-per-class` option (Hungarian assignment when there are exactly 7 images) is **off by default** and is not used in the standard command.

## 5. Training (`train.py`; not needed for inference)

- 21 training photos (7 classes x 3 layouts). Bean cut-outs are extracted with the same segmentation as `infer.py`.
- **PileSynth:** builds synthetic single-class piles with dense, touching and partly overlapping beans on a clean paper background. It adds shadows, colour/brightness jitter and JPEG re-compression at quality 30–95. This matches the natural piles in the test set.
- Models: torchvision MobileNetV3-Large and EfficientNet-B0 with ImageNet weights. Two-stage fine-tuning (head 3 epochs, then the full network 12 epochs), AdamW, cosine schedule, label smoothing 0.1, class-balanced sampling.
- Validation: leave-one-layout-out, 3 folds. The validation piles are built only from the held-out layout's beans.
- Held-out accuracy on dense synthetic piles: MobileNetV3-L 86.2%, EfficientNet-B0 85.7%, and 88.1% for the two averaged (210 piles).
- Final model: the 6 fold models (2 backbones x 3 folds) are exported as one averaged ONNX graph. `background=0` and `instance_weight=0.5` were chosen on the dense held-out piles.

```sh
python train.py --device cuda --run v1 --pile-mode mixed --backbones mobilenetv3_large_100 \
  --head-epochs 3 --finetune-epochs 12 --train-piles-per-class 20 --val-piles-per-class 10 --weights weights_v1
python train.py --device cuda --run v1e --pile-mode mixed --backbones efficientnet_b0 \
  --head-epochs 3 --finetune-epochs 12 --train-piles-per-class 20 --val-piles-per-class 10 --weights weights_v1e
```
- Training needs torch, torchvision and onnx (not listed in `requirements.txt`, which is for inference only).

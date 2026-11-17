#!/usr/bin/env bash
# Usage: clean_venv_test.sh <weights_dir> <label>
# Builds dist/<label>/team_XX_day1 with the given weights, installs ONLY requirements.txt
# into a fresh venv, runs the official command on the 21 train photos, validates output.
set -euo pipefail
REPO=~/Documents/Codex/2026-11-14/ro/outputs/sensor-mcp/Topgun-day1
WDIR=$1
LABEL=$2
SRC=$REPO/day1/team_XX_day1
DIST=$REPO/dist/$LABEL
PKG=$DIST/team_XX_day1
rm -rf "$DIST"
mkdir -p "$PKG/weights"
cp "$SRC/infer.py" "$SRC/train.py" "$SRC/requirements.txt" "$PKG/"
cp "$REPO/day1/dist_README.md" "$PKG/README.md"
cp "$WDIR/best.onnx" "$WDIR/meta.json" "$PKG/weights/"

# flat test dir (judges' layout: test/<image>)
TEST=$DIST/test
mkdir -p "$TEST"
cp "$REPO"/data/day1/train/*/*.jpg "$TEST/"

VENV=$DIST/venv
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -r "$PKG/requirements.txt"
"$VENV/bin/python" -m pip freeze > "$DIST/pip_freeze.txt"
cat "$DIST/pip_freeze.txt"

cd "$PKG"
START=$(date +%s.%N)
"$VENV/bin/python" infer.py --input "$TEST" --weights weights/best.pt --out outputs/
echo "exit=$?"
END=$(date +%s.%N)
echo "elapsed_s=$(echo "$END - $START" | bc)"

"$VENV/bin/python" - "$PKG/outputs/predictions.csv" <<'EOF'
import csv, sys, collections
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
assert list(rows[0].keys()) == ["filename", "class"], rows[0].keys()
ok = 0
conf = collections.Counter()
for r in rows:
    truth = r["filename"].rsplit(".", 1)[0].split("_", 1)[1]
    ok += truth == r["class"]
    if truth != r["class"]:
        conf[(truth, r["class"])] += 1
print(f"rows={len(rows)} correct={ok}/{len(rows)} errors={dict(conf)}")
EOF
ls "$PKG/outputs"
# cv2.dnn fallback check: hide onnxruntime
"$VENV/bin/python" -m pip uninstall -y -q onnxruntime
"$VENV/bin/python" infer.py --input "$TEST" --weights weights/best.onnx --out "$DIST/outputs_cv2dnn/"
diff <(sort "$PKG/outputs/predictions.csv") <(sort "$DIST/outputs_cv2dnn/predictions.csv") && echo "CV2DNN_SAME"
"$VENV/bin/python" -m pip install -q -r "$PKG/requirements.txt"

cd "$DIST"
rm -rf "$PKG/__pycache__"
zip -qr "team_XX_day1.zip" team_XX_day1
ls -la "$DIST"
unzip -l team_XX_day1.zip
echo CLEAN_DONE

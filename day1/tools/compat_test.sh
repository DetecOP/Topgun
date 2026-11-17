#!/usr/bin/env bash
# Usage: compat_test.sh <name> <pip specs...>   -- runs v0 package in a fresh venv with given packages (no onnxruntime)
set -uo pipefail
REPO=~/Documents/Codex/2026-11-14/ro/outputs/sensor-mcp/Topgun-day1
NAME=$1; shift
D=$REPO/dist/compat_$NAME
rm -rf "$D"; mkdir -p "$D"
python3 -m venv "$D/venv"
"$D/venv/bin/python" -m pip install -q --upgrade pip
"$D/venv/bin/python" -m pip install -q "$@" || { echo "INSTALL_FAIL $NAME"; exit 1; }
"$D/venv/bin/python" -m pip freeze | tr '\n' ' '; echo
cp -r "$REPO/dist/v0/team_XX_day1" "$D/pkg"
cp "$REPO/day1/team_XX_day1/infer.py" "$D/pkg/infer.py"   # latest infer.py (aggregate fallback)
rm -rf "$D/pkg/outputs"
cd "$D/pkg"
S=$(date +%s)
"$D/venv/bin/python" infer.py --input "$REPO/dist/v0/test" --weights weights/best.pt --out "$D/out"
echo "exit=$? secs=$(( $(date +%s) - S ))"
diff <(sort "$REPO/dist/v0/team_XX_day1/outputs/predictions.csv") <(sort "$D/out/predictions.csv") && echo "SAME_AS_ORT_$NAME"

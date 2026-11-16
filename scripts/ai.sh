#!/usr/bin/env bash
# ใช้ AI สองตัวร่วมกัน: ตัวหนึ่งวางแผนลง PLAN.md อีกตัวลงมือทำ
# ใช้: scripts/ai.sh <mode> "งานที่ต้องการ"
#   cc     = Claude คิด → Codex ทำ → Claude รีวิว
#   xc     = Codex คิด → Claude ทำ → Codex รีวิว
#   claude = Claude ทำคนเดียว (interactive)
#   codex  = Codex ทำคนเดียว (interactive)
#   review = ให้ทั้งสองตัวรีวิว git diff
# รันจาก root ของ repo (Windows ใช้ Git Bash)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

MODE=${1:-}; shift || true
TASK="$*"

plan_claude() { claude -p "อ่าน AGENTS.md แล้ววางแผนงานนี้ลง PLAN.md เป็น checklist ตามรูปแบบที่กำหนด ห้ามแก้ไฟล์อื่น: $TASK" --allowedTools "Read,Grep,Glob,Edit(PLAN.md),Write(PLAN.md)"; }
plan_codex()  { codex exec -s workspace-write "อ่าน AGENTS.md แล้ววางแผนงานนี้ลง PLAN.md เป็น checklist ตามรูปแบบที่กำหนด ห้ามแก้ไฟล์อื่น: $TASK"; }
do_codex()    { codex exec -s workspace-write "อ่าน AGENTS.md และ PLAN.md แล้วทำข้อที่ยังไม่ติ๊กทีละข้อ ติ๊ก [x] เมื่อผ่านขั้น verify แล้วเท่านั้น"; }
do_claude()   { claude -p "อ่าน AGENTS.md และ PLAN.md แล้วทำข้อที่ยังไม่ติ๊กทีละข้อ ติ๊ก [x] เมื่อผ่านขั้น verify แล้วเท่านั้น" --permission-mode acceptEdits; }
review_claude() { claude -p "รีวิว git diff เทียบกับ PLAN.md สรุปสิ่งที่ผิด ขาด หรือเสี่ยง ห้ามแก้ไฟล์" --allowedTools "Read,Grep,Glob,Bash(git diff:*),Bash(git status:*)"; }
review_codex()  { codex exec -s read-only "รีวิว git diff เทียบกับ PLAN.md สรุปสิ่งที่ผิด ขาด หรือเสี่ยง ห้ามแก้ไฟล์"; }

need_task() { [ -n "$TASK" ] || { echo "ใส่งานด้วย เช่น: scripts/ai.sh $MODE \"ทำ FastAPI รับ MQTT\""; exit 1; }; }

case "$MODE" in
  cc)     need_task; plan_claude; do_codex;  review_claude ;;
  xc)     need_task; plan_codex;  do_claude; review_codex ;;
  claude) claude ${TASK:+"$TASK"} ;;
  codex)  codex ${TASK:+"$TASK"} ;;
  review) review_claude; review_codex ;;
  *) sed -n '2,9p' "$0"; exit 1 ;;
esac

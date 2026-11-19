# A/B ในตลาดฝึก (:8000 เท่านั้น) · รันชุดละ N เกมสลับกันเป็นรอบๆ (ลดผลจากตลาดเปลี่ยนตามเวลา)
P="C:/Users/guttj/Documents/TGR2026/starter/Coffee-TESA-starter/.venv/Scripts/python.exe"
cd "$(dirname "$0")/../data/sandbox_agent"
N=${N:-40}
for rep in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
 for cfg in "cur|" "noinfo_off|NOINFO_SURE=0" "sc05|SHORT_CEIL=1 SHORT_FILL=0.5"; do
  name=${cfg%%|*}; extra=${cfg#*|}
  echo "== rep $rep $name ($extra) $(date +%H:%M)"
  env -u AGENT_ENV $extra AGENT_TAG=$name MARKET_URL=http://161.246.199.191:8000 USE_LLM=0 FREEZE_LEARNED=1 SANDBOX_FAST=1 LOG_PER_RUN=1 MAX_GAMES=$N PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$P" main.py --forever > /dev/null 2>&1
 done
done

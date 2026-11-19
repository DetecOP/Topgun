"""LLM ผู้จัด (event-llm ผ่าน gateway เท่านั้น) อ่านข้อเท็จจริงที่ Python ตีความแล้ว → ผลตรวจรายข้อ → ป้าย
สเปก Session B `work/day20/design/llm_behavior_test.md` · ผ่านชุดทดสอบ 19 พ.ย. (prompt v3: T1 10/10 · T2 7/8 ทิศราคา 9/9 ·
T3 20/20 ผิดทิศ 0 · T5 19/20 · p95 0.94 วิ) · ผลการทดสอบ `work/day20/llm_eval/`

LLM_LABEL = off (ค่าเริ่ม) | shadow (บันทึก + พิมพ์อย่างเดียว) | label (ใช้ป้ายของ LLM ทำตามตาราง DAY3 หัวข้อ 6 รอบถัดไป)
- ถามหลังส่งซองของรอบแล้วเสมอ → LLM ช้า/ล่ม ไม่กระทบซองรอบนี้ · ล่ม = ใช้ป้ายของกฎ
- Python คำนวณป้ายจากผลตรวจของ LLM ตามลำดับเอง (LLM เคยตอบผลตรวจถูกแต่เรียงป้ายผิด)
- ตัวกันทิศ: shortage เมื่อเราแพ้ราคารอบล่าสุด → ทิ้ง (ใช้ป้ายของกฎ)
- ไม่เกี่ยวกับ USE_LLM (ตัวปรับราคาแบบเก่าที่เคยผิดทิศ) · ห้ามสลับไป LLM อื่น"""
import os
import threading
import time
from pathlib import Path

ORDER = (("check_flood", "flood"), ("check_undercut", "undercut"), ("check_shortage", "shortage"),
         ("check_festival", "festival_surge"))
LABELS = ["normal", "undercut", "flood", "shortage", "festival_surge"]
SCHEMA = {"type": "object", "required": ["check_flood", "check_undercut", "check_shortage", "check_festival", "label", "reason"],
          "properties": {"check_flood": {"type": "boolean"}, "check_undercut": {"type": "boolean"},
                         "check_shortage": {"type": "boolean"}, "check_festival": {"type": "boolean"},
                         "label": {"type": "string", "enum": LABELS}, "reason": {"type": "string", "maxLength": 120}}}
_CLIENT = None
_LAST = [0.0]
_COOL = [0.0]


def mode() -> str:
    return os.environ.get("LLM_LABEL", "off")


def client():
    """LLM ผู้จัดจาก LLM_BASE_URL/LLM_MODEL/LLM_API_KEY (.env) · temperature 0 · thinking ปิด"""
    global _CLIENT
    if _CLIENT is None:
        from llm import LLM
        _CLIENT = LLM(os.environ["LLM_BASE_URL"], os.environ.get("LLM_MODEL", "event-llm"), os.environ.get("LLM_API_KEY", ""),
                      timeout=float(os.environ.get("LLM_LABEL_TIMEOUT", "15")), thinking=False, max_tokens=200, temperature=0.0)
    return _CLIENT


def system_prompt() -> str:
    return (Path(__file__).with_name("prompts") / "llm_label_v3.txt").read_text(encoding="utf-8")


def ask_labels(rule: dict, budget_s: float = 60.0) -> dict:
    """{type: {"llm": ป้าย LLM, "final": ป้ายที่ใช้, "guard": เหตุที่ทิ้ง/None, "reason", "s"}} · ถามทีละประเภท"""
    import json
    out = {}
    t_end = time.time() + budget_s
    sysp = system_prompt()
    for t, v in rule.items():
        res = {"llm": None, "final": v["label"], "guard": None, "reason": "", "s": None}
        if time.time() < _COOL[0]:              # เพิ่งโดน 429 → พัก 60 วิ ใช้ป้ายของกฎ
            res["guard"] = "พัก rate limit"
            out[t] = res
            continue
        if time.time() > t_end:
            res["guard"] = "หมดเวลา"
            out[t] = res
            continue
        gap = float(os.environ.get("LLM_LABEL_MIN_GAP", "4.0"))   # gateway ≤ 20 คำขอ/นาที/ทีม (คำขอที่โดน 429 ก็นับ)
        wait = _LAST[0] + gap - time.time()
        if wait > 0:
            threading.Event().wait(wait)      # ไม่ใช้ time.sleep (ตลาดจำลองปิด time.sleep เพื่อเร่งเกม → ตัวคุมอัตราเคยไม่ทำงาน)
        t0 = time.time()
        _LAST[0] = t0
        a = client().ask_json(sysp, "Facts (computed by the program):\n" + json.dumps(v["facts"], ensure_ascii=False)
                              + "\nLabel this buyer type.", SCHEMA, timeout=float(os.environ.get("LLM_LABEL_TIMEOUT", "15")))
        res["s"] = round(time.time() - t0, 2)
        if not isinstance(a, dict):
            res["guard"] = "LLM ไม่ตอบ"
            if "429" in str(client().last_error or ""):
                _COOL[0] = time.time() + float(os.environ.get("LLM_LABEL_COOLDOWN", "60"))
        else:
            lab = next((name for key, name in ORDER if a.get(key) is True), "normal")
            res["llm"], res["reason"] = lab, str(a.get("reason", ""))[:120]
            if lab == "shortage" and v["facts"].get("we_lost_outbid_last_round"):
                res["guard"] = "ห้าม shortage เมื่อแพ้ราคารอบล่าสุด"
            else:
                res["final"] = lab
        out[t] = res
    return out

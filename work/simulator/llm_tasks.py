# llm_tasks.py · งานที่ให้ LLM ช่วย (เฉพาะงานภาษา) พร้อมทางสำรองแบบกฎทุกงาน
#
# ที่มา: ผู้ใช้แจ้ง 17 พ.ย. ว่าผู้ซื้อในเกมเป็น AI และตลาดอยู่บน server ผู้จัด
#        ผู้จัดเน้น (16 พ.ย.) "ให้ผู้ซื้อเห็นข้อมูลคุณภาพ พร้อมเหตุผลว่าควรรับหรือขอตรวจซ้ำ"
#
# กฎเหล็ก: LLM ห้ามตัดสินตัวเลข (ราคา มูลค่า) ตัวเลขมาจากโมเดลของเราเท่านั้น
#   - pitch_for_buyer: LLM เขียนข้อความเสนอขาย → ตรวจว่าตัวเลขราคาไม่ถูกเปลี่ยน ถ้าผิดใช้ข้อความแบบกฎ
#   - parse_buyer_request: LLM อ่านความต้องการผู้ซื้อ → ตรวจชนิดและช่วงค่า ถ้าผิดใช้ตัวอ่านแบบกฎ
#
# ⚠️ ยังไม่ทราบ: API ผู้จัดรับข้อความไปกับข้อเสนอได้ไหม และผู้ซื้อส่งความต้องการเป็นข้อความหรือไม่

import json
import re

import config
from llm_client import LLMClient

SYSTEM_SELLER = (
    "You write short, factual sales notes for green robusta coffee lots to an AI buyer. "
    "Use ONLY the facts given. Never invent numbers, never change the price, never promise quality "
    "not in the facts. If data is missing, say it is an estimate and offer re-inspection. "
    "Max 3 sentences. Thai language."
)


def rule_pitch(offer):
    """ข้อความเสนอขายแบบกฎ (ใช้เมื่อ LLM ปิด ล้ม หรือเขียนผิด)"""
    flag = " แนะนำให้ตรวจซ้ำก่อนรับ" if offer.get("recheck") else ""
    return (f"เสนอล็อต {offer['lot_id']} ราคา {offer['price_per_kg']:.2f} บาท/กก. "
            f"({offer.get('reason', '')}){flag}")


def pitch_for_buyer(offer, client=None, force_llm=False):
    """คืน (ข้อความ, แหล่ง) แหล่ง = "llm" หรือ "rule"
    ค่าเริ่มต้นใช้ข้อความแบบกฎ (config.LLM_PITCH_ENABLED = False) · force_llm=True ใช้ตอนทดสอบ"""
    if not (config.LLM_PITCH_ENABLED or force_llm):
        return rule_pitch(offer), "rule"
    client = client or LLMClient()
    facts = {"lot_id": offer["lot_id"], "price_per_kg": offer["price_per_kg"],
             "weight_kg": offer.get("weight"), "facts": offer.get("reason", ""),
             "recommend_reinspection": bool(offer.get("recheck"))}
    text = client.chat([{"role": "system", "content": SYSTEM_SELLER},
                        {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
                       temperature=0.3, max_tokens=200)
    if not text:
        return rule_pitch(offer), "rule"
    if not numbers_are_from_facts(text, facts, must_include=offer["price_per_kg"]):
        return rule_pitch(offer), "rule"                       # LLM แต่งตัวเลขหรือไม่ใส่ราคาเดิม → ไม่ใช้
    return text.strip(), "llm"


def _nums(s):
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(s).replace(",", ""))}


def numbers_are_from_facts(text, facts, must_include=None):
    """ตัวเลขทุกตัวในข้อความของ LLM ต้องมีอยู่ในข้อมูลที่ให้ไป และต้องมีราคาจริงอยู่ด้วย
    (กัน LLM แต่งตัวเลข เช่น เปลี่ยนราคา หรือเอามูลค่ามาเรียกเป็นราคา)"""
    allowed = _nums(json.dumps(facts, ensure_ascii=False))
    found = _nums(text)
    if must_include is not None and float(must_include) not in found:
        return False
    return found <= allowed


# ---------------- อ่านความต้องการของผู้ซื้อ ----------------
SYSTEM_PARSER = (
    "Extract a coffee buyer's requirements from text. Reply ONLY JSON with keys: "
    "max_moisture (number % or null), max_defect (number % or null), "
    "size_pref (one of \"ติดเปลือก\",\"เล็ก\",\"กลาง\",\"ใหญ่\" or null), notes (short string). "
    "Use null when not stated. Do not guess."
)
SIZES = {"ติดเปลือก", "เล็ก", "กลาง", "ใหญ่"}


def rule_parse(text):
    """ตัวอ่านแบบกฎ: หาตัวเลขที่อยู่ใกล้คำว่า ความชื้น/moisture และ เมล็ดเสีย/defect"""
    t = text.lower()

    def near(words):
        for w in words:
            m = re.search(re.escape(w) + r"[^0-9]{0,25}?(\d+(?:\.\d+)?)", t)
            if m:
                return float(m.group(1))
        return None

    size = next((s for s in ("ติดเปลือก", "ใหญ่", "กลาง", "เล็ก") if s in text), None)
    for en, th in (("large", "ใหญ่"), ("medium", "กลาง"), ("small", "เล็ก")):
        if size is None and en in t:
            size = th
    return {"max_moisture": near(["ความชื้น", "moisture"]),
            "max_defect": near(["เมล็ดเสีย", "ตำหนิ", "defect"]),
            "size_pref": size, "notes": ""}


def _valid(d):
    """ตรวจผลจาก LLM: ชนิดถูก และค่าอยู่ในช่วงที่เป็นไปได้"""
    if not isinstance(d, dict):
        return False
    for k, lo, hi in (("max_moisture", 5, 20), ("max_defect", 0, 100)):
        v = d.get(k)
        if v is not None and not (isinstance(v, (int, float)) and lo <= v <= hi):
            return False
    return d.get("size_pref") in SIZES | {None}


def parse_buyer_request(text, client=None):
    """คืน (dict ความต้องการ, แหล่ง) · ถ้า LLM กับกฎขัดกันเรื่องตัวเลข เชื่อกฎ (ตัวเลขมาจากข้อความตรงๆ)"""
    client = client or LLMClient()
    rule = rule_parse(text)
    out = client.chat([{"role": "system", "content": SYSTEM_PARSER},
                       {"role": "user", "content": text}], temperature=0.0, json_mode=True,
                      max_tokens=150)
    try:
        d = json.loads(out) if out else None
    except ValueError:
        d = None
    if not _valid(d):
        return rule, "rule"
    for k in ("max_moisture", "max_defect"):                   # ตัวเลขต้องปรากฏในข้อความจริง ไม่งั้นใช้ของกฎ
        v = d.get(k)
        if v is not None and not re.search(rf"(?<![\d.]){re.escape(str(v).rstrip('0').rstrip('.'))}(?![\d])", text):
            d[k] = rule[k]
    return {k: d.get(k) for k in ("max_moisture", "max_defect", "size_pref", "notes")}, "llm"

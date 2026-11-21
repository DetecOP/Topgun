# llm_client.py · ตัวเชื่อม LLM แบบสลับได้: LLM ของผู้จัด / LLM ในเครื่องเรา (ollama) / ปิด
#
# หลักการ:
# - เรียกผ่านฟังก์ชันเดียว chat() ไม่ว่าจะใช้ LLM ตัวไหน → เปลี่ยนแค่ config.LLM_PROVIDER
# - "ไม่ยอมพัง": ถ้าเรียกไม่สำเร็จ/ช้าเกิน คืนค่า None ให้ฝั่งที่เรียกใช้ทางสำรองแบบกฎ
# - บันทึกทุกคำขอ/คำตอบลง logs/ ผ่าน log_template.py (ซ่อน key อัตโนมัติ)
# - ⚠️ รูปแบบ API ของผู้จัดยังไม่ทราบ รองรับไว้ 2 แบบที่พบบ่อย: "openai" และ "ollama"

import os
import sys
import time

import requests

import config

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # ให้ import log_template จาก work/ ได้
from log_template import log_exchange  # noqa: E402


class LLMClient:
    def __init__(self, provider=None):
        self.provider = provider or config.LLM_PROVIDER
        self.last_error = None                                 # ข้อความ error ล่าสุด (ไว้ดูตอนดีบัก)
        self.last_ms = None                                    # เวลาที่ใช้ล่าสุด (มิลลิวินาที)

    def describe(self):
        """บอกว่าตอนนี้ใช้ LLM ตัวไหน"""
        if self.provider == "organizer":
            return f"LLM ผู้จัด ({config.ORGANIZER_LLM_MODEL or 'ยังไม่กรอกชื่อโมเดล'} @ {config.ORGANIZER_LLM_BASE_URL or 'ยังไม่กรอก URL'})"
        if self.provider == "ollama":
            return f"LLM ในเครื่อง ({config.OLLAMA_MODEL} @ {config.OLLAMA_URL})"
        return "ปิด LLM (ใช้กฎแทน)"

    def _request(self):
        """คืน (url, headers, style, model) ตาม provider หรือ None ถ้ายังตั้งค่าไม่ครบ"""
        if self.provider == "organizer":
            if not config.ORGANIZER_LLM_BASE_URL or not config.ORGANIZER_LLM_MODEL:
                self.last_error = "ยังไม่ได้กรอก ORGANIZER_LLM_BASE_URL / ORGANIZER_LLM_MODEL ใน config.py"
                return None
            style = config.ORGANIZER_LLM_STYLE
            headers = {"Content-Type": "application/json"}
            if config.ORGANIZER_LLM_API_KEY:
                headers["Authorization"] = f"Bearer {config.ORGANIZER_LLM_API_KEY}"   # ← สมมติ รอยืนยันชื่อ header
            base = config.ORGANIZER_LLM_BASE_URL.rstrip("/")
            url = base + ("/chat/completions" if style == "openai" else "/api/chat")
            return url, headers, style, config.ORGANIZER_LLM_MODEL
        if self.provider == "ollama":
            return (config.OLLAMA_URL.rstrip("/") + "/api/chat", {"Content-Type": "application/json"},
                    "ollama", config.OLLAMA_MODEL)
        self.last_error = "LLM ปิดอยู่"
        return None

    def chat(self, messages, temperature=0.2, json_mode=False, max_tokens=300):
        """ส่งข้อความให้ LLM คืนข้อความตอบ (str) หรือ None ถ้าไม่สำเร็จ ไม่โยน error ออกไป"""
        req = self._request()
        if req is None:
            return None
        url, headers, style, model = req
        if style == "openai":
            body = {"model": model, "messages": messages, "temperature": temperature,
                    "max_tokens": max_tokens}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
        else:
            body = {"model": model, "messages": messages, "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens}}
            if json_mode:
                body["format"] = "json"
        start = time.perf_counter()
        try:
            r = requests.post(url, json=body, headers=headers, timeout=config.LLM_TIMEOUT)
            self.last_ms = (time.perf_counter() - start) * 1000
            data = r.json() if r.content else {}
            log_exchange("POST", url, request_body=body, status=r.status_code, response_body=data,
                         headers=headers, note=f"LLM {self.provider} {self.last_ms:.0f} ms")
            if not r.ok:
                self.last_error = f"HTTP {r.status_code}: {str(data)[:200]}"
                return None
            if style == "openai":
                return data["choices"][0]["message"]["content"]
            return data["message"]["content"]
        except Exception as e:                                 # เน็ตหลุด timeout รูปแบบตอบไม่ตรง ฯลฯ
            self.last_ms = (time.perf_counter() - start) * 1000
            self.last_error = f"{type(e).__name__}: {e}"
            log_exchange("POST", url, request_body=body, headers=headers, error=e,
                         note=f"LLM {self.provider} ล้มเหลว")
            return None

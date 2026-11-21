# transcribe.py · ถอดเสียงอบรม (ไฟล์เสียง/วิดีโอ) เป็นข้อความภาษาไทย ในเครื่อง ไม่ส่งขึ้นอินเทอร์เน็ต
#
# รัน (จากโฟลเดอร์ work):
#   asr\.venv\Scripts\python.exe asr\transcribe.py "C:\path\อบรม.m4a"
#   asr\.venv\Scripts\python.exe asr\transcribe.py "C:\path\โฟลเดอร์เสียง"          ← ถอดทุกไฟล์ในโฟลเดอร์
#   เพิ่ม --model turbo|thai|small   --device cpu|cuda|auto
#
# ผลลัพธ์: work/notes/transcripts/<ชื่อไฟล์>.txt (มีเวลา [mm:ss]) และ .srt (เปิดคู่วิดีโอได้)
# รองรับ .m4a .mp3 .wav .mp4 .mov .aac .ogg .webm (ไม่ต้องติดตั้ง ffmpeg)

import argparse
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / "notes" / "transcripts"
MODEL_DIR = HERE / "models"                                    # เก็บโมเดลในเครื่อง (ไม่ commit)
MODELS = {                                                     # ชื่อย่อ → repo บน Hugging Face
    "thai": "Avocaduu14/whisper-th-large-v3-ct2",              # 2.94 GB ฝึกภาษาไทยเพิ่ม
    "turbo": "deepdml/faster-whisper-large-v3-turbo-ct2",      # 1.55 GB หลายภาษา เร็ว
    "small": "Systran/faster-whisper-small",                   # 0.46 GB เล็ก ไทยอ่อน
}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".mp4", ".mov", ".aac", ".ogg", ".webm", ".flac"}
# คำเฉพาะที่น่าจะได้ยินในห้อง ช่วยให้ถอดคำเหล่านี้ถูก
DOMAIN_PROMPT = ("อบรม Track 3 The Next-Gen Market กาแฟโรบัสตา ชุมพร ล็อต ผู้ซื้อ ราคา มูลค่า คะแนน "
                 "ความชื้น เมล็ดเสีย ปิดซอง agent API endpoint token JSON Python LLM starter agent")


def fmt(t, srt=False):
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    if srt:
        return f"{h:02d}:{m:02d}:{s:02d},{int((t % 1) * 1000):03d}"
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def load_model(name, device):
    repo = MODELS.get(name, name)
    order = ["cuda", "cpu"] if device == "auto" else [device]
    last = None
    for dev in order:                                          # ลองการ์ดจอก่อน ไม่ได้ค่อยใช้ CPU
        try:
            compute = "int8_float16" if dev == "cuda" else "int8"
            model = WhisperModel(repo, device=dev, compute_type=compute, download_root=str(MODEL_DIR))
            print(f"ใช้โมเดล {repo} บน {dev} ({compute})")
            return model, dev
        except Exception as e:
            last = e
            print(f"ใช้ {dev} ไม่ได้: {type(e).__name__}: {str(e)[:150]}")
    raise SystemExit(f"โหลดโมเดลไม่ได้: {last}")


def transcribe(model, path, device):
    print(f"\n=== ถอดเสียง: {path.name}")
    start = time.perf_counter()
    try:
        segments, info = model.transcribe(str(path), language=ARGS.lang, beam_size=5, vad_filter=True,
                                          initial_prompt=DOMAIN_PROMPT, condition_on_previous_text=False)
        segments = list(_progress(segments, info.duration))
    except RuntimeError as e:                                  # เช่น การ์ดจอขาดไฟล์ cuBLAS/cuDNN ตอนเริ่มถอด
        if device != "cuda":
            raise
        print(f"การ์ดจอใช้ไม่ได้ระหว่างถอด ({str(e)[:120]}) → เปลี่ยนไปใช้ CPU")
        model, device = load_model(ARGS.model, "cpu")
        return transcribe(model, path, device)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    txt = OUT_DIR / f"{path.stem}.txt"
    srt = OUT_DIR / f"{path.stem}.srt"
    with open(txt, "w", encoding="utf-8") as f:
        f.write(f"# ถอดเสียงอัตโนมัติจาก {path.name} ({fmt(info.duration)}) · ตรวจตัวเลขสำคัญกับเสียงจริงก่อนใช้\n\n")
        for s in segments:
            f.write(f"[{fmt(s.start)}] {s.text.strip()}\n")
    with open(srt, "w", encoding="utf-8") as f:
        for i, s in enumerate(segments, 1):
            f.write(f"{i}\n{fmt(s.start, True)} --> {fmt(s.end, True)}\n{s.text.strip()}\n\n")
    took = time.perf_counter() - start
    print(f"เสร็จ: เสียงยาว {fmt(info.duration)} ใช้เวลา {fmt(took)} → {txt}")
    return model, device


def _progress(segments, total):
    last = -60
    for s in segments:
        if s.end - last >= 60:                                 # รายงานทุก 1 นาทีของเสียง
            print(f"  ...ถึง {fmt(s.end)} / {fmt(total)}")
            last = s.end
        yield s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ถอดเสียงภาษาไทยในเครื่อง")
    ap.add_argument("inputs", nargs="+", help="ไฟล์เสียง/วิดีโอ หรือโฟลเดอร์")
    ap.add_argument("--model", default="turbo", help="thai | turbo | small หรือชื่อ repo")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--lang", default="th", help="ภาษาในเสียง (th, en) · ห้องอบรมพูดไทยปนอังกฤษ ใช้ th")
    ARGS = ap.parse_args()
    files = []
    for p in map(Path, ARGS.inputs):
        files += sorted(f for f in p.iterdir() if f.suffix.lower() in AUDIO_EXT) if p.is_dir() else [p]
    if not files:
        raise SystemExit("ไม่พบไฟล์เสียง")
    model, dev = load_model(ARGS.model, ARGS.device)
    for f in files:
        model, dev = transcribe(model, f, dev)

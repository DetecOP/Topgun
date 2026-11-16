"""ดาวน์โหลดรูปเมล็ดกาแฟจาก Google Drive ของทีม แล้วแปลง HEIC เป็น JPG

ใช้: python scripts/fetch_bean_photos.py [--out data/beans/raw]
ต้องมี: pip install requests pillow pillow-heif
โฟลเดอร์ต้นทาง: https://drive.google.com/drive/folders/1VYZsic3YW1yIgX_zujZHi9xY-a1Iq3Uc (แชร์แบบ anyone-with-link)
"""
import argparse
import csv
import pathlib

import requests
from PIL import Image, ImageOps
import pillow_heif

pillow_heif.register_heif_opener()
MANIFEST = pathlib.Path(__file__).resolve().parents[1] / "ml/bean_classifier/drive_manifest.csv"
URL = "https://drive.google.com/uc?export=download&id={}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/beans/raw")
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(MANIFEST.open(encoding="utf8")))
    for i, r in enumerate(rows, 1):
        dst = out / (pathlib.Path(r["filename"]).stem + ".jpg")
        if dst.exists():
            continue
        resp = requests.get(URL.format(r["file_id"]), timeout=120)
        resp.raise_for_status()
        tmp = out / r["filename"]
        tmp.write_bytes(resp.content)
        im = ImageOps.exif_transpose(Image.open(tmp)).convert("RGB")
        im.save(dst, quality=95)
        if tmp != dst:
            tmp.unlink()
        print(f"[{i}/{len(rows)}] {dst.name} {im.size}", flush=True)


if __name__ == "__main__":
    main()

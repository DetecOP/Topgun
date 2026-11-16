# PLAN.md

ใบส่งงานระหว่าง AI ที่วางแผนกับ AI ที่ลงมือทำ รูปแบบตาม [AGENTS.md](AGENTS.md)

```
- [ ] งาน | ไฟล์ที่แก้ | วิธีเช็กว่าเสร็จ
```

## งานปัจจุบัน: Bean defect classifier (ผู้วางแผน: Claude / ผู้ทำ: Codex บน GPU server)

สเปกเต็มอยู่ที่ `ml/bean_classifier/SPEC.md` ต้องอ่านก่อนเริ่ม ทำตามลำดับ และหยุดรายงานเมื่อติดข้อที่ต้องให้คนตัดสินใจ

- [ ] 1. สร้าง env และเช็ก GPU | `ml/bean_classifier/requirements.txt` | `python -c "import torch;print(torch.cuda.is_available())"` เป็น True และบันทึกผล `nvidia-smi` ลง `ml/bean_classifier/results/env.txt`
- [ ] 2. ดึงรูปจาก Drive | (ใช้ `scripts/fetch_bean_photos.py` ที่มีอยู่) | `data/beans/raw/` มี 68 ไฟล์ .jpg
- [ ] 3. ตัดเมล็ดด้วย Grounding DINO/YOLO-World + SAM2 | `ml/bean_classifier/segment.py` | มี overlay ใน `data/beans/overlays/` และรายงานจำนวน crop ต่อภาพลง `results/segment_report.csv` ตรวจด้วยตาว่า 5 ภาพนี้ได้ ≥90%: `IMG_6270`, `IMG_6266`, `IMG_7603`, `IMG_20261116_162644`, `B5D50519-014F-43D6-BB68-D1F03C648158`
- [ ] 4. จัดกลุ่มเพื่อช่วย label | `ml/bean_classifier/cluster_label.py`, `ml/bean_classifier/cluster_map.yaml` | มี contact sheet HTML ต่อ cluster ใน `data/beans/clusters/` แล้ว **หยุดรอคนกรอก cluster_map.yaml** ห้ามเดา label
- [ ] 5. Baseline A (DINOv2 frozen + LogReg) | `ml/bean_classifier/train.py` | `results/A/metrics.json` มี macro-F1 แบบ StratifiedGroupKFold ตามภาพต้นทาง
- [ ] 6. Model B (ConvNeXt-T fine-tune) และ C (MobileNetV3 distill) | `ml/bean_classifier/train.py` | `results/B/`, `results/C/` มี metrics และ confusion matrix PNG
- [ ] 7. Export ONNX + TFLite int8 + Vela | `ml/bean_classifier/export.py` | รายงานความแม่นยำ int8 เทียบกับ fp32 ใน `results/C/export.json`
- [ ] 8. Grading + ประเมินมูลค่าเสียหาย | `ml/bean_classifier/grading.py`, `ml/bean_classifier/grading.yaml` | `pytest ml/bean_classifier/tests` ผ่าน และตัวอย่างจาก doc ส่วนที่ 2 (ตำหนิ 10%, 1000 กก., 150 บาท) ได้ค่าเสียจากการคัดออก 15,000 บาท
- [ ] 9. MCP server + FastAPI | `ml/bean_classifier/mcp_server.py`, `ml/bean_classifier/api.py` | `claude mcp add bean-classifier -- python ml/bean_classifier/mcp_server.py` แล้วเรียก `classify_beans` กับรูปตัวอย่างได้ผลเป็น JSON

## ข้อห้ามสำหรับงานนี้

- ห้าม commit รูปภาพ, crop, weights และ `.onnx`/`.tflite` เข้า git
- ห้ามรายงานความแม่นยำจาก split ที่ไม่ได้แบ่งตามภาพต้นทาง

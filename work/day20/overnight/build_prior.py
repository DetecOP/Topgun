"""สร้าง appraisal_prior.json ใหม่จากเฉลยตลาดฝึก (reveal) ทั้งเก่า + คืนนี้ แล้ววัดว่าดีกว่าของเดิมไหม

ใช้: python build_prior.py            → รายงานผล + เขียน candidate_prior.json (ไม่แตะ agent)
     python build_prior.py --apply    → ถ้าดีกว่าชัด (> 2 SE แบบจับคู่) จึงคัดลอกทับ agent/appraisal_prior.json (สำรองของเดิมก่อน)

วัดผล: แบ่งเกมเป็น 5 กลุ่ม · ประเมินกลุ่มที่ k ด้วย prior ที่สร้างจากกลุ่มอื่น (ไม่ใช้เฉลยของเกมตัวเอง)
คะแนนประเมินต่อเกม = 20 × (1 − MAPE/10%) ตัดที่ 0 (สไลด์ด่าน 2/3) · เทียบกับ prior เดิม (ไฟล์ที่ agent ใช้อยู่ ตายตัว)
หมายเหตุ: prior เดิมสร้างจากเกมเก่าส่วนใหญ่ในชุดนี้ → ข้อได้เปรียบของ prior เดิมในเกมเก่า (ประเมินแบบเห็นคำตอบ)
          จึงวัดแยก "เฉพาะเกมคืนนี้" ด้วย (ทั้งสอง prior ไม่เคยเห็น) และใช้ผลนั้นตัดสิน
"""
import glob
import json
import math
import shutil
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
AGENT = HERE.parent.parent / "day18" / "agent"
sys.path.insert(0, str(AGENT))
import appraisal  # noqa: E402

RULES = json.loads((HERE / "sandbox_rules.json").read_text(encoding="utf-8"))
OLD_LOGS = [HERE.parent.parent / "day18" / "logs_backup_20261118_pre_competition" / "logs"]
NEW_LOGS = [HERE / "sandbox_agent" / "logs"]
STEP = 0.05


def games(dirs):
    out = []
    for d in dirs:
        for f in sorted(glob.glob(str(d / "runs" / "*.jsonl"))) + [str(d / "decisions.jsonl")]:
            if not Path(f).exists():
                continue
            for line in open(f, encoding="utf-8"):
                if '"reveal"' not in line[:80]:
                    continue
                try:
                    lots = json.loads(line)["data"]["lots"]
                except Exception:
                    continue
                # ใช้เฉพาะตลาดแบบมี noise (ตัวอย่าง ≠ ค่าจริง อย่างน้อย 1 ล็อต) = แบบเดียวกับวันแข่ง
                if any(l["sample"] != l["true"] for l in lots) and all("true_value_per_kg" in l for l in lots):
                    out.append(lots)
    return out


def build(gs, source):
    hd, hm, sp = {}, {}, {}
    derr, merr = [], []
    for lots in gs:
        for l in lots:
            t, s = l["true"], l["sample"]
            kd, km = str(round(t["defect_pct"] / STEP)), str(round(t["moisture_pct"] / STEP))
            hd[kd] = hd.get(kd, 0) + 1
            hm[km] = hm.get(km, 0) + 1
            k = f'{int(s["screen"])}>{int(t["screen"])}'
            sp[k] = sp.get(k, 0) + 1
            derr.append((t["defect_pct"], s["defect_pct"] - t["defect_pct"]))
            merr.append(s["moisture_pct"] - t["moisture_pct"])
    # SD ของ defect = a + b × defect (ถดถอยบน |คลาด| × √(π/2) ซึ่งประมาณ SD ของ normal)
    xs = [d for d, _ in derr if d > 0.05]
    ys = [abs(e) * math.sqrt(math.pi / 2) for d, e in derr if d > 0.05]
    mx, my = st.mean(xs), st.mean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / max(sum((x - mx) ** 2 for x in xs), 1e-9)
    a = my - b * mx
    return {"source": source, "step": STEP,
            "noise": {"sd_defect_a": round(max(a, 0.05), 4), "sd_defect_b": round(max(b, 0.0), 4),
                      "sd_moisture": round(st.pstdev(merr), 4)},
            "defect_hist": hd, "moisture_hist": hm, "screen_pairs": sp}


def use(prior):
    p = dict(prior)
    p["hd"] = {int(k): v for k, v in p["defect_hist"].items()}
    p["hm"] = {int(k): v for k, v in p["moisture_hist"].items()}
    appraisal._PRIOR = p


def game_score(lots):
    errs = [abs(appraisal.estimate_one(RULES, l["sample"], "hybrid") - l["true_value_per_kg"]) / l["true_value_per_kg"]
            for l in lots]
    return max(0.0, 20 * (1 - (sum(errs) / len(errs)) / 0.10))


def main():
    old_g, new_g = games(OLD_LOGS), games(NEW_LOGS)
    allg = old_g + new_g
    cur = json.loads((AGENT / "appraisal_prior.json").read_text(encoding="utf-8"))
    print(f"เกมมี noise: เก่า {len(old_g)} · คืนนี้ {len(new_g)}")
    if len(allg) < 20:
        print("ข้อมูลน้อยเกินไป")
        return
    # ทดสอบ 5 กลุ่ม (สลับเกม) · prior ใหม่ไม่เห็นเกมที่ใช้วัด
    K = 5
    diffs_all, diffs_new = [], []
    new_ids = set(range(len(old_g), len(allg)))
    for k in range(K):
        test = [i for i in range(len(allg)) if i % K == k]
        train = [allg[i] for i in range(len(allg)) if i % K != k]
        cand = build(train, "cv")
        for i in test:
            use(cur)
            s_old = game_score(allg[i])
            use(cand)
            s_new = game_score(allg[i])
            diffs_all.append(s_new - s_old)
            if i in new_ids:
                diffs_new.append(s_new - s_old)

    def rep(name, d):
        if len(d) < 2:
            return f"{name}: เกม {len(d)} (น้อยเกิน)", 0.0, 1.0
        m, se = st.mean(d), st.stdev(d) / math.sqrt(len(d))
        return f"{name}: เกม {len(d)} · ใหม่ − เดิม = {m:+.3f} ± {se:.3f} คะแนน/20", m, se

    line_a, _, _ = rep("ทุกเกม (เดิมได้เปรียบเกมเก่า)", diffs_all)
    line_n, m_n, se_n = rep("เฉพาะเกมคืนนี้ (ยุติธรรม)", diffs_new)
    print(line_a)
    print(line_n)
    full = build(allg, f"ตลาดฝึก reveal {len(allg)} เกม (เก่า {len(old_g)} + คืนนี้ {len(new_g)}) · สร้าง {datetime.now():%Y-%m-%d %H:%M}")
    (HERE / "candidate_prior.json").write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
    print("noise ใหม่:", full["noise"], "· เดิม:", cur["noise"])
    better = len(diffs_new) >= 30 and m_n > 2 * se_n
    print("ตัดสิน:", "ดีกว่าชัด" if better else "ยังไม่ชัด → ไม่เปลี่ยน")
    if better and "--apply" in sys.argv:
        bak = HERE / f"appraisal_prior_backup_{datetime.now():%H%M}.json"
        shutil.copy(AGENT / "appraisal_prior.json", bak)
        shutil.copy(HERE / "candidate_prior.json", AGENT / "appraisal_prior.json")
        print("คัดลอกทับ agent/appraisal_prior.json แล้ว · สำรอง:", bak.name)


if __name__ == "__main__":
    main()

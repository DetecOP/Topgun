# competitors.py · คู่แข่งจำลอง 80+ กลยุทธ์ ไว้วัดผลโมเดลของเรา
#
# ⚠️ ทั้งหมดเป็น "การคาดเดา" ว่าทีมอื่นน่าจะทำแบบไหน ไม่ใช่ข้อมูลจริงของทีมใด
# ที่มาของการคาดเดา (clue จากไฟล์ TGR):
#   [C1] Track 3.pdf หน้า 4: ทุกทีมได้ starter agent ที่เล่นจนจบเกมได้ → ทีมส่วนใหญ่ใช้ starter (แก้นิดหน่อย)
#   [C2] Track 3.pdf หน้า 4: ใช้ LLM ของผู้จัด → หลายทีมให้ LLM ตั้งราคา (ผันผวน ชอบเลขกลม)
#   [C3] Track 3.pdf หน้า 5: วันแรกขายด้วยมือ → ติดนิสัยคน: ลดราคาเมื่อขายไม่ออก, เทขายใกล้หมดเวลา
#   [C4] Track 3.pdf หน้า 6: แนะนำคนถนัด Python 1–2 คน → ทีมที่ทำโมเดลเรียนรู้จริงจังมีน้อย
#   [C5] Track 2.pdf หน้า 2: "Agent ตั้งราคาจากความชื้นและคุณภาพ" → ตั้งราคาตามเกรดล็อต
#   [C6] Track 1.pdf หน้า 5: ปัญหาความชื้น/เชื้อรา → รีบขายล็อตที่ชื้นสูง
#   [C7] Track 3.pdf หน้า 3: "ได้ล็อตไม่ดีก็ชนะได้" → บางทีมเน้นขายให้ออกทุกล็อต
#
# ยังไม่ทราบว่า starter agent ของผู้จัดทำงานอย่างไร จึงสมมติว่า "บวกราคาคงที่จากมูลค่าประเมิน"
#
# ทุก agent มีหน้าที่ 2 อย่าง:
#   decide(lots, buyers, round_no, rounds_left) -> [{"lot_id", "buyer_id", "price_per_kg", "markup"}]
#   feedback(results)  results = [{"offer": ..., "sold": bool}]

import random

from valuation import PlaceholderValuator


class RuleAgent:
    """คู่แข่งแบบใช้กฎ: ตั้ง markup ด้วยฟังก์ชัน policy แล้วคูณกับมูลค่าที่ตัวเองประเมิน"""

    def __init__(self, name, family, policy, presell=True, buyer_mode="best",
                 round_to=None, value_noise=0.0):
        self.name = name                 # ชื่อกลยุทธ์ (ไม่ซ้ำ)
        self.family = family             # กลุ่มพฤติกรรม
        self.policy = policy             # ฟังก์ชัน (agent, ctx) -> markup
        self.presell = presell           # ขายก่อนมีผลวัดไหม
        self.buyer_mode = buyer_mode     # "best" = เลือกผู้ซื้อที่เคยขายได้บ่อย, "fixed" = ผู้ซื้อคนแรกเสมอ, "random"
        self.round_to = round_to         # ปัดราคาเป็นเลขกลม (บาท) แบบที่ LLM/คนชอบทำ
        self.value_noise = value_noise   # ความคลาดเคลื่อนในการประเมินมูลค่า (ทีมที่เข้าใจสูตรไม่ครบ)

    def setup(self, params, seed, n_rounds):
        self.rng = random.Random(seed)
        self.valuator = PlaceholderValuator(params)
        self.n_rounds = n_rounds
        self.mem = {"m": None, "sold": 0, "tried": 0, "last_win_m": None}
        self.lot_fails = {}              # ล็อต → จำนวนครั้งที่ขายไม่ออก
        self.buyer_wins = {}             # ผู้ซื้อ → จำนวนครั้งที่ขายได้
        self.known_values = []           # มูลค่าของล็อตที่วัดแล้ว (ใช้แยกล็อตดี/ไม่ดี)
        self.known_ids = set()
        self.noise = {}                  # ความคลาดเคลื่อนคงที่ต่อล็อต

    def _pick_buyer(self, lot, buyers):
        ok = [b for b in buyers if _eligible(lot, b)]
        if not ok:
            return None
        if self.buyer_mode == "fixed":
            return ok[0]["id"]
        if self.buyer_mode == "random":
            return self.rng.choice(ok)["id"]
        best = max(self.buyer_wins.get(b["id"], 0) for b in ok)
        return self.rng.choice([b for b in ok if self.buyer_wins.get(b["id"], 0) == best])["id"]

    def decide(self, lots, buyers, round_no, rounds_left):
        offers = []
        for lot in lots:
            self.valuator.observe(lot)
        for lot in lots:
            value, is_est = self.valuator.estimate(lot)
            if not is_est and lot["id"] not in self.known_ids:   # จำมูลค่าล็อตที่วัดแล้ว ล็อตละครั้ง
                self.known_ids.add(lot["id"])
                self.known_values.append(value)
            if is_est and not self.presell:
                continue
            noise = self.noise.setdefault(lot["id"], self.rng.gauss(0, self.value_noise))
            value *= (1 + noise)
            ctx = {"lot": lot, "value": value, "is_est": is_est, "r": round_no,
                   "rounds_left": rounds_left, "fails": self.lot_fails.get(lot["id"], 0)}
            m = self.policy(self, ctx)
            buyer = self._pick_buyer(lot, buyers)
            if buyer is None:
                continue
            price = value * (1 + m)
            if self.round_to:
                price = max(self.round_to, round(price / self.round_to) * self.round_to)
            offers.append({"lot_id": lot["id"], "buyer_id": buyer,
                           "price_per_kg": round(price, 2), "markup": m})
        return offers

    def feedback(self, results):
        for res in results:
            o = res["offer"]
            self.mem["tried"] += 1
            if res["sold"]:
                self.mem["sold"] += 1
                self.mem["last_win_m"] = o["markup"]
                self.buyer_wins[o["buyer_id"]] = self.buyer_wins.get(o["buyer_id"], 0) + 1
            else:
                self.lot_fails[o["lot_id"]] = self.lot_fails.get(o["lot_id"], 0) + 1
            if hasattr(self, "on_result"):
                self.on_result(self, o, res["sold"])


def _eligible(lot, buyer):
    if lot.get("moisture") is not None and buyer.get("max_moisture") is not None:
        if lot["moisture"] > buyer["max_moisture"]:
            return False
    if lot.get("defect_pct") is not None and buyer.get("max_defect") is not None:
        if lot["defect_pct"] > buyer["max_defect"]:
            return False
    return True


# ---------------- ฟังก์ชันสร้าง policy ของแต่ละกลุ่ม ----------------

def fixed(m):
    return lambda a, c: m


def per_lot_decay(start, step, floor):
    """[C3] ตั้งสูงก่อน ขายไม่ออกก็ลดทีละขั้น (ต่อล็อต)"""
    return lambda a, c: max(floor, start - step * c["fails"])


def round_decay(start, step, floor):
    """ลดราคาตามรอบเหมือนประมูลแบบดัตช์"""
    return lambda a, c: max(floor, start - step * (c["r"] - 1))


def deadline(hold, dump_left, dump):
    """[C3] ถือราคาสูง แล้วเทขายเมื่อเหลือไม่กี่รอบ"""
    return lambda a, c: dump if c["rounds_left"] <= dump_left else hold


def llm_like(center, spread):
    """[C2] LLM ตั้งราคา: ศูนย์กลางพอสมเหตุผลแต่สุ่มกระจาย"""
    return lambda a, c: center + a.rng.gauss(0, spread)


def quality_aware(good_m, bad_m):
    """[C5] ล็อตดีตั้งแพง ล็อตไม่ดีตั้งถูก (เทียบค่ากลางของล็อตที่วัดแล้ว)"""
    def f(a, c):
        if c["is_est"] or len(a.known_values) < 2:
            return (good_m + bad_m) / 2
        med = sorted(a.known_values)[len(a.known_values) // 2]
        return good_m if c["value"] >= med else bad_m
    return f


def moisture_fear(wet_m, dry_m, limit=12.5):
    """[C6] ล็อตชื้นเกินเกณฑ์ รีบขายถูก"""
    def f(a, c):
        m = c["lot"].get("moisture")
        return wet_m if (m is not None and m > limit) else dry_m
    return f


def random_markup(lo, hi):
    return lambda a, c: a.rng.uniform(lo, hi)


def make_aimd(init, up, down):
    """ขายได้ → ขึ้นราคา, ขายไม่ได้ → ลดราคา (ทั้งทีมใช้ค่าเดียว)"""
    def policy(a, c):
        if a.mem["m"] is None:
            a.mem["m"] = init
        return a.mem["m"]

    def on_result(a, o, sold):
        a.mem["m"] = min(0.5, a.mem["m"] + up) if sold else max(-0.2, a.mem["m"] - down)
    return policy, on_result


def make_target_rate(target, step):
    """พยายามให้อัตราขายได้เท่ากับเป้า"""
    def policy(a, c):
        if a.mem["m"] is None:
            a.mem["m"] = 0.1
        return a.mem["m"]

    def on_result(a, o, sold):
        rate = a.mem["sold"] / max(1, a.mem["tried"])
        a.mem["m"] += step if rate > target else -step
    return policy, on_result


def copy_last_win(start, bump, cut):
    """ใช้ราคาที่เคยขายได้ล่าสุด + เล็กน้อย, ขายไม่ออกก็ลด"""
    def policy(a, c):
        base = a.mem["last_win_m"] if a.mem["last_win_m"] is not None else start
        return base + bump - cut * c["fails"]
    return policy


# ---------------- รายชื่อคู่แข่งทั้งหมด ----------------
# FAMILY_WEIGHT = สัดส่วนทีมที่คาดว่าจะทำแบบนี้ (รวม 100) ใช้สุ่มคู่แข่งเข้าสนาม ← เดาจาก clue
FAMILY_WEIGHT = {
    "starter": 25,      # [C1][C4] ใช้ starter เกือบเหมือนเดิม
    "llm": 18,          # [C2]
    "fixed": 12,        # สูตรง่าย บวกคงที่
    "decay": 8,         # [C3] ลดเมื่อขายไม่ออก
    "aimd": 6,
    "undercut": 5,      # [C7] ขายถูกให้ออกหมด
    "deadline": 5,      # [C3]
    "quality": 5,       # [C5]
    "target": 3,
    "copy": 3,
    "moisture": 3,      # [C6]
    "bandit": 3,        # [C4] ทีมเก่ง ทำโมเดลเรียนรู้
    "random": 2,
    "focus": 1,         # ส่งให้ผู้ซื้อคนเดียวตลอด
    "mirror": 1,        # ทีมเก่งที่คิดแบบเดียวกับเรา (v2)
}


def build_pool():
    """คืน list ของ (ฟังก์ชันสร้าง agent, family) ทั้งหมด"""
    specs = []

    def add(name, family, policy, **kw):
        on_result = kw.pop("on_result", None)

        def make(name=name, family=family, policy=policy, kw=kw, on_result=on_result):
            ag = RuleAgent(name, family, policy, **kw)
            if on_result:
                ag.on_result = on_result
            return ag
        specs.append((name, family, make))

    for m in (0.0, 0.05, 0.10, 0.15):                                  # 8 ตัว
        for pre in (True, False):
            add(f"starter+{int(m*100)}%{'' if pre else '-รอวัด'}", "starter", fixed(m), presell=pre)
    for m in (-0.05, 0.02, 0.08, 0.12, 0.20, 0.30):                      # 12 ตัว
        for pre in (True, False):
            add(f"คงที่{m:+.0%}{'' if pre else '-รอวัด'}", "fixed", fixed(m), presell=pre)
    for m in (-0.15, -0.10, -0.07):                                     # 3 ตัว
        add(f"ตัดราคา{m:+.0%}", "undercut", fixed(m))
    for s in (0.15, 0.25, 0.35):                                        # 12 ตัว
        for st in (0.03, 0.06):
            for fl in (-0.05, 0.0):
                add(f"ลดเมื่อขายไม่ออก{s:.0%}/{st:.0%}/{fl:+.0%}", "decay", per_lot_decay(s, st, fl))
    for s, st in ((0.30, 0.05), (0.20, 0.03)):                          # 2 ตัว
        add(f"ลดตามรอบ{s:.0%}/{st:.0%}", "decay", round_decay(s, st, -0.05))
    for i0 in (0.05, 0.15):                                             # 8 ตัว
        for up in (0.02, 0.05):
            for dn in (0.05, 0.10):
                pol, onr = make_aimd(i0, up, dn)
                add(f"ขึ้นลงตามผล{i0:.0%}/{up:.0%}/{dn:.0%}", "aimd", pol, on_result=onr)
    for t in (0.3, 0.5, 0.7):                                           # 3 ตัว
        pol, onr = make_target_rate(t, 0.03)
        add(f"เป้าขายได้{t:.0%}", "target", pol, on_result=onr)
    for c in (0.05, 0.10, 0.15):                                        # 12 ตัว
        for sp in (0.05, 0.10):
            for rt in (None, 5):
                add(f"LLM{c:.0%}±{sp:.0%}{'-ปัด5บาท' if rt else ''}", "llm", llm_like(c, sp),
                    round_to=rt, value_noise=0.05)
    for g in (0.15, 0.25):                                              # 4 ตัว
        for b in (-0.05, 0.05):
            add(f"ตามเกรด ดี{g:+.0%}/ไม่ดี{b:+.0%}", "quality", quality_aware(g, b))
    for h in (0.20, 0.30):                                              # 8 ตัว
        for dl in (2, 3):
            for d in (-0.05, 0.0):
                add(f"ถือ{h:.0%}แล้วเท{d:+.0%}เมื่อเหลือ{dl}รอบ", "deadline", deadline(h, dl, d))
    add("กลัวชื้น-10%/+12%", "moisture", moisture_fear(-0.10, 0.12))     # 2 ตัว
    add("กลัวชื้น-5%/+8%", "moisture", moisture_fear(-0.05, 0.08))
    for s, b, c in ((0.10, 0.02, 0.03), (0.15, 0.03, 0.05), (0.05, 0.01, 0.02)):  # 3 ตัว
        add(f"ตามราคาที่เคยขายได้{s:.0%}", "copy", copy_last_win(s, b, c))
    add("สุ่ม-10..+35%", "random", random_markup(-0.10, 0.35))           # 2 ตัว
    add("สุ่ม0..+20%", "random", random_markup(0.0, 0.20))
    add("ผู้ซื้อคนเดียว+10%", "focus", fixed(0.10), buyer_mode="fixed")  # 2 ตัว
    add("ผู้ซื้อคนเดียว+20%", "focus", fixed(0.20), buyer_mode="fixed")
    return specs


POOL = build_pool()
assert len({n for n, _, _ in POOL}) == len(POOL), "ชื่อคู่แข่งซ้ำ"

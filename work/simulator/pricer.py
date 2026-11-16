# pricer.py · ส่วน "ตั้งราคาให้พอดี": เรียนจากผลขายแต่ละรอบว่าผู้ซื้อแต่ละคนรับราคาได้แค่ไหน
#
# พื้นฐานจากงานวิจัย (ดู RESEARCH.md):
# - Kleinberg & Leighton (FOCS 2003): ตั้งราคาแล้วรู้แค่ "ขายได้/ไม่ได้" = ปัญหา multi-armed bandit
# - Ferreira, Simchi-Levi & Wang (Operations Research 2018): Thompson sampling สำหรับตั้งราคา
#   เมื่อของมีจำกัดและเวลาจำกัด → ต้องคิดถึง "รอบที่เหลือ" ด้วย ไม่ใช่ดูแค่รอบนี้
#
# หลักการทำงาน:
# 1) มีระดับราคาให้ลองหลายระดับ (config.MARKUP_LEVELS) เทียบกับมูลค่าที่เราประเมิน
# 2) เก็บสถิติแยกผู้ซื้อ ว่าแต่ละระดับขายได้กี่ครั้ง ไม่ได้กี่ครั้ง
#    และใช้เหตุผลว่า "ราคาสูงขายได้ → ราคาต่ำกว่าก็ขายได้" ข้อมูล 1 รอบจึงสอนได้หลายระดับพร้อมกัน
# 3) [v2] ยืมข้อมูลจากผู้ซื้อคนอื่นบางส่วน (pool) เพราะเกมมีไม่กี่รอบ ผู้ซื้อใหม่จะได้ไม่เริ่มจากศูนย์
# 4) [v2] คิดล่วงหน้าหลายรอบ: ถ้ารอบนี้ขายไม่ได้ ยังเหลือกี่รอบให้ลองใหม่ (dynamic programming)
#    เหลือหลายรอบ → กล้าตั้งราคาสูง, ใกล้หมดเวลา → ยอมลดราคาให้ขายออก

import random

import config
from scoring import score_sold, score_unsold


class BuyerPriceLearner:
    def __init__(self, levels=None, seed=config.RANDOM_SEED, explore=True,
                 pool_weight=None, horizon_aware=None, informative_prior=None):
        self.levels = list(levels or config.MARKUP_LEVELS)     # ระดับราคาที่ลอง
        self.rng = random.Random(seed)                         # ตัวสุ่มของตัวเอง ผลจะได้ทำซ้ำได้
        self.explore = explore                                 # False = ใช้ค่าเฉลี่ย ไม่สุ่ม
        self.pool_weight = config.POOL_WEIGHT if pool_weight is None else pool_weight
        self.horizon_aware = config.HORIZON_AWARE if horizon_aware is None else horizon_aware
        self.informative_prior = (config.INFORMATIVE_PRIOR if informative_prior is None
                                  else informative_prior)      # False = เริ่ม 50% ทุกราคา (แบบ v1)
        self.stats = {}                                        # ผู้ซื้อ → [[a, b], ...] ต่อระดับ
        self.pool = [[0.0, 0.0] for _ in self.levels]          # ผลรวมของผู้ซื้อทุกคน (ไม่มีค่าเริ่ม)

    def _prior(self, m):
        """ค่าเริ่มต้น (a, b) ของระดับราคา m"""
        if not self.informative_prior:
            return [1.0, 1.0]                                  # ไม่รู้อะไรเลย = 50%
        p0 = config.PRIOR_ACCEPT_AT_ZERO - config.PRIOR_SLOPE * m
        p0 = min(0.95, max(0.05, p0))                          # กันค่าหลุดช่วง
        s = config.PRIOR_STRENGTH
        return [s * p0, s * (1 - p0)]

    def _get(self, buyer):
        if buyer not in self.stats:                            # ผู้ซื้อใหม่ เริ่มจากความเชื่อตั้งต้น
            self.stats[buyer] = [self._prior(m) for m in self.levels]
        return self.stats[buyer]

    def _ab(self, buyer, i):
        """ค่า (a, b) ของ Beta สำหรับระดับที่ i = ข้อมูลผู้ซื้อคนนี้ + ข้อมูลรวมคูณน้ำหนัก"""
        a, b = self._get(buyer)[i]
        ga, gb = self.pool[i]
        return a + self.pool_weight * ga, b + self.pool_weight * gb

    def _future_value(self, buyer, value_per_kg, weight, mode, rounds_left):
        """มูลค่าที่คาดว่าจะได้ ถ้ารอบนี้ขายไม่ได้แล้วไปลองรอบที่เหลือ (ใช้ค่าเฉลี่ยของความเชื่อ)"""
        v = score_unsold(mode, value_per_kg, weight)           # ถ้าจบเกมแล้วยังขายไม่ได้
        if not self.horizon_aware:                             # แบบ v1: สนใจแค่รอบสุดท้าย
            return v if rounds_left <= 1 else 0.0
        for _ in range(rounds_left - 1):                       # ย้อนจากรอบสุดท้ายมารอบถัดไป
            best = v
            for i, m in enumerate(self.levels):
                a, b = self._ab(buyer, i)
                p = a / (a + b)
                s = score_sold(mode, value_per_kg * (1 + m), value_per_kg, weight)
                best = max(best, p * s + (1 - p) * v)
            v = best
        return v

    def choose(self, buyer, value_per_kg, weight, mode, rounds_left):
        """เลือกระดับราคา คืน (markup, คะแนนที่คาด, มูลค่าถ้ารอต่อ)"""
        wait_value = self._future_value(buyer, value_per_kg, weight, mode, rounds_left)
        best = None
        for i, m in enumerate(self.levels):
            a, b = self._ab(buyer, i)
            p = self.rng.betavariate(a, b) if self.explore else a / (a + b)   # โอกาสขายได้
            s = score_sold(mode, value_per_kg * (1 + m), value_per_kg, weight)
            expected = p * s + (1 - p) * wait_value
            if best is None or expected > best[1]:
                best = (m, expected)
        return best[0], best[1], wait_value

    def update(self, buyer, markup, sold):
        """เรียนจากผล 1 ข้อเสนอ"""
        for i, m in enumerate(self.levels):
            if sold and m <= markup:                           # ขายได้ที่ราคานี้ → ราคาต่ำกว่าก็ขายได้
                self._get(buyer)[i][0] += 1
                self.pool[i][0] += 1
            if not sold and m >= markup:                       # ขายไม่ได้ → ราคาสูงกว่าก็ขายไม่ได้
                self._get(buyer)[i][1] += 1
                self.pool[i][1] += 1

    def summary(self, buyer):
        """โอกาสขายได้โดยเฉลี่ยของแต่ละระดับ (ไว้ดูว่าโมเดลเรียนรู้อะไรไปแล้ว ใช้กับ Dashboard ได้)"""
        out = {}
        for i, m in enumerate(self.levels):
            a, b = self._ab(buyer, i)
            out[m] = round(a / (a + b), 2)
        return out

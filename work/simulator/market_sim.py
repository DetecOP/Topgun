# market_sim.py · ตลาดจำลองในเครื่อง ไว้ทดสอบกลยุทธ์โดยไม่ต้องใช้ API ของผู้จัด
#
# ⚠️ กติกาของตลาดนี้ "แต่งขึ้นเอง" ทั้งหมด ไม่ใช่กติกาจริง:
# - ล็อตมีค่าจริง (ซ่อนไว้) คิดด้วยสูตรสมมติเดียวกับ valuation
# - ผลวัดของแต่ละล็อตจะเผยตอนรอบสุ่ม 2–5 (จำลองว่าข้อมูลเซ็นเซอร์มาช้า) และผลวัดมีความคลาดเคลื่อน
# - ผู้ซื้อแต่ละคนยอมจ่ายสูงสุด = มูลค่าจริง × ตัวคูณลับ และรับได้รอบละไม่กี่ล็อต
# - มีทีมคู่แข่งเสนอขายให้ผู้ซื้อกลุ่มเดียวกันทุกรอบ
# - ปิดซองแบบผู้ชนะจ่ายตามราคาที่เสนอ: ผู้ซื้อเลือกข้อเสนอที่ "คุ้มสำหรับตัวเอง" ที่สุดก่อน

import random

from valuation import placeholder_value_per_kg

SIZES = ["ติดเปลือก", "เล็ก", "กลาง", "ใหญ่"]


class Market:
    def __init__(self, params, seed, n_lots=6, n_buyers=3, n_competitors=4, n_rounds=8):
        rng = random.Random(seed)
        self.rng = rng
        self.params = params
        self.n_rounds = n_rounds
        self.n_competitors = n_competitors

        self.lots = []                                         # ล็อตของเรา (มีค่าจริงซ่อนไว้)
        for i in range(n_lots):
            true = {"moisture": rng.uniform(10.0, 14.5), "defect_pct": rng.uniform(2, 18),
                    "size": rng.choice(SIZES)}
            measured = {                                       # ผลวัดตัวอย่าง = ค่าจริง + ความคลาดเคลื่อน
                "moisture": round(true["moisture"] + rng.gauss(0, 0.3), 1),
                "defect_pct": round(max(0, true["defect_pct"] + rng.gauss(0, 1.5)), 1),
                "size": true["size"],
            }
            self.lots.append({
                "id": chr(ord("A") + i),
                "weight": rng.choice([50, 80, 100, 120, 150, 200]),
                "true_value": placeholder_value_per_kg(params, **true),
                "measured": measured,
                "reveal_round": rng.randint(2, 5),             # รอบที่ผลวัดมาถึง
                "sold": False,
            })

        self.buyers = []
        for j in range(n_buyers):
            self.buyers.append({
                "id": f"B{j + 1}",
                "max_moisture": rng.choice([None, 13.0, 13.5]),   # เงื่อนไขที่ประกาศ (None = ไม่จำกัด)
                "max_defect": rng.choice([None, 12, 15]),
                "_mult": rng.uniform(0.95, 1.25),               # ลับ: ยอมจ่ายสูงสุดเทียบมูลค่าจริง
                "_capacity": rng.choice([1, 2]),                # ลับ: รับได้กี่ล็อตต่อรอบ
            })

    def visible_lots(self, round_no):
        """ล็อตที่ยังขายไม่ได้ ในมุมมองของเรา (ผลวัดเป็น None ถ้ายังไม่ถึงรอบที่เผย)"""
        out = []
        for lot in self.lots:
            if lot["sold"]:
                continue
            known = round_no >= lot["reveal_round"]
            m = lot["measured"]
            out.append({"id": lot["id"], "weight": lot["weight"],
                        "moisture": m["moisture"] if known else None,
                        "defect_pct": m["defect_pct"] if known else None,
                        "size": m["size"] if known else None})
        return out

    def public_buyers(self):
        """ข้อมูลผู้ซื้อที่เราเห็น (ไม่มีค่าลับ)"""
        return [{k: v for k, v in b.items() if not k.startswith("_")} for b in self.buyers]

    def resolve(self, our_offers):
        """เปิดซองรอบนี้ คืนผลของข้อเสนอเรา [{offer, sold, true_value}]"""
        lot_by_id = {l["id"]: l for l in self.lots}
        bids = {b["id"]: [] for b in self.buyers}

        for o in our_offers:                                   # ข้อเสนอของเรา
            lot = lot_by_id[o["lot_id"]]
            b = next(x for x in self.buyers if x["id"] == o["buyer_id"])
            ok = ((b["max_moisture"] is None or lot["measured"]["moisture"] <= b["max_moisture"]) and
                  (b["max_defect"] is None or lot["measured"]["defect_pct"] <= b["max_defect"]))
            reserve = lot["true_value"] * b["_mult"]
            bids[b["id"]].append({"ours": o, "price": o["price_per_kg"], "reserve": reserve, "ok": ok})

        for _ in range(self.n_competitors):                    # ข้อเสนอคู่แข่ง (สุ่ม)
            b = self.rng.choice(self.buyers)
            their_value = self.rng.uniform(70, 110)
            bids[b["id"]].append({"ours": None, "ok": True,
                                  "price": their_value * (1 + self.rng.uniform(0.0, 0.2)),
                                  "reserve": their_value * b["_mult"]})

        results = []
        for b in self.buyers:
            ok_bids = [x for x in bids[b["id"]] if x["ok"] and x["price"] <= x["reserve"]]
            ok_bids.sort(key=lambda x: x["reserve"] - x["price"], reverse=True)   # คุ้มสำหรับผู้ซื้อสุดก่อน
            winners = {id(x) for x in ok_bids[: b["_capacity"]]}
            for x in bids[b["id"]]:
                if x["ours"] is None:
                    continue
                won = id(x) in winners
                lot = lot_by_id[x["ours"]["lot_id"]]
                if won:
                    lot["sold"] = True
                results.append({"offer": x["ours"], "sold": won, "true_value": lot["true_value"]})
        return results

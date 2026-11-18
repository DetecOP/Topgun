"""Coffee market agent ModEngi v2 (ต่อยอด starter): poll the market, appraise once, send offers every round.

    python main.py              # play until the market closes (ตลาดแข่ง)
    python main.py --forever    # sandbox: keep playing game after game (ตลาดฝึก)

.env: อ่านจากโฟลเดอร์นี้ก่อน ถ้าไม่มี อ่านจาก AGENT_ENV หรือ starter ต้นฉบับ (ไม่ต้องคัดลอก key มาไว้ที่นี่)
เปลี่ยนจาก starter: strategy v2 · LLM เป็นผู้ช่วย (advisor.py) ส่งชุดโมเดลก่อนเสมอ · บันทึก reveal ตอนจบเกมตลาดฝึก ·
จำค่าที่เรียนได้ข้ามเกม (logs/learned.json) · log ละเอียดขึ้น (ที่มาของราคาทุกซอง)
"""
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import advisor
import flags
import playbook
import strategy
from appraisal import appraisal_items, estimate_lots
from llm import LLM
from market import Market, MarketError
from market_model import MarketModel, load_learned, save_learned
from memory import Memory

HERE = Path(__file__).parent
LOGS = HERE / "logs"
STARTER_ENV = Path(r"C:\Users\guttj\Documents\TGR2026\starter\Coffee-TESA-starter\.env")


def load_env(path: Path) -> None:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


LOG_FILE: Path | None = None      # None = logs/decisions.jsonl (ค่าเดิมของ starter)


def set_log_file(per_run: bool, tag: str) -> Path:
    """ตลาดฝึก: เริ่มรันใหม่ = ไฟล์ log ใหม่ใน logs/runs/ · ตลาดแข่ง: logs/decisions.jsonl ไฟล์เดียว
    (pack.py และกรรมการหา logs/decisions.jsonl · รีสตาร์ทกลางเกมต้องต่อไฟล์เดิม)
    memory-*.json และ learned.json อยู่ที่ logs/ เสมอ → รีสตาร์ทแล้วไม่ลืมผลรอบก่อน"""
    global LOG_FILE
    if not per_run:
        LOG_FILE = LOGS / "decisions.jsonl"
        return LOG_FILE
    safe = "".join(c if c.isalnum() or c in "-_+" else "_" for c in tag)[:60]
    base = LOGS / "runs" / f"decisions-{datetime.now():%Y%m%d-%H%M%S}-{safe}"
    path, n = base.with_suffix(".jsonl"), 1
    while path.exists():
        n += 1
        path = Path(f"{base}-{n}.jsonl")
    LOG_FILE = path
    return path


def log(event: str, **data) -> None:
    path = LOG_FILE or LOGS / "decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"time": datetime.now().isoformat(timespec="seconds"), "event": event, **data}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    short = {k: v for k, v in data.items() if k not in ("offers", "notes", "meta", "summary", "data", "tv")}
    print(row["time"][11:], event, json.dumps(short, ensure_ascii=False)[:200], flush=True)


def send_offers(api: Market, offers: list[dict]) -> list[dict]:
    """Send all offers at once; if the batch is rejected, send them one by one and skip the bad ones."""
    try:
        return api.offer_batch(offers)["offers"]
    except MarketError as e:
        log("batch_rejected", error=str(e), allowed=e.allowed)
    sent = []
    for o in offers:
        try:
            sent.append(api.offer(o))
        except MarketError as e:
            log("offer_rejected", offer=o, error=str(e))
    return sent


def make_ctx(rules, info, tv, rid, salt, memory, llm, state, learned, adjust=None, volume=1.0):
    # สุ่มด้วย seed ต่อรอบ (ลับ: salt สุ่มตอนเปิดโปรแกรม) → รอบเดียวกันคิดซ้ำได้ผลเหมือนเดิม แต่คนอื่นเดาไม่ได้
    rng = random.Random(f"{salt}-{rid}")
    return strategy.Context(rules, info["calendar"], tv, rng, memory, llm, state["seconds_left"] or 999,
                            learned=learned, adjust=adjust or {}, volume=volume)


def play(api: Market, llm: LLM | None, forever: bool) -> None:
    info = api.calendar()
    rules = info["rules"]
    total = rules["timeline"]["rounds"]
    memory, tv, acted, game = None, {}, set(), None
    salt = random.SystemRandom().random()
    learned = load_learned(LOGS / "learned.json")
    # ตลาดฝึกแบบเร่ง (PIPELINE 4.10): ใช้เฉพาะเมื่อ /v1/version บอก mode=sandbox · ปิดด้วย SANDBOX_FAST=0
    try:
        version_mode = api.call("GET", "/v1/version").get("mode")
    except Exception:                               # noqa: BLE001
        version_mode = None
    is_sandbox = version_mode == "sandbox"
    fast = is_sandbox and os.environ.get("SANDBOX_FAST", "1") != "0"
    log_path = set_log_file(is_sandbox and os.environ.get("LOG_PER_RUN", "1") != "0", flags.tag())
    print(f"log ของรันนี้: {log_path}", flush=True)
    try:
        max_games = int(os.environ.get("MAX_GAMES", "0"))   # ตลาดฝึก: หยุดเองเมื่อครบจำนวนเกม (0 = ไม่จำกัด)
    except ValueError:
        max_games = 0
    log("start", market_mode=version_mode, sandbox_fast=fast, rounds=total,
        variant=flags.tag(), flags=flags.active(), max_games=max_games)
    print(f"ชุดทดลอง: {flags.tag()} · หยุดเมื่อครบ {max_games or '∞'} เกม", flush=True)
    advanced, results_logged, just_reset = set(), set(), False
    games_done = 0

    def advance(state: dict, key) -> None:
        """กด "ข้ามไปช่วงถัดไป" (ตลาดฝึกเท่านั้น) ครั้งเดียวต่อช่วง"""
        if not fast or state.get("market") != "sandbox" or key in advanced:
            return
        advanced.add(key)
        try:
            api.call("POST", "/v1/sandbox/advance")
            log("sandbox_advance", phase=state["phase"], key=str(key))
        except Exception as e:                      # noqa: BLE001
            log("sandbox_advance_error", error=str(e))

    while True:
        try:
            state = api.state()
        except Exception as e:                      # noqa: BLE001 — never die on a network error
            log("state_error", error=str(e))
            time.sleep(3)
            continue
        if just_reset and state["phase"] == "CLOSED":   # รอให้เกมใหม่เริ่มหลัง reset
            time.sleep(1)
            continue
        just_reset = False
        lots_key = tuple(sorted((l["lot_id"], json.dumps(l["sample"], sort_keys=True)) for l in state["lots"]))
        if (lots_key != game and fast and state.get("market") == "sandbox" and not state.get("appraisal_submitted")
                and state["phase"] not in ("SETUP", "APPRAISAL", "CLOSED")):
            # ตลาดฝึกแบบเร่ง: เปิดมาเจอเกมที่เดินไปแล้ว (พ้นช่วงประเมิน) → เกมนี้ได้คะแนนประเมิน 0 และไม่ครบรอบ
            # ทำให้สถิติเพี้ยน (เจอ 12:33: เข้ากลาง R7) → เริ่มเกมใหม่ทันที (ตลาดแข่งไม่ทำ: fast=False)
            try:
                api.call("POST", "/v1/sandbox/reset")
                log("sandbox_reset_midgame", phase=state["phase"], round=(state.get("round") or {}).get("round_id"))
                game, just_reset = None, True
            except Exception as e:                  # noqa: BLE001
                log("sandbox_reset_error", error=str(e))
            time.sleep(1)
            continue
        if lots_key != game:                        # new game (or sandbox reset): start fresh
            if game is not None:
                info = api.calendar()               # ตลาดฝึก: rules/calendar ของเกมใหม่อาจต่าง
                rules = info["rules"]
                total = rules["timeline"]["rounds"]
            game, acted, tv = lots_key, set(), estimate_lots(rules, state["lots"])
            tag = hashlib.sha1(repr(lots_key).encode()).hexdigest()[:8]
            memory = Memory(LOGS / f"memory-{state['market']}-{tag}.json")
            learned = load_learned(LOGS / "learned.json")
            log("new_game", market=state["market"], lots=len(state["lots"]), tv=tv,
                samples={l["lot_id"]: l["sample"] for l in state["lots"]}, calendar=info["calendar"],
                timeline=rules.get("timeline"), learned=learned, variant=flags.tag(), flags=flags.active(),
                code=flags.CODE_VERSION)
        phase = state["phase"]
        lr = state.get("last_results") or {}
        if lr.get("round_id") and (game, lr["round_id"]) not in results_logged:
            results_logged.add((game, lr["round_id"]))
            log("round_results", round=lr["round_id"], data=lr)     # ผลรอบก่อน: ซองเรา + market_summary ทุก RFQ

        if phase == "APPRAISAL" and not state["appraisal_submitted"]:
            try:
                api.appraise(appraisal_items(rules, state["lots"], tv))
                log("appraisal_sent", tv=tv, mode=os.environ.get("APPRAISAL_MODE", "hybrid"))
                acted.add("played")
                advance(state, ("APPRAISAL", game))
            except MarketError as e:
                log("appraisal_error", error=str(e))

        elif phase == "APPRAISAL":
            advance(state, ("APPRAISAL", game))

        elif phase == "ROUND_OPEN" and not state["paused"] and state["round"]["round_id"] not in acted:
            rid = state["round"]["round_id"]
            acted.update((rid, "played"))
            memory.record_results(state["last_results"])
            log("round_open", round=state["round"], seconds_left=state.get("seconds_left"),
                capacity_left_kg=state.get("capacity_left_kg"), round_capacity_kg=state.get("round_capacity_kg"),
                lots_kg={l["lot_id"]: l["kg_available"] for l in state["lots"]}, rfqs=state["rfqs"])
            if any(o["round_id"] == rid for o in state["my_open_offers"]):
                log("round_already_sent", round=rid, n=len(state["my_open_offers"]))
                advance(state, ("ROUND_OPEN", game, rid))
                continue
            t0 = time.time()
            ctx = make_ctx(rules, info, tv, rid, salt, memory, llm, state, learned)
            try:
                offers, source = strategy.decide(state, ctx)
            except Exception as e:                  # noqa: BLE001 — a bug in strategy must not stop the agent
                log("strategy_crashed", error=repr(e))
                ctx = make_ctx(rules, info, tv, rid, salt, memory, llm, state, learned)
                offers, source = strategy.guard(state, ctx, strategy.fallback_plan(state, ctx)), "fallback"
            sent = send_offers(api, offers) if offers else []
            log("offers_sent", round=rid, source=source, n=len(sent), kg=sum(o["kg"] for o in sent),
                seconds=round(time.time() - t0, 1), meta=getattr(ctx, "meta", {}), offers=offers, notes=ctx.notes)
            final = offers

            # LLM: ถามหลังส่งชุดโมเดลแล้ว · ได้คำตอบที่ผ่านการบีบและต่างจากเดิม → ส่งแทนทั้งชุด (replace_existing)
            # รอบซ้อม (ไม่นับคะแนน): ไม่ถาม LLM · ใช้หยั่งราคาอย่างเดียว ประหยัดโควตา gateway
            if llm is not None and source != "fallback" and not strategy.is_practice(state):
                left = (state["seconds_left"] or 0) - (time.time() - t0)
                cal = playbook.calendar_weights(info["calendar"], total)
                adv = advisor.ask(llm, state, ctx.meta, getattr(ctx, "model_summary", {}), cal, total, left)
                used = False
                if adv["ok"] and (adv["adjust"] or adv["volume"] != 1.0):
                    ctx2 = make_ctx(rules, info, tv, rid, salt, memory, llm, state, learned,
                                    adv["adjust"], adv["volume"])
                    try:
                        offers2, source2 = strategy.decide(state, ctx2)   # ใช้ state เดิม (capacity ก่อนส่ง)
                    except Exception as e:          # noqa: BLE001
                        log("strategy_crashed", error=repr(e), where="llm pass")
                        offers2 = None
                    if offers2 and offers2 != offers:
                        sent2 = send_offers(api, offers2)
                        if sent2:
                            final, used = offers2, True
                            log("offers_replaced", round=rid, source=source2, n=len(sent2),
                                kg=sum(o["kg"] for o in sent2), meta=ctx2.meta, offers=offers2)
                log("llm_call", round=rid, ok=adv["ok"], latency_s=adv["latency_s"], raw_adjust=adv["raw"],
                    clamped_adjust=adv["adjust"], volume=adv["volume"], reason=adv["reason"], used=used,
                    prompt_chars=adv.get("prompt_chars"), dropped=adv.get("dropped"))
            # ratio ที่จำ = ราคา ÷ TV ที่ใช้ตั้งราคา (basis) → หน่วยเดียวกับที่ strategy คิด
            memory.record_sent(rid, final, state, {**tv, **getattr(ctx, "basis", {})})
            advance(state, ("ROUND_OPEN", game, rid))      # งานรอบนี้เสร็จ (รวม LLM) → ข้าม

        elif phase == "CLOSED" and game is not None and "closed" not in acted:
            acted.add("closed")
            played = "played" in acted          # เกมนี้ agent ตัวนี้ได้ประเมิน/ส่งซองจริงไหม
            if played or not forever:
                memory.record_results(state["last_results"])
                snap = MarketModel(memory, learned).learned_snapshot()
                if os.environ.get("FREEZE_LEARNED", "0") != "1":   # ทดลองเทียบชุด: ทุกชุดเริ่มจาก learned.json เดียวกัน
                    save_learned(LOGS / "learned.json", snap)
                log("market_closed", standings=state["standings"], learned=snap, variant=flags.tag())
                if is_sandbox or state.get("market") == "sandbox":
                    try:   # เฉลยตลาดฝึก (ต้องขอก่อน reset): ใช้วัด noise ของตัวอย่าง (analyze_logs.py)
                        log("reveal", data=api.call("GET", "/v1/sandbox/reveal"))
                    except Exception as e:          # noqa: BLE001
                        log("reveal_error", error=str(e))
                games_done += 1
            else:   # เปิดโปรแกรมมาเจอเกมที่ปิดแล้ว (ไม่ได้เล่น) → ไม่นับ ไม่ลง log ผล
                log("skip_closed_game", reason="not played by this run")
            if not forever:
                return
            if fast and state.get("market") == "sandbox":
                try:   # เริ่มเกมใหม่ทันที (reset ก่อนหยุดด้วย รอบหน้าเริ่มเกมใหม่สะอาด)
                    api.call("POST", "/v1/sandbox/reset")
                    log("sandbox_reset")
                    game, just_reset = None, True
                except Exception as e:              # noqa: BLE001
                    log("sandbox_reset_error", error=str(e))
            if max_games and games_done >= max_games:
                log("max_games_reached", games=games_done, variant=flags.tag())
                print(f"ครบ {games_done} เกมแล้ว ({flags.tag()}) · หยุด", flush=True)
                return

        elif phase == "ROUND_OPEN" and state["round"]["round_id"] in acted:
            advance(state, ("ROUND_OPEN", game, state["round"]["round_id"]))

        elif phase not in ("APPRAISAL", "ROUND_OPEN", "CLOSED"):
            advance(state, (phase, game, (state.get("round") or {}).get("round_id")))   # clearing ฯลฯ

        left = state["seconds_left"] or 5
        time.sleep(0.5 if fast else min(5.0, max(0.5, left + 0.2)))


def main() -> None:
    load_env(HERE / ".env")
    if os.environ.get("AGENT_ENV"):
        load_env(Path(os.environ["AGENT_ENV"]))
    load_env(STARTER_ENV)
    if not os.environ.get("MARKET_URL") or not os.environ.get("TEAM_KEY"):
        sys.exit("ไม่พบ MARKET_URL / TEAM_KEY: ใส่ใน .env ของโฟลเดอร์นี้ หรือของ starter")
    api = Market(os.environ["MARKET_URL"], os.environ["TEAM_KEY"])
    llm = None
    if os.environ.get("USE_LLM", "1") == "1":
        llm = LLM(os.environ["LLM_BASE_URL"], os.environ["LLM_MODEL"], os.environ.get("LLM_API_KEY", ""),
                  timeout=float(os.environ.get("LLM_TIMEOUT", "60")), thinking=os.environ.get("LLM_THINKING") == "1",
                  max_tokens=400, temperature=0.2)
    print(f"ตลาด: {os.environ['MARKET_URL']} · LLM: {'เปิด' if llm else 'ปิด'}", flush=True)
    play(api, llm, "--forever" in sys.argv)


if __name__ == "__main__":
    main()

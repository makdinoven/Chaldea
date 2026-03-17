from __future__ import annotations

import asyncio, math, random, statistics, logging, traceback
from collections import defaultdict, deque
from typing import Any, Dict, Tuple, Deque

import os
import aioredis, uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from clients import get_battle_state, post_battle_action
from config import settings
from strategy import Strategy

# ────────────────────────────  logging  ───────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("auto-battle")

# ────────────────────────────  FastAPI  ───────────────────────────
app = FastAPI(title="Auto-Battle AI")
cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

strategy = Strategy()

# ─────────────────────────  in-memory хранилища  ──────────────────
REDIS: aioredis.Redis                                       # клиент Redis
ALLOWED: set[int]           = set()                         # pid, которыми управляем
PID_BATTLE: dict[int, int]  = {}                            # pid → последний battle_id

LAST_STATS: dict[Tuple[int, int], Dict[str, int]] = {}      # (bid,pid) → {hp,…}
HISTORY:    dict[Tuple[int, int], Deque[Dict[str, Any]]] = \
            defaultdict(lambda: deque(maxlen=12))           # dmg / heal / enemy_skill

# ────────────────────────────  pydantic  ─────────────────────────
class ModePayload(BaseModel):
    mode: str                 # attack / defense / balance

class RegisterPayload(BaseModel):
    participant_id: int
    battle_id:     int = 0    # можно 0 — определится по сообщению your_turn

# ─────────────────────────── startup / Redis  ────────────────────
@app.on_event("startup")
async def startup() -> None:
    global REDIS         # pylint: disable=global-statement
    REDIS = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    asyncio.create_task(redis_reader())
    log.info("auto-battle запущен, режим %s", strategy.mode)

async def redis_reader() -> None:
    """
    Слушаем каналы battle:*:your_turn и запускаем ход,
    если участник включён в ALLOWED.
    """
    pub = REDIS.pubsub()
    await pub.psubscribe("battle:*:your_turn")

    async for msg in pub.listen():
        if msg.get("type") != "pmessage":
            continue
        try:
            bid = int(msg["channel"].split(":")[1])
            pid = int(msg["data"])
        except (ValueError, IndexError):
            continue

        PID_BATTLE[pid] = bid
        if pid in ALLOWED:
            asyncio.create_task(handle_turn(bid, pid))

# ─────────────────────────────  REST  ────────────────────────────
@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "mode":   strategy.mode,
        "allowed": list(ALLOWED),
        "redis": await REDIS.ping(),
    }

@app.post("/mode")
def set_mode(p: ModePayload):
    try:
        strategy.set_mode(p.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "mode": strategy.mode}

@app.post("/register")
async def register(p: RegisterPayload):
    ALLOWED.add(p.participant_id)
    if p.battle_id:
        PID_BATTLE[p.participant_id] = p.battle_id

    # если уже наш ход → сразу ходим
    bid = PID_BATTLE.get(p.participant_id)
    if bid:
        ctx = await get_battle_state(bid)
        if ctx["runtime"]["current_actor"] == p.participant_id:
            asyncio.create_task(handle_turn(bid, p.participant_id))
    return {"ok": True, "allowed": list(ALLOWED)}

@app.post("/unregister")
def unregister(participant_id: int = Body(..., embed=True)):
    ALLOWED.discard(participant_id)
    return {"ok": True, "allowed": list(ALLOWED)}

# ──────────────────────────  helpers  ────────────────────────────
def _ratio(cur: int, mx: int) -> float:
    return round(cur / mx if mx else 0.0, 4)

def build_features(ctx: Dict[str, Any], pid: int) -> Dict[str, float]:
    """Формируем расширенный feature-vector для стратегии."""
    rt      = ctx["runtime"];                # runtime
    snap_me = next(s for s in ctx["snapshot"] if s["participant_id"] == pid)
    me_rt   = rt["participants"][str(pid)]

    # поиск врага – берём следующего в порядке ходов
    order         = rt["turn_order"]
    enemy_pid     = order[(order.index(pid) + 1) % len(order)]
    enemy_rt      = rt["participants"][str(enemy_pid)]

    max_hp        = snap_me["attributes"]["max_health"]
    max_mana      = snap_me["attributes"]["max_mana"]
    max_energy    = snap_me["attributes"]["max_energy"]
    max_stamina   = snap_me["attributes"]["max_stamina"]

    feats: Dict[str, float] = {
        # базовые соотношения
        "hp_ratio":      _ratio(me_rt["hp"],      max_hp),
        "mana_ratio":    _ratio(me_rt["mana"],    max_mana),
        "energy_ratio":  _ratio(me_rt["energy"],  max_energy),
        "stamina_ratio": _ratio(me_rt["stamina"], max_stamina),
    }

    # дельты (предыдущее состояние)
    key = (rt["turn_number"], pid)
    prev = LAST_STATS.get(key)
    if prev:
        feats.update({
            "hp_delta":      me_rt["hp"]      - prev["hp"],
            "mana_delta":    me_rt["mana"]    - prev["mana"],
            "energy_delta":  me_rt["energy"]  - prev["energy"],
            "stamina_delta": me_rt["stamina"] - prev["stamina"],
        })
    LAST_STATS[key] = me_rt.copy()           # сохранить текущее для след. раза

    # готовые скиллы
    feats["attack_ready_cnt"]  = sum(1 for cid in me_rt["cooldowns"].values() if cid==0)
    # разбивка по типам
    # проще: пересчитаем позже в стратегии

    # кол-во активных эффектов
    eff_me     = ctx["runtime"]["active_effects"].get(str(pid), [])
    eff_enemy  = ctx["runtime"]["active_effects"].get(str(enemy_pid), [])
    feats["self_buff_cnt"]  = sum(1 for e in eff_me    if e["magnitude"]>0)
    feats["self_debuff_cnt"]= sum(1 for e in eff_me    if e["magnitude"]<0)
    feats["enemy_buff_cnt"] = sum(1 for e in eff_enemy if e["magnitude"]>0)

    # суммарные %-баффы/резисты
    def _sum_pref(lst, pref):
        return sum(e["magnitude"] for e in lst if e["attribute"].startswith(pref))
    feats["buff_attack_pct"]  = _sum_pref(eff_me, "percent_damage")
    feats["buff_resist_pct"]  = _sum_pref(eff_me, "percent_resist")

    # позиция хода
    feats["turn_idx"]   = rt["turn_number"]
    feats["turn_mod_2"] = rt["turn_number"] & 1
    feats["turn_mod_3"] = rt["turn_number"] % 3

    # разница HP
    feats["my_hp_minus_enemy_hp"] = me_rt["hp"] - enemy_rt["hp"]

    # momentum / ДПС за 3 последних хода
    hist = HISTORY[(ctx["runtime"]["turn_number"], pid)]
    dps  = [h["dps"] for h in hist][-3:]
    feats["dps_last3_avg"] = statistics.mean(dps) if dps else 0.0

    # запас банок
    pots_hp = sum(s.get("health_recovery",0)*s["quantity"] for s in me_rt.get("fast_slots",[]))
    pots_mn = sum(s.get("mana_recovery",0)*s["quantity"]   for s in me_rt.get("fast_slots",[]))
    feats["hp_pots_left"]   = pots_hp
    feats["mana_pots_left"] = pots_mn

    # «близость к победе»
    est_dps = max(feats["dps_last3_avg"], 1.0)
    feats["enemy_lethal_in"] = math.ceil(enemy_rt["hp"] / est_dps)

    # шум
    feats["rand_uniform"] = random.random()
    return feats

# ─────────────────────────────  turn  ────────────────────────────
async def handle_turn(bid: int, pid: int) -> None:
    """Один авто-ход."""
    try:
        ctx = await get_battle_state(bid)
        if ctx["runtime"]["current_actor"] != pid:
            return                              # чужой ход

        # ---------- features / history ----------
        feats = build_features(ctx, pid)
        ctx["features"] = feats                # передаём стратегии

        # ---------- стратегия ----------
        skills, item_id = strategy.select_actions(ctx)
        payload = {"participant_id": pid, "skills": skills}
        if item_id:
            payload["skills"]["item_id"] = item_id

        # ---------- POST /action ----------
        res = await post_battle_action(bid, payload)
        log.info("battle=%s turn=%s pid=%s OK", bid, res["turn_number"], pid)

        # ---------- обновляем HISTORY ----------
        dmg = sum(ev.get("final",0) for ev in res["events"] if ev["event"]=="damage" and ev["source"]==pid)
        HISTORY[(bid, pid)].append({"dps": dmg})

    except Exception as exc:                   # pylint: disable=broad-except
        log.error("handle_turn error: %s", exc)
        log.error("TRACE:\n%s", traceback.format_exc())

# ─────────────────────────────  run  ─────────────────────────────
if __name__ == "__main__":                     # pragma: no cover
    uvicorn.run("main:app", host="0.0.0.0", port=8020, reload=False)

from __future__ import annotations

import asyncio, math, random, statistics, logging, traceback
from collections import defaultdict, deque
from typing import Any, Dict, Tuple, Deque

import os
import aioredis, uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth_http import get_current_user_via_http, UserRead
from clients import get_battle_state, get_character_owner, post_battle_action
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
OWNER: dict[int, int]       = {}                            # pid → user_id (кто зарегистрировал)
SPEED: dict[int, str]       = {}                            # pid → "fast" | "slow"

LAST_STATS: dict[Tuple[int, int], Dict[str, int]] = {}      # (bid,pid) → {hp,…}
HISTORY:    dict[Tuple[int, int], Deque[Dict[str, Any]]] = \
            defaultdict(lambda: deque(maxlen=12))           # dmg / heal / enemy_skill

# ────────────────────────────  pydantic  ─────────────────────────
class ModePayload(BaseModel):
    mode: str                 # attack / defense / balance

class SpeedPayload(BaseModel):
    participant_id: int
    speed: str                # "fast" | "slow"

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
def set_mode(p: ModePayload, _user: UserRead = Depends(get_current_user_via_http)):
    try:
        strategy.set_mode(p.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "mode": strategy.mode}

@app.post("/register")
async def register(p: RegisterPayload, user: UserRead = Depends(get_current_user_via_http)):
    # Ownership validation: проверяем, что персонаж принадлежит текущему пользователю
    bid = p.battle_id
    if bid:
        ctx = await get_battle_state(bid)
        pid_str = str(p.participant_id)
        participant_data = ctx.get("runtime", {}).get("participants", {}).get(pid_str)
        if not participant_data:
            raise HTTPException(403, "Участник не найден в этом бою")
        character_id = participant_data.get("character_id")
        if character_id:
            owner_user_id = await get_character_owner(character_id)
            if owner_user_id is None:
                raise HTTPException(404, "Персонаж не найден")
            if owner_user_id != user.id:
                raise HTTPException(403, "Вы не можете управлять чужим персонажем")

    ALLOWED.add(p.participant_id)
    OWNER[p.participant_id] = user.id
    SPEED[p.participant_id] = "fast"
    if p.battle_id:
        PID_BATTLE[p.participant_id] = p.battle_id

    # если уже наш ход → сразу ходим
    bid = PID_BATTLE.get(p.participant_id)
    if bid:
        if not p.battle_id:
            # battle state was not fetched yet — fetch now
            ctx = await get_battle_state(bid)
        if ctx["runtime"]["current_actor"] == p.participant_id:
            asyncio.create_task(handle_turn(bid, p.participant_id))
    return {"ok": True, "allowed": list(ALLOWED)}

@app.post("/internal/register")
async def internal_register(p: RegisterPayload):
    """
    Internal endpoint (no auth) — called by battle-service to register mob AI
    when a PvE battle is created. Not exposed via Nginx.
    """
    ALLOWED.add(p.participant_id)
    if p.battle_id:
        PID_BATTLE[p.participant_id] = p.battle_id

    # если уже наш ход → сразу ходим
    bid = PID_BATTLE.get(p.participant_id)
    if bid:
        ctx = await get_battle_state(bid)
        if ctx["runtime"]["current_actor"] == p.participant_id:
            asyncio.create_task(handle_turn(bid, p.participant_id))
    log.info("internal register pid=%s bid=%s", p.participant_id, p.battle_id)
    return {"ok": True, "allowed": list(ALLOWED)}


@app.post("/unregister")
def unregister(participant_id: int = Body(..., embed=True), user: UserRead = Depends(get_current_user_via_http)):
    # Проверяем, что пользователь сам регистрировал этот pid
    registered_owner = OWNER.get(participant_id)
    if registered_owner is not None and registered_owner != user.id:
        raise HTTPException(403, "Вы не можете отменить автобой чужого персонажа")
    ALLOWED.discard(participant_id)
    OWNER.pop(participant_id, None)
    SPEED.pop(participant_id, None)
    return {"ok": True, "allowed": list(ALLOWED)}


@app.post("/speed")
def set_speed(p: SpeedPayload, user: UserRead = Depends(get_current_user_via_http)):
    if p.speed not in ("fast", "slow"):
        raise HTTPException(400, "Допустимые значения скорости: fast, slow")
    if p.participant_id not in ALLOWED:
        raise HTTPException(404, "Участник не зарегистрирован в автобое")
    registered_owner = OWNER.get(p.participant_id)
    if registered_owner is not None and registered_owner != user.id:
        raise HTTPException(403, "Вы не можете менять скорость чужого автобоя")
    SPEED[p.participant_id] = p.speed
    return {"ok": True, "participant_id": p.participant_id, "speed": p.speed}

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

# ─────────────────────  cleanup on battle finish  ─────────────────
def _cleanup_battle(bid: int) -> None:
    """Удаляем ВСЕ pid, связанные с данным battle_id, из in-memory хранилищ."""
    pids_to_remove = [p for p, b in PID_BATTLE.items() if b == bid]
    for p in pids_to_remove:
        ALLOWED.discard(p)
        PID_BATTLE.pop(p, None)
        OWNER.pop(p, None)
        SPEED.pop(p, None)
    # Чистим LAST_STATS и HISTORY по battle_id
    for key in [k for k in LAST_STATS if k[0] == bid]:
        del LAST_STATS[key]
    for key in [k for k in HISTORY if k[0] == bid]:
        del HISTORY[key]
    log.info("battle=%s finished — cleaned up pids=%s", bid, pids_to_remove)

# ─────────────────────────────  turn  ────────────────────────────
MAX_RETRIES = 3

async def handle_turn(bid: int, pid: int) -> None:
    """Один авто-ход с retry логикой."""
    if SPEED.get(pid) == "slow":
        await asyncio.sleep(settings.AUTOBATTLE_SLOW_DELAY)
    for attempt in range(MAX_RETRIES + 1):
        try:
            ctx = await get_battle_state(bid)
            if ctx["runtime"]["current_actor"] != pid:
                return                              # чужой ход (или уже обработан)

            # ---------- features / history ----------
            feats = build_features(ctx, pid)
            ctx["features"] = feats                # передаём стратегии

            # ---------- стратегия ----------
            skills, item_id = strategy.select_actions(ctx)
            log.info("battle=%s pid=%s strategy chose: skills=%s item=%s", bid, pid, skills, item_id)

            # Debug: log available skills
            snap = next(s for s in ctx["snapshot"] if s["participant_id"] == pid)
            snap_skills = snap.get("skills", [])
            log.info("battle=%s pid=%s snapshot has %d skills: %s",
                     bid, pid, len(snap_skills),
                     [(s.get("id"), s.get("skill_type"), s.get("cost_energy")) for s in snap_skills])

            me_rt = ctx["runtime"]["participants"][str(pid)]
            log.info("battle=%s pid=%s runtime: energy=%s mana=%s cooldowns=%s",
                     bid, pid, me_rt.get("energy"), me_rt.get("mana"), me_rt.get("cooldowns"))

            payload = {"participant_id": pid, "skills": skills}
            if item_id:
                payload["skills"]["item_id"] = item_id

            # ---------- POST /action ----------
            res = await post_battle_action(bid, payload)
            log.info("battle=%s turn=%s pid=%s OK", bid, res["turn_number"], pid)

            # ---------- обновляем HISTORY ----------
            dmg = sum(ev.get("final",0) for ev in res["events"] if ev["event"]=="damage" and ev["source"]==pid)
            HISTORY[(bid, pid)].append({"dps": dmg})

            # ---------- cleanup on battle finish ----------
            if res.get("battle_finished"):
                _cleanup_battle(bid)

            return  # успех — выходим

        except Exception as exc:                   # pylint: disable=broad-except
            log.error("handle_turn error (attempt %d/%d) battle=%s pid=%s: %s",
                      attempt + 1, MAX_RETRIES + 1, bid, pid, exc)
            if attempt < MAX_RETRIES:
                delay = 2 ** (attempt + 1)  # 2s, 4s, 8s
                log.info("battle=%s pid=%s retrying in %ds...", bid, pid, delay)
                await asyncio.sleep(delay)
            else:
                log.error("handle_turn GIVING UP after %d attempts for battle=%s pid=%s",
                          MAX_RETRIES + 1, bid, pid)
                log.error("TRACE:\n%s", traceback.format_exc())

# ─────────────────────────────  run  ─────────────────────────────
if __name__ == "__main__":                     # pragma: no cover
    uvicorn.run("main:app", host="0.0.0.0", port=8020, reload=False)

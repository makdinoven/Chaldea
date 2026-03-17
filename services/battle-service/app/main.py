from datetime import datetime, timedelta, timezone
from os import supports_fd
from typing import List, Dict

from fastapi import FastAPI, Depends, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from crud import create_battle, write_turn, get_logs_for_turn
from schemas import BattleCreated, BattleCreate, ActionResponse, ActionRequest, LogResponse
from mongo_client import get_mongo_db
from database import get_db
from battle_engine import decrement_cooldowns, set_cooldown
from inventory_client import get_fast_slots
from character_client import get_character_profile
from buffs import decrement_durations, aggregate_modifiers, apply_new_effects, build_percent_damage_buffs, \
    build_percent_resist_buffs
from battle_engine import fetch_full_attributes, apply_flat_modifiers, fetch_main_weapon, compute_damage_with_rolls
from redis_state import init_battle_state, load_state, save_state, get_redis_client, ZSET_DEADLINES, cache_snapshot, \
    get_cached_snapshot, KEY_BATTLE_TURNS
from config import settings
from mongo_helpers import save_snapshot, load_snapshot
from tasks import save_log
from skills_client import character_has_rank, get_rank, get_item, character_ranks
import logging
import os
logging.basicConfig(
    level=logging.DEBUG,               # DEBUG, чтобы видеть максимум
    format="%(levelname)s | %(name)s | %(asctime)s | %(message)s",
)
logger = logging.getLogger("battle-service")
app = FastAPI(title="Battle Service")

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/battles", tags=["battles"])

def next_pid_after(cur, order):            # order = [id,id,…]
    idx = order.index(cur)
    return order[(idx + 1) % len(order)]

def _ensure_not_on_cooldown(state: Dict, pid: int, rank_ids: list[int]) -> None:
    """
    Если у участника pid для любого rank_id из списка
    cooldowns[rank_id] > 0  → HTTP 400.
    """
    cd = state["participants"][str(pid)]["cooldowns"]
    for rid in rank_ids:
        if cd.get(str(rid), 0) > 0:
            raise HTTPException(400, f"Rank {rid} is on cooldown")

async def build_participant_info(char_id: int, participant_id: int) -> dict:
    """
    Сбор ВСЕГО, что нужно зафиксировать на старте боя
    (avatar, name, attributes, skills, fast-slots).
    """
    attr   = await fetch_full_attributes(char_id)
    ranks  = await character_ranks (char_id)
    slots  = await get_fast_slots(char_id)
    profile = await get_character_profile(char_id)
    return {
        "participant_id": participant_id,
        "character_id"  : char_id,
        "name"          : profile["character_name"],
        "avatar"        : profile["character_photo"],
        "attributes"    : attr,
        "skills"        : ranks,
        "fast_slots"    : slots,
    }
async def _pay_skill_costs(state: dict, pid: int, ranks: list[dict]) -> dict:
    """
    Проверяет и списывает cost_energy / cost_mana / cost_stamina
    для переданных рангов. Возвращает словарь списанных величин,
    чтобы записать в лог события.
    """
    spend = {"energy": 0, "mana": 0, "stamina": 0}
    for r in ranks:
        spend["energy"]  += r.get("cost_energy",   0)
        spend["mana"]    += r.get("cost_mana",     0)
        spend["stamina"] += r.get("cost_stamina",  0)

    pstate = state["participants"][str(pid)]

    # Проверка «хватает ли»
    for res, value in spend.items():
        if pstate[res] < value:
            raise HTTPException(
                400, f"Not enough {res}: need {value}, have {pstate[res]}"
            )

    # Списываем
    for res, value in spend.items():
        pstate[res] -= value

    return spend

@router.post("/", response_model=BattleCreated, status_code=201)
async def create_battle_endpoint(
    battle_in: BattleCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создаём бой и инициализируем состояние в Redis.
    `battle_in.players` — список объектов
    `{ character_id: int, team: int }`
    """
    player_ids = [p.character_id for p in battle_in.players]
    teams = [p.team if p.team is not None else idx % 2 for idx, p in enumerate(battle_in.players)]

    # 1. Проверка минимального количества участников
    if len(battle_in.players) < 2:
        raise HTTPException(400, "Нужно минимум два участника")

    # 2. CRUD-создание записи в БД + участников
    battle_obj, participant_objs = await create_battle(db, player_ids, teams)

    # 3. Кто ходит первым (первый в списке → team-логика может быть иной)
    first_actor_pid = participant_objs[0].id
    moscow_tz = timezone(timedelta(hours=3))
    deadline = datetime.now(timezone.utc).astimezone(moscow_tz) + timedelta(hours=settings.TURN_TIMEOUT_HOURS)

    participants_info = []
    for p in participant_objs:
        participants_info.append(
            await build_participant_info(p.character_id, p.id)
        )

    # 4. Собираем payload для Redis
    participants_payload = []
    for snap in participants_info:  # каждый snap = build_participant_info(...)
        participants_payload.append({
            "participant_id": snap["participant_id"],
            "character_id": snap["character_id"],
            "team": next(
                pl.team for pl in participant_objs
                if pl.id == snap["participant_id"]
            ),
            # реальные цифры
            "hp": snap["attributes"]["current_health"],
            "mana": snap["attributes"]["current_mana"],
            "energy": snap["attributes"]["current_energy"],
            "stamina": snap["attributes"]["current_stamina"],
            # если хотите — max_*
            "max_hp": snap["attributes"]["max_health"],
            "max_mana": snap["attributes"]["max_mana"],
            "max_energy": snap["attributes"]["max_energy"],
            "max_stamina": snap["attributes"]["max_stamina"],
            "fast_slots": snap["fast_slots"],
        })
    await save_snapshot(battle_obj.id, participants_info)
    rds = await get_redis_client()
    await cache_snapshot(rds, battle_obj.id, participants_info)

    await init_battle_state(
        battle_id=battle_obj.id,
        participants_payload=participants_payload,
        first_actor_participant_id=first_actor_pid,
        deadline_at=deadline,
    )
    await rds.zadd(KEY_BATTLE_TURNS.format(id=battle_obj.id), {"0": 1})

    # 5. Возвращаем ответ
    return BattleCreated(
        battle_id=battle_obj.id,
        participants=[p.id for p in participant_objs],
        next_actor=first_actor_pid,
        deadline_at=deadline,
    )


# battle_service/main.py
@router.get("/{battle_id}/state")
async def get_state(battle_id: int):
    state = await load_state(battle_id)
    if not state:
        raise HTTPException(404, "State not found")

    # snapshot кладём в ответ (берём из Redis, а если нет — из Mongo)
    rds = await get_redis_client()
    snapshot = await get_cached_snapshot(rds, battle_id)
    if snapshot is None:
        snap_doc = await load_snapshot(battle_id)
        if snap_doc:
            snapshot = snap_doc["participants"]
            await cache_snapshot(rds, battle_id, snapshot)

    runtime = {
               "turn_number": state["turn_number"],
               "deadline_at": state["deadline_at"],
               "current_actor": state["next_actor"],
               "next_actor": next_pid_after(state["next_actor"], state["turn_order"]),
               "first_actor": state["first_actor"],
               "turn_order": state["turn_order"],
               "total_turns": state["total_turns"],
               "last_turn": state["last_turn"],
               "participants": {
                      pid: {
                            "hp": state["participants"][pid]["hp"],
                            "mana": state["participants"][pid]["mana"],
                            "energy": state["participants"][pid]["energy"],
                            "stamina": state["participants"][pid]["stamina"],
                            "cooldowns": state["participants"][pid]["cooldowns"],
                            "fast_slots": state["participants"][pid].get("fast_slots", []),
                        }
                            for pid in state["participants"]
                    },
                "active_effects": state["active_effects"],
                }

    return {"snapshot": snapshot, "runtime": runtime}



@router.post("/{battle_id}/action", response_model=ActionResponse)
async def make_action(
    battle_id: int,
    request: ActionRequest,
    db_session: AsyncSession = Depends(get_db),
):
    """
    Обработка полного хода:
      1. читаем текущее состояние из Redis;
      2. убеждаемся, что сейчас ходит именно participant_id;
      3. уменьшаем длительность активных эффектов;
      4. валидируем право владения rank-ами;
      5. применяем support- и defense-эффекты (target=self);
      6. применяем предмет из fast-слота (восстановление ресурсов);
      7. рассчитываем damage / эффекты attack-ранга (target=enemy);
      8. пишем ход в БД, обновляем Redis-state и дедлайны;
      9. отправляем детальный список событий в Celery → Mongo;
     10. возвращаем ActionResponse.
    """

    # ------------------------------------------------------------------------------
    # 1. Получаем Redis-состояние боя
    # ------------------------------------------------------------------------------
    battle_state: Dict | None = await load_state(battle_id)
    logger.debug(f"[ACTION] battle_id={battle_id}, request={request.dict()}")
    if battle_state is None:
        raise HTTPException(404, "Battle not found in Redis")

    # ------------------------------------------------------------------------------
    # 2. Проверяем, что сейчас ход указанного участника
    # ------------------------------------------------------------------------------
    if battle_state["next_actor"] != request.participant_id:
        raise HTTPException(403, "Not your turn")

    # ------------------------------------------------------------------------------
    # 3. Уменьшаем длительность старых баффов/дебаффов
    # ------------------------------------------------------------------------------
    decrement_durations(battle_state)
    decrement_cooldowns(battle_state)

    # ------------------------------------------------------------------------------
    # 4. Валидация владения ранками
    # ------------------------------------------------------------------------------
    participant_info = battle_state["participants"][str(request.participant_id)]
    attacker_character_id: int = participant_info["character_id"]

    for rank_id in filter(
        None,
        [
            request.skills.attack_rank_id,
            request.skills.defense_rank_id,
            request.skills.support_rank_id,
        ],
    ):
        if not await character_has_rank(attacker_character_id, rank_id):
            raise HTTPException(
                400,
                f"Character {attacker_character_id} does not own rank {rank_id}",
            )
    rank_ids = [
        r_id for r_id in [
            request.skills.attack_rank_id,
            request.skills.defense_rank_id,
            request.skills.support_rank_id,
        ] if r_id
    ]
    _ensure_not_on_cooldown(battle_state, request.participant_id, rank_ids)

    # ------------------------------------------------------------------------------
    # 5. Готовим атрибуты + активные модификаторы атакующего
    # ------------------------------------------------------------------------------
    attr_cache: dict[int, dict] ={}

    async def attrs(cid: int) -> dict:
        if cid not in attr_cache:
            attr_cache[cid] = await fetch_full_attributes(cid)
        return attr_cache[cid]

    base_attacker_attributes = await attrs(attacker_character_id)
    attacker_weapon = await fetch_main_weapon(attacker_character_id)

    # События этого хода копим в список
    turn_events: List[Dict] = []

    participant_ids = list(battle_state["participants"].keys())
    defender_pid = int(
        participant_ids[(participant_ids.index(str(request.participant_id)) + 1)
                        % len(participant_ids)]
    )
    defender_info = battle_state["participants"][str(defender_pid)]
    defender_character_id = defender_info["character_id"]

    base_defender_attributes = await attrs(defender_character_id)
    defender_buff_modifiers = aggregate_modifiers(
        battle_state.get("active_effects", {}).get(str(defender_pid), [])
    )
    defender_attributes = apply_flat_modifiers(
        base_defender_attributes, defender_buff_modifiers
    )

    # ------------------------------------------------------------------------------
    # 6. SUPPORT-навык (баффы на self)
    # ------------------------------------------------------------------------------
    support_id = request.skills.support_rank_id
    if support_id and support_id > 0:
        support_rank = await get_rank(request.skills.support_rank_id)

        # self-эффекты
        self_effects = [e for e in support_rank.get("effects", [])
                        if e.get("target_side") == "self"]
        if self_effects:
            apply_new_effects(battle_state, request.participant_id, self_effects)
            turn_events.append({
                "event": "apply_effects", "who": request.participant_id,
                "kind": "support", "effects": [e["effect_name"] for e in self_effects],
            })

        # enemy-эффекты
        enemy_effects = [e for e in support_rank.get("effects", [])
                         if e.get("target_side") == "enemy"]
        if enemy_effects:
            apply_new_effects(battle_state, defender_pid, enemy_effects)
            turn_events.append({
                "event": "apply_effects", "who": defender_pid,
                "kind": "support", "effects": [e["effect_name"] for e in enemy_effects],
            })

    # ------------------------------------------------------------------------------
    # 7. DEFENSE-навык (баффы на self)
    # ------------------------------------------------------------------------------
    defense_id=request.skills.defense_rank_id
    if defense_id and defense_id > 0:
        defense_rank = await get_rank(request.skills.defense_rank_id)

        self_effects = [e for e in defense_rank.get("effects", [])
                        if e.get("target_side") == "self"]
        if self_effects:
            apply_new_effects(battle_state, request.participant_id, self_effects)
            turn_events.append({
                "event": "apply_effects", "who": request.participant_id,
                "kind": "defense", "effects": [e["effect_name"] for e in self_effects],
            })

        enemy_effects = [e for e in defense_rank.get("effects", [])
                         if e.get("target_side") == "enemy"]
        if enemy_effects:
            apply_new_effects(battle_state, defender_pid, enemy_effects)
            turn_events.append({
                "event": "apply_effects", "who": defender_pid,
                "kind": "defense", "effects": [e["effect_name"] for e in enemy_effects],
            })

    # ------------------------------------------------------------------------------
    # 8. Использование предмета из fast-слота
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # 8. Использование предмета из fast-слота (только по выбору игрока)
    # ------------------------------------------------------------------------------
    item_id = request.skills.item_id  # может быть None / 0 / >0

    if item_id and item_id > 0:
        # 1) Берём полный JSON по предмету (там же recovery-поля)
        item_json = await get_item(item_id)

        # 2) Собираем recovery-payload
        recovery_payload = {
            key.replace("_recovery", ""): item_json[key]
            for key in (
                "health_recovery",
                "mana_recovery",
                "energy_recovery",
                "stamina_recovery",
            )
            if item_json.get(key)
        }

        # 3) Применяем к ресурсам персонажа в state
        me = str(request.participant_id)
        part = battle_state["participants"][me]
        for res, delta in recovery_payload.items():
            old = part[res if res != "health" else "hp"]
            mx = part[f"max_{res if res != 'health' else 'hp'}"]
            new = min(old + delta, mx)
            part[res if res != "health" else "hp"] = new

        # 4) Уменьшаем 1 шт. в соответствующем fast_slot
        for slot in part.get("fast_slots", []):
            if slot["item_id"] == item_id and slot.get("quantity", 0) > 0:
                slot["quantity"] -= 1
                break

        # 5) Логируем событие
        turn_events.append({
            "event": "item_use",
            "who": request.participant_id,
            "item_id": item_id,
            "item_name": item_json["name"],
            "recovery": recovery_payload,
        })
        logger.debug(f"[ITEM] used item_id={item_id}, rec={recovery_payload}, rem={slot.get('quantity')}")

    # ------------------------------------------------------------------------------
    # 9. ATTACK-навык
    # ------------------------------------------------------------------------------
    attack_id=request.skills.attack_rank_id
    logger.debug(f"[SKILL] attack_rank_id={request.skills.attack_rank_id}")
    if attack_id and attack_id >0:
        attack_rank = await get_rank(request.skills.attack_rank_id)
        logger.debug(f"[SKILL] attack_rank full_json={attack_rank}")

        attacker_buff_modifiers = aggregate_modifiers(
            battle_state.get("active_effects", {}).get(str(request.participant_id), [])
        )
        percent_damage_buffs = build_percent_damage_buffs(attacker_buff_modifiers)

        attacker_attributes = apply_flat_modifiers(
            base_attacker_attributes, attacker_buff_modifiers
        )

        defender_buff_modifiers = aggregate_modifiers(
            battle_state.get("active_effects", {}).get(str(defender_pid), [])
        )
        defender_percent_resists = build_percent_resist_buffs(defender_buff_modifiers)

        # damage_entries
        for dmg in attack_rank.get("damage_entries", []):
            dealt, log = await compute_damage_with_rolls(
                damage_entry=dmg,
                attacker_attr=attacker_attributes,
                weapon=attacker_weapon,
                percent_buffs=percent_damage_buffs,
                defender_attr=defender_attributes,
                percent_resists=defender_percent_resists,
            )
            battle_state["participants"][str(defender_pid)]["hp"] -= dealt
            turn_events.append({
                "event": "damage", "source": request.participant_id,
                "target": defender_pid, **log
            })

        # enemy-эффекты
        enemy_effects = [e for e in attack_rank.get("effects", [])
                         if e.get("target_side") == "enemy"]
        if enemy_effects:
            apply_new_effects(battle_state, defender_pid, enemy_effects)
            turn_events.append({
                "event": "apply_effects", "who": defender_pid,
                "kind": "attack",
                "effects": [e["effect_name"] for e in enemy_effects],
            })

        # 3.2  Эффекты, которые накладываются на enemy
        enemy_effects = [
            eff for eff in attack_rank.get("effects", [])  # ← безопасно
            if eff.get("target_side") == "enemy"
        ]
        if enemy_effects:
            apply_new_effects(battle_state, int(defender_pid), enemy_effects)
            turn_events.append({
                "event": "apply_effects",
                "who": int(defender_pid),
                "kind": "attack",
                "effects": [e["effect_name"] for e in enemy_effects],
            })

    attack_rank = await get_rank(request.skills.attack_rank_id) if request.skills.attack_rank_id else None
    defense_rank = await get_rank(request.skills.defense_rank_id) if request.skills.defense_rank_id else None
    support_rank = await get_rank(request.skills.support_rank_id) if request.skills.support_rank_id else None

    spend = await _pay_skill_costs(
        battle_state,
        request.participant_id,
        [r for r in (attack_rank, defense_rank, support_rank) if r]
    )
    if attack_rank and attack_rank.get("cooldown"):
        set_cooldown(battle_state, request.participant_id,
                      attack_rank["id"], attack_rank["cooldown"])
    if defense_rank and defense_rank.get("cooldown"):
        set_cooldown(battle_state, request.participant_id,
                      defense_rank["id"], defense_rank["cooldown"])
    if support_rank and support_rank.get("cooldown"):
        set_cooldown(battle_state, request.participant_id,
                      support_rank["id"], support_rank["cooldown"])

    turn_events.append(
        {"event": "resource_spend", "who": request.participant_id, **spend}
    )
    logger.debug("[EVENTS] turn_events=%s", turn_events)
    # ------------------------------------------------------------------------------
    # 10. Записываем ход в БД
    # ------------------------------------------------------------------------------
    new_turn_number = battle_state["turn_number"] + 1
    moscow_tz = timezone(timedelta(hours=3))
    started_at = datetime.now(timezone.utc).astimezone(moscow_tz)
    new_deadline = started_at + timedelta(hours=settings.TURN_TIMEOUT_HOURS)
    await write_turn(
        db_session,
        battle_id=battle_id,
        actor_participant_id=request.participant_id,
        turn_number=new_turn_number,
        skills=request.skills,
        deadline_at=new_deadline,
    )

    # ------------------------------------------------------------------------------
    # 11. Обновляем Redis-state (turn_number, next_actor, дедлайн)
    # ------------------------------------------------------------------------------
    participant_ids: List[str] = list(battle_state["participants"].keys())
    current_index = participant_ids.index(str(request.participant_id))
    next_actor_participant_id = int(
        participant_ids[(current_index + 1) % len(participant_ids)]
    )

    battle_state["turn_number"] = new_turn_number
    battle_state["next_actor"] = next_actor_participant_id
    battle_state["deadline_at"] = new_deadline.isoformat()

    await save_state(battle_id, battle_state)

    redis = await get_redis_client()

    await redis.zadd(KEY_BATTLE_TURNS.format(id=battle_id),
                     {str(new_turn_number): 1})

    await redis.zadd(
        ZSET_DEADLINES,
        {f"{battle_id}:{next_actor_participant_id}": new_deadline.timestamp()},
    )
    await redis.publish(
        f"battle:{battle_id}:your_turn", str(next_actor_participant_id)
    )

    # ------------------------------------------------------------------------------
    # 12. Асинхронно сохраняем лог хода в Mongo через Celery
    # ------------------------------------------------------------------------------
    save_log.delay(battle_id, new_turn_number, turn_events)

    # ------------------------------------------------------------------------------
    # 13. Возвращаем результат
    # ------------------------------------------------------------------------------
    return ActionResponse(
        ok=True,
        turn_number=new_turn_number,
        next_actor=next_actor_participant_id,
        deadline_at=new_deadline,
        events=turn_events
    )

@router.get("/battles/{battle_id}/logs")
async def list_turn_logs(battle_id: int, limit: int = 50):
    db = get_mongo_db()
    cursor = (
        db.battle_logs
          .find({"battle_id": battle_id})
          .sort("turn_number", -1)
          .limit(limit)
    )
    docs = [doc async for doc in cursor]
    for d in docs:
        d["_id"] = str(d["_id"])
    if not docs:
        raise HTTPException(404, "Нет логов для этого боя")
    return docs

@router.get("/battles/{battle_id}/logs/{turn_number}",
            response_model=LogResponse)
async def logs_for_turn(battle_id: int, turn_number: int):
    logs = await get_logs_for_turn(battle_id, turn_number)
    if not logs:
        return {"logs": []}              # возвращаем пустой список, не 404
    return {"logs": logs}

app.include_router(router)

from datetime import datetime, timedelta
from typing import List, Dict

from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from crud import create_battle, write_turn
from schemas import BattleCreated, BattleCreate, ActionResponse, ActionRequest

from database import get_db
from buffs import decrement_durations, aggregate_modifiers, apply_new_effects
from battle_engine import fetch_full_attributes, apply_flat_modifiers, fetch_main_weapon, compute_damage_with_rolls
from redis_state import init_battle_state, load_state, save_state, get_redis_client, ZSET_DEADLINES
from config import settings
from tasks import save_log
from skills_client import character_has_rank, get_rank, get_item

app = FastAPI(title="Battle Service")
router = APIRouter(prefix="/battles", tags=["battles"])


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

    # 1. Проверка минимального количества участников
    if len(battle_in.players) < 2:
        raise HTTPException(400, "Нужно минимум два участника")

    # 2. CRUD-создание записи в БД + участников
    battle_obj, participant_objs = await create_battle(
        db, battle_in.players
    )

    # 3. Кто ходит первым (первый в списке → team-логика может быть иной)
    first_actor_pid = participant_objs[0].id
    deadline = datetime.utcnow() + timedelta(hours=settings.TURN_TIMEOUT_HOURS)

    # 4. Собираем payload для Redis
    participants_payload = [
        {
            "participant_id": p.id,
            "character_id":  p.character_id,
            "team":          p.team,
        }
        for p in participant_objs
    ]

    await init_battle_state(
        battle_id=battle_obj.id,
        participants_payload=participants_payload,
        first_actor_participant_id=first_actor_pid,
        deadline_at=deadline,
    )

    # 5. Возвращаем ответ
    return BattleCreated(
        battle_id=battle_obj.id,
        participants=[p.id for p in participant_objs],
        next_actor=first_actor_pid,
        deadline_at=deadline,
    )


@router.get("/{battle_id}/state")
async def get_state(battle_id: int):
    state = await load_state(battle_id)
    if not state:
        raise HTTPException(404, "State not found")
    return state



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

    # ------------------------------------------------------------------------------
    # 5. Готовим атрибуты + активные модификаторы атакующего
    # ------------------------------------------------------------------------------
    base_attacker_attributes = await fetch_full_attributes(attacker_character_id)
    attacker_buff_modifiers = aggregate_modifiers(
        battle_state.get("active_effects", {}).get(str(request.participant_id), [])
    )
    attacker_attributes = apply_flat_modifiers(
        base_attacker_attributes, attacker_buff_modifiers
    )
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

    base_defender_attributes = await fetch_full_attributes(defender_character_id)
    defender_buff_modifiers = aggregate_modifiers(
        battle_state.get("active_effects", {}).get(str(defender_pid), [])
    )
    defender_attributes = apply_flat_modifiers(
        base_defender_attributes, defender_buff_modifiers
    )

    # суммарные %-баффы атаки (нужны compute_damage_with_rolls)
    percent_damage_buffs = attacker_buff_modifiers.get("percent_damage", {})

    # ------------------------------------------------------------------------------
    # 6. SUPPORT-навык (баффы на self)
    # ------------------------------------------------------------------------------
    if request.skills.support_rank_id is not None:
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
    if request.skills.defense_rank_id is not None:
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
    item_id = request.skills.item_id  # может быть None / 0 / >0

    if item_id and item_id > 0:  # ← пропускаем None или 0
        item_json = await get_item(item_id)

        recovery_payload = {
            key: item_json[key]
            for key in (
                "health_recovery",
                "mana_recovery",
                "energy_recovery",
                "stamina_recovery",
            )
            if item_json.get(key)
        }

        # обновляем текущие ресурсы прямо в Redis-state
        for recovery_key, delta in recovery_payload.items():
            resource = recovery_key.replace("_recovery", "")   # health, mana …
            current_value = battle_state["participants"][str(request.participant_id)][
                resource
            ]
            max_value = base_attacker_attributes[f"max_{resource}"]
            battle_state["participants"][str(request.participant_id)][resource] = min(
                current_value + delta, max_value
            )

        turn_events.append(
            {
                "event": "item_use",
                "who": request.participant_id,
                "item_id": item_json["id"],
                "recovery": recovery_payload,
            }
        )

    # ------------------------------------------------------------------------------
    # 9. ATTACK-навык
    # ------------------------------------------------------------------------------
    if request.skills.attack_rank_id is not None:
        attack_rank = await get_rank(request.skills.attack_rank_id)

        # damage_entries
        for dmg in attack_rank.get("damage_entries", []):
            dealt, log = await compute_damage_with_rolls(
                damage_entry=dmg,
                attacker_attr=attacker_attributes,
                weapon=attacker_weapon,
                percent_buffs=percent_damage_buffs,
                defender_attr=defender_attributes,
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

    # ------------------------------------------------------------------------------
    # 10. Записываем ход в БД
    # ------------------------------------------------------------------------------
    new_turn_number = battle_state["turn_number"] + 1
    new_deadline = datetime.utcnow() + timedelta(hours=settings.TURN_TIMEOUT_HOURS)

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

    await save_state(battle_id, battle_state)

    redis_client = await get_redis_client()
    await redis_client.zadd(
        ZSET_DEADLINES,
        {f"{battle_id}:{next_actor_participant_id}": new_deadline.timestamp()},
    )
    await redis_client.publish(
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
    )

@router.get("/battles/{battle_id}/logs")
async def list_turn_logs(battle_id: int, limit: int = 50):
    db = get_db()
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


app.include_router(router)

from datetime import datetime, timedelta, timezone
from os import supports_fd
from typing import List, Dict

from fastapi import FastAPI, Depends, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from crud import create_battle, write_turn, get_logs_for_turn, finish_battle, get_battle
from schemas import BattleCreated, BattleCreate, ActionResponse, ActionRequest, LogResponse, BattleRewards, BattleRewardItem
from auth_http import get_current_user_via_http, UserRead
from mongo_client import get_mongo_db
from database import get_db
from battle_engine import decrement_cooldowns, set_cooldown
from inventory_client import get_fast_slots
from character_client import get_character_profile
from buffs import decrement_durations, aggregate_modifiers, apply_new_effects, build_percent_damage_buffs, \
    build_percent_resist_buffs
from battle_engine import fetch_full_attributes, apply_flat_modifiers, fetch_main_weapon, compute_damage_with_rolls
from redis_state import init_battle_state, load_state, save_state, get_redis_client, ZSET_DEADLINES, cache_snapshot, \
    get_cached_snapshot, KEY_BATTLE_TURNS, state_key
from config import settings
from mongo_helpers import save_snapshot, load_snapshot
from tasks import save_log
from skills_client import character_has_rank, get_rank, get_item, character_ranks
import httpx
import logging
import os
import random
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
        remaining = cd.get(str(rid), 0)
        if remaining > 0:
            raise HTTPException(400, f"Навык на перезарядке (осталось ходов: {remaining})")

async def verify_character_ownership(db: AsyncSession, character_id: int, user_id: int):
    """Check that a character belongs to the given user."""
    result = await db.execute(
        text("SELECT user_id FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    if row[0] != user_id:
        raise HTTPException(
            status_code=403,
            detail="Вы можете управлять только своими персонажами",
        )


async def build_participant_info(char_id: int, participant_id: int) -> dict:
    """
    Сбор ВСЕГО, что нужно зафиксировать на старте боя
    (avatar, name, attributes, skills, fast-slots).
    """
    try:
        attr = await fetch_full_attributes(char_id)
    except Exception as e:
        logger.error(f"Не удалось получить атрибуты персонажа {char_id}: {e}")
        raise HTTPException(500, f"Не удалось получить атрибуты персонажа {char_id}")

    try:
        ranks = await character_ranks(char_id)
    except Exception as e:
        logger.warning(f"Не удалось получить навыки персонажа {char_id}: {e}")
        ranks = []

    try:
        slots = await get_fast_slots(char_id)
    except Exception as e:
        logger.warning(f"Не удалось получить быстрые слоты персонажа {char_id}: {e}")
        slots = []

    try:
        profile = await get_character_profile(char_id)
        name = profile["character_name"]
        avatar = profile.get("character_photo", "")
    except Exception as e:
        logger.warning(f"Не удалось получить профиль персонажа {char_id}: {e}")
        name = f"Персонаж #{char_id}"
        avatar = ""

    return {
        "participant_id": participant_id,
        "character_id"  : char_id,
        "name"          : name,
        "avatar"        : avatar,
        "attributes"    : attr,
        "skills"        : ranks,
        "fast_slots"    : slots,
    }


async def _distribute_pve_rewards(
    battle_state: dict,
    winner_team: int,
    turn_events: list,
) -> BattleRewards | None:
    """
    After a battle finishes, check if any defeated participant is a mob.
    If so, distribute rewards (XP, gold, loot) to the winning team's player characters.
    Returns BattleRewards or None if not a PvE battle.
    """
    char_service = settings.CHARACTER_SERVICE_URL
    inv_service = settings.INVENTORY_SERVICE_URL

    # Find defeated mob participants (HP <= 0 and is_npc)
    defeated_mob_char_ids = []
    winner_char_ids = []

    for pid_str, pdata in battle_state["participants"].items():
        char_id = pdata["character_id"]
        if pdata["hp"] <= 0 and pdata["team"] != winner_team:
            # Check if this character is a mob via character-service
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"{char_service}/characters/internal/mob-reward-data/{char_id}"
                    )
                    if resp.status_code == 200:
                        defeated_mob_char_ids.append((char_id, resp.json()))
            except httpx.RequestError as e:
                logger.error(f"Ошибка при проверке моба char_id={char_id}: {e}")
        elif pdata["team"] == winner_team and pdata["hp"] > 0:
            winner_char_ids.append(char_id)

    if not defeated_mob_char_ids or not winner_char_ids:
        return None

    # Aggregate rewards from all defeated mobs
    total_xp = 0
    total_gold = 0
    dropped_items: list[BattleRewardItem] = []

    for mob_char_id, reward_data in defeated_mob_char_ids:
        total_xp += reward_data.get("xp_reward", 0)
        total_gold += reward_data.get("gold_reward", 0)

        # Roll loot table
        for loot_entry in reward_data.get("loot_table", []):
            roll = random.random() * 100
            if roll < loot_entry["drop_chance"]:
                quantity = random.randint(
                    loot_entry["min_quantity"],
                    loot_entry["max_quantity"],
                )
                dropped_items.append(BattleRewardItem(
                    item_id=loot_entry["item_id"],
                    quantity=quantity,
                ))

        # Update active mob status to 'dead'
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.put(
                    f"{char_service}/characters/internal/active-mob-status/{mob_char_id}",
                    json={"status": "dead"},
                )
        except httpx.RequestError as e:
            logger.error(f"Ошибка при обновлении статуса моба char_id={mob_char_id}: {e}")

    # Distribute rewards to each winner
    for winner_id in winner_char_ids:
        # Add XP and gold
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{char_service}/characters/{winner_id}/add_rewards",
                    json={"xp": total_xp, "gold": total_gold},
                )
                if resp.status_code == 200:
                    logger.info(f"Награды добавлены для персонажа {winner_id}: xp={total_xp}, gold={total_gold}")
                else:
                    logger.error(f"Ошибка при добавлении наград для {winner_id}: {resp.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Ошибка при отправке наград для {winner_id}: {e}")

        # Add dropped items to inventory
        for item in dropped_items:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(
                        f"{inv_service}/inventory/{winner_id}/items",
                        json={"item_id": item.item_id, "quantity": item.quantity},
                    )
                    if resp.status_code == 200:
                        logger.info(f"Предмет {item.item_id} x{item.quantity} добавлен в инвентарь {winner_id}")
                    else:
                        logger.error(f"Ошибка при добавлении предмета {item.item_id} для {winner_id}: {resp.status_code}")
            except httpx.RequestError as e:
                logger.error(f"Ошибка при добавлении предмета {item.item_id} для {winner_id}: {e}")

    # Try to resolve item names for the reward response
    for item in dropped_items:
        try:
            item_data = await get_item(item.item_id)
            item.item_name = item_data.get("name")
        except Exception:
            pass

    turn_events.append({
        "event": "pve_rewards",
        "xp": total_xp,
        "gold": total_gold,
        "items": [{"item_id": i.item_id, "item_name": i.item_name, "quantity": i.quantity} for i in dropped_items],
    })

    return BattleRewards(
        xp=total_xp,
        gold=total_gold,
        items=dropped_items,
    )


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
    res_names_ru = {"energy": "энергии", "mana": "маны", "stamina": "выносливости"}
    for res, value in spend.items():
        if pstate[res] < value:
            raise HTTPException(
                400, f"Недостаточно {res_names_ru[res]}: нужно {value}, есть {pstate[res]}"
            )

    # Списываем
    for res, value in spend.items():
        pstate[res] -= value

    return spend

@router.post("/", response_model=BattleCreated, status_code=201)
async def create_battle_endpoint(
    battle_in: BattleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """
    Создаём бой и инициализируем состояние в Redis.
    `battle_in.players` — список объектов
    `{ character_id: int, team: int }`
    """
    player_ids = [p.character_id for p in battle_in.players]
    teams = [p.team if p.team is not None else idx % 2 for idx, p in enumerate(battle_in.players)]

    # 0. Ownership: at least one character must belong to the current user
    user_owns_any = False
    for cid in player_ids:
        result = await db.execute(
            text("SELECT user_id FROM characters WHERE id = :cid"),
            {"cid": cid},
        )
        row = result.fetchone()
        if row and row[0] == current_user.id:
            user_owns_any = True
            break
    if not user_owns_any:
        raise HTTPException(
            status_code=403,
            detail="Вы должны участвовать в бою своим персонажем",
        )

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

    # 5. Auto-register NPC/mob participants with autobattle-service
    for p in participant_objs:
        try:
            result = await db.execute(
                text("SELECT is_npc FROM characters WHERE id = :cid"),
                {"cid": p.character_id},
            )
            row = result.fetchone()
            if row and row[0]:
                # This is an NPC — register with autobattle-service (internal endpoint, no auth)
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        reg_resp = await client.post(
                            f"{settings.AUTOBATTLE_SERVICE_URL}/internal/register",
                            json={
                                "participant_id": p.id,
                                "battle_id": battle_obj.id,
                            },
                        )
                        if reg_resp.status_code == 200:
                            logger.info(
                                f"Моб participant_id={p.id} (char={p.character_id}) "
                                f"зарегистрирован в autobattle для боя {battle_obj.id}"
                            )
                        else:
                            logger.warning(
                                f"Не удалось зарегистрировать моба в autobattle: "
                                f"{reg_resp.status_code} - {reg_resp.text}"
                            )
                except httpx.RequestError as e:
                    logger.error(f"Ошибка при регистрации моба в autobattle: {e}")
        except Exception as e:
            logger.error(f"Ошибка при проверке NPC для participant {p.id}: {e}")

    # 6. Возвращаем ответ
    return BattleCreated(
        battle_id=battle_obj.id,
        participants=[p.id for p in participant_objs],
        next_actor=first_actor_pid,
        deadline_at=deadline,
    )


# -----------------------------------------------------------
# Internal endpoints (no auth, for service-to-service calls)
# -----------------------------------------------------------
@router.get("/internal/{battle_id}/state")
async def get_state_internal(battle_id: int):
    """Internal endpoint for autobattle-service — no JWT required."""
    state = await load_state(battle_id)
    if not state:
        raise HTTPException(404, "State not found")

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
                "team": state["participants"][pid]["team"],
                "character_id": state["participants"][pid]["character_id"],
                "max_hp": state["participants"][pid].get("max_hp", 0),
                "max_mana": state["participants"][pid].get("max_mana", 0),
                "max_energy": state["participants"][pid].get("max_energy", 0),
                "max_stamina": state["participants"][pid].get("max_stamina", 0),
            }
            for pid in state["participants"]
        },
        "active_effects": state["active_effects"],
    }

    return {"snapshot": snapshot, "runtime": runtime}


@router.post("/internal/{battle_id}/action", response_model=ActionResponse)
async def make_action_internal(
    battle_id: int,
    request: ActionRequest,
    db_session: AsyncSession = Depends(get_db),
):
    """Internal endpoint for autobattle-service — no JWT required."""
    return await _make_action_core(battle_id, request, db_session, skip_ownership=True)


# battle_service/main.py
@router.get("/{battle_id}/state")
async def get_state(
    battle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    state = await load_state(battle_id)
    if not state:
        raise HTTPException(404, "State not found")

    # Ownership: verify the user has a character participating in this battle
    participant_character_ids = [
        state["participants"][pid]["character_id"]
        for pid in state["participants"]
    ]
    user_is_participant = False
    for cid in participant_character_ids:
        result = await db.execute(
            text("SELECT user_id FROM characters WHERE id = :cid"),
            {"cid": cid},
        )
        row = result.fetchone()
        if row and row[0] == current_user.id:
            user_is_participant = True
            break
    if not user_is_participant:
        raise HTTPException(
            status_code=403,
            detail="Вы не участвуете в этом бою",
        )

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



async def _make_action_core(
    battle_id: int,
    request: ActionRequest,
    db_session: AsyncSession,
    skip_ownership: bool = False,
    current_user=None,
):
    """Core action logic shared by authenticated and internal endpoints."""

    # ------------------------------------------------------------------------------
    # 1. Получаем Redis-состояние боя
    # ------------------------------------------------------------------------------
    battle_record = await get_battle(db_session, battle_id)
    if battle_record and battle_record.status.value == "finished":
        raise HTTPException(400, "Бой уже завершён")

    battle_state: Dict | None = await load_state(battle_id)
    logger.debug(f"[ACTION] battle_id={battle_id}, request={request.dict()}")
    if battle_state is None:
        raise HTTPException(404, "Бой не найден")

    # ------------------------------------------------------------------------------
    # 1.5. Ownership check (skipped for internal/autobattle calls)
    # ------------------------------------------------------------------------------
    if not skip_ownership and current_user:
        participant_info_auth = battle_state["participants"].get(str(request.participant_id))
        if participant_info_auth is None:
            raise HTTPException(404, "Участник не найден в этом бою")
        await verify_character_ownership(
            db_session, participant_info_auth["character_id"], current_user.id
        )

    # ------------------------------------------------------------------------------
    # 2. Проверяем, что сейчас ход указанного участника
    # ------------------------------------------------------------------------------
    if battle_state["next_actor"] != request.participant_id:
        raise HTTPException(403, "Сейчас не ваш ход")

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
                "Персонаж не владеет этим навыком",
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
            apply_new_effects(battle_state, defender_pid, enemy_effects, is_enemy=True)
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
            apply_new_effects(battle_state, defender_pid, enemy_effects, is_enemy=True)
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
            apply_new_effects(battle_state, defender_pid, enemy_effects, is_enemy=True)
            turn_events.append({
                "event": "apply_effects", "who": defender_pid,
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
    # 9.5. Проверка HP <= 0 — завершение боя при гибели участника
    # ------------------------------------------------------------------------------
    battle_finished = False
    winner_team = None

    for pid_str, pdata in battle_state["participants"].items():
        if pdata["hp"] <= 0:
            battle_finished = True
            # The losing team is this participant's team; winner is the other team
            losing_team = pdata["team"]
            # Find the winning team (any team that is not the losing one)
            for other_pid_str, other_pdata in battle_state["participants"].items():
                if other_pdata["team"] != losing_team:
                    winner_team = other_pdata["team"]
                    break
            turn_events.append({
                "event": "participant_defeated",
                "who": int(pid_str),
                "hp": pdata["hp"],
            })
            break

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
    # 10.5. Если бой завершён — обновляем MySQL и Redis, возвращаем результат
    # ------------------------------------------------------------------------------
    if battle_finished:
        # Update battle status in MySQL
        await finish_battle(db_session, battle_id)

        # Sync final resources (HP, mana, energy, stamina) back to character_attributes DB
        for pid_str, pdata in battle_state["participants"].items():
            char_id = pdata["character_id"]
            try:
                await db_session.execute(
                    text("""
                        UPDATE character_attributes
                        SET current_health = :hp,
                            current_mana = :mana,
                            current_energy = :energy,
                            current_stamina = :stamina
                        WHERE character_id = :cid
                    """),
                    {
                        "hp": max(0, int(pdata["hp"])),
                        "mana": max(0, int(pdata["mana"])),
                        "energy": max(0, int(pdata["energy"])),
                        "stamina": max(0, int(pdata["stamina"])),
                        "cid": char_id,
                    },
                )
                await db_session.commit()
                logger.info(f"Ресурсы персонажа {char_id} синхронизированы после боя")
            except Exception as e:
                logger.error(f"Не удалось синхронизировать ресурсы персонажа {char_id}: {e}")

        # Update Redis state one last time with final HP values
        battle_state["turn_number"] = new_turn_number
        await save_state(battle_id, battle_state)

        # Expire Redis state (keep for 5 minutes for final reads, then auto-delete)
        redis = await get_redis_client()
        await redis.expire(state_key(battle_id), 300)

        # Clean up deadline entries
        for pid_str in battle_state["participants"]:
            await redis.zrem(ZSET_DEADLINES, f"{battle_id}:{pid_str}")

        turn_events.append({
            "event": "battle_finished",
            "winner_team": winner_team,
        })

        # PvE rewards: check if defeated participant is a mob
        battle_rewards = None
        if winner_team is not None:
            battle_rewards = await _distribute_pve_rewards(
                battle_state, winner_team, turn_events
            )

        # Save log via Celery
        save_log.delay(battle_id, new_turn_number, turn_events)

        return ActionResponse(
            ok=True,
            turn_number=new_turn_number,
            next_actor=request.participant_id,
            deadline_at=new_deadline,
            events=turn_events,
            battle_finished=True,
            winner_team=winner_team,
            rewards=battle_rewards,
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


@router.post("/{battle_id}/action", response_model=ActionResponse)
async def make_action(
    battle_id: int,
    request: ActionRequest,
    db_session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Authenticated action endpoint for player turns."""
    return await _make_action_core(
        battle_id, request, db_session,
        skip_ownership=False, current_user=current_user,
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

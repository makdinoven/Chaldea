import json
from datetime import datetime, timedelta, timezone
from os import supports_fd
from typing import List, Dict

from fastapi import FastAPI, Depends, HTTPException, APIRouter, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from crud import create_battle, write_turn, get_logs_for_turn, finish_battle, get_battle, get_active_battle_for_character
from schemas import (
    BattleCreated, BattleCreate, ActionResponse, ActionRequest, LogResponse,
    BattleRewards, BattleRewardItem,
    PvpInviteRequest, PvpInviteResponse, PvpRespondRequest, PvpRespondAcceptResponse,
    PendingInvitationsResponse, IncomingInvitation, OutgoingInvitation,
    CancelInvitationResponse, InBattleResponse,
    PvpAttackRequest, PvpAttackResponse,
    BattleHistoryItem, BattleStats, BattleHistoryResponse,
    AdminBattleParticipant, AdminBattleListItem, AdminBattleListResponse,
    AdminBattleStateResponse, AdminForceFinishResponse,
    LocationBattleParticipant, LocationBattleItem, LocationBattlesResponse,
    SpectateStateResponse,
    JoinRequestCreate, JoinRequestResponse, JoinRequestListItem, JoinRequestListResponse,
    AdminJoinRequestItem, AdminJoinRequestListResponse, AdminJoinRequestActionResponse,
)
from models import BattleType, BattleHistory, BattleResult, PvpInvitation, PvpInvitationStatus, BattleStatus, BattleJoinRequest, JoinRequestStatus, BattleParticipant
from rabbitmq_publisher import publish_notification
from auth_http import get_current_user_via_http, UserRead, require_permission
from mongo_client import get_mongo_db
from database import get_db
from battle_engine import decrement_cooldowns, set_cooldown
from inventory_client import get_fast_slots, consume_item
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

    # Record kills for bestiary (fire-and-forget)
    for mob_char_id, reward_data in defeated_mob_char_ids:
        for winner_id in winner_char_ids:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"{char_service}/characters/internal/record-mob-kill",
                        json={"character_id": winner_id, "mob_character_id": mob_char_id},
                    )
            except httpx.RequestError as e:
                logger.error(f"Ошибка записи kill для бестиария char={winner_id}, mob={mob_char_id}: {e}")

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

    # 0.5. Check none of the players are already in battle
    for cid in player_ids:
        existing_battle = await get_active_battle_for_character(db, cid)
        if existing_battle:
            raise HTTPException(400, "Персонаж уже в бою")

    # 1. Проверка минимального количества участников
    if len(battle_in.players) < 2:
        raise HTTPException(400, "Нужно минимум два участника")

    # 1.5. Derive location_id from first player character
    loc_result = await db.execute(
        text("SELECT current_location_id FROM characters WHERE id = :cid"),
        {"cid": player_ids[0]},
    )
    loc_row = loc_result.fetchone()
    battle_location_id = loc_row[0] if loc_row else None

    # 2. CRUD-создание записи в БД + участников
    bt = battle_in.battle_type or "pve"
    battle_obj, participant_objs = await create_battle(
        db, player_ids, teams, battle_type=bt, location_id=battle_location_id
    )

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
        "rewards": state.get("rewards"),
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

    # Load battle record for pause status
    battle_record = await get_battle(db, battle_id)
    is_paused = battle_record.is_paused if battle_record else False
    paused_reason = "Рассматривается заявка на присоединение" if is_paused else None

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
                "is_paused": is_paused,
                "paused_reason": paused_reason,
                "rewards": state.get("rewards"),
                }

    return {"snapshot": snapshot, "runtime": runtime}


@router.get("/{battle_id}/spectate", response_model=SpectateStateResponse)
async def spectate_battle(
    battle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """
    Spectate endpoint — returns battle state for observers at the same location.
    No participant ownership required, but user must have a character at the battle's location.
    """
    # 1. Load battle from MySQL
    battle_record = await get_battle(db, battle_id)
    if not battle_record:
        raise HTTPException(status_code=404, detail="Бой не найден")
    if battle_record.status not in (BattleStatus.pending, BattleStatus.in_progress):
        raise HTTPException(status_code=404, detail="Бой не активен")

    if not battle_record.location_id:
        raise HTTPException(status_code=404, detail="Бой не привязан к локации")

    # 2. Get user's characters and check if any is at the same location
    result = await db.execute(
        text("SELECT id, current_location_id FROM characters WHERE user_id = :uid"),
        {"uid": current_user.id},
    )
    user_characters = result.fetchall()
    user_at_location = any(
        row[1] == battle_record.location_id for row in user_characters
    )
    if not user_at_location:
        raise HTTPException(
            status_code=403,
            detail="Вы должны быть на той же локации для наблюдения",
        )

    # 3. Load state from Redis
    state = await load_state(battle_id)
    if not state:
        raise HTTPException(status_code=404, detail="Состояние боя не найдено")

    # 4. Load snapshot (Redis cache → MongoDB fallback)
    rds = await get_redis_client()
    snapshot = await get_cached_snapshot(rds, battle_id)
    if snapshot is None:
        snap_doc = await load_snapshot(battle_id)
        if snap_doc:
            snapshot = snap_doc["participants"]
            await cache_snapshot(rds, battle_id, snapshot)

    # 5. Build runtime with pause info
    is_paused = battle_record.is_paused
    paused_reason = "Рассматривается заявка на присоединение" if is_paused else None

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
        "is_paused": is_paused,
        "paused_reason": paused_reason,
    }

    return {"snapshot": snapshot, "runtime": runtime}


# ---------------------------------------------------------------------------
# Pause / Resume helpers (used by join-request and admin approve/reject)
# ---------------------------------------------------------------------------
async def pause_battle(db: AsyncSession, battle_id: int) -> None:
    """
    Pause a battle: set is_paused in MySQL, update Redis state
    (paused flag + remaining_deadline_seconds), remove deadline from ZSET.
    """
    # 1. MySQL: set is_paused = True
    await db.execute(
        text("UPDATE battles SET is_paused = 1 WHERE id = :bid"),
        {"bid": battle_id},
    )
    await db.commit()

    # 2. Redis state: set paused, store remaining deadline seconds
    state = await load_state(battle_id)
    if state:
        now = datetime.utcnow()
        deadline_at = datetime.fromisoformat(state["deadline_at"])
        remaining = max(0, (deadline_at - now).total_seconds())
        state["paused"] = True
        state["remaining_deadline_seconds"] = remaining
        await save_state(battle_id, state)

        # 3. Remove deadline from ZSET
        rds = await get_redis_client()
        for pid_str in state["participants"]:
            await rds.zrem(ZSET_DEADLINES, f"{battle_id}:{pid_str}")

    logger.info(f"Battle {battle_id} paused")


async def resume_battle_if_ready(db: AsyncSession, battle_id: int) -> bool:
    """
    Check if there are remaining pending join requests.
    If none, resume the battle. Returns True if resumed.
    """
    # Check for remaining pending requests
    result = await db.execute(
        text("""
            SELECT COUNT(*) FROM battle_join_requests
            WHERE battle_id = :bid AND status = 'pending'
        """),
        {"bid": battle_id},
    )
    pending_count = result.scalar()
    if pending_count > 0:
        return False

    # Resume: MySQL
    await db.execute(
        text("UPDATE battles SET is_paused = 0 WHERE id = :bid"),
        {"bid": battle_id},
    )
    await db.commit()

    # Resume: Redis state
    state = await load_state(battle_id)
    if state:
        remaining_secs = state.get("remaining_deadline_seconds", 60)
        now = datetime.utcnow()
        new_deadline = now + timedelta(seconds=remaining_secs)

        state["paused"] = False
        state["remaining_deadline_seconds"] = None
        state["deadline_at"] = new_deadline.isoformat()
        await save_state(battle_id, state)

        # Re-add deadline to ZSET for the current actor
        rds = await get_redis_client()
        next_actor = state["next_actor"]
        member = f"{battle_id}:{next_actor}"
        await rds.zadd(ZSET_DEADLINES, {member: new_deadline.timestamp()})

    # Notify all participants: "Бой продолжается!"
    participants_result = await db.execute(
        text("""
            SELECT DISTINCT c.user_id
            FROM battle_participants bp
            JOIN characters c ON bp.character_id = c.id
            WHERE bp.battle_id = :bid AND c.is_npc = 0
        """),
        {"bid": battle_id},
    )
    for row in participants_result.fetchall():
        try:
            await publish_notification(
                target_user_id=row[0],
                message="Бой продолжается!",
                ws_type="battle_resumed",
                ws_data={"battle_id": battle_id},
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления при возобновлении боя: {e}")

    logger.info(f"Battle {battle_id} resumed")
    return True


async def _auto_reject_pending_join_requests(db: AsyncSession, battle_id: int) -> None:
    """Auto-reject all pending join requests when a battle finishes."""
    await db.execute(
        text("""
            UPDATE battle_join_requests
            SET status = 'rejected', reviewed_at = NOW()
            WHERE battle_id = :bid AND status = 'pending'
        """),
        {"bid": battle_id},
    )
    await db.commit()


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
    # 1.1. Check if battle is paused (join request being reviewed)
    # ------------------------------------------------------------------------------
    if battle_state.get("paused"):
        raise HTTPException(400, "Бой приостановлен — рассматриваются заявки на присоединение")

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
    # 8. Использование предмета из fast-слота (одноразовое)
    # ------------------------------------------------------------------------------
    item_id = request.skills.item_id  # может быть None / 0 / >0

    if item_id and item_id > 0:
        me = str(request.participant_id)
        part = battle_state["participants"][me]

        # 1) Find matching slot by item_id in fast_slots
        matched_slot = None
        matched_idx = None
        for idx, slot in enumerate(part.get("fast_slots", [])):
            if slot["item_id"] == item_id:
                matched_slot = slot
                matched_idx = idx
                break

        if matched_slot is None:
            logger.warning(f"[ITEM] item_id={item_id} not found in fast_slots for participant {me}, skipping")
        else:
            # 2) Try to consume item in inventory (best-effort, does not block usage)
            try:
                consume_result = await consume_item(attacker_character_id, item_id)
                if consume_result.get("status") != "ok":
                    logger.warning(
                        f"[ITEM] Failed to consume item_id={item_id} in inventory for character "
                        f"{attacker_character_id}: {consume_result.get('detail', 'unknown error')}"
                    )
            except Exception as exc:
                logger.warning(f"[ITEM] consume_item call failed for item_id={item_id}: {exc}")

            # 3) Apply recovery from CACHED slot fields (always — slot exists in battle)
            recovery_payload = {
                key.replace("_recovery", ""): matched_slot[key]
                for key in (
                    "health_recovery",
                    "mana_recovery",
                    "energy_recovery",
                    "stamina_recovery",
                )
                if matched_slot.get(key)
            }

            for res, delta in recovery_payload.items():
                old = part[res if res != "health" else "hp"]
                mx = part[f"max_{res if res != 'health' else 'hp'}"]
                new = min(old + delta, mx)
                part[res if res != "health" else "hp"] = new

            # 4) Remove used slot from fast_slots array (one-time use)
            part["fast_slots"].pop(matched_idx)

            # 5) Log item_use event
            turn_events.append({
                "event": "item_use",
                "who": request.participant_id,
                "item_id": item_id,
                "item_name": matched_slot.get("name", f"item#{item_id}"),
                "recovery": recovery_payload,
            })
            logger.debug(
                f"[ITEM] consumed item_id={item_id}, recovery={recovery_payload}"
            )

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

        # Auto-reject all pending join requests
        await _auto_reject_pending_join_requests(db_session, battle_id)

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

        # PvP post-battle consequences: training duel → set loser HP to 1
        if winner_team is not None:
            try:
                bt_result = await db_session.execute(
                    text("SELECT battle_type FROM battles WHERE id = :bid"),
                    {"bid": battle_id},
                )
                bt_row = bt_result.fetchone()
                if bt_row and bt_row[0] == "pvp_training":
                    for pid_str, pdata in battle_state["participants"].items():
                        if pdata["hp"] <= 0 and pdata["team"] != winner_team:
                            await db_session.execute(
                                text("UPDATE character_attributes SET current_health = 1 WHERE character_id = :cid"),
                                {"cid": pdata["character_id"]},
                            )
                            await db_session.commit()
                            logger.info(
                                f"PvP training: HP персонажа {pdata['character_id']} установлен в 1"
                            )
                elif bt_row and bt_row[0] == "pvp_death":
                    for pid_str, pdata in battle_state["participants"].items():
                        if pdata["hp"] <= 0 and pdata["team"] != winner_team:
                            loser_char_id = pdata["character_id"]
                            # Fetch loser's user_id BEFORE unlink (it will be set to NULL)
                            loser_user_id = None
                            try:
                                loser_user_result = await db_session.execute(
                                    text("SELECT user_id FROM characters WHERE id = :cid"),
                                    {"cid": loser_char_id},
                                )
                                loser_user_row = loser_user_result.fetchone()
                                if loser_user_row:
                                    loser_user_id = loser_user_row[0]
                            except Exception as lookup_err:
                                logger.error(
                                    f"PvP death: ошибка поиска user_id для персонажа "
                                    f"{loser_char_id}: {lookup_err}"
                                )
                            # Unlink loser's character via character-service internal endpoint
                            try:
                                async with httpx.AsyncClient(timeout=10.0) as client:
                                    resp = await client.post(
                                        f"{settings.CHARACTER_SERVICE_URL}/characters/internal/unlink",
                                        json={"character_id": loser_char_id},
                                    )
                                    if resp.status_code == 200:
                                        logger.info(
                                            f"PvP death: персонаж {loser_char_id} отвязан от пользователя"
                                        )
                                    else:
                                        logger.error(
                                            f"PvP death: ошибка отвязки персонажа {loser_char_id}: "
                                            f"{resp.status_code} - {resp.text}"
                                        )
                            except httpx.RequestError as exc:
                                logger.error(
                                    f"PvP death: не удалось связаться с character-service для отвязки "
                                    f"персонажа {loser_char_id}: {exc}"
                                )
                            # Send notification to loser about character loss
                            if loser_user_id:
                                try:
                                    await publish_notification(
                                        target_user_id=loser_user_id,
                                        message="Ваш персонаж погиб в смертельном бою! Персонаж отвязан от аккаунта.",
                                        ws_type="pvp_death_character_lost",
                                        ws_data={"character_id": loser_char_id},
                                    )
                                except Exception as notify_err:
                                    logger.error(
                                        f"PvP death: ошибка отправки уведомления для персонажа "
                                        f"{loser_char_id}: {notify_err}"
                                    )
                            else:
                                logger.warning(
                                    f"PvP death: не удалось отправить уведомление — "
                                    f"user_id не найден для персонажа {loser_char_id}"
                                )
            except Exception as e:
                logger.error(f"Ошибка при обработке последствий PvP-боя: {e}")

        # PvE rewards: check if defeated participant is a mob
        battle_rewards = None
        if winner_team is not None:
            battle_rewards = await _distribute_pve_rewards(
                battle_state, winner_team, turn_events
            )

        # Store rewards in Redis state so frontend can read them via polling
        if battle_rewards:
            battle_state["rewards"] = battle_rewards.dict()
            await save_state(battle_id, battle_state)

        # NPC death: mark defeated NPCs (not mobs) as dead
        if winner_team is not None:
            for pid_str, pdata in battle_state["participants"].items():
                if pdata["hp"] <= 0 and pdata["team"] != winner_team:
                    defeated_char_id = pdata["character_id"]
                    try:
                        npc_check = await db_session.execute(
                            text(
                                "SELECT is_npc, npc_role FROM characters "
                                "WHERE id = :cid AND is_npc = 1 AND (npc_role IS NULL OR npc_role != 'mob')"
                            ),
                            {"cid": defeated_char_id},
                        )
                        npc_row = npc_check.fetchone()
                        if npc_row:
                            try:
                                async with httpx.AsyncClient(timeout=10.0) as client:
                                    resp = await client.put(
                                        f"{settings.CHARACTER_SERVICE_URL}/characters/internal/npc-status/{defeated_char_id}",
                                        json={"status": "dead"},
                                    )
                                    if resp.status_code == 200:
                                        logger.info(
                                            f"NPC death: NPC {defeated_char_id} помечен как dead"
                                        )
                                    else:
                                        logger.error(
                                            f"NPC death: ошибка обновления статуса NPC {defeated_char_id}: "
                                            f"{resp.status_code} - {resp.text}"
                                        )
                            except httpx.RequestError as exc:
                                logger.error(
                                    f"NPC death: не удалось связаться с character-service "
                                    f"для NPC {defeated_char_id}: {exc}"
                                )
                    except Exception as e:
                        logger.error(f"NPC death: ошибка проверки NPC {defeated_char_id}: {e}")

        # Save battle history to MySQL
        try:
            # Query battle_type from DB
            bh_bt_result = await db_session.execute(
                text("SELECT battle_type FROM battles WHERE id = :bid"),
                {"bid": battle_id},
            )
            bh_bt_row = bh_bt_result.fetchone()
            bh_battle_type = bh_bt_row[0] if bh_bt_row else "pve"

            # Get character names from snapshot (MongoDB/Redis) — avoids charset issues with raw SQL
            names_map = {}
            try:
                rds = await get_redis_client()
                snapshot = await get_cached_snapshot(rds, battle_id)
                if snapshot is None:
                    snap_doc = await load_snapshot(battle_id)
                    if snap_doc:
                        snapshot = snap_doc.get("participants", [])
                if snapshot:
                    for p in snapshot:
                        names_map[p["character_id"]] = p.get("name", f"Персонаж #{p['character_id']}")
            except Exception as snap_err:
                logger.warning(f"[HISTORY] Failed to load snapshot for names: {snap_err}")

            logger.info(f"[HISTORY] names_map from snapshot: {names_map}")

            for pid_str, pdata in battle_state["participants"].items():
                char_id = pdata["character_id"]
                char_name = names_map.get(char_id, f"Персонаж #{char_id}")
                is_winner = (winner_team is not None
                             and pdata["team"] == winner_team
                             and pdata["hp"] > 0)
                result_val = BattleResult.victory if is_winner else BattleResult.defeat

                # Collect opponent info
                opp_names = []
                opp_ids = []
                for other_pid, other_pdata in battle_state["participants"].items():
                    if other_pid != pid_str:
                        other_id = other_pdata["character_id"]
                        opp_names.append(names_map.get(other_id, f"Персонаж #{other_id}"))
                        opp_ids.append(other_id)

                history_entry = BattleHistory(
                    battle_id=battle_id,
                    character_id=char_id,
                    character_name=char_name,
                    opponent_names=opp_names,
                    opponent_character_ids=opp_ids,
                    battle_type=bh_battle_type,
                    result=result_val,
                    finished_at=datetime.utcnow(),
                )
                db_session.add(history_entry)

            await db_session.commit()
            logger.info(f"Battle history saved for battle {battle_id}")
        except Exception as e:
            logger.error(f"Failed to save battle history for battle {battle_id}: {e}")

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

# ---------------------------------------------------------------------------
# PvP: "Character in battle" check (Task 1.3)
# ---------------------------------------------------------------------------
@router.get("/character/{character_id}/in-battle", response_model=InBattleResponse)
async def check_character_in_battle(
    character_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Check if a character is currently in an active battle (no auth — internal)."""
    battle_id = await get_active_battle_for_character(db, character_id)
    if battle_id:
        return InBattleResponse(in_battle=True, battle_id=battle_id)
    return InBattleResponse(in_battle=False)


# ---------------------------------------------------------------------------
# PvP: Send invitation (Task 1.4)
# ---------------------------------------------------------------------------
PVP_INVITE_EXPIRY_HOURS = 3


async def _get_character_info(db: AsyncSession, character_id: int) -> dict | None:
    """Fetch basic character info from shared DB."""
    result = await db.execute(
        text("SELECT id, user_id, current_location_id, level FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "current_location_id": row[2],
        "level": row[3],
    }


async def _get_character_name(db: AsyncSession, character_id: int) -> str:
    """Fetch character name from shared DB."""
    result = await db.execute(
        text("SELECT name FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )
    row = result.fetchone()
    return row[0] if row else f"Персонаж #{character_id}"


async def _get_character_profile_info(db: AsyncSession, character_id: int) -> dict:
    """Fetch character name, avatar, level from shared DB."""
    result = await db.execute(
        text("SELECT name, avatar, level FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )
    row = result.fetchone()
    if not row:
        return {"name": f"Персонаж #{character_id}", "avatar": None, "level": 0}
    return {"name": row[0], "avatar": row[1], "level": row[2]}


@router.post("/pvp/invite", response_model=PvpInviteResponse, status_code=201)
async def send_pvp_invitation(
    req: PvpInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Send a PvP duel invitation (training or death duel)."""
    # Validate battle_type
    if req.battle_type not in ("pvp_training", "pvp_death"):
        raise HTTPException(400, "Недопустимый тип боя")

    # Cannot invite yourself
    if req.initiator_character_id == req.target_character_id:
        raise HTTPException(400, "Вы не можете вызвать самого себя")

    # Ownership check
    initiator = await _get_character_info(db, req.initiator_character_id)
    if not initiator:
        raise HTTPException(404, "Персонаж не найден")
    if initiator["user_id"] != current_user.id:
        raise HTTPException(403, "Вы должны использовать своего персонажа")

    # Target exists
    target = await _get_character_info(db, req.target_character_id)
    if not target:
        raise HTTPException(404, "Целевой персонаж не найден")

    # Same location
    if initiator["current_location_id"] != target["current_location_id"]:
        raise HTTPException(400, "Персонажи должны находиться в одной локации")

    # Not in battle
    if await get_active_battle_for_character(db, req.initiator_character_id):
        raise HTTPException(400, "Персонаж уже в бою")
    if await get_active_battle_for_character(db, req.target_character_id):
        raise HTTPException(400, "Целевой персонаж уже в бою")

    # No duplicate pending invitation
    dup_result = await db.execute(
        text("""
            SELECT id FROM pvp_invitations
            WHERE initiator_character_id = :init_id
              AND target_character_id = :target_id
              AND status = 'pending'
            LIMIT 1
        """),
        {"init_id": req.initiator_character_id, "target_id": req.target_character_id},
    )
    if dup_result.fetchone():
        raise HTTPException(409, "У вас уже есть активное приглашение для этого игрока")

    # Phase 2 validations for pvp_death (level 30+, not safe location)
    if req.battle_type == "pvp_death":
        if initiator["level"] < 30 or target["level"] < 30:
            raise HTTPException(400, "Оба персонажа должны быть 30+ уровня для смертельного боя")
        loc_result = await db.execute(
            text("SELECT marker_type FROM Locations WHERE id = :lid"),
            {"lid": initiator["current_location_id"]},
        )
        loc_row = loc_result.fetchone()
        if loc_row and loc_row[0] == "safe":
            raise HTTPException(400, "Смертельный бой невозможен на безопасной локации")

    # Create invitation
    from datetime import timedelta
    expires_at = datetime.utcnow() + timedelta(hours=PVP_INVITE_EXPIRY_HOURS)
    invitation = PvpInvitation(
        initiator_character_id=req.initiator_character_id,
        target_character_id=req.target_character_id,
        location_id=initiator["current_location_id"],
        battle_type=req.battle_type,
        status=PvpInvitationStatus.pending,
        expires_at=expires_at,
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # Send notification to target user
    initiator_name = await _get_character_name(db, req.initiator_character_id)
    battle_type_label = "тренировочный бой" if req.battle_type == "pvp_training" else "смертельный бой"
    await publish_notification(
        target_user_id=target["user_id"],
        message=f"{initiator_name} вызывает вас на {battle_type_label}!",
        ws_type="pvp_invitation",
        ws_data={
            "invitation_id": invitation.id,
            "initiator_name": initiator_name,
            "battle_type": req.battle_type,
        },
    )

    return PvpInviteResponse(
        invitation_id=invitation.id,
        initiator_character_id=invitation.initiator_character_id,
        target_character_id=invitation.target_character_id,
        battle_type=invitation.battle_type,
        status=invitation.status.value if hasattr(invitation.status, 'value') else invitation.status,
        expires_at=invitation.expires_at,
    )


# ---------------------------------------------------------------------------
# PvP: Respond to invitation (Task 1.4)
# ---------------------------------------------------------------------------
@router.post("/pvp/invite/{invitation_id}/respond", response_model=PvpRespondAcceptResponse)
async def respond_to_pvp_invitation(
    invitation_id: int,
    req: PvpRespondRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Accept or decline a PvP duel invitation."""
    if req.action not in ("accept", "decline"):
        raise HTTPException(400, "Действие должно быть 'accept' или 'decline'")

    # Fetch invitation
    result = await db.execute(
        text("SELECT * FROM pvp_invitations WHERE id = :iid"),
        {"iid": invitation_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Приглашение не найдено")

    inv_id = row[0]
    init_char_id = row[1]
    target_char_id = row[2]
    location_id = row[3]
    inv_battle_type = row[4]
    inv_status = row[5]
    inv_expires_at = row[7]

    # Must be pending
    if inv_status != "pending":
        raise HTTPException(400, "Приглашение уже было обработано")

    # Check expiry
    if datetime.utcnow() > inv_expires_at:
        await db.execute(
            text("UPDATE pvp_invitations SET status = 'expired' WHERE id = :iid"),
            {"iid": invitation_id},
        )
        await db.commit()
        raise HTTPException(400, "Приглашение истекло")

    # Must be the target character's owner
    target = await _get_character_info(db, target_char_id)
    if not target or target["user_id"] != current_user.id:
        raise HTTPException(403, "Это приглашение адресовано другому игроку")

    initiator_name = await _get_character_name(db, init_char_id)
    target_name = await _get_character_name(db, target_char_id)
    initiator = await _get_character_info(db, init_char_id)

    if req.action == "decline":
        await db.execute(
            text("UPDATE pvp_invitations SET status = 'declined' WHERE id = :iid"),
            {"iid": invitation_id},
        )
        await db.commit()

        # Notify initiator
        if initiator:
            await publish_notification(
                target_user_id=initiator["user_id"],
                message=f"{target_name} отклонил ваш вызов на бой.",
            )

        return PvpRespondAcceptResponse(
            invitation_id=invitation_id,
            status="declined",
        )

    # --- ACCEPT ---
    # Re-validate: same location, not in battle
    if not initiator:
        raise HTTPException(400, "Персонаж инициатора не найден")
    if initiator["current_location_id"] != target["current_location_id"]:
        raise HTTPException(400, "Персонажи должны находиться в одной локации")
    if await get_active_battle_for_character(db, init_char_id):
        raise HTTPException(400, "Персонаж инициатора уже в бою")
    if await get_active_battle_for_character(db, target_char_id):
        raise HTTPException(400, "Персонаж уже в бою")

    # Update invitation status
    await db.execute(
        text("UPDATE pvp_invitations SET status = 'accepted' WHERE id = :iid"),
        {"iid": invitation_id},
    )
    await db.commit()

    # Create battle (derive location_id from initiator)
    pvp_location_id = initiator["current_location_id"] if initiator else None
    bt = BattleType(inv_battle_type)
    battle_obj, participant_objs = await create_battle(
        db,
        player_ids=[init_char_id, target_char_id],
        teams=[0, 1],
        battle_type=bt,
        location_id=pvp_location_id,
    )

    # Initialize Redis state (same pattern as create_battle_endpoint)
    from datetime import timedelta
    first_actor_pid = participant_objs[0].id
    moscow_tz = timezone(timedelta(hours=3))
    deadline = datetime.now(timezone.utc).astimezone(moscow_tz) + timedelta(hours=settings.TURN_TIMEOUT_HOURS)

    participants_info = []
    for p in participant_objs:
        participants_info.append(
            await build_participant_info(p.character_id, p.id)
        )

    participants_payload = []
    for snap in participants_info:
        participants_payload.append({
            "participant_id": snap["participant_id"],
            "character_id": snap["character_id"],
            "team": next(
                pl.team for pl in participant_objs
                if pl.id == snap["participant_id"]
            ),
            "hp": snap["attributes"]["current_health"],
            "mana": snap["attributes"]["current_mana"],
            "energy": snap["attributes"]["current_energy"],
            "stamina": snap["attributes"]["current_stamina"],
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

    # Notify initiator about acceptance
    battle_type_label = "тренировочный бой" if inv_battle_type == "pvp_training" else "смертельный бой"
    await publish_notification(
        target_user_id=initiator["user_id"],
        message=f"{target_name} принял ваш вызов на {battle_type_label}! Бой начинается.",
        ws_type="pvp_battle_start",
        ws_data={
            "battle_id": battle_obj.id,
            "opponent_name": target_name,
            "battle_type": inv_battle_type,
        },
    )
    # Also notify target (the acceptor) with battle start info
    await publish_notification(
        target_user_id=target["user_id"],
        message=f"Бой с {initiator_name} начинается!",
        ws_type="pvp_battle_start",
        ws_data={
            "battle_id": battle_obj.id,
            "opponent_name": initiator_name,
            "battle_type": inv_battle_type,
        },
    )

    return PvpRespondAcceptResponse(
        invitation_id=invitation_id,
        status="accepted",
        battle_id=battle_obj.id,
        battle_url=f"/battle/{battle_obj.id}",
    )


# ---------------------------------------------------------------------------
# PvP: Get pending invitations (Task 1.4)
# ---------------------------------------------------------------------------
@router.get("/pvp/invitations/pending", response_model=PendingInvitationsResponse)
async def get_pending_invitations(
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Get all pending PvP invitations for the current user."""
    # Get all character IDs owned by the current user
    char_result = await db.execute(
        text("SELECT id FROM characters WHERE user_id = :uid"),
        {"uid": current_user.id},
    )
    user_char_ids = [r[0] for r in char_result.fetchall()]
    if not user_char_ids:
        return PendingInvitationsResponse(incoming=[], outgoing=[])

    # Incoming invitations (user is target)
    placeholders = ", ".join(f":c{i}" for i in range(len(user_char_ids)))
    params = {f"c{i}": cid for i, cid in enumerate(user_char_ids)}

    incoming_result = await db.execute(
        text(f"""
            SELECT id, initiator_character_id, battle_type, created_at, expires_at
            FROM pvp_invitations
            WHERE target_character_id IN ({placeholders})
              AND status = 'pending'
              AND expires_at > NOW()
            ORDER BY created_at DESC
        """),
        params,
    )
    incoming_rows = incoming_result.fetchall()

    incoming = []
    for row in incoming_rows:
        profile = await _get_character_profile_info(db, row[1])
        incoming.append(IncomingInvitation(
            invitation_id=row[0],
            initiator_character_id=row[1],
            initiator_name=profile["name"],
            initiator_avatar=profile["avatar"],
            initiator_level=profile["level"],
            battle_type=row[2],
            created_at=row[3],
            expires_at=row[4],
        ))

    # Outgoing invitations (user is initiator)
    outgoing_result = await db.execute(
        text(f"""
            SELECT id, target_character_id, battle_type, status, created_at
            FROM pvp_invitations
            WHERE initiator_character_id IN ({placeholders})
              AND status = 'pending'
              AND expires_at > NOW()
            ORDER BY created_at DESC
        """),
        params,
    )
    outgoing_rows = outgoing_result.fetchall()

    outgoing = []
    for row in outgoing_rows:
        target_name = await _get_character_name(db, row[1])
        outgoing.append(OutgoingInvitation(
            invitation_id=row[0],
            target_character_id=row[1],
            target_name=target_name,
            battle_type=row[2],
            status=row[3],
            created_at=row[4],
        ))

    return PendingInvitationsResponse(incoming=incoming, outgoing=outgoing)


# ---------------------------------------------------------------------------
# PvP: Cancel invitation (Task 1.4)
# ---------------------------------------------------------------------------
@router.delete("/pvp/invite/{invitation_id}", response_model=CancelInvitationResponse)
async def cancel_pvp_invitation(
    invitation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Cancel a pending PvP invitation (only initiator can cancel)."""
    result = await db.execute(
        text("SELECT id, initiator_character_id, status FROM pvp_invitations WHERE id = :iid"),
        {"iid": invitation_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Приглашение не найдено")

    if row[2] != "pending":
        raise HTTPException(400, "Приглашение уже было обработано")

    # Verify ownership of initiator character
    init_info = await _get_character_info(db, row[1])
    if not init_info or init_info["user_id"] != current_user.id:
        raise HTTPException(403, "Вы можете отменять только свои приглашения")

    await db.execute(
        text("UPDATE pvp_invitations SET status = 'cancelled' WHERE id = :iid"),
        {"iid": invitation_id},
    )
    await db.commit()

    return CancelInvitationResponse(invitation_id=invitation_id, status="cancelled")


# ---------------------------------------------------------------------------
# PvP: Attack (forced PvP, Task 1.5)
# ---------------------------------------------------------------------------
@router.post("/pvp/attack", response_model=PvpAttackResponse, status_code=201)
async def pvp_attack(
    req: PvpAttackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Force a PvP attack without consent. Not available on safe locations."""
    # Cannot attack yourself
    if req.attacker_character_id == req.victim_character_id:
        raise HTTPException(400, "Нельзя напасть на самого себя")

    # Ownership check
    attacker = await _get_character_info(db, req.attacker_character_id)
    if not attacker:
        raise HTTPException(404, "Персонаж не найден")
    if attacker["user_id"] != current_user.id:
        raise HTTPException(403, "Вы должны использовать своего персонажа")

    # Target exists
    victim = await _get_character_info(db, req.victim_character_id)
    if not victim:
        raise HTTPException(404, "Целевой персонаж не найден")

    # Same location
    if attacker["current_location_id"] != victim["current_location_id"]:
        raise HTTPException(400, "Персонажи должны находиться в одной локации")

    # Location must not be safe
    loc_result = await db.execute(
        text("SELECT marker_type FROM Locations WHERE id = :lid"),
        {"lid": attacker["current_location_id"]},
    )
    loc_row = loc_result.fetchone()
    if loc_row and loc_row[0] == "safe":
        raise HTTPException(400, "Нападение невозможно на безопасной локации")

    # Not in battle
    if await get_active_battle_for_character(db, req.attacker_character_id):
        raise HTTPException(400, "Персонаж уже в бою")
    if await get_active_battle_for_character(db, req.victim_character_id):
        raise HTTPException(400, "Целевой персонаж уже в бою")

    # Create battle immediately (derive location_id from attacker)
    attack_location_id = attacker["current_location_id"] if attacker else None
    battle_obj, participant_objs = await create_battle(
        db,
        player_ids=[req.attacker_character_id, req.victim_character_id],
        teams=[0, 1],
        battle_type=BattleType.pvp_attack,
        location_id=attack_location_id,
    )

    # Initialize Redis state (same pattern as create_battle_endpoint)
    from datetime import timedelta
    first_actor_pid = participant_objs[0].id
    moscow_tz = timezone(timedelta(hours=3))
    deadline = datetime.now(timezone.utc).astimezone(moscow_tz) + timedelta(hours=settings.TURN_TIMEOUT_HOURS)

    participants_info = []
    for p in participant_objs:
        participants_info.append(
            await build_participant_info(p.character_id, p.id)
        )

    participants_payload = []
    for snap in participants_info:
        participants_payload.append({
            "participant_id": snap["participant_id"],
            "character_id": snap["character_id"],
            "team": next(
                pl.team for pl in participant_objs
                if pl.id == snap["participant_id"]
            ),
            "hp": snap["attributes"]["current_health"],
            "mana": snap["attributes"]["current_mana"],
            "energy": snap["attributes"]["current_energy"],
            "stamina": snap["attributes"]["current_stamina"],
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

    # Notify victim
    attacker_name = await _get_character_name(db, req.attacker_character_id)
    await publish_notification(
        target_user_id=victim["user_id"],
        message=f"{attacker_name} напал на вас! Бой начинается.",
        ws_type="pvp_battle_start",
        ws_data={
            "battle_id": battle_obj.id,
            "attacker_name": attacker_name,
            "battle_type": "pvp_attack",
        },
    )

    return PvpAttackResponse(
        battle_id=battle_obj.id,
        battle_url=f"/battle/{battle_obj.id}",
        attacker_character_id=req.attacker_character_id,
        victim_character_id=req.victim_character_id,
    )


# ---------------------------------------------------------------------------
# Battle History endpoint (FEAT-065)
# ---------------------------------------------------------------------------
@router.get("/history/{character_id}", response_model=BattleHistoryResponse)
async def get_battle_history(
    character_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    battle_type: str | None = Query(None),
    result: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: paginated battle history with stats for a character."""
    # Build WHERE clause for filtered history query
    conditions = ["character_id = :cid"]
    params: dict = {"cid": character_id}

    if battle_type:
        conditions.append("battle_type = :bt")
        params["bt"] = battle_type
    if result:
        conditions.append("result = :res")
        params["res"] = result

    where = " AND ".join(conditions)

    # Stats query — PvP only (pvp_training, pvp_death, pvp_attack)
    stats_result = await db.execute(
        text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result = 'victory' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'defeat' THEN 1 ELSE 0 END) as losses
            FROM battle_history
            WHERE character_id = :cid AND battle_type != 'pve'
        """),
        {"cid": character_id},
    )
    stats_row = stats_result.fetchone()
    total = stats_row[0] or 0
    wins = stats_row[1] or 0
    losses = stats_row[2] or 0
    winrate = round((wins / total) * 100, 1) if total > 0 else 0.0

    # Count query (with filters)
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM battle_history WHERE {where}"),
        params,
    )
    total_count = count_result.scalar() or 0
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    # Paginated history query
    offset = (page - 1) * per_page
    rows = await db.execute(
        text(f"""
            SELECT battle_id, opponent_names, opponent_character_ids,
                   battle_type, result, finished_at
            FROM battle_history
            WHERE {where}
            ORDER BY finished_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": per_page, "offset": offset},
    )

    history = []
    for row in rows.fetchall():
        raw_names = row[1]
        raw_ids = row[2]
        opp_names = raw_names if isinstance(raw_names, list) else (json.loads(raw_names) if isinstance(raw_names, str) else [])
        opp_ids = raw_ids if isinstance(raw_ids, list) else (json.loads(raw_ids) if isinstance(raw_ids, str) else [])
        history.append(BattleHistoryItem(
            battle_id=row[0],
            opponent_names=opp_names,
            opponent_character_ids=opp_ids,
            battle_type=row[3],
            result=row[4],
            finished_at=row[5],
        ))

    return BattleHistoryResponse(
        history=history,
        stats=BattleStats(total=total, wins=wins, losses=losses, winrate=winrate),
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Admin endpoints — battle monitor (FEAT-067)
# ---------------------------------------------------------------------------

@router.get("/admin/active", response_model=AdminBattleListResponse)
async def admin_list_active_battles(
    battle_type: str | None = Query(default=None, description="Filter by battle type"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: UserRead = Depends(require_permission("battles:manage")),
):
    """List all active battles (pending / in_progress) with participant info."""

    # Build WHERE clause
    where = "b.status IN ('pending', 'in_progress')"
    params: dict = {}
    if battle_type:
        where += " AND b.battle_type = :bt"
        params["bt"] = battle_type

    # Total count
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM battles b WHERE {where}"),
        params,
    )
    total = count_result.scalar() or 0

    # Paginated battle IDs
    offset = (page - 1) * per_page
    battles_result = await db.execute(
        text(f"""
            SELECT b.id, b.status, b.battle_type, b.created_at, b.updated_at
            FROM battles b
            WHERE {where}
            ORDER BY b.created_at DESC
            LIMIT :lim OFFSET :off
        """),
        {**params, "lim": per_page, "off": offset},
    )
    battle_rows = battles_result.fetchall()

    if not battle_rows:
        return AdminBattleListResponse(battles=[], total=total, page=page, per_page=per_page)

    # Collect battle IDs and fetch participants + character info
    battle_ids = [r[0] for r in battle_rows]
    placeholders = ", ".join(f":bid{i}" for i in range(len(battle_ids)))
    bid_params = {f"bid{i}": bid for i, bid in enumerate(battle_ids)}

    parts_result = await db.execute(
        text(f"""
            SELECT bp.battle_id, bp.id AS participant_id, bp.character_id, bp.team,
                   c.name, c.level, c.is_npc
            FROM battle_participants bp
            JOIN characters c ON c.id = bp.character_id
            WHERE bp.battle_id IN ({placeholders})
            ORDER BY bp.battle_id, bp.id
        """),
        bid_params,
    )
    part_rows = parts_result.fetchall()

    # Group participants by battle_id
    parts_by_battle: dict[int, list[AdminBattleParticipant]] = {}
    for pr in part_rows:
        bid = pr[0]
        parts_by_battle.setdefault(bid, []).append(
            AdminBattleParticipant(
                participant_id=pr[1],
                character_id=pr[2],
                team=pr[3],
                character_name=pr[4] or f"Персонаж #{pr[2]}",
                level=pr[5] or 1,
                is_npc=bool(pr[6]),
            )
        )

    battles = []
    for br in battle_rows:
        battles.append(AdminBattleListItem(
            id=br[0],
            status=br[1],
            battle_type=br[2],
            created_at=br[3],
            updated_at=br[4],
            participants=parts_by_battle.get(br[0], []),
        ))

    return AdminBattleListResponse(battles=battles, total=total, page=page, per_page=per_page)


@router.get("/admin/{battle_id}/state", response_model=AdminBattleStateResponse)
async def admin_get_battle_state(
    battle_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: UserRead = Depends(require_permission("battles:manage")),
):
    """Get full battle state for admin viewing (no ownership check)."""

    # Verify battle exists in MySQL
    battle = await get_battle(db, battle_id)
    if not battle:
        raise HTTPException(status_code=404, detail="Бой не найден")

    battle_dict = {
        "id": battle.id,
        "status": battle.status.value if hasattr(battle.status, "value") else str(battle.status),
        "battle_type": battle.battle_type.value if hasattr(battle.battle_type, "value") else str(battle.battle_type),
        "created_at": battle.created_at.isoformat() if battle.created_at else None,
    }

    # Load Redis state
    state = await load_state(battle_id)
    has_redis_state = state is not None

    # Load snapshot from Redis cache or MongoDB fallback
    rds = await get_redis_client()
    snapshot = await get_cached_snapshot(rds, battle_id)
    if snapshot is None:
        snap_doc = await load_snapshot(battle_id)
        if snap_doc:
            snapshot = snap_doc.get("participants")
            if snapshot:
                await cache_snapshot(rds, battle_id, snapshot)

    runtime = None
    if state is not None:
        runtime = {
            "turn_number": state["turn_number"],
            "deadline_at": state["deadline_at"],
            "current_actor": state["next_actor"],
            "next_actor": next_pid_after(state["next_actor"], state["turn_order"]),
            "first_actor": state["first_actor"],
            "turn_order": state["turn_order"],
            "total_turns": state.get("total_turns", 0),
            "last_turn": state.get("last_turn", 0),
            "participants": {
                pid: {
                    "hp": state["participants"][pid]["hp"],
                    "mana": state["participants"][pid]["mana"],
                    "energy": state["participants"][pid]["energy"],
                    "stamina": state["participants"][pid]["stamina"],
                    "max_hp": state["participants"][pid].get("max_hp", 0),
                    "max_mana": state["participants"][pid].get("max_mana", 0),
                    "max_energy": state["participants"][pid].get("max_energy", 0),
                    "max_stamina": state["participants"][pid].get("max_stamina", 0),
                    "cooldowns": state["participants"][pid]["cooldowns"],
                    "fast_slots": state["participants"][pid].get("fast_slots", []),
                    "team": state["participants"][pid]["team"],
                    "character_id": state["participants"][pid]["character_id"],
                }
                for pid in state["participants"]
            },
            "active_effects": state.get("active_effects", {}),
        }

    return AdminBattleStateResponse(
        battle=battle_dict,
        snapshot=snapshot,
        runtime=runtime,
        has_redis_state=has_redis_state,
    )


@router.post("/admin/{battle_id}/force-finish", response_model=AdminForceFinishResponse)
async def admin_force_finish_battle(
    battle_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: UserRead = Depends(require_permission("battles:manage")),
):
    """Force-finish a battle: no winner, no rewards, no PvP consequences."""

    # 1. Validate battle exists and is active
    battle = await get_battle(db, battle_id)
    if not battle:
        raise HTTPException(status_code=404, detail="Бой не найден")

    battle_status = battle.status.value if hasattr(battle.status, "value") else str(battle.status)
    if battle_status in ("finished", "forfeit"):
        raise HTTPException(status_code=400, detail="Бой уже завершён")

    # 2. Load Redis state (may be None if expired)
    state = await load_state(battle_id)

    # 3. Sync final resources back to character_attributes (if Redis state exists)
    if state:
        for pid_str, pdata in state["participants"].items():
            char_id = pdata["character_id"]
            try:
                await db.execute(
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
                await db.commit()
                logger.info(f"Force-finish: ресурсы персонажа {char_id} синхронизированы")
            except Exception as e:
                logger.error(f"Force-finish: не удалось синхронизировать ресурсы персонажа {char_id}: {e}")

    # 4. Set battle status to 'finished' in MySQL
    await finish_battle(db, battle_id)

    # 4.5. Auto-reject all pending join requests
    await _auto_reject_pending_join_requests(db, battle_id)

    # 5. Clean up Redis state and deadlines
    redis_client = await get_redis_client()
    await redis_client.delete(state_key(battle_id))

    # Clean up deadline ZSET entries
    if state:
        for pid_str in state["participants"]:
            await redis_client.zrem(ZSET_DEADLINES, f"{battle_id}:{pid_str}")

    # Clean up snapshot and turns keys
    await redis_client.delete(f"battle:{battle_id}:snapshot")
    await redis_client.delete(f"battle:{battle_id}:turns")

    # 6. Publish force-finish event via Pub/Sub to notify connected clients
    await redis_client.publish(
        f"battle:{battle_id}:your_turn",
        "force_finished",
    )

    # 7. Autobattle cleanup: with Redis state deleted, autobattle-service
    # will get 404 on next state fetch and stop acting for this battle.
    # No explicit deregistration needed.

    logger.info(f"Battle {battle_id} force-finished by admin {_admin.username}")

    return AdminForceFinishResponse(
        ok=True,
        battle_id=battle_id,
        message="Бой принудительно завершён",
    )


# ---------------------------------------------------------------------------
# Location Battles: list active battles at a location (FEAT-069 T3)
# ---------------------------------------------------------------------------
@router.get(
    "/by-location/{location_id}",
    response_model=LocationBattlesResponse,
)
async def get_battles_by_location(
    location_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Return active battles (pending/in_progress) at a given location."""
    rows = await db.execute(
        text("""
            SELECT b.id, b.status, b.battle_type, b.is_paused, b.created_at,
                   bp.id AS participant_id, bp.character_id, bp.team,
                   c.name AS character_name, c.level, c.is_npc
            FROM battles b
            JOIN battle_participants bp ON b.id = bp.battle_id
            JOIN characters c ON bp.character_id = c.id
            WHERE b.location_id = :lid
              AND b.status IN ('pending', 'in_progress')
            ORDER BY b.created_at DESC, bp.id ASC
        """),
        {"lid": location_id},
    )
    all_rows = rows.fetchall()

    # Group by battle id
    battles_map: Dict[int, dict] = {}
    for row in all_rows:
        bid = row[0]
        if bid not in battles_map:
            battles_map[bid] = {
                "id": bid,
                "status": row[1],
                "battle_type": row[2],
                "is_paused": bool(row[3]),
                "created_at": row[4],
                "participants": [],
            }
        battles_map[bid]["participants"].append(
            LocationBattleParticipant(
                participant_id=row[5],
                character_id=row[6],
                character_name=row[8],
                level=row[9],
                team=row[7],
                is_npc=bool(row[10]),
            )
        )

    battles_list = [
        LocationBattleItem(**b) for b in battles_map.values()
    ]

    return LocationBattlesResponse(battles=battles_list)


# ---------------------------------------------------------------------------
# Admin join request endpoints (FEAT-069, T6)
# NOTE: These MUST be registered BEFORE /{battle_id}/join-request* routes,
# otherwise FastAPI matches "admin" as battle_id path parameter.
# ---------------------------------------------------------------------------

@router.get("/admin/join-requests", response_model=AdminJoinRequestListResponse)
async def admin_list_join_requests(
    filter_status: str = Query(default="pending", alias="status", description="Filter by status: pending, approved, rejected"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: UserRead = Depends(require_permission("battles:manage")),
):
    """List join requests with pagination and status filter (admin)."""

    # Total count
    count_result = await db.execute(
        text("""
            SELECT COUNT(*)
            FROM battle_join_requests bjr
            WHERE bjr.status = :status
        """),
        {"status": filter_status},
    )
    total = count_result.scalar() or 0

    # Paginated results with character + battle info
    offset = (page - 1) * per_page
    result = await db.execute(
        text("""
            SELECT bjr.id, bjr.battle_id, bjr.character_id,
                   c.name AS character_name, c.level AS character_level,
                   bjr.team, bjr.status, bjr.created_at,
                   b.battle_type,
                   (SELECT COUNT(*) FROM battle_participants bp WHERE bp.battle_id = bjr.battle_id) AS participants_count
            FROM battle_join_requests bjr
            JOIN characters c ON bjr.character_id = c.id
            JOIN battles b ON bjr.battle_id = b.id
            WHERE bjr.status = :status
            ORDER BY bjr.created_at DESC
            LIMIT :lim OFFSET :off
        """),
        {"status": filter_status, "lim": per_page, "off": offset},
    )
    rows = result.fetchall()

    requests = []
    for row in rows:
        status_val = row[6]
        if hasattr(status_val, "value"):
            status_val = status_val.value
        bt_val = row[8]
        if hasattr(bt_val, "value"):
            bt_val = bt_val.value
        requests.append(AdminJoinRequestItem(
            id=row[0],
            battle_id=row[1],
            character_id=row[2],
            character_name=row[3] or f"Персонаж #{row[2]}",
            character_level=row[4] or 1,
            team=row[5],
            status=status_val,
            created_at=row[7],
            battle_type=bt_val,
            battle_participants_count=row[9],
        ))

    return AdminJoinRequestListResponse(
        requests=requests, total=total, page=page, per_page=per_page
    )


@router.post(
    "/admin/join-requests/{request_id}/approve",
    response_model=AdminJoinRequestActionResponse,
)
async def admin_approve_join_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(require_permission("battles:manage")),
):
    """Approve a join request: add player to battle, update Redis + snapshot."""

    # 1. Load request, verify pending
    req_result = await db.execute(
        text("SELECT id, battle_id, character_id, user_id, team, status FROM battle_join_requests WHERE id = :rid"),
        {"rid": request_id},
    )
    req_row = req_result.fetchone()
    if not req_row:
        raise HTTPException(404, "Заявка не найдена")

    req_status = req_row[5]
    if hasattr(req_status, "value"):
        req_status = req_status.value
    if req_status != "pending":
        raise HTTPException(400, "Заявка уже рассмотрена")

    battle_id = req_row[1]
    character_id = req_row[2]
    requester_user_id = req_row[3]
    team = req_row[4]

    # 2. Load battle, verify active
    battle = await get_battle(db, battle_id)
    if not battle:
        raise HTTPException(404, "Бой не найден")

    battle_status = battle.status.value if hasattr(battle.status, "value") else str(battle.status)
    if battle_status in ("finished", "forfeit"):
        raise HTTPException(400, "Бой уже завершён")

    # 3. Update request status
    now = datetime.utcnow()
    await db.execute(
        text("""
            UPDATE battle_join_requests
            SET status = 'approved', reviewed_at = :now, reviewed_by = :admin_id
            WHERE id = :rid
        """),
        {"now": now, "admin_id": admin.id, "rid": request_id},
    )
    await db.commit()

    # 4. Create BattleParticipant in MySQL
    new_participant = BattleParticipant(
        battle_id=battle_id,
        character_id=character_id,
        team=team,
    )
    db.add(new_participant)
    await db.commit()
    await db.refresh(new_participant)
    participant_id = new_participant.id

    # 5. Build participant info (attributes, skills, fast_slots)
    participant_info = await build_participant_info(character_id, participant_id)

    # 6. Update Redis state: add participant to participants dict + turn_order
    state = await load_state(battle_id)
    if state:
        attr = participant_info["attributes"]
        state["participants"][str(participant_id)] = {
            "character_id": character_id,
            "team": team,
            "hp": attr["current_health"],
            "mana": attr["current_mana"],
            "energy": attr["current_energy"],
            "stamina": attr["current_stamina"],
            "max_hp": attr["max_health"],
            "max_mana": attr["max_mana"],
            "max_energy": attr["max_energy"],
            "max_stamina": attr["max_stamina"],
            "fast_slots": participant_info["fast_slots"],
            "cooldowns": {},
        }
        state["turn_order"].append(participant_id)
        await save_state(battle_id, state)

    # 7. Update snapshot in MongoDB and Redis cache
    rds = await get_redis_client()
    snapshot = await get_cached_snapshot(rds, battle_id)
    if snapshot is None:
        snap_doc = await load_snapshot(battle_id)
        if snap_doc:
            snapshot = snap_doc.get("participants")

    if snapshot is not None:
        # snapshot is a list of participant dicts
        snapshot.append(participant_info)
        # Update MongoDB
        mongo_db = get_mongo_db("game")
        await mongo_db.battle_snapshots.update_one(
            {"battle_id": battle_id},
            {"$set": {"participants": snapshot}},
        )
        # Update Redis cache
        await cache_snapshot(rds, battle_id, snapshot)

    # 8. Register autobattle if NPC
    try:
        is_npc_result = await db.execute(
            text("SELECT is_npc FROM characters WHERE id = :cid"),
            {"cid": character_id},
        )
        npc_row = is_npc_result.fetchone()
        if npc_row and npc_row[0]:
            autobattle_url = os.environ.get(
                "AUTOBATTLE_SERVICE_URL", "http://autobattle-service:8011"
            )
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{autobattle_url}/autobattle/register",
                    json={
                        "battle_id": battle_id,
                        "participant_id": participant_id,
                    },
                )
    except Exception as e:
        logger.error(f"Ошибка регистрации автобоя для NPC participant {participant_id}: {e}")

    # 9. Notify the requester
    try:
        await publish_notification(
            target_user_id=requester_user_id,
            message="Ваша заявка одобрена! Вы присоединились к бою.",
            ws_type="join_request_approved",
            ws_data={"battle_id": battle_id, "request_id": request_id},
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления при одобрении заявки: {e}")

    # 10. Resume battle if no more pending requests
    await resume_battle_if_ready(db, battle_id)

    logger.info(f"Join request {request_id} approved by admin {admin.username}, participant {participant_id} added to battle {battle_id}")

    return AdminJoinRequestActionResponse(
        ok=True,
        request_id=request_id,
        message="Заявка одобрена, игрок добавлен в бой",
    )


@router.post(
    "/admin/join-requests/{request_id}/reject",
    response_model=AdminJoinRequestActionResponse,
)
async def admin_reject_join_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(require_permission("battles:manage")),
):
    """Reject a join request and notify the requester."""

    # 1. Load request, verify pending
    req_result = await db.execute(
        text("SELECT id, battle_id, user_id, status FROM battle_join_requests WHERE id = :rid"),
        {"rid": request_id},
    )
    req_row = req_result.fetchone()
    if not req_row:
        raise HTTPException(404, "Заявка не найдена")

    req_status = req_row[3]
    if hasattr(req_status, "value"):
        req_status = req_status.value
    if req_status != "pending":
        raise HTTPException(400, "Заявка уже рассмотрена")

    battle_id = req_row[1]
    requester_user_id = req_row[2]

    # 2. Update request status
    now = datetime.utcnow()
    await db.execute(
        text("""
            UPDATE battle_join_requests
            SET status = 'rejected', reviewed_at = :now, reviewed_by = :admin_id
            WHERE id = :rid
        """),
        {"now": now, "admin_id": admin.id, "rid": request_id},
    )
    await db.commit()

    # 3. Notify the requester
    try:
        await publish_notification(
            target_user_id=requester_user_id,
            message="Ваша заявка на вступление в бой отклонена.",
            ws_type="join_request_rejected",
            ws_data={"battle_id": battle_id, "request_id": request_id},
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления при отклонении заявки: {e}")

    # 4. Resume battle if no more pending requests
    await resume_battle_if_ready(db, battle_id)

    logger.info(f"Join request {request_id} rejected by admin {admin.username}")

    return AdminJoinRequestActionResponse(
        ok=True,
        request_id=request_id,
        message="Заявка отклонена",
    )


# ---------------------------------------------------------------------------
# Join Requests: submit + list (FEAT-069 T5)
# ---------------------------------------------------------------------------
@router.post(
    "/{battle_id}/join-request",
    response_model=JoinRequestResponse,
    status_code=201,
)
async def create_join_request(
    battle_id: int,
    req: JoinRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Submit a join request to an active battle."""

    # 1. Validate team
    if req.team not in (0, 1):
        raise HTTPException(400, "Команда должна быть 0 или 1")

    # 2. Battle exists and is active
    battle = await get_battle(db, battle_id)
    if not battle:
        raise HTTPException(404, "Бой не найден")
    battle_status = battle.status.value if hasattr(battle.status, "value") else str(battle.status)
    if battle_status not in ("pending", "in_progress"):
        raise HTTPException(404, "Бой не активен")

    # 3. Character belongs to current user
    await verify_character_ownership(db, req.character_id, current_user.id)

    # 4. Character is at the same location as the battle
    if not battle.location_id:
        raise HTTPException(400, "Бой не привязан к локации")
    char_result = await db.execute(
        text("SELECT current_location_id FROM characters WHERE id = :cid"),
        {"cid": req.character_id},
    )
    char_row = char_result.fetchone()
    if not char_row:
        raise HTTPException(404, "Персонаж не найден")
    if char_row[0] != battle.location_id:
        raise HTTPException(403, "Персонаж должен находиться на той же локации, что и бой")

    # 5. Character is NOT already in any active battle
    active_bid = await get_active_battle_for_character(db, req.character_id)
    if active_bid:
        raise HTTPException(400, "Персонаж уже участвует в активном бою")

    # 6. Character is not already a participant in this battle
    part_result = await db.execute(
        text("""
            SELECT id FROM battle_participants
            WHERE battle_id = :bid AND character_id = :cid
            LIMIT 1
        """),
        {"bid": battle_id, "cid": req.character_id},
    )
    if part_result.fetchone():
        raise HTTPException(400, "Персонаж уже является участником этого боя")

    # 7. No existing join request for this character in this battle
    existing_result = await db.execute(
        text("""
            SELECT id, status FROM battle_join_requests
            WHERE battle_id = :bid AND character_id = :cid
            LIMIT 1
        """),
        {"bid": battle_id, "cid": req.character_id},
    )
    existing_row = existing_result.fetchone()
    if existing_row:
        raise HTTPException(400, "Заявка на вступление в этот бой уже подана")

    # 8. Create join request
    join_request = BattleJoinRequest(
        battle_id=battle_id,
        character_id=req.character_id,
        user_id=current_user.id,
        team=req.team,
        status=JoinRequestStatus.pending,
    )
    db.add(join_request)
    await db.commit()
    await db.refresh(join_request)

    # 9. Pause battle if not already paused
    is_paused = battle.is_paused
    if not is_paused:
        await pause_battle(db, battle_id)

        # Notify all participants about pause
        participants_result = await db.execute(
            text("""
                SELECT DISTINCT c.user_id
                FROM battle_participants bp
                JOIN characters c ON bp.character_id = c.id
                WHERE bp.battle_id = :bid AND c.is_npc = 0
            """),
            {"bid": battle_id},
        )
        for row in participants_result.fetchall():
            try:
                await publish_notification(
                    target_user_id=row[0],
                    message="Бой приостановлен — рассматривается заявка на присоединение",
                    ws_type="battle_paused",
                    ws_data={"battle_id": battle_id},
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления о паузе боя: {e}")

    return JoinRequestResponse(
        id=join_request.id,
        battle_id=join_request.battle_id,
        character_id=join_request.character_id,
        team=join_request.team,
        status=join_request.status.value if hasattr(join_request.status, "value") else str(join_request.status),
        created_at=join_request.created_at,
    )


@router.get(
    "/{battle_id}/join-requests",
    response_model=JoinRequestListResponse,
)
async def list_join_requests(
    battle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """List join requests for a battle with character info."""
    result = await db.execute(
        text("""
            SELECT bjr.id, bjr.character_id, c.name, c.level, c.avatar,
                   bjr.team, bjr.status, bjr.created_at
            FROM battle_join_requests bjr
            JOIN characters c ON bjr.character_id = c.id
            WHERE bjr.battle_id = :bid
            ORDER BY bjr.created_at DESC
        """),
        {"bid": battle_id},
    )
    rows = result.fetchall()

    requests = []
    for row in rows:
        status_val = row[6]
        if hasattr(status_val, "value"):
            status_val = status_val.value
        requests.append(JoinRequestListItem(
            id=row[0],
            character_id=row[1],
            character_name=row[2],
            character_level=row[3],
            character_avatar=row[4],
            team=row[5],
            status=status_val,
            created_at=row[7],
        ))

    return JoinRequestListResponse(requests=requests)


app.include_router(router)

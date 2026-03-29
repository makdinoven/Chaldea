import math
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import httpx
from sqlalchemy import select, text, func, and_, insert, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from models import (
    BpSeason, BpLevel, BpReward, BpMission,
    BpUserProgress, BpUserReward, BpUserMissionProgress,
    BpLocationVisit, BpUserSnapshot,
)

logger = logging.getLogger(__name__)

# Stub mission types that always return 0 progress
STUB_MISSION_TYPES = {"quest_complete", "dungeon_run", "resource_gather"}


# ---------------------------------------------------------------------------
# Season queries
# ---------------------------------------------------------------------------

async def get_current_season(db: AsyncSession) -> Optional[BpSeason]:
    """Return the active season, or a season in grace period, or None."""
    now = datetime.utcnow()
    # Prefer active season with is_active=True
    result = await db.execute(
        select(BpSeason).where(
            BpSeason.is_active == True,
            BpSeason.start_date <= now,
            BpSeason.grace_end_date >= now,
        ).order_by(BpSeason.start_date.desc()).limit(1)
    )
    season = result.scalars().first()
    if season:
        return season

    # Fallback: any season where now is within start..grace_end
    result = await db.execute(
        select(BpSeason).where(
            BpSeason.start_date <= now,
            BpSeason.grace_end_date >= now,
        ).order_by(BpSeason.start_date.desc()).limit(1)
    )
    return result.scalars().first()


async def get_season_with_levels(db: AsyncSession, season_id: int) -> Optional[BpSeason]:
    """Load a season with its levels and rewards eagerly."""
    result = await db.execute(
        select(BpSeason)
        .where(BpSeason.id == season_id)
        .options(
            selectinload(BpSeason.levels).selectinload(BpLevel.rewards)
        )
    )
    return result.scalars().first()


def compute_season_status(season: BpSeason) -> str:
    now = datetime.utcnow()
    if season.start_date <= now <= season.end_date:
        return "active"
    elif season.end_date < now <= season.grace_end_date:
        return "grace"
    return "ended"


def compute_current_week(season: BpSeason) -> int:
    now = datetime.utcnow()
    days_elapsed = (now - season.start_date).days
    if days_elapsed < 0:
        return 1
    return int(math.floor(days_elapsed / 7)) + 1


def compute_total_weeks(season: BpSeason) -> int:
    total_days = (season.end_date - season.start_date).days
    return int(math.ceil(total_days / 7))


def compute_days_remaining(season: BpSeason) -> int:
    now = datetime.utcnow()
    status = compute_season_status(season)
    if status == "active":
        delta = (season.end_date - now).days
        return max(delta, 0)
    elif status == "grace":
        delta = (season.grace_end_date - now).days
        return max(delta, 0)
    return 0


# ---------------------------------------------------------------------------
# Multi-character helper
# ---------------------------------------------------------------------------

async def get_user_character_ids(db: AsyncSession, user_id: int) -> List[int]:
    """Get all non-NPC character IDs owned by a user (shared DB read)."""
    result = await db.execute(
        text("SELECT id FROM characters WHERE user_id = :uid AND is_npc = 0"),
        {"uid": user_id},
    )
    return [row[0] for row in result.fetchall()]


# ---------------------------------------------------------------------------
# User progress — lazy enrollment
# ---------------------------------------------------------------------------

async def get_or_create_user_progress(
    db: AsyncSession, user_id: int, season: BpSeason,
) -> BpUserProgress:
    """Get user progress for a season, creating it (with snapshots) on first access."""
    result = await db.execute(
        select(BpUserProgress).where(
            BpUserProgress.user_id == user_id,
            BpUserProgress.season_id == season.id,
        )
    )
    progress = result.scalars().first()
    if progress:
        return progress

    # Create new progress
    progress = BpUserProgress(
        user_id=user_id,
        season_id=season.id,
        current_level=0,
        current_xp=0,
        is_premium=False,
    )
    db.add(progress)
    await db.flush()

    # Create snapshots for all user characters
    await _create_snapshots(db, user_id, season.id)
    await db.commit()
    await db.refresh(progress)
    return progress


async def _create_snapshots(db: AsyncSession, user_id: int, season_id: int):
    """Take baseline snapshots of character stats at enrollment time."""
    char_ids = await get_user_character_ids(db, user_id)
    for char_id in char_ids:
        # Snapshot pve_kills from character_attributes
        pve_kills = await _get_pve_kills(db, char_id)
        await _upsert_snapshot(db, user_id, season_id, char_id, "pve_kills", pve_kills)

        # Snapshot level from characters
        level = await _get_character_level(db, char_id)
        await _upsert_snapshot(db, user_id, season_id, char_id, "level", level)


async def _get_pve_kills(db: AsyncSession, character_id: int) -> int:
    result = await db.execute(
        text(
            "SELECT COALESCE(pve_kills, 0) FROM character_cumulative_stats "
            "WHERE character_id = :cid LIMIT 1"
        ),
        {"cid": character_id},
    )
    row = result.fetchone()
    return row[0] if row else 0


async def _get_character_level(db: AsyncSession, character_id: int) -> int:
    result = await db.execute(
        text("SELECT COALESCE(level, 1) FROM characters WHERE id = :cid LIMIT 1"),
        {"cid": character_id},
    )
    row = result.fetchone()
    return row[0] if row else 1


async def _upsert_snapshot(
    db: AsyncSession, user_id: int, season_id: int,
    character_id: int, snapshot_type: str, value: int,
):
    """Insert snapshot if it doesn't exist (ignore duplicates)."""
    existing = await db.execute(
        select(BpUserSnapshot).where(
            BpUserSnapshot.user_id == user_id,
            BpUserSnapshot.season_id == season_id,
            BpUserSnapshot.character_id == character_id,
            BpUserSnapshot.snapshot_type == snapshot_type,
        )
    )
    if existing.scalars().first():
        return
    snapshot = BpUserSnapshot(
        user_id=user_id,
        season_id=season_id,
        character_id=character_id,
        snapshot_type=snapshot_type,
        value_at_enrollment=value,
    )
    db.add(snapshot)
    await db.flush()


# ---------------------------------------------------------------------------
# XP and level-up logic
# ---------------------------------------------------------------------------

async def award_bp_xp(
    db: AsyncSession, user_id: int, season_id: int, xp_amount: int,
) -> Dict[str, Any]:
    """Award Battle Pass XP and handle level-ups. Returns new state."""
    result = await db.execute(
        select(BpUserProgress).where(
            BpUserProgress.user_id == user_id,
            BpUserProgress.season_id == season_id,
        )
    )
    progress = result.scalars().first()
    if not progress:
        return {"new_total_xp": 0, "new_level": 0, "leveled_up": False}

    old_level = progress.current_level
    progress.current_xp += xp_amount

    # Load levels sorted
    levels_result = await db.execute(
        select(BpLevel)
        .where(BpLevel.season_id == season_id)
        .order_by(BpLevel.level_number)
    )
    levels = levels_result.scalars().all()

    # Level-up loop
    for lvl in levels:
        if lvl.level_number <= progress.current_level:
            continue
        if progress.current_xp >= lvl.required_xp:
            progress.current_xp -= lvl.required_xp
            progress.current_level = lvl.level_number
        else:
            break

    await db.commit()
    await db.refresh(progress)

    return {
        "new_total_xp": progress.current_xp,
        "new_level": progress.current_level,
        "leveled_up": progress.current_level > old_level,
    }


async def get_xp_to_next_level(
    db: AsyncSession, season_id: int, current_level: int,
) -> Optional[int]:
    """Return XP required for the next level, or None if max level."""
    result = await db.execute(
        select(BpLevel.required_xp).where(
            BpLevel.season_id == season_id,
            BpLevel.level_number == current_level + 1,
        )
    )
    row = result.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Mission progress computation
# ---------------------------------------------------------------------------

async def compute_mission_progress(
    db: AsyncSession,
    user_id: int,
    season: BpSeason,
    mission: BpMission,
) -> int:
    """Compute fresh progress for a mission from shared DB data."""
    mtype = mission.mission_type

    if mtype in STUB_MISSION_TYPES:
        return 0

    char_ids = await get_user_character_ids(db, user_id)
    if not char_ids:
        return 0

    if mtype == "kill_mobs":
        return await _progress_kill_mobs(db, user_id, season.id, char_ids)
    elif mtype == "write_posts":
        return await _progress_write_posts(db, char_ids, season.start_date)
    elif mtype == "level_up":
        return await _progress_level_up(db, user_id, season.id, char_ids)
    elif mtype == "visit_locations":
        return await _progress_visit_locations(db, user_id, season.id)
    elif mtype == "earn_gold":
        return await _progress_earn_gold(db, char_ids, season.start_date)
    elif mtype == "spend_gold":
        return await _progress_spend_gold(db, char_ids, season.start_date)

    return 0


async def _progress_kill_mobs(
    db: AsyncSession, user_id: int, season_id: int, char_ids: List[int],
) -> int:
    """current pve_kills - snapshot pve_kills, summed across characters."""
    total_delta = 0
    for cid in char_ids:
        current = await _get_pve_kills(db, cid)
        # Get snapshot
        snap_result = await db.execute(
            select(BpUserSnapshot.value_at_enrollment).where(
                BpUserSnapshot.user_id == user_id,
                BpUserSnapshot.season_id == season_id,
                BpUserSnapshot.character_id == cid,
                BpUserSnapshot.snapshot_type == "pve_kills",
            )
        )
        snap_row = snap_result.fetchone()
        snapshot_val = snap_row[0] if snap_row else 0
        total_delta += max(current - snapshot_val, 0)
    return total_delta


async def _progress_write_posts(
    db: AsyncSession, char_ids: List[int], season_start: datetime,
) -> int:
    """COUNT posts since season_start for all user characters."""
    if not char_ids:
        return 0
    placeholders = ", ".join([f":cid_{i}" for i in range(len(char_ids))])
    params: Dict[str, Any] = {f"cid_{i}": cid for i, cid in enumerate(char_ids)}
    params["season_start"] = season_start
    result = await db.execute(
        text(
            f"SELECT COUNT(*) FROM posts "
            f"WHERE character_id IN ({placeholders}) "
            f"AND created_at >= :season_start"
        ),
        params,
    )
    row = result.fetchone()
    return row[0] if row else 0


async def _progress_level_up(
    db: AsyncSession, user_id: int, season_id: int, char_ids: List[int],
) -> int:
    """current level - snapshot level, summed across characters."""
    total_delta = 0
    for cid in char_ids:
        current = await _get_character_level(db, cid)
        snap_result = await db.execute(
            select(BpUserSnapshot.value_at_enrollment).where(
                BpUserSnapshot.user_id == user_id,
                BpUserSnapshot.season_id == season_id,
                BpUserSnapshot.character_id == cid,
                BpUserSnapshot.snapshot_type == "level",
            )
        )
        snap_row = snap_result.fetchone()
        snapshot_val = snap_row[0] if snap_row else 1
        total_delta += max(current - snapshot_val, 0)
    return total_delta


async def _progress_visit_locations(
    db: AsyncSession, user_id: int, season_id: int,
) -> int:
    """COUNT from bp_location_visits."""
    result = await db.execute(
        select(func.count(BpLocationVisit.id)).where(
            BpLocationVisit.user_id == user_id,
            BpLocationVisit.season_id == season_id,
        )
    )
    return result.scalar() or 0


async def _progress_earn_gold(
    db: AsyncSession, char_ids: List[int], season_start: datetime,
) -> int:
    """SUM positive amounts from gold_transactions since season_start."""
    if not char_ids:
        return 0
    placeholders = ", ".join([f":cid_{i}" for i in range(len(char_ids))])
    params: Dict[str, Any] = {f"cid_{i}": cid for i, cid in enumerate(char_ids)}
    params["season_start"] = season_start
    result = await db.execute(
        text(
            f"SELECT COALESCE(SUM(amount), 0) FROM gold_transactions "
            f"WHERE character_id IN ({placeholders}) "
            f"AND amount > 0 AND created_at >= :season_start"
        ),
        params,
    )
    row = result.fetchone()
    return row[0] if row else 0


async def _progress_spend_gold(
    db: AsyncSession, char_ids: List[int], season_start: datetime,
) -> int:
    """SUM absolute negative amounts from gold_transactions since season_start."""
    if not char_ids:
        return 0
    placeholders = ", ".join([f":cid_{i}" for i in range(len(char_ids))])
    params: Dict[str, Any] = {f"cid_{i}": cid for i, cid in enumerate(char_ids)}
    params["season_start"] = season_start
    result = await db.execute(
        text(
            f"SELECT COALESCE(SUM(ABS(amount)), 0) FROM gold_transactions "
            f"WHERE character_id IN ({placeholders}) "
            f"AND amount < 0 AND created_at >= :season_start"
        ),
        params,
    )
    row = result.fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Mission completion
# ---------------------------------------------------------------------------

async def get_user_mission_progress_record(
    db: AsyncSession, user_id: int, mission_id: int,
) -> Optional[BpUserMissionProgress]:
    result = await db.execute(
        select(BpUserMissionProgress).where(
            BpUserMissionProgress.user_id == user_id,
            BpUserMissionProgress.mission_id == mission_id,
        )
    )
    return result.scalars().first()


async def get_mission_by_id(db: AsyncSession, mission_id: int) -> Optional[BpMission]:
    result = await db.execute(
        select(BpMission).where(BpMission.id == mission_id)
    )
    return result.scalars().first()


async def complete_mission(
    db: AsyncSession,
    user_id: int,
    mission: BpMission,
    season: BpSeason,
) -> Dict[str, Any]:
    """
    Verify progress >= target, mark complete, award BP XP, handle level-up.
    Returns dict matching MissionCompleteOut.
    """
    # Re-compute fresh progress
    current_count = await compute_mission_progress(db, user_id, season, mission)
    if current_count < mission.target_count:
        return {"error": "Задание ещё не выполнено"}

    # Check if already completed
    record = await get_user_mission_progress_record(db, user_id, mission.id)
    if record and record.completed_at is not None:
        return {"error_conflict": "Задание уже завершено"}

    # Upsert progress record
    now = datetime.utcnow()
    if record:
        record.current_count = current_count
        record.completed_at = now
    else:
        record = BpUserMissionProgress(
            user_id=user_id,
            mission_id=mission.id,
            current_count=current_count,
            completed_at=now,
        )
        db.add(record)

    await db.flush()

    # Award BP XP
    xp_result = await award_bp_xp(db, user_id, season.id, mission.xp_reward)

    return {
        "ok": True,
        "xp_awarded": mission.xp_reward,
        "new_total_xp": xp_result["new_total_xp"],
        "new_level": xp_result["new_level"],
        "leveled_up": xp_result["leveled_up"],
    }


# ---------------------------------------------------------------------------
# Reward delivery
# ---------------------------------------------------------------------------

async def deliver_reward(
    reward: BpReward,
    character_id: int,
    user_id: int,
) -> None:
    """Deliver a reward to the character/user via inter-service HTTP calls."""
    if reward.reward_type == "gold" or reward.reward_type == "xp":
        xp = reward.reward_value if reward.reward_type == "xp" else 0
        gold = reward.reward_value if reward.reward_type == "gold" else 0
        await _deliver_gold_xp(character_id, xp=xp, gold=gold)
    elif reward.reward_type == "item":
        await _deliver_item(character_id, reward.item_id, 1)
    elif reward.reward_type == "diamonds":
        await _deliver_diamonds(user_id, reward.reward_value)
    elif reward.reward_type in ("frame", "chat_background"):
        cosmetic_type = "frame" if reward.reward_type == "frame" else "background"
        await _deliver_cosmetic(user_id, cosmetic_type, reward.cosmetic_slug)


async def _deliver_gold_xp(character_id: int, xp: int = 0, gold: int = 0):
    """POST to character-service /characters/{char_id}/add_rewards."""
    url = f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/add_rewards"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"xp": xp, "gold": gold})
            resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to deliver gold/xp to character {character_id}: {e}")
        raise


async def _deliver_item(character_id: int, item_id: int, quantity: int = 1):
    """POST to inventory-service /inventory/{char_id}/items."""
    url = f"{settings.INVENTORY_SERVICE_URL}/inventory/{character_id}/items"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"item_id": item_id, "quantity": quantity})
            resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to deliver item {item_id} to character {character_id}: {e}")
        raise


async def _deliver_diamonds(user_id: int, amount: int):
    """POST to user-service /users/internal/{user_id}/diamonds/add."""
    url = f"{settings.USER_SERVICE_URL}/users/internal/{user_id}/diamonds/add"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url, json={"amount": amount, "reason": "battle_pass_reward"}
            )
            resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to deliver {amount} diamonds to user {user_id}: {e}")
        raise


async def _deliver_cosmetic(user_id: int, cosmetic_type: str, cosmetic_slug: str):
    """POST to user-service /users/internal/{user_id}/cosmetics/unlock."""
    url = f"{settings.USER_SERVICE_URL}/users/internal/{user_id}/cosmetics/unlock"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={
                    "cosmetic_type": cosmetic_type,
                    "cosmetic_slug": cosmetic_slug,
                    "source": "battlepass",
                },
            )
            resp.raise_for_status()
    except Exception as e:
        logger.error(
            f"Failed to deliver cosmetic {cosmetic_type}/{cosmetic_slug} "
            f"to user {user_id}: {e}"
        )
        raise


# ---------------------------------------------------------------------------
# Reward claiming
# ---------------------------------------------------------------------------

async def claim_reward(
    db: AsyncSession,
    user_id: int,
    season: BpSeason,
    progress: BpUserProgress,
    level_number: int,
    track: str,
    character_id: int,
    character_name: str,
) -> Dict[str, Any]:
    """Claim a specific reward. Validates and delivers."""
    # Check season status allows claiming
    status = compute_season_status(season)
    if status == "ended":
        return {"error": "Период получения наград истёк"}

    # Check level reached
    if progress.current_level < level_number:
        return {"error": "Уровень ещё не достигнут"}

    # Check premium
    if track == "premium" and not progress.is_premium:
        return {"error": "Премиум-дорожка недоступна"}

    # Find the level and reward
    level_result = await db.execute(
        select(BpLevel).where(
            BpLevel.season_id == season.id,
            BpLevel.level_number == level_number,
        )
    )
    level = level_result.scalars().first()
    if not level:
        return {"error": "Уровень не найден"}

    # Check already claimed
    existing = await db.execute(
        select(BpUserReward).where(
            BpUserReward.user_id == user_id,
            BpUserReward.level_id == level.id,
            BpUserReward.track == track,
        )
    )
    if existing.scalars().first():
        return {"error_conflict": "Награда уже получена"}

    # Find reward for this level+track
    reward_result = await db.execute(
        select(BpReward).where(
            BpReward.level_id == level.id,
            BpReward.track == track,
        )
    )
    reward = reward_result.scalars().first()
    if not reward:
        return {"error": "Награда не найдена для данного уровня и дорожки"}

    # Deliver the reward
    await deliver_reward(reward, character_id, user_id)

    # Record the claim
    claim = BpUserReward(
        user_id=user_id,
        season_id=season.id,
        level_id=level.id,
        track=track,
        delivered_to_character_id=character_id,
    )
    db.add(claim)
    await db.commit()

    return {
        "ok": True,
        "reward_type": reward.reward_type,
        "reward_value": reward.reward_value,
        "delivered_to_character_id": character_id,
        "delivered_to_character_name": character_name,
    }


# ---------------------------------------------------------------------------
# Location visit tracking
# ---------------------------------------------------------------------------

async def track_location_visit(
    db: AsyncSession,
    user_id: int,
    character_id: int,
    location_id: int,
):
    """Upsert a location visit for the current season."""
    season = await get_current_season(db)
    if not season:
        return

    status = compute_season_status(season)
    if status != "active":
        return

    # Check if already visited
    existing = await db.execute(
        select(BpLocationVisit).where(
            BpLocationVisit.user_id == user_id,
            BpLocationVisit.season_id == season.id,
            BpLocationVisit.location_id == location_id,
        )
    )
    if existing.scalars().first():
        return

    visit = BpLocationVisit(
        user_id=user_id,
        season_id=season.id,
        location_id=location_id,
        character_id=character_id,
    )
    db.add(visit)
    await db.commit()


# ---------------------------------------------------------------------------
# Claimed rewards for progress response
# ---------------------------------------------------------------------------

async def get_claimed_rewards(
    db: AsyncSession, user_id: int, season_id: int,
) -> List[Dict[str, Any]]:
    """Get all claimed rewards with level_number for a user+season."""
    result = await db.execute(
        select(
            BpUserReward.track,
            BpUserReward.claimed_at,
            BpUserReward.delivered_to_character_id,
            BpLevel.level_number,
        )
        .join(BpLevel, BpUserReward.level_id == BpLevel.id)
        .where(
            BpUserReward.user_id == user_id,
            BpUserReward.season_id == season_id,
        )
    )
    rows = result.fetchall()
    return [
        {
            "level_number": row[3],
            "track": row[0],
            "claimed_at": row[1],
            "character_id": row[2],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Active character helper
# ---------------------------------------------------------------------------

async def get_active_character(db: AsyncSession, user: "UserRead") -> Optional[Dict[str, Any]]:
    """Get active character info via shared DB read."""
    if not user.current_character_id:
        return None
    result = await db.execute(
        text("SELECT id, name FROM characters WHERE id = :cid LIMIT 1"),
        {"cid": user.current_character_id},
    )
    row = result.fetchone()
    if row:
        return {"id": row[0], "name": row[1] or "Unknown"}
    return None


# ---------------------------------------------------------------------------
# Missions query helper
# ---------------------------------------------------------------------------

async def get_season_missions(
    db: AsyncSession, season_id: int, max_week: int,
) -> List[BpMission]:
    """Get all missions for a season up to the given week."""
    result = await db.execute(
        select(BpMission).where(
            BpMission.season_id == season_id,
            BpMission.week_number <= max_week,
        ).order_by(BpMission.week_number, BpMission.id)
    )
    return result.scalars().all()


# ===========================================================================
# Admin CRUD
# ===========================================================================

async def list_seasons(db: AsyncSession) -> Dict[str, Any]:
    """List all seasons ordered by start_date desc."""
    result = await db.execute(
        select(BpSeason).order_by(BpSeason.start_date.desc())
    )
    seasons = result.scalars().all()
    return {"items": seasons, "total": len(seasons)}


async def create_season(
    db: AsyncSession,
    name: str,
    segment_name: str,
    year: int,
    start_date,
    end_date,
) -> BpSeason:
    """Create a season with auto-calculated grace_end_date. Validates no date overlap."""
    grace_end_date = end_date + timedelta(days=7)

    # Check for date overlap with existing seasons
    overlap = await db.execute(
        select(BpSeason).where(
            and_(
                BpSeason.start_date < grace_end_date,
                BpSeason.grace_end_date > start_date,
            )
        )
    )
    if overlap.scalars().first():
        return {"error": "Даты пересекаются с существующим сезоном"}

    now = datetime.utcnow()
    season = BpSeason(
        name=name,
        segment_name=segment_name,
        year=year,
        start_date=start_date,
        end_date=end_date,
        grace_end_date=grace_end_date,
        is_active=(start_date <= now <= end_date),
    )
    db.add(season)
    await db.commit()
    await db.refresh(season)
    return season


async def update_season(
    db: AsyncSession, season_id: int, data: Dict[str, Any],
) -> Optional[Any]:
    """Update season fields. Returns updated season or None if not found."""
    result = await db.execute(
        select(BpSeason).where(BpSeason.id == season_id)
    )
    season = result.scalars().first()
    if not season:
        return None

    for key, value in data.items():
        if value is not None:
            setattr(season, key, value)

    # Recalculate grace_end_date if end_date was changed
    if "end_date" in data and data["end_date"] is not None:
        season.grace_end_date = season.end_date + timedelta(days=7)

    await db.commit()
    await db.refresh(season)
    return season


async def delete_season(db: AsyncSession, season_id: int) -> Dict[str, Any]:
    """Delete a season only if no user progress exists."""
    result = await db.execute(
        select(BpSeason).where(BpSeason.id == season_id)
    )
    season = result.scalars().first()
    if not season:
        return {"error_not_found": "Сезон не найден"}

    # Check for user progress
    progress_result = await db.execute(
        select(func.count(BpUserProgress.id)).where(
            BpUserProgress.season_id == season_id
        )
    )
    progress_count = progress_result.scalar() or 0
    if progress_count > 0:
        return {"error": "Невозможно удалить сезон с прогрессом игроков"}

    await db.delete(season)
    await db.commit()
    return {"ok": True}


async def get_levels_with_rewards(
    db: AsyncSession, season_id: int,
) -> List[BpLevel]:
    """Get all levels with rewards for a season (admin view)."""
    result = await db.execute(
        select(BpLevel)
        .where(BpLevel.season_id == season_id)
        .options(selectinload(BpLevel.rewards))
        .order_by(BpLevel.level_number)
    )
    return result.scalars().all()


async def bulk_upsert_levels(
    db: AsyncSession, season_id: int, levels_data: List[Dict[str, Any]],
) -> List[BpLevel]:
    """Delete old levels and insert new ones for a season (with rewards)."""
    # Delete existing levels (cascades to rewards)
    await db.execute(
        delete(BpLevel).where(BpLevel.season_id == season_id)
    )
    await db.flush()

    # Insert new levels with rewards
    for lvl_data in levels_data:
        level = BpLevel(
            season_id=season_id,
            level_number=lvl_data["level_number"],
            required_xp=lvl_data["required_xp"],
        )
        db.add(level)
        await db.flush()

        # Add free rewards
        for reward_data in lvl_data.get("free_rewards", []):
            reward = BpReward(
                level_id=level.id,
                track="free",
                reward_type=reward_data["reward_type"],
                reward_value=reward_data["reward_value"],
                item_id=reward_data.get("item_id"),
                cosmetic_slug=reward_data.get("cosmetic_slug"),
            )
            db.add(reward)

        # Add premium rewards
        for reward_data in lvl_data.get("premium_rewards", []):
            reward = BpReward(
                level_id=level.id,
                track="premium",
                reward_type=reward_data["reward_type"],
                reward_value=reward_data["reward_value"],
                item_id=reward_data.get("item_id"),
                cosmetic_slug=reward_data.get("cosmetic_slug"),
            )
            db.add(reward)

    await db.commit()

    # Return fresh data
    return await get_levels_with_rewards(db, season_id)


async def get_missions_grouped(
    db: AsyncSession, season_id: int,
) -> Dict[str, List[BpMission]]:
    """Get all missions for a season grouped by week_number."""
    result = await db.execute(
        select(BpMission)
        .where(BpMission.season_id == season_id)
        .order_by(BpMission.week_number, BpMission.id)
    )
    missions = result.scalars().all()

    weeks: Dict[str, List[BpMission]] = {}
    for m in missions:
        key = str(m.week_number)
        if key not in weeks:
            weeks[key] = []
        weeks[key].append(m)
    return weeks


async def bulk_upsert_missions(
    db: AsyncSession, season_id: int, missions_data: List[Dict[str, Any]],
) -> List[BpMission]:
    """Delete old missions and insert new ones for a season."""
    # Delete existing missions (cascades to user_mission_progress)
    await db.execute(
        delete(BpMission).where(BpMission.season_id == season_id)
    )
    await db.flush()

    new_missions = []
    for m_data in missions_data:
        mission = BpMission(
            season_id=season_id,
            week_number=m_data["week_number"],
            mission_type=m_data["mission_type"],
            description=m_data["description"],
            target_count=m_data["target_count"],
            xp_reward=m_data["xp_reward"],
        )
        db.add(mission)
        new_missions.append(mission)

    await db.commit()
    # Refresh to get IDs
    for m in new_missions:
        await db.refresh(m)
    return new_missions

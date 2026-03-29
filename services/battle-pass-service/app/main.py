import os
import logging
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from typing import List

from database import get_db
from auth_http import get_current_user_via_http, require_permission, UserRead
import crud
import schemas

logger = logging.getLogger(__name__)

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Public: GET /battle-pass/seasons/current
# ---------------------------------------------------------------------------

@app.get("/battle-pass/seasons/current", response_model=schemas.SeasonCurrentOut)
async def get_current_season(db: AsyncSession = Depends(get_db)):
    """Return the currently active or grace-period season with levels and rewards."""
    season = await crud.get_current_season(db)
    if not season:
        raise HTTPException(status_code=404, detail="Нет активного сезона")

    # Load with levels and rewards
    season = await crud.get_season_with_levels(db, season.id)
    if not season:
        raise HTTPException(status_code=404, detail="Нет активного сезона")

    season_status = crud.compute_season_status(season)
    current_week = crud.compute_current_week(season)
    total_weeks = crud.compute_total_weeks(season)
    days_remaining = crud.compute_days_remaining(season)

    # Build levels with rewards split by track
    levels_out = []
    for lvl in sorted(season.levels, key=lambda l: l.level_number):
        free_rewards = [
            schemas.RewardOut(
                id=r.id,
                reward_type=r.reward_type,
                reward_value=r.reward_value,
                item_id=r.item_id,
                item_name=None,
                cosmetic_slug=r.cosmetic_slug,
            )
            for r in lvl.rewards if r.track == "free"
        ]
        premium_rewards = [
            schemas.RewardOut(
                id=r.id,
                reward_type=r.reward_type,
                reward_value=r.reward_value,
                item_id=r.item_id,
                item_name=None,
                cosmetic_slug=r.cosmetic_slug,
            )
            for r in lvl.rewards if r.track == "premium"
        ]
        levels_out.append(schemas.LevelOut(
            level_number=lvl.level_number,
            required_xp=lvl.required_xp,
            free_rewards=free_rewards,
            premium_rewards=premium_rewards,
        ))

    return schemas.SeasonCurrentOut(
        id=season.id,
        name=season.name,
        segment_name=season.segment_name,
        year=season.year,
        start_date=season.start_date,
        end_date=season.end_date,
        grace_end_date=season.grace_end_date,
        is_active=season.is_active,
        status=season_status,
        days_remaining=days_remaining,
        current_week=current_week,
        total_weeks=total_weeks,
        levels=levels_out,
    )


# ---------------------------------------------------------------------------
# Auth: GET /battle-pass/me/progress
# ---------------------------------------------------------------------------

@app.get("/battle-pass/me/progress", response_model=schemas.UserProgressOut)
async def get_my_progress(
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Return user's progress in the current season. Auto-enrolls on first access."""
    season = await crud.get_current_season(db)
    if not season:
        raise HTTPException(status_code=404, detail="Нет активного сезона")

    progress = await crud.get_or_create_user_progress(db, user.id, season)
    xp_to_next = await crud.get_xp_to_next_level(db, season.id, progress.current_level)
    claimed = await crud.get_claimed_rewards(db, user.id, season.id)

    return schemas.UserProgressOut(
        season_id=season.id,
        current_level=progress.current_level,
        current_xp=progress.current_xp,
        xp_to_next_level=xp_to_next,
        is_premium=progress.is_premium,
        claimed_rewards=[
            schemas.ClaimedRewardOut(
                level_number=c["level_number"],
                track=c["track"],
                claimed_at=c["claimed_at"],
                character_id=c["character_id"],
            )
            for c in claimed
        ],
    )


# ---------------------------------------------------------------------------
# Auth: GET /battle-pass/me/missions
# ---------------------------------------------------------------------------

@app.get("/battle-pass/me/missions", response_model=schemas.MissionsResponse)
async def get_my_missions(
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Return all missions for the current season with fresh progress."""
    season = await crud.get_current_season(db)
    if not season:
        raise HTTPException(status_code=404, detail="Нет активного сезона")

    # Ensure enrollment (creates snapshots if needed)
    await crud.get_or_create_user_progress(db, user.id, season)

    current_week = crud.compute_current_week(season)
    missions = await crud.get_season_missions(db, season.id, current_week)

    missions_out = []
    for m in missions:
        # Check if already completed
        record = await crud.get_user_mission_progress_record(db, user.id, m.id)
        if record and record.completed_at is not None:
            current_count = record.current_count
            is_completed = True
            completed_at = record.completed_at
        else:
            # Fresh progress from DB
            current_count = await crud.compute_mission_progress(db, user.id, season, m)
            is_completed = False
            completed_at = None

        missions_out.append(schemas.MissionOut(
            id=m.id,
            week_number=m.week_number,
            mission_type=m.mission_type,
            description=m.description,
            target_count=m.target_count,
            current_count=current_count,
            is_completed=is_completed,
            completed_at=completed_at,
            xp_reward=m.xp_reward,
        ))

    return schemas.MissionsResponse(
        season_id=season.id,
        current_week=current_week,
        missions=missions_out,
    )


# ---------------------------------------------------------------------------
# Auth: POST /battle-pass/me/missions/{mission_id}/complete
# ---------------------------------------------------------------------------

@app.post(
    "/battle-pass/me/missions/{mission_id}/complete",
    response_model=schemas.MissionCompleteOut,
)
async def complete_mission(
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Mark a mission as completed and award BP XP."""
    season = await crud.get_current_season(db)
    if not season:
        raise HTTPException(status_code=404, detail="Нет активного сезона")

    season_status = crud.compute_season_status(season)
    if season_status != "active":
        raise HTTPException(status_code=400, detail="Сезон завершён, задания недоступны")

    mission = await crud.get_mission_by_id(db, mission_id)
    if not mission or mission.season_id != season.id:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    # Check week availability
    current_week = crud.compute_current_week(season)
    if mission.week_number > current_week:
        raise HTTPException(status_code=400, detail="Задание ещё недоступно")

    result = await crud.complete_mission(db, user.id, mission, season)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    if "error_conflict" in result:
        raise HTTPException(status_code=409, detail=result["error_conflict"])

    return schemas.MissionCompleteOut(**result)


# ---------------------------------------------------------------------------
# Auth: POST /battle-pass/me/rewards/claim
# ---------------------------------------------------------------------------

@app.post("/battle-pass/me/rewards/claim", response_model=schemas.RewardClaimOut)
async def claim_reward(
    body: schemas.RewardClaimRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Claim a reward for a specific level and track."""
    season = await crud.get_current_season(db)
    if not season:
        raise HTTPException(status_code=404, detail="Нет активного сезона")

    progress = await crud.get_or_create_user_progress(db, user.id, season)

    # Get active character
    if not user.current_character_id:
        raise HTTPException(status_code=400, detail="Выберите активного персонажа")

    char_info = await crud.get_active_character(db, user)
    if not char_info:
        raise HTTPException(status_code=400, detail="Выберите активного персонажа")

    # Validate track
    if body.track not in ("free", "premium"):
        raise HTTPException(status_code=400, detail="Неверная дорожка")

    result = await crud.claim_reward(
        db=db,
        user_id=user.id,
        season=season,
        progress=progress,
        level_number=body.level_number,
        track=body.track,
        character_id=char_info["id"],
        character_name=char_info["name"],
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    if "error_conflict" in result:
        raise HTTPException(status_code=409, detail=result["error_conflict"])

    return schemas.RewardClaimOut(**result)


# ---------------------------------------------------------------------------
# Auth: POST /battle-pass/me/premium/activate (stub)
# ---------------------------------------------------------------------------

@app.post("/battle-pass/me/premium/activate")
async def activate_premium(
    user: UserRead = Depends(get_current_user_via_http),
):
    """Stub endpoint for premium activation. Always returns 501."""
    raise HTTPException(
        status_code=501,
        detail="Покупка премиума временно недоступна",
    )


# ---------------------------------------------------------------------------
# Internal: POST /battle-pass/internal/track-event
# ---------------------------------------------------------------------------

@app.post("/battle-pass/internal/track-event")
async def track_event(
    body: schemas.TrackEventRequest,
    db: AsyncSession = Depends(get_db),
):
    """Internal endpoint for other services to report trackable events."""
    if body.event_type == "location_visit":
        location_id = (body.metadata or {}).get("location_id")
        if location_id is not None:
            try:
                await crud.track_location_visit(
                    db=db,
                    user_id=body.user_id,
                    character_id=body.character_id,
                    location_id=int(location_id),
                )
            except Exception as e:
                logger.warning(f"Failed to track location visit: {e}")

    return {"ok": True}


# ===========================================================================
# Admin: Seasons
# ===========================================================================

@app.get(
    "/battle-pass/admin/seasons",
    response_model=schemas.SeasonListOut,
)
async def admin_list_seasons(
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(require_permission("battlepass:read")),
):
    """List all seasons (admin)."""
    data = await crud.list_seasons(db)
    return schemas.SeasonListOut(
        items=[schemas.SeasonAdminOut.from_orm(s) for s in data["items"]],
        total=data["total"],
    )


@app.post(
    "/battle-pass/admin/seasons",
    response_model=schemas.SeasonAdminOut,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_season(
    body: schemas.SeasonCreate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(require_permission("battlepass:create")),
):
    """Create a new season (admin). grace_end_date = end_date + 7 days."""
    result = await crud.create_season(
        db,
        name=body.name,
        segment_name=body.segment_name,
        year=body.year,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return schemas.SeasonAdminOut.from_orm(result)


@app.put(
    "/battle-pass/admin/seasons/{season_id}",
    response_model=schemas.SeasonAdminOut,
)
async def admin_update_season(
    season_id: int,
    body: schemas.SeasonUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(require_permission("battlepass:update")),
):
    """Update season metadata (admin). Partial update — all fields optional."""
    data = body.dict(exclude_unset=True)
    result = await crud.update_season(db, season_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Сезон не найден")
    return schemas.SeasonAdminOut.from_orm(result)


@app.delete("/battle-pass/admin/seasons/{season_id}")
async def admin_delete_season(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(require_permission("battlepass:delete")),
):
    """Delete a season (only if no user progress exists)."""
    result = await crud.delete_season(db, season_id)
    if "error_not_found" in result:
        raise HTTPException(status_code=404, detail=result["error_not_found"])
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"ok": True}


# ===========================================================================
# Admin: Levels & Rewards
# ===========================================================================

@app.get(
    "/battle-pass/admin/seasons/{season_id}/levels",
    response_model=List[schemas.LevelAdminOut],
)
async def admin_get_levels(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(require_permission("battlepass:read")),
):
    """Get all levels with rewards for a season (admin)."""
    levels = await crud.get_levels_with_rewards(db, season_id)
    return [
        schemas.LevelAdminOut(
            id=lvl.id,
            level_number=lvl.level_number,
            required_xp=lvl.required_xp,
            rewards=[
                schemas.RewardAdminOut(
                    id=r.id,
                    track=r.track,
                    reward_type=r.reward_type,
                    reward_value=r.reward_value,
                    item_id=r.item_id,
                    cosmetic_slug=r.cosmetic_slug,
                )
                for r in lvl.rewards
            ],
        )
        for lvl in levels
    ]


@app.put(
    "/battle-pass/admin/seasons/{season_id}/levels",
    response_model=List[schemas.LevelAdminOut],
)
async def admin_upsert_levels(
    season_id: int,
    body: schemas.LevelsBulkUpsert,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(require_permission("battlepass:update")),
):
    """Bulk upsert all levels and their rewards for a season (admin)."""
    levels_data = [lvl.dict() for lvl in body.levels]
    levels = await crud.bulk_upsert_levels(db, season_id, levels_data)
    return [
        schemas.LevelAdminOut(
            id=lvl.id,
            level_number=lvl.level_number,
            required_xp=lvl.required_xp,
            rewards=[
                schemas.RewardAdminOut(
                    id=r.id,
                    track=r.track,
                    reward_type=r.reward_type,
                    reward_value=r.reward_value,
                    item_id=r.item_id,
                    cosmetic_slug=r.cosmetic_slug,
                )
                for r in lvl.rewards
            ],
        )
        for lvl in levels
    ]


# ===========================================================================
# Admin: Missions
# ===========================================================================

@app.get(
    "/battle-pass/admin/seasons/{season_id}/missions",
    response_model=schemas.MissionsGroupedOut,
)
async def admin_get_missions(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(require_permission("battlepass:read")),
):
    """Get all missions grouped by week (admin)."""
    weeks = await crud.get_missions_grouped(db, season_id)
    grouped = {}
    for week_key, missions in weeks.items():
        grouped[week_key] = [
            schemas.MissionAdminOut(
                id=m.id,
                week_number=m.week_number,
                mission_type=m.mission_type,
                description=m.description,
                target_count=m.target_count,
                xp_reward=m.xp_reward,
            )
            for m in missions
        ]
    return schemas.MissionsGroupedOut(weeks=grouped)


@app.put(
    "/battle-pass/admin/seasons/{season_id}/missions",
    response_model=List[schemas.MissionAdminOut],
)
async def admin_upsert_missions(
    season_id: int,
    body: schemas.MissionsBulkUpsert,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(require_permission("battlepass:update")),
):
    """Bulk upsert missions for a season (admin)."""
    missions_data = [m.dict() for m in body.missions]
    missions = await crud.bulk_upsert_missions(db, season_id, missions_data)
    return [
        schemas.MissionAdminOut(
            id=m.id,
            week_number=m.week_number,
            mission_type=m.mission_type,
            description=m.description,
            target_count=m.target_count,
            xp_reward=m.xp_reward,
        )
        for m in missions
    ]

import os
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import asyncio

from database import get_db
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import httpx

import models
import schemas
import crud
from rabbitmq_consumer import start_consumer
from auth_http import get_admin_user, get_current_user_via_http, require_permission

# Пример, если нужно
CHARACTER_SERVICE_URL = os.getenv("CHARACTER_SERVICE_URL", "http://character-service:8005/characters")
ATTRIBUTES_SERVICE_URL = os.getenv("ATTRIBUTES_SERVICE_URL", "http://character-attributes-service:8002/attributes")

app = FastAPI(title="Async Skill Service")

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/skills", tags=["skills"])


async def verify_character_ownership(db: AsyncSession, character_id: int, user_id: int):
    """Check that the character exists and belongs to the given user."""
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

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_consumer())

# -----------------------------------------------------------
# 0) Legacy endpoint
# -----------------------------------------------------------
@router.post("/", response_model=dict)
async def legacy_create_skills_for_new_character(
    data: schemas.LegacySkillRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Пример старого эндпоинта. Сюда приходит {character_id}.
    Создаём "Basic Attack" (skill_id=1) если нет, rank#1, и CharacterSkill.
    """
    char_id = data.character_id

    skill = await crud.get_skill(db, 1)
    if not skill:
        skill_data = schemas.SkillCreate(
            name="Basic Attack",
            skill_type="Attack",
            description="Простой базовый навык"
        )
        skill = await crud.create_skill(db, skill_data)
        rank_data = schemas.SkillRankCreate(skill_id=skill.id, rank_number=1)
        rank1 = await crud.create_skill_rank(db, rank_data)
    else:
        rank_list = await crud.list_skill_ranks_by_skill(db, skill.id)
        rank1 = None
        for r in rank_list:
            if r.rank_number == 1:
                rank1 = r
                break
        if not rank1:
            rank_data = schemas.SkillRankCreate(skill_id=skill.id, rank_number=1)
            rank1 = await crud.create_skill_rank(db, rank_data)

    data_cs = schemas.CharacterSkillCreate(
        character_id=char_id,
        skill_rank_id=rank1.id
    )
    cs = await crud.create_character_skill(db, data_cs)

    return {
        "id": cs.id,
        "message": "Basic skill assigned to character"
    }

# -----------------------------------------------------------
# 1) Админские роуты Skill
# -----------------------------------------------------------
@router.post("/admin/skills/", response_model=schemas.SkillRead)
async def admin_create_skill(
    data: schemas.SkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:create"))
):
    return await crud.create_skill(db, data)

@router.get("/admin/skills/", response_model=List[schemas.SkillRead])
async def admin_list_skills(db: AsyncSession = Depends(get_db), current_user = Depends(require_permission("skills:read"))):
    return await crud.list_skills(db)

@router.get("/admin/skills/{skill_id}", response_model=schemas.SkillRead)
async def admin_get_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:read"))
):
    skill = await crud.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill

@router.put("/admin/skills/{skill_id}", response_model=schemas.SkillRead)
async def admin_update_skill(
    skill_id: int,
    data: schemas.SkillUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:update"))
):
    updated = await crud.update_skill(db, skill_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
    return updated

@router.delete("/admin/skills/{skill_id}")
async def admin_delete_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:delete"))
):
    success = await crud.delete_skill(db, skill_id)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"detail": "Skill deleted"}

# -----------------------------------------------------------
# 2) Админские роуты SkillRank
# -----------------------------------------------------------
@router.post("/admin/skill_ranks/", response_model=schemas.SkillRankRead)
async def admin_create_skill_rank(
    data: schemas.SkillRankCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:create"))
):
    return await crud.create_skill_rank(db, data)

@router.get("/admin/skill_ranks/{rank_id}", response_model=schemas.SkillRankRead)
async def admin_get_skill_rank(
    rank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:read"))
):
    rank = await crud.get_skill_rank(db, rank_id)
    if not rank:
        raise HTTPException(status_code=404, detail="SkillRank not found")
    return rank

@router.put("/admin/skill_ranks/{rank_id}", response_model=schemas.SkillRankRead)
async def admin_update_skill_rank(
    rank_id: int,
    data: schemas.SkillRankUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:update"))
):
    updated = await crud.update_skill_rank(db, rank_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="SkillRank not found")
    return updated

@router.delete("/admin/skill_ranks/{rank_id}")
async def admin_delete_skill_rank(
    rank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:delete"))
):
    success = await crud.delete_skill_rank(db, rank_id)
    if not success:
        raise HTTPException(status_code=404, detail="SkillRank not found")
    return {"detail": "SkillRank deleted"}

# -----------------------------------------------------------
# 3) Админские роуты SkillRankDamage
# -----------------------------------------------------------
@router.post("/admin/damages/", response_model=schemas.SkillRankDamageRead)
async def admin_create_damage(
    data: schemas.SkillRankDamageCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:create"))
):
    return await crud.create_skill_rank_damage(db, data)

@router.get("/admin/damages/{damage_id}", response_model=schemas.SkillRankDamageRead)
async def admin_get_damage(
    damage_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:read"))
):
    dmg = await crud.get_skill_rank_damage(db, damage_id)
    if not dmg:
        raise HTTPException(status_code=404, detail="Damage not found")
    return dmg

@router.put("/admin/damages/{damage_id}", response_model=schemas.SkillRankDamageRead)
async def admin_update_damage(
    damage_id: int,
    data: schemas.SkillRankDamageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:update"))
):
    updated = await crud.update_skill_rank_damage(db, damage_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Damage not found")
    return updated

@router.delete("/admin/damages/{damage_id}")
async def admin_delete_damage(
    damage_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:delete"))
):
    success = await crud.delete_skill_rank_damage(db, damage_id)
    if not success:
        raise HTTPException(status_code=404, detail="Damage not found")
    return {"detail": "Damage entry deleted"}

# -----------------------------------------------------------
# 4) Админские роуты SkillRankEffect
# -----------------------------------------------------------
@router.post("/admin/effects/", response_model=schemas.SkillRankEffectRead)
async def admin_create_effect(
    data: schemas.SkillRankEffectCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:create"))
):
    return await crud.create_skill_rank_effect(db, data)

@router.get("/admin/effects/{effect_id}", response_model=schemas.SkillRankEffectRead)
async def admin_get_effect(
    effect_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:read"))
):
    eff = await crud.get_skill_rank_effect(db, effect_id)
    if not eff:
        raise HTTPException(status_code=404, detail="Effect not found")
    return eff

@router.put("/admin/effects/{effect_id}", response_model=schemas.SkillRankEffectRead)
async def admin_update_effect(
    effect_id: int,
    data: schemas.SkillRankEffectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:update"))
):
    updated = await crud.update_skill_rank_effect(db, effect_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Effect not found")
    return updated

@router.delete("/admin/effects/{effect_id}")
async def admin_delete_effect(
    effect_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:delete"))
):
    success = await crud.delete_skill_rank_effect(db, effect_id)
    if not success:
        raise HTTPException(status_code=404, detail="Effect not found")
    return {"detail": "Effect deleted"}

# -----------------------------------------------------------
# 5) Админские роуты CharacterSkill
# -----------------------------------------------------------
@router.post("/admin/character_skills/", response_model=schemas.CharacterSkillRead)
async def admin_give_character_skill(
    data: schemas.CharacterSkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:create"))
):
    return await crud.create_character_skill(db, data)

@router.delete("/admin/character_skills/by_character/{character_id}")
async def admin_delete_all_character_skills(
    character_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:delete"))
):
    """Bulk delete all skills for a character (admin only)."""
    count = await crud.delete_all_character_skills(db, character_id)
    return {"detail": "All character skills deleted", "count": count}

@router.put("/admin/character_skills/{cs_id}", response_model=schemas.CharacterSkillRead)
async def admin_update_character_skill_rank(
    cs_id: int,
    data: schemas.AdminCharacterSkillUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:update"))
):
    """Change the rank of an existing character skill (admin only)."""
    cs = await crud.get_character_skill(db, cs_id)
    if not cs:
        raise HTTPException(status_code=404, detail="CharacterSkill not found")
    updated_cs = await crud.update_character_skill_rank(db, cs_id, data.skill_rank_id)
    # Re-fetch with full relationship loading for CharacterSkillRead response
    result = await crud.list_character_skills_for_character(db, updated_cs.character_id)
    for item in result:
        if item.id == cs_id:
            return item
    return updated_cs

@router.delete("/admin/character_skills/{cs_id}")
async def admin_remove_character_skill(
    cs_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:delete"))
):
    success = await crud.delete_character_skill(db, cs_id)
    if not success:
        raise HTTPException(status_code=404, detail="CharacterSkill not found")
    return {"detail": "CharacterSkill removed"}

# -----------------------------------------------------------
# 6) Просмотр навыков у персонажа
# -----------------------------------------------------------
@router.get("/characters/{character_id}/skills", response_model=List[schemas.CharacterSkillRead])
async def list_skills_for_character(
    character_id: int,
    db: AsyncSession = Depends(get_db)
):
    return await crud.list_character_skills_for_character(db, character_id)

# -----------------------------------------------------------
# 6b) Публичный endpoint для получения ранга навыка (для battle-service)
# -----------------------------------------------------------
@router.get("/skill_ranks/{rank_id}", response_model=schemas.SkillRankRead)
async def get_skill_rank_public(
    rank_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint for internal service-to-service calls (battle-service)."""
    rank = await crud.get_skill_rank(db, rank_id)
    if not rank:
        raise HTTPException(status_code=404, detail="SkillRank not found")
    return rank

# -----------------------------------------------------------
# 7) Прокачка навыка
# -----------------------------------------------------------
@router.post("/character_skills/upgrade")
async def upgrade_skill(
    data: schemas.SkillUpgradeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """
    Пример логики прокачки ранга (вопрос совместимости).
    """
    character_id = data.character_id
    await verify_character_ownership(db, character_id, current_user.id)
    next_rank_id = data.next_rank_id

    # 1) Запрашиваем character-service
    # ...
    # 2) Проверяем rank
    rank = await crud.get_skill_rank(db, next_rank_id)
    if not rank:
        raise HTTPException(status_code=404, detail="SkillRank not found")

    # 3) Check and deduct experience for upgrade
    cost = rank.upgrade_cost
    if cost > 0:
        active_exp = await get_active_experience(character_id)
        if active_exp < cost:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно опыта для улучшения. Требуется: {cost}, доступно: {active_exp}",
            )
        await deduct_active_experience(character_id, cost)

    # 5) Обновляем/создаём CharacterSkill
    skill_id = rank.skill_id
    conflicts = await crud.build_conflicts_for_skill(db, skill_id)

    existing_cs_list = await crud.list_character_skills_for_character(db, character_id)
    already_owned_rank_ids = []
    for cs_obj in existing_cs_list:
        if cs_obj.skill_rank.skill_id == skill_id:
            already_owned_rank_ids.append(cs_obj.skill_rank.id)

    for owned_id in already_owned_rank_ids:
        if (owned_id, next_rank_id) in conflicts:
            raise HTTPException(
                status_code=403,
                detail=f"Нельзя прокачать ранг {next_rank_id}, конфликт с {owned_id}"
            )

    existing_cs = await crud.get_character_skill_by_skill_id(db, character_id, skill_id)
    if existing_cs:
        updated_cs = await crud.update_character_skill_rank(db, existing_cs.id, next_rank_id)
        return {"detail": "Skill rank upgraded", "character_skill_id": updated_cs.id}
    else:
        new_cs_data = schemas.CharacterSkillCreate(
            character_id=character_id,
            skill_rank_id=next_rank_id
        )
        new_cs = await crud.create_character_skill(db, new_cs_data)
        return {"detail": "Skill learned", "character_skill_id": new_cs.id}

# -----------------------------------------------------------
# 8) Получить полное дерево навыка
# -----------------------------------------------------------
@router.get("/admin/skills/{skill_id}/full_tree", response_model=schemas.FullSkillTreeResponse)
async def get_skill_full_tree(skill_id: int, db: AsyncSession = Depends(get_db), current_user = Depends(require_permission("skills:read"))):
    skill = await crud.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Подгружаем ranks
    await db.refresh(skill, ["ranks"])

    ranks_in_tree = []
    for rank in skill.ranks:
        await db.refresh(rank, ["damage_entries", "effects"])
        damage_list = []
        for dmg in rank.damage_entries:
            damage_list.append({
                "id": dmg.id,
                "damage_type": dmg.damage_type,
                "amount": dmg.amount,
                "description": dmg.description,
                "chance": dmg.chance,  # <-- нужно
                "target_side": dmg.target_side,
                "weapon_slot": dmg.weapon_slot
            })
        effect_list = []
        for eff in rank.effects:
            effect_list.append({
                "id": eff.id,
                "target_side": eff.target_side,
                "effect_name": eff.effect_name,
                "description": eff.description,
                "chance": eff.chance,
                "duration": eff.duration,
                "magnitude": eff.magnitude,
                "attribute_key": eff.attribute_key
            })
        ranks_in_tree.append({
            "id": rank.id,
            "rank_name": rank.rank_name,
            "rank_image": rank.rank_image,
            "rank_number": rank.rank_number,
            "left_child_id": rank.left_child_id,
            "right_child_id": rank.right_child_id,
            "cost_energy": rank.cost_energy,
            "cost_mana": rank.cost_mana,
            "cooldown": rank.cooldown,
            "level_requirement": rank.level_requirement,
            "upgrade_cost": rank.upgrade_cost,
            "class_limitations": rank.class_limitations,
            "race_limitations": rank.race_limitations,
            "subrace_limitations": rank.subrace_limitations,
            "rank_description": rank.rank_description,
            "damage_entries": damage_list,
            "effects": effect_list
        })

    response_data = {
        "id": skill.id,
        "name": skill.name,
        "skill_type": skill.skill_type,
        "description": skill.description,
        "class_limitations": skill.class_limitations,
        "race_limitations": skill.race_limitations,
        "subrace_limitations": skill.subrace_limitations,
        "min_level": skill.min_level,
        "purchase_cost": skill.purchase_cost,
        "skill_image": skill.skill_image,
        "ranks": ranks_in_tree
    }
    return response_data

# -----------------------------------------------------------
# 9) Обновить полную структуру
# -----------------------------------------------------------
@router.put("/admin/skills/{skill_id}/full_tree")
async def update_skill_full_tree(
    skill_id: int,
    data: schemas.FullSkillTreeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:update"))
):
    if skill_id != data.id:
        raise HTTPException(status_code=400, detail="Path skill_id != data.id")

    skill = await crud.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Обновляем поля Skill
    update_data = data.dict(exclude={"ranks"})
    for key, value in update_data.items():
        setattr(skill, key, value)
    db.add(skill)

    # Загрузка старых рангов
    stmt = (
        select(models.SkillRank)
        .where(models.SkillRank.skill_id == skill_id)
        .options(
            selectinload(models.SkillRank.damage_entries),
            selectinload(models.SkillRank.effects),
        )
    )
    result = await db.execute(stmt)
    old_ranks = result.scalars().all()
    old_map = {r.id: r for r in old_ranks}

    # Разделение на новые и существующие ранги
    new_ranks_data = []
    existing_ranks_data = []
    for rank_data in data.ranks:
        if isinstance(rank_data.id, str) and rank_data.id.startswith("temp-"):
            new_ranks_data.append(rank_data)
        elif isinstance(rank_data.id, int):
            existing_ranks_data.append(rank_data)
        else:
            raise HTTPException(
                status_code=400,
                detail="New ranks must have a temporary ID starting with 'temp-'"
            )

    temp_id_map = {}  # Маппинг временных ID в реальные

    # Создание новых рангов
    new_rank_objects = []
    for rank_data in new_ranks_data:
        new_rank = models.SkillRank(
            skill_id=skill_id,
            **rank_data.dict(
                exclude={"id", "damage_entries", "effects", "left_child_id", "right_child_id","skill_id"}
            )
        )
        db.add(new_rank)
        await db.flush()
        temp_id = rank_data.id
        temp_id_map[temp_id] = new_rank.id

        # Синхронизация damage и effects
        await crud.sync_damage_entries(db, new_rank, rank_data.damage_entries)
        await crud.sync_effects(db, new_rank, rank_data.effects)
        new_rank_objects.append(new_rank)

    # Обновление существующих рангов
    existing_ids = []
    for rank_data in existing_ranks_data:
        if rank_data.id not in old_map:
            raise HTTPException(status_code=400, detail=f"Rank {rank_data.id} not found")
        rank_obj = old_map[rank_data.id]
        for key, value in rank_data.dict(
            exclude={"id", "damage_entries", "effects", "left_child_id", "right_child_id","skill_id"}
        ).items():
            setattr(rank_obj, key, value)
        await crud.sync_damage_entries(db, rank_obj, rank_data.damage_entries)
        await crud.sync_effects(db, rank_obj, rank_data.effects)
        existing_ids.append(rank_data.id)

    # Определение ID для сохранения
    wanted_ids = set(existing_ids) | set(temp_id_map.values())

    # Удаление старых рангов
    for old_id, old_rank in old_map.items():
        if old_id not in wanted_ids:
            await db.delete(old_rank)

    # Второй проход: обновление left/right_child_id
    all_ranks = {**old_map, **{r.id: r for r in new_rank_objects}}
    for rank_data in data.ranks:
        # Определение реального ID ранга
        if isinstance(rank_data.id, str):
            real_id = temp_id_map.get(rank_data.id)
        else:
            real_id = rank_data.id
        if not real_id or real_id not in all_ranks:
            continue
        rank_obj = all_ranks[real_id]

        # Обработка left_child_id
        left_id = rank_data.left_child_id
        resolved_left_id = None
        if isinstance(left_id, str):
            resolved_left_id = temp_id_map.get(left_id)
        elif isinstance(left_id, int):
            resolved_left_id = left_id if left_id in wanted_ids else None
        rank_obj.left_child_id = resolved_left_id

        # Обработка right_child_id
        right_id = rank_data.right_child_id
        resolved_right_id = None
        if isinstance(right_id, str):
            resolved_right_id = temp_id_map.get(right_id)
        elif isinstance(right_id, int):
            resolved_right_id = right_id if right_id in wanted_ids else None
        rank_obj.right_child_id = resolved_right_id

    await db.commit()
    return {"detail": "Skill tree updated successfully", "temp_id_map": temp_id_map}

@router.post("/assign_multiple", response_model=dict)
async def assign_multiple_skills(
    data: schemas.MultipleSkillsAssignRequest,  # см. ниже
    db: AsyncSession = Depends(get_db)
):
    """
    Принимает массив {skill_id, rank_number} и назначает каждый навык (указанный ранг)
    персонажу. Если SkillRank(id=??) нет, создаём.
    Если SkillRank под skill_id с rank_number уже есть — просто берём его ID.
    Создаём CharacterSkill(character_id, skill_rank_id).
    """
    char_id = data.character_id
    assigned = []

    for skill_info in data.skills:
        skill_id = skill_info.skill_id
        rank_number = skill_info.rank_number

        # 1) Проверяем, что сам Skill с таким ID существует
        skill_obj = await crud.get_skill(db, skill_id)
        if not skill_obj:
            raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

        # 2) Ищем SkillRank для этого skill_id и rank_number
        existing_ranks = await crud.list_skill_ranks_by_skill(db, skill_id)
        rank_obj = None
        for r in existing_ranks:
            if r.rank_number == rank_number:
                rank_obj = r
                break
        # Если нет, создаём
        if not rank_obj:
            new_rank_data = schemas.SkillRankCreate(
                skill_id=skill_id,
                rank_number=rank_number
            )
            rank_obj = await crud.create_skill_rank(db, new_rank_data)

        # 3) Создаём CharacterSkill
        cs_data = schemas.CharacterSkillCreate(
            character_id=char_id,
            skill_rank_id=rank_obj.id
        )
        cs = await crud.create_character_skill(db, cs_data)
        assigned.append({"character_skill_id": cs.id, "skill_id": skill_id, "rank_number": rank_number})

    return {"assigned": assigned}


# ====================================================================
# 10) Admin: Class Skill Tree endpoints (FEAT-056)
# ====================================================================

@router.post("/admin/class_trees/", response_model=schemas.ClassSkillTreeRead)
async def admin_create_class_tree(
    data: schemas.ClassSkillTreeCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skill_trees:create")),
):
    return await crud.create_class_tree(db, data)


@router.get("/admin/class_trees/", response_model=List[schemas.ClassSkillTreeRead])
async def admin_list_class_trees(
    class_id: Optional[int] = None,
    tree_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skill_trees:read")),
):
    return await crud.list_class_trees(db, class_id=class_id, tree_type=tree_type)


@router.get("/admin/class_trees/{tree_id}", response_model=schemas.ClassSkillTreeRead)
async def admin_get_class_tree(
    tree_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skill_trees:read")),
):
    tree = await crud.get_class_tree(db, tree_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Class tree not found")
    return tree


@router.get("/admin/class_trees/{tree_id}/full", response_model=schemas.FullClassTreeResponse)
async def admin_get_full_class_tree(
    tree_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skill_trees:read")),
):
    result = await crud.get_full_class_tree(db, tree_id)
    if not result:
        raise HTTPException(status_code=404, detail="Class tree not found")
    return result


@router.put("/admin/class_trees/{tree_id}/full")
async def admin_save_full_class_tree(
    tree_id: int,
    data: schemas.FullClassTreeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skill_trees:update")),
):
    if tree_id != data.id:
        raise HTTPException(status_code=400, detail="Path tree_id != data.id")
    return await crud.save_full_class_tree(db, tree_id, data)


@router.delete("/admin/class_trees/{tree_id}")
async def admin_delete_class_tree(
    tree_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skill_trees:delete")),
):
    success = await crud.delete_class_tree(db, tree_id)
    if not success:
        raise HTTPException(status_code=404, detail="Class tree not found")
    return {"detail": "Class tree deleted"}


# --- Individual Node Operations ---

@router.post("/admin/class_trees/{tree_id}/nodes/", response_model=schemas.TreeNodeRead)
async def admin_create_tree_node(
    tree_id: int,
    data: schemas.TreeNodeCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skill_trees:create")),
):
    # Verify tree exists
    tree = await crud.get_class_tree(db, tree_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Class tree not found")
    if data.tree_id != tree_id:
        raise HTTPException(status_code=400, detail="Path tree_id != data.tree_id")
    return await crud.create_tree_node(db, data)


@router.put("/admin/class_trees/{tree_id}/nodes/{node_id}", response_model=schemas.TreeNodeRead)
async def admin_update_tree_node(
    tree_id: int,
    node_id: int,
    data: schemas.TreeNodeBase,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skill_trees:update")),
):
    updated = await crud.update_tree_node(db, node_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Tree node not found")
    return updated


@router.delete("/admin/class_trees/{tree_id}/nodes/{node_id}")
async def admin_delete_tree_node(
    tree_id: int,
    node_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skill_trees:delete")),
):
    success = await crud.delete_tree_node(db, node_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tree node not found")
    return {"detail": "Tree node deleted"}


# ====================================================================
# Helper functions for cross-service HTTP calls (FEAT-057)
# ====================================================================

async def deduct_active_experience(character_id: int, amount: int) -> int:
    """Deduct active_experience via character-attributes-service. Returns new balance."""
    async with httpx.AsyncClient() as client:
        url = f"{ATTRIBUTES_SERVICE_URL}/{character_id}/active_experience"
        resp = await client.put(url, json={"amount": -amount})
        if resp.status_code == 400:
            raise HTTPException(400, detail="Недостаточно опыта")
        if resp.status_code != 200:
            raise HTTPException(500, detail="Ошибка при списании опыта")
        return resp.json().get("active_experience", 0)


async def get_character_info(character_id: int) -> dict:
    """Get character class/level via character-service."""
    async with httpx.AsyncClient() as client:
        url = f"{CHARACTER_SERVICE_URL}/{character_id}/race_info"
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(404, detail="Персонаж не найден")
        return resp.json()


async def get_active_experience(character_id: int) -> int:
    """Get current active_experience from character-attributes-service."""
    async with httpx.AsyncClient() as client:
        url = f"{ATTRIBUTES_SERVICE_URL}/{character_id}"
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(500, detail="Не удалось получить атрибуты")
        return resp.json().get("active_experience", 0)


# ====================================================================
# 11) Player: Class Skill Tree endpoints (FEAT-057)
# ====================================================================

@router.get("/class_trees/by_class/{class_id}", response_model=schemas.FullClassTreeResponse)
async def get_class_tree_by_class(
    class_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: get the full class tree for a given class_id."""
    tree = await crud.get_class_tree_by_class_id(db, class_id, tree_type="class")
    if not tree:
        raise HTTPException(status_code=404, detail="Дерево навыков для этого класса не найдено")
    result = await crud.get_full_class_tree(db, tree.id)
    if not result:
        raise HTTPException(status_code=404, detail="Дерево навыков не найдено")
    return result


@router.get(
    "/class_trees/{tree_id}/progress/{character_id}",
    response_model=schemas.CharacterTreeProgressResponse,
)
async def get_tree_progress(
    tree_id: int,
    character_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Get character's progress on a specific tree (chosen nodes + purchased skills)."""
    await verify_character_ownership(db, character_id, current_user.id)

    # Chosen nodes
    progress_rows = await crud.get_character_tree_progress(db, character_id, tree_id)
    chosen_nodes = [
        schemas.ChosenNodeProgress(
            node_id=p.node_id,
            chosen_at=str(p.chosen_at) if p.chosen_at else None,
        )
        for p in progress_rows
    ]

    # Purchased skills: find character_skills that belong to this tree's nodes
    # Get all node_ids for this tree
    tree_data = await crud.get_class_tree(db, tree_id)
    if not tree_data:
        raise HTTPException(status_code=404, detail="Дерево навыков не найдено")

    node_ids = [n.id for n in tree_data.nodes]
    tree_skill_ids = await crud.get_skills_for_nodes(db, node_ids)

    purchased_skills = []
    if tree_skill_ids:
        all_cs = await crud.list_character_skills_for_character(db, character_id)
        for cs in all_cs:
            if cs.skill_rank.skill_id in tree_skill_ids:
                purchased_skills.append(
                    schemas.PurchasedSkillProgress(
                        skill_id=cs.skill_rank.skill_id,
                        skill_rank_id=cs.skill_rank_id,
                        character_skill_id=cs.id,
                    )
                )

    # Get active_experience and character_level via HTTP
    active_exp = await get_active_experience(character_id)
    char_info = await get_character_info(character_id)
    char_level = char_info.get("level", 0)

    return schemas.CharacterTreeProgressResponse(
        character_id=character_id,
        tree_id=tree_id,
        chosen_nodes=chosen_nodes,
        purchased_skills=purchased_skills,
        active_experience=active_exp,
        character_level=char_level,
    )


@router.post("/class_trees/{tree_id}/choose_node")
async def choose_node(
    tree_id: int,
    data: schemas.ChooseNodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Choose a node in the tree (free, validates prerequisites and branch conflicts)."""
    character_id = data.character_id
    node_id = data.node_id
    await verify_character_ownership(db, character_id, current_user.id)

    # 1. Verify node belongs to tree
    stmt = select(models.TreeNode).where(
        models.TreeNode.id == node_id,
        models.TreeNode.tree_id == tree_id,
    )
    result = await db.execute(stmt)
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден в этом дереве")

    # 2. Get character info and verify level
    char_info = await get_character_info(character_id)
    char_level = char_info.get("level", 0)
    if char_level < node.level_ring:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточный уровень персонажа. Требуется: {node.level_ring}, текущий: {char_level}",
        )

    # 3. Check tree's class_id matches character's class
    tree = await crud.get_class_tree(db, tree_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Дерево навыков не найдено")
    char_class_id = char_info.get("id_class")
    if tree.class_id != char_class_id:
        raise HTTPException(
            status_code=400,
            detail="Дерево навыков не соответствует классу персонажа",
        )

    # 4. Check node is not already chosen
    existing_progress = await crud.get_character_tree_progress(db, character_id, tree_id)
    chosen_node_ids = {p.node_id for p in existing_progress}
    if node_id in chosen_node_ids:
        raise HTTPException(status_code=400, detail="Узел уже выбран")

    # 5. Prerequisite check
    if node.node_type != "root":
        parent_ids = await crud.get_parent_nodes(db, node_id)
        if not parent_ids:
            raise HTTPException(
                status_code=400,
                detail="У узла нет родительских связей и он не является корневым",
            )
        has_chosen_parent = any(pid in chosen_node_ids for pid in parent_ids)
        if not has_chosen_parent:
            raise HTTPException(
                status_code=400,
                detail="Необходимо сначала выбрать предыдущий узел в цепочке",
            )

    # 6. Branch conflict check
    sibling_ids = await crud.get_sibling_nodes(db, tree_id, node_id)
    for sib_id in sibling_ids:
        if sib_id in chosen_node_ids:
            raise HTTPException(
                status_code=400,
                detail="Альтернативная ветка уже выбрана",
            )

    # 7. Insert progress
    await crud.add_character_tree_progress(db, character_id, tree_id, node_id)
    return {"detail": "Узел выбран", "node_id": node_id}


@router.post("/class_trees/purchase_skill")
async def purchase_skill(
    data: schemas.PurchaseSkillRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Buy a skill from a chosen node (costs active_experience)."""
    character_id = data.character_id
    node_id = data.node_id
    skill_id = data.skill_id
    await verify_character_ownership(db, character_id, current_user.id)

    # 1. Verify node is chosen by character
    # First get the node to find its tree_id
    stmt = select(models.TreeNode).where(models.TreeNode.id == node_id)
    result = await db.execute(stmt)
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")

    progress_rows = await crud.get_character_tree_progress(db, character_id, node.tree_id)
    chosen_node_ids = {p.node_id for p in progress_rows}
    if node_id not in chosen_node_ids:
        raise HTTPException(
            status_code=400,
            detail="Необходимо сначала выбрать этот узел",
        )

    # 2. Verify skill belongs to node
    stmt = select(models.TreeNodeSkill).where(
        models.TreeNodeSkill.node_id == node_id,
        models.TreeNodeSkill.skill_id == skill_id,
    )
    result = await db.execute(stmt)
    node_skill = result.scalar_one_or_none()
    if not node_skill:
        raise HTTPException(
            status_code=400,
            detail="Навык не привязан к этому узлу",
        )

    # 3. Check character doesn't already have this skill
    existing_cs = await crud.get_character_skill_by_skill_id(db, character_id, skill_id)
    if existing_cs:
        raise HTTPException(status_code=400, detail="Навык уже изучен")

    # 4. Get skill's purchase_cost
    skill = await crud.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Навык не найден")

    purchase_cost = skill.purchase_cost or 0

    # 5. Check and deduct experience
    if purchase_cost > 0:
        active_exp = await get_active_experience(character_id)
        if active_exp < purchase_cost:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно опыта. Требуется: {purchase_cost}, доступно: {active_exp}",
            )
        await deduct_active_experience(character_id, purchase_cost)

    # 6. Find rank 1 of the skill
    ranks = await crud.list_skill_ranks_by_skill(db, skill_id)
    rank1 = None
    for r in ranks:
        if r.rank_number == 1:
            rank1 = r
            break
    if not rank1:
        raise HTTPException(
            status_code=500,
            detail="У навыка нет базового ранга (rank 1)",
        )

    # 7. Create CharacterSkill
    cs_data = schemas.CharacterSkillCreate(
        character_id=character_id,
        skill_rank_id=rank1.id,
    )
    new_cs = await crud.create_character_skill(db, cs_data)
    return {"detail": "Навык изучен", "character_skill_id": new_cs.id}


@router.post("/class_trees/{tree_id}/reset")
async def reset_tree(
    tree_id: int,
    data: schemas.ResetTreeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Reset tree progress (except subclass choice). Skills from reset nodes are deleted."""
    character_id = data.character_id
    await verify_character_ownership(db, character_id, current_user.id)

    # 1. Get non-subclass progress rows (node_ids to reset)
    stmt = (
        select(models.CharacterTreeProgress)
        .join(models.TreeNode, models.TreeNode.id == models.CharacterTreeProgress.node_id)
        .where(
            models.CharacterTreeProgress.character_id == character_id,
            models.CharacterTreeProgress.tree_id == tree_id,
            models.TreeNode.node_type != "subclass_choice",
        )
    )
    result = await db.execute(stmt)
    progress_rows = result.scalars().all()

    if not progress_rows:
        return {"detail": "Нечего сбрасывать", "nodes_reset": 0, "skills_removed": 0}

    node_ids_to_reset = [p.node_id for p in progress_rows]

    # 2. Get skill_ids for those nodes
    skill_ids = await crud.get_skills_for_nodes(db, node_ids_to_reset)

    # 3. Delete character_skills for those skill_ids
    skills_removed = 0
    if skill_ids:
        skills_removed = await crud.delete_character_skills_by_skill_ids(
            db, character_id, skill_ids
        )

    # 4. Delete progress rows
    nodes_reset = await crud.delete_character_tree_progress_for_reset(
        db, character_id, tree_id
    )

    return {
        "detail": "Прогресс сброшен",
        "nodes_reset": nodes_reset,
        "skills_removed": skills_removed,
    }


@router.post("/admin/class_trees/reset_full")
async def admin_reset_tree_full(
    data: schemas.ResetTreeRequest,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_permission("skill_trees:update")),
):
    """Admin: fully reset ALL tree progress for a character (including subclass). Deletes all skills."""
    character_id = data.character_id

    # Find all trees for this character's progress
    stmt = (
        select(models.CharacterTreeProgress.tree_id)
        .where(models.CharacterTreeProgress.character_id == character_id)
        .distinct()
    )
    result = await db.execute(stmt)
    tree_ids = [row[0] for row in result.fetchall()]

    if not tree_ids:
        return {"detail": "Нечего сбрасывать", "nodes_reset": 0, "skills_removed": 0}

    total_nodes = 0
    total_skills = 0

    for tree_id in tree_ids:
        # Get ALL progress nodes (including subclass_choice)
        stmt = (
            select(models.CharacterTreeProgress)
            .where(
                models.CharacterTreeProgress.character_id == character_id,
                models.CharacterTreeProgress.tree_id == tree_id,
            )
        )
        result = await db.execute(stmt)
        progress_rows = result.scalars().all()

        node_ids = [p.node_id for p in progress_rows]

        # Delete skills from those nodes
        if node_ids:
            skill_ids = await crud.get_skills_for_nodes(db, node_ids)
            if skill_ids:
                total_skills += await crud.delete_character_skills_by_skill_ids(
                    db, character_id, skill_ids
                )

        # Delete ALL progress rows
        for row in progress_rows:
            await db.delete(row)
        total_nodes += len(progress_rows)

    await db.commit()
    return {
        "detail": "Весь прогресс сброшен (включая подкласс)",
        "nodes_reset": total_nodes,
        "skills_removed": total_skills,
    }


@router.get("/skills/{skill_id}/full_tree", response_model=schemas.FullSkillTreeResponse)
async def get_skill_full_tree_public(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: get the full skill tree (ranks, damage, effects) for player upgrade modal."""
    skill = await crud.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Навык не найден")

    await db.refresh(skill, ["ranks"])

    ranks_in_tree = []
    for rank in skill.ranks:
        await db.refresh(rank, ["damage_entries", "effects"])
        damage_list = []
        for dmg in rank.damage_entries:
            damage_list.append({
                "id": dmg.id,
                "damage_type": dmg.damage_type,
                "amount": dmg.amount,
                "description": dmg.description,
                "chance": dmg.chance,
                "target_side": dmg.target_side,
                "weapon_slot": dmg.weapon_slot
            })
        effect_list = []
        for eff in rank.effects:
            effect_list.append({
                "id": eff.id,
                "target_side": eff.target_side,
                "effect_name": eff.effect_name,
                "description": eff.description,
                "chance": eff.chance,
                "duration": eff.duration,
                "magnitude": eff.magnitude,
                "attribute_key": eff.attribute_key
            })
        ranks_in_tree.append({
            "id": rank.id,
            "rank_name": rank.rank_name,
            "rank_image": rank.rank_image,
            "rank_number": rank.rank_number,
            "left_child_id": rank.left_child_id,
            "right_child_id": rank.right_child_id,
            "cost_energy": rank.cost_energy,
            "cost_mana": rank.cost_mana,
            "cooldown": rank.cooldown,
            "level_requirement": rank.level_requirement,
            "upgrade_cost": rank.upgrade_cost,
            "class_limitations": rank.class_limitations,
            "race_limitations": rank.race_limitations,
            "subrace_limitations": rank.subrace_limitations,
            "rank_description": rank.rank_description,
            "damage_entries": damage_list,
            "effects": effect_list
        })

    return {
        "id": skill.id,
        "name": skill.name,
        "skill_type": skill.skill_type,
        "description": skill.description,
        "class_limitations": skill.class_limitations,
        "race_limitations": skill.race_limitations,
        "subrace_limitations": skill.subrace_limitations,
        "min_level": skill.min_level,
        "purchase_cost": skill.purchase_cost,
        "skill_image": skill.skill_image,
        "ranks": ranks_in_tree
    }


@router.get(
    "/class_trees/subclass_trees/{class_tree_id}",
    response_model=List[schemas.ClassSkillTreeRead],
)
async def get_subclass_trees(
    class_tree_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: get available subclass trees for a class tree."""
    stmt = (
        select(models.ClassSkillTree)
        .where(
            models.ClassSkillTree.parent_tree_id == class_tree_id,
            models.ClassSkillTree.tree_type == "subclass",
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()


app.include_router(router, prefix="")

from fastapi import FastAPI, APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db, create_tables
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import httpx
import os

import models
import schemas
import crud

# Пример, если нужно
CHARACTER_SERVICE_URL = os.getenv("CHARACTER_SERVICE_URL", "http://character-service:8000/characters")
ATTRIBUTES_SERVICE_URL = os.getenv("ATTRIBUTES_SERVICE_URL", "http://attribute-service:8000/attributes")

app = FastAPI(title="Async Skill Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/skills", tags=["skills"])

@app.on_event("startup")
async def startup_event():
    await create_tables()

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
    db: AsyncSession = Depends(get_db)
):
    return await crud.create_skill(db, data)

@router.get("/admin/skills/", response_model=List[schemas.SkillRead])
async def admin_list_skills(db: AsyncSession = Depends(get_db)):
    return await crud.list_skills(db)

@router.get("/admin/skills/{skill_id}", response_model=schemas.SkillRead)
async def admin_get_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db)
):
    skill = await crud.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill

@router.put("/admin/skills/{skill_id}", response_model=schemas.SkillRead)
async def admin_update_skill(
    skill_id: int,
    data: schemas.SkillUpdate,
    db: AsyncSession = Depends(get_db)
):
    updated = await crud.update_skill(db, skill_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
    return updated

@router.delete("/admin/skills/{skill_id}")
async def admin_delete_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db)
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
    db: AsyncSession = Depends(get_db)
):
    return await crud.create_skill_rank(db, data)

@router.get("/admin/skill_ranks/{rank_id}", response_model=schemas.SkillRankRead)
async def admin_get_skill_rank(
    rank_id: int,
    db: AsyncSession = Depends(get_db)
):
    rank = await crud.get_skill_rank(db, rank_id)
    if not rank:
        raise HTTPException(status_code=404, detail="SkillRank not found")
    return rank

@router.put("/admin/skill_ranks/{rank_id}", response_model=schemas.SkillRankRead)
async def admin_update_skill_rank(
    rank_id: int,
    data: schemas.SkillRankUpdate,
    db: AsyncSession = Depends(get_db)
):
    updated = await crud.update_skill_rank(db, rank_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="SkillRank not found")
    return updated

@router.delete("/admin/skill_ranks/{rank_id}")
async def admin_delete_skill_rank(
    rank_id: int,
    db: AsyncSession = Depends(get_db)
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
    db: AsyncSession = Depends(get_db)
):
    return await crud.create_skill_rank_damage(db, data)

@router.get("/admin/damages/{damage_id}", response_model=schemas.SkillRankDamageRead)
async def admin_get_damage(
    damage_id: int,
    db: AsyncSession = Depends(get_db)
):
    dmg = await crud.get_skill_rank_damage(db, damage_id)
    if not dmg:
        raise HTTPException(status_code=404, detail="Damage not found")
    return dmg

@router.put("/admin/damages/{damage_id}", response_model=schemas.SkillRankDamageRead)
async def admin_update_damage(
    damage_id: int,
    data: schemas.SkillRankDamageUpdate,
    db: AsyncSession = Depends(get_db)
):
    updated = await crud.update_skill_rank_damage(db, damage_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Damage not found")
    return updated

@router.delete("/admin/damages/{damage_id}")
async def admin_delete_damage(
    damage_id: int,
    db: AsyncSession = Depends(get_db)
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
    db: AsyncSession = Depends(get_db)
):
    return await crud.create_skill_rank_effect(db, data)

@router.get("/admin/effects/{effect_id}", response_model=schemas.SkillRankEffectRead)
async def admin_get_effect(
    effect_id: int,
    db: AsyncSession = Depends(get_db)
):
    eff = await crud.get_skill_rank_effect(db, effect_id)
    if not eff:
        raise HTTPException(status_code=404, detail="Effect not found")
    return eff

@router.put("/admin/effects/{effect_id}", response_model=schemas.SkillRankEffectRead)
async def admin_update_effect(
    effect_id: int,
    data: schemas.SkillRankEffectUpdate,
    db: AsyncSession = Depends(get_db)
):
    updated = await crud.update_skill_rank_effect(db, effect_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Effect not found")
    return updated

@router.delete("/admin/effects/{effect_id}")
async def admin_delete_effect(
    effect_id: int,
    db: AsyncSession = Depends(get_db)
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
    db: AsyncSession = Depends(get_db)
):
    return await crud.create_character_skill(db, data)

@router.delete("/admin/character_skills/{cs_id}")
async def admin_remove_character_skill(
    cs_id: int,
    db: AsyncSession = Depends(get_db)
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
# 7) Прокачка навыка
# -----------------------------------------------------------
@router.post("/character_skills/upgrade")
async def upgrade_skill(
    data: schemas.SkillUpgradeRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Пример логики прокачки ранга (вопрос совместимости).
    """
    character_id = data.character_id
    next_rank_id = data.next_rank_id

    # 1) Запрашиваем character-service
    # ...
    # 2) Проверяем rank
    rank = await crud.get_skill_rank(db, next_rank_id)
    if not rank:
        raise HTTPException(status_code=404, detail="SkillRank not found")

    # Класс, раса, подраса, уровень и т.д. (аналогично)
    # ...
    # 3) Узнаём active_experience
    # ...
    # 4) Проверяем cost => списываем
    cost = rank.upgrade_cost
    # ...
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
async def get_skill_full_tree(skill_id: int, db: AsyncSession = Depends(get_db)):
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
    db: AsyncSession = Depends(get_db)
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



app.include_router(router, prefix="")

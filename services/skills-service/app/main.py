import os
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Query
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
import subclasses as subclass_registry
from rabbitmq_consumer import start_consumer
from auth_http import get_admin_user, get_current_user_via_http, require_permission, allow_jwt_or_service_token

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
# 0) Legacy endpoint (FEAT-125: rebuilt for perk system)
# -----------------------------------------------------------
@router.post("/", response_model=dict)
async def legacy_create_skills_for_new_character(
    data: schemas.LegacySkillRequest,
    db: AsyncSession = Depends(get_db)
):
    """Создаёт базовый навык 'Basic Attack' и привязывает его к персонажу на уровне 0."""
    char_id = data.character_id

    skill = await crud.get_skill(db, 1)
    if not skill:
        skill_data = schemas.SkillCreate(
            name="Basic Attack",
            skill_type="Attack",
            description="Простой базовый навык",
        )
        skill = await crud.create_skill(db, skill_data)

    cs = await crud.create_character_skill(db, character_id=char_id, skill_id=skill.id, level=0)
    return {"id": cs.id, "message": "Basic skill assigned to character"}

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
async def admin_list_skills(
    q: str | None = Query(None),
    class_id: int | None = Query(None, description="Skills of this class and no subclass"),
    subclass_key: str | None = Query(None, description="Skills of this subclass"),
    race_id: int | None = Query(None, description="Skills of this race and no subrace"),
    subrace_id: int | None = Query(None, description="Skills of this subrace"),
    general: bool | None = Query(None, description="true: skills with no scoping at all"),
    mob: bool | None = Query(None, description="true: mob skills only, false: players' only"),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("skills:read")),
):
    """List skills for the admin, optionally narrowed to one category."""
    return await crud.list_skills(
        db,
        q=q,
        class_id=class_id,
        subclass_key=subclass_key,
        race_id=race_id,
        subrace_id=subrace_id,
        general=general,
        mob=mob,
    )

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
# 2) (FEAT-125) Admin: Perk pool CRUD
# -----------------------------------------------------------
@router.post("/admin/skills/{skill_id}/perks", response_model=schemas.SkillPerkRead, status_code=201)
async def admin_create_perk(
    skill_id: int,
    data: schemas.SkillPerkCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:create")),
):
    return await crud.create_perk(db, skill_id, data)


@router.get("/admin/skills/{skill_id}/perks", response_model=List[schemas.SkillPerkRead])
async def admin_list_perks(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:read")),
):
    return await crud.list_perks_for_skill(db, skill_id)


@router.get("/admin/skill_perks/{perk_id}", response_model=schemas.SkillPerkRead)
async def admin_get_perk(
    perk_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:read")),
):
    perk = await crud.get_perk(db, perk_id)
    if not perk:
        raise HTTPException(status_code=404, detail="Перк не найден")
    return perk


@router.put("/admin/skill_perks/{perk_id}", response_model=schemas.SkillPerkRead)
async def admin_update_perk(
    perk_id: int,
    data: schemas.SkillPerkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:update")),
):
    updated = await crud.update_perk(db, perk_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Перк не найден")
    return updated


@router.delete("/admin/skill_perks/{perk_id}", status_code=204)
async def admin_delete_perk(
    perk_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:delete")),
):
    success = await crud.delete_perk(db, perk_id)
    if not success:
        raise HTTPException(status_code=404, detail="Перк не найден")
    return None


# -----------------------------------------------------------
# 3) (FEAT-125) Admin: Skill base damage / effects CRUD
# -----------------------------------------------------------
@router.post("/admin/skills/{skill_id}/base_damage", response_model=schemas.SkillBaseDamageRead, status_code=201)
async def admin_create_base_damage(
    skill_id: int,
    data: schemas.DamageEntryWrite,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:create")),
):
    skill = await crud.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Навык не найден")
    return await crud.create_base_damage(db, skill_id, data)


@router.put("/admin/skills/{skill_id}/base_damage/{damage_id}", response_model=schemas.SkillBaseDamageRead)
async def admin_update_base_damage(
    skill_id: int,
    damage_id: int,
    data: schemas.DamageEntryWrite,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:update")),
):
    updated = await crud.update_base_damage(db, damage_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Базовая запись урона не найдена")
    return updated


@router.delete("/admin/skills/{skill_id}/base_damage/{damage_id}", status_code=204)
async def admin_delete_base_damage(
    skill_id: int,
    damage_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:delete")),
):
    success = await crud.delete_base_damage(db, damage_id)
    if not success:
        raise HTTPException(status_code=404, detail="Базовая запись урона не найдена")
    return None


@router.post("/admin/skills/{skill_id}/base_effects", response_model=schemas.SkillBaseEffectRead, status_code=201)
async def admin_create_base_effect(
    skill_id: int,
    data: schemas.EffectEntryWrite,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:create")),
):
    skill = await crud.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Навык не найден")
    return await crud.create_base_effect(db, skill_id, data)


@router.put("/admin/skills/{skill_id}/base_effects/{effect_id}", response_model=schemas.SkillBaseEffectRead)
async def admin_update_base_effect(
    skill_id: int,
    effect_id: int,
    data: schemas.EffectEntryWrite,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:update")),
):
    updated = await crud.update_base_effect(db, effect_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Базовый эффект не найден")
    return updated


@router.delete("/admin/skills/{skill_id}/base_effects/{effect_id}", status_code=204)
async def admin_delete_base_effect(
    skill_id: int,
    effect_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:delete")),
):
    success = await crud.delete_base_effect(db, effect_id)
    if not success:
        raise HTTPException(status_code=404, detail="Базовый эффект не найден")
    return None


# -----------------------------------------------------------
# 5) Admin: CharacterSkill
# -----------------------------------------------------------
@router.post("/admin/character_skills/", response_model=schemas.CharacterSkillRead)
async def admin_give_character_skill(
    data: schemas.AdminCharacterSkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:create")),
):
    cs = await crud.create_character_skill(
        db, character_id=data.character_id, skill_id=data.skill_id, level=data.level,
    )
    full = await crud._load_character_skill_full(db, cs.id)
    return crud.serialize_character_skill(full)


@router.delete("/admin/character_skills/by_character/{character_id}")
async def admin_delete_all_character_skills(
    character_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:delete")),
):
    count = await crud.delete_all_character_skills(db, character_id)
    return {"detail": "All character skills deleted", "count": count}


@router.put("/admin/character_skills/{cs_id}", response_model=schemas.CharacterSkillRead)
async def admin_update_character_skill(
    cs_id: int,
    data: schemas.AdminCharacterSkillUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:update")),
):
    """Admin: change the skill_id and/or level of an existing character_skill row."""
    await crud.admin_update_character_skill(db, cs_id, data.skill_id, data.level)
    full = await crud._load_character_skill_full(db, cs_id)
    return crud.serialize_character_skill(full)


@router.delete("/admin/character_skills/{cs_id}")
async def admin_remove_character_skill(
    cs_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("skills:delete")),
):
    success = await crud.delete_character_skill(db, cs_id)
    if not success:
        raise HTTPException(status_code=404, detail="CharacterSkill не найден")
    return {"detail": "CharacterSkill removed"}


# -----------------------------------------------------------
# 6) (FEAT-125) Player: list character's skills (new flat shape)
# -----------------------------------------------------------
@router.get("/characters/{character_id}/skills", response_model=List[schemas.CharacterSkillRead])
async def list_skills_for_character(
    character_id: int,
    db: AsyncSession = Depends(get_db),
):
    rows = await crud.list_character_skills_for_character(db, character_id)
    return [crud.serialize_character_skill(cs) for cs in rows]


# -----------------------------------------------------------
# 6a) Public: subclass registry
# Registered BEFORE "/{skill_id}" so "/subclasses" is not swallowed by it.
# -----------------------------------------------------------
@router.get("/subclasses", response_model=List[schemas.SubclassRead])
async def list_subclasses(class_id: Optional[int] = None):
    """Public reference: hardcoded subclass registry, optionally filtered by class."""
    items = (
        subclass_registry.subclasses_for_class(class_id)
        if class_id is not None
        else subclass_registry.SUBCLASSES
    )
    return items


# -----------------------------------------------------------
# 6a-bis) (FEAT-154) Public: bulk skill resolve
# Registered BEFORE "/{skill_id}" so "bulk" is not parsed as a skill id.
# -----------------------------------------------------------
MAX_BULK_IDS = 100


def _parse_bulk_ids(raw: str) -> List[int]:
    """
    Разбирает параметр ?ids=1,2,3 в дедуплицированный список int.
    Бросает HTTPException(400) при некорректном вводе или превышении лимита.
    """
    parts = [p.strip() for p in (raw or "").split(",")]
    parts = [p for p in parts if p]
    if not parts:
        raise HTTPException(status_code=400, detail="Параметр ids не должен быть пустым")

    # Лимит считается по сырым токенам (до дедупликации), иначе строка вида
    # ?ids=1,1,1,... любой длины проходила бы проверку.
    if len(parts) > MAX_BULK_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Слишком много идентификаторов: максимум {MAX_BULK_IDS}",
        )

    seen = set()
    ids: List[int] = []
    for part in parts:
        try:
            value = int(part)
        except ValueError:
            raise HTTPException(status_code=400, detail="Параметр ids должен содержать только целые числа через запятую")
        if value <= 0:
            raise HTTPException(status_code=400, detail="Идентификаторы должны быть положительными числами")
        if value not in seen:
            seen.add(value)
            ids.append(value)

    return ids


@router.get("/bulk", response_model=List[schemas.SkillBulkResponse])
async def get_skills_bulk(
    ids: str = Query(..., description="Идентификаторы навыков через запятую, максимум 100"),
    db: AsyncSession = Depends(get_db),
):
    """
    Массовый резолв навыков по списку id (публичный эндпоинт).
    Неизвестные id молча опускаются. Запрос параметризован (IN), SQL не строится строками.
    """
    skill_ids = _parse_bulk_ids(ids)
    result = await db.execute(
        select(models.Skill)
        .where(models.Skill.id.in_(skill_ids))
        .order_by(models.Skill.id.asc())
    )
    rows = result.scalars().all()
    return [
        schemas.SkillBulkResponse(
            id=row.id,
            name=row.name,
            description=row.description,
            icon_url=row.skill_image,
            class_limitations=row.class_limitations,
        )
        for row in rows
    ]


# -----------------------------------------------------------
# 6b) (FEAT-125) Public: skill base + perk pool
# -----------------------------------------------------------
@router.get("/{skill_id}", response_model=schemas.SkillWithPerksRead)
async def get_skill_with_perks_public(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
):
    data = await crud.get_skill_with_perks(db, skill_id)
    if not data:
        raise HTTPException(status_code=404, detail="Навык не найден")
    return data


# -----------------------------------------------------------
# 6c) (FEAT-125) Resolved skill (server-authoritative for battle-service)
# -----------------------------------------------------------
@router.get("/{skill_id}/resolved", response_model=schemas.ResolvedSkillRead)
async def get_resolved_skill(
    skill_id: int,
    character_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    caller=Depends(allow_jwt_or_service_token),
):
    """
    Server-authoritative resolved skill stats. Accepts:
    - JWT of the character's owner (validates ownership)
    - Admin/moderator JWT
    - Internal service token (battle-service / autobattle-service)
    """
    if caller is not None:
        # User token: must own the character or be admin/moderator
        if caller.role not in ("admin", "moderator"):
            await verify_character_ownership(db, character_id, caller.id)
    return await crud.resolve_character_skill(db, character_id, skill_id)


# -----------------------------------------------------------
# 7) (FEAT-125) Player: upgrade / pick perk / reset
# -----------------------------------------------------------
@router.post("/characters/{character_id}/skills/{skill_id}/upgrade")
async def upgrade_character_skill(
    character_id: int,
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    await verify_character_ownership(db, character_id, current_user.id)
    cs = await crud.get_character_skill_by_skill_id(db, character_id, skill_id)
    if not cs:
        raise HTTPException(status_code=404, detail="У персонажа нет этого навыка")
    skill = await crud.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Навык не найден")

    cost = (skill.purchase_cost or 0) // 2
    if cost > 0:
        active_exp = await get_active_experience(character_id)
        if active_exp < cost:
            raise HTTPException(
                status_code=402,
                detail=f"Недостаточно опыта для улучшения. Требуется: {cost}, доступно: {active_exp}",
            )
        await deduct_active_experience(character_id, cost)

    updated = await crud.upgrade_character_skill_level(db, cs.id)

    # Track cumulative stat (non-fatal)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{ATTRIBUTES_SERVICE_URL}/cumulative_stats/increment",
                json={"character_id": character_id, "increments": {"skills_used": 1}},
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Cumulative stats tracking error: {e}")

    return crud.serialize_character_skill(updated)


@router.post("/characters/{character_id}/skills/{skill_id}/perks/{perk_id}")
async def pick_skill_perk(
    character_id: int,
    skill_id: int,
    perk_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    await verify_character_ownership(db, character_id, current_user.id)
    cs = await crud.get_character_skill_by_skill_id(db, character_id, skill_id)
    if not cs:
        raise HTTPException(status_code=404, detail="У персонажа нет этого навыка")
    updated = await crud.pick_perk_for_character_skill(db, cs.id, perk_id)
    return crud.serialize_character_skill(updated)


@router.post("/characters/{character_id}/skills/{skill_id}/reset")
async def reset_character_skill_endpoint(
    character_id: int,
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    await verify_character_ownership(db, character_id, current_user.id)
    cs = await crud.get_character_skill_by_skill_id(db, character_id, skill_id)
    if not cs:
        raise HTTPException(status_code=404, detail="У персонажа нет этого навыка")
    updated = await crud.reset_character_skill(db, cs.id)
    return crud.serialize_character_skill(updated)


@router.post("/assign_multiple", response_model=dict)
async def assign_multiple_skills(
    data: schemas.MultipleSkillsAssignRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    (FEAT-125) Назначает указанные навыки персонажу на уровне 0.
    """
    char_id = data.character_id
    assigned = []
    for skill_info in data.skills:
        skill_id = skill_info.skill_id
        skill_obj = await crud.get_skill(db, skill_id)
        if not skill_obj:
            raise HTTPException(status_code=404, detail=f"Навык {skill_id} не найден")
        existing = await crud.get_character_skill_by_skill_id(db, char_id, skill_id)
        if existing:
            assigned.append({"character_skill_id": existing.id, "skill_id": skill_id, "level": existing.level})
            continue
        cs = await crud.create_character_skill(db, character_id=char_id, skill_id=skill_id, level=0)
        assigned.append({"character_skill_id": cs.id, "skill_id": skill_id, "level": 0})
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
            if cs.skill_id in tree_skill_ids:
                purchased_skills.append(
                    schemas.PurchasedSkillProgress(
                        skill_id=cs.skill_id,
                        character_skill_id=cs.id,
                        level=cs.level or 0,
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

    # 3. Check character doesn't already have this skill (FEAT-125: 409 "уже есть")
    existing_cs = await crud.get_character_skill_by_skill_id(db, character_id, skill_id)
    if existing_cs:
        raise HTTPException(status_code=409, detail="Навык уже есть")

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
                status_code=402,
                detail=f"Недостаточно опыта. Требуется: {purchase_cost}, доступно: {active_exp}",
            )
        await deduct_active_experience(character_id, purchase_cost)

    # 6. (FEAT-125) Insert CharacterSkill at level 0 — no ranks anymore.
    new_cs = await crud.create_character_skill(db, character_id=character_id, skill_id=skill_id, level=0)
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


# (FEAT-125) GET /skills/{skill_id}/full_tree removed — use GET /skills/{skill_id} (perk pool).


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

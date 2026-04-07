from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_, func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from sqlalchemy.orm import selectinload

import models, schemas

MAX_LEVEL = 4
MIN_PERK_POOL = 4
RESET_COOLDOWN_HOURS = 24

# -----------------------
# CRUD: Skill
# -----------------------
async def create_skill(db: AsyncSession, data: schemas.SkillCreate) -> models.Skill:
    new_skill = models.Skill(**data.dict())
    db.add(new_skill)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Навык с таким именем уже существует")
    await db.refresh(new_skill)
    return new_skill

async def get_skill(db: AsyncSession, skill_id: int) -> models.Skill | None:
    result = await db.execute(select(models.Skill).where(models.Skill.id == skill_id))
    return result.scalar_one_or_none()

async def list_skills(db: AsyncSession, q: str | None = None) -> list[models.Skill]:
    stmt = select(models.Skill)
    if q is not None and q.strip():
        q_stripped = q.strip()
        name_clause = func.lower(models.Skill.name).like(f"%{q_stripped.lower()}%")
        if q_stripped.isdigit():
            stmt = stmt.where(or_(name_clause, models.Skill.id == int(q_stripped)))
        else:
            stmt = stmt.where(name_clause)
    result = await db.execute(stmt)
    return result.scalars().all()

async def update_skill(db: AsyncSession, skill_id: int, data: schemas.SkillUpdate) -> models.Skill | None:
    skill = await get_skill(db, skill_id)
    if not skill:
        return None
    # data.dict(exclude_unset=True) чтобы не перетирать None
    for field, value in data.dict(exclude_unset=True).items():
        setattr(skill, field, value)
    await db.commit()
    await db.refresh(skill)
    return skill

async def delete_skill(db: AsyncSession, skill_id: int) -> bool:
    skill = await get_skill(db, skill_id)
    if not skill:
        return False

    # CharacterSkill rows for this skill (cascade by FK on delete in DB, but be explicit
    # to avoid leaving orphans during ORM-level deletes).
    cs_stmt = select(models.CharacterSkill).where(models.CharacterSkill.skill_id == skill_id)
    cs_result = await db.execute(cs_stmt)
    for cs in cs_result.scalars().all():
        await db.delete(cs)

    # tree_node_skills referencing this skill
    tns_stmt = select(models.TreeNodeSkill).where(models.TreeNodeSkill.skill_id == skill_id)
    tns_result = await db.execute(tns_stmt)
    for tns in tns_result.scalars().all():
        await db.delete(tns)

    # Cascades to base_damage / base_effects / perks via ORM
    await db.delete(skill)
    await db.commit()
    return True

# =====================================================================
# (FEAT-125) Perk + base damage/effect CRUD + character-skill progression
# =====================================================================

def _damage_to_dict(d) -> dict:
    return {
        "id": d.id,
        "damage_type": d.damage_type,
        "amount": d.amount,
        "description": d.description,
        "chance": d.chance,
        "target_side": d.target_side,
        "weapon_slot": d.weapon_slot,
    }


def _effect_to_dict(e) -> dict:
    return {
        "id": e.id,
        "target_side": e.target_side,
        "effect_name": e.effect_name,
        "description": e.description,
        "chance": e.chance,
        "duration": e.duration,
        "magnitude": e.magnitude,
        "attribute_key": e.attribute_key,
    }


# ---- base damage / effects (admin) ----

async def create_base_damage(db: AsyncSession, skill_id: int, data: schemas.DamageEntryWrite) -> models.SkillBaseDamage:
    obj = models.SkillBaseDamage(skill_id=skill_id, **data.dict())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def update_base_damage(db: AsyncSession, damage_id: int, data: schemas.DamageEntryWrite) -> models.SkillBaseDamage | None:
    obj = await db.get(models.SkillBaseDamage, damage_id)
    if not obj:
        return None
    for f, v in data.dict().items():
        setattr(obj, f, v)
    await db.commit()
    await db.refresh(obj)
    return obj


async def delete_base_damage(db: AsyncSession, damage_id: int) -> bool:
    obj = await db.get(models.SkillBaseDamage, damage_id)
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True


async def list_base_damage(db: AsyncSession, skill_id: int) -> list[models.SkillBaseDamage]:
    res = await db.execute(select(models.SkillBaseDamage).where(models.SkillBaseDamage.skill_id == skill_id))
    return res.scalars().all()


async def create_base_effect(db: AsyncSession, skill_id: int, data: schemas.EffectEntryWrite) -> models.SkillBaseEffect:
    obj = models.SkillBaseEffect(skill_id=skill_id, **data.dict())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def update_base_effect(db: AsyncSession, effect_id: int, data: schemas.EffectEntryWrite) -> models.SkillBaseEffect | None:
    obj = await db.get(models.SkillBaseEffect, effect_id)
    if not obj:
        return None
    for f, v in data.dict().items():
        setattr(obj, f, v)
    await db.commit()
    await db.refresh(obj)
    return obj


async def delete_base_effect(db: AsyncSession, effect_id: int) -> bool:
    obj = await db.get(models.SkillBaseEffect, effect_id)
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True


async def list_base_effects(db: AsyncSession, skill_id: int) -> list[models.SkillBaseEffect]:
    res = await db.execute(select(models.SkillBaseEffect).where(models.SkillBaseEffect.skill_id == skill_id))
    return res.scalars().all()


# ---- perk CRUD ----

async def _load_perk(db: AsyncSession, perk_id: int) -> models.SkillPerk | None:
    stmt = (
        select(models.SkillPerk)
        .options(
            selectinload(models.SkillPerk.damage_entries),
            selectinload(models.SkillPerk.effects),
        )
        .where(models.SkillPerk.id == perk_id)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def get_perk(db: AsyncSession, perk_id: int) -> models.SkillPerk | None:
    return await _load_perk(db, perk_id)


async def list_perks_for_skill(db: AsyncSession, skill_id: int) -> list[models.SkillPerk]:
    stmt = (
        select(models.SkillPerk)
        .options(
            selectinload(models.SkillPerk.damage_entries),
            selectinload(models.SkillPerk.effects),
        )
        .where(models.SkillPerk.skill_id == skill_id)
        .order_by(models.SkillPerk.sort_order, models.SkillPerk.id)
    )
    res = await db.execute(stmt)
    return res.scalars().all()


async def create_perk(db: AsyncSession, skill_id: int, data: schemas.SkillPerkCreate) -> models.SkillPerk:
    skill = await get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Навык не найден")
    perk = models.SkillPerk(
        skill_id=skill_id,
        name=data.name,
        description=data.description,
        perk_image=data.perk_image,
        delta_cost_energy=data.delta_cost_energy,
        delta_cost_mana=data.delta_cost_mana,
        delta_cooldown=data.delta_cooldown,
        sort_order=data.sort_order,
    )
    db.add(perk)
    await db.flush()
    for d in data.damage_entries:
        db.add(models.SkillPerkDamage(skill_perk_id=perk.id, **d.dict()))
    for e in data.effects:
        db.add(models.SkillPerkEffect(skill_perk_id=perk.id, **e.dict()))
    await db.commit()
    return await _load_perk(db, perk.id)


async def update_perk(db: AsyncSession, perk_id: int, data: schemas.SkillPerkUpdate) -> models.SkillPerk | None:
    perk = await _load_perk(db, perk_id)
    if not perk:
        return None
    perk.name = data.name
    perk.description = data.description
    perk.perk_image = data.perk_image
    perk.delta_cost_energy = data.delta_cost_energy
    perk.delta_cost_mana = data.delta_cost_mana
    perk.delta_cooldown = data.delta_cooldown
    perk.sort_order = data.sort_order

    # Replace sub-collections wholesale (perk pools are tiny).
    for old in list(perk.damage_entries):
        await db.delete(old)
    for old in list(perk.effects):
        await db.delete(old)
    await db.flush()
    for d in data.damage_entries:
        db.add(models.SkillPerkDamage(skill_perk_id=perk.id, **d.dict()))
    for e in data.effects:
        db.add(models.SkillPerkEffect(skill_perk_id=perk.id, **e.dict()))
    await db.commit()
    return await _load_perk(db, perk_id)


async def delete_perk(db: AsyncSession, perk_id: int) -> bool:
    """Delete a perk. Pool-size guard: refuse if it would drop below MIN_PERK_POOL."""
    perk = await db.get(models.SkillPerk, perk_id)
    if not perk:
        return False
    skill_id = perk.skill_id
    count_res = await db.execute(
        select(func.count(models.SkillPerk.id)).where(models.SkillPerk.skill_id == skill_id)
    )
    current = count_res.scalar_one() or 0
    if current - 1 < MIN_PERK_POOL:
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя удалить перк: пул должен содержать минимум {MIN_PERK_POOL} перков",
        )
    await db.delete(perk)
    await db.commit()
    return True


# ---- character_skills (new flat shape) ----

async def get_character_skill(db: AsyncSession, cs_id: int) -> models.CharacterSkill | None:
    return await db.get(models.CharacterSkill, cs_id)


async def get_character_skill_by_skill_id(
    db: AsyncSession, character_id: int, skill_id: int
) -> models.CharacterSkill | None:
    stmt = select(models.CharacterSkill).where(
        models.CharacterSkill.character_id == character_id,
        models.CharacterSkill.skill_id == skill_id,
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def _load_character_skill_full(db: AsyncSession, cs_id: int) -> models.CharacterSkill | None:
    stmt = (
        select(models.CharacterSkill)
        .options(
            selectinload(models.CharacterSkill.skill),
            selectinload(models.CharacterSkill.selected_perks),
        )
        .where(models.CharacterSkill.id == cs_id)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def list_character_skills_for_character(db: AsyncSession, character_id: int) -> list[models.CharacterSkill]:
    stmt = (
        select(models.CharacterSkill)
        .options(
            selectinload(models.CharacterSkill.skill),
            selectinload(models.CharacterSkill.selected_perks),
        )
        .where(models.CharacterSkill.character_id == character_id)
    )
    res = await db.execute(stmt)
    return res.scalars().all()


def serialize_character_skill(cs: models.CharacterSkill) -> dict:
    selected = [csp.skill_perk_id for csp in (cs.selected_perks or [])]
    return {
        "character_skill_id": cs.id,
        "skill_id": cs.skill_id,
        "character_id": cs.character_id,
        "level": cs.level or 0,
        "free_perk_points": max(0, (cs.level or 0) - len(selected)),
        "selected_perk_ids": selected,
        "reset_available_at": cs.reset_available_at,
        "skill": (
            {
                "id": cs.skill.id,
                "name": cs.skill.name,
                "skill_type": cs.skill.skill_type,
                "skill_image": cs.skill.skill_image,
            }
            if cs.skill
            else None
        ),
    }


async def create_character_skill(
    db: AsyncSession, character_id: int, skill_id: int, level: int = 0
) -> models.CharacterSkill:
    """Create a new (character, skill) row at the given level. 409 if it already exists."""
    skill = await get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Навык не найден")
    existing = await get_character_skill_by_skill_id(db, character_id, skill_id)
    if existing:
        raise HTTPException(status_code=409, detail="Навык уже есть")
    cs = models.CharacterSkill(character_id=character_id, skill_id=skill_id, level=level)
    db.add(cs)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Навык уже есть")
    await db.refresh(cs)
    return cs


async def admin_update_character_skill(
    db: AsyncSession, cs_id: int, skill_id: int, level: int
) -> models.CharacterSkill:
    cs = await get_character_skill(db, cs_id)
    if not cs:
        raise HTTPException(status_code=404, detail="CharacterSkill не найден")
    cs.skill_id = skill_id
    cs.level = level
    await db.commit()
    await db.refresh(cs)
    return cs


async def delete_character_skill(db: AsyncSession, cs_id: int) -> bool:
    cs = await get_character_skill(db, cs_id)
    if not cs:
        return False
    await db.delete(cs)
    await db.commit()
    return True


async def delete_all_character_skills(db: AsyncSession, character_id: int) -> int:
    stmt = select(models.CharacterSkill).where(models.CharacterSkill.character_id == character_id)
    res = await db.execute(stmt)
    rows = res.scalars().all()
    count = len(rows)
    for row in rows:
        await db.delete(row)
    if count > 0:
        await db.commit()
    return count


async def delete_character_skills_by_skill_ids(
    db: AsyncSession, character_id: int, skill_ids: list[int]
) -> int:
    if not skill_ids:
        return 0
    stmt = select(models.CharacterSkill).where(
        models.CharacterSkill.character_id == character_id,
        models.CharacterSkill.skill_id.in_(skill_ids),
    )
    res = await db.execute(stmt)
    rows = res.scalars().all()
    count = len(rows)
    for row in rows:
        await db.delete(row)
    if count > 0:
        await db.commit()
    return count


# ---- player progression: upgrade / pick perk / reset ----

async def upgrade_character_skill_level(db: AsyncSession, cs_id: int) -> models.CharacterSkill:
    cs = await _load_character_skill_full(db, cs_id)
    if not cs:
        raise HTTPException(status_code=404, detail="Навык персонажа не найден")
    if (cs.level or 0) >= MAX_LEVEL:
        raise HTTPException(status_code=409, detail="Навык уже на максимальном уровне")
    selected_count = len(cs.selected_perks or [])
    if selected_count < (cs.level or 0):
        raise HTTPException(
            status_code=409,
            detail="Сначала потратьте имеющееся очко перка",
        )
    cs.level = (cs.level or 0) + 1
    await db.commit()
    return await _load_character_skill_full(db, cs_id)


async def pick_perk_for_character_skill(
    db: AsyncSession, cs_id: int, perk_id: int
) -> models.CharacterSkill:
    cs = await _load_character_skill_full(db, cs_id)
    if not cs:
        raise HTTPException(status_code=404, detail="Навык персонажа не найден")
    perk = await db.get(models.SkillPerk, perk_id)
    if not perk:
        raise HTTPException(status_code=404, detail="Перк не найден")
    if perk.skill_id != cs.skill_id:
        raise HTTPException(status_code=400, detail="Перк не относится к этому навыку")
    selected = list(cs.selected_perks or [])
    if (cs.level or 0) - len(selected) < 1:
        raise HTTPException(status_code=409, detail="Нет свободных очков перков")
    if any(s.skill_perk_id == perk_id for s in selected):
        raise HTTPException(status_code=409, detail="Этот перк уже выбран")
    db.add(models.CharacterSkillPerk(character_skill_id=cs.id, skill_perk_id=perk_id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Этот перк уже выбран")
    return await _load_character_skill_full(db, cs_id)


async def reset_character_skill(db: AsyncSession, cs_id: int) -> models.CharacterSkill:
    cs = await _load_character_skill_full(db, cs_id)
    if not cs:
        raise HTTPException(status_code=404, detail="Навык персонажа не найден")
    if (cs.level or 0) <= 0:
        raise HTTPException(status_code=409, detail="Нечего сбрасывать: навык на уровне 0")
    now = datetime.utcnow()
    if cs.reset_available_at and cs.reset_available_at > now:
        raise HTTPException(
            status_code=409,
            detail=f"Сброс будет доступен {cs.reset_available_at.isoformat()}",
        )
    for csp in list(cs.selected_perks or []):
        await db.delete(csp)
    cs.level = 0
    cs.reset_available_at = now + timedelta(hours=RESET_COOLDOWN_HOURS)
    await db.commit()
    return await _load_character_skill_full(db, cs_id)


# ---- skill resolver (server-authoritative for battle-service) ----

async def get_skill_with_perks(db: AsyncSession, skill_id: int) -> dict | None:
    """Return skill base + perk pool dict (used for /skills/{id} and admin views)."""
    stmt = (
        select(models.Skill)
        .options(
            selectinload(models.Skill.base_damage),
            selectinload(models.Skill.base_effects),
            selectinload(models.Skill.perks).selectinload(models.SkillPerk.damage_entries),
            selectinload(models.Skill.perks).selectinload(models.SkillPerk.effects),
        )
        .where(models.Skill.id == skill_id)
    )
    res = await db.execute(stmt)
    skill = res.scalar_one_or_none()
    if not skill:
        return None

    upgrade_cost = (skill.purchase_cost or 0) // 2

    perks_out = []
    for p in sorted(skill.perks, key=lambda x: (x.sort_order or 0, x.id)):
        perks_out.append(
            {
                "id": p.id,
                "skill_id": p.skill_id,
                "name": p.name,
                "description": p.description,
                "perk_image": p.perk_image,
                "delta_cost_energy": p.delta_cost_energy,
                "delta_cost_mana": p.delta_cost_mana,
                "delta_cooldown": p.delta_cooldown,
                "sort_order": p.sort_order or 0,
                "damage_entries": [_damage_to_dict(d) for d in p.damage_entries],
                "effects": [_effect_to_dict(e) for e in p.effects],
            }
        )

    return {
        "id": skill.id,
        "name": skill.name,
        "skill_type": skill.skill_type,
        "description": skill.description,
        "purchase_cost": skill.purchase_cost or 0,
        "upgrade_cost": upgrade_cost,
        "skill_image": skill.skill_image,
        "min_level": skill.min_level or 1,
        "class_limitations": skill.class_limitations,
        "race_limitations": skill.race_limitations,
        "subrace_limitations": skill.subrace_limitations,
        "base": {
            "cost_energy": skill.cost_energy or 0,
            "cost_mana": skill.cost_mana or 0,
            "cooldown": skill.cooldown or 0,
            "level_requirement": skill.level_requirement or 1,
            "damage_entries": [_damage_to_dict(d) for d in skill.base_damage],
            "effects": [_effect_to_dict(e) for e in skill.base_effects],
        },
        "perks": perks_out,
    }


async def resolve_character_skill(
    db: AsyncSession, character_id: int, skill_id: int
) -> dict:
    """Server-authoritative resolved skill stats: base + Σ delta of selected perks."""
    skill_dict = await get_skill_with_perks(db, skill_id)
    if not skill_dict:
        raise HTTPException(status_code=404, detail="Навык не найден")

    cs = await get_character_skill_by_skill_id(db, character_id, skill_id)
    if not cs:
        raise HTTPException(status_code=409, detail="У персонажа нет этого навыка")
    cs_full = await _load_character_skill_full(db, cs.id)
    selected_ids = [csp.skill_perk_id for csp in (cs_full.selected_perks or [])]

    perks_by_id = {p["id"]: p for p in skill_dict["perks"]}
    selected_perks = [perks_by_id[pid] for pid in selected_ids if pid in perks_by_id]

    base = skill_dict["base"]
    cost_energy = base["cost_energy"]
    cost_mana = base["cost_mana"]
    cooldown = base["cooldown"]
    level_requirement = base["level_requirement"]

    damage_entries = list(base["damage_entries"])
    effects = list(base["effects"])

    for p in selected_perks:
        if p["delta_cost_energy"] is not None:
            cost_energy += p["delta_cost_energy"]
        if p["delta_cost_mana"] is not None:
            cost_mana += p["delta_cost_mana"]
        if p["delta_cooldown"] is not None:
            cooldown += p["delta_cooldown"]
        damage_entries.extend(p["damage_entries"])
        effects.extend(p["effects"])

    cooldown = max(0, cooldown)
    cost_energy = max(0, cost_energy)
    cost_mana = max(0, cost_mana)
    # level_requirement is fixed at the base value (PM clarification: no delta).

    return {
        "skill_id": skill_id,
        "character_id": character_id,
        "level": cs_full.level or 0,
        "selected_perk_ids": selected_ids,
        "skill_type": skill_dict["skill_type"],
        "cost_energy": cost_energy,
        "cost_mana": cost_mana,
        "cooldown": cooldown,
        "level_requirement": level_requirement,
        "damage_entries": damage_entries,
        "effects": effects,
    }


# ====================================================================
# CRUD: Class Skill Tree (FEAT-056)
# ====================================================================

async def create_class_tree(db: AsyncSession, data: schemas.ClassSkillTreeCreate) -> models.ClassSkillTree:
    tree = models.ClassSkillTree(**data.dict())
    db.add(tree)
    await db.commit()
    await db.refresh(tree)
    return tree


async def get_class_tree(db: AsyncSession, tree_id: int) -> models.ClassSkillTree | None:
    stmt = (
        select(models.ClassSkillTree)
        .options(
            selectinload(models.ClassSkillTree.nodes)
                .selectinload(models.TreeNode.node_skills),
            selectinload(models.ClassSkillTree.connections),
        )
        .where(models.ClassSkillTree.id == tree_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_class_trees(
    db: AsyncSession,
    class_id: int | None = None,
    tree_type: str | None = None,
) -> list[models.ClassSkillTree]:
    stmt = select(models.ClassSkillTree)
    if class_id is not None:
        stmt = stmt.where(models.ClassSkillTree.class_id == class_id)
    if tree_type is not None:
        stmt = stmt.where(models.ClassSkillTree.tree_type == tree_type)
    result = await db.execute(stmt)
    return result.scalars().all()


async def delete_class_tree(db: AsyncSession, tree_id: int) -> bool:
    tree = await get_class_tree(db, tree_id)
    if not tree:
        return False
    await db.delete(tree)
    await db.commit()
    return True


async def get_full_class_tree(db: AsyncSession, tree_id: int) -> dict | None:
    """Load tree with all nested data and build the full response dict with denormalized skill info."""
    stmt = (
        select(models.ClassSkillTree)
        .options(
            selectinload(models.ClassSkillTree.nodes)
                .selectinload(models.TreeNode.node_skills)
                .selectinload(models.TreeNodeSkill.skill),
            selectinload(models.ClassSkillTree.connections),
        )
        .where(models.ClassSkillTree.id == tree_id)
    )
    result = await db.execute(stmt)
    tree = result.scalar_one_or_none()
    if not tree:
        return None

    nodes_data = []
    for node in tree.nodes:
        skills_data = []
        for ns in node.node_skills:
            skill_obj = ns.skill
            skills_data.append({
                "id": ns.id,
                "skill_id": ns.skill_id,
                "sort_order": ns.sort_order,
                "skill_name": skill_obj.name if skill_obj else None,
                "skill_type": skill_obj.skill_type if skill_obj else None,
                "skill_image": skill_obj.skill_image if skill_obj else None,
            })
        nodes_data.append({
            "id": node.id,
            "tree_id": node.tree_id,
            "level_ring": node.level_ring,
            "position_x": node.position_x,
            "position_y": node.position_y,
            "name": node.name,
            "description": node.description,
            "node_type": node.node_type,
            "icon_image": node.icon_image,
            "sort_order": node.sort_order,
            "skills": skills_data,
        })

    connections_data = []
    for conn in tree.connections:
        connections_data.append({
            "id": conn.id,
            "from_node_id": conn.from_node_id,
            "to_node_id": conn.to_node_id,
        })

    return {
        "id": tree.id,
        "class_id": tree.class_id,
        "name": tree.name,
        "description": tree.description,
        "tree_type": tree.tree_type,
        "parent_tree_id": tree.parent_tree_id,
        "subclass_name": tree.subclass_name,
        "tree_image": tree.tree_image,
        "nodes": nodes_data,
        "connections": connections_data,
    }


async def save_full_class_tree(
    db: AsyncSession,
    tree_id: int,
    data: schemas.FullClassTreeUpdateRequest,
) -> dict:
    """
    Bulk save the entire class tree: nodes, connections, skill assignments.
    Follows the same temp-ID pattern as update_skill_full_tree.
    Returns {"detail": ..., "temp_id_map": {...}}.
    """
    # 1. Load existing tree
    stmt = (
        select(models.ClassSkillTree)
        .options(
            selectinload(models.ClassSkillTree.nodes)
                .selectinload(models.TreeNode.node_skills),
            selectinload(models.ClassSkillTree.connections),
        )
        .where(models.ClassSkillTree.id == tree_id)
    )
    result = await db.execute(stmt)
    tree = result.scalar_one_or_none()
    if not tree:
        raise HTTPException(status_code=404, detail="Class tree not found")

    # 2. Update tree metadata
    tree.class_id = data.class_id
    tree.name = data.name
    tree.description = data.description
    tree.tree_type = data.tree_type
    tree.parent_tree_id = data.parent_tree_id
    tree.subclass_name = data.subclass_name
    tree.tree_image = data.tree_image

    # 3. Build old nodes map
    old_nodes_map = {n.id: n for n in tree.nodes}
    old_connections_map = {c.id: c for c in tree.connections}

    # 4. Separate new and existing nodes
    new_nodes_data = []
    existing_nodes_data = []
    for node_data in data.nodes:
        if isinstance(node_data.id, str) and node_data.id.startswith("temp-"):
            new_nodes_data.append(node_data)
        elif isinstance(node_data.id, int):
            existing_nodes_data.append(node_data)
        else:
            raise HTTPException(
                status_code=400,
                detail="New nodes must have a temporary ID starting with 'temp-'"
            )

    temp_id_map = {}  # temp string ID -> real int ID

    # 5. Create new nodes
    new_node_objects = {}
    for node_data in new_nodes_data:
        new_node = models.TreeNode(
            tree_id=tree_id,
            level_ring=node_data.level_ring,
            position_x=node_data.position_x,
            position_y=node_data.position_y,
            name=node_data.name,
            description=node_data.description,
            node_type=node_data.node_type,
            icon_image=node_data.icon_image,
            sort_order=node_data.sort_order,
        )
        db.add(new_node)
        await db.flush()
        temp_id_map[node_data.id] = new_node.id
        new_node_objects[new_node.id] = new_node

    # 6. Update existing nodes
    existing_ids = []
    for node_data in existing_nodes_data:
        if node_data.id not in old_nodes_map:
            raise HTTPException(status_code=400, detail=f"Node {node_data.id} not found in tree")
        node_obj = old_nodes_map[node_data.id]
        node_obj.level_ring = node_data.level_ring
        node_obj.position_x = node_data.position_x
        node_obj.position_y = node_data.position_y
        node_obj.name = node_data.name
        node_obj.description = node_data.description
        node_obj.node_type = node_data.node_type
        node_obj.icon_image = node_data.icon_image
        node_obj.sort_order = node_data.sort_order
        existing_ids.append(node_data.id)

    # 7. Delete removed nodes (not in request)
    wanted_node_ids = set(existing_ids) | set(temp_id_map.values())
    for old_id, old_node in old_nodes_map.items():
        if old_id not in wanted_node_ids:
            await db.delete(old_node)

    # 8. Sync node_skills for each node
    all_nodes_map = {**old_nodes_map, **new_node_objects}
    for node_data in data.nodes:
        if isinstance(node_data.id, str):
            real_node_id = temp_id_map.get(node_data.id)
        else:
            real_node_id = node_data.id
        if not real_node_id or real_node_id not in all_nodes_map:
            continue
        node_obj = all_nodes_map[real_node_id]

        # Build set of desired (skill_id, sort_order) pairs
        desired_skills = {(s.skill_id, s.sort_order) for s in node_data.skills}
        desired_skill_ids = {s.skill_id for s in node_data.skills}

        # For new nodes, node_skills is empty (no lazy load needed)
        if real_node_id in new_node_objects:
            existing_node_skills = []
        else:
            existing_node_skills = list(node_obj.node_skills) if node_obj.node_skills else []
        for ns in existing_node_skills:
            if ns.skill_id not in desired_skill_ids:
                await db.delete(ns)
            else:
                # Update sort_order for existing skill assignments
                for s in node_data.skills:
                    if s.skill_id == ns.skill_id:
                        ns.sort_order = s.sort_order
                        break

        # Add new skill assignments
        existing_skill_ids = {ns.skill_id for ns in existing_node_skills}
        for s in node_data.skills:
            if s.skill_id not in existing_skill_ids:
                new_ns = models.TreeNodeSkill(
                    node_id=real_node_id,
                    skill_id=s.skill_id,
                    sort_order=s.sort_order,
                )
                db.add(new_ns)

    # 9. Resolve connections
    # Separate new and existing connections
    new_conns_data = []
    existing_conns_data = []
    for conn_data in data.connections:
        conn_id = conn_data.id
        if conn_id is None or (isinstance(conn_id, str) and conn_id.startswith("temp-")):
            new_conns_data.append(conn_data)
        elif isinstance(conn_id, int):
            existing_conns_data.append(conn_data)
        else:
            raise HTTPException(
                status_code=400,
                detail="New connections must have a temporary ID starting with 'temp-' or be null"
            )

    def resolve_node_id(node_ref):
        """Resolve a node ID reference (int or temp string) to a real int ID."""
        if isinstance(node_ref, str):
            resolved = temp_id_map.get(node_ref)
            if resolved is None:
                raise HTTPException(400, f"Temp node ID {node_ref} not found in temp_id_map")
            return resolved
        return node_ref

    # Create new connections
    for conn_data in new_conns_data:
        from_id = resolve_node_id(conn_data.from_node_id)
        to_id = resolve_node_id(conn_data.to_node_id)
        new_conn = models.TreeNodeConnection(
            tree_id=tree_id,
            from_node_id=from_id,
            to_node_id=to_id,
        )
        db.add(new_conn)
        await db.flush()
        if conn_data.id and isinstance(conn_data.id, str):
            temp_id_map[conn_data.id] = new_conn.id

    # Update existing connections
    existing_conn_ids = []
    for conn_data in existing_conns_data:
        if conn_data.id not in old_connections_map:
            raise HTTPException(status_code=400, detail=f"Connection {conn_data.id} not found in tree")
        conn_obj = old_connections_map[conn_data.id]
        conn_obj.from_node_id = resolve_node_id(conn_data.from_node_id)
        conn_obj.to_node_id = resolve_node_id(conn_data.to_node_id)
        existing_conn_ids.append(conn_data.id)

    # Delete removed connections
    wanted_conn_ids = set(existing_conn_ids)
    # Also add the newly created connection IDs
    for conn_data in new_conns_data:
        if conn_data.id and isinstance(conn_data.id, str) and conn_data.id in temp_id_map:
            wanted_conn_ids.add(temp_id_map[conn_data.id])
    for old_id, old_conn in old_connections_map.items():
        if old_id not in wanted_conn_ids:
            await db.delete(old_conn)

    # 10. Single commit
    await db.commit()

    return {"detail": "Class tree updated successfully", "temp_id_map": temp_id_map}


# -----------------------
# CRUD: TreeNode (individual operations)
# -----------------------
async def create_tree_node(db: AsyncSession, data: schemas.TreeNodeCreate) -> models.TreeNode:
    node = models.TreeNode(**data.dict())
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


async def update_tree_node(db: AsyncSession, node_id: int, data: schemas.TreeNodeBase) -> models.TreeNode | None:
    stmt = select(models.TreeNode).where(models.TreeNode.id == node_id)
    result = await db.execute(stmt)
    node = result.scalar_one_or_none()
    if not node:
        return None
    for field, value in data.dict(exclude_unset=True).items():
        setattr(node, field, value)
    await db.commit()
    await db.refresh(node)
    return node


async def delete_tree_node(db: AsyncSession, node_id: int) -> bool:
    stmt = (
        select(models.TreeNode)
        .options(selectinload(models.TreeNode.node_skills))
        .where(models.TreeNode.id == node_id)
    )
    result = await db.execute(stmt)
    node = result.scalar_one_or_none()
    if not node:
        return False
    await db.delete(node)
    await db.commit()
    return True


# (FEAT-125) build_conflicts_for_skill removed — binary-DAG ranks no longer exist.


# ====================================================================
# CRUD: Player Tree Progress (FEAT-057)
# ====================================================================

async def get_character_tree_progress(
    db: AsyncSession, character_id: int, tree_id: int
) -> list[models.CharacterTreeProgress]:
    """Get all chosen nodes for a character in a given tree."""
    stmt = (
        select(models.CharacterTreeProgress)
        .where(
            models.CharacterTreeProgress.character_id == character_id,
            models.CharacterTreeProgress.tree_id == tree_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def add_character_tree_progress(
    db: AsyncSession, character_id: int, tree_id: int, node_id: int
) -> models.CharacterTreeProgress:
    """Insert a new chosen node for the character."""
    progress = models.CharacterTreeProgress(
        character_id=character_id,
        tree_id=tree_id,
        node_id=node_id,
    )
    db.add(progress)
    await db.commit()
    await db.refresh(progress)
    return progress


async def delete_character_tree_progress_for_reset(
    db: AsyncSession, character_id: int, tree_id: int
) -> int:
    """Delete progress rows where node_type != 'subclass_choice'. Returns count of deleted rows."""
    # Get all progress rows for this character+tree
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
    rows = result.scalars().all()
    count = len(rows)
    for row in rows:
        await db.delete(row)
    if count > 0:
        await db.commit()
    return count


async def get_sibling_nodes(
    db: AsyncSession, tree_id: int, node_id: int
) -> list[int]:
    """
    Find branch conflict candidates: nodes at the same level_ring that share a parent.
    Connections can go either direction, so parent = connected node with lower level_ring.
    Returns list of sibling node IDs (excluding node_id itself).
    """
    # Get parent node IDs (connected nodes with lower level_ring)
    parent_ids = await get_parent_nodes(db, node_id)
    if not parent_ids:
        return []

    # Get the node's level_ring
    stmt = select(models.TreeNode.level_ring).where(models.TreeNode.id == node_id)
    result = await db.execute(stmt)
    level_ring = result.scalar_one_or_none()
    if level_ring is None:
        return []

    sibling_ids = set()
    for parent_id in parent_ids:
        # Find all nodes connected to this parent (both directions)
        stmt1 = select(models.TreeNodeConnection.to_node_id).where(
            models.TreeNodeConnection.from_node_id == parent_id
        )
        stmt2 = select(models.TreeNodeConnection.from_node_id).where(
            models.TreeNodeConnection.to_node_id == parent_id
        )
        r1 = await db.execute(stmt1)
        r2 = await db.execute(stmt2)
        connected = [row[0] for row in r1.fetchall()] + [row[0] for row in r2.fetchall()]

        # Filter: same level_ring, not self, not the parent
        candidate_ids = [cid for cid in connected if cid != node_id and cid != parent_id]
        if candidate_ids:
            stmt = select(models.TreeNode.id).where(
                models.TreeNode.id.in_(candidate_ids),
                models.TreeNode.level_ring == level_ring,
            )
            result = await db.execute(stmt)
            for row in result.fetchall():
                sibling_ids.add(row[0])

    return list(sibling_ids)


async def get_parent_nodes(db: AsyncSession, node_id: int) -> list[int]:
    """Get parent node IDs — nodes connected to this node with a LOWER level_ring."""
    # Get the node's level_ring
    stmt = select(models.TreeNode).where(models.TreeNode.id == node_id)
    result = await db.execute(stmt)
    node = result.scalar_one_or_none()
    if not node:
        return []

    # Find all connected nodes (both directions)
    stmt1 = select(models.TreeNodeConnection.from_node_id).where(
        models.TreeNodeConnection.to_node_id == node_id
    )
    stmt2 = select(models.TreeNodeConnection.to_node_id).where(
        models.TreeNodeConnection.from_node_id == node_id
    )
    r1 = await db.execute(stmt1)
    r2 = await db.execute(stmt2)
    connected_ids = [row[0] for row in r1.fetchall()] + [row[0] for row in r2.fetchall()]

    if not connected_ids:
        return []

    # Filter to nodes with lower level_ring (= parents)
    stmt = select(models.TreeNode.id).where(
        models.TreeNode.id.in_(connected_ids),
        models.TreeNode.level_ring < node.level_ring,
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.fetchall()]


async def get_skills_for_nodes(db: AsyncSession, node_ids: list[int]) -> list[int]:
    """Get skill_ids from tree_node_skills for the given node_ids."""
    if not node_ids:
        return []
    stmt = (
        select(models.TreeNodeSkill.skill_id)
        .where(models.TreeNodeSkill.node_id.in_(node_ids))
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.fetchall()]


# (FEAT-125) duplicate delete_character_skills_by_skill_ids removed — defined earlier in this file.


async def get_class_tree_by_class_id(
    db: AsyncSession, class_id: int, tree_type: str = "class"
) -> models.ClassSkillTree | None:
    """Find a class_skill_tree by class_id and tree_type."""
    stmt = (
        select(models.ClassSkillTree)
        .where(
            models.ClassSkillTree.class_id == class_id,
            models.ClassSkillTree.tree_type == tree_type,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


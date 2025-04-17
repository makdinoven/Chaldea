from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from sqlalchemy.orm import selectinload

import models, schemas

# -----------------------
# CRUD: Skill
# -----------------------
async def create_skill(db: AsyncSession, data: schemas.SkillCreate) -> models.Skill:
    new_skill = models.Skill(**data.dict())
    db.add(new_skill)
    await db.commit()
    await db.refresh(new_skill)
    return new_skill

async def get_skill(db: AsyncSession, skill_id: int) -> models.Skill | None:
    result = await db.execute(select(models.Skill).where(models.Skill.id == skill_id))
    return result.scalar_one_or_none()

async def list_skills(db: AsyncSession) -> list[models.Skill]:
    result = await db.execute(select(models.Skill))
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
    await db.delete(skill)
    await db.commit()
    return True

# -----------------------
# CRUD: SkillRank
# -----------------------
async def create_skill_rank(db: AsyncSession, data: schemas.SkillRankCreate) -> models.SkillRank:
    new_rank = models.SkillRank(**data.dict())
    db.add(new_rank)
    await db.commit()
    await db.refresh(new_rank)
    return new_rank

async def get_skill_rank(db: AsyncSession, rank_id: int) -> models.SkillRank | None:
    result = await db.execute(select(models.SkillRank).where(models.SkillRank.id == rank_id))
    return result.scalar_one_or_none()

async def list_skill_ranks_by_skill(db: AsyncSession, skill_id: int) -> list[models.SkillRank]:
    result = await db.execute(select(models.SkillRank).where(models.SkillRank.skill_id == skill_id))
    return result.scalars().all()

async def update_skill_rank(db: AsyncSession, rank_id: int, data: schemas.SkillRankUpdate) -> models.SkillRank | None:
    rank = await get_skill_rank(db, rank_id)
    if not rank:
        return None
    for field, value in data.dict(exclude_unset=True).items():
        setattr(rank, field, value)
    await db.commit()
    await db.refresh(rank)
    return rank

async def delete_skill_rank(db: AsyncSession, rank_id: int) -> bool:
    rank = await get_skill_rank(db, rank_id)
    if not rank:
        return False
    await db.delete(rank)
    await db.commit()
    return True

# -----------------------
# CRUD: SkillRankDamage
# -----------------------
async def create_skill_rank_damage(db: AsyncSession, data: schemas.SkillRankDamageCreate) -> models.SkillRankDamage:
    new_damage = models.SkillRankDamage(**data.dict())
    db.add(new_damage)
    await db.commit()
    await db.refresh(new_damage)
    return new_damage

async def get_skill_rank_damage(db: AsyncSession, damage_id: int) -> models.SkillRankDamage | None:
    stmt = select(models.SkillRankDamage).where(models.SkillRankDamage.id == damage_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def update_skill_rank_damage(db: AsyncSession, damage_id: int, data: schemas.SkillRankDamageUpdate) -> models.SkillRankDamage | None:
    dmg = await get_skill_rank_damage(db, damage_id)
    if not dmg:
        return None
    for field, value in data.dict(exclude_unset=True).items():
        setattr(dmg, field, value)
    await db.commit()
    await db.refresh(dmg)
    return dmg

async def delete_skill_rank_damage(db: AsyncSession, damage_id: int) -> bool:
    dmg = await get_skill_rank_damage(db, damage_id)
    if not dmg:
        return False
    await db.delete(dmg)
    await db.commit()
    return True

# -----------------------
# CRUD: SkillRankEffect
# -----------------------
async def create_skill_rank_effect(db: AsyncSession, data: schemas.SkillRankEffectCreate) -> models.SkillRankEffect:
    eff = models.SkillRankEffect(**data.dict())
    db.add(eff)
    await db.commit()
    await db.refresh(eff)
    return eff

async def get_skill_rank_effect(db: AsyncSession, effect_id: int) -> models.SkillRankEffect | None:
    stmt = select(models.SkillRankEffect).where(models.SkillRankEffect.id == effect_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def update_skill_rank_effect(db: AsyncSession, effect_id: int, data: schemas.SkillRankEffectUpdate) -> models.SkillRankEffect | None:
    eff = await get_skill_rank_effect(db, effect_id)
    if not eff:
        return None
    for field, value in data.dict(exclude_unset=True).items():
        setattr(eff, field, value)
    await db.commit()
    await db.refresh(eff)
    return eff

async def delete_skill_rank_effect(db: AsyncSession, effect_id: int) -> bool:
    eff = await get_skill_rank_effect(db, effect_id)
    if not eff:
        return False
    await db.delete(eff)
    await db.commit()
    return True

# -----------------------
# CRUD: CharacterSkill
# -----------------------
async def create_character_skill(db: AsyncSession, data: schemas.CharacterSkillCreate) -> models.CharacterSkill:
    cs = models.CharacterSkill(**data.dict())
    db.add(cs)
    await db.commit()
    await db.refresh(cs)
    return cs

async def get_character_skill(db: AsyncSession, cs_id: int) -> models.CharacterSkill | None:
    stmt = select(models.CharacterSkill).where(models.CharacterSkill.id == cs_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def list_character_skills_for_character(db: AsyncSession, character_id: int) -> list[models.CharacterSkill]:
    stmt = select(models.CharacterSkill).where(models.CharacterSkill.character_id == character_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def delete_character_skill(db: AsyncSession, cs_id: int) -> bool:
    cs = await get_character_skill(db, cs_id)
    if not cs:
        return False
    await db.delete(cs)
    await db.commit()
    return True

async def get_character_skill_by_skill_id(db: AsyncSession, character_id: int, skill_id: int) -> models.CharacterSkill | None:
    from sqlalchemy import select
    stmt = (
        select(models.CharacterSkill)
        .join(models.SkillRank, models.SkillRank.id == models.CharacterSkill.skill_rank_id)
        .where(models.CharacterSkill.character_id == character_id)
        .where(models.SkillRank.skill_id == skill_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def update_character_skill_rank(db: AsyncSession, cs_id: int, new_rank_id: int) -> models.CharacterSkill:
    cs = await get_character_skill(db, cs_id)
    if not cs:
        raise HTTPException(status_code=404, detail="CharacterSkill not found")
    cs.skill_rank_id = new_rank_id
    await db.commit()
    await db.refresh(cs)
    return cs


# -----------------------
# Синхронизация damage_entries и effects
# -----------------------
async def sync_damage_entries(db: AsyncSession, rank_obj: models.SkillRank, new_damage_list):
    result = await db.execute(
        select(models.SkillRank)
        .options(selectinload(models.SkillRank.damage_entries))
        .where(models.SkillRank.id == rank_obj.id)
    )
    rank = result.scalar_one()
    if not rank:
        raise HTTPException(status_code=404, detail=f"Rank {rank_obj.id} not found")

    old_entries = {d.id: d for d in rank.damage_entries}
    keep_ids = []

    for dmg_data in new_damage_list:
        # Если duration присутствует в dmg_data, просто игнорируем его
        if not getattr(dmg_data, "id", None):
            new_dmg = models.SkillRankDamage(
                skill_rank_id=rank.id,
                damage_type=dmg_data.damage_type,
                amount=dmg_data.amount,
                description=dmg_data.description,
                chance=dmg_data.chance,
                target_side=dmg_data.target_side,
                weapon_slot=dmg_data.weapon_slot,
            )
            db.add(new_dmg)
        else:
            if dmg_data.id not in old_entries:
                raise HTTPException(400, f"Damage entry id={dmg_data.id} not found")
            old_entry = old_entries[dmg_data.id]
            old_entry.damage_type = dmg_data.damage_type
            old_entry.amount = dmg_data.amount
            old_entry.description = dmg_data.description
            old_entry.chance = dmg_data.chance
            old_entry.target_side = dmg_data.target_side
            old_entry.weapon_slot = dmg_data.weapon_slot
            keep_ids.append(dmg_data.id)

    for old_id, old_entry in old_entries.items():
        if old_id not in keep_ids:
            await db.delete(old_entry)

    await db.commit()
    await db.refresh(rank)
    return rank

async def sync_effects(db: AsyncSession, rank_obj: models.SkillRank, new_effect_list):
    result = await db.execute(
        select(models.SkillRank)
        .options(selectinload(models.SkillRank.effects))
        .where(models.SkillRank.id == rank_obj.id)
    )
    rank = result.scalar_one_or_none()
    if not rank:
        raise HTTPException(status_code=404, detail=f"Rank {rank_obj.id} not found")
    old_map = {e.id: e for e in rank_obj.effects}

    keep_ids = []
    for eff_data in new_effect_list:
        if eff_data.id is None:
            new_eff = models.SkillRankEffect(
                skill_rank_id=rank_obj.id,
                target_side=eff_data.target_side,
                effect_name=eff_data.effect_name,
                description=eff_data.description,
                chance=eff_data.chance,
                duration=eff_data.duration,
                magnitude=eff_data.magnitude,
                attribute_key=eff_data.attribute_key
            )
            db.add(new_eff)
        else:
            old_eff = old_map.get(eff_data.id)
            if not old_eff:
                raise HTTPException(400, f"Effect entry id={eff_data.id} not found")
            old_eff.target_side = eff_data.target_side
            old_eff.effect_name = eff_data.effect_name
            old_eff.description = eff_data.description
            old_eff.chance = eff_data.chance
            old_eff.duration = eff_data.duration
            old_eff.magnitude = eff_data.magnitude
            old_eff.attribute_key = eff_data.attribute_key
            keep_ids.append(eff_data.id)

    for old_id, old_obj in old_map.items():
        if old_id not in keep_ids:
            await db.delete(old_obj)


async def build_conflicts_for_skill(db: AsyncSession, skill_id: int) -> set[tuple[int,int]]:
    """
    Собирает все пары конфликтующих rank_id (x,y),
    если один родитель имеет нескольких детей.
    """
    from models import SkillRank
    from sqlalchemy import select

    stmt = select(SkillRank).where(SkillRank.skill_id == skill_id)
    result = await db.execute(stmt)
    ranks = result.scalars().all()

    parent_to_children = {}
    for r in ranks:
        parent_to_children[r.id] = []

    for r in ranks:
        if r.left_child_id:
            parent_to_children[r.id].append(r.left_child_id)
        if r.right_child_id:
            parent_to_children[r.id].append(r.right_child_id)

    conflicts = set()
    for parent_id, children_list in parent_to_children.items():
        n = len(children_list)
        for i in range(n):
            for j in range(i+1, n):
                c1 = children_list[i]
                c2 = children_list[j]
                conflicts.add((c1, c2))
                conflicts.add((c2, c1))
    return conflicts


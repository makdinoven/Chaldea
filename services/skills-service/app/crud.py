from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
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

    # Delete character_skills referencing this skill's ranks
    rank_ids_stmt = select(models.SkillRank.id).where(models.SkillRank.skill_id == skill_id)
    rank_ids_result = await db.execute(rank_ids_stmt)
    rank_ids = [r[0] for r in rank_ids_result.fetchall()]

    if rank_ids:
        # Delete character_skills
        cs_stmt = select(models.CharacterSkill).where(
            models.CharacterSkill.skill_rank_id.in_(rank_ids)
        )
        cs_result = await db.execute(cs_stmt)
        for cs in cs_result.scalars().all():
            await db.delete(cs)

    # Delete tree_node_skills referencing this skill
    tns_stmt = select(models.TreeNodeSkill).where(models.TreeNodeSkill.skill_id == skill_id)
    tns_result = await db.execute(tns_stmt)
    for tns in tns_result.scalars().all():
        await db.delete(tns)

    # Now delete the skill (cascades to ranks → damage/effects via ORM)
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
    stmt = (
        select(models.SkillRank)
        .options(
            selectinload(models.SkillRank.damage_entries),
            selectinload(models.SkillRank.effects),
        )
        .where(models.SkillRank.id == rank_id)
    )
    result = await db.execute(stmt)
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

async def list_character_skills_for_character(db: AsyncSession, character_id: int):
    stmt = (
        select(models.CharacterSkill)
        .where(models.CharacterSkill.character_id == character_id)
        .options(
            selectinload(models.CharacterSkill.skill_rank)
                .selectinload(models.SkillRank.damage_entries),
            selectinload(models.CharacterSkill.skill_rank)
                .selectinload(models.SkillRank.effects),
        )
    )
    result = await db.execute(stmt)
    char_skills = result.scalars().all()

    # Denormalize skill info (name, type, image) from the Skill table
    skill_ids = list({cs.skill_rank.skill_id for cs in char_skills if cs.skill_rank})
    skill_map: dict[int, models.Skill] = {}
    if skill_ids:
        skills_result = await db.execute(
            select(models.Skill).where(models.Skill.id.in_(skill_ids))
        )
        for skill in skills_result.scalars().all():
            skill_map[skill.id] = skill

    # Attach denormalized fields
    for cs in char_skills:
        if cs.skill_rank and cs.skill_rank.skill_id in skill_map:
            skill = skill_map[cs.skill_rank.skill_id]
            cs.skill_name = skill.name
            cs.skill_type = skill.skill_type
            cs.skill_image = skill.skill_image
            cs.skill_description = skill.description
            cs.skill_min_level = skill.min_level
        else:
            cs.skill_name = None
            cs.skill_type = None
            cs.skill_image = None
            cs.skill_description = None
            cs.skill_min_level = None

    return char_skills

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

async def delete_all_character_skills(db: AsyncSession, character_id: int) -> int:
    """Delete all CharacterSkill rows for the given character_id. Returns count deleted."""
    stmt = select(models.CharacterSkill).where(models.CharacterSkill.character_id == character_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    count = len(rows)
    for row in rows:
        await db.delete(row)
    if count > 0:
        await db.commit()
    return count


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
    old_map = {e.id: e for e in rank.effects}

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


async def delete_character_skills_by_skill_ids(
    db: AsyncSession, character_id: int, skill_ids: list[int]
) -> int:
    """
    Delete character_skills rows where character_id matches AND
    skill_rank.skill_id is in skill_ids. Returns count of deleted rows.
    """
    if not skill_ids:
        return 0
    stmt = (
        select(models.CharacterSkill)
        .join(models.SkillRank, models.SkillRank.id == models.CharacterSkill.skill_rank_id)
        .where(
            models.CharacterSkill.character_id == character_id,
            models.SkillRank.skill_id.in_(skill_ids),
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


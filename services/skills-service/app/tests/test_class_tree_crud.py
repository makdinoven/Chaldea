"""
Tests for FEAT-056 Class Skill Tree CRUD functions in skills-service.

Tests crud.py functions directly (no HTTP layer):
- create_class_tree
- list_class_trees
- get_class_tree
- get_full_class_tree
- save_full_class_tree (bulk save with temp IDs, updates, deletes)
- delete_class_tree (cascade)
- create_tree_node, update_tree_node, delete_tree_node

skills-service is ASYNC (aiomysql), so we use async SQLite + AsyncSession.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# ---------------------------------------------------------------------------
# Async SQLite setup
# ---------------------------------------------------------------------------

_async_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
)

_AsyncTestSessionLocal = async_sessionmaker(
    _async_test_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# ---------------------------------------------------------------------------
# Patch database before importing models/crud
# ---------------------------------------------------------------------------
import database  # noqa: E402

database.engine = _async_test_engine
database.async_session = _AsyncTestSessionLocal


async def _test_create_tables():
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)


database.create_tables = _test_create_tables

import models  # noqa: E402
import schemas  # noqa: E402
import crud  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def setup_db():
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db(setup_db):
    async with _AsyncTestSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

async def _seed_skill(db: AsyncSession, skill_id: int = 1, name: str = "Fireball"):
    skill = models.Skill(id=skill_id, name=name, skill_type="Attack", description="Test skill")
    db.add(skill)
    await db.commit()
    return skill


async def _create_tree(db: AsyncSession, class_id: int = 1, name: str = "Warrior Tree",
                       tree_type: str = "class", subclass_name: str = None,
                       parent_tree_id: int = None) -> models.ClassSkillTree:
    data = schemas.ClassSkillTreeCreate(
        class_id=class_id,
        name=name,
        tree_type=tree_type,
        subclass_name=subclass_name,
        parent_tree_id=parent_tree_id,
    )
    return await crud.create_class_tree(db, data)


# ===========================================================================
# create_class_tree
# ===========================================================================

class TestCreateClassTree:

    @pytest.mark.asyncio
    async def test_basic_creation(self, db):
        tree = await _create_tree(db)
        assert tree.id is not None
        assert tree.class_id == 1
        assert tree.name == "Warrior Tree"
        assert tree.tree_type == "class"
        assert tree.subclass_name is None
        assert tree.parent_tree_id is None

    @pytest.mark.asyncio
    async def test_all_fields_stored(self, db):
        data = schemas.ClassSkillTreeCreate(
            class_id=2,
            name="Mage Tree",
            description="For mages",
            tree_type="class",
            tree_image="http://example.com/mage.png",
        )
        tree = await crud.create_class_tree(db, data)
        assert tree.description == "For mages"
        assert tree.tree_image == "http://example.com/mage.png"

    @pytest.mark.asyncio
    async def test_subclass_tree_creation(self, db):
        parent = await _create_tree(db)
        sub = await _create_tree(
            db, name="Berserker", tree_type="subclass",
            subclass_name="Berserker", parent_tree_id=parent.id,
        )
        assert sub.tree_type == "subclass"
        assert sub.parent_tree_id == parent.id
        assert sub.subclass_name == "Berserker"


# ===========================================================================
# list_class_trees
# ===========================================================================

class TestListClassTrees:

    @pytest.mark.asyncio
    async def test_list_empty(self, db):
        result = await crud.list_class_trees(db)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_all(self, db):
        await _create_tree(db, class_id=1, name="Warrior")
        await _create_tree(db, class_id=2, name="Mage")
        result = await crud.list_class_trees(db)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filter_by_class_id(self, db):
        await _create_tree(db, class_id=1, name="Warrior")
        await _create_tree(db, class_id=2, name="Mage")
        result = await crud.list_class_trees(db, class_id=1)
        assert len(result) == 1
        assert result[0].class_id == 1

    @pytest.mark.asyncio
    async def test_filter_by_tree_type(self, db):
        parent = await _create_tree(db, class_id=1, name="Warrior")
        await _create_tree(
            db, class_id=1, name="Berserker", tree_type="subclass",
            subclass_name="Berserker", parent_tree_id=parent.id,
        )
        result = await crud.list_class_trees(db, tree_type="subclass")
        assert len(result) == 1
        assert result[0].tree_type == "subclass"

    @pytest.mark.asyncio
    async def test_filter_by_both(self, db):
        await _create_tree(db, class_id=1, name="Warrior")
        await _create_tree(db, class_id=2, name="Mage")
        result = await crud.list_class_trees(db, class_id=1, tree_type="class")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_filter_no_match(self, db):
        await _create_tree(db, class_id=1, name="Warrior")
        result = await crud.list_class_trees(db, class_id=999)
        assert len(result) == 0


# ===========================================================================
# get_full_class_tree
# ===========================================================================

class TestGetFullClassTree:

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, db):
        result = await crud.get_full_class_tree(db, 99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_tree_structure(self, db):
        tree = await _create_tree(db)
        result = await crud.get_full_class_tree(db, tree.id)
        assert result is not None
        assert result["id"] == tree.id
        assert result["nodes"] == []
        assert result["connections"] == []

    @pytest.mark.asyncio
    async def test_nested_data_with_nodes(self, db):
        tree = await _create_tree(db)

        # Create a node directly
        node = models.TreeNode(
            tree_id=tree.id, level_ring=1, position_x=0, position_y=0,
            name="Root", node_type="root", sort_order=0,
        )
        db.add(node)
        await db.commit()

        result = await crud.get_full_class_tree(db, tree.id)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["name"] == "Root"
        assert result["nodes"][0]["level_ring"] == 1

    @pytest.mark.asyncio
    async def test_denormalized_skill_info(self, db):
        """get_full_class_tree should include skill_name, skill_type, skill_image from Skill."""
        skill = await _seed_skill(db, skill_id=1, name="Fireball")
        tree = await _create_tree(db)

        node = models.TreeNode(
            tree_id=tree.id, level_ring=1, position_x=0, position_y=0,
            name="Root", node_type="root",
        )
        db.add(node)
        await db.flush()

        ns = models.TreeNodeSkill(node_id=node.id, skill_id=1, sort_order=0)
        db.add(ns)
        await db.commit()

        result = await crud.get_full_class_tree(db, tree.id)
        skills = result["nodes"][0]["skills"]
        assert len(skills) == 1
        assert skills[0]["skill_name"] == "Fireball"
        assert skills[0]["skill_type"] == "Attack"
        assert skills[0]["skill_id"] == 1

    @pytest.mark.asyncio
    async def test_connections_included(self, db):
        tree = await _create_tree(db)

        node_a = models.TreeNode(
            tree_id=tree.id, level_ring=1, position_x=0, position_y=0,
            name="A", node_type="root",
        )
        node_b = models.TreeNode(
            tree_id=tree.id, level_ring=5, position_x=100, position_y=100,
            name="B", node_type="regular",
        )
        db.add_all([node_a, node_b])
        await db.flush()

        conn = models.TreeNodeConnection(
            tree_id=tree.id, from_node_id=node_a.id, to_node_id=node_b.id,
        )
        db.add(conn)
        await db.commit()

        result = await crud.get_full_class_tree(db, tree.id)
        assert len(result["connections"]) == 1
        assert result["connections"][0]["from_node_id"] == node_a.id
        assert result["connections"][0]["to_node_id"] == node_b.id


# ===========================================================================
# save_full_class_tree (the complex bulk save)
# ===========================================================================

class TestSaveFullClassTree:

    @pytest.mark.asyncio
    async def test_create_new_nodes_with_temp_ids(self, db):
        tree = await _create_tree(db)

        data = schemas.FullClassTreeUpdateRequest(
            id=tree.id,
            class_id=1,
            name="Warrior Tree",
            tree_type="class",
            nodes=[
                schemas.TreeNodeInTree(
                    id="temp-1", level_ring=1, position_x=0, position_y=0,
                    name="Root", node_type="root", sort_order=0, skills=[],
                ),
                schemas.TreeNodeInTree(
                    id="temp-2", level_ring=5, position_x=100, position_y=100,
                    name="Level 5", node_type="regular", sort_order=0, skills=[],
                ),
            ],
            connections=[],
        )
        result = await crud.save_full_class_tree(db, tree.id, data)
        assert "temp_id_map" in result
        assert "temp-1" in result["temp_id_map"]
        assert "temp-2" in result["temp_id_map"]
        assert isinstance(result["temp_id_map"]["temp-1"], int)
        assert result["temp_id_map"]["temp-1"] != result["temp_id_map"]["temp-2"]

    @pytest.mark.asyncio
    async def test_update_existing_nodes(self, db):
        tree = await _create_tree(db)

        # Create a node first
        data1 = schemas.FullClassTreeUpdateRequest(
            id=tree.id, class_id=1, name="Tree", tree_type="class",
            nodes=[
                schemas.TreeNodeInTree(
                    id="temp-1", level_ring=1, position_x=0, position_y=0,
                    name="Original", node_type="root", sort_order=0, skills=[],
                ),
            ],
            connections=[],
        )
        r1 = await crud.save_full_class_tree(db, tree.id, data1)
        real_id = r1["temp_id_map"]["temp-1"]

        # Update with the real ID
        data2 = schemas.FullClassTreeUpdateRequest(
            id=tree.id, class_id=1, name="Tree", tree_type="class",
            nodes=[
                schemas.TreeNodeInTree(
                    id=real_id, level_ring=1, position_x=50, position_y=50,
                    name="Updated", node_type="root", sort_order=1, skills=[],
                ),
            ],
            connections=[],
        )
        r2 = await crud.save_full_class_tree(db, tree.id, data2)
        assert r2["temp_id_map"] == {}  # No temp IDs in second save

        full = await crud.get_full_class_tree(db, tree.id)
        assert len(full["nodes"]) == 1
        assert full["nodes"][0]["name"] == "Updated"
        assert full["nodes"][0]["position_x"] == 50.0

    @pytest.mark.asyncio
    async def test_delete_removed_nodes(self, db):
        tree = await _create_tree(db)

        # Create two nodes
        data1 = schemas.FullClassTreeUpdateRequest(
            id=tree.id, class_id=1, name="Tree", tree_type="class",
            nodes=[
                schemas.TreeNodeInTree(
                    id="temp-1", level_ring=1, position_x=0, position_y=0,
                    name="A", node_type="root", sort_order=0, skills=[],
                ),
                schemas.TreeNodeInTree(
                    id="temp-2", level_ring=5, position_x=100, position_y=100,
                    name="B", node_type="regular", sort_order=0, skills=[],
                ),
            ],
            connections=[],
        )
        r1 = await crud.save_full_class_tree(db, tree.id, data1)
        id_a = r1["temp_id_map"]["temp-1"]

        # Save again with only node A — node B should be deleted
        data2 = schemas.FullClassTreeUpdateRequest(
            id=tree.id, class_id=1, name="Tree", tree_type="class",
            nodes=[
                schemas.TreeNodeInTree(
                    id=id_a, level_ring=1, position_x=0, position_y=0,
                    name="A", node_type="root", sort_order=0, skills=[],
                ),
            ],
            connections=[],
        )
        await crud.save_full_class_tree(db, tree.id, data2)

        full = await crud.get_full_class_tree(db, tree.id)
        assert len(full["nodes"]) == 1
        assert full["nodes"][0]["name"] == "A"

    @pytest.mark.asyncio
    async def test_connection_temp_id_resolution(self, db):
        tree = await _create_tree(db)

        data = schemas.FullClassTreeUpdateRequest(
            id=tree.id, class_id=1, name="Tree", tree_type="class",
            nodes=[
                schemas.TreeNodeInTree(
                    id="temp-1", level_ring=1, position_x=0, position_y=0,
                    name="Root", node_type="root", sort_order=0, skills=[],
                ),
                schemas.TreeNodeInTree(
                    id="temp-2", level_ring=5, position_x=100, position_y=100,
                    name="L5", node_type="regular", sort_order=0, skills=[],
                ),
            ],
            connections=[
                schemas.TreeNodeConnectionInTree(
                    id="temp-c1", from_node_id="temp-1", to_node_id="temp-2",
                ),
            ],
        )
        result = await crud.save_full_class_tree(db, tree.id, data)
        assert "temp-c1" in result["temp_id_map"]

        full = await crud.get_full_class_tree(db, tree.id)
        assert len(full["connections"]) == 1
        assert full["connections"][0]["from_node_id"] == result["temp_id_map"]["temp-1"]
        assert full["connections"][0]["to_node_id"] == result["temp_id_map"]["temp-2"]

    @pytest.mark.asyncio
    async def test_skill_assignment_sync(self, db):
        await _seed_skill(db, skill_id=1, name="Fireball")
        await _seed_skill(db, skill_id=2, name="Ice Bolt")
        tree = await _create_tree(db)

        # First save: assign skill 1
        data1 = schemas.FullClassTreeUpdateRequest(
            id=tree.id, class_id=1, name="Tree", tree_type="class",
            nodes=[
                schemas.TreeNodeInTree(
                    id="temp-1", level_ring=1, position_x=0, position_y=0,
                    name="Root", node_type="root", sort_order=0,
                    skills=[schemas.TreeNodeSkillEntry(skill_id=1, sort_order=0)],
                ),
            ],
            connections=[],
        )
        r1 = await crud.save_full_class_tree(db, tree.id, data1)
        real_id = r1["temp_id_map"]["temp-1"]

        full1 = await crud.get_full_class_tree(db, tree.id)
        assert len(full1["nodes"][0]["skills"]) == 1
        assert full1["nodes"][0]["skills"][0]["skill_id"] == 1

        # Second save: replace skill 1 with skill 2
        data2 = schemas.FullClassTreeUpdateRequest(
            id=tree.id, class_id=1, name="Tree", tree_type="class",
            nodes=[
                schemas.TreeNodeInTree(
                    id=real_id, level_ring=1, position_x=0, position_y=0,
                    name="Root", node_type="root", sort_order=0,
                    skills=[schemas.TreeNodeSkillEntry(skill_id=2, sort_order=0)],
                ),
            ],
            connections=[],
        )
        await crud.save_full_class_tree(db, tree.id, data2)

        full2 = await crud.get_full_class_tree(db, tree.id)
        assert len(full2["nodes"][0]["skills"]) == 1
        assert full2["nodes"][0]["skills"][0]["skill_id"] == 2

    @pytest.mark.asyncio
    async def test_nonexistent_tree_raises_404(self, db):
        from fastapi import HTTPException
        data = schemas.FullClassTreeUpdateRequest(
            id=99999, class_id=1, name="Ghost", tree_type="class",
            nodes=[], connections=[],
        )
        with pytest.raises(HTTPException) as exc_info:
            await crud.save_full_class_tree(db, 99999, data)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_metadata_update(self, db):
        """save_full_class_tree should also update tree metadata (name, description, etc.)."""
        tree = await _create_tree(db)

        data = schemas.FullClassTreeUpdateRequest(
            id=tree.id, class_id=2, name="Mage Tree Now",
            description="Changed description",
            tree_type="subclass", subclass_name="Pyro",
            nodes=[], connections=[],
        )
        await crud.save_full_class_tree(db, tree.id, data)

        full = await crud.get_full_class_tree(db, tree.id)
        assert full["name"] == "Mage Tree Now"
        assert full["class_id"] == 2
        assert full["description"] == "Changed description"
        assert full["tree_type"] == "subclass"
        assert full["subclass_name"] == "Pyro"


# ===========================================================================
# delete_class_tree (cascade)
# ===========================================================================

class TestDeleteClassTree:

    @pytest.mark.asyncio
    async def test_delete_existing(self, db):
        tree = await _create_tree(db)
        success = await crud.delete_class_tree(db, tree.id)
        assert success is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db):
        success = await crud.delete_class_tree(db, 99999)
        assert success is False

    @pytest.mark.asyncio
    async def test_cascade_removes_nodes_and_connections(self, db):
        tree = await _create_tree(db)

        # Create nodes and connection
        node_a = models.TreeNode(
            tree_id=tree.id, level_ring=1, position_x=0, position_y=0,
            name="A", node_type="root",
        )
        node_b = models.TreeNode(
            tree_id=tree.id, level_ring=5, position_x=100, position_y=100,
            name="B", node_type="regular",
        )
        db.add_all([node_a, node_b])
        await db.flush()

        conn = models.TreeNodeConnection(
            tree_id=tree.id, from_node_id=node_a.id, to_node_id=node_b.id,
        )
        db.add(conn)
        await db.commit()

        # Delete the tree
        success = await crud.delete_class_tree(db, tree.id)
        assert success is True

        # Verify no data remains
        result = await crud.get_full_class_tree(db, tree.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_cascade_removes_skill_assignments(self, db):
        await _seed_skill(db, skill_id=1, name="Fireball")
        tree = await _create_tree(db)

        node = models.TreeNode(
            tree_id=tree.id, level_ring=1, position_x=0, position_y=0,
            name="Root", node_type="root",
        )
        db.add(node)
        await db.flush()

        ns = models.TreeNodeSkill(node_id=node.id, skill_id=1, sort_order=0)
        db.add(ns)
        await db.commit()

        success = await crud.delete_class_tree(db, tree.id)
        assert success is True

        # Tree and its nodes/skill assignments should be gone
        result = await crud.get_full_class_tree(db, tree.id)
        assert result is None


# ===========================================================================
# Individual node CRUD
# ===========================================================================

class TestTreeNodeCrud:

    @pytest.mark.asyncio
    async def test_create_tree_node(self, db):
        tree = await _create_tree(db)
        data = schemas.TreeNodeCreate(
            tree_id=tree.id, level_ring=1, position_x=10, position_y=20,
            name="TestNode", node_type="root", sort_order=0,
        )
        node = await crud.create_tree_node(db, data)
        assert node.id is not None
        assert node.tree_id == tree.id
        assert node.name == "TestNode"
        assert node.position_x == 10.0

    @pytest.mark.asyncio
    async def test_update_tree_node(self, db):
        tree = await _create_tree(db)
        data = schemas.TreeNodeCreate(
            tree_id=tree.id, level_ring=1, position_x=0, position_y=0,
            name="Original", node_type="root",
        )
        node = await crud.create_tree_node(db, data)

        update_data = schemas.TreeNodeBase(
            level_ring=5, position_x=99, position_y=99,
            name="Updated", node_type="regular", sort_order=2,
        )
        updated = await crud.update_tree_node(db, node.id, update_data)
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.level_ring == 5
        assert updated.position_x == 99.0

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self, db):
        update_data = schemas.TreeNodeBase(
            level_ring=1, position_x=0, position_y=0,
            name="Ghost", node_type="regular",
        )
        result = await crud.update_tree_node(db, 99999, update_data)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_tree_node(self, db):
        tree = await _create_tree(db)
        data = schemas.TreeNodeCreate(
            tree_id=tree.id, level_ring=1, position_x=0, position_y=0,
            name="ToDelete", node_type="root",
        )
        node = await crud.create_tree_node(db, data)
        success = await crud.delete_tree_node(db, node.id)
        assert success is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, db):
        success = await crud.delete_tree_node(db, 99999)
        assert success is False

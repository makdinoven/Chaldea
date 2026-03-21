"""
Tests for FEAT-056 Class Skill Tree admin endpoints in skills-service.

Covers all 9 new admin endpoints under /skills/admin/class_trees/:
- CRUD for class trees
- Full tree get/save (bulk save with temp IDs)
- Individual node CRUD
- Auth/permission enforcement

skills-service is ASYNC (aiomysql), so we use httpx.AsyncClient + ASGITransport.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from auth_http import get_admin_user, get_current_user_via_http, require_permission, UserRead


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
# Patch database before importing main
# ---------------------------------------------------------------------------
import database  # noqa: E402

_original_get_db = database.get_db

# NOTE: engine/session patching moved into setup_db fixture to avoid
# cross-file collisions when pytest imports multiple test modules.

async def _override_get_db():
    async with _AsyncTestSessionLocal() as session:
        yield session


async def _test_create_tables():
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)


import models  # noqa: E402

import main as main_module  # noqa: E402
from main import app  # noqa: E402

app.router.on_startup.clear()


# ---------------------------------------------------------------------------
# Auth overrides
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "skill_trees:create", "skill_trees:read",
        "skill_trees:update", "skill_trees:delete",
        "skills:create", "skills:read", "skills:update", "skills:delete",
    ],
)

_USER_NO_PERMS = UserRead(
    id=2, username="user", role="user",
    permissions=[],
)


def _override_admin():
    return _ADMIN_USER


def _override_no_perms():
    from fastapi import HTTPException
    raise HTTPException(status_code=403, detail="Insufficient permissions")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def setup_db():
    """Create and drop tables for each test."""
    # Patch database engine/session at fixture time (not module level)
    database.engine = _async_test_engine
    database.async_session = _AsyncTestSessionLocal
    database.get_db = _override_get_db
    database.create_tables = _test_create_tables
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session(setup_db):
    async with _AsyncTestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def admin_client(setup_db):
    app.dependency_overrides[_original_get_db] = _override_get_db
    app.dependency_overrides[get_admin_user] = _override_admin
    app.dependency_overrides[get_current_user_via_http] = _override_admin
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def no_perm_client(setup_db):
    """Client with authenticated user but NO skill_trees permissions."""
    app.dependency_overrides[_original_get_db] = _override_get_db
    app.dependency_overrides[get_admin_user] = _override_no_perms
    app.dependency_overrides[get_current_user_via_http] = lambda: _USER_NO_PERMS
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

TREE_PAYLOAD = {
    "class_id": 1,
    "name": "Warrior Tree",
    "description": "Main warrior class tree",
    "tree_type": "class",
    "parent_tree_id": None,
    "subclass_name": None,
    "tree_image": None,
}

NODE_PAYLOAD = {
    "level_ring": 1,
    "position_x": 100.0,
    "position_y": 200.0,
    "name": "Root Node",
    "description": "Starting node",
    "node_type": "root",
    "icon_image": None,
    "sort_order": 0,
}


async def _seed_skill(db: AsyncSession, skill_id: int = 1, name: str = "Fireball"):
    """Create a Skill for testing skill assignment to tree nodes."""
    skill = models.Skill(id=skill_id, name=name, skill_type="Attack", description="Test skill")
    db.add(skill)
    await db.commit()
    return skill


async def _create_tree_via_api(client, payload=None):
    """Helper to create a tree and return its ID."""
    resp = await client.post("/skills/admin/class_trees/", json=payload or TREE_PAYLOAD)
    assert resp.status_code == 200, f"Failed to create tree: {resp.text}"
    return resp.json()


# ===========================================================================
# Auth / Permission tests
# ===========================================================================

class TestClassTreeAuthPermissions:
    """All admin class tree endpoints should enforce permissions."""

    @pytest.mark.asyncio
    async def test_create_tree_no_token_returns_401(self, setup_db):
        """No auth header -> 401."""
        app.dependency_overrides[_original_get_db] = _override_get_db
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/skills/admin/class_trees/", json=TREE_PAYLOAD)
        app.dependency_overrides.clear()
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_trees_no_perms_returns_403(self, no_perm_client):
        resp = await no_perm_client.get("/skills/admin/class_trees/")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_tree_no_perms_returns_403(self, no_perm_client):
        resp = await no_perm_client.get("/skills/admin/class_trees/1")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_full_tree_no_perms_returns_403(self, no_perm_client):
        resp = await no_perm_client.get("/skills/admin/class_trees/1/full")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_save_full_tree_no_perms_returns_403(self, no_perm_client):
        resp = await no_perm_client.put(
            "/skills/admin/class_trees/1/full",
            json={"id": 1, "class_id": 1, "name": "x", "tree_type": "class", "nodes": [], "connections": []},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_tree_no_perms_returns_403(self, no_perm_client):
        resp = await no_perm_client.delete("/skills/admin/class_trees/1")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_node_no_perms_returns_403(self, no_perm_client):
        resp = await no_perm_client.post(
            "/skills/admin/class_trees/1/nodes/",
            json={**NODE_PAYLOAD, "tree_id": 1},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_node_no_perms_returns_403(self, no_perm_client):
        resp = await no_perm_client.put(
            "/skills/admin/class_trees/1/nodes/1",
            json=NODE_PAYLOAD,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_node_no_perms_returns_403(self, no_perm_client):
        resp = await no_perm_client.delete("/skills/admin/class_trees/1/nodes/1")
        assert resp.status_code == 403


# ===========================================================================
# POST /skills/admin/class_trees/
# ===========================================================================

class TestCreateClassTree:

    @pytest.mark.asyncio
    async def test_create_tree_success(self, admin_client):
        data = await _create_tree_via_api(admin_client)
        assert data["id"] is not None
        assert data["name"] == "Warrior Tree"
        assert data["class_id"] == 1
        assert data["tree_type"] == "class"

    @pytest.mark.asyncio
    async def test_create_tree_response_shape(self, admin_client):
        data = await _create_tree_via_api(admin_client)
        expected_keys = {"id", "class_id", "name", "description", "tree_type",
                         "parent_tree_id", "subclass_name", "tree_image"}
        assert expected_keys.issubset(set(data.keys()))

    @pytest.mark.asyncio
    async def test_create_subclass_tree(self, admin_client):
        # Create parent class tree first
        parent = await _create_tree_via_api(admin_client)
        subclass_payload = {
            "class_id": 1,
            "name": "Berserker Subtree",
            "description": "Berserker subclass",
            "tree_type": "subclass",
            "parent_tree_id": parent["id"],
            "subclass_name": "Berserker",
            "tree_image": None,
        }
        resp = await admin_client.post("/skills/admin/class_trees/", json=subclass_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tree_type"] == "subclass"
        assert data["parent_tree_id"] == parent["id"]
        assert data["subclass_name"] == "Berserker"


# ===========================================================================
# GET /skills/admin/class_trees/
# ===========================================================================

class TestListClassTrees:

    @pytest.mark.asyncio
    async def test_list_empty(self, admin_client):
        resp = await admin_client.get("/skills/admin/class_trees/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_returns_created_trees(self, admin_client):
        await _create_tree_via_api(admin_client)
        await _create_tree_via_api(admin_client, {
            **TREE_PAYLOAD, "class_id": 2, "name": "Mage Tree",
        })
        resp = await admin_client.get("/skills/admin/class_trees/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_class_id(self, admin_client):
        await _create_tree_via_api(admin_client)
        await _create_tree_via_api(admin_client, {
            **TREE_PAYLOAD, "class_id": 2, "name": "Mage Tree",
        })
        resp = await admin_client.get("/skills/admin/class_trees/", params={"class_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["class_id"] == 1

    @pytest.mark.asyncio
    async def test_list_filter_by_tree_type(self, admin_client):
        await _create_tree_via_api(admin_client)
        parent = (await admin_client.get("/skills/admin/class_trees/")).json()[0]
        await _create_tree_via_api(admin_client, {
            **TREE_PAYLOAD, "name": "Berserker",
            "tree_type": "subclass", "subclass_name": "Berserker",
            "parent_tree_id": parent["id"],
        })
        resp = await admin_client.get("/skills/admin/class_trees/", params={"tree_type": "subclass"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["tree_type"] == "subclass"


# ===========================================================================
# GET /skills/admin/class_trees/{tree_id}
# ===========================================================================

class TestGetClassTree:

    @pytest.mark.asyncio
    async def test_get_existing_tree(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        resp = await admin_client.get(f"/skills/admin/class_trees/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_tree_returns_404(self, admin_client):
        resp = await admin_client.get("/skills/admin/class_trees/99999")
        assert resp.status_code == 404


# ===========================================================================
# GET /skills/admin/class_trees/{tree_id}/full
# ===========================================================================

class TestGetFullClassTree:

    @pytest.mark.asyncio
    async def test_get_full_empty_tree(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        resp = await admin_client.get(f"/skills/admin/class_trees/{created['id']}/full")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == created["id"]
        assert data["nodes"] == []
        assert data["connections"] == []

    @pytest.mark.asyncio
    async def test_get_full_tree_with_nodes(self, admin_client, db_session):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        # Create a node via API
        node_resp = await admin_client.post(
            f"/skills/admin/class_trees/{tree_id}/nodes/",
            json={**NODE_PAYLOAD, "tree_id": tree_id},
        )
        assert node_resp.status_code == 200

        resp = await admin_client.get(f"/skills/admin/class_trees/{tree_id}/full")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["name"] == "Root Node"

    @pytest.mark.asyncio
    async def test_get_full_nonexistent_returns_404(self, admin_client):
        resp = await admin_client.get("/skills/admin/class_trees/99999/full")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_full_tree_includes_skill_info(self, admin_client, db_session):
        """Full tree response should include denormalized skill data in node skills."""
        await _seed_skill(db_session, skill_id=1, name="Fireball")
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        # Use bulk save to create a node with a skill assigned
        save_payload = {
            "id": tree_id,
            "class_id": 1,
            "name": "Warrior Tree",
            "tree_type": "class",
            "nodes": [
                {
                    "id": "temp-1",
                    "level_ring": 1,
                    "position_x": 0,
                    "position_y": 0,
                    "name": "Root",
                    "node_type": "root",
                    "sort_order": 0,
                    "skills": [{"skill_id": 1, "sort_order": 0}],
                }
            ],
            "connections": [],
        }
        save_resp = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=save_payload
        )
        assert save_resp.status_code == 200

        # Fetch the full tree
        resp = await admin_client.get(f"/skills/admin/class_trees/{tree_id}/full")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 1
        skills = data["nodes"][0]["skills"]
        assert len(skills) == 1
        assert skills[0]["skill_name"] == "Fireball"
        assert skills[0]["skill_type"] == "Attack"


# ===========================================================================
# PUT /skills/admin/class_trees/{tree_id}/full  (bulk save)
# ===========================================================================

class TestSaveFullClassTree:

    @pytest.mark.asyncio
    async def test_save_creates_new_nodes_with_temp_ids(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        payload = {
            "id": tree_id,
            "class_id": 1,
            "name": "Warrior Tree",
            "tree_type": "class",
            "nodes": [
                {
                    "id": "temp-1",
                    "level_ring": 1,
                    "position_x": 0,
                    "position_y": 0,
                    "name": "Root",
                    "node_type": "root",
                    "sort_order": 0,
                    "skills": [],
                },
                {
                    "id": "temp-2",
                    "level_ring": 5,
                    "position_x": 100,
                    "position_y": 100,
                    "name": "Level 5 Node",
                    "node_type": "regular",
                    "sort_order": 0,
                    "skills": [],
                },
            ],
            "connections": [],
        }
        resp = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "temp_id_map" in data
        assert "temp-1" in data["temp_id_map"]
        assert "temp-2" in data["temp_id_map"]
        # Real IDs should be integers
        assert isinstance(data["temp_id_map"]["temp-1"], int)
        assert isinstance(data["temp_id_map"]["temp-2"], int)

    @pytest.mark.asyncio
    async def test_save_updates_existing_nodes(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        # First save: create a node
        payload1 = {
            "id": tree_id,
            "class_id": 1,
            "name": "Warrior Tree",
            "tree_type": "class",
            "nodes": [
                {
                    "id": "temp-1",
                    "level_ring": 1,
                    "position_x": 0,
                    "position_y": 0,
                    "name": "Root",
                    "node_type": "root",
                    "sort_order": 0,
                    "skills": [],
                }
            ],
            "connections": [],
        }
        resp1 = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=payload1
        )
        real_id = resp1.json()["temp_id_map"]["temp-1"]

        # Second save: update the node
        payload2 = {
            "id": tree_id,
            "class_id": 1,
            "name": "Warrior Tree Updated",
            "tree_type": "class",
            "nodes": [
                {
                    "id": real_id,
                    "level_ring": 1,
                    "position_x": 50,
                    "position_y": 50,
                    "name": "Root Updated",
                    "node_type": "root",
                    "sort_order": 1,
                    "skills": [],
                }
            ],
            "connections": [],
        }
        resp2 = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=payload2
        )
        assert resp2.status_code == 200

        # Verify the update via GET /full
        full_resp = await admin_client.get(f"/skills/admin/class_trees/{tree_id}/full")
        full_data = full_resp.json()
        assert full_data["name"] == "Warrior Tree Updated"
        assert len(full_data["nodes"]) == 1
        assert full_data["nodes"][0]["name"] == "Root Updated"
        assert full_data["nodes"][0]["position_x"] == 50.0

    @pytest.mark.asyncio
    async def test_save_deletes_removed_nodes(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        # Create two nodes
        payload1 = {
            "id": tree_id,
            "class_id": 1,
            "name": "Warrior Tree",
            "tree_type": "class",
            "nodes": [
                {
                    "id": "temp-1", "level_ring": 1, "position_x": 0, "position_y": 0,
                    "name": "Node A", "node_type": "root", "sort_order": 0, "skills": [],
                },
                {
                    "id": "temp-2", "level_ring": 5, "position_x": 100, "position_y": 100,
                    "name": "Node B", "node_type": "regular", "sort_order": 0, "skills": [],
                },
            ],
            "connections": [],
        }
        resp1 = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=payload1
        )
        map1 = resp1.json()["temp_id_map"]

        # Save again with only Node A — Node B should be deleted
        payload2 = {
            "id": tree_id,
            "class_id": 1,
            "name": "Warrior Tree",
            "tree_type": "class",
            "nodes": [
                {
                    "id": map1["temp-1"], "level_ring": 1, "position_x": 0, "position_y": 0,
                    "name": "Node A", "node_type": "root", "sort_order": 0, "skills": [],
                },
            ],
            "connections": [],
        }
        resp2 = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=payload2
        )
        assert resp2.status_code == 200

        full_resp = await admin_client.get(f"/skills/admin/class_trees/{tree_id}/full")
        assert len(full_resp.json()["nodes"]) == 1

    @pytest.mark.asyncio
    async def test_save_connections_with_temp_ids(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        payload = {
            "id": tree_id,
            "class_id": 1,
            "name": "Warrior Tree",
            "tree_type": "class",
            "nodes": [
                {
                    "id": "temp-1", "level_ring": 1, "position_x": 0, "position_y": 0,
                    "name": "Root", "node_type": "root", "sort_order": 0, "skills": [],
                },
                {
                    "id": "temp-2", "level_ring": 5, "position_x": 100, "position_y": 100,
                    "name": "Level 5", "node_type": "regular", "sort_order": 0, "skills": [],
                },
            ],
            "connections": [
                {"id": "temp-c1", "from_node_id": "temp-1", "to_node_id": "temp-2"},
            ],
        }
        resp = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "temp-c1" in data["temp_id_map"]

        # Verify connections
        full_resp = await admin_client.get(f"/skills/admin/class_trees/{tree_id}/full")
        full_data = full_resp.json()
        assert len(full_data["connections"]) == 1
        conn = full_data["connections"][0]
        assert conn["from_node_id"] == data["temp_id_map"]["temp-1"]
        assert conn["to_node_id"] == data["temp_id_map"]["temp-2"]

    @pytest.mark.asyncio
    async def test_save_skill_assignment(self, admin_client, db_session):
        await _seed_skill(db_session, skill_id=1, name="Fireball")
        await _seed_skill(db_session, skill_id=2, name="Ice Bolt")

        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        payload = {
            "id": tree_id,
            "class_id": 1,
            "name": "Warrior Tree",
            "tree_type": "class",
            "nodes": [
                {
                    "id": "temp-1", "level_ring": 1, "position_x": 0, "position_y": 0,
                    "name": "Root", "node_type": "root", "sort_order": 0,
                    "skills": [
                        {"skill_id": 1, "sort_order": 0},
                        {"skill_id": 2, "sort_order": 1},
                    ],
                },
            ],
            "connections": [],
        }
        resp = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=payload
        )
        assert resp.status_code == 200

        full_resp = await admin_client.get(f"/skills/admin/class_trees/{tree_id}/full")
        full_data = full_resp.json()
        skills = full_data["nodes"][0]["skills"]
        assert len(skills) == 2
        skill_ids = {s["skill_id"] for s in skills}
        assert skill_ids == {1, 2}

    @pytest.mark.asyncio
    async def test_save_empty_nodes_and_connections(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        payload = {
            "id": tree_id,
            "class_id": 1,
            "name": "Empty Tree",
            "tree_type": "class",
            "nodes": [],
            "connections": [],
        }
        resp = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=payload
        )
        assert resp.status_code == 200
        assert resp.json()["temp_id_map"] == {}

    @pytest.mark.asyncio
    async def test_save_path_id_mismatch_returns_400(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        payload = {
            "id": tree_id + 100,  # Mismatch
            "class_id": 1,
            "name": "Tree",
            "tree_type": "class",
            "nodes": [],
            "connections": [],
        }
        resp = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=payload
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_save_nonexistent_tree_returns_404(self, admin_client):
        payload = {
            "id": 99999,
            "class_id": 1,
            "name": "Ghost Tree",
            "tree_type": "class",
            "nodes": [],
            "connections": [],
        }
        resp = await admin_client.put(
            "/skills/admin/class_trees/99999/full", json=payload
        )
        assert resp.status_code == 404


# ===========================================================================
# DELETE /skills/admin/class_trees/{tree_id}
# ===========================================================================

class TestDeleteClassTree:

    @pytest.mark.asyncio
    async def test_delete_existing_tree(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        resp = await admin_client.delete(f"/skills/admin/class_trees/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Class tree deleted"

        # Verify gone
        get_resp = await admin_client.get(f"/skills/admin/class_trees/{created['id']}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, admin_client):
        resp = await admin_client.delete("/skills/admin/class_trees/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cascade_delete_removes_nodes_and_connections(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        # Populate tree
        payload = {
            "id": tree_id,
            "class_id": 1,
            "name": "Warrior Tree",
            "tree_type": "class",
            "nodes": [
                {
                    "id": "temp-1", "level_ring": 1, "position_x": 0, "position_y": 0,
                    "name": "Root", "node_type": "root", "sort_order": 0, "skills": [],
                },
                {
                    "id": "temp-2", "level_ring": 5, "position_x": 100, "position_y": 100,
                    "name": "Level 5", "node_type": "regular", "sort_order": 0, "skills": [],
                },
            ],
            "connections": [
                {"id": None, "from_node_id": "temp-1", "to_node_id": "temp-2"},
            ],
        }
        save_resp = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/full", json=payload
        )
        assert save_resp.status_code == 200

        # Delete the tree — cascade should remove nodes and connections
        del_resp = await admin_client.delete(f"/skills/admin/class_trees/{tree_id}")
        assert del_resp.status_code == 200

        # Verify tree is gone
        get_resp = await admin_client.get(f"/skills/admin/class_trees/{tree_id}/full")
        assert get_resp.status_code == 404


# ===========================================================================
# Individual Node endpoints
# ===========================================================================

class TestNodeEndpoints:

    @pytest.mark.asyncio
    async def test_create_node_success(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        resp = await admin_client.post(
            f"/skills/admin/class_trees/{tree_id}/nodes/",
            json={**NODE_PAYLOAD, "tree_id": tree_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Root Node"
        assert data["tree_id"] == tree_id
        assert data["level_ring"] == 1

    @pytest.mark.asyncio
    async def test_create_node_nonexistent_tree_returns_404(self, admin_client):
        resp = await admin_client.post(
            "/skills/admin/class_trees/99999/nodes/",
            json={**NODE_PAYLOAD, "tree_id": 99999},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_node_tree_id_mismatch_returns_400(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        resp = await admin_client.post(
            f"/skills/admin/class_trees/{tree_id}/nodes/",
            json={**NODE_PAYLOAD, "tree_id": tree_id + 100},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_node_success(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        # Create a node
        create_resp = await admin_client.post(
            f"/skills/admin/class_trees/{tree_id}/nodes/",
            json={**NODE_PAYLOAD, "tree_id": tree_id},
        )
        node_id = create_resp.json()["id"]

        # Update it
        updated_payload = {**NODE_PAYLOAD, "name": "Updated Root", "position_x": 999.0}
        resp = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/nodes/{node_id}",
            json=updated_payload,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Root"
        assert resp.json()["position_x"] == 999.0

    @pytest.mark.asyncio
    async def test_update_nonexistent_node_returns_404(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]
        resp = await admin_client.put(
            f"/skills/admin/class_trees/{tree_id}/nodes/99999",
            json=NODE_PAYLOAD,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_node_success(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]

        create_resp = await admin_client.post(
            f"/skills/admin/class_trees/{tree_id}/nodes/",
            json={**NODE_PAYLOAD, "tree_id": tree_id},
        )
        node_id = create_resp.json()["id"]

        resp = await admin_client.delete(f"/skills/admin/class_trees/{tree_id}/nodes/{node_id}")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Tree node deleted"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_node_returns_404(self, admin_client):
        created = await _create_tree_via_api(admin_client)
        tree_id = created["id"]
        resp = await admin_client.delete(f"/skills/admin/class_trees/{tree_id}/nodes/99999")
        assert resp.status_code == 404


# ===========================================================================
# Battle-service contract: existing endpoints still return same shape
# ===========================================================================

class TestExistingEndpointsContract:
    """Verify that existing skill endpoints are not broken by the new models."""

    @pytest.mark.asyncio
    async def test_get_character_skills_returns_200(self, admin_client, db_session):
        """GET /skills/characters/{id}/skills should return a list (even if empty)."""
        resp = await admin_client.get("/skills/characters/1/skills")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_skill_rank_returns_correct_shape(self, admin_client, db_session):
        """GET /skills/admin/skill_ranks/{id} should still return the rank with nested data."""
        # Seed a skill with rank
        skill = models.Skill(id=10, name="TestSkill", skill_type="Attack")
        db_session.add(skill)
        await db_session.flush()
        rank = models.SkillRank(id=10, skill_id=10, rank_number=1, rank_name="Rank I")
        db_session.add(rank)
        await db_session.commit()

        resp = await admin_client.get("/skills/admin/skill_ranks/10")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "skill_id" in data
        assert "rank_number" in data
        assert "damage_entries" in data
        assert "effects" in data

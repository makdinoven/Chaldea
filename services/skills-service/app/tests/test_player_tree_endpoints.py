"""
Tests for FEAT-057 Player Skill Tree endpoints in skills-service.

Covers all 7 new player endpoints:
- GET /skills/class_trees/by_class/{class_id}
- GET /skills/class_trees/{tree_id}/progress/{character_id}
- POST /skills/class_trees/{tree_id}/choose_node
- POST /skills/class_trees/purchase_skill
- POST /skills/class_trees/{tree_id}/reset
- GET /skills/class_trees/subclass_trees/{class_tree_id}

skills-service is ASYNC (aiomysql), so we use httpx.AsyncClient + ASGITransport.
HTTP calls to character-service and character-attributes-service are mocked.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import httpx
from httpx import ASGITransport
from sqlalchemy import text
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

_PLAYER_USER = UserRead(
    id=1, username="player", role="user",
    permissions=[],
)

_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "skill_trees:create", "skill_trees:read",
        "skill_trees:update", "skill_trees:delete",
        "skills:create", "skills:read", "skills:update", "skills:delete",
    ],
)


def _override_player():
    return _PLAYER_USER


def _override_admin():
    return _ADMIN_USER


# ---------------------------------------------------------------------------
# Mock helpers for cross-service HTTP calls
# ---------------------------------------------------------------------------

def _mock_character_info(class_id=1, level=10):
    """Build a mock response for get_character_info."""
    return {"id": 100, "id_class": class_id, "id_race": 1, "id_subrace": None, "level": level}


def _mock_httpx_response(status_code=200, json_data=None):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


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
async def player_client(setup_db):
    """Client with authenticated player (regular user)."""
    app.dependency_overrides[_original_get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = _override_player
    app.dependency_overrides[get_admin_user] = _override_admin
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def admin_client(setup_db):
    """Client with admin permissions (for seeding data via admin endpoints)."""
    app.dependency_overrides[_original_get_db] = _override_get_db
    app.dependency_overrides[get_admin_user] = _override_admin
    app.dependency_overrides[get_current_user_via_http] = _override_admin
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def _reject_auth():
    """Simulate missing auth by raising 401."""
    from fastapi import HTTPException
    raise HTTPException(status_code=401, detail="Not authenticated")


@pytest_asyncio.fixture()
async def no_auth_client(setup_db):
    """Client without any auth — override get_current_user_via_http to always raise 401."""
    app.dependency_overrides[_original_get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = _reject_auth
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


async def _seed_tree_with_nodes(admin_client, db_session):
    """
    Seed a complete tree structure:
    - 1 class tree (class_id=1)
    - root_node (level_ring=1, node_type='root')
    - child_node_a (level_ring=5, node_type='regular') - connected from root
    - child_node_b (level_ring=5, node_type='regular') - connected from root (sibling of a)
    - grandchild_node (level_ring=10, node_type='regular') - connected from child_node_a
    - subclass_node (level_ring=30, node_type='subclass_choice') - connected from grandchild
    - 2 skills with rank 1 each, assigned to root_node and child_node_a
    - A character row (id=100, user_id=1) in the characters table

    Returns dict with all IDs.
    """
    # Create skills first
    skill1 = models.Skill(id=1, name="Fireball", skill_type="Attack", description="Fire", purchase_cost=50)
    skill2 = models.Skill(id=2, name="Shield Bash", skill_type="Defense", description="Bash", purchase_cost=30)
    db_session.add_all([skill1, skill2])
    await db_session.commit()

    # Create rank 1 for each skill
    rank1_s1 = models.SkillRank(id=1, skill_id=1, rank_number=1, rank_name="Fireball I")
    rank1_s2 = models.SkillRank(id=2, skill_id=2, rank_number=1, rank_name="Shield Bash I")
    db_session.add_all([rank1_s1, rank1_s2])
    await db_session.commit()

    # Create tree via admin API
    resp = await admin_client.post("/skills/admin/class_trees/", json=TREE_PAYLOAD)
    assert resp.status_code == 200
    tree_id = resp.json()["id"]

    # Build full tree with nodes, connections, and skills via bulk save
    save_payload = {
        "id": tree_id,
        "class_id": 1,
        "name": "Warrior Tree",
        "tree_type": "class",
        "nodes": [
            {
                "id": "temp-root",
                "level_ring": 1,
                "position_x": 0, "position_y": 0,
                "name": "Root Node",
                "node_type": "root",
                "sort_order": 0,
                "skills": [{"skill_id": 1, "sort_order": 0}],
            },
            {
                "id": "temp-child-a",
                "level_ring": 5,
                "position_x": -100, "position_y": 100,
                "name": "Child A",
                "node_type": "regular",
                "sort_order": 0,
                "skills": [{"skill_id": 2, "sort_order": 0}],
            },
            {
                "id": "temp-child-b",
                "level_ring": 5,
                "position_x": 100, "position_y": 100,
                "name": "Child B",
                "node_type": "regular",
                "sort_order": 1,
                "skills": [],
            },
            {
                "id": "temp-grandchild",
                "level_ring": 10,
                "position_x": -100, "position_y": 200,
                "name": "Grandchild",
                "node_type": "regular",
                "sort_order": 0,
                "skills": [],
            },
            {
                "id": "temp-subclass",
                "level_ring": 30,
                "position_x": 0, "position_y": 300,
                "name": "Subclass Choice",
                "node_type": "subclass_choice",
                "sort_order": 0,
                "skills": [],
            },
        ],
        "connections": [
            {"id": "temp-c1", "from_node_id": "temp-root", "to_node_id": "temp-child-a"},
            {"id": "temp-c2", "from_node_id": "temp-root", "to_node_id": "temp-child-b"},
            {"id": "temp-c3", "from_node_id": "temp-child-a", "to_node_id": "temp-grandchild"},
            {"id": "temp-c4", "from_node_id": "temp-grandchild", "to_node_id": "temp-subclass"},
        ],
    }
    save_resp = await admin_client.put(
        f"/skills/admin/class_trees/{tree_id}/full", json=save_payload
    )
    assert save_resp.status_code == 200
    temp_id_map = save_resp.json()["temp_id_map"]

    root_id = temp_id_map["temp-root"]
    child_a_id = temp_id_map["temp-child-a"]
    child_b_id = temp_id_map["temp-child-b"]
    grandchild_id = temp_id_map["temp-grandchild"]
    subclass_id = temp_id_map["temp-subclass"]

    # Create a character row that belongs to user_id=1 (our test user)
    await db_session.execute(
        text(
            "INSERT OR IGNORE INTO characters (id, user_id) VALUES (:id, :uid)"
        ).bindparams(id=100, uid=_PLAYER_USER.id),
    )
    await db_session.commit()

    return {
        "tree_id": tree_id,
        "root_id": root_id,
        "child_a_id": child_a_id,
        "child_b_id": child_b_id,
        "grandchild_id": grandchild_id,
        "subclass_id": subclass_id,
        "skill1_id": 1,
        "skill2_id": 2,
        "rank1_s1_id": 1,
        "rank1_s2_id": 2,
        "character_id": 100,
    }


async def _create_characters_table(db_session):
    """Create a minimal characters table for verify_character_ownership."""
    await db_session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS characters ("
            "id INTEGER PRIMARY KEY, "
            "user_id INTEGER NOT NULL"
            ")"
        )
    )
    await db_session.commit()


@pytest_asyncio.fixture()
async def seeded_tree(admin_client, db_session):
    """Full tree fixture with all entities seeded. Returns IDs dict."""
    await _create_characters_table(db_session)
    return await _seed_tree_with_nodes(admin_client, db_session)


# ===========================================================================
# GET /skills/class_trees/by_class/{class_id}
# ===========================================================================

class TestGetClassTreeByClass:

    @pytest.mark.asyncio
    async def test_returns_tree_for_valid_class(self, player_client, seeded_tree):
        resp = await player_client.get("/skills/class_trees/by_class/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["class_id"] == 1
        assert data["tree_type"] == "class"
        assert len(data["nodes"]) == 5
        assert len(data["connections"]) == 4

    @pytest.mark.asyncio
    async def test_returns_404_for_class_with_no_tree(self, player_client, setup_db):
        resp = await player_client.get("/skills/class_trees/by_class/999")
        assert resp.status_code == 404


# ===========================================================================
# GET /skills/class_trees/{tree_id}/progress/{character_id}
# ===========================================================================

class TestGetTreeProgress:

    @pytest.mark.asyncio
    @patch.object(main_module, "get_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_empty_progress_for_new_character(
        self, mock_char_info, mock_exp, player_client, seeded_tree
    ):
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)
        mock_exp.return_value = 500

        ids = seeded_tree
        resp = await player_client.get(
            f"/skills/class_trees/{ids['tree_id']}/progress/{ids['character_id']}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_id"] == ids["character_id"]
        assert data["tree_id"] == ids["tree_id"]
        assert data["chosen_nodes"] == []
        assert data["purchased_skills"] == []
        assert data["active_experience"] == 500
        assert data["character_level"] == 10

    @pytest.mark.asyncio
    @patch.object(main_module, "get_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_progress_after_actions(
        self, mock_char_info, mock_exp, player_client, seeded_tree
    ):
        """After choosing root node and purchasing a skill, progress reflects both."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)
        mock_exp.return_value = 1000

        ids = seeded_tree

        # Choose root node
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 200

        # Purchase skill from root node (mock experience deduction)
        with patch.object(main_module, "deduct_active_experience", new_callable=AsyncMock) as mock_deduct:
            mock_deduct.return_value = 950
            resp = await player_client.post(
                "/skills/class_trees/purchase_skill",
                json={
                    "character_id": ids["character_id"],
                    "node_id": ids["root_id"],
                    "skill_id": ids["skill1_id"],
                },
            )
            assert resp.status_code == 200

        # Now check progress
        resp = await player_client.get(
            f"/skills/class_trees/{ids['tree_id']}/progress/{ids['character_id']}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["chosen_nodes"]) == 1
        assert data["chosen_nodes"][0]["node_id"] == ids["root_id"]
        assert len(data["purchased_skills"]) == 1
        assert data["purchased_skills"][0]["skill_id"] == ids["skill1_id"]

    @pytest.mark.asyncio
    async def test_requires_auth(self, no_auth_client):
        resp = await no_auth_client.get(
            "/skills/class_trees/1/progress/100"
        )
        assert resp.status_code == 401


# ===========================================================================
# POST /skills/class_trees/{tree_id}/choose_node
# ===========================================================================

class TestChooseNode:

    @pytest.mark.asyncio
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_choose_root_node_success(self, mock_char_info, player_client, seeded_tree):
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)

        ids = seeded_tree
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "Узел выбран"
        assert data["node_id"] == ids["root_id"]

    @pytest.mark.asyncio
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reject_node_not_in_tree(self, mock_char_info, player_client, seeded_tree):
        """Node with non-existent ID returns 404."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)

        ids = seeded_tree
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": 99999},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reject_level_too_low(self, mock_char_info, player_client, seeded_tree):
        """Character level < node.level_ring should be rejected."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=3)

        ids = seeded_tree
        # child_a has level_ring=5, character level=3
        # But first we need root to be chosen; root has level_ring=1 so let's try child_a directly
        # Actually, the level check happens before prerequisite check in the endpoint
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["child_a_id"]},
        )
        assert resp.status_code == 400
        assert "уровень" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reject_prerequisite_not_met(self, mock_char_info, player_client, seeded_tree):
        """Trying to choose child_a without choosing root first should fail."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)

        ids = seeded_tree
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["child_a_id"]},
        )
        assert resp.status_code == 400
        assert "предыдущий" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reject_branch_conflict(self, mock_char_info, player_client, seeded_tree):
        """After choosing child_a, trying to choose child_b (sibling) should fail."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)

        ids = seeded_tree
        # Choose root first
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 200

        # Choose child_a
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["child_a_id"]},
        )
        assert resp.status_code == 200

        # Now try child_b — sibling at same level_ring from same parent
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["child_b_id"]},
        )
        assert resp.status_code == 400
        assert "альтернативная" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reject_node_already_chosen(self, mock_char_info, player_client, seeded_tree):
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)

        ids = seeded_tree
        # Choose root
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 200

        # Try choosing root again
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 400
        assert "уже выбран" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reject_class_mismatch(self, mock_char_info, player_client, seeded_tree):
        """Tree is for class_id=1 but character has class_id=2."""
        mock_char_info.return_value = _mock_character_info(class_id=2, level=10)

        ids = seeded_tree
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 400
        assert "класс" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_requires_auth(self, no_auth_client):
        resp = await no_auth_client.post(
            "/skills/class_trees/1/choose_node",
            json={"character_id": 100, "node_id": 1},
        )
        assert resp.status_code == 401


# ===========================================================================
# POST /skills/class_trees/purchase_skill
# ===========================================================================

class TestPurchaseSkill:

    @pytest.mark.asyncio
    @patch.object(main_module, "deduct_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_purchase_skill_success(
        self, mock_char_info, mock_exp, mock_deduct, player_client, seeded_tree
    ):
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)
        mock_exp.return_value = 1000
        mock_deduct.return_value = 950

        ids = seeded_tree
        # Choose root node first
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 200

        # Purchase skill from root node
        resp = await player_client.post(
            "/skills/class_trees/purchase_skill",
            json={
                "character_id": ids["character_id"],
                "node_id": ids["root_id"],
                "skill_id": ids["skill1_id"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "Навык изучен"
        assert "character_skill_id" in data

    @pytest.mark.asyncio
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reject_node_not_chosen(self, mock_char_info, player_client, seeded_tree):
        """Cannot purchase skill from a node that hasn't been chosen."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)

        ids = seeded_tree
        resp = await player_client.post(
            "/skills/class_trees/purchase_skill",
            json={
                "character_id": ids["character_id"],
                "node_id": ids["root_id"],
                "skill_id": ids["skill1_id"],
            },
        )
        assert resp.status_code == 400
        assert "выбрать" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reject_skill_not_in_node(self, mock_char_info, player_client, seeded_tree):
        """Cannot purchase a skill that isn't assigned to the given node."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)

        ids = seeded_tree
        # Choose root node
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 200

        # Try to purchase skill2 from root (skill2 is assigned to child_a, not root)
        resp = await player_client.post(
            "/skills/class_trees/purchase_skill",
            json={
                "character_id": ids["character_id"],
                "node_id": ids["root_id"],
                "skill_id": ids["skill2_id"],
            },
        )
        assert resp.status_code == 400
        assert "не привязан" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch.object(main_module, "deduct_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reject_skill_already_purchased(
        self, mock_char_info, mock_exp, mock_deduct, player_client, seeded_tree
    ):
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)
        mock_exp.return_value = 1000
        mock_deduct.return_value = 950

        ids = seeded_tree
        # Choose root
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 200

        # Purchase skill once
        resp = await player_client.post(
            "/skills/class_trees/purchase_skill",
            json={
                "character_id": ids["character_id"],
                "node_id": ids["root_id"],
                "skill_id": ids["skill1_id"],
            },
        )
        assert resp.status_code == 200

        # Try again — should fail
        resp = await player_client.post(
            "/skills/class_trees/purchase_skill",
            json={
                "character_id": ids["character_id"],
                "node_id": ids["root_id"],
                "skill_id": ids["skill1_id"],
            },
        )
        assert resp.status_code == 400
        assert "уже изучен" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch.object(main_module, "get_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reject_insufficient_experience(
        self, mock_char_info, mock_exp, player_client, seeded_tree
    ):
        """Mock experience check to show insufficient funds."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)
        mock_exp.return_value = 10  # Less than purchase_cost=50

        ids = seeded_tree
        # Choose root
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 200

        # Try to purchase — should fail due to insufficient experience
        resp = await player_client.post(
            "/skills/class_trees/purchase_skill",
            json={
                "character_id": ids["character_id"],
                "node_id": ids["root_id"],
                "skill_id": ids["skill1_id"],
            },
        )
        assert resp.status_code == 400
        assert "опыт" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_requires_auth(self, no_auth_client):
        resp = await no_auth_client.post(
            "/skills/class_trees/purchase_skill",
            json={
                "character_id": 100,
                "node_id": 1,
                "skill_id": 1,
            },
        )
        assert resp.status_code == 401


# ===========================================================================
# POST /skills/class_trees/{tree_id}/reset
# ===========================================================================

class TestResetTree:

    @pytest.mark.asyncio
    @patch.object(main_module, "deduct_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reset_success(
        self, mock_char_info, mock_exp, mock_deduct, player_client, seeded_tree
    ):
        """Reset clears non-subclass nodes and associated skills."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)
        mock_exp.return_value = 1000
        mock_deduct.return_value = 950

        ids = seeded_tree
        # Choose root and purchase a skill
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        assert resp.status_code == 200

        resp = await player_client.post(
            "/skills/class_trees/purchase_skill",
            json={
                "character_id": ids["character_id"],
                "node_id": ids["root_id"],
                "skill_id": ids["skill1_id"],
            },
        )
        assert resp.status_code == 200

        # Reset
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/reset",
            json={"character_id": ids["character_id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "Прогресс сброшен"
        assert data["nodes_reset"] >= 1
        assert data["skills_removed"] >= 1

    @pytest.mark.asyncio
    @patch.object(main_module, "deduct_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reset_preserves_subclass_nodes(
        self, mock_char_info, mock_exp, mock_deduct, player_client, seeded_tree, db_session
    ):
        """Subclass_choice nodes should survive a reset."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=30)
        mock_exp.return_value = 5000
        mock_deduct.return_value = 4900

        ids = seeded_tree

        # Choose the full path: root -> child_a -> grandchild -> subclass
        for node_id in [ids["root_id"], ids["child_a_id"], ids["grandchild_id"], ids["subclass_id"]]:
            resp = await player_client.post(
                f"/skills/class_trees/{ids['tree_id']}/choose_node",
                json={"character_id": ids["character_id"], "node_id": node_id},
            )
            assert resp.status_code == 200, f"Failed to choose node {node_id}: {resp.text}"

        # Reset
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/reset",
            json={"character_id": ids["character_id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        # 4 nodes chosen, but subclass_choice should be preserved -> 3 reset
        assert data["nodes_reset"] == 3

        # Verify subclass node is still in progress
        mock_exp.return_value = 5000
        mock_char_info.return_value = _mock_character_info(class_id=1, level=30)
        progress_resp = await player_client.get(
            f"/skills/class_trees/{ids['tree_id']}/progress/{ids['character_id']}"
        )
        assert progress_resp.status_code == 200
        progress_data = progress_resp.json()
        chosen_node_ids = [cn["node_id"] for cn in progress_data["chosen_nodes"]]
        assert ids["subclass_id"] in chosen_node_ids
        # Non-subclass nodes should be gone
        assert ids["root_id"] not in chosen_node_ids

    @pytest.mark.asyncio
    @patch.object(main_module, "deduct_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_active_experience", new_callable=AsyncMock)
    @patch.object(main_module, "get_character_info", new_callable=AsyncMock)
    async def test_reset_cascade_deletes_character_skills(
        self, mock_char_info, mock_exp, mock_deduct, player_client, seeded_tree
    ):
        """Skills purchased from reset nodes should be deleted."""
        mock_char_info.return_value = _mock_character_info(class_id=1, level=10)
        mock_exp.return_value = 1000
        mock_deduct.return_value = 950

        ids = seeded_tree
        # Choose root and purchase skill
        await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/choose_node",
            json={"character_id": ids["character_id"], "node_id": ids["root_id"]},
        )
        await player_client.post(
            "/skills/class_trees/purchase_skill",
            json={
                "character_id": ids["character_id"],
                "node_id": ids["root_id"],
                "skill_id": ids["skill1_id"],
            },
        )

        # Verify skill exists before reset
        cs_resp = await player_client.get(f"/skills/characters/{ids['character_id']}/skills")
        assert cs_resp.status_code == 200
        assert len(cs_resp.json()) == 1

        # Reset
        resp = await player_client.post(
            f"/skills/class_trees/{ids['tree_id']}/reset",
            json={"character_id": ids["character_id"]},
        )
        assert resp.status_code == 200
        assert resp.json()["skills_removed"] == 1

        # Verify skill removed after reset
        cs_resp = await player_client.get(f"/skills/characters/{ids['character_id']}/skills")
        assert cs_resp.status_code == 200
        assert len(cs_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_requires_auth(self, no_auth_client):
        resp = await no_auth_client.post(
            "/skills/class_trees/1/reset",
            json={"character_id": 100},
        )
        assert resp.status_code == 401


# ===========================================================================
# GET /skills/class_trees/subclass_trees/{class_tree_id}
# ===========================================================================

class TestGetSubclassTrees:

    @pytest.mark.asyncio
    async def test_returns_subclass_trees(self, admin_client, seeded_tree):
        ids = seeded_tree
        # Create a subclass tree via admin API
        subclass_payload = {
            "class_id": 1,
            "name": "Berserker Subtree",
            "description": "Berserker subclass",
            "tree_type": "subclass",
            "parent_tree_id": ids["tree_id"],
            "subclass_name": "Berserker",
            "tree_image": None,
        }
        create_resp = await admin_client.post(
            "/skills/admin/class_trees/", json=subclass_payload
        )
        assert create_resp.status_code == 200

        # Fetch subclass trees (public endpoint, use admin_client which has DB override)
        resp = await admin_client.get(
            f"/skills/class_trees/subclass_trees/{ids['tree_id']}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["tree_type"] == "subclass"
        assert data[0]["parent_tree_id"] == ids["tree_id"]
        assert data[0]["subclass_name"] == "Berserker"

    @pytest.mark.asyncio
    async def test_returns_empty_list_if_none(self, admin_client, seeded_tree):
        ids = seeded_tree
        resp = await admin_client.get(
            f"/skills/class_trees/subclass_trees/{ids['tree_id']}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

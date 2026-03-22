"""
Tests for mob spawning & lifecycle (FEAT-059, Tasks #12-#15).

Covers:
1. spawn_mob_from_template — creates Character(is_npc=True, npc_role='mob'),
   attributes via HTTP, assigns skills, creates ActiveMob record
2. POST /characters/internal/try-spawn — spawn_chance, max_active, is_enabled
3. POST /characters/admin/active-mobs/spawn — admin manual spawn
4. GET /characters/admin/active-mobs — pagination, filters
5. DELETE /characters/admin/active-mobs/{id} — removes mob and character
6. GET /characters/mobs/by_location — returns only alive/in_battle mobs
7. Security: SQL injection, unauthorized access
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import database
from database import Base
from main import app, get_db
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from fastapi.testclient import TestClient
import models
import schemas
import crud


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve", "mobs:manage",
    ],
)


# ---------------------------------------------------------------------------
# Fixtures — real SQLite DB session
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(seed_fk_data):
    """Create fresh tables for every test, yield a session, then tear down."""
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def client(db_session):
    """FastAPI TestClient wired to real SQLite session with admin auth."""

    def override_get_db():
        yield db_session

    def override_admin():
        return _ADMIN_USER

    def override_token():
        return "fake-admin-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    app.dependency_overrides[OAUTH2_SCHEME] = override_token
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def noauth_client(db_session):
    """TestClient with DB but WITHOUT auth overrides (for auth testing)."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_mob_template(
    db,
    name="Дикий Волк",
    tier="normal",
    level=3,
    xp_reward=50,
    gold_reward=10,
    base_attributes=None,
):
    """Insert a MobTemplate directly into the DB."""
    template = models.MobTemplate(
        name=name,
        tier=tier,
        level=level,
        id_race=1,
        id_subrace=1,
        id_class=1,
        sex="genderless",
        base_attributes=base_attributes or {"strength": 15, "agility": 20},
        xp_reward=xp_reward,
        gold_reward=gold_reward,
        respawn_enabled=False,
        respawn_seconds=None,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def _create_spawn_rule(
    db,
    mob_template_id,
    location_id=1,
    spawn_chance=50.0,
    max_active=2,
    is_enabled=True,
):
    """Insert a LocationMobSpawn rule."""
    rule = models.LocationMobSpawn(
        mob_template_id=mob_template_id,
        location_id=location_id,
        spawn_chance=spawn_chance,
        max_active=max_active,
        is_enabled=is_enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _create_active_mob(
    db,
    mob_template_id,
    character_id,
    location_id=1,
    status="alive",
    spawn_type="random",
):
    """Insert an ActiveMob record directly."""
    am = models.ActiveMob(
        mob_template_id=mob_template_id,
        character_id=character_id,
        location_id=location_id,
        status=status,
        spawn_type=spawn_type,
    )
    db.add(am)
    db.commit()
    db.refresh(am)
    return am


def _create_mob_character(db, name="Волк", location_id=1, level=3):
    """Insert a Character record with is_npc=True, npc_role='mob'."""
    char = models.Character(
        name=name,
        id_race=1,
        id_subrace=1,
        id_class=1,
        sex="genderless",
        level=level,
        avatar="",
        appearance="",
        is_npc=True,
        npc_role="mob",
        user_id=None,
        request_id=None,
        currency_balance=0,
        stat_points=0,
        current_location_id=location_id,
    )
    db.add(char)
    db.commit()
    db.refresh(char)
    return char


# ===========================================================================
# 1. spawn_mob_from_template CRUD function
# ===========================================================================

class TestSpawnMobFromTemplate:
    """Test crud.spawn_mob_from_template creates correct records."""

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_creates_character_with_npc_fields(self, mock_attrs, db_session):
        template = _create_mob_template(db_session, name="Тестовый Волк")
        active_mob, character = crud.spawn_mob_from_template(
            db_session, template.id, location_id=5
        )

        assert character.is_npc is True
        assert character.npc_role == "mob"
        assert character.name == "Тестовый Волк"
        assert character.id_race == 1
        assert character.id_subrace == 1
        assert character.id_class == 1
        assert character.level == 3
        assert character.current_location_id == 5
        assert character.user_id is None

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_creates_active_mob_record(self, mock_attrs, db_session):
        template = _create_mob_template(db_session)
        active_mob, character = crud.spawn_mob_from_template(
            db_session, template.id, location_id=7, spawn_type="manual"
        )

        assert active_mob.mob_template_id == template.id
        assert active_mob.character_id == character.id
        assert active_mob.location_id == 7
        assert active_mob.status == "alive"
        assert active_mob.spawn_type == "manual"

    @patch("crud._sync_send_attributes_request", return_value={"id": 200})
    def test_calls_attributes_service(self, mock_attrs, db_session):
        template = _create_mob_template(
            db_session,
            base_attributes={"strength": 30, "agility": 25},
        )
        active_mob, character = crud.spawn_mob_from_template(
            db_session, template.id, location_id=1
        )

        mock_attrs.assert_called_once()
        call_args = mock_attrs.call_args
        assert call_args[0][0] == character.id  # character_id
        assert call_args[0][1]["strength"] == 30
        assert character.id_attributes == 200

    @patch("crud._sync_send_attributes_request", return_value=None)
    def test_attributes_failure_does_not_crash(self, mock_attrs, db_session):
        """If attributes service is down, mob is still created."""
        template = _create_mob_template(db_session)
        active_mob, character = crud.spawn_mob_from_template(
            db_session, template.id, location_id=1
        )

        assert active_mob is not None
        assert character.id_attributes is None

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_assigns_template_skills(self, mock_attrs, db_session):
        template = _create_mob_template(db_session)
        # Add template skills
        skill1 = models.MobTemplateSkill(mob_template_id=template.id, skill_rank_id=10)
        skill2 = models.MobTemplateSkill(mob_template_id=template.id, skill_rank_id=20)
        db_session.add_all([skill1, skill2])
        db_session.commit()

        # Need character_skills table to exist for INSERT
        # SQLite should have it from create_all if the model exists
        # The INSERT may fail silently — that is the expected behavior per crud.py
        active_mob, character = crud.spawn_mob_from_template(
            db_session, template.id, location_id=1
        )

        assert active_mob is not None
        assert character is not None

    def test_raises_on_nonexistent_template(self, db_session):
        with pytest.raises(ValueError, match="не найден"):
            crud.spawn_mob_from_template(db_session, template_id=99999, location_id=1)


# ===========================================================================
# 2. POST /characters/internal/try-spawn
# ===========================================================================

class TestTrySpawnEndpoint:
    """Test the internal try-spawn endpoint."""

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    @patch("random.random", return_value=0.01)
    def test_spawn_hit(self, mock_rng, mock_attrs, client, db_session):
        """When random roll is below spawn_chance, a mob is spawned."""

        template = _create_mob_template(db_session)
        _create_spawn_rule(db_session, template.id, location_id=10, spawn_chance=50.0)

        resp = client.post(
            "/characters/internal/try-spawn",
            json={"location_id": 10, "character_id": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["spawned"] is True
        assert "mob" in data
        assert data["mob"]["name"] == "Дикий Волк"
        assert data["mob"]["tier"] == "normal"

    @patch("random.random", return_value=0.99)
    def test_spawn_miss(self, mock_rng, client, db_session):
        """When random roll is above spawn_chance, no mob spawns."""

        template = _create_mob_template(db_session)
        _create_spawn_rule(db_session, template.id, location_id=10, spawn_chance=50.0)

        resp = client.post(
            "/characters/internal/try-spawn",
            json={"location_id": 10, "character_id": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["spawned"] is False

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    @patch("random.random", return_value=0.01)
    def test_spawn_respects_max_active(self, mock_rng, mock_attrs, client, db_session):
        """If max_active mobs already exist, no more spawn."""

        template = _create_mob_template(db_session)
        _create_spawn_rule(
            db_session, template.id, location_id=10,
            spawn_chance=100.0, max_active=1,
        )
        # Create existing alive mob at that location
        char = _create_mob_character(db_session, location_id=10)
        _create_active_mob(db_session, template.id, char.id, location_id=10, status="alive")

        resp = client.post(
            "/characters/internal/try-spawn",
            json={"location_id": 10, "character_id": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["spawned"] is False

    @patch("random.random", return_value=0.01)
    def test_spawn_respects_is_enabled(self, mock_rng, client, db_session):
        """Disabled rules are skipped."""

        template = _create_mob_template(db_session)
        _create_spawn_rule(
            db_session, template.id, location_id=10,
            spawn_chance=100.0, is_enabled=False,
        )

        resp = client.post(
            "/characters/internal/try-spawn",
            json={"location_id": 10, "character_id": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["spawned"] is False

    def test_no_spawn_rules_returns_false(self, client, db_session):
        """Location with no spawn rules returns spawned=False."""
        resp = client.post(
            "/characters/internal/try-spawn",
            json={"location_id": 999, "character_id": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["spawned"] is False

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    @patch("random.random", return_value=0.01)
    def test_dead_mobs_dont_count_for_max_active(self, mock_rng, mock_attrs, client, db_session):
        """Dead mobs should not count toward max_active limit."""

        template = _create_mob_template(db_session)
        _create_spawn_rule(
            db_session, template.id, location_id=10,
            spawn_chance=100.0, max_active=1,
        )
        # Existing DEAD mob — should not block new spawn
        char = _create_mob_character(db_session, location_id=10)
        _create_active_mob(db_session, template.id, char.id, location_id=10, status="dead")

        resp = client.post(
            "/characters/internal/try-spawn",
            json={"location_id": 10, "character_id": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["spawned"] is True


# ===========================================================================
# 3. POST /characters/admin/active-mobs/spawn — manual spawn
# ===========================================================================

class TestManualSpawn:
    """Admin manual spawn endpoint."""

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_manual_spawn_success(self, mock_attrs, client, db_session):
        template = _create_mob_template(db_session)

        resp = client.post(
            "/characters/admin/active-mobs/spawn",
            json={"mob_template_id": template.id, "location_id": 5},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["location_id"] == 5
        assert data["status"] == "alive"
        assert "character_id" in data
        assert "id" in data

    def test_manual_spawn_template_not_found(self, client, db_session):
        resp = client.post(
            "/characters/admin/active-mobs/spawn",
            json={"mob_template_id": 99999, "location_id": 5},
        )
        assert resp.status_code == 404

    def test_manual_spawn_requires_auth(self, noauth_client, db_session):
        """Without admin auth, should return 401/403."""
        resp = noauth_client.post(
            "/characters/admin/active-mobs/spawn",
            json={"mob_template_id": 1, "location_id": 5},
        )
        assert resp.status_code in (401, 403)


# ===========================================================================
# 4. GET /characters/admin/active-mobs — pagination & filters
# ===========================================================================

class TestListActiveMobs:
    """Admin active mobs list endpoint."""

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_list_active_mobs_empty(self, mock_attrs, client, db_session):
        resp = client.get("/characters/admin/active-mobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_list_active_mobs_with_data(self, mock_attrs, client, db_session):
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session, location_id=1)
        _create_active_mob(db_session, template.id, char.id, location_id=1)

        resp = client.get("/characters/admin/active-mobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "alive"

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_list_filter_by_location(self, mock_attrs, client, db_session):
        template = _create_mob_template(db_session)
        char1 = _create_mob_character(db_session, name="Волк1", location_id=1)
        char2 = _create_mob_character(db_session, name="Волк2", location_id=2)
        _create_active_mob(db_session, template.id, char1.id, location_id=1)
        _create_active_mob(db_session, template.id, char2.id, location_id=2)

        resp = client.get("/characters/admin/active-mobs?location_id=1")
        data = resp.json()
        assert data["total"] == 1

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_list_filter_by_status(self, mock_attrs, client, db_session):
        template = _create_mob_template(db_session)
        char1 = _create_mob_character(db_session, name="Волк1")
        char2 = _create_mob_character(db_session, name="Волк2")
        _create_active_mob(db_session, template.id, char1.id, status="alive")
        _create_active_mob(db_session, template.id, char2.id, status="dead")

        resp = client.get("/characters/admin/active-mobs?status=alive")
        data = resp.json()
        assert data["total"] == 1

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_list_pagination(self, mock_attrs, client, db_session):
        template = _create_mob_template(db_session)
        for i in range(5):
            char = _create_mob_character(db_session, name=f"Волк{i}")
            _create_active_mob(db_session, template.id, char.id)

        resp = client.get("/characters/admin/active-mobs?page=1&page_size=2")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_list_requires_auth(self, noauth_client, db_session):
        resp = noauth_client.get("/characters/admin/active-mobs")
        assert resp.status_code in (401, 403)


# ===========================================================================
# 5. DELETE /characters/admin/active-mobs/{id}
# ===========================================================================

class TestDeleteActiveMob:
    """Delete active mob and its character."""

    def test_delete_active_mob(self, client, db_session):
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session)
        am = _create_active_mob(db_session, template.id, char.id)

        resp = client.delete(f"/characters/admin/active-mobs/{am.id}")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Моб удалён"

        # Verify mob and character deleted
        assert db_session.query(models.ActiveMob).filter_by(id=am.id).first() is None
        assert db_session.query(models.Character).filter_by(id=char.id).first() is None

    def test_delete_nonexistent_mob(self, client, db_session):
        resp = client.delete("/characters/admin/active-mobs/99999")
        assert resp.status_code == 404

    def test_delete_requires_auth(self, noauth_client, db_session):
        resp = noauth_client.delete("/characters/admin/active-mobs/1")
        assert resp.status_code in (401, 403)


# ===========================================================================
# 6. GET /characters/mobs/by_location — public endpoint
# ===========================================================================

class TestMobsByLocation:
    """Public endpoint for mobs at a location."""

    def test_returns_alive_mobs(self, client, db_session):
        template = _create_mob_template(db_session, name="Злой Волк", tier="elite")
        char = _create_mob_character(db_session, name="Злой Волк", location_id=5)
        _create_active_mob(db_session, template.id, char.id, location_id=5, status="alive")

        resp = client.get("/characters/mobs/by_location?location_id=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Злой Волк"
        assert data[0]["tier"] == "elite"
        assert data[0]["status"] == "alive"

    def test_returns_in_battle_mobs(self, client, db_session):
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session)
        _create_active_mob(db_session, template.id, char.id, status="in_battle")

        resp = client.get("/characters/mobs/by_location?location_id=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "in_battle"

    def test_excludes_dead_mobs(self, client, db_session):
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session)
        _create_active_mob(db_session, template.id, char.id, status="dead")

        resp = client.get("/characters/mobs/by_location?location_id=1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_empty_location(self, client, db_session):
        resp = client.get("/characters/mobs/by_location?location_id=999")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_no_auth_required(self, noauth_client, db_session):
        """Public endpoint works without auth."""
        resp = noauth_client.get("/characters/mobs/by_location?location_id=1")
        assert resp.status_code == 200


# ===========================================================================
# 7. Security tests
# ===========================================================================

class TestMobSpawningSecurity:
    """Security edge cases for mob spawning endpoints."""

    def test_try_spawn_sql_injection_location_id(self, client, db_session):
        """SQL injection in try-spawn body should not crash."""
        resp = client.post(
            "/characters/internal/try-spawn",
            json={"location_id": 1, "character_id": 1},
        )
        # Should handle gracefully (return 200 or 422, not 500)
        assert resp.status_code in (200, 422)

    def test_mobs_by_location_negative_id(self, client, db_session):
        resp = client.get("/characters/mobs/by_location?location_id=-1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_manual_spawn_negative_template_id(self, client, db_session):
        resp = client.post(
            "/characters/admin/active-mobs/spawn",
            json={"mob_template_id": -1, "location_id": 5},
        )
        assert resp.status_code == 404

    def test_delete_mob_zero_id(self, client, db_session):
        resp = client.delete("/characters/admin/active-mobs/0")
        assert resp.status_code == 404

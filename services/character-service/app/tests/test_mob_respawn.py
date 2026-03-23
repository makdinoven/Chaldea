"""
Tests for mob lazy respawn logic in get_mobs_at_location (FEAT-069, Task T11).

Covers:
1. Dead mob with expired respawn_at (in the past) -> respawned to alive
2. Dead mob with future respawn_at -> stays dead, not returned
3. Dead mob without respawn_at (None) -> stays dead permanently
4. Alive mob -> unaffected by respawn logic
5. Mob with status in_battle -> unaffected
6. After respawn: battle_id, killed_at, respawn_at cleared; spawned_at updated; status alive
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timedelta

import database
from database import Base
from main import app, get_db
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from fastapi.testclient import TestClient
import models
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
# Fixtures
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_mob_template(
    db,
    name="Дикий Волк",
    tier="normal",
    level=3,
    respawn_enabled=False,
    respawn_seconds=None,
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
        base_attributes={"strength": 15, "agility": 20},
        xp_reward=50,
        gold_reward=10,
        respawn_enabled=respawn_enabled,
        respawn_seconds=respawn_seconds,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


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


def _create_active_mob(
    db,
    mob_template_id,
    character_id,
    location_id=1,
    status="alive",
    battle_id=None,
    killed_at=None,
    respawn_at=None,
    spawned_at=None,
):
    """Insert an ActiveMob record directly with full control over fields."""
    am = models.ActiveMob(
        mob_template_id=mob_template_id,
        character_id=character_id,
        location_id=location_id,
        status=status,
        spawn_type="random",
        battle_id=battle_id,
        killed_at=killed_at,
        respawn_at=respawn_at,
    )
    if spawned_at is not None:
        am.spawned_at = spawned_at
    db.add(am)
    db.commit()
    db.refresh(am)
    return am


# ===========================================================================
# 1. Dead mob with expired respawn_at -> should be respawned
# ===========================================================================

class TestDeadMobExpiredRespawn:
    """Dead mobs whose respawn_at is in the past should be respawned to alive."""

    def test_expired_respawn_mob_becomes_alive(self, db_session):
        """Dead mob with respawn_at in the past is respawned by get_mobs_at_location."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        char = _create_mob_character(db_session, location_id=10)
        past_time = datetime.utcnow() - timedelta(minutes=5)
        killed_time = datetime.utcnow() - timedelta(minutes=10)

        _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="dead",
            battle_id=42,
            killed_at=killed_time,
            respawn_at=past_time,
        )

        result = crud.get_mobs_at_location(db_session, location_id=10)

        # The mob should now appear in results (respawned)
        assert len(result) == 1
        assert result[0]["name"] == "Волк"
        assert result[0]["status"] == "alive"

    def test_expired_respawn_via_endpoint(self, client, db_session):
        """Dead mob with expired respawn_at appears via GET /characters/mobs/by_location."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        char = _create_mob_character(db_session, name="Волк-Респавн", location_id=7)
        past_time = datetime.utcnow() - timedelta(hours=1)
        killed_time = datetime.utcnow() - timedelta(hours=2)

        _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=7,
            status="dead",
            battle_id=99,
            killed_at=killed_time,
            respawn_at=past_time,
        )

        resp = client.get("/characters/mobs/by_location?location_id=7")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Волк-Респавн"
        assert data[0]["status"] == "alive"

    def test_multiple_expired_mobs_all_respawn(self, db_session):
        """Multiple dead mobs with expired respawn_at all get respawned."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=30)
        past_time = datetime.utcnow() - timedelta(minutes=1)

        for i in range(3):
            char = _create_mob_character(db_session, name=f"Волк{i}", location_id=20)
            _create_active_mob(
                db_session,
                template.id,
                char.id,
                location_id=20,
                status="dead",
                killed_at=past_time,
                respawn_at=past_time,
            )

        result = crud.get_mobs_at_location(db_session, location_id=20)
        assert len(result) == 3


# ===========================================================================
# 2. Dead mob with future respawn_at -> stays dead
# ===========================================================================

class TestDeadMobFutureRespawn:
    """Dead mobs whose respawn_at is in the future should not be respawned."""

    def test_future_respawn_mob_stays_dead(self, db_session):
        """Dead mob with respawn_at in the future is NOT returned."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=3600)
        char = _create_mob_character(db_session, location_id=10)
        future_time = datetime.utcnow() + timedelta(hours=1)

        _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="dead",
            killed_at=datetime.utcnow(),
            respawn_at=future_time,
        )

        result = crud.get_mobs_at_location(db_session, location_id=10)
        assert len(result) == 0

    def test_future_respawn_via_endpoint(self, client, db_session):
        """Dead mob with future respawn_at not returned via endpoint."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=3600)
        char = _create_mob_character(db_session, location_id=15)
        future_time = datetime.utcnow() + timedelta(hours=2)

        _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=15,
            status="dead",
            killed_at=datetime.utcnow(),
            respawn_at=future_time,
        )

        resp = client.get("/characters/mobs/by_location?location_id=15")
        assert resp.status_code == 200
        assert resp.json() == []


# ===========================================================================
# 3. Dead mob without respawn_at (None) -> stays dead permanently
# ===========================================================================

class TestDeadMobNoRespawn:
    """Dead mobs without respawn_at should stay dead permanently."""

    def test_no_respawn_at_stays_dead(self, db_session):
        """Dead mob with respawn_at=None is never respawned."""
        template = _create_mob_template(db_session, respawn_enabled=False)
        char = _create_mob_character(db_session, location_id=10)

        _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="dead",
            killed_at=datetime.utcnow() - timedelta(days=1),
            respawn_at=None,
        )

        result = crud.get_mobs_at_location(db_session, location_id=10)
        assert len(result) == 0

    def test_no_respawn_at_via_endpoint(self, client, db_session):
        """Dead mob with respawn_at=None stays dead via endpoint."""
        template = _create_mob_template(db_session, respawn_enabled=False)
        char = _create_mob_character(db_session, location_id=3)

        _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=3,
            status="dead",
            killed_at=datetime.utcnow() - timedelta(hours=5),
            respawn_at=None,
        )

        resp = client.get("/characters/mobs/by_location?location_id=3")
        assert resp.status_code == 200
        assert resp.json() == []


# ===========================================================================
# 4. Alive mob -> unaffected by respawn logic
# ===========================================================================

class TestAliveMobUnaffected:
    """Alive mobs should be returned normally, unaffected by respawn logic."""

    def test_alive_mob_returned(self, db_session):
        """Alive mob is returned without modification."""
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session, name="Живой Волк", location_id=10)
        am = _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="alive",
        )

        result = crud.get_mobs_at_location(db_session, location_id=10)
        assert len(result) == 1
        assert result[0]["name"] == "Живой Волк"
        assert result[0]["status"] == "alive"

    def test_alive_mob_fields_unchanged(self, db_session):
        """Alive mob's fields are not modified by get_mobs_at_location."""
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session, location_id=10)
        original_spawned = datetime.utcnow() - timedelta(hours=3)
        am = _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="alive",
            spawned_at=original_spawned,
        )

        crud.get_mobs_at_location(db_session, location_id=10)

        db_session.refresh(am)
        assert am.status == "alive"
        assert am.battle_id is None
        assert am.killed_at is None
        assert am.respawn_at is None


# ===========================================================================
# 5. Mob with status in_battle -> unaffected
# ===========================================================================

class TestInBattleMobUnaffected:
    """Mobs with status 'in_battle' should be returned and not modified."""

    def test_in_battle_mob_returned(self, db_session):
        """in_battle mob appears in results."""
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session, name="Бой-Волк", location_id=10)
        _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="in_battle",
            battle_id=55,
        )

        result = crud.get_mobs_at_location(db_session, location_id=10)
        assert len(result) == 1
        assert result[0]["name"] == "Бой-Волк"
        assert result[0]["status"] == "in_battle"

    def test_in_battle_mob_not_modified(self, db_session):
        """in_battle mob's battle_id is preserved."""
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session, location_id=10)
        am = _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="in_battle",
            battle_id=77,
        )

        crud.get_mobs_at_location(db_session, location_id=10)

        db_session.refresh(am)
        assert am.status == "in_battle"
        assert am.battle_id == 77


# ===========================================================================
# 6. After respawn: fields are correctly reset
# ===========================================================================

class TestRespawnFieldsReset:
    """After respawn, verify all fields are correctly updated."""

    def test_battle_id_cleared(self, db_session):
        """After respawn, battle_id should be None."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        char = _create_mob_character(db_session, location_id=10)
        past_time = datetime.utcnow() - timedelta(minutes=5)

        am = _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="dead",
            battle_id=42,
            killed_at=past_time,
            respawn_at=past_time,
        )

        crud.get_mobs_at_location(db_session, location_id=10)
        db_session.refresh(am)

        assert am.battle_id is None

    def test_killed_at_cleared(self, db_session):
        """After respawn, killed_at should be None."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        char = _create_mob_character(db_session, location_id=10)
        past_time = datetime.utcnow() - timedelta(minutes=5)

        am = _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="dead",
            battle_id=10,
            killed_at=past_time,
            respawn_at=past_time,
        )

        crud.get_mobs_at_location(db_session, location_id=10)
        db_session.refresh(am)

        assert am.killed_at is None

    def test_respawn_at_cleared(self, db_session):
        """After respawn, respawn_at should be None."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        char = _create_mob_character(db_session, location_id=10)
        past_time = datetime.utcnow() - timedelta(minutes=5)

        am = _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="dead",
            battle_id=5,
            killed_at=past_time,
            respawn_at=past_time,
        )

        crud.get_mobs_at_location(db_session, location_id=10)
        db_session.refresh(am)

        assert am.respawn_at is None

    def test_spawned_at_updated(self, db_session):
        """After respawn, spawned_at should be updated to approximately now."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        char = _create_mob_character(db_session, location_id=10)
        past_time = datetime.utcnow() - timedelta(minutes=5)
        old_spawned = datetime.utcnow() - timedelta(hours=2)

        am = _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="dead",
            battle_id=5,
            killed_at=past_time,
            respawn_at=past_time,
            spawned_at=old_spawned,
        )

        before_call = datetime.utcnow()
        crud.get_mobs_at_location(db_session, location_id=10)
        after_call = datetime.utcnow()
        db_session.refresh(am)

        assert am.spawned_at >= before_call - timedelta(seconds=1)
        assert am.spawned_at <= after_call + timedelta(seconds=1)

    def test_status_becomes_alive(self, db_session):
        """After respawn, status should be 'alive'."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        char = _create_mob_character(db_session, location_id=10)
        past_time = datetime.utcnow() - timedelta(minutes=5)

        am = _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="dead",
            battle_id=5,
            killed_at=past_time,
            respawn_at=past_time,
        )

        crud.get_mobs_at_location(db_session, location_id=10)
        db_session.refresh(am)

        assert am.status == "alive"

    def test_all_fields_reset_together(self, db_session):
        """Comprehensive check: all respawn field resets happen in one call."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        char = _create_mob_character(db_session, location_id=10)
        killed_time = datetime.utcnow() - timedelta(minutes=10)
        respawn_time = datetime.utcnow() - timedelta(minutes=5)
        old_spawned = datetime.utcnow() - timedelta(hours=1)

        am = _create_active_mob(
            db_session,
            template.id,
            char.id,
            location_id=10,
            status="dead",
            battle_id=123,
            killed_at=killed_time,
            respawn_at=respawn_time,
            spawned_at=old_spawned,
        )

        before_call = datetime.utcnow()
        result = crud.get_mobs_at_location(db_session, location_id=10)
        db_session.refresh(am)

        # Status
        assert am.status == "alive"
        # Cleared fields
        assert am.battle_id is None
        assert am.killed_at is None
        assert am.respawn_at is None
        # Updated spawned_at
        assert am.spawned_at >= before_call - timedelta(seconds=1)
        # Mob appears in results
        assert len(result) == 1


# ===========================================================================
# 7. Mixed scenarios
# ===========================================================================

class TestMixedRespawnScenarios:
    """Test combinations of alive, dead, in_battle, and respawning mobs."""

    def test_mixed_statuses_at_location(self, db_session):
        """Location with alive + dead(expired respawn) + dead(no respawn) + in_battle mobs."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        past_time = datetime.utcnow() - timedelta(minutes=5)

        # Alive mob
        char1 = _create_mob_character(db_session, name="Живой", location_id=30)
        _create_active_mob(db_session, template.id, char1.id, location_id=30, status="alive")

        # Dead mob with expired respawn -> should respawn
        char2 = _create_mob_character(db_session, name="Респавн", location_id=30)
        _create_active_mob(
            db_session, template.id, char2.id, location_id=30,
            status="dead", killed_at=past_time, respawn_at=past_time,
        )

        # Dead mob without respawn -> stays dead
        char3 = _create_mob_character(db_session, name="Мёртвый", location_id=30)
        _create_active_mob(
            db_session, template.id, char3.id, location_id=30,
            status="dead", killed_at=past_time, respawn_at=None,
        )

        # In-battle mob
        char4 = _create_mob_character(db_session, name="Бой", location_id=30)
        _create_active_mob(
            db_session, template.id, char4.id, location_id=30,
            status="in_battle", battle_id=88,
        )

        result = crud.get_mobs_at_location(db_session, location_id=30)

        # Should return: alive + respawned + in_battle = 3 mobs
        assert len(result) == 3
        names = {r["name"] for r in result}
        assert "Живой" in names
        assert "Респавн" in names
        assert "Бой" in names
        assert "Мёртвый" not in names

    def test_respawn_only_at_queried_location(self, db_session):
        """Respawn logic only affects mobs at the queried location."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        past_time = datetime.utcnow() - timedelta(minutes=5)

        # Dead mob at location 40 with expired respawn
        char1 = _create_mob_character(db_session, name="Loc40", location_id=40)
        am1 = _create_active_mob(
            db_session, template.id, char1.id, location_id=40,
            status="dead", killed_at=past_time, respawn_at=past_time,
        )

        # Dead mob at location 50 with expired respawn
        char2 = _create_mob_character(db_session, name="Loc50", location_id=50)
        am2 = _create_active_mob(
            db_session, template.id, char2.id, location_id=50,
            status="dead", killed_at=past_time, respawn_at=past_time,
        )

        # Query only location 40
        result = crud.get_mobs_at_location(db_session, location_id=40)

        assert len(result) == 1
        assert result[0]["name"] == "Loc40"

        # Mob at location 50 should still be dead
        db_session.refresh(am2)
        assert am2.status == "dead"

    def test_respawn_at_exactly_now(self, db_session):
        """Mob with respawn_at equal to now should be respawned (boundary case)."""
        template = _create_mob_template(db_session, respawn_enabled=True, respawn_seconds=60)
        char = _create_mob_character(db_session, location_id=10)

        # Set respawn_at to now (edge case: <= now)
        now = datetime.utcnow()
        _create_active_mob(
            db_session, template.id, char.id, location_id=10,
            status="dead", killed_at=now - timedelta(minutes=1), respawn_at=now,
        )

        result = crud.get_mobs_at_location(db_session, location_id=10)
        # respawn_at <= now should trigger respawn
        assert len(result) == 1

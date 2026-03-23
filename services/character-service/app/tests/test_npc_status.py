"""
Tests for NPC status feature (FEAT-064): npc_status column, filtering, and
internal status update endpoint.

Covers:
- GET /characters/npcs/by_location filters out dead NPCs
- GET /characters/npcs/by_location returns alive NPCs
- PUT /characters/internal/npc-status/{id} sets status to dead
- PUT /characters/internal/npc-status/{id} returns 404 for non-existent character
- PUT /characters/internal/npc-status/{id} rejects non-NPC characters
- GET /characters/admin/npcs includes npc_status field
- PUT /characters/admin/npcs/{id} can resurrect (set status to alive)
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from auth_http import (
    get_admin_user,
    get_current_user_via_http,
    require_permission,
    OAUTH2_SCHEME,
    UserRead,
)
from main import app, get_db
import models
import database


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NPC_ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=["npcs:read", "npcs:create", "npcs:update", "npcs:delete"],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(test_engine):
    """Real SQLite session for integration tests."""
    models.Base.metadata.create_all(bind=test_engine)
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def npc_client(db_session):
    """TestClient with real DB and mocked admin auth."""

    def override_get_db():
        yield db_session

    def override_admin():
        return _NPC_ADMIN_USER

    def override_token():
        return "fake-admin-token"

    def _require_perm_override(permission: str):
        def checker():
            return _NPC_ADMIN_USER
        return checker

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    app.dependency_overrides[OAUTH2_SCHEME] = override_token
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def seed_data(db_session, seed_fk_data):
    """Seed reference data and return a helper to create NPCs."""
    seed_fk_data(db_session)
    return db_session


@pytest.fixture
def create_npc(seed_data):
    """Helper to insert an NPC character directly into the DB."""

    def _create(
        name="Тестовый НПС",
        npc_role="merchant",
        npc_status="alive",
        location_id=1,
        is_npc=True,
    ):
        npc = models.Character(
            name=name,
            id_race=1,
            id_subrace=1,
            id_class=1,
            appearance="test",
            avatar="test.jpg",
            is_npc=is_npc,
            npc_role=npc_role,
            npc_status=npc_status,
            current_location_id=location_id,
            level=1,
            stat_points=0,
            currency_balance=0,
        )
        seed_data.add(npc)
        seed_data.commit()
        seed_data.refresh(npc)
        return npc

    return _create


# ============================================================
# 1. GET /characters/npcs/by_location — filtering
# ============================================================


class TestNpcsByLocationFiltering:
    """GET /characters/npcs/by_location?location_id=X"""

    def test_excludes_dead_npcs(self, npc_client, create_npc):
        """Dead NPCs should NOT appear in location NPC list."""
        create_npc(name="Мёртвый НПС", npc_status="dead", location_id=100)
        create_npc(name="Живой НПС", npc_status="alive", location_id=100)

        resp = npc_client.get("/characters/npcs/by_location", params={"location_id": 100})
        assert resp.status_code == 200
        names = [n["name"] for n in resp.json()]
        assert "Живой НПС" in names
        assert "Мёртвый НПС" not in names

    def test_returns_alive_npcs(self, npc_client, create_npc):
        """Alive NPCs should appear in location NPC list."""
        create_npc(name="НПС-торговец", npc_status="alive", location_id=200)
        create_npc(name="НПС-кузнец", npc_status="alive", location_id=200)

        resp = npc_client.get("/characters/npcs/by_location", params={"location_id": 200})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {n["name"] for n in data}
        assert names == {"НПС-торговец", "НПС-кузнец"}

    def test_excludes_mobs(self, npc_client, create_npc):
        """Mobs (npc_role='mob') should not appear in NPC list."""
        create_npc(name="Моб-волк", npc_role="mob", location_id=300)
        create_npc(name="НПС-стражник", npc_role="guard", location_id=300)

        resp = npc_client.get("/characters/npcs/by_location", params={"location_id": 300})
        assert resp.status_code == 200
        names = [n["name"] for n in resp.json()]
        assert "НПС-стражник" in names
        assert "Моб-волк" not in names

    def test_empty_location(self, npc_client, create_npc):
        """Location with no NPCs returns empty list."""
        resp = npc_client.get("/characters/npcs/by_location", params={"location_id": 999})
        assert resp.status_code == 200
        assert resp.json() == []


# ============================================================
# 2. PUT /characters/internal/npc-status/{id}
# ============================================================


class TestInternalNpcStatus:
    """PUT /characters/internal/npc-status/{character_id}"""

    def test_set_status_to_dead(self, npc_client, create_npc):
        """Should mark an alive NPC as dead."""
        npc = create_npc(name="Жертва", npc_status="alive")
        resp = npc_client.put(
            f"/characters/internal/npc-status/{npc.id}",
            json={"status": "dead"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["status"] == "dead"

    def test_set_status_to_alive(self, npc_client, create_npc):
        """Should mark a dead NPC as alive (resurrect)."""
        npc = create_npc(name="Воскрешаемый", npc_status="dead")
        resp = npc_client.put(
            f"/characters/internal/npc-status/{npc.id}",
            json={"status": "alive"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["status"] == "alive"

    def test_404_for_nonexistent_character(self, npc_client, create_npc):
        """Should return 404 when character does not exist."""
        resp = npc_client.put(
            "/characters/internal/npc-status/99999",
            json={"status": "dead"},
        )
        assert resp.status_code == 404

    def test_rejects_non_npc_character(self, npc_client, create_npc):
        """Should return 404 for a player character (is_npc=False)."""
        player = create_npc(name="Игрок", is_npc=False, npc_role=None)
        resp = npc_client.put(
            f"/characters/internal/npc-status/{player.id}",
            json={"status": "dead"},
        )
        assert resp.status_code == 404

    def test_rejects_mob_character(self, npc_client, create_npc):
        """Should return 404 for a mob character (npc_role='mob')."""
        mob = create_npc(name="Моб", npc_role="mob")
        resp = npc_client.put(
            f"/characters/internal/npc-status/{mob.id}",
            json={"status": "dead"},
        )
        assert resp.status_code == 404

    def test_invalid_status_rejected(self, npc_client, create_npc):
        """Should reject invalid status values."""
        npc = create_npc(name="Валидация")
        resp = npc_client.put(
            f"/characters/internal/npc-status/{npc.id}",
            json={"status": "invalid_value"},
        )
        assert resp.status_code == 422


# ============================================================
# 3. Admin NPC list — npc_status field
# ============================================================


class TestAdminNpcListStatus:
    """GET /characters/admin/npcs"""

    def test_includes_npc_status_field(self, npc_client, create_npc):
        """Admin NPC list items should include npc_status."""
        create_npc(name="Жив-НПС", npc_status="alive")
        create_npc(name="Мёртв-НПС", npc_status="dead")

        resp = npc_client.get("/characters/admin/npcs")
        assert resp.status_code == 200
        body = resp.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        assert len(items) >= 2

        statuses = {i["name"]: i["npc_status"] for i in items}
        assert statuses["Жив-НПС"] == "alive"
        assert statuses["Мёртв-НПС"] == "dead"

    def test_filter_by_status(self, npc_client, create_npc):
        """Admin NPC list should support filtering by npc_status."""
        create_npc(name="Живой", npc_status="alive")
        create_npc(name="Мертвый", npc_status="dead")

        resp = npc_client.get("/characters/admin/npcs", params={"npc_status": "dead"})
        assert resp.status_code == 200
        body = resp.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        names = [i["name"] for i in items]
        assert "Мертвый" in names
        assert "Живой" not in names


# ============================================================
# 4. Admin NPC update — resurrect
# ============================================================


class TestAdminNpcResurrect:
    """PUT /characters/admin/npcs/{id} with npc_status='alive'"""

    def test_resurrect_dead_npc(self, npc_client, create_npc):
        """Admin should be able to set npc_status to alive (resurrect)."""
        npc = create_npc(name="Мёртвый", npc_status="dead")

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"npc_status": "alive"},
        )
        assert resp.status_code == 200

        # Verify via get detail
        detail_resp = npc_client.get(f"/characters/admin/npcs/{npc.id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["npc_status"] == "alive"

    def test_kill_via_admin(self, npc_client, create_npc):
        """Admin should be able to set npc_status to dead."""
        npc = create_npc(name="Живой-НПС", npc_status="alive")

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"npc_status": "dead"},
        )
        assert resp.status_code == 200

        detail_resp = npc_client.get(f"/characters/admin/npcs/{npc.id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["npc_status"] == "dead"

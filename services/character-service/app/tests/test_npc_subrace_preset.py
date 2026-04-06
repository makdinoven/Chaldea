"""
Tests for NPC subrace preset application on update (FEAT-114).

When admin updates an NPC's id_subrace via PUT /characters/admin/npcs/{npc_id},
the endpoint should:
- Detect the subrace change
- Call generate_attributes_for_subrace() to get preset stats
- Call send_attributes_update_request() to push stats to character-attributes-service
- Call send_recalculate_request() to trigger derived stat recalculation

Covers:
1. Updating id_subrace triggers attribute update + recalculate
2. Updating NPC without changing id_subrace does NOT trigger attribute calls
3. Updating only non-subrace fields does NOT trigger attribute calls
4. Attribute service failure is handled gracefully (NPC update still succeeds)
5. Updating id_subrace to the same value does NOT trigger attribute calls
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from auth_http import (
    get_admin_user,
    get_current_user_via_http,
    OAUTH2_SCHEME,
    UserRead,
)
from main import app, get_db
import models
import database


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=["npcs:read", "npcs:create", "npcs:update", "npcs:delete"],
)

_SAMPLE_PRESET = {
    "strength": 15,
    "agility": 12,
    "intelligence": 8,
    "endurance": 14,
    "health": 10,
    "energy": 10,
    "mana": 6,
    "stamina": 13,
    "charisma": 7,
    "luck": 9,
}


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
def seed_data(db_session, seed_fk_data):
    """Seed reference data and return the session."""
    seed_fk_data(db_session)
    return db_session


@pytest.fixture
def seed_data_with_presets(seed_data):
    """Seed reference data and add stat_preset to subraces 1 and 2."""
    subrace_1 = seed_data.query(models.Subrace).filter_by(id_subrace=1).first()
    subrace_2 = seed_data.query(models.Subrace).filter_by(id_subrace=2).first()
    if subrace_1:
        subrace_1.stat_preset = _SAMPLE_PRESET
    if subrace_2:
        subrace_2.stat_preset = {
            "strength": 8,
            "agility": 15,
            "intelligence": 14,
            "endurance": 9,
            "health": 10,
            "energy": 12,
            "mana": 13,
            "stamina": 8,
            "charisma": 11,
            "luck": 10,
        }
    seed_data.commit()
    return seed_data


@pytest.fixture
def create_npc(seed_data_with_presets):
    """Helper to insert an NPC character directly into the DB."""

    def _create(
        name="Тестовый НПС",
        npc_role="merchant",
        npc_status="alive",
        location_id=1,
        id_subrace=1,
    ):
        npc = models.Character(
            name=name,
            id_race=1,
            id_subrace=id_subrace,
            id_class=1,
            appearance="test",
            avatar="test.jpg",
            is_npc=True,
            npc_role=npc_role,
            npc_status=npc_status,
            current_location_id=location_id,
            level=1,
            stat_points=0,
            currency_balance=0,
        )
        seed_data_with_presets.add(npc)
        seed_data_with_presets.commit()
        seed_data_with_presets.refresh(npc)
        return npc

    return _create


# ============================================================
# 1. Updating id_subrace triggers attribute update + recalculate
# ============================================================


class TestSubraceChangeTriggersAttributeUpdate:
    """PUT /characters/admin/npcs/{id} with changed id_subrace should update attributes."""

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_subrace_change_triggers_both_calls(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """Changing id_subrace should call send_attributes_update_request and send_recalculate_request."""
        npc = create_npc(name="НПС-раса", id_subrace=1)

        mock_attr_update.return_value = {"ok": True}
        mock_recalc.return_value = {"ok": True}

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"id_subrace": 2},
        )
        assert resp.status_code == 200

        mock_attr_update.assert_called_once()
        call_args = mock_attr_update.call_args
        assert call_args[0][0] == npc.id  # character_id
        assert isinstance(call_args[0][1], dict)  # attributes dict
        assert call_args[0][2] == "fake-admin-token"  # token

        mock_recalc.assert_called_once()
        recalc_args = mock_recalc.call_args
        assert recalc_args[0][0] == npc.id  # character_id
        assert recalc_args[0][1] == "fake-admin-token"  # token

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_subrace_change_passes_correct_preset(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """The attributes dict passed should come from the new subrace's stat_preset."""
        npc = create_npc(name="НПС-пресет", id_subrace=1)

        mock_attr_update.return_value = {"ok": True}
        mock_recalc.return_value = {"ok": True}

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"id_subrace": 2},
        )
        assert resp.status_code == 200

        # The attributes should be the preset of subrace 2
        call_args = mock_attr_update.call_args
        attributes = call_args[0][1]
        assert attributes["strength"] == 8
        assert attributes["agility"] == 15
        assert attributes["intelligence"] == 14

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_npc_update_response_correct(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """NPC update response should confirm success after subrace change."""
        npc = create_npc(name="НПС-ответ", id_subrace=1)

        mock_attr_update.return_value = {"ok": True}
        mock_recalc.return_value = {"ok": True}

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"id_subrace": 2},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == npc.id
        assert "обновлен" in body["detail"].lower() or "npc" in body["detail"].lower()


# ============================================================
# 2. Updating NPC without changing id_subrace does NOT trigger calls
# ============================================================


class TestNoSubraceChangeNoAttributeCalls:
    """Updating non-subrace fields should not trigger attribute service calls."""

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_update_name_no_attribute_calls(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """Updating only name should not call attribute update or recalculate."""
        npc = create_npc(name="Старое имя", id_subrace=1)

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"name": "Новое имя"},
        )
        assert resp.status_code == 200

        mock_attr_update.assert_not_called()
        mock_recalc.assert_not_called()


# ============================================================
# 3. Updating only non-subrace fields does NOT trigger calls
# ============================================================


class TestNonSubraceFieldsNoAttributeCalls:
    """Various non-subrace field updates should never trigger attribute calls."""

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_update_npc_role_no_attribute_calls(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """Updating npc_role should not trigger attribute calls."""
        npc = create_npc(name="НПС-роль", npc_role="merchant")

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"npc_role": "guard"},
        )
        assert resp.status_code == 200
        mock_attr_update.assert_not_called()
        mock_recalc.assert_not_called()

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_update_npc_status_no_attribute_calls(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """Updating npc_status should not trigger attribute calls."""
        npc = create_npc(name="НПС-статус", npc_status="alive")

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"npc_status": "dead"},
        )
        assert resp.status_code == 200
        mock_attr_update.assert_not_called()
        mock_recalc.assert_not_called()

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_update_level_no_attribute_calls(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """Updating level should not trigger attribute calls."""
        npc = create_npc(name="НПС-уровень")

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"level": 10},
        )
        assert resp.status_code == 200
        mock_attr_update.assert_not_called()
        mock_recalc.assert_not_called()

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_update_multiple_non_subrace_fields(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """Updating multiple non-subrace fields at once should not trigger attribute calls."""
        npc = create_npc(name="НПС-мульти")

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={
                "name": "Новое имя",
                "npc_role": "guard",
                "level": 5,
                "npc_status": "dead",
            },
        )
        assert resp.status_code == 200
        mock_attr_update.assert_not_called()
        mock_recalc.assert_not_called()


# ============================================================
# 4. Attribute service failure handled gracefully
# ============================================================


class TestAttributeServiceFailureHandledGracefully:
    """Attribute service errors should not fail the NPC update."""

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_attr_update_exception_npc_still_updated(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """If send_attributes_update_request raises, NPC update should still succeed."""
        npc = create_npc(name="НПС-ошибка", id_subrace=1)

        mock_attr_update.side_effect = Exception("Connection refused")

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"id_subrace": 2},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == npc.id

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_recalculate_exception_npc_still_updated(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """If send_recalculate_request raises, NPC update should still succeed."""
        npc = create_npc(name="НПС-рекалк-ошибка", id_subrace=1)

        mock_attr_update.return_value = {"ok": True}
        mock_recalc.side_effect = Exception("Timeout")

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"id_subrace": 2},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == npc.id

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_attr_update_returns_none_npc_still_updated(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """If send_attributes_update_request returns None, NPC update should still succeed."""
        npc = create_npc(name="НПС-null", id_subrace=1)

        mock_attr_update.return_value = None
        mock_recalc.return_value = None

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"id_subrace": 2},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == npc.id

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_npc_subrace_field_persisted_despite_attr_failure(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """Even if attribute calls fail, the NPC's id_subrace should be updated in DB."""
        npc = create_npc(name="НПС-persist", id_subrace=1)

        mock_attr_update.side_effect = Exception("Service down")

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"id_subrace": 2},
        )
        assert resp.status_code == 200

        # Verify via GET
        detail_resp = npc_client.get(f"/characters/admin/npcs/{npc.id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id_subrace"] == 2


# ============================================================
# 5. Updating id_subrace to the same value does NOT trigger calls
# ============================================================


class TestSameSubraceNoAttributeCalls:
    """Setting id_subrace to its current value should not trigger attribute updates."""

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_same_subrace_no_calls(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """Updating id_subrace to same value should not trigger attribute calls."""
        npc = create_npc(name="НПС-та-же-раса", id_subrace=1)

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"id_subrace": 1},
        )
        assert resp.status_code == 200
        mock_attr_update.assert_not_called()
        mock_recalc.assert_not_called()

    @patch("crud.send_recalculate_request", new_callable=AsyncMock)
    @patch("crud.send_attributes_update_request", new_callable=AsyncMock)
    def test_same_subrace_with_other_fields_no_calls(
        self, mock_attr_update, mock_recalc, npc_client, create_npc
    ):
        """Updating id_subrace to same value along with other fields should not trigger attribute calls."""
        npc = create_npc(name="НПС-комбо", id_subrace=1)

        resp = npc_client.put(
            f"/characters/admin/npcs/{npc.id}",
            json={"id_subrace": 1, "name": "Новое имя", "level": 5},
        )
        assert resp.status_code == 200
        mock_attr_update.assert_not_called()
        mock_recalc.assert_not_called()

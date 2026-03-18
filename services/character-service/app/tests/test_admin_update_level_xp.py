"""
Tests for Bug 1 fix in FEAT-022: admin_update_character syncs passive_experience
when level is changed.

Covers:
1. Level increase with XP below threshold -> PUT called with correct passive_experience
2. Level increase with XP already above threshold -> PUT NOT called
3. Level decrease -> XP not modified (no PUT call)
4. Update without level change -> no HTTP calls to attributes-service at all
5. Attributes-service unavailable -> level change still succeeds (graceful degradation)
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import String

import database
import models

# Patch Enum columns to String for SQLite compatibility
for col in models.Character.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(50)
for col in models.CharacterRequest.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(50)

from fastapi.testclient import TestClient
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve",
    ],
)


def _seed_request(db, request_id=1):
    """Create a minimal CharacterRequest needed as FK for Character."""
    req = models.CharacterRequest(
        id=request_id,
        name="Test",
        id_subrace=1,
        biography="bio",
        personality="pers",
        id_class=1,
        status="approved",
        user_id=10,
        appearance="appearance",
        id_race=1,
        avatar="/avatar.jpg",
    )
    db.add(req)
    db.commit()
    return req


def _seed_character(db, char_id=1, request_id=1, **overrides):
    """Create a Character in the test DB."""
    defaults = dict(
        id=char_id,
        name="TestChar",
        id_subrace=1,
        id_class=1,
        id_race=1,
        level=1,
        stat_points=0,
        currency_balance=100,
        request_id=request_id,
        user_id=10,
        appearance="appearance",
        avatar="/avatar.jpg",
    )
    defaults.update(overrides)
    ch = models.Character(**defaults)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def _seed_level_threshold(db, level_number, required_experience):
    """Create a LevelThreshold row."""
    lt = models.LevelThreshold(
        level_number=level_number,
        required_experience=required_experience,
    )
    db.add(lt)
    db.commit()
    return lt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session(test_engine, test_session_factory, seed_fk_data):
    database.Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        database.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def admin_client(db_session):
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
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# Tests for XP sync on level change
# ===========================================================================

class TestAdminUpdateLevelXpSync:
    """Tests for passive_experience synchronisation when admin changes level."""

    @patch("httpx.AsyncClient")
    def test_level_increase_xp_below_threshold(
        self, mock_client_class, admin_client, db_session
    ):
        """
        When level is increased and current XP is below the threshold for
        the new level, the endpoint must PUT the correct passive_experience
        to attributes-service.
        """
        _seed_request(db_session)
        _seed_character(db_session, level=1)
        _seed_level_threshold(db_session, level_number=5, required_experience=400)

        # Mock httpx.AsyncClient
        mock_instance = AsyncMock()

        # GET passive_experience -> returns low XP (below 400 threshold)
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"passive_experience": 50}

        # PUT response
        mock_put_response = MagicMock()
        mock_put_response.status_code = 200
        mock_put_response.text = "OK"

        mock_instance.get = AsyncMock(return_value=mock_get_response)
        mock_instance.put = AsyncMock(return_value=mock_put_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_instance

        resp = admin_client.put("/characters/admin/1", json={"level": 5})
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Character updated"

        # Verify character level updated in DB
        ch = db_session.query(models.Character).filter(models.Character.id == 1).first()
        assert ch.level == 5

        # Verify GET was called for passive_experience
        mock_instance.get.assert_called_once()

        # Verify PUT was called with correct passive_experience
        mock_instance.put.assert_called_once()
        put_call = mock_instance.put.call_args
        assert put_call.kwargs.get("json") == {"passive_experience": 400} or \
            (put_call.args and put_call.args[0] is not None and
             put_call.kwargs.get("json") == {"passive_experience": 400})

    @patch("httpx.AsyncClient")
    def test_level_increase_xp_already_above_threshold(
        self, mock_client_class, admin_client, db_session
    ):
        """
        When level is increased but current XP is already above the threshold
        for the new level, the endpoint must NOT call PUT to update XP.
        """
        _seed_request(db_session)
        _seed_character(db_session, level=1)
        _seed_level_threshold(db_session, level_number=5, required_experience=400)

        mock_instance = AsyncMock()

        # GET passive_experience -> returns high XP (above 400 threshold)
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"passive_experience": 999}

        mock_instance.get = AsyncMock(return_value=mock_get_response)
        mock_instance.put = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_instance

        resp = admin_client.put("/characters/admin/1", json={"level": 5})
        assert resp.status_code == 200

        # Verify GET was called (to check current XP)
        mock_instance.get.assert_called_once()

        # Verify PUT was NOT called (XP is already sufficient)
        mock_instance.put.assert_not_called()

    @patch("httpx.AsyncClient")
    def test_level_decrease_does_not_modify_xp(
        self, mock_client_class, admin_client, db_session
    ):
        """
        When level is decreased, the endpoint still checks XP but should
        NOT call PUT because existing XP will be above the lower threshold.
        """
        _seed_request(db_session)
        _seed_character(db_session, level=10)
        _seed_level_threshold(db_session, level_number=3, required_experience=100)
        _seed_level_threshold(db_session, level_number=10, required_experience=2000)

        mock_instance = AsyncMock()

        # Character had level 10, XP was appropriate for level 10.
        # Now level drops to 3, whose threshold is 100 — XP 2000 > 100, so no PUT.
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"passive_experience": 2000}

        mock_instance.get = AsyncMock(return_value=mock_get_response)
        mock_instance.put = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_instance

        resp = admin_client.put("/characters/admin/1", json={"level": 3})
        assert resp.status_code == 200

        ch = db_session.query(models.Character).filter(models.Character.id == 1).first()
        assert ch.level == 3

        # PUT to update XP should NOT have been called
        mock_instance.put.assert_not_called()

    def test_update_without_level_change_no_http_calls(
        self, admin_client, db_session
    ):
        """
        When only stat_points or currency_balance are updated (no level change),
        no HTTP calls to attributes-service should be made at all.
        """
        _seed_request(db_session)
        _seed_character(db_session, level=5, stat_points=0, currency_balance=100)

        with patch("httpx.AsyncClient") as mock_client_class:
            resp = admin_client.put(
                "/characters/admin/1",
                json={"stat_points": 50, "currency_balance": 200},
            )
            assert resp.status_code == 200

            ch = db_session.query(models.Character).filter(
                models.Character.id == 1
            ).first()
            assert ch.stat_points == 50
            assert ch.currency_balance == 200
            assert ch.level == 5  # unchanged

            # httpx.AsyncClient should not have been instantiated at all
            mock_client_class.assert_not_called()

    @patch("httpx.AsyncClient")
    def test_attributes_service_unavailable_level_still_updated(
        self, mock_client_class, admin_client, db_session
    ):
        """
        When attributes-service is unreachable (raises an exception),
        the level change should still succeed (graceful degradation).
        """
        _seed_request(db_session)
        _seed_character(db_session, level=1)
        _seed_level_threshold(db_session, level_number=5, required_experience=400)

        # Simulate connection error
        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_instance

        resp = admin_client.put("/characters/admin/1", json={"level": 5})

        # Level change must succeed despite attributes-service failure
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Character updated"

        ch = db_session.query(models.Character).filter(models.Character.id == 1).first()
        assert ch.level == 5

    @patch("httpx.AsyncClient")
    def test_level_increase_no_threshold_uses_zero(
        self, mock_client_class, admin_client, db_session
    ):
        """
        When no LevelThreshold entry exists for the target level (e.g. level 1),
        required_experience defaults to 0, so no PUT is needed.
        """
        _seed_request(db_session)
        _seed_character(db_session, level=3)
        # No threshold seeded for level 1

        mock_instance = AsyncMock()

        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"passive_experience": 50}

        mock_instance.get = AsyncMock(return_value=mock_get_response)
        mock_instance.put = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_instance

        resp = admin_client.put("/characters/admin/1", json={"level": 1})
        assert resp.status_code == 200

        # required_experience = 0 (no threshold found), XP = 50 >= 0, so no PUT
        mock_instance.put.assert_not_called()

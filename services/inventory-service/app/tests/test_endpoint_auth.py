"""
Tests for user-facing endpoint authentication in inventory-service.

Covers:
- I3: DELETE /inventory/{cid}/items/{iid} — ownership via verify_character_ownership
- I4: POST /inventory/{cid}/equip — ownership via verify_character_ownership
- I5: POST /inventory/{cid}/unequip — ownership via verify_character_ownership
- I6: POST /inventory/{cid}/use_item — ownership via verify_character_ownership
"""

from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, event, text, String
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import database
import models
from auth_http import get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db


# ---------------------------------------------------------------------------
# Test engine (self-contained, same approach as conftest.py)
# ---------------------------------------------------------------------------

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# Patch database module
database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

# Patch ENUM columns to String for SQLite compatibility
for col in models.Items.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(100)

for col in models.EquipmentSlot.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(100)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def auth_db_session():
    """Create all ORM tables + characters table, yield session, drop all."""
    database.Base.metadata.create_all(bind=_test_engine)

    # Create the `characters` table (not owned by this service but needed
    # by verify_character_ownership raw SQL query).
    with _test_engine.connect() as conn:
        conn.execute(text(
            """CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                name TEXT NOT NULL
            )"""
        ))
        conn.commit()

    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        database.Base.metadata.drop_all(bind=_test_engine)
        with _test_engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS characters"))
            conn.commit()


@pytest.fixture()
def auth_client(auth_db_session):
    """TestClient with DB override, NO auth override."""
    from main import get_db as main_get_db

    def override_get_db():
        yield auth_db_session

    app.dependency_overrides[main_get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def _insert_character(auth_db_session):
    """Insert a character row owned by user_id=1."""
    auth_db_session.execute(
        text("INSERT INTO characters (id, user_id, name) VALUES (:id, :uid, :name)"),
        {"id": 1, "uid": 1, "name": "TestChar"},
    )
    auth_db_session.commit()
    return 1


# ===========================================================================
# I3: DELETE /inventory/{cid}/items/{iid} — ownership check
# ===========================================================================

class TestRemoveItemAuth:
    """Auth tests for DELETE /inventory/{cid}/items/{iid}."""

    def test_missing_token_returns_401(self, auth_client):
        """No Authorization header -> 401."""
        response = auth_client.delete("/inventory/1/items/1?quantity=1")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_get, auth_client, _insert_character):
        """Token user (id=999) tries to remove item from character owned by user_id=1 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 999, "username": "hacker", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.delete(
            "/inventory/1/items/1?quantity=1",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_get, auth_client, _insert_character):
        """Token user (id=1) owns the character -> passes auth (not 401/403)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "owner", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.delete(
            "/inventory/1/items/1?quantity=1",
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should pass auth; likely 404 because there's no item in inventory
        assert response.status_code not in (401, 403)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)


# ===========================================================================
# I4: POST /inventory/{cid}/equip — ownership check
# ===========================================================================

class TestEquipItemAuth:
    """Auth tests for POST /inventory/{cid}/equip."""

    EQUIP_PAYLOAD = {"item_id": 1}

    def test_missing_token_returns_401(self, auth_client):
        """No Authorization header -> 401."""
        response = auth_client.post("/inventory/1/equip", json=self.EQUIP_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_get, auth_client, _insert_character):
        """Token user (id=999) tries to equip on character owned by user_id=1 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 999, "username": "hacker", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/equip",
            json=self.EQUIP_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_get, auth_client, _insert_character):
        """Token user (id=1) owns the character -> passes auth (not 401/403)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "owner", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/equip",
            json=self.EQUIP_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should pass auth; may fail on business logic (item not found)
        assert response.status_code not in (401, 403)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)


# ===========================================================================
# I5: POST /inventory/{cid}/unequip — ownership check
# ===========================================================================

class TestUnequipItemAuth:
    """Auth tests for POST /inventory/{cid}/unequip."""

    def test_missing_token_returns_401(self, auth_client):
        """No Authorization header -> 401."""
        response = auth_client.post("/inventory/1/unequip?slot_type=head")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_get, auth_client, _insert_character):
        """Token user (id=999) tries to unequip from character owned by user_id=1 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 999, "username": "hacker", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/unequip?slot_type=head",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_get, auth_client, _insert_character):
        """Token user (id=1) owns the character -> passes auth (not 401/403)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "owner", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/unequip?slot_type=head",
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should pass auth; may fail on business logic (slot empty)
        assert response.status_code not in (401, 403)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)


# ===========================================================================
# I6: POST /inventory/{cid}/use_item — ownership check
# ===========================================================================

class TestUseItemAuth:
    """Auth tests for POST /inventory/{cid}/use_item."""

    USE_PAYLOAD = {"item_id": 1, "quantity": 1}

    def test_missing_token_returns_401(self, auth_client):
        """No Authorization header -> 401."""
        response = auth_client.post("/inventory/1/use_item", json=self.USE_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_get, auth_client, _insert_character):
        """Token user (id=999) tries to use item on character owned by user_id=1 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 999, "username": "hacker", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/use_item",
            json=self.USE_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_get, auth_client, _insert_character):
        """Token user (id=1) owns the character -> passes auth (not 401/403)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "owner", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = auth_client.post(
            "/inventory/1/use_item",
            json=self.USE_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should pass auth; may fail on business logic (item not found)
        assert response.status_code not in (401, 403)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

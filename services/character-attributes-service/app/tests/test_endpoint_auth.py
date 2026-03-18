"""
Tests for user-facing endpoint authentication in character-attributes-service.

Covers:
- A2: POST /attributes/{cid}/upgrade — ownership via verify_character_ownership
"""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# conftest.py already handles sys.path and env vars; just import what we need.
from fastapi.testclient import TestClient

import database
import models
from auth_http import get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db


# ---------------------------------------------------------------------------
# Test engine (re-use the one from conftest if available, otherwise create)
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

# Patch database module to use test engine
database.engine = _test_engine
database.SessionLocal = _TestSessionLocal


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
def db_session():
    """Create tables, yield a session, then drop everything."""
    # Create all ORM tables
    database.Base.metadata.create_all(bind=_test_engine)

    # Also create the `characters` table (not owned by this service but needed
    # by verify_character_ownership which does raw SQL SELECT on it).
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
        # Drop characters table too
        with _test_engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS characters"))
            conn.commit()


@pytest.fixture()
def client(db_session):
    """TestClient with DB override, NO auth override."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def _insert_character(db_session):
    """Insert a character row owned by user_id=1."""
    db_session.execute(
        text("INSERT INTO characters (id, user_id, name) VALUES (:id, :uid, :name)"),
        {"id": 1, "uid": 1, "name": "TestChar"},
    )
    db_session.commit()
    return 1


# ===========================================================================
# A2: POST /attributes/{cid}/upgrade — ownership check
# ===========================================================================

class TestUpgradeAttributes:
    """Auth tests for POST /attributes/{character_id}/upgrade."""

    UPGRADE_PAYLOAD = {
        "strength": 1,
        "agility": 0,
        "intelligence": 0,
        "endurance": 0,
        "health": 0,
        "energy": 0,
        "mana": 0,
        "stamina": 0,
        "charisma": 0,
        "luck": 0,
    }

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        response = client.post("/attributes/1/upgrade", json=self.UPGRADE_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_get, client, _insert_character):
        """Token user (id=999) tries to upgrade character owned by user_id=1 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 999, "username": "hacker", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = client.post(
            "/attributes/1/upgrade",
            json=self.UPGRADE_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
        # Clean up the OAUTH2_SCHEME override (client fixture clears get_db only)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_get, client, _insert_character, db_session):
        """Token user (id=1) owns the character -> passes auth check (not 401/403).

        The endpoint will likely fail on subsequent business logic (httpx call to
        character-service) but that is outside the scope of auth testing.
        """
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "owner", "role": "user", "permissions": []}
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        # Insert character_attributes so the endpoint has data to work with
        attrs = models.CharacterAttributes(character_id=1)
        db_session.add(attrs)
        db_session.commit()

        response = client.post(
            "/attributes/1/upgrade",
            json=self.UPGRADE_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should not be 401 or 403 — auth passed. May be 500 due to httpx call mock
        # not being set up, but auth is verified.
        assert response.status_code not in (401, 403)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

    def test_nonexistent_character_returns_404(self, client):
        """Character does not exist in DB -> 404 from verify_character_ownership."""
        # Override auth to return a valid user
        app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
            id=1, username="user1", role="user", permissions=[]
        )
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = client.post(
            "/attributes/999/upgrade",
            json=self.UPGRADE_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 404
        app.dependency_overrides.pop(get_current_user_via_http, None)
        app.dependency_overrides.pop(OAUTH2_SCHEME, None)

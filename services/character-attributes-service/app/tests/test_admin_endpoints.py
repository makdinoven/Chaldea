"""
Tests for FEAT-021 admin endpoints in character-attributes-service:
- PUT /attributes/admin/{character_id}
- DELETE /attributes/{character_id}
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Patch database BEFORE importing main
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

import database  # noqa: E402
database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

import models  # noqa: E402
import schemas  # noqa: E402
from auth_http import get_admin_user, UserRead  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(id=1, username="admin", role="admin")
_REGULAR_USER = UserRead(id=2, username="player", role="user")


def _create_attributes(db, character_id=1, **overrides):
    """Create a CharacterAttributes row and return it."""
    defaults = dict(
        character_id=character_id,
        current_health=100,
        max_health=100,
        current_mana=75,
        max_mana=75,
        current_energy=50,
        max_energy=50,
        current_stamina=50,
        max_stamina=50,
        strength=10,
        agility=10,
        intelligence=10,
        endurance=10,
        health=10,
        mana=7,
        energy=5,
        stamina=10,
        charisma=1,
        luck=1,
        damage=0,
    )
    defaults.update(overrides)
    attr = models.CharacterAttributes(**defaults)
    db.add(attr)
    db.commit()
    db.refresh(attr)
    return attr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    database.Base.metadata.create_all(bind=_test_engine)
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        database.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def admin_client(db_session):
    def override_get_db():
        yield db_session

    def override_admin():
        return _ADMIN_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def non_admin_client(db_session):
    """Client that does not override auth — will fail auth (no token)."""
    def override_get_db():
        yield db_session

    # Do not override get_admin_user: the real auth_http will be called
    # but there's no real user-service, so it will fail with 401/503.
    # Instead, we override to return a non-admin user.
    def override_non_admin():
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Только администраторы могут выполнять это действие")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_non_admin
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# PUT /attributes/admin/{character_id}
# ===========================================================================

class TestAdminUpdateAttributes:

    def test_partial_update_success(self, admin_client, db_session):
        attr = _create_attributes(db_session, character_id=1)
        resp = admin_client.put(
            "/attributes/admin/1",
            json={"current_health": 999, "strength": 50},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_health"] == 999
        assert data["strength"] == 50
        # Other fields should remain unchanged
        assert data["max_health"] == 100

    def test_update_not_found(self, admin_client, db_session):
        resp = admin_client.put(
            "/attributes/admin/999",
            json={"strength": 10},
        )
        assert resp.status_code == 404

    def test_update_forbidden_for_non_admin(self, non_admin_client, db_session):
        resp = non_admin_client.put(
            "/attributes/admin/1",
            json={"strength": 10},
        )
        assert resp.status_code == 403

    def test_update_no_fields_still_returns(self, admin_client, db_session):
        """Sending empty body should still succeed (no-op) — returns current attrs."""
        _create_attributes(db_session, character_id=1)
        resp = admin_client.put(
            "/attributes/admin/1",
            json={},
        )
        assert resp.status_code == 200

    def test_update_float_fields(self, admin_client, db_session):
        _create_attributes(db_session, character_id=1, dodge=5.0, res_fire=0.0)
        resp = admin_client.put(
            "/attributes/admin/1",
            json={"dodge": 15.5, "res_fire": 25.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dodge"] == 15.5
        assert data["res_fire"] == 25.0


# ===========================================================================
# DELETE /attributes/{character_id}
# ===========================================================================

class TestAdminDeleteAttributes:

    def test_delete_success(self, admin_client, db_session):
        _create_attributes(db_session, character_id=1)
        resp = admin_client.delete("/attributes/1")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Attributes deleted"

        # Verify deleted
        attr = db_session.query(models.CharacterAttributes).filter(
            models.CharacterAttributes.character_id == 1
        ).first()
        assert attr is None

    def test_delete_not_found(self, admin_client, db_session):
        resp = admin_client.delete("/attributes/999")
        assert resp.status_code == 404

    def test_delete_forbidden_for_non_admin(self, non_admin_client, db_session):
        resp = non_admin_client.delete("/attributes/1")
        assert resp.status_code == 403

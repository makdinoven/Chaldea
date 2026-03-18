"""
Tests for FEAT-021 admin endpoints in user-service:
- DELETE /users/user_characters/{user_id}/{character_id}
- POST /users/{user_id}/clear_current_character
"""

import pytest
from unittest.mock import MagicMock
from database import Base
import models


# ---------------------------------------------------------------------------
# RBAC seed data — required because require_permission() queries the
# permissions table to compute effective permissions for the user.
# ---------------------------------------------------------------------------

def _seed_rbac(db):
    """Seed minimal RBAC tables so that admin users get 'users:manage' permission."""
    # Permission that the admin endpoints require
    perm = models.Permission(id=1, module="users", action="manage")
    db.add(perm)
    db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_admin_user(db):
    """Create an admin user in the test DB and return the user object."""
    user = models.User(
        id=1,
        email="admin@test.com",
        username="admin",
        hashed_password="hashed",
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_regular_user(db):
    """Create a regular (non-admin) user in the test DB."""
    user = models.User(
        id=2,
        email="player@test.com",
        username="player",
        hashed_password="hashed",
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_user_character_relation(db, user_id, character_id):
    """Insert a row in users_character."""
    relation = models.UserCharacter(user_id=user_id, character_id=character_id)
    db.add(relation)
    db.commit()
    return relation


def _override_auth(app, get_db_func, user_obj):
    """Override get_current_user to return the given user object."""
    from auth import get_current_user

    def override_get_current_user():
        return user_obj

    app.dependency_overrides[get_current_user] = override_get_current_user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(test_engine, test_session_local):
    Base.metadata.create_all(bind=test_engine)
    session = test_session_local()
    _seed_rbac(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def admin_client(db):
    """TestClient authenticated as admin."""
    from main import app
    from database import get_db
    from auth import get_current_user
    from fastapi.testclient import TestClient

    admin = _create_admin_user(db)

    def override_get_db():
        yield db

    def override_auth():
        return admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_auth
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def non_admin_client(db):
    """TestClient authenticated as a regular user."""
    from main import app
    from database import get_db
    from auth import get_current_user
    from fastapi.testclient import TestClient

    user = _create_regular_user(db)

    def override_get_db():
        yield db

    def override_auth():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_auth
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# DELETE /users/user_characters/{user_id}/{character_id}
# ===========================================================================

class TestDeleteUserCharacterRelation:

    def test_delete_relation_success(self, admin_client, db):
        _create_user_character_relation(db, user_id=1, character_id=5)
        resp = admin_client.delete("/users/user_characters/1/5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "User-character relation deleted"

        # Verify actually deleted from DB
        rel = db.query(models.UserCharacter).filter(
            models.UserCharacter.user_id == 1,
            models.UserCharacter.character_id == 5,
        ).first()
        assert rel is None

    def test_delete_relation_not_found(self, admin_client, db):
        resp = admin_client.delete("/users/user_characters/999/999")
        assert resp.status_code == 404

    def test_delete_relation_forbidden_for_non_admin(self, non_admin_client, db):
        resp = non_admin_client.delete("/users/user_characters/1/5")
        assert resp.status_code == 403


# ===========================================================================
# POST /users/{user_id}/clear_current_character
# ===========================================================================

class TestClearCurrentCharacter:

    def test_clear_matching_current_character(self, admin_client, db):
        """When user.current_character matches, it should be cleared."""
        user = db.query(models.User).filter(models.User.id == 1).first()
        user.current_character = 5
        db.commit()

        resp = admin_client.post(
            "/users/1/clear_current_character",
            json={"character_id": 5},
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Current character cleared"

        db.refresh(user)
        assert user.current_character is None

    def test_clear_non_matching_noop(self, admin_client, db):
        """When user.current_character does NOT match, it's a no-op (idempotent)."""
        user = db.query(models.User).filter(models.User.id == 1).first()
        user.current_character = 10
        db.commit()

        resp = admin_client.post(
            "/users/1/clear_current_character",
            json={"character_id": 5},
        )
        assert resp.status_code == 200

        db.refresh(user)
        assert user.current_character == 10  # unchanged

    def test_clear_user_not_found(self, admin_client, db):
        resp = admin_client.post(
            "/users/999/clear_current_character",
            json={"character_id": 5},
        )
        assert resp.status_code == 404

    def test_clear_forbidden_for_non_admin(self, non_admin_client, db):
        resp = non_admin_client.post(
            "/users/2/clear_current_character",
            json={"character_id": 5},
        )
        assert resp.status_code == 403

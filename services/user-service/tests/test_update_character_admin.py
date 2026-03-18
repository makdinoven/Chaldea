"""
Tests for FEAT-040: admin bypass on PUT /users/{user_id}/update_character.

Scenarios:
1. Admin can update any user's current_character -> 200
2. Moderator can update any user's current_character -> 200
3. Regular user CANNOT update another user's character -> 403
4. Regular user CAN update their own character -> 200
"""

import pytest
from fastapi.testclient import TestClient

from database import Base, get_db
from main import app
from auth import get_current_user
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_rbac(db):
    """Seed minimal RBAC roles so is_admin() can resolve role_id."""
    admin_role = models.Role(id=1, name="admin", level=100, description="Admin")
    mod_role = models.Role(id=2, name="moderator", level=50, description="Moderator")
    user_role = models.Role(id=3, name="user", level=0, description="User")
    db.add_all([admin_role, mod_role, user_role])
    db.commit()


def _create_user(db, *, id, email, username, role, role_id=None):
    """Create a user with given role and return the object."""
    user = models.User(
        id=id,
        email=email,
        username=username,
        hashed_password="hashed",
        role=role,
        role_id=role_id,
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


def _make_client(db, user_obj):
    """Return a TestClient authenticated as the given user, with DB overridden."""

    def override_get_db():
        yield db

    def override_auth():
        return user_obj

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_auth
    client = TestClient(app)
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(test_engine, test_session_local):
    """Clean DB session with RBAC roles seeded."""
    Base.metadata.create_all(bind=test_engine)
    session = test_session_local()
    _seed_rbac(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def target_user(db):
    """The user whose current_character will be updated (regular user, id=10)."""
    user = _create_user(db, id=10, email="target@test.com", username="target", role="user", role_id=3)
    # Give this user a character relation so the endpoint can find it
    _create_user_character_relation(db, user_id=10, character_id=42)
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUpdateCharacterAdminBypass:
    """PUT /users/{user_id}/update_character — admin/moderator bypass tests."""

    def test_admin_can_update_any_user_character(self, db, target_user):
        """Admin user calls PUT for another user's ID -> 200."""
        admin = _create_user(db, id=1, email="admin@test.com", username="admin", role="admin", role_id=1)
        client = _make_client(db, admin)
        try:
            resp = client.put(
                f"/users/{target_user.id}/update_character",
                json={"current_character": 42},
            )
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["current_character"] == 42

            # Verify DB was updated
            db.refresh(target_user)
            assert target_user.current_character == 42
        finally:
            app.dependency_overrides.clear()

    def test_moderator_can_update_any_user_character(self, db, target_user):
        """Moderator user calls PUT for another user's ID -> 200."""
        moderator = _create_user(db, id=2, email="mod@test.com", username="moderator", role="moderator", role_id=2)
        client = _make_client(db, moderator)
        try:
            resp = client.put(
                f"/users/{target_user.id}/update_character",
                json={"current_character": 42},
            )
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["current_character"] == 42
        finally:
            app.dependency_overrides.clear()

    def test_regular_user_cannot_update_another_user_character(self, db, target_user):
        """Regular user calls PUT for a different user_id -> 403."""
        regular = _create_user(db, id=3, email="regular@test.com", username="regular", role="user", role_id=3)
        client = _make_client(db, regular)
        try:
            resp = client.put(
                f"/users/{target_user.id}/update_character",
                json={"current_character": 42},
            )
            assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        finally:
            app.dependency_overrides.clear()

    def test_regular_user_can_update_own_character(self, db):
        """Regular user calls PUT for their own user_id -> 200."""
        regular = _create_user(db, id=5, email="self@test.com", username="selfuser", role="user", role_id=3)
        _create_user_character_relation(db, user_id=5, character_id=99)
        client = _make_client(db, regular)
        try:
            resp = client.put(
                f"/users/{regular.id}/update_character",
                json={"current_character": 99},
            )
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["current_character"] == 99

            # Verify DB was updated
            db.refresh(regular)
            assert regular.current_character == 99
        finally:
            app.dependency_overrides.clear()

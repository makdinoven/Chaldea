"""
FEAT-035 Task #6 — QA Tests for RBAC Management Endpoints.

Covers all 5 RBAC management endpoints in user-service:
1. GET /users/roles — list roles
2. PUT /users/{user_id}/role — assign role
3. GET /users/permissions — list permissions grouped by module
4. PUT /users/{user_id}/permissions — set permission overrides
5. GET /users/{user_id}/effective-permissions — get effective permissions
"""

import sys
import os

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

# conftest.py handles sys.path and env vars setup

from crud import create_user, pwd_context
from schemas import UserCreate
import models
from auth import get_current_user
from database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(db, username="testuser", email="test@example.com", password="secret123"):
    """Create a user via CRUD and return the ORM object."""
    user_data = UserCreate(email=email, username=username, password=password)
    return create_user(db, user_data)


def _seed_roles(db):
    """Seed the 4 standard roles into the DB. Returns dict {name: Role}."""
    roles_data = [
        ("user", 0, "Обычный пользователь"),
        ("editor", 20, "Редактор контента"),
        ("moderator", 50, "Модератор"),
        ("admin", 100, "Администратор"),
    ]
    roles = {}
    for name, level, desc in roles_data:
        role = models.Role(name=name, level=level, description=desc)
        db.add(role)
        db.flush()
        roles[name] = role
    db.commit()
    return roles


def _seed_permissions(db):
    """Seed permissions for 'users' and 'items' modules. Returns list of Permission objects."""
    perms = []
    for module in ("items", "users"):
        for action in ("create", "delete", "manage", "read", "update"):
            p = models.Permission(module=module, action=action, description=f"{module}:{action}")
            db.add(p)
            db.flush()
            perms.append(p)
    db.commit()
    return perms


def _seed_role_permissions(db, roles, permissions):
    """Assign permissions to roles following the project spec.

    - admin: gets ALL permissions (but code computes this dynamically)
    - moderator: gets items:* permissions (not users:manage)
    - editor: gets items:read only
    - user: no role_permissions
    """
    admin_role = roles["admin"]
    mod_role = roles["moderator"]
    editor_role = roles["editor"]

    for perm in permissions:
        # Admin gets everything via code, but we also seed for completeness
        db.add(models.RolePermission(role_id=admin_role.id, permission_id=perm.id))

        # Moderator gets items:* and users:read
        if perm.module == "items" or (perm.module == "users" and perm.action == "read"):
            db.add(models.RolePermission(role_id=mod_role.id, permission_id=perm.id))

        # Editor gets read only
        if perm.action == "read":
            db.add(models.RolePermission(role_id=editor_role.id, permission_id=perm.id))

    db.commit()


def _make_admin(db, user, roles):
    """Set a user to admin role."""
    admin_role = roles["admin"]
    user.role_id = admin_role.id
    user.role = "admin"
    db.commit()
    db.refresh(user)
    return user


def _make_user_with_role(db, user, roles, role_name):
    """Set a user to a specific role."""
    role = roles[role_name]
    user.role_id = role.id
    user.role = role_name
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def rbac_db(db_session):
    """DB session with RBAC seed data (roles, permissions, role_permissions)."""
    roles = _seed_roles(db_session)
    perms = _seed_permissions(db_session)
    _seed_role_permissions(db_session, roles, perms)
    return db_session


@pytest.fixture()
def roles(rbac_db):
    """Return dict of role name -> Role object."""
    all_roles = rbac_db.query(models.Role).all()
    return {r.name: r for r in all_roles}


@pytest.fixture()
def permissions(rbac_db):
    """Return list of all Permission objects."""
    return rbac_db.query(models.Permission).all()


@pytest.fixture()
def admin_user(rbac_db, roles):
    """Create and return an admin user."""
    user = _create_user(rbac_db, username="adminuser", email="admin@test.com")
    return _make_admin(rbac_db, user, roles)


@pytest.fixture()
def regular_user(rbac_db, roles):
    """Create and return a regular (non-admin) user."""
    user = _create_user(rbac_db, username="regularuser", email="regular@test.com")
    return _make_user_with_role(rbac_db, user, roles, "user")


@pytest.fixture()
def admin_client(rbac_db, admin_user):
    """TestClient authenticated as admin user."""
    from main import app

    def override_get_db():
        yield rbac_db

    def override_get_current_user():
        return admin_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def regular_client(rbac_db, regular_user):
    """TestClient authenticated as regular (non-admin) user."""
    from main import app

    def override_get_db():
        yield rbac_db

    def override_get_current_user():
        return regular_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def unauth_client(rbac_db):
    """TestClient with no auth override (unauthenticated)."""
    from main import app

    def override_get_db():
        yield rbac_db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# 1. GET /users/roles
# ===========================================================================

class TestListRoles:
    """Tests for GET /users/roles endpoint."""

    def test_admin_returns_all_roles_ordered_by_level(self, admin_client):
        """Admin can list all 4 roles, ordered by level ascending."""
        resp = admin_client.get("/users/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4
        levels = [r["level"] for r in data]
        assert levels == sorted(levels), "Roles must be ordered by level ascending"
        names = {r["name"] for r in data}
        assert names == {"user", "editor", "moderator", "admin"}

    def test_non_admin_returns_403(self, regular_client):
        """Non-admin user gets 403."""
        resp = regular_client.get("/users/roles")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, unauth_client):
        """Unauthenticated request gets 401."""
        resp = unauth_client.get("/users/roles")
        assert resp.status_code == 401


# ===========================================================================
# 2. PUT /users/{user_id}/role
# ===========================================================================

class TestAssignRole:
    """Tests for PUT /users/{user_id}/role endpoint."""

    def test_admin_assigns_moderator_role(self, admin_client, rbac_db, roles, regular_user):
        """Admin assigns moderator role — user role changes, legacy role string synced."""
        mod_role = roles["moderator"]
        resp = admin_client.put(
            f"/users/{regular_user.id}/role",
            json={"role_id": mod_role.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "moderator"
        assert data["id"] == regular_user.id

        # Verify DB was updated
        rbac_db.refresh(regular_user)
        assert regular_user.role_id == mod_role.id
        assert regular_user.role == "moderator"

    def test_admin_assigns_role_with_custom_display_name(self, admin_client, rbac_db, roles, regular_user):
        """Admin assigns role with custom display_name — role_display_name set correctly."""
        mod_role = roles["moderator"]
        resp = admin_client.put(
            f"/users/{regular_user.id}/role",
            json={"role_id": mod_role.id, "display_name": "Куратор контента"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role_display_name"] == "Куратор контента"

        rbac_db.refresh(regular_user)
        assert regular_user.role_display_name == "Куратор контента"

    def test_last_admin_protection(self, admin_client, roles, admin_user):
        """Cannot demote the only admin — returns 409."""
        user_role = roles["user"]
        resp = admin_client.put(
            f"/users/{admin_user.id}/role",
            json={"role_id": user_role.id},
        )
        assert resp.status_code == 409
        assert "последнего" in resp.json()["detail"].lower() or "админ" in resp.json()["detail"].lower()

    def test_demote_non_last_admin_succeeds(self, admin_client, rbac_db, roles):
        """Demoting a non-last admin succeeds when there are 2+ admins."""
        # Create a second admin
        second_admin = _create_user(rbac_db, username="admin2", email="admin2@test.com")
        _make_admin(rbac_db, second_admin, roles)

        user_role = roles["user"]
        resp = admin_client.put(
            f"/users/{second_admin.id}/role",
            json={"role_id": user_role.id},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "user"

    def test_non_admin_returns_403(self, regular_client, roles, admin_user):
        """Non-admin trying to assign role gets 403."""
        user_role = roles["user"]
        resp = regular_client.put(
            f"/users/{admin_user.id}/role",
            json={"role_id": user_role.id},
        )
        assert resp.status_code == 403

    def test_invalid_role_id_returns_404(self, admin_client, regular_user):
        """Invalid role_id returns 404."""
        resp = admin_client.put(
            f"/users/{regular_user.id}/role",
            json={"role_id": 99999},
        )
        assert resp.status_code == 404

    def test_invalid_user_id_returns_404(self, admin_client, roles):
        """Invalid user_id returns 404."""
        mod_role = roles["moderator"]
        resp = admin_client.put(
            "/users/99999/role",
            json={"role_id": mod_role.id},
        )
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, unauth_client, roles):
        """Unauthenticated request gets 401."""
        resp = unauth_client.put(
            "/users/1/role",
            json={"role_id": 1},
        )
        assert resp.status_code == 401


# ===========================================================================
# 3. GET /users/permissions
# ===========================================================================

class TestListPermissions:
    """Tests for GET /users/permissions endpoint."""

    def test_admin_returns_permissions_grouped_by_module(self, admin_client):
        """Admin gets permissions grouped by module (users and items)."""
        resp = admin_client.get("/users/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert "modules" in data
        modules = data["modules"]
        assert "users" in modules
        assert "items" in modules
        # Each module should have 5 actions (create, read, update, delete, manage)
        assert len(modules["users"]) == 5
        assert len(modules["items"]) == 5

    def test_permission_item_has_required_fields(self, admin_client):
        """Each permission item has id, module, action fields."""
        resp = admin_client.get("/users/permissions")
        data = resp.json()
        for module_name, perms in data["modules"].items():
            for perm in perms:
                assert "id" in perm
                assert "module" in perm
                assert "action" in perm
                assert perm["module"] == module_name

    def test_non_admin_returns_403(self, regular_client):
        """Non-admin gets 403."""
        resp = regular_client.get("/users/permissions")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, unauth_client):
        """Unauthenticated request gets 401."""
        resp = unauth_client.get("/users/permissions")
        assert resp.status_code == 401


# ===========================================================================
# 4. PUT /users/{user_id}/permissions
# ===========================================================================

class TestSetPermissionOverrides:
    """Tests for PUT /users/{user_id}/permissions endpoint."""

    def test_admin_sets_grants_for_editor(self, admin_client, rbac_db, roles):
        """Admin grants extra permissions to an editor user."""
        editor = _create_user(rbac_db, username="editor1", email="editor@test.com")
        _make_user_with_role(rbac_db, editor, roles, "editor")

        resp = admin_client.put(
            f"/users/{editor.id}/permissions",
            json={"grants": ["items:create", "items:update"], "revokes": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items:create" in data["permissions"]
        assert "items:update" in data["permissions"]
        assert data["overrides"]["grants"] == ["items:create", "items:update"]

    def test_admin_sets_revokes_for_moderator(self, admin_client, rbac_db, roles):
        """Admin revokes permissions from a moderator user."""
        mod = _create_user(rbac_db, username="mod1", email="mod@test.com")
        _make_user_with_role(rbac_db, mod, roles, "moderator")

        # Moderator has items:create by default via role_permissions
        resp = admin_client.put(
            f"/users/{mod.id}/permissions",
            json={"grants": [], "revokes": ["items:create"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items:create" not in data["permissions"]
        assert data["overrides"]["revokes"] == ["items:create"]

    def test_overrides_on_admin_returns_400(self, admin_client, admin_user):
        """Cannot set overrides on admin user — returns 400."""
        resp = admin_client.put(
            f"/users/{admin_user.id}/permissions",
            json={"grants": ["items:read"], "revokes": []},
        )
        assert resp.status_code == 400

    def test_invalid_permission_format_returns_422(self, admin_client, rbac_db, roles):
        """Permission string without colon returns 422."""
        user = _create_user(rbac_db, username="user_fmt", email="fmt@test.com")
        _make_user_with_role(rbac_db, user, roles, "user")

        resp = admin_client.put(
            f"/users/{user.id}/permissions",
            json={"grants": ["invalid_no_colon"], "revokes": []},
        )
        assert resp.status_code == 422

    def test_nonexistent_permission_returns_422(self, admin_client, rbac_db, roles):
        """Permission that doesn't exist in DB returns 422."""
        user = _create_user(rbac_db, username="user_nx", email="nx@test.com")
        _make_user_with_role(rbac_db, user, roles, "user")

        resp = admin_client.put(
            f"/users/{user.id}/permissions",
            json={"grants": ["nonexistent:action"], "revokes": []},
        )
        assert resp.status_code == 422

    def test_non_admin_returns_403(self, regular_client, regular_user):
        """Non-admin trying to set overrides gets 403."""
        resp = regular_client.put(
            f"/users/{regular_user.id}/permissions",
            json={"grants": ["items:read"], "revokes": []},
        )
        assert resp.status_code == 403

    def test_invalid_user_id_returns_404(self, admin_client):
        """Invalid user_id returns 404."""
        resp = admin_client.put(
            "/users/99999/permissions",
            json={"grants": [], "revokes": []},
        )
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, unauth_client):
        """Unauthenticated request gets 401."""
        resp = unauth_client.put(
            "/users/1/permissions",
            json={"grants": [], "revokes": []},
        )
        assert resp.status_code == 401

    def test_revoke_in_grants_field_returns_422_for_bad_format(self, admin_client, rbac_db, roles):
        """Invalid format in revokes also returns 422."""
        user = _create_user(rbac_db, username="user_rev", email="rev@test.com")
        _make_user_with_role(rbac_db, user, roles, "user")

        resp = admin_client.put(
            f"/users/{user.id}/permissions",
            json={"grants": [], "revokes": ["badformat"]},
        )
        assert resp.status_code == 422


# ===========================================================================
# 5. GET /users/{user_id}/effective-permissions
# ===========================================================================

class TestEffectivePermissions:
    """Tests for GET /users/{user_id}/effective-permissions endpoint."""

    def test_admin_user_gets_all_permissions(self, admin_client, admin_user, permissions):
        """Admin user has ALL permissions from the permissions table."""
        resp = admin_client.get(f"/users/{admin_user.id}/effective-permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "admin"
        assert data["user_id"] == admin_user.id
        # Admin gets all permissions dynamically
        effective = data["effective_permissions"]
        assert len(effective) == len(permissions)

    def test_moderator_gets_role_permissions(self, admin_client, rbac_db, roles):
        """Moderator gets only role-based permissions."""
        mod = _create_user(rbac_db, username="mod2", email="mod2@test.com")
        _make_user_with_role(rbac_db, mod, roles, "moderator")

        resp = admin_client.get(f"/users/{mod.id}/effective-permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "moderator"
        assert "items:create" in data["effective_permissions"]
        assert "users:read" in data["effective_permissions"]
        # Moderator should NOT have users:manage
        assert "users:manage" not in data["effective_permissions"]
        # role_permissions should be populated
        assert len(data["role_permissions"]) > 0

    def test_user_with_overrides_shows_correct_effective(self, admin_client, rbac_db, roles):
        """User with permission overrides shows correct effective permissions."""
        editor = _create_user(rbac_db, username="editor2", email="editor2@test.com")
        _make_user_with_role(rbac_db, editor, roles, "editor")

        # First set an override grant
        admin_client.put(
            f"/users/{editor.id}/permissions",
            json={"grants": ["items:create"], "revokes": ["items:read"]},
        )

        resp = admin_client.get(f"/users/{editor.id}/effective-permissions")
        assert resp.status_code == 200
        data = resp.json()
        # items:create should be granted via override
        assert "items:create" in data["effective_permissions"]
        # items:read was revoked
        assert "items:read" not in data["effective_permissions"]
        # Overrides should be reported
        assert "items:create" in data["overrides"]["grants"]
        assert "items:read" in data["overrides"]["revokes"]

    def test_non_admin_returns_403(self, regular_client, regular_user):
        """Non-admin gets 403."""
        resp = regular_client.get(f"/users/{regular_user.id}/effective-permissions")
        assert resp.status_code == 403

    def test_invalid_user_id_returns_404(self, admin_client):
        """Invalid user_id returns 404."""
        resp = admin_client.get("/users/99999/effective-permissions")
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, unauth_client):
        """Unauthenticated request gets 401."""
        resp = unauth_client.get("/users/1/effective-permissions")
        assert resp.status_code == 401

    def test_response_includes_role_display_name(self, admin_client, rbac_db, roles):
        """Response includes role_display_name if set."""
        user = _create_user(rbac_db, username="display_test", email="display@test.com")
        _make_user_with_role(rbac_db, user, roles, "moderator")
        user.role_display_name = "Куратор"
        rbac_db.commit()
        rbac_db.refresh(user)

        resp = admin_client.get(f"/users/{user.id}/effective-permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role_display_name"] == "Куратор"


# ===========================================================================
# Security tests
# ===========================================================================

class TestRBACSecurityEdgeCases:
    """Security-focused tests for RBAC endpoints."""

    def test_sql_injection_in_permission_string(self, admin_client, rbac_db, roles):
        """SQL injection in permission string must not crash the service."""
        user = _create_user(rbac_db, username="sqli_user", email="sqli@test.com")
        _make_user_with_role(rbac_db, user, roles, "user")

        resp = admin_client.put(
            f"/users/{user.id}/permissions",
            json={"grants": ["'; DROP TABLE users; --:action"], "revokes": []},
        )
        # Should return 422 (not found) rather than 500
        assert resp.status_code == 422

    def test_empty_grants_and_revokes_succeeds(self, admin_client, rbac_db, roles):
        """Empty grants and revokes clears existing overrides without error."""
        user = _create_user(rbac_db, username="empty_user", email="empty@test.com")
        _make_user_with_role(rbac_db, user, roles, "user")

        resp = admin_client.put(
            f"/users/{user.id}/permissions",
            json={"grants": [], "revokes": []},
        )
        assert resp.status_code == 200

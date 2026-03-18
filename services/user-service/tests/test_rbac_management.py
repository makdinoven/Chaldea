"""
FEAT-036 Task #12 — QA Tests for Migration 0007 and New Endpoints.

Covers:
1. Migration data integrity — all 27 permissions, module coverage, role assignments
2. GET /users/admin/list — pagination, search, role_id filter, auth checks
3. GET /users/roles/{role_id}/permissions — correct permissions per role, auth
4. PUT /users/roles/{role_id}/permissions — update, admin protection, validation, auth
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from crud import create_user, get_effective_permissions
from schemas import UserCreate
import models
from auth import get_current_user
from database import get_db


# ---------------------------------------------------------------------------
# All 27 permissions from migrations 0006 + 0007
# ---------------------------------------------------------------------------

ALL_PERMISSIONS = [
    # 0006: users module (IDs 1-4)
    (1,  "users",         "read"),
    (2,  "users",         "update"),
    (3,  "users",         "delete"),
    (4,  "users",         "manage"),
    # 0006: items module (IDs 5-8)
    (5,  "items",         "create"),
    (6,  "items",         "read"),
    (7,  "items",         "update"),
    (8,  "items",         "delete"),
    # 0007: characters module (IDs 9-13)
    (9,  "characters",    "create"),
    (10, "characters",    "read"),
    (11, "characters",    "update"),
    (12, "characters",    "delete"),
    (13, "characters",    "approve"),
    # 0007: skills module (IDs 14-17)
    (14, "skills",        "create"),
    (15, "skills",        "read"),
    (16, "skills",        "update"),
    (17, "skills",        "delete"),
    # 0007: locations module (IDs 18-21)
    (18, "locations",     "create"),
    (19, "locations",     "read"),
    (20, "locations",     "update"),
    (21, "locations",     "delete"),
    # 0007: rules module (IDs 22-25)
    (22, "rules",         "create"),
    (23, "rules",         "read"),
    (24, "rules",         "update"),
    (25, "rules",         "delete"),
    # 0007: photos module (ID 26)
    (26, "photos",        "upload"),
    # 0007: notifications module (ID 27)
    (27, "notifications", "create"),
]

EXPECTED_MODULES = {"users", "items", "characters", "skills", "locations", "rules", "photos", "notifications"}

# Moderator: all except users:* = 23 permissions
MODERATOR_PERMISSION_IDS = list(range(5, 28))  # items(5-8) + all new(9-27)

# Editor: *:read = users:read(1), items:read(6), characters:read(10), skills:read(15), locations:read(19), rules:read(23)
EDITOR_PERMISSION_IDS = [1, 6, 10, 15, 19, 23]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_permissions(db):
    """Seed all 27 permissions into the DB."""
    for pid, module, action in ALL_PERMISSIONS:
        db.add(models.Permission(id=pid, module=module, action=action,
                                 description=f"{module}:{action}"))
    db.commit()


def _seed_roles(db):
    """Seed the 4 standard roles. Returns {name: Role}."""
    roles_data = [
        (1, "user",      0,   "Regular user"),
        (2, "editor",    20,  "Editor"),
        (3, "moderator", 50,  "Moderator"),
        (4, "admin",     100, "Administrator"),
    ]
    roles = {}
    for rid, name, level, desc in roles_data:
        r = models.Role(id=rid, name=name, level=level, description=desc)
        db.add(r)
        roles[name] = r
    db.commit()
    return roles


def _seed_role_permissions(db):
    """Seed role_permissions matching migrations 0006 + 0007.

    Admin (4): all 27
    Moderator (3): items(5-8) + new(9-27) = 23
    Editor (2): users:read(1), items:read(6), characters:read(10), skills:read(15),
                locations:read(19), rules:read(23) = 6
    User (1): nothing
    """
    # Admin: all
    for pid in range(1, 28):
        db.add(models.RolePermission(role_id=4, permission_id=pid))
    # Moderator
    for pid in MODERATOR_PERMISSION_IDS:
        db.add(models.RolePermission(role_id=3, permission_id=pid))
    # Editor
    for pid in EDITOR_PERMISSION_IDS:
        db.add(models.RolePermission(role_id=2, permission_id=pid))
    db.commit()


def _seed_all_rbac(db):
    """Full RBAC seed: roles + 27 permissions + role_permissions."""
    roles = _seed_roles(db)
    _seed_permissions(db)
    _seed_role_permissions(db)
    return roles


def _create_user(db, username="testuser", email="test@example.com", password="secret123"):
    """Create a user via CRUD and return the ORM object."""
    user_data = UserCreate(email=email, username=username, password=password)
    return create_user(db, user_data)


def _set_role(db, user, roles, role_name):
    """Assign a role to a user."""
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
    """DB session with full RBAC seed (4 roles, 27 permissions, role_permissions)."""
    _seed_all_rbac(db_session)
    return db_session


@pytest.fixture()
def roles(rbac_db):
    """Return dict {name: Role}."""
    all_roles = rbac_db.query(models.Role).all()
    return {r.name: r for r in all_roles}


@pytest.fixture()
def admin_user(rbac_db, roles):
    user = _create_user(rbac_db, username="adminuser", email="admin@test.com")
    return _set_role(rbac_db, user, roles, "admin")


@pytest.fixture()
def moderator_user(rbac_db, roles):
    user = _create_user(rbac_db, username="moduser", email="mod@test.com")
    return _set_role(rbac_db, user, roles, "moderator")


@pytest.fixture()
def editor_user(rbac_db, roles):
    user = _create_user(rbac_db, username="editoruser", email="editor@test.com")
    return _set_role(rbac_db, user, roles, "editor")


@pytest.fixture()
def regular_user(rbac_db, roles):
    user = _create_user(rbac_db, username="regularuser", email="regular@test.com")
    return _set_role(rbac_db, user, roles, "user")


def _make_client(db, user=None):
    """Build a TestClient with DB + optional auth overrides."""
    from main import app

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture()
def admin_client(rbac_db, admin_user):
    from main import app
    client = _make_client(rbac_db, admin_user)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def regular_client(rbac_db, regular_user):
    from main import app
    client = _make_client(rbac_db, regular_user)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def unauth_client(rbac_db):
    """Client with no auth override — requests go through real auth (no token = 401)."""
    from main import app

    def override_get_db():
        yield rbac_db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# 1. Migration data integrity tests
# ===========================================================================

class TestMigrationDataIntegrity:
    """Verify the combined permission set from migrations 0006 + 0007."""

    def test_all_27_permissions_exist(self, rbac_db):
        """All 27 permissions should be seeded in the permissions table."""
        count = rbac_db.query(models.Permission).count()
        assert count == 27

    def test_all_modules_present(self, rbac_db):
        """All 8 modules should be represented in the permissions table."""
        modules = {
            p.module
            for p in rbac_db.query(models.Permission).all()
        }
        assert modules == EXPECTED_MODULES

    def test_each_permission_module_action(self, rbac_db):
        """Each expected (module, action) pair exists."""
        all_perms = rbac_db.query(models.Permission).all()
        actual = {(p.module, p.action) for p in all_perms}
        expected = {(m, a) for _, m, a in ALL_PERMISSIONS}
        assert actual == expected

    def test_admin_has_all_permissions_via_effective(self, rbac_db, admin_user):
        """Admin gets all 27 permissions via get_effective_permissions."""
        perms = get_effective_permissions(rbac_db, admin_user)
        assert len(perms) == 27
        # Spot-check a few
        assert "users:manage" in perms
        assert "characters:approve" in perms
        assert "photos:upload" in perms
        assert "notifications:create" in perms

    def test_moderator_has_23_permissions(self, rbac_db, moderator_user):
        """Moderator has all except users:* = 23 permissions."""
        perms = get_effective_permissions(rbac_db, moderator_user)
        assert len(perms) == 23
        # Must NOT have users:*
        assert "users:read" not in perms
        assert "users:update" not in perms
        assert "users:delete" not in perms
        assert "users:manage" not in perms
        # Must have everything else
        assert "items:create" in perms
        assert "characters:approve" in perms
        assert "skills:create" in perms
        assert "locations:create" in perms
        assert "rules:create" in perms
        assert "photos:upload" in perms
        assert "notifications:create" in perms

    def test_editor_has_6_read_permissions(self, rbac_db, editor_user):
        """Editor has only *:read permissions = 6 total."""
        perms = get_effective_permissions(rbac_db, editor_user)
        assert len(perms) == 6
        expected_editor = {
            "users:read", "items:read", "characters:read",
            "skills:read", "locations:read", "rules:read",
        }
        assert set(perms) == expected_editor

    def test_regular_user_has_no_permissions(self, rbac_db, regular_user):
        """Regular user has no permissions."""
        perms = get_effective_permissions(rbac_db, regular_user)
        assert perms == []

    def test_role_permissions_count_admin(self, rbac_db, roles):
        """Admin role has 27 explicit role_permissions rows."""
        count = (
            rbac_db.query(models.RolePermission)
            .filter(models.RolePermission.role_id == roles["admin"].id)
            .count()
        )
        assert count == 27

    def test_role_permissions_count_moderator(self, rbac_db, roles):
        """Moderator role has 23 explicit role_permissions rows."""
        count = (
            rbac_db.query(models.RolePermission)
            .filter(models.RolePermission.role_id == roles["moderator"].id)
            .count()
        )
        assert count == 23

    def test_role_permissions_count_editor(self, rbac_db, roles):
        """Editor role has 6 explicit role_permissions rows."""
        count = (
            rbac_db.query(models.RolePermission)
            .filter(models.RolePermission.role_id == roles["editor"].id)
            .count()
        )
        assert count == 6


# ===========================================================================
# 2. GET /users/admin/list tests
# ===========================================================================

class TestAdminList:
    """Tests for GET /users/admin/list endpoint."""

    def test_admin_returns_paginated_list(self, admin_client, admin_user):
        """Admin gets paginated user list with role and permissions."""
        resp = admin_client.get("/users/admin/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["total"] >= 1
        # admin_user should be in the list
        usernames = [item["username"] for item in data["items"]]
        assert "adminuser" in usernames

    def test_response_includes_role_and_permissions(self, admin_client, admin_user):
        """Each item includes role, role_id, role_display_name, permissions."""
        resp = admin_client.get("/users/admin/list")
        data = resp.json()
        admin_item = next(i for i in data["items"] if i["username"] == "adminuser")
        assert admin_item["role"] == "admin"
        assert admin_item["role_id"] is not None
        assert "permissions" in admin_item
        assert len(admin_item["permissions"]) == 27

    def test_search_filter_by_username(self, admin_client, rbac_db, roles):
        """Search filter narrows results by username."""
        # Create a second user with a distinct name
        u2 = _create_user(rbac_db, username="searchable_guy", email="search@test.com")
        _set_role(rbac_db, u2, roles, "editor")

        resp = admin_client.get("/users/admin/list?search=searchable")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["username"] == "searchable_guy"

    def test_search_filter_by_email(self, admin_client, rbac_db, roles):
        """Search filter also matches email."""
        u = _create_user(rbac_db, username="emailtest", email="unique_email_xyz@test.com")
        _set_role(rbac_db, u, roles, "user")

        resp = admin_client.get("/users/admin/list?search=unique_email_xyz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_role_id_filter(self, admin_client, rbac_db, roles):
        """role_id filter returns only users with that role."""
        # Create users with different roles
        u_mod = _create_user(rbac_db, username="modfilter", email="modfilter@test.com")
        _set_role(rbac_db, u_mod, roles, "moderator")

        mod_role_id = roles["moderator"].id
        resp = admin_client.get(f"/users/admin/list?role_id={mod_role_id}")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["role_id"] == mod_role_id

    def test_pagination_works(self, admin_client, rbac_db, roles):
        """Pagination returns correct page_size and allows paging through results."""
        # Create several users
        for i in range(5):
            u = _create_user(rbac_db, username=f"pageuser{i}", email=f"page{i}@test.com")
            _set_role(rbac_db, u, roles, "user")

        resp = admin_client.get("/users/admin/list?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["total"] >= 6  # admin_user + 5 created

        # Page 2
        resp2 = admin_client.get("/users/admin/list?page=2&page_size=2")
        data2 = resp2.json()
        assert data2["page"] == 2
        # Items on page 2 should be different from page 1
        page1_ids = {i["id"] for i in data["items"]}
        page2_ids = {i["id"] for i in data2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_non_admin_returns_403(self, regular_client):
        """Non-admin user gets 403."""
        resp = regular_client.get("/users/admin/list")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, unauth_client):
        """Unauthenticated request gets 401."""
        resp = unauth_client.get("/users/admin/list")
        assert resp.status_code == 401


# ===========================================================================
# 3. GET /users/roles/{role_id}/permissions tests
# ===========================================================================

class TestGetRolePermissions:
    """Tests for GET /users/roles/{role_id}/permissions endpoint."""

    def test_admin_gets_role_permissions(self, admin_client, roles):
        """Admin can retrieve permissions for a role."""
        resp = admin_client.get(f"/users/roles/{roles['moderator'].id}/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role_id"] == roles["moderator"].id
        assert data["role_name"] == "moderator"
        assert isinstance(data["permissions"], list)

    def test_moderator_permissions_correct(self, admin_client, roles):
        """Moderator role returns correct 23 permissions (all except users:*)."""
        resp = admin_client.get(f"/users/roles/{roles['moderator'].id}/permissions")
        data = resp.json()
        perms = data["permissions"]
        assert len(perms) == 23
        # Must not include users:*
        users_perms = [p for p in perms if p.startswith("users:")]
        assert users_perms == []
        # Must include items, characters, skills, locations, rules, photos, notifications
        assert "items:create" in perms
        assert "characters:approve" in perms
        assert "photos:upload" in perms

    def test_editor_permissions_correct(self, admin_client, roles):
        """Editor role returns correct 6 read-only permissions."""
        resp = admin_client.get(f"/users/roles/{roles['editor'].id}/permissions")
        data = resp.json()
        perms = data["permissions"]
        assert len(perms) == 6
        expected = {
            "users:read", "items:read", "characters:read",
            "skills:read", "locations:read", "rules:read",
        }
        assert set(perms) == expected

    def test_admin_role_returns_all_27(self, admin_client, roles):
        """Admin role returns all 27 permissions."""
        resp = admin_client.get(f"/users/roles/{roles['admin'].id}/permissions")
        data = resp.json()
        assert len(data["permissions"]) == 27

    def test_user_role_returns_empty(self, admin_client, roles):
        """Regular user role returns empty permissions list."""
        resp = admin_client.get(f"/users/roles/{roles['user'].id}/permissions")
        data = resp.json()
        assert data["permissions"] == []

    def test_invalid_role_id_returns_404(self, admin_client):
        """Non-existent role_id returns 404."""
        resp = admin_client.get("/users/roles/99999/permissions")
        assert resp.status_code == 404

    def test_non_admin_returns_403(self, regular_client, roles):
        """Non-admin user gets 403."""
        resp = regular_client.get(f"/users/roles/{roles['moderator'].id}/permissions")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, unauth_client, roles):
        """Unauthenticated request gets 401."""
        resp = unauth_client.get(f"/users/roles/{roles['moderator'].id}/permissions")
        assert resp.status_code == 401


# ===========================================================================
# 4. PUT /users/roles/{role_id}/permissions tests
# ===========================================================================

class TestSetRolePermissions:
    """Tests for PUT /users/roles/{role_id}/permissions endpoint."""

    def test_admin_updates_moderator_permissions(self, admin_client, rbac_db, roles):
        """Admin can update moderator permissions — saved correctly."""
        new_perms = ["items:read", "items:create", "characters:read"]
        resp = admin_client.put(
            f"/users/roles/{roles['moderator'].id}/permissions",
            json={"permissions": new_perms},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["permissions"]) == set(new_perms)
        assert data["role_name"] == "moderator"

        # Verify via GET
        resp2 = admin_client.get(f"/users/roles/{roles['moderator'].id}/permissions")
        assert set(resp2.json()["permissions"]) == set(new_perms)

    def test_cannot_modify_admin_role(self, admin_client, roles):
        """Cannot modify admin role permissions — returns 400."""
        resp = admin_client.put(
            f"/users/roles/{roles['admin'].id}/permissions",
            json={"permissions": ["items:read"]},
        )
        assert resp.status_code == 400
        assert "администратор" in resp.json()["detail"].lower()

    def test_invalid_permission_format_returns_422(self, admin_client, roles):
        """Permission string without colon returns 422."""
        resp = admin_client.put(
            f"/users/roles/{roles['moderator'].id}/permissions",
            json={"permissions": ["invalid_no_colon"]},
        )
        assert resp.status_code == 422

    def test_nonexistent_permission_returns_422(self, admin_client, roles):
        """Permission that does not exist in the DB returns 422."""
        resp = admin_client.put(
            f"/users/roles/{roles['moderator'].id}/permissions",
            json={"permissions": ["nonexistent:action"]},
        )
        assert resp.status_code == 422

    def test_non_admin_returns_403(self, regular_client, roles):
        """Non-admin user gets 403."""
        resp = regular_client.put(
            f"/users/roles/{roles['moderator'].id}/permissions",
            json={"permissions": ["items:read"]},
        )
        assert resp.status_code == 403

    def test_invalid_role_id_returns_404(self, admin_client):
        """Non-existent role_id returns 404."""
        resp = admin_client.put(
            "/users/roles/99999/permissions",
            json={"permissions": ["items:read"]},
        )
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, unauth_client, roles):
        """Unauthenticated request gets 401."""
        resp = unauth_client.put(
            f"/users/roles/{roles['moderator'].id}/permissions",
            json={"permissions": ["items:read"]},
        )
        assert resp.status_code == 401

    def test_empty_permissions_clears_role_permissions(self, admin_client, rbac_db, roles):
        """Empty permissions list clears all role_permissions for the role."""
        resp = admin_client.put(
            f"/users/roles/{roles['moderator'].id}/permissions",
            json={"permissions": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["permissions"] == []

        # Verify in DB
        count = (
            rbac_db.query(models.RolePermission)
            .filter(models.RolePermission.role_id == roles["moderator"].id)
            .count()
        )
        assert count == 0

    def test_sql_injection_in_permission_string(self, admin_client, roles):
        """SQL injection in permission string returns 422, not 500."""
        resp = admin_client.put(
            f"/users/roles/{roles['editor'].id}/permissions",
            json={"permissions": ["'; DROP TABLE permissions; --:evil"]},
        )
        assert resp.status_code == 422

    def test_updated_permissions_affect_effective(self, admin_client, rbac_db, roles):
        """After updating role permissions, get_effective_permissions reflects changes."""
        # Reduce editor to only items:read
        admin_client.put(
            f"/users/roles/{roles['editor'].id}/permissions",
            json={"permissions": ["items:read"]},
        )

        # Create editor user and check effective permissions
        editor = _create_user(rbac_db, username="efftest", email="eff@test.com")
        _set_role(rbac_db, editor, roles, "editor")
        perms = get_effective_permissions(rbac_db, editor)
        assert perms == ["items:read"]

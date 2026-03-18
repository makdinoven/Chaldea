"""
FEAT-035 Task #5 — QA Tests for RBAC Models, Migration, and CRUD.

Covers:
1. get_effective_permissions() for admin, moderator, editor, user roles
2. Permission overrides (grants add, revokes remove, both combined)
3. Admin auto-permissions (admin always gets ALL permissions)
4. /users/me endpoint returns permissions and role_display_name
5. require_permission() raises 403 when user lacks permission
"""

import pytest
from unittest.mock import patch, AsyncMock

import models
from crud import get_effective_permissions, require_permission, is_admin, require_admin
from database import Base, get_db
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

def _seed_roles(db):
    """Create the 4 standard RBAC roles."""
    roles = [
        models.Role(id=1, name="user", level=0, description="Regular user"),
        models.Role(id=2, name="editor", level=20, description="Editor (read-only admin)"),
        models.Role(id=3, name="moderator", level=50, description="Moderator (all except users)"),
        models.Role(id=4, name="admin", level=100, description="Administrator (full access)"),
    ]
    for r in roles:
        db.add(r)
    db.commit()
    return {r.name: r for r in roles}


def _seed_permissions(db):
    """Create the 8 standard permissions (users + items modules)."""
    perms = [
        models.Permission(id=1, module="users", action="read"),
        models.Permission(id=2, module="users", action="update"),
        models.Permission(id=3, module="users", action="delete"),
        models.Permission(id=4, module="users", action="manage"),
        models.Permission(id=5, module="items", action="create"),
        models.Permission(id=6, module="items", action="read"),
        models.Permission(id=7, module="items", action="update"),
        models.Permission(id=8, module="items", action="delete"),
    ]
    for p in perms:
        db.add(p)
    db.commit()
    return perms


def _seed_role_permissions(db):
    """Assign permissions to roles per spec:
    - Admin gets ALL (but admin auto-perm logic means role_permissions rows
      aren't strictly needed — tested separately)
    - Moderator gets items:* (permissions 5-8)
    - Editor gets *:read (permissions 1, 6)
    - User gets nothing
    """
    # Admin: all 8
    for pid in range(1, 9):
        db.add(models.RolePermission(role_id=4, permission_id=pid))
    # Moderator: items:* (ids 5-8)
    for pid in [5, 6, 7, 8]:
        db.add(models.RolePermission(role_id=3, permission_id=pid))
    # Editor: *:read (ids 1, 6)
    for pid in [1, 6]:
        db.add(models.RolePermission(role_id=2, permission_id=pid))
    # User: nothing
    db.commit()


def _seed_rbac(db):
    """Full RBAC seed: roles + permissions + role_permissions."""
    roles = _seed_roles(db)
    perms = _seed_permissions(db)
    _seed_role_permissions(db)
    return roles, perms


def _make_user(db, *, id, username, email, role_id=None, role_str="user", role_display_name=None):
    """Create a test user with specified role_id."""
    user = models.User(
        id=id,
        email=email,
        username=username,
        hashed_password="hashed_placeholder",
        role=role_str,
        role_id=role_id,
        role_display_name=role_display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def rbac_db(db_session):
    """DB session with RBAC seed data (roles, permissions, role_permissions)."""
    _seed_rbac(db_session)
    return db_session


@pytest.fixture()
def admin_user(rbac_db):
    return _make_user(rbac_db, id=1, username="admin", email="admin@test.com",
                      role_id=4, role_str="admin", role_display_name="Главный админ")


@pytest.fixture()
def moderator_user(rbac_db):
    return _make_user(rbac_db, id=2, username="moderator", email="mod@test.com",
                      role_id=3, role_str="moderator", role_display_name="Куратор контента")


@pytest.fixture()
def editor_user(rbac_db):
    return _make_user(rbac_db, id=3, username="editor", email="editor@test.com",
                      role_id=2, role_str="editor")


@pytest.fixture()
def regular_user(rbac_db):
    return _make_user(rbac_db, id=4, username="player", email="player@test.com",
                      role_id=1, role_str="user")


# ---------------------------------------------------------------------------
# 1. Test get_effective_permissions() for each role
# ---------------------------------------------------------------------------

class TestGetEffectivePermissions:
    """Test that get_effective_permissions returns correct permissions per role."""

    def test_admin_gets_all_permissions(self, rbac_db, admin_user):
        """Admin role should return ALL permissions from the permissions table."""
        perms = get_effective_permissions(rbac_db, admin_user)
        assert len(perms) == 8
        assert "users:read" in perms
        assert "users:update" in perms
        assert "users:delete" in perms
        assert "users:manage" in perms
        assert "items:create" in perms
        assert "items:read" in perms
        assert "items:update" in perms
        assert "items:delete" in perms

    def test_moderator_gets_items_permissions(self, rbac_db, moderator_user):
        """Moderator role should return only items:* permissions (via role_permissions)."""
        perms = get_effective_permissions(rbac_db, moderator_user)
        assert len(perms) == 4
        assert "items:create" in perms
        assert "items:read" in perms
        assert "items:update" in perms
        assert "items:delete" in perms
        # Must NOT have users permissions
        assert "users:manage" not in perms
        assert "users:read" not in perms

    def test_editor_gets_read_permissions(self, rbac_db, editor_user):
        """Editor role should return only *:read permissions (via role_permissions)."""
        perms = get_effective_permissions(rbac_db, editor_user)
        assert len(perms) == 2
        assert "items:read" in perms
        assert "users:read" in perms
        # Must NOT have write permissions
        assert "items:create" not in perms
        assert "users:manage" not in perms

    def test_regular_user_gets_no_permissions(self, rbac_db, regular_user):
        """User role should return empty list (no role_permissions assigned)."""
        perms = get_effective_permissions(rbac_db, regular_user)
        assert perms == []

    def test_user_without_role_id_uses_legacy_string(self, rbac_db):
        """User with no role_id falls back to legacy role string column."""
        user = _make_user(rbac_db, id=10, username="legacy", email="legacy@test.com",
                          role_id=None, role_str="user")
        perms = get_effective_permissions(rbac_db, user)
        assert perms == []

    def test_legacy_admin_string_gets_all_permissions(self, rbac_db):
        """User with role='admin' but no role_id should still get all permissions."""
        user = _make_user(rbac_db, id=11, username="legacyadmin", email="legacyadmin@test.com",
                          role_id=None, role_str="admin")
        perms = get_effective_permissions(rbac_db, user)
        assert len(perms) == 8


# ---------------------------------------------------------------------------
# 2. Test permission overrides
# ---------------------------------------------------------------------------

class TestPermissionOverrides:
    """Test user_permissions overrides (grants and revokes)."""

    def test_grant_adds_extra_permission(self, rbac_db, regular_user):
        """A granted user_permission should add a permission not in the role."""
        # Regular user has no permissions; grant items:read
        perm_items_read = rbac_db.query(models.Permission).filter(
            models.Permission.module == "items",
            models.Permission.action == "read",
        ).first()
        override = models.UserPermission(
            user_id=regular_user.id,
            permission_id=perm_items_read.id,
            granted=True,
        )
        rbac_db.add(override)
        rbac_db.commit()

        perms = get_effective_permissions(rbac_db, regular_user)
        assert "items:read" in perms
        assert len(perms) == 1

    def test_revoke_removes_role_permission(self, rbac_db, moderator_user):
        """A revoked user_permission should remove a permission from the role."""
        # Moderator has items:create; revoke it
        perm_items_create = rbac_db.query(models.Permission).filter(
            models.Permission.module == "items",
            models.Permission.action == "create",
        ).first()
        override = models.UserPermission(
            user_id=moderator_user.id,
            permission_id=perm_items_create.id,
            granted=False,
        )
        rbac_db.add(override)
        rbac_db.commit()

        perms = get_effective_permissions(rbac_db, moderator_user)
        assert "items:create" not in perms
        # Other moderator permissions remain
        assert "items:read" in perms
        assert "items:update" in perms
        assert "items:delete" in perms
        assert len(perms) == 3

    def test_grant_and_revoke_combined(self, rbac_db, moderator_user):
        """Both grant and revoke overrides apply correctly."""
        # Grant users:read (not in moderator role)
        perm_users_read = rbac_db.query(models.Permission).filter(
            models.Permission.module == "users",
            models.Permission.action == "read",
        ).first()
        rbac_db.add(models.UserPermission(
            user_id=moderator_user.id,
            permission_id=perm_users_read.id,
            granted=True,
        ))

        # Revoke items:delete (in moderator role)
        perm_items_delete = rbac_db.query(models.Permission).filter(
            models.Permission.module == "items",
            models.Permission.action == "delete",
        ).first()
        rbac_db.add(models.UserPermission(
            user_id=moderator_user.id,
            permission_id=perm_items_delete.id,
            granted=False,
        ))
        rbac_db.commit()

        perms = get_effective_permissions(rbac_db, moderator_user)
        # Should have: items:create, items:read, items:update + users:read
        # Should NOT have: items:delete
        assert "users:read" in perms
        assert "items:create" in perms
        assert "items:read" in perms
        assert "items:update" in perms
        assert "items:delete" not in perms
        assert len(perms) == 4

    def test_revoke_nonexistent_permission_is_noop(self, rbac_db, regular_user):
        """Revoking a permission the user doesn't have is a no-op."""
        perm = rbac_db.query(models.Permission).first()
        rbac_db.add(models.UserPermission(
            user_id=regular_user.id,
            permission_id=perm.id,
            granted=False,
        ))
        rbac_db.commit()

        perms = get_effective_permissions(rbac_db, regular_user)
        assert perms == []

    def test_grant_duplicate_permission_is_idempotent(self, rbac_db, moderator_user):
        """Granting a permission the role already has doesn't duplicate it."""
        perm_items_create = rbac_db.query(models.Permission).filter(
            models.Permission.module == "items",
            models.Permission.action == "create",
        ).first()
        rbac_db.add(models.UserPermission(
            user_id=moderator_user.id,
            permission_id=perm_items_create.id,
            granted=True,
        ))
        rbac_db.commit()

        perms = get_effective_permissions(rbac_db, moderator_user)
        # items:create should appear exactly once
        assert perms.count("items:create") == 1
        assert len(perms) == 4  # same count as moderator without override


# ---------------------------------------------------------------------------
# 3. Test admin auto-permissions (CRITICAL)
# ---------------------------------------------------------------------------

class TestAdminAutoPermissions:
    """Admin role must automatically get ALL permissions, including newly added ones."""

    def test_admin_gets_newly_added_permission(self, rbac_db, admin_user):
        """Adding a new permission to the DB should be included for admin user."""
        # Add a brand new permission
        new_perm = models.Permission(module="skills", action="create",
                                      description="Create skills")
        rbac_db.add(new_perm)
        rbac_db.commit()

        perms = get_effective_permissions(rbac_db, admin_user)
        assert "skills:create" in perms
        assert len(perms) == 9  # 8 original + 1 new

    def test_admin_gets_multiple_new_permissions(self, rbac_db, admin_user):
        """Adding multiple new permissions all appear for admin."""
        new_perms = [
            models.Permission(module="skills", action="create"),
            models.Permission(module="skills", action="delete"),
            models.Permission(module="locations", action="manage"),
        ]
        for p in new_perms:
            rbac_db.add(p)
        rbac_db.commit()

        perms = get_effective_permissions(rbac_db, admin_user)
        assert "skills:create" in perms
        assert "skills:delete" in perms
        assert "locations:manage" in perms
        assert len(perms) == 11  # 8 + 3

    def test_non_admin_does_not_get_new_permission_automatically(self, rbac_db, moderator_user):
        """Moderator should NOT auto-get new permissions (only admin does)."""
        rbac_db.add(models.Permission(module="skills", action="create"))
        rbac_db.commit()

        perms = get_effective_permissions(rbac_db, moderator_user)
        assert "skills:create" not in perms
        # Moderator still has only items:* (4 permissions)
        assert len(perms) == 4


# ---------------------------------------------------------------------------
# 4. Test /users/me response includes permissions and role_display_name
# ---------------------------------------------------------------------------

class TestUsersMeEndpoint:
    """Integration tests for GET /users/me — RBAC fields in response."""

    def _make_auth_client(self, db, user):
        """Create a TestClient authenticated as the given user."""
        from main import app
        from auth import get_current_user
        from fastapi.testclient import TestClient

        def override_get_db():
            yield db

        def override_auth():
            return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_auth
        client = TestClient(app)
        return client

    @patch("main.httpx.AsyncClient")
    def test_admin_me_returns_all_permissions(self, mock_httpx_class, rbac_db, admin_user):
        """Admin /me response includes all permissions and role_display_name."""
        client = self._make_auth_client(rbac_db, admin_user)
        try:
            resp = client.get("/users/me")
            assert resp.status_code == 200
            data = resp.json()
            assert data["role"] == "admin"
            assert data["role_display_name"] == "Главный админ"
            assert len(data["permissions"]) == 8
            assert "users:manage" in data["permissions"]
            assert "items:create" in data["permissions"]
        finally:
            from main import app
            app.dependency_overrides.clear()

    @patch("main.httpx.AsyncClient")
    def test_regular_user_me_returns_empty_permissions(self, mock_httpx_class, rbac_db, regular_user):
        """Regular user /me response includes empty permissions list."""
        client = self._make_auth_client(rbac_db, regular_user)
        try:
            resp = client.get("/users/me")
            assert resp.status_code == 200
            data = resp.json()
            assert data["role"] == "user"
            assert data["permissions"] == []
            assert data["role_display_name"] is None
        finally:
            from main import app
            app.dependency_overrides.clear()

    @patch("main.httpx.AsyncClient")
    def test_moderator_me_returns_items_permissions(self, mock_httpx_class, rbac_db, moderator_user):
        """Moderator /me response includes only items permissions."""
        client = self._make_auth_client(rbac_db, moderator_user)
        try:
            resp = client.get("/users/me")
            assert resp.status_code == 200
            data = resp.json()
            assert data["role"] == "moderator"
            assert data["role_display_name"] == "Куратор контента"
            perms = data["permissions"]
            assert len(perms) == 4
            assert all(p.startswith("items:") for p in perms)
        finally:
            from main import app
            app.dependency_overrides.clear()

    @patch("main.httpx.AsyncClient")
    def test_editor_me_returns_read_permissions(self, mock_httpx_class, rbac_db, editor_user):
        """Editor /me response includes only read permissions."""
        client = self._make_auth_client(rbac_db, editor_user)
        try:
            resp = client.get("/users/me")
            assert resp.status_code == 200
            data = resp.json()
            assert data["role"] == "editor"
            perms = data["permissions"]
            assert len(perms) == 2
            assert "items:read" in perms
            assert "users:read" in perms
        finally:
            from main import app
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 5. Test require_permission() and is_admin() / require_admin()
# ---------------------------------------------------------------------------

class TestRequirePermission:
    """Test that require_permission raises HTTPException 403 when permission is missing."""

    def test_user_with_permission_passes(self, rbac_db, moderator_user):
        """User with the required permission should not raise."""
        # Moderator has items:create — should not raise
        require_permission(rbac_db, moderator_user, "items:create")

    def test_user_without_permission_raises_403(self, rbac_db, regular_user):
        """User without the required permission should raise HTTPException 403."""
        with pytest.raises(HTTPException) as exc_info:
            require_permission(rbac_db, regular_user, "items:create")
        assert exc_info.value.status_code == 403

    def test_admin_has_any_permission(self, rbac_db, admin_user):
        """Admin should have any permission — require_permission should not raise."""
        require_permission(rbac_db, admin_user, "users:manage")
        require_permission(rbac_db, admin_user, "items:delete")

    def test_moderator_without_users_manage_raises(self, rbac_db, moderator_user):
        """Moderator should NOT have users:manage."""
        with pytest.raises(HTTPException) as exc_info:
            require_permission(rbac_db, moderator_user, "users:manage")
        assert exc_info.value.status_code == 403

    def test_editor_without_items_create_raises(self, rbac_db, editor_user):
        """Editor should NOT have items:create (only read)."""
        with pytest.raises(HTTPException) as exc_info:
            require_permission(rbac_db, editor_user, "items:create")
        assert exc_info.value.status_code == 403

    def test_error_message_is_russian(self, rbac_db, regular_user):
        """403 error detail should be in Russian."""
        with pytest.raises(HTTPException) as exc_info:
            require_permission(rbac_db, regular_user, "items:create")
        assert "прав" in exc_info.value.detail.lower()


class TestIsAdmin:
    """Test is_admin() helper function."""

    def test_admin_role_id_returns_true(self, rbac_db, admin_user):
        assert is_admin(rbac_db, admin_user) is True

    def test_moderator_returns_false(self, rbac_db, moderator_user):
        assert is_admin(rbac_db, moderator_user) is False

    def test_regular_user_returns_false(self, rbac_db, regular_user):
        assert is_admin(rbac_db, regular_user) is False

    def test_legacy_admin_string_returns_true(self, rbac_db):
        user = _make_user(rbac_db, id=20, username="legadmin2", email="legadmin2@test.com",
                          role_id=None, role_str="admin")
        assert is_admin(rbac_db, user) is True

    def test_legacy_user_string_returns_false(self, rbac_db):
        user = _make_user(rbac_db, id=21, username="leguser", email="leguser@test.com",
                          role_id=None, role_str="user")
        assert is_admin(rbac_db, user) is False


class TestRequireAdmin:
    """Test require_admin() raises 403 for non-admin users."""

    def test_admin_passes(self, rbac_db, admin_user):
        require_admin(rbac_db, admin_user)  # should not raise

    def test_moderator_raises_403(self, rbac_db, moderator_user):
        with pytest.raises(HTTPException) as exc_info:
            require_admin(rbac_db, moderator_user)
        assert exc_info.value.status_code == 403

    def test_regular_user_raises_403(self, rbac_db, regular_user):
        with pytest.raises(HTTPException) as exc_info:
            require_admin(rbac_db, regular_user)
        assert exc_info.value.status_code == 403

    def test_error_message_mentions_admin(self, rbac_db, regular_user):
        with pytest.raises(HTTPException) as exc_info:
            require_admin(rbac_db, regular_user)
        assert "администратор" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# 6. Security edge cases
# ---------------------------------------------------------------------------

class TestSecurityEdgeCases:
    """Edge cases and negative scenarios for RBAC system."""

    def test_user_with_nonexistent_role_id_falls_back(self, rbac_db):
        """User with role_id pointing to deleted role falls back to legacy string."""
        user = _make_user(rbac_db, id=30, username="orphan", email="orphan@test.com",
                          role_id=999, role_str="user")
        perms = get_effective_permissions(rbac_db, user)
        assert perms == []

    def test_user_with_no_role_at_all_gets_no_permissions(self, rbac_db):
        """User with no role_id and no role string defaults to 'user' (no perms)."""
        user = _make_user(rbac_db, id=31, username="norole", email="norole@test.com",
                          role_id=None, role_str=None)
        perms = get_effective_permissions(rbac_db, user)
        assert perms == []

    def test_permissions_are_sorted(self, rbac_db, moderator_user):
        """Effective permissions list should be sorted for consistency."""
        perms = get_effective_permissions(rbac_db, moderator_user)
        assert perms == sorted(perms)

    def test_unique_constraint_user_permission(self, rbac_db, regular_user):
        """user_permissions has unique constraint on (user_id, permission_id)."""
        from sqlalchemy.exc import IntegrityError

        perm = rbac_db.query(models.Permission).first()
        rbac_db.add(models.UserPermission(
            user_id=regular_user.id, permission_id=perm.id, granted=True
        ))
        rbac_db.commit()

        rbac_db.add(models.UserPermission(
            user_id=regular_user.id, permission_id=perm.id, granted=False
        ))
        with pytest.raises(IntegrityError):
            rbac_db.commit()
        rbac_db.rollback()

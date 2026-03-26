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
        import main as main_module
        from main import app
        from fastapi.testclient import TestClient

        def override_get_db():
            yield db

        def override_auth():
            return user

        app.dependency_overrides[get_db] = override_get_db
        # Use main.get_current_user (the original function object captured by
        # `from auth import *`) instead of importing from auth directly,
        # because test_jwt_secret.py reloads the auth module creating new
        # function objects that don't match Depends() keys in main.py.
        app.dependency_overrides[main_module.get_current_user] = override_auth
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


# ---------------------------------------------------------------------------
# 7. FEAT-078: Perks RBAC permissions (migration 0017)
# ---------------------------------------------------------------------------

PERKS_PERMISSIONS = [
    ("perks", "read"),
    ("perks", "create"),
    ("perks", "update"),
    ("perks", "delete"),
    ("perks", "grant"),
]

# Mirrors ROLE_ACTIONS from migration 0017
PERKS_ROLE_ACTIONS = {
    3: ["read", "create", "update", "grant"],   # Moderator
    2: ["read"],                                  # Editor
}


def _seed_perks_permissions(db):
    """Seed the 5 perks permissions and their role assignments (mirrors migration 0017)."""
    perm_objects = []
    for module, action in PERKS_PERMISSIONS:
        perm = models.Permission(module=module, action=action,
                                 description=f"Perks: {action}")
        db.add(perm)
        perm_objects.append(perm)
    db.flush()  # assigns IDs

    # Assign to roles
    for perm in perm_objects:
        for role_id, actions in PERKS_ROLE_ACTIONS.items():
            if perm.action in actions:
                db.add(models.RolePermission(role_id=role_id, permission_id=perm.id))
    db.commit()
    return perm_objects


@pytest.fixture()
def rbac_db_with_perks(rbac_db):
    """DB session with base RBAC seed data + perks permissions from migration 0017."""
    _seed_perks_permissions(rbac_db)
    return rbac_db


class TestPerksPermissions:
    """FEAT-078 Task #13: Verify perks RBAC permissions from migration 0017."""

    def test_perks_permissions_exist(self, rbac_db_with_perks):
        """All 5 perks permissions must exist in the DB after migration."""
        db = rbac_db_with_perks
        for module, action in PERKS_PERMISSIONS:
            perm = db.query(models.Permission).filter(
                models.Permission.module == module,
                models.Permission.action == action,
            ).first()
            assert perm is not None, f"Permission {module}:{action} not found in DB"

    def test_perks_permissions_count(self, rbac_db_with_perks):
        """Exactly 5 perks permissions should exist."""
        db = rbac_db_with_perks
        count = db.query(models.Permission).filter(
            models.Permission.module == "perks"
        ).count()
        assert count == 5

    def test_admin_has_all_perks_permissions(self, rbac_db_with_perks):
        """Admin (role_id=4) should have all 5 perks permissions via auto-permissions."""
        db = rbac_db_with_perks
        admin = _make_user(db, id=100, username="perkadmin", email="perkadmin@test.com",
                           role_id=4, role_str="admin")
        perms = get_effective_permissions(db, admin)
        for module, action in PERKS_PERMISSIONS:
            perm_str = f"{module}:{action}"
            assert perm_str in perms, f"Admin missing {perm_str}"
        # 8 base + 5 perks = 13 total
        assert len(perms) == 13

    def test_moderator_has_correct_perks_permissions(self, rbac_db_with_perks):
        """Moderator (role_id=3) should have perks:read, perks:create, perks:update, perks:grant."""
        db = rbac_db_with_perks
        mod = _make_user(db, id=101, username="perkmod", email="perkmod@test.com",
                         role_id=3, role_str="moderator")
        perms = get_effective_permissions(db, mod)
        assert "perks:read" in perms
        assert "perks:create" in perms
        assert "perks:update" in perms
        assert "perks:grant" in perms
        assert "perks:delete" not in perms
        # 4 base items:* + 4 perks = 8 total
        assert len(perms) == 8

    def test_editor_has_only_perks_read(self, rbac_db_with_perks):
        """Editor (role_id=2) should have only perks:read."""
        db = rbac_db_with_perks
        editor = _make_user(db, id=102, username="perkeditor", email="perkeditor@test.com",
                            role_id=2, role_str="editor")
        perms = get_effective_permissions(db, editor)
        assert "perks:read" in perms
        assert "perks:create" not in perms
        assert "perks:update" not in perms
        assert "perks:delete" not in perms
        assert "perks:grant" not in perms
        # 2 base *:read + 1 perks:read = 3 total
        assert len(perms) == 3

    def test_regular_user_has_no_perks_permissions(self, rbac_db_with_perks):
        """Regular user (role_id=1) should have no perks permissions."""
        db = rbac_db_with_perks
        user = _make_user(db, id=103, username="perkuser", email="perkuser@test.com",
                          role_id=1, role_str="user")
        perms = get_effective_permissions(db, user)
        assert not any(p.startswith("perks:") for p in perms)
        assert perms == []

    def test_require_permission_perks_admin(self, rbac_db_with_perks):
        """Admin can pass require_permission for any perks permission."""
        db = rbac_db_with_perks
        admin = _make_user(db, id=104, username="perkadmin2", email="perkadmin2@test.com",
                           role_id=4, role_str="admin")
        for module, action in PERKS_PERMISSIONS:
            require_permission(db, admin, f"{module}:{action}")

    def test_require_permission_perks_editor_blocked(self, rbac_db_with_perks):
        """Editor should be blocked from perks:create via require_permission."""
        db = rbac_db_with_perks
        editor = _make_user(db, id=105, username="perkeditor2", email="perkeditor2@test.com",
                            role_id=2, role_str="editor")
        with pytest.raises(HTTPException) as exc_info:
            require_permission(db, editor, "perks:create")
        assert exc_info.value.status_code == 403

    def test_require_permission_perks_moderator_blocked_delete(self, rbac_db_with_perks):
        """Moderator should be blocked from perks:delete via require_permission."""
        db = rbac_db_with_perks
        mod = _make_user(db, id=106, username="perkmod2", email="perkmod2@test.com",
                         role_id=3, role_str="moderator")
        with pytest.raises(HTTPException) as exc_info:
            require_permission(db, mod, "perks:delete")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 8. FEAT-080: Titles RBAC permissions (migration 0018)
# ---------------------------------------------------------------------------

TITLES_PERMISSIONS = [
    ("titles", "read"),
    ("titles", "create"),
    ("titles", "update"),
    ("titles", "delete"),
    ("titles", "grant"),
]

# Mirrors ROLE_ACTIONS from migration 0018
TITLES_ROLE_ACTIONS = {
    3: ["read", "create", "update", "grant"],  # Moderator
    2: ["read"],                                # Editor
}


def _seed_titles_permissions(db):
    """Seed the 5 titles permissions and their role assignments (mirrors migration 0018)."""
    perm_objects = []
    for module, action in TITLES_PERMISSIONS:
        perm = models.Permission(module=module, action=action,
                                 description=f"Titles: {action}")
        db.add(perm)
        perm_objects.append(perm)
    db.flush()  # assigns IDs

    # Assign to roles
    for perm in perm_objects:
        for role_id, actions in TITLES_ROLE_ACTIONS.items():
            if perm.action in actions:
                db.add(models.RolePermission(role_id=role_id, permission_id=perm.id))
    db.commit()
    return perm_objects


@pytest.fixture()
def rbac_db_with_titles(rbac_db):
    """DB session with base RBAC seed data + titles permissions from migration 0018."""
    _seed_titles_permissions(rbac_db)
    return rbac_db


class TestTitlesPermissions:
    """FEAT-080 Task #13: Verify titles RBAC permissions from migration 0018."""

    def test_titles_permissions_exist(self, rbac_db_with_titles):
        """All 5 titles permissions must exist in the DB after migration."""
        db = rbac_db_with_titles
        for module, action in TITLES_PERMISSIONS:
            perm = db.query(models.Permission).filter(
                models.Permission.module == module,
                models.Permission.action == action,
            ).first()
            assert perm is not None, f"Permission {module}:{action} not found in DB"

    def test_titles_permissions_count(self, rbac_db_with_titles):
        """Exactly 5 titles permissions should exist."""
        db = rbac_db_with_titles
        count = db.query(models.Permission).filter(
            models.Permission.module == "titles"
        ).count()
        assert count == 5

    def test_admin_has_all_titles_permissions(self, rbac_db_with_titles):
        """Admin (role_id=4) should have all 5 titles permissions via auto-permissions."""
        db = rbac_db_with_titles
        admin = _make_user(db, id=200, username="titleadmin", email="titleadmin@test.com",
                           role_id=4, role_str="admin")
        perms = get_effective_permissions(db, admin)
        for module, action in TITLES_PERMISSIONS:
            perm_str = f"{module}:{action}"
            assert perm_str in perms, f"Admin missing {perm_str}"
        # 8 base + 5 titles = 13 total
        assert len(perms) == 13

    def test_moderator_has_correct_titles_permissions(self, rbac_db_with_titles):
        """Moderator (role_id=3) should have titles:read, titles:create, titles:update, titles:grant."""
        db = rbac_db_with_titles
        mod = _make_user(db, id=201, username="titlemod", email="titlemod@test.com",
                         role_id=3, role_str="moderator")
        perms = get_effective_permissions(db, mod)
        assert "titles:read" in perms
        assert "titles:create" in perms
        assert "titles:update" in perms
        assert "titles:grant" in perms
        assert "titles:delete" not in perms
        # 4 base items:* + 4 titles = 8 total
        assert len(perms) == 8

    def test_editor_has_only_titles_read(self, rbac_db_with_titles):
        """Editor (role_id=2) should have only titles:read."""
        db = rbac_db_with_titles
        editor = _make_user(db, id=202, username="titleeditor", email="titleeditor@test.com",
                            role_id=2, role_str="editor")
        perms = get_effective_permissions(db, editor)
        assert "titles:read" in perms
        assert "titles:create" not in perms
        assert "titles:update" not in perms
        assert "titles:delete" not in perms
        assert "titles:grant" not in perms
        # 2 base *:read + 1 titles:read = 3 total
        assert len(perms) == 3

    def test_regular_user_has_no_titles_permissions(self, rbac_db_with_titles):
        """Regular user (role_id=1) should have no titles permissions."""
        db = rbac_db_with_titles
        user = _make_user(db, id=203, username="titleuser", email="titleuser@test.com",
                          role_id=1, role_str="user")
        perms = get_effective_permissions(db, user)
        assert not any(p.startswith("titles:") for p in perms)
        assert perms == []

    def test_require_permission_titles_admin(self, rbac_db_with_titles):
        """Admin can pass require_permission for any titles permission."""
        db = rbac_db_with_titles
        admin = _make_user(db, id=204, username="titleadmin2", email="titleadmin2@test.com",
                           role_id=4, role_str="admin")
        for module, action in TITLES_PERMISSIONS:
            require_permission(db, admin, f"{module}:{action}")

    def test_require_permission_titles_editor_blocked(self, rbac_db_with_titles):
        """Editor should be blocked from titles:create via require_permission."""
        db = rbac_db_with_titles
        editor = _make_user(db, id=205, username="titleeditor2", email="titleeditor2@test.com",
                            role_id=2, role_str="editor")
        with pytest.raises(HTTPException) as exc_info:
            require_permission(db, editor, "titles:create")
        assert exc_info.value.status_code == 403

    def test_require_permission_titles_moderator_blocked_delete(self, rbac_db_with_titles):
        """Moderator should be blocked from titles:delete via require_permission."""
        db = rbac_db_with_titles
        mod = _make_user(db, id=206, username="titlemod2", email="titlemod2@test.com",
                         role_id=3, role_str="moderator")
        with pytest.raises(HTTPException) as exc_info:
            require_permission(db, mod, "titles:delete")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 9. FEAT-081: Professions RBAC permissions (migration 0019)
# ---------------------------------------------------------------------------

PROFESSIONS_PERMISSIONS = [
    ("professions", "read"),
    ("professions", "create"),
    ("professions", "update"),
    ("professions", "delete"),
    ("professions", "manage"),
]

# Mirrors ROLE_ACTIONS from migration 0019
PROFESSIONS_ROLE_ACTIONS = {
    3: ["read", "create", "update", "manage"],  # Moderator
    2: ["read"],                                  # Editor
}


def _seed_professions_permissions(db):
    """Seed the 5 professions permissions and their role assignments (mirrors migration 0019)."""
    perm_objects = []
    for module, action in PROFESSIONS_PERMISSIONS:
        perm = models.Permission(module=module, action=action,
                                 description=f"Professions: {action}")
        db.add(perm)
        perm_objects.append(perm)
    db.flush()  # assigns IDs

    # Assign to roles
    for perm in perm_objects:
        for role_id, actions in PROFESSIONS_ROLE_ACTIONS.items():
            if perm.action in actions:
                db.add(models.RolePermission(role_id=role_id, permission_id=perm.id))
    db.commit()
    return perm_objects


@pytest.fixture()
def rbac_db_with_professions(rbac_db):
    """DB session with base RBAC seed data + professions permissions from migration 0019."""
    _seed_professions_permissions(rbac_db)
    return rbac_db


class TestProfessionsPermissions:
    """FEAT-081 Task #9: Verify professions RBAC permissions from migration 0019."""

    def test_professions_permissions_exist(self, rbac_db_with_professions):
        """All 5 professions permissions must exist in the DB after migration."""
        db = rbac_db_with_professions
        for module, action in PROFESSIONS_PERMISSIONS:
            perm = db.query(models.Permission).filter(
                models.Permission.module == module,
                models.Permission.action == action,
            ).first()
            assert perm is not None, f"Permission {module}:{action} not found in DB"

    def test_professions_permissions_count(self, rbac_db_with_professions):
        """Exactly 5 professions permissions should exist."""
        db = rbac_db_with_professions
        count = db.query(models.Permission).filter(
            models.Permission.module == "professions"
        ).count()
        assert count == 5

    def test_admin_has_all_professions_permissions(self, rbac_db_with_professions):
        """Admin (role_id=4) should have all 5 professions permissions via auto-permissions."""
        db = rbac_db_with_professions
        admin = _make_user(db, id=300, username="profadmin", email="profadmin@test.com",
                           role_id=4, role_str="admin")
        perms = get_effective_permissions(db, admin)
        for module, action in PROFESSIONS_PERMISSIONS:
            perm_str = f"{module}:{action}"
            assert perm_str in perms, f"Admin missing {perm_str}"
        # 8 base + 5 professions = 13 total
        assert len(perms) == 13

    def test_moderator_has_correct_professions_permissions(self, rbac_db_with_professions):
        """Moderator (role_id=3) should have professions:read, create, update, manage."""
        db = rbac_db_with_professions
        mod = _make_user(db, id=301, username="profmod", email="profmod@test.com",
                         role_id=3, role_str="moderator")
        perms = get_effective_permissions(db, mod)
        assert "professions:read" in perms
        assert "professions:create" in perms
        assert "professions:update" in perms
        assert "professions:manage" in perms
        assert "professions:delete" not in perms
        # 4 base items:* + 4 professions = 8 total
        assert len(perms) == 8

    def test_editor_has_only_professions_read(self, rbac_db_with_professions):
        """Editor (role_id=2) should have only professions:read."""
        db = rbac_db_with_professions
        editor = _make_user(db, id=302, username="profeditor", email="profeditor@test.com",
                            role_id=2, role_str="editor")
        perms = get_effective_permissions(db, editor)
        assert "professions:read" in perms
        assert "professions:create" not in perms
        assert "professions:update" not in perms
        assert "professions:delete" not in perms
        assert "professions:manage" not in perms
        # 2 base *:read + 1 professions:read = 3 total
        assert len(perms) == 3

    def test_regular_user_has_no_professions_permissions(self, rbac_db_with_professions):
        """Regular user (role_id=1) should have no professions permissions."""
        db = rbac_db_with_professions
        user = _make_user(db, id=303, username="profuser", email="profuser@test.com",
                          role_id=1, role_str="user")
        perms = get_effective_permissions(db, user)
        assert not any(p.startswith("professions:") for p in perms)
        assert perms == []

    def test_require_permission_professions_admin(self, rbac_db_with_professions):
        """Admin can pass require_permission for any professions permission."""
        db = rbac_db_with_professions
        admin = _make_user(db, id=304, username="profadmin2", email="profadmin2@test.com",
                           role_id=4, role_str="admin")
        for module, action in PROFESSIONS_PERMISSIONS:
            require_permission(db, admin, f"{module}:{action}")

    def test_require_permission_professions_editor_blocked(self, rbac_db_with_professions):
        """Editor should be blocked from professions:create via require_permission."""
        db = rbac_db_with_professions
        editor = _make_user(db, id=305, username="profeditor2", email="profeditor2@test.com",
                            role_id=2, role_str="editor")
        with pytest.raises(HTTPException) as exc_info:
            require_permission(db, editor, "professions:create")
        assert exc_info.value.status_code == 403

    def test_require_permission_professions_moderator_blocked_delete(self, rbac_db_with_professions):
        """Moderator should be blocked from professions:delete via require_permission."""
        db = rbac_db_with_professions
        mod = _make_user(db, id=306, username="profmod2", email="profmod2@test.com",
                         role_id=3, role_str="moderator")
        with pytest.raises(HTTPException) as exc_info:
            require_permission(db, mod, "professions:delete")
        assert exc_info.value.status_code == 403

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


# ---------------------------------------------------------------------------
# 10. FEAT-158: Moderation RBAC permissions (migration 0027)
# ---------------------------------------------------------------------------

MODERATION_PERMISSIONS = [
    ("moderation", "read"),
    ("moderation", "review"),
]

# Mirrors ROLE_ACTIONS from migration 0027.
# Admin (4) is intentionally absent — it receives every row of `permissions`
# automatically. Editor (2) gets nothing: editors have no moderation access.
MODERATION_ROLE_ACTIONS = {
    3: ["read", "review"],   # Moderator — must keep the access get_admin_user gave it
}


def _seed_moderation_permissions(db):
    """Seed the 2 moderation permissions and their role grants (mirrors migration 0027)."""
    perm_objects = []
    for module, action in MODERATION_PERMISSIONS:
        perm = models.Permission(module=module, action=action,
                                 description=f"Moderation: {action}")
        db.add(perm)
        perm_objects.append(perm)
    db.flush()  # assigns IDs

    for perm in perm_objects:
        for role_id, actions in MODERATION_ROLE_ACTIONS.items():
            if perm.action in actions:
                db.add(models.RolePermission(role_id=role_id, permission_id=perm.id))
    db.commit()
    return perm_objects


@pytest.fixture()
def rbac_db_with_moderation(rbac_db):
    """DB session with base RBAC seed data + moderation permissions from migration 0027."""
    _seed_moderation_permissions(rbac_db)
    return rbac_db


class TestModerationPermissions:
    """FEAT-158 Task #7: Verify moderation RBAC permissions from migration 0027."""

    def test_moderation_permissions_exist(self, rbac_db_with_moderation):
        """Both moderation permissions must exist in the DB after migration."""
        db = rbac_db_with_moderation
        for module, action in MODERATION_PERMISSIONS:
            perm = db.query(models.Permission).filter(
                models.Permission.module == module,
                models.Permission.action == action,
            ).first()
            assert perm is not None, f"Permission {module}:{action} not found in DB"

    def test_moderation_permissions_count(self, rbac_db_with_moderation):
        """Exactly 2 moderation permissions should exist."""
        db = rbac_db_with_moderation
        count = db.query(models.Permission).filter(
            models.Permission.module == "moderation"
        ).count()
        assert count == 2

    def test_admin_has_all_moderation_permissions(self, rbac_db_with_moderation):
        """Admin (role_id=4) gets both moderation permissions via auto-permissions.

        This is the mechanism FEAT-158 tripped over: admin permissions come from a
        SELECT over the `permissions` table, so an unregistered string is a
        permission the admin does NOT have.
        """
        db = rbac_db_with_moderation
        admin = _make_user(db, id=400, username="modadmin", email="modadmin@test.com",
                           role_id=4, role_str="admin")
        perms = get_effective_permissions(db, admin)
        for module, action in MODERATION_PERMISSIONS:
            perm_str = f"{module}:{action}"
            assert perm_str in perms, f"Admin missing {perm_str}"
        # 8 base + 2 moderation = 10 total
        assert len(perms) == 10

    def test_moderator_keeps_full_moderation_access(self, rbac_db_with_moderation):
        """Moderator (role_id=3) must keep BOTH actions.

        The four admin endpoints previously used `get_admin_user`, which admitted
        admin *and* moderator. Moving them onto `require_permission` must not
        narrow that — a moderator without `moderation:review` would silently lose
        the ability to act on the queue.
        """
        db = rbac_db_with_moderation
        mod = _make_user(db, id=401, username="modmod", email="modmod@test.com",
                         role_id=3, role_str="moderator")
        perms = get_effective_permissions(db, mod)
        assert "moderation:read" in perms
        assert "moderation:review" in perms
        # 4 base items:* + 2 moderation = 6 total
        assert len(perms) == 6

    def test_editor_has_no_moderation_permissions(self, rbac_db_with_moderation):
        """Editor (role_id=2) gets nothing — editors have no moderation access today."""
        db = rbac_db_with_moderation
        editor = _make_user(db, id=402, username="modeditor", email="modeditor@test.com",
                            role_id=2, role_str="editor")
        perms = get_effective_permissions(db, editor)
        assert not any(p.startswith("moderation:") for p in perms)
        # 2 base *:read, unchanged
        assert len(perms) == 2

    def test_regular_user_has_no_moderation_permissions(self, rbac_db_with_moderation):
        """Regular user (role_id=1) must not reach the moderation queue."""
        db = rbac_db_with_moderation
        user = _make_user(db, id=403, username="moduser", email="moduser@test.com",
                          role_id=1, role_str="user")
        perms = get_effective_permissions(db, user)
        assert not any(p.startswith("moderation:") for p in perms)
        assert perms == []

    def test_require_permission_moderation_admin(self, rbac_db_with_moderation):
        """Admin passes require_permission for both moderation permissions."""
        db = rbac_db_with_moderation
        admin = _make_user(db, id=404, username="modadmin2", email="modadmin2@test.com",
                           role_id=4, role_str="admin")
        for module, action in MODERATION_PERMISSIONS:
            require_permission(db, admin, f"{module}:{action}")

    def test_require_permission_moderation_moderator(self, rbac_db_with_moderation):
        """Moderator passes require_permission for both moderation permissions."""
        db = rbac_db_with_moderation
        mod = _make_user(db, id=405, username="modmod2", email="modmod2@test.com",
                         role_id=3, role_str="moderator")
        for module, action in MODERATION_PERMISSIONS:
            require_permission(db, mod, f"{module}:{action}")

    def test_require_permission_moderation_editor_blocked(self, rbac_db_with_moderation):
        """Editor is blocked from the moderation queue."""
        db = rbac_db_with_moderation
        editor = _make_user(db, id=406, username="modeditor2", email="modeditor2@test.com",
                            role_id=2, role_str="editor")
        with pytest.raises(HTTPException) as exc_info:
            require_permission(db, editor, "moderation:read")
        assert exc_info.value.status_code == 403

    def test_require_permission_moderation_user_blocked(self, rbac_db_with_moderation):
        """A regular player is blocked from reviewing moderation rows."""
        db = rbac_db_with_moderation
        user = _make_user(db, id=407, username="moduser2", email="moduser2@test.com",
                          role_id=1, role_str="user")
        with pytest.raises(HTTPException) as exc_info:
            require_permission(db, user, "moderation:review")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 11. FEAT-160: posts:history permission (migration 0029) — the empty grant
# ---------------------------------------------------------------------------
#
# Registered with **zero role_permissions rows on purpose**. That emptiness is
# the access rule: admins receive every row of `permissions` automatically
# (crud.py:31-33), everyone else only their explicit grants. So the permission
# is "admins, plus anyone named in user_permissions" — see 3.9 of FEAT-160 and
# the dedicated suite in test_posts_history_permission.py.
#
# Note on section 3 above (TestAdminAutoPermissions): it proves admin picks up
# *any* newly inserted permission row, but it works from this file's synthetic
# seed and never reads the migration tree — so it does not, by itself, cover
# `posts:history`. That is why the row is seeded here explicitly, the same way
# every other per-module suite in this file does it.

POSTS_HISTORY = "posts:history"


def _seed_posts_history_permission(db):
    """Seed posts:history exactly as migration 0029 does — and grant it to NO role."""
    perm = models.Permission(
        module="posts",
        action="history",
        description="Просмотр истории правок постов (админ)",
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return perm


@pytest.fixture()
def rbac_db_with_posts_history(rbac_db):
    """Base RBAC seed + the posts:history row from migration 0029."""
    _seed_posts_history_permission(rbac_db)
    return rbac_db


class TestPostsHistoryPermission:
    """FEAT-160 Task #5: posts:history is admin-only but delegable."""

    def test_posts_history_permission_exists(self, rbac_db_with_posts_history):
        db = rbac_db_with_posts_history
        perm = db.query(models.Permission).filter(
            models.Permission.module == "posts",
            models.Permission.action == "history",
        ).first()
        assert perm is not None

    def test_exactly_one_posts_permission(self, rbac_db_with_posts_history):
        """The `posts` module has a single action — nothing else belongs to it."""
        db = rbac_db_with_posts_history
        assert db.query(models.Permission).filter(
            models.Permission.module == "posts").count() == 1

    def test_no_role_holds_posts_history(self, rbac_db_with_posts_history):
        """Zero role_permissions rows — the mechanism, asserted as emptiness."""
        db = rbac_db_with_posts_history
        perm = db.query(models.Permission).filter(
            models.Permission.module == "posts").one()
        assert db.query(models.RolePermission).filter(
            models.RolePermission.permission_id == perm.id).count() == 0

    def test_admin_picks_up_the_new_permission_automatically(
            self, rbac_db_with_posts_history):
        """The "admin has every permission" rule, checked on this actual row."""
        db = rbac_db_with_posts_history
        admin = _make_user(db, id=500, username="phadmin", email="phadmin@test.com",
                           role_id=4, role_str="admin")
        perms = get_effective_permissions(db, admin)
        assert POSTS_HISTORY in perms
        # 8 base + 1 new = 9
        assert len(perms) == 9

    def test_moderator_does_not_get_posts_history(self, rbac_db_with_posts_history):
        """The case the permission exists for: moderators must never hold it."""
        db = rbac_db_with_posts_history
        mod = _make_user(db, id=501, username="phmod", email="phmod@test.com",
                         role_id=3, role_str="moderator")
        perms = get_effective_permissions(db, mod)
        assert POSTS_HISTORY not in perms
        assert len(perms) == 4  # unchanged items:*

    def test_editor_does_not_get_posts_history(self, rbac_db_with_posts_history):
        db = rbac_db_with_posts_history
        editor = _make_user(db, id=502, username="pheditor", email="pheditor@test.com",
                            role_id=2, role_str="editor")
        assert POSTS_HISTORY not in get_effective_permissions(db, editor)

    def test_regular_user_does_not_get_posts_history(self, rbac_db_with_posts_history):
        db = rbac_db_with_posts_history
        user = _make_user(db, id=503, username="phuser", email="phuser@test.com",
                          role_id=1, role_str="user")
        assert get_effective_permissions(db, user) == []

    def test_delegated_grant_works_and_can_be_revoked(self, rbac_db_with_posts_history):
        """Per-person delegation through user_permissions — no deploy needed."""
        db = rbac_db_with_posts_history
        mod = _make_user(db, id=504, username="phmod2", email="phmod2@test.com",
                         role_id=3, role_str="moderator")
        perm = db.query(models.Permission).filter(
            models.Permission.module == "posts").one()
        override = models.UserPermission(user_id=mod.id, permission_id=perm.id,
                                         granted=True)
        db.add(override)
        db.commit()
        assert POSTS_HISTORY in get_effective_permissions(db, mod)
        require_permission(db, mod, POSTS_HISTORY)  # must not raise

        override.granted = False
        db.commit()
        assert POSTS_HISTORY not in get_effective_permissions(db, mod)

    def test_require_permission_matrix(self, rbac_db_with_posts_history):
        """Admin passes; moderator, editor and player each get 403."""
        db = rbac_db_with_posts_history
        admin = _make_user(db, id=505, username="phadmin2", email="phadmin2@test.com",
                           role_id=4, role_str="admin")
        require_permission(db, admin, POSTS_HISTORY)

        for uid, name, role_id, role_str in (
            (506, "phmod3", 3, "moderator"),
            (507, "pheditor3", 2, "editor"),
            (508, "phuser3", 1, "user"),
        ):
            user = _make_user(db, id=uid, username=name, email=f"{name}@test.com",
                              role_id=role_id, role_str=role_str)
            with pytest.raises(HTTPException) as exc_info:
                require_permission(db, user, POSTS_HISTORY)
            assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 12. FEAT-181: economy permissions (migration 0032)
# ---------------------------------------------------------------------------
#
# Seeded explicitly: TestAdminAutoPermissions works on this file's synthetic
# seed and never reads the migration tree, so a new `permissions` row is not
# covered by it automatically.

ECONOMY_PERMISSIONS = [
    ("economy", "read"),
    ("economy", "emit"),
    ("economy", "adjust"),
    ("economy", "settings"),
]

# Mirrors ROLE_ACTIONS from migration 0032. Admin (4) is absent on purpose —
# it receives every row of `permissions`. Editor (2) gets nothing.
ECONOMY_ROLE_ACTIONS = {
    3: ["read"],  # Moderator — view-only economy access
}


def _seed_economy_permissions(db):
    """Seed the 4 economy permissions and their role grants (mirrors 0032)."""
    perm_objects = []
    for module, action in ECONOMY_PERMISSIONS:
        perm = models.Permission(module=module, action=action,
                                 description=f"Economy: {action}")
        db.add(perm)
        perm_objects.append(perm)
    db.flush()

    for perm in perm_objects:
        for role_id, actions in ECONOMY_ROLE_ACTIONS.items():
            if perm.action in actions:
                db.add(models.RolePermission(role_id=role_id, permission_id=perm.id))
    db.commit()
    return perm_objects


@pytest.fixture()
def rbac_db_with_economy(rbac_db):
    """Base RBAC seed + economy permissions from migration 0032."""
    _seed_economy_permissions(rbac_db)
    return rbac_db


class TestEconomyPermissions:
    """FEAT-181 Q4: economy:read/emit/adjust/settings."""

    def test_seed_mirrors_the_migration(self):
        """The mirror above must match migration 0032 — otherwise this suite
        tests a different permission set than production gets."""
        import importlib.util
        from pathlib import Path
        path = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
                / "0032_add_economy_permissions.py")
        spec = importlib.util.spec_from_file_location("mig_0032", path)
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        assert [(m, a) for m, a, _ in mig.PERMISSIONS] == ECONOMY_PERMISSIONS
        assert mig.ROLE_ACTIONS == ECONOMY_ROLE_ACTIONS
        assert mig.revision == "0032" and mig.down_revision == "0031"

    def test_exactly_four_economy_permissions(self, rbac_db_with_economy):
        db = rbac_db_with_economy
        assert db.query(models.Permission).filter(
            models.Permission.module == "economy").count() == 4

    def test_admin_gets_all_four(self, rbac_db_with_economy):
        db = rbac_db_with_economy
        admin = _make_user(db, id=600, username="ecadmin", email="ecadmin@test.com",
                           role_id=4, role_str="admin")
        perms = get_effective_permissions(db, admin)
        for module, action in ECONOMY_PERMISSIONS:
            assert f"{module}:{action}" in perms
        # 8 base + 4 economy = 12
        assert len(perms) == 12

    def test_moderator_gets_only_read(self, rbac_db_with_economy):
        db = rbac_db_with_economy
        mod = _make_user(db, id=601, username="ecmod", email="ecmod@test.com",
                         role_id=3, role_str="moderator")
        perms = get_effective_permissions(db, mod)
        assert [p for p in perms if p.startswith("economy:")] == ["economy:read"]
        # 4 base items:* + economy:read = 5
        assert len(perms) == 5

    def test_editor_gets_none(self, rbac_db_with_economy):
        db = rbac_db_with_economy
        editor = _make_user(db, id=602, username="eceditor", email="eceditor@test.com",
                            role_id=2, role_str="editor")
        perms = get_effective_permissions(db, editor)
        assert not any(p.startswith("economy:") for p in perms)
        assert len(perms) == 2  # base *:read, unchanged

    def test_regular_user_gets_none(self, rbac_db_with_economy):
        db = rbac_db_with_economy
        user = _make_user(db, id=603, username="ecuser", email="ecuser@test.com",
                          role_id=1, role_str="user")
        assert get_effective_permissions(db, user) == []

    def test_require_permission_matrix(self, rbac_db_with_economy):
        """Admin passes all four; moderator only read; editor/user nothing."""
        db = rbac_db_with_economy
        admin = _make_user(db, id=604, username="ecadmin2", email="ecadmin2@test.com",
                           role_id=4, role_str="admin")
        mod = _make_user(db, id=605, username="ecmod2", email="ecmod2@test.com",
                         role_id=3, role_str="moderator")
        editor = _make_user(db, id=606, username="eceditor2", email="eceditor2@test.com",
                            role_id=2, role_str="editor")
        user = _make_user(db, id=607, username="ecuser2", email="ecuser2@test.com",
                          role_id=1, role_str="user")

        for module, action in ECONOMY_PERMISSIONS:
            perm = f"{module}:{action}"
            require_permission(db, admin, perm)
            if action == "read":
                require_permission(db, mod, perm)
            else:
                with pytest.raises(HTTPException) as exc_info:
                    require_permission(db, mod, perm)
                assert exc_info.value.status_code == 403
            for blocked in (editor, user):
                with pytest.raises(HTTPException) as exc_info:
                    require_permission(db, blocked, perm)
                assert exc_info.value.status_code == 403

    def test_delegated_adjust_to_moderator(self, rbac_db_with_economy):
        """economy:adjust can be granted per person via user_permissions."""
        db = rbac_db_with_economy
        mod = _make_user(db, id=608, username="ecmod3", email="ecmod3@test.com",
                         role_id=3, role_str="moderator")
        perm = db.query(models.Permission).filter(
            models.Permission.module == "economy",
            models.Permission.action == "adjust",
        ).one()
        db.add(models.UserPermission(user_id=mod.id, permission_id=perm.id, granted=True))
        db.commit()
        require_permission(db, mod, "economy:adjust")  # must not raise


# ---------------------------------------------------------------------------
# 13. FEAT-197: reputation permissions (migration 0033)
# ---------------------------------------------------------------------------
#
# Seeded explicitly (CLAUDE.md §10.13): TestAdminAutoPermissions works on this
# file's synthetic seed and never reads the migration tree, so the three new
# `permissions` rows are not covered by it automatically.

REPUTATION_PERMISSIONS = [
    ("reputation", "read"),
    ("reputation", "manage"),
    ("reputation", "settings"),
]

# Mirrors ROLE_ACTIONS from migration 0033. Admin (4) is absent on purpose —
# it receives every row of `permissions`. Editor (2) gets nothing;
# reputation:settings is admin-only (FEAT-197 §3.14 A3).
REPUTATION_ROLE_ACTIONS = {
    3: ["read", "manage"],  # Moderator — view + per-character adjust with a reason
}


def _seed_reputation_permissions(db):
    """Seed the 3 reputation permissions and their role grants (mirrors 0033)."""
    perm_objects = []
    for module, action in REPUTATION_PERMISSIONS:
        perm = models.Permission(module=module, action=action,
                                 description=f"Reputation: {action}")
        db.add(perm)
        perm_objects.append(perm)
    db.flush()

    for perm in perm_objects:
        for role_id, actions in REPUTATION_ROLE_ACTIONS.items():
            if perm.action in actions:
                db.add(models.RolePermission(role_id=role_id, permission_id=perm.id))
    db.commit()
    return perm_objects


@pytest.fixture()
def rbac_db_with_reputation(rbac_db):
    """Base RBAC seed + reputation permissions from migration 0033."""
    _seed_reputation_permissions(rbac_db)
    return rbac_db


class TestReputationPermissions:
    """FEAT-197: reputation:read/manage/settings."""

    def test_seed_mirrors_the_migration(self):
        """The mirror above must match migration 0033 — otherwise this suite
        tests a different permission set than production gets."""
        import importlib.util
        from pathlib import Path
        path = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
                / "0033_reputation_permissions.py")
        spec = importlib.util.spec_from_file_location("mig_0033", path)
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        assert [(m, a) for m, a, _ in mig.PERMISSIONS] == REPUTATION_PERMISSIONS
        assert mig.ROLE_ACTIONS == REPUTATION_ROLE_ACTIONS
        assert mig.revision == "0033" and mig.down_revision == "0032"

    def test_exactly_three_reputation_permissions(self, rbac_db_with_reputation):
        db = rbac_db_with_reputation
        assert db.query(models.Permission).filter(
            models.Permission.module == "reputation").count() == 3

    def test_admin_gets_all_three(self, rbac_db_with_reputation):
        db = rbac_db_with_reputation
        admin = _make_user(db, id=700, username="rpadmin", email="rpadmin@test.com",
                           role_id=4, role_str="admin")
        perms = get_effective_permissions(db, admin)
        for module, action in REPUTATION_PERMISSIONS:
            assert f"{module}:{action}" in perms
        # 8 base + 3 reputation = 11
        assert len(perms) == 11

    def test_moderator_gets_exactly_read_and_manage(self, rbac_db_with_reputation):
        db = rbac_db_with_reputation
        mod = _make_user(db, id=701, username="rpmod", email="rpmod@test.com",
                         role_id=3, role_str="moderator")
        perms = get_effective_permissions(db, mod)
        assert sorted(p for p in perms if p.startswith("reputation:")) == \
            ["reputation:manage", "reputation:read"]
        assert "reputation:settings" not in perms
        # 4 base items:* + reputation:read + reputation:manage = 6
        assert len(perms) == 6

    def test_editor_gets_none(self, rbac_db_with_reputation):
        db = rbac_db_with_reputation
        editor = _make_user(db, id=702, username="rpeditor", email="rpeditor@test.com",
                            role_id=2, role_str="editor")
        perms = get_effective_permissions(db, editor)
        assert not any(p.startswith("reputation:") for p in perms)
        assert len(perms) == 2  # base *:read, unchanged

    def test_regular_user_gets_none(self, rbac_db_with_reputation):
        db = rbac_db_with_reputation
        user = _make_user(db, id=703, username="rpuser", email="rpuser@test.com",
                          role_id=1, role_str="user")
        assert get_effective_permissions(db, user) == []

    def test_require_permission_matrix(self, rbac_db_with_reputation):
        """Admin passes all three; moderator read+manage; editor/user nothing."""
        db = rbac_db_with_reputation
        admin = _make_user(db, id=704, username="rpadmin2", email="rpadmin2@test.com",
                           role_id=4, role_str="admin")
        mod = _make_user(db, id=705, username="rpmod2", email="rpmod2@test.com",
                         role_id=3, role_str="moderator")
        editor = _make_user(db, id=706, username="rpeditor2", email="rpeditor2@test.com",
                            role_id=2, role_str="editor")
        user = _make_user(db, id=707, username="rpuser2", email="rpuser2@test.com",
                          role_id=1, role_str="user")

        for module, action in REPUTATION_PERMISSIONS:
            perm = f"{module}:{action}"
            require_permission(db, admin, perm)
            if action in ("read", "manage"):
                require_permission(db, mod, perm)
            else:
                with pytest.raises(HTTPException) as exc_info:
                    require_permission(db, mod, perm)
                assert exc_info.value.status_code == 403
            for blocked in (editor, user):
                with pytest.raises(HTTPException) as exc_info:
                    require_permission(db, blocked, perm)
                assert exc_info.value.status_code == 403

    def test_settings_can_be_delegated_and_revoked(self, rbac_db_with_reputation):
        """reputation:settings can be granted per person via user_permissions."""
        db = rbac_db_with_reputation
        mod = _make_user(db, id=708, username="rpmod3", email="rpmod3@test.com",
                         role_id=3, role_str="moderator")
        perm = db.query(models.Permission).filter(
            models.Permission.module == "reputation",
            models.Permission.action == "settings",
        ).one()
        override = models.UserPermission(user_id=mod.id, permission_id=perm.id, granted=True)
        db.add(override)
        db.commit()
        require_permission(db, mod, "reputation:settings")  # must not raise
        override.granted = False
        db.commit()
        assert "reputation:settings" not in get_effective_permissions(db, mod)

    def test_reputation_and_economy_together(self, rbac_db_with_reputation):
        """Both module seeds at once: the counts grow by exactly the module sizes."""
        db = rbac_db_with_reputation
        _seed_economy_permissions(db)
        admin = _make_user(db, id=709, username="rpadmin3", email="rpadmin3@test.com",
                           role_id=4, role_str="admin")
        assert len(get_effective_permissions(db, admin)) == 15  # 8 base + 4 economy + 3 reputation
        mod = _make_user(db, id=710, username="rpmod4", email="rpmod4@test.com",
                         role_id=3, role_str="moderator")
        # 4 base items:* + economy:read + reputation:read + reputation:manage = 7
        assert len(get_effective_permissions(db, mod)) == 7


# ---------------------------------------------------------------------------
# 14. FEAT-205: factions permissions (migration 0034)
# ---------------------------------------------------------------------------
#
# Seeded explicitly (CLAUDE.md §10.13): TestAdminAutoPermissions works on this
# file's synthetic seed and never reads the migration tree, so the five new
# `permissions` rows are not covered by it automatically.

FACTION_PERMISSIONS = [
    ("factions", "read"),
    ("factions", "edit"),
    ("factions", "delete"),
    ("factions", "manage"),
    ("factions", "settings"),
]

# Mirrors ROLE_ACTIONS from migration 0034. Admin (4) is absent on purpose —
# it receives every row of `permissions`. Editor (2) gets nothing;
# factions:delete and factions:settings are admin-only (FEAT-205 §3.10).
FACTION_ROLE_ACTIONS = {
    3: ["read", "edit", "manage"],  # Moderator
}


def _seed_faction_permissions(db):
    """Seed the 5 factions permissions and their role grants (mirrors 0034)."""
    perm_objects = []
    for module, action in FACTION_PERMISSIONS:
        perm = models.Permission(module=module, action=action,
                                 description=f"Factions: {action}")
        db.add(perm)
        perm_objects.append(perm)
    db.flush()

    for perm in perm_objects:
        for role_id, actions in FACTION_ROLE_ACTIONS.items():
            if perm.action in actions:
                db.add(models.RolePermission(role_id=role_id, permission_id=perm.id))
    db.commit()
    return perm_objects


@pytest.fixture()
def rbac_db_with_factions(rbac_db):
    """Base RBAC seed + factions permissions from migration 0034."""
    _seed_faction_permissions(rbac_db)
    return rbac_db


class TestFactionPermissions:
    """FEAT-205: factions:read/edit/delete/manage/settings."""

    def test_seed_mirrors_the_migration(self):
        """The mirror above must match migration 0034 — otherwise this suite
        tests a different permission set than production gets."""
        import importlib.util
        from pathlib import Path
        path = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
                / "0034_faction_permissions.py")
        spec = importlib.util.spec_from_file_location("mig_0034", path)
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        assert [(m, a) for m, a, _ in mig.PERMISSIONS] == FACTION_PERMISSIONS
        assert mig.ROLE_ACTIONS == FACTION_ROLE_ACTIONS
        assert mig.revision == "0034" and mig.down_revision == "0033"
        assert len(mig.revision) <= 32  # alembic_version column limit

    def test_exactly_five_faction_permissions(self, rbac_db_with_factions):
        db = rbac_db_with_factions
        assert db.query(models.Permission).filter(
            models.Permission.module == "factions").count() == 5

    def test_admin_gets_all_five(self, rbac_db_with_factions):
        db = rbac_db_with_factions
        admin = _make_user(db, id=800, username="fcadmin", email="fcadmin@test.com",
                           role_id=4, role_str="admin")
        perms = get_effective_permissions(db, admin)
        for module, action in FACTION_PERMISSIONS:
            assert f"{module}:{action}" in perms
        # 8 base + 5 factions = 13
        assert len(perms) == 13

    def test_moderator_gets_exactly_read_edit_manage(self, rbac_db_with_factions):
        db = rbac_db_with_factions
        mod = _make_user(db, id=801, username="fcmod", email="fcmod@test.com",
                         role_id=3, role_str="moderator")
        perms = get_effective_permissions(db, mod)
        assert sorted(p for p in perms if p.startswith("factions:")) == \
            ["factions:edit", "factions:manage", "factions:read"]
        assert "factions:delete" not in perms
        assert "factions:settings" not in perms
        # 4 base items:* + 3 factions = 7
        assert len(perms) == 7

    def test_editor_gets_none(self, rbac_db_with_factions):
        db = rbac_db_with_factions
        editor = _make_user(db, id=802, username="fceditor", email="fceditor@test.com",
                            role_id=2, role_str="editor")
        perms = get_effective_permissions(db, editor)
        assert not any(p.startswith("factions:") for p in perms)
        assert len(perms) == 2  # base *:read, unchanged

    def test_regular_user_gets_none(self, rbac_db_with_factions):
        db = rbac_db_with_factions
        user = _make_user(db, id=803, username="fcuser", email="fcuser@test.com",
                          role_id=1, role_str="user")
        assert get_effective_permissions(db, user) == []

    def test_require_permission_matrix(self, rbac_db_with_factions):
        """Admin passes all five; moderator read/edit/manage; editor/user nothing."""
        db = rbac_db_with_factions
        admin = _make_user(db, id=804, username="fcadmin2", email="fcadmin2@test.com",
                           role_id=4, role_str="admin")
        mod = _make_user(db, id=805, username="fcmod2", email="fcmod2@test.com",
                         role_id=3, role_str="moderator")
        editor = _make_user(db, id=806, username="fceditor2", email="fceditor2@test.com",
                            role_id=2, role_str="editor")
        user = _make_user(db, id=807, username="fcuser2", email="fcuser2@test.com",
                          role_id=1, role_str="user")

        for module, action in FACTION_PERMISSIONS:
            perm = f"{module}:{action}"
            require_permission(db, admin, perm)
            if action in ("read", "edit", "manage"):
                require_permission(db, mod, perm)
            else:
                with pytest.raises(HTTPException) as exc_info:
                    require_permission(db, mod, perm)
                assert exc_info.value.status_code == 403
            for blocked in (editor, user):
                with pytest.raises(HTTPException) as exc_info:
                    require_permission(db, blocked, perm)
                assert exc_info.value.status_code == 403

    def test_settings_can_be_delegated_and_revoked(self, rbac_db_with_factions):
        """factions:settings can be granted per person via user_permissions."""
        db = rbac_db_with_factions
        mod = _make_user(db, id=808, username="fcmod3", email="fcmod3@test.com",
                         role_id=3, role_str="moderator")
        perm = db.query(models.Permission).filter(
            models.Permission.module == "factions",
            models.Permission.action == "settings",
        ).one()
        override = models.UserPermission(user_id=mod.id, permission_id=perm.id, granted=True)
        db.add(override)
        db.commit()
        require_permission(db, mod, "factions:settings")  # must not raise
        override.granted = False
        db.commit()
        assert "factions:settings" not in get_effective_permissions(db, mod)

    def test_factions_with_reputation_and_economy(self, rbac_db_with_factions):
        """All three module seeds at once: counts grow by exactly the module sizes."""
        db = rbac_db_with_factions
        _seed_economy_permissions(db)
        _seed_reputation_permissions(db)
        admin = _make_user(db, id=809, username="fcadmin3", email="fcadmin3@test.com",
                           role_id=4, role_str="admin")
        # 8 base + 4 economy + 3 reputation + 5 factions = 20
        assert len(get_effective_permissions(db, admin)) == 20
        mod = _make_user(db, id=810, username="fcmod4", email="fcmod4@test.com",
                         role_id=3, role_str="moderator")
        # 4 base items:* + economy:read + reputation:read/manage
        # + factions:read/edit/manage = 10
        assert len(get_effective_permissions(db, mod)) == 10


# ---------------------------------------------------------------------------
# 15. FEAT-206: factions:economy permission (migration 0035)
# ---------------------------------------------------------------------------
#
# Seeded explicitly (CLAUDE.md §10.13): TestAdminAutoPermissions never reads
# the migration tree, so the new `permissions` row is not covered by it.

FACTION_ECONOMY_PERMISSIONS = [
    ("factions", "economy"),
]

# Mirrors ROLE_ACTIONS from migration 0035. Admin (4) gets it automatically;
# editor (2) gets nothing (FEAT-206 §3).
FACTION_ECONOMY_ROLE_ACTIONS = {
    3: ["economy"],  # Moderator
}


def _seed_faction_economy_permission(db):
    """Seed factions:economy and its role grants (mirrors 0035)."""
    perm_objects = []
    for module, action in FACTION_ECONOMY_PERMISSIONS:
        perm = models.Permission(module=module, action=action,
                                 description=f"Factions: {action}")
        db.add(perm)
        perm_objects.append(perm)
    db.flush()

    for perm in perm_objects:
        for role_id, actions in FACTION_ECONOMY_ROLE_ACTIONS.items():
            if perm.action in actions:
                db.add(models.RolePermission(role_id=role_id, permission_id=perm.id))
    db.commit()
    return perm_objects


@pytest.fixture()
def rbac_db_with_faction_economy(rbac_db):
    """Base RBAC seed + factions:* (0034) + factions:economy (0035)."""
    _seed_faction_permissions(rbac_db)
    _seed_faction_economy_permission(rbac_db)
    return rbac_db


class TestFactionEconomyPermission:
    """FEAT-206: factions:economy."""

    def test_seed_mirrors_the_migration(self):
        """Migration 0035 lists exactly factions:economy, moderator only."""
        import importlib.util
        from pathlib import Path
        path = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
                / "0035_faction_economy_perm.py")
        spec = importlib.util.spec_from_file_location("mig_0035", path)
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        assert [(m, a) for m, a, _ in mig.PERMISSIONS] == FACTION_ECONOMY_PERMISSIONS
        assert mig.ROLE_ACTIONS == FACTION_ECONOMY_ROLE_ACTIONS
        assert mig.revision == "0035" and mig.down_revision == "0034"
        assert len(mig.revision) <= 32  # alembic_version column limit

    def test_factions_module_now_has_six(self, rbac_db_with_faction_economy):
        db = rbac_db_with_faction_economy
        assert db.query(models.Permission).filter(
            models.Permission.module == "factions").count() == 6

    def test_admin_gets_it(self, rbac_db_with_faction_economy):
        db = rbac_db_with_faction_economy
        admin = _make_user(db, id=820, username="feadmin", email="feadmin@test.com",
                           role_id=4, role_str="admin")
        perms = get_effective_permissions(db, admin)
        assert "factions:economy" in perms
        # 8 base + 5 factions + 1 factions:economy = 14
        assert len(perms) == 14

    def test_moderator_gets_it(self, rbac_db_with_faction_economy):
        db = rbac_db_with_faction_economy
        mod = _make_user(db, id=821, username="femod", email="femod@test.com",
                         role_id=3, role_str="moderator")
        perms = get_effective_permissions(db, mod)
        assert sorted(p for p in perms if p.startswith("factions:")) == \
            ["factions:economy", "factions:edit", "factions:manage", "factions:read"]
        # 4 base items:* + 3 factions + 1 factions:economy = 8
        assert len(perms) == 8

    def test_editor_and_user_do_not(self, rbac_db_with_faction_economy):
        db = rbac_db_with_faction_economy
        editor = _make_user(db, id=822, username="feeditor", email="feeditor@test.com",
                            role_id=2, role_str="editor")
        user = _make_user(db, id=823, username="feuser", email="feuser@test.com",
                          role_id=1, role_str="user")
        assert "factions:economy" not in get_effective_permissions(db, editor)
        assert len(get_effective_permissions(db, editor)) == 2  # base *:read
        assert get_effective_permissions(db, user) == []

    def test_require_permission_matrix(self, rbac_db_with_faction_economy):
        db = rbac_db_with_faction_economy
        admin = _make_user(db, id=824, username="feadmin2", email="feadmin2@test.com",
                           role_id=4, role_str="admin")
        mod = _make_user(db, id=825, username="femod2", email="femod2@test.com",
                         role_id=3, role_str="moderator")
        editor = _make_user(db, id=826, username="feeditor2", email="feeditor2@test.com",
                            role_id=2, role_str="editor")
        user = _make_user(db, id=827, username="feuser2", email="feuser2@test.com",
                          role_id=1, role_str="user")
        require_permission(db, admin, "factions:economy")
        require_permission(db, mod, "factions:economy")
        for blocked in (editor, user):
            with pytest.raises(HTTPException) as exc_info:
                require_permission(db, blocked, "factions:economy")
            assert exc_info.value.status_code == 403

    def test_can_be_revoked_per_person(self, rbac_db_with_faction_economy):
        db = rbac_db_with_faction_economy
        mod = _make_user(db, id=828, username="femod3", email="femod3@test.com",
                         role_id=3, role_str="moderator")
        perm = db.query(models.Permission).filter(
            models.Permission.module == "factions",
            models.Permission.action == "economy",
        ).one()
        db.add(models.UserPermission(user_id=mod.id, permission_id=perm.id, granted=False))
        db.commit()
        assert "factions:economy" not in get_effective_permissions(db, mod)

    def test_with_economy_and_reputation(self, rbac_db_with_faction_economy):
        """All module seeds at once: counts grow by exactly the module sizes."""
        db = rbac_db_with_faction_economy
        _seed_economy_permissions(db)
        _seed_reputation_permissions(db)
        admin = _make_user(db, id=829, username="feadmin3", email="feadmin3@test.com",
                           role_id=4, role_str="admin")
        # 8 base + 4 economy + 3 reputation + 5 factions + 1 factions:economy = 21
        assert len(get_effective_permissions(db, admin)) == 21
        mod = _make_user(db, id=830, username="femod4", email="femod4@test.com",
                         role_id=3, role_str="moderator")
        # 10 (see TestFactionPermissions) + factions:economy = 11
        assert len(get_effective_permissions(db, mod)) == 11

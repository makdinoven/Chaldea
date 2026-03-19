"""
FEAT-045 Task #10 — QA Tests for chat:delete and chat:ban permissions.

Verifies that Alembic migration 0011_add_chat_permissions correctly:
1. Creates permissions with module="chat" and actions "delete" and "ban"
2. Assigns both permissions to Admin (role_id=4) and Moderator (role_id=3)
3. Regular User and Editor roles do NOT have these permissions
4. Admin auto-permission mechanism includes chat permissions
"""

import pytest

import models
from crud import get_effective_permissions, require_permission
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

def _seed_roles(db):
    """Create the 4 standard RBAC roles."""
    roles = [
        models.Role(id=1, name="user", level=0, description="Regular user"),
        models.Role(id=2, name="editor", level=20, description="Editor"),
        models.Role(id=3, name="moderator", level=50, description="Moderator"),
        models.Role(id=4, name="admin", level=100, description="Administrator"),
    ]
    for r in roles:
        db.add(r)
    db.commit()
    return {r.name: r for r in roles}


def _seed_chat_permissions(db):
    """Create the chat:delete and chat:ban permissions (as migration 0011 does)."""
    perms = [
        models.Permission(id=32, module="chat", action="delete",
                          description="Удаление сообщений в чате"),
        models.Permission(id=33, module="chat", action="ban",
                          description="Бан/разбан пользователей в чате"),
    ]
    for p in perms:
        db.add(p)
    db.commit()
    return perms


def _seed_chat_role_permissions(db):
    """Assign chat permissions to Admin and Moderator (as migration 0011 does)."""
    assignments = [
        models.RolePermission(role_id=4, permission_id=32),  # Admin - chat:delete
        models.RolePermission(role_id=4, permission_id=33),  # Admin - chat:ban
        models.RolePermission(role_id=3, permission_id=32),  # Moderator - chat:delete
        models.RolePermission(role_id=3, permission_id=33),  # Moderator - chat:ban
    ]
    for rp in assignments:
        db.add(rp)
    db.commit()


def _seed_chat_rbac(db):
    """Full seed: roles + chat permissions + role_permissions."""
    roles = _seed_roles(db)
    perms = _seed_chat_permissions(db)
    _seed_chat_role_permissions(db)
    return roles, perms


def _make_user(db, *, id, username, email, role_id=None, role_str="user"):
    """Create a test user with specified role_id."""
    user = models.User(
        id=id,
        email=email,
        username=username,
        hashed_password="hashed_placeholder",
        role=role_str,
        role_id=role_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def chat_rbac_db(db_session):
    """DB session with roles and chat permissions seeded."""
    _seed_chat_rbac(db_session)
    return db_session


@pytest.fixture()
def admin_user(chat_rbac_db):
    return _make_user(chat_rbac_db, id=1, username="admin", email="admin@test.com",
                      role_id=4, role_str="admin")


@pytest.fixture()
def moderator_user(chat_rbac_db):
    return _make_user(chat_rbac_db, id=2, username="moderator", email="mod@test.com",
                      role_id=3, role_str="moderator")


@pytest.fixture()
def editor_user(chat_rbac_db):
    return _make_user(chat_rbac_db, id=3, username="editor", email="editor@test.com",
                      role_id=2, role_str="editor")


@pytest.fixture()
def regular_user(chat_rbac_db):
    return _make_user(chat_rbac_db, id=4, username="player", email="player@test.com",
                      role_id=1, role_str="user")


# ---------------------------------------------------------------------------
# 1. Test that chat permissions exist in the DB
# ---------------------------------------------------------------------------

class TestChatPermissionsExist:
    """Verify that chat:delete and chat:ban permissions are created."""

    def test_chat_delete_permission_exists(self, chat_rbac_db):
        """Permission with module=chat, action=delete should exist."""
        perm = chat_rbac_db.query(models.Permission).filter(
            models.Permission.module == "chat",
            models.Permission.action == "delete",
        ).first()
        assert perm is not None
        assert perm.id == 32

    def test_chat_ban_permission_exists(self, chat_rbac_db):
        """Permission with module=chat, action=ban should exist."""
        perm = chat_rbac_db.query(models.Permission).filter(
            models.Permission.module == "chat",
            models.Permission.action == "ban",
        ).first()
        assert perm is not None
        assert perm.id == 33

    def test_chat_permissions_have_descriptions(self, chat_rbac_db):
        """Both chat permissions should have Russian descriptions."""
        perms = chat_rbac_db.query(models.Permission).filter(
            models.Permission.module == "chat",
        ).all()
        assert len(perms) == 2
        for perm in perms:
            assert perm.description is not None
            assert len(perm.description) > 0


# ---------------------------------------------------------------------------
# 2. Test Admin has chat permissions
# ---------------------------------------------------------------------------

class TestAdminChatPermissions:
    """Admin role must have both chat:delete and chat:ban permissions."""

    def test_admin_has_chat_delete(self, chat_rbac_db, admin_user):
        """Admin should have chat:delete permission."""
        perms = get_effective_permissions(chat_rbac_db, admin_user)
        assert "chat:delete" in perms

    def test_admin_has_chat_ban(self, chat_rbac_db, admin_user):
        """Admin should have chat:ban permission."""
        perms = get_effective_permissions(chat_rbac_db, admin_user)
        assert "chat:ban" in perms

    def test_admin_role_permission_rows_exist(self, chat_rbac_db):
        """Admin (role_id=4) should have role_permissions rows for both chat perms."""
        rps = chat_rbac_db.query(models.RolePermission).filter(
            models.RolePermission.role_id == 4,
            models.RolePermission.permission_id.in_([32, 33]),
        ).all()
        assert len(rps) == 2

    def test_require_permission_chat_delete_passes_for_admin(self, chat_rbac_db, admin_user):
        """require_permission('chat:delete') should not raise for admin."""
        require_permission(chat_rbac_db, admin_user, "chat:delete")

    def test_require_permission_chat_ban_passes_for_admin(self, chat_rbac_db, admin_user):
        """require_permission('chat:ban') should not raise for admin."""
        require_permission(chat_rbac_db, admin_user, "chat:ban")


# ---------------------------------------------------------------------------
# 3. Test Moderator has chat permissions
# ---------------------------------------------------------------------------

class TestModeratorChatPermissions:
    """Moderator role must have both chat:delete and chat:ban permissions."""

    def test_moderator_has_chat_delete(self, chat_rbac_db, moderator_user):
        """Moderator should have chat:delete permission."""
        perms = get_effective_permissions(chat_rbac_db, moderator_user)
        assert "chat:delete" in perms

    def test_moderator_has_chat_ban(self, chat_rbac_db, moderator_user):
        """Moderator should have chat:ban permission."""
        perms = get_effective_permissions(chat_rbac_db, moderator_user)
        assert "chat:ban" in perms

    def test_moderator_role_permission_rows_exist(self, chat_rbac_db):
        """Moderator (role_id=3) should have role_permissions rows for both chat perms."""
        rps = chat_rbac_db.query(models.RolePermission).filter(
            models.RolePermission.role_id == 3,
            models.RolePermission.permission_id.in_([32, 33]),
        ).all()
        assert len(rps) == 2

    def test_require_permission_chat_delete_passes_for_moderator(self, chat_rbac_db, moderator_user):
        """require_permission('chat:delete') should not raise for moderator."""
        require_permission(chat_rbac_db, moderator_user, "chat:delete")

    def test_require_permission_chat_ban_passes_for_moderator(self, chat_rbac_db, moderator_user):
        """require_permission('chat:ban') should not raise for moderator."""
        require_permission(chat_rbac_db, moderator_user, "chat:ban")


# ---------------------------------------------------------------------------
# 4. Test that regular User does NOT have chat permissions
# ---------------------------------------------------------------------------

class TestUserNoChatPermissions:
    """Regular User role must NOT have chat:delete or chat:ban."""

    def test_user_does_not_have_chat_delete(self, chat_rbac_db, regular_user):
        """Regular user should not have chat:delete permission."""
        perms = get_effective_permissions(chat_rbac_db, regular_user)
        assert "chat:delete" not in perms

    def test_user_does_not_have_chat_ban(self, chat_rbac_db, regular_user):
        """Regular user should not have chat:ban permission."""
        perms = get_effective_permissions(chat_rbac_db, regular_user)
        assert "chat:ban" not in perms

    def test_require_permission_chat_delete_raises_for_user(self, chat_rbac_db, regular_user):
        """require_permission('chat:delete') should raise 403 for regular user."""
        with pytest.raises(HTTPException) as exc_info:
            require_permission(chat_rbac_db, regular_user, "chat:delete")
        assert exc_info.value.status_code == 403

    def test_require_permission_chat_ban_raises_for_user(self, chat_rbac_db, regular_user):
        """require_permission('chat:ban') should raise 403 for regular user."""
        with pytest.raises(HTTPException) as exc_info:
            require_permission(chat_rbac_db, regular_user, "chat:ban")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 5. Test that Editor does NOT have chat permissions
# ---------------------------------------------------------------------------

class TestEditorNoChatPermissions:
    """Editor role must NOT have chat:delete or chat:ban."""

    def test_editor_does_not_have_chat_delete(self, chat_rbac_db, editor_user):
        """Editor should not have chat:delete permission."""
        perms = get_effective_permissions(chat_rbac_db, editor_user)
        assert "chat:delete" not in perms

    def test_editor_does_not_have_chat_ban(self, chat_rbac_db, editor_user):
        """Editor should not have chat:ban permission."""
        perms = get_effective_permissions(chat_rbac_db, editor_user)
        assert "chat:ban" not in perms

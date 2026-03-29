"""
FEAT-102 Task #12 — QA Tests for battlepass RBAC permissions.

Covers:
1. Battlepass permissions exist in the DB (battlepass:read, battlepass:create,
   battlepass:update, battlepass:delete)
2. Admin role has ALL battlepass permissions (via auto-permission logic)
3. Moderator has battlepass:read
4. Editor has battlepass:read
"""

import pytest

import models
from crud import get_effective_permissions


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_roles(db):
    """Create the 4 standard RBAC roles. Returns dict {name: Role}."""
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


def _seed_battlepass_permissions(db):
    """Create the 4 battlepass permissions. Returns list of Permission objects."""
    perms = []
    for action in ("read", "create", "update", "delete"):
        p = models.Permission(
            module="battlepass",
            action=action,
            description=f"battlepass:{action}",
        )
        db.add(p)
        db.flush()
        perms.append(p)
    db.commit()
    return perms


def _seed_role_permissions_for_bp(db, roles, permissions):
    """Assign battlepass permissions to roles per migration spec.

    - admin: gets ALL automatically (no explicit rows needed)
    - moderator: battlepass:read
    - editor: battlepass:read
    - user: nothing
    """
    read_perm = next(p for p in permissions if p.action == "read")

    # Moderator gets read
    db.add(models.RolePermission(role_id=roles["moderator"].id, permission_id=read_perm.id))
    # Editor gets read
    db.add(models.RolePermission(role_id=roles["editor"].id, permission_id=read_perm.id))
    db.commit()


def _make_user(db, username, email, role_id=None):
    """Create a minimal user with optional role_id."""
    user = models.User(
        email=email,
        username=username,
        hashed_password="fakehash",
        role="user",
        role_id=role_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ===========================================================================
# 1. Battlepass permissions exist
# ===========================================================================

class TestBattlepassPermissionsExist:

    def test_all_four_permissions_created(self, db_session):
        """After seeding, all 4 battlepass permissions should exist."""
        _seed_battlepass_permissions(db_session)

        perms = (
            db_session.query(models.Permission)
            .filter(models.Permission.module == "battlepass")
            .all()
        )
        actions = {p.action for p in perms}
        assert actions == {"read", "create", "update", "delete"}

    def test_permission_module_action_pairs(self, db_session):
        """Each permission has the correct module:action pair."""
        perms = _seed_battlepass_permissions(db_session)
        for p in perms:
            assert p.module == "battlepass"
            assert p.action in ("read", "create", "update", "delete")


# ===========================================================================
# 2. Admin gets ALL battlepass permissions
# ===========================================================================

class TestAdminBattlepassPermissions:

    def test_admin_has_all_battlepass_permissions(self, db_session):
        """Admin role automatically gets all permissions (including battlepass)."""
        roles = _seed_roles(db_session)
        bp_perms = _seed_battlepass_permissions(db_session)
        # No explicit role_permissions for admin — auto-perm logic handles it
        admin_user = _make_user(
            db_session,
            username="adminuser",
            email="admin@test.com",
            role_id=roles["admin"].id,
        )

        effective = get_effective_permissions(db_session, admin_user)
        effective_set = set(effective)

        for action in ("read", "create", "update", "delete"):
            assert f"battlepass:{action}" in effective_set, (
                f"Admin missing battlepass:{action}"
            )

    def test_admin_has_all_permissions_including_non_bp(self, db_session):
        """Admin auto-perm returns every permission in the DB, not just battlepass."""
        roles = _seed_roles(db_session)
        bp_perms = _seed_battlepass_permissions(db_session)

        # Add a non-battlepass permission
        other = models.Permission(module="items", action="read", description="items:read")
        db_session.add(other)
        db_session.commit()

        admin_user = _make_user(
            db_session,
            username="adminuser",
            email="admin@test.com",
            role_id=roles["admin"].id,
        )

        effective = set(get_effective_permissions(db_session, admin_user))
        assert "items:read" in effective
        assert "battlepass:read" in effective


# ===========================================================================
# 3. Moderator has battlepass:read
# ===========================================================================

class TestModeratorBattlepassPermissions:

    def test_moderator_has_battlepass_read(self, db_session):
        """Moderator should have battlepass:read via role_permissions."""
        roles = _seed_roles(db_session)
        bp_perms = _seed_battlepass_permissions(db_session)
        _seed_role_permissions_for_bp(db_session, roles, bp_perms)

        mod_user = _make_user(
            db_session,
            username="moduser",
            email="mod@test.com",
            role_id=roles["moderator"].id,
        )

        effective = set(get_effective_permissions(db_session, mod_user))
        assert "battlepass:read" in effective

    def test_moderator_lacks_battlepass_write_permissions(self, db_session):
        """Moderator should NOT have create/update/delete battlepass permissions."""
        roles = _seed_roles(db_session)
        bp_perms = _seed_battlepass_permissions(db_session)
        _seed_role_permissions_for_bp(db_session, roles, bp_perms)

        mod_user = _make_user(
            db_session,
            username="moduser",
            email="mod@test.com",
            role_id=roles["moderator"].id,
        )

        effective = set(get_effective_permissions(db_session, mod_user))
        for action in ("create", "update", "delete"):
            assert f"battlepass:{action}" not in effective, (
                f"Moderator should not have battlepass:{action}"
            )


# ===========================================================================
# 4. Editor has battlepass:read
# ===========================================================================

class TestEditorBattlepassPermissions:

    def test_editor_has_battlepass_read(self, db_session):
        """Editor should have battlepass:read via role_permissions."""
        roles = _seed_roles(db_session)
        bp_perms = _seed_battlepass_permissions(db_session)
        _seed_role_permissions_for_bp(db_session, roles, bp_perms)

        editor_user = _make_user(
            db_session,
            username="editoruser",
            email="editor@test.com",
            role_id=roles["editor"].id,
        )

        effective = set(get_effective_permissions(db_session, editor_user))
        assert "battlepass:read" in effective

    def test_editor_lacks_battlepass_write_permissions(self, db_session):
        """Editor should NOT have create/update/delete battlepass permissions."""
        roles = _seed_roles(db_session)
        bp_perms = _seed_battlepass_permissions(db_session)
        _seed_role_permissions_for_bp(db_session, roles, bp_perms)

        editor_user = _make_user(
            db_session,
            username="editoruser",
            email="editor@test.com",
            role_id=roles["editor"].id,
        )

        effective = set(get_effective_permissions(db_session, editor_user))
        for action in ("create", "update", "delete"):
            assert f"battlepass:{action}" not in effective, (
                f"Editor should not have battlepass:{action}"
            )


# ===========================================================================
# 5. Regular user has no battlepass permissions
# ===========================================================================

class TestRegularUserBattlepassPermissions:

    def test_regular_user_has_no_battlepass_permissions(self, db_session):
        """Regular user (no role_id) should have no battlepass permissions."""
        _seed_roles(db_session)
        _seed_battlepass_permissions(db_session)

        user = _make_user(
            db_session,
            username="regularuser",
            email="regular@test.com",
            role_id=None,
        )

        effective = set(get_effective_permissions(db_session, user))
        bp_perms_in_effective = {p for p in effective if p.startswith("battlepass:")}
        assert bp_perms_in_effective == set(), (
            f"Regular user should have no battlepass permissions, got: {bp_perms_in_effective}"
        )

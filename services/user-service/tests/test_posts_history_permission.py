"""
FEAT-160 Task #5 — RBAC coverage for the `posts:history` permission (migration 0029).

The point of this suite is the **grant matrix**, not "somebody gets a 403".

`posts:history` exists precisely because no existing permission could express
"admins only": a moderator already holds every `moderation:*` action (migration
0027) and all five `characters:*`, so reusing any of them would have handed post
edit history to every moderator. Migration 0029 therefore registers the row with
**zero `role_permissions` grants**, and that emptiness *is* the mechanism:
`crud.get_effective_permissions` (services/user-service/crud.py:14-35) hands the
role `admin` every row of the `permissions` table, while every other role gets
only its explicit grants plus `user_permissions` overrides.

Consequences that are asserted here rather than assumed:

* an **admin holds** `posts:history`;
* a **moderator does not** — the single most important case, and the one a
  generic "role without the permission gets 403" test would not catch;
* an editor and a plain player do not;
* the **delegation path works**: a `user_permissions` grant hands it to one named
  moderator, and a revoke takes it back. This is the capability the user chose
  this design for over a hard `get_strict_admin_user` role check, so it is pinned.

Two layers, mirroring `test_moderation_permissions.py`:

1. **Declarative content of migration 0029** — constants and source text, so a
   hand edit that renames the permission, drops the Russian description, or (the
   dangerous one) adds a `role_permissions` insert fails here.
2. **The real `upgrade()` executed against the SQLite test DB.** The migration's
   own SQL runs — its `op` binding is swapped for the test session's connection —
   so the effect assertions below are derived from the migration file itself, not
   from a hand-written copy of it. Granting the permission to a role *in the
   migration* therefore breaks the moderator test, which is exactly the future
   "fix" that must not pass silently.
"""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import models
from crud import get_effective_permissions, require_permission
from fastapi import HTTPException


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "0029_add_posts_history_permission.py"
)

PERMISSION = "posts:history"
MODULE = "posts"
ACTION = "history"

USER_ROLE_ID = 1
EDITOR_ROLE_ID = 2
MODERATOR_ROLE_ID = 3
ADMIN_ROLE_ID = 4


# ---------------------------------------------------------------------------
# Seed helpers (kept local so the file does not depend on sibling test modules)
# ---------------------------------------------------------------------------

def _seed_roles(db):
    for role in (
        models.Role(id=USER_ROLE_ID, name="user", level=0),
        models.Role(id=EDITOR_ROLE_ID, name="editor", level=20),
        models.Role(id=MODERATOR_ROLE_ID, name="moderator", level=50),
        models.Role(id=ADMIN_ROLE_ID, name="admin", level=100),
    ):
        db.add(role)
    db.commit()


def _seed_moderation_like_permissions(db):
    """Give the moderator role the permissions it really holds today.

    Without this the moderator's permission list would be empty and "moderator
    does not hold posts:history" would be true for the wrong reason. Migration
    0027 grants both `moderation:*` actions to role_id=3; `characters:*` is the
    other family FEAT-162 ran into.
    """
    granted = [
        ("moderation", "read"),
        ("moderation", "review"),
        ("characters", "read"),
        ("characters", "approve"),
    ]
    for module, action in granted:
        perm = models.Permission(module=module, action=action,
                                 description=f"{module}: {action}")
        db.add(perm)
        db.flush()
        db.add(models.RolePermission(role_id=MODERATOR_ROLE_ID,
                                     permission_id=perm.id))
    db.commit()


def _make_user(db, *, id, username, role_id, role_str):
    user = models.User(
        id=id,
        email=f"{username}@test.com",
        username=username,
        hashed_password="hashed_placeholder",
        role=role_str,
        role_id=role_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "feat160_migration_0029", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(migration, db, func_name):
    """Execute the migration's real upgrade()/downgrade() on the test session."""
    conn = db.connection()
    original_op = migration.op
    migration.op = SimpleNamespace(get_bind=lambda: conn)
    try:
        getattr(migration, func_name)()
        db.commit()
    finally:
        migration.op = original_op


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def migration_0029():
    if not MIGRATION_PATH.is_file():
        pytest.fail(f"migration 0029 is missing: {MIGRATION_PATH}")
    try:
        return _load_migration()
    except ImportError as exc:  # pragma: no cover — alembic missing in the env
        pytest.skip(f"alembic not importable in this environment: {exc}")


@pytest.fixture()
def migration_source():
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture()
def rbac_db(db_session):
    _seed_roles(db_session)
    _seed_moderation_like_permissions(db_session)
    return db_session


@pytest.fixture()
def migrated_db(rbac_db, migration_0029):
    """RBAC seed + migration 0029's own upgrade() actually executed."""
    _run(migration_0029, rbac_db, "upgrade")
    return rbac_db


@pytest.fixture()
def admin(migrated_db):
    return _make_user(migrated_db, id=601, username="ph_admin",
                      role_id=ADMIN_ROLE_ID, role_str="admin")


@pytest.fixture()
def moderator(migrated_db):
    return _make_user(migrated_db, id=602, username="ph_moderator",
                      role_id=MODERATOR_ROLE_ID, role_str="moderator")


@pytest.fixture()
def editor(migrated_db):
    return _make_user(migrated_db, id=603, username="ph_editor",
                      role_id=EDITOR_ROLE_ID, role_str="editor")


@pytest.fixture()
def player(migrated_db):
    return _make_user(migrated_db, id=604, username="ph_player",
                      role_id=USER_ROLE_ID, role_str="user")


def _posts_permission(db):
    return db.query(models.Permission).filter(
        models.Permission.module == MODULE,
        models.Permission.action == ACTION,
    ).first()


# ---------------------------------------------------------------------------
# Layer 1 — what migration 0029 declares
# ---------------------------------------------------------------------------

class TestMigration0029Declaration:

    def test_revision_chain(self, migration_0029):
        assert migration_0029.revision == "0029"
        assert migration_0029.down_revision == "0028"

    def test_registers_posts_history(self, migration_0029):
        assert migration_0029.MODULE == MODULE
        assert migration_0029.ACTION == ACTION

    def test_description_is_russian_and_non_empty(self, migration_0029):
        """User-facing permission descriptions are Russian (Language Policy)."""
        description = migration_0029.DESCRIPTION
        assert description.strip()
        assert re.search(r"[а-яА-Я]", description), description

    def test_module_is_posts_not_moderation(self, migration_0029):
        """`moderation:post_history` would recreate the FEAT-158 tile/route bug:
        AdminPage renders the «Модерация постов» tile from hasModuleAccess
        ('moderation') while the route demands `moderation:read`."""
        assert migration_0029.MODULE != "moderation"

    def test_upgrade_inserts_no_role_permissions(self, migration_source):
        """THE guard on the design: the empty grant is the feature.

        Attaching this permission to a role would hand post edit history to every
        moderator, which is the exact thing the permission exists to prevent."""
        assert "INSERT INTO role_permissions" not in migration_source
        assert "role_permissions" in migration_source, (
            "downgrade must still clean role_permissions rows"
        )

    def test_no_hardcoded_ids(self, migration_source):
        """Ids are resolved by SELECT; hardcoded ones collide across environments."""
        assert "SELECT id FROM permissions WHERE module = :m AND action = :a" in migration_source
        assert not re.search(r"role_id\s*=\s*\d", migration_source)

    def test_upgrade_is_idempotent_by_construction(self, migration_source):
        upgrade_body = migration_source.split("def upgrade")[1].split("def downgrade")[0]
        select_at = upgrade_body.index("SELECT id FROM permissions")
        insert_at = upgrade_body.index("INSERT INTO permissions")
        assert select_at < insert_at
        assert "if not existing:" in upgrade_body

    def test_downgrade_deletes_grants_before_the_permission(self, migration_source):
        """Order matters — both grant tables reference permissions.id."""
        body = migration_source.split("def downgrade")[1]
        role_at = body.index("DELETE FROM role_permissions")
        user_at = body.index("DELETE FROM user_permissions")
        perm_at = body.index("DELETE FROM permissions")
        assert role_at < perm_at
        assert user_at < perm_at


# ---------------------------------------------------------------------------
# Layer 2 — what the executed migration does to the database
# ---------------------------------------------------------------------------

class TestMigration0029Effect:

    def test_inserts_exactly_one_permissions_row(self, migrated_db):
        rows = migrated_db.query(models.Permission).filter(
            models.Permission.module == MODULE
        ).all()
        assert len(rows) == 1
        assert rows[0].action == ACTION

    def test_description_stored_is_russian(self, migrated_db):
        perm = _posts_permission(migrated_db)
        assert perm.description
        assert re.search(r"[а-яА-Я]", perm.description), perm.description

    def test_inserts_zero_role_permissions_rows(self, migrated_db):
        """Explicitly asserted emptiness: a future grant to any role breaks this."""
        perm = _posts_permission(migrated_db)
        grants = migrated_db.query(models.RolePermission).filter(
            models.RolePermission.permission_id == perm.id
        ).all()
        assert grants == [], (
            "posts:history must be granted to NO role — admins receive it "
            "implicitly via get_effective_permissions, moderators must not."
        )

    def test_rerunning_upgrade_creates_no_duplicate(self, migrated_db, migration_0029):
        _run(migration_0029, migrated_db, "upgrade")
        count = migrated_db.query(models.Permission).filter(
            models.Permission.module == MODULE
        ).count()
        assert count == 1

    def test_downgrade_removes_the_permission_and_its_grants(self, migrated_db,
                                                             migration_0029, moderator):
        perm = _posts_permission(migrated_db)
        migrated_db.add(models.UserPermission(
            user_id=moderator.id, permission_id=perm.id, granted=True))
        migrated_db.commit()
        perm_id = perm.id

        _run(migration_0029, migrated_db, "downgrade")

        assert _posts_permission(migrated_db) is None
        assert migrated_db.query(models.UserPermission).filter(
            models.UserPermission.permission_id == perm_id).count() == 0
        assert migrated_db.query(models.RolePermission).filter(
            models.RolePermission.permission_id == perm_id).count() == 0


# ---------------------------------------------------------------------------
# Layer 3 — the access matrix through get_effective_permissions
# ---------------------------------------------------------------------------

class TestPostsHistoryGrantMatrix:

    def test_admin_has_posts_history(self, migrated_db, admin):
        """Admins hold it implicitly — every row of `permissions` is theirs."""
        assert PERMISSION in get_effective_permissions(migrated_db, admin)

    def test_moderator_does_not_have_posts_history(self, migrated_db, moderator):
        """THE case this permission exists for.

        The moderator genuinely holds moderation:* and characters:* here, so this
        is not vacuous — and it fails the moment anyone grants posts:history to
        the moderator role."""
        perms = get_effective_permissions(migrated_db, moderator)
        assert "moderation:read" in perms, "seed sanity: moderator must hold its real grants"
        assert "moderation:review" in perms
        assert PERMISSION not in perms

    def test_editor_does_not_have_posts_history(self, migrated_db, editor):
        assert PERMISSION not in get_effective_permissions(migrated_db, editor)

    def test_plain_user_does_not_have_posts_history(self, migrated_db, player):
        perms = get_effective_permissions(migrated_db, player)
        assert perms == []
        assert PERMISSION not in perms

    def test_no_module_posts_permission_leaks_to_any_non_admin(self, migrated_db,
                                                               moderator, editor, player):
        """Nothing under the `posts` module reaches a non-admin by default."""
        for user in (moderator, editor, player):
            perms = get_effective_permissions(migrated_db, user)
            assert not any(p.startswith("posts:") for p in perms), (user.username, perms)

    def test_legacy_admin_string_also_has_it(self, migrated_db):
        """An admin with no role_id (legacy column) is still an admin."""
        legacy = _make_user(migrated_db, id=610, username="ph_legacyadmin",
                            role_id=None, role_str="admin")
        assert PERMISSION in get_effective_permissions(migrated_db, legacy)

    def test_require_permission_allows_admin(self, migrated_db, admin):
        require_permission(migrated_db, admin, PERMISSION)  # must not raise

    def test_require_permission_blocks_moderator(self, migrated_db, moderator):
        with pytest.raises(HTTPException) as exc:
            require_permission(migrated_db, moderator, PERMISSION)
        assert exc.value.status_code == 403

    def test_require_permission_blocks_editor_and_player(self, migrated_db, editor, player):
        for user in (editor, player):
            with pytest.raises(HTTPException) as exc:
                require_permission(migrated_db, user, PERMISSION)
            assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Layer 4 — delegation, the reason a permission was chosen over a role check
# ---------------------------------------------------------------------------

class TestPostsHistoryDelegation:

    def test_explicit_grant_gives_one_moderator_the_permission(self, migrated_db, moderator):
        """The user can hand post history to one named person without a deploy."""
        perm = _posts_permission(migrated_db)
        migrated_db.add(models.UserPermission(
            user_id=moderator.id, permission_id=perm.id, granted=True))
        migrated_db.commit()

        perms = get_effective_permissions(migrated_db, moderator)
        assert PERMISSION in perms
        require_permission(migrated_db, moderator, PERMISSION)  # must not raise

    def test_grant_does_not_leak_to_other_moderators(self, migrated_db, moderator):
        """Delegation is per-user, not per-role."""
        other = _make_user(migrated_db, id=620, username="ph_moderator2",
                           role_id=MODERATOR_ROLE_ID, role_str="moderator")
        perm = _posts_permission(migrated_db)
        migrated_db.add(models.UserPermission(
            user_id=moderator.id, permission_id=perm.id, granted=True))
        migrated_db.commit()

        assert PERMISSION in get_effective_permissions(migrated_db, moderator)
        assert PERMISSION not in get_effective_permissions(migrated_db, other)

    def test_revoking_the_grant_removes_the_permission(self, migrated_db, moderator):
        perm = _posts_permission(migrated_db)
        override = models.UserPermission(
            user_id=moderator.id, permission_id=perm.id, granted=True)
        migrated_db.add(override)
        migrated_db.commit()
        assert PERMISSION in get_effective_permissions(migrated_db, moderator)

        override.granted = False
        migrated_db.commit()

        perms = get_effective_permissions(migrated_db, moderator)
        assert PERMISSION not in perms
        with pytest.raises(HTTPException) as exc:
            require_permission(migrated_db, moderator, PERMISSION)
        assert exc.value.status_code == 403

    def test_delegated_grant_adds_nothing_else(self, migrated_db, player):
        """A plain player granted posts:history gets exactly that, not admin."""
        perm = _posts_permission(migrated_db)
        migrated_db.add(models.UserPermission(
            user_id=player.id, permission_id=perm.id, granted=True))
        migrated_db.commit()

        assert get_effective_permissions(migrated_db, player) == [PERMISSION]

"""
FEAT-158 Task #7 — moderation module permissions + the App.tsx consistency guard.

Two independent layers:

1. **Migration 0027 content.** The migration file is loaded directly and its
   declarative constants are asserted, so a hand edit that drops a permission or
   silently narrows the moderator grant fails here. The *effect* of the migration
   on ``get_effective_permissions`` lives in ``test_rbac_permissions.py``
   (section 10), next to the other per-module permission suites.

2. **The structural guard.** FEAT-158 existed because the frontend route
   ``/admin/moderation`` demanded ``moderation:read`` while no migration ever
   created that row — admins get "all permissions" by *selecting the permissions
   table*, so a permission nobody registered is a permission nobody has, and
   ``ProtectedRoute`` bounced every admin back to ``/home``. This test parses
   every ``requiredPermission="…"`` out of ``App.tsx`` and asserts each one is
   registered by a migration, making that class of bug impossible to reintroduce.

   Two details matter for the guard to be trustworthy:

   * ``gametime:read`` / ``gametime:update`` are seeded by a **locations-service**
     migration (``004_game_time_config.py``), not by user-service. A naive scan of
     ``user-service/alembic`` alone would report them as unregistered — a false
     positive on working code. Both migration trees are therefore scanned.
   * The frontend lives outside the per-service container image (``/app`` holds
     the service only), so the test ``skip``s when ``App.tsx`` is not reachable
     from the test's working directory rather than failing a per-service job.
     It runs for real in CI, where the whole repository is checked out.
"""

import importlib.util
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Layer 1 — migration 0027 declares what section 3.1 of the feature says
# ---------------------------------------------------------------------------

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "0027_add_moderation_permissions.py"
)

MODERATOR_ROLE_ID = 3
ADMIN_ROLE_ID = 4
EDITOR_ROLE_ID = 2


def _load_migration():
    """Import the alembic revision module by path (it is not on sys.path)."""
    spec = importlib.util.spec_from_file_location(
        "feat158_migration_0027", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration_0027():
    if not MIGRATION_PATH.is_file():
        pytest.fail(f"migration 0027 is missing: {MIGRATION_PATH}")
    try:
        return _load_migration()
    except ImportError as exc:  # pragma: no cover — alembic missing in the env
        pytest.skip(f"alembic not importable in this environment: {exc}")


class TestMigration0027Declaration:
    """The migration registers the moderation module and grants it correctly."""

    def test_revision_chain(self, migration_0027):
        assert migration_0027.revision == "0027"
        assert migration_0027.down_revision == "0026"

    def test_registers_both_moderation_permissions(self, migration_0027):
        pairs = {(m, a) for m, a, _desc in migration_0027.PERMISSIONS}
        assert pairs == {("moderation", "read"), ("moderation", "review")}

    def test_descriptions_are_russian_and_non_empty(self, migration_0027):
        """User-facing permission descriptions are Russian (Language Policy)."""
        for _module, _action, description in migration_0027.PERMISSIONS:
            assert description.strip()
            assert re.search(r"[а-яА-Я]", description), description

    def test_moderator_keeps_full_moderation_access(self, migration_0027):
        """Regression guard: the endpoints used to admit admin **and** moderator
        via ``get_admin_user``. Narrowing them to admin-only would be a silent
        loss of access, so the moderator role must receive both actions."""
        actions = migration_0027.ROLE_ACTIONS.get(MODERATOR_ROLE_ID)
        assert actions is not None, "moderator (role_id=3) got no moderation grant"
        assert set(actions) == {"read", "review"}

    def test_admin_is_not_granted_explicitly(self, migration_0027):
        """Admin receives every row of `permissions` automatically (crud.py:31-33);
        an explicit grant would be dead rows."""
        assert ADMIN_ROLE_ID not in migration_0027.ROLE_ACTIONS

    def test_editor_gets_nothing(self, migration_0027):
        """Editors have no moderation access today — the fix must not add any."""
        assert EDITOR_ROLE_ID not in migration_0027.ROLE_ACTIONS

    def test_no_hardcoded_permission_ids(self, migration_0027):
        """Everything from 0013 on uses LAST_INSERT_ID(); hardcoded ids collide."""
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        assert "LAST_INSERT_ID()" in source
        assert "INSERT INTO permissions (module, action, description) VALUES (:m, :a, :d)" in source

    def test_upgrade_is_idempotent_by_construction(self, migration_0027):
        """Re-running must be a no-op: both inserts are SELECT-guarded."""
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        assert "SELECT id FROM permissions WHERE module = :m AND action = :a" in source
        assert "SELECT 1 FROM role_permissions WHERE role_id = :r AND permission_id = :p" in source

    def test_downgrade_removes_role_permissions_before_permissions(self, migration_0027):
        """Order matters — role_permissions references permissions.id."""
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        rp = source.index("DELETE FROM role_permissions")
        perms = source.index("DELETE FROM permissions WHERE id IN")
        assert rp < perms


# ---------------------------------------------------------------------------
# Layer 2 — every requiredPermission in App.tsx must be registered somewhere
# ---------------------------------------------------------------------------

APP_TSX_REL = Path("services/frontend/app-chaldea/src/components/App/App.tsx")

# Both migration trees that seed rows into the shared `permissions` table.
# `gametime:*` lives in the locations-service tree (see the module docstring).
MIGRATION_DIRS = (
    Path("services/user-service/alembic/versions"),
    Path("services/locations-service/app/alembic/versions"),
)

REQUIRED_PERMISSION_RE = re.compile(
    r"""requiredPermission\s*=\s*["']([a-z_]+:[a-z_]+)["']"""
)

# `{'module': 'characters', 'action': 'read', ...}` — bulk_insert style (0007-0011).
PERM_DICT_RE = re.compile(
    r"""['"]module['"]\s*:\s*['"]([a-z_]+)['"]\s*,\s*['"]action['"]\s*:\s*['"]([a-z_]+)['"]"""
)
# `("moderation", "read", "…")` — PERMISSIONS-list style (0013 onwards) and the
# raw `VALUES ('gametime', 'read', '…')` tuples in locations-service 004.
PERM_TUPLE_RE = re.compile(
    r"""\(\s*['"]([a-z_]+)['"]\s*,\s*['"]([a-z_]+)['"]\s*,\s*['"]"""
)
# `{"m": "mobs", "a": "manage", "d": "…"}` — the literal bind-parameter style of
# the single-permission migrations (0015, 0008-era one-offs).
PERM_BIND_RE = re.compile(
    r"""['"]m['"]\s*:\s*['"]([a-z_]+)['"]\s*,\s*['"]a['"]\s*:\s*['"]([a-z_]+)['"]"""
)


def _repo_root():
    """Walk up from this file until the frontend App.tsx is visible."""
    for parent in Path(__file__).resolve().parents:
        if (parent / APP_TSX_REL).is_file():
            return parent
    return None


def _registered_permissions(root: Path) -> set:
    """Collect every `module:action` any migration inserts into `permissions`."""
    found = set()
    for rel_dir in MIGRATION_DIRS:
        directory = root / rel_dir
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            if "permissions" not in source:
                continue
            for module, action in PERM_DICT_RE.findall(source):
                found.add(f"{module}:{action}")
            for module, action in PERM_TUPLE_RE.findall(source):
                found.add(f"{module}:{action}")
            for module, action in PERM_BIND_RE.findall(source):
                found.add(f"{module}:{action}")
    return found


@pytest.fixture(scope="module")
def repo_root():
    root = _repo_root()
    if root is None:
        pytest.skip(
            "App.tsx is not reachable from the test working directory "
            "(expected inside a per-service container); the guard runs in CI, "
            "where the full repository is checked out"
        )
    return root


@pytest.fixture(scope="module")
def registered(repo_root):
    return _registered_permissions(repo_root)


@pytest.fixture(scope="module")
def route_permissions(repo_root):
    source = (repo_root / APP_TSX_REL).read_text(encoding="utf-8")
    return REQUIRED_PERMISSION_RE.findall(source)


class TestAppTsxPermissionGuard:
    """Every permission the frontend routes on must exist in the database."""

    def test_parser_actually_finds_permissions(self, registered):
        """Self-check: a broken parser would make the guard below vacuous."""
        assert len(registered) > 50, len(registered)
        # One sample per declaration style the parser has to understand.
        assert "users:manage" in registered          # 0006 bulk_insert dicts
        assert "characters:approve" in registered    # 0007 bulk_insert dicts
        assert "skill_trees:read" in registered      # 0013 inline tuple list
        assert "moderation:read" in registered       # 0027 PERMISSIONS constant
        assert "moderation:review" in registered
        assert "mobs:manage" in registered           # 0015 literal bind params
        assert "gametime:read" in registered         # locations-service 004 raw SQL

    def test_parser_rejects_unregistered_strings(self, registered):
        """The guard can fail: a permission nobody registers is not in the set."""
        assert "moderation:nonexistent" not in registered
        assert "totally_made_up:read" not in registered

    def test_app_tsx_routes_were_found(self, route_permissions):
        """Self-check: an empty list would make the guard below vacuous."""
        assert len(route_permissions) > 20, route_permissions
        assert "moderation:read" in route_permissions

    def test_every_route_permission_is_registered(self, route_permissions, registered):
        """THE guard — this is the assertion FEAT-158 would have failed on."""
        missing = sorted({p for p in route_permissions if p not in registered})
        assert not missing, (
            "App.tsx routes on permissions that no migration registers: "
            f"{missing}. Admins get permissions by SELECTing the `permissions` "
            "table, so an unregistered string locks the route out for everyone. "
            "Register it in a user-service Alembic migration (CLAUDE.md §10.13)."
        )

    def test_moderation_route_is_covered(self, route_permissions, registered):
        """The specific regression FEAT-158 fixed."""
        assert "moderation:read" in route_permissions
        assert "moderation:read" in registered

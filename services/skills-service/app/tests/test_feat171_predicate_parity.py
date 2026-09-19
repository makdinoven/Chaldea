"""
FEAT-171 task 20 — parity matrix for `visibility.can_view_private`.

§3.1 D1 deliberately keeps a COPY of this predicate per service instead of
inventing a shared Python package inside a security feature. There are now
FIVE of them:

  services/character-service/app/visibility.py             (sync)
  services/character-attributes-service/app/visibility.py  (sync)
  services/inventory-service/app/visibility.py             (sync)
  services/skills-service/app/visibility.py                (async twin)
  services/locations-service/app/visibility.py             (async twin, added by
      the review fix for the NPC-shop side door — task 22)

The price of that decision is **drift**: one copy quietly losing the admin
branch, the NPC branch, or the "404 before 403" ordering would reopen exactly
the hole FEAT-171 closes, and nothing anywhere would go red.

So this file *is* the enforcement the Architect promised. The same matrix lives
in all five services under the same name; a copy that drifts fails here.

**Keep the five files identical.** The only difference between them is the sync
vs async call shape in `_can_view` / `_require`.

The matrix (§3.1):

| viewer                                    | expected                          |
|-------------------------------------------|-----------------------------------|
| missing character id                      | HTTPException 404 «Персонаж не найден» |
| NPC / mob (`user_id IS NULL`), any viewer | True  — Q6: an NPC has no private layer |
| guest (`user is None`)                    | False                             |
| another player                            | False                             |
| the owner                                 | True                              |
| admin with `characters:read`              | True                              |
| moderator with `characters:read`          | True                              |
| moderator **without** `characters:read`   | False — role AND permission       |
| editor/user holding `characters:read`     | False — permission is not enough  |

The two "without" rows are the point of the file: a copy that degraded the
`and` into an `or`, or dropped the permission check altogether, still passes
every happy-path test in the service — and fails here.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import visibility  # noqa: E402
from auth_http import UserRead  # noqa: E402


# ---------------------------------------------------------------------------
# A self-contained `characters` table — the predicate reads nothing else.
# Deliberately NOT the service's own engine: this file tests the predicate,
# not the service's wiring, and must stay runnable in every one of the five.
# ---------------------------------------------------------------------------

_engine = create_async_engine(
    "sqlite+aiosqlite://", connect_args={"check_same_thread": False}
)
_Session = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

OWNER_ID = 42
STRANGER_ID = 43

PLAYER_CHARACTER = 1      # user_id = OWNER_ID
NPC_CHARACTER = 2         # user_id IS NULL
MISSING_CHARACTER = 99999


@pytest_asyncio.fixture()
async def db():
    async with _engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS characters"))
        await conn.execute(
            text(
                "CREATE TABLE characters ("
                "  id INTEGER PRIMARY KEY,"
                "  name VARCHAR(255),"
                "  user_id INTEGER NULL"
                ")"
            )
        )
        await conn.execute(
            text("INSERT INTO characters (id, name, user_id) VALUES (:i, 'Player', :u)"),
            {"i": PLAYER_CHARACTER, "u": OWNER_ID},
        )
        await conn.execute(
            text("INSERT INTO characters (id, name, user_id) VALUES (:i, 'Mob', NULL)"),
            {"i": NPC_CHARACTER},
        )
    async with _Session() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS characters"))


def _user(user_id, role, permissions=()):
    return UserRead(
        id=user_id, username=f"u{user_id}", role=role, permissions=list(permissions)
    )


GUEST = None
OWNER = _user(OWNER_ID, "user")
STRANGER = _user(STRANGER_ID, "user")
ADMIN = _user(7, "admin", ["characters:read", "items:create"])
MODERATOR = _user(8, "moderator", ["characters:read"])
MODERATOR_NO_PERM = _user(9, "moderator", ["chat:delete"])
ADMIN_NO_PERM = _user(10, "admin", [])
EDITOR_WITH_PERM = _user(11, "editor", ["characters:read"])
USER_WITH_PERM = _user(12, "user", ["characters:read"])
ROLELESS = _user(13, None, ["characters:read"])
NO_PERMISSIONS_FIELD = UserRead(id=14, username="u14", role="moderator")


# ---------------------------------------------------------------------------
# Sync / async shim — the ONLY line that differs between the five copies.
# ---------------------------------------------------------------------------

async def _can_view(db, character_id, user):
    return await visibility.can_view_private(db, character_id, user)


async def _require(db, character_id, user):
    return await visibility.require_private_access(db, character_id, user)


# ===========================================================================
# 1. The player character
# ===========================================================================

class TestPlayerCharacter:
    """user_id = 42 — the ordinary case every gated route runs."""

    @pytest.mark.parametrize(
        "viewer,expected,why",
        [
            (GUEST, False, "гость не видит приватный слой"),
            (STRANGER, False, "другой игрок не видит приватный слой"),
            (OWNER, True, "владелец видит всё"),
            (ADMIN, True, "админ с characters:read видит всё"),
            (MODERATOR, True, "модератор с characters:read видит всё"),
            (MODERATOR_NO_PERM, False, "модератор БЕЗ characters:read — не видит"),
            (ADMIN_NO_PERM, False, "роли без разрешения недостаточно"),
            (EDITOR_WITH_PERM, False, "разрешения без привилегированной роли недостаточно"),
            (USER_WITH_PERM, False, "обычный игрок с разрешением — всё равно нет"),
            (ROLELESS, False, "пустая роль не проходит"),
            (NO_PERMISSIONS_FIELD, False, "модератор без списка разрешений — не видит"),
        ],
    )
    async def test_matrix(self, db, viewer, expected, why):
        assert await _can_view(db, PLAYER_CHARACTER, viewer) is expected, why

    async def test_role_and_permission_is_an_and_not_an_or(self, db):
        """The single assertion that catches `or` creeping into a copy."""
        assert await _can_view(db, PLAYER_CHARACTER, MODERATOR_NO_PERM) is False
        assert await _can_view(db, PLAYER_CHARACTER, EDITOR_WITH_PERM) is False
        assert await _can_view(db, PLAYER_CHARACTER, MODERATOR) is True

    async def test_the_owner_is_matched_by_user_id_not_by_name(self, db):
        """A viewer whose id differs is a stranger even with the same username."""
        impostor = UserRead(
            id=STRANGER_ID, username=OWNER.username, role="user", permissions=[]
        )
        assert await _can_view(db, PLAYER_CHARACTER, impostor) is False


# ===========================================================================
# 2. NPCs and mobs — Q6: `user_id IS NULL` means "no private layer"
# ===========================================================================

class TestNpcCharacter:

    @pytest.mark.parametrize(
        "viewer",
        [GUEST, STRANGER, OWNER, ADMIN, MODERATOR, MODERATOR_NO_PERM, USER_WITH_PERM],
    )
    async def test_npc_is_public_for_everyone(self, db, viewer):
        assert await _can_view(db, NPC_CHARACTER, viewer) is True

    async def test_require_does_not_raise_for_an_npc(self, db):
        assert await _require(db, NPC_CHARACTER, GUEST) is None


# ===========================================================================
# 3. Existence is never disclosed — 404 BEFORE the ownership branch
# ===========================================================================

class TestMissingCharacter:
    """§3.8: a 403-vs-404 difference would turn the gate into an existence oracle."""

    @pytest.mark.parametrize(
        "viewer", [GUEST, STRANGER, OWNER, ADMIN, MODERATOR, MODERATOR_NO_PERM]
    )
    async def test_missing_id_is_404_for_every_viewer(self, db, viewer):
        with pytest.raises(HTTPException) as exc:
            await _can_view(db, MISSING_CHARACTER, viewer)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Персонаж не найден"

    @pytest.mark.parametrize("viewer", [GUEST, STRANGER, MODERATOR_NO_PERM])
    async def test_require_also_404s_a_missing_id_rather_than_403(self, db, viewer):
        """The stranger branch must never run first: a 403 here would tell an
        attacker that the id exists."""
        with pytest.raises(HTTPException) as exc:
            await _require(db, MISSING_CHARACTER, viewer)
        assert exc.value.status_code == 404, (
            "403 for a missing id makes the gate an existence oracle"
        )


# ===========================================================================
# 4. The hard-gate wrapper
# ===========================================================================

class TestRequirePrivateAccess:

    @pytest.mark.parametrize("viewer", [GUEST, STRANGER, MODERATOR_NO_PERM])
    async def test_strangers_get_403_with_the_shared_russian_message(self, db, viewer):
        with pytest.raises(HTTPException) as exc:
            await _require(db, PLAYER_CHARACTER, viewer)
        assert exc.value.status_code == 403
        assert exc.value.detail == "Эти данные доступны только владельцу персонажа"

    @pytest.mark.parametrize("viewer", [OWNER, ADMIN, MODERATOR])
    async def test_privileged_viewers_pass_through(self, db, viewer):
        assert await _require(db, PLAYER_CHARACTER, viewer) is None


# ===========================================================================
# 5. The copies themselves — constants must not drift either
# ===========================================================================

class TestSharedConstants:

    def test_permission_name(self):
        assert visibility.CHARACTER_PRIVATE_PERMISSION == "characters:read"

    def test_privileged_roles(self):
        assert tuple(visibility.PRIVILEGED_ROLES) == ("admin", "moderator")

    def test_the_module_names_the_feature_it_mirrors(self):
        """§3.1 D1 requires the docstring so the next reader finds the other
        four copies instead of editing one in isolation."""
        assert "FEAT-171" in (visibility.__doc__ or "")

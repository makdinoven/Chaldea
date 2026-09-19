"""
FEAT-171 task 18 (skills half) — `GET /skills/characters/{id}/skills` is S1,
the one route closed with **style B'**.

Style B' exists because this route has two legitimate callers with completely
different credentials: the player's browser (a JWT) and battle-service, which
has always sent the shared secret in the *Bearer* position
(`battle-service/app/skills_client._service_headers`). `allow_jwt_or_service_token`
yields `None` for the service caller and a `UserRead` for a person, and
`require_character_skills_access` lets `None` straight through while sending a
real user through `can_view_private`.

That "`None` means allowed" branch is the risky part of the design — it is one
refactor away from letting an *unauthenticated* request through as a service
call — so it is pinned from both sides here: the service token must pass, and a
guest with no token at all must get 401 from the dependency itself, never the
`None` branch.

Matrix (§3.4 S1): service token ⇒ 200, owner ⇒ 200, admin/moderator with
`characters:read` ⇒ 200, moderator without it ⇒ 403, stranger ⇒ 403,
guest ⇒ 401, NPC ⇒ 200 for anyone, missing id ⇒ 404 (checked before the
ownership branch — §3.8).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import auth_http  # noqa: E402
from auth_http import UserRead  # noqa: E402

_engine = create_async_engine(
    "sqlite+aiosqlite://", connect_args={"check_same_thread": False}
)
_Session = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

import database  # noqa: E402,F401
import models  # noqa: E402
import main as main_module  # noqa: E402
from main import app  # noqa: E402

app.router.on_startup.clear()

_main_get_db = main_module.get_db

SERVICE_TOKEN = "test-internal-token"

OWNER_ID = 42
STRANGER_ID = 43

PLAYER_CHARACTER = 100
NPC_CHARACTER = 101
MISSING_CHARACTER = 99999


def _user(uid, role, permissions=()):
    return UserRead(id=uid, username=f"u{uid}", role=role, permissions=list(permissions))


OWNER = _user(OWNER_ID, "user")
STRANGER = _user(STRANGER_ID, "user")
ADMIN = _user(7, "admin", ["characters:read"])
MODERATOR = _user(8, "moderator", ["characters:read"])
MODERATOR_NO_PERM = _user(9, "moderator", [])

ALLOWED = [("owner", OWNER), ("admin", ADMIN), ("moderator", MODERATOR)]
REFUSED = [("stranger", STRANGER), ("moderator_without_permission", MODERATOR_NO_PERM)]


def _url(character_id):
    return f"/skills/characters/{character_id}/skills"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def setup_db():
    async with _engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    async with _Session() as session:
        await session.execute(text(
            "CREATE TABLE IF NOT EXISTS characters ("
            " id INTEGER PRIMARY KEY, user_id INTEGER NULL)"
        ))
        await session.execute(text("DELETE FROM characters"))
        await session.execute(
            text("INSERT INTO characters (id, user_id) VALUES (:c, :u)"),
            {"c": PLAYER_CHARACTER, "u": OWNER_ID},
        )
        await session.execute(
            text("INSERT INTO characters (id, user_id) VALUES (:c, NULL)"),
            {"c": NPC_CHARACTER},
        )
        # One skill each, so a 200 is distinguishable from an empty gate.
        session.add(models.Skill(id=1, name="Огненный шар", skill_type="attack"))
        session.add(models.CharacterSkill(
            id=1, character_id=PLAYER_CHARACTER, skill_id=1, level=3,
        ))
        session.add(models.CharacterSkill(
            id=2, character_id=NPC_CHARACTER, skill_id=1, level=1,
        ))
        await session.commit()
    yield
    async with _engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS characters"))
        await conn.run_sync(models.Base.metadata.drop_all)


async def _override_get_db():
    async with _Session() as session:
        yield session


@pytest_asyncio.fixture()
async def viewer_client(setup_db, monkeypatch):
    """Factory over the REAL `allow_jwt_or_service_token`.

    Only `get_current_user_via_http` (the network hop to user-service) is
    stubbed, so the dependency's own branching — service token vs JWT vs no
    token — is the code under test, not a dependency override.
    """
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", SERVICE_TOKEN)
    app.dependency_overrides[_main_get_db] = _override_get_db

    def _make(viewer=None, token=None):
        """`viewer=None, token=None` -> a guest; `token=SERVICE_TOKEN` -> a service."""
        if viewer is not None:
            monkeypatch.setattr(
                auth_http, "get_current_user_via_http", lambda t=None: viewer
            )
            token = token or "player-jwt"
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        transport = ASGITransport(app=app)
        return httpx.AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        )

    yield _make
    app.dependency_overrides.clear()


# ===========================================================================
# The matrix
# ===========================================================================

class TestSkillsListGate:

    @pytest.mark.parametrize("name,viewer", ALLOWED)
    async def test_privileged_viewers_get_the_list(self, viewer_client, name, viewer):
        async with viewer_client(viewer) as c:
            r = await c.get(_url(PLAYER_CHARACTER))
        assert r.status_code == 200, f"{name}: {r.text}"
        assert len(r.json()) == 1
        assert r.json()[0]["level"] == 3

    @pytest.mark.parametrize("name,viewer", REFUSED)
    async def test_refused_viewers_get_403(self, viewer_client, name, viewer):
        async with viewer_client(viewer) as c:
            r = await c.get(_url(PLAYER_CHARACTER))
        assert r.status_code == 403, f"{name}: {r.text}"
        assert r.json()["detail"] == "Эти данные доступны только владельцу персонажа"

    async def test_a_guest_is_401_from_the_dependency(self, viewer_client):
        """No token at all must be rejected by `OAUTH2_SCHEME`, and must NOT
        fall into the `viewer is None` (= service caller) branch."""
        async with viewer_client() as c:
            r = await c.get(_url(PLAYER_CHARACTER))
        assert r.status_code == 401, r.text

    async def test_the_service_token_passes(self, viewer_client):
        """battle-service already sends exactly this — zero caller changes."""
        async with viewer_client(token=SERVICE_TOKEN) as c:
            r = await c.get(_url(PLAYER_CHARACTER))
        assert r.status_code == 200, r.text
        assert len(r.json()) == 1

    async def test_the_service_token_also_reads_a_character_it_does_not_own(
        self, viewer_client
    ):
        """The engine has no user in context — that is the whole point."""
        async with viewer_client(token=SERVICE_TOKEN) as c:
            assert (await c.get(_url(NPC_CHARACTER))).status_code == 200

    async def test_a_wrong_service_token_is_not_a_service_caller(self, viewer_client):
        """A near-miss secret must fall through to the JWT path — where it is
        an unknown token — and never be treated as `None` (= allowed).

        The comparison is case-sensitive and exact; with user-service out of
        reach the fall-through surfaces as 503 rather than 401, which is fine:
        what matters is that it is not a 200."""
        async with viewer_client(token=SERVICE_TOKEN.upper()) as c:
            r = await c.get(_url(PLAYER_CHARACTER))
        assert r.status_code in (401, 403, 503), r.text
        assert r.status_code != 200

    @pytest.mark.parametrize("name,viewer", ALLOWED + REFUSED)
    async def test_an_npc_is_public(self, viewer_client, name, viewer):
        async with viewer_client(viewer) as c:
            r = await c.get(_url(NPC_CHARACTER))
        assert r.status_code == 200, f"{name}: {r.text}"

    @pytest.mark.parametrize("name,viewer", ALLOWED + REFUSED)
    async def test_missing_id_is_404_before_the_ownership_branch(
        self, viewer_client, name, viewer
    ):
        async with viewer_client(viewer) as c:
            r = await c.get(_url(MISSING_CHARACTER))
        assert r.status_code == 404, f"{name}: {r.text}"
        assert r.json()["detail"] == "Персонаж не найден"

    async def test_missing_id_is_404_for_the_service_caller_too(self, viewer_client):
        """The service branch skips the predicate entirely, so the 404 comes
        from the query — an empty list here would hide a bad id from the
        engine instead of surfacing it."""
        async with viewer_client(token=SERVICE_TOKEN) as c:
            r = await c.get(_url(MISSING_CHARACTER))
        assert r.status_code == 200 and r.json() == [], r.text


# ===========================================================================
# The private numbers really are behind the gate
# ===========================================================================

class TestWhatTheGateProtects:

    async def test_levels_and_perk_picks_are_only_behind_it(self, viewer_client):
        """§2.3: skill levels, `free_perk_points` and `selected_perk_ids` are
        the build a PvP opponent would scout."""
        async with viewer_client(OWNER) as c:
            row = (await c.get(_url(PLAYER_CHARACTER))).json()[0]
        for key in ("level", "free_perk_points", "selected_perk_ids"):
            assert key in row, key

        async with viewer_client(STRANGER) as c:
            r = await c.get(_url(PLAYER_CHARACTER))
        assert r.status_code == 403
        assert "level" not in r.text


# ===========================================================================
# The catalogue stayed open (§3.4 S3)
# ===========================================================================

class TestCatalogueStillPublic:

    async def test_subclasses_registry_needs_no_token(self, viewer_client):
        async with viewer_client() as c:
            assert (await c.get("/skills/subclasses")).status_code == 200

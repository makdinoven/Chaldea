"""
FEAT-169 #17 (QA) — skills-service: the three mutating skill-grant routes.

Until this feature anyone could POST a body with an arbitrary `character_id`
and hand out any skill to any character:

    POST /skills/                    (legacy "Basic Attack" creation)
    POST /skills/assign_multiple     (bulk grant)

Both are now closed, but **not with the same gate** — the decision is made per
caller (§3.1):

  * `POST /skills/internal/assign_multiple` (new twin) and `POST /skills/`
    are container-only  → `verify_internal_token` (gate I).
  * `POST /skills/assign_multiple` keeps its path because the **admin** NPC
    editor calls it for characters the admin does not own → gate A,
    `require_permission("skills:create")`.

A second thing this file pins is that skills-service now has **two different
token mechanisms** and they must stay apart:

  * `verify_internal_token` — the shared secret in the `X-Internal-Token`
    *header* (FEAT-169 M5);
  * `allow_jwt_or_service_token` — the same secret compared in the *Bearer*
    position, used only by `GET /skills/{id}/resolved` (FEAT-125).

Accepting one secret in two header positions would widen the attack surface,
so each mechanism must reject the other's placement. That is tested both ways.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Async SQLite engine, wired in before main is imported
# ---------------------------------------------------------------------------

_async_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
)

_AsyncTestSessionLocal = async_sessionmaker(
    _async_test_engine, expire_on_commit=False, class_=AsyncSession
)

import database  # noqa: E402

database.engine = _async_test_engine
database.async_session = _AsyncTestSessionLocal


async def _override_get_db():
    async with _AsyncTestSessionLocal() as session:
        yield session


async def _test_create_tables():
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)


database.create_tables = _test_create_tables

import auth_http  # noqa: E402
import models  # noqa: E402
import main as main_module  # noqa: E402
from main import app  # noqa: E402

app.router.on_startup.clear()

# `main.get_db` is the exact function object captured by every `Depends(get_db)`
# at import time — the only reliable override key, whatever other test module
# reassigned `database.get_db` first.
_GET_DB_KEY = main_module.get_db


TOKEN = "test-internal-token"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}

CHARACTER_ID = 4242

INTERNAL_PATH = "/skills/internal/assign_multiple"
PUBLIC_PATH = "/skills/assign_multiple"
LEGACY_PATH = "/skills/"

_ASSIGN_BODY = {
    "character_id": CHARACTER_ID,
    "skills": [{"skill_id": 1}, {"skill_id": 2}],
}
_LEGACY_BODY = {"character_id": CHARACTER_ID}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def setup_db():
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    """`auth_http` resolves the secret into a module-level constant at import
    time, so pinning the env var alone would have no effect — the constant is
    what `verify_internal_token` reads."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest_asyncio.fixture()
async def db_session(setup_db):
    async with _AsyncTestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def seeded(db_session):
    """Two skills the grant routes can hand out."""
    db_session.add(models.Skill(id=1, name="Fireball", skill_type="Attack",
                                description="Fire spell"))
    db_session.add(models.Skill(id=2, name="Ice Spear", skill_type="Attack",
                                description="Ice spell"))
    await db_session.commit()


@pytest_asyncio.fixture()
async def client(setup_db):
    app.dependency_overrides[_GET_DB_KEY] = _override_get_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _granted_skill_ids(db_session, character_id=CHARACTER_ID):
    db_session.expire_all()
    rows = await db_session.execute(
        select(models.CharacterSkill.skill_id).where(
            models.CharacterSkill.character_id == character_id
        )
    )
    return sorted(rows.scalars().all())


def _user_response(status_code: int, payload: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload or {}
    return resp


_PLAIN_PLAYER = {"id": 7, "username": "player", "role": "user",
                 "permissions": ["skills:read"]}
_SKILL_EDITOR = {"id": 8, "username": "editor", "role": "editor",
                 "permissions": ["skills:create", "skills:read"]}


# ══════════════════════════════════════════════════════════════════════════════
# 1. Gate I — POST /skills/internal/assign_multiple
# ══════════════════════════════════════════════════════════════════════════════

_INTERNAL_ROUTES = [
    (INTERNAL_PATH, _ASSIGN_BODY),
    (LEGACY_PATH, _LEGACY_BODY),
]
_INTERNAL_IDS = ["internal/assign_multiple", "legacy POST /skills/"]


class TestInternalRoutesRejectOutsiders:
    """No header / wrong header / empty header — 401, and nothing written."""

    @pytest.mark.parametrize("path, body", _INTERNAL_ROUTES, ids=_INTERNAL_IDS)
    async def test_no_header_returns_401_and_grants_nothing(
        self, client, db_session, seeded, path, body
    ):
        resp = await client.post(path, json=body)
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == "Недействительный internal token"
        assert await _granted_skill_ids(db_session) == [], \
            f"{path} granted skills despite rejecting the request"

    @pytest.mark.parametrize("path, body", _INTERNAL_ROUTES, ids=_INTERNAL_IDS)
    async def test_wrong_header_returns_401(self, client, db_session, seeded,
                                            path, body):
        resp = await client.post(path, json=body, headers=WRONG_HEADERS)
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Недействительный internal token"
        assert await _granted_skill_ids(db_session) == []

    @pytest.mark.parametrize("path, body", _INTERNAL_ROUTES, ids=_INTERNAL_IDS)
    async def test_empty_header_value_returns_401(self, client, db_session,
                                                  seeded, path, body):
        resp = await client.post(path, json=body,
                                 headers={"X-Internal-Token": ""})
        assert resp.status_code == 401
        assert await _granted_skill_ids(db_session) == []

    @pytest.mark.parametrize("path, body", _INTERNAL_ROUTES, ids=_INTERNAL_IDS)
    async def test_auth_runs_before_schema_validation(self, client, seeded,
                                                      path, body):
        """A malformed anonymous body must still answer 401, not 422 — a 422
        means the request reached the handler's schema."""
        resp = await client.post(path, json={"nonsense": True})
        assert resp.status_code == 401, resp.text

    @pytest.mark.parametrize("path, body", _INTERNAL_ROUTES, ids=_INTERNAL_IDS)
    async def test_header_name_is_case_insensitive_but_value_is_not(
        self, client, seeded, path, body
    ):
        assert (await client.post(path, json=body,
                                  headers={"x-internal-token": TOKEN})
                ).status_code not in (401, 503)
        assert (await client.post(path, json=body,
                                  headers={"X-Internal-Token": TOKEN.upper()})
                ).status_code == 401


class TestInternalRoutesFailClosed:
    """An unconfigured service must reject everything with 503 — never 200."""

    @pytest.mark.parametrize("path, body", _INTERNAL_ROUTES, ids=_INTERNAL_IDS)
    async def test_empty_token_env_returns_503_and_never_200(
        self, client, db_session, seeded, monkeypatch, path, body
    ):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        for headers in ({}, GOOD_HEADERS, WRONG_HEADERS,
                        {"X-Internal-Token": ""}):
            resp = await client.post(path, json=body, headers=headers)
            assert resp.status_code == 503, resp.text
            assert resp.json()["detail"] == "Internal service token не настроен"
        assert await _granted_skill_ids(db_session) == []


class TestInternalRoutesAcceptTheToken:
    """character-service must keep working: approval grants preset skills."""

    async def test_internal_assign_multiple_grants_the_skills(
        self, client, db_session, seeded
    ):
        resp = await client.post(INTERNAL_PATH, json=_ASSIGN_BODY,
                                 headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert [row["skill_id"] for row in resp.json()["assigned"]] == [1, 2]
        assert await _granted_skill_ids(db_session) == [1, 2]

    async def test_internal_assign_multiple_is_idempotent(self, client, seeded):
        """`send_skills_presets_request` may be retried; an already-granted
        skill must come back as the existing row, not a duplicate."""
        first = await client.post(INTERNAL_PATH, json=_ASSIGN_BODY,
                                  headers=GOOD_HEADERS)
        second = await client.post(INTERNAL_PATH, json=_ASSIGN_BODY,
                                   headers=GOOD_HEADERS)
        assert second.status_code == 200, second.text
        assert second.json() == first.json()

    async def test_internal_assign_multiple_unknown_skill_is_404(
        self, client, db_session, seeded
    ):
        resp = await client.post(
            INTERNAL_PATH,
            json={"character_id": CHARACTER_ID, "skills": [{"skill_id": 999}]},
            headers=GOOD_HEADERS,
        )
        assert resp.status_code == 404
        assert "999" in resp.json()["detail"]

    async def test_legacy_route_grants_the_basic_attack(self, client, db_session):
        resp = await client.post(LEGACY_PATH, json=_LEGACY_BODY,
                                 headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["message"] == "Basic skill assigned to character"
        assert await _granted_skill_ids(db_session) != []


# ══════════════════════════════════════════════════════════════════════════════
# 2. The two token mechanisms must not be interchangeable
# ══════════════════════════════════════════════════════════════════════════════
# skills-service is the only service carrying both `verify_internal_token`
# (header position) and `allow_jwt_or_service_token` (Bearer position). If one
# ever grew out of the other, the same secret would open twice the surface.


class TestTheTwoTokenMechanismsStayApart:

    @pytest.mark.parametrize("path, body", _INTERNAL_ROUTES, ids=_INTERNAL_IDS)
    async def test_service_token_in_the_bearer_position_is_not_accepted(
        self, client, db_session, seeded, path, body
    ):
        """`verify_internal_token` reads ONLY `X-Internal-Token`. The very same
        secret presented as a Bearer must not open an internal route."""
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _user_response(401)
            resp = await client.post(
                path, json=body,
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == "Недействительный internal token"
        assert await _granted_skill_ids(db_session) == []

    @pytest.mark.parametrize("path, body", _INTERNAL_ROUTES, ids=_INTERNAL_IDS)
    async def test_a_player_bearer_jwt_is_not_accepted_either(
        self, client, db_session, seeded, path, body
    ):
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _user_response(200, _SKILL_EDITOR)
            resp = await client.post(
                path, json=body, headers={"Authorization": "Bearer player-jwt"}
            )
        assert resp.status_code == 401
        assert await _granted_skill_ids(db_session) == []

    async def test_the_header_position_does_not_open_the_bearer_route(
        self, client, seeded
    ):
        """And the other way round: `GET /skills/{id}/resolved` accepts the
        secret only as a Bearer (`allow_jwt_or_service_token`). Presenting it
        in `X-Internal-Token` must not authenticate the caller."""
        resp = await client.get("/skills/1/resolved",
                                params={"character_id": CHARACTER_ID},
                                headers=GOOD_HEADERS)
        assert resp.status_code == 401, resp.text

    async def test_the_bearer_route_still_takes_the_secret_as_a_bearer(
        self, client, seeded
    ):
        """Regression guard for FEAT-125: battle-service must keep reading
        resolved skills with the service token in the Bearer position."""
        resp = await client.get("/skills/1/resolved",
                                params={"character_id": CHARACTER_ID},
                                headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code != 401, resp.text


# ══════════════════════════════════════════════════════════════════════════════
# 3. Gate A — POST /skills/assign_multiple (admin NPC editor)
# ══════════════════════════════════════════════════════════════════════════════


class TestPublicAssignMultipleIsAdminOnly:

    async def test_anonymous_returns_401_and_grants_nothing(
        self, client, db_session, seeded
    ):
        resp = await client.post(PUBLIC_PATH, json=_ASSIGN_BODY)
        assert resp.status_code == 401, resp.text
        assert await _granted_skill_ids(db_session) == []

    async def test_plain_player_returns_403_and_grants_nothing(
        self, client, db_session, seeded
    ):
        """The hole this closes: a logged-in player could grant any skill to
        any character, their own or somebody else's."""
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _user_response(200, _PLAIN_PLAYER)
            resp = await client.post(
                PUBLIC_PATH, json=_ASSIGN_BODY,
                headers={"Authorization": "Bearer player-jwt"},
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Недостаточно прав"
        assert await _granted_skill_ids(db_session) == []

    async def test_invalid_jwt_returns_401(self, client, db_session, seeded):
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _user_response(401)
            resp = await client.post(
                PUBLIC_PATH, json=_ASSIGN_BODY,
                headers={"Authorization": "Bearer bad-token"},
            )
        assert resp.status_code == 401
        assert await _granted_skill_ids(db_session) == []

    async def test_skills_create_holder_gets_200(self, client, db_session, seeded):
        """`NpcStatsEditor.tsx` assigns skills to an NPC the admin does not own
        — so the gate is the permission, not ownership."""
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _user_response(200, _SKILL_EDITOR)
            resp = await client.post(
                PUBLIC_PATH, json=_ASSIGN_BODY,
                headers={"Authorization": "Bearer admin-jwt"},
            )
        assert resp.status_code == 200, resp.text
        assert await _granted_skill_ids(db_session) == [1, 2]

    async def test_the_internal_token_header_does_not_open_the_public_route(
        self, client, db_session, seeded
    ):
        """The public path is gate A, not gate I: the service secret must not
        substitute for the admin permission."""
        resp = await client.post(PUBLIC_PATH, json=_ASSIGN_BODY,
                                 headers=GOOD_HEADERS)
        assert resp.status_code == 401, resp.text
        assert await _granted_skill_ids(db_session) == []


# ══════════════════════════════════════════════════════════════════════════════
# 4. The twin and the public route share one body — and must keep sharing it
# ══════════════════════════════════════════════════════════════════════════════


class TestTheTwinAndThePublicRouteAgree:

    async def test_same_input_produces_the_same_payload(self, client, db_session,
                                                        seeded):
        """Both routes call `_assign_multiple_core`. If somebody forks the
        logic, the admin editor and character approval would start handing out
        different things."""
        internal = await client.post(INTERNAL_PATH, json=_ASSIGN_BODY,
                                     headers=GOOD_HEADERS)
        assert internal.status_code == 200, internal.text

        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _user_response(200, _SKILL_EDITOR)
            public = await client.post(
                PUBLIC_PATH, json=_ASSIGN_BODY,
                headers={"Authorization": "Bearer admin-jwt"},
            )
        assert public.status_code == 200, public.text
        assert public.json() == internal.json()

    async def test_both_routes_reach_the_same_core(self):
        import inspect

        for fn in (main_module.assign_multiple_skills_internal,
                   main_module.assign_multiple_skills):
            assert "_assign_multiple_core" in inspect.getsource(fn), (
                f"{fn.__name__} no longer delegates to _assign_multiple_core — "
                "the two routes may now diverge"
            )


# ══════════════════════════════════════════════════════════════════════════════
# 5. Route-table sweep — nobody may quietly un-gate any of the three
# ══════════════════════════════════════════════════════════════════════════════


class TestTheGatesAreOnTheRouteTable:

    def _dependency_names(self, route):
        return {
            getattr(dep.call, "__name__", type(dep.call).__name__)
            for dep in route.dependant.dependencies
        }

    def test_internal_routes_require_the_internal_token(self):
        from fastapi.routing import APIRoute

        wanted = {
            ("POST", "/skills/internal/assign_multiple"),
            ("POST", "/skills/"),
        }
        found = set()
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            if "verify_internal_token" not in self._dependency_names(route):
                continue
            for method in route.methods:
                found.add((method, route.path))
        assert wanted <= found, f"no longer gated: {sorted(wanted - found)}"

    def test_the_public_assign_multiple_is_behind_a_permission(self):
        from fastapi.routing import APIRoute

        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            if route.path != PUBLIC_PATH or "POST" not in route.methods:
                continue
            names = self._dependency_names(route)
            # require_permission returns a closure named `checker`
            assert "checker" in names, (
                f"{PUBLIC_PATH} lost its require_permission dependency "
                f"(deps: {sorted(names)})"
            )
            assert "verify_internal_token" not in names, (
                "the public admin route must not accept the service token"
            )
            return
        pytest.fail(f"POST {PUBLIC_PATH} is no longer registered")

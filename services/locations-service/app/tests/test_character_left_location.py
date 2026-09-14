"""FEAT-162 task #10 — POST /locations/internal/character-left-location.

One endpoint, two very different jobs, and the tests are split accordingly.

**The mandatory half** — expiring the character's open action gates and pending
gate requests in the location they are leaving — is what the whole feature
exists for. A failure here has to reach the caller as a 500 so the admin move
aborts *before* writing the new location. So it is tested against a real
in-memory aiosqlite database with real rows, and the assertions are mostly
about what is *not* touched: `consumed` gates, already-`expired` gates,
non-`pending` requests, the same character's rows in other locations, other
characters' rows in this one. An over-broad `UPDATE` here would quietly
destroy rights people paid for with post length.

**The best-effort half** — pruning a forming party in battle-service — must
never fail the request, because the normal move path treats it the same way.
Both failure shapes (transport error, non-2xx) are asserted to still return
200 with `party_pruned=false`.

Plus the guard (`verify_internal_token`: no header / wrong header → 401, env
unset → 503) and idempotency, which is what lets the admin move retry safely.

DB-level cases call the route coroutine directly with a real session; the HTTP
contract cases go through `TestClient` with the mock session from conftest.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, event, text as sa_text
from sqlalchemy.dialects.mysql import MEDIUMTEXT, TINYINT
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
import main as main_module  # noqa: E402
import schemas  # noqa: E402
from models import ActionGate, Location, Post, PostGateRequest  # noqa: E402


# ---------------------------------------------------------------------------
# SQLite DDL hooks — MySQL-only column types have no sqlite spelling.
# (Same hooks test_post_gate_requests.py established.)
# ---------------------------------------------------------------------------

@compiles(BigInteger, "sqlite")
def _bigint_as_sqlite_integer(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


@compiles(MEDIUMTEXT, "sqlite")
def _mediumtext_as_sqlite_text(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "TEXT"


@compiles(TINYINT, "sqlite")
def _tinyint_as_sqlite_integer(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


TOKEN = "secret-test-token-162"
GOOD = {"X-Internal-Token": TOKEN}

LOC_LEFT = 810          # the location being left
LOC_ELSEWHERE = 811     # an unrelated location — must stay untouched
CHAR = 8100
OTHER_CHAR = 8101


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_setup(dbapi_conn, _record):  # pragma: no cover - connection hook
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        # `expire_gate_requests` stamps reviewed_at with NOW().
        dbapi_conn.create_function(
            "NOW", 0, lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )

    async with engine.begin() as conn:
        for ddl in (
            'CREATE TABLE "Regions" (id INTEGER PRIMARY KEY)',
            'CREATE TABLE "Districts" (id INTEGER PRIMARY KEY)',
        ):
            await conn.execute(sa_text(ddl))
        for table in (
            Location.__table__,
            Post.__table__,
            ActionGate.__table__,
            PostGateRequest.__table__,
        ):
            await conn.run_sync(table.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        for loc_id, name in ((LOC_LEFT, "Пирс"), (LOC_ELSEWHERE, "Бар «Три Галки»")):
            s.add(Location(
                id=loc_id, name=name, type="location", recommended_level=1,
                quick_travel_marker=False, description="d", marker_type="safe",
                sort_order=0, is_starting=False,
            ))
        await s.commit()
        yield s

    await engine.dispose()


@pytest.fixture()
def internal_token():
    original = getattr(main_module, "INTERNAL_SERVICE_TOKEN", "")
    main_module.INTERNAL_SERVICE_TOKEN = TOKEN
    try:
        yield TOKEN
    finally:
        main_module.INTERNAL_SERVICE_TOKEN = original


@pytest.fixture()
def token_unset():
    original = getattr(main_module, "INTERNAL_SERVICE_TOKEN", "")
    main_module.INTERNAL_SERVICE_TOKEN = ""
    try:
        yield
    finally:
        main_module.INTERNAL_SERVICE_TOKEN = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _add_gate(session, *, character_id=CHAR, location_id=LOC_LEFT,
                    status="open", action_type="combat", target_ref=1) -> int:
    gate = ActionGate(
        character_id=character_id, location_id=location_id, post_id=None,
        action_type=action_type, target_ref=target_ref, status=status,
    )
    session.add(gate)
    await session.commit()
    await session.refresh(gate)
    return gate.id


async def _add_request(session, *, character_id=CHAR, location_id=LOC_LEFT,
                       status="pending") -> int:
    req = PostGateRequest(
        post_id=None, character_id=character_id, location_id=location_id,
        user_id=1, gates=[{"action_type": "combat", "targets": [1]}],
        status=status,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req.id


async def _gate_status(session, gate_id: int) -> str:
    return (await session.execute(
        sa_text("SELECT status FROM action_gates WHERE id = :i"), {"i": gate_id},
    )).scalar()


async def _request_status(session, request_id: int) -> str:
    return (await session.execute(
        sa_text("SELECT status FROM post_gate_requests WHERE id = :i"),
        {"i": request_id},
    )).scalar()


async def _request_reviewed_at(session, request_id: int):
    return (await session.execute(
        sa_text("SELECT reviewed_at FROM post_gate_requests WHERE id = :i"),
        {"i": request_id},
    )).scalar()


def _prune_ok(status_code=200):
    """Patch the outbound battle-service party call with a given outcome."""
    resp = MagicMock(status_code=status_code)
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch.object(main_module.httpx, "AsyncClient", return_value=cm), client


async def _call(session, character_id=CHAR, from_location_id=LOC_LEFT,
                prune_status=200):
    """Invoke the route coroutine directly against the real session.

    The token guard is a FastAPI dependency and is covered separately by the
    HTTP-level tests below, so it is passed as ``None`` here.
    """
    patcher, _client = _prune_ok(prune_status)
    with patcher:
        return await main_module.character_left_location_route(
            schemas.CharacterLeftLocationRequest(
                character_id=character_id, from_location_id=from_location_id,
            ),
            session,
            None,
        )


# ===========================================================================
# 1. The guard
# ===========================================================================

class TestInternalTokenGuard:
    def test_no_header_is_rejected(self, client, internal_token):
        resp = client.post(
            "/locations/internal/character-left-location",
            json={"character_id": CHAR, "from_location_id": LOC_LEFT},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Недействительный internal token"

    def test_wrong_token_is_rejected(self, client, internal_token):
        resp = client.post(
            "/locations/internal/character-left-location",
            json={"character_id": CHAR, "from_location_id": LOC_LEFT},
            headers={"X-Internal-Token": "nope"},
        )
        assert resp.status_code == 401

    def test_unset_env_fails_closed_with_503(self, client, token_unset):
        """A forgotten env var must break loudly, never serve the endpoint
        unauthenticated — including to a caller who presents the real token."""
        for headers in (None, GOOD):
            resp = client.post(
                "/locations/internal/character-left-location",
                json={"character_id": CHAR, "from_location_id": LOC_LEFT},
                headers=headers,
            )
            assert resp.status_code == 503
            assert resp.json()["detail"] == "Internal service token не настроен"

    @patch("crud.expire_action_gates", new_callable=AsyncMock, return_value=0)
    @patch("crud.expire_gate_requests", new_callable=AsyncMock, return_value=0)
    def test_valid_token_is_accepted(
        self, _requests, _gates, client, internal_token,
    ):
        patcher, _ = _prune_ok(200)
        with patcher:
            resp = client.post(
                "/locations/internal/character-left-location",
                json={"character_id": CHAR, "from_location_id": LOC_LEFT},
                headers=GOOD,
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["ok"] is True


# ===========================================================================
# 2. The mandatory cleanup — real rows
# ===========================================================================

@pytest.mark.asyncio
class TestGatesAndRequestsAreExpired:
    async def test_open_gates_and_pending_requests_are_expired(self, session):
        g1 = await _add_gate(session, target_ref=1)
        g2 = await _add_gate(session, target_ref=2)
        r1 = await _add_request(session)

        result = await _call(session)

        assert result.ok is True
        assert result.gates_expired == 2
        assert result.gate_requests_expired == 1
        assert await _gate_status(session, g1) == "expired"
        assert await _gate_status(session, g2) == "expired"
        assert await _request_status(session, r1) == "expired"
        # The moderation queue entry is stamped as handled, not just flipped.
        assert await _request_reviewed_at(session, r1) is not None

    async def test_consumed_and_already_expired_gates_are_left_alone(self, session):
        """`consumed` is history — the action already fired and the row is the
        audit trail of it. Re-flipping it to `expired` would rewrite that."""
        consumed = await _add_gate(session, status="consumed", target_ref=3)
        already = await _add_gate(session, status="expired", target_ref=4)
        open_gate = await _add_gate(session, target_ref=5)

        result = await _call(session)

        assert result.gates_expired == 1
        assert await _gate_status(session, consumed) == "consumed"
        assert await _gate_status(session, already) == "expired"
        assert await _gate_status(session, open_gate) == "expired"

    @pytest.mark.parametrize("status", ["approved", "rejected", "expired"])
    async def test_non_pending_requests_are_left_alone(self, session, status):
        decided = await _add_request(session, status=status)
        await _call(session)
        assert await _request_status(session, decided) == status

    async def test_other_locations_are_untouched(self, session):
        """Leaving the pier must not disarm the character everywhere else —
        gates are per (character, location)."""
        here = await _add_gate(session, location_id=LOC_LEFT)
        there = await _add_gate(session, location_id=LOC_ELSEWHERE)
        req_there = await _add_request(session, location_id=LOC_ELSEWHERE)

        result = await _call(session, from_location_id=LOC_LEFT)

        assert result.gates_expired == 1
        assert await _gate_status(session, here) == "expired"
        assert await _gate_status(session, there) == "open"
        assert await _request_status(session, req_there) == "pending"

    async def test_other_characters_in_the_same_location_are_untouched(self, session):
        mine = await _add_gate(session, character_id=CHAR)
        theirs = await _add_gate(session, character_id=OTHER_CHAR)
        their_req = await _add_request(session, character_id=OTHER_CHAR)

        result = await _call(session, character_id=CHAR)

        assert result.gates_expired == 1
        assert result.gate_requests_expired == 0
        assert await _gate_status(session, mine) == "expired"
        assert await _gate_status(session, theirs) == "open"
        assert await _request_status(session, their_req) == "pending"

    async def test_nothing_to_expire_is_not_an_error(self, session):
        result = await _call(session)
        assert result.ok is True
        assert result.gates_expired == 0
        assert result.gate_requests_expired == 0


# ===========================================================================
# 3. Null from_location_id — both cleanups skipped
# ===========================================================================

@pytest.mark.asyncio
class TestNullFromLocation:
    async def test_null_location_skips_both_cleanups(self, session):
        """A character with no location has nothing to leave behind. The
        endpoint must not guess a location — and must not touch every row the
        character owns, which is what an unguarded UPDATE would do."""
        gate = await _add_gate(session)
        req = await _add_request(session)

        result = await _call(session, from_location_id=None)

        assert result.ok is True
        assert result.gates_expired == 0
        assert result.gate_requests_expired == 0
        assert await _gate_status(session, gate) == "open"
        assert await _request_status(session, req) == "pending"

    async def test_null_location_omitted_from_the_body_behaves_the_same(
        self, session,
    ):
        gate = await _add_gate(session)
        patcher, _ = _prune_ok(200)
        with patcher:
            result = await main_module.character_left_location_route(
                schemas.CharacterLeftLocationRequest(character_id=CHAR),
                session, None,
            )
        assert result.gates_expired == 0
        assert await _gate_status(session, gate) == "open"

    async def test_null_location_still_prunes_the_party(self, session):
        """The party prune is not location-scoped, so it still runs — leaving
        a forming party behind would be the same class of leak as the gates."""
        patcher, http_client = _prune_ok(200)
        with patcher:
            result = await main_module.character_left_location_route(
                schemas.CharacterLeftLocationRequest(
                    character_id=CHAR, from_location_id=None,
                ),
                session, None,
            )
        assert result.party_pruned is True
        http_client.post.assert_awaited_once()


# ===========================================================================
# 4. Idempotency
# ===========================================================================

@pytest.mark.asyncio
class TestIdempotency:
    async def test_second_call_returns_zero_counts_without_error(self, session):
        """What makes the admin move safe to retry: the counts are how many
        rows *this* call flipped, so a repeat reports zeros rather than
        failing or double-counting."""
        await _add_gate(session, target_ref=1)
        await _add_gate(session, target_ref=2)
        await _add_request(session)

        first = await _call(session)
        second = await _call(session)
        third = await _call(session)

        assert (first.gates_expired, first.gate_requests_expired) == (2, 1)
        assert (second.gates_expired, second.gate_requests_expired) == (0, 0)
        assert (third.gates_expired, third.gate_requests_expired) == (0, 0)
        assert second.ok is third.ok is True


# ===========================================================================
# 5. The best-effort half — a party-prune failure must not fail the request
# ===========================================================================

@pytest.mark.asyncio
class TestPartyPruneIsBestEffort:
    async def test_successful_prune_is_reported(self, session):
        patcher, http_client = _prune_ok(200)
        with patcher:
            result = await main_module.character_left_location_route(
                schemas.CharacterLeftLocationRequest(
                    character_id=CHAR, from_location_id=LOC_LEFT,
                ),
                session, None,
            )
        assert result.party_pruned is True
        assert http_client.post.await_args.kwargs["params"] == {"character_id": CHAR}

    async def test_prune_returning_an_error_status_still_returns_success(
        self, session,
    ):
        gate = await _add_gate(session)
        result = await _call(session, prune_status=500)

        assert result.ok is True
        assert result.party_pruned is False
        # The mandatory half still happened — that is the point of the split.
        assert result.gates_expired == 1
        assert await _gate_status(session, gate) == "expired"

    async def test_prune_transport_failure_still_returns_success(self, session):
        """battle-service down: the gates are already expired and the caller
        is about to move the character. Failing here would abort a move for a
        reason the normal move path ignores."""
        gate = await _add_gate(session)

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(side_effect=OSError("connection refused"))
        cm.__aexit__ = AsyncMock(return_value=False)
        with patch.object(main_module.httpx, "AsyncClient", return_value=cm):
            result = await main_module.character_left_location_route(
                schemas.CharacterLeftLocationRequest(
                    character_id=CHAR, from_location_id=LOC_LEFT,
                ),
                session, None,
            )

        assert result.ok is True
        assert result.party_pruned is False
        assert result.gates_expired == 1
        assert await _gate_status(session, gate) == "expired"


# ===========================================================================
# 6. A gate-cleanup DB failure MUST reach the caller as 500
# ===========================================================================

class TestGateFailureIsFatal:
    """The asymmetry is the feature: the party prune swallows failures, the
    gate cleanup does not. character-service turns this 500 into a 502 and
    refuses to move the character at all."""

    @patch("crud.expire_action_gates", new_callable=AsyncMock)
    def test_gate_expiry_failure_returns_500(
        self, mock_gates, client, internal_token,
    ):
        mock_gates.side_effect = RuntimeError("deadlock")
        resp = client.post(
            "/locations/internal/character-left-location",
            json={"character_id": CHAR, "from_location_id": LOC_LEFT},
            headers=GOOD,
        )
        assert resp.status_code == 500
        assert resp.json()["detail"] == (
            "Не удалось погасить намерения персонажа в покидаемой локации"
        )

    @patch("crud.expire_action_gates", new_callable=AsyncMock, return_value=2)
    @patch("crud.expire_gate_requests", new_callable=AsyncMock)
    def test_gate_request_expiry_failure_returns_500(
        self, mock_requests, _mock_gates, client, internal_token,
    ):
        mock_requests.side_effect = RuntimeError("deadlock")
        resp = client.post(
            "/locations/internal/character-left-location",
            json={"character_id": CHAR, "from_location_id": LOC_LEFT},
            headers=GOOD,
        )
        assert resp.status_code == 500

    @patch("crud.expire_action_gates", new_callable=AsyncMock, return_value=0)
    @patch("crud.expire_gate_requests", new_callable=AsyncMock, return_value=0)
    def test_counts_are_reported_verbatim(
        self, mock_requests, mock_gates, client, internal_token,
    ):
        mock_gates.return_value = 3
        mock_requests.return_value = 2
        patcher, _ = _prune_ok(200)
        with patcher:
            resp = client.post(
                "/locations/internal/character-left-location",
                json={"character_id": CHAR, "from_location_id": LOC_LEFT},
                headers=GOOD,
            )
        body = resp.json()
        assert body == {
            "ok": True, "gates_expired": 3,
            "gate_requests_expired": 2, "party_pruned": True,
        }
        mock_gates.assert_awaited_once()
        assert mock_gates.await_args.args[1:] == (CHAR, LOC_LEFT)
        assert mock_requests.await_args.args[1:] == (CHAR, LOC_LEFT)


# ===========================================================================
# 7. Input validation
# ===========================================================================

class TestValidation:
    @pytest.mark.parametrize("body", [
        {},
        {"character_id": 0},
        {"character_id": -1},
        {"character_id": "'; DROP TABLE action_gates; --"},
        {"character_id": CHAR, "from_location_id": "1 OR 1=1"},
    ])
    def test_bad_bodies_are_rejected_before_any_sql(
        self, client, internal_token, body,
    ):
        resp = client.post(
            "/locations/internal/character-left-location",
            json=body, headers=GOOD,
        )
        assert resp.status_code == 422

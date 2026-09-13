"""FEAT-159 task T11 — retro-added gates as moderation requests (Phase B, T8–T10).

The feature's whole danger lives in one sentence: **gates are bought with text
length**. A post that already spent its characters on five gates must not be
able to edit itself into five more. Section 3.6 closes that by recomputing the
budget over *three* sources at once — every ``action_gates`` row of the post
regardless of status, the gates inside any **pending** ``post_gate_requests``
row, and the gates being requested now — merged by ``action_type`` with a
**union** of targets.

Each of those three sources is a separate way to break the rule, so each is
tested separately (``TestBudgetDoublingExploit``), including the
``expired``-status path — leaving and re-entering a location must not refund a
budget — and the pending-request path, which bypasses ``action_gates``
altogether.

Four layers:

1. **``crud.merge_gate_lists`` as a pure function.** It is the single point
   where the merge happens, so it is tested on its own and not only through an
   endpoint: union rather than concatenation, duplicate collapse, ``None`` kept
   as a distinct member, dicts and objects both accepted.
2. **``crud.edit_post`` against real in-memory aiosqlite** — the budget, the
   request row, and the guarantee that an edit *never* creates an
   ``action_gates`` row.
3. **``crud.review_gate_request`` against the same database** — approval
   re-checks everything in order and **refuses rather than grants**; every
   refusal leaves zero gate rows; rejection creates nothing.
4. **The two admin routes through ``TestClient``** with the crud layer mocked —
   ``moderation:read`` / ``moderation:review``, and the deliberate FEAT-158
   decision that a **moderator** keeps access (narrowing it to admin-only would
   be a silent regression).

Plus the lifecycle rules of section 3.8 (leaving the location expires a pending
request; deleting the post closes it as ``rejected``) and the ``pending_gates``
batch surfacing of T10.

The SQLite translation hooks (``FOR UPDATE``, ``NOW() - INTERVAL ? HOUR``) are
the ones ``test_post_editing.py`` established: they act at the **cursor** level,
so the functions under test run completely untouched and the hour is still
decided by the database against the stored naive timestamp.
"""

import asyncio
import inspect
import os
import re
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, event, text as sa_text
from sqlalchemy.dialects.mysql import MEDIUMTEXT, TINYINT
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
import main as main_module  # noqa: E402
from models import (  # noqa: E402
    ActionGate,
    Location,
    Post,
    PostDeletionRequest,
    PostGateRequest,
    PostReport,
)
from main import app  # noqa: E402
from database import get_db  # noqa: E402


# ---------------------------------------------------------------------------
# SQLite DDL hooks — MySQL-specific column types have no sqlite spelling.
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


LOCATION_ID = 60
OTHER_LOCATION_ID = 61
CHARACTER_ID = 600
OTHER_CHARACTER_ID = 601
AUTHOR_USER_ID = 20
ADMIN_USER_ID = 21

POST_ID = 700

# Gate costs (crud.GATE_SYMBOL_COST): combat 200/target, everything else
# 500/target, floored at MIN_POST_LENGTH = 300.
COMBAT_COST = 200


_INTERVAL_RE = re.compile(r"NOW\(\)\s*-\s*INTERVAL\s*\?\s*HOUR", re.IGNORECASE)
_FOR_UPDATE_RE = re.compile(r"\s+FOR\s+UPDATE\s*$", re.IGNORECASE)


def _sqlite_translate(statement: str) -> str:
    statement = _INTERVAL_RE.sub("datetime('now', '-' || ? || ' hours')", statement)
    return _FOR_UPDATE_RE.sub("", statement)


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    """In-memory async SQLite with the tables this feature actually touches.

    ``characters`` is a bare stub table because it belongs to character-service
    and has no model here, yet both ``edit_post`` and ``review_gate_request``
    read it with raw SQL — ownership and "is the character still in the
    location" are decided there, so it is backed by a real table rather than
    mocked away.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_setup(dbapi_conn, _record):  # pragma: no cover - connection hook
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        dbapi_conn.create_function(
            "NOW", 0, lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )

    @event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def _translate(conn, cursor, statement, parameters, context, executemany):  # pragma: no cover - hook
        return _sqlite_translate(statement), parameters

    async with engine.begin() as conn:
        for ddl in (
            'CREATE TABLE "Regions" (id INTEGER PRIMARY KEY)',
            'CREATE TABLE "Districts" (id INTEGER PRIMARY KEY)',
            "CREATE TABLE characters "
            "(id INTEGER PRIMARY KEY, user_id INTEGER, current_location_id INTEGER)",
        ):
            await conn.execute(sa_text(ddl))
        for table in (
            Location.__table__,
            Post.__table__,
            ActionGate.__table__,
            PostDeletionRequest.__table__,
            PostReport.__table__,
            PostGateRequest.__table__,
        ):
            await conn.run_sync(table.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        for loc_id, name in ((LOCATION_ID, "Бар «Три Галки»"), (OTHER_LOCATION_ID, "Пирс")):
            s.add(Location(
                id=loc_id, name=name, type="location", recommended_level=1,
                quick_travel_marker=False, description="d", marker_type="safe",
                sort_order=0, is_starting=False,
            ))
        await s.execute(sa_text(
            "INSERT INTO characters (id, user_id, current_location_id) "
            "VALUES (:a, :au, :al), (:b, :bu, :bl)"
        ), {"a": CHARACTER_ID, "au": AUTHOR_USER_ID, "al": LOCATION_ID,
            "b": OTHER_CHARACTER_ID, "bu": ADMIN_USER_ID, "bl": LOCATION_ID})
        await s.commit()
        yield s

    await engine.dispose()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _plain(length: int) -> str:
    """Plain text of exactly ``length`` characters after HTML stripping."""
    return "а" * length


async def _add_post(
    session,
    post_id: int = POST_ID,
    *,
    character_id: int = CHARACTER_ID,
    location_id: int = LOCATION_ID,
    content: str | None = None,
    minutes_ago: int = 0,
) -> Post:
    post = Post(
        id=post_id, character_id=character_id, location_id=location_id,
        content=content if content is not None else _plain(1000),
        post_type="regular",
        created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
    )
    session.add(post)
    await session.commit()
    return post


async def _add_gates(
    session,
    post_id: int,
    action_type: str,
    targets,
    *,
    status: str = "open",
    character_id: int = CHARACTER_ID,
    location_id: int = LOCATION_ID,
) -> None:
    """Real ``action_gates`` rows — one per target, exactly as
    ``crud.create_action_gates`` writes them."""
    for target in targets:
        session.add(ActionGate(
            character_id=character_id, location_id=location_id, post_id=post_id,
            action_type=action_type, target_ref=target, status=status,
        ))
    await session.commit()


async def _add_request(
    session,
    post_id,
    gates,
    *,
    status: str = "pending",
    character_id: int = CHARACTER_ID,
    location_id: int = LOCATION_ID,
    user_id: int = AUTHOR_USER_ID,
) -> PostGateRequest:
    req = PostGateRequest(
        post_id=post_id, character_id=character_id, location_id=location_id,
        user_id=user_id, gates=gates, status=status,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def _gate_rows(session, post_id=POST_ID) -> list:
    rows = (await session.execute(sa_text(
        "SELECT action_type, target_ref, status FROM action_gates WHERE post_id = :p "
        "ORDER BY action_type, target_ref"
    ), {"p": post_id})).fetchall()
    return [(a, t, s) for a, t, s in rows]


async def _gate_row_count(session) -> int:
    return (await session.execute(
        sa_text("SELECT COUNT(*) FROM action_gates")
    )).scalar()


async def _request_status(session, request_id: int) -> str:
    return (await session.execute(
        sa_text("SELECT status FROM post_gate_requests WHERE id = :r"),
        {"r": request_id},
    )).scalar()


async def _post_content(session, post_id=POST_ID):
    return (await session.execute(
        sa_text("SELECT content FROM posts WHERE id = :p"), {"p": post_id}
    )).scalar()


async def _edit(session, **kwargs):
    kwargs.setdefault("post_id", POST_ID)
    kwargs.setdefault("user_id", AUTHOR_USER_ID)
    kwargs.setdefault("is_admin", False)
    return await crud.edit_post(session, **kwargs)


# ===========================================================================
# Layer 1 — merge_gate_lists as a pure function (section 3.6 rule 3)
# ===========================================================================

class TestMergeGateListsIsPure:
    """``merge_gate_lists`` is where the whole class of budget exploits is
    closed, so it is tested directly rather than only through the endpoint."""

    def test_it_unions_targets_instead_of_concatenating_entries(self):
        """Two entries of the same action type become ONE entry with the union.

        Concatenation would keep two entries and
        ``required_symbols_for_gates`` would charge ``cost * len(targets)``
        twice — double-charging a target named in both.
        """
        merged = crud.merge_gate_lists(
            [{"action_type": "combat", "targets": [1, 2]}],
            [{"action_type": "combat", "targets": [2, 3]}],
        )
        assert len(merged) == 1
        assert merged[0]["action_type"] == "combat"
        assert sorted(merged[0]["targets"]) == [1, 2, 3]

    def test_the_union_makes_the_cost_exact_not_doubled(self):
        merged = crud.merge_gate_lists(
            [{"action_type": "combat", "targets": [1, 2]}],
            [{"action_type": "combat", "targets": [2, 3]}],
        )
        # Three distinct mobs, not four: 3 * 200 = 600.
        assert crud.required_symbols_for_gates(merged) == 3 * COMBAT_COST

    def test_a_target_repeated_inside_one_list_collapses(self):
        merged = crud.merge_gate_lists(
            [{"action_type": "combat", "targets": [7, 7, 7]}]
        )
        assert merged[0]["targets"] == [7]

    def test_different_action_types_stay_separate(self):
        merged = crud.merge_gate_lists(
            [{"action_type": "combat", "targets": [1]}],
            [{"action_type": "gathering", "targets": [1]}],
        )
        assert {g["action_type"] for g in merged} == {"combat", "gathering"}
        # The same id under two intents is two different things: 200 + 500.
        assert crud.required_symbols_for_gates(merged) == 700

    def test_none_is_a_distinct_member_and_still_costs_a_target(self):
        """A gate created with no target at all is stored as ``target_ref
        NULL``; it must keep costing its one target's worth and must not be
        confused with a real id."""
        merged = crud.merge_gate_lists(
            [{"action_type": "gathering", "targets": [None]}],
            [{"action_type": "gathering", "targets": [5]}],
        )
        assert None in merged[0]["targets"]
        assert 5 in merged[0]["targets"]
        assert len(merged[0]["targets"]) == 2
        assert crud.required_symbols_for_gates(merged) == 1000

    def test_none_repeated_collapses_to_one_member(self):
        merged = crud.merge_gate_lists(
            [{"action_type": "gathering", "targets": [None]}],
            [{"action_type": "gathering", "targets": [None]}],
        )
        assert merged[0]["targets"] == [None]

    def test_objects_are_accepted_as_well_as_dicts(self):
        """``schemas.GateSpec`` instances arrive from the request body; rows
        read from the database arrive as dicts. Both must merge."""
        merged = crud.merge_gate_lists(
            [{"action_type": "combat", "targets": [1]}],
            [SimpleNamespace(action_type="combat", targets=[2])],
        )
        assert len(merged) == 1
        assert sorted(merged[0]["targets"]) == [1, 2]

    def test_empty_and_none_inputs_are_harmless(self):
        assert crud.merge_gate_lists() == []
        assert crud.merge_gate_lists(None, [], None) == []

    def test_an_entry_without_an_action_type_is_dropped(self):
        merged = crud.merge_gate_lists([{"targets": [1]}, {"action_type": "combat", "targets": [1]}])
        assert [g["action_type"] for g in merged] == ["combat"]

    def test_it_does_not_mutate_its_inputs(self):
        """Pure on purpose — ``edit_post`` calls it twice on the same lists."""
        a = [{"action_type": "combat", "targets": [1]}]
        b = [{"action_type": "combat", "targets": [2]}]
        crud.merge_gate_lists(a, b)
        assert a == [{"action_type": "combat", "targets": [1]}]
        assert b == [{"action_type": "combat", "targets": [2]}]

    def test_string_target_ids_are_normalised_to_ints(self):
        merged = crud.merge_gate_lists(
            [{"action_type": "combat", "targets": ["4"]}],
            [{"action_type": "combat", "targets": [4]}],
        )
        assert merged[0]["targets"] == [4]


# ===========================================================================
# Layer 2 — the budget-doubling exploit, through crud.edit_post
# ===========================================================================

class TestBudgetDoublingExploit:
    """**The headline case of FEAT-159.**

    A post buys gates with its own length. Once spent, that length cannot be
    spent again — no matter which of the three sources holds the already-bought
    gates. Each source gets its own test, because each is a separate way for a
    naive implementation to leak the budget.
    """

    @pytest.mark.asyncio
    async def test_path_one_open_gates_cannot_be_doubled(self, session):
        """Five ``open`` combat gates on a 1000-char post: a sixth needs 1200."""
        await _add_post(session, content=_plain(1000))
        await _add_gates(session, POST_ID, "combat", [1, 2, 3, 4, 5])

        with pytest.raises(HTTPException) as exc:
            await _edit(
                session,
                content=_plain(1000),
                gates=[{"action_type": "combat", "targets": [6]}],
            )
        assert exc.value.status_code == 400
        assert "минимум 1200" in exc.value.detail
        assert "сейчас: 1000" in exc.value.detail
        # Nothing was written: not the text, not a request.
        assert await _post_content(session) == _plain(1000)
        assert (await session.execute(
            sa_text("SELECT COUNT(*) FROM post_gate_requests"))).scalar() == 0

    @pytest.mark.asyncio
    async def test_path_two_expired_gates_are_not_refunded(self, session):
        """Leaving and re-entering the location expires the gates — and must
        NOT hand the characters back.

        Counting only ``open`` rows would mean: buy five gates, step next door
        and back, edit, "add" five more against the same 1000 characters.
        """
        await _add_post(session, content=_plain(1000))
        await _add_gates(session, POST_ID, "combat", [1, 2, 3, 4, 5], status="expired")

        with pytest.raises(HTTPException) as exc:
            await _edit(
                session,
                content=_plain(1000),
                gates=[{"action_type": "combat", "targets": [6]}],
            )
        assert exc.value.status_code == 400
        assert "минимум 1200" in exc.value.detail

    @pytest.mark.asyncio
    async def test_consumed_gates_are_not_refunded_either(self, session):
        """A gate that already fired is still a gate the post paid for."""
        await _add_post(session, content=_plain(1000))
        await _add_gates(session, POST_ID, "combat", [1, 2, 3, 4, 5], status="consumed")

        with pytest.raises(HTTPException) as exc:
            await _edit(
                session,
                content=_plain(1000),
                gates=[{"action_type": "combat", "targets": [6]}],
            )
        assert exc.value.status_code == 400
        assert "минимум 1200" in exc.value.detail

    @pytest.mark.asyncio
    async def test_path_three_a_pending_request_already_spends_the_budget(self, session):
        """Gates awaiting moderation have no ``action_gates`` row yet, so a
        budget read from that table alone sees a free post.

        Here the post has *no* gate rows at all — only a pending request for
        three combat targets (600 characters' worth). Shrinking the text to 400
        must still be refused.
        """
        await _add_post(session, content=_plain(1000))
        await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [1, 2, 3]}])

        with pytest.raises(HTTPException) as exc:
            await _edit(session, content=_plain(400))
        assert exc.value.status_code == 400
        assert "минимум 600" in exc.value.detail
        assert "сейчас: 400" in exc.value.detail

    @pytest.mark.asyncio
    async def test_path_three_a_second_pending_request_is_refused(self, session):
        """The other half of the pending path: filing request after request,
        each validated against an unchanged ``action_gates``, would double the
        budget through the queue instead of the gate table. One pending request
        per post — 409."""
        await _add_post(session, content=_plain(1000))
        await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [1, 2, 3, 4, 5]}])

        with pytest.raises(HTTPException) as exc:
            await _edit(
                session,
                content=_plain(1000),
                gates=[{"action_type": "combat", "targets": [6]}],
            )
        assert exc.value.status_code == 409
        assert exc.value.detail == "Заявка на намерение по этому посту уже на рассмотрении"
        assert (await session.execute(
            sa_text("SELECT COUNT(*) FROM post_gate_requests"))).scalar() == 1

    @pytest.mark.asyncio
    async def test_the_three_sources_are_summed_together(self, session):
        """One existing gate + two pending + two requested = five distinct
        combat targets = 1000 characters, and 999 is not enough."""
        await _add_post(session, content=_plain(999))
        await _add_gates(session, POST_ID, "combat", [1])
        await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [2, 3]}])

        # The second-request guard fires before the budget, so the budget effect
        # of all three sources is observed on a plain (gateless) edit instead.
        with pytest.raises(HTTPException) as exc:
            await _edit(session, content=_plain(599))
        assert exc.value.status_code == 400
        assert "минимум 600" in exc.value.detail

    @pytest.mark.asyncio
    async def test_an_edit_that_pays_for_everything_is_allowed(self, session):
        """The rule is a budget, not a ban: 1200 characters buy the sixth gate."""
        await _add_post(session, content=_plain(1000))
        await _add_gates(session, POST_ID, "combat", [1, 2, 3, 4, 5])

        result = await _edit(
            session,
            content=_plain(1200),
            gates=[{"action_type": "combat", "targets": [6]}],
        )
        assert result["gate_request_status"] == "pending"
        assert result["gate_request_id"] is not None
        assert await _post_content(session) == _plain(1200)

    @pytest.mark.asyncio
    async def test_shortening_below_the_existing_gates_is_refused(self, session):
        """Section 1's «правка сокращает текст ниже бюджета» — the same rule,
        no separate code path: the merged set includes the existing gates."""
        await _add_post(session, content=_plain(1000))
        await _add_gates(session, POST_ID, "combat", [1, 2, 3, 4, 5])

        with pytest.raises(HTTPException) as exc:
            await _edit(session, content=_plain(307))
        assert exc.value.status_code == 400
        assert "минимум 1000" in exc.value.detail
        # Already-granted gates are never revoked by an edit — the edit simply
        # does not happen.
        assert len(await _gate_rows(session)) == 5

    @pytest.mark.asyncio
    async def test_an_admin_is_bound_by_the_budget_too(self, session):
        """The 2026-09-13 ruling bypasses the two *editing limits*, not content
        validation."""
        await _add_post(session, content=_plain(1000), minutes_ago=600)
        await _add_gates(session, POST_ID, "combat", [1, 2, 3, 4, 5])

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=POST_ID, content=_plain(500),
                user_id=ADMIN_USER_ID, is_admin=True,
            )
        assert exc.value.status_code == 400
        assert "минимум 1000" in exc.value.detail


# ===========================================================================
# Layer 2b — what an edit does and does not write
# ===========================================================================

class TestEditNeverGrantsAGate:

    @pytest.mark.asyncio
    async def test_an_edit_creates_no_action_gate_row(self, session):
        """The mechanic must stay locked until an admin approves. A retro-added
        gate that fired on save would make the whole moderation step theatre."""
        await _add_post(session, content=_plain(1000))
        assert await _gate_row_count(session) == 0

        result = await _edit(
            session,
            content=_plain(1000),
            gates=[{"action_type": "combat", "targets": [9]}],
        )

        assert await _gate_row_count(session) == 0
        assert result["gate_request_id"] is not None
        # ...and the right is genuinely absent.
        assert await crud.check_action_gate(
            session, CHARACTER_ID, LOCATION_ID, "combat", 9
        ) is False

    @pytest.mark.asyncio
    async def test_the_request_row_records_the_gates_and_is_pending(self, session):
        await _add_post(session, content=_plain(1000))
        result = await _edit(
            session,
            content=_plain(1000),
            gates=[{"action_type": "combat", "targets": [9, 10]}],
        )
        row = (await session.execute(sa_text(
            "SELECT post_id, character_id, location_id, user_id, gates, status "
            "FROM post_gate_requests WHERE id = :r"
        ), {"r": result["gate_request_id"]})).fetchone()
        assert row.post_id == POST_ID
        assert row.character_id == CHARACTER_ID
        assert row.location_id == LOCATION_ID
        assert row.user_id == AUTHOR_USER_ID
        assert row.status == "pending"
        assert crud._decode_gates_json(row.gates) == [
            {"action_type": "combat", "targets": [9, 10]}
        ]

    @pytest.mark.asyncio
    async def test_an_edit_without_gates_files_no_request(self, session):
        await _add_post(session, content=_plain(1000))
        result = await _edit(session, content=_plain(400))
        assert result["gate_request_id"] is None
        assert result["gate_request_status"] is None
        assert (await session.execute(
            sa_text("SELECT COUNT(*) FROM post_gate_requests"))).scalar() == 0


class TestGateRequestValidation:

    @pytest.mark.asyncio
    async def test_a_target_the_post_already_gates_is_refused(self, session):
        """Naming an existing gate is either a client bug or an attempt to
        re-buy a consumed one. Loud 400, not a silent merge."""
        await _add_post(session, content=_plain(2000))
        await _add_gates(session, POST_ID, "combat", [3])

        with pytest.raises(HTTPException) as exc:
            await _edit(
                session,
                content=_plain(2000),
                gates=[{"action_type": "combat", "targets": [3]}],
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == "Гейт на эту цель уже есть в посте"

    @pytest.mark.asyncio
    async def test_a_target_in_a_pending_request_is_refused_too(self, session):
        """Same rule, other source — but the one-pending-request guard is the
        first to fire, so this asserts the 409 rather than the 400."""
        await _add_post(session, content=_plain(2000))
        await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [3]}])

        with pytest.raises(HTTPException) as exc:
            await _edit(
                session,
                content=_plain(2000),
                gates=[{"action_type": "combat", "targets": [3]}],
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_the_same_target_twice_in_one_request_is_refused(self, session):
        await _add_post(session, content=_plain(2000))
        with pytest.raises(HTTPException) as exc:
            await _edit(
                session,
                content=_plain(2000),
                gates=[{"action_type": "combat", "targets": [4, 4]}],
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == "Цель указана дважды в одном намерении"

    @pytest.mark.asyncio
    async def test_a_character_outside_the_posts_location_cannot_request(self, session):
        """Gates are granted to a character on a location; asking for one after
        walking away is asking to resurrect a right that leaving destroys."""
        await _add_post(session, content=_plain(2000))
        await session.execute(sa_text(
            "UPDATE characters SET current_location_id = :l WHERE id = :c"
        ), {"l": OTHER_LOCATION_ID, "c": CHARACTER_ID})
        await session.commit()

        with pytest.raises(HTTPException) as exc:
            await _edit(
                session,
                content=_plain(2000),
                gates=[{"action_type": "combat", "targets": [4]}],
            )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Чтобы добавить намерение, нужно находиться в этой локации"
        assert (await session.execute(
            sa_text("SELECT COUNT(*) FROM post_gate_requests"))).scalar() == 0

    @pytest.mark.asyncio
    async def test_an_unknown_gate_type_is_refused(self, session):
        await _add_post(session, content=_plain(2000))
        with pytest.raises(HTTPException) as exc:
            await _edit(
                session,
                content=_plain(2000),
                gates=[{"action_type": "teleport", "targets": [1]}],
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == "Неизвестный тип гейта"

    @pytest.mark.asyncio
    async def test_a_gate_without_a_target_is_refused(self, session):
        await _add_post(session, content=_plain(2000))
        with pytest.raises(HTTPException) as exc:
            await _edit(
                session,
                content=_plain(2000),
                gates=[{"action_type": "combat", "targets": []}],
            )
        assert exc.value.status_code == 400
        assert "выберите цель" in exc.value.detail

    @pytest.mark.asyncio
    async def test_a_stranger_cannot_file_a_request_on_someone_elses_post(self, session):
        """Authorisation comes first: the 403 is about ownership, and nothing
        is written."""
        await _add_post(session, content=_plain(2000))
        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=POST_ID, content=_plain(2000),
                user_id=ADMIN_USER_ID, is_admin=False,
                gates=[{"action_type": "combat", "targets": [4]}],
            )
        assert exc.value.status_code == 403
        assert (await session.execute(
            sa_text("SELECT COUNT(*) FROM post_gate_requests"))).scalar() == 0


# ===========================================================================
# Layer 3 — review_gate_request: approval re-checks, refuses, grants nothing
# ===========================================================================

class TestApproveGrantsExactlyTheRequestedGates:

    @pytest.mark.asyncio
    async def test_approve_creates_the_gates_and_they_are_honoured(self, session):
        await _add_post(session, content=_plain(1000))
        req = await _add_request(
            session, POST_ID, [{"action_type": "combat", "targets": [11, 12]}]
        )

        result = await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)

        assert result["status"] == "approved"
        assert await _gate_rows(session) == [
            ("combat", 11, "open"), ("combat", 12, "open")
        ]
        assert await crud.check_action_gate(
            session, CHARACTER_ID, LOCATION_ID, "combat", 11
        ) is True
        assert await crud.check_action_gate(
            session, CHARACTER_ID, LOCATION_ID, "combat", 13
        ) is False

    @pytest.mark.asyncio
    async def test_approve_records_the_reviewer(self, session):
        await _add_post(session, content=_plain(1000))
        req = await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [11]}])
        await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        row = (await session.execute(sa_text(
            "SELECT reviewed_by_user_id, reviewed_at FROM post_gate_requests WHERE id = :r"
        ), {"r": req.id})).fetchone()
        assert row.reviewed_by_user_id == ADMIN_USER_ID
        assert row.reviewed_at is not None


class TestRejectCreatesNothing:

    @pytest.mark.asyncio
    async def test_reject_leaves_no_gate_rows(self, session):
        """FEAT-158's rule: a rejected decision grants no rights, not even
        partial ones."""
        await _add_post(session, content=_plain(1000))
        req = await _add_request(
            session, POST_ID, [{"action_type": "combat", "targets": [11, 12]}]
        )

        result = await crud.review_gate_request(session, req.id, "reject", ADMIN_USER_ID)

        assert result["status"] == "rejected"
        assert await _gate_row_count(session) == 0
        assert await crud.check_action_gate(
            session, CHARACTER_ID, LOCATION_ID, "combat", 11
        ) is False

    @pytest.mark.asyncio
    async def test_reject_works_even_when_approval_would_not(self, session):
        """A request whose post is gone can still be closed — that is the point
        of «заявку можно только отклонить»."""
        await _add_post(session, content=_plain(1000))
        req = await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [11]}])
        await session.execute(sa_text("DELETE FROM posts WHERE id = :p"), {"p": POST_ID})
        await session.commit()

        result = await crud.review_gate_request(session, req.id, "reject", ADMIN_USER_ID)
        assert result["status"] == "rejected"
        assert await _gate_row_count(session) == 0


class TestApproveRefusesRatherThanGrants:
    """Four re-checks, in the documented order. **Every refusal must leave zero
    gate rows** — a half-granted approval is the worst possible outcome."""

    @pytest.mark.asyncio
    async def test_a_request_already_reviewed_is_refused(self, session):
        await _add_post(session, content=_plain(1000))
        req = await _add_request(
            session, POST_ID, [{"action_type": "combat", "targets": [11]}],
            status="approved",
        )
        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        assert exc.value.status_code == 400
        assert exc.value.detail == "Заявка уже рассмотрена"
        assert await _gate_row_count(session) == 0

    @pytest.mark.asyncio
    async def test_an_expired_request_cannot_be_approved(self, session):
        """The request the player left behind when they walked away."""
        await _add_post(session, content=_plain(1000))
        req = await _add_request(
            session, POST_ID, [{"action_type": "combat", "targets": [11]}],
            status="expired",
        )
        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        assert exc.value.status_code == 400
        assert await _gate_row_count(session) == 0

    @pytest.mark.asyncio
    async def test_a_deleted_post_is_refused(self, session):
        """``post_id`` survives deletion as NULL (migration 037 policy); gates
        for a post that no longer exists would be rights nothing backs."""
        await _add_post(session, content=_plain(1000))
        req = await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [11]}])
        await session.execute(sa_text("DELETE FROM posts WHERE id = :p"), {"p": POST_ID})
        await session.commit()

        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        assert exc.value.status_code == 409
        assert exc.value.detail == "Пост удалён — заявку можно только отклонить"
        assert await _gate_row_count(session) == 0
        assert await _request_status(session, req.id) == "pending"

    @pytest.mark.asyncio
    async def test_a_character_who_left_the_location_is_refused(self, session):
        """Leaving a location is what kills gates; approval must not resurrect
        one. This is the defensive half of section 3.8 — the proactive half is
        ``expire_gate_requests``."""
        await _add_post(session, content=_plain(1000))
        req = await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [11]}])
        await session.execute(sa_text(
            "UPDATE characters SET current_location_id = :l WHERE id = :c"
        ), {"l": OTHER_LOCATION_ID, "c": CHARACTER_ID})
        await session.commit()

        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        assert exc.value.status_code == 409
        assert exc.value.detail == "Персонаж покинул локацию — заявка больше не действительна"
        assert await _gate_row_count(session) == 0

    @pytest.mark.asyncio
    async def test_a_post_shortened_after_the_request_is_refused(self, session):
        """The exploit the second check exists for: file a request against a
        2000-character post, cut it to 300, let the admin approve gates the text
        no longer pays for."""
        await _add_post(session, content=_plain(2000))
        req = await _add_request(
            session, POST_ID,
            [{"action_type": "combat", "targets": [11, 12, 13, 14, 15]}],
        )
        await session.execute(sa_text(
            "UPDATE posts SET content = :c WHERE id = :p"
        ), {"c": _plain(300), "p": POST_ID})
        await session.commit()

        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        assert exc.value.status_code == 409
        assert "минимум 1000" in exc.value.detail
        assert "сейчас: 300" in exc.value.detail
        assert await _gate_row_count(session) == 0
        assert await _request_status(session, req.id) == "pending"

    @pytest.mark.asyncio
    async def test_the_approval_budget_counts_the_posts_existing_gates(self, session):
        """The re-check is the *merged* budget, not just the request's own
        gates: three existing combat gates plus three requested need 1200."""
        await _add_post(session, content=_plain(1000))
        await _add_gates(session, POST_ID, "combat", [1, 2, 3])
        req = await _add_request(
            session, POST_ID, [{"action_type": "combat", "targets": [11, 12, 13]}]
        )

        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        assert exc.value.status_code == 409
        assert "минимум 1200" in exc.value.detail
        # Only the three pre-existing gates remain; none were added.
        assert len(await _gate_rows(session)) == 3

    @pytest.mark.asyncio
    async def test_the_request_under_review_is_not_counted_twice(self, session):
        """Its own gates must be excluded from the "other pending" list, or an
        approvable request would be charged twice and never approve."""
        await _add_post(session, content=_plain(1000))
        req = await _add_request(
            session, POST_ID,
            [{"action_type": "combat", "targets": [11, 12, 13, 14, 15]}],
        )
        result = await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        assert result["status"] == "approved"
        assert len(await _gate_rows(session)) == 5

    @pytest.mark.asyncio
    async def test_the_checks_run_in_the_documented_order(self, session):
        """A request that fails several checks reports the earliest one: still
        pending, then post alive, then location, then budget."""
        await _add_post(session, content=_plain(300))
        # Already reviewed AND the post is too short AND the character left.
        req = await _add_request(
            session, POST_ID,
            [{"action_type": "combat", "targets": [11, 12, 13, 14, 15]}],
            status="rejected",
        )
        await session.execute(sa_text(
            "UPDATE characters SET current_location_id = NULL WHERE id = :c"
        ), {"c": CHARACTER_ID})
        await session.commit()

        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        assert exc.value.detail == "Заявка уже рассмотрена"

    @pytest.mark.asyncio
    async def test_a_deleted_post_outranks_a_missing_character(self, session):
        await _add_post(session, content=_plain(1000))
        req = await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [11]}])
        await session.execute(sa_text("DELETE FROM posts WHERE id = :p"), {"p": POST_ID})
        await session.execute(sa_text(
            "UPDATE characters SET current_location_id = NULL WHERE id = :c"
        ), {"c": CHARACTER_ID})
        await session.commit()

        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        assert exc.value.detail == "Пост удалён — заявку можно только отклонить"

    @pytest.mark.asyncio
    async def test_a_missing_character_outranks_a_short_post(self, session):
        await _add_post(session, content=_plain(300))
        req = await _add_request(
            session, POST_ID,
            [{"action_type": "combat", "targets": [11, 12, 13, 14, 15]}],
        )
        await session.execute(sa_text(
            "UPDATE characters SET current_location_id = :l WHERE id = :c"
        ), {"l": OTHER_LOCATION_ID, "c": CHARACTER_ID})
        await session.commit()

        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, req.id, "approve", ADMIN_USER_ID)
        assert exc.value.detail == "Персонаж покинул локацию — заявка больше не действительна"

    @pytest.mark.asyncio
    async def test_an_unknown_request_is_404(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, 999999, "approve", ADMIN_USER_ID)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_an_unknown_action_is_400(self, session):
        await _add_post(session, content=_plain(1000))
        req = await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [11]}])
        with pytest.raises(HTTPException) as exc:
            await crud.review_gate_request(session, req.id, "grant", ADMIN_USER_ID)
        assert exc.value.status_code == 400
        assert await _gate_row_count(session) == 0


# ===========================================================================
# Layer 3b — lifecycle (section 3.8)
# ===========================================================================

class TestLeavingTheLocationExpiresTheRequest:

    @pytest.mark.asyncio
    async def test_a_pending_request_becomes_expired(self, session):
        await _add_post(session, content=_plain(1000))
        req = await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [11]}])

        await crud.expire_gate_requests(session, CHARACTER_ID, LOCATION_ID)

        assert await _request_status(session, req.id) == "expired"

    @pytest.mark.asyncio
    async def test_only_this_character_and_location_are_touched(self, session):
        await _add_post(session, content=_plain(1000))
        mine = await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [11]}])
        elsewhere = await _add_request(
            session, None, [{"action_type": "combat", "targets": [12]}],
            location_id=OTHER_LOCATION_ID,
        )
        someone_else = await _add_request(
            session, None, [{"action_type": "combat", "targets": [13]}],
            character_id=OTHER_CHARACTER_ID,
        )

        await crud.expire_gate_requests(session, CHARACTER_ID, LOCATION_ID)

        assert await _request_status(session, mine.id) == "expired"
        assert await _request_status(session, elsewhere.id) == "pending"
        assert await _request_status(session, someone_else.id) == "pending"

    @pytest.mark.asyncio
    async def test_an_already_reviewed_request_is_left_alone(self, session):
        """Expiring an approved request would rewrite a moderator's decision."""
        await _add_post(session, content=_plain(1000))
        approved = await _add_request(
            session, POST_ID, [{"action_type": "combat", "targets": [11]}],
            status="approved",
        )
        await crud.expire_gate_requests(session, CHARACTER_ID, LOCATION_ID)
        assert await _request_status(session, approved.id) == "approved"

    def test_both_movement_paths_expire_requests(self):
        """Gates are expired at two call sites (``move_and_post`` and
        ``quick_move``); a request left pending at either one would outlive the
        gates it is about."""
        for handler in (main_module.move_and_post, main_module.quick_move):
            source = inspect.getsource(handler)
            assert "expire_action_gates" in source
            assert "expire_gate_requests" in source, handler.__name__


class TestDeletingThePostClosesTheRequest:

    @pytest.mark.asyncio
    async def test_a_pending_request_is_rejected_when_the_post_is_deleted(self, session):
        """A pending request about a post that no longer exists can only ever be
        rejected — approving it would grant rights the text no longer backs."""
        await _add_post(session, content=_plain(1000))
        req = await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [11]}])

        await crud._close_sibling_moderation_rows(session, POST_ID, None, None, ADMIN_USER_ID)
        await session.commit()

        assert await _request_status(session, req.id) == "rejected"
        row = (await session.execute(sa_text(
            "SELECT reviewed_by_user_id FROM post_gate_requests WHERE id = :r"
        ), {"r": req.id})).fetchone()
        assert row.reviewed_by_user_id == ADMIN_USER_ID
        assert await _gate_row_count(session) == 0

    @pytest.mark.asyncio
    async def test_requests_on_other_posts_are_untouched(self, session):
        await _add_post(session, content=_plain(1000))
        await _add_post(session, post_id=POST_ID + 1, content=_plain(1000))
        mine = await _add_request(session, POST_ID, [{"action_type": "combat", "targets": [11]}])
        other = await _add_request(session, POST_ID + 1, [{"action_type": "combat", "targets": [12]}])

        await crud._close_sibling_moderation_rows(session, POST_ID, None, None, ADMIN_USER_ID)
        await session.commit()

        assert await _request_status(session, mine.id) == "rejected"
        assert await _request_status(session, other.id) == "pending"


# ===========================================================================
# Layer 3c — T10: pending_gates surfacing
# ===========================================================================

class TestPendingGatesSurfacing:

    @pytest.mark.asyncio
    async def test_only_pending_requests_are_reported(self, session):
        """Approved requests already show through ``action_gates``; rejected and
        expired ones grant nothing, so neither belongs in «на рассмотрении»."""
        for offset, status in enumerate(("pending", "approved", "rejected", "expired")):
            pid = POST_ID + offset
            await _add_post(session, post_id=pid, content=_plain(1000))
            await _add_request(
                session, pid, [{"action_type": "combat", "targets": [1]}], status=status
            )

        result = await crud.pending_gates_for_posts(
            session, [POST_ID, POST_ID + 1, POST_ID + 2, POST_ID + 3]
        )
        assert result == {POST_ID: {"combat": 1}}

    @pytest.mark.asyncio
    async def test_targets_are_counted_per_action_type(self, session):
        await _add_post(session, content=_plain(3000))
        await _add_request(session, POST_ID, [
            {"action_type": "combat", "targets": [1, 2, 3]},
            {"action_type": "gathering", "targets": [7]},
        ])
        result = await crud.pending_gates_for_posts(session, [POST_ID])
        assert result == {POST_ID: {"combat": 3, "gathering": 1}}

    @pytest.mark.asyncio
    async def test_an_empty_post_list_short_circuits(self, session):
        assert await crud.pending_gates_for_posts(session, []) == {}

    @pytest.mark.asyncio
    async def test_the_whole_feed_costs_exactly_one_query(self, session):
        """A per-post query here would put N round-trips on every location
        page — the reason this is a batch helper at all."""
        post_ids = []
        for offset in range(6):
            pid = POST_ID + offset
            post_ids.append(pid)
            await _add_post(session, post_id=pid, content=_plain(1000))
            await _add_request(session, pid, [{"action_type": "combat", "targets": [1]}])

        statements = []
        original = session.execute

        async def _counting(statement, *args, **kwargs):
            statements.append(statement)
            return await original(statement, *args, **kwargs)

        session.execute = _counting
        try:
            result = await crud.pending_gates_for_posts(session, post_ids)
        finally:
            session.execute = original

        assert len(statements) == 1
        assert len(result) == 6


# ===========================================================================
# Layer 4 — the two admin routes: permissions
# ===========================================================================

QUEUE_URL = "/locations/admin/moderation/gate-requests"
REVIEW_URL = "/locations/admin/moderation/gate-requests/1/review"
REVIEW_BODY = {"action": "reject"}
AUTH_HEADER = {"Authorization": "Bearer fake-token"}

# Admin holds every registered permission automatically; moderator holds both
# moderation permissions through user-service migration 0027.
ADMIN_ME = {"id": 1, "username": "admin", "role": "admin",
            "permissions": ["moderation:read", "moderation:review", "users:manage"]}
MODERATOR_ME = {"id": 2, "username": "mod", "role": "moderator",
                "permissions": ["moderation:read", "moderation:review"]}
READ_ONLY_ME = {"id": 3, "username": "readonly", "role": "moderator",
                "permissions": ["moderation:read"]}
PLAYER_ME = {"id": 4, "username": "player", "role": "user", "permissions": []}


def _me(payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


def _request_row(**overrides):
    row = {
        "id": 1,
        "post_id": POST_ID,
        "user_id": AUTHOR_USER_ID,
        "character_id": CHARACTER_ID,
        "location_id": LOCATION_ID,
        "gates": [{"action_type": "combat", "targets": [11]}],
        "status": "pending",
        "created_at": datetime(2026, 9, 13, 12, 0, 0),
        "reviewed_at": None,
        "post_content": "Текст поста",
        "post_character_name": "Скиталец",
        "post_location_name": "Бар «Три Галки»",
        "requester_username": "player",
        "targets_resolved": {"combat": [{"id": 11, "name": "Крыса", "state": "моб"}]},
    }
    row.update(overrides)
    return row


@pytest.fixture()
def admin_client():
    async def _fake_get_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _fake_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestGateRequestModerationPermissions:
    """``moderation:read`` / ``moderation:review``, exactly as the deletion and
    report queues. FEAT-158 deliberately kept **moderators** on these
    endpoints; narrowing them to admin-only here would be a silent regression,
    so that is asserted explicitly."""

    def test_no_token_is_401(self, admin_client):
        assert admin_client.get(QUEUE_URL).status_code == 401
        assert admin_client.put(REVIEW_URL, json=REVIEW_BODY).status_code == 401

    @patch("auth_http.requests.get")
    def test_a_rejected_token_is_401(self, mock_get, admin_client):
        mock_get.return_value = _me({}, status_code=401)
        assert admin_client.get(QUEUE_URL, headers=AUTH_HEADER).status_code == 401
        assert admin_client.put(
            REVIEW_URL, json=REVIEW_BODY, headers=AUTH_HEADER
        ).status_code == 401

    @patch("auth_http.requests.get")
    def test_a_player_without_the_permission_is_403(self, mock_get, admin_client):
        mock_get.return_value = _me(PLAYER_ME)
        with patch("main.crud.get_pending_gate_requests", new_callable=AsyncMock) as q, \
             patch("main.crud.review_gate_request", new_callable=AsyncMock) as r:
            assert admin_client.get(QUEUE_URL, headers=AUTH_HEADER).status_code == 403
            assert admin_client.put(
                REVIEW_URL, json=REVIEW_BODY, headers=AUTH_HEADER
            ).status_code == 403
        q.assert_not_called()
        r.assert_not_called()

    @patch("auth_http.requests.get")
    def test_an_admin_may_read_and_review(self, mock_get, admin_client):
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_pending_gate_requests", new_callable=AsyncMock,
                   return_value=[_request_row()]), \
             patch("main.crud.review_gate_request", new_callable=AsyncMock,
                   return_value=_request_row(status="rejected")):
            assert admin_client.get(QUEUE_URL, headers=AUTH_HEADER).status_code == 200
            assert admin_client.put(
                REVIEW_URL, json=REVIEW_BODY, headers=AUTH_HEADER
            ).status_code == 200

    @patch("auth_http.requests.get")
    def test_a_moderator_may_read_and_review_too(self, mock_get, admin_client):
        """FEAT-158 preserved moderator access on purpose — these endpoints use
        ``require_permission``, not ``get_strict_admin_user``."""
        mock_get.return_value = _me(MODERATOR_ME)
        with patch("main.crud.get_pending_gate_requests", new_callable=AsyncMock,
                   return_value=[_request_row()]), \
             patch("main.crud.review_gate_request", new_callable=AsyncMock,
                   return_value=_request_row(status="approved")) as review:
            assert admin_client.get(QUEUE_URL, headers=AUTH_HEADER).status_code == 200
            r = admin_client.put(
                REVIEW_URL, json={"action": "approve"}, headers=AUTH_HEADER
            )
        assert r.status_code == 200
        # The reviewer recorded is the moderator, not a hardcoded admin.
        assert review.await_args.args[3] == MODERATOR_ME["id"]

    @patch("auth_http.requests.get")
    def test_read_permission_alone_cannot_review(self, mock_get, admin_client):
        mock_get.return_value = _me(READ_ONLY_ME)
        with patch("main.crud.get_pending_gate_requests", new_callable=AsyncMock,
                   return_value=[]), \
             patch("main.crud.review_gate_request", new_callable=AsyncMock) as review:
            assert admin_client.get(QUEUE_URL, headers=AUTH_HEADER).status_code == 200
            r = admin_client.put(REVIEW_URL, json=REVIEW_BODY, headers=AUTH_HEADER)
        assert r.status_code == 403
        review.assert_not_called()

    @patch("auth_http.requests.get")
    def test_the_queue_carries_the_gate_payload_and_resolved_targets(self, mock_get, admin_client):
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_pending_gate_requests", new_callable=AsyncMock,
                   return_value=[_request_row()]):
            body = admin_client.get(QUEUE_URL, headers=AUTH_HEADER).json()
        assert body[0]["gates"] == [{"action_type": "combat", "targets": [11]}]
        assert body[0]["targets_resolved"]["combat"][0]["name"] == "Крыса"
        assert body[0]["post_content"] == "Текст поста"

    @patch("auth_http.requests.get")
    def test_enrichment_degrading_to_nothing_does_not_break_the_queue(self, mock_get, admin_client):
        """``targets_resolved`` is a hint, never a validation (section 3.9): a
        failed resolve must leave the card renderable."""
        mock_get.return_value = _me(ADMIN_ME)
        bare = _request_row(
            targets_resolved={}, post_character_name=None,
            requester_username=None, post_location_name=None,
        )
        with patch("main.crud.get_pending_gate_requests", new_callable=AsyncMock,
                   return_value=[bare]):
            r = admin_client.get(QUEUE_URL, headers=AUTH_HEADER)
        assert r.status_code == 200
        assert r.json()[0]["targets_resolved"] == {}

    @patch("auth_http.requests.get")
    def test_a_request_whose_post_was_deleted_still_renders(self, mock_get, admin_client):
        """``post_id`` is NULL after deletion (migration 037 policy) and the
        schema must accept that rather than 500 the whole queue."""
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_pending_gate_requests", new_callable=AsyncMock,
                   return_value=[_request_row(post_id=None, post_content=None)]):
            r = admin_client.get(QUEUE_URL, headers=AUTH_HEADER)
        assert r.status_code == 200
        assert r.json()[0]["post_id"] is None

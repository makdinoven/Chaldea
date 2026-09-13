"""FEAT-158 task 9 — deleting a post revokes the rights that post granted.

Bug 3 of the feature: a post is the thing that *justifies* an action. Moderation
deleted the post with a bulk ``delete(Post)``, which bypasses ORM cascades, and
``action_gates.post_id`` is ``ON DELETE SET NULL`` — so the gate rows survived
the deletion still ``open``. The player kept the right to attack, gather or enter
a dungeon on the strength of a post that had just been removed for being abusive.
In other words: the punishment did not punish.

``crud.expire_action_gates_for_post`` closes that, and these tests pin the four
decisions the design made explicitly (section 3.4):

* ``open`` gates become ``expired`` — the row is kept as an audit trail of what
  was granted and revoked, it is not deleted;
* ``consumed`` gates are left alone — the action already fired, and rewriting
  that history would corrupt the record;
* gates belonging to **other** posts are untouched;
* ``reject`` / ``dismiss`` revoke nothing — the post survives, so its gates must
  survive with it.

Layer-1 style (real in-memory aiosqlite with ``PRAGMA foreign_keys=ON``), because
the atomicity claim — the revocation and the delete share one transaction — is a
database fact that a mocked session cannot demonstrate.
"""

import asyncio
import os
import sys
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, event, select, text as sa_text
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
from models import (  # noqa: E402
    ActionGate,
    Location,
    Post,
    PostDeletionRequest,
    PostReport,
)


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


LOCATION_ID = 10
CHARACTER_ID = 100
OTHER_CHARACTER_ID = 101
AUTHOR_USER_ID = 5
MODERATOR_USER_ID = 77


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    """In-memory async SQLite with the tables the revocation path touches."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_setup(dbapi_conn, _record):  # pragma: no cover - connection hook
        # FK enforcement is the point: the post delete must null action_gates.post_id.
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        # `_close_sibling_moderation_rows` writes raw MySQL `NOW()`.
        dbapi_conn.create_function(
            "NOW", 0,
            lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )

    async with engine.begin() as conn:
        # `Locations` references Regions/Districts; SQLite refuses to write a
        # table whose parents are missing even when the column is NULL.
        for ddl in (
            'CREATE TABLE "Regions" (id INTEGER PRIMARY KEY)',
            'CREATE TABLE "Districts" (id INTEGER PRIMARY KEY)',
        ):
            await conn.execute(sa_text(ddl))
        for table in (
            Location.__table__,
            Post.__table__,
            ActionGate.__table__,
            PostDeletionRequest.__table__,
            PostReport.__table__,
        ):
            await conn.run_sync(table.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        s.add(Location(
            id=LOCATION_ID, name="Бар «Три Галки»", type="location",
            recommended_level=1, quick_travel_marker=False, description="d",
            marker_type="safe", sort_order=0, is_starting=False,
        ))
        await s.commit()
        yield s

    await engine.dispose()


async def _add_post(session, post_id: int) -> Post:
    post = Post(
        id=post_id, character_id=CHARACTER_ID, location_id=LOCATION_ID,
        content="Боевой пост", post_type="combat",
    )
    session.add(post)
    await session.commit()
    return post


async def _add_gate(session, post_id, status="open", action_type="combat",
                    character_id=CHARACTER_ID) -> int:
    gate = ActionGate(
        character_id=character_id, location_id=LOCATION_ID, post_id=post_id,
        action_type=action_type, target_ref=1, status=status,
    )
    session.add(gate)
    await session.commit()
    await session.refresh(gate)
    return gate.id


async def _gate_row(session, gate_id):
    """Read a gate's (status, post_id) straight from the database."""
    result = await session.execute(
        sa_text("SELECT status, post_id FROM action_gates WHERE id = :i"),
        {"i": gate_id},
    )
    return result.fetchone()


async def _post_exists(session, post_id) -> bool:
    result = await session.execute(select(Post).where(Post.id == post_id))
    return result.scalars().first() is not None


async def _add_deletion_request(session, post_id) -> int:
    req = PostDeletionRequest(
        post_id=post_id, user_id=AUTHOR_USER_ID, reason="Опечатка", status="pending",
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req.id


async def _add_report(session, post_id) -> int:
    report = PostReport(
        post_id=post_id, user_id=AUTHOR_USER_ID + 1, reason="Абуз", status="pending",
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report.id


# ===========================================================================
# 1. The primitive itself
# ===========================================================================

@pytest.mark.asyncio
class TestExpireActionGatesForPost:
    """`expire_action_gates_for_post` in isolation."""

    async def test_open_gates_become_expired(self, session):
        await _add_post(session, 1)
        gate_id = await _add_gate(session, 1, status="open")

        await crud.expire_action_gates_for_post(session, 1)
        await session.commit()

        status, post_id = await _gate_row(session, gate_id)
        assert status == "expired"
        # The row survives — it is the audit trail of what was granted and revoked.
        assert post_id == 1

    async def test_consumed_gates_are_untouched(self, session):
        await _add_post(session, 2)
        gate_id = await _add_gate(session, 2, status="consumed")

        await crud.expire_action_gates_for_post(session, 2)
        await session.commit()

        status, _ = await _gate_row(session, gate_id)
        assert status == "consumed"

    async def test_already_expired_gates_stay_expired(self, session):
        await _add_post(session, 3)
        gate_id = await _add_gate(session, 3, status="expired")

        await crud.expire_action_gates_for_post(session, 3)
        await session.commit()

        status, _ = await _gate_row(session, gate_id)
        assert status == "expired"

    async def test_other_posts_are_unaffected(self, session):
        await _add_post(session, 4)
        await _add_post(session, 5)
        target = await _add_gate(session, 4, status="open")
        bystander = await _add_gate(session, 5, status="open")

        await crud.expire_action_gates_for_post(session, 4)
        await session.commit()

        assert (await _gate_row(session, target))[0] == "expired"
        assert (await _gate_row(session, bystander))[0] == "open"

    async def test_every_open_gate_of_the_post_is_revoked(self, session):
        """One post can grant several rights (combat + gathering + npc)."""
        await _add_post(session, 6)
        ids = [
            await _add_gate(session, 6, action_type="combat"),
            await _add_gate(session, 6, action_type="gathering"),
            await _add_gate(session, 6, action_type="npc_dialogue"),
        ]

        await crud.expire_action_gates_for_post(session, 6)
        await session.commit()

        for gate_id in ids:
            assert (await _gate_row(session, gate_id))[0] == "expired"

    async def test_does_not_commit_on_its_own(self, session):
        """Revocation must ride the caller's transaction so it can roll back
        together with the delete — the helper committing would break atomicity."""
        await _add_post(session, 7)
        gate_id = await _add_gate(session, 7, status="open")

        await crud.expire_action_gates_for_post(session, 7)
        await session.rollback()

        status, _ = await _gate_row(session, gate_id)
        assert status == "open", "the helper committed; the rollback was ignored"


# ===========================================================================
# 2. Through the moderation review paths
# ===========================================================================

@pytest.mark.asyncio
class TestGateRevocationThroughModeration:
    """The two code paths that can delete a post."""

    async def test_approving_a_deletion_request_revokes_the_gates(self, session):
        await _add_post(session, 11)
        open_gate = await _add_gate(session, 11, status="open")
        consumed_gate = await _add_gate(session, 11, status="consumed")
        request_id = await _add_deletion_request(session, 11)

        await crud.review_deletion_request(
            session, request_id, "approve", MODERATOR_USER_ID
        )

        open_status, open_post_id = await _gate_row(session, open_gate)
        assert open_status == "expired"
        # The post is gone, so the FK has nulled the link.
        assert open_post_id is None
        assert (await _gate_row(session, consumed_gate))[0] == "consumed"
        assert not await _post_exists(session, 11)

    async def test_resolving_a_report_revokes_the_gates(self, session):
        await _add_post(session, 12)
        open_gate = await _add_gate(session, 12, status="open")
        consumed_gate = await _add_gate(session, 12, status="consumed")
        report_id = await _add_report(session, 12)

        await crud.review_report(session, report_id, "resolve", MODERATOR_USER_ID)

        assert (await _gate_row(session, open_gate))[0] == "expired"
        assert (await _gate_row(session, consumed_gate))[0] == "consumed"
        assert not await _post_exists(session, 12)

    async def test_rejecting_a_deletion_request_revokes_nothing(self, session):
        """The post survives, so the rights it granted survive with it."""
        await _add_post(session, 13)
        gate_id = await _add_gate(session, 13, status="open")
        request_id = await _add_deletion_request(session, 13)

        await crud.review_deletion_request(
            session, request_id, "reject", MODERATOR_USER_ID
        )

        status, post_id = await _gate_row(session, gate_id)
        assert status == "open"
        assert post_id == 13
        assert await _post_exists(session, 13)

    async def test_dismissing_a_report_revokes_nothing(self, session):
        await _add_post(session, 14)
        gate_id = await _add_gate(session, 14, status="open")
        report_id = await _add_report(session, 14)

        await crud.review_report(session, report_id, "dismiss", MODERATOR_USER_ID)

        assert (await _gate_row(session, gate_id))[0] == "open"
        assert await _post_exists(session, 14)

    async def test_another_players_gates_are_not_collateral_damage(self, session):
        """Only the deleted post's gates go — a second player standing in the
        same location with their own post keeps their rights."""
        await _add_post(session, 15)
        await _add_post(session, 16)
        doomed = await _add_gate(session, 15, status="open")
        neighbour = await _add_gate(
            session, 16, status="open", character_id=OTHER_CHARACTER_ID
        )
        request_id = await _add_deletion_request(session, 15)

        await crud.review_deletion_request(
            session, request_id, "approve", MODERATOR_USER_ID
        )

        assert (await _gate_row(session, doomed))[0] == "expired"
        neighbour_status, neighbour_post = await _gate_row(session, neighbour)
        assert neighbour_status == "open"
        assert neighbour_post == 16
        assert await _post_exists(session, 16)

    async def test_revocation_and_deletion_are_one_transaction(self, session):
        """If the delete fails, the revocation must not stand on its own.

        Driven directly against the primitive + delete pair, because the review
        handler commits: what is asserted here is that nothing in the pair
        commits early, so a rollback takes both halves with it.
        """
        from sqlalchemy import delete as sa_delete

        await _add_post(session, 17)
        gate_id = await _add_gate(session, 17, status="open")

        await crud.expire_action_gates_for_post(session, 17)
        await session.execute(sa_delete(Post).where(Post.id == 17))
        await session.rollback()

        status, post_id = await _gate_row(session, gate_id)
        assert status == "open"
        assert post_id == 17
        assert await _post_exists(session, 17)

    async def test_approving_an_orphaned_request_revokes_nothing(self, session):
        """A row whose post is already NULL has no gates to find."""
        await _add_post(session, 18)
        gate_id = await _add_gate(session, 18, status="open")
        request_id = await _add_deletion_request(session, None)

        await crud.review_deletion_request(
            session, request_id, "approve", MODERATOR_USER_ID
        )

        assert (await _gate_row(session, gate_id))[0] == "open"
        assert await _post_exists(session, 18)

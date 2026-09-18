"""FEAT-168, review #2 gap 2 — quest completion end to end, on a REAL session.

The XP-book work put a cross-service HTTP call on the quest reward path. The
previous tests could not see what that did to the session:

  * the guard tests handed `add_experience` an `AsyncMock()` session — and
    `AsyncMock().new` is a truthy child mock, so the branch that frees the DB
    connection (and with it the branch that expires the caller's ORM objects)
    never ran;
  * the endpoint tests mocked `crud.add_experience` away and passed a plain
    `MagicMock` quest, which has no expiry semantics at all.

The blocker that shipped green through both: an XP-only quest
(`reward_exp > 0`, `reward_currency == 0`) blew up **after** the XP was written
and **before** `complete_quest_record`, so the player got the XP and the quest
stayed `active` — infinitely re-completable. A gold-bearing quest survived only
because the currency write left the session dirty and skipped the risky branch.

So these tests run the real route function against a real aiosqlite
`AsyncSession` with real `crud`, and assert the two halves of the outcome
together: **XP awarded AND the quest marked completed**. Only the network is
mocked (`crud.httpx.AsyncClient`, the cumulative-stats call), because the
network is the contract; everything else is the code under test.

Deliberately structure-agnostic: nothing here patches or asserts on a helper
name, so it keeps working whichever shape the reward path settles on.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, event, text
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
import main  # noqa: E402
import schemas  # noqa: E402
from models import CharacterQuest, CharacterQuestProgress, Quest, QuestObjective  # noqa: E402


# ---------------------------------------------------------------------------
# SQLite DDL hooks (same as test_post_drafts.py)
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


CHARACTER_ID = 100
USER_ID = 5
QUEST_ID = 42
NPC_ID = 9
START_XP = 1000
START_GOLD = 250

# Cross-service tables locations-service writes but does not own.
_CROSS_SERVICE_DDL = (
    """CREATE TABLE characters (
           id INTEGER PRIMARY KEY,
           user_id INTEGER,
           currency_balance INTEGER NOT NULL DEFAULT 0
       )""",
    """CREATE TABLE character_attributes (
           character_id INTEGER PRIMARY KEY,
           passive_experience INTEGER NOT NULL DEFAULT 0,
           active_experience INTEGER NOT NULL DEFAULT 0
       )""",
    """CREATE TABLE gold_transactions (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           character_id INTEGER NOT NULL,
           amount INTEGER NOT NULL,
           balance_after INTEGER NOT NULL,
           transaction_type TEXT NOT NULL,
           source TEXT,
           metadata TEXT,
           created_at TIMESTAMP
       )""",
)


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    """Real in-memory async SQLite with the quest tables and the cross-service
    tables the reward path writes to."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    # `complete_quest_record` uses MySQL's NOW(); teach SQLite the same name
    # (the repo already does this in inventory-service's conftest).
    @event.listens_for(engine.sync_engine, "connect")
    def _register_now(dbapi_conn, _record):  # pragma: no cover - DDL hook
        dbapi_conn.create_function(
            "NOW", 0, lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        )

    async with engine.begin() as conn:
        await conn.run_sync(Quest.__table__.create)
        await conn.run_sync(QuestObjective.__table__.create)
        await conn.run_sync(CharacterQuest.__table__.create)
        await conn.run_sync(CharacterQuestProgress.__table__.create)
        for ddl in _CROSS_SERVICE_DDL:
            await conn.execute(text(ddl))

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        await s.execute(
            text("INSERT INTO characters (id, user_id, currency_balance) "
                 "VALUES (:cid, :uid, :bal)"),
            {"cid": CHARACTER_ID, "uid": USER_ID, "bal": START_GOLD},
        )
        await s.execute(
            text("INSERT INTO character_attributes "
                 "(character_id, passive_experience, active_experience) "
                 "VALUES (:cid, :xp, 0)"),
            {"cid": CHARACTER_ID, "xp": START_XP},
        )
        await s.commit()
        yield s

    await engine.dispose()


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

async def _seed_quest(session, *, reward_exp, reward_currency,
                      reward_items=None, all_objectives_done=True):
    quest = Quest(
        id=QUEST_ID, npc_id=NPC_ID, title="Принести сведения",
        description="Поговорить со связным", quest_type="standard", min_level=1,
        reward_currency=reward_currency, reward_exp=reward_exp,
        reward_items=reward_items, is_active=True,
    )
    objective = QuestObjective(
        id=1, quest_id=QUEST_ID, description="Поговорить",
        objective_type="talk_npc", target_id=NPC_ID, target_count=1, sort_order=0,
    )
    cq = CharacterQuest(id=1, character_id=CHARACTER_ID, quest_id=QUEST_ID,
                        status="active")
    progress = CharacterQuestProgress(
        id=1, character_quest_id=1, objective_id=1,
        current_count=1 if all_objectives_done else 0,
        is_completed=all_objectives_done,
    )
    session.add_all([quest, objective, cq, progress])
    await session.commit()
    return quest


async def _read_xp(session):
    result = await session.execute(
        text("SELECT passive_experience FROM character_attributes WHERE character_id = :cid"),
        {"cid": CHARACTER_ID},
    )
    return int(result.fetchone()[0])


async def _read_quest_status(session):
    result = await session.execute(
        text("SELECT status FROM character_quests WHERE character_id = :cid "
             "AND quest_id = :qid"),
        {"cid": CHARACTER_ID, "qid": QUEST_ID},
    )
    row = result.fetchone()
    return row[0] if row else None


async def _read_gold(session):
    result = await session.execute(
        text("SELECT currency_balance FROM characters WHERE id = :cid"),
        {"cid": CHARACTER_ID},
    )
    return int(result.fetchone()[0])


def _multiplier_client(multiplier=1.0, *, fail=False):
    """A stand-in for `httpx.AsyncClient` used as an async context manager —
    the only seam these tests mock, because it is the service boundary."""
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"multiplier": multiplier})

    client = AsyncMock()
    if fail:
        client.get = AsyncMock(side_effect=RuntimeError("inventory-service недоступен"))
    else:
        client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, client


class _Ctx:
    """Patches every OUTBOUND call of the route and nothing else."""

    def __init__(self, multiplier=1.0, fail=False):
        self.factory, self.client = _multiplier_client(multiplier, fail=fail)
        self._patchers = [
            patch.object(crud.httpx, "AsyncClient", self.factory),
            patch.object(main.httpx, "AsyncClient", self.factory),
            patch.object(main, "verify_character_ownership", AsyncMock(return_value=None)),
            patch.object(main, "_track_cumulative_stats", AsyncMock(return_value=None)),
        ]

    def __enter__(self):
        for p in self._patchers:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patchers):
            p.stop()


async def _complete(session, multiplier=1.0, fail=False):
    body = schemas.QuestCompleteRequest(character_id=CHARACTER_ID)
    user = MagicMock()
    user.id = USER_ID
    with _Ctx(multiplier, fail=fail) as ctx:
        result = await main.complete_quest(
            quest_id=QUEST_ID, body=body, request=MagicMock(),
            session=session, current_user=user,
        )
    return result, ctx


# ═══════════════════════════════════════════════════════════════════════════
# The blocker: an XP-only quest
# ═══════════════════════════════════════════════════════════════════════════

class TestXpOnlyQuest:
    """`reward_exp > 0`, `reward_currency == 0` — the shape that shipped broken."""

    @pytest.mark.asyncio
    async def test_xp_awarded_and_quest_marked_completed(self, session):
        await _seed_quest(session, reward_exp=100, reward_currency=0)

        result, _ = await _complete(session)

        assert result["success"] is True
        assert await _read_xp(session) == START_XP + 100
        assert await _read_quest_status(session) == "completed", \
            "the quest must not stay active — that made it re-completable forever"

    @pytest.mark.asyncio
    async def test_the_quest_cannot_be_completed_twice(self, session):
        """The player-visible consequence of the blocker: infinite XP."""
        await _seed_quest(session, reward_exp=100, reward_currency=0)
        await _complete(session)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as excinfo:
            await _complete(session)
        assert excinfo.value.status_code == 404
        assert await _read_xp(session) == START_XP + 100, \
            "a second completion must not award the XP again"

    @pytest.mark.asyncio
    async def test_the_book_multiplier_is_applied_and_reported(self, session):
        await _seed_quest(session, reward_exp=100, reward_currency=0)

        result, _ = await _complete(session, multiplier=1.35)

        assert await _read_xp(session) == START_XP + 135
        assert result["reward_exp"] == 135, "the player is shown what they got"
        assert await _read_quest_status(session) == "completed"

    @pytest.mark.asyncio
    async def test_truncation_matches_the_profession_xp_rule(self, session):
        await _seed_quest(session, reward_exp=101, reward_currency=0)
        result, _ = await _complete(session, multiplier=1.25)
        assert await _read_xp(session) == START_XP + 126   # int(101 * 1.25)
        assert result["reward_exp"] == 126

    @pytest.mark.asyncio
    async def test_fail_open_still_completes_the_quest(self, session):
        """inventory-service down: base XP, and the quest still closes."""
        await _seed_quest(session, reward_exp=100, reward_currency=0)

        result, _ = await _complete(session, fail=True)

        assert await _read_xp(session) == START_XP + 100
        assert result["reward_exp"] == 100
        assert await _read_quest_status(session) == "completed"

    @pytest.mark.asyncio
    async def test_the_quest_object_is_still_readable_after_the_xp_award(self, session):
        """The direct cause of the blocker: the reward path must not expire the
        ORM objects the route loaded. The route reads `quest.reward_items` and
        `quest.reward_currency` AFTER awarding XP, so a response that carries
        them proves the objects survived."""
        await _seed_quest(session, reward_exp=100, reward_currency=0,
                          reward_items=[{"item_id": 7, "quantity": 2}])

        result, ctx = await _complete(session)

        assert result["reward_items"] == [{"item_id": 7, "quantity": 2}]
        assert result["reward_currency"] == 0
        assert result["new_balance"] is None
        assert await _read_quest_status(session) == "completed"
        # The reward item really was requested from inventory-service.
        assert ctx.client.post.await_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# The shape that accidentally worked — it must keep working
# ═══════════════════════════════════════════════════════════════════════════

class TestGoldBearingQuest:

    @pytest.mark.asyncio
    async def test_gold_and_xp_and_completion_all_land(self, session):
        await _seed_quest(session, reward_exp=100, reward_currency=50)

        result, _ = await _complete(session, multiplier=1.35)

        assert await _read_gold(session) == START_GOLD + 50
        assert await _read_xp(session) == START_XP + 135
        assert await _read_quest_status(session) == "completed"
        assert result["reward_currency"] == 50
        assert result["new_balance"] == START_GOLD + 50
        assert result["reward_exp"] == 135

    @pytest.mark.asyncio
    async def test_gold_is_never_multiplied_by_an_xp_book(self, session):
        await _seed_quest(session, reward_exp=100, reward_currency=50)
        await _complete(session, multiplier=2.0)
        assert await _read_gold(session) == START_GOLD + 50

    @pytest.mark.asyncio
    async def test_gold_only_quest_completes_without_touching_xp(self, session):
        await _seed_quest(session, reward_exp=0, reward_currency=50)

        result, _ = await _complete(session, multiplier=2.0)

        assert await _read_xp(session) == START_XP
        assert result["reward_exp"] == 0
        assert await _read_gold(session) == START_GOLD + 50
        assert await _read_quest_status(session) == "completed"


# ═══════════════════════════════════════════════════════════════════════════
# Refusals must leave the world alone
# ═══════════════════════════════════════════════════════════════════════════

class TestRefusals:

    @pytest.mark.asyncio
    async def test_incomplete_objectives_award_nothing(self, session):
        await _seed_quest(session, reward_exp=100, reward_currency=50,
                          all_objectives_done=False)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as excinfo:
            await _complete(session)

        assert excinfo.value.status_code == 400
        assert await _read_xp(session) == START_XP
        assert await _read_gold(session) == START_GOLD
        assert await _read_quest_status(session) == "active"

    @pytest.mark.asyncio
    async def test_no_active_quest_is_a_404(self, session):
        await _seed_quest(session, reward_exp=100, reward_currency=0)
        await session.execute(
            text("UPDATE character_quests SET status = 'completed' WHERE id = 1"))
        await session.commit()

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as excinfo:
            await _complete(session)
        assert excinfo.value.status_code == 404
        assert await _read_xp(session) == START_XP

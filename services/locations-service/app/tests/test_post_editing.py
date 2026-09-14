"""FEAT-159 task T4 — post editing (Phase A): the two limits, the «изменено»
marker, and the guarantee that editing never pays XP.

Three layers, the same split as ``test_post_moderation.py`` / ``test_post_drafts.py``:

1. **``crud.edit_post`` against real in-memory aiosqlite.** The two limits are
   *database* facts, not Python branches, and a mocked session can assert neither:

   * "nobody posted after it" is ``WHERE location_id = :loc AND id > :pid`` —
     an **ordering** fact. The whole point of using ``id >`` rather than
     ``created_at >`` is that two posts can share a one-second MySQL
     ``TIMESTAMP``; proving that requires two real rows that actually share a
     timestamp and differ only by autoincrement id
     (``test_same_second_later_post_still_blocks_the_edit``).
   * the hour is evaluated **in SQL against ``NOW()``**, never in Python,
     because ``posts.created_at`` is a naive MySQL ``TIMESTAMP``. Feeding the
     function a hand-made row would paper over exactly the naive/aware bug the
     design calls out, so the fixture stores real rows and lets the database
     decide.

   Two SQL constructs have no SQLite spelling — ``FOR UPDATE`` and
   ``NOW() - INTERVAL ? HOUR``. They are translated at the **cursor** level by a
   ``before_cursor_execute`` hook, so ``crud.edit_post`` itself runs completely
   untouched and the translation is deliberately narrow: it rewrites the
   interval arithmetic into the SQLite equivalent (still evaluated by the
   database, still against the database clock, still against the stored naive
   timestamp) and drops the row lock, which SQLite does not need because the
   in-memory database is single-connection. Nothing about ``id >`` is touched.

2. **The route through ``TestClient`` with ``crud.edit_post`` mocked.** Status
   codes, the response contract and the authorisation matrix — in particular
   that a **moderator is not an admin** here: the route checks
   ``role == "admin"`` rather than using ``get_admin_user`` (which admits
   moderators), so a moderator editing someone else's post must get 403.

3. **``crud.get_post_details``** — the derived ``edited_by_admin`` flag, with the
   character-service profile call mocked, including the degrade-to-``False``
   path when that lookup fails.

Mocking style follows ``conftest.py`` (env vars + patched engine),
``test_rbac_enforcement.py`` (``patch("auth_http.requests.get")``) and
``test_post_moderation.py`` (``_httpx_client`` for the profile downstream).
"""

import asyncio
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
from models import ActionGate, Location, Post, PostGateRequest, PostVersion  # noqa: E402
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


LOCATION_ID = 40
OTHER_LOCATION_ID = 41
CHARACTER_ID = 400
OTHER_CHARACTER_ID = 401
ADMIN_CHARACTER_ID = 402
AUTHOR_USER_ID = 9
STRANGER_USER_ID = 10
ADMIN_USER_ID = 11

# Long enough to clear MIN_POST_LENGTH (300 chars after stripping HTML).
LONG_TEXT = "Скиталец молча оглядывает зал, считая тени на стенах. " * 8
ORIGINAL_TEXT = "Исходный текст поста. " * 20

# `NOW() - INTERVAL ? HOUR` -> the SQLite equivalent, same single bound param in
# the same position, still evaluated by the database against the stored naive
# timestamp. `FOR UPDATE` is dropped: the in-memory database has one connection.
_INTERVAL_RE = re.compile(r"NOW\(\)\s*-\s*INTERVAL\s*\?\s*HOUR", re.IGNORECASE)
_FOR_UPDATE_RE = re.compile(r"\s+FOR\s+UPDATE\s*$", re.IGNORECASE)


def _sqlite_translate(statement: str) -> str:
    statement = _INTERVAL_RE.sub(
        "datetime('now', '-' || ? || ' hours')", statement
    )
    return _FOR_UPDATE_RE.sub("", statement)


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    """In-memory async SQLite holding the tables ``edit_post`` actually touches.

    ``characters`` is created as a bare stub: ``edit_post`` reads
    ``SELECT user_id FROM characters`` with raw SQL even though the table belongs
    to character-service and has no model here. That cross-service raw read is
    part of the behaviour under test (it decides ownership), so it is backed by a
    real table rather than mocked away.

    ``action_gates`` is a real table too, and for the same reason: the symbol
    budget of section 3.6 is read from it with raw SQL
    (``crud.gate_list_for_post``) and is the single thing standing between a
    player and the "buy five gates with 1000 characters, then cut the post to
    307" exploit. Mocking that read would test the mock.
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
            "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER)",
        ):
            await conn.execute(sa_text(ddl))
        for table in (
            Location.__table__, Post.__table__, ActionGate.__table__,
            # Phase B: `edit_post` reads pending gate requests for the budget
            # (section 3.6 rule 2) and writes one when gates are requested.
            PostGateRequest.__table__,
            # FEAT-160: `edit_post` snapshots the pre-edit text here, in the
            # same transaction. Real table, not a mock — the snapshot is the
            # whole point of the history and must be observable.
            PostVersion.__table__,
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
            "INSERT INTO characters (id, user_id) "
            "VALUES (:a, :au), (:b, :bu), (:c, :cu)"
        ), {"a": CHARACTER_ID, "au": AUTHOR_USER_ID,
            "b": OTHER_CHARACTER_ID, "bu": STRANGER_USER_ID,
            "c": ADMIN_CHARACTER_ID, "cu": ADMIN_USER_ID})
        await s.commit()
        yield s

    await engine.dispose()


async def _add_post(
    session,
    post_id: int,
    *,
    character_id: int = CHARACTER_ID,
    location_id: int = LOCATION_ID,
    content: str = ORIGINAL_TEXT,
    minutes_ago: int = 0,
    created_at: datetime | None = None,
    edited_at: datetime | None = None,
    edited_by_user_id: int | None = None,
) -> Post:
    """Insert a post with a real ``created_at`` the database will compare itself."""
    when = created_at or (datetime.utcnow() - timedelta(minutes=minutes_ago))
    post = Post(
        id=post_id, character_id=character_id, location_id=location_id,
        content=content, post_type="regular", created_at=when,
        edited_at=edited_at, edited_by_user_id=edited_by_user_id,
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
    """Give a post real ``action_gates`` rows — one per target, exactly the way
    ``crud.create_action_gates`` writes them."""
    for target in targets:
        session.add(ActionGate(
            character_id=character_id, location_id=location_id, post_id=post_id,
            action_type=action_type, target_ref=target, status=status,
        ))
    await session.commit()


def _plain(length: int) -> str:
    """Plain text of exactly ``length`` characters after HTML stripping."""
    return "а" * length


async def _reload(session, post_id: int) -> Post:
    result = await session.execute(
        select(Post).where(Post.id == post_id).execution_options(populate_existing=True)
    )
    return result.scalars().first()


def _no_outbound_http():
    """An ``httpx.AsyncClient`` replacement that fails loudly if anything calls out.

    Editing must not talk to any other service — no XP award, no party bonus, no
    transaction log.
    """
    def _boom(*_args, **_kwargs):  # pragma: no cover - only runs on failure
        raise AssertionError("edit_post must not make outbound HTTP calls")

    return _boom


# ===========================================================================
# Layer 1 — crud.edit_post against real aiosqlite
# ===========================================================================

@pytest.mark.asyncio
class TestOwnerCanEdit:
    async def test_owner_edits_the_latest_post_inside_the_window(self, session):
        await _add_post(session, 1, minutes_ago=5)

        result = await crud.edit_post(
            session, post_id=1, content=LONG_TEXT,
            user_id=AUTHOR_USER_ID, is_admin=False,
        )

        assert result["id"] == 1
        assert result["content"] == LONG_TEXT
        # `length` is the PLAIN length, built with `crud.strip_html_tags` — the
        # same helper behind post XP and the gate budgets. For this plain text
        # that differs from `len(LONG_TEXT)` only by the trailing space the
        # helper's `.strip()` drops.
        assert result["length"] == len(crud.strip_html_tags(LONG_TEXT))
        assert result["edited_at"] is not None
        # The author edited it — the marker must not accuse an admin.
        assert result["edited_by_admin"] is False

    async def test_edited_at_is_written_and_created_at_is_untouched(self, session):
        created = datetime.utcnow() - timedelta(minutes=30)
        await _add_post(session, 2, created_at=created)
        before = await _reload(session, 2)
        created_before = before.created_at

        await crud.edit_post(
            session, post_id=2, content=LONG_TEXT,
            user_id=AUTHOR_USER_ID, is_admin=False,
        )

        after = await _reload(session, 2)
        assert after.content == LONG_TEXT
        assert after.edited_at is not None
        assert after.edited_by_user_id == AUTHOR_USER_ID
        # The edit window is measured from publication; moving created_at would
        # silently renew it.
        assert after.created_at == created_before

    async def test_a_post_in_another_location_does_not_block_the_edit(self, session):
        await _add_post(session, 3, minutes_ago=5)
        await _add_post(session, 4, location_id=OTHER_LOCATION_ID, minutes_ago=1)

        result = await crud.edit_post(
            session, post_id=3, content=LONG_TEXT,
            user_id=AUTHOR_USER_ID, is_admin=False,
        )
        assert result["content"] == LONG_TEXT

    async def test_a_previous_post_in_the_same_location_does_not_block(self, session):
        """The limit is «nobody posted AFTER it», i.e. `id >` — a lower id is fine."""
        await _add_post(session, 5, minutes_ago=20)
        await _add_post(session, 6, minutes_ago=5)

        result = await crud.edit_post(
            session, post_id=6, content=LONG_TEXT,
            user_id=AUTHOR_USER_ID, is_admin=False,
        )
        assert result["content"] == LONG_TEXT


@pytest.mark.asyncio
class TestLaterPostLimit:
    async def test_someone_posted_after_it_is_403(self, session):
        await _add_post(session, 11, minutes_ago=5)
        await _add_post(session, 12, character_id=OTHER_CHARACTER_ID, minutes_ago=1)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=11, content=LONG_TEXT,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == (
            "После этого поста уже написали — редактирование недоступно"
        )
        assert (await _reload(session, 11)).content == ORIGINAL_TEXT

    async def test_same_second_later_post_still_blocks_the_edit(self, session):
        """The reason the check is `id >` and not `created_at >`.

        ``posts.created_at`` is a one-second MySQL ``TIMESTAMP``: two posts made
        in the same second are indistinguishable by time. Here both rows carry
        the *identical* timestamp and differ only by autoincrement id — which is
        exactly how the feed orders them (``get_posts_by_location`` sorts by
        ``id DESC``). Swap the implementation to ``created_at >`` and this test
        fails, letting a player rewrite a post someone has already answered.
        """
        same_moment = datetime.utcnow() - timedelta(minutes=2)
        await _add_post(session, 21, created_at=same_moment)
        await _add_post(session, 22, character_id=OTHER_CHARACTER_ID,
                        created_at=same_moment)

        row_a, row_b = await _reload(session, 21), await _reload(session, 22)
        assert row_a.created_at == row_b.created_at, "fixture must share the timestamp"

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=21, content=LONG_TEXT,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )

        assert exc.value.status_code == 403
        assert "уже написали" in exc.value.detail

    async def test_own_later_post_blocks_it_too(self, session):
        """The rule is about the location's flow, not about who wrote the reply."""
        await _add_post(session, 23, minutes_ago=5)
        await _add_post(session, 24, minutes_ago=1)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=23, content=LONG_TEXT,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
class TestHourWindow:
    async def test_expired_window_is_403(self, session):
        await _add_post(session, 31, minutes_ago=120)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=31, content=LONG_TEXT,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == (
            "Редактировать пост можно в течение часа после публикации"
        )
        assert (await _reload(session, 31)).content == ORIGINAL_TEXT
        assert (await _reload(session, 31)).edited_at is None

    async def test_just_inside_the_window_is_allowed(self, session):
        await _add_post(session, 32, minutes_ago=59)

        result = await crud.edit_post(
            session, post_id=32, content=LONG_TEXT,
            user_id=AUTHOR_USER_ID, is_admin=False,
        )
        assert result["content"] == LONG_TEXT

    async def test_just_outside_the_window_is_refused(self, session):
        await _add_post(session, 33, minutes_ago=61)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=33, content=LONG_TEXT,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 403

    async def test_a_previous_edit_does_not_extend_the_window(self, session):
        """The window is measured from publication and never consults
        ``edited_at`` — otherwise each edit would renew it forever."""
        await _add_post(
            session, 34, minutes_ago=120,
            edited_at=datetime.utcnow(), edited_by_user_id=AUTHOR_USER_ID,
        )

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=34, content=LONG_TEXT,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 403
        assert "в течение часа после публикации" in exc.value.detail

    async def test_the_window_is_decided_by_the_database_clock(self, session):
        """Guard against the check migrating into Python.

        ``posts.created_at`` is a **naive** timestamp written by the database's
        own ``NOW()``. Comparing it in Python against an aware
        ``datetime.now(timezone.utc)`` is the classic naive/aware bug and would
        shift the window by the container's UTC offset. Asserting that the two
        stored posts straddle the boundary the *database* computes pins the
        comparison where it belongs.
        """
        await _add_post(session, 35, minutes_ago=10)
        await _add_post(session, 36, location_id=OTHER_LOCATION_ID, minutes_ago=200)

        verdicts = (await session.execute(sa_text(
            "SELECT id, (created_at > NOW() - INTERVAL :hours HOUR) AS within_window "
            "FROM posts WHERE id IN (35, 36) ORDER BY id"
        ), {"hours": crud.POST_EDIT_WINDOW_HOURS})).fetchall()

        assert [bool(row.within_window) for row in verdicts] == [True, False]


@pytest.mark.asyncio
class TestAuthorisation:
    async def test_a_stranger_cannot_edit_someone_elses_post(self, session):
        await _add_post(session, 41, minutes_ago=5)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=41, content=LONG_TEXT,
                user_id=STRANGER_USER_ID, is_admin=False,
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == "Вы можете редактировать только свои посты"
        assert (await _reload(session, 41)).content == ORIGINAL_TEXT

    async def test_a_stranger_is_refused_even_when_every_limit_would_pass(self, session):
        """The stranger branch is independent of the two limits: a fresh, last
        post — one that no limit would refuse — is still not editable by someone
        who did not write it and is not an admin."""
        await _add_post(session, 42, minutes_ago=1)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=42, content=LONG_TEXT,
                user_id=STRANGER_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Вы можете редактировать только свои посты"

    async def test_missing_post_is_404(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=999999, content=LONG_TEXT,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Пост не найден"

    async def test_unknown_author_character_is_not_treated_as_owner(self, session):
        """A post whose character row is gone must not become editable by
        whoever happens to ask — ``author_user_id is None`` is not ownership."""
        await _add_post(session, 43, character_id=88888, minutes_ago=1)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=43, content=LONG_TEXT,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
class TestAdminBypass:
    async def test_admin_edits_a_stale_post_someone_answered(self, session):
        """Both limits at once: two hours old *and* replied to."""
        await _add_post(session, 51, minutes_ago=180)
        await _add_post(session, 52, character_id=OTHER_CHARACTER_ID, minutes_ago=5)

        result = await crud.edit_post(
            session, post_id=51, content=LONG_TEXT,
            user_id=ADMIN_USER_ID, is_admin=True,
        )

        assert result["content"] == LONG_TEXT
        assert result["edited_by_admin"] is True
        stored = await _reload(session, 51)
        assert stored.edited_by_user_id == ADMIN_USER_ID
        assert stored.edited_at is not None

    async def test_admin_edit_records_the_admin_not_the_author(self, session):
        await _add_post(session, 53, minutes_ago=5)

        await crud.edit_post(
            session, post_id=53, content=LONG_TEXT,
            user_id=ADMIN_USER_ID, is_admin=True,
        )

        stored = await _reload(session, 53)
        assert stored.edited_by_user_id == ADMIN_USER_ID
        assert stored.character_id == CHARACTER_ID

    async def test_admin_edits_their_own_stale_and_answered_post(self, session):
        """**User ruling of 2026-09-13: «Админ должен править и свои посты без
        ограничений.»** (FEAT-159 section 3.3, superseding the original
        ordering.)

        The admin branch is evaluated *before* the ownership branch, so role
        ``admin`` bypasses both limits unconditionally — on their own posts just
        as on other people's. This post is three hours old **and** has a later
        post after it in the same location: both limits would refuse the same
        edit from a plain owner (asserted in
        ``test_the_same_own_post_is_refused_to_a_plain_owner``), and the admin
        still gets a 200.

        Do not "fix" this back to a 403: the original design did test ownership
        first, which left an admin subject to both limits on their own post, and
        the user overruled it.

        Note the flag: ``edited_by_admin`` is False here because the admin *is*
        the author, so the post is marked plainly «изменено». That is
        intentional (3.3), not a bug.
        """
        await _add_post(session, 54, character_id=ADMIN_CHARACTER_ID,
                        minutes_ago=180)
        await _add_post(session, 56, character_id=OTHER_CHARACTER_ID,
                        minutes_ago=5)

        result = await crud.edit_post(
            session, post_id=54, content=LONG_TEXT,
            user_id=ADMIN_USER_ID, is_admin=True,
        )

        assert result["content"] == LONG_TEXT
        assert result["edited_at"] is not None
        # The author edited it — plain «изменено», not «администратором».
        assert result["edited_by_admin"] is False
        stored = await _reload(session, 54)
        assert stored.content == LONG_TEXT
        assert stored.edited_at is not None
        # The audit column still records the actual editor.
        assert stored.edited_by_user_id == ADMIN_USER_ID

    async def test_the_same_own_post_is_refused_to_a_plain_owner(self, session):
        """The control for the test above: the identical situation with
        ``is_admin=False``. Without this pair the bypass test could pass because
        the limits stopped working rather than because the admin cleared them."""
        await _add_post(session, 57, minutes_ago=180)
        await _add_post(session, 58, character_id=OTHER_CHARACTER_ID,
                        minutes_ago=5)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=57, content=LONG_TEXT,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 403
        assert (await _reload(session, 57)).content == ORIGINAL_TEXT

    async def test_admin_editing_their_own_fresh_post_is_also_a_plain_marker(self, session):
        """Ownership, not the hour, decides the marker: on the happy path too an
        admin editing their own post is «изменено», never «администратором»."""
        await _add_post(session, 59, character_id=ADMIN_CHARACTER_ID, minutes_ago=5)

        result = await crud.edit_post(
            session, post_id=59, content=LONG_TEXT,
            user_id=ADMIN_USER_ID, is_admin=True,
        )
        assert result["edited_by_admin"] is False
        assert (await _reload(session, 59)).edited_by_user_id == ADMIN_USER_ID

    async def test_a_moderator_gets_no_bypass_at_the_crud_layer(self, session):
        """A moderator is deliberately **not** an admin here: the route checks
        ``role == "admin"`` rather than ``get_admin_user`` (which admits
        moderators), so a moderator reaches this function with
        ``is_admin=False`` and takes the stranger branch even on a post that no
        limit would have saved anyway.

        The route half of the same rule is
        ``TestEditRouteAdminFlag::test_a_moderator_editing_another_players_post_is_403``.
        """
        await _add_post(session, 60, minutes_ago=180)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=60, content=LONG_TEXT,
                user_id=STRANGER_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Вы можете редактировать только свои посты"
        assert (await _reload(session, 60)).content == ORIGINAL_TEXT
        assert (await _reload(session, 60)).edited_at is None


@pytest.mark.asyncio
class TestContentValidation:
    async def test_too_short_content_is_400_and_nothing_is_written(self, session):
        await _add_post(session, 61, minutes_ago=5)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=61, content="Коротко.",
                user_id=AUTHOR_USER_ID, is_admin=False,
            )

        assert exc.value.status_code == 400
        assert "Минимальная длина поста" in exc.value.detail
        stored = await _reload(session, 61)
        assert stored.content == ORIGINAL_TEXT
        assert stored.edited_at is None

    async def test_length_is_measured_after_stripping_html(self, session):
        """Markup must not buy length: a tag-heavy but short post is refused."""
        await _add_post(session, 62, minutes_ago=5)
        markup = "<p><b><i><span style='color:red'>" + ("а" * 50) + "</span></i></b></p>"

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=62, content=markup,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 400

    async def test_the_admin_bypass_does_not_skip_the_length_check(self, session):
        await _add_post(session, 63, minutes_ago=500)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=63, content="Коротко.",
                user_id=ADMIN_USER_ID, is_admin=True,
            )
        assert exc.value.status_code == 400

    async def test_the_length_check_survives_on_the_admins_own_post(self, session):
        """The branch the 2026-09-13 ruling moved. An admin editing their *own*
        stale post now walks past both editing limits — the bypass must not
        swallow the content validation on the way past."""
        await _add_post(session, 66, character_id=ADMIN_CHARACTER_ID,
                        minutes_ago=500)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=66, content="Коротко.",
                user_id=ADMIN_USER_ID, is_admin=True,
            )

        assert exc.value.status_code == 400
        assert "Минимальная длина поста" in exc.value.detail
        stored = await _reload(session, 66)
        assert stored.content == ORIGINAL_TEXT
        assert stored.edited_at is None

    async def test_sql_injection_in_content_is_stored_verbatim(self, session):
        """Security: the content is a bound parameter, never concatenated."""
        await _add_post(session, 64, minutes_ago=5)
        payload = "'; DROP TABLE posts; -- " + LONG_TEXT

        result = await crud.edit_post(
            session, post_id=64, content=payload,
            user_id=AUTHOR_USER_ID, is_admin=False,
        )

        assert result["content"] == payload
        assert (await _reload(session, 64)).content == payload
        # The table is still there, with the row still in it.
        survivors = (await session.execute(
            sa_text("SELECT COUNT(*) FROM posts")
        )).scalar()
        assert survivors >= 1

    async def test_script_payload_is_not_mangled_by_the_backend(self, session):
        """XSS sanitisation is the client's job (DOMPurify) and storage stays raw
        HTML — the edit path must not invent a second, different policy."""
        await _add_post(session, 65, minutes_ago=5)
        payload = "<script>alert(1)</script>" + LONG_TEXT

        result = await crud.edit_post(
            session, post_id=65, content=payload,
            user_id=AUTHOR_USER_ID, is_admin=False,
        )
        assert result["content"] == payload


@pytest.mark.asyncio
class TestGateSymbolBudget:
    """FEAT-159 section 3.6 — the exploit named in section 1 and found live in
    review #1 (issue #1).

    Gates are bought with **text length** (200 characters per ``combat`` target,
    500 for every other intent, floored at ``MIN_POST_LENGTH``). Before the fix,
    ``edit_post`` checked only the general minimum, so a 1000-character post
    could buy five combat gates and then be edited down to 307 characters: the
    gates stayed, the text that paid for them did not. Reproduced live —
    200 OK, and ``client/details`` still reported ``gates: {combat: 5}``.

    The budget is read from ``action_gates`` (``crud.gate_list_for_post``),
    never from a request payload, so it does not matter which endpoint created
    the post.
    """

    async def test_five_combat_gates_cannot_be_shrunk_below_their_budget(self, session):
        """The exploit itself. Five ``combat`` targets cost 5 x 200 = 1000."""
        await _add_post(session, 101, minutes_ago=5, content=_plain(1000))
        await _add_gates(session, 101, "combat", [501, 502, 503, 504, 505])

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=101, content=_plain(307),
                user_id=AUTHOR_USER_ID, is_admin=False,
            )

        assert exc.value.status_code == 400
        assert exc.value.detail == (
            "Для всех действий этого поста нужно минимум 1000 символов (сейчас: 307)"
        )
        # Not just the status code: the rejection must leave the row alone.
        stored = await _reload(session, 101)
        assert stored.content == _plain(1000)
        assert stored.edited_at is None
        assert stored.edited_by_user_id is None
        # And the gates the post bought are never revoked by a refused edit.
        remaining = (await session.execute(sa_text(
            "SELECT COUNT(*) FROM action_gates WHERE post_id = 101"
        ))).scalar()
        assert remaining == 5

    async def test_expired_gates_still_count(self, session):
        """The subtle half, and the reason ``gate_list_for_post`` reads **all**
        statuses.

        Gates are set to ``expired`` when the character leaves the location
        (``crud.expire_action_gates``). If only ``open`` rows counted, the
        exploit would simply grow a step: buy five gates, walk next door and
        back so all five expire, then edit the text down and "re-buy" against
        the same 1000 characters. The post bought those gates; leaving the room
        does not refund the budget.
        """
        await _add_post(session, 102, minutes_ago=5, content=_plain(1000))
        await _add_gates(session, 102, "combat", [501, 502, 503, 504, 505],
                         status="expired")

        # Precondition: nothing is `open` any more — the refund scenario exactly.
        open_rows = (await session.execute(sa_text(
            "SELECT COUNT(*) FROM action_gates "
            "WHERE post_id = 102 AND status = 'open'"
        ))).scalar()
        assert open_rows == 0

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=102, content=_plain(307),
                user_id=AUTHOR_USER_ID, is_admin=False,
            )

        assert exc.value.status_code == 400
        assert "минимум 1000 символов" in exc.value.detail
        assert (await _reload(session, 102)).content == _plain(1000)
        assert (await _reload(session, 102)).edited_at is None

    async def test_consumed_gates_still_count(self, session):
        """A gate that already fired is the most spent of all — the mechanic ran.
        ``consumed`` rows count for the same reason ``expired`` ones do."""
        await _add_post(session, 103, minutes_ago=5, content=_plain(1000))
        await _add_gates(session, 103, "combat", [501, 502, 503, 504, 505],
                         status="consumed")

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=103, content=_plain(999),
                user_id=AUTHOR_USER_ID, is_admin=False,
            )

        assert exc.value.status_code == 400
        assert "минимум 1000 символов" in exc.value.detail
        assert (await _reload(session, 103)).edited_at is None

    async def test_mixed_statuses_are_all_charged(self, session):
        """One of each: the sum is over the whole gate set, not over a subset."""
        await _add_post(session, 104, minutes_ago=5, content=_plain(1000))
        await _add_gates(session, 104, "combat", [501, 502], status="open")
        await _add_gates(session, 104, "combat", [503], status="consumed")
        await _add_gates(session, 104, "combat", [504, 505], status="expired")

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=104, content=_plain(800),
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 400
        assert "минимум 1000 символов" in exc.value.detail

    async def test_gates_of_another_post_are_not_charged(self, session):
        """The budget is per post. A neighbouring post's gates must not make
        this one unshrinkable — the control for the tests above."""
        await _add_post(session, 105, minutes_ago=20, content=_plain(1000))
        await _add_gates(session, 105, "combat", [501, 502, 503, 504, 505])
        await _add_post(session, 106, minutes_ago=5, content=_plain(1000))

        result = await crud.edit_post(
            session, post_id=106, content=_plain(300),
            user_id=AUTHOR_USER_ID, is_admin=False,
        )
        assert result["content"] == _plain(300)

    async def test_exactly_the_required_length_is_accepted(self, session):
        """The boundary is exact — 1000 characters pays for five combat gates.

        The submitted text is 1000 characters of a DIFFERENT letter, not a copy
        of the stored one: since FEAT-160 (3.7) byte-identical content is a
        no-op, and re-submitting `_plain(1000)` verbatim would leave `edited_at`
        null for a reason that has nothing to do with the budget rule this test
        is about. Rewriting the whole post to exactly the required length is the
        case that must pass — same boundary, still a real edit.
        """
        await _add_post(session, 107, minutes_ago=5, content=_plain(1000))
        await _add_gates(session, 107, "combat", [501, 502, 503, 504, 505])

        rewritten = "б" * 1000
        assert rewritten != _plain(1000), "the edit must be a real change, not a no-op"

        result = await crud.edit_post(
            session, post_id=107, content=rewritten,
            user_id=AUTHOR_USER_ID, is_admin=False,
        )

        assert result["length"] == 1000
        assert result["edited_at"] is not None
        assert (await _reload(session, 107)).edited_at is not None

    async def test_one_character_short_is_refused(self, session):
        """The other side of the same boundary: 999 is not 1000."""
        await _add_post(session, 108, minutes_ago=5, content=_plain(1000))
        await _add_gates(session, 108, "combat", [501, 502, 503, 504, 505])

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=108, content=_plain(999),
                user_id=AUTHOR_USER_ID, is_admin=False,
            )

        assert exc.value.status_code == 400
        assert exc.value.detail == (
            "Для всех действий этого поста нужно минимум 1000 символов (сейчас: 999)"
        )
        assert (await _reload(session, 108)).edited_at is None

    async def test_growing_the_post_is_always_fine(self, session):
        """The budget is a floor, not a target — a longer edit is accepted."""
        await _add_post(session, 109, minutes_ago=5, content=_plain(1000))
        await _add_gates(session, 109, "combat", [501, 502, 503, 504, 505])

        result = await crud.edit_post(
            session, post_id=109, content=_plain(2500),
            user_id=AUTHOR_USER_ID, is_admin=False,
        )
        assert result["length"] == 2500

    async def test_the_budget_counts_the_expensive_intents_too(self, session):
        """``pvp`` / ``gathering`` / ``dungeon`` / ``npc_dialogue`` cost 500 per
        target, so a mixed post is not charged at the cheap combat rate."""
        await _add_post(session, 110, minutes_ago=5, content=_plain(1500))
        await _add_gates(session, 110, "npc_dialogue", [601])
        await _add_gates(session, 110, "combat", [602, 603])

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=110, content=_plain(899),
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        # 500 (npc_dialogue x 1) + 200 x 2 (combat) = 900.
        assert exc.value.status_code == 400
        assert exc.value.detail == (
            "Для всех действий этого поста нужно минимум 900 символов (сейчас: 899)"
        )

        result = await crud.edit_post(
            session, post_id=110, content=_plain(900),
            user_id=AUTHOR_USER_ID, is_admin=False,
        )
        assert result["length"] == 900

    async def test_a_targetless_gate_still_costs_one_target(self, session):
        """``target_ref`` is nullable. ``required_symbols_for_gates`` charges
        ``max(1, len(targets))``, and ``merge_gate_lists`` keeps ``None`` as a
        distinct member, so such a gate is charged — and charged once."""
        await _add_post(session, 111, minutes_ago=5, content=_plain(1000))
        await _add_gates(session, 111, "gathering", [None, None])

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=111, content=_plain(499),
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == (
            "Для всех действий этого поста нужно минимум 500 символов (сейчас: 499)"
        )

    async def test_the_budget_length_is_measured_after_stripping_html(self, session):
        """Markup must not buy gates either: a tag-padded body is still 307
        characters of text."""
        await _add_post(session, 112, minutes_ago=5, content=_plain(1000))
        await _add_gates(session, 112, "combat", [501, 502, 503, 504, 505])
        markup = "<p><b>" + _plain(307) + "</b></p>" + "<span></span>" * 60

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=112, content=markup,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 400
        assert "(сейчас: 307)" in exc.value.detail

    async def test_an_admin_gets_the_same_400(self, session):
        """**The 2026-09-13 ruling frees an admin from the hour and the "someone
        posted after" limits — not from content validation.** The gate budget is
        content validation, exactly like the minimum-length check, so an admin
        editing someone else's post is refused identically.
        """
        await _add_post(session, 113, minutes_ago=300, content=_plain(1000))
        await _add_gates(session, 113, "combat", [501, 502, 503, 504, 505])
        await _add_post(session, 114, character_id=OTHER_CHARACTER_ID, minutes_ago=5)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=113, content=_plain(307),
                user_id=ADMIN_USER_ID, is_admin=True,
            )

        assert exc.value.status_code == 400
        assert exc.value.detail == (
            "Для всех действий этого поста нужно минимум 1000 символов (сейчас: 307)"
        )
        stored = await _reload(session, 113)
        assert stored.content == _plain(1000)
        assert stored.edited_at is None
        assert stored.edited_by_user_id is None

    async def test_an_admin_editing_their_own_gated_post_is_bound_too(self, session):
        await _add_post(session, 115, character_id=ADMIN_CHARACTER_ID,
                        minutes_ago=300, content=_plain(1000))
        await _add_gates(session, 115, "combat", [501, 502, 503, 504, 505],
                         character_id=ADMIN_CHARACTER_ID)

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=115, content=_plain(999),
                user_id=ADMIN_USER_ID, is_admin=True,
            )
        assert exc.value.status_code == 400
        assert "минимум 1000 символов" in exc.value.detail

    async def test_a_post_without_gates_only_faces_the_general_minimum(self, session):
        """Nothing changed for the ordinary post: 300 passes, 299 is refused —
        and with the *minimum-length* wording, not the gate one, so the player
        is told which rule stopped them."""
        await _add_post(session, 116, minutes_ago=5)

        result = await crud.edit_post(
            session, post_id=116, content=_plain(300),
            user_id=AUTHOR_USER_ID, is_admin=False,
        )
        assert result["length"] == 300

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(
                session, post_id=116, content=_plain(299),
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == (
            "Минимальная длина поста — 300 символов (сейчас: 299)"
        )
        assert "действий этого поста" not in exc.value.detail

    async def test_a_gate_belonging_to_no_post_is_not_charged(self, session):
        """``action_gates.post_id`` is ``ON DELETE SET NULL``, so orphan rows
        exist. They must not attach themselves to whatever post is being
        edited."""
        await _add_post(session, 117, minutes_ago=5)
        session.add(ActionGate(
            character_id=CHARACTER_ID, location_id=LOCATION_ID, post_id=None,
            action_type="combat", target_ref=501, status="open",
        ))
        await session.commit()

        result = await crud.edit_post(
            session, post_id=117, content=_plain(300),
            user_id=AUTHOR_USER_ID, is_admin=False,
        )
        assert result["length"] == 300

    async def test_gate_list_for_post_reads_every_status(self, session):
        """``gate_list_for_post`` directly: one merged entry, three targets, the
        statuses irrelevant."""
        await _add_post(session, 118, minutes_ago=5, content=_plain(1000))
        await _add_gates(session, 118, "combat", [501], status="open")
        await _add_gates(session, 118, "combat", [502], status="consumed")
        await _add_gates(session, 118, "combat", [503], status="expired")

        gates = await crud.gate_list_for_post(session, 118)

        assert gates == [{"action_type": "combat", "targets": [501, 502, 503]}]
        assert crud.required_symbols_for_gates(gates) == 600

    async def test_gate_list_for_post_is_empty_for_a_gateless_post(self, session):
        await _add_post(session, 119, minutes_ago=5)
        assert await crud.gate_list_for_post(session, 119) == []


@pytest.mark.asyncio
class TestNoExperienceOnEdit:
    """The rule the whole feature hangs on: editing is not an XP farm."""

    async def test_no_xp_is_awarded_and_no_service_is_called(self, session):
        await _add_post(session, 71, minutes_ago=5)

        with patch("crud.award_post_xp_and_log", new_callable=AsyncMock) as award, \
             patch("crud.calculate_post_xp") as calc, \
             patch("crud.httpx.AsyncClient", side_effect=_no_outbound_http()):
            await crud.edit_post(
                session, post_id=71, content=LONG_TEXT,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )

        award.assert_not_called()
        calc.assert_not_called()

    async def test_growing_the_post_by_a_thousand_characters_pays_nothing(self, session):
        """The exact farming route: publish short, edit long, collect. Twice."""
        await _add_post(session, 72, minutes_ago=5)

        with patch("crud.award_post_xp_and_log", new_callable=AsyncMock) as award, \
             patch("crud.calculate_post_xp") as calc:
            await crud.edit_post(
                session, post_id=72, content=LONG_TEXT * 3,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )
            await crud.edit_post(
                session, post_id=72, content=LONG_TEXT * 6,
                user_id=AUTHOR_USER_ID, is_admin=False,
            )

        award.assert_not_called()
        calc.assert_not_called()

    async def test_an_admin_edit_pays_nothing_either(self, session):
        await _add_post(session, 73, minutes_ago=300)

        with patch("crud.award_post_xp_and_log", new_callable=AsyncMock) as award:
            await crud.edit_post(
                session, post_id=73, content=LONG_TEXT * 3,
                user_id=ADMIN_USER_ID, is_admin=True,
            )
        award.assert_not_called()

    async def test_an_admin_growing_their_own_old_post_pays_nothing(self, session):
        """The route the 2026-09-13 ruling opened: an admin may now rewrite
        their own hours-old post at will. That must not become the XP farm the
        hour window was closing — XP is never recomputed, on any path."""
        await _add_post(session, 74, character_id=ADMIN_CHARACTER_ID,
                        minutes_ago=600)

        with patch("crud.award_post_xp_and_log", new_callable=AsyncMock) as award, \
             patch("crud.calculate_post_xp") as calc, \
             patch("crud.httpx.AsyncClient", side_effect=_no_outbound_http()):
            await crud.edit_post(
                session, post_id=74, content=LONG_TEXT * 4,
                user_id=ADMIN_USER_ID, is_admin=True,
            )
            await crud.edit_post(
                session, post_id=74, content=LONG_TEXT * 8,
                user_id=ADMIN_USER_ID, is_admin=True,
            )

        award.assert_not_called()
        calc.assert_not_called()


# ===========================================================================
# Layer 2 — the route: status codes, contract and the access matrix
# ===========================================================================

EDIT_URL = "/locations/posts/77"
AUTH_HEADER = {"Authorization": "Bearer token"}
BODY = {"content": LONG_TEXT}

ADMIN_ME = {"id": ADMIN_USER_ID, "username": "admin", "role": "admin",
            "permissions": ["moderation:read", "moderation:review"]}
MODERATOR_ME = {"id": 12, "username": "mod", "role": "moderator",
                "permissions": ["moderation:read", "moderation:review"]}
EDITOR_ME = {"id": 13, "username": "editor", "role": "editor", "permissions": []}
PLAYER_ME = {"id": AUTHOR_USER_ID, "username": "player", "role": "user",
             "permissions": []}


def _me(payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


def _edit_result(**overrides):
    row = {
        "id": 77,
        "content": LONG_TEXT,
        "length": len(LONG_TEXT),
        "created_at": datetime(2026, 9, 13, 12, 0, 0),
        "edited_at": datetime(2026, 9, 13, 12, 30, 0),
        "edited_by_admin": False,
    }
    row.update(overrides)
    return row


@pytest.fixture()
def edit_client():
    async def _fake_get_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _fake_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestEditRouteContract:
    def test_no_token_is_401(self, edit_client):
        assert edit_client.put(EDIT_URL, json=BODY).status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_is_401(self, mock_get, edit_client):
        mock_get.return_value = _me({}, status_code=401)
        assert edit_client.put(
            EDIT_URL, json=BODY, headers=AUTH_HEADER
        ).status_code == 401

    @patch("auth_http.requests.get")
    def test_owner_gets_the_documented_response_shape(self, mock_get, edit_client):
        mock_get.return_value = _me(PLAYER_ME)
        with patch("main.crud.edit_post", new_callable=AsyncMock,
                   return_value=_edit_result()):
            r = edit_client.put(EDIT_URL, json=BODY, headers=AUTH_HEADER)

        assert r.status_code == 200
        body = r.json()
        # The exact key set is the point of this test — an extra field is a
        # contract change, not a detail. Phase B added exactly two, both
        # additive and both `None` when the edit asked for no gates (3.2).
        assert set(body) == {
            "id", "content", "length", "created_at", "edited_at", "edited_by_admin",
            "gate_request_id", "gate_request_status",
        }
        assert body["id"] == 77
        assert body["edited_by_admin"] is False
        assert body["gate_request_id"] is None
        assert body["gate_request_status"] is None
        # edited_by_user_id is an audit field and must never reach the client.
        assert "edited_by_user_id" not in body

    @patch("auth_http.requests.get")
    def test_missing_content_is_422(self, mock_get, edit_client):
        mock_get.return_value = _me(PLAYER_ME)
        with patch("main.crud.edit_post", new_callable=AsyncMock) as edit:
            r = edit_client.put(EDIT_URL, json={}, headers=AUTH_HEADER)
        assert r.status_code == 422
        edit.assert_not_called()

    @patch("auth_http.requests.get")
    def test_the_route_is_not_shadowed_by_the_draft_route(self, mock_get, edit_client):
        """``PUT /locations/{location_id}/draft`` has a literal second segment,
        so ``PUT /locations/posts/{id}`` must reach its own handler."""
        mock_get.return_value = _me(PLAYER_ME)
        with patch("main.crud.edit_post", new_callable=AsyncMock,
                   return_value=_edit_result()) as edit:
            edit_client.put(EDIT_URL, json=BODY, headers=AUTH_HEADER)
        edit.assert_awaited_once()
        assert edit.await_args.kwargs["post_id"] == 77

    @pytest.mark.parametrize("status_code,detail", [
        (403, "После этого поста уже написали — редактирование недоступно"),
        (403, "Редактировать пост можно в течение часа после публикации"),
        (403, "Вы можете редактировать только свои посты"),
        (404, "Пост не найден"),
        (400, "Минимальная длина поста — 300 символов (сейчас: 8)"),
    ])
    @patch("auth_http.requests.get")
    def test_rejections_surface_as_real_status_codes_in_russian(
        self, mock_get, edit_client, status_code, detail
    ):
        """Never a 200-with-error-body: the client keeps the player's text only
        because it can tell success from failure by the status code."""
        mock_get.return_value = _me(PLAYER_ME)
        with patch("main.crud.edit_post", new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=status_code, detail=detail)):
            r = edit_client.put(EDIT_URL, json=BODY, headers=AUTH_HEADER)

        assert r.status_code == status_code
        assert r.json()["detail"] == detail


class TestEditRouteAdminFlag:
    """Security: who the route considers an admin. The route checks
    ``role == "admin"`` on purpose and does **not** use ``get_admin_user``,
    which admits moderators."""

    @pytest.mark.parametrize("me,expected", [
        (ADMIN_ME, True),
        (MODERATOR_ME, False),
        (EDITOR_ME, False),
        (PLAYER_ME, False),
    ])
    @patch("auth_http.requests.get")
    def test_only_role_admin_sets_the_bypass(self, mock_get, edit_client, me, expected):
        mock_get.return_value = _me(me)
        with patch("main.crud.edit_post", new_callable=AsyncMock,
                   return_value=_edit_result()) as edit:
            r = edit_client.put(EDIT_URL, json=BODY, headers=AUTH_HEADER)

        assert r.status_code == 200
        assert edit.await_args.kwargs["is_admin"] is expected
        assert edit.await_args.kwargs["user_id"] == me["id"]

    @patch("auth_http.requests.get")
    def test_a_moderator_editing_another_players_post_is_403(self, mock_get, edit_client):
        """A moderator reaches the handler with ``is_admin=False``, so the crud
        layer takes the stranger branch. Both halves are asserted: the flag the
        route passes, and the 403 it returns.
        """
        mock_get.return_value = _me(MODERATOR_ME)
        with patch("main.crud.edit_post", new_callable=AsyncMock,
                   side_effect=HTTPException(
                       status_code=403,
                       detail="Вы можете редактировать только свои посты",
                   )) as edit:
            r = edit_client.put(EDIT_URL, json=BODY, headers=AUTH_HEADER)

        assert r.status_code == 403
        assert r.json()["detail"] == "Вы можете редактировать только свои посты"
        assert edit.await_args.kwargs["is_admin"] is False

    @patch("auth_http.requests.get")
    def test_moderation_permissions_do_not_grant_the_bypass(self, mock_get, edit_client):
        """Holding every moderation permission is still not role ``admin`` —
        editing someone else's post is role-gated, not permission-gated."""
        mock_get.return_value = _me(dict(
            MODERATOR_ME,
            permissions=["moderation:read", "moderation:review", "locations:write"],
        ))
        with patch("main.crud.edit_post", new_callable=AsyncMock,
                   return_value=_edit_result()) as edit:
            edit_client.put(EDIT_URL, json=BODY, headers=AUTH_HEADER)
        assert edit.await_args.kwargs["is_admin"] is False


# ===========================================================================
# Layer 3 — the derived «изменено администратором» flag (T3)
# ===========================================================================

def _httpx_client(get_side_effect):
    """Mock for ``async with httpx.AsyncClient(...) as client``."""
    instance = AsyncMock()
    instance.__aenter__.return_value = instance
    instance.__aexit__.return_value = False
    instance.get.side_effect = get_side_effect
    return instance


def _profile(payload: dict):
    async def _get(_url, *_args, **_kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = payload
        resp.raise_for_status = MagicMock()
        return resp
    return _get


def _profile_down(_url=None, *_args, **_kwargs):
    async def _get(*_a, **_kw):
        raise RuntimeError("character-service is down")
    return _get


PROFILE_PAYLOAD = {
    "character_photo": "p.png",
    "character_title": "Скиталец",
    "user_id": AUTHOR_USER_ID,
    "user_nickname": "player",
    "character_name": "Мирена",
}


def _post_stub(**overrides):
    row = {
        "id": 90,
        "character_id": CHARACTER_ID,
        "content": ORIGINAL_TEXT,
        "created_at": datetime(2026, 9, 13, 12, 0, 0),
        "edited_at": None,
        "edited_by_user_id": None,
    }
    row.update(overrides)
    return SimpleNamespace(**row)


@pytest.mark.asyncio
class TestEditedByAdminDerivation:
    async def test_never_edited_post_reports_no_marker(self):
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_profile(PROFILE_PAYLOAD))):
            details = await crud.get_post_details(_post_stub())

        assert details["edited_at"] is None
        assert details["edited_by_admin"] is False

    async def test_author_edit_is_a_plain_marker(self):
        post = _post_stub(
            edited_at=datetime(2026, 9, 13, 12, 30, 0),
            edited_by_user_id=AUTHOR_USER_ID,
        )
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_profile(PROFILE_PAYLOAD))):
            details = await crud.get_post_details(post)

        assert details["edited_at"] == datetime(2026, 9, 13, 12, 30, 0)
        assert details["edited_by_admin"] is False

    async def test_admin_edit_is_flagged(self):
        post = _post_stub(
            edited_at=datetime(2026, 9, 13, 12, 30, 0),
            edited_by_user_id=ADMIN_USER_ID,
        )
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_profile(PROFILE_PAYLOAD))):
            details = await crud.get_post_details(post)

        assert details["edited_by_admin"] is True
        # The audit column itself stays server-side.
        assert "edited_by_user_id" not in details

    async def test_profile_lookup_failure_degrades_to_false(self):
        """The path the implementing agent could not exercise live.

        character-service being down must never turn every edited post into
        «изменено администратором», and must never 500 the location page. The
        marker itself survives — only the accusation is dropped.
        """
        post = _post_stub(
            edited_at=datetime(2026, 9, 13, 12, 30, 0),
            edited_by_user_id=ADMIN_USER_ID,
        )
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_profile_down())):
            details = await crud.get_post_details(post)

        assert details["edited_by_admin"] is False
        assert details["edited_at"] == datetime(2026, 9, 13, 12, 30, 0)
        assert details["user_id"] is None
        assert details["character_name"] == ""
        assert details["post_id"] == 90

    async def test_profile_http_error_degrades_to_false(self):
        """A 500 from character-service takes the same path as a dead socket:
        ``raise_for_status`` raises inside the ``try``."""
        async def _boom(_url, *_a, **_kw):
            resp = MagicMock()
            resp.status_code = 500
            resp.raise_for_status.side_effect = RuntimeError("500")
            return resp

        post = _post_stub(
            edited_at=datetime(2026, 9, 13, 12, 30, 0),
            edited_by_user_id=ADMIN_USER_ID,
        )
        with patch("crud.httpx.AsyncClient", return_value=_httpx_client(_boom)):
            details = await crud.get_post_details(post)

        assert details["edited_by_admin"] is False

    async def test_profile_without_user_id_degrades_to_false(self):
        """An older character-service payload that omits ``user_id`` must not be
        read as "the editor differs from the author"."""
        post = _post_stub(
            edited_at=datetime(2026, 9, 13, 12, 30, 0),
            edited_by_user_id=ADMIN_USER_ID,
        )
        payload = dict(PROFILE_PAYLOAD)
        payload.pop("user_id")
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_profile(payload))):
            details = await crud.get_post_details(post)

        assert details["edited_by_admin"] is False

    async def test_edited_at_without_an_editor_is_not_flagged(self):
        """A row edited before migration 038 backfilled anything (or by a path
        that forgot the audit column) is «изменено», not «администратором»."""
        post = _post_stub(
            edited_at=datetime(2026, 9, 13, 12, 30, 0), edited_by_user_id=None,
        )
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_profile(PROFILE_PAYLOAD))):
            details = await crud.get_post_details(post)

        assert details["edited_by_admin"] is False

    async def test_editor_recorded_but_no_timestamp_is_not_flagged(self):
        post = _post_stub(edited_at=None, edited_by_user_id=ADMIN_USER_ID)
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_profile(PROFILE_PAYLOAD))):
            details = await crud.get_post_details(post)

        assert details["edited_by_admin"] is False


# ===========================================================================
# Layer 4 — ``crud.merge_gate_lists`` as a pure function (T4 / section 3.6)
# ===========================================================================

class TestMergeGateLists:
    """The single point where the symbol budget is assembled, so it is tested
    directly and not only through the endpoint (FEAT-159 section 3.6).

    Three properties are load-bearing, and each closes a hole:

    1. **Group by ``action_type``** — ``required_symbols_for_gates`` charges
       ``cost * max(1, len(targets))`` *per entry*, so leaving two entries of the
       same type in the list is only correct by accident.
    2. **Union the targets** — a target named twice must be paid for once, and
       must not create a duplicate gate.
    3. **``None`` is a distinct member** — a gate with no target still costs one
       target's worth, and must not be collapsed into a real target.

    Phase B (T8) will pass the pending-request list and the newly-requested list
    as further arguments; these tests pin the behaviour that must survive that.
    """

    def test_an_empty_call_is_an_empty_list(self):
        assert crud.merge_gate_lists() == []

    def test_empty_and_none_lists_are_skipped(self):
        assert crud.merge_gate_lists([], None, []) == []

    def test_a_single_list_passes_through_grouped(self):
        merged = crud.merge_gate_lists([{"action_type": "combat", "targets": [1, 2]}])
        assert merged == [{"action_type": "combat", "targets": [1, 2]}]

    def test_entries_of_the_same_type_are_grouped_into_one(self):
        merged = crud.merge_gate_lists([
            {"action_type": "combat", "targets": [1]},
            {"action_type": "combat", "targets": [2]},
            {"action_type": "combat", "targets": [3]},
        ])
        assert merged == [{"action_type": "combat", "targets": [1, 2, 3]}]
        assert crud.required_symbols_for_gates(merged) == 600

    def test_targets_are_unioned_not_concatenated(self):
        """The same target in two lists is bought once. Concatenating instead
        would charge 4 x 200 = 800 for two distinct mobs."""
        merged = crud.merge_gate_lists(
            [{"action_type": "combat", "targets": [1, 2]}],
            [{"action_type": "combat", "targets": [2, 1]}],
        )
        assert merged == [{"action_type": "combat", "targets": [1, 2]}]
        assert crud.required_symbols_for_gates(merged) == 400

    def test_duplicates_inside_one_list_are_collapsed_too(self):
        merged = crud.merge_gate_lists([
            {"action_type": "combat", "targets": [7, 7, 7]},
        ])
        assert merged == [{"action_type": "combat", "targets": [7]}]

    def test_different_action_types_stay_separate(self):
        merged = crud.merge_gate_lists(
            [{"action_type": "combat", "targets": [1]}],
            [{"action_type": "npc_dialogue", "targets": [1]}],
        )
        assert {e["action_type"] for e in merged} == {"combat", "npc_dialogue"}
        # The same numeric id under two intents is two different things.
        assert crud.required_symbols_for_gates(merged) == 700

    def test_none_is_kept_as_a_distinct_member(self):
        """A gate created with no target at all. It must not merge into a real
        target, and it must not disappear — it still costs one target's worth."""
        merged = crud.merge_gate_lists(
            [{"action_type": "gathering", "targets": [None]}],
            [{"action_type": "gathering", "targets": [5]}],
        )
        assert merged == [{"action_type": "gathering", "targets": [None, 5]}]
        assert crud.required_symbols_for_gates(merged) == 1000

    def test_repeated_nones_collapse_to_one(self):
        merged = crud.merge_gate_lists([
            {"action_type": "gathering", "targets": [None]},
            {"action_type": "gathering", "targets": [None]},
        ])
        assert merged == [{"action_type": "gathering", "targets": [None]}]
        assert crud.required_symbols_for_gates(merged) == 500

    def test_a_targetless_entry_is_kept_with_an_empty_target_list(self):
        """An entry whose ``targets`` is empty still exists, and
        ``required_symbols_for_gates`` floors it at one target."""
        merged = crud.merge_gate_lists([{"action_type": "dungeon", "targets": []}])
        assert merged == [{"action_type": "dungeon", "targets": []}]
        assert crud.required_symbols_for_gates(merged) == 500

    def test_targets_none_is_tolerated(self):
        merged = crud.merge_gate_lists([{"action_type": "dungeon", "targets": None}])
        assert merged == [{"action_type": "dungeon", "targets": []}]

    def test_an_entry_without_an_action_type_is_dropped(self):
        merged = crud.merge_gate_lists([
            {"action_type": None, "targets": [1]},
            {"targets": [2]},
            {"action_type": "combat", "targets": [3]},
        ])
        assert merged == [{"action_type": "combat", "targets": [3]}]

    def test_objects_are_accepted_as_well_as_dicts(self):
        """Phase B passes Pydantic ``GateSpec`` models alongside the dict rows
        read from ``action_gates``, so both shapes must work in one call."""
        merged = crud.merge_gate_lists(
            [{"action_type": "combat", "targets": [1]}],
            [SimpleNamespace(action_type="combat", targets=[2])],
        )
        assert merged == [{"action_type": "combat", "targets": [1, 2]}]

    def test_string_targets_are_normalised_to_ints(self):
        """A JSON payload may carry ``"12"``; it must not become a second,
        separately charged member next to ``12``."""
        merged = crud.merge_gate_lists(
            [{"action_type": "combat", "targets": [12]}],
            [{"action_type": "combat", "targets": ["12"]}],
        )
        assert merged == [{"action_type": "combat", "targets": [12]}]
        assert crud.required_symbols_for_gates(merged) == 300

    def test_the_inputs_are_not_mutated(self):
        """Pure on purpose: ``edit_post`` reuses the list it passed in."""
        first = [{"action_type": "combat", "targets": [1]}]
        second = [{"action_type": "combat", "targets": [2]}]
        crud.merge_gate_lists(first, second)
        assert first == [{"action_type": "combat", "targets": [1]}]
        assert second == [{"action_type": "combat", "targets": [2]}]

    def test_the_five_gate_post_costs_a_thousand_characters(self):
        """The exploit's arithmetic, stated once in a pure test: this is the
        number ``TestGateSymbolBudget`` enforces end to end."""
        merged = crud.merge_gate_lists([
            {"action_type": "combat", "targets": [t]} for t in (501, 502, 503, 504, 505)
        ])
        assert merged == [
            {"action_type": "combat", "targets": [501, 502, 503, 504, 505]}
        ]
        assert crud.required_symbols_for_gates(merged) == 1000

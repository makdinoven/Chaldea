"""FEAT-160 task T6 — post edit history: what is stored, and who is allowed to read it.

Two layers, the same split ``test_post_editing.py`` established:

1. **Real in-memory aiosqlite.** Everything this feature promises is a *database*
   fact, not a Python branch, and a mocked session can assert none of it:

   * a version row holds the text the edit **destroyed**, never the text it
     produced. Swap those two and the very first edit loses the original — the
     precise wording that gets quoted and then disputed. Only real rows, read
     back after a real ``UPDATE``, can tell the two apart.
   * the snapshot and the ``UPDATE posts`` live in **one transaction**. Proving
     that needs a real failure landing between them and a real rollback, so the
     fixture can make the ``UPDATE`` itself blow up
     (``fail_on_statement``) and the test then asks the database — not the code
     — whether anything survived.
   * ``ON DELETE CASCADE`` is asserted by **actually deleting a post** and
     counting the rows left, rather than by reading the FK back out of the
     model. Reading the declaration only proves the declaration was written.
   * the section-3.6 mapping is an off-by-one over real rows. Getting it wrong
     attributes a change to the wrong person, which in a dispute-resolution tool
     is worse than having no tool, so it is tested directly, with two different
     editors, against rows the database actually produced.

2. **The route through ``TestClient``** with ``crud.get_post_versions`` mocked —
   status codes and the access matrix. The one that matters is the
   **moderator**: they hold every other moderation permission, the endpoint
   guards on ``posts:history`` (granted to no role, user-service migration
   0029), and a future "fix" swapping ``require_permission`` for
   ``get_admin_user`` would silently hand post history to every moderator
   without breaking anything else.

The SQLite translation hooks (``FOR UPDATE``, ``NOW() - INTERVAL ? HOUR``) are
the same narrow ones ``test_post_editing.py`` uses, and for the same reason:
``crud.edit_post`` runs completely untouched.
"""

import asyncio
import os
import re
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, event, select, text as sa_text
from sqlalchemy.dialects.mysql import MEDIUMTEXT, TINYINT
from sqlalchemy.exc import IntegrityError
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


LOCATION_ID = 60
CHARACTER_ID = 600
OTHER_CHARACTER_ID = 601
AUTHOR_USER_ID = 21
ADMIN_USER_ID = 22
SECOND_EDITOR_USER_ID = 23

# Three distinct texts, each comfortably over MIN_POST_LENGTH (300 plain chars).
# They must differ BYTE-WISE, or the no-op short circuit of 3.7 turns the edit
# into a no-op and nothing is recorded at all.
TEXT_V1 = "Первая редакция: скиталец входит в зал и считает тени. " * 8
TEXT_V2 = "Вторая редакция: скиталец входит в зал и не считает ничего. " * 8
TEXT_V3 = "Третья редакция: скиталец разворачивается и уходит в дождь. " * 8


_INTERVAL_RE = re.compile(r"NOW\(\)\s*-\s*INTERVAL\s*\?\s*HOUR", re.IGNORECASE)
_FOR_UPDATE_RE = re.compile(r"\s+FOR\s+UPDATE\s*$", re.IGNORECASE)


def _sqlite_translate(statement: str) -> str:
    statement = _INTERVAL_RE.sub(
        "datetime('now', '-' || ? || ' hours')", statement
    )
    return _FOR_UPDATE_RE.sub("", statement)


class _InjectedFailure(RuntimeError):
    """Raised by the fixture's cursor hook to simulate a mid-transaction crash."""


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    """In-memory async SQLite holding the tables ``edit_post`` / ``get_post_versions``
    actually touch, plus a knob for injecting a mid-transaction failure.

    ``characters`` is a bare stub table on purpose: ``edit_post`` decides
    ownership with a raw ``SELECT user_id FROM characters`` across the service
    boundary, and that read is part of the behaviour under test.

    The tables come from the ORM models, which are byte-for-byte the shape
    migration 040 creates in MySQL — see
    ``TestTheFixtureMirrorsTheRealSchema`` below, which asserts that rather than
    assuming it.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    # {"match": <substring of a SQL statement>} — when set, the cursor hook
    # raises instead of running that statement. Used to prove the snapshot and
    # the UPDATE share one transaction.
    fail_on = {"match": None}

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_setup(dbapi_conn, _record):  # pragma: no cover - connection hook
        # CASCADE is off by default in SQLite; the whole point of one of these
        # tests is that the database, not the application, deletes the history.
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        dbapi_conn.create_function(
            "NOW", 0, lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )

    @event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def _translate(conn, cursor, statement, parameters, context, executemany):  # pragma: no cover - hook
        translated = _sqlite_translate(statement)
        match = fail_on["match"]
        if match and match in " ".join(translated.split()):
            raise _InjectedFailure(f"injected failure on: {match}")
        return translated, parameters

    async with engine.begin() as conn:
        for ddl in (
            'CREATE TABLE "Regions" (id INTEGER PRIMARY KEY)',
            'CREATE TABLE "Districts" (id INTEGER PRIMARY KEY)',
            "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER, "
            "current_location_id INTEGER)",
        ):
            await conn.execute(sa_text(ddl))
        for table in (
            Location.__table__, Post.__table__, ActionGate.__table__,
            PostGateRequest.__table__, PostVersion.__table__,
        ):
            await conn.run_sync(table.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        s.add(Location(
            id=LOCATION_ID, name="Мокрый причал", type="location",
            recommended_level=1, quick_travel_marker=False, description="d",
            marker_type="safe", sort_order=0, is_starting=False,
        ))
        await s.execute(sa_text(
            "INSERT INTO characters (id, user_id, current_location_id) "
            "VALUES (:a, :au, :loc), (:b, :bu, :loc)"
        ), {"a": CHARACTER_ID, "au": AUTHOR_USER_ID,
            "b": OTHER_CHARACTER_ID, "bu": SECOND_EDITOR_USER_ID,
            "loc": LOCATION_ID})
        await s.commit()
        s.info["fail_on"] = fail_on
        yield s

    await engine.dispose()


async def _add_post(
    session,
    post_id: int,
    *,
    character_id: int = CHARACTER_ID,
    content: str = TEXT_V1,
    minutes_ago: int = 5,
    edited_at: datetime | None = None,
    edited_by_user_id: int | None = None,
) -> None:
    session.add(Post(
        id=post_id, character_id=character_id, location_id=LOCATION_ID,
        content=content, post_type="regular",
        created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
        edited_at=edited_at, edited_by_user_id=edited_by_user_id,
    ))
    await session.commit()


async def _versions(session, post_id: int) -> list:
    """Raw ``post_versions`` rows, ascending — the storage view, before the
    section-3.6 flip."""
    return (await session.execute(sa_text(
        "SELECT version_no, content, edited_by_user_id, is_original, created_at "
        "FROM post_versions WHERE post_id = :pid ORDER BY version_no ASC"
    ), {"pid": post_id})).fetchall()


async def _version_count(session, post_id: int) -> int:
    return (await session.execute(sa_text(
        "SELECT COUNT(*) FROM post_versions WHERE post_id = :pid"
    ), {"pid": post_id})).scalar()


async def _reload(session, post_id: int) -> Post:
    result = await session.execute(
        select(Post).where(Post.id == post_id).execution_options(populate_existing=True)
    )
    return result.scalars().first()


def _ts(value) -> str | None:
    """Normalise a timestamp for comparison.

    SQLite hands raw ``text()`` queries the stored string while the ORM layer
    converts to ``datetime``; MySQL returns ``datetime`` from both. The mapping
    under test is about *which* timestamp lands on *which* entry, not about the
    driver's type, so both sides are compared as ``YYYY-MM-DD HH:MM:SS``.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)[:19]


def _no_username_lookup():
    """``_fetch_username_map`` replacement — user-service is another service and
    is never called for real from a test."""
    return AsyncMock(return_value={})


# ===========================================================================
# Layer 0 — the fixture must model a table that actually exists
# ===========================================================================

class TestTheFixtureMirrorsTheRealSchema:
    """``PostVersion.__table__`` is what every aiosqlite fixture here creates, so
    a model that drifts from migration 040 would leave the whole suite testing a
    database that does not exist. Assert the shape instead of trusting it.

    The live MySQL table was checked by hand against these same facts:
    ``post_id int NOT NULL``, ``uq_post_versions_post_version (post_id,
    version_no)``, ``fk_post_versions_post_id ... ON DELETE CASCADE``,
    ``is_original tinyint(1) NOT NULL DEFAULT '1'``.
    """

    def test_the_columns_match_migration_040(self):
        cols = {c.name: c for c in PostVersion.__table__.columns}
        assert set(cols) == {
            "id", "post_id", "version_no", "content",
            "edited_by_user_id", "is_original", "created_at",
        }
        # NOT NULL on post_id is what makes an orphaned copy of deleted content
        # unrepresentable rather than merely unlikely (3.3).
        for name in ("post_id", "version_no", "content",
                     "edited_by_user_id", "is_original", "created_at"):
            assert cols[name].nullable is False, name

    def test_post_id_cascades_and_points_at_posts(self):
        fk = list(PostVersion.__table__.columns["post_id"].foreign_keys)
        assert len(fk) == 1
        assert fk[0].column.table.name == "posts"
        # SET NULL here (the 037/039 convention) would leave a surviving copy of
        # moderated-away text in an admin view — see 3.3.
        assert fk[0].ondelete == "CASCADE"

    def test_the_unique_key_is_post_id_plus_version_no(self):
        uniques = [
            c for c in PostVersion.__table__.constraints
            if c.__class__.__name__ == "UniqueConstraint"
        ]
        assert len(uniques) == 1
        assert uniques[0].name == "uq_post_versions_post_version"
        assert [c.name for c in uniques[0].columns] == ["post_id", "version_no"]


# ===========================================================================
# Layer 1 — what edit_post writes
# ===========================================================================

@pytest.mark.asyncio
class TestTheStoredTextIsThePreEditText:
    """3.4 — the single most important fact about this table. A row holds the
    text the edit **replaced**. Store the "after" text instead and the original
    is destroyed by the very first edit, which is exactly the wording a dispute
    is about."""

    async def test_one_edit_stores_the_text_from_before_it(self, session):
        await _add_post(session, 1, content=TEXT_V1)

        await crud.edit_post(
            session, post_id=1, content=TEXT_V2,
            user_id=AUTHOR_USER_ID, is_admin=False,
        )

        rows = await _versions(session, 1)
        assert len(rows) == 1
        assert rows[0].content == TEXT_V1, "the row must hold the PRE-edit text"
        assert rows[0].content != TEXT_V2, "storing the post-edit text loses the original"
        # The current text is never duplicated into the table; it is read live.
        assert (await _reload(session, 1)).content == TEXT_V2

    async def test_two_edits_leave_the_full_chain_in_order(self, session):
        """v1 = the original, v2 = the text after edit #1, posts.content = after #2."""
        await _add_post(session, 2, content=TEXT_V1)

        await crud.edit_post(session, post_id=2, content=TEXT_V2,
                             user_id=AUTHOR_USER_ID, is_admin=False)
        await crud.edit_post(session, post_id=2, content=TEXT_V3,
                             user_id=AUTHOR_USER_ID, is_admin=True)

        rows = await _versions(session, 2)
        assert [r.content for r in rows] == [TEXT_V1, TEXT_V2]
        assert (await _reload(session, 2)).content == TEXT_V3

    async def test_the_row_records_who_destroyed_the_text_not_who_wrote_it(self, session):
        """The deliberate off-by-one of the storage model (3.4): an admin editing
        somebody else's post is recorded on the row holding the *author's* text."""
        await _add_post(session, 3, content=TEXT_V1)

        await crud.edit_post(session, post_id=3, content=TEXT_V2,
                             user_id=ADMIN_USER_ID, is_admin=True)

        rows = await _versions(session, 3)
        assert rows[0].content == TEXT_V1          # the author's wording
        assert rows[0].edited_by_user_id == ADMIN_USER_ID   # the admin who replaced it


@pytest.mark.asyncio
class TestVersionNumbering:
    async def test_the_first_version_is_one_and_it_increments(self, session):
        await _add_post(session, 11, content=TEXT_V1)

        await crud.edit_post(session, post_id=11, content=TEXT_V2,
                             user_id=AUTHOR_USER_ID, is_admin=False)
        assert [r.version_no for r in await _versions(session, 11)] == [1]

        await crud.edit_post(session, post_id=11, content=TEXT_V3,
                             user_id=AUTHOR_USER_ID, is_admin=True)
        assert [r.version_no for r in await _versions(session, 11)] == [1, 2]

    async def test_numbering_is_per_post_not_global(self, session):
        await _add_post(session, 12, content=TEXT_V1)
        await _add_post(session, 13, content=TEXT_V1, character_id=OTHER_CHARACTER_ID)

        # `is_admin=True` on post 12: post 13 is a later post in the same
        # location, which blocks a non-admin edit (FEAT-159 limit 1). The
        # numbering is what is under test, not that limit.
        await crud.edit_post(session, post_id=12, content=TEXT_V2,
                             user_id=AUTHOR_USER_ID, is_admin=True)
        await crud.edit_post(session, post_id=13, content=TEXT_V2,
                             user_id=SECOND_EDITOR_USER_ID, is_admin=False)

        assert [r.version_no for r in await _versions(session, 12)] == [1]
        assert [r.version_no for r in await _versions(session, 13)] == [1]

    async def test_the_unique_key_refuses_a_duplicate_version_no(self, session):
        """``uq_post_versions_post_version`` is the backstop behind the
        MAX(version_no) + 1 read-modify-write. If two writers ever slipped past
        the row lock, the database refuses the second one rather than silently
        keeping two "version 1"s."""
        await _add_post(session, 14, content=TEXT_V1)
        await crud.edit_post(session, post_id=14, content=TEXT_V2,
                             user_id=AUTHOR_USER_ID, is_admin=False)

        with pytest.raises(IntegrityError):
            await session.execute(sa_text(
                "INSERT INTO post_versions "
                "(post_id, version_no, content, edited_by_user_id, is_original) "
                "VALUES (14, 1, 'дубль', 1, 1)"
            ))
        await session.rollback()
        assert await _version_count(session, 14) == 1


@pytest.mark.asyncio
class TestIsOriginalFlag:
    """3.6 — whether the earliest stored text really is the post's first wording
    cannot be derived after the fact, so it is recorded at write time."""

    async def test_first_snapshot_of_a_never_edited_post_is_the_original(self, session):
        await _add_post(session, 21, content=TEXT_V1, edited_at=None)

        await crud.edit_post(session, post_id=21, content=TEXT_V2,
                             user_id=AUTHOR_USER_ID, is_admin=False)

        rows = await _versions(session, 21)
        assert bool(rows[0].is_original) is True

    async def test_first_snapshot_of_a_pre_deployment_edit_is_not_the_original(self, session):
        """``edited_at`` set and no rows = the post was edited before history
        existed. Its true original is gone, and the flag must say so instead of
        letting the API imply the post was never touched."""
        await _add_post(
            session, 22, content=TEXT_V1,
            edited_at=datetime.utcnow() - timedelta(days=3),
            edited_by_user_id=AUTHOR_USER_ID,
        )

        await crud.edit_post(session, post_id=22, content=TEXT_V2,
                             user_id=ADMIN_USER_ID, is_admin=True)

        rows = await _versions(session, 22)
        assert bool(rows[0].is_original) is False

    async def test_the_flag_is_only_about_the_first_row(self, session):
        """After edit #1 the post has ``edited_at``, so every later row records
        ``is_original = 0``. The column is documented as meaningless past
        version 1 — this pins that behaviour so a reader does not mistake row 2's
        zero for "the original was lost"."""
        await _add_post(session, 23, content=TEXT_V1, edited_at=None)

        await crud.edit_post(session, post_id=23, content=TEXT_V2,
                             user_id=AUTHOR_USER_ID, is_admin=False)
        await crud.edit_post(session, post_id=23, content=TEXT_V3,
                             user_id=AUTHOR_USER_ID, is_admin=True)

        rows = await _versions(session, 23)
        assert [bool(r.is_original) for r in rows] == [True, False]

        with patch.object(crud, "_fetch_username_map", _no_username_lookup()):
            history = await crud.get_post_versions(session, 23)
        # Row 1 is the only one that decides it.
        assert history["original_available"] is True


@pytest.mark.asyncio
class TestTheWriteIsInTheSameTransaction:
    """3.7 — no edit without its record, and no record without its edit."""

    async def test_a_validation_failure_writes_no_version_row(self, session):
        """The gate symbol budget rejects the edit *after* the post is read and
        *before* the snapshot. Nothing must be left behind."""
        await _add_post(session, 31, content="а" * 1000)
        for target in (501, 502, 503, 504, 505):
            session.add(ActionGate(
                character_id=CHARACTER_ID, location_id=LOCATION_ID, post_id=31,
                action_type="combat", target_ref=target, status="open",
            ))
        await session.commit()

        with pytest.raises(HTTPException) as exc:
            await crud.edit_post(session, post_id=31, content="б" * 307,
                                 user_id=AUTHOR_USER_ID, is_admin=False)

        assert exc.value.status_code == 400
        assert await _version_count(session, 31) == 0
        assert (await _reload(session, 31)).edited_at is None

    async def test_a_failure_after_the_insert_leaves_no_version_row(self, session):
        """The one that actually proves the transaction boundary.

        The snapshot INSERT runs, and then the ``UPDATE posts`` is made to
        explode. If the version write had its own commit — or sat in its own
        session — the row would survive and the admin history would show a
        "previous version" for an edit that never happened. It must not.
        """
        await _add_post(session, 32, content=TEXT_V1)

        session.info["fail_on"]["match"] = "UPDATE posts SET content"
        try:
            with pytest.raises(_InjectedFailure):
                await crud.edit_post(session, post_id=32, content=TEXT_V2,
                                     user_id=AUTHOR_USER_ID, is_admin=False)
        finally:
            session.info["fail_on"]["match"] = None
        await session.rollback()

        assert await _version_count(session, 32) == 0, (
            "the snapshot outlived the edit it belongs to"
        )
        stored = await _reload(session, 32)
        assert stored.content == TEXT_V1
        assert stored.edited_at is None

    async def test_the_control_case_does_write_a_row(self, session):
        """Guards the test above from passing for the wrong reason: with no
        injected failure, the very same call leaves exactly one row."""
        await _add_post(session, 33, content=TEXT_V1)

        await crud.edit_post(session, post_id=33, content=TEXT_V2,
                             user_id=AUTHOR_USER_ID, is_admin=False)

        assert await _version_count(session, 33) == 1


@pytest.mark.asyncio
class TestDeletingThePostDeletesItsHistory:
    """3.3 — asserted by deleting a post for real. Reading ``ondelete`` off the
    model would only prove somebody typed the word CASCADE."""

    async def test_delete_from_posts_takes_the_versions_with_it(self, session):
        await _add_post(session, 41, content=TEXT_V1)
        await crud.edit_post(session, post_id=41, content=TEXT_V2,
                             user_id=AUTHOR_USER_ID, is_admin=False)
        await crud.edit_post(session, post_id=41, content=TEXT_V3,
                             user_id=AUTHOR_USER_ID, is_admin=True)
        assert await _version_count(session, 41) == 2

        # Exactly what moderation does — crud.review_report / review_deletion_request.
        await session.execute(sa_text("DELETE FROM posts WHERE id = :pid"), {"pid": 41})
        await session.commit()

        assert await _version_count(session, 41) == 0, (
            "a moderated-away post left a surviving copy of its content behind"
        )

    async def test_other_posts_history_is_untouched(self, session):
        await _add_post(session, 42, content=TEXT_V1)
        await _add_post(session, 43, content=TEXT_V1, character_id=OTHER_CHARACTER_ID)
        # As above: post 43 is later in the same location, so the edit of 42
        # goes through the admin bypass.
        await crud.edit_post(session, post_id=42, content=TEXT_V2,
                             user_id=AUTHOR_USER_ID, is_admin=True)
        await crud.edit_post(session, post_id=43, content=TEXT_V2,
                             user_id=SECOND_EDITOR_USER_ID, is_admin=False)

        await session.execute(sa_text("DELETE FROM posts WHERE id = 42"))
        await session.commit()

        assert await _version_count(session, 42) == 0
        assert await _version_count(session, 43) == 1


@pytest.mark.asyncio
class TestNoOpEdits:
    """3.7 — submitting byte-identical content is not an edit.

    Without the short circuit, an admin who opens the editor and presses Save
    manufactures a fake «изменено» on a post nobody changed, plus a version row
    whose "previous text" is the current text.
    """

    async def test_identical_content_writes_no_version_row(self, session):
        await _add_post(session, 51, content=TEXT_V1, edited_at=None)

        result = await crud.edit_post(session, post_id=51, content=TEXT_V1,
                                      user_id=AUTHOR_USER_ID, is_admin=False)

        assert await _version_count(session, 51) == 0
        # Still a success — the save is accepted, it simply changes nothing.
        assert result["id"] == 51
        assert result["content"] == TEXT_V1
        # And no fake «изменено» marker.
        assert result["edited_at"] is None
        assert (await _reload(session, 51)).edited_at is None

    async def test_identical_content_does_not_move_an_existing_edited_at(self, session):
        """On an already-edited post the marker must keep pointing at the real
        last edit, not at the moment somebody re-saved it unchanged."""
        earlier = datetime.utcnow() - timedelta(days=2)
        await _add_post(session, 52, content=TEXT_V1, edited_at=earlier,
                        edited_by_user_id=AUTHOR_USER_ID)

        await crud.edit_post(session, post_id=52, content=TEXT_V1,
                             user_id=ADMIN_USER_ID, is_admin=True)

        stored = await _reload(session, 52)
        assert _ts(stored.edited_at) == _ts(earlier)
        assert stored.edited_by_user_id == AUTHOR_USER_ID
        assert await _version_count(session, 52) == 0

    async def test_a_gate_request_is_still_filed_on_a_no_op_save(self, session):
        """Deliberately **outside** the short circuit: asking for a gate is a real
        request even when the text is untouched. Folding it into the no-op would
        silently drop the player's request and show them a success toast."""
        await _add_post(session, 53, content="а" * 1000, edited_at=None)

        result = await crud.edit_post(
            session, post_id=53, content="а" * 1000,
            user_id=AUTHOR_USER_ID, is_admin=False,
            gates=[{"action_type": "combat", "targets": [777]}],
        )

        assert result["gate_request_id"] is not None
        assert result["gate_request_status"] == "pending"
        filed = (await session.execute(sa_text(
            "SELECT COUNT(*) FROM post_gate_requests WHERE post_id = 53"
        ))).scalar()
        assert filed == 1
        # ...and it still did not fabricate a version or an «изменено» marker.
        assert await _version_count(session, 53) == 0
        assert (await _reload(session, 53)).edited_at is None


# ===========================================================================
# Layer 1b — crud.get_post_versions: the section-3.6 mapping
# ===========================================================================

@pytest.mark.asyncio
class TestVersionMapping:
    """The off-by-one is resolved exactly once, server-side, and this is where
    that is proven.

    A ``post_versions`` row carries the editor and timestamp of the edit that
    **destroyed** its text. The API must hand the admin the editor and timestamp
    of the edit that **produced** it. An off-by-one here attributes a change to
    the wrong person — in a tool whose only job is settling «ты написал не так»,
    that is worse than having no tool at all.
    """

    async def test_an_unedited_post_is_a_single_current_entry(self, session):
        await _add_post(session, 61, content=TEXT_V1, edited_at=None)

        with patch.object(crud, "_fetch_username_map", _no_username_lookup()):
            history = await crud.get_post_versions(session, 61)

        assert history["post_id"] == 61
        assert history["post_edited_at"] is None
        # An untouched post is missing nothing.
        assert history["original_available"] is True
        assert len(history["versions"]) == 1
        only = history["versions"][0]
        assert only["version_no"] == 1
        assert only["is_current"] is True
        assert only["content"] == TEXT_V1
        assert only["author_user_id"] is None
        # Publication produced the current text; no edit did.
        post = await _reload(session, 61)
        assert _ts(only["created_at"]) == _ts(post.created_at)

    async def test_after_one_edit_the_original_keeps_the_publication_time(self, session):
        await _add_post(session, 62, content=TEXT_V1, edited_at=None)
        post_created = (await _reload(session, 62)).created_at

        await crud.edit_post(session, post_id=62, content=TEXT_V2,
                             user_id=ADMIN_USER_ID, is_admin=True)

        with patch.object(crud, "_fetch_username_map", _no_username_lookup()):
            history = await crud.get_post_versions(session, 62)

        assert history["original_available"] is True
        v1, v2 = history["versions"]
        # Version 1 is the post's own author's wording: no editor, published at
        # posts.created_at — NOT the timestamp stored on the row, which belongs
        # to the edit that replaced this text.
        assert v1["version_no"] == 1
        assert v1["content"] == TEXT_V1
        assert v1["author_user_id"] is None
        assert _ts(v1["created_at"]) == _ts(post_created)
        assert v1["is_current"] is False
        # Version 2 is the current text, produced by the admin's edit.
        assert v2["version_no"] == 2
        assert v2["content"] == TEXT_V2
        assert v2["is_current"] is True
        assert v2["author_user_id"] == ADMIN_USER_ID
        post = await _reload(session, 62)
        assert _ts(v2["created_at"]) == _ts(post.edited_at)

    async def test_two_edits_by_two_people_are_attributed_correctly(self, session):
        """The heart of 3.6, with two distinct editors so an off-by-one cannot
        hide behind a single id.

        Storage:  row1(TEXT_V1, destroyed by ADMIN) row2(TEXT_V2, destroyed by SECOND)
        API:      v1 TEXT_V1 by nobody (the author)
                  v2 TEXT_V2 by ADMIN, at row1.created_at
                  v3 TEXT_V3 by SECOND, at posts.edited_at   <- current
        """
        await _add_post(session, 63, content=TEXT_V1, edited_at=None)
        post_created = (await _reload(session, 63)).created_at

        await crud.edit_post(session, post_id=63, content=TEXT_V2,
                             user_id=ADMIN_USER_ID, is_admin=True)
        await crud.edit_post(session, post_id=63, content=TEXT_V3,
                             user_id=SECOND_EDITOR_USER_ID, is_admin=True)

        rows = await _versions(session, 63)
        # Precondition — the storage really is off by one.
        assert [r.edited_by_user_id for r in rows] == [ADMIN_USER_ID, SECOND_EDITOR_USER_ID]

        with patch.object(crud, "_fetch_username_map", _no_username_lookup()):
            history = await crud.get_post_versions(session, 63)

        v1, v2, v3 = history["versions"]
        assert [e["version_no"] for e in history["versions"]] == [1, 2, 3]
        assert [e["content"] for e in history["versions"]] == [TEXT_V1, TEXT_V2, TEXT_V3]
        assert [e["is_current"] for e in history["versions"]] == [False, False, True]

        assert v1["author_user_id"] is None
        assert _ts(v1["created_at"]) == _ts(post_created)

        # TEXT_V2 was PRODUCED by the admin — who is recorded on row 1, the row
        # holding TEXT_V1. Reading the editor off row 2 would credit this text to
        # SECOND_EDITOR_USER_ID, who in fact destroyed it.
        assert v2["author_user_id"] == ADMIN_USER_ID
        assert _ts(v2["created_at"]) == _ts(rows[0].created_at)

        assert v3["author_user_id"] == SECOND_EDITOR_USER_ID
        post = await _reload(session, 63)
        assert _ts(v3["created_at"]) == _ts(post.edited_at)

    async def test_a_longer_chain_keeps_every_text_with_its_own_editor(self, session):
        """Three edits, three different editors — the shift has to hold all the
        way down the list, not just for the pair at the end."""
        await _add_post(session, 67, content=TEXT_V1, edited_at=None)
        editors = [AUTHOR_USER_ID, ADMIN_USER_ID, SECOND_EDITOR_USER_ID]
        for uid, body in zip(editors, (TEXT_V2, TEXT_V3, TEXT_V1 + "хвост")):
            await crud.edit_post(session, post_id=67, content=body,
                                 user_id=uid, is_admin=True)

        rows = await _versions(session, 67)
        with patch.object(crud, "_fetch_username_map", _no_username_lookup()):
            history = await crud.get_post_versions(session, 67)

        assert [e["version_no"] for e in history["versions"]] == [1, 2, 3, 4]
        # Entry k is authored by the editor recorded on row k-1; entry 1 by
        # nobody (the post's own author).
        assert [e["author_user_id"] for e in history["versions"]] == [None] + editors
        assert [_ts(e["created_at"]) for e in history["versions"][1:-1]] == [
            _ts(r.created_at) for r in rows[:-1]
        ]

    async def test_the_current_text_is_read_live_and_is_never_a_stored_row(self, session):
        await _add_post(session, 64, content=TEXT_V1, edited_at=None)
        await crud.edit_post(session, post_id=64, content=TEXT_V2,
                             user_id=AUTHOR_USER_ID, is_admin=False)

        with patch.object(crud, "_fetch_username_map", _no_username_lookup()):
            history = await crud.get_post_versions(session, 64)

        current = history["versions"][-1]
        assert current["is_current"] is True
        assert current["content"] == (await _reload(session, 64)).content
        # Exactly one current entry, and it is the last one.
        assert sum(1 for e in history["versions"] if e["is_current"]) == 1

    async def test_usernames_are_resolved_for_the_editors_that_exist(self, session):
        await _add_post(session, 65, content=TEXT_V1, edited_at=None)
        await crud.edit_post(session, post_id=65, content=TEXT_V2,
                             user_id=ADMIN_USER_ID, is_admin=True)

        lookup = AsyncMock(return_value={ADMIN_USER_ID: "gm_varan"})
        with patch.object(crud, "_fetch_username_map", lookup):
            history = await crud.get_post_versions(session, 65)

        assert history["versions"][-1]["author_username"] == "gm_varan"
        # Only the entries that actually name an editor are looked up.
        assert lookup.await_args.args[0] == [ADMIN_USER_ID]

    async def test_a_deleted_editor_account_degrades_to_null(self, session):
        """Section 1 edge case. A missing name must not turn an admin's dispute
        lookup into a 500 — the UI renders «Пользователь #N»."""
        await _add_post(session, 66, content=TEXT_V1, edited_at=None)
        await crud.edit_post(session, post_id=66, content=TEXT_V2,
                             user_id=ADMIN_USER_ID, is_admin=True)

        with patch.object(crud, "_fetch_username_map",
                          AsyncMock(return_value={ADMIN_USER_ID: None})):
            history = await crud.get_post_versions(session, 66)

        assert history["versions"][-1]["author_user_id"] == ADMIN_USER_ID
        assert history["versions"][-1]["author_username"] is None

    async def test_unknown_post_is_404(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.get_post_versions(session, 999999)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Пост не найден"


@pytest.mark.asyncio
class TestPreDeploymentHonesty:
    """3.6 — a post edited before this feature shipped has an unrecoverable
    original, and the response must say so rather than presenting the oldest
    surviving text as "the original"."""

    async def test_original_unavailable_and_version_one_has_no_timestamp(self, session):
        """The pre-deployment case: ``edited_at`` was already set when the first
        version row was written, so row 1 is NOT the original — and dating it
        with ``posts.created_at`` would be a lie about when that text was
        written."""
        await _add_post(
            session, 71, content=TEXT_V1,
            edited_at=datetime.utcnow() - timedelta(days=3),
            edited_by_user_id=AUTHOR_USER_ID,
        )

        await crud.edit_post(session, post_id=71, content=TEXT_V2,
                             user_id=ADMIN_USER_ID, is_admin=True)

        with patch.object(crud, "_fetch_username_map", _no_username_lookup()):
            history = await crud.get_post_versions(session, 71)

        assert history["original_available"] is False
        v1 = history["versions"][0]
        assert v1["version_no"] == 1
        assert v1["content"] == TEXT_V1
        assert v1["created_at"] is None, (
            "an unrecoverable original must not be dated from posts.created_at"
        )
        assert v1["author_user_id"] is None
        # The rest of the chain is unaffected.
        assert history["versions"][-1]["is_current"] is True
        assert history["versions"][-1]["author_user_id"] == ADMIN_USER_ID

    async def test_edited_before_deployment_with_no_rows_at_all(self, session):
        """«Пост редактировали до появления истории — сравнивать не с чем.»"""
        edited = datetime.utcnow() - timedelta(days=3)
        await _add_post(session, 72, content=TEXT_V2, edited_at=edited,
                        edited_by_user_id=AUTHOR_USER_ID)

        with patch.object(crud, "_fetch_username_map", _no_username_lookup()):
            history = await crud.get_post_versions(session, 72)

        assert history["original_available"] is False
        assert _ts(history["post_edited_at"]) == _ts(edited)
        assert len(history["versions"]) == 1
        assert history["versions"][0]["is_current"] is True
        assert _ts(history["versions"][0]["created_at"]) == _ts(edited)


# ===========================================================================
# Layer 2 — the route and its access matrix
# ===========================================================================

VERSIONS_URL = "/locations/posts/77/versions"
AUTH_HEADER = {"Authorization": "Bearer token"}

# An admin's /users/me carries EVERY row of the permissions table — user-service
# `crud.get_effective_permissions` selects the table itself for role `admin`. So
# `posts:history` is in this list precisely because migration 0029 created it,
# and not because any role_permissions row grants it.
ADMIN_ME = {"id": ADMIN_USER_ID, "username": "admin", "role": "admin",
            "permissions": ["locations:read", "moderation:read",
                            "moderation:review", "posts:history"]}
# The regression risk. A moderator holds every other moderation power and must
# still be refused: the history is a dispute-resolution tool, not a moderation
# queue. Swapping `require_permission("posts:history")` for `get_admin_user`
# would turn this 403 into a 200 and break nothing else.
MODERATOR_ME = {"id": 31, "username": "mod", "role": "moderator",
                "permissions": ["moderation:read", "moderation:review",
                                "locations:read"]}
EDITOR_ME = {"id": 32, "username": "editor", "role": "editor",
             "permissions": ["locations:read"]}
PLAYER_ME = {"id": AUTHOR_USER_ID, "username": "player", "role": "user",
             "permissions": []}
# The point of choosing a permission over a hard role gate (3.9): one named
# person can be handed post history through `user_permissions`, with no deploy.
DELEGATED_ME = {"id": 33, "username": "trusted_mod", "role": "moderator",
                "permissions": ["moderation:read", "posts:history"]}


def _me(payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


def _history(**overrides):
    row = {
        "post_id": 77,
        "post_edited_at": datetime(2026, 9, 14, 12, 30, 0),
        "original_available": True,
        "versions": [
            {"version_no": 1, "content": TEXT_V1,
             "created_at": datetime(2026, 9, 14, 12, 0, 0),
             "author_user_id": None, "author_username": None, "is_current": False},
            {"version_no": 2, "content": TEXT_V2,
             "created_at": datetime(2026, 9, 14, 12, 30, 0),
             "author_user_id": ADMIN_USER_ID, "author_username": "admin",
             "is_current": True},
        ],
    }
    row.update(overrides)
    return row


@pytest.fixture()
def history_client():
    async def _fake_get_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _fake_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestVersionsRouteAccessMatrix:
    """3.9 — admins implicitly, moderators never, delegates explicitly."""

    def test_anonymous_is_401(self, history_client):
        with patch("main.crud.get_post_versions", new_callable=AsyncMock) as spy:
            assert history_client.get(VERSIONS_URL).status_code == 401
        spy.assert_not_called()

    @patch("auth_http.requests.get")
    def test_invalid_token_is_401(self, mock_get, history_client):
        mock_get.return_value = _me({}, status_code=401)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock) as spy:
            r = history_client.get(VERSIONS_URL, headers=AUTH_HEADER)
        assert r.status_code == 401
        spy.assert_not_called()

    @patch("auth_http.requests.get")
    def test_admin_is_200(self, mock_get, history_client):
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock,
                   return_value=_history()) as spy:
            r = history_client.get(VERSIONS_URL, headers=AUTH_HEADER)
        assert r.status_code == 200
        assert spy.await_args.args[1] == 77

    @patch("auth_http.requests.get")
    def test_moderator_is_403(self, mock_get, history_client):
        """The regression this suite exists for. A moderator holding
        `moderation:read` **and** `moderation:review` still does not hold
        `posts:history`."""
        mock_get.return_value = _me(MODERATOR_ME)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock) as spy:
            r = history_client.get(VERSIONS_URL, headers=AUTH_HEADER)
        assert r.status_code == 403
        assert r.json()["detail"] == "Недостаточно прав"
        # Refused by the dependency — the post is never even read.
        spy.assert_not_called()

    @patch("auth_http.requests.get")
    def test_plain_player_is_403(self, mock_get, history_client):
        mock_get.return_value = _me(PLAYER_ME)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock) as spy:
            r = history_client.get(VERSIONS_URL, headers=AUTH_HEADER)
        assert r.status_code == 403
        assert r.json()["detail"] == "Недостаточно прав"
        spy.assert_not_called()

    @patch("auth_http.requests.get")
    def test_editor_is_403(self, mock_get, history_client):
        mock_get.return_value = _me(EDITOR_ME)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock):
            r = history_client.get(VERSIONS_URL, headers=AUTH_HEADER)
        assert r.status_code == 403

    @patch("auth_http.requests.get")
    def test_a_delegated_non_admin_is_200(self, mock_get, history_client):
        """A `user_permissions` grant to one named moderator works without a
        deploy — the reason 3.9 chose a permission over `get_strict_admin_user`.
        The role here is still `moderator`, so a role check would refuse this."""
        mock_get.return_value = _me(DELEGATED_ME)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock,
                   return_value=_history()):
            r = history_client.get(VERSIONS_URL, headers=AUTH_HEADER)
        assert r.status_code == 200


class TestVersionsRouteContract:
    @patch("auth_http.requests.get")
    def test_the_response_shape_is_the_documented_one(self, mock_get, history_client):
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock,
                   return_value=_history()):
            r = history_client.get(VERSIONS_URL, headers=AUTH_HEADER)

        body = r.json()
        assert set(body) == {"post_id", "post_edited_at", "original_available", "versions"}
        assert set(body["versions"][0]) == {
            "version_no", "content", "created_at",
            "author_user_id", "author_username", "is_current",
        }
        assert [v["version_no"] for v in body["versions"]] == [1, 2]
        assert body["versions"][-1]["is_current"] is True

    @patch("auth_http.requests.get")
    def test_a_null_created_at_survives_serialisation(self, mock_get, history_client):
        """The pre-deployment case has to reach the client as ``null``; a
        non-Optional schema would answer 500 instead."""
        payload = _history(original_available=False)
        payload["versions"][0]["created_at"] = None
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock,
                   return_value=payload):
            r = history_client.get(VERSIONS_URL, headers=AUTH_HEADER)

        assert r.status_code == 200
        assert r.json()["original_available"] is False
        assert r.json()["versions"][0]["created_at"] is None

    @patch("auth_http.requests.get")
    def test_unknown_post_is_404_in_russian(self, mock_get, history_client):
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=404, detail="Пост не найден")):
            r = history_client.get("/locations/posts/424242/versions",
                                   headers=AUTH_HEADER)
        assert r.status_code == 404
        assert r.json()["detail"] == "Пост не найден"

    @patch("auth_http.requests.get")
    def test_a_non_numeric_post_id_is_422(self, mock_get, history_client):
        """``post_id`` is a path ``int`` and nothing else is accepted — the only
        input this endpoint takes."""
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock) as spy:
            r = history_client.get("/locations/posts/'; DROP TABLE posts; --/versions",
                                   headers=AUTH_HEADER)
        assert r.status_code == 422
        spy.assert_not_called()

    @patch("auth_http.requests.get")
    def test_the_route_does_not_shadow_the_post_details_route(self, mock_get, history_client):
        """``/posts/{id}/versions`` must reach its own handler rather than being
        swallowed by another ``/posts/`` route."""
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_post_versions", new_callable=AsyncMock,
                   return_value=_history(post_id=99)) as spy:
            r = history_client.get("/locations/posts/99/versions", headers=AUTH_HEADER)
        assert r.status_code == 200
        spy.assert_awaited_once()
        assert spy.await_args.args[1] == 99

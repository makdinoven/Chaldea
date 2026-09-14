"""FEAT-156 slice B (T9) — server-side drafts for RP posts.

Two layers, deliberately separated (same split as ``test_origin_starting_points.py``):

1. **CRUD against real in-memory aiosqlite.** The three rules the feature rests on —
   "one live draft per (character, location)", "an empty text is never stored" and
   "the eleventh text evicts the oldest **by ``updated_at``**" — are ordering and
   uniqueness facts. A mocked session would only prove that the code calls the
   functions it calls; it cannot prove that the oldest row is the one that dies.
2. **Routes through ``TestClient`` with the crud layer mocked.** Auth, status codes
   and the Russian error strings are pinned independently of the database.

The security case (D2/D6 on someone else's draft) lives in layer 2 and is asserted
precisely, not approximately: the endpoint must load the row first and run the
ownership check against ``row.character_id`` — never against a client-supplied id —
so the test asserts *which* character id the ownership query was given, and that a
rejected DELETE leaves the row in place.

Mocking style follows ``conftest.py`` (env vars + patched engine), ``test_action_gates.py``
(``app.dependency_overrides`` for ``get_current_user_via_http``, ``patch(..., new_callable=AsyncMock)``
for the async guards) and ``test_move_and_post_messages.py`` (URL-aware ``httpx.AsyncClient`` mock).
"""

import asyncio
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, select, func as sa_func
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
from models import Location, PostDraft  # noqa: E402
from main import app  # noqa: E402
from database import get_db  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402


# ---------------------------------------------------------------------------
# SQLite DDL hooks — MySQL-specific column types have no sqlite spelling.
# ---------------------------------------------------------------------------

@compiles(BigInteger, "sqlite")
def _bigint_as_sqlite_integer(type_, compiler, **kw):  # pragma: no cover - DDL hook
    # SQLite only auto-assigns a PK for the exact type "INTEGER".
    return "INTEGER"


@compiles(MEDIUMTEXT, "sqlite")
def _mediumtext_as_sqlite_text(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "TEXT"


@compiles(TINYINT, "sqlite")
def _tinyint_as_sqlite_integer(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


CHARACTER_ID = 100          # belongs to OWNER_USER_ID
OTHER_CHARACTER_ID = 777    # belongs to OTHER_USER_ID
OWNER_USER_ID = 5
OTHER_USER_ID = 999
LOCATION_ID = 10
OTHER_LOCATION_ID = 11


# ===========================================================================
# Layer 1 — crud against real aiosqlite
# ===========================================================================

@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    """In-memory async SQLite with only the two tables the drafts touch.

    The FK pragma is deliberately left OFF: ``post_drafts.location_id`` points at
    ``Locations``, whose own FKs (districts, regions) are irrelevant here, and the
    cascade it implements is a MySQL DDL fact, not something these tests assert.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Location.__table__.create)
        await conn.run_sync(PostDraft.__table__.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            Location(
                id=LOCATION_ID, name="Бар «Три Галки»", type="location",
                recommended_level=1, quick_travel_marker=False,
                description="d", marker_type="safe", sort_order=0,
                is_starting=False,
            ),
            Location(
                id=OTHER_LOCATION_ID, name="Воронья Церковь", type="location",
                recommended_level=1, quick_travel_marker=False,
                description="d", marker_type="safe", sort_order=0,
                is_starting=False,
            ),
        ])
        await s.commit()
        yield s

    await engine.dispose()


async def _rows(session, character_id=CHARACTER_ID):
    result = await session.execute(
        select(PostDraft)
        .where(PostDraft.character_id == character_id)
        .order_by(PostDraft.id.asc())
    )
    return list(result.scalars().all())


async def _count(session, character_id=CHARACTER_ID):
    result = await session.execute(
        select(sa_func.count()).select_from(PostDraft)
        .where(PostDraft.character_id == character_id)
    )
    return int(result.scalar_one())


def _seed_archived(session, character_id, location_id, updated_at, content="старый текст"):
    draft = PostDraft(
        character_id=character_id, location_id=location_id, content=content,
        active=None, created_at=updated_at, updated_at=updated_at,
    )
    session.add(draft)
    return draft


class TestUpsertDraft:
    """D4's engine: create, then update, the one live draft of a location."""

    @pytest.mark.asyncio
    async def test_upsert_creates_the_live_draft(self, session):
        draft = await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "<p>Первая строчка поста</p>"
        )

        assert draft is not None
        assert draft.id is not None
        assert draft.character_id == CHARACTER_ID
        assert draft.location_id == LOCATION_ID
        assert draft.content == "<p>Первая строчка поста</p>"
        # active == 1 (never 0) is what the unique key rests on.
        assert draft.active == crud.DRAFT_ACTIVE
        assert draft.is_active is True
        # A draft is not a sent post.
        assert draft.sent_at is None
        assert draft.is_sent is False
        assert await _count(session) == 1

    @pytest.mark.asyncio
    async def test_second_upsert_updates_the_same_row(self, session):
        first = await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "<p>Черновик, версия один</p>"
        )
        first_id, first_updated = first.id, first.updated_at

        second = await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "<p>Черновик, версия два</p>"
        )

        assert second.id == first_id, "autosave must update, not accumulate rows"
        assert second.content == "<p>Черновик, версия два</p>"
        assert second.updated_at >= first_updated
        assert second.active == crud.DRAFT_ACTIVE
        assert await _count(session) == 1

    @pytest.mark.asyncio
    async def test_live_draft_is_per_location(self, session):
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>В баре</p>")
        await crud.upsert_draft(
            session, CHARACTER_ID, OTHER_LOCATION_ID, "<p>В церкви</p>"
        )

        assert await _count(session) == 2
        here = await crud.get_active_draft(session, CHARACTER_ID, LOCATION_ID)
        there = await crud.get_active_draft(session, CHARACTER_ID, OTHER_LOCATION_ID)
        assert here.content == "<p>В баре</p>"
        assert there.content == "<p>В церкви</p>"

    @pytest.mark.asyncio
    async def test_empty_content_deletes_the_draft_and_returns_none(self, session):
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Есть текст</p>")
        assert await _count(session) == 1

        result = await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "")

        assert result is None
        assert await _count(session) == 0
        assert await crud.get_active_draft(session, CHARACTER_ID, LOCATION_ID) is None

    @pytest.mark.asyncio
    async def test_html_only_content_counts_as_empty(self, session):
        """TipTap leaves `<p></p>` behind when the user selects all and deletes."""
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Есть текст</p>")

        result = await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "<p></p>"
        )

        assert result is None
        assert await _count(session) == 0

    @pytest.mark.asyncio
    async def test_empty_content_without_an_existing_draft_is_a_no_op(self, session):
        result = await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "")

        assert result is None
        assert await _count(session) == 0

    @pytest.mark.asyncio
    async def test_oversized_content_raises_400_in_russian(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.upsert_draft(
                session, CHARACTER_ID, LOCATION_ID,
                "я" * (crud.MAX_DRAFT_LENGTH + 1),
            )

        assert exc.value.status_code == 400
        assert str(crud.MAX_DRAFT_LENGTH) in exc.value.detail
        assert "Черновик слишком длинный" in exc.value.detail
        assert await _count(session) == 0

    @pytest.mark.asyncio
    async def test_content_at_the_exact_limit_is_accepted(self, session):
        draft = await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "я" * crud.MAX_DRAFT_LENGTH
        )

        assert draft is not None
        assert len(draft.content) == crud.MAX_DRAFT_LENGTH

    @pytest.mark.asyncio
    async def test_sql_injection_in_content_is_stored_as_data(self, session):
        """Content is bound, never interpolated — the table must survive it."""
        payload = "'; DROP TABLE post_drafts; --"

        draft = await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, payload)

        assert draft.content == payload
        assert await _count(session) == 1


class TestEviction:
    """The 10-item cap: the oldest text **by ``updated_at``** is the one that dies."""

    @pytest.mark.asyncio
    async def test_eleventh_text_evicts_the_oldest_by_updated_at(self, session):
        base = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
        # Ids ascend while updated_at DESCENDS, so "oldest" can never be mistaken
        # for "lowest id" or "first inserted".
        seeded = []
        for offset in range(crud.MAX_DRAFTS_PER_CHARACTER):
            seeded.append(_seed_archived(
                session, CHARACTER_ID, LOCATION_ID,
                base - timedelta(minutes=offset), content=f"текст {offset}",
            ))
        await session.commit()
        oldest = seeded[-1]                 # highest id, smallest updated_at
        oldest_id = oldest.id
        survivor_ids = {d.id for d in seeded[:-1]}
        assert await _count(session) == crud.MAX_DRAFTS_PER_CHARACTER

        fresh = await crud.upsert_draft(
            session, CHARACTER_ID, OTHER_LOCATION_ID, "<p>Одиннадцатый текст</p>"
        )

        assert await _count(session) == crud.MAX_DRAFTS_PER_CHARACTER
        remaining = {d.id for d in await _rows(session)}
        assert oldest_id not in remaining, "the least recently updated row must go"
        assert survivor_ids | {fresh.id} == remaining

    @pytest.mark.asyncio
    async def test_eviction_is_scoped_to_one_character(self, session):
        base = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
        for offset in range(crud.MAX_DRAFTS_PER_CHARACTER):
            _seed_archived(
                session, OTHER_CHARACTER_ID, LOCATION_ID,
                base - timedelta(minutes=offset),
            )
        await session.commit()

        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Мой</p>")

        # The cap is per character (Q2 in section 3.11) — the neighbour keeps ten.
        assert await _count(session, OTHER_CHARACTER_ID) == crud.MAX_DRAFTS_PER_CHARACTER
        assert await _count(session, CHARACTER_ID) == 1

    @pytest.mark.asyncio
    async def test_evict_drafts_is_a_no_op_below_the_cap(self, session):
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Один</p>")

        assert await crud.evict_drafts(session, CHARACTER_ID) == 0
        assert await _count(session) == 1


class TestArchiveOnPost:
    """A sent post turns the live draft into a «дописанный» archived row."""

    @pytest.mark.asyncio
    async def test_successful_post_archives_the_live_draft(self, session):
        live = await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "<p>Недописанный автосейв</p>"
        )

        archived = await crud.archive_draft_on_post(
            session, CHARACTER_ID, LOCATION_ID, "<p>Финальный отправленный текст</p>"
        )

        assert archived.id == live.id, "the same row is archived, not a copy"
        assert archived.active is None          # live slot released
        assert archived.is_active is False
        assert archived.sent_at is not None     # «дописанный»
        assert archived.is_sent is True
        # The last autosave may lag behind the final edit — the posted text wins.
        assert archived.content == "<p>Финальный отправленный текст</p>"
        assert await crud.get_active_draft(session, CHARACTER_ID, LOCATION_ID) is None
        assert await _count(session) == 1

    @pytest.mark.asyncio
    async def test_archive_inserts_a_row_when_no_live_draft_exists(self, session):
        """The draft API may have been down while the player was typing."""
        archived = await crud.archive_draft_on_post(
            session, CHARACTER_ID, LOCATION_ID, "<p>Пост без автосейва</p>"
        )

        assert archived.id is not None
        assert archived.active is None
        assert archived.sent_at is not None
        assert archived.content == "<p>Пост без автосейва</p>"
        assert await _count(session) == 1

    @pytest.mark.asyncio
    async def test_archiving_frees_the_live_slot_for_a_new_draft(self, session):
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Первый</p>")
        await crud.archive_draft_on_post(
            session, CHARACTER_ID, LOCATION_ID, "<p>Первый</p>"
        )

        # The unique key is (character, location, active); NULLs are distinct, so
        # a fresh live draft in the same location must still be insertable.
        again = await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "<p>Второй</p>"
        )

        assert again.active == crud.DRAFT_ACTIVE
        assert await _count(session) == 2


class TestDeleteAndList:

    @pytest.mark.asyncio
    async def test_delete_active_draft_is_idempotent(self, session):
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Текст</p>")

        assert await crud.delete_active_draft(session, CHARACTER_ID, LOCATION_ID) == 1
        assert await crud.delete_active_draft(session, CHARACTER_ID, LOCATION_ID) == 0
        assert await _count(session) == 0

    @pytest.mark.asyncio
    async def test_delete_active_draft_leaves_archived_rows_alone(self, session):
        await crud.archive_draft_on_post(
            session, CHARACTER_ID, LOCATION_ID, "<p>Отправленный</p>"
        )
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Живой</p>")

        assert await crud.delete_active_draft(session, CHARACTER_ID, LOCATION_ID) == 1

        rows = await _rows(session)
        assert len(rows) == 1
        assert rows[0].is_sent is True

    @pytest.mark.asyncio
    async def test_delete_draft_by_id_is_idempotent(self, session):
        draft = await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "<p>Текст</p>"
        )

        assert await crud.delete_draft_by_id(session, draft.id) == 1
        assert await crud.delete_draft_by_id(session, draft.id) == 0

    @pytest.mark.asyncio
    async def test_list_drafts_is_newest_first_capped_and_without_content(self, session):
        base = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
        for offset in range(12):
            _seed_archived(
                session, CHARACTER_ID, LOCATION_ID,
                base - timedelta(minutes=offset), content=f"<p>текст {offset}</p>",
            )
        await session.commit()

        items = await crud.list_drafts(session, CHARACTER_ID)

        assert len(items) == crud.MAX_DRAFTS_PER_CHARACTER
        assert [i["preview"] for i in items][0] == "текст 0"
        assert all("content" not in i for i in items)
        assert items[0]["location_name"] == "Бар «Три Галки»"
        assert items[0]["char_count"] == len("текст 0")

    @pytest.mark.asyncio
    async def test_list_drafts_previews_are_plain_text_and_truncated(self, session):
        long_text = "б" * (crud.DRAFT_PREVIEW_LENGTH + 50)
        await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, f"<p><strong>{long_text}</strong></p>"
        )

        items = await crud.list_drafts(session, CHARACTER_ID)

        assert len(items) == 1
        assert "<" not in items[0]["preview"]
        assert items[0]["preview"].endswith("…")
        assert len(items[0]["preview"]) == crud.DRAFT_PREVIEW_LENGTH + 1
        assert items[0]["char_count"] == len(long_text)
        assert items[0]["is_active"] is True
        assert items[0]["is_sent"] is False

    @pytest.mark.asyncio
    async def test_list_drafts_of_another_character_is_empty(self, session):
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Мой</p>")

        assert await crud.list_drafts(session, OTHER_CHARACTER_ID) == []


# ===========================================================================
# Layer 2 — routes D1..D6 through TestClient
# ===========================================================================

CHARACTER_OWNERS = {CHARACTER_ID: OWNER_USER_ID, OTHER_CHARACTER_ID: OTHER_USER_ID}


def _ownership_session(owners=None):
    """Async session mock that answers only `SELECT user_id FROM characters`.

    `verify_character_ownership` is the real function in these tests — the whole
    point of the 403 case is *which* character id it is handed.
    """
    owners = CHARACTER_OWNERS if owners is None else owners
    session = AsyncMock()
    session.ownership_calls = []

    def _execute(statement, params=None, *args, **kwargs):
        result = MagicMock()
        if params and "cid" in params:
            session.ownership_calls.append(params["cid"])
            user_id = owners.get(params["cid"])
            result.fetchone.return_value = None if user_id is None else (user_id,)
        else:
            result.fetchone.return_value = None
            result.scalars.return_value.first.return_value = None
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


@contextmanager
def _client(session, user_id=OWNER_USER_ID, authenticate=True):
    async def _fake_get_db():
        yield session

    app.dependency_overrides[get_db] = _fake_get_db
    if authenticate:
        app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
            id=user_id, username="owner", role="user", permissions=[]
        )
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user_via_http, None)


def _draft_row(draft_id=1, character_id=CHARACTER_ID, location_id=LOCATION_ID,
               content="<p>Чужой текст</p>"):
    now = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
    return PostDraft(
        id=draft_id, character_id=character_id, location_id=location_id,
        content=content, active=crud.DRAFT_ACTIVE, sent_at=None,
        created_at=now, updated_at=now,
    )


AUTH = {"Authorization": "Bearer fake-token"}


# ── every route is closed without a token ─────────────────────────────────
ROUTES = [
    ("get", f"/locations/drafts?character_id={CHARACTER_ID}", None),
    ("get", "/locations/drafts/1", None),
    ("delete", "/locations/drafts/1", None),
    ("get", f"/locations/{LOCATION_ID}/draft?character_id={CHARACTER_ID}", None),
    ("put", f"/locations/{LOCATION_ID}/draft",
     {"character_id": CHARACTER_ID, "content": "<p>Текст</p>"}),
    ("delete", f"/locations/{LOCATION_ID}/draft?character_id={CHARACTER_ID}", None),
]


class TestDraftRoutesRequireAToken:

    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_no_token_is_401(self, method, path, body):
        """No Authorization header at all — the route must never reach the DB."""
        with _client(_ownership_session(), authenticate=False) as client:
            response = getattr(client, method)(
                path, **({"json": body} if body is not None else {})
            )

        assert response.status_code == 401


# ── D2 / D6: a draft belonging to another player ──────────────────────────
class TestCrossUserDraftAccessIsForbidden:
    """The key security case: authorisation runs on the **row's** character_id."""

    def test_d2_returns_403_and_leaks_no_content(self):
        foreign = _draft_row(draft_id=42, character_id=OTHER_CHARACTER_ID)
        session = _ownership_session()

        with patch("main.crud.get_draft_by_id", new_callable=AsyncMock,
                   return_value=foreign) as get_row:
            with _client(session, user_id=OWNER_USER_ID) as client:
                response = client.get("/locations/drafts/42", headers=AUTH)

        assert response.status_code == 403
        assert response.json()["detail"] == "Вы можете управлять только своими персонажами"
        assert "Чужой текст" not in response.text
        get_row.assert_awaited_once()
        # Authorised on the row's owner (777), never on anything from the client.
        assert session.ownership_calls == [OTHER_CHARACTER_ID]

    def test_d6_returns_403_and_the_row_survives(self):
        """A rejected DELETE must leave the other player's draft in place."""
        store = {42: _draft_row(draft_id=42, character_id=OTHER_CHARACTER_ID)}

        async def _get(_session, draft_id):
            return store.get(draft_id)

        async def _delete(_session, draft_id):
            return 1 if store.pop(draft_id, None) else 0

        session = _ownership_session()
        with patch("main.crud.get_draft_by_id", side_effect=_get), \
             patch("main.crud.delete_draft_by_id", side_effect=_delete) as deleter:
            with _client(session, user_id=OWNER_USER_ID) as client:
                response = client.delete("/locations/drafts/42", headers=AUTH)

        assert response.status_code == 403
        deleter.assert_not_awaited()
        assert 42 in store, "the foreign draft must still exist after a rejected DELETE"
        assert session.ownership_calls == [OTHER_CHARACTER_ID]

    def test_d1_returns_403_for_another_players_character(self):
        session = _ownership_session()
        with patch("main.crud.list_drafts", new_callable=AsyncMock,
                   return_value=[]) as lister:
            with _client(session, user_id=OWNER_USER_ID) as client:
                response = client.get(
                    f"/locations/drafts?character_id={OTHER_CHARACTER_ID}",
                    headers=AUTH,
                )

        assert response.status_code == 403
        lister.assert_not_awaited()

    def test_d4_returns_403_for_another_players_character(self):
        session = _ownership_session()
        with patch("main.crud.upsert_draft", new_callable=AsyncMock) as upsert:
            with _client(session, user_id=OWNER_USER_ID) as client:
                response = client.put(
                    f"/locations/{LOCATION_ID}/draft",
                    json={"character_id": OTHER_CHARACTER_ID, "content": "<p>Х</p>"},
                    headers=AUTH,
                )

        assert response.status_code == 403
        upsert.assert_not_awaited()

    def test_unknown_character_is_404(self):
        session = _ownership_session()
        with _client(session, user_id=OWNER_USER_ID) as client:
            response = client.get(
                "/locations/drafts?character_id=123456", headers=AUTH
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Персонаж не найден"


class TestMissingDraft:

    @pytest.mark.parametrize("method", ["get", "delete"])
    def test_missing_draft_is_404_in_russian(self, method):
        session = _ownership_session()
        with patch("main.crud.get_draft_by_id", new_callable=AsyncMock,
                   return_value=None):
            with _client(session) as client:
                response = getattr(client, method)(
                    "/locations/drafts/999", headers=AUTH
                )

        assert response.status_code == 404
        assert response.json()["detail"] == "Черновик не найден"


class TestSaveAndClearRoutes:

    def test_d4_rejects_oversized_content_with_a_russian_400(self):
        session = _ownership_session()
        with patch("main.crud.upsert_draft", new_callable=AsyncMock) as upsert:
            with _client(session) as client:
                response = client.put(
                    f"/locations/{LOCATION_ID}/draft",
                    json={
                        "character_id": CHARACTER_ID,
                        "content": "я" * (crud.MAX_DRAFT_LENGTH + 1),
                    },
                    headers=AUTH,
                )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail == (
            f"Черновик слишком длинный — максимум {crud.MAX_DRAFT_LENGTH} символов"
        )
        # Rejected before the DB round-trip.
        upsert.assert_not_awaited()

    def test_d4_returns_null_when_the_content_was_empty(self):
        session = _ownership_session()
        with patch("main.crud.upsert_draft", new_callable=AsyncMock,
                   return_value=None) as upsert:
            with _client(session) as client:
                response = client.put(
                    f"/locations/{LOCATION_ID}/draft",
                    json={"character_id": CHARACTER_ID, "content": ""},
                    headers=AUTH,
                )

        assert response.status_code == 200
        assert response.json() is None
        upsert.assert_awaited_once()

    def test_d4_saves_and_returns_the_draft(self):
        session = _ownership_session()
        saved = _draft_row(draft_id=7, content="<p>Сохранено</p>")
        with patch("main.crud.upsert_draft", new_callable=AsyncMock,
                   return_value=saved):
            with _client(session) as client:
                response = client.put(
                    f"/locations/{LOCATION_ID}/draft",
                    json={"character_id": CHARACTER_ID, "content": "<p>Сохранено</p>"},
                    headers=AUTH,
                )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == 7
        assert body["content"] == "<p>Сохранено</p>"
        assert body["is_active"] is True
        assert body["is_sent"] is False

    def test_d3_returns_null_when_there_is_no_live_draft(self):
        session = _ownership_session()
        with patch("main.crud.get_active_draft", new_callable=AsyncMock,
                   return_value=None):
            with _client(session) as client:
                response = client.get(
                    f"/locations/{LOCATION_ID}/draft?character_id={CHARACTER_ID}",
                    headers=AUTH,
                )

        assert response.status_code == 200
        assert response.json() is None

    def test_d5_is_idempotent(self):
        """«Очистить черновик» twice in a row: 204 both times."""
        session = _ownership_session()
        rowcounts = iter([1, 0])

        async def _delete(_session, character_id, location_id):
            return next(rowcounts)

        with patch("main.crud.delete_active_draft", side_effect=_delete):
            with _client(session) as client:
                first = client.delete(
                    f"/locations/{LOCATION_ID}/draft?character_id={CHARACTER_ID}",
                    headers=AUTH,
                )
                second = client.delete(
                    f"/locations/{LOCATION_ID}/draft?character_id={CHARACTER_ID}",
                    headers=AUTH,
                )

        assert first.status_code == 204
        assert second.status_code == 204
        assert first.content == b""
        assert second.content == b""

    def test_d6_deletes_an_own_draft(self):
        session = _ownership_session()
        own = _draft_row(draft_id=8, character_id=CHARACTER_ID)
        with patch("main.crud.get_draft_by_id", new_callable=AsyncMock,
                   return_value=own), \
             patch("main.crud.delete_draft_by_id", new_callable=AsyncMock,
                   return_value=1) as deleter:
            with _client(session) as client:
                response = client.delete("/locations/drafts/8", headers=AUTH)

        assert response.status_code == 204
        deleter.assert_awaited_once()
        assert session.ownership_calls == [CHARACTER_ID]


# ===========================================================================
# Layer 2b — archive-on-send inside move_and_post
# ===========================================================================

POST_CONTENT = "Персонаж делает шаг вперёд. " * 20   # > MIN_POST_LENGTH plain chars
NEW_POST_ID = 555


def _created_post():
    post = MagicMock()
    post.id = NEW_POST_ID
    post.character_id = CHARACTER_ID
    post.location_id = LOCATION_ID
    post.content = POST_CONTENT
    post.created_at = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
    return post


def _http_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _httpx_for_a_successful_post():
    """`async with httpx.AsyncClient(...)` mock for the whole happy path.

    The character stays in `LOCATION_ID` (profile reports it as the current one),
    so movement_cost is 0: no adjacency lookup and no travel cooldown.
    """
    instance = AsyncMock()
    instance.__aenter__.return_value = instance
    instance.__aexit__.return_value = False

    async def _get(url, *args, **kwargs):
        if "/profile" in url:
            return _http_response(200, {
                "current_location_id": LOCATION_ID,
                "travel_cooldown_until": None,
                "character_name": "Лоен",
            })
        if "/attributes/" in url:
            return _http_response(200, {"current_stamina": 100})
        raise AssertionError(f"unexpected outbound GET: {url}")

    async def _put(url, *args, **kwargs):
        return _http_response(200, {})

    async def _post(url, *args, **kwargs):
        return _http_response(200, {})

    instance.get.side_effect = _get
    instance.put.side_effect = _put
    instance.post.side_effect = _post
    return instance


@contextmanager
def _move_and_post_env(archive_mock):
    """Everything move_and_post touches, mocked, except the archive call."""
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = (OWNER_USER_ID,)
    result.scalars.return_value.first.return_value = None  # destination Location
    session.execute = AsyncMock(return_value=result)

    async def _fake_get_db():
        yield session

    app.dependency_overrides[get_db] = _fake_get_db
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=OWNER_USER_ID, username="owner", role="user", permissions=[]
    )
    try:
        with patch("main.verify_character_ownership", new_callable=AsyncMock), \
             patch("main.check_not_in_battle", new_callable=AsyncMock), \
             patch("main.check_not_gathering", new_callable=AsyncMock), \
             patch("main.crud.create_post", new_callable=AsyncMock,
                   return_value=_created_post()) as create_post, \
             patch("main.crud.archive_draft_on_post", archive_mock), \
             patch("main.crud.get_favorite_user_ids", new_callable=AsyncMock,
                   return_value=[]), \
             patch("main.crud.award_post_xp_and_log", new_callable=AsyncMock), \
             patch("main._try_spawn_mob", new_callable=AsyncMock), \
             patch("main._track_cumulative_stats", new_callable=AsyncMock), \
             patch("main._auto_progress_quest", new_callable=AsyncMock), \
             patch("httpx.AsyncClient",
                   return_value=_httpx_for_a_successful_post()):
            with TestClient(app) as client:
                yield client, create_post
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user_via_http, None)


def _send_post(client):
    return client.post(
        f"/locations/{LOCATION_ID}/move_and_post",
        json={"character_id": CHARACTER_ID, "content": POST_CONTENT},
        headers=AUTH,
    )


class TestArchiveOnSendInsideMoveAndPost:

    def test_successful_post_archives_the_live_draft(self):
        archive = AsyncMock()
        with _move_and_post_env(archive) as (client, create_post):
            response = _send_post(client)

        assert response.status_code == 200
        assert response.json()["id"] == NEW_POST_ID
        create_post.assert_awaited_once()
        archive.assert_awaited_once()
        # (session, character_id, location_id, content) — the posted text, so the
        # archived row matches what the player actually sent.
        args = archive.await_args.args
        assert args[1] == CHARACTER_ID
        assert args[2] == LOCATION_ID
        assert args[3] == POST_CONTENT

    def test_post_still_succeeds_when_archiving_raises(self):
        """Draft bookkeeping must never fail a post the database already took.

        `create_post` has committed by the time `archive_draft_on_post` runs, so
        letting its failure propagate would return an error for a post that exists —
        exactly the class of bug this feature was written to remove.
        """
        archive = AsyncMock(side_effect=RuntimeError("post_drafts is on fire"))
        with _move_and_post_env(archive) as (client, create_post):
            response = _send_post(client)

        assert response.status_code == 200, "a draft failure must not fail the post"
        assert response.json()["id"] == NEW_POST_ID
        create_post.assert_awaited_once()   # the post WAS created
        archive.assert_awaited_once()       # and archiving really did blow up


# ===========================================================================
# Layer 3 — D7, the character-deletion cleanup hook (T18)
# ===========================================================================
#
# D7 is the one draft route that is NOT ownership-scoped: the character row is
# already being destroyed by character-service when it fires, so
# `verify_character_ownership` would 404. It is guarded by RBAC instead
# (`locations:delete`), and the token it runs under is the one that was allowed
# to delete the character.
#
# Two properties matter and are asserted separately:
#   * blast radius — only `post_drafts` of *that* character die (layer 3a, real
#     aiosqlite, because "did the neighbour's row survive" is a database fact);
#   * access + shape — 200/count, idempotency, 403, 401 (layer 3b, routes).

from models import Post  # noqa: E402


async def _create_posts_table(session):
    """Add `posts` to the throwaway SQLite DB used by the crud layer."""
    def _create(sync_session):
        Post.__table__.create(sync_session.connection(), checkfirst=True)

    await session.run_sync(_create)


async def _post_ids(session, character_id):
    result = await session.execute(
        select(Post.id).where(Post.character_id == character_id).order_by(Post.id)
    )
    return list(result.scalars().all())


class TestD7DeletesDraftsByCharacter:
    """`crud.delete_drafts_by_character` — the blast radius of the cleanup."""

    @pytest.mark.asyncio
    async def test_deletes_every_draft_of_the_character(self, session):
        """Both kinds of row go: the live draft and the archived history."""
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Живой</p>")
        _seed_archived(
            session, CHARACTER_ID, OTHER_LOCATION_ID,
            datetime(2026, 9, 1, tzinfo=timezone.utc), content="<p>Архивный</p>",
        )
        await session.commit()
        assert await _count(session) == 2

        deleted = await crud.delete_drafts_by_character(session, CHARACTER_ID)

        assert deleted == 2
        assert await _count(session) == 0

    @pytest.mark.asyncio
    async def test_other_characters_drafts_survive(self, session):
        """The key scoping case: one character is deleted, not the location."""
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Мой</p>")
        await crud.upsert_draft(
            session, OTHER_CHARACTER_ID, LOCATION_ID, "<p>Соседский</p>"
        )
        await crud.upsert_draft(
            session, OTHER_CHARACTER_ID, OTHER_LOCATION_ID, "<p>Соседский-2</p>"
        )

        deleted = await crud.delete_drafts_by_character(session, CHARACTER_ID)

        assert deleted == 1
        assert await _count(session, CHARACTER_ID) == 0
        assert await _count(session, OTHER_CHARACTER_ID) == 2
        survivors = [d.content for d in await _rows(session, OTHER_CHARACTER_ID)]
        assert survivors == ["<p>Соседский</p>", "<p>Соседский-2</p>"]

    @pytest.mark.asyncio
    async def test_posts_are_not_touched(self, session):
        """Drafts only — see 3.12 "Why drafts only".

        A deleted character's posts stay: other players' posts in the same
        location read them as narrative context, so removing them would tear a
        hole in the shared RP history. This test is the guard on that decision.
        """
        await _create_posts_table(session)
        session.add_all([
            Post(id=1, character_id=CHARACTER_ID, location_id=LOCATION_ID,
                 content="Пост удаляемого персонажа", post_type="regular"),
            Post(id=2, character_id=OTHER_CHARACTER_ID, location_id=LOCATION_ID,
                 content="Пост соседа", post_type="regular"),
        ])
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Черновик</p>")

        deleted = await crud.delete_drafts_by_character(session, CHARACTER_ID)

        assert deleted == 1
        assert await _count(session, CHARACTER_ID) == 0
        assert await _post_ids(session, CHARACTER_ID) == [1]
        assert await _post_ids(session, OTHER_CHARACTER_ID) == [2]

    @pytest.mark.asyncio
    async def test_second_call_is_idempotent(self, session):
        """character-service may retry; a no-op cleanup must report 0, not fail."""
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Живой</p>")

        assert await crud.delete_drafts_by_character(session, CHARACTER_ID) == 1
        assert await crud.delete_drafts_by_character(session, CHARACTER_ID) == 0

    @pytest.mark.asyncio
    async def test_unknown_character_is_not_an_error(self, session):
        assert await crud.delete_drafts_by_character(session, 424242) == 0


D7_PATH = f"/locations/admin/drafts/by_character/{CHARACTER_ID}"


@contextmanager
def _rbac_client(session, permissions):
    """TestClient authenticated as a user holding exactly `permissions`.

    D7's guard is `require_permission("locations:delete")`, whose own dependency
    is `get_current_user_via_http` — so overriding the user is enough to drive
    the permission check for real, rather than stubbing it out.
    """
    async def _fake_get_db():
        yield session

    app.dependency_overrides[get_db] = _fake_get_db
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=1, username="admin", role="admin", permissions=list(permissions)
    )
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user_via_http, None)


class TestD7Route:

    def test_returns_200_and_the_deleted_count(self):
        session = AsyncMock()
        with patch("main.crud.delete_drafts_by_character", new_callable=AsyncMock,
                   return_value=3) as cleanup:
            with _rbac_client(session, ["locations:delete"]) as client:
                response = client.delete(D7_PATH, headers=AUTH)

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 3
        assert "detail" in body
        cleanup.assert_awaited_once()
        assert cleanup.await_args.args[1] == CHARACTER_ID

    def test_second_call_returns_count_zero(self):
        """Idempotent: a retry from character-service must still be a 200."""
        session = AsyncMock()
        counts = iter([2, 0])

        async def _cleanup(_session, _character_id):
            return next(counts)

        with patch("main.crud.delete_drafts_by_character", side_effect=_cleanup):
            with _rbac_client(session, ["locations:delete"]) as client:
                first = client.delete(D7_PATH, headers=AUTH)
                second = client.delete(D7_PATH, headers=AUTH)

        assert first.status_code == 200
        assert first.json()["count"] == 2
        assert second.status_code == 200
        assert second.json()["count"] == 0

    def test_403_without_the_locations_delete_permission(self):
        """A token that may not delete locations may not wipe drafts either."""
        session = AsyncMock()
        with patch("main.crud.delete_drafts_by_character",
                   new_callable=AsyncMock) as cleanup:
            with _rbac_client(session, ["locations:read"]) as client:
                response = client.delete(D7_PATH, headers=AUTH)

        assert response.status_code == 403
        assert response.json()["detail"] == "Недостаточно прав"
        cleanup.assert_not_awaited()

    def test_401_without_a_token(self):
        session = AsyncMock()

        async def _fake_get_db():
            yield session

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with patch("main.crud.delete_drafts_by_character",
                       new_callable=AsyncMock) as cleanup:
                with TestClient(app) as client:
                    response = client.delete(D7_PATH)
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 401
        cleanup.assert_not_awaited()

    def test_the_admin_route_is_not_swallowed_by_the_location_id_routes(self):
        """`/locations/admin/...` must not be parsed as `/locations/{location_id}`.

        A 422 here would mean FastAPI matched a numeric-path route instead and
        the cleanup silently never ran.
        """
        session = AsyncMock()
        with patch("main.crud.delete_drafts_by_character", new_callable=AsyncMock,
                   return_value=0):
            with _rbac_client(session, ["locations:delete"]) as client:
                response = client.delete(D7_PATH, headers=AUTH)

        assert response.status_code == 200


# ===========================================================================
# Layer 4 — «Отмена» retires the draft instead of destroying it (T21, §3.13)
# ===========================================================================
# D5 gained one optional query parameter, `keep_in_history`, and the crud
# function behind it, `archive_active_draft`. The distinction it draws is the
# whole point of the ruling, so it is asserted on rows, never on call counts:
#
#   * layer 4a (real aiosqlite) — what happens to the row. The core regression
#     is "cancel, write again in the same location, the cancelled text is still
#     there": it proves the live slot was genuinely freed, rather than the new
#     text upserting over the retired row through `uq_post_drafts_active`.
#   * layer 4b (routes, crud mocked) — that the parameter selects the right
#     crud function, that omitting it keeps the shipped «Очистить черновик»
#     behaviour byte for byte, and that the extended route is no laxer about
#     ownership than it was.


def _seed_live(session, character_id, location_id, updated_at,
               content="<p>Недописанный текст</p>"):
    """A live draft with an explicitly old `updated_at`.

    `upsert_draft` would stamp `updated_at = now`, which makes the deliberate
    bump inside `archive_active_draft` unobservable within one test run.
    """
    draft = PostDraft(
        character_id=character_id, location_id=location_id, content=content,
        active=crud.DRAFT_ACTIVE, sent_at=None,
        created_at=updated_at, updated_at=updated_at,
    )
    session.add(draft)
    return draft


class TestArchiveActiveDraft:
    """`crud.archive_active_draft` — the row after «Отмена»."""

    @pytest.mark.asyncio
    async def test_cancel_retires_the_row_and_keeps_the_text(self, session):
        """`active` NULL, `sent_at` still NULL, content untouched, one row."""
        old = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc)
        live = _seed_live(session, CHARACTER_ID, LOCATION_ID, old,
                          content="<p>Два часа работы</p>")
        await session.commit()
        live_id = live.id

        retired = await crud.archive_active_draft(session, CHARACTER_ID, LOCATION_ID)

        assert retired == 1
        rows = await _rows(session)
        assert [r.id for r in rows] == [live_id], "the row is retired, not copied"
        row = rows[0]
        assert row.active is None                      # live slot released
        assert row.is_active is False
        assert row.sent_at is None, "a cancelled text never became a post"
        assert row.is_sent is False
        assert row.content == "<p>Два часа работы</p>"  # the text is the point
        assert row.created_at == old
        assert row.updated_at > old, "the writer just touched it — it sorts to the top"

    @pytest.mark.asyncio
    async def test_cancel_then_write_again_keeps_the_cancelled_text(self, session):
        """**The core regression** (§3.13).

        Cancel, then write a new post in the *same* location. If the live slot
        had only been emptied in the editor and not in the table, the next
        autosave would upsert over that very row and the cancelled text would be
        gone — the exact loss this whole feature exists to prevent.
        """
        cancelled = await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "<p>Отменённый текст</p>"
        )
        cancelled_id = cancelled.id

        await crud.archive_active_draft(session, CHARACTER_ID, LOCATION_ID)
        fresh = await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "<p>Новый текст</p>"
        )

        assert fresh.id != cancelled_id, "a new post must start a new row"
        assert fresh.active == crud.DRAFT_ACTIVE
        assert await _count(session) == 2

        survivor = next(r for r in await _rows(session) if r.id == cancelled_id)
        assert survivor.content == "<p>Отменённый текст</p>"
        assert survivor.active is None
        assert survivor.sent_at is None

    @pytest.mark.asyncio
    async def test_the_editor_opens_empty_after_a_cancel(self, session):
        """D3 reads `get_active_draft`, so it must answer `None` here."""
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Текст</p>")

        await crud.archive_active_draft(session, CHARACTER_ID, LOCATION_ID)

        assert await crud.get_active_draft(session, CHARACTER_ID, LOCATION_ID) is None
        assert await _count(session) == 1, "empty editor, but the text is kept"

    @pytest.mark.asyncio
    async def test_the_cancelled_row_renders_as_a_draft_not_as_sent(self, session):
        """`DraftsPanel` badges on `is_sent` — a cancelled text is «Черновик»."""
        await crud.upsert_draft(
            session, CHARACTER_ID, LOCATION_ID, "<p>Отменённый текст</p>"
        )
        await crud.archive_active_draft(session, CHARACTER_ID, LOCATION_ID)

        items = await crud.list_drafts(session, CHARACTER_ID)

        assert len(items) == 1
        assert items[0]["is_sent"] is False, "«Отправлен» would be a lie"
        assert items[0]["is_active"] is False
        assert items[0]["preview"] == "Отменённый текст"
        assert items[0]["location_name"] == "Бар «Три Галки»"

    @pytest.mark.asyncio
    async def test_archiving_with_no_live_draft_retires_nothing(self, session):
        """Idempotency: nothing to keep, so nothing is invented or disturbed."""
        _seed_archived(session, CHARACTER_ID, LOCATION_ID,
                       datetime(2026, 9, 1, tzinfo=timezone.utc),
                       content="<p>Старое</p>")
        await session.commit()
        # Read back through the DB: SQLite returns the stamp naive, so the
        # "unchanged" comparison has to be against the stored value, not the seed.
        before = (await _rows(session))[0].updated_at

        assert await crud.archive_active_draft(session, CHARACTER_ID, LOCATION_ID) == 0

        rows = await _rows(session)
        assert len(rows) == 1
        assert rows[0].content == "<p>Старое</p>"
        assert rows[0].updated_at == before

    @pytest.mark.asyncio
    async def test_archiving_twice_retires_only_once(self, session):
        """A double-click on «Отмена» must not disturb the row it already kept."""
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Текст</p>")

        assert await crud.archive_active_draft(session, CHARACTER_ID, LOCATION_ID) == 1
        first_updated_at = (await _rows(session))[0].updated_at

        assert await crud.archive_active_draft(session, CHARACTER_ID, LOCATION_ID) == 0

        rows = await _rows(session)
        assert len(rows) == 1
        assert rows[0].updated_at == first_updated_at
        assert rows[0].content == "<p>Текст</p>"

    @pytest.mark.asyncio
    async def test_cancel_touches_only_this_character_and_location(self, session):
        """Scoping: my other location and the neighbour keep their live drafts."""
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Отменяемый</p>")
        elsewhere = await crud.upsert_draft(
            session, CHARACTER_ID, OTHER_LOCATION_ID, "<p>Другая локация</p>"
        )
        neighbour = await crud.upsert_draft(
            session, OTHER_CHARACTER_ID, LOCATION_ID, "<p>Соседский</p>"
        )

        assert await crud.archive_active_draft(session, CHARACTER_ID, LOCATION_ID) == 1

        still_live = await crud.get_active_draft(
            session, CHARACTER_ID, OTHER_LOCATION_ID)
        assert still_live is not None and still_live.id == elsewhere.id
        neighbours = await crud.get_active_draft(
            session, OTHER_CHARACTER_ID, LOCATION_ID)
        assert neighbours is not None and neighbours.id == neighbour.id

    @pytest.mark.asyncio
    async def test_a_sent_row_in_the_same_location_is_left_alone(self, session):
        """`sent_at` is never cleared: «Отправлен» must not degrade to «Черновик»."""
        sent = await crud.archive_draft_on_post(
            session, CHARACTER_ID, LOCATION_ID, "<p>Отправленный</p>"
        )
        sent_id, sent_at = sent.id, sent.sent_at
        await crud.upsert_draft(session, CHARACTER_ID, LOCATION_ID, "<p>Новый</p>")

        assert await crud.archive_active_draft(session, CHARACTER_ID, LOCATION_ID) == 1

        rows = {r.id: r for r in await _rows(session)}
        assert len(rows) == 2
        assert rows[sent_id].sent_at == sent_at
        assert rows[sent_id].content == "<p>Отправленный</p>"
        cancelled = next(r for r in rows.values() if r.id != sent_id)
        assert cancelled.sent_at is None
        assert cancelled.content == "<p>Новый</p>"

    @pytest.mark.asyncio
    async def test_a_cancelled_draft_is_still_one_of_the_ten(self, session):
        """Eviction keeps working: the cap counts retired texts too, and the
        just-cancelled one leads the list (§3.13 — `updated_at` is bumped on
        purpose, so it is the last of the ten to age out, not the first)."""
        base = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
        for offset in range(crud.MAX_DRAFTS_PER_CHARACTER):
            _seed_archived(
                session, CHARACTER_ID, LOCATION_ID,
                base - timedelta(minutes=offset), content=f"<p>текст {offset}</p>",
            )
        await session.commit()

        # The eleventh text evicts the oldest, as always...
        live = await crud.upsert_draft(
            session, CHARACTER_ID, OTHER_LOCATION_ID, "<p>Одиннадцатый</p>"
        )
        assert await _count(session) == crud.MAX_DRAFTS_PER_CHARACTER

        # ...and cancelling it keeps it inside that same cap, not outside it.
        assert await crud.archive_active_draft(
            session, CHARACTER_ID, OTHER_LOCATION_ID) == 1

        assert await _count(session) == crud.MAX_DRAFTS_PER_CHARACTER
        items = await crud.list_drafts(session, CHARACTER_ID)
        assert items[0]["id"] == live.id, "the text just cancelled leads the list"
        assert items[0]["is_sent"] is False
        assert items[0]["is_active"] is False


D5_PATH = f"/locations/{LOCATION_ID}/draft"


@contextmanager
def _d5_crud_mocks():
    """Both D5 branches patched at once, so each test asserts *which* one ran.

    Asserting only "archive was awaited" would still pass if the route also
    hard-deleted the row; the two branches are mutually exclusive by design.
    """
    with patch("main.crud.archive_active_draft", new_callable=AsyncMock,
               return_value=1) as archive, \
         patch("main.crud.delete_active_draft", new_callable=AsyncMock,
               return_value=1) as hard_delete:
        yield archive, hard_delete


class TestD5KeepInHistory:
    """The route half: the parameter picks a branch, the default keeps the old one."""

    @pytest.mark.parametrize("raw", ["true", "True", "1"])
    def test_keep_in_history_true_archives_instead_of_deleting(self, raw):
        session = _ownership_session()
        with _d5_crud_mocks() as (archive, hard_delete):
            with _client(session) as client:
                response = client.delete(
                    f"{D5_PATH}?character_id={CHARACTER_ID}&keep_in_history={raw}",
                    headers=AUTH,
                )

        assert response.status_code == 204
        assert response.content == b""
        # «Отмена» must never reach the destructive branch.
        hard_delete.assert_not_awaited()
        archive.assert_awaited_once()
        assert archive.await_args.args[1:] == (CHARACTER_ID, LOCATION_ID)

    @pytest.mark.parametrize("query", [
        "",                         # omitted — the shipped «Очистить черновик»
        "&keep_in_history=false",
        "&keep_in_history=False",
        "&keep_in_history=0",
    ])
    def test_default_and_false_still_hard_delete(self, query):
        """Backward compatibility: the shipped button sends no parameter at all."""
        session = _ownership_session()
        with _d5_crud_mocks() as (archive, hard_delete):
            with _client(session) as client:
                response = client.delete(
                    f"{D5_PATH}?character_id={CHARACTER_ID}{query}", headers=AUTH,
                )

        assert response.status_code == 204
        archive.assert_not_awaited()
        hard_delete.assert_awaited_once()
        assert hard_delete.await_args.args[1:] == (CHARACTER_ID, LOCATION_ID)

    def test_archiving_twice_is_204_both_times(self):
        """Idempotent: the second call retires nothing and still answers 204."""
        session = _ownership_session()
        retired = iter([1, 0])

        async def _archive(_session, _character_id, _location_id):
            return next(retired)

        with patch("main.crud.archive_active_draft", side_effect=_archive), \
             patch("main.crud.delete_active_draft", new_callable=AsyncMock) as hard:
            with _client(session) as client:
                path = f"{D5_PATH}?character_id={CHARACTER_ID}&keep_in_history=true"
                first = client.delete(path, headers=AUTH)
                second = client.delete(path, headers=AUTH)

        assert first.status_code == 204
        assert second.status_code == 204
        assert first.content == b""
        assert second.content == b""
        hard.assert_not_awaited()

    def test_a_garbage_value_is_422_and_touches_nothing(self):
        """Neither branch may run on an unparseable flag."""
        session = _ownership_session()
        with _d5_crud_mocks() as (archive, hard_delete):
            with _client(session) as client:
                response = client.delete(
                    f"{D5_PATH}?character_id={CHARACTER_ID}&keep_in_history=maybe",
                    headers=AUTH,
                )

        assert response.status_code == 422
        archive.assert_not_awaited()
        hard_delete.assert_not_awaited()

    def test_403_when_cancelling_another_players_draft(self):
        """The extended route is no laxer about ownership than before."""
        session = _ownership_session()
        with _d5_crud_mocks() as (archive, hard_delete):
            with _client(session, user_id=OWNER_USER_ID) as client:
                response = client.delete(
                    f"{D5_PATH}?character_id={OTHER_CHARACTER_ID}&keep_in_history=true",
                    headers=AUTH,
                )

        assert response.status_code == 403
        assert response.json()["detail"] == "Вы можете управлять только своими персонажами"
        archive.assert_not_awaited()
        hard_delete.assert_not_awaited()
        assert session.ownership_calls == [OTHER_CHARACTER_ID]

    def test_401_without_a_token(self):
        session = _ownership_session()
        with _d5_crud_mocks() as (archive, hard_delete):
            with _client(session, authenticate=False) as client:
                response = client.delete(
                    f"{D5_PATH}?character_id={CHARACTER_ID}&keep_in_history=true"
                )

        assert response.status_code == 401
        archive.assert_not_awaited()
        hard_delete.assert_not_awaited()

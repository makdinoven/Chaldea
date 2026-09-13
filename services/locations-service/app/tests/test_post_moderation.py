"""FEAT-158 tasks 8 + 14 — post moderation: authorization, response contract and
the approve/resolve regression.

Three layers, deliberately separated (same split as ``test_post_drafts.py``):

1. **CRUD against real in-memory aiosqlite** — task 14. The bug this covers was a
   *schema* fact, not a code path: ``post_deletion_requests.post_id`` /
   ``post_reports.post_id`` were ``ON DELETE CASCADE``, so deleting the post
   destroyed the very row the handler was about to stamp with its decision, the
   flush raised ``StaleDataError`` and every «Одобрить» / «Решена» click returned
   500. A mocked session cannot prove any of that — only a database that actually
   enforces the foreign key can. So the tables are created from ``models.py`` with
   ``PRAGMA foreign_keys=ON``: **revert migration 037 (i.e. put ``models.py`` back
   to ``ondelete="CASCADE", nullable=False``) and these tests fail**, which is
   exactly what task 14 asks for.
2. **Routes through ``TestClient`` with the crud layer mocked** — task 8. Status
   codes and the access matrix are pinned independently of the database.
3. **The enrichment helpers** — task 8's response contract: names resolved from
   mocked downstreams, deduped outbound calls, and `null` (never a 500) when a
   downstream is down.

Two things the access matrix asserts on purpose:

* **Moderator access is preserved.** The four admin endpoints used to be guarded
  by ``get_admin_user``, which admitted admin **and** moderator. Moving them onto
  ``require_permission`` must not quietly narrow that to admin-only.
* **The two player POSTs stay open to ordinary players.** They are normal
  gameplay actions and must never demand a moderation permission.

Mocking style follows ``conftest.py`` (env vars + patched engine),
``test_rbac_enforcement.py`` (``patch("auth_http.requests.get")`` for the token
check) and ``test_move_and_post_messages.py`` (URL-aware ``httpx.AsyncClient``).
"""

import asyncio
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
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
from models import (  # noqa: E402
    ActionGate,
    Location,
    Post,
    PostDeletionRequest,
    PostReport,
)
from main import app  # noqa: E402
from database import get_db  # noqa: E402


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


LOCATION_ID = 10
CHARACTER_ID = 100
AUTHOR_USER_ID = 5
REPORTER_USER_ID = 6
MODERATOR_USER_ID = 77


# ===========================================================================
# Layer 1 — crud against real aiosqlite (task 14)
# ===========================================================================

@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    """In-memory async SQLite with the five tables the moderation paths touch.

    ``PRAGMA foreign_keys=ON`` is essential and not incidental: the whole point of
    task 14 is that the FK behaviour on ``posts`` deletion is what used to break
    the review handlers. ``NOW()`` is registered as a SQLite function because
    ``_close_sibling_moderation_rows`` writes raw MySQL SQL — the same kind of
    dialect accommodation as the ``@compiles`` hooks above.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_setup(dbapi_conn, _record):  # pragma: no cover - connection hook
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        dbapi_conn.create_function(
            "NOW", 0,
            lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )

    async with engine.begin() as conn:
        # With FK enforcement on, SQLite refuses to touch a table whose parent
        # tables are absent — even when the child column is NULL. `Locations`
        # points at `Regions` / `Districts`, which are irrelevant here, so they
        # are created as bare id stubs rather than dragging the whole schema in.
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


async def _add_post(session, post_id: int, content: str = "Пост для модерации") -> Post:
    post = Post(
        id=post_id, character_id=CHARACTER_ID, location_id=LOCATION_ID,
        content=content, post_type="regular",
    )
    session.add(post)
    await session.commit()
    return post


async def _add_deletion_request(session, post_id, user_id=AUTHOR_USER_ID,
                                status="pending") -> PostDeletionRequest:
    req = PostDeletionRequest(
        post_id=post_id, user_id=user_id, reason="Опечатка", status=status,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def _add_report(session, post_id, user_id=REPORTER_USER_ID,
                      status="pending") -> PostReport:
    report = PostReport(
        post_id=post_id, user_id=user_id, reason="Оскорбление", status=status,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


async def _add_gate(session, post_id, status="open", action_type="combat") -> ActionGate:
    gate = ActionGate(
        character_id=CHARACTER_ID, location_id=LOCATION_ID, post_id=post_id,
        action_type=action_type, target_ref=1, status=status,
    )
    session.add(gate)
    await session.commit()
    await session.refresh(gate)
    return gate


async def _post_exists(session, post_id) -> bool:
    result = await session.execute(select(Post).where(Post.id == post_id))
    return result.scalars().first() is not None


async def _reload(session, model, row_id):
    """Re-read a row from the DB, overwriting whatever the identity map holds.

    ``populate_existing`` rather than ``expire_all``: expiring every instance
    would turn a later attribute read on an unrelated object into lazy IO from a
    sync context (``MissingGreenlet``).
    """
    result = await session.execute(
        select(model).where(model.id == row_id).execution_options(populate_existing=True)
    )
    return result.scalars().first()


@pytest.mark.asyncio
class TestApproveDeletionRequest:
    """Task 14 — the path that used to return 500 on every click."""

    async def test_approve_deletes_post_and_keeps_the_decision(self, session):
        """The 500 regression, asserted as the outcome the moderator expects.

        Pre-037 this raised ``StaleDataError``: the CASCADE removed the request
        row, the handler's UPDATE matched 0 rows, everything rolled back.
        """
        await _add_post(session, 1)
        req = await _add_deletion_request(session, 1)

        result = await crud.review_deletion_request(
            session, req.id, "approve", MODERATOR_USER_ID
        )

        assert result.status == "approved"
        assert result.reviewed_by_user_id == MODERATOR_USER_ID
        assert result.reviewed_at is not None
        # The FK is SET NULL now — the audit row outlives the post it is about.
        assert result.post_id is None
        assert not await _post_exists(session, 1)

        # ...and it really is on disk, not just in the identity map.
        stored = await _reload(session, PostDeletionRequest, req.id)
        assert stored is not None, "the moderation row was destroyed by the delete"
        assert stored.status == "approved"
        assert stored.post_id is None

    async def test_reject_changes_nothing_but_the_status(self, session):
        await _add_post(session, 2)
        req = await _add_deletion_request(session, 2)

        result = await crud.review_deletion_request(
            session, req.id, "reject", MODERATOR_USER_ID
        )

        assert result.status == "rejected"
        assert result.post_id == 2
        assert await _post_exists(session, 2)

    async def test_already_reviewed_request_is_rejected(self, session):
        await _add_post(session, 3)
        req = await _add_deletion_request(session, 3, status="approved")
        with pytest.raises(Exception) as exc:
            await crud.review_deletion_request(
                session, req.id, "approve", MODERATOR_USER_ID
            )
        assert getattr(exc.value, "status_code", None) == 400

    async def test_unknown_request_is_404(self, session):
        with pytest.raises(Exception) as exc:
            await crud.review_deletion_request(
                session, 999999, "approve", MODERATOR_USER_ID
            )
        assert getattr(exc.value, "status_code", None) == 404

    async def test_invalid_action_is_400(self, session):
        await _add_post(session, 4)
        req = await _add_deletion_request(session, 4)
        with pytest.raises(Exception) as exc:
            await crud.review_deletion_request(
                session, req.id, "delete_everything", MODERATOR_USER_ID
            )
        assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.asyncio
class TestResolveReport:
    """Task 14 — the same regression on the reports queue."""

    async def test_resolve_deletes_post_and_keeps_the_decision(self, session):
        await _add_post(session, 11)
        report = await _add_report(session, 11)

        result = await crud.review_report(
            session, report.id, "resolve", MODERATOR_USER_ID
        )

        assert result.status == "resolved"
        assert result.reviewed_by_user_id == MODERATOR_USER_ID
        assert result.reviewed_at is not None
        assert result.post_id is None
        assert not await _post_exists(session, 11)

        stored = await _reload(session, PostReport, report.id)
        assert stored is not None, "the report row was destroyed by the delete"
        assert stored.status == "resolved"
        assert stored.post_id is None

    async def test_dismiss_leaves_the_post_alone(self, session):
        await _add_post(session, 12)
        report = await _add_report(session, 12)

        result = await crud.review_report(
            session, report.id, "dismiss", MODERATOR_USER_ID
        )

        assert result.status == "dismissed"
        assert result.post_id == 12
        assert await _post_exists(session, 12)


@pytest.mark.asyncio
class TestStaleAndSiblingRows:
    """Task 14 — rows that survive their post, and rows about a post someone
    else just got deleted."""

    async def test_row_with_null_post_id_is_reviewable(self, session):
        """Rows orphaned before this feature shipped must not blow up.

        With no post to delete the handler records the decision and returns
        normally; nothing else in the database moves.
        """
        await _add_post(session, 21)
        orphan = await _add_deletion_request(session, None)

        result = await crud.review_deletion_request(
            session, orphan.id, "approve", MODERATOR_USER_ID
        )

        assert result.status == "approved"
        assert result.post_id is None
        # The unrelated post is untouched — no `DELETE ... WHERE id IS NULL` fallout.
        assert await _post_exists(session, 21)

    async def test_orphan_report_is_reviewable(self, session):
        await _add_post(session, 22)
        orphan = await _add_report(session, None)

        result = await crud.review_report(
            session, orphan.id, "resolve", MODERATOR_USER_ID
        )

        assert result.status == "resolved"
        assert await _post_exists(session, 22)

    async def test_sibling_rows_on_the_same_post_are_closed(self, session):
        """Two players reported the same post; a third asked for its deletion.

        Resolving one report deletes the post, so the outcome every sibling asked
        for has been achieved — they are closed and attributed to the acting
        moderator instead of lingering in the queue pointing at nothing.
        """
        await _add_post(session, 31)
        report_a = await _add_report(session, 31, user_id=REPORTER_USER_ID)
        report_b = await _add_report(session, 31, user_id=REPORTER_USER_ID + 1)
        deletion = await _add_deletion_request(session, 31)

        await crud.review_report(session, report_a.id, "resolve", MODERATOR_USER_ID)

        sibling = await _reload(session, PostReport, report_b.id)
        assert sibling.status == "resolved"
        assert sibling.reviewed_by_user_id == MODERATOR_USER_ID
        assert sibling.reviewed_at is not None
        assert sibling.post_id is None

        sibling_req = await _reload(session, PostDeletionRequest, deletion.id)
        assert sibling_req.status == "approved"
        assert sibling_req.reviewed_by_user_id == MODERATOR_USER_ID

    async def test_pending_rows_on_other_posts_are_untouched(self, session):
        await _add_post(session, 41)
        await _add_post(session, 42)
        target = await _add_report(session, 41)
        bystander = await _add_report(session, 42)

        await crud.review_report(session, target.id, "resolve", MODERATOR_USER_ID)

        other = await _reload(session, PostReport, bystander.id)
        assert other.status == "pending"
        assert other.post_id == 42
        assert await _post_exists(session, 42)

    async def test_reject_does_not_close_siblings(self, session):
        """Nothing was deleted, so nothing anyone asked for has happened."""
        await _add_post(session, 51)
        report = await _add_report(session, 51)
        deletion = await _add_deletion_request(session, 51)

        await crud.review_deletion_request(
            session, deletion.id, "reject", MODERATOR_USER_ID
        )

        sibling = await _reload(session, PostReport, report.id)
        assert sibling.status == "pending"
        assert sibling.post_id == 51


@pytest.mark.asyncio
class TestReviewRevokesGates:
    """Task 14's tie-in with task 6 — the full matrix lives in
    ``test_gate_revocation.py``; this pins the review path itself."""

    async def test_approve_expires_open_gates_only(self, session):
        await _add_post(session, 61)
        await _add_post(session, 62)
        open_gate = await _add_gate(session, 61, status="open")
        consumed_gate = await _add_gate(session, 61, status="consumed")
        foreign_gate = await _add_gate(session, 62, status="open")
        req = await _add_deletion_request(session, 61)

        await crud.review_deletion_request(
            session, req.id, "approve", MODERATOR_USER_ID
        )

        assert (await _reload(session, ActionGate, open_gate.id)).status == "expired"
        # The action already fired — rewriting that history would corrupt the record.
        assert (await _reload(session, ActionGate, consumed_gate.id)).status == "consumed"
        assert (await _reload(session, ActionGate, foreign_gate.id)).status == "open"


@pytest.mark.asyncio
class TestQueueRendersOrphanedRows:
    """Task 14 — a row whose post is gone must render, not explode."""

    async def test_orphan_row_has_all_post_fields_null(self, session):
        await _add_deletion_request(session, None)

        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_downstream_ok())):
            items = await crud.get_pending_deletion_requests(session)

        assert len(items) == 1
        item = items[0]
        assert item["post_id"] is None
        assert item["post_content"] is None
        assert item["post_character_id"] is None
        assert item["post_character_name"] is None
        assert item["post_created_at"] is None
        # The requester is still resolvable — the user account outlives the post.
        assert item["requester_username"] == f"user{AUTHOR_USER_ID}"

    async def test_live_row_carries_the_enriched_fields(self, session):
        await _add_post(session, 71, content="Текст поста")
        await _add_deletion_request(session, 71)

        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_downstream_ok())):
            items = await crud.get_pending_deletion_requests(session)

        item = items[0]
        assert item["post_content"] == "Текст поста"
        assert item["post_character_id"] == CHARACTER_ID
        assert item["post_character_name"] == f"Персонаж {CHARACTER_ID}"
        assert item["post_created_at"] is not None
        assert item["requester_username"] == f"user{AUTHOR_USER_ID}"

    async def test_reviewed_rows_drop_out_of_the_queue(self, session):
        await _add_post(session, 81)
        req = await _add_deletion_request(session, 81)
        await crud.review_deletion_request(
            session, req.id, "approve", MODERATOR_USER_ID
        )

        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_downstream_ok())):
            items = await crud.get_pending_deletion_requests(session)

        assert items == []

    async def test_reports_queue_renders_orphans_too(self, session):
        await _add_report(session, None)

        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_downstream_ok())):
            items = await crud.get_pending_reports(session)

        assert len(items) == 1
        assert items[0]["post_content"] is None
        assert items[0]["post_character_name"] is None
        assert items[0]["post_created_at"] is None


# ===========================================================================
# Layer 3 — name enrichment (task 8's response contract)
# ===========================================================================

def _http_response(status_code: int, payload: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


def _httpx_client(get_side_effect):
    """Mock for `async with httpx.AsyncClient(...) as client`."""
    instance = AsyncMock()
    instance.__aenter__.return_value = instance
    instance.__aexit__.return_value = False
    instance.get.side_effect = get_side_effect
    return instance


def _downstream_ok(calls: list | None = None):
    """URL-aware `client.get` for both downstreams; optionally records calls."""

    async def _get(url, *args, **kwargs):
        if calls is not None:
            calls.append(url)
        if "/characters/" in url:
            cid = url.split("/characters/")[1].split("/")[0]
            return _http_response(200, {"name": f"Персонаж {cid}", "avatar": None})
        if "/users/" in url:
            uid = url.rstrip("/").split("/users/")[1]
            return _http_response(200, {"id": int(uid), "username": f"user{uid}"})
        raise AssertionError(f"unexpected outbound GET: {url}")

    return _get


def _moderation_item(item_id, character_id, user_id):
    return {
        "id": item_id,
        "post_id": item_id,
        "user_id": user_id,
        "reason": None,
        "status": "pending",
        "created_at": datetime(2026, 9, 13, 12, 0, 0),
        "reviewed_at": None,
        "post_content": "текст",
        "post_character_id": character_id,
        "post_location_id": LOCATION_ID,
        "post_created_at": datetime(2026, 9, 13, 11, 0, 0),
    }


@pytest.mark.asyncio
class TestModerationEnrichment:
    """Names are resolved server-side, once per distinct id, and never fatally."""

    async def test_names_are_resolved(self):
        items = [_moderation_item(1, 100, 5)]
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_downstream_ok())):
            out = await crud._enrich_moderation_items(items)
        assert out[0]["post_character_name"] == "Персонаж 100"
        assert out[0]["requester_username"] == "user5"

    async def test_outbound_calls_are_deduped(self):
        """Three rows, two distinct characters and two distinct users → 4 calls,
        not 6. The queue must not fan out per row."""
        calls = []
        items = [
            _moderation_item(1, 100, 5),
            _moderation_item(2, 100, 5),
            _moderation_item(3, 101, 6),
        ]
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_downstream_ok(calls))):
            await crud._enrich_moderation_items(items)

        character_calls = [c for c in calls if "/characters/" in c]
        user_calls = [c for c in calls if "/users/" in c]
        assert len(character_calls) == 2, character_calls
        assert len(user_calls) == 2, user_calls

    async def test_downstream_failure_degrades_to_null(self):
        """character-service / user-service down must yield `null` names — the
        moderation queue may never become a 500 because a neighbour is sick."""

        async def _boom(url, *args, **kwargs):
            raise RuntimeError("connection refused")

        items = [_moderation_item(1, 100, 5)]
        with patch("crud.httpx.AsyncClient", return_value=_httpx_client(_boom)):
            out = await crud._enrich_moderation_items(items)
        assert out[0]["post_character_name"] is None
        assert out[0]["requester_username"] is None

    async def test_downstream_404_degrades_to_null(self):
        """Deleted character / deleted user — the UI renders «Персонаж #id»."""

        async def _not_found(url, *args, **kwargs):
            return _http_response(404, {})

        items = [_moderation_item(1, 100, 5)]
        with patch("crud.httpx.AsyncClient", return_value=_httpx_client(_not_found)):
            out = await crud._enrich_moderation_items(items)
        assert out[0]["post_character_name"] is None
        assert out[0]["requester_username"] is None

    async def test_empty_name_becomes_null(self):
        """An empty string from character-service means "not resolved"."""

        async def _empty(url, *args, **kwargs):
            if "/characters/" in url:
                return _http_response(200, {"name": "", "avatar": None})
            return _http_response(200, {"username": ""})

        items = [_moderation_item(1, 100, 5)]
        with patch("crud.httpx.AsyncClient", return_value=_httpx_client(_empty)):
            out = await crud._enrich_moderation_items(items)
        assert out[0]["post_character_name"] is None
        assert out[0]["requester_username"] is None

    async def test_null_character_id_makes_no_call(self):
        """An orphaned row has no character id — do not call anyone about it."""
        calls = []
        item = _moderation_item(1, None, 5)
        item["post_content"] = None
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_downstream_ok(calls))):
            out = await crud._enrich_moderation_items([item])
        assert out[0]["post_character_name"] is None
        assert not [c for c in calls if "/characters/" in c]

    async def test_empty_queue_makes_no_calls(self):
        calls = []
        with patch("crud.httpx.AsyncClient",
                   return_value=_httpx_client(_downstream_ok(calls))):
            out = await crud._enrich_moderation_items([])
        assert out == []
        assert calls == []


# ===========================================================================
# Layer 2 — endpoint authorization + response contract (task 8)
# ===========================================================================

DELETION_QUEUE_URL = "/locations/admin/moderation/deletion-requests"
REPORTS_QUEUE_URL = "/locations/admin/moderation/reports"
DELETION_REVIEW_URL = "/locations/admin/moderation/deletion-requests/1/review"
REPORT_REVIEW_URL = "/locations/admin/moderation/reports/1/review"

ADMIN_GET_URLS = (DELETION_QUEUE_URL, REPORTS_QUEUE_URL)
ADMIN_PUT_URLS = (DELETION_REVIEW_URL, REPORT_REVIEW_URL)

REVIEW_BODY = {"action": "reject"}
AUTH_HEADER = {"Authorization": "Bearer fake-token"}

# What /users/me returns for each actor. Admin receives every registered
# permission automatically; moderator receives both via migration 0027.
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


def _queue_row(**overrides):
    row = {
        "id": 1,
        "post_id": 7,
        "user_id": 5,
        "reason": "Оскорбление",
        "status": "pending",
        "created_at": datetime(2026, 9, 13, 12, 0, 0),
        "reviewed_at": None,
        "post_content": "Текст поста",
        "post_character_id": 100,
        "post_location_id": LOCATION_ID,
        "post_character_name": "Скиталец",
        "post_created_at": datetime(2026, 9, 13, 11, 0, 0),
        "requester_username": "player",
    }
    row.update(overrides)
    return row


def _reviewed_row(post_id=None):
    return SimpleNamespace(
        id=1, post_id=post_id, user_id=5, reason=None, status="approved",
        created_at=datetime(2026, 9, 13, 12, 0, 0),
        reviewed_at=datetime(2026, 9, 13, 13, 0, 0),
    )


@pytest.fixture()
def moderation_client():
    """TestClient with the DB mocked; each test patches the crud calls it needs."""
    async def _fake_get_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _fake_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestModerationEndpointAuthorization:
    """The access matrix for the four admin endpoints."""

    def test_no_token_is_401(self, moderation_client):
        for url in ADMIN_GET_URLS:
            assert moderation_client.get(url).status_code == 401, url
        for url in ADMIN_PUT_URLS:
            assert moderation_client.put(url, json=REVIEW_BODY).status_code == 401, url

    @patch("auth_http.requests.get")
    def test_invalid_token_is_401(self, mock_get, moderation_client):
        mock_get.return_value = _me({}, status_code=401)
        for url in ADMIN_GET_URLS:
            assert moderation_client.get(url, headers=AUTH_HEADER).status_code == 401, url

    @patch("auth_http.requests.get")
    def test_ordinary_player_is_403(self, mock_get, moderation_client):
        mock_get.return_value = _me(PLAYER_ME)
        for url in ADMIN_GET_URLS:
            r = moderation_client.get(url, headers=AUTH_HEADER)
            assert r.status_code == 403, url
            assert r.json()["detail"] == "Недостаточно прав"
        for url in ADMIN_PUT_URLS:
            assert moderation_client.put(
                url, json=REVIEW_BODY, headers=AUTH_HEADER
            ).status_code == 403, url

    @patch("auth_http.requests.get")
    def test_admin_reads_the_queues(self, mock_get, moderation_client):
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_pending_deletion_requests",
                   new_callable=AsyncMock, return_value=[]), \
             patch("main.crud.get_pending_reports",
                   new_callable=AsyncMock, return_value=[]):
            for url in ADMIN_GET_URLS:
                assert moderation_client.get(url, headers=AUTH_HEADER).status_code == 200, url

    @patch("auth_http.requests.get")
    def test_moderator_reads_the_queues(self, mock_get, moderation_client):
        """Regression guard: `get_admin_user` admitted moderators, and moving to
        `require_permission` must not have narrowed the endpoints to admin-only."""
        mock_get.return_value = _me(MODERATOR_ME)
        with patch("main.crud.get_pending_deletion_requests",
                   new_callable=AsyncMock, return_value=[]), \
             patch("main.crud.get_pending_reports",
                   new_callable=AsyncMock, return_value=[]):
            for url in ADMIN_GET_URLS:
                assert moderation_client.get(url, headers=AUTH_HEADER).status_code == 200, url

    @patch("auth_http.requests.get")
    def test_moderator_can_review(self, mock_get, moderation_client):
        """The destructive half of the queue must stay open to moderators too."""
        mock_get.return_value = _me(MODERATOR_ME)
        with patch("main.crud.review_deletion_request",
                   new_callable=AsyncMock, return_value=_reviewed_row()), \
             patch("main.crud.review_report",
                   new_callable=AsyncMock, return_value=_reviewed_row()):
            for url in ADMIN_PUT_URLS:
                assert moderation_client.put(
                    url, json=REVIEW_BODY, headers=AUTH_HEADER
                ).status_code == 200, url

    @patch("auth_http.requests.get")
    def test_admin_can_review(self, mock_get, moderation_client):
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.review_deletion_request",
                   new_callable=AsyncMock, return_value=_reviewed_row()), \
             patch("main.crud.review_report",
                   new_callable=AsyncMock, return_value=_reviewed_row()):
            for url in ADMIN_PUT_URLS:
                assert moderation_client.put(
                    url, json=REVIEW_BODY, headers=AUTH_HEADER
                ).status_code == 200, url

    @patch("auth_http.requests.get")
    def test_read_only_moderator_cannot_review(self, mock_get, moderation_client):
        """read/review are split on purpose: reviewing destroys a post."""
        mock_get.return_value = _me(READ_ONLY_ME)
        with patch("main.crud.get_pending_deletion_requests",
                   new_callable=AsyncMock, return_value=[]), \
             patch("main.crud.get_pending_reports",
                   new_callable=AsyncMock, return_value=[]):
            for url in ADMIN_GET_URLS:
                assert moderation_client.get(url, headers=AUTH_HEADER).status_code == 200, url
        for url in ADMIN_PUT_URLS:
            r = moderation_client.put(url, json=REVIEW_BODY, headers=AUTH_HEADER)
            assert r.status_code == 403, url

    @patch("auth_http.requests.get")
    def test_review_permission_alone_does_not_grant_other_modules(
        self, mock_get, moderation_client
    ):
        """Cross-module isolation — a moderation token is not a locations token."""
        mock_get.return_value = _me(MODERATOR_ME)
        r = moderation_client.post(
            "/locations/countries/create",
            json={"name": "X", "description": "Y"},
            headers=AUTH_HEADER,
        )
        assert r.status_code == 403


class TestPlayerModerationEndpointsStayOpen:
    """The two player POSTs must keep working for an ordinary player."""

    @patch("auth_http.requests.get")
    def test_player_can_request_deletion(self, mock_get, moderation_client):
        mock_get.return_value = _me(PLAYER_ME)
        created = SimpleNamespace(
            id=1, post_id=7, user_id=4, reason="Опечатка", status="pending",
            created_at=datetime(2026, 9, 13, 12, 0, 0), reviewed_at=None,
        )
        with patch("main.crud.create_deletion_request",
                   new_callable=AsyncMock, return_value=created):
            r = moderation_client.post(
                "/locations/posts/7/request-deletion",
                json={"reason": "Опечатка"}, headers=AUTH_HEADER,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

    @patch("auth_http.requests.get")
    def test_player_can_report(self, mock_get, moderation_client):
        mock_get.return_value = _me(PLAYER_ME)
        created = SimpleNamespace(
            id=2, post_id=7, user_id=4, reason="Оскорбление", status="pending",
            created_at=datetime(2026, 9, 13, 12, 0, 0), reviewed_at=None,
        )
        with patch("main.crud.create_report",
                   new_callable=AsyncMock, return_value=created):
            r = moderation_client.post(
                "/locations/posts/7/report",
                json={"reason": "Оскорбление"}, headers=AUTH_HEADER,
            )
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

    def test_player_endpoints_still_require_a_token(self, moderation_client):
        assert moderation_client.post(
            "/locations/posts/7/report", json={"reason": "x"}
        ).status_code == 401


class TestModerationResponseContract:
    """The enriched fields the moderation screen renders."""

    @patch("auth_http.requests.get")
    def test_deletion_queue_carries_the_enriched_fields(self, mock_get, moderation_client):
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_pending_deletion_requests",
                   new_callable=AsyncMock, return_value=[_queue_row()]):
            r = moderation_client.get(DELETION_QUEUE_URL, headers=AUTH_HEADER)
        assert r.status_code == 200
        row = r.json()[0]
        assert row["post_character_name"] == "Скиталец"
        assert row["requester_username"] == "player"
        assert row["post_created_at"] is not None
        assert row["post_content"] == "Текст поста"
        assert row["post_id"] == 7

    @patch("auth_http.requests.get")
    def test_reports_queue_carries_the_enriched_fields(self, mock_get, moderation_client):
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.get_pending_reports",
                   new_callable=AsyncMock, return_value=[_queue_row()]):
            r = moderation_client.get(REPORTS_QUEUE_URL, headers=AUTH_HEADER)
        assert r.status_code == 200
        assert r.json()[0]["post_character_name"] == "Скиталец"

    @patch("auth_http.requests.get")
    def test_null_names_and_null_post_id_serialize(self, mock_get, moderation_client):
        """A row whose post and whose character are both gone: every post field
        comes back `null` and the response is still a 200."""
        mock_get.return_value = _me(ADMIN_ME)
        orphan = _queue_row(
            post_id=None, post_content=None, post_character_id=None,
            post_character_name=None, post_created_at=None,
            requester_username=None,
        )
        with patch("main.crud.get_pending_deletion_requests",
                   new_callable=AsyncMock, return_value=[orphan]):
            r = moderation_client.get(DELETION_QUEUE_URL, headers=AUTH_HEADER)
        assert r.status_code == 200
        row = r.json()[0]
        for field in ("post_id", "post_content", "post_character_id",
                      "post_character_name", "post_created_at", "requester_username"):
            assert row[field] is None, field

    @patch("auth_http.requests.get")
    def test_review_response_tolerates_a_null_post_id(self, mock_get, moderation_client):
        """The second half of the 500: after the delete, `session.refresh()`
        reloads `post_id` as NULL, and a non-Optional schema field would turn the
        StaleDataError into a Pydantic validation error."""
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.review_deletion_request",
                   new_callable=AsyncMock, return_value=_reviewed_row(post_id=None)):
            r = moderation_client.put(
                DELETION_REVIEW_URL, json={"action": "approve"}, headers=AUTH_HEADER
            )
        assert r.status_code == 200
        assert r.json()["post_id"] is None
        assert r.json()["status"] == "approved"

    @patch("auth_http.requests.get")
    def test_report_review_response_tolerates_a_null_post_id(self, mock_get, moderation_client):
        mock_get.return_value = _me(ADMIN_ME)
        with patch("main.crud.review_report",
                   new_callable=AsyncMock, return_value=_reviewed_row(post_id=None)):
            r = moderation_client.put(
                REPORT_REVIEW_URL, json={"action": "resolve"}, headers=AUTH_HEADER
            )
        assert r.status_code == 200
        assert r.json()["post_id"] is None

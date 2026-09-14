"""FEAT-156 (T18, character-service half) — the drafts cleanup in `delete_character`.

`DELETE /characters/{character_id}` fans out to every service that owns a slice of
the character's data before dropping the row itself. FEAT-156 adds **step 4.5**:
`DELETE {LOCATIONS_SERVICE_URL}/locations/admin/drafts/by_character/{id}`
(`main.py`, between the user-service cleanup and `db.delete(character)`).

Two things are tested, and the second one is the point of the task:

1. The call is made — **exactly once**, at the documented URL, carrying the
   caller's own Bearer token (the cleanup endpoint is RBAC-guarded on the far
   side, so a missing or rewritten header would silently 401 and leave orphans).
2. **A failing cleanup never fails the deletion.** locations-service being down,
   slow, or returning a 500 must still leave the character deleted and the
   endpoint answering 200 — a half-deleted character is worse than an orphan
   draft, which is exactly why steps 1–4 all swallow their errors too.

Mocking follows this service's own conventions (`tests/conftest.py` + the fixture
shape of `test_admin_character_management.py`): sync SQLAlchemy against the shared
in-memory SQLite engine, auth bypassed through `app.dependency_overrides`, and
`httpx.AsyncClient` patched wholesale so no outbound request is ever attempted.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import String

import database
import models

# Enum columns have no SQLite spelling — same shim as test_admin_character_management.py
for col in models.Character.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(50)
for col in models.CharacterRequest.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(50)

from fastapi.testclient import TestClient          # noqa: E402
from auth_http import (                            # noqa: E402
    get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead,
)
from config import settings                        # noqa: E402
from main import app, get_db                       # noqa: E402


CHARACTER_ID = 1
USER_ID = 10
TOKEN = "fake-admin-token"

DRAFTS_URL = (
    f"{settings.LOCATIONS_SERVICE_URL}"
    f"/locations/admin/drafts/by_character/{CHARACTER_ID}"
)

_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve",
    ],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session(test_engine, test_session_factory, seed_fk_data):
    database.Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        database.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def admin_client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = lambda: _ADMIN_USER
    app.dependency_overrides[get_current_user_via_http] = lambda: _ADMIN_USER
    app.dependency_overrides[OAUTH2_SCHEME] = lambda: TOKEN
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_character(db, char_id=CHARACTER_ID, user_id=USER_ID):
    db.add(models.CharacterRequest(
        id=char_id, name="Лоен", id_subrace=1, biography="bio", personality="pers",
        id_class=1, status="approved", user_id=user_id, appearance="appearance",
        id_race=1, avatar="/avatar.jpg",
    ))
    db.commit()
    ch = models.Character(
        id=char_id, name="Лоен", id_subrace=1, id_class=1, id_race=1, level=1,
        stat_points=0, currency_balance=100, request_id=char_id, user_id=user_id,
        appearance="appearance", avatar="/avatar.jpg",
    )
    db.add(ch)
    db.commit()
    return ch


class _RecordedCall:
    __slots__ = ("method", "url", "headers")

    def __init__(self, method, url, headers):
        self.method, self.url, self.headers = method, url, headers


def _httpx_mock(drafts_status=200, drafts_raises=None):
    """Patchable `httpx.AsyncClient` that records every outbound cleanup call.

    `drafts_status` / `drafts_raises` apply **only** to the step-4.5 URL, so the
    failure cases isolate the drafts call instead of breaking the whole fan-out —
    otherwise a passing test would not prove which failure was tolerated.
    """
    calls = []

    def _response(status_code):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = "OK" if status_code == 200 else "boom"
        return resp

    instance = AsyncMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)

    async def _delete(url, *args, headers=None, **kwargs):
        calls.append(_RecordedCall("DELETE", url, headers))
        if url == DRAFTS_URL:
            if drafts_raises is not None:
                raise drafts_raises
            return _response(drafts_status)
        return _response(200)

    async def _post(url, *args, headers=None, **kwargs):
        calls.append(_RecordedCall("POST", url, headers))
        return _response(200)

    instance.delete = AsyncMock(side_effect=_delete)
    instance.post = AsyncMock(side_effect=_post)

    client_class = MagicMock(return_value=instance)
    client_class.recorded_calls = calls
    return client_class


def _drafts_calls(client_class):
    return [c for c in client_class.recorded_calls if c.url == DRAFTS_URL]


# ===========================================================================
# Step 4.5 fires
# ===========================================================================

class TestDraftsCleanupIsCalled:

    def test_cleanup_called_exactly_once_with_the_forwarded_token(
        self, admin_client, db_session
    ):
        _seed_character(db_session)
        client_class = _httpx_mock()

        with patch("httpx.AsyncClient", client_class):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 200

        drafts = _drafts_calls(client_class)
        assert len(drafts) == 1, "the cleanup must fire once, not zero or twice"
        assert drafts[0].method == "DELETE"
        # The far side is guarded by require_permission("locations:delete"):
        # without the caller's own token the cleanup would 401 and orphan the rows.
        assert drafts[0].headers == {"Authorization": f"Bearer {TOKEN}"}

    def test_cleanup_runs_after_user_service_and_after_the_row_is_dropped(
        self, admin_client, db_session
    ):
        """Ordering matters: it is step 4.5, not step 0.

        The character row is dropped and committed *first*; only then does the
        best-effort fan-out run. That is the safe failure mode — a fan-out that
        dies leaves orphaned rows in the neighbours rather than a gutted
        character still sitting in the admin's list. Within the fan-out, drafts
        cleanup must still come after user-service so a slow locations-service
        cannot delay releasing the user's current character.
        """
        _seed_character(db_session)
        client_class = _httpx_mock()

        with patch("httpx.AsyncClient", client_class):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 200
        urls = [c.url for c in client_class.recorded_calls]
        assert DRAFTS_URL in urls
        user_service_calls = [
            i for i, u in enumerate(urls) if "/users/" in u
        ]
        assert user_service_calls, "the user-service cleanup must still run"
        assert urls.index(DRAFTS_URL) > max(user_service_calls)
        # …and the row really is gone (it was dropped before the fan-out began).
        assert db_session.query(models.Character).filter(
            models.Character.id == CHARACTER_ID
        ).first() is None

    def test_cleanup_runs_for_a_character_with_no_user(
        self, admin_client, db_session
    ):
        """Step 4 is skipped when `user_id` is NULL — 4.5 must not be."""
        _seed_character(db_session, user_id=None)
        client_class = _httpx_mock()

        with patch("httpx.AsyncClient", client_class):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 200
        assert len(_drafts_calls(client_class)) == 1

    def test_no_cleanup_for_a_character_that_does_not_exist(
        self, admin_client, db_session
    ):
        """404 short-circuits before the fan-out — no stray cleanup calls."""
        client_class = _httpx_mock()

        with patch("httpx.AsyncClient", client_class):
            resp = admin_client.delete("/characters/999")

        assert resp.status_code == 404
        assert client_class.recorded_calls == []


# ===========================================================================
# …and a failing cleanup never blocks the deletion (the key case)
# ===========================================================================

class TestDraftsCleanupFailureIsTolerated:
    """Draft bookkeeping must never leave a half-deleted character behind."""

    @pytest.mark.parametrize("status", [500, 502, 403, 401, 404])
    def test_character_is_still_deleted_when_cleanup_returns_an_error(
        self, status, admin_client, db_session
    ):
        _seed_character(db_session)
        client_class = _httpx_mock(drafts_status=status)

        with patch("httpx.AsyncClient", client_class):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 200, f"cleanup {status} must not fail the delete"
        assert len(_drafts_calls(client_class)) == 1, "no retry storm"
        assert db_session.query(models.Character).filter(
            models.Character.id == CHARACTER_ID
        ).first() is None

    @pytest.mark.parametrize("error", [
        ConnectionError("locations-service is down"),
        TimeoutError("locations-service took too long"),
        RuntimeError("unexpected"),
    ])
    def test_character_is_still_deleted_when_cleanup_raises(
        self, error, admin_client, db_session
    ):
        """locations-service unreachable — the exception must be swallowed."""
        _seed_character(db_session)
        client_class = _httpx_mock(drafts_raises=error)

        with patch("httpx.AsyncClient", client_class):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 200
        assert "успешно удален" in resp.json()["message"]
        assert db_session.query(models.Character).filter(
            models.Character.id == CHARACTER_ID
        ).first() is None

    def test_failure_is_logged_as_a_warning(self, admin_client, db_session):
        """Silently swallowed is not the same as silent: it must be traceable."""
        _seed_character(db_session)
        client_class = _httpx_mock(drafts_raises=ConnectionError("down"))

        with patch("httpx.AsyncClient", client_class), \
             patch("main.logger.warning") as warn:
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 200
        messages = [str(call.args[0]) for call in warn.call_args_list]
        assert any("post drafts" in m.lower() for m in messages), messages

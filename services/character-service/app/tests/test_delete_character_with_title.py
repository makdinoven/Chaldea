"""`DELETE /characters/{character_id}` — titles cascade and the ordering invariant.

Two user-reported bugs in the admin panel are pinned here.

**The cascade.** `character_titles.character_id` is half of that table's composite
primary key, so without `cascade="all, delete-orphan"` on `Character.titles` the
ORM tried to NULL it out and raised `AssertionError` — not a `SQLAlchemyError`,
so the endpoint's handler never caught it and FastAPI answered a bare 500 with an
empty body. Any character that had ever been granted a title was undeletable.

**The ordering.** The cleanup fan-out (inventory / skills / attributes / the
user-character link) used to run *before* the row delete. When the delete then
blew up, the fan-out had already succeeded: the character was left **gutted but
present** — stripped of everything, still in the admin list, and the admin was
told the deletion failed. The fix moves the row delete to step 0. That invariant
— *a failed delete touches nothing* — is the property tested hardest below,
because it is the one that turns a visible error into silent data loss.

The fan-out crosses service boundaries over HTTP, so "inventory / skills /
attributes / user-link are untouched" is observable here as *zero outbound
requests were attempted*. `httpx.AsyncClient` is patched wholesale (same shape as
`test_delete_character_cleanup.py`) and every call it would have made is recorded.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import String, text
from sqlalchemy.exc import OperationalError

import database
import models

# Enum columns have no SQLite spelling — same shim as test_delete_character_cleanup.py
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
TITLE_ID = 77
TOKEN = "fake-admin-token"

INVENTORY_URL = f"{settings.INVENTORY_SERVICE_URL}{CHARACTER_ID}/all"
SKILLS_URL = (
    f"{settings.SKILLS_SERVICE_URL}"
    f"admin/character_skills/by_character/{CHARACTER_ID}"
)
ATTRIBUTES_URL = f"{settings.ATTRIBUTES_SERVICE_URL}{CHARACTER_ID}"
USER_LINK_URL = (
    f"{settings.USER_SERVICE_URL}/users/user_characters/{USER_ID}/{CHARACTER_ID}"
)
CLEAR_CURRENT_URL = (
    f"{settings.USER_SERVICE_URL}/users/{USER_ID}/clear_current_character"
)
DRAFTS_URL = (
    f"{settings.LOCATIONS_SERVICE_URL}"
    f"/locations/admin/drafts/by_character/{CHARACTER_ID}"
)

#: Every URL the fan-out touches. None of them may be requested on a failed delete.
FANOUT_URLS = (
    INVENTORY_URL, SKILLS_URL, ATTRIBUTES_URL,
    USER_LINK_URL, CLEAR_CURRENT_URL, DRAFTS_URL,
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
    # raise_server_exceptions=False so an uncaught exception surfaces as the bare
    # 500 the admin actually saw, instead of blowing up the test run.
    yield TestClient(app, raise_server_exceptions=False)
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


def _grant_title(db, char_id=CHARACTER_ID, title_id=TITLE_ID, make_current=False):
    """Give the character a title — the exact state that made it undeletable."""
    if not db.query(models.Title).filter_by(id_title=title_id).first():
        db.add(models.Title(id_title=title_id, name=f"Победитель-{title_id}"))
        db.commit()
    db.add(models.CharacterTitle(character_id=char_id, title_id=title_id))
    if make_current:
        db.query(models.Character).filter_by(id=char_id).update(
            {"current_title_id": title_id}
        )
    db.commit()


def _title_rows(db, char_id=CHARACTER_ID):
    return db.query(models.CharacterTitle).filter_by(character_id=char_id).all()


class _RecordedCall:
    __slots__ = ("method", "url", "headers")

    def __init__(self, method, url, headers):
        self.method, self.url, self.headers = method, url, headers


def _httpx_mock():
    """`httpx.AsyncClient` stand-in recording every outbound call; all succeed."""
    calls = []

    def _response():
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "OK"
        return resp

    instance = AsyncMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)

    async def _delete(url, *args, headers=None, **kwargs):
        calls.append(_RecordedCall("DELETE", url, headers))
        return _response()

    async def _post(url, *args, headers=None, **kwargs):
        calls.append(_RecordedCall("POST", url, headers))
        return _response()

    instance.delete = AsyncMock(side_effect=_delete)
    instance.post = AsyncMock(side_effect=_post)

    client_class = MagicMock(return_value=instance)
    client_class.recorded_calls = calls
    return client_class


# ===========================================================================
# Bug 1 — a character that owns a title is deletable
# ===========================================================================

class TestDeleteCharacterWithTitle:
    """The cascade gap: `character_titles.character_id` is part of the PK."""

    def test_character_with_a_title_is_deleted(self, admin_client, db_session):
        _seed_character(db_session)
        _grant_title(db_session)
        assert len(_title_rows(db_session)) == 1

        client_class = _httpx_mock()
        with patch("httpx.AsyncClient", client_class):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 200, resp.text
        assert "успешно удален" in resp.json()["message"]

        db_session.expire_all()
        assert db_session.query(models.Character).filter_by(
            id=CHARACTER_ID
        ).first() is None
        # The link rows go with it — no orphans pointing at a dead character.
        assert _title_rows(db_session) == []
        # …while the title itself is shared game content and must survive.
        assert db_session.query(models.Title).filter_by(
            id_title=TITLE_ID
        ).first() is not None

    def test_character_with_several_titles_is_deleted(self, admin_client, db_session):
        """More than one link row — delete-orphan must clear all of them."""
        _seed_character(db_session)
        for tid in (TITLE_ID, TITLE_ID + 1, TITLE_ID + 2):
            _grant_title(db_session, title_id=tid)
        assert len(_title_rows(db_session)) == 3

        client_class = _httpx_mock()
        with patch("httpx.AsyncClient", client_class):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert _title_rows(db_session) == []
        assert db_session.query(models.Title).count() == 3

    def test_character_wearing_a_title_is_deleted(self, admin_client, db_session):
        """`current_title_id` points at the title as well — still deletable."""
        _seed_character(db_session)
        _grant_title(db_session, make_current=True)

        client_class = _httpx_mock()
        with patch("httpx.AsyncClient", client_class):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert db_session.query(models.Character).filter_by(
            id=CHARACTER_ID
        ).first() is None
        assert _title_rows(db_session) == []

    def test_character_without_a_title_is_still_deleted(self, admin_client, db_session):
        """The cascade must not have broken the ordinary path."""
        _seed_character(db_session)
        assert _title_rows(db_session) == []

        client_class = _httpx_mock()
        with patch("httpx.AsyncClient", client_class):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert db_session.query(models.Character).filter_by(
            id=CHARACTER_ID
        ).first() is None

    def test_raw_sql_delete_cascades_too(self, db_session):
        """The DB-side FK is `ON DELETE CASCADE`, not just the ORM relationship.

        Migration 022 exists because deletes that bypass the ORM (raw SQL, a DBA
        at the console, another service touching the shared database) would
        otherwise hit the FK and fail, or leave orphan link rows behind.
        """
        _seed_character(db_session)
        _grant_title(db_session)

        db_session.execute(
            text("DELETE FROM characters WHERE id = :cid"), {"cid": CHARACTER_ID}
        )
        db_session.commit()
        db_session.expire_all()

        assert db_session.execute(
            text("SELECT COUNT(*) FROM character_titles WHERE character_id = :cid"),
            {"cid": CHARACTER_ID},
        ).scalar() == 0


# ===========================================================================
# Bug 1, second half — the ordering invariant (the one worth testing hardest)
# ===========================================================================

class TestFailedDeleteTouchesNothing:
    """A failed delete must leave the character whole, not gutted.

    The fan-out is irreversible from here: it is HTTP to four other services and
    cannot join our transaction. The only protection is that it never starts
    unless the row is already gone. Every test in this class asserts the same
    thing from a different angle — nothing went out over the wire.
    """

    @staticmethod
    def _failing_delete(session, exc):
        """Make `db.delete()` blow up the way the composite PK used to."""
        return patch.object(session, "delete", side_effect=exc)

    @pytest.mark.parametrize("exc", [
        # The original failure: an ORM-level assertion, NOT a SQLAlchemyError —
        # which is exactly why the old `except SQLAlchemyError` missed it.
        AssertionError("Dependency rule tried to blank-out primary key column"),
        OperationalError("DELETE FROM characters", {}, Exception("db is gone")),
        RuntimeError("something else entirely"),
    ])
    def test_no_cleanup_call_is_made_when_the_delete_fails(
        self, exc, admin_client, db_session
    ):
        _seed_character(db_session)
        _grant_title(db_session)
        client_class = _httpx_mock()

        with patch("httpx.AsyncClient", client_class), \
             self._failing_delete(db_session, exc):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 500
        # THE invariant: inventory, skills, attributes, the user link and the
        # drafts were never contacted, so none of them could have been wiped.
        assert client_class.recorded_calls == [], (
            "cleanup ran despite the delete failing — the character would be "
            "gutted but still listed: "
            f"{[c.url for c in client_class.recorded_calls]}"
        )

    @pytest.mark.parametrize("url", FANOUT_URLS)
    def test_each_individual_cleanup_endpoint_is_left_alone(
        self, url, admin_client, db_session
    ):
        """Spelled out per service so a failure names the one that leaked."""
        _seed_character(db_session)
        client_class = _httpx_mock()

        with patch("httpx.AsyncClient", client_class), \
             self._failing_delete(db_session, AssertionError("boom")):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 500
        assert url not in [c.url for c in client_class.recorded_calls]

    def test_the_character_survives_intact(self, admin_client, db_session):
        """Row, user link and titles all still there after the failure."""
        _seed_character(db_session)
        _grant_title(db_session)
        client_class = _httpx_mock()

        with patch("httpx.AsyncClient", client_class), \
             self._failing_delete(db_session, AssertionError("boom")):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 500
        db_session.expire_all()
        char = db_session.query(models.Character).filter_by(id=CHARACTER_ID).first()
        assert char is not None, "the character must not vanish on a failed delete"
        assert char.user_id == USER_ID, "the user link must survive"
        assert char.currency_balance == 100
        assert len(_title_rows(db_session)) == 1, "the titles must survive"

    def test_the_session_is_rolled_back_and_still_usable(
        self, admin_client, db_session
    ):
        """No rollback left the session in a broken state for the next request."""
        _seed_character(db_session)
        client_class = _httpx_mock()

        with patch("httpx.AsyncClient", client_class), \
             self._failing_delete(db_session, AssertionError("boom")):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")
        assert resp.status_code == 500

        # A follow-up query on the same session must just work.
        assert db_session.query(models.Character).count() == 1

    def test_the_500_carries_a_russian_detail_not_an_empty_body(
        self, admin_client, db_session
    ):
        """The admin used to get a bare 500 with no body at all."""
        _seed_character(db_session)
        client_class = _httpx_mock()

        with patch("httpx.AsyncClient", client_class), \
             self._failing_delete(db_session, AssertionError("boom")):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 500
        assert resp.content, "empty 500 body — the admin sees nothing"
        body = resp.json()
        detail = body.get("detail")
        assert isinstance(detail, str) and detail, body
        assert any("а" <= ch.lower() <= "я" for ch in detail), (
            f"detail must be Russian, got {detail!r}"
        )
        assert str(CHARACTER_ID) in detail, "the admin needs to know which one"
        # It must also say the data is safe — that is the whole point of the reorder.
        assert "не пострадали" in detail, detail

    def test_the_failure_is_logged_with_a_traceback(self, admin_client, db_session):
        """Swallowing the cause is what hid this for three features."""
        _seed_character(db_session)
        client_class = _httpx_mock()

        with patch("httpx.AsyncClient", client_class), \
             patch("main.logger.error") as err, \
             self._failing_delete(db_session, AssertionError("boom")):
            resp = admin_client.delete(f"/characters/{CHARACTER_ID}")

        assert resp.status_code == 500
        assert err.called, "a 500 with no log entry is undebuggable"
        assert any(
            call.kwargs.get("exc_info") for call in err.call_args_list
        ), "the traceback must be logged, not just the message"

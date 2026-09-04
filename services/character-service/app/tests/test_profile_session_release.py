"""
Regression tests for GET /characters/{id}/profile.

This endpoint calls user-service over HTTP. user-service's own GET /users/me
calls back into this service (/short_info), so if the profile endpoint holds its
pooled DB connection across that await, the two services drain each other's
connection pools under concurrent load until character-service raises
"QueuePool limit of size 5 overflow 10 reached" and stops answering entirely
(including endpoints that never touch the DB).

The fix materialises every field before the call and releases the session first.
These tests pin that behaviour down so it cannot silently regress.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import pytest

import database
from database import Base
from main import app, get_db
from fastapi.testclient import TestClient
import models


@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _make_char(session, cid=1, user_id=42, name="Дудка"):
    session.add(models.Character(
        id=cid, name=name, user_id=user_id, id_subrace=1, id_class=1, id_race=1,
        appearance="—", avatar=f"avatar_{cid}.png", level=7, is_npc=False,
        current_location_id=3,
    ))
    session.commit()


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = ""

    def json(self):
        return self._payload


@pytest.fixture
def track_session_release(db_session, monkeypatch):
    """Record whether db.close() had already run when the HTTP call was made."""
    state = {"closed": False, "closed_before_http": None, "http_called": False}

    original_close = db_session.close

    def tracking_close():
        state["closed"] = True
        return original_close()

    monkeypatch.setattr(db_session, "close", tracking_close)
    return state


def _patch_user_service(monkeypatch, state, response):
    async def fake_get(self, url, *args, **kwargs):
        state["http_called"] = True
        state["closed_before_http"] = state["closed"]
        return response

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


def test_db_session_released_before_user_service_call(
    client, db_session, monkeypatch, track_session_release
):
    """The pooled connection must be back in the pool before the outbound call."""
    _make_char(db_session)
    _patch_user_service(
        monkeypatch, track_session_release,
        _FakeResponse(200, {"username": "Dudka"}),
    )

    resp = client.get("/characters/1/profile")

    assert resp.status_code == 200
    assert track_session_release["http_called"] is True
    assert track_session_release["closed_before_http"] is True, (
        "DB session was still open during the cross-service call — "
        "this is the deadlock that exhausted QueuePool"
    )


def test_profile_payload_survives_early_session_close(
    client, db_session, monkeypatch, track_session_release
):
    """Closing the session early must not detach the fields we still return."""
    _make_char(db_session)
    _patch_user_service(
        monkeypatch, track_session_release,
        _FakeResponse(200, {"username": "Dudka"}),
    )

    body = client.get("/characters/1/profile").json()

    assert body["character_name"] == "Дудка"
    assert body["character_photo"] == "avatar_1.png"
    assert body["character_level"] == 7
    assert body["current_location_id"] == 3
    assert body["user_id"] == 42
    assert body["user_nickname"] == "Dudka"
    # No title set on the character.
    assert body["character_title"] == ""
    assert body["character_title_rarity"] is None


def test_user_service_failure_degrades_gracefully(
    client, db_session, monkeypatch, track_session_release
):
    """A dead user-service must yield an empty nickname, not a 500."""
    _make_char(db_session)

    async def failing_get(self, url, *args, **kwargs):
        track_session_release["closed_before_http"] = track_session_release["closed"]
        raise httpx.ConnectTimeout("user-service unreachable")

    monkeypatch.setattr(httpx.AsyncClient, "get", failing_get)

    resp = client.get("/characters/1/profile")

    assert resp.status_code == 200
    assert resp.json()["user_nickname"] == ""
    # Even on the failure path the connection must already be released.
    assert track_session_release["closed_before_http"] is True


def test_user_service_non_200_degrades_gracefully(
    client, db_session, monkeypatch, track_session_release
):
    """A 404/500 from user-service must not break the character profile."""
    _make_char(db_session)
    _patch_user_service(monkeypatch, track_session_release, _FakeResponse(404))

    resp = client.get("/characters/1/profile")

    assert resp.status_code == 200
    assert resp.json()["user_nickname"] == ""


def test_character_without_user_skips_http_call(
    client, db_session, monkeypatch, track_session_release
):
    """NPCs have no user_id — no cross-service call should happen at all."""
    _make_char(db_session, user_id=None)
    _patch_user_service(
        monkeypatch, track_session_release, _FakeResponse(200, {"username": "x"}),
    )

    resp = client.get("/characters/1/profile")

    assert resp.status_code == 200
    assert track_session_release["http_called"] is False
    assert resp.json()["user_nickname"] == ""


def test_missing_character_returns_404(client, db_session):
    assert client.get("/characters/999/profile").status_code == 404

"""FEAT-180 stage 6b — POST /characters/internal/{character_id}/home-teleport.

inventory-service calls it when a home teleport scroll is read. It moves the
character with the admin move's side effects (gathering cancelled, intentions in
the location left expired, travel cooldown reset) and logs a `home_teleport`
row; it is internal-only (X-Internal-Token) and refuses in battle, in a dungeon
run, under another activity lock (asleep, reading) and when already there.

Fixtures (the shared-DB stand-ins, the locations-service mocks) come from the
admin move tests.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sa_text

import activity_lock
import auth_http
import models
from main import app, get_db
from tests.test_admin_move_character import (  # noqa: F401  (fixtures)
    LOC_FROM, LOC_TO, LOC_UNKNOWN, _reload, character, cleanup_mocks, db_session,
)

TOKEN = "home-token"
HEADERS = {"X-Internal-Token": TOKEN}


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _go(client, cid, location_id=LOC_TO, headers=HEADERS):
    return client.post(f"/characters/internal/{cid}/home-teleport", json={"location_id": location_id},
                       headers=headers)


def _logs(db_session, cid):
    return db_session.query(models.CharacterLog).filter_by(character_id=cid, event_type="home_teleport").all()


def test_needs_the_internal_token(client, db_session, character, cleanup_mocks):
    assert _go(client, character.id, headers={}).status_code == 401
    assert _go(client, character.id, headers={"X-Internal-Token": "wrong"}).status_code == 401
    assert _reload(db_session, character.id).current_location_id == LOC_FROM


def test_moves_with_the_side_effects_and_logs(client, db_session, character, cleanup_mocks):
    cleanup_mocks["cancel"].return_value = {"cancelled": True}
    r = _go(client, character.id)
    assert r.status_code == 200, r.text
    assert r.json() == {"character_id": character.id, "from_location_id": LOC_FROM, "location_id": LOC_TO,
                        "location_name": "Бар «Три Галки»", "gathering_cancelled": True}
    fresh = _reload(db_session, character.id)
    assert fresh.current_location_id == LOC_TO and fresh.travel_cooldown_until is None
    assert cleanup_mocks["cancel"].await_args.kwargs["reason"] == "home_teleport"
    cleanup_mocks["notify"].assert_awaited_once_with(character.id, LOC_FROM)
    (log,) = _logs(db_session, character.id)
    assert "домой" in log.description and "admin_user_id" not in log.metadata_
    assert log.metadata_["to_location_id"] == LOC_TO


def test_refusals_move_nothing(client, db_session, character, cleanup_mocks):
    assert _go(client, character.id, location_id=LOC_FROM).status_code == 400
    assert _go(client, character.id, location_id=LOC_UNKNOWN).status_code == 404
    assert _go(client, 987654).status_code == 404
    db_session.execute(sa_text("INSERT INTO battles (id, status) VALUES (1, 'in_progress')"))
    db_session.execute(sa_text("INSERT INTO battle_participants (battle_id, character_id) VALUES (1, :c)"),
                       {"c": character.id})
    db_session.commit()
    r = _go(client, character.id)
    assert r.status_code == 409 and "бою" in r.json()["detail"]
    db_session.execute(sa_text("DELETE FROM battle_participants"))
    db_session.commit()
    character.reading_since = datetime.utcnow()
    db_session.commit()
    r = _go(client, character.id)
    assert r.status_code == 409 and "читает" in r.json()["detail"]
    assert _reload(db_session, character.id).current_location_id == LOC_FROM
    assert _logs(db_session, character.id) == []
    cleanup_mocks["cancel"].assert_not_awaited()


def test_a_failed_cleanup_moves_nothing(client, db_session, character, cleanup_mocks):
    import locations_client
    cleanup_mocks["notify"].side_effect = locations_client.LocationsServiceError("нет связи")
    assert _go(client, character.id).status_code == 502
    assert _reload(db_session, character.id).current_location_id == LOC_FROM
    assert _logs(db_session, character.id) == []


# --- the reading lock (activity_lock.REASON_READING) ------------------------------------

def test_reading_locks_with_its_own_reason():
    lock = activity_lock.compute_lock(None, None, reading_since=datetime.utcnow())
    assert (lock["locked"], lock["reason"]) == (True, activity_lock.REASON_READING)
    assert activity_lock.lock_message(lock) == "Персонаж читает — сначала нужно закончить чтение"


def test_sleep_and_harder_locks_win_over_reading():
    now = datetime.utcnow()
    assert activity_lock.compute_lock(None, None, asleep_since=now, reading_since=now)["reason"] == "asleep"
    assert activity_lock.compute_lock(3, None, reading_since=now)["reason"] == "dungeon"


def test_lock_for_character_reads_the_reading_column():
    from types import SimpleNamespace
    reader = SimpleNamespace(dungeon_session_id=None, unconscious_until=None, asleep_since=None,
                             reading_since=datetime.utcnow())
    assert activity_lock.lock_for_character(reader)["reason"] == activity_lock.REASON_READING

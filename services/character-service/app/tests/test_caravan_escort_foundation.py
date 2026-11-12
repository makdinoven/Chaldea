"""FEAT-212 task 1 — the caravan escort foundation (features/FEAT-212 §3.5 / §3.6).

* the ``caravan_escort`` activity lock reason: priority and the neutral refusal text for every subject;
* the escort is hidden from ``/characters/by_location``;
* public reads (``short_info``, ``/public``, ``/list``) show the frozen hire location and no lock; the internal
  short_info keeps the real values unless ``masked=true``;
* ``update_location`` refuses an escort (defence in depth);
* ``caravan_escort_crud.release`` ends the job without pay (idempotent).

Lean on purpose (CI time): reuses the short_info fixtures, no economy world.
"""

from datetime import datetime, timedelta

import activity_lock
import caravan_escort_crud
import models
from tests.test_short_info_extended import (  # noqa: F401  (fixtures)
    _create_character, _seed_reference_data, client, db_session, internal_token,
)

HIRE_LOC = 101
ROAD_LOC = 102
CARAVAN = 7
NEUTRAL = "Цель: действие сейчас недоступно"


def _escort(db, *, name="Охранник"):
    race, cls, subrace = _seed_reference_data(db)
    ch = _create_character(db, name=name, race=race, cls=cls, subrace=subrace, current_location_id=ROAD_LOC)
    db.add(models.EconCaravanEscort(caravan_id=CARAVAN, character_id=ch.id, status="active",
                                    hire_location_id=HIRE_LOC, joined_at=datetime.utcnow()))
    ch.escort_caravan_id = CARAVAN
    db.commit()
    return ch


# --------------------------------------------------------------------------------------------- lock reason

def test_escort_lock_priority_and_neutral_text():
    lock = activity_lock.compute_lock(None, None, escort_caravan_id=5)
    assert (lock["locked"], lock["reason"]) == (True, activity_lock.REASON_CARAVAN_ESCORT)
    assert activity_lock.lock_message(lock, "Цель") == NEUTRAL
    assert activity_lock.lock_message(lock) == "Персонаж: действие сейчас недоступно"
    assert "карав" not in activity_lock.lock_message(lock, "Целевой персонаж").lower()
    # dungeon / unconscious / law win; escort wins over asleep / reading
    assert activity_lock.compute_lock(3, None, escort_caravan_id=5)["reason"] == activity_lock.REASON_DUNGEON
    later = datetime.utcnow() + timedelta(hours=1)
    assert activity_lock.compute_lock(None, later, escort_caravan_id=5)["reason"] == activity_lock.REASON_UNCONSCIOUS
    assert activity_lock.compute_lock(None, None, asleep_since=datetime.utcnow(), escort_caravan_id=5)["reason"] \
        == activity_lock.REASON_CARAVAN_ESCORT
    assert activity_lock.compute_lock(None, None, escort_caravan_id=None)["locked"] is False


# --------------------------------------------------------------------------------------------- visibility

def test_escort_hidden_from_location_list(client, db_session):
    ch = _escort(db_session)
    other = _create_character(db_session, name="Прохожий", race=db_session.query(models.Race).first(),
                              cls=db_session.query(models.Class).first(), current_location_id=ROAD_LOC)
    resp = client.get("/characters/by_location", params={"location_id": ROAD_LOC})
    assert resp.status_code == 200
    assert [p["id"] for p in resp.json()] == [other.id]
    assert ch.id not in [p["id"] for p in client.get("/characters/by_location",
                                                     params={"location_id": HIRE_LOC}).json()]


def test_public_short_info_is_masked_internal_is_real(client, db_session, internal_token):
    ch = _escort(db_session)
    public = client.get(f"/characters/{ch.id}/short_info").json()
    assert public["current_location_id"] == HIRE_LOC
    assert public["activity_lock"]["locked"] is False and public["activity_lock"]["reason"] is None
    headers = {"X-Internal-Token": internal_token}
    real = client.get(f"/characters/internal/{ch.id}/short_info", headers=headers).json()
    assert real["current_location_id"] == ROAD_LOC
    assert real["activity_lock"]["reason"] == activity_lock.REASON_CARAVAN_ESCORT
    masked = client.get(f"/characters/internal/{ch.id}/short_info", params={"masked": "true"}, headers=headers).json()
    assert masked["current_location_id"] == HIRE_LOC and masked["activity_lock"]["locked"] is False
    assert "currency_balance" in masked


def test_public_passport_and_list_show_hire_location(client, db_session):
    ch = _escort(db_session)
    assert client.get(f"/characters/{ch.id}/public").json()["current_location_id"] == HIRE_LOC
    items = {i["id"]: i for i in client.get("/characters/list").json()["items"]}
    assert items[ch.id]["current_location_id"] == HIRE_LOC


def test_not_an_escort_is_unchanged(client, db_session):
    race, cls, subrace = _seed_reference_data(db_session)
    ch = _create_character(db_session, race=race, cls=cls, subrace=subrace, current_location_id=ROAD_LOC)
    assert client.get(f"/characters/{ch.id}/short_info").json()["current_location_id"] == ROAD_LOC
    assert client.get("/characters/list").json()["items"][0]["current_location_id"] == ROAD_LOC


# --------------------------------------------------------------------------------------------- move / release

def test_update_location_refuses_escort(client, db_session, internal_token):
    ch = _escort(db_session)
    resp = client.put(f"/characters/internal/{ch.id}/update_location", json={"new_location_id": HIRE_LOC},
                      headers={"X-Internal-Token": internal_token})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Персонаж: действие сейчас недоступно"
    db_session.expire_all()
    assert db_session.get(models.Character, ch.id).current_location_id == ROAD_LOC


def test_release_ends_the_job_without_pay(db_session):
    ch = _escort(db_session)
    result = caravan_escort_crud.release(db_session, ch.id)
    db_session.commit()
    assert result.released and result.caravan_id == CARAVAN and result.notice is not None
    db_session.expire_all()
    character = db_session.get(models.Character, ch.id)
    assert character.escort_caravan_id is None and character.current_location_id == ROAD_LOC
    row = db_session.query(models.EconCaravanEscort).filter_by(character_id=ch.id).one()
    assert (row.status, row.fee, row.bonus) == ("released", 0, 0) and row.ended_at is not None
    assert db_session.query(models.CharacterLog).filter_by(character_id=ch.id, event_type="caravan_escort").count() == 1
    assert caravan_escort_crud.release(db_session, ch.id).released is False                 # idempotent

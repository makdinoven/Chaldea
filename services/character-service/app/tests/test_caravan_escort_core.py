"""FEAT-212 task 2 — smoke tests of the escort core (C1–C6, stepping, delivery pay, rewards, guild gate).

Lean on purpose (CI time; the full matrix is QA task 9): reuses the FEAT-211 raid world (``rw`` / ``api`` of
``test_caravan_raids``: a physical caravan food 400 marks standing at L_GATE1, players 501 / 502 / 503 there).
The ``npc_dialogue`` gate (``locations_client.check_npc_gate``) is mocked.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

import caravan_escort_crud as escorts
import locations_client
import models
from tests.test_caravan_raids import (  # noqa: F401  (fixtures)
    MATE, MATE_USER, RAIDER, STRANGER, _as_user, _gold, api, rw,
)
from tests.test_econ_tick import _rows, _scalar, factory  # noqa: F401
from tests.test_econ_tick_caravans import _exec, _set_params
from tests.test_econ_tick_events import calendar  # noqa: F401
from tests.test_physical_caravans import L_GATE1, L_GATE2, L_ROAD1, _check, _walk, world  # noqa: F401

NPC = 601
VIEW = f"/characters/caravans/caravaneer/{NPC}"
JOB = "/characters/caravans/escort"
LEAVE = "/characters/caravans/escort/leave"
MESSAGES = "/characters/caravans/escort/messages"
C1_ITEM_KEYS = {"id", "group_code", "group_name", "departs_in_sec", "has_seats", "pay_estimate", "can_hire", "reason"}


def _hire_url(caravan_id):
    return f"/characters/caravans/{caravan_id}/escort/hire"


@pytest.fixture
def esc(api, rw, monkeypatch):
    db = rw()
    try:
        db.add(models.Character(id=NPC, name="Караванщик", user_id=None, id_subrace=1, id_class=1, id_race=1,
                                appearance="-", avatar="-", is_npc=True, npc_role=escorts.CARAVANEER_ROLE,
                                current_location_id=L_GATE1, level=1, currency_balance=0))
        db.commit()
    finally:
        db.close()
    rw.gate = AsyncMock(return_value=True)
    monkeypatch.setattr(locations_client, "check_npc_gate", rw.gate)
    return api


def _hire(client, f, character=RAIDER):
    return client.post(_hire_url(f.cid), json={"character_id": character, "npc_id": NPC})


def _escort_column(f, cid):
    return _scalar(f, "SELECT escort_caravan_id FROM characters WHERE id = :c", c=cid)


def test_view_hire_and_seats(esc, rw):
    view = esc.get(VIEW, params={"character_id": RAIDER})
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["seats_enabled"] is True and body["my_escort_caravan_id"] is None
    (item,) = body["caravans"]
    assert set(item) == C1_ITEM_KEYS                      # no seat / escort counts, no route / value (PM decision 1)
    assert (item["id"], item["has_seats"], item["can_hire"]) == (rw.cid, True, True)
    assert item["pay_estimate"] == 400 * 5 // 100 // 3     # fee pool / seats

    resp = _hire(esc, rw)
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert (job["caravan_id"], job["state"], job["seats_total"]) == (rw.cid, "preparing", 3)
    assert [p["location_id"] for p in job["route"]][0] == L_GATE1 and job["escorts"][0]["character_id"] == RAIDER
    assert _escort_column(rw, RAIDER) == rw.cid
    again = esc.get(VIEW, params={"character_id": RAIDER}).json()
    assert again["my_escort_caravan_id"] == rw.cid
    assert again["caravans"][0]["reason"] == escorts.MSG_ALREADY_ESCORT
    assert _hire(esc, rw).json()["detail"] == escorts.MSG_ALREADY_ESCORT

    _set_params(rw, caravan_escort_seats=1)
    _as_user(MATE_USER)
    assert esc.get(VIEW, params={"character_id": MATE}).json()["caravans"][0]["has_seats"] is False
    resp = _hire(esc, rw, MATE)
    assert (resp.status_code, resp.json()["detail"]) == (409, escorts.MSG_NO_SEATS)
    _check(rw)


def test_gate_location_and_owner_refusals(esc, rw):
    rw.gate.return_value = False
    resp = esc.get(VIEW, params={"character_id": RAIDER})
    assert (resp.status_code, resp.json()["detail"]) == (403, escorts.MSG_GATE_CLOSED)
    rw.gate.return_value = True
    rw.gate.side_effect = locations_client.GateUnavailable()
    assert _hire(esc, rw).status_code == 503 and _escort_column(rw, RAIDER) is None
    rw.gate.side_effect = None
    assert esc.get(f"/characters/caravans/caravaneer/{RAIDER}",
                   params={"character_id": RAIDER}).json()["detail"] == escorts.MSG_CARAVANEER_NOT_FOUND
    _exec(rw, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_ROAD1, c=RAIDER)
    resp = esc.get(VIEW, params={"character_id": RAIDER})
    assert (resp.status_code, resp.json()["detail"]) == (400, escorts.MSG_NOT_AT_CARAVANEER)
    assert esc.get(VIEW, params={"character_id": STRANGER}).status_code == 403      # not the owner


def test_escort_rides_and_is_paid_on_delivery(esc, rw):
    assert _hire(esc, rw).status_code == 201
    _walk(rw, 4)                                           # 3 steps along 101-102-202-201, then delivery + rewards
    assert _scalar(rw, "SELECT current_location_id FROM characters WHERE id = :c", c=RAIDER) == L_GATE2
    row = _rows(rw, "SELECT status, fee, bonus, rewards_done FROM econ_caravan_escorts")[0]
    assert (row[0], int(row[1]), int(row[2]), int(row[3])) == ("delivered", 20, 0, 1)
    assert _gold(rw, RAIDER) == 20 and _escort_column(rw, RAIDER) is None
    assert _scalar(rw, "SELECT status FROM econ_caravans WHERE id = :c", c=rw.cid) == "delivered"
    actions = {r[0] for r in _rows(rw, "SELECT action FROM reputation_log WHERE character_id = :c", c=RAIDER)}
    assert "caravan_escort" in actions
    assert esc.get(JOB, params={"character_id": RAIDER}).json() == {"escort": None}
    _check(rw)


def test_leave_no_rejoin_and_refused_in_battle(esc, rw):
    assert _hire(esc, rw).status_code == 201
    _exec(rw, "INSERT INTO econ_caravan_raids (caravan_id, leader_character_id, location_id, status, created_at) "
              "VALUES (:c, :l, :loc, 'fighting', :now)", c=rw.cid, l=MATE, loc=L_GATE1, now=datetime.utcnow())
    resp = esc.post(LEAVE, json={"character_id": RAIDER})
    assert (resp.status_code, resp.json()["detail"]) == (409, escorts.MSG_LEAVE_IN_BATTLE)
    _exec(rw, "DELETE FROM econ_caravan_raids")
    resp = esc.post(LEAVE, json={"character_id": RAIDER})
    assert resp.status_code == 200 and resp.json() == {"left": True, "location_id": L_GATE1}
    assert _escort_column(rw, RAIDER) is None
    assert _hire(esc, rw).json()["detail"] == escorts.MSG_NO_REJOIN
    assert esc.post(LEAVE, json={"character_id": RAIDER}).status_code == 404


def test_channel_members_only_length_and_throttle(esc, rw):
    assert esc.get(MESSAGES, params={"character_id": RAIDER}).status_code == 404
    assert _hire(esc, rw).status_code == 201
    resp = esc.post(MESSAGES, json={"character_id": RAIDER, "text": "  Тихо, впереди засада  "})
    assert resp.status_code == 201 and resp.json()["body"] == "Тихо, впереди засада"
    assert esc.post(MESSAGES, json={"character_id": RAIDER, "text": "ещё"}).status_code == 429
    _exec(rw, "UPDATE econ_caravan_messages SET created_at = :t", t=datetime.utcnow() - timedelta(seconds=10))
    assert esc.post(MESSAGES, json={"character_id": RAIDER, "text": "   "}).status_code == 400
    assert esc.post(MESSAGES, json={"character_id": RAIDER, "text": "x" * 501}).status_code == 400
    page = esc.get(MESSAGES, params={"character_id": RAIDER}).json()
    assert page["caravan_id"] == rw.cid and [m["character_id"] for m in page["messages"]] == [RAIDER]
    assert esc.get(MESSAGES, params={"character_id": RAIDER,
                                     "after_id": page["messages"][0]["id"]}).json()["messages"] == []
    _as_user(MATE_USER)
    assert esc.get(MESSAGES, params={"character_id": MATE}).status_code == 404     # not an escort

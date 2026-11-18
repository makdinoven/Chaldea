"""FEAT-216 task 8 (developer smoke): smuggler escorts hired at a «Скупщик» (features/FEAT-216 §3.6, C7 / C8).

Focused checks only (the full flows are QA task 15): the caravaneer never sees / hires a contraband caravan; the fence
lists it (anywhere in the seller region) with the smuggler pay share; the fence hire leads the character to the caravan
with the fence as the hire location; an active customs officer is refused; a fence of another region finds nothing; a
smuggling run is pay only (no reputation / fame / faction rewards).
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

import caravan_escort_crud as escorts
import econ_sim
import models
from tests.test_caravan_escorts import (  # noqa: F401  (fixtures)
    NPC, OWNERS, VIEW, _as_user, _hire_url, _loc, _rows, _scalar, api, calendar, esc, factory, rw, world,
)
from tests.test_econ_tick_caravans import _exec, _set_params
from tests.test_physical_caravans import L_GATE1, L_GATE2, L_ROAD1
from tests.test_caravan_raids import RAIDER, USER

FENCE = 602
FENCE_VIEW = f"/characters/caravans/fence/{FENCE}"


@pytest.fixture
def smug(esc, rw):
    """The escort world with its caravan turned contraband, a fence on the road of the seller region (not at the
    gate) and the raider standing next to the fence."""
    db = rw()
    try:
        db.add(models.Character(id=FENCE, name="Скупщик", user_id=None, id_subrace=1, id_class=1, id_race=1,
                                appearance="-", avatar="-", is_npc=True, npc_role=escorts.FENCE_ROLE,
                                current_location_id=L_ROAD1, level=1, currency_balance=0))
        db.commit()
    finally:
        db.close()
    _exec(rw, "UPDATE econ_caravans SET is_contraband = 1, markup_pct = 50 WHERE id = :c", c=rw.cid)
    _exec(rw, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_ROAD1, c=RAIDER)
    _set_params(rw, customs_smuggler_fee_share=0.10, caravan_escort_fee_share=0.05)
    return esc


def _seats(rw):
    db = rw()
    try:
        return escorts._seats(escorts._params(db))
    finally:
        db.close()


def test_caravaneer_never_lists_or_hires_contraband(smug, rw):
    _exec(rw, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_GATE1, c=RAIDER)
    _as_user(USER)
    assert smug.get(VIEW, params={"character_id": RAIDER}).json()["caravans"] == []
    resp = smug.post(_hire_url(rw.cid), json={"character_id": RAIDER, "npc_id": NPC})
    assert (resp.status_code, resp.json()["detail"]) == (404, escorts.MSG_CARAVAN_NOT_FOUND)


def test_fence_lists_contraband_of_its_region_with_the_smuggler_share(smug, rw):
    _as_user(USER)
    resp = smug.get(FENCE_VIEW, params={"character_id": RAIDER})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["gate_location_id"] == L_GATE1 and body["gate_location_name"]
    assert [c["id"] for c in body["caravans"]] == [rw.cid]
    item = body["caravans"][0]
    assert "is_contraband" not in item and "markup_pct" not in item       # shown as an ordinary caravan
    assert item["can_hire"] is True
    assert item["pay_estimate"] == 40 // _seats(rw)                        # 400 marks x 10 %, every seat taken
    # the caravaneer endpoint does not accept a fence, the fence endpoint does not accept a caravaneer
    assert smug.get(VIEW.replace(str(NPC), str(FENCE)), params={"character_id": RAIDER}).status_code == 404
    resp = smug.get(f"/characters/caravans/fence/{NPC}", params={"character_id": RAIDER})
    assert (resp.status_code, resp.json()["detail"]) == (404, escorts.MSG_FENCE_NOT_FOUND)


def test_fence_lists_no_legal_caravan(smug, rw):
    _exec(rw, "UPDATE econ_caravans SET is_contraband = 0")
    _as_user(USER)
    assert smug.get(FENCE_VIEW, params={"character_id": RAIDER}).json()["caravans"] == []
    resp = smug.post(_hire_url(rw.cid), json={"character_id": RAIDER, "npc_id": FENCE})
    assert (resp.status_code, resp.json()["detail"]) == (404, escorts.MSG_CARAVAN_NOT_FOUND)


def test_fence_hire_leads_the_smuggler_to_the_caravan(smug, rw):
    _exec(rw, "UPDATE characters SET house_room_id = NULL WHERE id = :c", c=RAIDER)
    _as_user(USER)
    resp = smug.post(_hire_url(rw.cid), json={"character_id": RAIDER, "npc_id": FENCE})
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["is_contraband"] is True and job["state"] == escorts.STATE_PREPARING
    assert job["current_location_id"] == L_GATE1
    assert _loc(rw, RAIDER) == L_GATE1                                     # moved from the fence to the gate
    assert _scalar(rw, "SELECT hire_location_id FROM econ_caravan_escorts WHERE character_id = :c",
                   c=RAIDER) == L_ROAD1                                    # the public mask shows him at the fence
    assert _scalar(rw, "SELECT escort_caravan_id FROM characters WHERE id = :c", c=RAIDER) == rw.cid
    logs = [r[0] for r in _rows(rw, "SELECT description FROM character_logs WHERE character_id = :c", c=RAIDER)]
    assert any("у скупщика" in d for d in logs)


def test_active_customs_officer_is_refused(smug, rw):
    db = rw()
    try:
        db.add(models.EconCustomsOfficer(character_id=RAIDER, country_id=1, status="active",
                                         enlisted_at=datetime.utcnow()))
        db.commit()
    finally:
        db.close()
    _as_user(USER)
    item = smug.get(FENCE_VIEW, params={"character_id": RAIDER}).json()["caravans"][0]
    assert (item["can_hire"], item["reason"]) == (False, escorts.MSG_OFFICER)
    resp = smug.post(_hire_url(rw.cid), json={"character_id": RAIDER, "npc_id": FENCE})
    assert (resp.status_code, resp.json()["detail"]) == (403, escorts.MSG_OFFICER)
    assert _loc(rw, RAIDER) == L_ROAD1
    _exec(rw, "UPDATE econ_customs_officers SET status = 'resigned'")
    assert smug.post(_hire_url(rw.cid), json={"character_id": RAIDER, "npc_id": FENCE}).status_code == 201


def test_fence_of_another_region_finds_nothing(smug, rw):
    _exec(rw, "UPDATE characters SET current_location_id = :l WHERE id IN (:n, :c)", l=L_GATE2, n=FENCE, c=RAIDER)
    _as_user(USER)
    assert smug.get(FENCE_VIEW, params={"character_id": RAIDER}).json()["caravans"] == []
    resp = smug.post(_hire_url(rw.cid), json={"character_id": RAIDER, "npc_id": FENCE})
    assert (resp.status_code, resp.json()["detail"]) == (404, escorts.MSG_CARAVAN_NOT_FOUND)


def test_pools_pick_the_smuggler_share():
    params = econ_sim.SimParams(caravan_escort_fee_share=0.05, caravan_escort_bonus_share=0.03,
                                customs_smuggler_fee_share=0.10)
    assert escorts.pools(400, params, False) == (20, 0)
    assert escorts.pools(400, params, False, True) == (40, 0)
    assert escorts.pools(400, params, True, True) == (40, 12)


def test_smuggling_run_is_pay_only(smug, rw, monkeypatch):
    _as_user(USER)
    assert smug.post(_hire_url(rw.cid), json={"character_id": RAIDER, "npc_id": FENCE}).status_code == 201
    _exec(rw, "UPDATE econ_caravan_escorts SET status = 'delivered' WHERE character_id = :c", c=RAIDER)
    escort_id = _scalar(rw, "SELECT id FROM econ_caravan_escorts WHERE character_id = :c", c=RAIDER)
    import faction_kills
    import reputation_crud

    def boom(*a, **k):
        raise AssertionError("no rewards for a smuggling run")
    monkeypatch.setattr(faction_kills, "apply_caravan_deed", boom)
    monkeypatch.setattr(reputation_crud, "apply_reputation", boom)
    db = rw()
    try:
        params = SimpleNamespace(caravan_escort_defense_fame=5)
        assert escorts.reward_one(db, escort_id, datetime.utcnow(), params) is True
        assert escorts.reward_one(db, escort_id, datetime.utcnow(), params) is False   # claimed once
    finally:
        db.close()
    assert _scalar(rw, "SELECT rewards_done FROM econ_caravan_escorts WHERE id = :e", e=escort_id) == 1

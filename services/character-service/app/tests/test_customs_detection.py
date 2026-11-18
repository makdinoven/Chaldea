"""FEAT-216 task 7: detection, the officer's inspect, settlement and confiscation (focused checks on the FEAT-211 raid
world of ``test_caravan_raids``; the full flows incl. crimes / fame / reputation are QA task 15).

The raid world's caravan (food 200 units, 400 marks paid, region 1 → region 2, both country 1) is turned into
contraband by hand (``is_contraband = 1``; its destination country 1 makes it illegal everywhere in country 1). After
the first pass it stands at L_ROAD1 (region 1, country 1), a non-final node, so the customs check runs there.
battle-service is mocked (``battle_client.create_customs_battle``); the rolls go through ``customs_crud.rng``.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import battle_client
import caravan_pass
import caravan_raid_crud as raids
import customs_crud
from tests.test_caravan_raids import (  # noqa: F401  (fixtures)
    BATTLE, INTERNAL, MATE, RAIDER, RESULT, STRANGER, _as_user, _person, api, rw,
)
from tests.test_econ_tick import _balance, _rows, _scalar, factory  # noqa: F401
from tests.test_econ_tick_caravans import _exec, _set_params
from tests.test_econ_tick_events import calendar  # noqa: F401  (autouse: no calendar HTTP)
from tests.test_physical_caravans import L_GATE1, L_ROAD1, START, _check, _row, world  # noqa: F401

GUARD = 601
REAL_CONSEQUENCES = customs_crud.consequences
INSPECT = "/characters/caravans/{}/inspect"
ALWAYS = SimpleNamespace(random=lambda: 0.0)       # roll 0.00 < any positive chance
NEVER = SimpleNamespace(random=lambda: 0.9999)     # roll 99.99


class FakeCustomsBattle:
    def __init__(self):
        self.calls = []
        self.error = None

    async def __call__(self, raid_id, caravan_id, location_id, leader_character_id=None, group=False,
                       enforcer_npc_ids=(), guard_character_ids=(), escort_character_ids=()):
        self.calls.append({"raid_id": raid_id, "caravan_id": caravan_id, "location_id": location_id,
                           "leader": leader_character_id, "group": group, "enforcers": list(enforcer_npc_ids),
                           "guards": list(guard_character_ids), "escorts": list(escort_character_ids)})
        if self.error is not None:
            raise self.error
        attackers = [leader_character_id] if leader_character_id else list(enforcer_npc_ids)
        return {"battle_id": BATTLE, "attacker_character_ids": attackers,
                "escort_character_ids": list(escort_character_ids)}


@pytest.fixture
def cw(rw, monkeypatch):
    """Contraband caravan + customs on; the stealth maths are stubbed (no attributes / skills tables here)."""
    _exec(rw, "UPDATE econ_caravans SET is_contraband = 1")
    rw.customs = FakeCustomsBattle()
    monkeypatch.setattr(battle_client, "create_customs_battle", rw.customs)
    monkeypatch.setattr(customs_crud, "_escort_reduction", lambda db, ids, params, s: (0, 20))
    monkeypatch.setattr(customs_crud, "officer_attention", lambda db, cid, s: 0)
    rw.roll = ALWAYS
    monkeypatch.setattr(customs_crud, "rng", lambda: rw.roll)
    rw.consequences = []

    def fake_consequences(db, raid, caravan, params, now):
        import shadow_crud
        rw.consequences.append((int(raid.id), raid.kind, caravan.seized_region_id))
        return shadow_crud.KillOutcome()
    monkeypatch.setattr(customs_crud, "consequences", fake_consequences)
    return rw


def _officer(f, cid=RAIDER, location=L_ROAD1, country=1):
    _exec(f, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=location, c=cid)
    _exec(f, "INSERT INTO econ_customs_officers (character_id, country_id, status, enlisted_at, seizures, earned) "
             "VALUES (:c, :k, 'active', :t, 0, 0)", c=cid, k=country, t=START)


def _guard(f, location=L_ROAD1):
    db = f()
    try:
        _person(db, GUARD, None, location, npc=True, name="Стражник")
        db.commit()
    finally:
        db.close()
    _exec(f, "UPDATE characters SET npc_role = 'guard', npc_status = 'alive' WHERE id = :i", i=GUARD)


def _alerted(f):
    """One pass (the officer notices the caravan), then the alert is stretched past the API's real clock."""
    _pass(f)
    assert _row(f).customs_alert_officer_id == RAIDER
    _exec(f, "UPDATE econ_caravans SET customs_alert_until = :t", t=datetime(2100, 1, 1))


def _escort(f, cid=MATE):
    _exec(f, "INSERT INTO econ_caravan_escorts (caravan_id, character_id, status, hire_location_id, in_raid, fee, "
             "bonus, rewards_done, joined_at) VALUES (:car, :c, 'active', :l, 0, 0, 0, 0, :t)",
          car=f.cid, c=cid, l=L_GATE1, t=START)


def _pass(f, now=START):
    stats = caravan_pass.run_pass(f, now=now, force=True, rng=lambda: 0.5)
    _check(f)
    return stats


def _raid_row(f):
    rows = _rows(f, "SELECT id, kind, status, leader_character_id, seized_done, officer_paid, law_done, "
                    "faction_done FROM econ_caravan_raids")
    return rows[0] if rows else None


def _seizure_ops(f):
    return _rows(f, "SELECT id FROM econ_operations WHERE op_type = 'caravan_seizure'")


# ===================================================================================================================


def test_officer_on_watch_raises_an_alert_and_the_caravan_waits(cw):
    _officer(cw)
    _set_params(cw, customs_alert_minutes=40)
    stats = _pass(cw)
    assert stats["moved"] == 1 and stats.get("customs_alert") == 1
    row = _row(cw)
    assert (row.current_location_id, row.customs_alert_officer_id) == (L_ROAD1, RAIDER)
    assert row.customs_alert_until == START + timedelta(minutes=40)
    assert _pass(cw, START + timedelta(minutes=30))["held"] == 1                # alert holds the caravan
    assert _row(cw).current_location_id == L_ROAD1
    assert _pass(cw, START + timedelta(minutes=41))["moved"] == 1               # expired → moves on


def test_failed_roll_and_no_guards_change_nothing(cw):
    _officer(cw)
    cw.roll = NEVER
    _pass(cw)
    row = _row(cw)
    assert row.customs_alert_officer_id is None and row.status == "in_transit"


def test_legal_caravan_and_customs_off_are_never_checked(cw):
    _officer(cw)
    _exec(cw, "UPDATE econ_caravans SET is_contraband = 0")
    _pass(cw)
    assert _row(cw).customs_alert_officer_id is None


def test_officer_of_another_country_does_not_watch(cw):
    _officer(cw, country=2)
    _pass(cw)
    assert _row(cw).customs_alert_officer_id is None


def test_inspect_is_one_generic_404_for_everyone_but_the_alerted_officer(api, cw):
    _officer(cw)
    _alerted(cw)
    _exec(cw, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_ROAD1, c=MATE)
    for cid, user in ((MATE, 8), (STRANGER, 99)):
        _as_user(user)
        resp = api.post(INSPECT.format(cw.cid), json={"character_id": cid})
        assert resp.status_code == 404 and resp.json()["detail"] == customs_crud.MSG_NOTHING_TO_INSPECT
    _as_user(7)
    assert api.post(INSPECT.format(999999), json={"character_id": RAIDER}).json()["detail"] == \
        customs_crud.MSG_NOTHING_TO_INSPECT
    assert cw.customs.calls == [] and _raid_row(cw) is None


def test_inspect_won_fight_seizes_the_caravan_and_pays_the_officer(api, cw):
    _officer(cw)
    _alerted(cw)
    resp = api.post(INSPECT.format(cw.cid), json={"character_id": RAIDER, "group": False})
    assert resp.status_code == 201, resp.text
    assert resp.json()["battle_id"] == BATTLE
    call = cw.customs.calls[0]
    assert (call["leader"], call["enforcers"], call["location_id"]) == (RAIDER, [], L_ROAD1) and call["guards"]
    raid = _raid_row(cw)
    assert (raid[1], raid[2], raid[3]) == ("customs", "fighting", RAIDER)
    assert _row(cw).customs_alert_officer_id is None                            # alert consumed
    paid = _row(cw).paid_purse + _row(cw).paid_treasury
    country, gold = _balance(cw, "country_treasury", 1), _scalar(cw, "SELECT currency_balance FROM characters "
                                                                    "WHERE id = :c", c=RAIDER)
    stock = _scalar(cw, "SELECT stock FROM econ_region_goods WHERE region_id = 1 AND group_code = 'food'")

    resp = api.post(RESULT, json={"battle_id": BATTLE, "caravan_raid_id": raid[0], "winner_team": 0,
                                  "aborted": False}, headers=INTERNAL)
    assert resp.status_code == 200 and resp.json()["status"] == "won"
    _check(cw)
    row = _row(cw)
    assert (row.status, row.cancel_reason, row.seized_region_id, row.seized_country_id) == \
        ("cancelled", "seized_customs", 1, 1)
    share = int(paid * 0.2)
    assert _scalar(cw, "SELECT currency_balance FROM characters WHERE id = :c", c=RAIDER) == gold + share
    assert _balance(cw, "country_treasury", 1) == country + paid - share
    assert float(_scalar(cw, "SELECT stock FROM econ_region_goods WHERE region_id = 1 AND group_code = 'food'")) == \
        pytest.approx(float(stock) + 200)
    raid = _raid_row(cw)
    assert (raid[4], raid[5], raid[6]) == (1, share, 1)                         # seized, officer_paid, law step
    assert cw.consequences == [(raid[0], "customs", 1)]
    assert _rows(cw, "SELECT seizures, earned FROM econ_customs_officers WHERE character_id = :c", c=RAIDER) == \
        [(1, share)]
    assert len(_seizure_ops(cw)) == 1 and cw.law.calls == []                   # no bandit consequences
    share_out = raids.raid_share_by_battle(cw(), BATTLE, RAIDER)
    assert share_out["raid"] is False                                          # the victory window: plain PvE


def test_repelled_inspection_lets_the_caravan_move_on(api, cw):
    _officer(cw)
    _alerted(cw)
    raid_id = api.post(INSPECT.format(cw.cid), json={"character_id": RAIDER}).json()["raid_id"]
    api.post(RESULT, json={"battle_id": BATTLE, "caravan_raid_id": raid_id, "winner_team": 1, "aborted": False},
             headers=INTERNAL)
    row = _row(cw)
    assert row.status == "in_transit" and row.next_move_at is not None and _seizure_ops(cw) == []


def test_patrol_without_escorts_confiscates_without_a_fight(cw):
    _guard(cw)
    country = _balance(cw, "country_treasury", 1)
    paid = _row(cw).paid_purse + _row(cw).paid_treasury
    stats = _pass(cw)
    assert stats.get("customs_seized") == 1 and cw.customs.calls == []
    row = _row(cw)
    assert (row.status, row.cancel_reason, row.seized_region_id) == ("cancelled", "seized_patrol", 1)
    assert _balance(cw, "country_treasury", 1) == country + paid
    assert _raid_row(cw) is None


def test_patrol_with_escorts_starts_a_fight_and_409_falls_back_to_seizure(cw):
    _guard(cw)
    _escort(cw)
    cw.customs.error = battle_client.BattleServiceError("x", 409, customs_crud.BS_NO_DEFENDERS)
    stats = _pass(cw)
    assert stats.get("customs_seized") == 1
    call = cw.customs.calls[0]
    assert (call["enforcers"], call["escorts"], call["leader"], call["guards"]) == ([GUARD], [MATE], None, [])
    assert _row(cw).cancel_reason == "seized_patrol" and _raid_row(cw) is None
    assert _rows(cw, "SELECT status FROM econ_caravan_escorts") == [("cancelled",)]


def test_patrol_fight_won_by_guards_is_confiscated_by_the_followup(cw, api):
    _guard(cw)
    _escort(cw)
    assert _pass(cw).get("customs_patrol_fight") == 1
    raid = _raid_row(cw)
    assert (raid[1], raid[2], raid[3]) == ("patrol", "fighting", GUARD)
    api.post(RESULT, json={"battle_id": BATTLE, "caravan_raid_id": raid[0], "winner_team": 0, "aborted": False},
             headers=INTERNAL)
    row = _row(cw)
    assert (row.status, row.cancel_reason) == ("cancelled", "seized_patrol")
    assert _raid_row(cw)[5] == 0                                               # no officer share for a patrol
    assert _rows(cw, "SELECT status FROM econ_caravan_escorts") == [("fallen",)]
    assert cw.consequences == [(raid[0], "patrol", 1)]


def test_seizure_waits_while_an_economy_run_is_running(cw, api):
    _officer(cw)
    _alerted(cw)
    raid_id = api.post(INSPECT.format(cw.cid), json={"character_id": RAIDER}).json()["raid_id"]
    _exec(cw, "INSERT INTO econ_tick_runs (id, trigger_kind, status, started_at, heartbeat_at) "
              "VALUES (77, 'manual', 'running', :t, :t)", t=START)
    api.post(RESULT, json={"battle_id": BATTLE, "caravan_raid_id": raid_id, "winner_team": 0, "aborted": False},
             headers=INTERNAL)
    row = _row(cw)
    assert row.status == "in_transit" and row.next_move_at is None             # frozen, not seized yet
    assert _raid_row(cw)[6] == 0                                               # law step waits for the seizure
    _exec(cw, "UPDATE econ_tick_runs SET status = 'done' WHERE id = 77")
    _pass(cw, START + timedelta(minutes=5))                                     # the follow-up seizes it
    assert _row(cw).cancel_reason == "seized_customs" and _raid_row(cw)[6] == 1



def test_consequences_crime_for_escorts_fame_and_reputation_for_the_officer(cw, api, monkeypatch):
    """The real law step (unmocked): ``smuggling`` crime for the escort in the seizure region, fame
    ``customs_seizure`` for the officer."""
    monkeypatch.setattr(customs_crud, "consequences", REAL_CONSEQUENCES)
    _escort(cw)
    _officer(cw)
    _alerted(cw)
    raid_id = api.post(INSPECT.format(cw.cid), json={"character_id": RAIDER}).json()["raid_id"]
    api.post(RESULT, json={"battle_id": BATTLE, "caravan_raid_id": raid_id, "winner_team": 0, "aborted": False},
             headers=INTERNAL)
    assert _row(cw).cancel_reason == "seized_customs" and _raid_row(cw)[6] == 1
    assert _rows(cw, "SELECT character_id, crime_type, region_id, event_key FROM law_crimes") ==         [(MATE, "smuggling", 1, f"law:smuggling:r{raid_id}:{MATE}")]
    fame = _rows(cw, "SELECT character_id, source, delta FROM renown_log WHERE scale = 'fame'")
    assert (RAIDER, "customs_seizure", 30) in fame
    assert (RAIDER, "reputation", 10) in fame                                  # the +20 reputation's own fame

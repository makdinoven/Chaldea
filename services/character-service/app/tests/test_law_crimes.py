"""FEAT-198 QA (task 9): crimes and the NPC-status hook (§3.4, L7, §3.14 A2).

* ``register_crime``: idempotent key, bandit / non-positive -> nothing, max clamp, heavy floor, crime row status,
  NPCs never get wanted, decay anchor;
* ``PUT /characters/internal/npc-status``: a merchant kill gives reputation + wanted once; a guard is KNOCKED OUT
  (conditional, stays alive, −300 rep + wanted >= heavy floor once, repeat is a no-op);
* the NPC list hides knocked-out guards and keeps NULL-role NPCs.
"""

from datetime import datetime, timedelta

import pytest

import law_core as lc
import law_crud
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BANDIT, BETA, GAMMA, GUARD, GUARD_POST, INTERNAL, L_MARKET, MERCHANT, NO_ROLE, NOWHERE, OVERRIDE,
    R_OST, SCRIBE, USER_ALPHA, api, exec_, force_witnessed, law_payloads, law_world, now, q, rep_world, rows,
    set_wanted, wanted,
)

# FEAT-199: these FEAT-198 tests assume immediate application -> every kill is witnessed
pytestmark = pytest.mark.usefixtures("force_witnessed")


def _crime(f, **kwargs):
    db = f()
    try:
        params = dict(crime_type="npc_kill", character_id=ALPHA, region_id=R_OST, points=150,
                      event_key="crime:test:1")
        params.update(kwargs)
        result = law_crud.register_crime(db, **params)
        db.commit()
        return result
    finally:
        db.close()


# =============================================================================================== register_crime

def test_register_crime_applies_and_is_idempotent(law_world):
    first = _crime(law_world)
    assert not first.duplicate and first.crime_id and first.change is not None
    assert (first.change.value_before, first.change.value_after, first.change.level_after) == (0, 150, "offender")
    assert first.change.level_raised and first.change.user_id == USER_ALPHA
    assert first.change.region_name == "Ост"
    assert wanted(law_world, ALPHA, R_OST) == 150
    crime = rows(law_world, "SELECT status, wanted_points, wanted_applied, crime_type, resolved_at FROM law_crimes")
    assert crime[0][:4] == ("reported", 150, 150, "npc_kill") and crime[0][4] is not None
    assert q(law_world, "SELECT decay_at FROM character_wanted WHERE character_id = :c", c=ALPHA) is not None
    again = _crime(law_world)
    assert again.duplicate and again.change is None
    assert wanted(law_world, ALPHA, R_OST) == 150
    assert q(law_world, "SELECT COUNT(*) FROM law_crimes") == 1
    assert q(law_world, "SELECT COUNT(*) FROM law_log WHERE action = 'crime'") == 1


def test_register_crime_skips_non_positive_and_npcs(law_world):
    assert _crime(law_world, points=0).skipped
    assert _crime(law_world, points=-20, event_key="k2").skipped               # bandit-like weight
    assert _crime(law_world, character_id=MERCHANT, event_key="k3").skipped     # NPCs never get wanted
    assert q(law_world, "SELECT COUNT(*) FROM law_crimes") == 0
    assert wanted(law_world, ALPHA, R_OST) is None


def test_register_crime_clamp_and_floor(law_world):
    set_wanted(law_world, ALPHA, R_OST, 900)
    r = _crime(law_world, points=500)
    assert r.change.value_after == 1000                                         # max_wanted
    r = _crime(law_world, character_id=BETA, points=0, floor=600, event_key="crime:escape:1:1",
               crime_type="jail_escape")
    assert r.change.value_after == 600 and r.change.level_after == "villain"
    assert rows(law_world, "SELECT wanted_points, wanted_applied FROM law_crimes WHERE character_id = :c",
                c=BETA) == [(0, 600)]


def test_register_crime_long_key_rejected(law_world):
    with pytest.raises(law_crud.LawError) as exc:
        _crime(law_world, event_key="x" * 192)
    assert exc.value.status_code == 400


def test_register_crime_decays_before_adding(law_world):
    set_wanted(law_world, ALPHA, R_OST, 200, decay_at=now() - timedelta(days=2))   # effective 100
    r = _crime(law_world, points=150)
    assert (r.change.value_before, r.change.value_after) == (100, 250)


# =============================================================================================== npc-status hook

def _kill(api, npc_id, killers, battle_id=77):
    body = {"status": "dead", "killer_character_ids": killers}
    if battle_id is not None:
        body["battle_id"] = battle_id
    return api.put(f"/characters/internal/npc-status/{npc_id}", json=body, headers=INTERNAL)


def test_merchant_kill_creates_wanted_once(api, law_world, stub_law_notify_send):
    resp = _kill(api, MERCHANT, [ALPHA, BETA, BANDIT])
    assert resp.status_code == 200, resp.text
    assert resp.json()["killed"] is True and resp.json()["status"] == "dead"
    assert wanted(law_world, ALPHA, R_OST) == 150 and wanted(law_world, BETA, R_OST) == 150
    assert wanted(law_world, BANDIT, R_OST) is None                              # NPC killers ignored
    keys = [r[0] for r in rows(law_world, "SELECT event_key FROM law_crimes ORDER BY character_id")]
    assert keys == [f"crime:npc_kill:{MERCHANT}:77:{ALPHA}", f"crime:npc_kill:{MERCHANT}:77:{BETA}"]
    payloads = law_payloads(stub_law_notify_send)
    assert {p["target_value"] for p in payloads} == {7, 8}
    assert all(p["category"] == "progress" and p["ws_type"] == "law_wanted" for p in payloads)
    assert "Нарушитель" in payloads[0]["message"] and "150" not in payloads[0]["message"]
    # a repeated report: no new crime, no new wanted
    resp = _kill(api, MERCHANT, [ALPHA, BETA])
    assert resp.json()["killed"] is False
    assert q(law_world, "SELECT COUNT(*) FROM law_crimes") == 2 and wanted(law_world, ALPHA, R_OST) == 150


def test_bandit_kill_is_not_a_crime(api, law_world):
    assert _kill(api, BANDIT, [ALPHA]).json()["killed"] is True
    assert q(law_world, "SELECT COUNT(*) FROM law_crimes") == 0
    assert wanted(law_world, ALPHA, R_OST) is None


def test_npc_without_region_is_not_a_crime(api, law_world):
    assert _kill(api, NOWHERE, [ALPHA]).json()["killed"] is True
    assert q(law_world, "SELECT COUNT(*) FROM law_crimes") == 0


def test_guard_is_knocked_out_not_killed(api, law_world):
    before = datetime.utcnow().replace(microsecond=0)
    resp = _kill(api, GUARD, [ALPHA])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "alive" and data["killed"] is True
    ko = datetime.fromisoformat(data["knocked_out_until"])
    assert before + timedelta(hours=6) <= ko <= before + timedelta(hours=6, seconds=5)
    assert q(law_world, "SELECT npc_status FROM characters WHERE id = :i", i=GUARD) == "alive"
    assert q(law_world, "SELECT unconscious_until FROM characters WHERE id = :i", i=GUARD) is not None
    # reputation -300 and wanted raised to the heavy floor (300 points -> 600)
    assert q(law_world, "SELECT value FROM character_reputation WHERE character_id = :c AND region_id = :r",
             c=ALPHA, r=R_OST) == -300
    assert wanted(law_world, ALPHA, R_OST) == 600
    assert rows(law_world, "SELECT crime_type, wanted_points FROM law_crimes") == [("guard_defeat", 300)]
    assert q(law_world, "SELECT COUNT(*) FROM law_log WHERE action = 'guard_ko' AND character_id = :g",
             g=GUARD) == 1
    # a repeated report while KO'd: nothing more
    again = _kill(api, GUARD, [ALPHA]).json()
    assert again["killed"] is False and again["knocked_out_until"] is None
    assert q(law_world, "SELECT value FROM character_reputation WHERE character_id = :c AND region_id = :r",
             c=ALPHA, r=R_OST) == -300
    assert q(law_world, "SELECT COUNT(*) FROM law_crimes") == 1


def test_guard_with_small_override_still_reaches_heavy_floor(api, law_world):
    set_wanted(law_world, BETA, R_OST, 700)
    assert _kill(api, OVERRIDE, [ALPHA, BETA]).json()["killed"] is True
    assert wanted(law_world, ALPHA, R_OST) == 600                               # 5 points, floor 600
    assert wanted(law_world, BETA, R_OST) == 705                                # already above the floor


def test_knocked_out_guard_can_be_knocked_out_again_after_recovery(api, law_world):
    _kill(api, GUARD_POST, [ALPHA], battle_id=1)
    exec_(law_world, "UPDATE characters SET unconscious_until = :t WHERE id = :g",
          t=datetime.utcnow() - timedelta(minutes=1), g=GUARD_POST)
    data = _kill(api, GUARD_POST, [BETA], battle_id=2).json()
    assert data["killed"] is True and data["knocked_out_until"]
    assert q(law_world, "SELECT COUNT(*) FROM law_crimes WHERE crime_type = 'guard_defeat'") == 2


def test_dead_guard_is_not_knocked_out(law_world):
    exec_(law_world, "UPDATE characters SET npc_status = 'dead' WHERE id = :g", g=GUARD_POST)
    db = law_world()
    try:
        assert law_crud.knock_out_guard(db, GUARD_POST, battle_id=5) is None
    finally:
        db.close()


def test_guard_kill_without_killers_only_knocks_out(api, law_world):
    resp = api.put(f"/characters/internal/npc-status/{GUARD_POST}", json={"status": "dead"}, headers=INTERNAL)
    assert resp.status_code == 200 and resp.json()["status"] == "alive"
    assert q(law_world, "SELECT COUNT(*) FROM law_crimes") == 0


def test_reviving_a_knocked_out_guard_clears_the_knock_out(api, law_world):
    _kill(api, GUARD, [ALPHA])
    assert q(law_world, "SELECT unconscious_until FROM characters WHERE id = :g", g=GUARD) is not None
    resp = api.put(f"/characters/internal/npc-status/{GUARD}", json={"status": "alive"}, headers=INTERNAL)
    assert resp.status_code == 200 and resp.json()["status"] == "alive"
    assert q(law_world, "SELECT unconscious_until FROM characters WHERE id = :g", g=GUARD) is None
    loc = q(law_world, "SELECT current_location_id FROM characters WHERE id = :g", g=GUARD)
    db = law_world()
    try:
        assert GUARD in law_crud.guards_at(db, loc, datetime.utcnow())             # on duty at once
    finally:
        db.close()


def test_npc_status_requires_internal_token(api, law_world):
    resp = api.put(f"/characters/internal/npc-status/{GUARD}", json={"status": "dead"})
    assert resp.status_code in (401, 403)
    assert q(law_world, "SELECT unconscious_until FROM characters WHERE id = :g", g=GUARD) is None


# =============================================================================================== NPC list

def test_npc_list_hides_knocked_out_guards_and_keeps_null_role(api, law_world):
    ids = {n["id"] for n in api.get("/characters/npcs/by_location", params={"location_id": L_MARKET}).json()}
    assert {GUARD, NO_ROLE, MERCHANT, SCRIBE} <= ids                            # NULL role listed (side-bug fix)
    _kill(api, GUARD, [ALPHA])
    ids = {n["id"] for n in api.get("/characters/npcs/by_location", params={"location_id": L_MARKET}).json()}
    assert GUARD not in ids and NO_ROLE in ids
    exec_(law_world, "UPDATE characters SET unconscious_until = :t WHERE id = :g",
          t=datetime.utcnow() - timedelta(seconds=5), g=GUARD)
    ids = {n["id"] for n in api.get("/characters/npcs/by_location", params={"location_id": L_MARKET}).json()}
    assert GUARD in ids

"""FEAT-198 QA (task 9): entry evaluation (§3.4) and its hooks.

* ``evaluate_entry``: no guard / KO'd guard / dead guard / wanted 0 non-outlaw -> no encounter; an outlaw with 0
  wanted is stopped (user decision 1) at the outlaw minimum level; snapshots; NPCs and locked characters skipped;
* ``PUT /characters/internal/{id}/update_location``: the encounter is created in the same commit as the move,
  409 while jailed / in an encounter (anti-dodge), the response carries ``law_encounter`` without raw numbers;
* teleport master = entry (user decision 4); the home scroll / admin move are not hooked (``apply_admin_move``);
* §3.14-ANSWERED A7: a fled character is not stopped again in that location for 1 hour.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

import crud
import econ_ledger
import law_crud
import locations_client
import models
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GAMMA, GUARD_FARM, GUARD_POST, INTERNAL, L_FARM, L_JAIL, L_MARKET, L_POST, L_ROAD, R_OST,
    R_PASHNI, USER_ALPHA, api, as_user, char_row, encounter, exec_, jail_character, law_payloads, law_world,
    make_encounter, now, q, rep_world, rows, set_value, set_wanted, wanted,
)


def _move(api, cid, loc, source=None, headers=INTERNAL):
    body = {"new_location_id": loc}
    if source is not None:
        body["source"] = source
    return api.put(f"/characters/internal/{cid}/update_location", json=body, headers=headers)


# =============================================================================================== evaluate_entry

def test_no_wanted_no_encounter(law_world):
    assert make_encounter(law_world) is None
    assert q(law_world, "SELECT COUNT(*) FROM law_encounters") == 0


def test_wanted_meets_guard_with_snapshots(law_world):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world, source="quick_move")
    enc = encounter(law_world, enc_id)
    assert (enc.status, enc.region_id, enc.location_id, enc.from_location_id) == ("pending", R_OST, L_POST,
                                                                                   L_MARKET)
    assert (enc.guard_npc_id, enc.level_code, enc.fine, enc.jail_hours) == (GUARD_POST, "offender", 150, 12)
    assert (enc.is_outlaw, enc.has_jail, enc.flee_used, enc.source) == (False, True, False, "quick_move")
    assert enc.wanted_value == 150
    created, expires = enc.created_at, enc.expires_at
    assert expires - created == timedelta(hours=24)
    assert char_row(law_world, ALPHA).law_encounter_id == enc_id
    assert q(law_world, "SELECT action FROM law_log WHERE event_key = :k", k=f"law:encounter:{enc_id}") == "encounter"


def test_location_without_guard(law_world):
    set_wanted(law_world, ALPHA, R_OST, 150)
    assert make_encounter(law_world, location_id=L_ROAD) is None


def test_knocked_out_or_dead_guard_does_not_meet(law_world):
    set_wanted(law_world, ALPHA, R_OST, 150)
    exec_(law_world, "UPDATE characters SET unconscious_until = :t WHERE id = :g",
          t=datetime.utcnow() + timedelta(hours=1), g=GUARD_POST)
    assert make_encounter(law_world) is None
    exec_(law_world, "UPDATE characters SET unconscious_until = NULL, npc_status = 'dead' WHERE id = :g",
          g=GUARD_POST)
    assert make_encounter(law_world) is None


def test_fully_decayed_wanted_is_not_stopped(law_world):
    set_wanted(law_world, ALPHA, R_OST, 100, decay_at=now() - timedelta(days=3))       # 50/day -> 0
    assert make_encounter(law_world) is None


def test_wanted_in_another_region_does_not_count(law_world):
    set_wanted(law_world, ALPHA, R_PASHNI, 500)
    assert make_encounter(law_world) is None


def test_outlaw_with_zero_wanted_is_stopped_at_outlaw_level(law_world):
    set_value(law_world, ALPHA, R_OST, -700)                                           # «Вне закона»
    enc = encounter(law_world, make_encounter(law_world))
    assert enc.is_outlaw and enc.level_code == "criminal" and enc.wanted_value == 0
    assert (enc.fine, enc.jail_hours) == (400, 24)


def test_outlaw_above_min_level_keeps_the_higher_level(law_world):
    set_value(law_world, ALPHA, R_OST, -700)
    set_wanted(law_world, ALPHA, R_OST, 950)
    enc = encounter(law_world, make_encounter(law_world))
    assert enc.level_code == "enemy" and enc.jail_hours == 168


def test_region_without_jail_snapshot(law_world):
    set_wanted(law_world, ALPHA, R_PASHNI, 150)
    enc = encounter(law_world, make_encounter(law_world, location_id=L_FARM))
    assert enc.has_jail is False and enc.guard_npc_id == GUARD_FARM


def test_already_locked_characters_are_skipped(law_world):
    set_wanted(law_world, ALPHA, R_OST, 150)
    first = make_encounter(law_world)
    assert first is not None
    assert make_encounter(law_world) is None                                            # already in an encounter
    set_wanted(law_world, BETA, R_OST, 150)
    jail_character(law_world, BETA)
    assert make_encounter(law_world, character_id=BETA) is None                         # jailed
    assert q(law_world, "SELECT COUNT(*) FROM law_encounters") == 1


def test_flee_cooldown_blocks_a_new_stop_for_one_hour(law_world):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    exec_(law_world, "UPDATE law_encounters SET status = 'fled', cooldown_until = :t WHERE id = :e",
          t=now() + timedelta(minutes=59), e=enc_id)
    exec_(law_world, "UPDATE characters SET law_encounter_id = NULL WHERE id = :c", c=ALPHA)
    assert make_encounter(law_world) is None                                            # same location: cooldown
    set_wanted(law_world, ALPHA, R_PASHNI, 150)
    assert make_encounter(law_world, location_id=L_FARM) is not None                    # another location: stopped
    exec_(law_world, "UPDATE characters SET law_encounter_id = NULL WHERE id = :c", c=ALPHA)
    exec_(law_world, "UPDATE law_encounters SET cooldown_until = :t WHERE id = :e",
          t=now() - timedelta(seconds=1), e=enc_id)
    assert make_encounter(law_world) is not None                                        # cooldown over


# =============================================================================================== update_location

def test_update_location_creates_encounter_in_the_move_commit(api, law_world, stub_law_notify_send):
    set_wanted(law_world, ALPHA, R_OST, 150)
    resp = _move(api, ALPHA, L_POST, source="quick_move")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["current_location_id"] == L_POST
    enc = data["law_encounter"]
    assert enc["status"] == "pending" and enc["options"] == ["fine", "surrender", "flee", "fight"]
    assert enc["guard_name"] == "Стражник Орм" and enc["level_name"] == "Нарушитель"
    assert "wanted_value" not in enc and "level_code" not in enc                        # no raw numbers
    assert enc["flee_chance_pct"] == 20.0                                               # base, 0 agility / luck
    row = char_row(law_world, ALPHA)
    assert row.current_location_id == L_POST and row.law_encounter_id == enc["id"]
    assert encounter(law_world, enc["id"]).source == "quick_move"
    payload = law_payloads(stub_law_notify_send)
    assert payload and payload[0]["ws_type"] == "law_encounter" and payload[0]["category"] == "system"
    assert payload[0]["target_value"] == USER_ALPHA


def test_update_location_unknown_source_is_a_move(api, law_world):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = _move(api, ALPHA, L_POST, source="teleport'; DROP TABLE characters;--").json()["law_encounter"]["id"]
    assert encounter(law_world, enc_id).source == "move"


def test_update_location_409_while_in_encounter_or_jail(api, law_world):
    set_wanted(law_world, ALPHA, R_OST, 150)
    assert _move(api, ALPHA, L_POST).status_code == 200
    resp = _move(api, ALPHA, L_MARKET)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Персонаж остановлен стражей — сначала нужно решить, как поступить"
    assert char_row(law_world, ALPHA).current_location_id == L_POST                    # nothing moved
    jail_character(law_world, BETA, hours=2)
    resp = _move(api, BETA, L_MARKET)
    assert resp.status_code == 409 and resp.json()["detail"].startswith("Персонаж в тюрьме — осталось")
    assert char_row(law_world, BETA).current_location_id == L_JAIL


def test_update_location_post_in_same_location_does_not_evaluate(api, law_world):
    exec_(law_world, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_POST, c=ALPHA)
    set_wanted(law_world, ALPHA, R_OST, 150)
    resp = _move(api, ALPHA, L_POST)
    assert resp.status_code == 200 and resp.json()["law_encounter"] is None


def test_update_location_without_wanted_has_null_encounter(api, law_world):
    resp = _move(api, ALPHA, L_POST)
    assert resp.status_code == 200 and resp.json()["law_encounter"] is None


def test_update_location_requires_internal_token(api, law_world):
    assert _move(api, ALPHA, L_POST, headers={}).status_code in (401, 403)


def test_expired_jail_does_not_block_moves(api, law_world):
    jail_character(law_world, BETA, hours=-1)
    assert _move(api, BETA, L_MARKET).status_code == 200


# =============================================================================================== teleport

TP_FROM, TP_TO = 70, 71


@pytest.fixture
def teleport_world(law_world, monkeypatch):
    db = law_world()
    try:
        with econ_ledger.allow_direct_balance_write(db):
            for cid, loc in ((TP_FROM, L_MARKET), (TP_TO, L_POST)):
                db.add(models.Character(id=cid, name=f"Маг {cid}", user_id=None, id_subrace=1, id_class=1,
                                        id_race=1, appearance="-", avatar="-", is_npc=True,
                                        npc_role="teleport_master", npc_status="alive", current_location_id=loc,
                                        level=5, currency_balance=0))
            db.flush()
        db.add(models.TeleportLink(id=1, from_npc_id=TP_FROM, to_npc_id=TP_TO, cost_gold=0))
        db.execute(text("UPDATE users SET current_character = :c WHERE id = :u"), {"c": ALPHA, "u": USER_ALPHA})
        db.commit()
    finally:
        db.close()
    left = MagicMock()
    monkeypatch.setattr(locations_client, "notify_character_left_location_sync", left)
    return law_world


def test_teleport_master_arrival_is_an_entry(api, teleport_world, stub_law_notify_send):
    set_wanted(teleport_world, ALPHA, R_OST, 150)
    as_user(USER_ALPHA)
    resp = api.post(f"/characters/npcs/{TP_FROM}/teleport", json={"link_id": 1})
    assert resp.status_code == 200, resp.text
    enc = resp.json()["law_encounter"]
    assert enc and enc["status"] == "pending"
    assert "law_encounter_id" not in resp.json()                                        # internal field stripped
    stored = encounter(teleport_world, enc["id"])
    assert (stored.source, stored.from_location_id, stored.location_id) == ("teleport", L_MARKET, L_POST)
    assert char_row(teleport_world, ALPHA).law_encounter_id == enc["id"]
    assert any(p["ws_type"] == "law_encounter" for p in law_payloads(stub_law_notify_send))


def test_teleport_without_wanted_has_no_encounter(api, teleport_world):
    as_user(USER_ALPHA)
    resp = api.post(f"/characters/npcs/{TP_FROM}/teleport", json={"link_id": 1})
    assert resp.status_code == 200, resp.text
    assert resp.json()["law_encounter"] is None


def test_teleport_refused_while_in_encounter(api, teleport_world):
    set_wanted(teleport_world, ALPHA, R_OST, 150)
    make_encounter(teleport_world, location_id=L_POST)
    exec_(teleport_world, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_MARKET, c=ALPHA)
    as_user(USER_ALPHA)
    resp = api.post(f"/characters/npcs/{TP_FROM}/teleport", json={"link_id": 1})
    assert resp.status_code == 409 and "стражей" in resp.json()["detail"]


def test_admin_move_does_not_evaluate_entry(law_world):
    """The home scroll and the admin move both write through apply_admin_move: never an encounter (decision 4)."""
    set_wanted(law_world, ALPHA, R_OST, 150)
    db = law_world()
    try:
        crud.apply_admin_move(db, character_id=ALPHA, from_location_id=L_MARKET, from_location_name="Рынок",
                              to_location_id=L_POST, to_location_name="Застава", event_type="home_teleport",
                              description="Свиток")
    finally:
        db.close()
    row = char_row(law_world, ALPHA)
    assert row.current_location_id == L_POST and row.law_encounter_id is None
    assert q(law_world, "SELECT COUNT(*) FROM law_encounters") == 0

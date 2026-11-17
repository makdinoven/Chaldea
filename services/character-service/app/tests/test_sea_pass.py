"""FEAT-213 QA (T7): the sea pass of the character-service scheduler (features/FEAT-213 §3.8–3.10).

* the claim / throttle on ``sea_settings``, the pass runs with the economy tick switched off, missing tables, one
  failing ship never blocks the others;
* departure (trip k = trip_no + 1): ticket holders sail, unentitled players are put ashore (no consequences) with the
  law entry check ``voyage`` and the LS cleanup, sailors need a post on the deck after the hire (``post_floor_id``) of
  the plain length, stowaways roll the crew's notice (stealth / mask / fame, ``law_crud.detection_rng``) — caught → the
  ``stowaway`` crime in the port's region (reported or masked + suspicion, idempotent key) and put ashore; tickets of
  holders not aboard burn, sailor / stowaway attempts expire; players in a battle are never moved; gathering cancelled;
  no path → stays docked with ``blocked_reason``;
* zone stepping with the offline catch-up, arrival (passes completed, Captain to the port, notices), the next
  departure puts the riders without a new pass ashore, a ticket bought at sea carries on;
* an invalid next stop is skipped; no valid stop → safe landing (refunds, fallbacks to any stop / the start location);
  the deck vanished → safe landing once; Captain placement (reverting manual moves; dead / in battle untouched).
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

import econ_scheduler
import econ_tick
import law_core
import law_crud
import law_notify
import models
import sea_core
import sea_crud
import sea_pass
from tests.law_world import set_wanted
from tests.sea_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, CAPTAIN, CAPTAIN2, DECK, DECK2, GAMMA, LAND, P_A, P_B, P_C, R_A, START, USER_ALPHA, USER_BETA,
    Z1, Z2, Z3, Z4, Z5, FixedRng, add_pass, api, buy, depart, exec_, gold, law_world, loc, make_ship, money_total,
    now, passes, place, post, q, rep_world, rows, run_ship, sea, sea_logs, sea_payloads, set_ship, ship,
)
from tests.shadow_world import give_mask, set_attrs, set_renown


def _status(sea, pass_id):
    return q(sea, "SELECT status FROM sea_passes WHERE id = :p", p=pass_id)


def _events(stub, event):
    return [p for p in sea_payloads(stub) if p["ws_data"].get("event") == event]


def _crimes(sea, character_id=ALPHA):
    return rows(sea, "SELECT crime_type, region_id, location_id, wanted_points, status, event_key, masked "
                     "FROM law_crimes WHERE character_id = :c ORDER BY id", c=character_id)


def _wanted(sea, character_id, region_id):
    return int(q(sea, "SELECT COALESCE(MAX(value), 0) FROM character_wanted WHERE character_id = :c "
                      "AND region_id = :r", c=character_id, r=region_id) or 0)


def _rng(monkeypatch, value):
    rng = FixedRng(value)
    monkeypatch.setattr(law_crud, "detection_rng", lambda: rng)
    return rng


def _in_battle(sea, character_id, battle_id=1):
    exec_(sea, "INSERT INTO battles (id, status) VALUES (:b, 'in_progress')", b=battle_id)
    exec_(sea, "INSERT INTO battle_participants (battle_id, character_id) VALUES (:b, :c)", b=battle_id, c=character_id)


# =============================================================================================== claim / run_pass

def test_claim_throttles_for_the_run_interval(sea):
    t = now()
    db = sea()
    try:
        assert sea_pass.claim_run(db, t) is True
        assert sea_pass.claim_run(db, t + timedelta(seconds=10)) is False
        assert sea_pass.claim_run(db, t + timedelta(seconds=sea_pass.RUN_INTERVAL_SECONDS)) is True
    finally:
        db.close()


@pytest.mark.parametrize("sql", ["DROP TABLE sea_settings", "DELETE FROM sea_settings"])
def test_claim_without_the_settings_table_or_row_is_false(sea, sql):
    exec_(sea, sql)
    db = sea()
    try:
        assert sea_pass.claim_run(db, now()) is False
    finally:
        db.close()


def test_run_pass_is_throttled_unless_forced(sea):
    t = sea.t0 + timedelta(minutes=31)
    first = sea_pass.run_pass(sea, now=t)
    assert first["ships"] == 1 and first["departed"] == 1
    assert sea_pass.run_pass(sea, now=t + timedelta(seconds=5)) is None
    assert sea_pass.run_pass(sea, now=t + timedelta(seconds=5), force=True)["ships"] == 1


def test_run_pass_without_the_sea_tables_is_none(sea, monkeypatch):
    monkeypatch.setitem(sea_crud._available_cache, "ok", False)
    exec_(sea, "DROP TABLE sea_passes")
    assert sea_pass.run_pass(sea, now=now(), force=True) is None


def test_one_failing_ship_does_not_block_the_others(sea, monkeypatch):
    other = make_ship(sea, name="Чайка", deck=DECK2, captain=CAPTAIN2, stops=(P_B, P_A), when=sea.t0)
    real = sea_pass.process_ship

    def flaky(db, ship_id, when):
        if int(ship_id) == sea.ship_id:
            raise RuntimeError("boom")
        return real(db, ship_id, when)

    monkeypatch.setattr(sea_pass, "process_ship", flaky)
    stats = sea_pass.run_pass(sea, now=sea.t0 + timedelta(minutes=31), force=True)
    assert stats["failed"] == 1 and stats["departed"] == 1
    assert ship(sea).status == "docked" and ship(sea, other).status == "sailing"


def test_ships_sail_with_the_economy_tick_switched_off(sea, monkeypatch):
    for name in ("run_reputation_decay", "run_law_pass", "run_faction_pass", "run_caravan_pass"):
        monkeypatch.setattr(econ_scheduler, name, lambda factory: None)
    tick = MagicMock(name="run_tick")
    monkeypatch.setattr(econ_tick, "run_tick", tick)
    db = sea()
    try:
        db.add(models.EconSimSettings(id=1, tick_enabled=False, params={}))
        db.commit()
    finally:
        db.close()
    set_ship(sea, departs_at=now() - timedelta(minutes=1))
    assert econ_scheduler.run_scheduled_once(sea) is None
    tick.assert_not_called()
    assert ship(sea).status == "sailing" and ship(sea).trip_no == 1


# =============================================================================================== departure

def test_departure_state_and_captain_on_deck(sea, stub_law_notify_send):
    buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    out, t = depart(sea)
    s = ship(sea)
    assert out.events[0] == sea_pass.EV_DEPARTED
    assert (s.status, s.trip_no, s.stop_index, s.next_stop_index, s.direction) == ("sailing", 1, 0, 1, 1)
    assert (s.next_port_id, s.leg_path, s.leg_pos, s.current_zone_id) == (P_B, [Z1, Z2, Z3], 0, Z1)
    assert s.next_zone_at == t + timedelta(minutes=10)
    assert (s.docked_port_id, s.departs_at, s.last_port_id, s.blocked_reason) == (None, None, P_A, None)
    assert loc(sea, CAPTAIN) == DECK and loc(sea, ALPHA) == DECK
    (p,) = passes(sea)
    assert p.status == "active"
    (n,) = _events(stub_law_notify_send, sea_pass.EV_DEPARTED)
    assert n["target_value"] == USER_ALPHA and "Оазис" in n["message"] and "30 мин" in n["message"]


def test_unentitled_player_is_put_ashore_without_consequences(sea, stub_law_notify_send):
    place(sea, ALPHA, DECK)
    out, _ = depart(sea)
    assert loc(sea, ALPHA) == P_A and ship(sea).status == "sailing"
    assert [a.character_id for a in out.ashore] == [ALPHA]
    sea.left.assert_called_once_with(ALPHA, DECK)
    assert _crimes(sea) == [] and _wanted(sea, ALPHA, R_A) == 0
    (n,) = _events(stub_law_notify_send, sea_pass.EV_ASHORE)
    assert "нет билета" in n["message"]
    assert any("высадили" in m for m in sea_logs(sea, ALPHA))
    assert q(sea, "SELECT house_room_id FROM characters WHERE id = :c", c=ALPHA) is None


def test_ticket_holder_not_aboard_burns_without_refund(sea, stub_law_notify_send):
    pid = buy(sea, BETA)
    depart(sea)
    assert _status(sea, pid) == "burnt" and gold(sea, BETA) == 975
    assert q(sea, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'sea_refund'") == 0
    (n,) = _events(stub_law_notify_send, sea_pass.EV_BURNT)
    assert n["target_value"] == USER_BETA and "сгорел" in n["message"]


@pytest.mark.parametrize("kind", ["sailor", "stowaway"])
def test_sailor_and_stowaway_not_aboard_expire(sea, kind):
    pid = add_pass(sea, BETA, kind=kind)
    depart(sea)
    assert _status(sea, pid) == "expired"


def test_player_in_a_battle_is_never_moved(sea):
    place(sea, ALPHA, DECK)
    _in_battle(sea, ALPHA)
    out, _ = depart(sea)
    assert loc(sea, ALPHA) == DECK and out.ashore == [] and ship(sea).status == "sailing"


def test_gathering_player_put_ashore_gets_the_gathering_cancelled(sea):
    place(sea, ALPHA, DECK)
    exec_(sea, "INSERT INTO gathering_sessions (character_id, status) VALUES (:c, 'active')", c=ALPHA)
    depart(sea)
    assert loc(sea, ALPHA) == P_A
    sea.cancel.assert_awaited_once_with(ALPHA, reason=sea_pass.GATHER_CANCEL_REASON)


def test_put_ashore_runs_the_law_entry_check_with_the_voyage_source(sea):
    place(sea, 60, P_A)                          # a guard of region 10 stands in the port
    set_wanted(sea, ALPHA, R_A, 200)
    place(sea, ALPHA, DECK)
    depart(sea)
    enc = rows(sea, "SELECT source, location_id, from_location_id FROM law_encounters WHERE character_id = :c",
               c=ALPHA)
    assert enc == [(law_core.SOURCE_VOYAGE, P_A, DECK)]
    assert q(sea, "SELECT law_encounter_id FROM characters WHERE id = :c", c=ALPHA) is not None


def test_no_path_keeps_the_ship_docked(sea):
    exec_(sea, "DELETE FROM LocationNeighbors WHERE neighbor_id = :z OR location_id = :z", z=Z3)
    place(sea, ALPHA, DECK)
    before = ship(sea).departs_at
    out, _ = depart(sea)
    s = ship(sea)
    assert (s.status, s.blocked_reason, s.departs_at, s.trip_no) == ("docked", sea_core.BLOCKED_NO_PATH, before, 0)
    assert loc(sea, ALPHA) == DECK and out.ashore == []


# ---------------------------------------------------------------------------------------------- sailors

@pytest.mark.parametrize("content, ok", [
    ("я" * 800, True),
    ("<p>" + "я" * 799 + "</p>" + "<b></b>" * 50, False),      # long raw HTML, 799 plain characters
    ("<p>" + "я" * 800 + "</p>", True),
])
def test_sailor_needs_a_post_of_the_plain_length(sea, stub_law_notify_send, content, ok):
    pid = add_pass(sea, ALPHA, kind="sailor", post_floor_id=0)
    place(sea, ALPHA, DECK)
    post(sea, ALPHA, DECK, content)
    depart(sea)
    if ok:
        assert loc(sea, ALPHA) == DECK and _status(sea, pid) == "active"
    else:
        assert loc(sea, ALPHA) == P_A and _status(sea, pid) == "ashore"
        (n,) = _events(stub_law_notify_send, sea_pass.EV_SAILOR_ASHORE)
        assert "800" in n["message"]


def test_sailor_posts_before_the_hire_or_elsewhere_do_not_count(sea):
    old = post(sea, ALPHA, DECK, "я" * 900)
    post(sea, ALPHA, LAND, "я" * 900)
    pid = add_pass(sea, ALPHA, kind="sailor", post_floor_id=old)
    place(sea, ALPHA, DECK)
    depart(sea)
    assert loc(sea, ALPHA) == P_A and _status(sea, pid) == "ashore"
    assert _crimes(sea) == []                    # not working = put ashore, no crime (user decision)


def test_sailor_min_chars_follows_the_settings(sea):
    exec_(sea, "UPDATE sea_settings SET sailor_post_min_chars = 300")
    pid = add_pass(sea, ALPHA, kind="sailor", post_floor_id=0)
    place(sea, ALPHA, DECK)
    post(sea, ALPHA, DECK, "я" * 300)
    depart(sea)
    assert loc(sea, ALPHA) == DECK and _status(sea, pid) == "active"


# ---------------------------------------------------------------------------------------------- stowaways

def test_stowaway_caught_is_a_reported_crime_in_the_port_region(sea, stub_law_notify_send):
    pid = add_pass(sea, ALPHA, kind="stowaway")
    place(sea, ALPHA, DECK)                      # law_world rng: 0.00 -> always noticed
    depart(sea)
    assert loc(sea, ALPHA) == P_A and _status(sea, pid) == "caught"
    assert _crimes(sea) == [("stowaway", R_A, P_A, 50, "reported", f"law:stowaway:{pid}", 0)]
    assert _wanted(sea, ALPHA, R_A) > 0
    (n,) = _events(stub_law_notify_send, sea_pass.EV_CAUGHT)
    assert "поймала" in n["message"]
    assert sea_payloads(stub_law_notify_send, law_notify.WS_WANTED)


def test_stowaway_not_caught_sails_without_a_trace(sea, monkeypatch):
    rng = _rng(monkeypatch, 0.99)
    pid = add_pass(sea, ALPHA, kind="stowaway")
    place(sea, ALPHA, DECK)
    depart(sea)
    assert rng.calls == 1
    assert loc(sea, ALPHA) == DECK and _status(sea, pid) == "active"
    assert _crimes(sea) == [] and _wanted(sea, ALPHA, R_A) == 0


def test_masked_stowaway_caught_is_a_masked_crime_plus_suspicion(sea, stub_law_notify_send):
    give_mask(sea, ALPHA)
    pid = add_pass(sea, ALPHA, kind="stowaway")
    place(sea, ALPHA, DECK)
    depart(sea)
    (crime,) = _crimes(sea)
    assert crime[:6] == ("stowaway", R_A, P_A, 50, "masked", f"law:stowaway:{pid}") and crime[6] == 1
    assert _wanted(sea, ALPHA, R_A) == 0
    assert int(q(sea, "SELECT value FROM region_suspicion WHERE region_id = :r", r=R_A)) == 20
    assert sea_payloads(stub_law_notify_send, law_notify.WS_MASKED)
    assert loc(sea, ALPHA) == P_A


def test_stowaway_wanted_points_follow_the_settings(sea):
    exec_(sea, "UPDATE sea_settings SET stowaway_wanted_points = 120")
    add_pass(sea, ALPHA, kind="stowaway")
    place(sea, ALPHA, DECK)
    depart(sea)
    assert _crimes(sea)[0][3] == 120


def test_stowaway_crime_key_is_idempotent(sea):
    pid = add_pass(sea, ALPHA, kind="stowaway")
    roll = sea_pass.StowawayRoll(True, False, Decimal("60.00"), Decimal("1.00"), Decimal(0))
    for _ in range(2):
        db = sea()
        try:
            row = db.get(models.SeaPass, pid)
            sea_pass.register_stowaway_crime(db, row, P_A, roll, 50, now(), sea_pass.ShipOutcome(sea.ship_id))
            db.commit()
        finally:
            db.close()
    assert len(_crimes(sea)) == 1


def test_stowaway_crime_without_a_port_region_is_skipped(sea):
    pid = add_pass(sea, ALPHA, kind="stowaway")
    roll = sea_pass.StowawayRoll(True, False, Decimal("60.00"), Decimal("1.00"), Decimal(0))
    db = sea()
    try:
        sea_pass.register_stowaway_crime(db, db.get(models.SeaPass, pid), START, roll, 50, now(),
                                         sea_pass.ShipOutcome(sea.ship_id))
        db.commit()
    finally:
        db.close()
    assert _crimes(sea) == []


def _roll(sea, base=60):
    db = sea()
    try:
        return sea_pass.stowaway_roll(db, ALPHA, base, law_crud.load_settings(db))
    finally:
        db.close()


def test_stowaway_chance_base_stealth_fame_and_mask(sea, monkeypatch):
    _rng(monkeypatch, 0.99)
    assert _roll(sea).chance == Decimal("60.00")
    set_attrs(sea, ALPHA, stealth=40)                    # 40 × 0.5 % = 20 % reduction
    r = _roll(sea)
    assert (r.chance, r.reduction_pct, r.masked) == (Decimal("48.00"), Decimal("20.00"), False)
    set_attrs(sea, ALPHA, stealth=0)
    set_renown(sea, ALPHA, fame=600)                     # «Знаменитый»: +10 %
    assert _roll(sea).chance == Decimal("66.00")
    give_mask(sea, ALPHA)                                # a masked face: fame does not count
    r = _roll(sea)
    assert (r.chance, r.masked) == (Decimal("60.00"), True)


def test_stowaway_chance_is_clamped_to_the_law_detection_bounds(sea, monkeypatch):
    rng = _rng(monkeypatch, 0.04)
    r = _roll(sea, base=0)
    assert r.chance == Decimal("5.00") and r.caught is True and rng.calls == 1   # roll 4.00 < min 5 %
    set_renown(sea, ALPHA, fame=1600)
    assert _roll(sea, base=100).chance == Decimal("100.00")


# ---------------------------------------------------------------------------------------------- one right per trip

def test_the_best_right_wins_when_a_character_holds_several(sea, monkeypatch):
    rng = _rng(monkeypatch, 0.0)
    add_pass(sea, ALPHA, kind="stowaway")
    add_pass(sea, ALPHA, kind="ticket")
    place(sea, ALPHA, DECK)
    depart(sea)
    assert loc(sea, ALPHA) == DECK and rng.calls == 0 and _crimes(sea) == []


# =============================================================================================== stepping / arrival

def test_zone_stepping_then_arrival(sea, stub_law_notify_send):
    pid = buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    run_ship(sea, t + timedelta(minutes=10))
    assert (ship(sea).leg_pos, ship(sea).current_zone_id) == (1, Z2)
    run_ship(sea, t + timedelta(minutes=15))                         # not due yet
    assert ship(sea).leg_pos == 1
    run_ship(sea, t + timedelta(minutes=20))
    assert (ship(sea).leg_pos, ship(sea).current_zone_id) == (2, Z3)
    out = run_ship(sea, t + timedelta(minutes=30))
    s = ship(sea)
    assert sea_pass.EV_ARRIVED in out.events
    assert (s.status, s.stop_index, s.docked_port_id, s.current_zone_id, s.leg_path) == ("docked", 1, P_B, Z3, None)
    assert s.departs_at == t + timedelta(minutes=60) and s.next_zone_at is None and s.last_port_id == P_B
    assert loc(sea, CAPTAIN) == P_B and loc(sea, ALPHA) == DECK          # players leave by a post
    assert _status(sea, pid) == "completed"
    (n,) = _events(stub_law_notify_send, sea_pass.EV_ARRIVED)
    assert "Оазис" in n["message"] and "использован" in n["message"]


def test_arrival_does_not_ask_to_rebuy_when_the_next_leg_is_paid(sea, stub_law_notify_send):
    first = buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    second = buy(sea, ALPHA, to_trip=2, when=t + timedelta(minutes=1))   # next leg bought from the Captain at sea
    run_ship(sea, t + timedelta(minutes=30))
    assert _status(sea, first) == "completed" and _status(sea, second) == "active"
    (n,) = _events(stub_law_notify_send, sea_pass.EV_ARRIVED)
    assert "Оазис" in n["message"] and "использован" not in n["message"]


def test_offline_catch_up_arrives_in_one_pass(sea):
    _, t = depart(sea)
    out = run_ship(sea, t + timedelta(hours=5))
    assert out.events.count("zone") == 2 and sea_pass.EV_ARRIVED in out.events
    assert ship(sea).status == "docked" and ship(sea).departs_at == t + timedelta(hours=5, minutes=30)


def test_after_arrival_a_rider_without_a_new_pass_is_put_ashore_at_the_next_departure(sea):
    buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    run_ship(sea, t + timedelta(minutes=30))
    out, _ = depart(sea)
    assert loc(sea, ALPHA) == P_B and [a.character_id for a in out.ashore] == [ALPHA]
    assert ship(sea).trip_no == 2 and ship(sea).next_port_id == P_C


def test_a_ticket_bought_at_sea_carries_the_rider_on(sea):
    buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    second = buy(sea, ALPHA, to_trip=2)                               # from the Captain on deck
    run_ship(sea, t + timedelta(minutes=30))
    assert _status(sea, second) == "active"
    depart(sea)
    assert loc(sea, ALPHA) == DECK and ship(sea).trip_no == 2


def test_multi_stop_ticket_burns_when_the_holder_walks_off_midway(sea):
    pid = buy(sea, ALPHA, to_trip=2)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    run_ship(sea, t + timedelta(minutes=30))
    place(sea, ALPHA, P_B)
    depart(sea)
    assert _status(sea, pid) == "burnt"


def test_there_and_back_turns_at_the_end_of_the_line(sea):
    _, t = depart(sea)
    for _ in range(3):
        run_ship(sea, t + timedelta(hours=5))
        _, t = depart(sea)
    s = ship(sea)
    assert (s.trip_no, s.stop_index, s.next_stop_index, s.direction, s.next_port_id) == (4, 1, 0, -1, P_A)
    assert s.leg_path == [Z3, Z2, Z1]


# =============================================================================================== broken data

def test_invalid_next_stop_is_skipped(sea, stub_law_notify_send):
    pid = buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    exec_(sea, "UPDATE Locations SET is_port = 0 WHERE id = :p", p=P_B)
    out = run_ship(sea, t + timedelta(minutes=30))
    s = ship(sea)
    assert sea_pass.EV_REROUTED in out.events and s.status == "sailing"
    assert (s.next_stop_index, s.next_port_id, s.leg_path, s.leg_pos, s.current_zone_id) == (2, P_C, [Z3, Z4], 0, Z3)
    assert _events(stub_law_notify_send, sea_pass.EV_REROUTED)
    run_ship(sea, t + timedelta(minutes=50))
    s = ship(sea)
    assert (s.status, s.docked_port_id, s.stop_index) == ("docked", P_C, 2)
    assert _status(sea, pid) == "completed" and loc(sea, CAPTAIN) == P_C


def test_invalid_stops_are_skipped_at_departure_too(sea):
    exec_(sea, "UPDATE Locations SET port_sea_zone_id = NULL WHERE id = :p", p=P_B)
    depart(sea)
    s = ship(sea)
    assert (s.status, s.next_stop_index, s.next_port_id) == ("sailing", 2, P_C)
    assert s.leg_path == [Z1, Z2, Z3, Z4]


def test_no_valid_stop_at_sea_is_a_safe_landing_with_refunds(sea):
    buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    place(sea, BETA, DECK)
    future = buy(sea, BETA, to_trip=2)                               # not started yet -> refunded
    assert gold(sea, BETA) < 1000
    total = money_total(sea)
    exec_(sea, "UPDATE Locations SET is_port = 0 WHERE id IN (103, 200, 110)")
    out = run_ship(sea, t + timedelta(minutes=30))
    s = ship(sea)
    assert sea_pass.EV_SAFE_LANDING in out.events
    assert (s.is_active, s.blocked_reason, s.status, s.docked_port_id, s.stop_index) == \
        (False, sea_core.BLOCKED_NO_VALID_STOP, "docked", P_A, 0)
    assert loc(sea, ALPHA) == P_A and loc(sea, BETA) == P_A and loc(sea, CAPTAIN) == P_A
    assert _status(sea, future) == "refunded" and gold(sea, BETA) == 1000 and money_total(sea) == total
    assert {p.status for p in passes(sea, character_id=ALPHA)} == {"completed"}
    assert q(sea, "SELECT COUNT(*) FROM sea_passes WHERE status = 'active'") == 0


def test_safe_landing_with_an_empty_deck_keeps_refunded_passes_refunded(sea):
    _, t = depart(sea)
    future = add_pass(sea, BETA, first=2, last=2, from_port=P_B, to_port=P_C)
    exec_(sea, "UPDATE Locations SET is_port = 0 WHERE id IN (103, 200, 110)")
    run_ship(sea, t + timedelta(minutes=30))
    assert _status(sea, future) == "refunded"


def test_safe_landing_falls_back_to_the_start_location(sea):
    buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    exec_(sea, "DELETE FROM Locations WHERE id IN (103, 200, 110)")
    run_ship(sea, t + timedelta(minutes=30))
    assert loc(sea, ALPHA) == START and ship(sea).is_active is False
    assert q(sea, "SELECT COUNT(*) FROM law_encounters") == 0        # a fallback target: no law check


def test_safe_landing_falls_back_to_any_existing_stop(sea):
    buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    exec_(sea, "UPDATE Locations SET is_port = 0 WHERE id IN (200, 110)")
    exec_(sea, "DELETE FROM Locations WHERE id = :p", p=P_A)
    run_ship(sea, t + timedelta(minutes=30))
    assert loc(sea, ALPHA) == P_B


def test_missing_deck_is_a_safe_landing_once(sea):
    pid = add_pass(sea, BETA, first=1, last=1)
    place(sea, ALPHA, DECK)
    exec_(sea, "DELETE FROM Locations WHERE id = :d", d=DECK)
    out = run_ship(sea, sea.t0 + timedelta(minutes=1))
    s = ship(sea)
    assert sea_pass.EV_SAFE_LANDING in out.events
    assert (s.is_active, s.blocked_reason, s.status) == (False, sea_core.BLOCKED_NO_DECK, "docked")
    assert loc(sea, ALPHA) == P_A and _status(sea, pid) == "refunded"
    sea.left.assert_called_once_with(ALPHA, DECK)
    again = run_ship(sea, sea.t0 + timedelta(hours=2))
    assert sea_pass.EV_SAFE_LANDING not in again.events and sea_pass.EV_DEPARTED not in again.events


# =============================================================================================== Captain placement

def test_captain_moved_by_hand_is_put_back(sea):
    place(sea, CAPTAIN, LAND)
    out = run_ship(sea, sea.t0 + timedelta(minutes=1))
    assert "captain_moved" in out.events and loc(sea, CAPTAIN) == P_A
    depart(sea)
    place(sea, CAPTAIN, P_A)
    run_ship(sea, ship(sea).next_zone_at - timedelta(minutes=1))
    assert loc(sea, CAPTAIN) == DECK


def test_dead_captain_or_captain_in_battle_is_not_moved(sea):
    place(sea, CAPTAIN, LAND)
    exec_(sea, "UPDATE characters SET npc_status = 'dead' WHERE id = :c", c=CAPTAIN)
    run_ship(sea, sea.t0 + timedelta(minutes=1))
    assert loc(sea, CAPTAIN) == LAND
    exec_(sea, "UPDATE characters SET npc_status = 'alive' WHERE id = :c", c=CAPTAIN)
    _in_battle(sea, CAPTAIN)
    out = run_ship(sea, sea.t0 + timedelta(minutes=1))
    assert loc(sea, CAPTAIN) == LAND and "captain_moved" not in out.events


def test_ship_without_a_captain_still_sails(sea):
    set_ship(sea, captain_npc_id=None)
    place(sea, CAPTAIN, LAND)
    depart(sea)
    assert ship(sea).status == "sailing" and loc(sea, CAPTAIN) == LAND


def test_switched_off_ship_never_departs(sea):
    set_ship(sea, is_active=False)
    out = run_ship(sea, sea.t0 + timedelta(hours=3))
    assert ship(sea).status == "docked" and sea_pass.EV_DEPARTED not in out.events


def test_after_commit_survives_a_failing_gathering_cancel(sea):
    place(sea, ALPHA, DECK)
    exec_(sea, "INSERT INTO gathering_sessions (character_id, status) VALUES (:c, 'active')", c=ALPHA)
    sea.cancel.side_effect = RuntimeError("LS down")
    depart(sea)
    assert loc(sea, ALPHA) == P_A
    sea.left.assert_called_once_with(ALPHA, DECK)

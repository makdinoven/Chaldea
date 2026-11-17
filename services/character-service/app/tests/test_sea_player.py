"""FEAT-213 QA (T7): the player side of the ships in character-service (features/FEAT-213 §3.5–3.7, §3.11, §3.13).

* S1–S5: auth (401 / 403 owner), the dialogue gate (403 / 503, mocked) and the reputation tier on S2 / S3 only, the
  Captain context (404 unknown / not a Captain / dead / knocked out / without a ship, 400 not next to him), the view
  (destinations, fares base + per zone, ETAs, seats, sailor slots, stowaway option, own passes);
* tickets: seats per trip, ``to_trip`` bounds, double purchase = 409 + one charge, 402 shape without a charge, the
  fare to the departure port's region treasury + the country tax (like the teleport), a ticket bought on deck at sea
  starts with the next trip; sailor job (slots, hiring off, post floor); stowaway attempt (presence, at sea, twice);
* the deck header (nearby ships docked / at sea, passengers, own passes);
* ``update_location`` (G1 / G2): boarding with / without a right, after departure, switched-off ship, from another
  port, leaving docked / at sea / to a wrong place, a sea zone destination, the ship → character lock order race;
* G2 / G3: admin move into a zone (refused) / onto a deck (allowed), home teleport into a deck / zone (refused) and
  off a deck (allowed), ``execute_teleport`` / ``create_teleport_link`` with a deck / zone target;
* deploy skew: the sea API answers 503 without the tables; security cases.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import crud
import econ_core
import locations_client
import models
import sea_core
import sea_crud
from auth_http import get_current_user_via_http
from main import app
from tests.sea_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, CAPTAIN, CAPTAIN2, C_A, C_B, DECK, DECK2, GAMMA, INTERNAL, LAND, P_A, P_B, P_C, R_A, R_B,
    USER_ALPHA, USER_BETA, Z1, Z2, Z3, add_pass, api, as_user, buy, client, exec_, gold, law_world, loc, make_ship,
    money_total, now, op, passes, place, postings, q, rep_world, rows, sea, sea_logs, sea_payloads, set_gold,
    set_ship, ship, treasury,
)

VIEW = f"/characters/sea/captain/{CAPTAIN}"


def _tickets_url(ship_id):
    return f"/characters/sea/ships/{ship_id}/tickets"


def _view(c, character=ALPHA, npc=CAPTAIN):
    return c.get(f"/characters/sea/captain/{npc}", params={"character_id": character})


def _buy(c, sea, character=ALPHA, to_trip=1, npc=CAPTAIN, ship_id=None):
    return c.post(_tickets_url(ship_id or sea.ship_id),
                  json={"character_id": character, "npc_id": npc, "to_trip": to_trip})


def _hire(c, sea, character=ALPHA, npc=CAPTAIN):
    return c.post(f"/characters/sea/ships/{sea.ship_id}/sailor", json={"character_id": character, "npc_id": npc})


def _sneak(c, sea, character=ALPHA, ship_id=None):
    return c.post(f"/characters/sea/ships/{ship_id or sea.ship_id}/stowaway", json={"character_id": character})


def _deck(c, location_id=DECK, character=ALPHA):
    return c.get(f"/characters/sea/decks/{location_id}", params={"character_id": character})


def _move(c, character, dest):
    return c.put(f"/characters/internal/{character}/update_location", json={"new_location_id": dest},
                 headers=INTERNAL)


def _sail(sea, trip_no=1, leg_pos=0, zone=Z1, next_stop=1, next_port=P_B, ship_id=None):
    """Put the ship at sea on trip ``trip_no`` (state as the sea pass leaves it) with the Captain on deck."""
    set_ship(sea, ship_id, status=sea_core.STATUS_SAILING, trip_no=trip_no, stop_index=next_stop - 1,
             next_stop_index=next_stop, next_port_id=next_port, docked_port_id=None, departs_at=None,
             leg_path=[Z1, Z2, Z3], leg_pos=leg_pos, current_zone_id=zone, next_zone_at=now() + timedelta(minutes=5))
    place(sea, CAPTAIN, DECK)


@pytest.fixture
def alpha(client):
    as_user(USER_ALPHA)
    return client


# =============================================================================================== S1 view

def test_view_needs_a_token(client):
    assert _view(client).status_code == 401


def test_view_of_someone_elses_character_is_403(client):
    as_user(USER_BETA)
    r = _view(client, ALPHA)
    assert (r.status_code, r.json()["detail"]) == (403, sea_crud.MSG_NOT_OWNER)


@pytest.mark.parametrize("npc", [999, 50])     # unknown / a merchant
def test_view_unknown_or_not_a_captain_is_404(alpha, npc):
    r = _view(alpha, npc=npc)
    assert (r.status_code, r.json()["detail"]) == (404, sea_crud.MSG_CAPTAIN_NOT_FOUND)


def test_view_dead_or_knocked_out_captain_is_404(alpha, sea):
    exec_(sea, "UPDATE characters SET npc_status = 'dead' WHERE id = :c", c=CAPTAIN)
    assert _view(alpha).status_code == 404
    exec_(sea, "UPDATE characters SET npc_status = 'alive', unconscious_until = :u WHERE id = :c",
          u=now() + timedelta(hours=1), c=CAPTAIN)
    assert _view(alpha).status_code == 404


def test_view_captain_without_a_ship_is_404(alpha, sea):
    place(sea, ALPHA, P_B)
    r = _view(alpha, npc=CAPTAIN2)
    assert (r.status_code, r.json()["detail"]) == (404, sea_crud.MSG_CAPTAIN_NO_SHIP)


def test_view_away_from_the_captain_is_400(alpha, sea):
    place(sea, ALPHA, LAND)
    r = _view(alpha)
    assert (r.status_code, r.json()["detail"]) == (400, sea_crud.MSG_NOT_AT_CAPTAIN)


def test_view_needs_no_dialogue_gate(alpha, sea):
    assert _view(alpha).status_code == 200
    sea.gate.assert_not_called()


def test_view_lists_destinations_with_fares_etas_and_seats(alpha, sea):
    r = _view(alpha)
    assert r.status_code == 200, r.text
    body = r.json()
    s = ship(sea)
    assert body["npc_id"] == CAPTAIN and body["balance"] == 1000
    assert body["ship"]["status"] == "docked" and body["ship"]["docked_port"] == {"id": P_A, "name": "Тракт"}
    assert body["ship"]["current_zone"] == {"id": Z1, "name": "Пролив Ветров", "sea_name": "Море Эйдонэи"}
    assert body["ship"]["captain"]["id"] == CAPTAIN
    assert [st["port_id"] for st in body["ship"]["stops"]] == [P_A, P_B, P_C]
    d1, d2 = body["destinations"]
    assert (d1["to_trip"], d1["port_id"], d1["zones"], d1["fare"], d1["seats_left"], d1["can_buy"]) == \
        (1, P_B, 3, 25, 2, True)
    assert (d1["region_name"], d1["country_name"]) == ("Дюны", "Пустошь")
    assert (d2["to_trip"], d2["port_id"], d2["zones"], d2["fare"]) == (2, P_C, 5, 35)
    assert d1["eta"].startswith((s.departs_at + timedelta(minutes=30)).isoformat()[:16])
    assert d2["eta"].startswith((s.departs_at + timedelta(minutes=30 + 30 + 20)).isoformat()[:16])
    assert body["sailor"] == {"slots_left": 1, "min_chars": 800, "can_hire": True, "reason": None}
    assert body["stowaway"] == {"can_try": True, "reason": None}
    assert body["my_passes"] == []


def test_view_reasons_when_full_idle_or_already_aboard(alpha, sea):
    add_pass(sea, BETA, first=1, last=1)
    add_pass(sea, GAMMA, first=1, last=2)
    body = _view(alpha).json()
    assert [d["seats_left"] for d in body["destinations"]] == [0, 0]
    assert {d["reason"] for d in body["destinations"]} == {sea_crud.MSG_NO_SEATS}
    add_pass(sea, ALPHA, kind="sailor")
    body = _view(alpha).json()
    assert body["destinations"][0]["reason"] == sea_crud.MSG_ALREADY_PASS
    assert body["sailor"]["can_hire"] is False and body["stowaway"]["reason"] == sea_crud.MSG_ALREADY_PASS
    assert [p["kind"] for p in body["my_passes"]] == ["sailor"] and body["my_passes"][0]["valid_now"] is True
    set_ship(sea, is_active=False)
    body = _view(alpha).json()
    assert body["destinations"][0]["reason"] == sea_crud.MSG_SHIP_IDLE


# =============================================================================================== S2 tickets

def test_ticket_needs_a_token_and_the_owner(client, sea):
    assert _buy(client, sea).status_code == 401
    as_user(USER_BETA)
    assert _buy(client, sea).status_code == 403
    assert passes(sea) == [] and gold(sea, ALPHA) == 1000


def test_ticket_dialogue_gate_closed_is_403_and_changes_nothing(alpha, sea):
    sea.gate.return_value = False
    r = _buy(alpha, sea)
    assert (r.status_code, r.json()["detail"]) == (403, sea_crud.MSG_GATE_CLOSED)
    sea.gate.assert_awaited_once_with(ALPHA, P_A, CAPTAIN)
    assert passes(sea) == [] and gold(sea, ALPHA) == 1000


def test_ticket_dialogue_gate_unavailable_is_503(alpha, sea):
    sea.gate.side_effect = locations_client.GateUnavailable("down")
    r = _buy(alpha, sea)
    assert (r.status_code, r.json()["detail"]) == (503, sea_crud.MSG_GATE_UNAVAILABLE)
    assert passes(sea) == []


def test_ticket_reputation_tier_gate_is_403(alpha, sea):
    exec_(sea, "UPDATE characters SET reputation_min_tier = 'trusted' WHERE id = :c", c=CAPTAIN)
    r = _buy(alpha, sea)
    assert r.status_code == 403 and "репутация" in r.json()["detail"].lower()
    assert passes(sea) == [] and gold(sea, ALPHA) == 1000


def test_ticket_happy_path_charges_the_departure_region_with_the_country_tax(alpha, sea, stub_law_notify_send):
    total = money_total(sea)
    r = _buy(alpha, sea)
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["kind"], body["status"], body["first_trip"], body["last_trip"], body["fare"]) == \
        ("ticket", "active", 1, 1, 25)
    assert (body["from_port_id"], body["to_port_id"], body["from_name"], body["to_name"]) == (P_A, P_B, "Тракт", "Оазис")
    assert body["valid_now"] is True
    assert gold(sea, ALPHA) == 975
    region, country = treasury(sea, "region_treasury", R_A), treasury(sea, "country_treasury", C_A)
    assert region + country == 25 and country > 0                 # automatic region -> country tax, like the teleport
    (p,) = passes(sea)
    assert op(sea, p.fare_op_id) == (econ_core.OP_SEA_FARE, f"sea_fare:{p.id}")
    legs = postings(sea, p.fare_op_id)
    assert legs[0][:5] == ("character", ALPHA, "region_treasury", R_A, 25)
    assert ("region_treasury", R_A, "country_treasury", C_A, country, econ_core.LEG_TAX) in legs
    assert money_total(sea) == total
    assert any("Билет" in m for m in sea_logs(sea, ALPHA))
    (n,) = sea_payloads(stub_law_notify_send)
    assert n["target_value"] == USER_ALPHA and n["ws_data"]["event"] == "ticket"


def test_ticket_over_two_stops(alpha, sea):
    r = _buy(alpha, sea, to_trip=2)
    assert r.status_code == 201, r.text
    assert (r.json()["last_trip"], r.json()["to_port_id"], r.json()["fare"]) == (2, P_C, 35)
    assert gold(sea, ALPHA) == 965


def test_double_purchase_is_409_and_charged_once(alpha, sea):
    assert _buy(alpha, sea).status_code == 201
    r = _buy(alpha, sea, to_trip=2)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_ALREADY_PASS)
    assert len(passes(sea)) == 1 and gold(sea, ALPHA) == 975
    assert q(sea, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'sea_fare'") == 1


def test_insufficient_money_is_402_with_the_shape_and_no_charge(alpha, sea):
    set_gold(sea, ALPHA, 10)
    total = money_total(sea)
    r = _buy(alpha, sea)
    assert r.status_code == 402
    detail = r.json()["detail"]
    assert detail["error"] == "insufficient_gold" and detail["required"] == 25 and detail["balance"] == 10
    assert detail["message"].startswith("Недостаточно")
    assert passes(sea) == [] and gold(sea, ALPHA) == 10 and money_total(sea) == total


@pytest.mark.parametrize("to_trip", [3, 99])
def test_ticket_beyond_the_next_stops_is_409(alpha, sea, to_trip):
    r = _buy(alpha, sea, to_trip=to_trip)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_BAD_TRIP)


def test_ticket_trip_zero_is_a_validation_error(alpha, sea):
    assert _buy(alpha, sea, to_trip=0).status_code == 422


def test_seats_are_counted_over_every_covered_trip(alpha, sea):
    set_ship(sea, capacity=1)
    add_pass(sea, BETA, first=1, last=1)
    r = _buy(alpha, sea, to_trip=2)                       # trip 1 is full
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_NO_SEATS)
    assert gold(sea, ALPHA) == 1000


def test_sailors_and_stowaways_take_no_ticket_seats(alpha, sea):
    set_ship(sea, capacity=1)
    add_pass(sea, BETA, kind="sailor")
    add_pass(sea, GAMMA, kind="stowaway")
    assert _buy(alpha, sea).status_code == 201


def test_ticket_refusals_idle_lock_other_ship(alpha, sea):
    set_ship(sea, is_active=False)
    assert _buy(alpha, sea).json()["detail"] == sea_crud.MSG_SHIP_IDLE
    set_ship(sea, is_active=True)
    other = make_ship(sea, name="Чайка", deck=DECK2, captain=CAPTAIN2, stops=(P_B, P_A))
    r = _buy(alpha, sea, ship_id=other)
    assert (r.status_code, r.json()["detail"]) == (400, sea_crud.MSG_OTHER_SHIP)
    exec_(sea, "UPDATE characters SET unconscious_until = :u WHERE id = :c", u=now() + timedelta(hours=1), c=ALPHA)
    r = _buy(alpha, sea)
    assert r.status_code == 409 and r.json()["detail"] != sea_crud.MSG_SHIP_IDLE
    assert passes(sea) == [] and gold(sea, ALPHA) == 1000


def test_free_ticket_posts_no_operation(alpha, sea):
    set_ship(sea, fare_base=0, fare_per_zone=0)
    r = _buy(alpha, sea)
    assert r.status_code == 201 and r.json()["fare"] == 0
    (p,) = passes(sea)
    assert p.fare_op_id is None and gold(sea, ALPHA) == 1000


def test_ticket_bought_on_deck_at_sea_starts_with_the_next_trip(alpha, sea):
    _sail(sea)
    place(sea, ALPHA, DECK)
    body = _view(alpha).json()
    (d,) = body["destinations"]                           # n - 1 = 2 trips from the stop it heads to: 200 -> 110 -> 200
    assert (d["to_trip"], d["port_id"], d["zones"], d["fare"]) == (2, P_C, 2, 20)
    assert body["stowaway"]["reason"] == sea_crud.MSG_SHIP_AT_SEA
    r = _buy(alpha, sea, to_trip=2)
    assert r.status_code == 201, r.text
    assert (r.json()["first_trip"], r.json()["from_port_id"], r.json()["to_port_id"]) == (2, P_B, P_C)
    assert r.json()["valid_now"] is False                 # trip 1 is the one sailing now
    assert treasury(sea, "region_treasury", R_B) + treasury(sea, "country_treasury", C_B) == 20


def test_ticket_from_port_while_the_captain_is_at_sea_is_400(alpha, sea):
    _sail(sea)
    r = _buy(alpha, sea)                                  # Alpha still in the port, the Captain on deck
    assert (r.status_code, r.json()["detail"]) == (400, sea_crud.MSG_NOT_AT_CAPTAIN)


# =============================================================================================== S3 sailor

def test_sailor_hire_snapshots_the_post_floor(alpha, sea):
    exec_(sea, "INSERT INTO posts (character_id, location_id, content) VALUES (2, 100, 'x'), (2, 100, 'y')")
    r = _hire(alpha, sea)
    assert r.status_code == 201, r.text
    assert (r.json()["kind"], r.json()["fare"], r.json()["first_trip"], r.json()["last_trip"]) == ("sailor", 0, 1, 1)
    (p,) = passes(sea)
    assert p.post_floor_id == 2 and gold(sea, ALPHA) == 1000


def test_sailor_slots_and_hiring_off(alpha, sea):
    add_pass(sea, BETA, kind="sailor")
    r = _hire(alpha, sea)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_NO_CREW_SLOTS)
    set_ship(sea, crew_slots=0)
    r = _hire(alpha, sea)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_HIRING_OFF)


def test_sailor_gate_closed_is_403(alpha, sea):
    sea.gate.return_value = False
    assert _hire(alpha, sea).status_code == 403
    assert passes(sea) == []


def test_sailor_after_a_ticket_is_409(alpha, sea):
    assert _buy(alpha, sea).status_code == 201
    r = _hire(alpha, sea)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_ALREADY_PASS)


# =============================================================================================== S4 stowaway

def test_stowaway_attempt_is_neutral_and_needs_no_gate(alpha, sea):
    r = _sneak(alpha, sea)
    assert (r.status_code, r.json()) == (201, {"message": sea_crud.MSG_SNEAK_DONE})
    (p,) = passes(sea)
    assert (p.kind, p.first_trip, p.last_trip, p.fare) == ("stowaway", 1, 1, 0)
    sea.gate.assert_not_called()


def test_stowaway_from_the_deck_while_docked_is_allowed(alpha, sea):
    place(sea, ALPHA, DECK)
    assert _sneak(alpha, sea).status_code == 201


def test_stowaway_refusals(alpha, sea):
    place(sea, ALPHA, LAND)
    r = _sneak(alpha, sea)
    assert (r.status_code, r.json()["detail"]) == (400, sea_crud.MSG_NOT_IN_PORT)
    place(sea, ALPHA, P_A)
    assert _sneak(alpha, sea).status_code == 201
    r = _sneak(alpha, sea)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_ALREADY_PASS)
    _sail(sea)
    place(sea, BETA, DECK)
    as_user(USER_BETA)
    r = _sneak(alpha, sea, character=BETA)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_SHIP_AT_SEA)
    r = _sneak(alpha, sea, character=BETA, ship_id=999)
    assert (r.status_code, r.json()["detail"]) == (404, sea_crud.MSG_SHIP_NOT_FOUND)


def test_stowaway_needs_a_token_and_the_owner(client, sea):
    assert _sneak(client, sea).status_code == 401
    as_user(USER_BETA)
    assert _sneak(client, sea).status_code == 403
    assert passes(sea) == []


# =============================================================================================== S5 deck

def test_deck_header_docked(alpha, sea):
    other = make_ship(sea, name="Чайка", deck=DECK2, captain=CAPTAIN2, stops=(P_B, P_A))
    set_ship(sea, other, status="docked", docked_port_id=P_A, stop_index=1, current_zone_id=Z1)
    place(sea, BETA, DECK)
    add_pass(sea, ALPHA)
    r = _deck(alpha)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ship"]["id"] == sea.ship_id and body["ship"]["departs_at"] is not None
    assert body["ships_nearby"] == [{"id": other, "name": "Чайка"}]
    assert body["passengers_count"] == 1
    assert [p["kind"] for p in body["my_passes"]] == ["ticket"]
    assert body["sailor_post_min_chars"] > 0


def test_deck_header_at_sea_sees_ships_in_the_same_zone(alpha, sea):
    other = make_ship(sea, name="Чайка", deck=DECK2, captain=CAPTAIN2, stops=(P_B, P_A))
    _sail(sea, zone=Z2, leg_pos=1)
    set_ship(sea, other, status="sailing", docked_port_id=None, current_zone_id=Z2, next_port_id=P_A,
             leg_path=[Z3, Z2, Z1], leg_pos=1, next_zone_at=now() + timedelta(minutes=3))
    body = _deck(alpha).json()
    assert body["ship"]["status"] == "sailing" and body["ship"]["next_port"] == {"id": P_B, "name": "Оазис"}
    assert body["ship"]["current_zone"]["name"] == "Северный залив" and body["ship"]["arrives_at"] is not None
    assert body["ships_nearby"] == [{"id": other, "name": "Чайка"}]
    set_ship(sea, other, current_zone_id=Z3)
    assert _deck(alpha).json()["ships_nearby"] == []


def test_deck_header_refusals(client, sea):
    assert _deck(client).status_code == 401
    as_user(USER_BETA)
    assert _deck(client).status_code == 403
    as_user(USER_ALPHA)
    r = _deck(client, location_id=LAND)
    assert (r.status_code, r.json()["detail"]) == (404, sea_crud.MSG_NOT_A_DECK)


# =============================================================================================== deploy skew

def test_sea_api_is_503_without_the_tables(alpha, sea, monkeypatch):
    monkeypatch.setitem(sea_crud._available_cache, "ok", False)
    exec_(sea, "DROP TABLE sea_settings")
    assert _view(alpha).status_code == 503
    assert _deck(alpha).status_code == 503
    assert _sneak(alpha, sea).status_code == 503


def test_sea_available_caches_only_a_positive_answer(sea, monkeypatch):
    monkeypatch.setitem(sea_crud._available_cache, "ok", False)
    db = sea()
    try:
        assert sea_crud.sea_available(db) is True
        assert sea_crud._available_cache["ok"] is True
    finally:
        db.close()
    monkeypatch.setitem(sea_crud._available_cache, "ok", False)
    exec_(sea, "DROP TABLE sea_passes")
    db = sea()
    try:
        assert sea_crud.sea_available(db) is False
        assert sea_crud._available_cache["ok"] is False
    finally:
        db.close()


# =============================================================================================== update_location (G1 / G2)

def test_boarding_without_a_right_is_refused(client, sea):
    r = _move(client, ALPHA, DECK)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_NEED_PASS)
    assert loc(sea, ALPHA) == P_A


@pytest.mark.parametrize("kind", ["ticket", "sailor", "stowaway"])
def test_boarding_with_a_right_works(client, sea, kind):
    add_pass(sea, ALPHA, kind=kind)
    r = _move(client, ALPHA, DECK)
    assert r.status_code == 200, r.text
    assert loc(sea, ALPHA) == DECK


def test_boarding_with_a_spent_or_future_pass_is_refused(client, sea):
    add_pass(sea, ALPHA, status="burnt")
    add_pass(sea, ALPHA, first=2, last=2)
    assert _move(client, ALPHA, DECK).json()["detail"] == sea_crud.MSG_NEED_PASS


def test_boarding_after_departure_is_refused(client, sea):
    add_pass(sea, ALPHA)
    _sail(sea)
    r = _move(client, ALPHA, DECK)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_SHIP_GONE)


def test_boarding_a_switched_off_ship_is_refused(client, sea):
    add_pass(sea, ALPHA)
    set_ship(sea, is_active=False)
    assert _move(client, ALPHA, DECK).json()["detail"] == sea_crud.MSG_SHIP_OFF


def test_boarding_from_another_port_is_refused(client, sea):
    add_pass(sea, ALPHA)
    place(sea, ALPHA, LAND)
    assert _move(client, ALPHA, DECK).json()["detail"] == sea_crud.MSG_SHIP_GONE


def test_leaving_the_deck_while_docked_only_to_the_port(client, sea):
    place(sea, ALPHA, DECK)
    r = _move(client, ALPHA, LAND)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_ONLY_TO_PORT)
    set_ship(sea, is_active=False)                         # disembarking needs no right, also when switched off
    assert _move(client, ALPHA, P_A).status_code == 200
    assert loc(sea, ALPHA) == P_A


def test_leaving_the_deck_at_sea_is_refused(client, sea):
    place(sea, ALPHA, DECK)
    _sail(sea)
    for dest in (P_A, P_B, LAND):
        r = _move(client, ALPHA, dest)
        assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_AT_SEA_NO_LANDING)
    assert loc(sea, ALPHA) == DECK


@pytest.mark.parametrize("start", [P_A, DECK])
def test_a_sea_zone_is_never_a_destination(client, sea, start):
    place(sea, ALPHA, start)
    r = _move(client, ALPHA, Z1)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_OPEN_SEA)
    assert loc(sea, ALPHA) == start


def test_ordinary_moves_are_untouched(client, sea):
    assert _move(client, ALPHA, LAND).status_code == 200
    assert loc(sea, ALPHA) == LAND


def test_ship_rows_are_locked_before_the_character(client, sea, monkeypatch):
    calls = []
    real = sea_crud.lock_ships_for_move

    def spy(db, cur, new):
        ships = real(db, cur, new)
        calls.append((cur, new, [s.id for s in ships]))
        return ships

    monkeypatch.setattr(sea_crud, "lock_ships_for_move", spy)
    add_pass(sea, ALPHA)
    assert _move(client, ALPHA, DECK).status_code == 200
    assert calls == [(P_A, DECK, [sea.ship_id])]


def test_location_changed_between_the_peek_and_the_lock_is_409(client, sea, monkeypatch):
    real = sea_crud.lock_ships_for_move

    def racing(db, cur, new):
        ships = real(db, cur, new)
        # a departure (or another tab) moved the character after the unlocked peek
        db.execute(models.Character.__table__.update().where(models.Character.id == ALPHA)
                   .values(current_location_id=LAND))
        return ships

    monkeypatch.setattr(sea_crud, "lock_ships_for_move", racing)
    add_pass(sea, ALPHA)
    r = _move(client, ALPHA, DECK)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_RETRY)
    assert loc(sea, ALPHA) == P_A                          # rolled back


# =============================================================================================== G2 / G3

def _admin_move(c, character, dest):
    as_user(1, "admin", ["characters:teleport"])
    return c.post(f"/characters/admin/{character}/move", json={"new_location_id": dest})


def test_admin_move_into_a_sea_zone_is_refused(client, sea):
    r = _admin_move(client, ALPHA, Z2)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_OPEN_SEA)
    assert loc(sea, ALPHA) == P_A


def test_admin_move_onto_and_off_a_deck_is_allowed(client, sea):
    assert _admin_move(client, ALPHA, DECK).status_code == 200
    assert loc(sea, ALPHA) == DECK
    _sail(sea)
    assert _admin_move(client, ALPHA, LAND).status_code == 200
    assert loc(sea, ALPHA) == LAND


def _home(c, character, dest):
    return c.post(f"/characters/internal/{character}/home-teleport", json={"location_id": dest}, headers=INTERNAL)


@pytest.mark.parametrize("dest", [DECK, Z1])
def test_home_teleport_never_lands_on_a_deck_or_in_a_zone(client, sea, dest):
    r = _home(client, ALPHA, dest)
    assert (r.status_code, r.json()["detail"]) == (409, sea_crud.MSG_TELEPORT_TARGET)
    assert loc(sea, ALPHA) == P_A


def test_home_teleport_off_a_deck_at_sea_works(client, sea):
    place(sea, ALPHA, DECK)
    _sail(sea)
    r = _home(client, ALPHA, LAND)
    assert r.status_code == 200, r.text
    assert loc(sea, ALPHA) == LAND


def _teleporters(sea, target_location):
    exec_(sea, "UPDATE users SET current_character = :c WHERE id = :u", c=ALPHA, u=USER_ALPHA)
    db = sea()
    try:
        for cid, where in ((80, P_A), (81, target_location)):
            db.add(models.Character(id=cid, name=f"Маг {cid}", user_id=None, id_subrace=1, id_class=1, id_race=1,
                                    appearance="-", avatar="-", is_npc=True, npc_role=crud.TELEPORT_ROLE,
                                    npc_status="alive", current_location_id=where, level=5, currency_balance=0))
        db.flush()
        link = models.TeleportLink(from_npc_id=80, to_npc_id=81, cost_gold=0)
        db.add(link)
        db.commit()
        return int(link.id)
    finally:
        db.close()


@pytest.mark.parametrize("target", [DECK, Z2])
def test_execute_teleport_refuses_a_deck_or_zone_target(sea, target):
    link_id = _teleporters(sea, target)
    db = sea()
    try:
        with pytest.raises(HTTPException) as exc:
            crud.execute_teleport(db, USER_ALPHA, 80, link_id)
        assert (exc.value.status_code, exc.value.detail) == (409, sea_crud.MSG_TELEPORT_TARGET)
        db.rollback()
    finally:
        db.close()
    assert loc(sea, ALPHA) == P_A and gold(sea, ALPHA) == 1000


@pytest.mark.parametrize("target, bidirectional", [(DECK, False), (Z2, False), (DECK, True)])
def test_create_teleport_link_refuses_a_deck_or_zone_end(sea, target, bidirectional):
    exec_(sea, "DELETE FROM teleport_links")
    _teleporters(sea, LAND)
    exec_(sea, "DELETE FROM teleport_links")
    if bidirectional:      # the source end stands on the deck, the target on land
        place(sea, 80, target)
        place(sea, 81, LAND)
    else:
        place(sea, 81, target)
    db = sea()
    try:
        with pytest.raises(HTTPException) as exc:
            crud.create_teleport_link(db, SimpleNamespace(from_npc_id=80, to_npc_id=81, cost_gold=0,
                                                          bidirectional=bidirectional, min_reputation_tier=None))
        assert exc.value.status_code == 422 and sea_crud.MSG_TELEPORT_TARGET in exc.value.detail
        db.rollback()
    finally:
        db.close()
    assert q(sea, "SELECT COUNT(*) FROM teleport_links") == 0


def test_teleport_target_refusal_is_none_for_land(sea):
    db = sea()
    try:
        assert sea_crud.teleport_target_refusal(db, LAND) is None
        assert sea_crud.teleport_target_refusal(db, None) is None
        assert sea_crud.teleport_target_refusal(db, "x") is None
    finally:
        db.close()


# =============================================================================================== security

def test_injection_like_ids_are_validation_errors(alpha, sea):
    assert alpha.get("/characters/sea/captain/1%27%20OR%201=1", params={"character_id": ALPHA}).status_code == 422
    assert alpha.get(VIEW, params={"character_id": "1; DROP TABLE sea_ships"}).status_code == 422
    r = alpha.post(_tickets_url(sea.ship_id), json={"character_id": ALPHA, "npc_id": CAPTAIN, "to_trip": "1 OR 1"})
    assert r.status_code == 422
    assert alpha.post(_tickets_url(0), json={"character_id": ALPHA, "npc_id": CAPTAIN, "to_trip": 1}).status_code == 422
    assert q(sea, "SELECT COUNT(*) FROM sea_ships") == 1


def test_negative_ids_are_validation_errors(alpha, sea):
    assert alpha.post(_tickets_url(sea.ship_id),
                      json={"character_id": -1, "npc_id": CAPTAIN, "to_trip": 1}).status_code == 422
    assert _deck(alpha, location_id=-5).status_code == 422


def test_unexpected_db_error_is_a_generic_500(alpha, sea, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def boom(*a, **k):
        raise OperationalError("SELECT secret", {}, Exception("password=hunter2"))

    monkeypatch.setattr(sea_crud, "captain_view", boom)
    r = _view(alpha)
    assert r.status_code == 500 and "hunter2" not in r.text and "SELECT" not in r.text

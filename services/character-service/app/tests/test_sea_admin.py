"""FEAT-213 QA (T7): the ship admin A1–A7 (features/FEAT-213 §3.10, §3.12, §3.13, §3.16).

* permissions: ``locations:read`` / ``create`` / ``update`` / ``delete`` (no token 401, a missing permission 403);
* A2 validations (deck: exists, hidden country, not a zone / port, no links, not bound; Captain: NPC, role, alive,
  not bound; stops: 2..30, consecutive differ, ports with a zone, every leg resolvable, manual override valid) and the
  created state (docked at stop 0, departure in ``boarding_minutes``, Captain moved to the port);
* A3: the deck is immutable, the route only while docked (the docked port must stay), a route change refunds the
  passes not started yet and completes the started ones, switching off refunds, switching on re-plans the departure;
  refunds reverse every posting of the fare exactly (world money conserved) and are idempotent;
* A4: only while docked; everyone on deck put ashore, passes refunded / completed and kept as history;
* A5 leg preview problems, A6 candidates, A7 settings ranges; security cases.
"""

from datetime import timedelta

import pytest

import econ_core
import models
import sea_admin
import sea_core
import sea_crud
from tests.sea_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, CAPTAIN, CAPTAIN2, C_A, DECK, DECK2, DECK_FREE, LAND, P_A, P_B, P_C, R_A, USER_ALPHA, Z1, Z2,
    Z3, Z4, Z5, add_pass, api, as_user, buy, client, depart, exec_, gold, law_world, loc, make_ship, money_total,
    now, op, passes, place, postings, q, rep_world, rows, run_ship, sea, set_ship, ship, treasury,
)

SHIPS = "/characters/admin/sea/ships"
PREVIEW = "/characters/admin/sea/legs/preview"
CANDIDATES = "/characters/admin/sea/candidates"
SETTINGS = "/characters/admin/sea/settings"
ALL = ["locations:read", "locations:create", "locations:update", "locations:delete"]


@pytest.fixture
def admin(client):
    as_user(1, "admin", ALL)
    return client


def _body(**kw):
    body = dict(name="Чайка", deck_location_id=DECK2, captain_npc_id=CAPTAIN2, capacity=4, crew_slots=1,
                boarding_minutes=20, zone_minutes=5, fare_base=3, fare_per_zone=2,
                stops=[{"port_location_id": P_B}, {"port_location_id": P_A}])
    body.update(kw)
    return body


def _stops(*ports):
    return [p if isinstance(p, dict) else {"port_location_id": p} for p in ports]


def _ship_count(sea):
    return int(q(sea, "SELECT COUNT(*) FROM sea_ships"))


# =============================================================================================== permissions

ENDPOINTS = [
    ("get", SHIPS, None, "locations:read"),
    ("post", SHIPS, _body(), "locations:create"),
    ("patch", f"{SHIPS}/1", {"name": "Новое имя"}, "locations:update"),
    ("delete", f"{SHIPS}/1", None, "locations:delete"),
    ("post", PREVIEW, {"stops": _stops(P_A, P_B)}, "locations:read"),
    ("get", CANDIDATES, None, "locations:read"),
    ("get", SETTINGS, None, "locations:read"),
    ("put", SETTINGS, {"sailor_post_min_chars": 500, "stowaway_base_pct": 40, "stowaway_wanted_points": 10,
                       "path_max_zones": 50}, "locations:update"),
]


def _call(c, method, path, body):
    return getattr(c, method)(path, json=body) if body is not None else getattr(c, method)(path)


@pytest.mark.parametrize("method, path, body, perm", ENDPOINTS)
def test_admin_needs_a_token(client, method, path, body, perm):
    assert _call(client, method, path, body).status_code == 401


@pytest.mark.parametrize("method, path, body, perm", ENDPOINTS)
def test_admin_needs_the_exact_permission(client, sea, method, path, body, perm):
    others = [p for p in ALL if p != perm]
    as_user(2, "moderator", others)
    r = _call(client, method, path, body)
    assert r.status_code == 403, r.text
    assert _ship_count(sea) == 1 and ship(sea).name == "Морская дева"


@pytest.mark.parametrize("method, path, body, perm", ENDPOINTS)
def test_admin_with_the_permission_passes(client, sea, method, path, body, perm):
    as_user(3, "editor", [perm])
    r = _call(client, method, path, body)
    assert r.status_code in (200, 201, 204), r.text


def test_plain_user_is_403(client):
    as_user(USER_ALPHA)
    assert client.get(SHIPS).status_code == 403


# =============================================================================================== A1 list

def test_list_shows_state_legs_and_people(admin, sea):
    place(sea, ALPHA, DECK)
    add_pass(sea, BETA)
    (row,) = admin.get(SHIPS).json()
    assert (row["name"], row["status"], row["trip_no"], row["is_active"]) == ("Морская дева", "docked", 0, True)
    assert row["captain"]["id"] == CAPTAIN and row["captain"]["location_name"] == "Тракт"
    assert row["captain_problem"] is None and row["blocked_reason"] is None
    assert row["deck"] == {"id": DECK, "name": "Палуба Морской девы"}
    assert [s["port_id"] for s in row["stops"]] == [P_A, P_B, P_C]
    assert [(lg["ok"], [z["id"] for z in lg["zones"]], lg["minutes"]) for lg in row["legs"]] == \
        [(True, [Z1, Z2, Z3], 30), (True, [Z3, Z4], 20)]
    assert (row["passengers_count"], row["active_passes"]) == (1, 1)
    assert row["current_zone"]["sea_name"] == "Море Эйдонэи"


@pytest.mark.parametrize("sql, text", [
    ("UPDATE characters SET npc_status = 'dead' WHERE id = 70", "мёртв"),
    ("UPDATE characters SET npc_role = 'merchant' WHERE id = 70", "Капитан"),
    ("DELETE FROM characters WHERE id = 70", "удалён"),
    ("UPDATE sea_ships SET captain_npc_id = NULL", "не назначен"),
])
def test_list_explains_a_missing_captain(admin, sea, sql, text):
    exec_(sea, sql)
    assert text in admin.get(SHIPS).json()[0]["captain_problem"]


# =============================================================================================== A2 create

def test_create_docks_at_the_first_stop_and_moves_the_captain(admin, sea):
    place(sea, CAPTAIN2, LAND)
    r = admin.post(SHIPS, json=_body())
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["status"], body["stop_index"], body["docked_port"]["id"], body["current_zone"]["id"]) == \
        ("docked", 0, P_B, Z3)
    s = ship(sea, body["id"])
    assert s.departs_at is not None and s.last_port_id == P_B and s.direction == 1
    assert loc(sea, CAPTAIN2) == P_B


def test_create_switched_off_has_no_departure(admin, sea):
    r = admin.post(SHIPS, json=_body(is_active=False))
    assert r.status_code == 201 and r.json()["departs_at"] is None


def test_create_with_a_valid_manual_path(admin, sea):
    r = admin.post(SHIPS, json=_body(stops=_stops({"port_location_id": P_A, "path_override": [Z1, Z5, Z3]}, P_B)))
    assert r.status_code == 201, r.text
    leg = r.json()["legs"][0]
    assert leg["override"] is True and [z["id"] for z in leg["zones"]] == [Z1, Z5, Z3]
    assert r.json()["stops"][0]["path_override"] == [Z1, Z5, Z3]
    assert r.json()["stops"][1]["path_override"] is None      # the last stop of a line keeps no override


@pytest.mark.parametrize("change, status, detail", [
    (dict(deck_location_id=999), 404, sea_admin.MSG_DECK_NOT_FOUND),
    (dict(deck_location_id=LAND), 409, sea_admin.MSG_DECK_NOT_HIDDEN),
    (dict(deck_location_id=Z1), 409, sea_admin.MSG_DECK_ZONE),
    (dict(deck_location_id=DECK), 409, sea_admin.MSG_DECK_BOUND.format(name="Морская дева")),
    (dict(captain_npc_id=999), 404, sea_admin.MSG_CAPTAIN_NOT_FOUND),
    (dict(captain_npc_id=ALPHA), 404, sea_admin.MSG_CAPTAIN_NOT_FOUND),
    (dict(captain_npc_id=50), 409, sea_admin.MSG_CAPTAIN_ROLE),
    (dict(captain_npc_id=CAPTAIN), 409, sea_admin.MSG_CAPTAIN_BOUND.format(name="Морская дева")),
    (dict(stops=_stops(P_A, P_A, P_B)), 409, sea_admin.MSG_STOPS_SAME.format(n=2)),
    (dict(stops=_stops(P_A, P_B, P_A), is_loop=True), 409, sea_admin.MSG_STOPS_SAME.format(n=3)),
    (dict(stops=_stops(P_A, LAND)), 409, sea_admin.MSG_STOP_NOT_PORT.format(name="Рынок")),
    (dict(stops=_stops(P_A, 999)), 409, sea_admin.MSG_STOP_NOT_PORT.format(name="#999")),
    (dict(stops=_stops({"port_location_id": P_A, "path_override": [Z1, Z3]}, P_B)), 409,
     sea_admin.MSG_BAD_OVERRIDE.format(n=1, a="Тракт", b="Оазис")),
])
def test_create_refusals(admin, sea, change, status, detail):
    r = admin.post(SHIPS, json=_body(**change))
    assert (r.status_code, r.json()["detail"]) == (status, detail)
    assert _ship_count(sea) == 1


def test_create_refuses_a_port_deck_and_a_linked_deck(admin, sea):
    exec_(sea, "UPDATE Locations SET is_port = 1 WHERE id = :d", d=DECK2)
    assert admin.post(SHIPS, json=_body()).json()["detail"] == sea_admin.MSG_DECK_PORT
    exec_(sea, "UPDATE Locations SET is_port = 0 WHERE id = :d", d=DECK2)
    exec_(sea, "INSERT INTO LocationNeighbors (location_id, neighbor_id) VALUES (:a, :b)", a=DECK_FREE, b=DECK2)
    assert admin.post(SHIPS, json=_body()).json()["detail"] == sea_admin.MSG_DECK_LINKED
    exec_(sea, "DELETE FROM LocationNeighbors WHERE location_id = :a", a=DECK_FREE)
    exec_(sea, "INSERT INTO arrow_neighbors (arrow_id, location_id) VALUES (1, :d)", d=DECK2)
    assert admin.post(SHIPS, json=_body()).json()["detail"] == sea_admin.MSG_DECK_LINKED
    assert _ship_count(sea) == 1


def test_create_refuses_a_dead_captain_and_a_stop_without_a_zone(admin, sea):
    exec_(sea, "UPDATE characters SET npc_status = 'dead' WHERE id = :c", c=CAPTAIN2)
    assert admin.post(SHIPS, json=_body()).json()["detail"] == sea_admin.MSG_CAPTAIN_DEAD
    exec_(sea, "UPDATE Locations SET is_port = 1 WHERE id = 101")          # a port that opens to no zone
    r = admin.post(SHIPS, json=_body(captain_npc_id=None, stops=_stops(P_A, 101)))
    assert (r.status_code, r.json()["detail"]) == (409, sea_admin.MSG_STOP_NOT_PORT.format(name="Застава"))


def test_create_refuses_an_unreachable_leg(admin, sea):
    exec_(sea, "DELETE FROM LocationNeighbors WHERE location_id = :z OR neighbor_id = :z", z=Z4)
    r = admin.post(SHIPS, json=_body(stops=_stops(P_B, P_C)))
    assert (r.status_code, r.json()["detail"]) == (409, sea_admin.MSG_NO_PATH.format(a="Оазис", b="Нива", n=1))


def test_create_checks_the_loop_closing_leg(admin, sea):
    stops = _stops(P_A, P_B, {"port_location_id": P_C, "path_override": [Z4, Z1]})    # last -> first, not adjacent
    r = admin.post(SHIPS, json=_body(captain_npc_id=None, stops=stops, is_loop=True))
    assert (r.status_code, r.json()["detail"]) == (409, sea_admin.MSG_BAD_OVERRIDE.format(n=3, a="Нива", b="Тракт"))
    stops[2]["path_override"] = [Z4, Z3, Z2, Z1]
    r = admin.post(SHIPS, json=_body(captain_npc_id=None, stops=stops, is_loop=True))
    assert r.status_code == 201, r.text
    assert r.json()["legs"][2]["override"] is True and r.json()["stops"][2]["path_override"] == [Z4, Z3, Z2, Z1]


@pytest.mark.parametrize("change", [
    dict(name=""), dict(name="x" * 101), dict(capacity=201), dict(capacity=-1), dict(crew_slots=21),
    dict(boarding_minutes=0), dict(zone_minutes=1441), dict(fare_base=-1), dict(stops=_stops(P_A)),
    dict(stops=_stops(*([P_A, P_B] * 16))), dict(stops=[{"port_location_id": 0}, {"port_location_id": P_A}]),
    dict(stops=[{"port_location_id": P_A, "path_override": [Z1, 0]}, {"port_location_id": P_B}]),
    dict(stops=[{"port_location_id": P_A, "path_override": [Z1] * 1001}, {"port_location_id": P_B}]),
    dict(deck_location_id=0), dict(captain_npc_id=0),
])
def test_create_validation_errors(admin, sea, change):
    assert admin.post(SHIPS, json=_body(**change)).status_code == 422
    assert _ship_count(sea) == 1


# =============================================================================================== A3 update

def test_update_simple_fields(admin, sea):
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"name": "  Дева  ", "capacity": 7, "fare_base": 0})
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["capacity"], r.json()["fare_base"]) == ("Дева", 7, 0)


def test_update_unknown_ship_is_404(admin, sea):
    r = admin.patch(f"{SHIPS}/999", json={"name": "x"})
    assert (r.status_code, r.json()["detail"]) == (404, sea_crud.MSG_SHIP_NOT_FOUND)


def test_deck_is_immutable(admin, sea):
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"deck_location_id": DECK2})
    assert (r.status_code, r.json()["detail"]) == (409, sea_admin.MSG_DECK_IMMUTABLE)
    assert admin.patch(f"{SHIPS}/{sea.ship_id}", json={"deck_location_id": DECK}).status_code == 200


def test_captain_rebind_and_unbind(admin, sea):
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"captain_npc_id": CAPTAIN2})
    assert r.status_code == 200 and r.json()["captain_npc_id"] == CAPTAIN2
    assert loc(sea, CAPTAIN2) == P_A
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"captain_npc_id": None})
    assert r.status_code == 200 and r.json()["captain_npc_id"] is None
    other = make_ship(sea, name="Чайка", deck=DECK2, captain=CAPTAIN2, stops=(P_B, P_A))
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"captain_npc_id": CAPTAIN2})
    assert (r.status_code, r.json()["detail"]) == (409, sea_admin.MSG_CAPTAIN_BOUND.format(name="Чайка"))
    assert other


def test_route_change_at_sea_is_refused_but_the_same_route_is_fine(admin, sea):
    depart(sea)
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"stops": _stops(P_A, P_B)})
    assert (r.status_code, r.json()["detail"]) == (409, sea_admin.MSG_ROUTE_AT_SEA)
    assert admin.patch(f"{SHIPS}/{sea.ship_id}", json={"is_loop": True}).status_code == 409
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"stops": _stops(P_A, P_B, P_C), "capacity": 5})
    assert r.status_code == 200 and r.json()["capacity"] == 5


def test_route_change_must_keep_the_docked_port(admin, sea):
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"stops": _stops(P_B, P_C)})
    assert (r.status_code, r.json()["detail"]) == (409, sea_admin.MSG_DOCKED_PORT_KEPT.format(name="Тракт"))
    assert len(rows(sea, "SELECT id FROM sea_ship_stops WHERE ship_id = :s", s=sea.ship_id)) == 3


def test_route_change_refunds_not_started_and_completes_started_passes(admin, sea, stub_law_notify_send):
    started = buy(sea, ALPHA, to_trip=2)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    run_ship(sea, t + timedelta(minutes=30))                  # docked at 200, trip 1 done, Alpha's ticket runs on
    place(sea, BETA, P_B)
    future = buy(sea, BETA, to_trip=2)                        # 200 -> 110, starts with trip 2
    assert gold(sea, BETA) < 1000
    total = money_total(sea)
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"stops": _stops(P_C, P_B, P_A)})
    assert r.status_code == 200, r.text
    assert (r.json()["stop_index"], r.json()["docked_port"]["id"]) == (1, P_B)
    by_id = {p.id: p for p in passes(sea)}
    assert by_id[started].status == "completed" and by_id[started].refund_op_id is None
    assert by_id[future].status == "refunded" and by_id[future].refund_op_id is not None
    assert gold(sea, BETA) == 1000 and money_total(sea) == total
    assert q(sea, "SELECT COUNT(*) FROM econ_operations WHERE idempotency_key = :k", k=f"sea_refund:{future}") == 1
    assert [s[0] for s in rows(sea, "SELECT port_location_id FROM sea_ship_stops WHERE ship_id = :s ORDER BY idx",
                               s=sea.ship_id)] == [P_C, P_B, P_A]
    refunds = [p for c in stub_law_notify_send.call_args_list for p in c.args[0]
               if p["ws_data"].get("event") == "refund"]
    assert [p["target_value"] for p in refunds] == [8]


def test_refund_reverses_every_posting_exactly(sea):
    total = money_total(sea)
    pid = buy(sea, ALPHA)
    (p,) = passes(sea)
    fare_legs = postings(sea, p.fare_op_id)
    db = sea()
    try:
        row = db.get(models.SeaPass, pid)
        assert sea_crud.refund_pass(db, row) is True
        db.commit()
    finally:
        db.close()
    (p,) = passes(sea)
    assert p.status == "refunded" and op(sea, p.refund_op_id) == (econ_core.OP_SEA_REFUND, f"sea_refund:{pid}")
    back = postings(sea, p.refund_op_id)
    assert sorted((b[2], b[3], b[0], b[1], b[4]) for b in back) == sorted(f[:5] for f in fare_legs)
    assert {b[5] for b in back} == {econ_core.LEG_REFUND}
    assert gold(sea, ALPHA) == 1000 and money_total(sea) == total
    assert treasury(sea, "region_treasury", R_A) == 0 and treasury(sea, "country_treasury", C_A) == 0


def test_refund_is_idempotent(sea):
    pid = buy(sea, ALPHA)
    for _ in range(2):
        db = sea()
        try:
            row = db.get(models.SeaPass, pid)
            row.status = "active"
            sea_crud.refund_pass(db, row)
            db.commit()
        finally:
            db.close()
    assert gold(sea, ALPHA) == 1000
    assert q(sea, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'sea_refund'") == 1
    assert passes(sea)[0].refund_op_id is not None


def test_switch_off_refunds_and_switch_on_replans(admin, sea):
    pid = buy(sea, ALPHA)
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False and r.json()["departs_at"] is None
    assert passes(sea)[0].status == "refunded" and gold(sea, ALPHA) == 1000
    before = now()
    r = admin.patch(f"{SHIPS}/{sea.ship_id}", json={"is_active": True, "boarding_minutes": 15})
    s = ship(sea)
    assert r.status_code == 200 and s.is_active and s.blocked_reason is None
    assert before + timedelta(minutes=14) <= s.departs_at <= now() + timedelta(minutes=16)
    assert pid


def test_switch_off_at_sea_keeps_started_passes_and_docks_for_good(admin, sea):
    pid = buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    _, t = depart(sea)
    assert admin.patch(f"{SHIPS}/{sea.ship_id}", json={"is_active": False}).status_code == 200
    assert passes(sea)[0].status == "active"
    run_ship(sea, t + timedelta(minutes=30))
    s = ship(sea)
    assert (s.status, s.docked_port_id, s.departs_at) == ("docked", P_B, None)
    run_ship(sea, t + timedelta(days=1))
    assert ship(sea).status == "docked" and pid


# =============================================================================================== A4 delete

def test_delete_at_sea_is_refused(admin, sea):
    depart(sea)
    r = admin.delete(f"{SHIPS}/{sea.ship_id}")
    assert (r.status_code, r.json()["detail"]) == (409, sea_admin.MSG_DELETE_AT_SEA)
    assert _ship_count(sea) == 1


def test_delete_puts_everyone_ashore_and_refunds(admin, sea):
    pid = buy(sea, ALPHA)
    place(sea, ALPHA, DECK)
    place(sea, BETA, DECK)
    total = money_total(sea)
    assert admin.delete(f"{SHIPS}/{sea.ship_id}").status_code == 204
    assert _ship_count(sea) == 0
    assert q(sea, "SELECT COUNT(*) FROM sea_ship_stops") == 0
    assert loc(sea, ALPHA) == P_A and loc(sea, BETA) == P_A
    (p,) = passes(sea)                                          # history kept
    assert p.id == pid and p.status == "refunded"
    assert gold(sea, ALPHA) == 1000 and money_total(sea) == total
    assert q(sea, "SELECT COUNT(*) FROM econ_operations WHERE idempotency_key = :k", k=f"sea_refund:{pid}") == 1
    assert sorted(c.args for c in sea.left.call_args_list) == [(ALPHA, DECK), (BETA, DECK)]
    assert q(sea, "SELECT COUNT(*) FROM Locations WHERE id = :d", d=DECK) == 1   # the deck location stays


# Regression (QA T7): delete_ship / _end_passes_for_route_change re-read the passes with populate_existing()
# before a flush, so a just-refunded pass came back 'active' and was marked 'completed'.


def test_delete_marks_a_refunded_pass_refunded(admin, sea):
    pid = buy(sea, ALPHA)
    assert admin.delete(f"{SHIPS}/{sea.ship_id}").status_code == 204
    (p,) = passes(sea)
    assert (p.id, p.status) == (pid, "refunded") and p.refund_op_id is not None


def test_route_change_marks_a_refunded_pass_refunded(admin, sea):
    pid = buy(sea, ALPHA)
    assert admin.patch(f"{SHIPS}/{sea.ship_id}", json={"stops": _stops(P_A, P_B)}).status_code == 200
    (p,) = passes(sea)
    assert (p.id, p.status) == (pid, "refunded") and p.refund_op_id is not None


def test_delete_unknown_is_404(admin, sea):
    assert admin.delete(f"{SHIPS}/999").status_code == 404


# =============================================================================================== A5 preview

def _preview(c, *stops, is_loop=False, zone_minutes=None):
    body = {"stops": _stops(*stops), "is_loop": is_loop}
    if zone_minutes:
        body["zone_minutes"] = zone_minutes
    r = c.post(PREVIEW, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_preview_paths_and_minutes(admin, sea):
    (leg,) = _preview(admin, P_A, P_B, zone_minutes=7)
    assert (leg["ok"], leg["override"], leg["minutes"], leg["problem"]) == (True, False, 21, None)
    assert [z["name"] for z in leg["zones"]] == ["Пролив Ветров", "Северный залив", "Тихая бухта"]
    assert leg["from"] == {"id": P_A, "name": "Тракт"}


def test_preview_problems(admin, sea):
    exec_(sea, "UPDATE Locations SET is_port = 1 WHERE id = 101")
    legs = _preview(admin, P_A, P_A, LAND, P_B, 101)
    assert [lg["problem"] for lg in legs] == ["same_port", "not_port", "not_port", sea_core.LEG_NO_ZONE]
    assert all(lg["ok"] is False and lg["problem_text"] for lg in legs)


def test_preview_bad_and_good_override(admin, sea):
    (bad,) = _preview(admin, {"port_location_id": P_A, "path_override": [Z1, Z3]}, P_B)
    assert (bad["ok"], bad["override"], bad["problem"]) == (False, False, sea_core.LEG_BAD_OVERRIDE)
    assert [z["id"] for z in bad["zones"]] == [Z1, Z2, Z3]          # the BFS path is shown instead
    (good,) = _preview(admin, {"port_location_id": P_A, "path_override": [Z1, Z5, Z3]}, P_B)
    assert (good["ok"], good["override"]) == (True, True)


def test_preview_no_path_and_loop_leg(admin, sea):
    exec_(sea, "DELETE FROM LocationNeighbors WHERE location_id = :z OR neighbor_id = :z", z=Z4)
    legs = _preview(admin, P_A, P_B, P_C, is_loop=True)
    assert [(lg["index"], lg["from"]["id"], lg["to"]["id"], lg["problem"]) for lg in legs] == [
        (0, P_A, P_B, None), (1, P_B, P_C, sea_core.LEG_NO_PATH), (2, P_C, P_A, sea_core.LEG_NO_PATH)]


# =============================================================================================== A6 candidates

def test_candidates_list_free_decks_and_captains(admin, sea):
    exec_(sea, "INSERT INTO LocationNeighbors (location_id, neighbor_id) VALUES (:a, :b)", a=DECK_FREE, b=Z1)
    body = admin.get(CANDIDATES).json()
    assert [d["id"] for d in body["decks"]] == [DECK2]
    assert body["decks"][0]["country_name"] == "Моря"
    assert [c["id"] for c in body["captains"]] == [CAPTAIN2]
    own = admin.get(CANDIDATES, params={"ship_id": sea.ship_id}).json()
    assert [d["id"] for d in own["decks"]] == [DECK, DECK2]
    assert [c["id"] for c in own["captains"]] == [CAPTAIN, CAPTAIN2]
    exec_(sea, "UPDATE characters SET npc_status = 'dead' WHERE id = :c", c=CAPTAIN2)
    assert admin.get(CANDIDATES).json()["captains"] == []


# =============================================================================================== A7 settings

def test_settings_defaults_and_save(admin, sea):
    assert admin.get(SETTINGS).json() == {"sailor_post_min_chars": 800, "stowaway_base_pct": 60.0,
                                          "stowaway_wanted_points": 50, "path_max_zones": 200}
    new = {"sailor_post_min_chars": 1200, "stowaway_base_pct": 33.33, "stowaway_wanted_points": 75,
           "path_max_zones": 40}
    r = admin.put(SETTINGS, json=new)
    assert r.status_code == 200 and r.json() == new
    assert admin.get(SETTINGS).json() == new


@pytest.mark.parametrize("field, value", [
    ("sailor_post_min_chars", 299), ("sailor_post_min_chars", 20001), ("stowaway_base_pct", -1),
    ("stowaway_base_pct", 100.5), ("stowaway_wanted_points", 0), ("path_max_zones", 9), ("path_max_zones", 1001),
])
def test_settings_ranges(admin, sea, field, value):
    body = {"sailor_post_min_chars": 800, "stowaway_base_pct": 60, "stowaway_wanted_points": 50,
            "path_max_zones": 200, field: value}
    assert admin.put(SETTINGS, json=body).status_code == 422
    assert admin.get(SETTINGS).json()["path_max_zones"] == 200


# =============================================================================================== security

@pytest.mark.parametrize("name", ["'; DROP TABLE sea_ships; --", "\" OR 1=1 --", "<script>alert(1)</script>"])
def test_hostile_names_are_stored_as_plain_text(admin, sea, name):
    r = admin.post(SHIPS, json=_body(name=name))
    assert r.status_code == 201, r.text
    assert r.json()["name"] == name
    assert _ship_count(sea) == 2


def test_injection_like_path_ids_are_validation_errors(admin, sea):
    assert admin.patch(f"{SHIPS}/1%20OR%201=1", json={"name": "x"}).status_code == 422
    assert admin.delete(f"{SHIPS}/0").status_code == 422
    assert admin.get(CANDIDATES, params={"ship_id": "1;DROP"}).status_code == 422
    assert _ship_count(sea) == 1


def test_admin_db_error_is_a_generic_500(admin, sea, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def boom(*a, **k):
        raise OperationalError("SELECT secret", {}, Exception("password=hunter2"))

    monkeypatch.setattr(sea_admin, "list_ships", boom)
    r = admin.get(SHIPS)
    assert (r.status_code, r.json()["detail"]) == (500, sea_admin.MSG_LOAD_FAILED)
    assert "hunter2" not in r.text

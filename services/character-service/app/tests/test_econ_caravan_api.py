"""FEAT-192 QA (#10): caravan admin API (contract 3.11), the region card ``caravans`` field (3.12), the sim params
(3.10) and the summary escrow sub-invariant, on SQLite.

World = ``test_econ_tick.factory`` (countries 1 «Мидденгерд», 2 «Пустошь») + the auction tables the summary reads
(their real columns: ``auction_listings.current_bid / current_bidder_id / status``,
``auction_storage.gold_amount``). Caravans are produced by the real pass (``test_econ_tick_caravans`` helpers) or,
for card edge cases, inserted as ``econ_caravans`` rows with the columns of migration 035.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import econ_core as core
import econ_tick
import economy_api
import economy_caravan_crud as crud
import models
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.test_econ_tick import T0, _add_region, _rows, _scalar, factory  # noqa: F401  (factory: fixture)
from tests.test_econ_tick_caravans import (
    _caravans, _exec, _good, _pair, _pass, _region, _two_regions,
)

BASE = "/characters/admin/economy"
CARAVANS = f"{BASE}/caravans"
READ = ["economy:read"]
SETTINGS = ["economy:read", "economy:settings"]
ALL_PERMS = ["economy:read", "economy:emit", "economy:adjust", "economy:settings"]

EXTRA_DDL = [
    """CREATE TABLE IF NOT EXISTS auction_listings (id INTEGER PRIMARY KEY, current_bid INTEGER NOT NULL DEFAULT 0,
        current_bidder_id INTEGER NULL, status VARCHAR(20) NOT NULL DEFAULT 'active')""",
    "CREATE TABLE IF NOT EXISTS auction_storage (id INTEGER PRIMARY KEY, gold_amount INTEGER NOT NULL DEFAULT 0)",
]

CARD_LINE_KEYS = {"group_code", "group_name", "region_id", "region_name", "country_name", "foreign", "in_transit"}


@pytest.fixture
def world(factory):
    for ddl in EXTRA_DDL:
        _exec(factory, ddl)

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[economy_api.get_db] = override_get_db
    core.invalidate_settings_cache()
    yield factory
    app.dependency_overrides.pop(economy_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)
    core.invalidate_settings_cache()


def _as(permissions, role="moderator", user_id=7):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username="tester", role=role, permissions=list(permissions))


@pytest.fixture
def api(world):
    _as(ALL_PERMS, role="admin")
    return TestClient(app)


def _put_pair(c, a=1, b=2, enabled=True, duty=10.0, **extra):
    return c.put(f"{CARAVANS}/pairs", json={"country_a": a, "country_b": b, "is_enabled": enabled,
                                           "duty_pct": duty, **extra})


def _card(c, region_id):
    resp = c.get(f"/characters/economy/regions/{region_id}/card")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _insert_caravan(f, *, frm, to, group="food", status="in_transit", run=1, finished_at=None, from_country=1,
                    to_country=1):
    db = f()
    try:
        db.add(models.EconCaravan(
            dispatch_run_id=run, from_region_id=frm, to_region_id=to, from_country_id=from_country,
            to_country_id=to_country, group_code=group, units=Decimal("1.000"), unit_price=Decimal("2.0000"),
            value=0, duty=0, duty_pct=Decimal("0"), paid_purse=0, paid_treasury=0, travel_runs=1,
            runs_left=1 if status == "in_transit" else 0, last_run_id=run, status=status,
            cancel_reason="destination_left" if status == "cancelled" else None,
            goods_returned=True if status == "cancelled" else None, created_at=T0, finished_at=finished_at,
            finished_run_id=run + 1 if status != "in_transit" else None))
        db.commit()
    finally:
        db.close()


def _now():
    return datetime.utcnow().replace(microsecond=0)


# --------------------------------------------------------------------------------------------- permissions

def test_unauthenticated_is_401(world):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    anon = TestClient(app)
    assert anon.get(f"{CARAVANS}/overview").status_code == 401
    assert anon.get(CARAVANS).status_code == 401
    assert _put_pair(anon).status_code == 401


def test_plain_user_is_403_everywhere(world):
    _as([], role="user")
    c = TestClient(app)
    for resp in (c.get(f"{CARAVANS}/overview"), c.get(CARAVANS), _put_pair(c)):
        assert resp.status_code == 403 and resp.json()["detail"] == "Недостаточно прав"


def test_read_permission_reads_but_cannot_write(world):
    _as(READ)
    c = TestClient(app)
    assert c.get(f"{CARAVANS}/overview").status_code == 200
    assert c.get(CARAVANS).status_code == 200
    assert _put_pair(c).status_code == 403
    assert c.put(f"{BASE}/sim", json={"tick_enabled": True, "params": {"caravan_surplus_share": 0.5}}) \
        .status_code == 403
    assert _scalar(world, "SELECT COUNT(*) FROM econ_trade_pairs") == 0


def test_settings_permission_can_write_pairs_without_emit(world):
    _as(SETTINGS)
    resp = _put_pair(TestClient(app))
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------------------------- overview

def test_overview_defaults(api, world):
    _region(world, 1)
    _region(world, 2)
    _region(world, 3, country=2)
    _add_region(world, 4, world_row=False)                 # econ row of a deleted region: not counted
    data = api.get(f"{CARAVANS}/overview").json()
    feat192 = {"caravans_enabled": 1, "caravan_surplus_share": 0.25, "caravan_purse_share": 0.25,
               "caravan_treasury_food_share": 0.5, "caravan_travel_domestic": 1,
               "caravan_travel_foreign": 2, "caravan_min_value": 10, "caravan_max_per_run": 200}
    # FEAT-211 3.14 extends the caravan card with the physical caravan / raid keys
    assert {k: data["params"][k] for k in feat192} == feat192
    assert set(data["params"]) == set(crud.CARAVAN_PARAM_KEYS)
    assert data["escrow"] == {"balance": 0, "expected": 0, "ok": True}
    assert data["in_transit"] == {"count": 0, "value": 0, "duty": 0}
    assert data["last_run"] is None
    assert data["countries"] == [{"country_id": 1, "name": "Мидденгерд", "participating_regions": 2},
                                 {"country_id": 2, "name": "Пустошь", "participating_regions": 1}]
    assert data["pairs"] == [{"country_a": 1, "country_b": 2, "name_a": "Мидденгерд", "name_b": "Пустошь",
                              "is_enabled": False, "duty_pct": 10.0, "updated_at": None}]


def test_overview_every_unordered_pair_once(api, world):
    _exec(world, "INSERT INTO Countries (id, name) VALUES (3, 'Альтер')")
    pairs = api.get(f"{CARAVANS}/overview").json()["pairs"]
    assert sorted((p["country_a"], p["country_b"]) for p in pairs) == [(1, 2), (1, 3), (2, 3)]
    assert all(p["country_a"] < p["country_b"] for p in pairs)


def test_overview_counters_after_runs(api, world):
    _two_regions(world, seller_country=2)
    _pair(world, 1, 2, duty=10)
    first = econ_tick.run_tick(world, trigger="manual", now=T0)
    data = api.get(f"{CARAVANS}/overview").json()
    food = [c for c in _caravans(world) if c["group"] == "food"]
    assert food and food[0]["dispatch_run_id"] == first.run_id
    assert data["last_run"]["run_id"] == first.run_id
    assert data["last_run"]["dispatched"] == first.caravans_dispatched == len(_caravans(world))
    assert (data["last_run"]["delivered"], data["last_run"]["cancelled"]) == (0, 0)
    in_transit = [c for c in _caravans(world) if c["status"] == "in_transit"]
    assert data["in_transit"] == {"count": len(in_transit), "value": sum(c["value"] for c in in_transit),
                                  "duty": sum(c["duty"] for c in in_transit)}
    assert data["escrow"]["ok"] is True
    assert data["escrow"]["balance"] == data["escrow"]["expected"] == \
        sum(c["paid_purse"] + c["paid_treasury"] for c in in_transit) > 0

    econ_tick.run_tick(world, trigger="manual", now=T0 + timedelta(minutes=30))
    third = econ_tick.run_tick(world, trigger="manual", now=T0 + timedelta(minutes=60))
    last = api.get(f"{CARAVANS}/overview").json()["last_run"]
    assert last["run_id"] == third.run_id and last["delivered"] == third.caravans_delivered >= 1


def test_overview_escrow_mismatch_is_reported(api, world):
    _two_regions(world)
    _pass(world, 1)
    _exec(world, "UPDATE econ_caravans SET paid_purse = paid_purse + 5")
    escrow = api.get(f"{CARAVANS}/overview").json()["escrow"]
    assert escrow["ok"] is False and escrow["expected"] == escrow["balance"] + 5


# --------------------------------------------------------------------------------------------- pairs PUT

def test_put_pair_normalises_and_persists(api, world):
    resp = _put_pair(api, a=2, b=1, enabled=True, duty=12.345)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["country_a"], body["country_b"], body["name_a"], body["name_b"]) == (1, 2, "Мидденгерд", "Пустошь")
    assert body["is_enabled"] is True and body["duty_pct"] == 12.35 and body["updated_at"]
    [(a, b, on, duty, by)] = _rows(world, "SELECT country_a, country_b, is_enabled, duty_pct, updated_by "
                                          "FROM econ_trade_pairs")
    assert (a, b, bool(on), Decimal(str(duty)).quantize(Decimal("0.01")), by) == (1, 2, True, Decimal("12.35"), 7)
    pair = api.get(f"{CARAVANS}/overview").json()["pairs"][0]
    assert (pair["is_enabled"], pair["duty_pct"]) == (True, 12.35)

    # second PUT updates the same row (upsert), both orders hit it
    assert _put_pair(api, a=1, b=2, enabled=False, duty=0).status_code == 200
    assert _rows(world, "SELECT COUNT(*) FROM econ_trade_pairs")[0][0] == 1
    pair = api.get(f"{CARAVANS}/overview").json()["pairs"][0]
    assert (pair["is_enabled"], pair["duty_pct"]) == (False, 0.0)


def test_put_pair_duty_bounds_are_inclusive(api, world):
    assert _put_pair(api, duty=0).json()["duty_pct"] == 0.0
    assert _put_pair(api, duty=100).json()["duty_pct"] == 100.0


def test_put_pair_same_country_is_400(api, world):
    resp = _put_pair(api, a=1, b=1)
    assert resp.status_code == 400 and resp.json()["detail"] == "Страна не может торговать сама с собой"


@pytest.mark.parametrize("a, b", [(1, 99), (99, 1), (98, 99)])
def test_put_pair_unknown_country_is_404(api, world, a, b):
    resp = _put_pair(api, a=a, b=b)
    assert resp.status_code == 404 and resp.json()["detail"] == "Страна не найдена"


@pytest.mark.parametrize("payload", [
    {"country_a": 1, "country_b": 2, "is_enabled": True, "duty_pct": -0.01},
    {"country_a": 1, "country_b": 2, "is_enabled": True, "duty_pct": 100.01},
    {"country_a": 0, "country_b": 2, "is_enabled": True, "duty_pct": 10},
    {"country_a": -1, "country_b": 2, "is_enabled": True, "duty_pct": 10},
    {"country_a": "1", "country_b": 2, "is_enabled": True, "duty_pct": 10},
    {"country_a": "1; DROP TABLE econ_trade_pairs", "country_b": 2, "is_enabled": True, "duty_pct": 10},
    {"country_a": 1, "country_b": 2, "is_enabled": "yes", "duty_pct": 10},
    {"country_a": 1, "country_b": 2, "is_enabled": True, "duty_pct": "<script>"},
    {"country_a": 1, "country_b": 2, "is_enabled": True},
    {"country_a": 1, "country_b": 2, "is_enabled": True, "duty_pct": 10, "updated_by": 1},
])
def test_put_pair_validation_is_422(api, world, payload):
    assert api.put(f"{CARAVANS}/pairs", json=payload).status_code == 422
    assert _scalar(world, "SELECT COUNT(*) FROM econ_trade_pairs") == 0


def test_enabled_pair_opens_foreign_trade_in_the_tick(api, world):
    _two_regions(world, seller_country=2)
    _pass(world, 1)
    assert _caravans(world) == []
    assert _put_pair(api, a=2, b=1, duty=25).status_code == 200
    _pass(world, 2)
    [c] = _caravans(world)
    assert (c["travel_runs"], float(c["duty_pct"]), c["duty"]) == (2, 25.0, 100)


# --------------------------------------------------------------------------------------------- list

@pytest.fixture
def listed(api, world):
    """c1 food 1 -> 2 delivered, c2 ore 1 -> 2 in transit, c3 food 3 (country 2) -> 2 cancelled, c4 wood 2 -> 3."""
    _region(world, 1)
    _region(world, 2)
    _region(world, 3, country=2)
    _insert_caravan(world, frm=1, to=2, status="delivered", run=1, finished_at=T0)
    _insert_caravan(world, frm=1, to=2, group="ore_metal", run=2)
    _insert_caravan(world, frm=3, to=2, status="cancelled", run=3, finished_at=T0, from_country=2)
    _insert_caravan(world, frm=2, to=3, group="wood", run=4, to_country=2)
    return api


def test_list_newest_first_with_names(listed):
    data = listed.get(CARAVANS).json()
    assert data["total"] == 4
    assert [i["id"] for i in data["items"]] == [4, 3, 2, 1]
    first = data["items"][-1]
    assert set(first) == {"id", "status", "group_code", "group_name", "from_region_id", "from_region_name",
                          "from_country_id", "from_country_name", "to_region_id", "to_region_name", "to_country_id",
                          "to_country_name", "units", "unit_price", "value", "duty", "duty_pct", "paid_purse",
                          "paid_treasury", "travel_runs", "runs_left", "dispatch_run_id", "finished_run_id",
                          "cancel_reason", "goods_returned", "created_at", "finished_at",
                          # FEAT-211 A4 (admin only)
                          "is_physical", "current_location_id", "current_location_name", "route_index", "route_len",
                          "next_move_at", "arrived_at", "hold_started_at", "guard_count", "stolen_units", "raid_paid",
                          "raid_status",
                          # FEAT-212 A4
                          "escort_count"}
    assert (first["status"], first["group_name"], first["from_region_name"], first["to_region_name"],
            first["from_country_name"], first["finished_run_id"], first["cancel_reason"], first["goods_returned"]) == \
        ("delivered", "Продовольствие", "Регион 1", "Регион 2", "Мидденгерд", 2, None, None)
    cancelled = data["items"][1]
    assert (cancelled["cancel_reason"], cancelled["goods_returned"], cancelled["from_country_name"]) == \
        ("destination_left", True, "Пустошь")
    assert data["items"][2]["finished_run_id"] is None and data["items"][2]["finished_at"] is None


@pytest.mark.parametrize("params, ids", [
    ({"status": "in_transit"}, [4, 2]),
    ({"status": "delivered"}, [1]),
    ({"status": "cancelled"}, [3]),
    ({"status": "all"}, [4, 3, 2, 1]),
    ({"region_id": 3}, [4, 3]),                    # from OR to
    ({"region_id": 1}, [2, 1]),
    ({"region_id": 999}, []),
    ({"group_code": "food"}, [3, 1]),
    ({"group_code": "food", "status": "delivered"}, [1]),
    ({"group_code": ""}, [4, 3, 2, 1]),            # empty = no filter
    ({"limit": 2}, [4, 3]),
    ({"limit": 2, "offset": 2}, [2, 1]),
    ({"offset": 10}, []),
])
def test_list_filters(listed, params, ids):
    data = listed.get(CARAVANS, params=params).json()
    assert [i["id"] for i in data["items"]] == ids
    if "limit" not in params and "offset" not in params:
        assert data["total"] == len(ids)
    else:
        assert data["total"] == 4


def test_list_names_null_for_deleted_entities(listed, world):
    _exec(world, "DELETE FROM Regions WHERE id = 3")
    _exec(world, "DELETE FROM Countries WHERE id = 2")
    item = next(i for i in listed.get(CARAVANS).json()["items"] if i["id"] == 4)
    assert (item["to_region_id"], item["to_region_name"], item["to_country_id"], item["to_country_name"]) == \
        (3, None, 2, None)
    assert item["from_region_name"] == "Регион 2"


@pytest.mark.parametrize("params", [
    {"status": "lost"}, {"status": "in_transit' OR '1'='1"}, {"status": "ALL"},
    {"region_id": 0}, {"region_id": -3}, {"region_id": "1 OR 1=1"},
    {"limit": 0}, {"limit": 201}, {"limit": "1; DROP TABLE econ_caravans"}, {"offset": -1},
    {"group_code": "x" * 33},
])
def test_list_validation_is_422(listed, params):
    assert listed.get(CARAVANS, params=params).status_code == 422


@pytest.mark.parametrize("code", ["salt", "food' OR 1=1 --", "'; DROP TABLE econ_caravans; --", "<script>"])
def test_list_unknown_group_is_400(listed, world, code):
    resp = listed.get(CARAVANS, params={"group_code": code})
    assert resp.status_code == 400 and resp.json()["detail"] == "Неизвестная группа товаров"
    assert listed.get(CARAVANS).json()["total"] == 4                  # table intact


def test_list_limit_bounds_inclusive(listed):
    assert listed.get(CARAVANS, params={"limit": 1}).status_code == 200
    assert listed.get(CARAVANS, params={"limit": 200}).status_code == 200


# --------------------------------------------------------------------------------------------- sim params

def _put_sim(c, **params):
    return c.put(f"{BASE}/sim", json={"tick_enabled": True, "params": params})


def test_sim_accepts_the_caravan_params_without_emit(world):
    _as(SETTINGS)
    c = TestClient(app)
    values = {"caravans_enabled": 0, "caravan_surplus_share": 0.4, "caravan_purse_share": 0.1,
              "caravan_treasury_food_share": 0.75, "caravan_travel_domestic": 2, "caravan_travel_foreign": 8,
              "caravan_min_value": 50, "caravan_max_per_run": 5000}
    resp = _put_sim(c, **values)
    assert resp.status_code == 200, resp.text
    params = resp.json()["params"]
    assert {k: params[k] for k in values} == values
    overview = c.get(f"{CARAVANS}/overview").json()["params"]
    assert {k: overview[k] for k in values} == values


@pytest.mark.parametrize("key, value", [
    ("caravans_enabled", 2), ("caravans_enabled", -1), ("caravan_surplus_share", 1.01),
    ("caravan_surplus_share", -0.1), ("caravan_purse_share", 2), ("caravan_treasury_food_share", -1),
    ("caravan_travel_domestic", 0), ("caravan_travel_domestic", 9), ("caravan_travel_foreign", 0),
    ("caravan_travel_foreign", 9), ("caravan_min_value", 0), ("caravan_min_value", 1_000_001),
    ("caravan_max_per_run", 0), ("caravan_max_per_run", 5001),
])
def test_sim_caravan_param_bounds(api, key, value):
    assert _put_sim(api, **{key: value}).status_code in (400, 422)
    params = api.get(f"{CARAVANS}/overview").json()["params"]
    assert params["caravans_enabled"] == 1 and params["caravan_travel_domestic"] == 1


# --------------------------------------------------------------------------------------------- summary

def test_summary_caravan_escrow_fields(api, world):
    _two_regions(world)
    summary = api.get(f"{BASE}/summary").json()
    assert summary["totals"]["caravan_escrow"] == 0
    assert (summary["invariant"]["caravan_escrow_expected"], summary["invariant"]["caravan_escrow_actual"]) == (0, 0)
    assert summary["invariant"]["ok"] is True

    _pass(world, 1)
    summary = api.get(f"{BASE}/summary").json()
    assert summary["totals"]["caravan_escrow"] == 400
    assert summary["invariant"]["caravan_escrow_expected"] == summary["invariant"]["caravan_escrow_actual"] == 400
    assert summary["invariant"]["ok"] is True and summary["invariant"]["ledger_sum"] == 0

    _exec(world, "UPDATE econ_caravans SET paid_purse = 1")
    summary = api.get(f"{BASE}/summary").json()
    assert summary["invariant"]["caravan_escrow_expected"] == 1 and summary["invariant"]["ok"] is False


def test_escrow_cannot_be_adjusted_by_admin(api, world):
    _two_regions(world)
    _pass(world, 1)
    account_id = _scalar(world, "SELECT id FROM econ_accounts WHERE kind = 'caravan_escrow' AND ref_id = 0")
    resp = api.post(f"{BASE}/adjust", json={"account_id": account_id, "delta": -100,
                                            "comment": "попытка корректировки"})
    assert resp.status_code == 400 and resp.json()["detail"] == "Этот счёт нельзя корректировать"
    assert _scalar(world, "SELECT balance FROM econ_accounts WHERE id = :i", i=account_id) == 400


# --------------------------------------------------------------------------------------------- region card

def test_card_lines_in_transit_then_recent(api, world):
    _two_regions(world)
    _pass(world, 1, now=_now())
    buyer, seller = _card(api, 2), _card(api, 1)
    assert buyer["caravans"] == {"incoming": [{
        "group_code": "food", "group_name": "Продовольствие", "region_id": 1, "region_name": "Регион 1",
        "country_name": None, "foreign": False, "in_transit": True}], "outgoing": []}
    assert seller["caravans"] == {"incoming": [], "outgoing": [{
        "group_code": "food", "group_name": "Продовольствие", "region_id": 2, "region_name": "Регион 2",
        "country_name": None, "foreign": False, "in_transit": True}]}

    _pass(world, 2, now=_now())
    assert _card(api, 2)["caravans"]["incoming"][0]["in_transit"] is False         # «Привезли»
    assert _card(api, 1)["caravans"]["outgoing"][0]["in_transit"] is False         # «Вывезли»
    # older than a day: gone
    _exec(world, "UPDATE econ_caravans SET finished_at = :t", t=_now() - timedelta(hours=crud.CARD_RECENT_HOURS + 1))
    assert _card(api, 2)["caravans"] == {"incoming": [], "outgoing": []}


def test_card_is_words_only(api, world):
    _two_regions(world, seller_country=2)
    _pair(world, 1, 2)
    _pass(world, 1, now=_now())
    card = _card(api, 2)
    [line] = card["caravans"]["incoming"]
    assert set(line) == CARD_LINE_KEYS
    assert (line["foreign"], line["country_name"], line["region_name"]) == (True, "Пустошь", "Регион 1")
    numeric = {k for k, v in line.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    assert numeric == {"region_id"}
    assert not ({"units", "value", "duty", "price", "unit_price", "paid_purse"} & set(str(card["caravans"]).split("'")))


def test_card_hides_cancelled_and_dedups_with_in_transit_winning(api, world):
    _region(world, 1)
    _region(world, 2)
    now = _now()
    _insert_caravan(world, frm=1, to=2, status="delivered", run=1, finished_at=now)
    _insert_caravan(world, frm=1, to=2, status="in_transit", run=2)
    _insert_caravan(world, frm=1, to=2, status="delivered", run=3, finished_at=now)
    _insert_caravan(world, frm=1, to=2, group="wood", status="cancelled", run=4, finished_at=now)
    card = _card(api, 2)["caravans"]
    assert [(l["group_code"], l["region_id"], l["in_transit"]) for l in card["incoming"]] == [("food", 1, True)]


def test_card_order_and_limit(api, world):
    _region(world, 2)
    now = _now()
    groups = ["food", "ore_metal", "wood", "herbs", "hides_textiles", "magic", "weapons", "armor"]
    for i, group in enumerate(groups):
        rid = 10 + i
        _exec(world, "INSERT INTO Regions (id, name, country_id) VALUES (:i, :n, 1)", i=rid, n=f"Регион {rid}")
        delivered = i % 2 == 0
        _insert_caravan(world, frm=rid, to=2, group=group, run=i + 1,
                        status="delivered" if delivered else "in_transit", finished_at=now if delivered else None)
    lines = _card(api, 2)["caravans"]["incoming"]
    assert len(lines) == crud.CARD_MAX_LINES == 6
    flags = [l["in_transit"] for l in lines]
    assert flags == sorted(flags, reverse=True)                          # in transit first
    order = {code: so for code, so in _rows(world, "SELECT code, sort_order FROM econ_goods_groups")}
    transit = [order[l["group_code"]] for l in lines if l["in_transit"]]
    recent = [order[l["group_code"]] for l in lines if not l["in_transit"]]
    assert transit == sorted(transit) and recent == sorted(recent)
    assert sum(flags) == 4                                               # all four in-transit lines kept


def test_card_drops_deleted_other_region(api, world):
    _two_regions(world)
    _pass(world, 1, now=_now())
    _exec(world, "DELETE FROM Regions WHERE id = 1")
    assert _card(api, 2)["caravans"]["incoming"] == []


def test_card_hidden_shapes_have_empty_caravans(api, world):
    _two_regions(world)
    _pass(world, 1, now=_now())
    _exec(world, "UPDATE econ_regions SET population = 0 WHERE region_id = 2")
    card = _card(api, 2)
    assert card["participating"] is False and card["caravans"] == {"incoming": [], "outgoing": []}
    assert _card(api, 999)["caravans"] == {"incoming": [], "outgoing": []}
    assert _card(api, 0)["caravans"] == {"incoming": [], "outgoing": []}


def test_card_is_public(world):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    _two_regions(world)
    _pass(world, 1, now=_now())
    resp = TestClient(app).get("/characters/economy/regions/2/card")
    assert resp.status_code == 200 and resp.json()["caravans"]["incoming"]

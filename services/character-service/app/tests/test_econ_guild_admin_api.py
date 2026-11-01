"""FEAT-193 QA (#10): admin guild API (``GET /characters/admin/economy/guild``, contract 3.10), the 9 guild params
of the sim PUT (3.4) and ``guild_wants`` on the public region card (3.9), on SQLite.

World: ``build_world`` of ``test_econ_guild_api.py`` (region 10 with open wood / food orders, budget 5 000, guild
masters 60 alive + 61 dead @10, 62 @20, 64 nowhere).
"""

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import econ_core as core
import econ_ledger
import economy_api
import economy_guild_crud as guild_crud
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.test_econ_guild_api import (
    ALPHA, G_20, G_DEAD, G_NPC, SOURCE, _exec, _q, add_order, build_world, set_budget,
)
from tests.test_econ_tick import factory  # noqa: F401  (factory is a fixture)

BASE = "/characters/admin/economy"
READ = ["economy:read"]
SETTINGS = ["economy:read", "economy:settings"]
ALL_PERMS = ["economy:read", "economy:emit", "economy:adjust", "economy:settings"]
GUILD_PARAMS = {
    "guild_enabled": 1, "guild_markup_pct": 20.0, "guild_open_threshold_pct": 80.0, "guild_min_order_value": 50,
    "guild_purse_share": 0.25, "guild_treasury_food_share": 0.25, "guild_xp_per_mark": 0.1,
    "guild_xp_per_mark_merchant_items": 0.05, "guild_xp_daily_cap": 200,
}


@pytest.fixture
def world(factory):
    build_world(factory)

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


def _as(permissions, role="moderator"):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=7, username="tester", role=role, permissions=list(permissions))


@pytest.fixture
def api(world):
    _as(READ)
    return TestClient(app)


def _guild(api, **params):
    return api.get(f"{BASE}/guild", params=params)


# --------------------------------------------------------------------------------------------- permissions

def test_unauthenticated_is_401(world):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    assert TestClient(app).get(f"{BASE}/guild").status_code == 401


def test_plain_user_is_403(world):
    _as([], role="user")
    resp = TestClient(app).get(f"{BASE}/guild")
    assert resp.status_code == 403 and resp.json()["detail"] == "Недостаточно прав"


def test_settings_without_read_is_403_and_read_is_enough(world):
    _as(["economy:settings"])
    assert TestClient(app).get(f"{BASE}/guild").status_code == 403
    _as(READ)
    assert TestClient(app).get(f"{BASE}/guild").status_code == 200


# --------------------------------------------------------------------------------------------- view

def test_admin_view_params_totals_regions_and_open_orders(api, world):
    resp = _guild(api)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["params"] == GUILD_PARAMS
    assert data["totals"] == {"open": 2, "units_left_value": 700, "paid_last_7d": 0, "hand_ins_last_7d": 0,
                              "xp_last_7d": 0}                       # 100 x 5 (wood) + 100 x 2 (food)
    regions = {r["region_id"]: r for r in data["regions"]}
    assert sorted(regions) == [10, 20]                               # participating regions only
    r10 = regions[10]
    assert (r10["region_name"], r10["guild_budget"], r10["guild_food_budget"], r10["open_orders"]) == \
        ("Регион 10", 5000, 0, 2)
    assert [(m["npc_id"], m["npc_status"], m["location_name"]) for m in r10["masters"]] == [
        (G_NPC, "alive", "Площадь"), (G_DEAD, "dead", "Площадь")]
    assert [m["npc_id"] for m in regions[20]["masters"]] == [G_20]
    assert regions[20]["open_orders"] == 0
    assert data["total"] == 2
    assert [(i["group_code"], i["group_name"], i["status"]) for i in data["items"]] == [
        ("food", "Продовольствие", "open"), ("wood", "Древесина", "open")]        # newest first
    wood = data["items"][1]
    assert (wood["region_name"], wood["units_total"], wood["units_left"], wood["price_mult"], wood["markup_pct"],
            wood["close_reason"], wood["closed_at"]) == ("Регион 10", 100.0, 100.0, 1.0, 20.0, None, None)


def test_region_without_master_has_empty_masters(api, world):
    _exec(world, "UPDATE characters SET current_location_id = 100 WHERE id = :i", i=G_20)
    regions = {r["region_id"]: r for r in _guild(api).json()["regions"]}
    assert regions[20]["masters"] == []


def _more_orders(f):
    add_order(f, 10, "ore_metal", 40, status="closed")
    add_order(f, 10, "herbs", 30, status="filled")
    add_order(f, 20, "wood", 50)
    add_order(f, 99, "wood", 10, status="closed")                   # region deleted from the world


def test_status_filters(api, world):
    _more_orders(world)
    def codes(**p):
        data = _guild(api, **p).json()
        return data["total"], [(i["region_id"], i["group_code"], i["status"]) for i in data["items"]]
    assert codes() == (3, [(20, "wood", "open"), (10, "food", "open"), (10, "wood", "open")])
    assert codes(status="closed") == (3, [(99, "wood", "closed"), (10, "herbs", "filled"),
                                          (10, "ore_metal", "closed")])
    assert codes(status="filled") == (1, [(10, "herbs", "filled")])
    assert codes(status="all")[0] == 6
    assert codes(status="all", region_id=10)[0] == 4
    assert codes(status="all", group_code="wood")[0] == 3
    assert codes(status="all", region_id=10, group_code="wood") == (1, [(10, "wood", "open")])
    closed = _guild(api, status="closed").json()["items"]
    assert closed[0]["region_name"] is None                          # LEFT JOIN, deleted region


def test_pagination(api, world):
    _more_orders(world)
    page = _guild(api, status="all", limit=2, offset=0).json()
    assert page["total"] == 6 and len(page["items"]) == 2
    ids = [i["id"] for i in page["items"]]
    nxt = _guild(api, status="all", limit=2, offset=2).json()["items"]
    assert ids == sorted(ids, reverse=True) and nxt[0]["id"] < ids[-1]
    assert _guild(api, status="all", limit=200, offset=100).json()["items"] == []


@pytest.mark.parametrize("params", [
    {"status": "bogus"}, {"status": "open' OR 1=1 --"}, {"status": ""}, {"region_id": 0}, {"region_id": "x"},
    {"limit": 0}, {"limit": 201}, {"offset": -1}, {"group_code": "x" * 33},
])
def test_query_validation_is_422(api, world, params):
    assert _guild(api, **params).status_code == 422


@pytest.mark.parametrize("group_code", ["nope", "wood' OR 1=1 --", "<script>alert(1)</script>"])
def test_unknown_or_injection_like_group_is_400(api, world, group_code):
    resp = _guild(api, group_code=group_code)
    assert resp.status_code == 400 and resp.json()["detail"] == guild_crud.MSG_UNKNOWN_GROUP


def test_totals_count_last_7_days_of_hand_ins_and_xp(api, world):
    db = world()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_GUILD_ORDER, source_service=SOURCE, apply_tax=False,
                                   region_id=10, idempotency_key="guild:1:req-00000001",
                                   legs=[core.Leg(core.AccountRef.purse(10), core.AccountRef.character(ALPHA), 60),
                                         core.Leg(core.AccountRef.region(10), core.AccountRef.character(ALPHA), 15)])
        db.commit()
    finally:
        db.close()
    today = guild_crud.today_utc()
    _exec(world, "INSERT INTO econ_guild_xp_days (character_id, day, xp) VALUES (1, :a, 6), (2, :b, 4), (1, :c, 50)",
          a=today, b=today - timedelta(days=6), c=today - timedelta(days=7))
    totals = _guild(api).json()["totals"]
    assert (totals["paid_last_7d"], totals["hand_ins_last_7d"], totals["xp_last_7d"]) == (75, 1, 10)


# --------------------------------------------------------------------------------------------- sim PUT (3.4)

def _put_sim(c, **params):
    return c.put(f"{BASE}/sim", json={"tick_enabled": True, "params": params})


def test_sim_put_accepts_the_nine_guild_params_without_emit(world):
    _as(SETTINGS)
    c = TestClient(app)
    values = {"guild_enabled": 0, "guild_markup_pct": 35.5, "guild_open_threshold_pct": 60.0,
              "guild_min_order_value": 120, "guild_purse_share": 0.4, "guild_treasury_food_share": 0.1,
              "guild_xp_per_mark": 0.2, "guild_xp_per_mark_merchant_items": 0.02, "guild_xp_daily_cap": 500}
    resp = _put_sim(c, **values)
    assert resp.status_code == 200, resp.text
    assert {k: resp.json()["params"][k] for k in values} == values
    assert _guild(c).json()["params"] == values


@pytest.mark.parametrize("key, value", [
    ("guild_enabled", 2), ("guild_enabled", -1), ("guild_markup_pct", -0.1), ("guild_markup_pct", 200.1),
    ("guild_open_threshold_pct", 0.5), ("guild_open_threshold_pct", 101), ("guild_min_order_value", 0),
    ("guild_min_order_value", 1_000_001), ("guild_purse_share", 1.01), ("guild_treasury_food_share", -0.5),
    ("guild_xp_per_mark", 10.5), ("guild_xp_per_mark_merchant_items", -1), ("guild_xp_daily_cap", -1),
    ("guild_xp_daily_cap", 1_000_001),
])
def test_sim_put_guild_bounds(world, key, value):
    _as(ALL_PERMS, role="admin")
    c = TestClient(app)
    assert _put_sim(c, **{key: value}).status_code in (400, 422)
    assert c.get(f"{BASE}/sim").json()["params"][key] == GUILD_PARAMS[key]


def test_sim_put_needs_settings(world):
    _as(READ)
    assert _put_sim(TestClient(app), guild_markup_pct=50.0).status_code == 403


# --------------------------------------------------------------------------------------------- region card (3.9)

def _card(region_id):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    resp = TestClient(app).get(f"/characters/economy/regions/{region_id}/card")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_card_lists_wanted_groups_words_only(world):
    card = _card(10)
    assert card["participating"] is True
    assert card["guild_wants"] == [{"group_code": "food", "group_name": "Продовольствие"},
                                   {"group_code": "wood", "group_name": "Древесина"}]      # group order
    assert not any(ch.isdigit() for ch in json.dumps(card["guild_wants"], ensure_ascii=False))
    assert _card(20)["guild_wants"] == []                           # no orders there


def test_card_hides_orders_without_a_living_guild_master(world):
    _exec(world, "UPDATE characters SET npc_status = 'dead' WHERE id = :i", i=G_NPC)
    assert _card(10)["guild_wants"] == []                           # 61 is dead too
    _exec(world, "UPDATE characters SET npc_status = 'alive' WHERE id = :i", i=G_DEAD)
    assert len(_card(10)["guild_wants"]) == 2


def test_card_hides_orders_that_cannot_pay(world):
    set_budget(world, budget=0, food=0)
    assert _card(10)["guild_wants"] == []
    set_budget(world, budget=0, food=50)
    assert [w["group_code"] for w in _card(10)["guild_wants"]] == ["food"]   # the treasury tops up food only


def test_card_hides_exhausted_orders(world):
    _exec(world, "UPDATE econ_guild_orders SET units_left = 0 WHERE group_code = 'wood'")
    assert [w["group_code"] for w in _card(10)["guild_wants"]] == ["food"]


def test_card_hidden_shape_has_empty_guild_wants(world):
    _exec(world, "UPDATE econ_regions SET population = 0 WHERE region_id = 10")
    card = _card(10)
    assert card["participating"] is False and card["guild_wants"] == []
    assert _card(0)["guild_wants"] == []
    assert _card(424242)["guild_wants"] == []

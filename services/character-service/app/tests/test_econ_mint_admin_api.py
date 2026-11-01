"""FEAT-191 QA (#10): admin mint API (contract 3.10), the sim money-param guard and ``has_mint`` on the public
region card, on SQLite. World = ``test_econ_mint_api.build_world`` (see its docstring).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import econ_core as core
import econ_ledger
import economy_api
import economy_mint_crud as mint_crud
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.test_econ_mint_api import (
    BANKER, BREAD, INGOT, LIMIT, MINTER, MINTER_DEAD, MINTER_NO_CAPITAL, MINTER_PORT, ORE, ORE_OFF, ORE_TOOLS,
    _exec, _q, _rows, build_world,
)
from tests.test_econ_tick import factory  # noqa: F401  (factory is a fixture)

BASE = "/characters/admin/economy"
READ = ["economy:read"]
SETTINGS = ["economy:read", "economy:settings"]
ALL_PERMS = ["economy:read", "economy:emit", "economy:adjust", "economy:settings"]


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
    _as(ALL_PERMS, role="admin")
    return TestClient(app)


def _country(api, country_id):
    data = api.get(f"{BASE}/mint").json()
    return next(c for c in data["countries"] if c["country_id"] == country_id)


def _put_country(api, country_id=1, **body):
    payload = {"capital_region_id": None, "season_limit": None, "is_enabled": True}
    payload.update(body)
    return api.put(f"{BASE}/mint/countries/{country_id}", json=payload)


# --------------------------------------------------------------------------------------------- permissions

def test_unauthenticated_is_401(world):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    anon = TestClient(app)
    assert anon.get(f"{BASE}/mint").status_code == 401
    assert anon.get(f"{BASE}/mint/items").status_code == 401
    assert anon.get(f"{BASE}/mint/quotas").status_code == 401
    assert _put_country(anon).status_code == 401
    assert anon.put(f"{BASE}/mint/items/{ORE}", json={"marks_per_item": 1, "is_enabled": True}).status_code == 401
    assert anon.delete(f"{BASE}/mint/items/{ORE}").status_code == 401


def test_plain_user_is_403_everywhere(world):
    _as([], role="user")
    c = TestClient(app)
    for resp in (c.get(f"{BASE}/mint"), c.get(f"{BASE}/mint/items"), c.get(f"{BASE}/mint/quotas"),
                 _put_country(c), c.put(f"{BASE}/mint/items/{ORE}", json={"marks_per_item": 1, "is_enabled": True}),
                 c.delete(f"{BASE}/mint/items/{ORE}")):
        assert resp.status_code == 403 and resp.json()["detail"] == "Недостаточно прав"


def test_read_permission_reads_but_cannot_write(world):
    _as(READ)
    c = TestClient(app)
    assert c.get(f"{BASE}/mint").status_code == 200
    assert c.get(f"{BASE}/mint/items").status_code == 200
    assert c.get(f"{BASE}/mint/quotas").status_code == 200
    assert _put_country(c).status_code == 403
    assert c.put(f"{BASE}/mint/items/{ORE}", json={"marks_per_item": 1, "is_enabled": True}).status_code == 403
    assert c.delete(f"{BASE}/mint/items/{ORE}").status_code == 403


def test_settings_without_emit_cannot_authorise_money(world):
    _as(SETTINGS)
    c = TestClient(app)
    assert _put_country(c, season_limit=5).status_code == 403
    assert c.put(f"{BASE}/mint/items/{ORE}", json={"marks_per_item": 99, "is_enabled": True}).status_code == 403
    assert c.delete(f"{BASE}/mint/items/{ORE}").status_code == 403
    assert _q(world, "SELECT COUNT(*) FROM econ_mints") == 0
    assert _q(world, "SELECT marks_per_item FROM econ_mint_items WHERE item_id = :i", i=ORE) == 12


def test_emit_without_settings_cannot_write_either(world):
    _as(["economy:read", "economy:emit"])
    assert _put_country(TestClient(app)).status_code == 403


# --------------------------------------------------------------------------------------------- admin view

def test_admin_view_lists_countries_with_capital_minters_and_counters(api, world):
    _exec(world, "INSERT INTO econ_mint_seasons (country_id, period_index, minted_court, minted_players, "
                 "ore_units_court, ore_units_players, created_at) VALUES (1, 0, 300, 200, 0, 0, :t)",
          t=mint_crud.now_utc())
    resp = api.get(f"{BASE}/mint")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["period"]["index"] == 0 and data["period"]["year"] == 1
    assert data["params"] == {"mint_season_limit": LIMIT, "mint_court_marks_per_unit": 8.0,
                              "mint_court_threshold_pct": 100.0, "quota_season_amount": 0}
    c1, c2 = data["countries"]
    assert (c1["country_id"], c1["country_name"], c1["capital_region_id"], c1["capital_source"]) == \
        (1, "Мидденгерд", 10, "auto")
    assert c1["working"] is True and c1["closed_reason"] is None and c1["is_enabled"] is True
    assert (c1["season_limit"], c1["season_limit_override"], c1["minted_court"], c1["minted_players"],
            c1["remaining"]) == (LIMIT, None, 300, 200, LIMIT - 500)
    assert c1["ore_stock"] == 100.0 and c1["ore_norm"] == 200.0
    assert [r["region_id"] for r in c1["candidates"]] == [10, 20]            # the capital template first
    minters = {m["npc_id"]: m for m in c1["minters"]}
    assert sorted(minters) == [MINTER, MINTER_DEAD, MINTER_PORT]
    assert minters[MINTER]["in_capital"] is True and minters[MINTER_PORT]["in_capital"] is False
    assert minters[MINTER_DEAD]["npc_status"] == "dead"
    assert BANKER not in minters
    assert c2["capital_source"] == "none" and c2["working"] is False
    assert c2["closed_reason"] == mint_crud.REASON_NO_CAPITAL
    assert [m["npc_id"] for m in c2["minters"]] == [MINTER_NO_CAPITAL]


def test_admin_remaining_is_zero_when_the_mint_is_closed(api, world):
    """Review note 1: the admin card follows the player view — a closed mint has nothing remaining."""
    c2 = _country(api, 2)                                                   # no capital -> closed
    assert c2["working"] is False and c2["season_limit"] == LIMIT and c2["remaining"] == 0
    _exec(world, "INSERT INTO econ_mints (country_id, is_enabled) VALUES (1, 0)")
    c1 = _country(api, 1)
    assert c1["working"] is False and c1["closed_reason"] == mint_crud.REASON_DISABLED and c1["remaining"] == 0
    _exec(world, "UPDATE econ_mints SET is_enabled = 1 WHERE country_id = 1")
    assert _country(api, 1)["remaining"] == LIMIT


# --------------------------------------------------------------------------------------------- PUT country

def test_put_country_manual_capital_limit_and_back_to_auto(api, world):
    resp = _put_country(api, capital_region_id=20, season_limit=777, is_enabled=True)
    assert resp.status_code == 200, resp.text
    c = resp.json()
    assert (c["capital_region_id"], c["capital_source"], c["capital_override_id"]) == (20, "manual", 20)
    assert (c["season_limit"], c["season_limit_override"], c["working"]) == (777, 777, True)
    assert _rows(world, "SELECT capital_region_id, season_limit, is_enabled, updated_by FROM econ_mints") == \
        [(20, 777, 1, 7)]

    resp = _put_country(api, capital_region_id=None, season_limit=None, is_enabled=False)
    c = resp.json()
    assert (c["capital_region_id"], c["capital_source"], c["season_limit"], c["working"], c["closed_reason"]) == \
        (10, "auto", LIMIT, False, mint_crud.REASON_DISABLED)
    assert _q(world, "SELECT COUNT(*) FROM econ_mints") == 1


def test_put_country_foreign_region_is_400_and_unknown_country_404(api, world):
    resp = _put_country(api, capital_region_id=30)                    # region of country 2
    assert resp.status_code == 400 and resp.json()["detail"] == mint_crud.MSG_REGION_FOREIGN
    resp = _put_country(api, capital_region_id=9999)
    assert resp.status_code == 400 and resp.json()["detail"] == mint_crud.MSG_REGION_FOREIGN
    resp = _put_country(api, country_id=99)
    assert resp.status_code == 404 and resp.json()["detail"] == mint_crud.MSG_COUNTRY_NOT_FOUND
    assert _q(world, "SELECT COUNT(*) FROM econ_mints") == 0


def test_stale_override_is_reported(api, world):
    _exec(world, "INSERT INTO econ_mints (country_id, capital_region_id, is_enabled) VALUES (1, 30, 1)")
    c = _country(api, 1)
    assert (c["capital_region_id"], c["capital_source"], c["capital_override_id"], c["override_stale"]) == \
        (10, "auto", 30, True)


@pytest.mark.parametrize("body", [
    {"capital_region_id": "10; DROP TABLE econ_mints", "season_limit": None, "is_enabled": True},
    {"capital_region_id": None, "season_limit": -1, "is_enabled": True},
    {"capital_region_id": None, "season_limit": 1_000_000_001, "is_enabled": True},
    {"capital_region_id": 0, "season_limit": None, "is_enabled": True},
    {"capital_region_id": None, "season_limit": None, "is_enabled": "yes"},
    {"capital_region_id": None, "season_limit": None},                         # every key is required
    {"season_limit": None, "is_enabled": True},
    {"capital_region_id": None, "season_limit": None, "is_enabled": True, "extra": 1},
])
def test_put_country_validation(api, world, body):
    assert api.put(f"{BASE}/mint/countries/1", json=body).status_code == 422
    assert _q(world, "SELECT COUNT(*) FROM econ_mints") == 0


# --------------------------------------------------------------------------------------------- items

def test_items_list_marks_invalid_groups(api, world):
    resp = api.get(f"{BASE}/mint/items")
    assert resp.status_code == 200
    items = {i["item_id"]: i for i in resp.json()}
    assert sorted(items) == [ORE, INGOT, ORE_TOOLS, ORE_OFF]
    assert items[ORE] == {"item_id": ORE, "name": "Железная руда", "image": None, "item_type": "resource",
                          "resource_subcategory": "ore", "effective_group": "ore_metal", "marks_per_item": 12,
                          "is_enabled": True, "valid": True}
    assert items[ORE_TOOLS]["valid"] is False and items[ORE_TOOLS]["effective_group"] == "tools"
    assert items[ORE_OFF]["is_enabled"] is False and items[ORE_OFF]["valid"] is True


def test_item_upsert_update_and_delete(api, world):
    resp = api.put(f"{BASE}/mint/items/{ORE}", json={"marks_per_item": 15, "is_enabled": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["marks_per_item"] == 15 and resp.json()["is_enabled"] is False
    assert _rows(world, "SELECT marks_per_item, is_enabled, updated_by FROM econ_mint_items WHERE item_id = :i",
                 i=ORE) == [(15, 0, 7)]
    _exec(world, "DELETE FROM econ_mint_items WHERE item_id = :i", i=INGOT)
    resp = api.put(f"{BASE}/mint/items/{INGOT}", json={"marks_per_item": 1_000_000, "is_enabled": True})
    assert resp.status_code == 200 and resp.json()["valid"] is True            # inserted
    assert api.delete(f"{BASE}/mint/items/{INGOT}").status_code == 204
    resp = api.delete(f"{BASE}/mint/items/{INGOT}")
    assert resp.status_code == 404 and resp.json()["detail"] == mint_crud.MSG_ITEM_NOT_FOUND
    assert _q(world, "SELECT COUNT(*) FROM econ_mint_items WHERE item_id = :i", i=INGOT) == 0


def test_item_upsert_refusals(api, world):
    resp = api.put(f"{BASE}/mint/items/9999", json={"marks_per_item": 5, "is_enabled": True})
    assert resp.status_code == 404 and resp.json()["detail"] == mint_crud.MSG_ITEM_NOT_FOUND
    for item_id in (BREAD, ORE_TOOLS):
        resp = api.put(f"{BASE}/mint/items/{item_id}", json={"marks_per_item": 5, "is_enabled": True})
        assert resp.status_code == 400 and resp.json()["detail"] == mint_crud.MSG_ITEM_NOT_ORE, item_id
    assert _q(world, "SELECT COUNT(*) FROM econ_mint_items WHERE item_id = :i", i=BREAD) == 0
    assert _q(world, "SELECT marks_per_item FROM econ_mint_items WHERE item_id = :i", i=ORE_TOOLS) == 5


@pytest.mark.parametrize("body", [
    {"marks_per_item": 0, "is_enabled": True},
    {"marks_per_item": 1_000_001, "is_enabled": True},
    {"marks_per_item": 2.5, "is_enabled": True},
    {"marks_per_item": "5' OR '1'='1", "is_enabled": True},
    {"marks_per_item": 5},
    {"marks_per_item": 5, "is_enabled": True, "comment": "x"},
])
def test_item_upsert_validation(api, world, body):
    assert api.put(f"{BASE}/mint/items/{ORE}", json=body).status_code == 422
    assert _q(world, "SELECT marks_per_item FROM econ_mint_items WHERE item_id = :i", i=ORE) == 12


def test_item_path_injection_is_422(api, world):
    assert api.put(f"{BASE}/mint/items/500%20OR%201=1", json={"marks_per_item": 5, "is_enabled": True}) \
        .status_code == 422
    assert api.delete(f"{BASE}/mint/items/500;DROP").status_code == 422
    assert _q(world, "SELECT COUNT(*) FROM econ_mint_items") == 4


# --------------------------------------------------------------------------------------------- quotas

def _post_quota(world, period_index, amount, regions):
    db = world()
    try:
        econ_ledger.post_operation(
            db, op_type=core.OP_SEASON_QUOTA, source_service="character-service", apply_tax=False,
            idempotency_key=f"season_quota:p{period_index}",
            legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.region(rid), amt) for rid, amt in regions],
            metadata={"period_index": period_index, "year": period_index // 4 + 1, "season": "spring",
                      "amount": amount, "regions": {str(r): a for r, a in regions}, "run_id": 1})
        db.commit()
    finally:
        db.close()


def test_quotas_list_newest_first_with_limit(api, world):
    assert api.get(f"{BASE}/mint/quotas").json() == []
    _post_quota(world, 0, 1000, [(10, 600), (20, 400)])
    _post_quota(world, 1, 500, [(10, 500)])
    resp = api.get(f"{BASE}/mint/quotas")
    assert resp.status_code == 200
    rows = resp.json()
    assert [(r["period_index"], r["amount"], r["regions"], r["year"], r["season"]) for r in rows] == \
        [(1, 500, 1, 1, "spring"), (0, 1000, 2, 1, "spring")]
    assert rows[0]["operation_id"] > rows[1]["operation_id"] and rows[0]["created_at"]
    assert len(api.get(f"{BASE}/mint/quotas", params={"limit": 1}).json()) == 1
    for bad in (0, 101, "1; DROP TABLE econ_operations"):
        assert api.get(f"{BASE}/mint/quotas", params={"limit": bad}).status_code == 422


# --------------------------------------------------------------------------------------------- sim money guard

def _put_sim(c, **params):
    return c.put(f"{BASE}/sim", json={"tick_enabled": True, "params": params})


def test_sim_money_params_need_emit(world):
    _as(SETTINGS)
    c = TestClient(app)
    for key, value in (("quota_season_amount", 5000), ("mint_season_limit", 1), ("mint_court_marks_per_unit", 9.5)):
        resp = _put_sim(c, **{key: value})
        assert resp.status_code == 403 and resp.json()["detail"] == economy_api.MSG_NEED_EMIT, key
    # unchanged money values and the (non-money) threshold are fine without emit
    resp = _put_sim(c, mint_season_limit=LIMIT, mint_court_marks_per_unit=8.0, mint_court_threshold_pct=50.0)
    assert resp.status_code == 200, resp.text
    assert resp.json()["params"]["mint_court_threshold_pct"] == 50.0
    assert resp.json()["params"]["mint_season_limit"] == LIMIT

    _as(["economy:read", "economy:settings", "economy:emit"])
    resp = _put_sim(TestClient(app), quota_season_amount=5000, mint_season_limit=20_000)
    assert resp.status_code == 200, resp.text
    assert resp.json()["params"]["quota_season_amount"] == 5000
    assert resp.json()["params"]["mint_season_limit"] == 20_000


def test_sim_money_params_bounds(api, world):
    assert _put_sim(api, quota_season_amount=-1).status_code in (400, 422)
    assert _put_sim(api, mint_season_limit=1_000_000_001).status_code in (400, 422)
    assert _put_sim(api, mint_court_marks_per_unit=0).status_code in (400, 422)
    assert _put_sim(api, mint_court_threshold_pct=1001).status_code in (400, 422)
    assert api.get(f"{BASE}/sim").json()["params"]["quota_season_amount"] == 0


# --------------------------------------------------------------------------------------------- region card

def _card(region_id):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    resp = TestClient(app).get(f"/characters/economy/regions/{region_id}/card")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_region_card_has_mint_in_both_shapes(world):
    card = _card(10)
    assert card["participating"] is True and card["has_mint"] is True
    card = _card(20)
    assert card["participating"] is True and card["has_mint"] is False         # not the capital
    assert _card(30)["has_mint"] is False                                       # country without a capital
    _exec(world, "INSERT INTO Regions (id, name, country_id) VALUES (40, 'Глушь', 1)")
    hidden = _card(40)
    assert hidden["participating"] is False and hidden["has_mint"] is False
    assert _card(999)["has_mint"] is False
    assert _card(0)["has_mint"] is False

    # a manual capital that does not take part in the economy: hidden shape, mint closed
    _exec(world, "INSERT INTO econ_mints (country_id, capital_region_id, is_enabled) VALUES (1, 40, 1)")
    assert _card(40)["has_mint"] is False and _card(10)["has_mint"] is False


def test_region_card_has_mint_follows_the_status(world):
    _exec(world, "INSERT INTO econ_mints (country_id, is_enabled) VALUES (1, 0)")
    assert _card(10)["has_mint"] is False
    _exec(world, "UPDATE econ_mints SET is_enabled = 1, capital_region_id = 20")
    assert _card(10)["has_mint"] is False and _card(20)["has_mint"] is True


# --------------------------------------------------------------------------------------------- ore search (frontend)

def test_item_groups_filter_by_ore_metal_for_the_mint_search(api, world):
    """EconomyMint.tsx searches ore via GET /admin/economy/item-groups?group=ore_metal (effective group)."""
    _exec(world, "CREATE TABLE IF NOT EXISTS quest_objectives (id INTEGER PRIMARY KEY, quest_id INTEGER NOT NULL "
                 "DEFAULT 1, objective_type VARCHAR(32) NOT NULL, target_id INTEGER NULL)")
    resp = api.get(f"{BASE}/item-groups", params={"group": "ore_metal", "page": 1, "page_size": 50})
    assert resp.status_code == 200, resp.text
    ids = sorted(i["item_id"] for i in resp.json()["items"])
    assert ids == [ORE, INGOT, ORE_OFF]                       # the tools override and bread are filtered out
    resp = api.get(f"{BASE}/item-groups", params={"group": "ore_metal", "q": "Медн"})
    assert [i["item_id"] for i in resp.json()["items"]] == [ORE_OFF]
    assert api.get(f"{BASE}/item-groups", params={"group": "ore' OR 1=1 --"}).status_code == 400

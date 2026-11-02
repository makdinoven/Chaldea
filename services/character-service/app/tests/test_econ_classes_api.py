"""FEAT-194 QA (#9): admin / player API of the social classes (harness of ``test_econ_regions_api``).

In that harness templates and goods groups carry the model defaults (template mix 0.45 / 0.45 / 0.10, class demand
1 / 1 / 1); a PUT of region 10 (fortress) / 20 (rural, population 0) / 30 (agrarian) copies the template's shares
(``world`` fixture). Region 40 never gets an economy row.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from main import app
from tests.test_econ_regions_api import (  # noqa: F401  (engine / api / world are fixtures)
    BASE, FILL, GROUP_BODY, TEMPLATE_BODY, _as_user, _assert_ledger_closes, _balance, _numbers, _ops, _q, _region,
    api, engine, world,
)

FORTRESS = {"template_code": "fortress", "population": 300_000, "tax_rate": 0.1}
CARD = "/characters/economy/regions/{}/card"


def _items(api):
    return {r["region_id"]: r for r in api.get(f"{BASE}/regions").json()["items"]}


def _shares(engine, region_id):
    return tuple(Decimal(str(_q(engine, f"SELECT {c} FROM econ_regions WHERE region_id = :r", r=region_id)))
                 if _q(engine, f"SELECT {c} FROM econ_regions WHERE region_id = :r", r=region_id) is not None
                 else None for c in ("class_poor", "class_middling", "class_rich"))


def _set_template_mix(api, code, poor, middling, rich):
    tpl = next(t for t in api.get(f"{BASE}/templates").json()["items"] if t["code"] == code)
    body = {k: tpl[k] for k in ("name", "description", "settlement_noun", "noun_gender", "default_population",
                                "tax_rate")}
    resp = api.put(f"{BASE}/templates/{code}", json={**body, "class_poor": poor, "class_middling": middling,
                                                     "class_rich": rich})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _set_sim(api, **params):
    resp = api.put(f"{BASE}/sim", json={"tick_enabled": True, "params": params})
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------------------------- list / detail

def test_regions_list_class_fields(world, engine):
    items = _items(world)
    ten = items[10]
    assert (ten["class_poor"], ten["class_middling"], ten["class_rich"]) == (0.45, 0.45, 0.1)   # copied
    assert ten["class_base"] == {"poor": 0.45, "middling": 0.45, "rich": 0.1}
    assert ten["class_dpoor"] == 0.0 and ten["class_drich"] == 0.0
    assert ten["wealth_norm"] == 0 and ten["last_wealth_tax"] == 0 and ten["money_vs_norm"] is None
    forty = items[40]
    assert forty["class_poor"] is None and forty["class_base"] is None and forty["wealth_norm"] == 0
    world.post(f"{BASE}/regions/fill", json=FILL)
    ten = _items(world)[10]
    assert ten["wealth_norm"] > 0
    assert ten["money_vs_norm"] == pytest.approx(1.0, abs=1e-4)          # the fill tops the purse up to the norm
    assert _balance(engine, "population_purse", 10) == ten["wealth_norm"]


def test_region_detail_class_report(world):
    world.post(f"{BASE}/regions/fill", json=FILL)
    detail = _region(world, 10)
    rep = detail["classes"]
    assert set(rep) == {"classes", "wealth_norm", "money_norm", "deficit", "r"}
    assert set(rep["classes"]) == {"poor", "middling", "rich"}
    for item in rep["classes"].values():
        assert set(item) == {"share", "base_share", "norm_days", "norm_per_resident", "money_per_resident",
                             "needs_per_resident_day", "afford"}
    assert rep["wealth_norm"] == detail["wealth_norm"]
    assert rep["money_norm"] == rep["wealth_norm"] + detail["treasury_target"]
    assert rep["r"] == pytest.approx(1.0, abs=1e-3) and rep["deficit"] == 0
    assert rep["classes"]["poor"]["norm_days"] == 3.0 and rep["classes"]["rich"]["norm_days"] == 21.0
    assert _region(world, 40)["classes"] is None                          # no economy row
    _set_sim(world, classes_enabled=0)
    assert _region(world, 10)["classes"] is None                          # layer switched off


# --------------------------------------------------------------------------------------------- region PUT

def test_region_put_shares_stored_with_middling_derived(world, engine):
    resp = world.put(f"{BASE}/regions/10", json={**FORTRESS, "class_poor": 0.5, "class_middling": 0.4,
                                                 "class_rich": 0.1})
    assert resp.status_code == 200, resp.text
    assert _shares(engine, 10) == (Decimal("0.5"), Decimal("0.4"), Decimal("0.1"))
    # within the 0.001 tolerance: middling is stored as 1 - poor - rich
    resp = world.put(f"{BASE}/regions/10", json={**FORTRESS, "class_poor": 0.5, "class_middling": 0.4,
                                                 "class_rich": 0.1005})
    assert resp.status_code == 200, resp.text
    poor, middling, rich = _shares(engine, 10)
    assert (poor, rich) == (Decimal("0.5"), Decimal("0.1005")) and middling == Decimal("0.3995")
    assert poor + middling + rich == 1
    assert resp.json()["class_middling"] == pytest.approx(0.3995)
    # omitted -> kept
    assert world.put(f"{BASE}/regions/10", json=FORTRESS).status_code == 200
    assert _shares(engine, 10)[2] == Decimal("0.1005")


@pytest.mark.parametrize("shares,detail", [
    ({"class_poor": 0.5, "class_middling": 0.5}, "Укажите все три доли"),
    ({"class_rich": 0.1}, "Укажите все три доли"),
    ({"class_poor": 0.5, "class_middling": 0.4, "class_rich": 0.2}, "Сумма долей должна быть 100 %"),
    ({"class_poor": 0.3, "class_middling": 0.3, "class_rich": 0.3}, "Сумма долей должна быть 100 %"),
    ({"class_poor": 0.0, "class_middling": 0.0, "class_rich": 0.0}, "Сумма долей должна быть 100 %"),
])
def test_region_put_shares_400(world, engine, shares, detail):
    before = _shares(engine, 10)
    resp = world.put(f"{BASE}/regions/10", json={**FORTRESS, "tax_rate": 0.3, **shares})
    assert resp.status_code == 400 and resp.json()["detail"] == detail
    assert _shares(engine, 10) == before
    assert float(_q(engine, "SELECT tax_rate FROM econ_regions WHERE region_id = 10")) == pytest.approx(0.1)


@pytest.mark.parametrize("bad", [-0.1, 1.01, "много", True, "'; DROP TABLE econ_regions; --",
                                 "0.5 OR 1=1", [0.5], {"v": 1}, "NaN", "inf"])
def test_region_put_share_values_422(world, engine, bad):
    resp = world.put(f"{BASE}/regions/10", json={**FORTRESS, "class_poor": bad, "class_middling": 0.5,
                                                 "class_rich": 0.1})
    assert resp.status_code == 422, resp.text
    assert _q(engine, "SELECT COUNT(*) FROM econ_regions") == 3            # table intact


def test_region_put_share_bounds_inclusive(world, engine):
    resp = world.put(f"{BASE}/regions/10", json={**FORTRESS, "class_poor": 1, "class_middling": 0,
                                                 "class_rich": 0})
    assert resp.status_code == 200, resp.text
    assert _shares(engine, 10) == (Decimal(1), Decimal(0), Decimal(0))


def test_region_without_shares_copies_its_template(api, engine):
    resp = api.put(f"{BASE}/regions/40", json={"template_code": None, "population": 1000, "tax_rate": 0.1})
    assert resp.status_code == 200 and resp.json()["class_poor"] is None
    _set_template_mix(api, "rural", 0.6, 0.35, 0.05)
    resp = api.put(f"{BASE}/regions/40", json={"template_code": "rural", "population": 1000, "tax_rate": 0.1})
    assert resp.status_code == 200
    assert _shares(engine, 40) == (Decimal("0.6"), Decimal("0.35"), Decimal("0.05"))
    # template removed -> shares kept (unused while not participating)
    resp = api.put(f"{BASE}/regions/40", json={"template_code": None, "population": 1000, "tax_rate": 0.1})
    assert resp.status_code == 200 and resp.json()["class_poor"] == 0.6


def test_region_shares_change_moves_norm_stock_right_away(world):
    """The goods norms are recomputed with the new class factors at once (the purse norm at the next recount)."""
    world.put(f"{BASE}/goods-groups/jewelry", json={**GROUP_BODY, "name": "Украшения", "base_price": 40,
                                                     "class_demand_poor": 0.05, "class_demand_middling": 0.6,
                                                     "class_demand_rich": 6})
    world.post(f"{BASE}/regions/10/apply-template", json={"reset_stocks": True})
    before = {g["group_code"]: g["norm_stock"] for g in _region(world, 10)["goods"]}
    world.put(f"{BASE}/regions/10", json={**FORTRESS, "class_poor": 0.2, "class_middling": 0.5, "class_rich": 0.3})
    after = {g["group_code"]: g["norm_stock"] for g in _region(world, 10)["goods"]}
    assert after["jewelry"] > before["jewelry"] * 1.5
    assert after["food"] == pytest.approx(before["food"], rel=1e-6)       # food weights 1/1/1 in this harness


# --------------------------------------------------------------------------------------------- apply-template / fill

def test_apply_template_resets_shares_shift_and_writes_the_norm(world, engine):
    world.post(f"{BASE}/regions/fill", json=FILL)
    world.post(f"{BASE}/sim/run")
    world.put(f"{BASE}/regions/10", json={**FORTRESS, "class_poor": 0.7, "class_middling": 0.25, "class_rich": 0.05})
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE econ_regions SET class_dpoor = 0.01, class_drich = -0.002, wealth_norm = 1 "
                             "WHERE region_id = 10")
    resp = world.post(f"{BASE}/regions/10/apply-template", json={"reset_stocks": True})
    assert resp.status_code == 200, resp.text
    item = resp.json()
    assert (item["class_poor"], item["class_middling"], item["class_rich"]) == (0.45, 0.45, 0.1)
    assert item["class_dpoor"] == 0.0 and item["class_drich"] == 0.0
    assert item["wealth_norm"] > 1


def test_fill_keeps_hand_edited_shares_unless_reset_classes(world, engine):
    world.put(f"{BASE}/regions/10", json={**FORTRESS, "class_poor": 0.7, "class_middling": 0.25, "class_rich": 0.05})
    first = world.post(f"{BASE}/regions/fill", json=FILL).json()
    assert first["classes_reset"] == []                                   # every row already had shares
    assert _shares(engine, 10) == (Decimal("0.7"), Decimal("0.25"), Decimal("0.05"))
    norm_kept = _items(world)[10]["wealth_norm"]
    assert _balance(engine, "population_purse", 10) == norm_kept          # purse target = the (class) norm

    resp = world.post(f"{BASE}/regions/fill", json={**FILL, "reset_classes": True})
    assert resp.status_code == 200, resp.text
    assert sorted(resp.json()["classes_reset"]) == [10, 20, 30]           # every templated target row
    assert _shares(engine, 10) == (Decimal("0.45"), Decimal("0.45"), Decimal("0.1"))
    norm_reset = _items(world)[10]["wealth_norm"]
    assert norm_reset != norm_kept
    assert _balance(engine, "population_purse", 10) >= norm_reset         # top-up only, no return without the flag
    _assert_ledger_closes(engine, world)


def test_fill_gives_null_share_rows_their_template(world, engine):
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE econ_regions SET class_poor = NULL, class_middling = NULL, class_rich = NULL "
                             "WHERE region_id = 30")
    resp = world.post(f"{BASE}/regions/fill", json=FILL)
    assert 30 in resp.json()["classes_reset"] and 10 not in resp.json()["classes_reset"]
    assert _shares(engine, 30) == (Decimal("0.45"), Decimal("0.45"), Decimal("0.1"))


def test_fill_purse_target_without_classes_is_the_old_target(world, engine):
    _set_sim(world, classes_enabled=0)
    world.post(f"{BASE}/regions/fill", json=FILL)
    on_off = _items(world)[10]["wealth_norm"]
    assert _balance(engine, "population_purse", 10) == on_off > 0


@pytest.mark.parametrize("bad", ["true", 1, 0, None, [], {}])
def test_fill_reset_classes_is_strict_bool(world, engine, bad):
    resp = world.post(f"{BASE}/regions/fill", json={**FILL, "reset_classes": bad})
    assert resp.status_code == 422
    assert _ops(engine) == 0


# --------------------------------------------------------------------------------------------- templates / groups

def test_template_shares_stored_at_four_decimals_and_kept_when_omitted(api, engine):
    tpl = _set_template_mix(api, "rural", 0.61234, 0.331, 0.05666)
    assert tpl["class_poor"] == 0.6123 and tpl["class_rich"] == 0.0567
    assert tpl["class_middling"] == pytest.approx(0.331)                  # derived: 1 - poor - rich
    resp = api.put(f"{BASE}/templates/rural", json=TEMPLATE_BODY)        # no class fields -> kept
    assert resp.status_code == 200 and resp.json()["class_poor"] == 0.6123


@pytest.mark.parametrize("shares,status", [
    ({"class_poor": 0.5}, 400),
    ({"class_poor": 0.5, "class_middling": 0.6, "class_rich": 0.1}, 400),
    ({"class_poor": 1.5, "class_middling": 0.0, "class_rich": 0.0}, 422),
    ({"class_poor": -0.5, "class_middling": 1.0, "class_rich": 0.5}, 422),
    ({"class_poor": "<script>", "class_middling": 0.5, "class_rich": 0.1}, 422),
])
def test_template_shares_validation(api, engine, shares, status):
    resp = api.put(f"{BASE}/templates/rural", json={**TEMPLATE_BODY, **shares})
    assert resp.status_code == status, resp.text
    assert float(_q(engine, "SELECT class_poor FROM econ_region_templates WHERE code = 'rural'")) == 0.45


def test_template_share_edit_does_not_touch_region_shares(world, engine):
    _set_template_mix(world, "fortress", 0.3, 0.5, 0.2)
    assert _shares(engine, 10) == (Decimal("0.45"), Decimal("0.45"), Decimal("0.1"))
    assert _items(world)[10]["class_base"] == {"poor": 0.3, "middling": 0.5, "rich": 0.2}


def test_goods_group_class_demand_fields(api, engine):
    resp = api.put(f"{BASE}/goods-groups/food", json={**GROUP_BODY, "class_demand_poor": 0.9,
                                                       "class_demand_middling": 1, "class_demand_rich": 1.234})
    assert resp.status_code == 200, resp.text
    g = resp.json()
    assert (g["class_demand_poor"], g["class_demand_middling"], g["class_demand_rich"]) == (0.9, 1.0, 1.234)
    resp = api.put(f"{BASE}/goods-groups/food", json={**GROUP_BODY, "class_demand_rich": 20})   # others kept
    g = resp.json()
    assert (g["class_demand_poor"], g["class_demand_rich"]) == (0.9, 20.0)
    assert api.put(f"{BASE}/goods-groups/food", json=GROUP_BODY).json()["class_demand_rich"] == 20.0


@pytest.mark.parametrize("patch", [{"class_demand_poor": -0.1}, {"class_demand_rich": 20.5},
                                   {"class_demand_middling": "много"}, {"class_demand_rich": True},
                                   {"class_demand_poor": "1; DROP TABLE econ_goods_groups"}])
def test_goods_group_class_demand_422(api, engine, patch):
    assert api.put(f"{BASE}/goods-groups/food", json={**GROUP_BODY, **patch}).status_code == 422
    assert float(_q(engine, "SELECT class_demand_rich FROM econ_goods_groups WHERE code = 'food'")) == 1.0


# --------------------------------------------------------------------------------------------- history / sim params

def test_history_class_columns(world):
    world.post(f"{BASE}/regions/fill", json=FILL)
    assert world.post(f"{BASE}/sim/run").status_code == 200
    item = world.get(f"{BASE}/regions/10/history").json()["items"][0]
    assert (item["class_poor"], item["class_middling"], item["class_rich"]) == (0.45, 0.45, 0.1)
    assert item["wealth_norm"] == _items(world)[10]["wealth_norm"] > 0
    assert item["wealth_tax"] == _items(world)[10]["last_wealth_tax"]


def test_sim_class_params_defaults_and_bounds_cross_rule(api):
    params = api.get(f"{BASE}/sim").json()["params"]
    assert params["classes_enabled"] == 1 and params["wealth_tax_rate"] == 0.02
    assert (params["class_norm_days_poor"], params["class_norm_days_middling"], params["class_norm_days_rich"]) == \
        (3.0, 7.0, 21.0)
    assert (params["class_share_min"], params["class_share_max"]) == (0.02, 0.9)
    assert params["grant_deficit_share"] == 0.25
    # the tightest legal pair still passes the min < max rule (its bounds 0..0.3 / 0.4..1 never overlap)
    _set_sim(api, class_share_min=0.3, class_share_max=0.4)
    for bad in ({"class_share_min": 0.31}, {"class_share_max": 0.39}, {"classes_enabled": 2},
                {"classes_enabled": 0.5}, {"wealth_tax_rate": 0.21}):
        assert api.put(f"{BASE}/sim", json={"tick_enabled": True, "params": bad}).status_code == 422, bad


# --------------------------------------------------------------------------------------------- card

def test_card_classes_words_and_no_numbers(world):
    world.post(f"{BASE}/regions/fill", json=FILL)
    world.post(f"{BASE}/sim/run")
    card = TestClient(app).get(CARD.format(10)).json()
    assert set(card["classes"]) == {"state", "label", "bar"}
    assert card["classes"]["state"] in ("poor", "modest", "wealthy", "rich")
    assert set(card["classes"]["bar"].values()) <= {"few", "some", "many"}
    assert card["phrases"][0] == card["classes"]["label"]
    assert _numbers(card) == [(".region_id", 10)]
    adjectives = ("Богат", "Зажиточ", "Скромн", "Бедн")
    assert sum(1 for p in card["phrases"] if p.startswith(adjectives)) == 1   # no second «Богатый …»
    assert not card["prosperity"]["label"].startswith(adjectives)


def test_card_shares_never_leak(world):
    world.put(f"{BASE}/regions/10", json={**FORTRESS, "class_poor": 0.123457, "class_middling": 0.5,
                                          "class_rich": 0.376543})
    world.post(f"{BASE}/regions/fill", json=FILL)
    world.post(f"{BASE}/sim/run")
    resp = TestClient(app).get(CARD.format(10))
    for leak in ("0.123", "12.3", "0.376", "37.6", "37.7", "wealth_norm", "class_poor", "share", "%"):
        assert leak not in resp.text, leak
    card = resp.json()
    assert card["classes"]["bar"] == {"poor": "few", "middling": "many", "rich": "many"}
    assert card["classes"]["state"] == "rich" and card["classes"]["label"] == "Богатая крепость"


def test_card_without_classes_has_no_classes_key(world, engine):
    world.post(f"{BASE}/regions/fill", json=FILL)
    _set_sim(world, classes_enabled=0)
    card = TestClient(app).get(CARD.format(10)).json()
    assert "classes" not in card
    assert card["phrases"][0] == card["prosperity"]["label"]
    assert card["prosperity"]["label"].split()[0] in ("Богатая", "Зажиточная", "Скромная", "Бедная")
    _set_sim(world, classes_enabled=1)
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE econ_regions SET class_poor = NULL, class_middling = NULL, class_rich = NULL "
                             "WHERE region_id = 10")
    card = TestClient(app).get(CARD.format(10)).json()
    assert "classes" not in card and _numbers(card) == [(".region_id", 10)]


# --------------------------------------------------------------------------------------------- permissions

CLASS_WRITES = [
    ("put", f"{BASE}/regions/10", {**FORTRESS, "class_poor": 0.6, "class_middling": 0.3, "class_rich": 0.1},
     "economy:settings"),
    ("put", f"{BASE}/templates/rural", {**TEMPLATE_BODY, "class_poor": 0.6, "class_middling": 0.3, "class_rich": 0.1},
     "economy:settings"),
    ("put", f"{BASE}/goods-groups/food", {**GROUP_BODY, "class_demand_rich": 3}, "economy:settings"),
    ("put", f"{BASE}/sim", {"tick_enabled": True, "params": {"classes_enabled": 0}}, "economy:settings"),
    ("post", f"{BASE}/regions/10/apply-template", {"reset_stocks": True}, "economy:settings"),
    ("post", f"{BASE}/regions/fill", {**FILL, "reset_classes": True}, "economy:settings"),
]


@pytest.mark.parametrize("method,url,body,perm", CLASS_WRITES, ids=[f"{m} {u[len(BASE):]}" for m, u, _b, _p in
                                                                     CLASS_WRITES])
def test_class_writes_need_settings(world, engine, method, url, body, perm):
    before = (_shares(engine, 10), _q(engine, "SELECT class_poor FROM econ_region_templates WHERE code = 'rural'"),
              _q(engine, "SELECT class_demand_rich FROM econ_goods_groups WHERE code = 'food'"))
    from auth_http import get_current_user_via_http
    app.dependency_overrides.pop(get_current_user_via_http, None)
    assert getattr(TestClient(app), method)(url, json=body).status_code == 401
    _as_user(["economy:read", "economy:emit", "economy:adjust"])
    resp = getattr(TestClient(app), method)(url, json=body)
    assert resp.status_code == 403 and resp.json()["detail"] == "Недостаточно прав"
    after = (_shares(engine, 10), _q(engine, "SELECT class_poor FROM econ_region_templates WHERE code = 'rural'"),
             _q(engine, "SELECT class_demand_rich FROM econ_goods_groups WHERE code = 'food'"))
    assert after == before and _ops(engine) == 0


def test_class_reads_need_economy_read(world):
    from auth_http import get_current_user_via_http
    app.dependency_overrides.pop(get_current_user_via_http, None)
    assert TestClient(app).get(f"{BASE}/regions/10").status_code == 401
    _as_user(["economy:settings"])
    assert TestClient(app).get(f"{BASE}/regions/10").status_code == 403
    _as_user(["economy:read"])
    assert TestClient(app).get(f"{BASE}/regions/10").json()["classes"] is not None

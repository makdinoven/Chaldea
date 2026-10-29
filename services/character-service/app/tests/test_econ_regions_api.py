"""FEAT-182 Q3: living-regions economy API of character-service (contract 3.7) on SQLite.

Every test gets its own in-memory database built from the character-service metadata (the conftest
``after_create`` hook adds the Countries / Regions / Districts / Locations hierarchy), seeded with the
migration-028 defaults (goods groups, chains, templates, sim params) plus the foreign tables the endpoints
read with raw SQL: ``items`` / ``quest_objectives`` (inventory / locations services) and the auction tables
(the summary invariant). Those tables live only in this fixture, so conftest stays untouched.

World used below:
    Countries 1 «Мидденгерд», 2 «Пустошь»
    Regions 10 «Ост» (c1), 20 «Пашни» (c1), 30 «Нива» (c2), 40 «Глушь» (c1, never gets an economy row)
"""

import importlib.util
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import econ_core as core
import econ_tick
import economy_api
import models
from auth_http import UserRead, get_current_user_via_http
from main import app
from schemas import ECON_SIM_PARAM_BOUNDS, ECON_SIM_INT_PARAMS

MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "028_econ_living_regions.py")
_spec = importlib.util.spec_from_file_location("migration_028_for_regions_api", MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

BASE = "/characters/admin/economy"
ALL_PERMS = ["economy:read", "economy:emit", "economy:adjust", "economy:settings"]
FILL = {"comment": "Заполнение для теста"}

EXTRA_DDL = [
    """CREATE TABLE items (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, item_type VARCHAR(32) NOT NULL,
        item_rarity VARCHAR(32) NOT NULL DEFAULT 'common', resource_subcategory VARCHAR(32) NULL,
        is_food INTEGER NOT NULL DEFAULT 0, price INTEGER NOT NULL DEFAULT 0, image VARCHAR(255) NULL)""",
    """CREATE TABLE quest_objectives (id INTEGER PRIMARY KEY, quest_id INTEGER NOT NULL DEFAULT 1,
        objective_type VARCHAR(32) NOT NULL, target_id INTEGER NULL)""",
    """CREATE TABLE auction_listings (id INTEGER PRIMARY KEY, current_bid INTEGER NOT NULL DEFAULT 0,
        current_bidder_id INTEGER NULL, status VARCHAR(20) NOT NULL DEFAULT 'active')""",
    "CREATE TABLE auction_storage (id INTEGER PRIMARY KEY, gold_amount INTEGER NOT NULL DEFAULT 0)",
]

ITEMS = [
    # id, name, item_type, rarity, subcategory, is_food
    (1, "Хлеб", "consumable", "common", None, 1),
    (2, "Железная руда", "resource", "common", "ore", 0),
    (3, "Свиток огня", "scroll", "rare", None, 0),
    (4, "Меч", "weapon", "common", None, 0),
    (5, "Странная штука", "misc", "common", None, 0),
    (6, "Легендарный клинок", "weapon", "legendary", None, 0),
    (7, "Скидка 100%_всё", "misc", "common", None, 0),
]


# --------------------------------------------------------------------------------------------- fixtures

@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=eng)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    db = factory()
    for ddl in EXTRA_DDL:
        db.execute(text(ddl))
    for i, g in enumerate(mig.GROUPS, 1):
        db.add(models.EconGoodsGroup(code=g[0], name=g[1], sort_order=i, base_price=g[2], norm_per_1000=g[3],
                                     norm_days=g[4], prosperity_elasticity=g[5], price_elasticity=g[6],
                                     is_food=bool(g[7])))
    db.flush()
    for group_code, inputs in mig.INPUTS.items():
        for input_code, ratio in inputs:
            db.add(models.EconGroupInput(group_code=group_code, input_code=input_code, ratio=ratio))
    for i, t in enumerate(mig.TEMPLATES, 1):
        db.add(models.EconRegionTemplate(code=t[0], name=t[1], description=t[2], settlement_noun=t[3],
                                         noun_gender=t[4], default_population=t[5], tax_rate=t[6], sort_order=i))
    db.flush()
    for t in mig.TEMPLATES:
        for group_code, prod, cmult in mig.template_goods(t[0]):
            db.add(models.EconTemplateGood(template_code=t[0], group_code=group_code, production_per_1000=prod,
                                           consumption_mult=cmult))
    db.add(models.EconSimSettings(id=1, tick_enabled=True, params=dict(mig.DEFAULT_PARAMS)))
    db.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Мидденгерд'), (2, 'Пустошь')"))
    db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Ост', 1), (20, 'Пашни', 1), "
                    "(30, 'Нива', 2), (40, 'Глушь', 1)"))
    for item in ITEMS:
        db.execute(text("INSERT INTO items (id, name, item_type, item_rarity, resource_subcategory, is_food, price) "
                        "VALUES (:i, :n, :t, :r, :s, :f, 10)"),
                   {"i": item[0], "n": item[1], "t": item[2], "r": item[3], "s": item[4], "f": item[5]})
    db.execute(text("INSERT INTO quest_objectives (id, objective_type, target_id) VALUES "
                    "(1, 'collect', 2), (2, 'kill', 4), (3, 'deliver', 1)"))
    db.commit()
    db.close()

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[economy_api.get_db] = override_get_db
    core.invalidate_settings_cache()
    yield eng
    app.dependency_overrides.pop(economy_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)
    core.invalidate_settings_cache()
    eng.dispose()


def _as_user(permissions, user_id=7):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username="tester", role="moderator", permissions=permissions)


@pytest.fixture
def api(engine):
    _as_user(ALL_PERMS)
    return TestClient(app)


@pytest.fixture
def world(api):
    """Region 10 fortress (3000), 20 rural with population 0, 30 agrarian (8000); 40 has no economy row."""
    for region_id, template, population in ((10, "fortress", 3000), (20, "rural", 0), (30, "agrarian", 8000)):
        resp = api.put(f"{BASE}/regions/{region_id}",
                       json={"template_code": template, "population": population, "tax_rate": 0.1})
        assert resp.status_code == 200, resp.text
    return api


def _q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def _balance(engine, kind, ref_id):
    return int(_q(engine, "SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r", k=kind, r=ref_id)
               or 0)


def _assert_ledger_closes(engine, api=None):
    assert int(_q(engine, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts")) == 0
    assert _q(engine, "SELECT COUNT(*) FROM econ_accounts WHERE allow_negative = 0 AND balance < 0") == 0
    # Balances equal the posting history of every account.
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT a.id, a.balance, "
            "COALESCE((SELECT SUM(amount) FROM econ_postings WHERE to_account_id = a.id), 0) - "
            "COALESCE((SELECT SUM(amount) FROM econ_postings WHERE from_account_id = a.id), 0) "
            "FROM econ_accounts a")).fetchall()
    assert all(int(r[1]) == int(r[2]) for r in rows), rows
    if api is not None:
        resp = api.get(f"{BASE}/summary")
        assert resp.status_code == 200, resp.text
        assert resp.json()["invariant"]["ok"] is True


def _region(api, region_id):
    resp = api.get(f"{BASE}/regions/{region_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _goods(detail):
    return {g["group_code"]: g for g in detail["goods"]}


def _ops(engine):
    return _q(engine, "SELECT COUNT(*) FROM econ_operations")


# --------------------------------------------------------------------------------------------- RBAC

GROUP_BODY = {"name": "Продовольствие", "base_price": 3, "norm_per_1000": 300, "norm_days": 7,
              "prosperity_elasticity": 0, "price_elasticity": 0.1, "inputs": []}
TEMPLATE_BODY = {"name": "Сельская округа", "description": "Деревни", "settlement_noun": "Округа",
                 "noun_gender": "f", "default_population": 2500, "tax_rate": 0.06, "goods": []}
REGION_BODY = {"template_code": "rural", "population": 1000, "tax_rate": 0.1}

ENDPOINTS = [
    ("get", f"{BASE}/regions", None, "economy:read"),
    ("get", f"{BASE}/regions/10", None, "economy:read"),
    ("get", f"{BASE}/regions/10/history", None, "economy:read"),
    ("get", f"{BASE}/goods-groups", None, "economy:read"),
    ("get", f"{BASE}/templates", None, "economy:read"),
    ("get", f"{BASE}/item-groups", None, "economy:read"),
    ("get", f"{BASE}/sim", None, "economy:read"),
    ("put", f"{BASE}/regions/10", REGION_BODY, "economy:settings"),
    ("post", f"{BASE}/regions/10/apply-template", {"reset_stocks": True}, "economy:settings"),
    ("put", f"{BASE}/goods-groups/food", GROUP_BODY, "economy:settings"),
    ("put", f"{BASE}/templates/rural", TEMPLATE_BODY, "economy:settings"),
    ("put", f"{BASE}/item-groups", {"item_ids": [1], "off_market": True}, "economy:settings"),
    ("put", f"{BASE}/sim", {"tick_enabled": False, "params": {}}, "economy:settings"),
    ("post", f"{BASE}/sim/run", None, "economy:settings"),
    ("post", f"{BASE}/regions/fill", FILL, "economy:settings"),
]
IDS = [f"{e[0]} {e[1][len(BASE):]}" for e in ENDPOINTS]


@pytest.mark.parametrize("method,url,body,perm", ENDPOINTS, ids=IDS)
def test_admin_endpoints_401_without_token(engine, method, url, body, perm):
    resp = getattr(TestClient(app), method)(url, **({"json": body} if body else {}))
    assert resp.status_code == 401


@pytest.mark.parametrize("method,url,body,perm", ENDPOINTS, ids=IDS)
def test_admin_endpoints_403_without_their_permission(engine, method, url, body, perm):
    _as_user([p for p in ALL_PERMS if p != perm] + ["characters:update"])
    resp = getattr(TestClient(app), method)(url, **({"json": body} if body else {}))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Недостаточно прав"
    assert _ops(engine) == 0
    assert _q(engine, "SELECT COUNT(*) FROM econ_tick_runs") == 0


@pytest.mark.parametrize("method,url,body,perm", [e for e in ENDPOINTS if not e[1].endswith("/fill")],
                         ids=[i for i in IDS if not i.endswith("/fill")])
def test_admin_endpoints_allowed_with_only_their_permission(engine, method, url, body, perm):
    _as_user([perm])
    resp = getattr(TestClient(app), method)(url, **({"json": body} if body else {}))
    assert resp.status_code not in (401, 403), resp.text


def test_moderator_with_read_only_cannot_write(engine):
    _as_user(["economy:read"])
    client = TestClient(app)
    assert client.get(f"{BASE}/regions").status_code == 200
    for method, url, body, perm in ENDPOINTS:
        if perm != "economy:read":
            assert getattr(client, method)(url, **({"json": body} if body else {})).status_code == 403


@pytest.mark.parametrize("perms", [["economy:settings"], ["economy:emit"], ["economy:read", "economy:adjust"]])
def test_fill_needs_both_settings_and_emit(world, engine, perms):
    _as_user(perms)
    resp = TestClient(app).post(f"{BASE}/regions/fill", json=FILL)
    assert resp.status_code == 403
    assert _ops(engine) == 0


def test_fill_allowed_with_exactly_settings_and_emit(world, engine):
    _as_user(["economy:settings", "economy:emit"])
    resp = TestClient(app).post(f"{BASE}/regions/fill", json=FILL)
    assert resp.status_code == 200, resp.text
    assert resp.json()["emitted"] > 0
    actor = _q(engine, "SELECT actor_user_id FROM econ_operations WHERE op_type = 'admin_emission' LIMIT 1")
    assert actor == 7


def test_public_card_needs_no_auth(world):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    resp = TestClient(app).get("/characters/economy/regions/10/card")
    assert resp.status_code == 200 and resp.json()["participating"] is True


# --------------------------------------------------------------------------------------------- regions list / detail

REGION_KEYS = {"region_id", "name", "country_id", "country_name", "template_code", "template_name", "population",
               "tax_rate", "stability", "prosperity", "hunger", "satisfaction", "purse", "treasury",
               "treasury_target", "last_income", "last_tax", "last_wages", "last_grant", "last_tick_at",
               "simulated"}
GOOD_KEYS = {"group_code", "name", "production_per_1000", "consumption_mult", "stock", "norm_stock", "price_mult",
             "prev_price_mult", "last_produced", "last_consumed", "last_demand", "last_spoiled"}


def test_regions_list_shape_includes_every_world_region(world):
    resp = world.get(f"{BASE}/regions")
    assert resp.status_code == 200
    items = {r["region_id"]: r for r in resp.json()["items"]}
    assert set(items) == {10, 20, 30, 40}
    for item in items.values():
        assert set(item) == REGION_KEYS
    assert items[10]["template_code"] == "fortress" and items[10]["template_name"] == "Пограничная крепость"
    assert items[10]["country_name"] == "Мидденгерд" and items[30]["country_name"] == "Пустошь"
    assert items[10]["simulated"] is True and items[30]["simulated"] is True
    assert items[20]["simulated"] is False                                  # population 0
    assert items[40]["simulated"] is False and items[40]["template_code"] is None
    assert items[40]["population"] == 0 and items[40]["purse"] == 0


def test_region_detail_shape_and_404(world):
    detail = _region(world, 10)
    assert set(detail) == REGION_KEYS | {"goods"}
    assert [g["group_code"] for g in detail["goods"]] == list(core.GOODS_GROUPS)
    for good in detail["goods"]:
        assert set(good) == GOOD_KEYS
        assert good["stock"] == pytest.approx(good["norm_stock"], abs=0.01)      # created from the template
    assert _goods(detail)["food"]["name"] == "Продовольствие"
    assert world.get(f"{BASE}/regions/999").status_code == 404
    assert world.get(f"{BASE}/regions/40").json()["goods"] == []


# --------------------------------------------------------------------------------------------- region PUT

def test_region_put_partial_goods_keeps_the_others(world):
    before = _goods(_region(world, 10))
    resp = world.put(f"{BASE}/regions/10", json={
        "template_code": "fortress", "population": 3000, "tax_rate": 0.2, "stability": 40, "prosperity": 30,
        "goods": [{"group_code": "food", "production_per_1000": 1, "consumption_mult": 2, "stock": 5}]})
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    after = _goods(detail)
    assert after["food"]["production_per_1000"] == 1 and after["food"]["consumption_mult"] == 2
    assert after["food"]["stock"] == 5
    for code in core.GOODS_GROUPS:
        if code != "food":
            assert after[code]["production_per_1000"] == pytest.approx(before[code]["production_per_1000"])
            assert after[code]["stock"] == pytest.approx(before[code]["stock"])
    assert detail["tax_rate"] == pytest.approx(0.2)
    assert detail["stability"] == 40 and detail["prosperity"] == 30


def test_region_put_template_change_does_not_overwrite_goods(world):
    before = _goods(_region(world, 10))
    resp = world.put(f"{BASE}/regions/10", json={"template_code": "magic", "population": 3000, "tax_rate": 0.1})
    assert resp.status_code == 200
    after = _goods(resp.json())
    assert resp.json()["template_code"] == "magic"
    assert all(after[c]["production_per_1000"] == pytest.approx(before[c]["production_per_1000"])
               for c in core.GOODS_GROUPS)


def test_region_put_without_template_creates_no_goods(api):
    resp = api.put(f"{BASE}/regions/40", json={"template_code": None, "population": 100, "tax_rate": 0})
    assert resp.status_code == 200, resp.text
    assert resp.json()["goods"] == [] and resp.json()["simulated"] is False


def test_region_put_unknown_region_and_template(api):
    assert api.put(f"{BASE}/regions/999", json=REGION_BODY).status_code == 404
    resp = api.put(f"{BASE}/regions/10", json={**REGION_BODY, "template_code": "atlantis"})
    assert resp.status_code == 400 and resp.json()["detail"] == "Неизвестный шаблон региона"


@pytest.mark.parametrize("patch", [
    {"population": -1}, {"population": 10_000_001}, {"population": 1.5}, {"population": "много"},
    {"population": True}, {"tax_rate": -0.01}, {"tax_rate": 0.51}, {"stability": 101}, {"stability": -1},
    {"prosperity": 100.5}, {"template_code": "<script>alert(1)</script>"},
    {"goods": [{"group_code": "gold", "production_per_1000": 1, "consumption_mult": 1}]},
    {"goods": [{"group_code": "food", "production_per_1000": 100_001, "consumption_mult": 1}]},
    {"goods": [{"group_code": "food", "production_per_1000": -1, "consumption_mult": 1}]},
    {"goods": [{"group_code": "food", "production_per_1000": 1, "consumption_mult": 11}]},
    {"goods": [{"group_code": "food", "production_per_1000": 1, "consumption_mult": 1, "stock": -5}]},
    {"goods": [{"group_code": "food", "production_per_1000": 1, "consumption_mult": 1},
               {"group_code": "food", "production_per_1000": 2, "consumption_mult": 1}]},
])
def test_region_put_validation_422(world, patch):
    resp = world.put(f"{BASE}/regions/10", json={**REGION_BODY, **patch})
    assert resp.status_code == 422, resp.text


def test_region_put_bounds_inclusive(world):
    resp = world.put(f"{BASE}/regions/10", json={"template_code": "fortress", "population": 10_000_000,
                                                 "tax_rate": 0.5, "stability": 100, "prosperity": 0})
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------------------------- apply-template

def test_apply_template_resets_stocks_and_tax(world):
    world.put(f"{BASE}/regions/10", json={"template_code": "fortress", "population": 3000, "tax_rate": 0.3,
                                          "goods": [{"group_code": "food", "production_per_1000": 1,
                                                     "consumption_mult": 1, "stock": 1}]})
    resp = world.post(f"{BASE}/regions/10/apply-template", json={"reset_stocks": True})
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    tgoods = {g: (p, c) for g, p, c in mig.template_goods("fortress")}
    food = _goods(detail)["food"]
    assert food["production_per_1000"] == pytest.approx(tgoods["food"][0], abs=0.001)
    assert food["stock"] == pytest.approx(food["norm_stock"], abs=0.01)
    assert detail["tax_rate"] == pytest.approx(0.06)
    assert detail["population"] == 3000                                     # kept


def test_apply_template_keeps_stocks_when_asked(world):
    world.put(f"{BASE}/regions/10", json={"template_code": "fortress", "population": 3000, "tax_rate": 0.1,
                                          "goods": [{"group_code": "food", "production_per_1000": 1,
                                                     "consumption_mult": 1, "stock": 1}]})
    resp = world.post(f"{BASE}/regions/10/apply-template", json={"reset_stocks": False})
    assert resp.status_code == 200
    assert _goods(resp.json())["food"]["stock"] == 1


def test_apply_template_without_body_defaults_to_reset(world):
    resp = world.post(f"{BASE}/regions/10/apply-template")
    assert resp.status_code == 200, resp.text


def test_apply_template_errors(world):
    assert world.post(f"{BASE}/regions/999/apply-template", json={}).status_code == 404
    resp = world.post(f"{BASE}/regions/40/apply-template", json={})
    assert resp.status_code == 400 and resp.json()["detail"] == "Сначала выберите шаблон региона"
    assert world.post(f"{BASE}/regions/10/apply-template", json={"reset_stocks": "yes"}).status_code == 422


# --------------------------------------------------------------------------------------------- fill

def test_fill_shape_and_idempotent_top_up(world, engine):
    resp = world.post(f"{BASE}/regions/fill", json=FILL)
    assert resp.status_code == 200, resp.text
    first = resp.json()
    assert set(first) == {"regions", "operation_id", "operation_ids", "emitted", "emitted_purses",
                          "emitted_treasuries", "skipped_no_population"}
    assert first["regions"] == 3
    assert first["skipped_no_population"] == [20]
    assert len(first["operation_ids"]) == 2 and first["operation_id"] == first["operation_ids"][-1]
    assert first["emitted_purses"] > 0 and first["emitted_treasuries"] > 0
    assert first["emitted"] == first["emitted_purses"] + first["emitted_treasuries"]

    purses = _balance(engine, "population_purse", 10) + _balance(engine, "population_purse", 30)
    treasuries = _balance(engine, "region_treasury", 10) + _balance(engine, "region_treasury", 30)
    assert purses == first["emitted_purses"] and treasuries == first["emitted_treasuries"]
    assert _balance(engine, "population_purse", 20) == 0
    assert _balance(engine, "emission", 0) == -first["emitted"]
    # One admin_emission per region, tagged with the region.
    assert _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'admin_emission'") == 2
    assert _q(engine, "SELECT COUNT(DISTINCT region_id) FROM econ_operations "
                      "WHERE op_type = 'admin_emission' AND region_id IN (10, 30)") == 2
    assert _region(world, 10)["treasury_target"] == _balance(engine, "region_treasury", 10)
    _assert_ledger_closes(engine, world)

    resp = world.post(f"{BASE}/regions/fill", json=FILL)
    assert resp.status_code == 200
    second = resp.json()
    assert second["emitted"] == 0 and second["operation_id"] is None and second["operation_ids"] == []
    assert second["regions"] == 3
    assert _q(engine, "SELECT COUNT(*) FROM econ_operations") == 2
    _assert_ledger_closes(engine, world)


def test_fill_tops_up_only_the_missing_amount(world, engine):
    world.post(f"{BASE}/regions/fill", json={**FILL, "region_ids": [10]})
    # A tick moves money between the purse and the treasury; the next fill only adds the gap.
    assert world.post(f"{BASE}/sim/run").status_code == 200
    purse_before = _balance(engine, "population_purse", 10)
    treasury_before = _balance(engine, "region_treasury", 10)
    issued_before = -_balance(engine, "emission", 0)
    body = {**FILL, "region_ids": [10], "reset_stocks": False}
    resp = world.post(f"{BASE}/regions/fill", json=body)
    assert resp.status_code == 200, resp.text
    second = resp.json()
    assert _balance(engine, "population_purse", 10) == purse_before + second["emitted_purses"]
    assert _balance(engine, "region_treasury", 10) == treasury_before + second["emitted_treasuries"]
    assert -_balance(engine, "emission", 0) == issued_before + second["emitted"]
    assert second["emitted"] > 0                                    # the tick spent something
    # Right after a fill nothing is missing any more.
    assert world.post(f"{BASE}/regions/fill", json=body).json()["emitted"] == 0
    _assert_ledger_closes(engine, world)


def test_fill_without_treasury_reserve(world, engine):
    resp = world.post(f"{BASE}/regions/fill", json={**FILL, "treasury_to_reserve": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["emitted_treasuries"] == 0 and body["emitted_purses"] > 0
    assert _balance(engine, "region_treasury", 10) == 0 and _balance(engine, "region_treasury", 30) == 0
    _assert_ledger_closes(engine, world)


def test_fill_without_purses(world, engine):
    resp = world.post(f"{BASE}/regions/fill", json={**FILL, "fund_purses": False})
    assert resp.status_code == 200
    assert resp.json()["emitted_purses"] == 0 and resp.json()["emitted_treasuries"] > 0
    assert _balance(engine, "population_purse", 10) == 0
    _assert_ledger_closes(engine, world)


def test_fill_population_from_template_only_for_empty_rows(world, engine):
    resp = world.post(f"{BASE}/regions/fill", json={**FILL, "population_from_template": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["skipped_no_population"] == []
    assert _region(world, 20)["population"] == 2500                         # rural default
    assert _region(world, 10)["population"] == 3000                         # kept
    assert _balance(engine, "population_purse", 20) > 0
    _assert_ledger_closes(engine, world)


def test_fill_explicit_region_ids(world, engine):
    resp = world.post(f"{BASE}/regions/fill", json={**FILL, "region_ids": [30]})
    assert resp.status_code == 200 and resp.json()["regions"] == 1
    assert _balance(engine, "population_purse", 10) == 0 and _balance(engine, "population_purse", 30) > 0
    _assert_ledger_closes(engine, world)


def test_fill_explicit_region_without_template_400(world, engine):
    resp = world.post(f"{BASE}/regions/fill", json={**FILL, "region_ids": [10, 40]})
    assert resp.status_code == 400
    assert "Глушь" in resp.json()["detail"]
    resp = world.post(f"{BASE}/regions/fill", json={**FILL, "region_ids": [999]})
    assert resp.status_code == 400
    assert _ops(engine) == 0                                               # rolled back as a whole


@pytest.mark.parametrize("body", [
    {}, {"comment": "аб"}, {"comment": "x" * 501}, {**FILL, "region_ids": []}, {**FILL, "region_ids": ["10"]},
    {**FILL, "region_ids": [0]}, {**FILL, "region_ids": list(range(1, 502))}, {**FILL, "fund_purses": "yes"},
    {**FILL, "treasury_to_reserve": 1},
])
def test_fill_validation_422(world, engine, body):
    assert world.post(f"{BASE}/regions/fill", json=body).status_code == 422
    assert _ops(engine) == 0


# --------------------------------------------------------------------------------------------- history

def test_history_after_run_and_limit_bounds(world):
    world.post(f"{BASE}/regions/fill", json=FILL)
    assert world.post(f"{BASE}/sim/run").status_code == 200
    assert world.post(f"{BASE}/sim/run").status_code == 200
    resp = world.get(f"{BASE}/regions/10/history")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2 and items[0]["id"] > items[1]["id"]              # newest first
    assert set(items[0]) == {"id", "run_id", "region_id", "created_at", "population", "stability", "prosperity",
                             "hunger", "purse", "treasury", "income", "tax", "wages", "grant_amount", "goods"}
    assert set(items[0]["goods"]["food"]) == {"stock", "price_mult", "produced", "consumed"}
    assert len(world.get(f"{BASE}/regions/10/history", params={"limit": 1}).json()["items"]) == 1
    assert world.get(f"{BASE}/regions/20/history").json()["items"] == []
    for bad in (0, 201, -1, "abc"):
        assert world.get(f"{BASE}/regions/10/history", params={"limit": bad}).status_code == 422
    assert world.get(f"{BASE}/regions/10/history", params={"limit": 200}).status_code == 200


# --------------------------------------------------------------------------------------------- goods groups

def test_goods_groups_list_shape(api):
    resp = api.get(f"{BASE}/goods-groups")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [g["code"] for g in items] == list(core.GOODS_GROUPS)
    assert set(items[0]) == {"code", "name", "sort_order", "is_food", "base_price", "norm_per_1000", "norm_days",
                             "prosperity_elasticity", "price_elasticity", "inputs", "updated_at"}
    weapons = next(g for g in items if g["code"] == "weapons")
    assert weapons["inputs"] == [{"input_code": "ore_metal", "ratio": 3.0}]


def test_goods_group_update_with_inputs(api):
    body = {**GROUP_BODY, "name": "  Еда  ", "base_price": 4, "inputs": [{"input_code": "herbs", "ratio": 0.5}]}
    resp = api.put(f"{BASE}/goods-groups/food", json=body)
    assert resp.status_code == 200, resp.text
    group = resp.json()
    assert group["name"] == "Еда" and group["base_price"] == 4
    assert group["inputs"] == [{"input_code": "herbs", "ratio": 0.5}]
    # Replaces the chain: clearing the inputs removes them.
    resp = api.put(f"{BASE}/goods-groups/food", json=GROUP_BODY)
    assert resp.json()["inputs"] == []


def test_goods_group_chain_self_input_and_cycle_400(api):
    resp = api.put(f"{BASE}/goods-groups/food", json={**GROUP_BODY, "inputs": [{"input_code": "food", "ratio": 1}]})
    assert resp.status_code == 400 and resp.json()["detail"] == "Группа не может быть сырьём сама для себя"
    # weapons <- ore_metal already; ore_metal <- weapons closes the loop.
    ore = {**GROUP_BODY, "name": "Руда и металл", "inputs": [{"input_code": "weapons", "ratio": 1}]}
    resp = api.put(f"{BASE}/goods-groups/ore_metal", json=ore)
    assert resp.status_code == 400 and resp.json()["detail"] == "Цепочка производства замыкается в круг"
    # Longer loop: wood <- household (household <- wood).
    wood = {**GROUP_BODY, "name": "Древесина", "inputs": [{"input_code": "household", "ratio": 1}]}
    assert api.put(f"{BASE}/goods-groups/wood", json=wood).status_code == 400
    # Raw group may get a non-cyclic input.
    herbs = {**GROUP_BODY, "name": "Травы", "inputs": [{"input_code": "wood", "ratio": 1}]}
    assert api.put(f"{BASE}/goods-groups/herbs", json=herbs).status_code == 200


def test_goods_group_unknown_404(api):
    assert api.put(f"{BASE}/goods-groups/gold", json=GROUP_BODY).status_code == 404


@pytest.mark.parametrize("patch", [
    {"name": "<script>alert(1)</script>"}, {"name": "   "}, {"name": "x" * 101}, {"base_price": 0},
    {"base_price": 1.5}, {"base_price": 1_000_001}, {"norm_per_1000": -1}, {"norm_per_1000": 100_001},
    {"norm_days": 0.4}, {"norm_days": 366}, {"prosperity_elasticity": 3.1}, {"price_elasticity": -0.1},
    {"inputs": [{"input_code": "gold", "ratio": 1}]}, {"inputs": [{"input_code": "herbs", "ratio": 0}]},
    {"inputs": [{"input_code": "herbs", "ratio": 101}]},
    {"inputs": [{"input_code": "herbs", "ratio": 1}, {"input_code": "herbs", "ratio": 2}]},
])
def test_goods_group_validation_422(api, patch):
    assert api.put(f"{BASE}/goods-groups/food", json={**GROUP_BODY, **patch}).status_code == 422


# --------------------------------------------------------------------------------------------- templates

def test_templates_list_shape(api):
    items = api.get(f"{BASE}/templates").json()["items"]
    assert [t["code"] for t in items] == [t[0] for t in mig.TEMPLATES]
    assert set(items[0]) == {"code", "name", "description", "settlement_noun", "noun_gender", "default_population",
                             "tax_rate", "sort_order", "updated_at", "goods"}
    assert [g["group_code"] for g in items[0]["goods"]] == list(core.GOODS_GROUPS)


def test_template_update_partial_goods(api):
    before = {g["group_code"]: g for g in next(t for t in api.get(f"{BASE}/templates").json()["items"]
                                             if t["code"] == "rural")["goods"]}
    body = {**TEMPLATE_BODY, "settlement_noun": "Деревня", "description": "  ",
            "goods": [{"group_code": "wood", "production_per_1000": 50, "consumption_mult": 2}]}
    resp = api.put(f"{BASE}/templates/rural", json=body)
    assert resp.status_code == 200, resp.text
    tpl = resp.json()
    assert tpl["settlement_noun"] == "Деревня" and tpl["description"] is None
    goods = {g["group_code"]: g for g in tpl["goods"]}
    assert goods["wood"] == {"group_code": "wood", "production_per_1000": 50.0, "consumption_mult": 2.0}
    assert goods["food"]["production_per_1000"] == pytest.approx(before["food"]["production_per_1000"])


def test_template_unknown_404(api):
    assert api.put(f"{BASE}/templates/atlantis", json=TEMPLATE_BODY).status_code == 404


@pytest.mark.parametrize("patch", [
    {"name": "<script>alert(1)</script>"}, {"description": "<b>жирный</b>"}, {"settlement_noun": "Город>"},
    {"settlement_noun": ""}, {"settlement_noun": "x" * 51}, {"noun_gender": "x"}, {"noun_gender": None},
    {"default_population": -1}, {"default_population": 10_000_001}, {"default_population": 2.5},
    {"tax_rate": 0.51}, {"tax_rate": -0.1}, {"description": "x" * 501},
    {"goods": [{"group_code": "gold", "production_per_1000": 1, "consumption_mult": 1}]},
    {"goods": [{"group_code": "food", "production_per_1000": 1, "consumption_mult": 10.5}]},
    {"goods": [{"group_code": "food", "production_per_1000": 1, "consumption_mult": 1},
               {"group_code": "food", "production_per_1000": 1, "consumption_mult": 1}]},
])
def test_template_validation_422(api, patch):
    assert api.put(f"{BASE}/templates/rural", json={**TEMPLATE_BODY, **patch}).status_code == 422


# --------------------------------------------------------------------------------------------- item groups

ITEM_KEYS = {"item_id", "name", "item_type", "item_rarity", "resource_subcategory", "is_food", "price", "image",
             "auto_group", "auto_off_market", "override_group", "override_off_market", "group", "off_market",
             "in_quests"}


def _items(api, **params):
    resp = api.get(f"{BASE}/item-groups", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_item_groups_shape_auto_rule_and_in_quests(api):
    page = _items(api)
    assert set(page) == {"items", "total", "page", "page_size"}
    assert page["total"] == len(ITEMS) and page["page"] == 1 and page["page_size"] == 50
    items = {i["item_id"]: i for i in page["items"]}
    for item in items.values():
        assert set(item) == ITEM_KEYS
    assert items[1]["group"] == "food" and items[2]["group"] == "ore_metal" and items[4]["group"] == "weapons"
    assert items[3]["group"] is None and items[3]["off_market"] is True                 # scroll
    assert items[6]["group"] == "weapons" and items[6]["off_market"] is True            # legendary
    assert items[5]["group"] is None and items[5]["off_market"] is False
    assert items[2]["in_quests"] is True and items[1]["in_quests"] is True              # collect / deliver
    assert items[4]["in_quests"] is False                                               # kill objective only
    assert all(i["override_group"] is None and i["override_off_market"] is None for i in items.values())


def test_item_groups_filters(api):
    assert {i["item_id"] for i in _items(api, group="none")["items"]} == {3, 5, 7}
    assert {i["item_id"] for i in _items(api, group="weapons")["items"]} == {4, 6}
    assert {i["item_id"] for i in _items(api, off_market=True)["items"]} == {3, 6}
    assert {i["item_id"] for i in _items(api, item_type="weapon")["items"]} == {4, 6}
    assert _items(api, source="manual")["total"] == 0
    assert _items(api, source="auto")["total"] == len(ITEMS)
    assert {i["item_id"] for i in _items(api, q="руда")["items"]} == {2}
    page = _items(api, page=2, page_size=3)
    assert page["total"] == len(ITEMS) and len(page["items"]) == 3
    assert len(_items(api, page=3, page_size=3)["items"]) == 1


def test_item_groups_like_wildcards_are_literal(api):
    assert {i["item_id"] for i in _items(api, q="100%")["items"]} == {7}
    assert {i["item_id"] for i in _items(api, q="%_")["items"]} == {7}
    assert _items(api, q="%")["total"] == 1


@pytest.mark.parametrize("q", ["' OR '1'='1", "'; DROP TABLE items; --", "\" OR 1=1 --", "!", "Меч') --"])
def test_item_groups_sql_injection_like_q_is_safe(api, engine, q):
    assert _items(api, q=q)["total"] == 0
    assert _q(engine, "SELECT COUNT(*) FROM items") == len(ITEMS)


@pytest.mark.parametrize("params", [
    {"item_type": "dragon"}, {"group": "gold"}, {"source": "magic"}, {"q": "x" * 101},
])
def test_item_groups_bad_filters_400(api, params):
    assert api.get(f"{BASE}/item-groups", params=params).status_code == 400


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 101}, {"page_size": 0}, {"off_market": "maybe"}])
def test_item_groups_bad_paging_422(api, params):
    assert api.get(f"{BASE}/item-groups", params=params).status_code == 422


def test_item_groups_bulk_set_null_and_reset(api, engine):
    resp = api.put(f"{BASE}/item-groups", json={"item_ids": [5, 1, 5, 999], "group_code": "tools"})
    assert resp.status_code == 200 and resp.json() == {"updated": 2}                    # dedup, 999 ignored
    items = {i["item_id"]: i for i in _items(api)["items"]}
    assert items[5]["group"] == "tools" and items[5]["override_group"] == "tools" and items[5]["auto_group"] is None
    assert items[1]["group"] == "tools" and items[1]["auto_group"] == "food"
    assert {i["item_id"] for i in _items(api, source="manual")["items"]} == {1, 5}
    assert _q(engine, "SELECT updated_by_user_id FROM econ_item_groups WHERE item_id = 5") == 7

    # off_market only: the group override stays.
    assert api.put(f"{BASE}/item-groups", json={"item_ids": [1], "off_market": True}).json() == {"updated": 1}
    item1 = {i["item_id"]: i for i in _items(api)["items"]}[1]
    assert item1["group"] == "tools" and item1["off_market"] is True

    # null = back to auto; both null -> the override row disappears.
    api.put(f"{BASE}/item-groups", json={"item_ids": [5], "group_code": None})
    assert _q(engine, "SELECT COUNT(*) FROM econ_item_groups WHERE item_id = 5") == 0
    item5 = {i["item_id"]: i for i in _items(api)["items"]}[5]
    assert item5["group"] is None and item5["override_group"] is None

    resp = api.put(f"{BASE}/item-groups", json={"item_ids": [1], "reset": True})
    assert resp.status_code == 200 and resp.json() == {"updated": 1}
    assert _q(engine, "SELECT COUNT(*) FROM econ_item_groups") == 0
    assert _items(api, source="manual")["total"] == 0


def test_item_groups_null_on_new_row_creates_nothing(api, engine):
    resp = api.put(f"{BASE}/item-groups", json={"item_ids": [2], "group_code": None, "off_market": None})
    assert resp.status_code == 200
    assert _q(engine, "SELECT COUNT(*) FROM econ_item_groups") == 0


def test_item_groups_only_unknown_ids(api):
    assert api.put(f"{BASE}/item-groups", json={"item_ids": [999], "off_market": True}).json() == {"updated": 0}


def test_item_groups_bulk_500_ok_501_rejected(api):
    assert api.put(f"{BASE}/item-groups", json={"item_ids": list(range(1, 501)), "off_market": False}
                   ).json() == {"updated": len(ITEMS)}
    resp = api.put(f"{BASE}/item-groups", json={"item_ids": list(range(1, 502)), "off_market": False})
    assert resp.status_code == 422


def test_item_groups_reset_cannot_combine_and_nothing_to_change(api, engine):
    resp = api.put(f"{BASE}/item-groups", json={"item_ids": [1], "reset": True, "group_code": "food"})
    assert resp.status_code == 400
    resp = api.put(f"{BASE}/item-groups", json={"item_ids": [1], "reset": True, "off_market": None})
    assert resp.status_code == 400
    resp = api.put(f"{BASE}/item-groups", json={"item_ids": [1]})
    assert resp.status_code == 400 and resp.json()["detail"] == "Не указано, что менять"
    assert _q(engine, "SELECT COUNT(*) FROM econ_item_groups") == 0


@pytest.mark.parametrize("body", [
    {"item_ids": [], "off_market": True}, {"item_ids": ["1"], "off_market": True},
    {"item_ids": [0], "off_market": True}, {"item_ids": [1], "group_code": "gold"},
    {"item_ids": [1], "off_market": "yes"}, {"item_ids": [1], "reset": 1}, {"off_market": True},
])
def test_item_groups_put_validation_422(api, body):
    assert api.put(f"{BASE}/item-groups", json=body).status_code == 422


# --------------------------------------------------------------------------------------------- sim settings / run

def test_sim_get_shape(api):
    resp = api.get(f"{BASE}/sim")
    assert resp.status_code == 200
    sim = resp.json()
    assert set(sim) == {"tick_enabled", "env_enabled", "params", "current_slot_start", "next_slot_at", "running",
                        "runs"}
    assert sim["tick_enabled"] is True and sim["running"] is None and sim["runs"] == []
    assert set(sim["params"]) == set(ECON_SIM_PARAM_BOUNDS)
    assert sim["params"]["price_max"] == 3.0


def test_sim_put_merges_params(api):
    resp = api.put(f"{BASE}/sim", json={"tick_enabled": False, "params": {"price_max": 4.5, "dt": "0.5"}})
    assert resp.status_code == 200, resp.text
    sim = resp.json()
    assert sim["tick_enabled"] is False
    assert sim["params"]["price_max"] == 4.5 and sim["params"]["dt"] == 0.5
    assert sim["params"]["price_min"] == 0.5                                 # untouched key kept
    assert api.get(f"{BASE}/sim").json()["params"]["price_max"] == 4.5


@pytest.mark.parametrize("key", sorted(ECON_SIM_PARAM_BOUNDS))
def test_sim_params_bounds(api, key):
    lo, hi = ECON_SIM_PARAM_BOUNDS[key]
    step = 1 if key in ECON_SIM_INT_PARAMS else 0.01
    for bad in (lo - step, hi + step):
        resp = api.put(f"{BASE}/sim", json={"tick_enabled": True, "params": {key: bad}})
        assert resp.status_code == 422, (key, bad, resp.text)
    for good in (lo, hi):
        if key in ("price_min", "price_max", "prod_price_min", "prod_price_max"):
            continue                                                # bound values may hit the cross-field rule
        resp = api.put(f"{BASE}/sim", json={"tick_enabled": True, "params": {key: good}})
        assert resp.status_code == 200, (key, good, resp.text)


@pytest.mark.parametrize("key", sorted(ECON_SIM_INT_PARAMS))
def test_sim_int_params_reject_fractions(api, key):
    resp = api.put(f"{BASE}/sim", json={"tick_enabled": True, "params": {key: 10.5}})
    assert resp.status_code == 422


@pytest.mark.parametrize("body", [
    {"tick_enabled": True, "params": {"unknown_knob": 1}},
    {"tick_enabled": "yes", "params": {}},
    {"params": {}},
    {"tick_enabled": True, "params": {"dt": True}},
    {"tick_enabled": True, "params": {"dt": "быстро"}},
    {"tick_enabled": True, "params": {"dt": "NaN"}},
])
def test_sim_put_validation_422(api, body):
    assert api.put(f"{BASE}/sim", json=body).status_code == 422


@pytest.mark.parametrize("params", [
    {"price_min": 1.0, "price_max": 1.0},
    {"prod_price_min": 1.0, "prod_price_max": 1.0},
])
def test_sim_put_cross_field_rules(api, params):
    resp = api.put(f"{BASE}/sim", json={"tick_enabled": False, "params": params})
    assert resp.status_code == 400, resp.text
    sim = api.get(f"{BASE}/sim").json()
    assert sim["params"]["price_max"] == 3.0 and sim["tick_enabled"] is True        # nothing stored


def test_sim_put_cross_field_rule_uses_stored_values(api):
    assert api.put(f"{BASE}/sim", json={"tick_enabled": True, "params": {"price_min": 1.0}}).status_code == 200
    # stored price_min 1.0 now; price_max 1.0 alone breaks price_min < price_max.
    assert api.put(f"{BASE}/sim", json={"tick_enabled": True, "params": {"price_max": 1.0}}).status_code == 400


def test_sim_run_summary_and_ledger(world, engine):
    world.post(f"{BASE}/regions/fill", json=FILL)
    resp = world.post(f"{BASE}/sim/run")
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert {"id", "trigger_kind", "status", "regions_total", "regions_done", "regions_failed", "started_at",
            "finished_at"} <= set(run)
    assert run["trigger_kind"] == "manual" and run["status"] == "done"
    assert (run["regions_total"], run["regions_done"], run["regions_failed"]) == (2, 2, 0)   # 20 has population 0
    assert _q(engine, "SELECT actor_user_id FROM econ_tick_runs WHERE id = :i", i=run["id"]) == 7
    assert _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_tick'") == 2
    sim = world.get(f"{BASE}/sim").json()
    assert sim["running"] is None and [r["id"] for r in sim["runs"]] == [run["id"]]
    assert _region(world, 10)["last_tick_at"] is not None
    _assert_ledger_closes(engine, world)


def test_sim_run_409_while_a_run_is_alive(world, engine):
    session = sessionmaker(bind=engine)()
    alive = models.EconTickRun(slot=None, trigger_kind="manual", status="running",
                               started_at=econ_tick._utcnow(), heartbeat_at=econ_tick._utcnow())
    session.add(alive)
    session.commit()
    session.close()
    resp = world.post(f"{BASE}/sim/run")
    assert resp.status_code == 409 and resp.json()["detail"] == "Пересчёт уже идёт, попробуйте позже"
    assert _q(engine, "SELECT COUNT(*) FROM econ_tick_runs") == 1
    assert _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_tick'") == 0
    assert world.get(f"{BASE}/sim").json()["running"]["status"] == "running"


# --------------------------------------------------------------------------------------------- operations / summary

def test_operations_exclude_op_type(world, engine):
    world.post(f"{BASE}/regions/fill", json=FILL)
    world.post(f"{BASE}/sim/run")
    total = _ops(engine)
    ticks = _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_tick'")
    assert ticks == 2 and total == 4
    resp = world.get(f"{BASE}/operations", params={"exclude_op_type": "region_tick"})
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == total - ticks
    assert all(op["op_type"] != "region_tick" for op in page["items"])
    only = world.get(f"{BASE}/operations", params={"op_type": "region_tick"}).json()
    assert only["total"] == ticks
    assert world.get(f"{BASE}/operations", params={"exclude_op_type": "bogus"}).status_code == 400
    assert world.get(f"{BASE}/operations", params={"exclude_op_type": ""}).json()["total"] == total


def test_summary_population_purses(world, engine):
    world.post(f"{BASE}/regions/fill", json=FILL)
    summary = world.get(f"{BASE}/summary").json()
    purses = _balance(engine, "population_purse", 10) + _balance(engine, "population_purse", 30)
    assert summary["totals"]["population_purses"] == purses > 0
    regions = {r["region_id"]: r for c in summary["countries"] for r in c["regions"]}
    assert regions[10]["purse_balance"] == _balance(engine, "population_purse", 10)
    assert regions[10]["purse_account_id"] is not None
    assert regions[40]["purse_account_id"] is None and regions[40]["purse_balance"] is None
    assert summary["invariant"]["ok"] is True


# --------------------------------------------------------------------------------------------- public card

CARD_KEYS = {"region_id", "participating", "updated_at", "food", "treasury", "stability", "prosperity",
             "price_level", "shortages", "surpluses", "phrases", "groups"}


def _numbers(value, path=""):
    """Every numeric leaf of a JSON value (bools excluded) as (path, value)."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [(path, value)]
    if isinstance(value, dict):
        return [n for k, v in value.items() for n in _numbers(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [n for i, v in enumerate(value) for n in _numbers(v, f"{path}[{i}]")]
    return []


def test_card_shape_has_no_money_numbers(world):
    world.post(f"{BASE}/regions/fill", json=FILL)
    world.post(f"{BASE}/sim/run")
    resp = TestClient(app).get("/characters/economy/regions/10/card")
    assert resp.status_code == 200
    card = resp.json()
    assert set(card) == CARD_KEYS
    assert card["participating"] is True and card["updated_at"] is not None
    assert _numbers(card) == [(".region_id", 10)]                           # only the id is numeric
    for block in ("food", "treasury", "stability", "prosperity", "price_level"):
        assert set(card[block]) == {"state", "label"}
    assert card["food"]["state"] in ("fed", "tight", "hunger")
    assert card["food"]["label"].startswith("Крепость")                      # fortress noun, feminine
    if card["food"]["state"] == "fed":
        assert card["food"]["label"] == "Крепость сыта"
    assert [g["code"] for g in card["groups"]] == list(core.GOODS_GROUPS)
    assert all(set(g) == {"code", "name", "level", "trend"} for g in card["groups"])
    assert card["phrases"][0] == card["food"]["label"]
    text_dump = resp.text
    for word in ("purse", "balance", "stock", "price_mult", "treasury_target", "population"):
        assert word not in text_dump


def test_card_participating_false(world):
    world.put(f"{BASE}/regions/30", json={"template_code": None, "population": 8000, "tax_rate": 0.1})
    client = TestClient(app)
    for region_id in (20, 30, 40, 999, 0, -5):                # pop 0, no template, no row, unknown, bad ids
        resp = client.get(f"/characters/economy/regions/{region_id}/card")
        assert resp.status_code == 200
        assert resp.json() == {"region_id": region_id, "participating": False}
    assert client.get("/characters/economy/regions/abc/card").status_code == 422


def test_card_before_any_tick(world):
    card = TestClient(app).get("/characters/economy/regions/30/card").json()
    assert card["participating"] is True and card["updated_at"] is None
    assert card["food"]["label"] == "Край сыт"                               # agrarian noun, masculine

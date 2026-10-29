"""FEAT-183 Q3: admin API of the NPC merchants (contract 3.7) on SQLite.

GET  /characters/admin/economy/merchants        — economy:read
POST /characters/admin/economy/merchants/fund   — economy:settings AND economy:emit

Own in-memory database per test (character-service metadata + conftest hierarchy), migration-028 seed, plus the
foreign tables the endpoints read: ``Locations.marker_type``, ``items``, ``npc_shop_items`` (DDL from
``econ_contract_cases.MERCHANT_SQLITE_DDL``) and the auction tables of the summary invariant.

World:
    region 10 «Ост» (fortress) <- location 100 (safe), 101 (dungeon); region 20 «Пашни» (rural) <- 200;
    region 30 «Глушь» (no economy) <- 300
    NPC 31 @100 cash 0     — bread (4, target 10), ore (30, target 5, stock NULL), scroll (off-market)   target 190
    NPC 32 @100 cash 10000 — bread (target 10)                                                          at target
    NPC 35 @200 cash 50    — bread (40, target 10)                                                      target 400
    NPC 37 @100 cash 0     — a player-origin row only                                                   no target
    NPC 38 @100            — an inactive row only (listed, but not a fund candidate)
    NPC 33 @101 (dungeon), 34 @300 (not simulated), 36 dead @100                                       legacy
"""

import importlib.util
import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import econ_core as core
import econ_ledger
import econ_tick
import economy_api
import models
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.econ_contract_cases import MERCHANT_SQLITE_DDL

MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "028_econ_living_regions.py")
_spec = importlib.util.spec_from_file_location("migration_028_for_merchants_api", MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

BASE = "/characters/admin/economy"
LIST_URL = f"{BASE}/merchants"
FUND_URL = f"{BASE}/merchants/fund"
ALL_PERMS = ["economy:read", "economy:emit", "economy:adjust", "economy:settings"]
FUND = {"comment": "Пополнение касс"}
SOURCE = "character-service"

EXTRA_DDL = [ddl for ddl in MERCHANT_SQLITE_DDL
             if ddl.lstrip().startswith(("CREATE TABLE items", "CREATE TABLE npc_shop_items"))] + [
    """CREATE TABLE auction_listings (id INTEGER PRIMARY KEY, current_bid INTEGER NOT NULL DEFAULT 0,
        current_bidder_id INTEGER NULL, status VARCHAR(20) NOT NULL DEFAULT 'active')""",
    "CREATE TABLE auction_storage (id INTEGER PRIMARY KEY, gold_amount INTEGER NOT NULL DEFAULT 0)",
]

ITEMS = [
    (1, "Хлеб", "consumable", "common", None, 1),
    (2, "Железная руда", "resource", "common", "ore", 0),
    (3, "Свиток", "scroll", "rare", None, 0),
    (4, "Меч", "weapon", "common", None, 0),
]

NPCS = [  # id, status, location, cash
    (31, "alive", 100, 0), (32, "alive", 100, 10_000), (35, "alive", 200, 50), (37, "alive", 100, 0),
    (38, "alive", 100, 0), (33, "alive", 101, 0), (34, "alive", 300, 0), (36, "dead", 100, 0),
]

SHOP_ROWS = [  # id, npc_id, item_id, buy, sell, stock, is_active, restock_target, origin
    (1, 31, 1, 4, 2, 3, 1, 10, "admin"),
    (2, 31, 2, 30, 12, None, 1, 5, "admin"),
    (3, 31, 3, 60, 0, 2, 1, 5, "admin"),
    (4, 32, 1, 4, 2, 10, 1, 10, "admin"),
    (5, 35, 1, 40, 20, 10, 1, 10, "admin"),
    (6, 37, 4, 150, 60, 2, 1, 0, "player"),
    (7, 38, 1, 4, 2, 5, 0, 10, "admin"),
    (8, 33, 1, 4, 2, None, 1, 10, "admin"),
    (9, 34, 1, 4, 2, 4, 1, 10, "admin"),
    (10, 36, 1, 4, 2, 4, 1, 10, "admin"),
]

TARGETS = {31: 2 * (10 * 2 + 5 * 15), 32: 2 * 10 * 2, 35: 2 * 10 * 20}     # cash_target_mult x Σ target x wholesale


# --------------------------------------------------------------------------------------------- fixtures

@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=eng)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    db = factory()
    db.execute(text("ALTER TABLE Locations ADD COLUMN marker_type VARCHAR(16) NOT NULL DEFAULT 'safe'"))
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
    db.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Мидденгерд')"))
    db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Ост', 1), (20, 'Пашни', 1), "
                    "(30, 'Глушь', 1)"))
    db.execute(text("INSERT INTO Locations (id, name, region_id, marker_type) VALUES (100, 'Рынок', 10, 'safe'), "
                    "(101, 'Склеп', 10, 'dungeon'), (200, 'Село', 20, 'safe'), (300, 'Хутор', 30, 'safe')"))
    for item in ITEMS:
        db.execute(text("INSERT INTO items (id, name, item_type, item_rarity, resource_subcategory, is_food, price) "
                        "VALUES (:i, :n, :t, :r, :s, :f, 10)"),
                   {"i": item[0], "n": item[1], "t": item[2], "r": item[3], "s": item[4], "f": item[5]})
    with econ_ledger.allow_direct_balance_write(db):
        for npc_id, status, location, _cash in NPCS:
            db.add(models.Character(id=npc_id, name=f"НПС {npc_id}", id_subrace=1, id_class=1, id_race=1,
                                    appearance="-", avatar="-", is_npc=True, npc_status=status,
                                    current_location_id=location, currency_balance=0))
        db.flush()
    for npc_id, _status, _location, cash in NPCS:
        if cash:
            econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                       legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.character(npc_id),
                                                      cash)])
    for row in SHOP_ROWS:
        db.execute(text("INSERT INTO npc_shop_items (id, npc_id, item_id, buy_price, sell_price, stock, is_active, "
                        "restock_target, origin) VALUES (:a, :b, :c, :d, :e, :f, :g, :h, :i)"),
                   dict(zip("abcdefghi", row)))
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
    eng.factory = factory
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
    client = TestClient(app)
    for region_id, template in ((10, "fortress"), (20, "rural")):
        resp = client.put(f"{BASE}/regions/{region_id}",
                          json={"template_code": template, "population": 3000, "tax_rate": 0.1})
        assert resp.status_code == 200, resp.text
    return client


def _q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def _cash(engine, npc_id):
    return int(_q(engine, "SELECT currency_balance FROM characters WHERE id = :i", i=npc_id))


def _ops(engine):
    return _q(engine, "SELECT COUNT(*) FROM econ_operations")


def _assert_invariant(engine, api):
    accounts = int(_q(engine, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character'"))
    characters = int(_q(engine, "SELECT COALESCE(SUM(currency_balance), 0) FROM characters"))
    assert accounts + characters == 0
    assert _q(engine, "SELECT COUNT(*) FROM characters WHERE currency_balance < 0") == 0
    resp = api.get(f"{BASE}/summary")
    assert resp.status_code == 200, resp.text
    invariant = resp.json()["invariant"]
    assert invariant["ok"] is True, invariant
    assert invariant["ledger_sum"] == 0


def _items(resp):
    assert resp.status_code == 200, resp.text
    return {m["npc_id"]: m for m in resp.json()["items"]}


# --------------------------------------------------------------------------------------------- RBAC

ENDPOINTS = [("get", LIST_URL, None), ("post", FUND_URL, FUND)]


@pytest.mark.parametrize("method,url,body", ENDPOINTS, ids=["list", "fund"])
def test_401_without_token(engine, method, url, body):
    resp = getattr(TestClient(app), method)(url, **({"json": body} if body else {}))
    assert resp.status_code == 401
    assert _ops(engine) == NPC_FUNDING_OPS


NPC_FUNDING_OPS = 2       # the fixture's opening balances of NPC 32 and 35


@pytest.mark.parametrize("perms", [["economy:settings"], ["economy:emit"], ["economy:read", "economy:adjust"],
                                   ["economy:read", "economy:emit", "economy:adjust"],
                                   ["economy:read", "economy:settings", "economy:adjust"],
                                   ["characters:update", "items:create"]])
def test_fund_needs_both_settings_and_emit(api, engine, perms):
    _as_user(perms)
    resp = TestClient(app).post(FUND_URL, json=FUND)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Недостаточно прав"
    assert _ops(engine) == NPC_FUNDING_OPS
    assert _cash(engine, 31) == 0


def test_fund_allowed_with_exactly_settings_and_emit(api, engine):
    _as_user(["economy:settings", "economy:emit"], user_id=42)
    resp = TestClient(app).post(FUND_URL, json=FUND)
    assert resp.status_code == 200, resp.text
    assert resp.json()["emitted"] > 0
    assert _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'admin_emission' "
                      "AND actor_user_id = 42") == 2


@pytest.mark.parametrize("perms", [["economy:emit", "economy:settings", "economy:adjust"], ["characters:read"], []])
def test_list_needs_read(api, perms):
    _as_user(perms)
    resp = TestClient(app).get(LIST_URL)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Недостаточно прав"


def test_list_allowed_with_only_read(api):
    _as_user(["economy:read"])
    client = TestClient(app)
    assert client.get(LIST_URL).status_code == 200
    assert client.post(FUND_URL, json=FUND).status_code == 403


# --------------------------------------------------------------------------------------------- list

ITEM_KEYS = {"npc_id", "name", "location_id", "region_id", "region_name", "living", "reason", "tax_rate", "cash",
             "cash_target", "rows", "stock_value", "last_trade"}
ROW_KEYS = {"row_id", "item_id", "item_name", "group", "off_market", "origin", "is_active", "base_buy", "base_sell",
            "ask", "bid", "market", "stock", "restock_target"}


def test_list_shape_and_statuses(api, engine):
    resp = api.get(LIST_URL)
    body = resp.json()
    items = _items(resp)
    assert set(items) == {31, 32, 33, 34, 35, 36, 37, 38}
    assert [m["npc_id"] for m in body["items"]] == sorted(items)
    for m in items.values():
        assert set(m) == ITEM_KEYS
        for r in m["rows"]:
            assert set(r) == ROW_KEYS
    assert body["totals"] == {"merchants": 8, "living": 5, "cash": 10_050}

    m31 = items[31]
    assert (m31["living"], m31["reason"], m31["region_id"], m31["region_name"], m31["location_id"]) == \
        (True, None, 10, "Ост", 100)
    assert m31["cash_target"] == TARGETS[31] and m31["cash"] == 0
    assert m31["name"] == "НПС 31" and m31["last_trade"] is None
    assert items[32]["cash_target"] == TARGETS[32]
    assert items[35]["cash_target"] == TARGETS[35] and items[35]["region_name"] == "Пашни"
    assert items[37]["cash_target"] == 0
    assert (items[33]["living"], items[33]["reason"]) == (False, core.MERCHANT_REASON_DUNGEON)
    assert (items[34]["living"], items[34]["reason"]) == (False, core.MERCHANT_REASON_NOT_SIMULATED)
    assert (items[36]["living"], items[36]["reason"]) == (False, core.MERCHANT_REASON_DEAD)
    for legacy in (33, 34, 36):
        assert items[legacy]["cash_target"] == 0 and items[legacy]["last_trade"] is None


def test_list_rows_prices_and_stock(api, engine):
    items = _items(api.get(LIST_URL))
    rows = {r["row_id"]: r for r in items[31]["rows"]}
    assert [r["row_id"] for r in items[31]["rows"]] == [1, 2, 3]
    bread_mult = _q(engine, "SELECT price_mult FROM econ_region_goods WHERE region_id = 10 AND group_code = 'food'")
    ore_mult = _q(engine, "SELECT price_mult FROM econ_region_goods WHERE region_id = 10 "
                          "AND group_code = 'ore_metal'")
    assert rows[1]["group"] == "food" and rows[1]["market"] is True and rows[1]["off_market"] is False
    assert rows[1]["ask"] == core.market_ask(4, bread_mult)
    assert rows[1]["bid"] == core.market_bid(2, bread_mult, rows[1]["ask"])
    assert rows[2]["ask"] == core.market_ask(30, ore_mult)
    assert rows[2]["stock"] == 0                                   # living: NULL -> 0
    assert rows[2]["item_name"] == "Железная руда" and rows[2]["base_buy"] == 30 and rows[2]["base_sell"] == 12
    assert rows[3]["off_market"] is True and rows[3]["market"] is False and rows[3]["ask"] == 60
    assert items[31]["stock_value"] == 3 * rows[1]["ask"] + 2 * rows[3]["ask"]
    legacy = items[33]["rows"][0]
    assert legacy["stock"] is None and legacy["ask"] == 4 and legacy["market"] is False   # legacy NULL = unlimited
    assert items[37]["rows"][0]["origin"] == "player"
    inactive = items[38]["rows"][0]
    assert inactive["is_active"] is False
    assert items[38]["stock_value"] == 0 and items[38]["cash_target"] == 0


def test_list_filters(api):
    assert set(_items(api.get(LIST_URL, params={"region_id": 10}))) == {31, 32, 33, 36, 37, 38}
    assert set(_items(api.get(LIST_URL, params={"region_id": 20}))) == {35}
    assert set(_items(api.get(LIST_URL, params={"region_id": 999}))) == set()
    assert set(_items(api.get(LIST_URL, params={"living": "true"}))) == {31, 32, 35, 37, 38}
    assert set(_items(api.get(LIST_URL, params={"living": "false"}))) == {33, 34, 36}
    both = api.get(LIST_URL, params={"region_id": 10, "living": "false"})
    assert set(_items(both)) == {33, 36}
    assert both.json()["totals"] == {"merchants": 2, "living": 0, "cash": 0}


@pytest.mark.parametrize("params", [{"region_id": 0}, {"region_id": "x"}, {"living": "maybe"},
                                    {"region_id": "1; DROP TABLE npc_shop_items"}])
def test_list_bad_query_is_422(api, engine, params):
    assert api.get(LIST_URL, params=params).status_code == 422
    assert _q(engine, "SELECT COUNT(*) FROM npc_shop_items") == len(SHOP_ROWS)


def test_list_without_shops_is_empty(api, engine):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM npc_shop_items"))
        conn.commit()
    resp = api.get(LIST_URL)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "totals": {"merchants": 0, "living": 0, "cash": 0}}


def test_list_shows_last_trade_after_a_tick(api, engine):
    assert api.post(FUND_URL, json=FUND).status_code == 200
    summary = econ_tick.run_tick(engine.factory, trigger="manual")
    assert summary.merchant_ops_posted >= 1
    items = _items(api.get(LIST_URL))
    trade = items[31]["last_trade"]
    assert trade is not None and trade["run_id"] == summary.run_id
    assert set(trade) == {"operation_id", "run_id", "at", "sold_items", "sold_value", "tax", "restock_items",
                          "restock_value", "upkeep"}
    meta = _q(engine, "SELECT metadata FROM econ_operations WHERE id = :i", i=trade["operation_id"])
    meta = json.loads(meta) if isinstance(meta, str) else meta
    entry = meta["merchants"]["31"]
    assert {k: trade[k] for k in entry} == entry
    assert items[33]["last_trade"] is None
    _assert_invariant(engine, api)


# --------------------------------------------------------------------------------------------- fund

def test_fund_tops_up_every_living_merchant_once(api, engine):
    resp = api.post(FUND_URL, json=FUND)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["emitted"] == TARGETS[31] + (TARGETS[35] - 50)
    assert body["merchants"] == 4 and body["funded"] == 2 and len(body["operation_ids"]) == 2
    assert body["skipped"] == [{"npc_id": 32, "reason": "at_target"}, {"npc_id": 37, "reason": "no_target"}]
    assert _cash(engine, 31) == TARGETS[31] and _cash(engine, 35) == TARGETS[35]
    assert _cash(engine, 32) == 10_000
    for npc_id in (33, 34, 36, 37, 38):
        assert _cash(engine, npc_id) == 0

    with engine.connect() as conn:
        ops = conn.execute(text("SELECT id, op_type, region_id, comment, idempotency_key, metadata, actor_user_id "
                                "FROM econ_operations WHERE id IN (:a, :b) ORDER BY id"),
                           {"a": body["operation_ids"][0], "b": body["operation_ids"][1]}).fetchall()
        legs = conn.execute(text("SELECT p.operation_id, fa.kind, ta.kind, ta.ref_id, p.amount, p.leg_type "
                                 "FROM econ_postings p JOIN econ_accounts fa ON fa.id = p.from_account_id "
                                 "JOIN econ_accounts ta ON ta.id = p.to_account_id WHERE p.operation_id IN (:a, :b) "
                                 "ORDER BY p.id"),
                            {"a": body["operation_ids"][0], "b": body["operation_ids"][1]}).fetchall()
    assert [(o[1], o[2], o[3], o[6]) for o in ops] == [("admin_emission", 10, "Пополнение касс", 7),
                                                       ("admin_emission", 20, "Пополнение касс", 7)]
    assert ops[0][4].startswith("merchant_fund:r:10:m") and ops[1][4].startswith("merchant_fund:r:20:m")
    meta = json.loads(ops[0][5]) if isinstance(ops[0][5], str) else ops[0][5]
    assert meta["merchant_fund"] is True and meta["targets"] == {"31": TARGETS[31]}
    # emission -> NPC legs only: no tax legs (apply_tax=False)
    assert [tuple(l[1:]) for l in legs] == [("emission", "character", 31, TARGETS[31], "main"),
                                           ("emission", "character", 35, TARGETS[35] - 50, "main")]
    _assert_invariant(engine, api)

    again = api.post(FUND_URL, json=FUND)
    assert again.status_code == 200
    second = again.json()
    assert second["emitted"] == 0 and second["operation_ids"] == [] and second["funded"] == 0
    assert {s["npc_id"]: s["reason"] for s in second["skipped"]} == {
        31: "at_target", 32: "at_target", 35: "at_target", 37: "no_target"}
    assert _cash(engine, 31) == TARGETS[31]
    _assert_invariant(engine, api)


def test_fund_by_npc_ids_reports_skip_reasons(api, engine):
    resp = api.post(FUND_URL, json={**FUND, "npc_ids": [999, 36, 34, 33, 38, 31, 31]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped"] == [
        {"npc_id": 33, "reason": core.MERCHANT_REASON_DUNGEON},
        {"npc_id": 34, "reason": core.MERCHANT_REASON_NOT_SIMULATED},
        {"npc_id": 36, "reason": core.MERCHANT_REASON_DEAD},
        {"npc_id": 38, "reason": "not_merchant"},           # inactive rows only
        {"npc_id": 999, "reason": "not_merchant"},
    ]
    assert body["emitted"] == TARGETS[31] and body["funded"] == 1 and body["merchants"] == 1
    assert _cash(engine, 35) == 50
    _assert_invariant(engine, api)


def test_fund_by_region(api, engine):
    body = api.post(FUND_URL, json={**FUND, "region_ids": [20]}).json()
    assert body["emitted"] == TARGETS[35] - 50 and body["funded"] == 1 and body["skipped"] == []
    assert _cash(engine, 31) == 0
    body = api.post(FUND_URL, json={**FUND, "region_ids": [20], "npc_ids": [31, 35]}).json()
    assert body["emitted"] == 0
    assert body["skipped"] == [{"npc_id": 31, "reason": "region_filtered"}, {"npc_id": 35, "reason": "at_target"}]
    body = api.post(FUND_URL, json={**FUND, "region_ids": [30, 999]}).json()
    assert body == {"merchants": 0, "funded": 0, "operation_ids": [], "emitted": 0, "skipped": []}
    _assert_invariant(engine, api)


def test_fund_tops_up_only_the_difference_after_spending(api, engine):
    api.post(FUND_URL, json=FUND)
    db = engine.factory()
    econ_ledger.post_operation(db, op_type=core.OP_ADMIN_ADJUST, source_service=SOURCE, comment="тест",
                               legs=[core.Leg(core.AccountRef.character(31), core.AccountRef.adjustment(), 40)])
    db.commit()
    db.close()
    assert _cash(engine, 31) == TARGETS[31] - 40
    body = api.post(FUND_URL, json=FUND).json()
    assert body["emitted"] == 40 and body["funded"] == 1
    assert _cash(engine, 31) == TARGETS[31]
    _assert_invariant(engine, api)


def test_concurrent_identical_fund_posts_once(api, engine, monkeypatch):
    """Two clicks computed on the same state share the idempotency key: the second one is skipped
    (DuplicateOperation) instead of emitting twice. Simulated by feeding the second call the state the first saw
    (on MySQL the NPC row lock serialises them; SQLite has a single connection here)."""
    import economy_merchants_crud as crud

    first = engine.factory()
    try:
        seen_posting = crud._last_character_posting(first, [35])
        r1 = crud.fund_merchants(first, region_ids=[20], npc_ids=None, comment="раз", actor_user_id=1)
        first.commit()
    finally:
        first.close()
    monkeypatch.setattr(econ_ledger, "lock_characters", lambda db, ids: {35: 50})
    monkeypatch.setattr(crud, "_last_character_posting", lambda db, ids: seen_posting)
    second = engine.factory()
    try:
        r2 = crud.fund_merchants(second, region_ids=[20], npc_ids=None, comment="раз", actor_user_id=1)
        second.commit()
    finally:
        second.close()
    monkeypatch.undo()
    assert r1["emitted"] == TARGETS[35] - 50 and len(r1["operation_ids"]) == 1
    assert r2["emitted"] == 0 and r2["operation_ids"] == [] and r2["funded"] == 0
    assert _cash(engine, 35) == TARGETS[35]
    _assert_invariant(engine, api)


@pytest.mark.parametrize("body", [
    {},
    {"comment": None},
    {"comment": 123},
    {"comment": "ab"},
    {"comment": "   ab   "},
    {"comment": "x" * 501},
    {**FUND, "npc_ids": []},
    {**FUND, "region_ids": []},
    {**FUND, "npc_ids": [0]},
    {**FUND, "npc_ids": [-5]},
    {**FUND, "npc_ids": ["31"]},
    {**FUND, "npc_ids": [1.5]},
    {**FUND, "region_ids": list(range(1, 502))},
    {**FUND, "npc_ids": "31; DROP TABLE characters"},
])
def test_fund_validation_is_422_and_moves_nothing(api, engine, body):
    resp = api.post(FUND_URL, json=body)
    assert resp.status_code == 422, resp.text
    assert _ops(engine) == NPC_FUNDING_OPS
    assert _cash(engine, 31) == 0


def test_fund_comment_is_stripped_and_long_comment_accepted(api, engine):
    resp = api.post(FUND_URL, json={"comment": "  " + "к" * 500 + "  ", "region_ids": [20]})
    assert resp.status_code == 200, resp.text
    comment = _q(engine, "SELECT comment FROM econ_operations WHERE id = :i", i=resp.json()["operation_ids"][0])
    assert comment == "к" * 500
    _assert_invariant(engine, api)


def test_fund_with_xss_comment_is_stored_verbatim(api, engine):
    payload = "<script>alert(1)</script>"
    resp = api.post(FUND_URL, json={"comment": payload, "region_ids": [20]})
    assert resp.status_code == 200
    assert _q(engine, "SELECT comment FROM econ_operations WHERE id = :i", i=resp.json()["operation_ids"][0]) == payload


def test_merchants_trade_in_regions_with_lore_populations(api, engine):
    """FEAT-186: residents of lore-sized regions (300 000 / 250 000 at scale 100) still buy from the merchants."""
    for region_id, template, population in ((10, "fortress", 300_000), (20, "rural", 250_000)):
        resp = api.put(f"{BASE}/regions/{region_id}",
                       json={"template_code": template, "population": population, "tax_rate": 0.1})
        assert resp.status_code == 200, resp.text
    assert api.post(f"{BASE}/regions/fill", json={"comment": "Заполнение для теста"}).status_code == 200
    assert api.post(FUND_URL, json=FUND).status_code == 200
    summary = econ_tick.run_tick(engine.factory, trigger="manual")
    assert summary.status == "done" and summary.merchant_ops_posted >= 1
    trade = _items(api.get(LIST_URL))[31]["last_trade"]
    assert trade is not None and trade["sold_items"] > 0 and trade["sold_value"] > 0
    assert _q(engine, "SELECT COUNT(*) FROM characters WHERE currency_balance < 0") == 0
    _assert_invariant(engine, api)

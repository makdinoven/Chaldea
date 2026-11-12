"""FEAT-193 QA (#10): player guild API at a «Гильдия торговцев» (contract 3.6 / 3.6a / 3.10) on SQLite.

The FEAT-145 gate (``locations_client.check_npc_gate``) and the quest XP book lookups
(``crud.get_character_xp_multiplier[_async]``) are mocked. Shared tables of other services get their real columns:
``items`` / ``character_inventory`` (inventory-service), ``npc_shop_items`` (locations-service), ``quest_objectives``,
``character_attributes`` (character-attributes-service).

World (seed of ``test_econ_tick.factory``: goods groups wood base 5, food base 2, ore_metal base 10):
    region 10 «Регион 10» (rural, purse 100 000), region 20 (rural); all price_mult 1
    locations 100 @10 (safe), 150 @10 (dungeon), 200 @20, 300 (no region)
    players: 1 «Альфа» (user 7) @100 (attributes row, 0 XP, level 2), 2 «Бета» (user 8) @200,
             3 «Гамма» (user 9) @100 (no attributes row)
    guild NPCs: 60 @100, 61 dead @100, 62 @200, 64 @300 (no region); 63 banker @100
    merchants: 70 living @100, 71 legacy @150 (dungeon of region 10), 72 dead @100, 73 living @200 (other region)
    orders of region 10: wood 100 units, food 100 units; guild_budget 5 000, guild_food_budget 0
    items (wood unless noted; price 10 -> 2 units per piece, offer floor(10 x 1 x 1.2) = 12):
        600 WOOD, 601 PLANK (price 0 -> group base 5: 1 unit, offer 6), 602 scroll, 603 recipe,
        604 legendary wood, 605 quest wood, 606 wood with an off-market override, 607 ore, 608 bread (food, price 10),
        609 CHEAP (living merchant asks 1 -> price 0), 610 MERCH (living asks 14 -> cap 7),
        611 BIDW (living asks 14 -> cap 7, legacy bids 13 -> 13), 612 LEGACYW (legacy asks 16 -> 8),
        613 DEADW (only a dead merchant sells it -> 12), 614 RESALE (living player-resale row, stock 0 -> 12),
        615 OTHERW (only a merchant of region 20 sells it -> 12)
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import crud
import econ_core as core
import econ_ledger
import economy_api
import economy_guild_crud as guild_crud
import locations_client
import models
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.econ_contract_cases import MERCHANT_SQLITE_DDL
from tests.test_econ_tick import _add_region, factory  # noqa: F401  (factory is a fixture)

GUILD = "/characters/economy/guild"
SOURCE = "character-service"
ALPHA, BETA, GAMMA = 1, 2, 3
G_NPC, G_DEAD, G_20, BANKER, G_NOWHERE = 60, 61, 62, 63, 64
M_LIVING, M_LEGACY, M_DEAD, M_OTHER = 70, 71, 72, 73
(WOOD, PLANK, SCROLL, RECIPE, LEGEND, QUEST_WOOD, OFF_WOOD, ORE, BREAD, CHEAP, MERCH, BIDW, LEGACYW, DEADW, RESALE,
 OTHERW) = range(600, 616)
PURSE = 100_000
BUDGET = 5_000

ITEMS_DDL = """CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, image VARCHAR(255) NULL, item_type VARCHAR(32) NOT NULL,
    item_rarity VARCHAR(32) NOT NULL DEFAULT 'common', resource_subcategory VARCHAR(32) NULL,
    is_food INTEGER NOT NULL DEFAULT 0, price INTEGER NOT NULL DEFAULT 0)"""
INVENTORY_DDL = """CREATE TABLE IF NOT EXISTS character_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL, item_id INTEGER NOT NULL,
    quantity INTEGER DEFAULT 1, is_identified INTEGER DEFAULT 1, enhancement_points_spent INTEGER DEFAULT 0,
    enhancement_bonuses TEXT NULL, socketed_gems TEXT NULL, current_durability INTEGER NULL)"""
QUEST_DDL = """CREATE TABLE IF NOT EXISTS quest_objectives (id INTEGER PRIMARY KEY, quest_id INTEGER NOT NULL DEFAULT 1,
    objective_type VARCHAR(32) NOT NULL, target_id INTEGER NULL)"""
ATTRIBUTES_DDL = """CREATE TABLE IF NOT EXISTS character_attributes (id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL, passive_experience INTEGER DEFAULT 0, active_experience INTEGER DEFAULT 0)"""
SHOP_DDL = next(d for d in MERCHANT_SQLITE_DDL if d.lstrip().startswith("CREATE TABLE npc_shop_items"))

ITEMS = [  # id, name, type, rarity, subcategory, is_food, price
    (WOOD, "Бревно", "resource", "common", "wood", 0, 10),
    (PLANK, "Щепа", "resource", "common", "wood", 0, 0),
    (SCROLL, "Свиток", "scroll", "common", None, 0, 10),
    (RECIPE, "Рецепт", "recipe", "common", None, 0, 10),
    (LEGEND, "Древо мира", "resource", "legendary", "wood", 0, 10),
    (QUEST_WOOD, "Заветное полено", "resource", "common", "wood", 0, 10),
    (OFF_WOOD, "Реликтовая ветвь", "resource", "common", "wood", 0, 10),
    (ORE, "Руда", "resource", "common", "ore", 0, 10),
    (BREAD, "Хлеб", "consumable", "common", None, 1, 10),
    (CHEAP, "Хворост", "resource", "common", "wood", 0, 10),
    (MERCH, "Брус", "resource", "common", "wood", 0, 10),
    (BIDW, "Дубовый брус", "resource", "common", "wood", 0, 10),
    (LEGACYW, "Кедр", "resource", "common", "wood", 0, 10),
    (DEADW, "Ясень", "resource", "common", "wood", 0, 10),
    (RESALE, "Берёза", "resource", "common", "wood", 0, 10),
    (OTHERW, "Сосна", "resource", "common", "wood", 0, 10),
]
SHOP_ROWS = [  # id, npc, item, buy, sell, stock, active, restock_target, origin
    (1, M_LIVING, CHEAP, 1, 0, 5, 1, 10, "admin"),
    (2, M_LIVING, MERCH, 14, 0, 5, 1, 10, "admin"),
    (3, M_LIVING, BIDW, 14, 0, 5, 1, 10, "admin"),
    (4, M_LEGACY, BIDW, 30, 13, None, 1, 0, "admin"),
    (5, M_LEGACY, LEGACYW, 16, 0, None, 1, 0, "admin"),
    (6, M_DEAD, DEADW, 2, 0, 5, 1, 10, "admin"),
    (7, M_LIVING, RESALE, 14, 0, 0, 1, 0, "player"),
    (8, M_OTHER, OTHERW, 2, 0, 5, 1, 10, "admin"),
]


# --------------------------------------------------------------------------------------------- helpers

def _exec(f, sql, **params):
    db = f()
    try:
        db.execute(text(sql), params)
        db.commit()
    finally:
        db.close()


def _q(f, sql, **params):
    db = f()
    try:
        return db.execute(text(sql), params).scalar()
    finally:
        db.close()


def _rows(f, sql, **params):
    db = f()
    try:
        return [tuple(r) for r in db.execute(text(sql), params).fetchall()]
    finally:
        db.close()


def set_params(f, **values):
    db = f()
    try:
        row = db.get(models.EconSimSettings, 1)
        params = dict(row.params)
        params.update(values)
        row.params = params
        db.commit()
    finally:
        db.close()
    core.invalidate_settings_cache()


def fund(f, ref, amount):
    db = f()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                   legs=[core.Leg(core.AccountRef.emission(), ref, amount)])
        db.commit()
    finally:
        db.close()


def add_order(f, region_id, group, units, *, mult="1", markup="20", status="open"):
    db = f()
    try:
        row = models.EconGuildOrder(
            region_id=region_id, group_code=group, open_key=f"r{region_id}:{group}" if status == "open" else None,
            status=status, close_reason=None if status == "open" else status, units_total=Decimal(str(units)),
            units_left=Decimal(str(units)) if status == "open" else Decimal("0"), units_filled=Decimal("0"),
            price_mult=Decimal(mult), markup_pct=Decimal(markup), pieces=0, paid_total=0, paid_treasury=0,
            hand_ins=0, opened_run_id=1, last_run_id=1, opened_at=guild_crud.now_utc(),
            updated_at=guild_crud.now_utc())
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def set_budget(f, region_id=10, budget=BUDGET, food=0):
    _exec(f, "UPDATE econ_regions SET guild_budget = :b, guild_food_budget = :fb WHERE region_id = :r",
          b=budget, fb=food, r=region_id)


def build_world(f):
    """The world of the module docstring (shared with test_econ_guild_admin_api.py)."""
    for ddl in (ITEMS_DDL, INVENTORY_DDL, QUEST_DDL, ATTRIBUTES_DDL, SHOP_DDL):
        _exec(f, ddl)
    _exec(f, "ALTER TABLE Locations ADD COLUMN marker_type VARCHAR(32) NULL")   # not in the portable hierarchy
    _add_region(f, 10, template="rural", purse=PURSE)
    _add_region(f, 20, template="rural", purse=PURSE)
    _exec(f, "UPDATE econ_region_goods SET stock = norm_stock, price_mult = 1")
    _exec(f, "INSERT INTO Locations (id, name, region_id, marker_type) VALUES (100, 'Площадь', 10, 'safe'), "
             "(150, 'Склеп', 10, 'dungeon'), (200, 'Пристань', 20, 'safe'), (300, 'Пустошь', NULL, 'safe')")
    db = f()
    try:
        for item in ITEMS:
            db.execute(text("INSERT INTO items (id, name, item_type, item_rarity, resource_subcategory, is_food, "
                            "price) VALUES (:i, :n, :t, :r, :s, :fd, :p)"),
                       dict(zip(("i", "n", "t", "r", "s", "fd", "p"), item)))
        db.add(models.EconItemGroup(item_id=OFF_WOOD, group_code=None, off_market=True))
        db.execute(text("INSERT INTO quest_objectives (objective_type, target_id) VALUES ('collect', :i), "
                        "('kill', :w)"), {"i": QUEST_WOOD, "w": WOOD})
        for row in SHOP_ROWS:
            db.execute(text("INSERT INTO npc_shop_items (id, npc_id, item_id, buy_price, sell_price, stock, "
                            "is_active, restock_target, origin) VALUES (:a, :b, :c, :d, :e, :f, :g, :h, :i)"),
                       dict(zip("abcdefghi", row)))
        people = [  # id, name, user, npc, role, status, location
            (ALPHA, "Альфа", 7, False, None, "alive", 100), (BETA, "Бета", 8, False, None, "alive", 200),
            (GAMMA, "Гамма", 9, False, None, "alive", 100),
            (G_NPC, "Гильдмейстер", None, True, "guild", "alive", 100),
            (G_DEAD, "Покойный гильдмейстер", None, True, "guild", "dead", 100),
            (G_20, "Портовый гильдмейстер", None, True, "guild", "alive", 200),
            (BANKER, "Банкир", None, True, "banker", "alive", 100),
            (G_NOWHERE, "Странник", None, True, "guild", "alive", 300),
            (M_LIVING, "Лавочник", None, True, "merchant", "alive", 100),
            (M_LEGACY, "Могильщик", None, True, "merchant", "alive", 150),
            (M_DEAD, "Мёртвый лавочник", None, True, "merchant", "dead", 100),
            (M_OTHER, "Чужой лавочник", None, True, "merchant", "alive", 200),
        ]
        with econ_ledger.allow_direct_balance_write(db):
            for cid, name, user, npc, role, status, loc in people:
                db.add(models.Character(id=cid, name=name, user_id=user, id_subrace=1, id_class=1, id_race=1,
                                        appearance="-", avatar="-", is_npc=npc, npc_role=role, npc_status=status,
                                        current_location_id=loc, level=2, currency_balance=0))
            db.flush()
        db.execute(text("INSERT INTO character_attributes (character_id, passive_experience) VALUES (:c, 0)"),
                   {"c": ALPHA})
        db.add(models.LevelThreshold(level_number=3, required_experience=30))
        db.commit()
    finally:
        db.close()
    fund(f, core.AccountRef.region(10), 10_000)
    add_order(f, 10, "wood", 100)
    add_order(f, 10, "food", 100)
    set_budget(f)


@pytest.fixture
def world(factory, monkeypatch):
    build_world(factory)

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[economy_api.get_db] = override_get_db
    gate = AsyncMock(return_value=True)
    monkeypatch.setattr(locations_client, "check_npc_gate", gate)
    book = AsyncMock(return_value=1.0)
    monkeypatch.setattr(crud, "get_character_xp_multiplier_async", book)
    monkeypatch.setattr(crud, "get_character_xp_multiplier", lambda *_a, **_k: 1.0)
    factory.gate = gate
    factory.book = book
    core.invalidate_settings_cache()
    yield factory
    app.dependency_overrides.pop(economy_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)
    core.invalidate_settings_cache()


def _as_user(user_id=7):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username="tester", role="user", permissions=[])


@pytest.fixture
def client(world):
    _as_user(7)
    return TestClient(app)


def give(f, character_id, item_id, quantity, **extra):
    cols = {"character_id": character_id, "item_id": item_id, "quantity": quantity, **extra}
    _exec(f, f"INSERT INTO character_inventory ({', '.join(cols)}) VALUES ({', '.join(':' + k for k in cols)})",
          **cols)


def _inv(f, item_id=WOOD, character_id=ALPHA):
    return _rows(f, "SELECT id, quantity FROM character_inventory WHERE character_id = :c AND item_id = :i "
                    "ORDER BY id", c=character_id, i=item_id)


def _wallet(f, cid=ALPHA):
    return int(_q(f, "SELECT currency_balance FROM characters WHERE id = :i", i=cid))


def _acc(f, kind, ref):
    return int(_q(f, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind = :k AND ref_id = :r",
                  k=kind, r=ref) or 0)


def _stock(f, group="wood", region_id=10):
    return Decimal(str(_q(f, "SELECT stock FROM econ_region_goods WHERE region_id = :r AND group_code = :g",
                          r=region_id, g=group))).quantize(Decimal("0.001"))


def _order(f, group="wood", region_id=10):
    cols = ("id", "status", "open_key", "close_reason", "units_left", "units_filled", "pieces", "paid_total",
            "paid_treasury", "hand_ins")
    row = _rows(f, f"SELECT {', '.join(cols)} FROM econ_guild_orders WHERE region_id = :r AND group_code = :g "
                   "ORDER BY id DESC", r=region_id, g=group)[0]
    out = dict(zip(cols, row))
    out["units_left"] = Decimal(str(out["units_left"])).quantize(Decimal("0.001"))
    out["units_filled"] = Decimal(str(out["units_filled"])).quantize(Decimal("0.001"))
    return out


def _budget(f, region_id=10):
    return tuple(_rows(f, "SELECT guild_budget, guild_food_budget FROM econ_regions WHERE region_id = :r",
                       r=region_id)[0])


def _ops(f):
    return _rows(f, "SELECT id, idempotency_key, region_id, location_id, actor_user_id, metadata FROM econ_operations "
                    "WHERE op_type = 'guild_order' ORDER BY id")


def _meta(f, op_index=-1):
    raw = _ops(f)[op_index][5]
    return json.loads(raw) if isinstance(raw, str) else raw


def _legs(f, op_id):
    return _rows(f, "SELECT a1.kind, a1.ref_id, a2.kind, a2.ref_id, l.amount, l.leg_type FROM econ_postings l "
                    "JOIN econ_accounts a1 ON a1.id = l.from_account_id "
                    "JOIN econ_accounts a2 ON a2.id = l.to_account_id WHERE l.operation_id = :i ORDER BY l.id",
                 i=op_id)


def _xp(f, cid=ALPHA):
    value = _q(f, "SELECT passive_experience FROM character_attributes WHERE character_id = :c", c=cid)
    return None if value is None else int(value)


def _xp_day(f, cid=ALPHA):
    return int(_q(f, "SELECT COALESCE(SUM(xp), 0) FROM econ_guild_xp_days WHERE character_id = :c", c=cid))


def assert_invariant(f):
    accounts = int(_q(f, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character'"))
    characters = int(_q(f, "SELECT COALESCE(SUM(currency_balance), 0) FROM characters"))
    assert accounts + characters == 0
    assert _q(f, "SELECT COUNT(*) FROM characters WHERE currency_balance < 0") == 0
    assert _q(f, "SELECT COUNT(*) FROM econ_accounts WHERE allow_negative = 0 AND balance < 0") == 0
    # the guild never creates money and never taxes
    assert _q(f, "SELECT COUNT(*) FROM econ_postings l JOIN econ_operations o ON o.id = l.operation_id "
                 "WHERE o.op_type = 'guild_order' AND l.leg_type <> 'main'") == 0
    assert _q(f, "SELECT COUNT(*) FROM econ_postings l JOIN econ_operations o ON o.id = l.operation_id "
                 "JOIN econ_accounts a ON a.id = l.from_account_id WHERE o.op_type = 'guild_order' "
                 "AND a.kind NOT IN ('population_purse', 'region_treasury')") == 0


_REQ = [0]


def post(client, item_id=WOOD, quantity=1, npc=G_NPC, character_id=ALPHA, request_id=None, **extra):
    if request_id is None:
        _REQ[0] += 1
        request_id = f"req-{_REQ[0]:08d}"
    payload = {"character_id": character_id, "item_id": item_id, "quantity": quantity, "request_id": request_id}
    payload.update(extra)
    return client.post(f"{GUILD}/npc/{npc}/hand-in", json=payload)


def view(client, npc=G_NPC, character_id=ALPHA):
    return client.get(f"{GUILD}/npc/{npc}", params={"character_id": character_id})


# --------------------------------------------------------------------------------------------- view

def test_view_lists_orders_offers_and_refusals_without_money_numbers(client, world):
    give(world, ALPHA, WOOD, 3)
    give(world, ALPHA, WOOD, 4)
    give(world, ALPHA, WOOD, 9, enhancement_points_spent=2)          # not a plain stack
    give(world, ALPHA, WOOD, 5, current_durability=10)               # not a plain stack
    for item in (LEGEND, QUEST_WOOD, OFF_WOOD, SCROLL, RECIPE, ORE, MERCH):
        give(world, ALPHA, item, 2)
    resp = view(client)
    assert resp.status_code == 200, resp.text
    v = resp.json()
    assert (v["npc_id"], v["npc_name"], v["region_id"], v["region_name"]) == (G_NPC, "Гильдмейстер", 10, "Регион 10")
    assert v["working"] is True and v["closed_reason"] is None and v["markup_pct"] == 20.0
    assert v["xp"] == {"per_mark": 0.1, "per_mark_merchant_items": 0.05, "daily_cap": 200, "left_today": 200,
                       "multiplier": 1.0}
    assert v["wallet"] == 0
    orders = {o["group_code"]: o for o in v["orders"]}
    assert set(orders) == {"wood", "food"}
    assert (orders["wood"]["units_total"], orders["wood"]["units_left"], orders["wood"]["filled_pct"],
            orders["wood"]["payable"], orders["wood"]["is_food"]) == (100.0, 100.0, 0, True, False)
    assert orders["food"]["is_food"] is True
    offers = {o["item_id"]: o for o in v["offers"]}
    assert sorted(offers) == [WOOD, MERCH]
    assert (offers[WOOD]["have"], offers[WOOD]["unit_price"], offers[WOOD]["units_per_item"],
            offers[WOOD]["max_accept"], offers[WOOD]["capped_by_merchants"], offers[WOOD]["xp_rate"],
            offers[WOOD]["order_id"]) == (7, 12, 2.0, 7, False, 0.1, orders["wood"]["order_id"])
    assert (offers[MERCH]["unit_price"], offers[MERCH]["capped_by_merchants"], offers[MERCH]["xp_rate"]) == \
        (7, True, 0.05)
    refused = {r["item_id"]: r["reason"] for r in v["refused"]}
    assert refused == {LEGEND: guild_crud.MSG_ITEM_NOT_ACCEPTED, QUEST_WOOD: guild_crud.MSG_QUEST_ITEM,
                       OFF_WOOD: guild_crud.MSG_ITEM_NOT_ACCEPTED}
    # scroll / recipe (no group) and ore (no ore order) are not «wanted» at all
    for word in ("budget", "purse", "treasury", "guild_budget"):
        assert word not in resp.text
    world.gate.assert_awaited_once()                    # FEAT-212 3.11: the window is gated too


def test_view_max_accept_follows_volume_and_money(client, world):
    give(world, ALPHA, WOOD, 80)
    set_budget(world, budget=120)
    offer = view(client).json()["offers"][0]
    assert offer["max_accept"] == 10                                  # 120 // 12
    set_budget(world, budget=BUDGET)
    _exec(world, "UPDATE econ_guild_orders SET units_left = 5 WHERE group_code = 'wood'")
    offer = view(client).json()["offers"][0]
    assert offer["max_accept"] == 3                                   # ceil(5 / 2)


def test_view_not_payable_order_is_listed_as_such(client, world):
    set_budget(world, budget=0, food=0)
    orders = {o["group_code"]: o["payable"] for o in view(client).json()["orders"]}
    assert orders == {"wood": False, "food": False}
    set_budget(world, budget=0, food=50)
    orders = {o["group_code"]: o["payable"] for o in view(client).json()["orders"]}
    assert orders == {"wood": False, "food": True}


def test_view_of_a_closed_guild_answers_the_reason(client, world):
    _exec(world, "UPDATE characters SET current_location_id = 300 WHERE id = :i", i=ALPHA)
    give(world, ALPHA, WOOD, 3)
    v = view(client, npc=G_NOWHERE).json()
    assert (v["working"], v["region_id"], v["closed_reason"]) == (False, None, guild_crud.REASON_NOT_PARTICIPATING)
    assert v["orders"] == v["offers"] == v["refused"] == []
    _exec(world, "UPDATE characters SET current_location_id = 100 WHERE id = :i", i=ALPHA)
    set_params(world, guild_enabled=0)
    v = view(client).json()
    assert (v["working"], v["closed_reason"], v["orders"]) == (False, guild_crud.REASON_DISABLED, [])


def test_view_xp_block_uses_the_book_and_the_day_counter(client, world, monkeypatch):
    monkeypatch.setattr(crud, "get_character_xp_multiplier", lambda *_a, **_k: 1.5)
    _exec(world, "INSERT INTO econ_guild_xp_days (character_id, day, xp) VALUES (:c, :d, 60)",
          c=ALPHA, d=guild_crud.today_utc())
    xp = view(client).json()["xp"]
    assert (xp["left_today"], xp["multiplier"]) == (140, 1.5)


# --------------------------------------------------------------------------------------------- hand-in: success

def test_hand_in_success_multi_stack(client, world):
    give(world, ALPHA, WOOD, 3)
    give(world, ALPHA, WOOD, 4)
    give(world, ALPHA, WOOD, 9, enhancement_points_spent=2)
    purse = _acc(world, "population_purse", 10)
    stock = _stock(world)
    resp = post(client, quantity=5, request_id="req-success1")
    assert resp.status_code == 200, resp.text
    r = resp.json()
    assert (r["quantity"], r["requested"], r["partial"], r["unit_price"], r["total"], r["xp"], r["xp_capped"]) == \
        (5, 5, False, 12, 60, 6, False)
    assert r["wallet"] == 60 == _wallet(world) and r["view"]["wallet"] == 60
    assert r["message"] == "Гильдия приняла Бревно × 5 — получено 60 марок и 6 опыта"
    inv = _inv(world)
    assert [q for _i, q in inv] == [2, 9]                             # first stack gone, the enhanced one untouched
    assert _stock(world) == stock + Decimal("10")
    o = _order(world)
    assert (o["status"], o["units_left"], o["units_filled"], o["pieces"], o["paid_total"], o["paid_treasury"],
            o["hand_ins"]) == ("open", Decimal("90.000"), Decimal("10.000"), 5, 60, 0, 1)
    assert _budget(world) == (BUDGET - 60, 0)
    assert _acc(world, "population_purse", 10) == purse - 60
    [(op_id, key, region, location, actor, _m)] = _ops(world)
    assert (key, region, location, actor) == ("guild:1:req-success1", 10, 100, 7)
    assert [leg for leg in _legs(world, op_id) if leg[4] > 0] == [
        ("population_purse", 10, "character", ALPHA, 60, "main")]
    meta = _meta(world)
    assert (meta["order_id"], meta["npc_id"], meta["item_id"], meta["group"], meta["quantity"], meta["requested"],
            meta["unit_price"], meta["paid_purse"], meta["paid_treasury"]) == \
        (o["id"], G_NPC, WOOD, "wood", 5, 5, 12, 60, 0)
    assert (meta["xp_base"], meta["xp"], meta["xp_rate"], meta["xp_multiplier"]) == (6, 6, 0.1, 1.0)
    assert meta["cheapest_ask"] is None and meta["best_bid"] == 5          # the living merchant buys wood
    assert _xp(world) == 6 and _xp_day(world) == 6
    assert r["view"]["xp"]["left_today"] == 194
    assert_invariant(world)


def test_food_hand_in_uses_the_treasury_top_up(client, world):
    give(world, ALPHA, BREAD, 5)                                      # 5 units each, 12 marks
    set_budget(world, budget=10, food=1000)
    treasury = _acc(world, "region_treasury", 10)
    resp = post(client, item_id=BREAD, quantity=5)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 60
    assert _budget(world) == (0, 950)
    assert _acc(world, "region_treasury", 10) == treasury - 50
    o = _order(world, "food")
    assert (o["paid_total"], o["paid_treasury"], o["units_left"]) == (60, 50, Decimal("75.000"))
    op_id = _ops(world)[0][0]
    assert sorted(leg for leg in _legs(world, op_id) if leg[4] > 0) == [
        ("population_purse", 10, "character", ALPHA, 10, "main"),
        ("region_treasury", 10, "character", ALPHA, 50, "main")]
    assert_invariant(world)


def test_non_food_never_touches_the_treasury(client, world):
    give(world, ALPHA, WOOD, 5)
    set_budget(world, budget=24, food=1000)
    resp = post(client, quantity=5)
    assert resp.status_code == 200 and resp.json()["quantity"] == 2   # 24 // 12, the food budget is not for wood
    assert _budget(world) == (0, 1000)


def test_price_zero_item_valued_at_group_base(client, world):
    give(world, ALPHA, PLANK, 4)
    resp = post(client, item_id=PLANK, quantity=4)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["unit_price"], resp.json()["total"]) == (6, 24)
    assert _order(world)["units_left"] == Decimal("96.000")           # 1 unit per piece


def test_snapshot_mult_and_markup_of_the_order_are_used(client, world):
    _exec(world, "UPDATE econ_guild_orders SET price_mult = 1.5, markup_pct = 50 WHERE group_code = 'wood'")
    set_params(world, guild_markup_pct=0.0)                           # takes effect only on the next recount
    give(world, ALPHA, WOOD, 1)
    assert post(client).json()["unit_price"] == 22                    # floor(10 x 1.5 x 1.5)


# --------------------------------------------------------------------------------------------- partial / filled

def test_partial_by_volume_overshoots_then_the_order_is_filled(client, world):
    _exec(world, "UPDATE econ_guild_orders SET units_left = 5 WHERE group_code = 'wood'")
    give(world, ALPHA, WOOD, 10)
    stock = _stock(world)
    resp = post(client, quantity=5)
    assert resp.status_code == 200, resp.text
    r = resp.json()
    assert (r["quantity"], r["requested"], r["partial"], r["total"]) == (3, 5, True, 36)
    assert r["message"].startswith("Принято 3 из 5 шт. — заказ почти закрыт, остальное осталось у вас. "
                                   "Получено 36 марок")
    assert _stock(world) == stock + Decimal("6")                      # the last piece overshoots the order
    o = _order(world)
    assert (o["status"], o["open_key"], o["close_reason"], o["units_left"], o["pieces"]) == \
        ("filled", None, "filled", Decimal("0.000"), 3)
    assert _inv(world)[0][1] == 7
    again = post(client, quantity=1)
    assert again.status_code == 409 and again.json()["detail"] == guild_crud.MSG_NO_ORDER
    assert _inv(world)[0][1] == 7
    assert_invariant(world)


def test_partial_by_money(client, world):
    set_budget(world, budget=30)
    give(world, ALPHA, WOOD, 5)
    resp = post(client, quantity=5)
    r = resp.json()
    assert (r["quantity"], r["partial"], r["total"]) == (2, True, 24)
    assert guild_crud.WHY_MONEY in r["message"]
    assert _budget(world) == (6, 0) and _inv(world)[0][1] == 3


def test_budget_is_bounded_by_the_live_purse(client, world):
    _exec(world, "UPDATE econ_accounts SET balance = 20 WHERE kind = 'population_purse' AND ref_id = 10")
    give(world, ALPHA, WOOD, 5)
    r = post(client, quantity=5).json()
    assert r["quantity"] == 1 and r["total"] == 12                    # min(5000, 20) // 12
    assert _acc(world, "population_purse", 10) == 8


def test_no_money_is_409_and_takes_nothing(client, world):
    set_budget(world, budget=11)
    give(world, ALPHA, WOOD, 5)
    resp = post(client, quantity=1)
    assert resp.status_code == 409 and resp.json()["detail"] == guild_crud.MSG_NO_MONEY
    assert _inv(world)[0][1] == 5 and _ops(world) == [] and _wallet(world) == 0


def test_budget_is_never_exceeded_over_many_hand_ins(client, world):
    set_budget(world, budget=100)
    give(world, ALPHA, WOOD, 50)
    paid = 0
    for _ in range(12):
        resp = post(client, quantity=3)
        if resp.status_code != 200:
            assert resp.status_code == 409 and resp.json()["detail"] == guild_crud.MSG_NO_MONEY
            break
        paid += resp.json()["total"]
    assert paid <= 100 and paid == 96 and _budget(world) == (4, 0)
    assert_invariant(world)


# --------------------------------------------------------------------------------------------- refusals

@pytest.mark.parametrize("item_id, status, detail", [
    (SCROLL, 400, guild_crud.MSG_ITEM_NOT_ACCEPTED),
    (RECIPE, 400, guild_crud.MSG_ITEM_NOT_ACCEPTED),
    (LEGEND, 400, guild_crud.MSG_ITEM_NOT_ACCEPTED),
    (OFF_WOOD, 400, guild_crud.MSG_ITEM_NOT_ACCEPTED),
    (QUEST_WOOD, 400, guild_crud.MSG_QUEST_ITEM),
    (ORE, 409, guild_crud.MSG_NO_ORDER),
    (CHEAP, 400, guild_crud.MSG_NOT_WORTH),
    (9999, 400, guild_crud.MSG_ITEM_NOT_ACCEPTED),
])
def test_refused_items_take_nothing(client, world, item_id, status, detail):
    if item_id != 9999:
        give(world, ALPHA, item_id, 3)
    resp = post(client, item_id=item_id, quantity=1)
    assert resp.status_code == status and resp.json()["detail"] == detail
    if item_id != 9999:
        assert _inv(world, item_id)[0][1] == 3
    assert _ops(world) == [] and _wallet(world) == 0 and _xp(world) == 0


def test_cheap_item_is_refused_in_the_view_too(client, world):
    give(world, ALPHA, CHEAP, 2)
    v = view(client).json()
    assert v["offers"] == [] and v["refused"][0]["reason"] == guild_crud.MSG_NOT_WORTH


def test_only_non_plain_stacks_is_not_enough(client, world):
    give(world, ALPHA, WOOD, 9, enhancement_points_spent=2)
    give(world, ALPHA, WOOD, 4, socketed_gems="[1]")
    resp = post(client, quantity=1)
    assert resp.status_code == 400
    assert resp.json()["detail"] == guild_crud.MSG_NOT_ENOUGH.format(name="Бревно", need=1, have=0)
    assert [q for _i, q in _inv(world)] == [9, 4]


def test_not_enough_takes_nothing_even_when_the_order_would_cap_it(client, world):
    _exec(world, "UPDATE econ_guild_orders SET units_left = 2 WHERE group_code = 'wood'")
    give(world, ALPHA, WOOD, 3)
    resp = post(client, quantity=5)                                   # the order would take 1, the bag has 3 < 5
    assert resp.status_code == 400 and "нужно 5, есть 3" in resp.json()["detail"]
    assert _inv(world)[0][1] == 3 and _ops(world) == [] and _order(world)["units_left"] == Decimal("2.000")


# --------------------------------------------------------------------------------------------- merchant price cap / floor

@pytest.mark.parametrize("item_id, price, rate, ask, bid", [
    (MERCH, 7, 0.05, 14, 0),          # living merchant sells: floor(14 x 0.5)
    (BIDW, 13, 0.05, 14, 13),         # capped to 7, but the legacy merchant pays 13 -> never less than a merchant
    (LEGACYW, 8, 0.05, 16, 5),        # legacy-in-region merchant sells: floor(16 x 0.5); the living one bids 5
    (DEADW, 12, 0.1, None, 5),        # only a dead merchant sells it: ignored (the living one buys wood -> bid 5)
    (RESALE, 12, 0.1, None, 0),       # player-resale row with stock 0 does not cap (its own row bids 0)
    (OTHERW, 12, 0.1, None, 5),       # a merchant of another region does not count
])
def test_merchant_cap_and_bid_floor_through_the_loader(client, world, item_id, price, rate, ask, bid):
    give(world, ALPHA, item_id, 10)
    resp = post(client, item_id=item_id, quantity=10)
    assert resp.status_code == 200, resp.text
    assert resp.json()["unit_price"] == price
    meta = _meta(world)
    assert (meta["unit_price"], meta["xp_rate"], meta["cheapest_ask"], meta["best_bid"]) == (price, rate, ask, bid)
    assert resp.json()["xp"] == int(Decimal(price * 10) * Decimal(str(rate)))
    assert price >= bid


def test_player_resale_row_counts_while_in_stock(client, world):
    _exec(world, "UPDATE npc_shop_items SET stock = 3 WHERE id = 7")
    give(world, ALPHA, RESALE, 2)
    assert post(client, item_id=RESALE, quantity=1).json()["unit_price"] == 7
    assert _meta(world)["xp_rate"] == 0.05


def test_inactive_merchant_row_does_not_cap(client, world):
    _exec(world, "UPDATE npc_shop_items SET is_active = 0 WHERE id = 2")
    give(world, ALPHA, MERCH, 1)
    assert post(client, item_id=MERCH).json()["unit_price"] == 12


def test_guild_never_pays_less_than_the_best_bid_even_above_the_offer(client, world):
    _exec(world, "UPDATE npc_shop_items SET sell_price = 15, buy_price = 40 WHERE id = 4")   # legacy bids 15 > 12
    give(world, ALPHA, BIDW, 1)
    assert post(client, item_id=BIDW).json()["unit_price"] == 15


# --------------------------------------------------------------------------------------------- atomicity / idempotency

def test_same_request_id_twice_is_one_operation_and_xp_once(client, world):
    give(world, ALPHA, WOOD, 10)
    first = post(client, quantity=5, request_id="req-twice001")
    assert first.status_code == 200
    again = post(client, quantity=5, request_id="req-twice001")
    assert again.status_code == 409 and again.json()["detail"] == guild_crud.MSG_DUPLICATE
    assert len(_ops(world)) == 1 and _inv(world)[0][1] == 5 and _wallet(world) == 60
    assert _xp(world) == 6 and _xp_day(world) == 6 and _order(world)["hand_ins"] == 1
    # another character with the same request_id is a different key
    give(world, GAMMA, WOOD, 1)
    _as_user(9)
    assert post(client, character_id=GAMMA, request_id="req-twice001").status_code == 200
    assert [k for _i, k, *_r in _ops(world)] == ["guild:1:req-twice001", "guild:3:req-twice001"]


@pytest.mark.parametrize("exc, status, detail", [
    (core.InsufficientFunds(core.AccountRef.purse(10), 60), 409, guild_crud.MSG_RETRY_MONEY),
    (core.DuplicateOperation(1), 409, guild_crud.MSG_DUPLICATE),
    (core.EconomyError("rejected"), 400, "Операция отклонена"),
])
def test_posting_failure_rolls_back_items_order_budget_and_xp(client, world, monkeypatch, exc, status, detail):
    give(world, ALPHA, WOOD, 5)
    stock, order, budget = _stock(world), _order(world), _budget(world)

    def failing(*_a, **_k):
        raise exc

    monkeypatch.setattr(econ_ledger, "post_operation", failing)
    resp = post(client, quantity=5)
    assert resp.status_code == status and resp.json()["detail"] == detail
    assert _inv(world)[0][1] == 5 and _stock(world) == stock and _order(world) == order
    assert _budget(world) == budget and _wallet(world) == 0
    assert _xp(world) == 0 and _xp_day(world) == 0


def test_db_error_hides_internals(client, world, monkeypatch):
    from sqlalchemy.exc import OperationalError
    give(world, ALPHA, WOOD, 5)

    def broken(*_a, **_k):
        raise OperationalError("INSERT secret", {}, Exception("db down"))

    monkeypatch.setattr(econ_ledger, "post_operation", broken)
    resp = post(client, quantity=1)
    assert resp.status_code == 500 and "secret" not in resp.text and "INSERT" not in resp.text
    assert _inv(world)[0][1] == 5 and _xp_day(world) == 0


# --------------------------------------------------------------------------------------------- XP (3.6a)

def test_xp_daily_cap_across_hand_ins_and_both_rates(client, world):
    set_params(world, guild_xp_daily_cap=10)
    for item in (WOOD, DEADW, MERCH):
        give(world, ALPHA, item, 20)
    r1 = post(client, item_id=WOOD, quantity=5).json()                # 60 x 10 % = 6
    assert (r1["xp"], r1["xp_capped"]) == (6, False)
    r2 = post(client, item_id=DEADW, quantity=5).json()               # 6 more, only 4 left
    assert (r2["xp"], r2["xp_capped"]) == (4, True)
    assert r2["message"].endswith(" и 4 опыта")
    r3 = post(client, item_id=MERCH, quantity=10).json()              # 70 x 5 % = 3, nothing left
    assert (r3["xp"], r3["xp_capped"]) == (0, True)
    assert r3["message"].endswith(guild_crud.MSG_XP_CAPPED)
    assert _xp(world) == 10 and _xp_day(world) == 10
    assert r3["view"]["xp"]["left_today"] == 0
    assert _meta(world)["xp_base"] == 0 and _meta(world)["xp_rate"] == 0.05


def test_next_utc_day_resets_the_cap(client, world, monkeypatch):
    set_params(world, guild_xp_daily_cap=6)
    give(world, ALPHA, WOOD, 20)
    day1 = datetime(2026, 11, 1, 23, 50)
    monkeypatch.setattr(guild_crud, "now_utc", lambda: day1)
    assert post(client, quantity=5).json()["xp"] == 6
    assert post(client, quantity=5).json()["xp"] == 0
    monkeypatch.setattr(guild_crud, "now_utc", lambda: day1 + timedelta(minutes=20))
    assert post(client, quantity=5).json()["xp"] == 6
    assert _rows(world, "SELECT day, xp FROM econ_guild_xp_days ORDER BY day") == [("2026-11-01", 6),
                                                                                    ("2026-11-02", 6)]
    assert _xp(world) == 12


def test_cap_zero_turns_guild_xp_off(client, world):
    set_params(world, guild_xp_daily_cap=0)
    give(world, ALPHA, WOOD, 5)
    r = post(client, quantity=5).json()
    assert (r["xp"], r["xp_capped"]) == (0, False)
    assert r["message"] == "Гильдия приняла Бревно × 5 — получено 60 марок"
    assert _xp(world) == 0


def test_rates_are_params(client, world):
    set_params(world, guild_xp_per_mark=0.5, guild_xp_per_mark_merchant_items=0.0)
    give(world, ALPHA, WOOD, 5)
    give(world, ALPHA, MERCH, 5)
    assert post(client, quantity=5).json()["xp"] == 30
    assert post(client, item_id=MERCH, quantity=5).json()["xp"] == 0


def test_quest_book_multiplies_after_the_cap(client, world):
    world.book.return_value = 1.5
    set_params(world, guild_xp_daily_cap=4)
    give(world, ALPHA, WOOD, 5)
    r = post(client, quantity=5).json()                               # base min(6, 4) = 4 -> int(4 x 1.5) = 6
    assert (r["xp"], r["xp_capped"]) == (6, True)
    assert _xp(world) == 6 and _xp_day(world) == 4                    # the cap counts base XP
    meta = _meta(world)
    assert (meta["xp_base"], meta["xp"], meta["xp_multiplier"]) == (4, 6, 1.5)
    world.book.assert_awaited_with(ALPHA, crud.XP_SOURCE_QUEST)


def test_no_attributes_row_hand_in_succeeds_with_zero_xp(client, world):
    _as_user(9)
    give(world, GAMMA, WOOD, 5)
    resp = post(client, character_id=GAMMA, quantity=5)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["xp"], resp.json()["total"]) == (0, 60)
    assert _wallet(world, GAMMA) == 60 and _xp_day(world, GAMMA) == 0
    assert _meta(world)["xp"] == 0


def test_level_up_after_crossing_a_threshold(client, world):
    _exec(world, "UPDATE character_attributes SET passive_experience = 25 WHERE character_id = :c", c=ALPHA)
    give(world, ALPHA, WOOD, 5)
    assert post(client, quantity=5).json()["xp"] == 6
    assert _xp(world) == 31
    assert _rows(world, "SELECT level, stat_points FROM characters WHERE id = :i", i=ALPHA) == [(3, 10)]


# --------------------------------------------------------------------------------------------- gate order / security

def test_unauthenticated_is_401(world):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    anon = TestClient(app)
    assert view(anon).status_code == 401
    assert post(anon).status_code == 401
    world.gate.assert_not_called()


def test_other_users_character_is_403(client, world):
    _as_user(8)
    give(world, ALPHA, WOOD, 5)
    for resp in (view(client), post(client)):
        assert resp.status_code == 403 and resp.json()["detail"] == guild_crud.MSG_NOT_OWNER
    assert _inv(world)[0][1] == 5
    world.gate.assert_not_called()


def test_npc_as_the_character_is_refused(client, world):
    _exec(world, "UPDATE characters SET user_id = 7 WHERE id = :i", i=M_LIVING)
    resp = post(client, character_id=M_LIVING)
    assert resp.status_code == 403 and resp.json()["detail"] == guild_crud.MSG_NOT_PLAYER


def test_unknown_character_is_404(client, world):
    assert post(client, character_id=9999).status_code == 404


@pytest.mark.parametrize("npc", [BANKER, M_LIVING, ALPHA, 9999])
def test_not_a_guild_is_404(client, world, npc):
    for resp in (view(client, npc=npc), post(client, npc=npc)):
        assert resp.status_code == 404 and resp.json()["detail"] == guild_crud.MSG_GUILD_NOT_FOUND


def test_dead_guild_is_409_before_the_location(client, world):
    _exec(world, "UPDATE characters SET current_location_id = 200 WHERE id = :i", i=G_DEAD)
    for resp in (view(client, npc=G_DEAD), post(client, npc=G_DEAD)):
        assert resp.status_code == 409 and resp.json()["detail"] == guild_crud.MSG_GUILD_DEAD


def test_activity_lock_is_409_for_the_hand_in_only(client, world):
    _exec(world, "UPDATE characters SET dungeon_session_id = 5 WHERE id = :i", i=ALPHA)
    give(world, ALPHA, WOOD, 1)
    resp = post(client)
    assert resp.status_code == 409 and "подземелье" in resp.json()["detail"]
    assert view(client).status_code == 200
    world.gate.assert_awaited_once()                    # only the view asked (FEAT-212 3.11); the hand-in stopped first
    assert _inv(world)[0][1] == 1


def test_wrong_location_is_400_and_never_asks_the_gate(client, world):
    for resp in (view(client, npc=G_20), post(client, npc=G_20)):
        assert resp.status_code == 400 and resp.json()["detail"] == guild_crud.MSG_WRONG_LOCATION
    world.gate.assert_not_called()


def test_gate_closed_403_and_unavailable_503(client, world):
    give(world, ALPHA, WOOD, 1)
    world.gate.return_value = False
    resp = post(client)
    assert resp.status_code == 403 and resp.json()["detail"] == guild_crud.MSG_GATE_CLOSED
    world.gate.return_value = True
    world.gate.side_effect = locations_client.GateUnavailable()
    resp = post(client)
    assert resp.status_code == 503 and resp.json()["detail"] == guild_crud.MSG_GATE_UNAVAILABLE
    assert _inv(world)[0][1] == 1 and _ops(world) == []
    world.gate.assert_awaited_with(ALPHA, 100, G_NPC)


def test_view_needs_the_dialogue_gate_too(client, world):
    """FEAT-212 3.11: the guild window itself is behind the npc_dialogue gate (fail-closed)."""
    world.gate.return_value = False
    resp = view(client)
    assert resp.status_code == 403 and resp.json()["detail"] == guild_crud.MSG_GATE_CLOSED
    world.gate.return_value = True
    world.gate.side_effect = locations_client.GateUnavailable()
    resp = view(client)
    assert resp.status_code == 503 and resp.json()["detail"] == guild_crud.MSG_GATE_UNAVAILABLE
    world.gate.side_effect = None
    assert view(client).status_code == 200


def test_region_not_participating_or_disabled_is_409(client, world):
    give(world, ALPHA, WOOD, 1)
    _exec(world, "UPDATE characters SET current_location_id = 300 WHERE id = :i", i=ALPHA)
    resp = post(client, npc=G_NOWHERE)
    assert resp.status_code == 409
    assert resp.json()["detail"] == guild_crud.MSG_GUILD_CLOSED.format(reason=guild_crud.REASON_NOT_PARTICIPATING)
    _exec(world, "UPDATE characters SET current_location_id = 100 WHERE id = :i", i=ALPHA)
    set_params(world, guild_enabled=0)
    resp = post(client)
    assert resp.status_code == 409
    assert resp.json()["detail"] == guild_crud.MSG_GUILD_CLOSED.format(reason=guild_crud.REASON_DISABLED)
    set_params(world, guild_enabled=1)
    _exec(world, "UPDATE econ_regions SET population = 0 WHERE region_id = 10")
    resp = post(client)
    assert resp.status_code == 409 and guild_crud.REASON_NOT_PARTICIPATING in resp.json()["detail"]
    assert _inv(world)[0][1] == 1 and _ops(world) == []


@pytest.mark.parametrize("request_id", [
    "'; DROP TABLE econ_operations; --", "req\" OR 1=1 --", "<script>alert(1)</script>", "short", "x" * 65,
    "req_with_underscore", "",
])
def test_injection_like_request_id_is_422(client, world, request_id):
    give(world, ALPHA, WOOD, 1)
    assert post(client, request_id=request_id).status_code == 422
    assert _inv(world)[0][1] == 1 and _ops(world) == []


@pytest.mark.parametrize("field, value", [
    ("quantity", 0), ("quantity", 10_001), ("quantity", "5"), ("quantity", 1.5), ("quantity", True),
    ("item_id", 0), ("item_id", "600"), ("character_id", 0), ("character_id", "1 OR 1=1"),
])
def test_body_validation_is_422(client, world, field, value):
    give(world, ALPHA, WOOD, 1)
    assert post(client, **{field: value}).status_code == 422
    assert _ops(world) == []


def test_missing_request_id_is_422(client, world):
    resp = client.post(f"{GUILD}/npc/{G_NPC}/hand-in", json={"character_id": ALPHA, "item_id": WOOD, "quantity": 1})
    assert resp.status_code == 422


def test_view_query_validation(client, world):
    assert client.get(f"{GUILD}/npc/{G_NPC}").status_code == 422
    assert client.get(f"{GUILD}/npc/{G_NPC}", params={"character_id": "1; DROP TABLE items"}).status_code == 422
    assert client.get(f"{GUILD}/npc/{G_NPC}", params={"character_id": 0}).status_code == 422


def test_xss_like_item_name_is_plain_json_data(client, world):
    _exec(world, "UPDATE items SET name = :n WHERE id = :i", n="<img src=x onerror=alert(1)>", i=WOOD)
    give(world, ALPHA, WOOD, 1)
    resp = post(client)
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("application/json")
    assert resp.json()["message"].startswith("Гильдия приняла <img src=x onerror=alert(1)> × 1")
    assert _meta(world)["item_name"] == "<img src=x onerror=alert(1)>"

"""FEAT-191 QA (#10): player mint API at a «Монетчик» (contract 3.8 / 3.10) on SQLite.

The FEAT-145 gate is mocked (``locations_client.check_npc_gate``). Shared tables of other services are created with
their real columns: ``items`` (inventory-service), ``character_inventory`` (inventory-service, incl.
``enhancement_points_spent`` / ``socketed_gems`` / ``current_durability``), ``game_time_config`` (locations-service).

World (seed of ``test_econ_tick.factory``: goods groups, templates, countries 1 «Мидденгерд», 2 «Пустошь»):
    country 1: region 10 «Регион 10» capital (the mint), 20 port; country 2: region 30 agrarian (no capital)
    locations 100 @10, 200 @20, 300 (no region), 400 @30
    players: 1 «Альфа» (user 7) @100 wallet 1000, 2 «Бета» (user 8) @200, 3 «Гамма» (user 9) @400
    NPCs: 60 minter @100, 61 dead minter @100, 62 minter @200 (not the capital), 63 banker @100,
          64 minter @400 (country without a capital), 65 minter @300 (no region)
    items: 500 iron ore (ore, price 10), 501 ingot (price 30), 502 bread (food), 503 ore overridden to tools,
           504 ore (disabled in the mint list)
    mint list: 500 -> 12 marks, 501 -> 40, 503 -> 5 (invalid group), 504 -> 7 (disabled)
    params: mint_season_limit = 10 000; calendar epoch = now - 10 days (period 0)
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import econ_core as core
import econ_ledger
import econ_mint
import economy_api
import economy_mint_crud as mint_crud
import locations_client
import models
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.test_econ_tick import _add_region, factory  # noqa: F401  (factory is a fixture)

MINT = "/characters/economy/mint"
SOURCE = "character-service"
ALPHA, BETA, GAMMA = 1, 2, 3
MINTER, MINTER_DEAD, MINTER_PORT, BANKER, MINTER_NO_CAPITAL, MINTER_NOWHERE = 60, 61, 62, 63, 64, 65
ORE, INGOT, BREAD, ORE_TOOLS, ORE_OFF = 500, 501, 502, 503, 504
LIMIT = 10_000
WALLET = 1000

ITEMS_DDL = """CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, image VARCHAR(255) NULL, item_type VARCHAR(32) NOT NULL,
    item_rarity VARCHAR(32) NOT NULL DEFAULT 'common', resource_subcategory VARCHAR(32) NULL,
    is_food INTEGER NOT NULL DEFAULT 0, price INTEGER NOT NULL DEFAULT 0)"""
INVENTORY_DDL = """CREATE TABLE IF NOT EXISTS character_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL, item_id INTEGER NOT NULL,
    quantity INTEGER DEFAULT 1, is_identified INTEGER DEFAULT 1, enhancement_points_spent INTEGER DEFAULT 0,
    enhancement_bonuses TEXT NULL, socketed_gems TEXT NULL, current_durability INTEGER NULL)"""
GAME_TIME_DDL = """CREATE TABLE IF NOT EXISTS game_time_config (
    id INTEGER PRIMARY KEY, epoch DATETIME NOT NULL, offset_days INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME NULL)"""


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


def build_world(f):
    """The world of the module docstring (shared with test_econ_mint_admin_api.py)."""
    for ddl in (ITEMS_DDL, INVENTORY_DDL, GAME_TIME_DDL):
        _exec(f, ddl)
    epoch = mint_crud.now_utc() - timedelta(days=10)
    _exec(f, "INSERT INTO game_time_config (id, epoch, offset_days) VALUES (1, :e, 0)", e=epoch)
    _add_region(f, 10, template="capital", purse=0)
    _add_region(f, 20, template="port", purse=0)
    _add_region(f, 30, template="agrarian", country_id=2, purse=0)
    _exec(f, "UPDATE econ_region_goods SET stock = 100, norm_stock = 200 WHERE group_code = 'ore_metal'")
    _exec(f, "INSERT INTO Locations (id, name, region_id) VALUES (100, 'Площадь', 10), (200, 'Пристань', 20), "
             "(300, 'Пустошь', NULL), (400, 'Нива', 30)")
    _exec(f, "INSERT INTO items (id, name, item_type, resource_subcategory, is_food, price) VALUES "
             "(500, 'Железная руда', 'resource', 'ore', 0, 10), (501, 'Слиток', 'resource', 'ingot', 0, 30), "
             "(502, 'Хлеб', 'consumable', NULL, 1, 5), (503, 'Странная руда', 'resource', 'ore', 0, 10), "
             "(504, 'Медная руда', 'resource', 'ore', 0, 10)")
    db = f()
    try:
        db.add(models.EconItemGroup(item_id=ORE_TOOLS, group_code="tools"))
        for item_id, rate, enabled in ((ORE, 12, True), (INGOT, 40, True), (ORE_TOOLS, 5, True),
                                       (ORE_OFF, 7, False)):
            db.add(models.EconMintItem(item_id=item_id, marks_per_item=rate, is_enabled=enabled))
        people = [  # id, name, user, npc, role, status, location
            (ALPHA, "Альфа", 7, False, None, "alive", 100), (BETA, "Бета", 8, False, None, "alive", 200),
            (GAMMA, "Гамма", 9, False, None, "alive", 400),
            (MINTER, "Монетчик", None, True, "minter", "alive", 100),
            (MINTER_DEAD, "Мёртвый монетчик", None, True, "minter", "dead", 100),
            (MINTER_PORT, "Портовый монетчик", None, True, "minter", "alive", 200),
            (BANKER, "Банкир", None, True, "banker", "alive", 100),
            (MINTER_NO_CAPITAL, "Сельский монетчик", None, True, "minter", "alive", 400),
            (MINTER_NOWHERE, "Странник", None, True, "minter", "alive", 300),
        ]
        with econ_ledger.allow_direct_balance_write(db):
            for cid, name, user, npc, role, status, loc in people:
                db.add(models.Character(id=cid, name=name, user_id=user, id_subrace=1, id_class=1, id_race=1,
                                        appearance="-", avatar="-", is_npc=npc, npc_role=role, npc_status=status,
                                        current_location_id=loc, level=2, currency_balance=0))
            db.flush()
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                   legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.character(ALPHA),
                                                  WALLET)])
        db.commit()
    finally:
        db.close()
    set_params(f, mint_season_limit=LIMIT)
    return epoch


@pytest.fixture
def world(factory, monkeypatch):
    epoch = build_world(factory)

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[economy_api.get_db] = override_get_db
    gate = AsyncMock(return_value=True)
    monkeypatch.setattr(locations_client, "check_npc_gate", gate)
    factory.gate = gate
    factory.epoch = epoch
    yield factory
    app.dependency_overrides.pop(economy_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _as_user(user_id=7):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username="tester", role="user", permissions=[])


@pytest.fixture
def client(world):
    _as_user(7)
    return TestClient(app)


def _give(f, character_id, item_id, quantity, **extra):
    cols = {"character_id": character_id, "item_id": item_id, "quantity": quantity, **extra}
    names = ", ".join(cols)
    _exec(f, f"INSERT INTO character_inventory ({names}) VALUES ({', '.join(':' + k for k in cols)})", **cols)


def _inv(f, character_id=ALPHA, item_id=ORE):
    return _rows(f, "SELECT id, quantity FROM character_inventory WHERE character_id = :c AND item_id = :i "
                    "ORDER BY id", c=character_id, i=item_id)


def _wallet(f, cid=ALPHA):
    return int(_q(f, "SELECT currency_balance FROM characters WHERE id = :i", i=cid))


def _ore_stock(f, region_id=10):
    return Decimal(str(_q(f, "SELECT stock FROM econ_region_goods WHERE region_id = :r AND group_code = 'ore_metal'",
                          r=region_id))).quantize(Decimal("0.001"))


def _season(f, country_id=1):
    rows = _rows(f, "SELECT minted_court, minted_players, ore_units_players FROM econ_mint_seasons "
                    "WHERE country_id = :c AND period_index = 0", c=country_id)
    return rows[0] if rows else None


def _mint_ops(f):
    return _rows(f, "SELECT id, idempotency_key, region_id, location_id, actor_user_id FROM econ_operations "
                    "WHERE op_type = 'mint_player' ORDER BY id")


def _assert_invariant(f):
    accounts = int(_q(f, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character'"))
    characters = int(_q(f, "SELECT COALESCE(SUM(currency_balance), 0) FROM characters"))
    assert accounts + characters == 0


def _period(f):
    return econ_mint.period_of(f.epoch, 0, mint_crud.now_utc())


def _post(client, body=None, npc=MINTER, **kw):
    payload = {"character_id": ALPHA, "item_id": ORE, "quantity": 1, "request_id": "req-00000001"}
    payload.update(body or {})
    payload.update(kw)
    return client.post(f"{MINT}/npc/{npc}/mint", json=payload)


def _view(client, npc=MINTER, character_id=ALPHA):
    return client.get(f"{MINT}/npc/{npc}", params={"character_id": character_id})


def _set_season(f, minted_court=0, minted_players=0, country_id=1):
    _exec(f, "INSERT INTO econ_mint_seasons (country_id, period_index, minted_court, minted_players, "
             "ore_units_court, ore_units_players, created_at) VALUES (:c, 0, :mc, :mp, 0, 0, :t)",
          c=country_id, mc=minted_court, mp=minted_players, t=mint_crud.now_utc())


# --------------------------------------------------------------------------------------------- view

def test_view_lists_accepted_ore_have_and_limit(client, world):
    _give(world, ALPHA, ORE, 3)
    _give(world, ALPHA, ORE, 4)
    _give(world, ALPHA, ORE, 9, enhancement_points_spent=2)            # not a plain stack
    _give(world, ALPHA, INGOT, 2)
    _set_season(world, minted_court=100, minted_players=50)
    resp = _view(client)
    assert resp.status_code == 200, resp.text
    v = resp.json()
    assert (v["npc_id"], v["npc_name"], v["country_id"], v["country_name"], v["region_id"]) == \
        (MINTER, "Монетчик", 1, "Мидденгерд", 10)
    assert v["working"] is True and v["closed_reason"] is None
    period = _period(world)
    assert v["period"]["index"] == 0 and v["period"]["season"] == period.season and v["period"]["year"] == 1
    assert (v["limit"], v["minted_court"], v["minted_players"], v["remaining"]) == (LIMIT, 100, 50, LIMIT - 150)
    assert v["wallet"] == WALLET
    items = {i["item_id"]: i for i in v["items"]}
    assert sorted(items) == [ORE, INGOT]                                # invalid group / disabled are hidden
    assert (items[ORE]["name"], items[ORE]["marks_per_item"], items[ORE]["have"],
            items[ORE]["max_by_limit"]) == ("Железная руда", 12, 7, (LIMIT - 150) // 12)
    assert items[INGOT]["have"] == 2 and items[INGOT]["max_by_limit"] == (LIMIT - 150) // 40
    world.gate.assert_not_called()                                      # GET needs no gate


def test_view_of_a_closed_mint_answers_the_reason(client, world):
    _exec(world, "INSERT INTO econ_mints (country_id, is_enabled) VALUES (1, 0)")
    v = _view(client).json()
    assert v["working"] is False and v["closed_reason"] == mint_crud.REASON_DISABLED and v["remaining"] == 0


# --------------------------------------------------------------------------------------------- success

def test_mint_success_multi_stack(client, world):
    _give(world, ALPHA, ORE, 3)
    _give(world, ALPHA, ORE, 4)
    stock_before = _ore_stock(world)
    resp = _post(client, quantity=5)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["marks"] == 60 and data["quantity"] == 5 and data["wallet"] == WALLET + 60
    assert data["requested"] == 5 and data["partial"] is False
    assert data["message"] == "Отчеканено 60 марок: Железная руда × 5"
    assert data["operation_id"] and data["view"]["minted_players"] == 60
    assert data["view"]["items"][0]["have"] == 2
    rows = _inv(world)
    assert len(rows) == 1 and rows[0][1] == 2                           # first stack deleted, second decremented
    assert _ore_stock(world) == stock_before + 5                        # price 10 / base 10 = 1 unit each
    court, players, units = _season(world)
    assert (court, players) == (0, 60) and Decimal(str(units)) == Decimal("5")
    assert _wallet(world) == WALLET + 60
    (op_id, key, region_id, location_id, actor), = _mint_ops(world)
    assert key == "mint:1:req-00000001" and region_id == 10 and location_id == 100 and actor == 7
    legs = _rows(world, "SELECT a1.kind, a2.kind, a2.ref_id, l.amount FROM econ_postings l "
                        "JOIN econ_accounts a1 ON a1.id = l.from_account_id "
                        "JOIN econ_accounts a2 ON a2.id = l.to_account_id WHERE l.operation_id = :o", o=op_id)
    assert legs == [("emission", "character", ALPHA, 60)]               # untaxed, one leg
    world.gate.assert_awaited_with(ALPHA, 100, MINTER)
    _assert_invariant(world)


def test_mint_whole_stack_and_ingot_units(client, world):
    _give(world, ALPHA, INGOT, 2)
    stock_before = _ore_stock(world)
    resp = _post(client, item_id=INGOT, quantity=2)
    assert resp.status_code == 200, resp.text
    assert resp.json()["marks"] == 80
    assert _inv(world, item_id=INGOT) == []
    assert _ore_stock(world) == stock_before + 6                        # price 30 / base 10 = 3 units each


def test_non_plain_stacks_are_never_taken(client, world):
    _give(world, ALPHA, ORE, 5, enhancement_points_spent=1)
    _give(world, ALPHA, ORE, 5, socketed_gems="[1]")
    _give(world, ALPHA, ORE, 5, current_durability=10)
    _give(world, ALPHA, ORE, 2)
    resp = _post(client, quantity=3)
    assert resp.status_code == 400
    assert resp.json()["detail"] == mint_crud.MSG_NOT_ENOUGH.format(name="Железная руда", need=3, have=2)
    assert _post(client, quantity=2, request_id="req-00000002").status_code == 200
    assert sorted(q for _i, q in _inv(world)) == [5, 5, 5]


def test_not_enough_ore_takes_nothing(client, world):
    _give(world, ALPHA, ORE, 2)
    resp = _post(client, quantity=3)
    assert resp.status_code == 400 and "нужно 3, есть 2" in resp.json()["detail"]
    assert _inv(world)[0][1] == 2 and _wallet(world) == WALLET and _mint_ops(world) == []
    assert _season(world)[:2] == (0, 0)


# --------------------------------------------------------------------------------------------- items / limit

@pytest.mark.parametrize("item_id", [BREAD, ORE_TOOLS, ORE_OFF, 9999])
def test_item_not_accepted(client, world, item_id):
    _give(world, ALPHA, item_id, 5)
    resp = _post(client, item_id=item_id)
    assert resp.status_code == 400 and resp.json()["detail"] == mint_crud.MSG_ITEM_NOT_ACCEPTED
    assert _rows(world, "SELECT quantity FROM character_inventory WHERE item_id = :i", i=item_id) == [(5,)]


def test_limit_exhausted(client, world):
    _give(world, ALPHA, ORE, 5)
    _set_season(world, minted_court=LIMIT - 11)                         # 11 left < 12 per piece
    resp = _post(client)
    assert resp.status_code == 409
    assert resp.json()["detail"] == mint_crud.MSG_LIMIT.format(date=econ_mint.fmt_date(_period(world).ends_at))
    assert _inv(world)[0][1] == 5 and _wallet(world) == WALLET


def test_request_that_does_not_fit_is_accepted_partially(client, world):
    """User decision 2026-11-01: take as much as fits, pay for it, the rest of the ore stays with the player."""
    _give(world, ALPHA, ORE, 3)
    _give(world, ALPHA, ORE, 4)
    _set_season(world, minted_court=100, minted_players=LIMIT - 100 - 30)  # 30 left -> 2 pieces of 12
    stock_before = _ore_stock(world)
    resp = _post(client, quantity=5)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert (data["quantity"], data["requested"], data["partial"], data["marks"]) == (2, 5, True, 24)
    assert data["message"] == mint_crud.MSG_PARTIAL.format(accepted=2, requested=5, marks="24 марки",
                                                           name="Железная руда")
    assert data["message"].startswith("Принято 2 из 5 шт. — лимит сезона исчерпан, остальная руда осталась у вас")
    assert data["wallet"] == WALLET + 24 and _wallet(world) == WALLET + 24
    assert [q for _i, q in _inv(world)] == [1, 4]  # 2 taken from the first stack only
    assert _ore_stock(world) == stock_before + 2                        # stock grows by the accepted pieces only
    court, players, units = _season(world)
    assert (court, players) == (100, LIMIT - 100 - 30 + 24) and Decimal(str(units)) == Decimal("2")
    (op_id, key, *_rest), = _mint_ops(world)
    assert key == "mint:1:req-00000001"
    assert _rows(world, "SELECT amount FROM econ_postings WHERE operation_id = :o", o=op_id) == [(24,)]
    v = data["view"]
    assert v["remaining"] == 6 and v["items"][0]["have"] == 5 and v["items"][0]["max_by_limit"] == 0
    _assert_invariant(world)


def test_partial_acceptance_takes_across_stacks(client, world):
    _give(world, ALPHA, ORE, 2)
    _give(world, ALPHA, ORE, 2)
    _give(world, ALPHA, ORE, 5)
    _set_season(world, minted_players=LIMIT - 12 * 5 - 7)              # 67 left -> 5 pieces
    resp = _post(client, quantity=9)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["quantity"], resp.json()["marks"], resp.json()["partial"]) == (5, 60, True)
    assert [q for _i, q in _inv(world)] == [4]  # 2 + 2 deleted, third stack 5 -> 4
    assert _season(world)[1] == LIMIT - 7


def test_exact_fit_is_not_partial(client, world):
    _give(world, ALPHA, ORE, 5)
    _set_season(world, minted_players=LIMIT - 36)                      # exactly 3 pieces
    data = _post(client, quantity=3).json()
    assert (data["quantity"], data["requested"], data["partial"]) == (3, 3, False)
    assert data["message"] == "Отчеканено 36 марок: Железная руда × 3"


def test_partial_needs_the_requested_quantity_in_the_bag(client, world):
    """The «not enough ore» check is against the REQUESTED quantity, even when fewer pieces would fit."""
    _give(world, ALPHA, ORE, 3)
    _set_season(world, minted_players=LIMIT - 24)                      # 2 pieces fit
    resp = _post(client, quantity=4)
    assert resp.status_code == 400
    assert resp.json()["detail"] == mint_crud.MSG_NOT_ENOUGH.format(name="Железная руда", need=4, have=3)
    assert _inv(world)[0][1] == 3 and _wallet(world) == WALLET and _mint_ops(world) == []
    assert _season(world)[:2] == (0, LIMIT - 24)


def test_partial_retry_with_the_same_request_id_is_one_operation(client, world):
    _give(world, ALPHA, ORE, 10)
    _set_season(world, minted_players=LIMIT - 36)                      # 3 pieces fit
    first = _post(client, quantity=5)
    assert first.status_code == 200 and first.json()["quantity"] == 3
    again = _post(client, quantity=5)
    assert again.status_code == 409 and again.json()["detail"] == mint_crud.MSG_DUPLICATE
    assert len(_mint_ops(world)) == 1 and _inv(world)[0][1] == 7 and _wallet(world) == WALLET + 36
    assert _season(world)[1] == LIMIT


def test_nothing_fits_is_still_409_and_takes_nothing(client, world):
    _give(world, ALPHA, ORE, 5)
    _set_season(world, minted_players=LIMIT - 11)                      # 11 left < 12 per piece
    stock_before = _ore_stock(world)
    resp = _post(client, quantity=5)
    assert resp.status_code == 409
    assert resp.json()["detail"] == mint_crud.MSG_LIMIT.format(date=econ_mint.fmt_date(_period(world).ends_at))
    assert _inv(world)[0][1] == 5 and _wallet(world) == WALLET and _mint_ops(world) == []
    assert _ore_stock(world) == stock_before and _season(world)[:2] == (0, LIMIT - 11)


def test_partial_posting_failure_keeps_all_the_ore(client, world, monkeypatch):
    _give(world, ALPHA, ORE, 5)
    _set_season(world, minted_players=LIMIT - 24)
    stock_before = _ore_stock(world)

    def rejected(*_a, **_k):
        raise core.EconomyError("rejected")

    monkeypatch.setattr(econ_ledger, "post_operation", rejected)
    assert _post(client, quantity=5).status_code == 400
    assert _inv(world)[0][1] == 5 and _ore_stock(world) == stock_before
    assert _season(world)[:2] == (0, LIMIT - 24) and _wallet(world) == WALLET


def test_shared_limit_counts_court_and_players(client, world):
    _give(world, ALPHA, ORE, 10)
    _set_season(world, minted_court=LIMIT - 24)
    assert _post(client, quantity=2).status_code == 200
    assert _season(world)[:2] == (LIMIT - 24, 24)
    assert _post(client, quantity=1, request_id="req-00000002").status_code == 409


# --------------------------------------------------------------------------------------------- idempotency / atomicity

def test_same_request_id_twice_is_one_operation(client, world):
    _give(world, ALPHA, ORE, 10)
    assert _post(client, quantity=2).status_code == 200
    again = _post(client, quantity=2)
    assert again.status_code == 409 and again.json()["detail"] == mint_crud.MSG_DUPLICATE
    assert len(_mint_ops(world)) == 1 and _inv(world)[0][1] == 8 and _wallet(world) == WALLET + 24
    assert _season(world)[1] == 24
    # another character's identical request_id is a different key
    _give(world, BETA, ORE, 1)
    _exec(world, "UPDATE characters SET current_location_id = 100 WHERE id = :i", i=BETA)
    _as_user(8)
    assert _post(client, character_id=BETA).status_code == 200
    assert [k for _i, k, *_r in _mint_ops(world)] == ["mint:1:req-00000001", "mint:2:req-00000001"]


def test_posting_failure_keeps_the_ore(client, world, monkeypatch):
    _give(world, ALPHA, ORE, 5)
    stock_before = _ore_stock(world)

    def rejected(*_a, **_k):
        raise core.EconomyError("rejected")

    monkeypatch.setattr(econ_ledger, "post_operation", rejected)
    resp = _post(client, quantity=3)
    assert resp.status_code == 400 and resp.json()["detail"] == "Операция отклонена"
    assert _inv(world)[0][1] == 5 and _ore_stock(world) == stock_before
    assert _season(world)[:2] == (0, 0) and _wallet(world) == WALLET


def test_db_error_on_posting_keeps_the_ore_and_hides_internals(client, world, monkeypatch):
    from sqlalchemy.exc import OperationalError
    _give(world, ALPHA, ORE, 5)

    def broken(*_a, **_k):
        raise OperationalError("INSERT secret", {}, Exception("db down"))

    monkeypatch.setattr(econ_ledger, "post_operation", broken)
    resp = _post(client, quantity=3)
    assert resp.status_code == 500 and "secret" not in resp.text and "INSERT" not in resp.text
    assert _inv(world)[0][1] == 5 and _season(world)[:2] == (0, 0)


def test_duplicate_raised_by_the_ledger_rolls_back(client, world, monkeypatch):
    _give(world, ALPHA, ORE, 5)

    def dup(*_a, **_k):
        raise core.DuplicateOperation(1)

    monkeypatch.setattr(econ_ledger, "post_operation", dup)
    resp = _post(client, quantity=3)
    assert resp.status_code == 409 and resp.json()["detail"] == mint_crud.MSG_DUPLICATE
    assert _inv(world)[0][1] == 5 and _season(world)[:2] == (0, 0)


# --------------------------------------------------------------------------------------------- gate order

def test_unauthenticated_is_401(world):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    anon = TestClient(app)
    assert anon.get(f"{MINT}/npc/{MINTER}", params={"character_id": ALPHA}).status_code == 401
    assert _post(anon).status_code == 401
    world.gate.assert_not_called()


def test_other_users_character_is_403_before_the_minter(client, world):
    _give(world, ALPHA, ORE, 5)
    _as_user(8)
    for npc in (MINTER, BANKER, 999):
        resp = _post(client, npc=npc)
        assert resp.status_code == 403 and resp.json()["detail"] == mint_crud.MSG_NOT_OWNER, npc
    assert _view(client).status_code == 403
    assert _inv(world)[0][1] == 5
    world.gate.assert_not_called()


def test_unknown_character_is_404(client, world):
    resp = _post(client, character_id=999)
    assert resp.status_code == 404 and resp.json()["detail"] == mint_crud.MSG_CHARACTER_NOT_FOUND


def test_npc_character_cannot_mint(client, world):
    _exec(world, "UPDATE characters SET user_id = 7 WHERE id = :i", i=BANKER)
    resp = _post(client, character_id=BANKER)
    assert resp.status_code == 403 and resp.json()["detail"] == mint_crud.MSG_NOT_PLAYER


@pytest.mark.parametrize("npc", [BANKER, ALPHA, 999])
def test_not_a_minter_is_404(client, world, npc):
    resp = _post(client, npc=npc)
    assert resp.status_code == 404 and resp.json()["detail"] == mint_crud.MSG_MINTER_NOT_FOUND
    assert _view(client, npc=npc).status_code == 404
    world.gate.assert_not_called()


def test_dead_minter_is_409_before_the_location(client, world):
    _exec(world, "UPDATE characters SET current_location_id = 200 WHERE id = :i", i=ALPHA)
    resp = _post(client, npc=MINTER_DEAD)
    assert resp.status_code == 409 and resp.json()["detail"] == mint_crud.MSG_MINTER_DEAD
    assert _view(client, npc=MINTER_DEAD).status_code == 409
    world.gate.assert_not_called()


def test_activity_lock_is_409_before_location_and_gate(client, world):
    _exec(world, "UPDATE characters SET dungeon_session_id = 5 WHERE id = :i", i=ALPHA)
    resp = _post(client, npc=MINTER_PORT)                               # other location as well
    assert resp.status_code == 409 and resp.json()["detail"] == "Персонаж находится в подземелье"
    world.gate.assert_not_called()
    assert _view(client).status_code == 200                             # GET is not locked


def test_wrong_location_is_400_and_never_asks_the_gate(client, world):
    resp = _post(client, npc=MINTER_PORT)
    assert resp.status_code == 400 and resp.json()["detail"] == mint_crud.MSG_WRONG_LOCATION
    assert _view(client, npc=MINTER_PORT).status_code == 400
    world.gate.assert_not_called()


def test_gate_closed_403_and_unavailable_503(client, world):
    _give(world, ALPHA, ORE, 5)
    world.gate.return_value = False
    resp = _post(client)
    assert resp.status_code == 403 and resp.json()["detail"] == mint_crud.MSG_GATE_CLOSED
    world.gate.return_value = True
    world.gate.side_effect = locations_client.GateUnavailable()
    resp = _post(client)
    assert resp.status_code == 503 and resp.json()["detail"] == mint_crud.MSG_GATE_UNAVAILABLE
    assert _inv(world)[0][1] == 5 and _mint_ops(world) == []


def test_minter_outside_the_capital_is_409(client, world):
    _as_user(8)
    _give(world, BETA, ORE, 5)
    resp = _post(client, npc=MINTER_PORT, character_id=BETA)
    assert resp.status_code == 409 and resp.json()["detail"] == mint_crud.MSG_NO_MINT
    assert _view(client, npc=MINTER_PORT, character_id=BETA).status_code == 409
    assert _inv(world, BETA)[0][1] == 5


def test_minter_without_a_region_is_409(client, world):
    _exec(world, "UPDATE characters SET current_location_id = 300 WHERE id = :i", i=ALPHA)
    resp = _post(client, npc=MINTER_NOWHERE)
    assert resp.status_code == 409 and resp.json()["detail"] == mint_crud.MSG_NO_MINT
    world.gate.assert_awaited_with(ALPHA, 300, MINTER_NOWHERE)          # the gate comes before the region


def test_country_without_a_capital_is_closed(client, world):
    _as_user(9)
    _give(world, GAMMA, ORE, 5)
    resp = _post(client, npc=MINTER_NO_CAPITAL, character_id=GAMMA)
    assert resp.status_code == 409
    assert resp.json()["detail"] == mint_crud.MSG_MINT_CLOSED.format(reason=mint_crud.REASON_NO_CAPITAL)
    v = _view(client, npc=MINTER_NO_CAPITAL, character_id=GAMMA).json()
    assert v["working"] is False and v["closed_reason"] == mint_crud.REASON_NO_CAPITAL


@pytest.mark.parametrize("setup,reason", [
    ("INSERT INTO econ_mints (country_id, is_enabled) VALUES (1, 0)", mint_crud.REASON_DISABLED),
    ("INSERT INTO econ_mints (country_id, season_limit, is_enabled) VALUES (1, 0, 1)", mint_crud.REASON_NO_LIMIT),
    ("DELETE FROM game_time_config", mint_crud.REASON_NO_CALENDAR),
    ("UPDATE econ_regions SET population = 0 WHERE region_id = 10", mint_crud.REASON_NOT_PARTICIPATING),
    ("DELETE FROM econ_region_goods WHERE region_id = 10 AND group_code = 'ore_metal'",
     mint_crud.REASON_NO_ORE_STOCK),
])
def test_closed_mint_reasons(client, world, setup, reason):
    _give(world, ALPHA, ORE, 5)
    _exec(world, setup)
    resp = _post(client)
    assert resp.status_code == 409
    assert resp.json()["detail"] == mint_crud.MSG_MINT_CLOSED.format(reason=reason)
    assert _inv(world)[0][1] == 5 and _mint_ops(world) == []


def test_manual_capital_moves_the_mint(client, world):
    """An admin picks the port as the capital: the old capital's minter no longer serves the mint."""
    _exec(world, "INSERT INTO econ_mints (country_id, capital_region_id, is_enabled) VALUES (1, 20, 1)")
    _give(world, ALPHA, ORE, 5)
    assert _post(client).json()["detail"] == mint_crud.MSG_NO_MINT
    _as_user(8)
    _give(world, BETA, ORE, 5)
    resp = _post(client, npc=MINTER_PORT, character_id=BETA)
    assert resp.status_code == 200, resp.text
    assert _mint_ops(world)[0][2] == 20


# --------------------------------------------------------------------------------------------- validation / security

@pytest.mark.parametrize("patch", [
    {"request_id": "x'; DROP TABLE econ_operations; --"},
    {"request_id": "' OR 1=1 --"},
    {"request_id": "short"},
    {"request_id": "a" * 65},
    {"request_id": None},
    {"item_id": "500; DROP TABLE items"},
    {"item_id": "500"},
    {"character_id": "1 OR 1=1"},
    {"quantity": 0},
    {"quantity": -3},
    {"quantity": 10_001},
    {"quantity": 1.5},
    {"quantity": True},
])
def test_malformed_body_is_422_and_changes_nothing(client, world, patch):
    _give(world, ALPHA, ORE, 5)
    resp = _post(client, patch)
    assert resp.status_code == 422, patch
    assert _inv(world)[0][1] == 5 and _mint_ops(world) == []
    world.gate.assert_not_called()


def test_missing_request_id_is_422(client, world):
    resp = client.post(f"{MINT}/npc/{MINTER}/mint", json={"character_id": ALPHA, "item_id": ORE, "quantity": 1})
    assert resp.status_code == 422


def test_injection_like_path_and_query_are_rejected(client, world):
    assert client.get(f"{MINT}/npc/60%20OR%201=1", params={"character_id": ALPHA}).status_code == 422
    assert client.get(f"{MINT}/npc/{MINTER}", params={"character_id": "1; DROP TABLE characters"}).status_code == 422
    assert _q(world, "SELECT COUNT(*) FROM characters") == 9

"""FEAT-183 B3: admin shop editor endpoints + crud.merchant_market on the shared merchant SQLite world.

World (econ_contract_cases MERCHANT_*): NPC 31 «Trader» is a living merchant of region 10 (capital,
tax 0.15, food ×1.4, ore ×0.8) with rows 1 (bread, stock 5), 2 (ore, stock NULL), 4 (scroll, inactive);
NPC 32 (via a parent location, also living) has a player-origin row 3; 33 dead, 34 no location,
35 dungeon, 36 no region, 37/38/39 not simulated, 40 is a player, 41 location gone.
"""

import os
import sys
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import econ_contract_cases as cc  # noqa: E402
from auth_http import UserRead, get_admin_user  # noqa: E402
from database import get_db  # noqa: E402
from main import app  # noqa: E402


def _build_world(path):
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        for ddl in cc.MERCHANT_SQLITE_DDL:
            conn.execute(text(ddl))
        for sql, params in cc.MERCHANT_SEED_SQL:
            conn.execute(text(sql), params)
    eng.dispose()


def _sql(path, query, **params):
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        rows = conn.execute(text(query), params)
        out = rows.fetchall() if rows.returns_rows else None
    eng.dispose()
    return out


@pytest.fixture()
def world(tmp_path):
    path = tmp_path / "shop.db"
    _build_world(path)
    return path


@pytest.fixture()
def api(world):
    engine = create_async_engine(f"sqlite+aiosqlite:///{world}", poolclass=NullPool)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _db():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_admin_user] = lambda: UserRead(id=1, username="admin", role="admin", permissions=[])
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


async def _market(world, npc_id):
    engine = create_async_engine(f"sqlite+aiosqlite:///{world}", poolclass=NullPool)
    try:
        async with sessionmaker(engine, class_=AsyncSession)() as s:
            return await crud.merchant_market(s, npc_id)
    finally:
        await engine.dispose()


# ----------------------------------------------------------------------------- crud.merchant_market

async def test_merchant_market_living(world):
    m = await _market(world, 31)
    assert (m.living, m.reason, m.location_id, m.region_id) == (True, None, 1000, 10)
    assert m.tax_rate == Decimal("0.15")
    assert m.mults["food"] == Decimal("1.4") and m.mults["ore_metal"] == Decimal("0.8")
    assert m.mults["tools"] == Decimal(1)                      # group without a region row -> ×1
    assert m.group_base == {"food": 2, "ore_metal": 10, "tools": 15, "weapons": 120}
    assert m.bid_share == Decimal("0.4")                       # from econ_sim_settings.params


@pytest.mark.parametrize("npc_id,reason,region_id", [
    (33, "dead", 10), (34, "no_location", None), (35, "dungeon", 10), (36, "no_region", None),
    (37, "not_simulated", 20), (38, "not_simulated", 30), (39, "not_simulated", 40),
    (40, "not_npc", None), (41, "no_region", None), (999, "not_npc", None),
])
async def test_merchant_market_legacy(world, npc_id, reason, region_id):
    m = await _market(world, npc_id)
    assert (m.living, m.reason, m.region_id) == (False, reason, region_id)
    assert (m.mults, m.group_base) == ({}, {})
    assert m.bid_share == Decimal("0.5")                       # default, params not read for legacy


async def test_merchant_market_region_without_econ_row_has_no_tax(world):
    assert (await _market(world, 38)).tax_rate is None
    assert (await _market(world, 37)).tax_rate == Decimal("0.1")


# ----------------------------------------------------------------------------- GET /market

def test_market_endpoint_living(api, world):
    r = api.get("/locations/admin/npc-shop/31/market")
    assert r.status_code == 200
    body = r.json()
    assert body["living"] is True and body["reason"] is None
    assert (body["region_id"], body["region_name"], body["location_id"]) == (10, "Capital", 1000)
    assert body["tax_rate"] == pytest.approx(0.15)
    assert body["cash"] == 500
    # active admin on-market rows: bread (food) and ore (ore_metal); the inactive scroll is ignored
    assert body["buys_groups"] == [{"code": "food", "name": "Еда"}, {"code": "ore_metal", "name": "Руда"}]


def test_market_endpoint_player_origin_rows_do_not_widen_groups(api):
    body = api.get("/locations/admin/npc-shop/32/market").json()
    assert body["living"] is True and body["buys_groups"] == []


@pytest.mark.parametrize("npc_id,reason", [(34, "no_location"), (35, "dungeon"), (36, "no_region"),
                                           (38, "not_simulated")])
def test_market_endpoint_legacy(api, npc_id, reason):
    body = api.get(f"/locations/admin/npc-shop/{npc_id}/market").json()
    assert (body["living"], body["reason"], body["buys_groups"]) == (False, reason, [])


@pytest.mark.parametrize("npc_id", [40, 999])
def test_market_endpoint_unknown_npc(api, npc_id):
    r = api.get(f"/locations/admin/npc-shop/{npc_id}/market")
    assert r.status_code == 404 and r.json()["detail"] == "НПС не найден"


# ----------------------------------------------------------------------------- admin list / create / update

def test_admin_list_has_market_prices(api):
    rows = {r["id"]: r for r in api.get("/locations/admin/npc-shop/31/items").json()}
    assert set(rows) == {1, 2, 4}
    bread, ore, scroll = rows[1], rows[2], rows[4]
    # bread: base 4/2, food ×1.4 -> ask ceil(5.6)=6, bid min(floor(2.8)=2, floor(6*0.5)=3) = 2
    assert (bread["group"], bread["market"], bread["ask"], bread["bid"]) == ("food", True, 6, 2)
    assert (bread["restock_target"], bread["origin"]) == (10, "admin")
    # ore: base 3000/1250, ×0.8 -> ask 2400, bid min(1000, 1200) = 1000
    assert (ore["ask"], ore["bid"], ore["stock"]) == (2400, 1000, None)
    # scroll: off-market -> ×1, sell 0 -> does not buy
    assert (scroll["off_market"], scroll["market"], scroll["ask"], scroll["bid"]) == (True, False, 60, 0)


def test_admin_list_legacy_merchant_bid_cap(api, world):
    _sql(world, "INSERT INTO npc_shop_items (id, npc_id, item_id, buy_price, sell_price, stock, restock_target) "
                "VALUES (10, 38, 1, 30, 25, 3, 3)")
    row = api.get("/locations/admin/npc-shop/38/items").json()[0]
    assert (row["market"], row["ask"], row["bid"]) == (False, 30, 15)   # ×1, bid capped at floor(30*0.5)


def test_admin_create_ok_and_duplicate(api, world):
    r = api.post("/locations/admin/npc-shop/31/items", json={"item_id": 3, "buy_price": 200, "sell_price": 80})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["restock_target"], body["origin"], body["stock"], body["group"]) == (10, "admin", None, "weapons")
    assert (body["ask"], body["bid"]) == (200, 80)                       # weapons ×1 in region 10
    dup = api.post("/locations/admin/npc-shop/31/items", json={"item_id": 3, "buy_price": 5})
    assert dup.status_code == 409 and dup.json()["detail"] == "Этот предмет уже есть в магазине"
    assert _sql(world, "SELECT COUNT(*) FROM npc_shop_items WHERE npc_id = 31 AND item_id = 3")[0][0] == 1


@pytest.mark.parametrize("npc_id,item_id,detail", [(999, 1, "НПС не найден"), (40, 1, "НПС не найден"),
                                                   (31, 404, "Предмет не найден")])
def test_admin_create_unknown_npc_or_item(api, npc_id, item_id, detail):
    r = api.post(f"/locations/admin/npc-shop/{npc_id}/items", json={"item_id": item_id, "buy_price": 5})
    assert r.status_code == 404 and r.json()["detail"] == detail


@pytest.mark.parametrize("body", [
    {"item_id": 3, "buy_price": 0},
    {"item_id": 3, "buy_price": -5},
    {"item_id": 3, "buy_price": 1_000_000_001},
    {"item_id": 3, "buy_price": 5, "sell_price": -1},
    {"item_id": 3, "buy_price": 5, "stock": -1},
    {"item_id": 3, "buy_price": 5, "stock": 100_001},
    {"item_id": 3, "buy_price": 5, "restock_target": -1},
    {"item_id": 0, "buy_price": 5},
    {"item_id": "1; DROP TABLE items", "buy_price": 5},
])
def test_admin_create_bounds(api, body):
    assert api.post("/locations/admin/npc-shop/31/items", json=body).status_code == 422


def test_admin_update_player_row_becomes_admin(api, world):
    r = api.put("/locations/admin/npc-shop/items/3", json={"stock": None, "restock_target": 4})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["origin"], body["stock"], body["restock_target"]) == ("admin", None, 4)
    assert _sql(world, "SELECT origin, stock, restock_target FROM npc_shop_items WHERE id = 3")[0] == ("admin", None, 4)


@pytest.mark.parametrize("body", [{"buy_price": 0}, {"sell_price": -1}, {"stock": -2}, {"restock_target": 100_001}])
def test_admin_update_bounds(api, body):
    assert api.put("/locations/admin/npc-shop/items/1", json=body).status_code == 422


def test_admin_update_missing_row(api):
    assert api.put("/locations/admin/npc-shop/items/999", json={"stock": 1}).status_code == 404

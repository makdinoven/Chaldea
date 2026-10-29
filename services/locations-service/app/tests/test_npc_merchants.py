"""FEAT-183 Q2: NPC merchant player flows — gaps not covered by B3 / B4 tests.

B4 (`test_econ_locations_flows.py` TestNpcBuy / TestNpcSell / TestLivingMerchant) and B3
(`test_npc_shop_admin_market.py`) already pin the main paths. This file adds:

* trade_tax at the region rate on the PAID (discounted) amount, the 10 % country leg only when it
  is ≥ 1, no trade_tax leg when it rounds to 0; regions with an econ row that are not simulated,
  dead NPCs and off-market rows of a living merchant;
* stock / cash races on two real connections (last unit, merchant cash for one sale, first sale
  of a new item creating ONE player-origin row);
* refund fallback with the merchant's cash really spent (no mocked reversal) and the double
  failure path (nothing paid twice);
* sell refusals at the exact cash boundary, unknown / off-market / sell_price 0 / inactive /
  player-origin-only groups, credit failure other than InsufficientFunds (item returned, 500);
* no profitable buy -> sell-back round trip at maximal charisma for absurd admin prices, living
  and legacy, including through a player-origin row;
* HTTP: quantity / id bounds (strings, SQL-like strings, huge numbers), sell-offers auth
  (401 / 403 / 404) and no cash disclosure, public shop window hiding rules and field set,
  admin shop endpoints RBAC (401 / 403 / moderator ok);
* migration 053: revision id length / chain (the dedupe statement is MySQL-only `DELETE … JOIN`,
  not runnable on SQLite — verified on the local MySQL, see the feature log).

Every money-moving scenario ends with the world invariant Σ characters + Σ accounts = 0.
"""

import asyncio
import importlib.util
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import econ_core  # noqa: E402
import econ_ledger  # noqa: E402
import main  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from database import get_db  # noqa: E402

# Helpers + the `shop_db` fixture of the B4 flows (Test* classes are NOT imported: no double collection).
from test_econ_locations_flows import (  # noqa: E402,F401
    shop_db, _Shop, _buy, _sell, _mirror_row, _make_living, _fund, _shop_item, _balance, _stock,
    _account, _world_sum, _one, _ops, _http_factory, _user,
    PLAYER, OTHER, USER, OTHER_USER, NPC_REGION, NPC_NOWHERE, REGION_A, COUNTRY_A, ROW, ITEM,
    OTHER_FOOD, SWORD,
)

RARE_FOOD, AXE, TRINKET = 10, 11, 12   # legendary food (off-market), a second weapon, misc (no group)
MAX_CHARISMA = 10 ** 6             # discount is capped at 50 %


async def _legs(s, op_type="npc_shop_buy"):
    rows = (await s.execute(text(
        "SELECT p.leg_type, p.amount FROM econ_postings p JOIN econ_operations o ON o.id = p.operation_id "
        "WHERE o.op_type = :t ORDER BY p.id"), {"t": op_type})).fetchall()
    return sorted(tuple(r) for r in rows)


async def _exec(s, sql, **p):
    await s.execute(text(sql), p)
    await s.commit()


async def _set_stock(s, stock, row=ROW):
    await _exec(s, "UPDATE npc_shop_items SET stock = :st WHERE id = :r", st=stock, r=row)


async def _add_items(s):
    await _exec(s, "INSERT INTO items (id, name, image, item_type, item_rarity, resource_subcategory, is_food, "
                   "price) VALUES (10, 'Амброзия', NULL, 'consumable', 'legendary', NULL, 1, 50), "
                   "(11, 'Топор', NULL, 'weapon', 'common', NULL, 0, 200), "
                   "(12, 'Безделушка', NULL, 'misc', 'common', NULL, 0, 20)")


# ═══════════════════════════════════════════════════════════════════════════
# Buy legs and amounts
# ═══════════════════════════════════════════════════════════════════════════

class TestLivingBuyLegs:

    @pytest.mark.parametrize("tax,price,expected_legs,npc,region,country", [
        # ask = ceil(price * 1.5); trade_tax = floor(ask * tax); country = floor(trade_tax * 0.1)
        ("0.2", 100, [("main", 150), ("tax", 3), ("trade_tax", 30)], 120, 27, 3),
        ("0.05", 100, [("main", 150), ("trade_tax", 7)], 143, 7, 0),        # country 0.7 -> no leg
        ("0", 100, [("main", 150)], 150, 0, 0),                              # tax-free region
        ("0.2", 2, [("main", 3)], 3, 0, 0),                                  # trade_tax 0.6 -> no leg
        ("0.15", 600, [("main", 900), ("tax", 13), ("trade_tax", 135)], 765, 122, 13),
    ])
    async def test_trade_tax_follows_the_region_rate(self, shop_db, tax, price, expected_legs, npc, region,
                                                     country):
        await _make_living(shop_db, tax=tax)
        with _Shop(item=_shop_item(NPC_REGION, price=price, stock=3)):
            out = await _buy(shop_db, NPC_REGION)
        paid = expected_legs[0][1]
        assert out["total_price"] == paid
        assert await _legs(shop_db) == sorted(expected_legs)
        assert await _balance(shop_db, PLAYER) == 1000 - paid
        assert await _balance(shop_db, NPC_REGION) == npc
        assert (await _account(shop_db, "region_treasury", REGION_A) or 0) == region
        assert (await _account(shop_db, "country_treasury", COUNTRY_A) or 0) == country
        assert await _stock(shop_db) == 2
        assert await _world_sum(shop_db) == 0

    async def test_trade_tax_is_taken_from_the_discounted_amount(self, shop_db):
        await _make_living(shop_db)
        # ask 150, charisma cap 50 % -> 75; trade_tax floor(15) = 15, country 1
        with _Shop(item=_shop_item(NPC_REGION, price=100, stock=3), charisma=MAX_CHARISMA):
            out = await _buy(shop_db, NPC_REGION)
        assert (out["total_price"], out["discount_percent"]) == (75, 50.0)
        assert await _legs(shop_db) == [("main", 75), ("tax", 1), ("trade_tax", 15)]
        assert (await _balance(shop_db, PLAYER), await _balance(shop_db, NPC_REGION)) == (925, 60)
        assert await _world_sum(shop_db) == 0

    async def test_region_with_an_econ_row_but_no_population_stays_legacy(self, shop_db):
        await _exec(shop_db, "INSERT INTO econ_regions (region_id, template_code, population, tax_rate) "
                             "VALUES (10, 'capital', 0, 0.2)")
        await _exec(shop_db, "INSERT INTO econ_region_goods (region_id, group_code, price_mult) "
                             "VALUES (10, 'food', 1.5)")
        with _Shop(item=_shop_item(NPC_REGION, price=100, stock=None)):
            out = await _buy(shop_db, NPC_REGION)
        # base price (×1), treasury paid, unlimited stock stays NULL, the NPC's cash is untouched
        assert out["total_price"] == 100
        assert await _legs(shop_db) == [("main", 100), ("tax", 10)]
        assert await _balance(shop_db, NPC_REGION) == 0
        assert await _account(shop_db, "region_treasury", REGION_A) == 90
        assert await _stock(shop_db) is None
        assert await _world_sum(shop_db) == 0

    async def test_dead_merchant_trades_the_legacy_way(self, shop_db):
        await _make_living(shop_db)
        await _exec(shop_db, "UPDATE characters SET npc_status = 'dead' WHERE id = :n", n=NPC_REGION)
        with _Shop(item=_shop_item(NPC_REGION, price=100, stock=None)):
            out = await _buy(shop_db, NPC_REGION)
        assert out["total_price"] == 100
        assert ("trade_tax", 20) not in await _legs(shop_db)
        assert await _balance(shop_db, NPC_REGION) == 0
        assert await _world_sum(shop_db) == 0

    async def test_off_market_row_of_a_living_merchant_is_base_priced_and_taxed(self, shop_db):
        await _make_living(shop_db)
        await _exec(shop_db, "INSERT INTO econ_item_groups (item_id, group_code, off_market) VALUES (7, NULL, 1)")
        with _Shop(item=_shop_item(NPC_REGION, price=100, stock=2)):
            out = await _buy(shop_db, NPC_REGION)
        assert out["total_price"] == 100                                 # ×1, not ×1.5
        assert await _legs(shop_db) == [("main", 100), ("tax", 2), ("trade_tax", 20)]
        assert await _balance(shop_db, NPC_REGION) == 80
        assert await _stock(shop_db) == 1
        assert await _world_sum(shop_db) == 0

    async def test_player_short_of_gold_at_a_living_merchant_moves_nothing(self, shop_db):
        await _make_living(shop_db)
        await _exec(shop_db, "UPDATE characters SET currency_balance = 149 WHERE id = :c", c=PLAYER)
        await _exec(shop_db, "UPDATE econ_accounts SET balance = balance + 851 WHERE kind = 'emission'")
        assert await _world_sum(shop_db) == 0
        with _Shop(item=_shop_item(NPC_REGION, price=100, stock=5)) as shop:
            with pytest.raises(HTTPException) as exc:
                await _buy(shop_db, NPC_REGION)
        assert exc.value.status_code == 400 and exc.value.detail.startswith("Недостаточно")
        shop.client.post.assert_not_awaited()
        assert await _stock(shop_db) == 5
        assert (await _balance(shop_db, PLAYER), await _balance(shop_db, NPC_REGION)) == (149, 0)
        assert await _one(shop_db, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'npc_shop_buy'") == 0
        assert await _world_sum(shop_db) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Races on two real connections
# ═══════════════════════════════════════════════════════════════════════════

def _refused_without_payment(result):
    """The loser of a race: a clean 4xx refusal or the database lock (SQLite) — never a payment."""
    if isinstance(result, HTTPException):
        return result.status_code in (400, 409, 500)
    return isinstance(result, Exception)


async def _two_sessions(shop_db):
    return (AsyncSession(bind=shop_db.bind, expire_on_commit=False),
            AsyncSession(bind=shop_db.bind, expire_on_commit=False))


class TestRaces:

    @pytest.mark.parametrize("living", [True, False])
    async def test_concurrent_buys_of_the_last_unit_pay_once(self, shop_db, living):
        if living:
            await _make_living(shop_db)
        with _Shop(item=_shop_item(NPC_REGION, price=50, stock=1)) as shop:
            await _mirror_row(shop_db, NPC_REGION)
            a, b = await _two_sessions(shop_db)
            try:
                results = await asyncio.gather(
                    _buy(a, NPC_REGION, mirror=False),
                    _buy(b, NPC_REGION, character_id=OTHER, uid=OTHER_USER, mirror=False),
                    return_exceptions=True)
            finally:
                await a.close()
                await b.close()
        paid = [r for r in results if isinstance(r, dict)]
        assert len(paid) == 1, results
        assert all(_refused_without_payment(r) for r in results if not isinstance(r, dict)), results
        assert shop.client.post.await_count == 1
        price = 75 if living else 50
        assert sorted([await _balance(shop_db, PLAYER), await _balance(shop_db, OTHER)]) == [1000 - price, 1000]
        assert await _stock(shop_db) == 0
        assert await _ops(shop_db, "npc_shop_buy") == 1
        assert await _world_sum(shop_db) == 0

    async def test_concurrent_sales_to_a_merchant_with_cash_for_one(self, shop_db):
        await _make_living(shop_db)
        await _fund(shop_db, NPC_REGION, 60)                 # bid = 60: exactly one unit
        await _set_stock(shop_db, 0)
        with _Shop(sell_price=40) as shop:
            await _mirror_row(shop_db, NPC_REGION)
            a, b = await _two_sessions(shop_db)
            try:
                results = await asyncio.gather(
                    _sell(a, NPC_REGION, mirror=False),
                    _sell(b, NPC_REGION, character_id=OTHER, uid=OTHER_USER, mirror=False),
                    return_exceptions=True)
            finally:
                await a.close()
                await b.close()
        paid = [r for r in results if isinstance(r, dict)]
        assert len(paid) == 1, results
        loser = [r for r in results if not isinstance(r, dict)][0]
        if isinstance(loser, HTTPException) and loser.status_code == 400:
            # refused by the plain cash pre-check (the winner committed first): nothing removed
            assert shop.client.delete.await_count == 1
            shop.client.post.assert_not_awaited()
        else:
            # both items removed, the loser's credit failed -> item returned through the internal route
            assert isinstance(loser, HTTPException) and loser.status_code in (409, 500), loser
            assert shop.client.delete.await_count == 2
            assert shop.client.post.await_count == 1
            assert "/inventory/internal/characters/" in shop.client.post.await_args.args[0]
        assert await _balance(shop_db, NPC_REGION) == 0
        assert sorted([await _balance(shop_db, PLAYER), await _balance(shop_db, OTHER)]) == [1000, 1060]
        assert await _stock(shop_db) == 1                    # only the paid unit is stocked
        assert await _ops(shop_db, "npc_shop_sell") == 1
        assert await _world_sum(shop_db) == 0

    async def test_concurrent_first_sales_of_a_new_item_share_one_row(self, shop_db):
        await _make_living(shop_db)
        await _fund(shop_db, NPC_REGION, 1000)
        with _Shop():
            a, b = await _two_sessions(shop_db)
            try:
                results = await asyncio.gather(
                    _sell(a, NPC_REGION, item_id=OTHER_FOOD, quantity=2, mirror=False),
                    _sell(b, NPC_REGION, character_id=OTHER, uid=OTHER_USER, item_id=OTHER_FOOD, quantity=3,
                          mirror=False),
                    return_exceptions=True)
            finally:
                await a.close()
                await b.close()
        paid = [r for r in results if isinstance(r, dict)]
        assert paid, results
        rows = (await shop_db.execute(text(
            "SELECT stock, origin FROM npc_shop_items WHERE npc_id = :n AND item_id = :i"),
            {"n": NPC_REGION, "i": OTHER_FOOD})).fetchall()
        assert len(rows) == 1 and rows[0][1] == "player"
        assert rows[0][0] == sum(r["quantity"] for r in paid)
        assert await _balance(shop_db, NPC_REGION) == 1000 - sum(r["total_price"] for r in paid)
        assert await _world_sum(shop_db) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Refunds
# ═══════════════════════════════════════════════════════════════════════════

class TestRefund:

    async def test_fallback_when_the_merchant_really_spent_the_cash(self, shop_db):
        """No mocked reversal: between the purchase and the failed inventory add the merchant's
        cash is spent (another player's sale on a separate connection); the reversal is refused
        by the ledger and the treasury of his place refunds the player."""
        await _make_living(shop_db)

        async def _spend_then_refuse(*args, **kwargs):
            other = AsyncSession(bind=shop_db.bind, expire_on_commit=False)
            try:
                cash = await crud.merchant_cash(other, NPC_REGION)
                await crud.pay_player_from_merchant(other, NPC_REGION, OTHER, cash, region_id=REGION_A,
                                                    location_id=1000, metadata={"test": "drain"})
                await other.commit()
            finally:
                await other.close()
            return MagicMock(status_code=400, json=MagicMock(return_value={"detail": "Инвентарь переполнен"}))

        with _Shop(item=_shop_item(NPC_REGION, price=100, stock=5)) as shop:
            shop.client.post = AsyncMock(side_effect=_spend_then_refuse)
            with pytest.raises(HTTPException) as exc:
                await _buy(shop_db, NPC_REGION)
        assert exc.value.status_code == 500
        assert await _balance(shop_db, PLAYER) == 1000                   # refunded in full
        assert await _balance(shop_db, NPC_REGION) == 0
        assert await _balance(shop_db, OTHER) == 1120                    # 150 - trade_tax 30
        assert await _stock(shop_db) == 5
        meta = await _one(shop_db, "SELECT metadata FROM econ_operations WHERE op_type = 'npc_shop_buy_refund'")
        assert '"fallback": true' in meta and '"reverses_operation_id"' in meta
        assert await _ops(shop_db, "npc_shop_buy_refund") == 1
        assert await _world_sum(shop_db) == 0

    async def test_reversal_and_fallback_both_failing_pay_nothing_twice(self, shop_db):
        await _make_living(shop_db)

        async def _broke(*a, **kw):
            raise econ_core.InsufficientFunds(econ_core.AccountRef.character(NPC_REGION), 120)

        async def _down(*a, **kw):
            raise RuntimeError("db down")

        with _Shop(item=_shop_item(NPC_REGION, price=100, stock=5), post_status=400), \
                patch.object(crud, "reverse_operation", _broke), patch.object(crud, "pay_character", _down):
            with pytest.raises(HTTPException) as exc:
                await _buy(shop_db, NPC_REGION)
        assert exc.value.status_code == 500
        # residual risk (logged): the purchase stands, nothing is refunded twice, the stock take stands
        assert await _balance(shop_db, PLAYER) == 850
        assert await _ops(shop_db, "npc_shop_buy_refund") == 0
        assert await _stock(shop_db) == 4
        assert await _world_sum(shop_db) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Selling: refusals and failures
# ═══════════════════════════════════════════════════════════════════════════

class TestSellRefusals:

    @pytest.mark.parametrize("cash,ok", [(0, False), (59, False), (60, True), (61, True)])
    async def test_cash_boundary(self, shop_db, cash, ok):
        await _make_living(shop_db)
        if cash:
            await _fund(shop_db, NPC_REGION, cash)
        await _set_stock(shop_db, 0)
        with _Shop(sell_price=40) as shop:
            if ok:
                out = await _sell(shop_db, NPC_REGION)
                assert out["total_price"] == 60
            else:
                with pytest.raises(HTTPException) as exc:
                    await _sell(shop_db, NPC_REGION)
                assert exc.value.status_code == 409 and exc.value.detail == "У меня сейчас нет на это денег"
                shop.client.delete.assert_not_awaited()
                shop.client.post.assert_not_awaited()
        assert await _balance(shop_db, NPC_REGION) == (cash - 60 if ok else cash)
        assert await _stock(shop_db) == (1 if ok else 0)
        assert await _world_sum(shop_db) == 0

    async def test_broke_merchant_refuses_a_new_item_without_creating_a_row(self, shop_db):
        await _make_living(shop_db)
        with _Shop() as shop:
            with pytest.raises(HTTPException) as exc:
                await _sell(shop_db, NPC_REGION, item_id=OTHER_FOOD, mirror=False)
        assert exc.value.status_code == 409
        shop.client.delete.assert_not_awaited()
        assert await _one(shop_db, "SELECT COUNT(*) FROM npc_shop_items WHERE item_id = :i", i=OTHER_FOOD) == 0

    @pytest.mark.parametrize("setup,item_id", [
        ("rare", RARE_FOOD),                                         # food group, legendary -> off-market
        ("override_off_market", OTHER_FOOD),                         # admin override off-market
        ("no_group", TRINKET),                                       # misc: no goods group -> off-market
        ("row_sell_zero", ITEM),                                     # admin row with sell_price 0
        ("row_inactive", ITEM),                                      # inactive admin row
        ("only_inactive_food_row", OTHER_FOOD),                      # inactive row does not make food bought
        ("player_row_only", AXE),                                    # player-origin weapon row: weapons not bought
        ("unknown_item", 4242),                                      # not in items
    ])
    async def test_living_merchant_refuses(self, shop_db, setup, item_id):
        await _make_living(shop_db)
        await _fund(shop_db, NPC_REGION, 10_000)
        await _add_items(shop_db)
        if setup == "override_off_market":
            await _exec(shop_db, "INSERT INTO econ_item_groups (item_id, group_code, off_market) VALUES (8, 'food', 1)")
        elif setup == "row_sell_zero":
            await _exec(shop_db, "UPDATE npc_shop_items SET sell_price = 0 WHERE id = :r", r=ROW)
        elif setup in ("row_inactive", "only_inactive_food_row"):
            await _exec(shop_db, "UPDATE npc_shop_items SET is_active = 0 WHERE id = :r", r=ROW)
        elif setup == "player_row_only":
            await _exec(shop_db, "INSERT INTO npc_shop_items (npc_id, item_id, buy_price, sell_price, stock, "
                                 "is_active, restock_target, origin) VALUES (:n, 9, 300, 150, 2, 1, 0, 'player')",
                        n=NPC_REGION)
        with _Shop() as shop:
            with pytest.raises(HTTPException) as exc:
                await _sell(shop_db, NPC_REGION, item_id=item_id, mirror=False)
        assert exc.value.status_code == 400 and exc.value.detail == "Этот NPC не покупает данный предмет"
        shop.client.delete.assert_not_awaited()
        assert await _balance(shop_db, NPC_REGION) == 10_000
        assert await _ops(shop_db, "npc_shop_sell") == 0

    async def test_player_origin_row_itself_is_bought_at_its_bid(self, shop_db):
        await _make_living(shop_db)
        await _fund(shop_db, NPC_REGION, 1000)
        await _exec(shop_db, "INSERT INTO npc_shop_items (id, npc_id, item_id, buy_price, sell_price, stock, "
                             "is_active, restock_target, origin) VALUES (901, :n, 9, 300, 150, 0, 1, 0, 'player')",
                    n=NPC_REGION)
        with _Shop():
            out = await _sell(shop_db, NPC_REGION, item_id=SWORD, mirror=False)
        # weapons have no region row -> ×1: bid = min(150, floor(300 * 0.5)) = 150
        assert out["total_price"] == 150
        assert await _stock(shop_db, 901) == 1
        assert await _world_sum(shop_db) == 0

    async def test_legacy_row_with_sell_price_zero_is_refused(self, shop_db):
        await _exec(shop_db, "UPDATE npc_shop_items SET sell_price = 0 WHERE id = :r", r=ROW)
        with _Shop() as shop:
            with pytest.raises(HTTPException) as exc:
                await _sell(shop_db, NPC_REGION, mirror=False)
        assert exc.value.status_code == 400
        shop.client.delete.assert_not_awaited()

    @pytest.mark.parametrize("returned", [True, False])
    async def test_other_credit_failure_returns_the_item_and_answers_500(self, shop_db, returned):
        await _make_living(shop_db)
        await _fund(shop_db, NPC_REGION, 1000)

        async def _boom(*a, **kw):
            raise RuntimeError("ledger down")

        with _Shop(sell_price=40, post_status=200 if returned else 500) as shop, \
                patch.object(crud, "pay_player_from_merchant", _boom):
            with pytest.raises(HTTPException) as exc:
                await _sell(shop_db, NPC_REGION, item_id=OTHER_FOOD, quantity=2, mirror=False)
        assert exc.value.status_code == 500 and exc.value.detail == "Не удалось завершить продажу"
        assert shop.client.delete.await_count == 1
        shop.client.post.assert_awaited_once()
        assert shop.client.post.await_args.kwargs["json"] == {"item_id": OTHER_FOOD, "quantity": 2}
        assert "X-Internal-Token" in shop.client.post.await_args.kwargs["headers"]   # internal route, not the JWT
        # the player-origin row insert rolled back with the failed credit
        assert await _one(shop_db, "SELECT COUNT(*) FROM npc_shop_items WHERE item_id = :i", i=OTHER_FOOD) == 0
        assert (await _balance(shop_db, PLAYER), await _balance(shop_db, NPC_REGION)) == (1000, 1000)
        assert await _world_sum(shop_db) == 0

    async def test_legacy_credit_failure_returns_the_item(self, shop_db):
        async def _boom(*a, **kw):
            raise RuntimeError("ledger down")

        with _Shop(sell_price=40) as shop, patch.object(crud, "pay_character", _boom):
            with pytest.raises(HTTPException) as exc:
                await _sell(shop_db, NPC_REGION)
        assert exc.value.status_code == 500
        shop.client.post.assert_awaited_once()
        assert await _balance(shop_db, PLAYER) == 1000
        assert await _one(shop_db, "SELECT COUNT(*) FROM econ_operations") == 0


# ═══════════════════════════════════════════════════════════════════════════
# No profitable buy -> sell-back round trip
# ═══════════════════════════════════════════════════════════════════════════

class TestNoProfitableRoundTrip:

    @pytest.mark.parametrize("living", [True, False])
    @pytest.mark.parametrize("mult", ["0.5", "1", "1.5", "3.7"])
    @pytest.mark.parametrize("buy_price,sell_price", [(1, 1), (3, 3), (99, 500), (101, 101), (12345, 99999)])
    async def test_buy_at_max_charisma_then_sell_back(self, shop_db, living, mult, buy_price, sell_price):
        if living:
            await _make_living(shop_db, food_mult=mult)
            await _fund(shop_db, NPC_REGION, 10 ** 6)
        if buy_price > 1000:
            await _fund(shop_db, PLAYER, 10 ** 6)
        start = await _balance(shop_db, PLAYER)
        with _Shop(item=_shop_item(NPC_REGION, price=buy_price, stock=5, sell_price=sell_price),
                   charisma=MAX_CHARISMA):
            bought = await _buy(shop_db, NPC_REGION)
            try:
                sold_total = (await _sell(shop_db, NPC_REGION, mirror=False))["total_price"]
            except HTTPException as exc:          # bid < 1 -> «does not buy»: no round trip at all
                assert exc.status_code == 400
                sold_total = 0
        assert sold_total <= bought["total_price"], (bought, sold_total)
        assert await _balance(shop_db, PLAYER) <= start
        assert await _world_sum(shop_db) == 0

    @pytest.mark.parametrize("mult", ["0.5", "1.5", "3.7"])
    async def test_round_trip_through_a_player_origin_row(self, shop_db, mult):
        await _make_living(shop_db, food_mult=mult)
        await _fund(shop_db, NPC_REGION, 10 ** 6)
        start = await _balance(shop_db, PLAYER)
        with _Shop(charisma=MAX_CHARISMA):
            await _sell(shop_db, NPC_REGION, item_id=OTHER_FOOD, quantity=3, mirror=False)
        row = await _one(shop_db, "SELECT id FROM npc_shop_items WHERE item_id = :i", i=OTHER_FOOD)
        stored = (await shop_db.execute(text("SELECT id, npc_id, item_id, buy_price, sell_price, stock FROM "
                                             "npc_shop_items WHERE id = :r"), {"r": row})).first()
        item = SimpleNamespace(id=stored[0], npc_id=stored[1], item_id=stored[2], is_active=True,
                               buy_price=stored[3], sell_price=stored[4], stock=stored[5], origin="player")
        with _Shop(item=item, charisma=MAX_CHARISMA):
            body = main.schemas.ShopBuyRequest(character_id=PLAYER, shop_item_id=row, quantity=3)
            await main.buy_from_npc(npc_id=NPC_REGION, body=body, request=MagicMock(), session=shop_db,
                                    current_user=_user())
            await _sell(shop_db, NPC_REGION, item_id=OTHER_FOOD, quantity=3, mirror=False)
        # sold 3, bought 3 back, sold 3 again: the player holds what he started with minus nothing gained
        # from the buy/sell-back pair (first sale is a plain sale, the pair must not be profitable)
        first_sale = await _one(shop_db, "SELECT MIN(id) FROM econ_operations WHERE op_type = 'npc_shop_sell'")
        legs = (await shop_db.execute(text(
            "SELECT o.op_type, SUM(p.amount) FROM econ_operations o JOIN econ_postings p ON p.operation_id = o.id "
            "WHERE p.leg_type = 'main' AND o.id > :f GROUP BY o.op_type"), {"f": first_sale})).fetchall()
        sums = dict(legs)
        assert sums["npc_shop_sell"] <= sums["npc_shop_buy"]
        assert await _balance(shop_db, PLAYER) >= start              # sanity: first sale paid something
        assert await _world_sum(shop_db) == 0


# ═══════════════════════════════════════════════════════════════════════════
# HTTP: bounds, auth, shop window, admin RBAC
# ═══════════════════════════════════════════════════════════════════════════

OWNER_U = UserRead(id=USER, username="owner", role="user", permissions=[])
STRANGER_U = UserRead(id=99, username="stranger", role="user", permissions=[])
ADMIN_U = UserRead(id=1, username="admin", role="admin", permissions=["characters:read"])
MODERATOR_U = UserRead(id=2, username="mod", role="moderator", permissions=[])


@pytest.fixture()
def http(shop_db, tmp_path):
    """TestClient over the shop_db file. `http.viewer = user | None` sets the authenticated user
    (None = no override: the real OAuth2 dependency answers 401 without a token)."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'shop.db'}", poolclass=NullPool)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _db():
        async with Session() as s:
            yield s

    app = main.app
    app.dependency_overrides[get_db] = _db

    class _Http:
        def as_user(self, user):
            if user is None:
                app.dependency_overrides.pop(get_current_user_via_http, None)
            else:
                app.dependency_overrides[get_current_user_via_http] = lambda: user
            return self.client

    h = _Http()
    with TestClient(app) as client:
        h.client = client
        yield h
    app.dependency_overrides.clear()


class TestHttpBounds:

    @pytest.mark.parametrize("field,value", [
        ("quantity", "abc"), ("quantity", "1; DROP TABLE npc_shop_items"), ("quantity", 0), ("quantity", -1),
        ("quantity", 1000), ("quantity", 10 ** 30), ("quantity", None), ("quantity", []),
        ("shop_item_id", "1 OR 1=1"), ("shop_item_id", 0), ("shop_item_id", -5),
        ("character_id", "1' --"), ("character_id", 0),
    ])
    async def test_buy_body_is_validated(self, http, field, value):
        body = {"character_id": PLAYER, "shop_item_id": ROW, "quantity": 1, field: value}
        r = http.as_user(OWNER_U).post(f"/locations/npcs/{NPC_REGION}/shop/buy", json=body)
        assert r.status_code == 422, r.text

    @pytest.mark.parametrize("field,value", [
        ("quantity", "abc"), ("quantity", 0), ("quantity", -1), ("quantity", 1000), ("quantity", 10 ** 30),
        ("item_id", "7 OR 1=1"), ("item_id", 0), ("character_id", -1),
    ])
    async def test_sell_body_is_validated(self, http, field, value):
        body = {"character_id": PLAYER, "item_id": ITEM, "quantity": 1, field: value}
        r = http.as_user(OWNER_U).post(f"/locations/npcs/{NPC_REGION}/shop/sell", json=body)
        assert r.status_code == 422, r.text

    @pytest.mark.parametrize("path", [
        "/locations/npcs/1%20OR%201=1/shop", "/locations/npcs/abc/shop/sell-offers?character_id=1",
        "/locations/npcs/50%27--/shop/buy",
    ])
    async def test_sql_like_path_ids_are_422(self, http, path):
        client = http.as_user(OWNER_U)
        r = client.post(path, json={}) if path.endswith("/buy") else client.get(path)
        assert r.status_code == 422

    async def test_buy_without_token_is_401(self, http):
        r = http.as_user(None).post(f"/locations/npcs/{NPC_REGION}/shop/buy",
                                    json={"character_id": PLAYER, "shop_item_id": ROW, "quantity": 1})
        assert r.status_code == 401

    async def test_negative_npc_id_moves_nothing(self, http, shop_db):
        with patch.object(main, "_require_npc_gate", AsyncMock(return_value=None)):
            r = http.as_user(OWNER_U).post("/locations/npcs/-1/shop/buy",
                                           json={"character_id": PLAYER, "shop_item_id": ROW, "quantity": 1})
        assert r.status_code == 404
        assert await (_one(shop_db, "SELECT COUNT(*) FROM econ_operations")) == 0


class TestSellOffersHttp:

    async def _bag(self, shop_db, rows):
        for item_id, qty in rows:
            await shop_db.execute(text("INSERT INTO character_inventory (character_id, item_id, quantity) "
                                       "VALUES (1, :i, :q)"), {"i": item_id, "q": qty})
        await shop_db.commit()

    async def test_without_token_is_401(self, http):
        r = http.as_user(None).get(f"/locations/npcs/{NPC_REGION}/shop/sell-offers?character_id={PLAYER}")
        assert r.status_code == 401

    @pytest.mark.parametrize("viewer,status", [(STRANGER_U, 403), (MODERATOR_U, 403), (OWNER_U, 200),
                                               (ADMIN_U, 200)])
    async def test_private_gate(self, http, viewer, status):
        r = http.as_user(viewer).get(f"/locations/npcs/{NPC_REGION}/shop/sell-offers?character_id={PLAYER}")
        assert r.status_code == status, r.text

    @pytest.mark.parametrize("npc_id,character_id", [(NPC_REGION, 4242), (4242, PLAYER), (OTHER, PLAYER)])
    async def test_unknown_character_or_npc_is_404(self, http, npc_id, character_id):
        r = http.as_user(ADMIN_U).get(f"/locations/npcs/{npc_id}/shop/sell-offers?character_id={character_id}")
        assert r.status_code == 404

    @pytest.mark.parametrize("query", ["", "?character_id=0", "?character_id=-1", "?character_id=abc",
                                       "?character_id=1%20OR%201=1"])
    async def test_bad_character_id_is_422(self, http, query):
        r = http.as_user(OWNER_U).get(f"/locations/npcs/{NPC_REGION}/shop/sell-offers{query}")
        assert r.status_code == 422

    async def test_offers_do_not_depend_on_or_disclose_the_cash(self, http, shop_db):
        await (_make_living(shop_db))
        await self._bag(shop_db, [(ITEM, 5000), (OTHER_FOOD, 2), (SWORD, 1)])
        url = f"/locations/npcs/{NPC_REGION}/shop/sell-offers?character_id={PLAYER}"
        broke = http.as_user(OWNER_U).get(url).json()
        await (_fund(shop_db, NPC_REGION, 10 ** 6))
        rich = http.as_user(OWNER_U).get(url).json()
        assert broke == rich
        assert [(o["item_id"], o["unit_price"], o["max_quantity"]) for o in rich] == [(7, 60, 999), (8, 7, 2)]
        assert all(set(o) == {"item_id", "item_name", "item_image", "unit_price", "max_quantity"} for o in rich)

    async def test_legacy_offers_only_rows_with_a_buy_price(self, http, shop_db):
        await self._bag(shop_db, [(ITEM, 1), (OTHER_FOOD, 2)])
        r = http.as_user(OWNER_U).get(f"/locations/npcs/{NPC_REGION}/shop/sell-offers?character_id={PLAYER}")
        assert [(o["item_id"], o["unit_price"]) for o in r.json()] == [(7, 40)]

    async def test_empty_bag(self, http):
        r = http.as_user(OWNER_U).get(f"/locations/npcs/{NPC_REGION}/shop/sell-offers?character_id={PLAYER}")
        assert r.status_code == 200 and r.json() == []


PUBLIC_KEYS = {"id", "npc_id", "item_id", "buy_price", "sell_price", "stock", "is_active", "item_name",
               "item_image", "item_rarity", "item_type", "created_at", "base_buy_price", "base_sell_price",
               "in_stock", "market", "price_level", "living"}


class TestShopWindowHttp:

    async def _rows(self, shop_db):
        await (_exec(shop_db, "INSERT INTO npc_shop_items (id, npc_id, item_id, buy_price, sell_price, stock, "
                             "is_active, restock_target, origin) VALUES "
                             "(910, :n, 8, 10, 5, 0, 1, 0, 'player'), "     # player row, empty -> hidden
                             "(911, :n, 9, 300, 150, 2, 1, 0, 'player'), "  # player row with stock -> shown
                             "(912, :n, 10, 50, 0, 3, 0, 3, 'admin')",      # inactive -> hidden
                    n=NPC_REGION))

    async def test_living_window(self, http, shop_db):
        await (_make_living(shop_db))
        await (_add_items(shop_db))
        await self._rows(shop_db)
        await (_fund(shop_db, NPC_REGION, 777))
        r = http.as_user(None).get(f"/locations/npcs/{NPC_REGION}/shop")
        assert r.status_code == 200
        rows = {row["id"]: row for row in r.json()}
        assert set(rows) == {ROW, 911}
        assert all(set(row) == PUBLIC_KEYS for row in rows.values())   # no cash / restock / origin / tax
        assert "777" not in r.text
        assert (rows[ROW]["stock"], rows[ROW]["in_stock"]) == (0, False)  # living NULL -> 0, still listed
        assert (rows[911]["stock"], rows[911]["in_stock"], rows[911]["buy_price"]) == (2, True, 300)

    async def test_legacy_window_keeps_unlimited_stock(self, http, shop_db):
        await (_add_items(shop_db))
        await self._rows(shop_db)
        rows = {row["id"]: row for row in http.as_user(None).get(f"/locations/npcs/{NPC_REGION}/shop").json()}
        assert set(rows) == {ROW, 911}
        assert (rows[ROW]["stock"], rows[ROW]["in_stock"], rows[ROW]["living"]) == (None, True, False)
        assert (rows[ROW]["buy_price"], rows[ROW]["sell_price"]) == (100, 40)

    async def test_unknown_npc_has_an_empty_window(self, http):
        r = http.as_user(None).get("/locations/npcs/4242/shop")
        assert r.status_code == 200 and r.json() == []


class TestAdminShopRbac:

    ENDPOINTS = [
        ("get", f"/locations/admin/npc-shop/{NPC_REGION}/items", None),
        ("get", f"/locations/admin/npc-shop/{NPC_REGION}/market", None),
        ("post", f"/locations/admin/npc-shop/{NPC_REGION}/items", {"item_id": SWORD, "buy_price": 5}),
        ("put", f"/locations/admin/npc-shop/items/{ROW}", {"stock": 3}),
        ("delete", f"/locations/admin/npc-shop/items/{ROW}", None),
    ]

    @pytest.mark.parametrize("method,path,body", ENDPOINTS)
    async def test_without_token_is_401(self, http, shop_db, method, path, body):
        client = http.as_user(None)
        r = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert r.status_code == 401
        assert await (_one(shop_db, "SELECT COUNT(*) FROM npc_shop_items")) == 1
        assert await (_stock(shop_db)) is None

    @pytest.mark.parametrize("method,path,body", ENDPOINTS)
    async def test_player_is_403(self, http, shop_db, method, path, body):
        client = http.as_user(OWNER_U)
        r = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert r.status_code == 403
        assert await (_one(shop_db, "SELECT COUNT(*) FROM npc_shop_items")) == 1
        assert await (_stock(shop_db)) is None

    async def test_moderator_may_edit_and_sees_the_cash(self, http, shop_db):
        await (_make_living(shop_db))
        await (_fund(shop_db, NPC_REGION, 321))
        client = http.as_user(MODERATOR_U)
        body = client.get(f"/locations/admin/npc-shop/{NPC_REGION}/market").json()
        assert (body["living"], body["cash"], body["region_id"]) == (True, 321, REGION_A)
        r = client.post(f"/locations/admin/npc-shop/{NPC_REGION}/items", json={"item_id": SWORD, "buy_price": 5})
        assert r.status_code == 200, r.text
        dup = client.post(f"/locations/admin/npc-shop/{NPC_REGION}/items", json={"item_id": SWORD, "buy_price": 9})
        assert dup.status_code == 409

    @pytest.mark.parametrize("path", ["/locations/admin/npc-shop/1%20OR%201=1/items",
                                      "/locations/admin/npc-shop/50;DROP/market"])
    async def test_sql_like_ids_are_422(self, http, path):
        assert http.as_user(ADMIN_U).get(path).status_code == 422

    async def test_sql_like_put_id_is_422(self, http):
        r = http.as_user(ADMIN_U).put("/locations/admin/npc-shop/items/1%27%20OR%20%271", json={"stock": 1})
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Migration 053
# ═══════════════════════════════════════════════════════════════════════════

def _migration():
    path = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "053_npc_shop_market.py")
    spec = importlib.util.spec_from_file_location("mig053", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_053_revision_chain():
    mod = _migration()
    assert mod.revision == "053_npc_shop_market" and len(mod.revision) <= 32
    assert os.path.exists(os.path.join(os.path.dirname(__file__), "..", "alembic", "versions",
                                       f"{mod.down_revision}.py")) or mod.down_revision.startswith("052")
    assert mod.DEFAULT_RESTOCK_TARGET == econ_core.DEFAULT_RESTOCK_TARGET


def test_migration_053_dedupe_prefers_the_active_lowest_id():
    """The dedupe statement is MySQL `DELETE … JOIN` (not runnable on SQLite); pin its keep-rule:
    a row is deleted only when a row of the same (npc, item) is more active, or equally active
    with a lower id."""
    sql = " ".join(_migration().DEDUPE_SQL.split())
    assert "k.npc_id = s.npc_id AND k.item_id = s.item_id AND k.id <> s.id" in sql
    assert "(k.is_active > s.is_active OR (k.is_active = s.is_active AND k.id < s.id))" in sql

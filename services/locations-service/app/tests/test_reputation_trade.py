"""FEAT-197 (task 10): region reputation at the NPC merchants of locations-service.

Real reads (``@pytest.mark.real_reputation``) against the FEAT-181/183 shop world of
``test_econ_locations_flows`` (``shop_db``) plus the SQLite stand-ins of the character-service
reputation tables (``reputation_sqlite.py``). Only the network (inventory-service, charisma) is mocked.

Covered:

* the personal shop view: discount tiers add to charisma under the 50 % cap (the reputation share in
  ``price_reasons`` is the APPLIED one), markup tiers raise the price above ``buy_price``, labels;
  the public view is unchanged even for an outlaw; a merchant without a region ignores reputation;
* reputation is per region (the merchant's region, not the player's), lazily decayed, and read from the
  admin-edited tier table (custom names / percents; an incomplete table falls back to the defaults);
* buy: price, ``discount_percent`` (net, negative with a markup), ``price_reasons``, operation metadata;
* A1 sell side: bid cut −10 / −25 %, a bid cut to 0 = «does not buy», high tiers never raise the bid,
  ``price_reasons`` / ``base_unit_price`` on sell-offers and on the sale itself, living merchant too;
* Вне закона: 409 on the personal shop view, sell-offers, buy and sell — nothing moves;
* NPC-level gate (``characters.reputation_min_tier``) on sell-offers, the FEAT-145 trade gate and the
  dialogue; security: SQL-like tier codes are never executed.
"""

import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import econ_core  # noqa: E402
import main  # noqa: E402
import reputation_core as rc  # noqa: E402
import reputation_read  # noqa: E402
import reputation_sqlite  # noqa: E402
import visibility  # noqa: E402

from test_econ_locations_flows import (  # noqa: E402,F401
    shop_db, _Shop, _buy, _sell, _mirror_row, _make_living, _fund, _shop_item, _balance, _stock,
    _one, _ops, _world_sum, _user,
    PLAYER, OTHER, USER, NPC_REGION, NPC_NOWHERE, REGION_A, ROW, ITEM,
)

pytestmark = pytest.mark.real_reputation

REGION_B = 20                       # another country (location 1001)
LEGEND, DEFENDER, TRUSTED, FAMILIAR, WANDERER = 900, 600, 300, 100, 0
WATCHED, OUTCAST, OUTLAW = -100, -300, -600
CHARISMA_10 = 100                   # 10 % (FEAT-195)
CHARISMA_35 = 1000                  # 35 %
CHARISMA_40 = 1200                  # 40 %
CHARISMA_MAX = 10 ** 6              # 50 % (cap)
REFUSED = "Торговцы этого края отказываются иметь с вами дело (репутация: Вне закона)"


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
async def rdb(shop_db):
    """shop_db + the reputation tables (empty = default settings / tiers) + characters.reputation_min_tier."""
    await reputation_sqlite.create_async(shop_db)
    await shop_db.commit()
    return shop_db


async def _rep(s, value, *, region=REGION_A, cid=PLAYER, decay_at=None):
    await s.execute(text("INSERT INTO character_reputation (character_id, region_id, value, decay_at, updated_at) "
                         "VALUES (:c, :r, :v, :d, :u)"),
                    {"c": cid, "r": region, "v": value, "d": decay_at, "u": datetime.utcnow()})
    await s.commit()


async def _npc_tier(s, code, npc=NPC_REGION):
    await s.execute(text("UPDATE characters SET reputation_min_tier = :t WHERE id = :n"), {"t": code, "n": npc})
    await s.commit()


async def _seed_tiers(s, **over):
    """All 8 tiers in reputation_tiers (the defaults with `over` = {code: {field: value}} applied)."""
    for t in rc.DEFAULT_TIERS:
        row = {"code": t.code, "sort_order": t.sort_order, "name": t.name, "min_value": t.min_value,
               "price_pct": str(t.price_pct), "sell_pct": str(t.sell_pct), "trade_refused": int(t.trade_refused)}
        row.update(over.get(t.code, {}))
        await s.execute(text("INSERT INTO reputation_tiers (code, sort_order, name, min_value, price_pct, sell_pct, "
                             "trade_refused) VALUES (:code, :sort_order, :name, :min_value, :price_pct, :sell_pct, "
                             ":trade_refused)"), row)
    await s.commit()


async def _bag(s, item_id=ITEM, quantity=3, cid=PLAYER):
    await s.execute(text("INSERT INTO character_inventory (character_id, item_id, quantity) VALUES (:c, :i, :q)"),
                    {"c": cid, "i": item_id, "q": quantity})
    await s.commit()


async def _set_row(s, *, buy_price=100, sell_price=40, npc=NPC_REGION):
    await s.execute(text("UPDATE npc_shop_items SET npc_id = :n, buy_price = :b, sell_price = :sp WHERE id = :r"),
                    {"n": npc, "b": buy_price, "sp": sell_price, "r": ROW})
    await s.commit()


async def _personal_shop(s, *, npc=NPC_REGION, charisma=0, character_id=PLAYER):
    with patch.object(visibility, "require_private_access", AsyncMock(return_value=None)), \
            patch.object(main, "_fetch_charisma", AsyncMock(return_value=charisma)):
        return await main.get_npc_shop(npc_id=npc, character_id=character_id, session=s, current_user=_user())


def _rep_reason(percent, label):
    return {"source": "reputation", "percent": percent, "label": label}


def _cha_reason(percent):
    return {"source": "charisma", "percent": percent, "label": "Скидка за харизму"}


def _reasons(row):
    return [r.dict() for r in row.price_reasons]


# ═══════════════════════════════════════════════════════════════════════════
# Personal shop view (GET /npcs/{id}/shop?character_id)
# ═══════════════════════════════════════════════════════════════════════════

class TestShopView:

    @pytest.mark.parametrize("value,charisma,price,reasons", [
        (WANDERER, 0, 100, []),
        (FAMILIAR, 0, 100, []),                                                   # 0 % tier: no reason
        (TRUSTED, 0, 95, [_rep_reason(5.0, "Скидка за репутацию (Свой человек)")]),
        (DEFENDER, 0, 90, [_rep_reason(10.0, "Скидка за репутацию (Заступник)")]),
        (LEGEND, 0, 85, [_rep_reason(15.0, "Скидка за репутацию (Легенда края)")]),
        (LEGEND, CHARISMA_10, 75, [_cha_reason(10.0), _rep_reason(15.0, "Скидка за репутацию (Легенда края)")]),
        # the SUM is capped at 50 %: the reputation share shown is what was really applied
        (LEGEND, CHARISMA_35, 50, [_cha_reason(35.0), _rep_reason(15.0, "Скидка за репутацию (Легенда края)")]),
        (LEGEND, CHARISMA_40, 50, [_cha_reason(40.0), _rep_reason(10.0, "Скидка за репутацию (Легенда края)")]),
        (LEGEND, CHARISMA_MAX, 50, [_cha_reason(50.0)]),                         # nothing left for reputation
        # markups apply on top of the charisma price and may exceed buy_price
        (WATCHED, 0, 110, [_rep_reason(-10.0, "Наценка за репутацию (На заметке)")]),
        (OUTCAST, 0, 125, [_rep_reason(-25.0, "Наценка за репутацию (Изгой)")]),
        (OUTCAST, CHARISMA_10, 113, [_cha_reason(10.0), _rep_reason(-25.0, "Наценка за репутацию (Изгой)")]),
        (WATCHED, CHARISMA_MAX, 55, [_cha_reason(50.0), _rep_reason(-10.0, "Наценка за репутацию (На заметке)")]),
    ])
    async def test_price_and_reasons_by_tier(self, rdb, value, charisma, price, reasons):
        await _rep(rdb, value)
        (row,) = await _personal_shop(rdb, charisma=charisma)
        assert row.buy_price == 100
        assert row.discounted_buy_price == price
        assert _reasons(row) == reasons
        assert row.discounted_buy_price == econ_core.reputation_ask(
            100, econ_core.charisma_discount_pct(charisma), rc.tier_for(value, rc.DEFAULT_TIERS).price_pct)

    async def test_markup_price_is_above_the_shop_price(self, rdb):
        await _rep(rdb, OUTCAST)
        (row,) = await _personal_shop(rdb)
        assert row.discounted_buy_price > row.buy_price

    async def test_discount_never_goes_below_half_the_ask(self, rdb):
        await _set_row(rdb, buy_price=7)
        await _rep(rdb, LEGEND)
        (row,) = await _personal_shop(rdb, charisma=CHARISMA_MAX)
        assert row.discounted_buy_price == 4                                   # ceil(7 * 0.5)

    async def test_reputation_of_another_region_does_not_count(self, rdb):
        await _rep(rdb, LEGEND, region=REGION_B)
        await _rep(rdb, OUTLAW, cid=OTHER)                                      # someone else's standing
        (row,) = await _personal_shop(rdb)
        assert (row.discounted_buy_price, _reasons(row)) == (100, [])

    async def test_outlaw_in_another_region_still_trades_here(self, rdb):
        await _rep(rdb, OUTLAW, region=REGION_B)
        (row,) = await _personal_shop(rdb)
        assert row.discounted_buy_price == 100

    async def test_outlaw_gets_409_on_the_personal_view(self, rdb):
        await _rep(rdb, OUTLAW)
        with pytest.raises(HTTPException) as exc:
            await _personal_shop(rdb)
        assert (exc.value.status_code, exc.value.detail) == (409, REFUSED)

    async def test_outlaw_at_the_boundary(self, rdb):
        await _rep(rdb, -599)                                                   # still Изгой
        (row,) = await _personal_shop(rdb)
        assert row.discounted_buy_price == 125
        await rdb.execute(text("UPDATE character_reputation SET value = -600"))
        await rdb.commit()
        with pytest.raises(HTTPException) as exc:
            await _personal_shop(rdb)
        assert exc.value.status_code == 409

    async def test_public_view_is_unchanged_for_an_outlaw(self, rdb):
        await _rep(rdb, OUTLAW)
        rows = await main.get_npc_shop(npc_id=NPC_REGION, character_id=None, session=rdb, current_user=None)
        assert len(rows) == 1
        dumped = rows[0].dict()
        assert "discounted_buy_price" not in dumped and "price_reasons" not in dumped
        assert dumped["buy_price"] == 100

    async def test_merchant_without_a_region_ignores_reputation(self, rdb):
        await _set_row(rdb, npc=NPC_NOWHERE)
        await _rep(rdb, OUTLAW)                                                 # region 10 only
        (row,) = await _personal_shop(rdb, npc=NPC_NOWHERE, charisma=CHARISMA_10)
        assert (row.discounted_buy_price, _reasons(row)) == (90, [_cha_reason(10.0)])

    async def test_lazy_decay_lifts_the_tier(self, rdb):
        # −301 (Изгой) a day and a minute ago at 10 points/day -> −291 (На заметке)
        await _rep(rdb, -301, decay_at=datetime.utcnow() - timedelta(days=1, minutes=1))
        (row,) = await _personal_shop(rdb)
        assert row.discounted_buy_price == 110
        assert _reasons(row) == [_rep_reason(-10.0, "Наценка за репутацию (На заметке)")]

    async def test_decay_off_in_settings_keeps_the_tier(self, rdb):
        await rdb.execute(text("INSERT INTO reputation_settings (id, min_value, max_value, echo_pct, decay_per_day) "
                               "VALUES (1, -1000, 1000, 20, 0)"))
        await _rep(rdb, -301, decay_at=datetime.utcnow() - timedelta(days=30))
        (row,) = await _personal_shop(rdb)
        assert row.discounted_buy_price == 125

    async def test_admin_edited_tier_names_and_percents_are_used(self, rdb):
        await _seed_tiers(rdb, trusted={"name": "Друг края", "price_pct": "20"})
        await _rep(rdb, TRUSTED)
        (row,) = await _personal_shop(rdb)
        assert row.discounted_buy_price == 80
        assert _reasons(row) == [_rep_reason(20.0, "Скидка за репутацию (Друг края)")]

    async def test_admin_can_make_another_tier_refuse_trade(self, rdb):
        await _seed_tiers(rdb, outcast={"trade_refused": 1})
        await _rep(rdb, OUTCAST)
        with pytest.raises(HTTPException) as exc:
            await _personal_shop(rdb)
        assert exc.value.status_code == 409 and "Изгой" in exc.value.detail

    async def test_incomplete_tier_table_falls_back_to_the_defaults(self, rdb):
        await rdb.execute(text("INSERT INTO reputation_tiers (code, sort_order, name, min_value, price_pct, "
                               "sell_pct, trade_refused) VALUES ('trusted', 6, 'Сломано', 300, 40, 0, 0)"))
        await rdb.commit()
        await _rep(rdb, TRUSTED)
        (row,) = await _personal_shop(rdb)
        assert row.discounted_buy_price == 95                                   # default 5 %, not 40 %

    async def test_empty_shop_answers_an_empty_list_without_reading_reputation(self, rdb):
        await rdb.execute(text("DELETE FROM npc_shop_items"))
        await rdb.commit()
        await _rep(rdb, OUTLAW)
        assert await _personal_shop(rdb) == []


# ═══════════════════════════════════════════════════════════════════════════
# Buy
# ═══════════════════════════════════════════════════════════════════════════

class TestBuy:

    @pytest.mark.parametrize("value,charisma,total,net,reasons", [
        (WANDERER, 0, 100, 0.0, []),
        (TRUSTED, 0, 95, 5.0, [_rep_reason(5.0, "Скидка за репутацию (Свой человек)")]),
        (LEGEND, CHARISMA_40, 50, 50.0,
         [_cha_reason(40.0), _rep_reason(10.0, "Скидка за репутацию (Легенда края)")]),
        (WATCHED, 0, 110, -10.0, [_rep_reason(-10.0, "Наценка за репутацию (На заметке)")]),
        (OUTCAST, CHARISMA_10, 113, -15.0, [_cha_reason(10.0), _rep_reason(-25.0, "Наценка за репутацию (Изгой)")]),
    ])
    async def test_buy_price_reasons_and_net_percent(self, rdb, value, charisma, total, net, reasons):
        await _rep(rdb, value)
        with _Shop(item=_shop_item(NPC_REGION, price=100), charisma=charisma) as shop:
            out = await _buy(rdb, NPC_REGION)
        assert (out["total_price"], out["discount_percent"], out["price_reasons"]) == (total, net, reasons)
        assert await _balance(rdb, PLAYER) == 1000 - total
        assert shop.client.post.await_count == 1
        assert await _world_sum(rdb) == 0

    async def test_buy_metadata_records_the_tier(self, rdb):
        await _rep(rdb, WATCHED)
        with _Shop(item=_shop_item(NPC_REGION, price=100)):
            await _buy(rdb, NPC_REGION, quantity=2)
        meta = await _one(rdb, "SELECT metadata FROM econ_operations WHERE op_type = 'npc_shop_buy'")
        assert '"reputation_tier": "watched"' in meta and '"reputation_pct": -10.0' in meta
        assert '"unit_price": 110' in meta

    async def test_neutral_tier_writes_no_reputation_metadata(self, rdb):
        with _Shop(item=_shop_item(NPC_REGION, price=100)):
            await _buy(rdb, NPC_REGION)
        meta = await _one(rdb, "SELECT metadata FROM econ_operations WHERE op_type = 'npc_shop_buy'")
        assert "reputation" not in meta

    async def test_living_merchant_markup_on_the_region_price(self, rdb):
        await _make_living(rdb)                                                 # ask 150
        await _rep(rdb, WATCHED)
        with _Shop(item=_shop_item(NPC_REGION, price=100, stock=3)):
            out = await _buy(rdb, NPC_REGION)
        assert out["total_price"] == 165
        assert await _balance(rdb, PLAYER) == 835
        assert await _world_sum(rdb) == 0

    async def test_outlaw_cannot_buy_and_nothing_moves(self, rdb):
        await _rep(rdb, OUTLAW)
        with _Shop(item=_shop_item(NPC_REGION, price=100, stock=3)) as shop:
            with pytest.raises(HTTPException) as exc:
                await _buy(rdb, NPC_REGION)
        assert (exc.value.status_code, exc.value.detail) == (409, REFUSED)
        shop.client.post.assert_not_awaited()
        assert await _balance(rdb, PLAYER) == 1000
        assert await _stock(rdb) == 3
        assert await _ops(rdb, "npc_shop_buy") == 0
        assert await _world_sum(rdb) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Sell (A1: low tiers lower the merchant's bid)
# ═══════════════════════════════════════════════════════════════════════════

BID_CUT_W = _rep_reason(-10.0, "Скупка дешевле из-за репутации (На заметке)")
BID_CUT_O = _rep_reason(-25.0, "Скупка дешевле из-за репутации (Изгой)")


class TestSell:

    @pytest.mark.parametrize("value,unit,reasons", [
        (WANDERER, 40, []),
        (WATCHED, 36, [BID_CUT_W]),                  # floor(40 * 0.9)
        (OUTCAST, 30, [BID_CUT_O]),                  # floor(40 * 0.75)
        (TRUSTED, 40, []),                           # high tiers never raise the bid
        (DEFENDER, 40, []),
        (LEGEND, 40, []),
    ])
    async def test_sale_bid_by_tier(self, rdb, value, unit, reasons):
        await _rep(rdb, value)
        with _Shop(sell_price=40) as shop:
            out = await _sell(rdb, NPC_REGION, quantity=2)
        assert (out["total_price"], out["price_reasons"]) == (unit * 2, reasons)
        assert await _balance(rdb, PLAYER) == 1000 + unit * 2
        assert shop.client.delete.await_count == 1
        assert await _world_sum(rdb) == 0

    async def test_sale_metadata_keeps_the_base_bid(self, rdb):
        await _rep(rdb, OUTCAST)
        with _Shop(sell_price=40):
            await _sell(rdb, NPC_REGION)
        meta = await _one(rdb, "SELECT metadata FROM econ_operations WHERE op_type = 'npc_shop_sell'")
        assert '"sell_price": 30' in meta and '"base_sell_price": 40' in meta
        assert '"reputation_tier": "outcast"' in meta and '"reputation_sell_pct": -25.0' in meta

    @pytest.mark.parametrize("value", [WATCHED, OUTCAST])
    async def test_bid_cut_to_zero_means_the_merchant_does_not_buy(self, rdb, value):
        await _rep(rdb, value)
        with _Shop(sell_price=1) as shop:
            with pytest.raises(HTTPException) as exc:
                await _sell(rdb, NPC_REGION)
        assert exc.value.status_code == 400 and exc.value.detail == "Этот NPC не покупает данный предмет"
        shop.client.delete.assert_not_awaited()                                 # the item stays in the bag
        assert await _balance(rdb, PLAYER) == 1000
        assert await _ops(rdb, "npc_shop_sell") == 0

    async def test_living_merchant_pays_the_cut_bid_from_his_cash(self, rdb):
        await _make_living(rdb)
        await _fund(rdb, NPC_REGION, 1000)
        await _rep(rdb, WATCHED)
        with _Shop(sell_price=40):
            out = await _sell(rdb, NPC_REGION)                                 # bid 60 -> 54
        assert out["total_price"] == 54
        assert await _balance(rdb, NPC_REGION) == 1000 - 54
        assert await _world_sum(rdb) == 0

    async def test_admin_edited_sell_pct_is_used_and_positive_values_never_raise(self, rdb):
        await _seed_tiers(rdb, watched={"sell_pct": "-50"}, legend={"sell_pct": "30"})
        await _rep(rdb, WATCHED)
        await _rep(rdb, LEGEND, cid=OTHER)
        with _Shop(sell_price=40):
            out = await _sell(rdb, NPC_REGION)
        assert out["total_price"] == 20
        with _Shop(sell_price=40):
            out = await _sell(rdb, NPC_REGION, character_id=OTHER, uid=12)
        assert (out["total_price"], out["price_reasons"]) == (40, [])

    async def test_outlaw_cannot_sell_and_keeps_the_item(self, rdb):
        await _rep(rdb, OUTLAW)
        with _Shop(sell_price=40) as shop:
            with pytest.raises(HTTPException) as exc:
                await _sell(rdb, NPC_REGION)
        assert (exc.value.status_code, exc.value.detail) == (409, REFUSED)
        shop.client.delete.assert_not_awaited()
        assert await _balance(rdb, PLAYER) == 1000
        assert await _world_sum(rdb) == 0


class TestQuoteBids:

    async def _market(self, s):
        return await crud.merchant_market(s, NPC_REGION)

    async def test_default_sell_pct_is_the_old_behaviour(self, rdb):
        quotes = await crud.quote_bids(rdb, await self._market(rdb), [ITEM])
        assert quotes[ITEM].unit_price == 40 and quotes[ITEM].base_unit_price is None

    async def test_cut_bid_keeps_the_base(self, rdb):
        quotes = await crud.quote_bids(rdb, await self._market(rdb), [ITEM], rc.DEFAULT_TIERS[1].sell_pct)
        assert (quotes[ITEM].unit_price, quotes[ITEM].base_unit_price) == (30, 40)

    @pytest.mark.parametrize("pct", [10, 50, "abc", None])
    async def test_positive_or_garbage_pct_never_raises_the_bid(self, rdb, pct):
        quotes = await crud.quote_bids(rdb, await self._market(rdb), [ITEM], pct)
        assert quotes[ITEM].unit_price == 40 and quotes[ITEM].base_unit_price is None

    async def test_full_cut_drops_the_item(self, rdb):
        assert await crud.quote_bids(rdb, await self._market(rdb), [ITEM], -100) == {}


# ═══════════════════════════════════════════════════════════════════════════
# Sell offers (GET /npcs/{id}/shop/sell-offers)
# ═══════════════════════════════════════════════════════════════════════════

async def _offers_route(s, *, npc=NPC_REGION, character_id=PLAYER):
    with patch.object(visibility, "require_private_access", AsyncMock(return_value=None)):
        return await main.get_npc_shop_sell_offers(npc_id=npc, character_id=character_id, session=s,
                                                   current_user=_user())


class TestSellOffers:

    @pytest.mark.parametrize("value,unit,reasons", [
        (WANDERER, 40, []),
        (WATCHED, 36, [BID_CUT_W]),
        (OUTCAST, 30, [BID_CUT_O]),
        (LEGEND, 40, []),
    ])
    async def test_offers_show_the_cut_and_the_base(self, rdb, value, unit, reasons):
        await _bag(rdb)
        await _rep(rdb, value)
        (offer,) = await _offers_route(rdb)
        assert (offer["unit_price"], offer["base_unit_price"], offer["price_reasons"]) == (unit, 40, reasons)
        assert offer["max_quantity"] == 3

    async def test_item_whose_bid_is_cut_to_zero_is_not_offered(self, rdb):
        await _set_row(rdb, sell_price=1)
        await _bag(rdb)
        await _rep(rdb, OUTCAST)
        assert await _offers_route(rdb) == []

    async def test_outlaw_gets_409_even_with_an_empty_bag(self, rdb):
        await _rep(rdb, OUTLAW)
        with pytest.raises(HTTPException) as exc:
            await _offers_route(rdb)
        assert (exc.value.status_code, exc.value.detail) == (409, REFUSED)

    async def test_dead_merchant_answers_empty_before_the_refusal(self, rdb):
        await _rep(rdb, OUTLAW)
        await rdb.execute(text("UPDATE characters SET npc_status = 'dead' WHERE id = :n"), {"n": NPC_REGION})
        await rdb.commit()
        assert await _offers_route(rdb) == []

    async def test_npc_tier_gate_is_403(self, rdb):
        await _bag(rdb)
        await _npc_tier(rdb, "trusted")
        with pytest.raises(HTTPException) as exc:
            await _offers_route(rdb)
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужна репутация: Свой человек")
        await _rep(rdb, TRUSTED)
        (offer,) = await _offers_route(rdb)
        assert offer["unit_price"] == 40

    async def test_offers_schema_carries_the_new_fields(self, rdb):
        await _bag(rdb)
        await _rep(rdb, WATCHED)
        import schemas
        (offer,) = await _offers_route(rdb)
        parsed = schemas.ShopSellOfferRead(**offer)
        assert parsed.base_unit_price == 40 and parsed.price_reasons[0].source == "reputation"


# ═══════════════════════════════════════════════════════════════════════════
# NPC-level gate: FEAT-145 trade gate + dialogue
# ═══════════════════════════════════════════════════════════════════════════

class TestNpcGate:

    async def test_trade_gate_refuses_below_the_npc_tier(self, rdb):
        await _npc_tier(rdb, "defender")
        await _rep(rdb, TRUSTED)
        with patch.object(crud, "check_action_gate", AsyncMock(return_value=True)):
            with pytest.raises(HTTPException) as exc:
                await main._require_npc_gate(rdb, PLAYER, NPC_REGION)
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужна репутация: Заступник")

    async def test_trade_gate_passes_at_the_tier(self, rdb):
        await _npc_tier(rdb, "defender")
        await _rep(rdb, DEFENDER)
        with patch.object(crud, "check_action_gate", AsyncMock(return_value=True)):
            assert await main._require_npc_gate(rdb, PLAYER, NPC_REGION) is None

    async def test_post_intent_gate_still_comes_first(self, rdb):
        await _npc_tier(rdb, "legend")
        with patch.object(crud, "check_action_gate", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await main._require_npc_gate(rdb, PLAYER, NPC_REGION)
        assert exc.value.detail == "Нужен пост-намерение «Диалог с НПС» с этим персонажем"

    @pytest.mark.parametrize("code", [None, "", "bogus"])
    async def test_no_or_unknown_npc_code_is_no_gate(self, rdb, code):
        await _npc_tier(rdb, code)
        await _rep(rdb, OUTCAST)
        with patch.object(crud, "check_action_gate", AsyncMock(return_value=True)):
            assert await main._require_npc_gate(rdb, PLAYER, NPC_REGION) is None

    async def test_npc_without_a_region_has_no_gate(self, rdb):
        await _npc_tier(rdb, "legend", npc=NPC_NOWHERE)
        with patch.object(crud, "check_action_gate", AsyncMock(return_value=True)):
            assert await main._require_npc_gate(rdb, PLAYER, NPC_NOWHERE) is None

    async def test_npc_gate_uses_the_npcs_region(self, rdb):
        await _npc_tier(rdb, "trusted")
        await _rep(rdb, LEGEND, region=REGION_B)
        with patch.object(crud, "check_action_gate", AsyncMock(return_value=True)):
            with pytest.raises(HTTPException) as exc:
                await main._require_npc_gate(rdb, PLAYER, NPC_REGION)
        assert exc.value.status_code == 403

    async def _dialogue(self, s, character_id=PLAYER):
        node = {"id": 1, "npc_text": "Здравствуй", "options": []}
        with patch.object(crud, "get_active_dialogue_for_npc", AsyncMock(return_value=node)), \
                patch.object(crud, "check_action_gate", AsyncMock(return_value=True)), \
                patch.object(visibility, "require_private_access", AsyncMock(return_value=None)):
            return await main.get_npc_dialogue(npc_id=NPC_REGION, character_id=character_id, session=s,
                                               current_user=_user())

    async def test_dialogue_gate(self, rdb):
        await _npc_tier(rdb, "familiar")
        with pytest.raises(HTTPException) as exc:
            await self._dialogue(rdb)
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужна репутация: Знакомое лицо")
        await _rep(rdb, FAMILIAR)
        assert (await self._dialogue(rdb))["id"] == 1

    async def test_dialogue_without_a_character_stays_public(self, rdb):
        await _npc_tier(rdb, "legend")
        assert (await self._dialogue(rdb, character_id=None))["id"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# reputation_read helpers + security
# ═══════════════════════════════════════════════════════════════════════════

class TestReadHelpers:

    def test_ask_reasons_without_a_region_shows_only_charisma(self):
        reasons, net = reputation_read.ask_reasons(econ_core.Decimal(10), reputation_read.NEUTRAL_TERMS)
        assert (reasons, net) == ([_cha_reason(10.0)], 10.0)

    def test_bid_reasons_only_for_a_cut(self):
        tier = rc.DEFAULT_TIERS[6]
        terms = reputation_read.TradeTerms(tier=tier, price_pct=tier.price_pct, sell_pct=econ_core.Decimal(0))
        assert reputation_read.bid_reasons(terms) == []
        assert reputation_read.bid_reasons(reputation_read.NEUTRAL_TERMS) == []

    async def test_trade_terms_without_a_row_is_wanderer(self, rdb):
        terms = await reputation_read.trade_terms(rdb, PLAYER, REGION_A)
        assert (terms.tier.code, terms.price_pct, terms.sell_pct, terms.refused) == ("wanderer", 0, 0, False)

    async def test_trade_terms_without_region_is_neutral(self, rdb):
        assert await reputation_read.trade_terms(rdb, PLAYER, None) is reputation_read.NEUTRAL_TERMS

    @pytest.mark.parametrize("payload", [
        "trusted' OR '1'='1", "legend; DROP TABLE character_reputation;--", "' UNION SELECT 1,2--",
    ])
    async def test_sql_like_tier_codes_are_inert(self, rdb, payload):
        await _rep(rdb, OUTCAST)
        assert await reputation_read.gate_failure(rdb, PLAYER, REGION_A, payload) is None
        await _npc_tier(rdb, payload)
        assert await reputation_read.npc_gate_failure(rdb, PLAYER, NPC_REGION) is None
        assert await _one(rdb, "SELECT COUNT(*) FROM character_reputation") == 1
        assert await _one(rdb, "SELECT reputation_min_tier FROM characters WHERE id = :n", n=NPC_REGION) == payload

    async def test_effective_value_reads_by_region(self, rdb):
        await _rep(rdb, -50, region=REGION_B)
        assert await reputation_read.effective_value(rdb, PLAYER, REGION_A) == 0
        assert await reputation_read.effective_value(rdb, PLAYER, REGION_B) == -50
        assert await reputation_read.effective_value(rdb, PLAYER, None) == 0

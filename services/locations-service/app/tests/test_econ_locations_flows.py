"""FEAT-181 Q3: locations-service money flows end to end on the REAL async ledger.

`test_econ_locations.py` covers the crud wrappers; this file drives the routes that use them:

* NPC shop: buy (charisma price, tax leg to the country, refund on an inventory failure that
  restores every account exactly), sell (region pays, world treasury when the NPC's place has
  no region), ownership 403, negative / huge quantities;
* quest reward: paid by the quest giver's region, and once only even when the status race is
  lost (the idempotency key is the second line of defence);
* houses: purchase / build / layer + cell unlock / upgrade / tax are atomic with their business
  rows (a failure after the posting rolls back both), resale is one operation and leaves both
  balances intact on a failure, regionless plots pay the world treasury, ownership + price limits;
* region / country deletion: `treasury_closed` postings in the delete transaction, rolled back
  with it.

Every money-moving scenario ends with the world invariant  Σ characters + Σ accounts = 0
(pre-existing fixture gold is backed by an emission account so the invariant starts at 0).
Only the network is mocked.
"""

import asyncio
import contextlib
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import BigInteger, event, text
from sqlalchemy.dialects.mysql import MEDIUMTEXT, TINYINT
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import econ_core  # noqa: E402
import econ_ledger  # noqa: E402
import econ_contract_cases as cc  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402

# House routes run through the FEAT-180 fixture (TestClient + file SQLite + ledger tables).
from test_houses import (  # noqa: E402,F401
    api, _plot, _house, _empty_house, _cell, _gold, _owe, _plan_body, _cells, _rooms,
    OWNER, FRIEND, STRANGER, ADMIN, TOWN, REGION,
)


@compiles(BigInteger, "sqlite")
def _bigint(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


@compiles(MEDIUMTEXT, "sqlite")
def _mediumtext(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "TEXT"


@compiles(TINYINT, "sqlite")
def _tinyint(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


COUNTRY = 1  # test_houses puts REGION (7) into country 1


# ═══════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _one(s, sql, **p):
    row = (await s.execute(text(sql), p)).first()
    return None if row is None else row[0]


async def _account(s, kind, ref_id=0):
    return await _one(s, cc.ACCOUNT_BALANCE_SQL, kind=kind, ref_id=ref_id)


async def _ops(s, op_type):
    return await _one(s, "SELECT COUNT(*) FROM econ_operations WHERE op_type = :t", t=op_type)


async def _world_sum(s):
    return await _one(s, cc.WORLD_SUM_SQL)


async def _back_existing_gold(s):
    """Fixture gold written straight into `characters` is backed by an emission account."""
    total = await _one(s, "SELECT COALESCE(SUM(currency_balance), 0) FROM characters")
    await s.execute(text("INSERT INTO econ_accounts (kind, ref_id, name, balance, allow_negative) "
                         "VALUES ('emission', 0, 'emission', :b, 1)"), {"b": -int(total)})
    await s.commit()


def _http_factory(*, post_status=200, post_exc=None, delete_status=200):
    """Stand-in for httpx.AsyncClient (async context manager)."""
    resp_post = MagicMock(status_code=post_status)
    resp_post.json = MagicMock(return_value={"detail": "Инвентарь переполнен"})
    resp_del = MagicMock(status_code=delete_status)
    resp_del.json = MagicMock(return_value={"detail": "Предмета нет"})
    client = AsyncMock()
    client.post = AsyncMock(side_effect=post_exc) if post_exc else AsyncMock(return_value=resp_post)
    client.delete = AsyncMock(return_value=resp_del)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, client


# ═══════════════════════════════════════════════════════════════════════════
# NPC shop
# ═══════════════════════════════════════════════════════════════════════════

PLAYER, OTHER, USER, OTHER_USER = 1, 2, 11, 12
NPC_REGION, NPC_NOWHERE = 50, 51          # NPCs at location 1000 (region 10) / 1003 (no region)
REGION_A, COUNTRY_A = 10, 1


@pytest_asyncio.fixture()
async def shop_db(tmp_path):
    econ_core.invalidate_settings_cache()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'shop.db'}", poolclass=NullPool)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        await s.execute(text(
            "CREATE TABLE characters (id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '', user_id INTEGER, "
            "currency_balance BIGINT NOT NULL DEFAULT 0, current_location_id INTEGER, "
            "is_npc INTEGER NOT NULL DEFAULT 0)"))
        for ddl in cc.SQLITE_DDL:
            await s.execute(text(ddl))
        for sql, params in cc.SEED_SQL:
            if "INTO characters" not in sql:
                await s.execute(text(sql), params)
        await s.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"))
        await s.execute(text("INSERT INTO items VALUES (7, 'Зелье')"))
        rows = [(PLAYER, USER, 1000, 1000, 0), (OTHER, OTHER_USER, 1000, 1000, 0),
                (NPC_REGION, None, 0, 1000, 1), (NPC_NOWHERE, None, 0, 1003, 1)]
        for cid, uid, gold, loc, npc in rows:
            await s.execute(text("INSERT INTO characters (id, user_id, currency_balance, current_location_id, "
                                 "is_npc) VALUES (:i, :u, :g, :l, :n)"),
                            {"i": cid, "u": uid, "g": gold, "l": loc, "n": npc})
        await s.commit()
        await _back_existing_gold(s)
    async with Session() as s:
        yield s
    await engine.dispose()
    econ_core.invalidate_settings_cache()


def _shop_item(npc_id, price=100, stock=None):
    return SimpleNamespace(id=900, npc_id=npc_id, item_id=7, is_active=True, buy_price=price, stock=stock)


class _Shop:
    """Patches the shop route's outbound calls and lookups that need other services' tables."""

    def __init__(self, *, item=None, charisma=0, sell_price=40, **http):
        self.factory, self.client = _http_factory(**http)
        self.decrement = AsyncMock(return_value=True)
        self._p = [
            patch.object(main.httpx, "AsyncClient", self.factory),
            patch.object(main, "_require_npc_gate", AsyncMock(return_value=None)),
            patch.object(main, "check_not_activity_locked", AsyncMock(return_value=None)),
            patch.object(main, "_fetch_charisma", AsyncMock(return_value=charisma)),
            patch.object(main, "_track_cumulative_stats", AsyncMock(return_value=None)),
            patch.object(crud, "get_shop_item_by_id", AsyncMock(return_value=item)),
            patch.object(crud, "decrement_stock", self.decrement),
            patch.object(crud, "find_sell_price_for_item", AsyncMock(return_value=sell_price)),
        ]

    def __enter__(self):
        for p in self._p:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._p):
            p.stop()


def _user(uid=USER):
    return SimpleNamespace(id=uid)


async def _buy(s, npc_id, *, character_id=PLAYER, quantity=1, uid=USER):
    body = schemas.ShopBuyRequest(character_id=character_id, shop_item_id=900, quantity=quantity)
    return await main.buy_from_npc(npc_id=npc_id, body=body, request=MagicMock(), session=s,
                                   current_user=_user(uid))


async def _sell(s, npc_id, *, character_id=PLAYER, quantity=1, uid=USER):
    request = MagicMock()
    request.headers = {"authorization": "Bearer t"}
    body = schemas.ShopSellRequest(character_id=character_id, item_id=7, quantity=quantity)
    return await main.sell_to_npc(npc_id=npc_id, body=body, request=request, session=s,
                                  current_user=_user(uid))


async def _balance(s, cid):
    return await _one(s, cc.CHARACTER_BALANCE_SQL, id=cid)


class TestNpcBuy:

    async def test_buy_with_charisma_pays_the_region_and_taxes_the_country(self, shop_db):
        # charisma 50 -> 10 % off; ceil(155 * 0.9) = 140 per unit, 2 units = 280
        with _Shop(item=_shop_item(NPC_REGION, price=155), charisma=50) as shop:
            out = await _buy(shop_db, NPC_REGION, quantity=2)
        assert (out["total_price"], out["discount_percent"], out["new_balance"]) == (280, 10.0, 720)
        assert await _balance(shop_db, PLAYER) == 720
        assert await _account(shop_db, "region_treasury", REGION_A) == 252
        assert await _account(shop_db, "country_treasury", COUNTRY_A) == 28
        meta = await _one(shop_db, "SELECT metadata FROM econ_operations WHERE op_type = 'npc_shop_buy'")
        assert '"unit_price": 140' in meta and '"quantity": 2' in meta
        assert shop.client.post.await_count == 1
        assert await _world_sum(shop_db) == 0

    async def test_inventory_refusal_refunds_every_leg(self, shop_db):
        with _Shop(item=_shop_item(NPC_REGION, price=200, stock=5), post_status=400) as shop:
            with pytest.raises(HTTPException) as exc:
                await _buy(shop_db, NPC_REGION)
        assert exc.value.status_code == 500 and exc.value.detail == "Инвентарь переполнен"
        assert await _balance(shop_db, PLAYER) == 1000
        assert await _account(shop_db, "region_treasury", REGION_A) == 0
        assert await _account(shop_db, "country_treasury", COUNTRY_A) == 0
        assert (await _ops(shop_db, "npc_shop_buy"), await _ops(shop_db, "npc_shop_buy_refund")) == (1, 1)
        shop.decrement.assert_not_awaited()       # stock untouched on a failed purchase
        assert await _world_sum(shop_db) == 0

    async def test_inventory_unreachable_refunds_and_answers_503(self, shop_db):
        import httpx
        with _Shop(item=_shop_item(NPC_REGION, price=200), post_exc=httpx.ConnectError("down")):
            with pytest.raises(HTTPException) as exc:
                await _buy(shop_db, NPC_REGION)
        assert exc.value.status_code == 503
        assert await _balance(shop_db, PLAYER) == 1000
        assert await _account(shop_db, "region_treasury", REGION_A) == 0
        refund = await _one(shop_db, "SELECT metadata FROM econ_operations WHERE op_type = 'npc_shop_buy_refund'")
        assert "inventory service unavailable" in refund and "reverses_operation_id" in refund
        assert await _world_sum(shop_db) == 0

    async def test_not_enough_gold_moves_nothing_and_skips_inventory(self, shop_db):
        with _Shop(item=_shop_item(NPC_REGION, price=600)) as shop:
            with pytest.raises(HTTPException) as exc:
                await _buy(shop_db, NPC_REGION, quantity=2)
        assert exc.value.status_code == 400 and exc.value.detail == "Недостаточно марок"
        shop.client.post.assert_not_awaited()
        assert await _balance(shop_db, PLAYER) == 1000
        assert await _ops(shop_db, "npc_shop_buy") == 0
        assert await _world_sum(shop_db) == 0

    async def test_npc_without_region_is_paid_through_the_world_treasury(self, shop_db):
        await shop_db.execute(text("UPDATE characters SET current_location_id = 1003 WHERE id = :c"), {"c": PLAYER})
        await shop_db.commit()
        with _Shop(item=_shop_item(NPC_NOWHERE, price=100)):
            await _buy(shop_db, NPC_NOWHERE)
        assert await _account(shop_db, "world_treasury") == 100
        assert await _one(shop_db, "SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'") == 0
        assert await _world_sum(shop_db) == 0

    async def test_someone_elses_character_is_403(self, shop_db):
        with _Shop(item=_shop_item(NPC_REGION)) as shop:
            with pytest.raises(HTTPException) as exc:
                await _buy(shop_db, NPC_REGION, character_id=OTHER, uid=USER)
        assert exc.value.status_code == 403
        shop.client.post.assert_not_awaited()
        assert await _balance(shop_db, OTHER) == 1000
        assert await _one(shop_db, "SELECT COUNT(*) FROM econ_operations") == 0

    @pytest.mark.parametrize("quantity", [0, -1, -10**6])
    async def test_non_positive_quantity_is_refused(self, shop_db, quantity):
        with _Shop(item=_shop_item(NPC_REGION)):
            with pytest.raises(HTTPException) as exc:
                await _buy(shop_db, NPC_REGION, quantity=quantity)
        assert exc.value.status_code == 400
        assert await _balance(shop_db, PLAYER) == 1000
        assert await _one(shop_db, "SELECT COUNT(*) FROM econ_operations") == 0

    async def test_huge_quantity_is_refused_without_moving_gold(self, shop_db):
        with _Shop(item=_shop_item(NPC_REGION, price=10**9)) as shop:
            with pytest.raises(HTTPException) as exc:
                await _buy(shop_db, NPC_REGION, quantity=10**6)
        assert exc.value.status_code == 400
        shop.client.post.assert_not_awaited()
        assert await _balance(shop_db, PLAYER) == 1000
        assert await _world_sum(shop_db) == 0

    async def test_limited_stock_smaller_than_quantity_is_refused(self, shop_db):
        with _Shop(item=_shop_item(NPC_REGION, stock=1)):
            with pytest.raises(HTTPException) as exc:
                await _buy(shop_db, NPC_REGION, quantity=2)
        assert exc.value.status_code == 400
        assert await _balance(shop_db, PLAYER) == 1000


class TestNpcSell:

    async def test_sell_is_paid_by_the_npc_region(self, shop_db):
        with _Shop(sell_price=40) as shop:
            out = await _sell(shop_db, NPC_REGION, quantity=3)
        assert (out["total_price"], out["new_balance"]) == (120, 1120)
        assert await _account(shop_db, "region_treasury", REGION_A) == -120
        assert await _one(shop_db, "SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'") == 0
        assert shop.client.delete.await_count == 1
        assert await _world_sum(shop_db) == 0

    async def test_sell_at_a_place_without_region_uses_the_world_treasury(self, shop_db):
        await shop_db.execute(text("UPDATE characters SET current_location_id = 1003 WHERE id = :c"), {"c": PLAYER})
        await shop_db.commit()
        with _Shop(sell_price=25):
            await _sell(shop_db, NPC_NOWHERE)
        assert await _account(shop_db, "world_treasury") == -25
        assert await _world_sum(shop_db) == 0

    async def test_inventory_refusal_pays_nothing(self, shop_db):
        with _Shop(delete_status=404):
            with pytest.raises(HTTPException) as exc:
                await _sell(shop_db, NPC_REGION)
        assert exc.value.status_code == 404
        assert await _balance(shop_db, PLAYER) == 1000
        assert await _one(shop_db, "SELECT COUNT(*) FROM econ_operations") == 0

    async def test_someone_elses_character_is_403(self, shop_db):
        with _Shop() as shop:
            with pytest.raises(HTTPException) as exc:
                await _sell(shop_db, NPC_REGION, character_id=OTHER, uid=USER)
        assert exc.value.status_code == 403
        shop.client.delete.assert_not_awaited()
        assert await _balance(shop_db, OTHER) == 1000

    @pytest.mark.parametrize("quantity", [0, -5])
    async def test_non_positive_quantity_is_refused(self, shop_db, quantity):
        with _Shop() as shop:
            with pytest.raises(HTTPException) as exc:
                await _sell(shop_db, NPC_REGION, quantity=quantity)
        assert exc.value.status_code == 400
        shop.client.delete.assert_not_awaited()
        assert await _balance(shop_db, PLAYER) == 1000


# ═══════════════════════════════════════════════════════════════════════════
# Quest reward
# ═══════════════════════════════════════════════════════════════════════════

Q_CHAR, Q_USER, Q_ID, Q_NPC = 100, 5, 42, 9


@pytest_asyncio.fixture()
async def quest_db(tmp_path):
    econ_core.invalidate_settings_cache()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'quest.db'}", poolclass=NullPool)

    @event.listens_for(engine.sync_engine, "connect")
    def _now(dbapi_conn, _record):  # pragma: no cover - DDL hook
        dbapi_conn.create_function("NOW", 0, lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

    async with engine.begin() as conn:
        for m in (models.Quest, models.QuestObjective, models.CharacterQuest, models.CharacterQuestProgress):
            await conn.run_sync(m.__table__.create)
        await conn.execute(text(
            "CREATE TABLE characters (id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '', user_id INTEGER, "
            "currency_balance BIGINT NOT NULL DEFAULT 0, current_location_id INTEGER, "
            "is_npc INTEGER NOT NULL DEFAULT 0)"))
        await conn.execute(text("CREATE TABLE character_attributes (character_id INTEGER PRIMARY KEY, "
                                "passive_experience INTEGER NOT NULL DEFAULT 0, "
                                "active_experience INTEGER NOT NULL DEFAULT 0)"))
        for ddl in cc.SQLITE_DDL:
            await conn.execute(text(ddl))
        for sql, params in cc.SEED_SQL:
            if "INTO characters" not in sql:
                await conn.execute(text(sql), params)
        await conn.execute(text("INSERT INTO characters (id, user_id, currency_balance, current_location_id) "
                                "VALUES (:c, :u, 250, 1000)"), {"c": Q_CHAR, "u": Q_USER})
        await conn.execute(text("INSERT INTO characters (id, current_location_id, is_npc) VALUES (:n, 1001, 1)"),
                           {"n": Q_NPC})
        await conn.execute(text("INSERT INTO character_attributes VALUES (:c, 1000, 0)"), {"c": Q_CHAR})

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        await _back_existing_gold(s)
        s.add_all([
            models.Quest(id=Q_ID, npc_id=Q_NPC, title="Гонец", description="", quest_type="standard", min_level=1,
                         reward_currency=60, reward_exp=10, reward_items=None, is_active=True),
            models.QuestObjective(id=1, quest_id=Q_ID, description="Поговорить", objective_type="talk_npc",
                                  target_id=Q_NPC, target_count=1, sort_order=0),
            models.CharacterQuest(id=1, character_id=Q_CHAR, quest_id=Q_ID, status="active"),
            models.CharacterQuestProgress(id=1, character_quest_id=1, objective_id=1, current_count=1,
                                          is_completed=True),
        ])
        await s.commit()
        yield s
    await engine.dispose()
    econ_core.invalidate_settings_cache()


@contextlib.contextmanager
def _quest_patches():
    # Patched once per test: patch.object stacks entered from concurrent coroutines unwind
    # out of order and leave the module attributes mocked for the rest of the session.
    factory, _client = _http_factory()
    with patch.object(crud.httpx, "AsyncClient", factory), patch.object(main.httpx, "AsyncClient", factory), \
            patch.object(main, "check_not_activity_locked", AsyncMock(return_value=None)), \
            patch.object(main, "_track_cumulative_stats", AsyncMock(return_value=None)), \
            patch.object(crud, "get_character_xp_multiplier", AsyncMock(return_value=None)):
        yield


async def _call_complete_quest(s, uid=Q_USER):
    return await main.complete_quest(quest_id=Q_ID, body=schemas.QuestCompleteRequest(character_id=Q_CHAR),
                                     request=MagicMock(), session=s, current_user=_user(uid))


async def _complete_quest(s, uid=Q_USER):
    with _quest_patches():
        return await _call_complete_quest(s, uid)


async def _xp(s):
    return await _one(s, "SELECT passive_experience FROM character_attributes WHERE character_id = :c", c=Q_CHAR)


class TestQuestReward:

    async def test_reward_comes_from_the_quest_givers_region_with_tax(self, quest_db):
        out = await _complete_quest(quest_db)
        assert out["new_balance"] == 310
        # quest giver stands in location 1001 (region 20); the player is in 1000 (region 10)
        assert await _account(quest_db, "region_treasury", 20) == -60
        assert await _account(quest_db, "region_treasury", 10) is None
        assert await _one(quest_db, "SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'") == 0
        assert await _world_sum(quest_db) == 0

    async def test_lost_status_race_is_caught_by_the_key_and_pays_nothing_twice(self, quest_db):
        """Both requests see the quest active (as if read concurrently): the second one gets past
        the conditional completion, but the idempotency key refuses the payment and its XP."""
        await _complete_quest(quest_db)
        with patch.object(crud, "check_quest_completable",
                          AsyncMock(return_value={"all_completed": True, "character_quest_id": 1})), \
                patch.object(crud, "complete_quest_record", AsyncMock(return_value=True)):
            with pytest.raises(HTTPException) as exc:
                await _complete_quest(quest_db)
        assert exc.value.status_code == 409
        assert await _balance(quest_db, Q_CHAR) == 310
        assert await _xp(quest_db) == 1010
        assert await _ops(quest_db, "quest_reward") == 1
        assert await _world_sum(quest_db) == 0

    async def test_two_concurrent_completions_on_separate_connections_pay_once(self, quest_db):
        """Two completions started together, each on its own connection: exactly one is paid
        (the loser is refused by the conditional completion or by the database lock)."""
        a = AsyncSession(bind=quest_db.bind, expire_on_commit=False)
        b = AsyncSession(bind=quest_db.bind, expire_on_commit=False)
        try:
            with _quest_patches():
                results = await asyncio.gather(_call_complete_quest(a), _call_complete_quest(b),
                                               return_exceptions=True)
        finally:
            await a.close()
            await b.close()
        paid = [r for r in results if isinstance(r, dict)]
        assert len(paid) == 1, results
        assert await _balance(quest_db, Q_CHAR) == 310
        assert await _xp(quest_db) == 1010
        assert await _ops(quest_db, "quest_reward") == 1
        assert await _world_sum(quest_db) == 0

    async def test_someone_elses_character_is_403(self, quest_db):
        with pytest.raises(HTTPException) as exc:
            await _complete_quest(quest_db, uid=Q_USER + 1)
        assert exc.value.status_code == 403
        assert await _balance(quest_db, Q_CHAR) == 250
        assert await _one(quest_db, "SELECT status FROM character_quests WHERE id = 1") == "active"

    async def test_quest_giver_without_a_place_falls_back_to_the_player_region(self, quest_db):
        await quest_db.execute(text("UPDATE characters SET current_location_id = NULL WHERE id = :n"), {"n": Q_NPC})
        await quest_db.commit()
        await _complete_quest(quest_db)
        assert await _account(quest_db, "region_treasury", 10) == -60
        assert await _world_sum(quest_db) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Houses (routes through the FEAT-180 TestClient fixture)
# ═══════════════════════════════════════════════════════════════════════════

def _acc(api, kind, ref_id=0):
    rows = api.sql(cc.ACCOUNT_BALANCE_SQL, kind=kind, ref_id=ref_id)
    return rows[0][0] if rows else None


def _ops_sync(api, op_type):
    return api.sql("SELECT COUNT(*) FROM econ_operations WHERE op_type = :t", t=op_type)[0][0]


def _world(api):
    return api.sql(cc.WORLD_SUM_SQL)[0][0]


@pytest.fixture()
def homes(api):
    """test_houses' api with its fixture gold backed by an emission account (world sum 0)."""
    total = api.sql("SELECT SUM(currency_balance) FROM characters")[0][0]
    api.sql("INSERT INTO econ_accounts (kind, ref_id, name, balance, allow_negative) "
            "VALUES ('emission', 0, 'emission', :b, 1)", b=-int(total))
    econ_core.invalidate_settings_cache()
    yield api
    econ_core.invalidate_settings_cache()


def _set_gold(api, cid, gold):
    """Moves gold between the character and the emission account (keeps the world sum at 0)."""
    old = _gold(api, cid)
    api.sql("UPDATE characters SET currency_balance = :g WHERE id = :c", g=gold, c=cid)
    api.sql("UPDATE econ_accounts SET balance = balance - :d WHERE kind = 'emission'", d=gold - old)


class _FailAfterPosting:
    """The posting succeeds, then the request blows up before its commit."""

    def __init__(self, monkeypatch):
        real = econ_ledger.post_operation
        self.calls = 0

        async def _post(*args, **kwargs):
            await real(*args, **kwargs)
            self.calls += 1
            raise RuntimeError("crash between the posting and the commit")

        monkeypatch.setattr(econ_ledger, "post_operation", _post)


def _crash(fn):
    with pytest.raises(RuntimeError, match="crash between"):
        fn()


class TestHousePayments:

    def test_purchase_pays_the_plot_region_and_taxes_its_country(self, homes):
        hid, _ = _house(homes)
        assert _gold(homes, 10) == 700
        assert (_acc(homes, "region_treasury", REGION), _acc(homes, "country_treasury", COUNTRY)) == (270, 30)
        meta = homes.sql("SELECT metadata, region_id FROM econ_operations WHERE op_type = 'house_purchase'")
        assert len(meta) == 1 and f'"house_id": {hid}' in meta[0][0] and meta[0][1] == REGION
        assert _world(homes) == 0

    def test_purchase_crash_before_commit_keeps_gold_and_the_plot_free(self, homes, monkeypatch):
        pid = _plot(homes)
        _FailAfterPosting(monkeypatch)
        _crash(lambda: homes.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}))
        assert _gold(homes, 10) == 1000
        assert homes.sql("SELECT COUNT(*) FROM houses")[0][0] == 0
        assert homes.sql("SELECT COUNT(*) FROM house_rooms")[0][0] == 0
        assert homes.sql("SELECT COUNT(*) FROM econ_operations")[0][0] == 0
        assert _world(homes) == 0

    def test_purchase_without_gold_leaves_no_house_and_no_operation(self, homes):
        pid = _plot(homes, price=300)
        assert homes.as_(FRIEND).post(f"/plots/{pid}/buy", {"character_id": 20}).status_code == 400
        assert homes.sql("SELECT COUNT(*) FROM houses")[0][0] == 0
        assert _ops_sync(homes, "house_purchase") == 0
        assert _world(homes) == 0

    def test_plot_without_region_pays_the_world_treasury(self, homes):
        homes.sql("INSERT INTO Locations (id, name, district_id, type, recommended_level, quick_travel_marker, "
                  "description, marker_type, sort_order, no_quick_move, is_starting) "
                  "VALUES (300, 'Пустошь', NULL, 'location', 1, 0, '', 'safe', 0, 0, 0)")
        pid = _plot(homes, location_id=300)
        assert homes.sql("SELECT region_id FROM house_plots WHERE id = :p", p=pid)[0][0] is None
        homes.sql("UPDATE characters SET current_location_id = 300 WHERE id = 10")
        assert homes.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).status_code == 200
        assert _acc(homes, "world_treasury") == 300
        assert homes.sql("SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'")[0][0] == 0
        assert _world(homes) == 0

    def test_build_crash_keeps_gold_materials_and_the_cell(self, homes, monkeypatch):
        hid = _empty_house(homes, cells=2)
        cost_id = homes.sql("SELECT id FROM house_build_costs WHERE room_type = 'hall' AND level = 1")[0][0]
        homes.sql("INSERT INTO house_build_cost_items (cost_id, item_id, quantity) VALUES (:c, 1, 2)", c=cost_id)
        homes.sql("INSERT INTO character_inventory (character_id, item_id, quantity) VALUES (10, 1, 5)")
        gold, cell = _gold(homes, 10), _cell(homes, hid)
        _FailAfterPosting(monkeypatch)
        _crash(lambda: homes.as_(OWNER).post(f"/{hid}/rooms", {**cell, "character_id": 10, "room_type": "hall",
                                                                "name": "Зал"}))
        assert _gold(homes, 10) == gold
        assert homes.sql("SELECT SUM(quantity) FROM character_inventory WHERE character_id = 10")[0][0] == 5
        assert homes.sql("SELECT COUNT(*) FROM house_rooms WHERE house_id = :h", h=hid)[0][0] == 0
        assert _ops_sync(homes, "house_build") == 0
        assert _world(homes) == 0

    def test_build_pays_the_region_with_tax(self, homes):
        hid = _empty_house(homes, cells=2)
        region, country = _acc(homes, "region_treasury", REGION), _acc(homes, "country_treasury", COUNTRY)
        r = homes.as_(OWNER).post(f"/{hid}/rooms", {**_cell(homes, hid), "character_id": 10, "room_type": "hall",
                                                     "name": "Зал"})
        assert r.status_code == 200, r.text
        assert _acc(homes, "region_treasury", REGION) - region == 90
        assert _acc(homes, "country_treasury", COUNTRY) - country == 10
        assert _ops_sync(homes, "house_build") == 1
        assert _world(homes) == 0

    def test_upgrade_crash_keeps_the_room_level(self, homes, monkeypatch):
        hid, rooms = _house(homes)
        gold = _gold(homes, 10)
        _FailAfterPosting(monkeypatch)
        _crash(lambda: homes.as_(OWNER).post(f"/{hid}/rooms/{rooms['bedroom']}/upgrade", {"character_id": 10}))
        row = homes.sql("SELECT level, upgrade_to_level FROM house_rooms WHERE id = :r", r=rooms["bedroom"])[0]
        assert tuple(row) == (1, None)
        assert _gold(homes, 10) == gold
        assert _world(homes) == 0

    def test_layer_and_cell_unlock_crash_buy_nothing(self, homes, monkeypatch):
        pid = homes.as_(ADMIN).post("/admin/plots", _plan_body()).json()["id"]
        hid = homes.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).json()["house_id"]
        cells, gold = _cells(homes, hid), _gold(homes, 10)
        _FailAfterPosting(monkeypatch)
        _crash(lambda: homes.as_(OWNER).post(f"/{hid}/layers/floor2/unlock", {"character_id": 10}))
        _crash(lambda: homes.post(f"/{hid}/cells/{cells[('floor1', 2, 0)]['id']}/unlock", {"character_id": 10}))
        assert homes.sql("SELECT COUNT(*) FROM house_layer_unlocks")[0][0] == 0
        assert homes.sql("SELECT COUNT(*) FROM house_cell_unlocks")[0][0] == 0
        assert _gold(homes, 10) == gold
        assert _ops_sync(homes, "house_build") == 0
        assert _world(homes) == 0

    def test_unlocks_post_house_build_operations(self, homes):
        pid = homes.as_(ADMIN).post("/admin/plots", _plan_body()).json()["id"]
        hid = homes.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).json()["house_id"]
        cells = _cells(homes, hid)
        assert homes.as_(OWNER).post(f"/{hid}/cells/{cells[('floor1', 2, 0)]['id']}/unlock",
                                     {"character_id": 10}).status_code == 200
        assert homes.post(f"/{hid}/layers/floor2/unlock", {"character_id": 10}).status_code == 200
        assert _ops_sync(homes, "house_build") == 2
        assert _world(homes) == 0

    def test_tax_goes_to_the_region_and_the_country(self, homes):
        hid, _ = _house(homes)
        _owe(homes, hid, 1)
        region = _acc(homes, "region_treasury", REGION)
        assert homes.as_(OWNER).post(f"/{hid}/tax", {"character_id": 10}).status_code == 200
        assert _acc(homes, "region_treasury", REGION) - region == 165 - 16   # floor(165 * 0.1) = 16 to the country
        assert _ops_sync(homes, "house_tax") == 1
        assert _world(homes) == 0

    def test_tax_crash_leaves_the_debt_and_the_gold(self, homes, monkeypatch):
        hid, _ = _house(homes)
        _owe(homes, hid, 2)
        through = homes.sql("SELECT tax_paid_through FROM houses WHERE id = :h", h=hid)[0][0]
        gold = _gold(homes, 10)
        _FailAfterPosting(monkeypatch)
        _crash(lambda: homes.as_(OWNER).post(f"/{hid}/tax", {"character_id": 10}))
        assert homes.sql("SELECT tax_paid_through FROM houses WHERE id = :h", h=hid)[0][0] == through
        assert _gold(homes, 10) == gold
        assert _world(homes) == 0

    def test_someone_elses_character_cannot_pay_or_build(self, homes):
        hid, rooms = _house(homes)
        _owe(homes, hid, 1)
        gold = _gold(homes, 10)
        # STRANGER's user names the OWNER's character
        assert homes.as_(STRANGER).post(f"/{hid}/tax", {"character_id": 10}).status_code == 403
        assert homes.as_(STRANGER).post(f"/{hid}/rooms/{rooms['bedroom']}/upgrade",
                                        {"character_id": 10}).status_code == 403
        assert _gold(homes, 10) == gold
        assert _ops_sync(homes, "house_tax") == 0


class TestHouseResale:

    def _listed(self, homes, price=400):
        hid, _ = _house(homes)
        assert homes.as_(OWNER).put(f"/{hid}/sale", {"character_id": 10, "price": price}).status_code == 200
        return hid

    def test_resale_is_one_operation_without_tax(self, homes):
        hid = self._listed(homes)
        seller, buyer = _gold(homes, 10), _gold(homes, 30)
        assert homes.as_(STRANGER).post(f"/{hid}/buy", {"character_id": 30}).status_code == 200
        assert (_gold(homes, 10), _gold(homes, 30)) == (seller + 400, buyer - 400)
        ops = homes.sql("SELECT id, location_id FROM econ_operations WHERE op_type = 'house_resale'")
        assert len(ops) == 1 and ops[0][1] == TOWN
        legs = homes.sql("SELECT leg_type, amount FROM econ_postings WHERE operation_id = :o", o=ops[0][0])
        assert [tuple(r) for r in legs] == [("main", 400)]
        assert _world(homes) == 0

    def test_buyer_short_of_gold_changes_nothing(self, homes):
        hid = self._listed(homes, price=900)
        _set_gold(homes, 30, 899)
        seller = _gold(homes, 10)
        r = homes.as_(STRANGER).post(f"/{hid}/buy", {"character_id": 30})
        assert r.status_code == 400 and r.json()["detail"] == "Не хватает марок"
        assert homes.sql("SELECT owner_character_id, sale_price FROM houses WHERE id = :h", h=hid)[0] == (10, 900)
        assert (_gold(homes, 10), _gold(homes, 30)) == (seller, 899)
        assert _ops_sync(homes, "house_resale") == 0
        assert _world(homes) == 0

    def test_crash_before_commit_leaves_both_balances_and_the_owner(self, homes, monkeypatch):
        hid = self._listed(homes)
        homes.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
        seller, buyer = _gold(homes, 10), _gold(homes, 30)
        _FailAfterPosting(monkeypatch)
        _crash(lambda: homes.as_(STRANGER).post(f"/{hid}/buy", {"character_id": 30}))
        assert homes.sql("SELECT owner_character_id FROM houses WHERE id = :h", h=hid)[0][0] == 10
        assert homes.sql("SELECT COUNT(*) FROM house_residents WHERE house_id = :h", h=hid)[0][0] == 1
        assert (_gold(homes, 10), _gold(homes, 30)) == (seller, buyer)
        assert _ops_sync(homes, "house_resale") == 0
        assert _world(homes) == 0

    def test_buying_with_someone_elses_character_is_403(self, homes):
        hid = self._listed(homes)
        buyer = _gold(homes, 30)
        assert homes.as_(FRIEND).post(f"/{hid}/buy", {"character_id": 30}).status_code == 403
        assert _gold(homes, 30) == buyer
        assert homes.sql("SELECT owner_character_id FROM houses WHERE id = :h", h=hid)[0][0] == 10

    def test_a_sold_house_is_not_sold_twice(self, homes):
        hid = self._listed(homes)
        assert homes.as_(STRANGER).post(f"/{hid}/buy", {"character_id": 30}).status_code == 200
        _set_gold(homes, 20, 5000)
        assert homes.as_(FRIEND).post(f"/{hid}/buy", {"character_id": 20}).status_code == 409
        assert _gold(homes, 20) == 5000
        assert _ops_sync(homes, "house_resale") == 1
        assert _world(homes) == 0

    @pytest.mark.parametrize("price", [0, -1, 10**9 + 1, 10**18])
    def test_sale_price_limits(self, homes, price):
        hid, _ = _house(homes)
        assert homes.as_(OWNER).put(f"/{hid}/sale", {"character_id": 10, "price": price}).status_code == 422
        assert homes.sql("SELECT sale_price FROM houses WHERE id = :h", h=hid)[0][0] is None


# ═══════════════════════════════════════════════════════════════════════════
# Region / country deletion
# ═══════════════════════════════════════════════════════════════════════════

@pytest_asyncio.fixture()
async def world_db(tmp_path):
    """ORM world tables (Countries / Regions / Districts / Locations / neighbours) + the ledger.
    country 1: region 10 (district 100, location 1000), region 11 (standalone location 1100);
    country 2: region 20 (location 1001)."""
    econ_core.invalidate_settings_cache()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'world.db'}", poolclass=NullPool)
    async with engine.begin() as conn:
        for m in (models.Country, models.Region, models.District, models.Location, models.LocationNeighbor):
            await conn.run_sync(m.__table__.create)
        for ddl in cc.SQLITE_DDL:
            await conn.execute(text(ddl))
        await conn.execute(text("INSERT INTO Countries (id, name, description) VALUES (1, 'A', ''), (2, 'B', '')"))
        await conn.execute(text("INSERT INTO Regions (id, name, country_id, description) VALUES "
                                "(10, 'A1', 1, ''), (11, 'A2', 1, ''), (20, 'B1', 2, '')"))
        await conn.execute(text("INSERT INTO Districts (id, name, region_id, description, sort_order) VALUES (100, 'D', 10, '', 0)"))
        loc = ("INSERT INTO Locations (id, name, district_id, region_id, type, recommended_level, "
               "quick_travel_marker, description, marker_type, sort_order, no_quick_move, is_starting) "
               "VALUES (:i, 'L', :d, :r, 'location', 1, 0, '', 'safe', 0, 0, 0)")
        for i, d, r in ((1000, 100, None), (1100, None, 11), (1001, None, 20)):
            await conn.execute(text(loc), {"i": i, "d": d, "r": r})
        await conn.execute(text("INSERT INTO characters (id, name, currency_balance) VALUES (1, 'A', 0)"))
        await conn.execute(text("INSERT INTO econ_settings (id, currency_name, currency_genitive, currency_one, "
                                "currency_few, currency_many, currency_short, country_tax_rate) "
                                "VALUES (1, 'Золото', 'золота', 'золотой', 'золотых', 'золотых', 'зол.', 0.1)"))
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        await econ_ledger.post_operation(
            s, op_type="admin_emission", legs=[econ_core.Leg(econ_core.AccountRef.emission(),
                                                             econ_core.AccountRef.character(1), 1000)],
            source_service="test", comment="seed", apply_tax=False)
        # region 10: +450 (country 1 +50); region 11: -70; region 20: +90 (country 2 +10)
        await crud.charge_character(s, 1, 500, op_type="npc_shop_buy", location_id=1000)
        await crud.pay_character(s, 1, 70, op_type="npc_shop_sell", location_id=1100)
        await crud.charge_character(s, 1, 100, op_type="npc_shop_buy", location_id=1001)
        await s.commit()
        yield s
    await engine.dispose()
    econ_core.invalidate_settings_cache()


async def _active(s, kind, ref_id):
    return await _one(s, "SELECT is_active FROM econ_accounts WHERE kind = :k AND ref_id = :r", k=kind, r=ref_id)


class TestTreasuryClosing:

    async def test_deleting_a_region_moves_its_treasury_to_the_country(self, world_db):
        s = world_db
        assert (await _account(s, "region_treasury", 10), await _account(s, "country_treasury", 1)) == (450, 50)
        await crud.delete_region(s, 10)
        assert await _one(s, "SELECT COUNT(*) FROM Regions WHERE id = 10") == 0
        assert await _account(s, "region_treasury", 10) == 0
        assert await _account(s, "country_treasury", 1) == 500
        assert await _active(s, "region_treasury", 10) == 0
        meta = await _one(s, "SELECT metadata FROM econ_operations WHERE op_type = 'treasury_closed'")
        assert '"region_id": 10' in meta
        assert await _one(s, "SELECT COUNT(*) FROM econ_postings p JOIN econ_operations o ON o.id = p.operation_id "
                             "WHERE o.op_type = 'treasury_closed' AND p.leg_type = 'tax'") == 0
        assert await _world_sum(s) == 0

    async def test_a_negative_region_is_covered_by_its_country(self, world_db):
        s = world_db
        await crud.delete_region(s, 11)
        assert await _account(s, "region_treasury", 11) == 0
        assert await _account(s, "country_treasury", 1) == 50 - 70
        assert await _world_sum(s) == 0

    async def test_deleting_a_country_closes_its_regions_then_itself_into_the_world(self, world_db):
        s = world_db
        await crud.delete_country(s, 1)
        for kind, ref in (("region_treasury", 10), ("region_treasury", 11), ("country_treasury", 1)):
            assert await _account(s, kind, ref) == 0, (kind, ref)
            assert await _active(s, kind, ref) == 0, (kind, ref)
        assert await _account(s, "world_treasury") == 450 - 70 + 50
        assert await _ops(s, "treasury_closed") == 3
        # the other country is untouched
        assert (await _account(s, "region_treasury", 20), await _account(s, "country_treasury", 2)) == (90, 10)
        assert await _active(s, "region_treasury", 20) == 1
        assert await _world_sum(s) == 0

    async def test_a_failed_region_delete_rolls_the_closing_back(self, world_db, monkeypatch):
        s = world_db

        async def _boom(*a, **kw):
            raise RuntimeError("district delete failed")

        monkeypatch.setattr(crud, "delete_district", _boom)
        with pytest.raises(RuntimeError):
            await crud.delete_region(s, 10)
        await s.rollback()
        assert await _account(s, "region_treasury", 10) == 450
        assert await _account(s, "country_treasury", 1) == 50
        assert await _active(s, "region_treasury", 10) == 1
        assert await _ops(s, "treasury_closed") == 0
        assert await _one(s, "SELECT COUNT(*) FROM Regions WHERE id = 10") == 1
        assert await _world_sum(s) == 0

    async def test_a_region_never_paid_into_posts_nothing(self, world_db):
        s = world_db
        await s.execute(text("INSERT INTO Regions (id, name, country_id, description) VALUES (12, 'A3', 1, '')"))
        await s.commit()
        await crud.delete_region(s, 12)
        assert await _ops(s, "treasury_closed") == 0
        assert await _world_sum(s) == 0

    async def _fund_purse(self, s, region_id, amount):
        await econ_ledger.post_operation(
            s, op_type="admin_emission",
            legs=[econ_core.Leg(econ_core.AccountRef.emission(), econ_core.AccountRef.purse(region_id), amount)],
            source_service="test", comment="purse seed", apply_tax=False)
        await s.commit()

    async def test_deleting_a_region_moves_its_population_purse_to_the_country_untaxed(self, world_db):
        """FEAT-182 3.8: purse -> country (no tax leg), then the treasury as before; both deactivated."""
        s = world_db
        await self._fund_purse(s, 10, 1200)
        assert await _account(s, "population_purse", 10) == 1200
        await crud.delete_region(s, 10)
        assert await _account(s, "population_purse", 10) == 0
        assert await _active(s, "population_purse", 10) == 0
        assert await _account(s, "region_treasury", 10) == 0
        assert await _active(s, "region_treasury", 10) == 0
        assert await _account(s, "country_treasury", 1) == 50 + 450 + 1200
        assert await _ops(s, "treasury_closed") == 2
        assert await _one(s, "SELECT COUNT(*) FROM econ_postings p JOIN econ_operations o ON o.id = p.operation_id "
                             "WHERE o.op_type = 'treasury_closed' AND p.leg_type = 'tax'") == 0
        assert await _world_sum(s) == 0

    async def test_an_empty_purse_is_deactivated_without_a_posting(self, world_db):
        s = world_db
        await self._fund_purse(s, 10, 300)
        await econ_ledger.post_operation(
            s, op_type="admin_adjust",
            legs=[econ_core.Leg(econ_core.AccountRef.purse(10), econ_core.AccountRef.adjustment(), 300)],
            source_service="test", comment="drain", apply_tax=False)
        await s.commit()
        await crud.delete_region(s, 10)
        assert await _active(s, "population_purse", 10) == 0
        assert await _ops(s, "treasury_closed") == 1  # the region treasury only
        assert await _world_sum(s) == 0

    async def test_a_failed_region_delete_keeps_the_purse(self, world_db, monkeypatch):
        """FEAT-182: the purse closing is part of the same transaction as the region delete."""
        s = world_db
        await self._fund_purse(s, 10, 800)

        async def _boom(*a, **kw):
            raise RuntimeError("district delete failed")

        monkeypatch.setattr(crud, "delete_district", _boom)
        with pytest.raises(RuntimeError):
            await crud.delete_region(s, 10)
        await s.rollback()
        assert await _account(s, "population_purse", 10) == 800
        assert await _active(s, "population_purse", 10) == 1
        assert await _account(s, "country_treasury", 1) == 50
        assert await _ops(s, "treasury_closed") == 0
        assert await _world_sum(s) == 0

    async def test_a_negative_treasury_and_a_funded_purse_close_in_one_delete(self, world_db):
        """Region 11 owes 70; its purse (500) and the debt both land in country 1, untaxed."""
        s = world_db
        await self._fund_purse(s, 11, 500)
        await crud.delete_region(s, 11)
        assert await _account(s, "population_purse", 11) == 0
        assert await _account(s, "region_treasury", 11) == 0
        assert await _account(s, "country_treasury", 1) == 50 + 500 - 70
        assert await _one(s, "SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'") == 2  # seed buys only
        assert await _world_sum(s) == 0

    async def test_purse_cannot_be_overdrawn_through_the_async_ledger(self, world_db):
        s = world_db
        await self._fund_purse(s, 20, 40)
        with pytest.raises(econ_core.InsufficientFunds):
            await econ_ledger.post_operation(
                s, op_type="region_tick",
                legs=[econ_core.Leg(econ_core.AccountRef.purse(20), econ_core.AccountRef.region(20), 41)],
                source_service="test", region_id=20)
        await s.rollback()
        assert await _account(s, "population_purse", 20) == 40
        assert await _ops(s, "region_tick") == 0
        assert await _world_sum(s) == 0

    async def test_deleting_a_country_sends_region_purses_to_the_world(self, world_db):
        s = world_db
        await self._fund_purse(s, 10, 200)
        await self._fund_purse(s, 11, 30)
        await crud.delete_country(s, 1)
        for ref in (10, 11):
            assert await _account(s, "population_purse", ref) == 0
            assert await _active(s, "population_purse", ref) == 0
        assert await _account(s, "world_treasury") == 450 - 70 + 50 + 200 + 30
        assert await _world_sum(s) == 0

    async def test_unknown_region_is_404_and_moves_nothing(self, world_db):
        with pytest.raises(HTTPException) as exc:
            await crud.delete_region(world_db, 999)
        assert exc.value.status_code == 404
        assert await _ops(world_db, "treasury_closed") == 0

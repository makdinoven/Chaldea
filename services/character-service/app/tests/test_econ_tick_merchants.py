"""FEAT-183 Q3: the NPC merchants step of the region tick (``econ_tick``) on SQLite.

Every test gets its own in-memory database built from the character-service metadata (the conftest ``after_create``
hook adds Countries / Regions / Districts / Locations), seeded with the migration-028 defaults like
``test_econ_tick.py``, plus the foreign tables the merchant step reads: ``Locations.marker_type`` (added here,
conftest's portable Locations has no such column), ``items`` and ``npc_shop_items`` (their DDL comes from
``econ_contract_cases.MERCHANT_SQLITE_DDL``). NPCs are inserted through the ORM with balance 0 and get their cash by
an emission operation, so the ledger stays closed.

World:
    country 1 <- region 1 (rural) <- location 100 (safe), 101 (dungeon)
    country 1 <- region 2 (rural) <- location 200
    country 1 <- region 3 (no economy row) <- location 300
    NPC 31 alive @100 (living, region 1) — bread (stock 30), ore (stock NULL), scroll (off-market),
            sold-out player-origin sword, inactive bread-like row
    NPC 35 alive @200 (living, region 2) — bread
    NPC 32 dead @100, NPC 33 alive @101 (dungeon), NPC 34 alive @300 (not simulated)  — legacy, never touched
    shop row of NPC 999 (no character) — orphan, purged at run start
"""

import importlib.util
import json
import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import econ_core as core
import econ_ledger
import econ_merchant
import econ_sim
import econ_tick
import models
from tests.econ_contract_cases import MERCHANT_SQLITE_DDL

MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "028_econ_living_regions.py")
_spec = importlib.util.spec_from_file_location("migration_028_for_tick_merchants", MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

T0 = datetime(2026, 10, 28, 0, 5)
SOURCE = "character-service"
FOREIGN_DDL = [ddl for ddl in MERCHANT_SQLITE_DDL
               if ddl.lstrip().startswith(("CREATE TABLE items", "CREATE TABLE npc_shop_items"))]

ITEMS = [
    # id, name, item_type, rarity, subcategory, is_food
    (1, "Хлеб", "consumable", "common", None, 1),            # food (base 2)
    (2, "Железная руда", "resource", "common", "ore", 0),    # ore_metal (base 10)
    (3, "Свиток", "scroll", "rare", None, 0),               # off-market
    (4, "Меч", "weapon", "common", None, 0),                # weapons
    (5, "Лепёшка", "consumable", "common", None, 1),         # food
]

# id, npc_id, item_id, buy_price, sell_price, stock, is_active, restock_target, origin
SHOP_ROWS = [
    (1, 31, 1, 40, 20, 30, 1, 40, "admin"),
    (2, 31, 2, 30, 10, None, 1, 6, "admin"),
    (3, 31, 3, 60, 0, 3, 1, 5, "admin"),
    (4, 31, 4, 150, 60, 0, 1, 0, "player"),
    (5, 31, 5, 4, 2, 7, 0, 10, "admin"),
    (6, 35, 1, 40, 20, 12, 1, 15, "admin"),
    (7, 32, 1, 4, 2, 5, 1, 10, "admin"),
    (8, 33, 1, 4, 2, None, 1, 10, "admin"),
    (9, 34, 1, 4, 2, 2, 1, 10, "admin"),
    (10, 999, 1, 4, 2, 5, 1, 10, "admin"),
]

NPCS = [
    # id, status, location, cash
    (31, "alive", 100, 5_000),
    (35, "alive", 200, 300),
    (32, "dead", 100, 700),
    (33, "alive", 101, 800),
    (34, "alive", 300, 900),
]
LEGACY_ROWS = (7, 8, 9)


# --------------------------------------------------------------------------------------------- fixtures

@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()
    db.execute(text("ALTER TABLE Locations ADD COLUMN marker_type VARCHAR(16) NOT NULL DEFAULT 'safe'"))
    for ddl in FOREIGN_DDL:
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
    db.commit()
    db.close()
    core.invalidate_settings_cache()
    yield session_factory
    core.invalidate_settings_cache()
    engine.dispose()


def _add_region(factory, region_id, template="rural"):
    db = factory()
    try:
        db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (:i, :n, 1)"),
                   {"i": region_id, "n": f"Регион {region_id}"})
        groups = econ_tick.load_groups(db)
        tpl = db.get(models.EconRegionTemplate, template)
        pop = tpl.default_population
        goods = econ_sim.starting_goods(groups, {g: (p, c) for g, p, c in mig.template_goods(template)}, pop)
        db.add(models.EconRegion(region_id=region_id, template_code=template, population=pop, tax_rate=tpl.tax_rate))
        db.flush()
        for code, g in goods.items():
            db.add(models.EconRegionGood(region_id=region_id, group_code=code,
                                         production_per_1000=g.production_per_1000,
                                         consumption_mult=g.consumption_mult,
                                         stock=round(g.stock, 3), norm_stock=round(g.norm_stock, 3)))
        _emit(db, core.AccountRef.purse(region_id), econ_sim.starting_purse(groups, goods, pop))
        db.commit()
    finally:
        db.close()


def _emit(db, ref, amount):
    econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                               legs=[core.Leg(core.AccountRef.emission(), ref, int(amount))])


@pytest.fixture
def world(factory):
    _add_region(factory, 1)
    _add_region(factory, 2)
    db = factory()
    try:
        db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (3, 'Глушь', 1)"))
        db.execute(text("UPDATE econ_regions SET tax_rate = 0.3"))       # visible trade tax + country share
        db.execute(text("INSERT INTO Locations (id, name, region_id, marker_type) VALUES "
                        "(100, 'Рынок', 1, 'safe'), (101, 'Склеп', 1, 'dungeon'), (200, 'Село', 2, 'safe'), "
                        "(300, 'Хутор', 3, 'safe')"))
        for item in ITEMS:
            db.execute(text("INSERT INTO items (id, name, item_type, item_rarity, resource_subcategory, is_food, "
                            "price) VALUES (:i, :n, :t, :r, :s, :f, 10)"),
                       {"i": item[0], "n": item[1], "t": item[2], "r": item[3], "s": item[4], "f": item[5]})
        with econ_ledger.allow_direct_balance_write(db):
            for npc_id, status, location, _cash in NPCS:
                db.add(models.Character(id=npc_id, name=f"НПС {npc_id}", id_subrace=1, id_class=1, id_race=1,
                                        appearance="-", avatar="-", is_npc=True, npc_status=status,
                                        current_location_id=location, currency_balance=0))
            db.flush()
        for npc_id, _status, _location, cash in NPCS:
            _emit(db, core.AccountRef.character(npc_id), cash)
        for row in SHOP_ROWS:
            db.execute(text("INSERT INTO npc_shop_items (id, npc_id, item_id, buy_price, sell_price, stock, "
                            "is_active, restock_target, origin) VALUES (:a, :b, :c, :d, :e, :f, :g, :h, :i)"),
                       dict(zip("abcdefghi", row)))
        db.commit()
    finally:
        db.close()
    return factory


@pytest.fixture
def spy(monkeypatch):
    """Records every merchant_step call: [(market, merchants, result)]."""
    calls = []
    original = econ_merchant.merchant_step

    def recording(market, merchants, params=econ_sim.DEFAULT_PARAMS):
        result = original(market, merchants, params)
        calls.append((market, list(merchants), result))
        return result

    monkeypatch.setattr(econ_merchant, "merchant_step", recording)
    return calls


def _rows(factory, sql, **params):
    db = factory()
    try:
        return [tuple(r) for r in db.execute(text(sql), params).fetchall()]
    finally:
        db.close()


def _scalar(factory, sql, **params):
    db = factory()
    try:
        return db.execute(text(sql), params).scalar()
    finally:
        db.close()


def _stocks(factory):
    return dict(_rows(factory, "SELECT id, stock FROM npc_shop_items ORDER BY id"))


def _cash(factory, npc_id):
    return int(_scalar(factory, "SELECT currency_balance FROM characters WHERE id = :i", i=npc_id))


def _region_stock(factory, region_id):
    return {g: float(s) for g, s in _rows(factory, "SELECT group_code, stock FROM econ_region_goods "
                                                    "WHERE region_id = :r", r=region_id)}


def _merchant_ops(factory):
    return _rows(factory, "SELECT id, region_id, idempotency_key, metadata FROM econ_operations "
                          "WHERE op_type = 'merchant_trade' ORDER BY id")


def _postings(factory, op_id):
    return _rows(factory, "SELECT fa.kind, fa.ref_id, ta.kind, ta.ref_id, p.amount, p.leg_type "
                          "FROM econ_postings p JOIN econ_accounts fa ON fa.id = p.from_account_id "
                          "JOIN econ_accounts ta ON ta.id = p.to_account_id WHERE p.operation_id = :o ORDER BY p.id",
                 o=op_id)


def _assert_ledger_closes(factory):
    """Summary invariant: non-character accounts + characters.currency_balance sum to 0; nothing negative;
    every balance equals its posting history (character accounts: the characters row)."""
    accounts = int(_scalar(factory, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character'"))
    characters = int(_scalar(factory, "SELECT COALESCE(SUM(currency_balance), 0) FROM characters"))
    assert accounts + characters == 0
    assert _rows(factory, "SELECT kind, ref_id, balance FROM econ_accounts "
                          "WHERE allow_negative = 0 AND balance < 0 AND kind <> 'character'") == []
    assert _rows(factory, "SELECT id FROM characters WHERE currency_balance < 0") == []
    history = ("COALESCE((SELECT SUM(amount) FROM econ_postings WHERE to_account_id = a.id), 0) - "
               "COALESCE((SELECT SUM(amount) FROM econ_postings WHERE from_account_id = a.id), 0)")
    rows = _rows(factory, f"SELECT a.balance, {history} FROM econ_accounts a WHERE a.kind <> 'character'")
    assert all(int(r[0]) == int(r[1]) for r in rows)
    rows = _rows(factory, f"SELECT c.currency_balance, {history} FROM characters c "
                          "JOIN econ_accounts a ON a.kind = 'character' AND a.ref_id = c.id")
    assert all(int(r[0]) == int(r[1]) for r in rows)
    try:
        assert _rows(factory, "SELECT id FROM npc_shop_items WHERE stock < 0") == []
    except Exception as exc:  # the table may be dropped by a test
        if "no such table" not in str(exc):
            raise


def _run(factory):
    return econ_tick.run_tick(factory, trigger="manual", now=T0)


# --------------------------------------------------------------------------------------------- the step

def test_one_merchant_trade_op_per_region_with_expected_legs(world, spy):
    summary = _run(world)
    assert summary.status == "done" and summary.regions_done == 2 and summary.merchant_failures == 0
    assert len(spy) == 2
    ops = _merchant_ops(world)
    assert [(o[1], o[2]) for o in ops] == [(1, f"merchant_trade:{summary.run_id}:r:1"),
                                           (2, f"merchant_trade:{summary.run_id}:r:2")]
    assert summary.merchant_ops_posted == 2
    assert summary.merchants_processed == 2

    db = world()
    country_rate = econ_ledger.get_economy_settings(db).country_tax_rate
    db.close()
    for (op_id, region_id, _key, meta), (market, merchants, step) in zip(ops, spy):
        assert market.region_id == region_id
        assert [m.npc_id for m in merchants] == ([31] if region_id == 1 else [35])
        expected = core.add_tax_legs(step.legs, country_rate, {region_id: 1})
        assert _postings(world, op_id) == [(l.src.kind, l.src.ref_id, l.dst.kind, l.dst.ref_id, l.amount, l.leg_type)
                                           for l in expected]
        assert any(l.leg_type == core.LEG_TRADE_TAX for l in step.legs)
        assert any(l.leg_type == core.LEG_TAX and l.dst == core.AccountRef.country(1) for l in expected)
        meta = json.loads(meta) if isinstance(meta, str) else meta
        assert meta["run_id"] == summary.run_id
        assert meta["sold_value"] == step.sold_value and meta["tax"] == step.tax
        assert meta["purse_budget"] == step.purse_budget
        assert meta["merchants"] == step.metadata()["merchants"]
    _assert_ledger_closes(world)


def test_goods_move_both_ways(world, spy):
    _run(world)
    stocks = _stocks(world)
    market, merchants, step = spy[0]
    sold = {r.row_id: r for m in step.merchants for r in m.rows}
    # bread: residents bought from the shop -> row stock fell, region food rose by sold x units (40 / 2 = 20)
    assert sold[1].sold > 0
    # ore: NULL stock became a number and was restocked from the region
    assert sold[2].stock_before == 0 and sold[2].restocked > 0
    assert stocks[1] == sold[1].stock_after and stocks[2] == sold[2].stock_after
    assert step.stock_delta["ore_metal"] < 0
    # the stored region stock is the sim result moved by the merchants
    region = _region_stock(world, 1)
    for g, value in step.stock_after.items():
        assert region[g] == pytest.approx(value, abs=1e-3)
        assert region[g] >= 0
    # the history row reflects the merchants
    history = _scalar(world, "SELECT goods FROM econ_region_history WHERE region_id = 1")
    history = json.loads(history) if isinstance(history, str) else history
    for g, value in step.stock_after.items():
        assert history[g]["stock"] == pytest.approx(value, abs=1e-3)
    # cash moved exactly as the step said
    m31 = step.merchants[0]
    assert _cash(world, 31) == m31.cash_after == 5_000 + m31.sold_value - m31.tax - m31.restock_value - m31.upkeep


def test_off_market_and_inactive_rows_untouched(world, spy):
    _run(world)
    stocks = _stocks(world)
    assert stocks[3] == 3          # scroll off-market
    assert stocks[5] == 7          # inactive row is not part of the merchant
    _market, merchants, _step = spy[0]
    assert sorted(r.row_id for r in merchants[0].rows) == [1, 2, 3, 4]


def test_legacy_dead_and_dungeon_merchants_are_skipped(world, spy):
    before = _stocks(world)
    summary = _run(world)
    after = _stocks(world)
    for row_id in LEGACY_ROWS:
        assert after[row_id] == before[row_id]          # NULL stays NULL (legacy unlimited)
    assert after[8] is None
    for npc_id, cash in ((32, 700), (33, 800), (34, 900)):
        assert _cash(world, npc_id) == cash
    traded = {n for _m, merchants, _s in spy for n in (m.npc_id for m in merchants)}
    assert traded == {31, 35}
    for op in _merchant_ops(world):
        meta = json.loads(op[3]) if isinstance(op[3], str) else op[3]
        assert set(meta["merchants"]) <= {"31", "35"}
    assert summary.merchants_processed == 2


def test_orphan_and_sold_out_player_rows_are_purged(world):
    summary = _run(world)
    ids = set(_stocks(world))
    assert 10 not in ids           # NPC 999 does not exist
    assert 4 not in ids            # player-origin, stock 0
    assert summary.shop_rows_purged == 2
    assert {1, 2, 3, 5, 6, 7, 8, 9} <= ids


def test_player_origin_row_with_stock_is_kept_and_sold_from(world, spy):
    db = world()
    db.execute(text("UPDATE npc_shop_items SET stock = 5 WHERE id = 4"))
    db.commit()
    db.close()
    summary = _run(world)
    assert summary.shop_rows_purged == 1          # only the orphan
    row4 = [r for m in spy[0][2].merchants for r in m.rows if r.row_id == 4][0]
    assert row4.restocked == 0
    assert _stocks(world).get(4) == row4.stock_after
    _assert_ledger_closes(world)


def test_rerun_of_the_same_run_is_a_noop(world):
    summary = _run(world)
    stocks, cash = _stocks(world), _cash(world, 31)
    goods = _region_stock(world, 1)
    ops = _scalar(world, "SELECT COUNT(*) FROM econ_operations")
    groups = econ_tick.load_groups(world())
    params = econ_tick.load_params(world())
    outcome = econ_tick._process_region(world, run_id=summary.run_id, region_id=1, grant=0, groups=groups,
                                        params=params, country_tax_rate=0.1, now=T0, merchant_npcs=[31])
    assert outcome.status == "already"
    assert _stocks(world) == stocks and _cash(world, 31) == cash and _region_stock(world, 1) == goods
    assert _scalar(world, "SELECT COUNT(*) FROM econ_operations") == ops


def test_merchant_op_key_already_posted_skips_only_the_merchants(world, spy):
    """Another runner posted the merchants of region 1 (run 1): the SAVEPOINT rolls back, the region still ticks."""
    db = world()
    db.execute(text("INSERT INTO econ_operations (op_type, idempotency_key, region_id, source_service, created_at) "
                    "VALUES ('merchant_trade', 'merchant_trade:1:r:1', 1, 'character-service', :t)"), {"t": T0})
    db.commit()
    db.close()
    before = _stocks(world)
    summary = _run(world)
    assert summary.run_id == 1 and summary.status == "done" and summary.regions_done == 2
    assert summary.merchant_failures == 0
    assert summary.merchant_ops_posted == 1                      # region 2 only
    after = _stocks(world)
    assert all(after[r] == before[r] for r in (1, 2, 3))         # region 1 shop untouched
    assert _cash(world, 31) == 5_000
    assert _scalar(world, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_tick'") == 2
    assert _scalar(world, "SELECT last_run_id FROM econ_regions WHERE region_id = 1") == 1
    _assert_ledger_closes(world)


def test_failing_merchant_step_does_not_fail_the_region(world, monkeypatch):
    """The posting of region 1's merchants blows up after the shop rows were updated: all of it is rolled back."""
    original = econ_ledger.post_operation

    def boom(session, *, op_type, **kwargs):
        if op_type == core.OP_MERCHANT_TRADE and kwargs.get("region_id") == 1:
            raise RuntimeError("broken merchant")
        return original(session, op_type=op_type, **kwargs)

    monkeypatch.setattr(econ_ledger, "post_operation", boom)
    before = _stocks(world)
    summary = _run(world)
    assert summary.status == "done" and summary.regions_done == 2 and summary.regions_failed == 0
    assert summary.merchant_failures == 1 and summary.merchant_failed_region_ids == [1]
    assert summary.merchant_ops_posted == 1
    after = _stocks(world)
    assert all(after[r] == before[r] for r in (1, 2, 3))         # UPDATEs inside the SAVEPOINT rolled back
    assert 4 in after                                           # the player-row DELETE too
    assert _cash(world, 31) == 5_000
    # the region itself ticked
    assert _scalar(world, "SELECT last_run_id FROM econ_regions WHERE region_id = 1") == summary.run_id
    assert _scalar(world, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_tick'") == 2
    assert _scalar(world, "SELECT COUNT(*) FROM econ_region_history WHERE region_id = 1") == 1
    # the run row remembers the merchant failure
    error = _scalar(world, "SELECT error FROM econ_tick_runs WHERE id = :i", i=summary.run_id)
    assert econ_tick.MERCHANT_ERROR_PREFIX in error
    assert econ_tick.merchant_failures_from_error(error) == 1
    assert _scalar(world, "SELECT status FROM econ_tick_runs WHERE id = :i", i=summary.run_id) == "done"
    _assert_ledger_closes(world)


def test_pure_step_exception_is_isolated(world, monkeypatch):
    def broken(*_a, **_k):
        raise ZeroDivisionError("bad data")

    monkeypatch.setattr(econ_merchant, "merchant_step", broken)
    summary = _run(world)
    assert summary.status == "done" and summary.regions_done == 2
    assert summary.merchant_failures == 2 and summary.merchant_ops_posted == 0
    assert _merchant_ops(world) == []
    assert _scalar(world, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_tick'") == 2
    _assert_ledger_closes(world)


def test_lock_failure_skips_merchants_but_region_ticks(world, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError("lock failed")

    monkeypatch.setattr(econ_tick, "lock_merchants", broken)
    summary = _run(world)
    assert summary.status == "done" and summary.regions_done == 2
    assert summary.merchant_failures == 2
    assert _merchant_ops(world) == []
    _assert_ledger_closes(world)


def test_missing_shop_table_regions_still_tick(world):
    db = world()
    db.execute(text("DROP TABLE npc_shop_items"))
    db.commit()
    db.close()
    summary = _run(world)
    assert summary.status == "done" and summary.regions_done == 2 and summary.regions_failed == 0
    assert summary.merchants_processed == 0 and summary.merchant_failures == 0 and summary.shop_rows_purged == 0
    assert _scalar(world, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_tick'") == 2
    _assert_ledger_closes(world)


def test_merchant_moved_after_the_map_is_dropped_under_the_lock(world, monkeypatch, spy):
    """The run map says NPC 31 trades in region 1, but he is moved into the dungeon before region 1 locks him."""
    original = econ_tick.build_merchant_map

    def build_then_move(session):
        result = original(session)
        mover = world()
        mover.execute(text("UPDATE characters SET current_location_id = 101 WHERE id = 31"))
        mover.commit()
        mover.close()
        return result

    monkeypatch.setattr(econ_tick, "build_merchant_map", build_then_move)
    before = _stocks(world)
    summary = _run(world)
    assert summary.status == "done" and summary.merchant_failures == 0
    assert [c[0].region_id for c in spy] == [2]               # region 1 had nobody left to trade
    after = _stocks(world)
    assert all(after[r] == before[r] for r in (1, 2, 3))
    assert _cash(world, 31) == 5_000


def test_many_runs_keep_the_world_consistent(world):
    for minute in range(6):
        summary = econ_tick.run_tick(world, trigger="manual", now=datetime(2026, 10, 28, 1, minute * 5))
        assert summary.status == "done" and summary.merchant_failures == 0
        _assert_ledger_closes(world)
        for g, s in _region_stock(world, 1).items():
            assert s >= 0
    assert len(_merchant_ops(world)) >= 6
    assert _scalar(world, "SELECT COUNT(*) FROM econ_tick_runs") == 6

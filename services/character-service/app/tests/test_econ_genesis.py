"""FEAT-181 Q1: genesis emission of migration 027_world_economy.

The migration's `_genesis(conn)` is plain SQL written for MySQL. It runs here against SQLite
through a thin connection shim that only translates the two MySQL-only spellings it uses:
`INSERT IGNORE` -> `INSERT OR IGNORE`, and the information_schema table check -> sqlite_master.
Everything else (which rows are inserted, amounts, idempotency) is the migration's own SQL.
"""

import importlib.util
import os

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import economy_crud
from tests import econ_contract_cases as cc

MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "027_world_economy.py")


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_027_world_economy", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mig = _load_migration()


class _SqliteConn:
    """Connection proxy: MySQL `INSERT IGNORE` spelled the SQLite way."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, clause, params=None):
        sql = clause.text.replace("INSERT IGNORE", "INSERT OR IGNORE")
        return self._conn.execute(sa.text(sql), params or {})


def _sqlite_table_exists(conn, name):
    return bool(conn._conn.execute(sa.text(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = :n"), {"n": name}).scalar())


@pytest.fixture()
def genesis_db(monkeypatch):
    monkeypatch.setattr(mig, "_table_exists", _sqlite_table_exists)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        for ddl in cc.SQLITE_DDL:
            conn.execute(text(ddl))
    yield engine
    engine.dispose()


def _seed_world(engine, *, auction=True, hierarchy=True):
    with engine.begin() as conn:
        if hierarchy:
            conn.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Мидденгерд'), (2, 'Пустошь')"))
            conn.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (9, 'Мэттанхейм', 1), "
                              "(10, 'Предгорья', 1), (20, 'Дюны', 2)"))
        conn.execute(text("INSERT INTO characters (id, name, currency_balance) VALUES "
                          "(1, 'Ашари', 100), (2, 'Пустой', 0), (3, 'Богач', 250), (4, 'НПС-торговец', 40)"))
        if auction:
            conn.execute(text("CREATE TABLE auction_listings (id INTEGER PRIMARY KEY, current_bid INTEGER, "
                              "current_bidder_id INTEGER NULL, status VARCHAR(20))"))
            conn.execute(text("CREATE TABLE auction_storage (id INTEGER PRIMARY KEY, gold_amount INTEGER)"))
            conn.execute(text("INSERT INTO auction_listings (id, current_bid, current_bidder_id, status) VALUES "
                              "(1, 30, 1, 'active'), (2, 70, NULL, 'active'), (3, 500, 3, 'sold')"))
            conn.execute(text("INSERT INTO auction_storage (id, gold_amount) VALUES (1, 100), (2, 46)"))


def _run_genesis(engine):
    with engine.begin() as conn:
        mig._genesis(_SqliteConn(conn))


def _rows(engine, sql, **params):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql), params).fetchall()]


def _scalar(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def _balance(engine, kind, ref_id=0):
    return _scalar(engine, "SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r", k=kind, r=ref_id)


def _drifting(engine):
    return _rows(engine, economy_crud.SQL_CHARACTER_LEDGER, limit=50)


def test_genesis_issues_every_balance_and_closes_the_world(genesis_db):
    _seed_world(genesis_db)
    _run_genesis(genesis_db)

    # Singletons + one treasury per region / country, all treasuries at 0.
    accounts = {(k, r): (n, b, neg) for k, r, n, b, neg in _rows(
        genesis_db, "SELECT kind, ref_id, name, balance, allow_negative FROM econ_accounts "
                    "WHERE kind <> 'character'")}
    assert accounts == {
        ("emission", 0): ("Эмиссия", -(390 + 30 + 146), 1),
        ("adjustment", 0): ("Корректировки", 0, 1),
        ("world_treasury", 0): ("Казна Скитальцев", 0, 1),
        ("auction_escrow", 0): ("Ставки аукциона", 30, 0),          # only the active bid with a bidder
        ("auction_storage", 0): ("Хранилище аукциона", 146, 0),
        ("region_treasury", 9): ("Мэттанхейм", 0, 1),
        ("region_treasury", 10): ("Предгорья", 0, 1),
        ("region_treasury", 20): ("Дюны", 0, 1),
        ("country_treasury", 1): ("Мидденгерд", 0, 1),
        ("country_treasury", 2): ("Пустошь", 0, 1),
    }

    # Character accounts only for non-zero balances; their own balance column stays 0.
    assert _rows(genesis_db, "SELECT ref_id, name, balance, allow_negative FROM econ_accounts "
                             "WHERE kind = 'character' ORDER BY ref_id") == [
        (1, "Ашари", 0, 0), (3, "Богач", 0, 0), (4, "НПС-торговец", 0, 0)]

    ops = _rows(genesis_db, "SELECT id, op_type, idempotency_key, source_service, comment FROM econ_operations")
    assert len(ops) == 1
    assert ops[0][1:] == ("genesis", "genesis", "character-service", "Начальная эмиссия")

    legs = _rows(genesis_db, (
        "SELECT fa.kind, ta.kind, ta.ref_id, p.amount, p.leg_type FROM econ_postings p "
        "JOIN econ_accounts fa ON fa.id = p.from_account_id JOIN econ_accounts ta ON ta.id = p.to_account_id "
        "WHERE p.operation_id = :op ORDER BY p.id"), op=ops[0][0])
    assert legs == [
        ("emission", "character", 1, 100, "main"),
        ("emission", "character", 3, 250, "main"),
        ("emission", "character", 4, 40, "main"),
        ("emission", "auction_escrow", 0, 30, "main"),
        ("emission", "auction_storage", 0, 146, "main"),
    ]

    assert _scalar(genesis_db, cc.WORLD_SUM_SQL) == 0
    assert _drifting(genesis_db) == []          # every character balance == its postings


def test_genesis_is_idempotent(genesis_db):
    _seed_world(genesis_db)
    _run_genesis(genesis_db)
    before = (_rows(genesis_db, "SELECT kind, ref_id, balance FROM econ_accounts ORDER BY id"),
              _scalar(genesis_db, "SELECT COUNT(*) FROM econ_postings"))
    _run_genesis(genesis_db)
    after = (_rows(genesis_db, "SELECT kind, ref_id, balance FROM econ_accounts ORDER BY id"),
             _scalar(genesis_db, "SELECT COUNT(*) FROM econ_postings"))
    assert before == after
    assert _scalar(genesis_db, "SELECT COUNT(*) FROM econ_operations") == 1
    assert _scalar(genesis_db, cc.WORLD_SUM_SQL) == 0


def test_rerun_adds_treasuries_of_new_regions_but_no_second_emission(genesis_db):
    _seed_world(genesis_db)
    _run_genesis(genesis_db)
    with genesis_db.begin() as conn:
        conn.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (30, 'Новый край', 2)"))
        conn.execute(text("INSERT INTO characters (id, name, currency_balance) VALUES (5, 'Поздний', 10)"))
    _run_genesis(genesis_db)
    assert _balance(genesis_db, "region_treasury", 30) == 0
    assert _scalar(genesis_db, "SELECT COUNT(*) FROM econ_operations") == 1
    assert _balance(genesis_db, "emission") == -566       # the late balance is not re-issued


def test_negative_character_balance_flows_back_to_emission(genesis_db):
    with genesis_db.begin() as conn:
        conn.execute(text("INSERT INTO characters (id, name, currency_balance) VALUES (1, 'Должник', -5), "
                          "(2, 'Ашари', 50)"))
    _run_genesis(genesis_db)
    legs = _rows(genesis_db, (
        "SELECT fa.kind, fa.ref_id, ta.kind, ta.ref_id, p.amount FROM econ_postings p "
        "JOIN econ_accounts fa ON fa.id = p.from_account_id JOIN econ_accounts ta ON ta.id = p.to_account_id "
        "ORDER BY p.id"))
    assert ("character", 1, "emission", 0, 5) in legs
    assert ("emission", 0, "character", 2, 50) in legs
    assert _balance(genesis_db, "emission") == -45
    assert _scalar(genesis_db, cc.WORLD_SUM_SQL) == 0
    assert _drifting(genesis_db) == []


def test_genesis_on_db_without_foreign_tables(genesis_db):
    """No auction tables, no regions/countries rows: only singletons + characters."""
    _seed_world(genesis_db, auction=False, hierarchy=False)
    _run_genesis(genesis_db)
    kinds = {r[0] for r in _rows(genesis_db, "SELECT kind FROM econ_accounts")}
    assert kinds == {"emission", "adjustment", "world_treasury", "auction_escrow", "auction_storage", "character"}
    assert _balance(genesis_db, "auction_escrow") == 0 and _balance(genesis_db, "auction_storage") == 0
    assert _balance(genesis_db, "emission") == -390
    assert _scalar(genesis_db, "SELECT COUNT(*) FROM econ_postings") == 3
    assert _scalar(genesis_db, cc.WORLD_SUM_SQL) == 0


def test_genesis_on_empty_world(genesis_db):
    _run_genesis(genesis_db)
    assert _scalar(genesis_db, "SELECT COUNT(*) FROM econ_operations") == 1
    assert _scalar(genesis_db, "SELECT COUNT(*) FROM econ_postings") == 0
    assert _balance(genesis_db, "emission") == 0


def test_migration_metadata():
    assert mig.revision == "027_world_economy"
    assert mig.down_revision == "026_house_presence"
    assert len(mig.revision) <= 32
    # Singletons mirror econ_core.
    import econ_core
    for kind, name, allow_negative in mig.SINGLETONS:
        assert econ_core.SINGLETON_NAMES[kind] == name
        assert bool(allow_negative) == (kind in econ_core.NEGATIVE_ALLOWED_KINDS)

"""
Fixtures for inventory-service tests.

Uses SQLite in-memory DB, patches config before main.py import.
"""

import sys
import os

import pytest
from sqlalchemy import create_engine, event, String, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add the app directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set DB env vars BEFORE importing config/database — Pydantic BaseSettings
# requires DB_HOST, DB_USERNAME, DB_PASSWORD, DB_DATABASE (no defaults).
# The actual MySQL URL is never used because we patch database.engine below.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

# ── SQLite in-memory engine ──────────────────────────────────────────────
_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# Patch the database module BEFORE importing main.py
import database  # noqa: E402
database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

# Patch ENUM columns to String for SQLite compatibility
import models  # noqa: E402
for col in models.Items.__table__.columns:
    col_type = type(col.type).__name__
    if col_type == "Enum":
        col.type = String(100)

for col in models.EquipmentSlot.__table__.columns:
    col_type = type(col.type).__name__
    if col_type == "Enum":
        col.type = String(100)

for col in models.TradeOffer.__table__.columns:
    col_type = type(col.type).__name__
    if col_type == "Enum":
        col.type = String(100)

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


def get_db():
    db = _TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Cross-service shared tables ──────────────────────────────────────────
# These tables physically live in other services (locations-service, battle-service,
# user-service) but inventory-service queries them via raw SQL through the shared
# MySQL DB. They are NOT in inventory-service's Base.metadata, so we manage them
# manually here:
# - Created once per test (so any test path that calls is_character_gathering /
#   is_character_in_battle / verify_character_ownership doesn't fail with
#   "no such table"), regardless of whether the test seeds rows into them.
# - Dropped on teardown so leftover rows from one test never leak into the next
#   (e.g. test_battle_lock.py inserts a battle row that previously survived into
#   test_gathering.py and made the wrong "во время боя" check fire).
_CROSS_SERVICE_TABLE_DDL = [
    # gathering_sessions — owned by locations-service (FEAT-128)
    """CREATE TABLE gathering_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        character_id INTEGER NOT NULL,
        node_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        started_at TIMESTAMP,
        complete_at TIMESTAMP,
        stamina_paid INTEGER DEFAULT 0
    )""",
    # battles + battle_participants — owned by battle-service
    """CREATE TABLE battles (
        id INTEGER PRIMARY KEY,
        status TEXT DEFAULT 'in_progress'
    )""",
    """CREATE TABLE battle_participants (
        id INTEGER PRIMARY KEY,
        battle_id INTEGER,
        character_id INTEGER
    )""",
]

_CROSS_SERVICE_TABLES = ["gathering_sessions", "battle_participants", "battles"]


def _create_cross_service_tables(conn):
    for ddl in _CROSS_SERVICE_TABLE_DDL:
        conn.execute(text(ddl))


def _drop_cross_service_tables(conn):
    for tbl in _CROSS_SERVICE_TABLES:
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))


@pytest.fixture()
def db_session():
    """Yield a clean DB session; tables are created/dropped per test."""
    database.Base.metadata.create_all(bind=_test_engine)
    with _test_engine.connect() as conn:
        # Drop first to clean any leftovers from previous (failed) test runs.
        _drop_cross_service_tables(conn)
        _create_cross_service_tables(conn)
        # Register NOW() UDF on this connection for the gathering_sessions raw SQL.
        # NOTE: the StaticPool keeps a single underlying SQLite connection alive,
        # so this UDF persists for all tests in the run.
        try:
            from datetime import datetime as _dt
            conn.connection.dbapi_connection.create_function(
                "NOW", 0,
                lambda: _dt.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            )
        except Exception:
            # Older SQLAlchemy / pysqlite — fall back to .connection
            try:
                from datetime import datetime as _dt
                conn.connection.create_function(
                    "NOW", 0,
                    lambda: _dt.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                )
            except Exception:
                pass
        conn.commit()
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Disable FK checks before drop_all to avoid circular dependency errors
        # (items <-> recipes have mutual FKs via blueprint_recipe_id / result_item_id)
        with _test_engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            _drop_cross_service_tables(conn)
            conn.commit()
        database.Base.metadata.drop_all(bind=_test_engine)
        with _test_engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.commit()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with DB overridden to SQLite in-memory."""
    from main import get_db as main_get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[main_get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

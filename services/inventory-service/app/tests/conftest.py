"""
Fixtures for inventory-service tests.

Uses SQLite in-memory DB, patches config before main.py import.
"""

import sys
import os

import pytest
from sqlalchemy import create_engine, event, String
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

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


def get_db():
    db = _TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def db_session():
    """Yield a clean DB session; tables are created/dropped per test."""
    database.Base.metadata.create_all(bind=_test_engine)
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        database.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with DB overridden to SQLite in-memory."""
    from main import get_db as main_get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[main_get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

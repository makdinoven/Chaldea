"""
Tests for PUT /{character_id}/passive_experience endpoint (FEAT-095, Task #11).

Covers:
  - Adding positive amount
  - Subtracting (negative amount)
  - Subtracting more than available (400)
  - Non-existent character (404)
  - Zero amount (no change)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# SQLite test engine — must be configured before importing app modules
# ---------------------------------------------------------------------------

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

import database  # noqa: E402

database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

import auth_http  # noqa: E402
import models  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _setup_tables():
    """Create all tables before each test and drop them after."""
    models.Base.metadata.create_all(bind=_test_engine)
    yield
    models.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def db_session():
    """Yield a fresh DB session, rolled back after test."""
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    """TestClient with overridden get_db dependency."""

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_attributes(db_session, character_id=1, passive_experience=0):
    """Insert a CharacterAttributes row directly for testing."""
    row = models.CharacterAttributes(
        character_id=character_id,
        passive_experience=passive_experience,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# PUT /attributes/{character_id}/passive_experience
# ---------------------------------------------------------------------------


# FEAT-167: the mutating /attributes/ endpoints require the internal token.
INTERNAL_TOKEN = "test-internal-token"
INTERNAL_HEADERS = {"X-Internal-Token": INTERNAL_TOKEN}


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    """`auth_http` resolves the secret into a module-level constant at import
    time, so the constant is what must be pinned — `monkeypatch.setenv` alone
    would have no effect (the trap documented in FEAT-167 §2.0). conftest only
    `setdefault`s the env var, so inside a service container the real token wins
    and every request below would answer 401 without this fixture."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", INTERNAL_TOKEN)


class TestUpdatePassiveExperience:
    """Tests for the PUT passive_experience endpoint."""

    def test_add_positive_amount(self, client, db_session):
        """A) Adding a positive amount should increase passive_experience."""
        _seed_attributes(db_session, character_id=10, passive_experience=0)

        resp = client.put(
            "/attributes/10/passive_experience",
            json={"amount": 3},
            headers=INTERNAL_HEADERS,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["passive_experience"] == 3

    def test_add_negative_amount_subtract(self, client, db_session):
        """B) Adding a negative amount should decrease passive_experience."""
        _seed_attributes(db_session, character_id=20, passive_experience=10)

        resp = client.put(
            "/attributes/20/passive_experience",
            json={"amount": -2},
            headers=INTERNAL_HEADERS,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["passive_experience"] == 8

    def test_subtract_more_than_available_returns_400(self, client, db_session):
        """C) Subtracting more than available should return 400."""
        _seed_attributes(db_session, character_id=30, passive_experience=5)

        resp = client.put(
            "/attributes/30/passive_experience",
            json={"amount": -10},
            headers=INTERNAL_HEADERS,
        )

        assert resp.status_code == 400
        assert "negative" in resp.json()["detail"].lower()

    def test_nonexistent_character_returns_404(self, client):
        """D) PUT for a non-existent character_id should return 404."""
        resp = client.put(
            "/attributes/99999/passive_experience",
            json={"amount": 5},
            headers=INTERNAL_HEADERS,
        )

        assert resp.status_code == 404

    def test_zero_amount_no_change(self, client, db_session):
        """E) Zero amount should return 200 with value unchanged."""
        _seed_attributes(db_session, character_id=40, passive_experience=7)

        resp = client.put(
            "/attributes/40/passive_experience",
            json={"amount": 0},
            headers=INTERNAL_HEADERS,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["passive_experience"] == 7

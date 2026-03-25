"""
Tests for cumulative stats endpoints and CRUD logic (FEAT-078, Task #10).

Covers:
  - GET /attributes/{character_id}/cumulative_stats
  - POST /attributes/cumulative_stats/increment
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
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


@event.listens_for(_test_engine, "connect")
def _register_greatest(dbapi_conn, connection_record):
    """Register GREATEST() for SQLite (MySQL built-in, absent in SQLite)."""
    dbapi_conn.create_function("GREATEST", 2, lambda a, b: max(a, b))


_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

import database  # noqa: E402

database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

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


def _seed_cumulative_row(db_session, character_id=1, **overrides):
    """Insert a CharacterCumulativeStats row directly for testing."""
    row = models.CharacterCumulativeStats(character_id=character_id, **overrides)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# GET /attributes/{character_id}/cumulative_stats
# ---------------------------------------------------------------------------


class TestGetCumulativeStats:
    """Tests for the GET endpoint."""

    def test_returns_zeros_when_no_row_exists(self, client):
        """When no cumulative stats row exists, return all zeros."""
        resp = client.get("/attributes/999/cumulative_stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_id"] == 999
        assert data["total_damage_dealt"] == 0
        assert data["pvp_wins"] == 0
        assert data["total_battles"] == 0
        assert data["max_damage_single_battle"] == 0
        assert data["total_gold_earned"] == 0
        assert data["locations_visited"] == 0
        assert data["skills_used"] == 0

    def test_returns_existing_data(self, client, db_session):
        """When a row exists, return its actual values."""
        _seed_cumulative_row(
            db_session,
            character_id=1,
            total_damage_dealt=5000,
            pvp_wins=10,
            total_battles=20,
        )
        resp = client.get("/attributes/1/cumulative_stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_id"] == 1
        assert data["total_damage_dealt"] == 5000
        assert data["pvp_wins"] == 10
        assert data["total_battles"] == 20
        # Fields not set should still be 0
        assert data["pve_kills"] == 0


# ---------------------------------------------------------------------------
# POST /attributes/cumulative_stats/increment
# ---------------------------------------------------------------------------


@patch("perk_evaluator.evaluate_perks", return_value=[])
class TestIncrementCumulativeStats:
    """Tests for the POST increment endpoint."""

    def test_creates_row_lazily(self, _mock_eval, client, db_session):
        """First increment for a new character_id should create the row."""
        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 42,
                "increments": {"total_battles": 1},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "Stats updated"
        assert "newly_unlocked_perks" in data

        # Verify the row was created
        row = (
            db_session.query(models.CharacterCumulativeStats)
            .filter_by(character_id=42)
            .first()
        )
        assert row is not None
        assert row.total_battles == 1

    def test_increments_atomically(self, _mock_eval, client, db_session):
        """Incrementing an existing row should add to the current value."""
        _seed_cumulative_row(db_session, character_id=1, pvp_wins=5)

        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 1,
                "increments": {"pvp_wins": 3},
            },
        )
        assert resp.status_code == 200

        db_session.expire_all()
        row = (
            db_session.query(models.CharacterCumulativeStats)
            .filter_by(character_id=1)
            .first()
        )
        assert row.pvp_wins == 8

    def test_set_max_updates_when_greater(self, _mock_eval, client, db_session):
        """set_max should update the field when the new value exceeds the current."""
        _seed_cumulative_row(
            db_session, character_id=1, max_damage_single_battle=100
        )

        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 1,
                "increments": {},
                "set_max": {"max_damage_single_battle": 500},
            },
        )
        assert resp.status_code == 200

        db_session.expire_all()
        row = (
            db_session.query(models.CharacterCumulativeStats)
            .filter_by(character_id=1)
            .first()
        )
        assert row.max_damage_single_battle == 500

    def test_set_max_does_not_decrease(self, _mock_eval, client, db_session):
        """set_max should NOT decrease an existing value."""
        _seed_cumulative_row(
            db_session, character_id=1, max_damage_single_battle=500
        )

        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 1,
                "increments": {},
                "set_max": {"max_damage_single_battle": 100},
            },
        )
        assert resp.status_code == 200

        db_session.expire_all()
        row = (
            db_session.query(models.CharacterCumulativeStats)
            .filter_by(character_id=1)
            .first()
        )
        assert row.max_damage_single_battle == 500

    def test_invalid_increment_field_rejected(self, _mock_eval, client):
        """Invalid column names in 'increments' should be rejected with 400."""
        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 1,
                "increments": {"nonexistent_field": 10},
            },
        )
        assert resp.status_code == 400
        assert "nonexistent_field" in resp.json()["detail"]

    def test_invalid_set_max_field_rejected(self, _mock_eval, client):
        """Invalid column names in 'set_max' should be rejected with 400."""
        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 1,
                "increments": {},
                "set_max": {"bogus_column": 99},
            },
        )
        assert resp.status_code == 400
        assert "bogus_column" in resp.json()["detail"]

    def test_multiple_fields_in_one_request(self, _mock_eval, client, db_session):
        """Multiple fields can be incremented in a single request."""
        _seed_cumulative_row(
            db_session,
            character_id=1,
            total_damage_dealt=100,
            total_battles=5,
            pvp_wins=2,
        )

        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 1,
                "increments": {
                    "total_damage_dealt": 50,
                    "total_battles": 1,
                    "pvp_wins": 1,
                },
            },
        )
        assert resp.status_code == 200

        db_session.expire_all()
        row = (
            db_session.query(models.CharacterCumulativeStats)
            .filter_by(character_id=1)
            .first()
        )
        assert row.total_damage_dealt == 150
        assert row.total_battles == 6
        assert row.pvp_wins == 3

    def test_response_includes_newly_unlocked_perks(self, _mock_eval, client):
        """Response should always contain 'newly_unlocked_perks' key."""
        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 1,
                "increments": {"total_battles": 1},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "newly_unlocked_perks" in data
        assert isinstance(data["newly_unlocked_perks"], list)

    def test_increment_and_set_max_in_same_request(
        self, _mock_eval, client, db_session
    ):
        """Both increments and set_max can be used in the same request."""
        _seed_cumulative_row(
            db_session,
            character_id=1,
            total_damage_dealt=200,
            max_damage_single_battle=150,
        )

        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 1,
                "increments": {"total_damage_dealt": 300},
                "set_max": {"max_damage_single_battle": 400},
            },
        )
        assert resp.status_code == 200

        db_session.expire_all()
        row = (
            db_session.query(models.CharacterCumulativeStats)
            .filter_by(character_id=1)
            .first()
        )
        assert row.total_damage_dealt == 500
        assert row.max_damage_single_battle == 400

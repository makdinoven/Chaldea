"""
Tests for title evaluation trigger in increment_cumulative_stats (FEAT-080, Task #14).

Verifies that after cumulative stats are updated, the endpoint makes an HTTP POST
to character-service /characters/internal/evaluate-titles with the correct character_id.
The call must be non-fatal: if it fails, stats are still saved.
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
# Tests: Title evaluation trigger in increment_cumulative_stats
# ---------------------------------------------------------------------------


@patch("perk_evaluator.evaluate_perks", return_value=[])
class TestTitleEvaluationTrigger:
    """Tests that increment_cumulative_stats triggers title evaluation via HTTP."""

    @patch("main.httpx.post")
    def test_title_evaluation_trigger_is_called(
        self, mock_httpx_post, _mock_eval, client
    ):
        """After stats increment, httpx.post should be called to evaluate titles."""
        mock_httpx_post.return_value = MagicMock(status_code=200)

        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 7,
                "increments": {"total_battles": 1},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Stats updated"

        # Verify httpx.post was called for title evaluation
        mock_httpx_post.assert_called_once()
        call_args = mock_httpx_post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "/characters/internal/evaluate-titles" in url

    @patch("main.httpx.post")
    def test_title_evaluation_passes_correct_character_id(
        self, mock_httpx_post, _mock_eval, client
    ):
        """The title evaluation call must include the correct character_id in JSON body."""
        mock_httpx_post.return_value = MagicMock(status_code=200)

        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 42,
                "increments": {"pvp_wins": 1},
            },
        )
        assert resp.status_code == 200

        mock_httpx_post.assert_called_once()
        call_args = mock_httpx_post.call_args
        # json= keyword argument should contain character_id
        json_body = call_args[1].get("json", {})
        assert json_body["character_id"] == 42

    @patch("main.httpx.post")
    def test_title_evaluation_failure_is_non_fatal(
        self, mock_httpx_post, _mock_eval, client, db_session
    ):
        """If title evaluation HTTP call raises, the endpoint still succeeds."""
        mock_httpx_post.side_effect = Exception("Connection refused")

        resp = client.post(
            "/attributes/cumulative_stats/increment",
            json={
                "character_id": 99,
                "increments": {"total_battles": 1, "total_damage_dealt": 500},
            },
        )
        # Endpoint must still return 200 — title evaluation is non-fatal
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Stats updated"

        # Verify stats were actually saved despite title evaluation failure
        row = (
            db_session.query(models.CharacterCumulativeStats)
            .filter_by(character_id=99)
            .first()
        )
        assert row is not None
        assert row.total_battles == 1
        assert row.total_damage_dealt == 500

    @patch("main.httpx.post")
    def test_title_evaluation_error_is_logged(
        self, mock_httpx_post, _mock_eval, client, caplog
    ):
        """When title evaluation fails, the error should be logged."""
        mock_httpx_post.side_effect = Exception("Connection refused")

        import logging

        with caplog.at_level(logging.ERROR):
            resp = client.post(
                "/attributes/cumulative_stats/increment",
                json={
                    "character_id": 55,
                    "increments": {"total_battles": 1},
                },
            )
        assert resp.status_code == 200

        # Verify error was logged
        title_error_logs = [
            r for r in caplog.records if "Title evaluation error" in r.message
        ]
        assert len(title_error_logs) >= 1
        assert "55" in title_error_logs[0].message

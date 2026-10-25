"""
Fixtures for locations-service tests.

Adds the app directory to sys.path so bare imports work.
Patches the async engine/session so tests don't need a real MySQL connection.
"""

import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add the app directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set DB env vars BEFORE importing config/database — Pydantic BaseSettings
# requires DB_HOST, DB_USERNAME, DB_PASSWORD, DB_DATABASE (no defaults).
# The actual MySQL URL is never used because we patch database.engine below.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

# Patch the async engine before importing main to avoid MySQL connection on startup
import database  # noqa: E402

_orig_engine = database.engine

# Create a mock engine whose begin() returns an async context manager
_mock_engine = MagicMock()
_mock_conn = AsyncMock()
_mock_conn.run_sync = AsyncMock()

_mock_cm = AsyncMock()
_mock_cm.__aenter__ = AsyncMock(return_value=_mock_conn)
_mock_cm.__aexit__ = AsyncMock(return_value=False)
_mock_engine.begin = MagicMock(return_value=_mock_cm)

database.engine = _mock_engine

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from database import get_db  # noqa: E402


async def _fake_get_db():
    yield MagicMock()


@pytest.fixture()
def client():
    """FastAPI TestClient with async DB overridden to a mock."""
    app.dependency_overrides[get_db] = _fake_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# FEAT-175 activity lock. The lock lives in two `characters` columns owned by
# character-service; most tests here run against mocked DBs or hand-written
# table mirrors that don't carry them. Default: "not locked". Tests that
# exercise the real query opt out with @pytest.mark.real_activity_lock
# (see test_activity_lock.py).
# ---------------------------------------------------------------------------

import activity_lock as _activity_lock  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_activity_lock: run the real FEAT-175 activity-lock query",
    )


@pytest.fixture(autouse=True)
def _activity_lock_default_unlocked(request, monkeypatch):
    if request.node.get_closest_marker("real_activity_lock"):
        return

    async def _unlocked(db, character_id):
        return _activity_lock.compute_lock(None, None)

    monkeypatch.setattr(_activity_lock, "get_activity_lock", _unlocked)

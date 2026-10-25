"""
Fixtures for battle-service tests.

Sets required environment variables and patches the async database engine
before any service module is imported, preventing MySQL/Redis/Mongo connections.
"""

import os
import sys

# Set DB env vars BEFORE importing config/database — they have no defaults.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

# Add the app directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, AsyncMock  # noqa: E402

# Patch the async engine before importing main
import database  # noqa: E402

_mock_engine = MagicMock()
_mock_conn = AsyncMock()
_mock_conn.run_sync = AsyncMock()
_mock_cm = AsyncMock()
_mock_cm.__aenter__ = AsyncMock(return_value=_mock_conn)
_mock_cm.__aexit__ = AsyncMock(return_value=False)
_mock_engine.begin = MagicMock(return_value=_mock_cm)
database.engine = _mock_engine


# ---------------------------------------------------------------------------
# FEAT-175 activity lock. The lock lives in two `characters` columns owned by
# character-service; the mocked DBs in this suite don't model them. Default:
# "not locked" and "not a dungeon battle". Tests that exercise the real query
# opt out with @pytest.mark.real_activity_lock (see test_activity_lock.py).
# ---------------------------------------------------------------------------

import pytest  # noqa: E402
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

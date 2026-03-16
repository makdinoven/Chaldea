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

"""
Fixtures for photo-service tests.

Adds the photo-service root to sys.path so bare imports work.
Patches external dependencies (S3, DB) so tests run in isolation.
"""

import sys
import os
from unittest.mock import MagicMock

# Add the photo-service directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set required env vars before importing app modules (config.py reads them at import time)
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_DATABASE", "testdb")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from database import get_db  # noqa: E402
from main import app  # noqa: E402

_mock_session = MagicMock()


def _override_get_db():
    yield _mock_session


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture()
def client():
    """FastAPI TestClient for photo-service."""
    with TestClient(app) as c:
        yield c

"""
Fixtures for photo-service tests.

Adds the photo-service root to sys.path so bare imports work.
Patches external dependencies (S3, DB) so tests run in isolation.
"""

import sys
import os

# Add the photo-service directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture()
def client():
    """FastAPI TestClient for photo-service."""
    with TestClient(app) as c:
        yield c

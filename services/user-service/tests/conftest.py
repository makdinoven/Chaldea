"""
Fixtures for user-service tests.

Uses SQLite in-memory DB, mocks external services (RabbitMQ, httpx).
"""

import sys
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Add the service root to sys.path so bare imports (models, crud, etc.) work.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# We must set JWT_SECRET_KEY before importing auth.py (it reads os.environ on import).
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-tests")

from database import Base, get_db  # noqa: E402
from main import app  # noqa: E402

# ── SQLite in-memory engine ──────────────────────────────────────────────
_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


@pytest.fixture()
def test_engine():
    """Expose the in-memory SQLite engine for tests that need it directly."""
    return _test_engine


@pytest.fixture()
def test_session_local():
    """Expose the sessionmaker factory for tests that need it directly."""
    return _TestSessionLocal


@pytest.fixture()
def db_session():
    """Yield a clean DB session; tables are created/dropped per test."""
    Base.metadata.create_all(bind=_test_engine)
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with DB overridden to SQLite in-memory."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

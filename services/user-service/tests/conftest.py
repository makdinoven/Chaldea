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

# Pydantic v1/v2 compatibility: config.py uses `from pydantic import BaseSettings`
# which works in Pydantic v1 but was moved to pydantic-settings in v2.
# This shim ensures tests work in both environments.
try:
    from pydantic import BaseSettings  # noqa: F401 — Pydantic v1, nothing to do
except ImportError:
    try:
        from pydantic_settings import BaseSettings as _BS  # noqa: F401
        import pydantic as _pydantic
        _pydantic.BaseSettings = _BS
    except ImportError:
        # Pydantic v2 without pydantic-settings: provide a minimal BaseSettings shim.
        import pydantic as _pydantic

        class _BaseSettings(_pydantic.BaseModel):
            """Minimal BaseSettings shim for Pydantic v2 test environments."""

            def __init__(self, **kwargs):
                # Read values from env vars (matching Pydantic v1 BaseSettings behavior)
                for field_name in self.model_fields:
                    if field_name not in kwargs:
                        env_val = os.environ.get(field_name)
                        if env_val is not None:
                            kwargs[field_name] = env_val
                super().__init__(**kwargs)

        _pydantic.BaseSettings = _BaseSettings

# Set DB env vars BEFORE importing config/database — Pydantic BaseSettings
# requires DB_HOST, DB_USERNAME, DB_PASSWORD, DB_DATABASE (no defaults).
# The actual MySQL URL is never used because tests override get_db with SQLite.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

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

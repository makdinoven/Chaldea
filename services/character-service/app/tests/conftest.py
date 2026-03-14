import sys
import os

# Add the app directory to sys.path so that bare imports (models, crud, etc.) work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Patch database.engine BEFORE importing main.py
# main.py calls models.Base.metadata.create_all(bind=engine) at module level,
# which would try to connect to MySQL. We replace the engine with a SQLite
# in-memory engine so tests can run without a real database.
# ---------------------------------------------------------------------------
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

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

# NOW it is safe to import main — create_all will use the SQLite engine
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from main import app, get_db  # noqa: E402


@pytest.fixture
def mock_db_session():
    """Create a mock DB session to avoid real database connections."""
    session = MagicMock()
    return session


@pytest.fixture
def client(mock_db_session):
    """
    FastAPI TestClient with overridden get_db dependency.
    Uses a mock session so no real DB is needed.
    """
    def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

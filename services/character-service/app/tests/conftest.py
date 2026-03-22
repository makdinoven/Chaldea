import sys
import os

# Add the app directory to sys.path so that bare imports (models, crud, etc.) work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set DB env vars BEFORE importing config/database — Pydantic BaseSettings
# requires DB_HOST, DB_USERNAME, DB_PASSWORD, DB_DATABASE (no defaults).
# The actual MySQL URL is never used because we patch database.engine below.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

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

import models  # noqa: E402
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead  # noqa: E402
from main import app, get_db  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helper: seed FK reference data (races, subraces, classes)
# ---------------------------------------------------------------------------

def _seed_reference_data(session):
    """Insert minimal races, subraces and classes required by FK constraints.

    Must be called AFTER ``Base.metadata.create_all()`` and BEFORE any test
    that inserts into ``character_requests`` or ``characters``.
    Idempotent: skips rows that already exist.
    """
    # Races
    for rid, name in [(1, "Человек"), (2, "Эльф"), (3, "Драконид"),
                      (4, "Дворф"), (5, "Демон"), (6, "Бистмен"), (7, "Урук")]:
        if not session.query(models.Race).filter_by(id_race=rid).first():
            session.add(models.Race(id_race=rid, name=name))
    session.flush()

    # Subraces
    subraces = [
        (1, 1, "Норд"), (2, 1, "Ост"), (3, 1, "Ориентал"),
        (4, 2, "Лесной"), (5, 2, "Темный"), (6, 2, "Малах"),
        (7, 3, "Равагарт"), (8, 3, "Рорис"),
        (9, 4, "Золотой"), (10, 4, "Ониксовый"),
        (11, 5, "Левиаан"), (12, 5, "Альб"),
        (13, 6, "Зверолюд"), (14, 6, "Полукровка"),
        (15, 7, "Северные"), (16, 7, "Темный урук"),
    ]
    for sid, rid, name in subraces:
        if not session.query(models.Subrace).filter_by(id_subrace=sid).first():
            session.add(models.Subrace(id_subrace=sid, id_race=rid, name=name))
    session.flush()

    # Classes
    for cid, name in [(1, "Воин"), (2, "Плут"), (3, "Маг")]:
        if not session.query(models.Class).filter_by(id_class=cid).first():
            session.add(models.Class(id_class=cid, name=name))
    session.commit()


@pytest.fixture
def seed_fk_data():
    """Return the seed function so test files can call it on their own session."""
    return _seed_reference_data


# ---------------------------------------------------------------------------
# Shared admin user constant for test fixtures
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve",
    ],
)


@pytest.fixture
def test_engine():
    """Expose the in-memory SQLite engine for tests that need direct access."""
    return _test_engine


@pytest.fixture
def test_session_factory():
    """Expose the test SessionLocal factory for tests that need direct access."""
    return _TestSessionLocal


@pytest.fixture
def mock_db_session():
    """Create a mock DB session to avoid real database connections."""
    session = MagicMock()
    # Default: character count check returns 0 (under limit)
    session.execute.return_value.scalar.return_value = 0
    return session


@pytest.fixture
def client(mock_db_session):
    """
    FastAPI TestClient with overridden get_db dependency.
    Uses a mock session so no real DB is needed.
    Does NOT override auth — used by tests that verify auth behaviour.
    """
    def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_mock_client(mock_db_session):
    """
    FastAPI TestClient with overridden get_db AND admin auth.
    Uses a mock session. Suitable for tests that need to bypass auth.
    """
    def override_get_db():
        yield mock_db_session

    def override_admin():
        return _ADMIN_USER

    def override_token():
        return "fake-admin-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    app.dependency_overrides[OAUTH2_SCHEME] = override_token
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()

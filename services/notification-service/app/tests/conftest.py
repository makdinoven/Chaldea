"""
Fixtures for notification-service tests.

Uses SQLite in-memory DB, mocks RabbitMQ consumers and auth dependency.
"""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# ── Set DB env vars BEFORE any app module import ─────────────────────────
# notification-service database.py reads individual DB_* vars via os.environ
# and falls back to DATABASE_URL. Set both so the SQLite override works.
os.environ["DB_HOST"] = "localhost"
os.environ["DB_USERNAME"] = "testuser"
os.environ["DB_PASSWORD"] = "testpass"
os.environ["DB_DATABASE"] = "testdb"
os.environ["DATABASE_URL"] = "sqlite://"

# ── Patch consumers BEFORE importing main.py ────────────────────────────
# main.py calls start_user_registration_consumer() and
# start_general_notifications_consumer() at module level during startup,
# which require a live RabbitMQ connection. We mock them out.
sys.modules.setdefault("pika", MagicMock())

# Ensure app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import Base, engine, get_db  # noqa: E402
from auth_http import UserRead  # noqa: E402

# ── Use the engine from database.py (now SQLite via env var) ─────────────
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# SQLite does not support MySQL ENUM columns. We monkey-patch the model's
# status column to use plain String before creating tables.
from models import Notification as NotificationModel  # noqa: E402
from chat_models import ChatMessage as ChatMessageModel  # noqa: E402

NotificationModel.__table__.c.status.type = String(10)
ChatMessageModel.__table__.c.channel.type = String(20)

# Ticket models also use MySQL ENUM columns that need patching for SQLite
from ticket_models import SupportTicket as TicketModel  # noqa: E402

TicketModel.__table__.c.category.type = String(20)
TicketModel.__table__.c.status.type = String(20)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture()
def db_session():
    """Yield a clean DB session; tables are created/dropped per test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _make_user(user_id: int = 1, username: str = "testuser", role: str = "user", permissions: list = None):
    """Helper: build a UserRead instance with given attributes."""
    return UserRead(id=user_id, username=username, role=role, permissions=permissions or [])


@pytest.fixture()
def test_user():
    """A regular (non-admin) user."""
    return _make_user(user_id=1, username="testuser", role="user")


@pytest.fixture()
def admin_user():
    """An admin user."""
    return _make_user(user_id=99, username="admin", role="admin", permissions=[
        "notifications:create", "notifications:read", "notifications:update", "notifications:delete",
        "chat:delete", "chat:ban",
    ])


@pytest.fixture()
def moderator_user():
    """A moderator user with chat moderation permissions."""
    return _make_user(user_id=50, username="moderator", role="moderator", permissions=[
        "chat:delete", "chat:ban",
    ])


@pytest.fixture()
def client(db_session, test_user):
    """
    FastAPI TestClient with:
    - DB overridden to SQLite in-memory session
    - Auth overridden to return test_user (role=user)
    - RabbitMQ consumers mocked
    """
    from auth_http import get_current_user_via_http
    from main import app

    def override_get_db():
        yield db_session

    def override_auth():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_auth
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_client(db_session, admin_user):
    """
    FastAPI TestClient authenticated as admin.
    """
    from auth_http import get_current_user_via_http
    from main import app

    def override_get_db():
        yield db_session

    def override_auth():
        return admin_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_auth
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def moderator_client(db_session, moderator_user):
    """
    FastAPI TestClient authenticated as moderator (has chat:delete, chat:ban).
    """
    from auth_http import get_current_user_via_http
    from main import app

    def override_get_db():
        yield db_session

    def override_auth():
        return moderator_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_auth
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def ticket_admin_user():
    """An admin user with ticket permissions."""
    return _make_user(user_id=99, username="admin", role="admin", permissions=[
        "notifications:create", "notifications:read", "notifications:update", "notifications:delete",
        "chat:delete", "chat:ban",
        "tickets:read", "tickets:reply", "tickets:manage",
    ])


class _TicketTestHelper:
    """Helper that provides a single TestClient with switchable auth identity.

    Because FastAPI's dependency_overrides is a global dict on the app,
    using two separate client fixtures in the same test causes the second
    to overwrite the first.  This helper keeps one TestClient and lets tests
    switch between user and admin identities on the fly.
    """

    def __init__(self, app, db_session, user, admin):
        self._app = app
        self._db_session = db_session
        self._user = user
        self._admin = admin
        self._current = user
        self._setup_overrides()
        self.client = TestClient(app)

    # ---- public API --------------------------------------------------
    def as_user(self):
        """Switch auth to regular user."""
        self._current = self._user
        self._update_auth()
        return self.client

    def as_admin(self):
        """Switch auth to admin with ticket permissions."""
        self._current = self._admin
        self._update_auth()
        return self.client

    # ---- internal ----------------------------------------------------
    def _setup_overrides(self):
        from auth_http import get_current_user_via_http
        def override_get_db():
            yield self._db_session
        self._app.dependency_overrides[get_db] = override_get_db
        self._update_auth()

    def _update_auth(self):
        from auth_http import get_current_user_via_http
        current = self._current
        self._app.dependency_overrides[get_current_user_via_http] = lambda: current

    def cleanup(self):
        self._app.dependency_overrides.clear()


@pytest.fixture()
def ticket_helper(db_session, test_user, ticket_admin_user):
    """Provides a _TicketTestHelper with switchable user/admin auth."""
    from main import app
    helper = _TicketTestHelper(app, db_session, test_user, ticket_admin_user)
    yield helper
    helper.cleanup()


@pytest.fixture()
def ticket_client(ticket_helper):
    """Convenience: TestClient authenticated as regular user (for ticket tests)."""
    return ticket_helper.as_user()


@pytest.fixture()
def ticket_admin_client(ticket_helper):
    """Convenience: TestClient authenticated as admin with ticket permissions."""
    return ticket_helper.as_admin()


@pytest.fixture()
def seed_notifications(db_session):
    """Insert a handful of notifications for user_id=1."""
    from models import Notification
    from datetime import datetime

    items = [
        Notification(user_id=1, message="First unread", status="unread", created_at=datetime(2026, 1, 1, 10, 0)),
        Notification(user_id=1, message="Second unread", status="unread", created_at=datetime(2026, 1, 1, 11, 0)),
        Notification(user_id=1, message="Already read", status="read", created_at=datetime(2026, 1, 1, 9, 0)),
        Notification(user_id=2, message="Other user", status="unread", created_at=datetime(2026, 1, 1, 12, 0)),
    ]
    db_session.add_all(items)
    db_session.commit()
    for n in items:
        db_session.refresh(n)
    return items

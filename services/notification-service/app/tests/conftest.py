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

# ── Patch consumers BEFORE importing main.py ────────────────────────────
# main.py calls start_user_registration_consumer() and
# start_general_notifications_consumer() at module level during startup,
# which require a live RabbitMQ connection. We mock them out.
sys.modules.setdefault("pika", MagicMock())

# Ensure app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import Base, get_db  # noqa: E402
from auth_http import UserRead  # noqa: E402

# ── SQLite in-memory engine ──────────────────────────────────────────────
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# SQLite does not support MySQL ENUM columns. We monkey-patch the model's
# status column to use plain String before creating tables.
from models import Notification as NotificationModel  # noqa: E402

NotificationModel.__table__.c.status.type = String(10)


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


def _make_user(user_id: int = 1, username: str = "testuser", role: str = "user"):
    """Helper: build a UserRead instance with given attributes."""
    user = UserRead()
    user.id = user_id
    user.username = username
    user.role = role
    return user


@pytest.fixture()
def test_user():
    """A regular (non-admin) user."""
    return _make_user(user_id=1, username="testuser", role="user")


@pytest.fixture()
def admin_user():
    """An admin user."""
    return _make_user(user_id=99, username="admin", role="admin")


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

"""
FEAT-028 Task #3 — Tests for login authentication, password hashing,
config settings, and database URL construction.

Covers:
1. Password hashing/verification with pinned bcrypt==3.2.2 + passlib==1.7.4
2. Config reads env vars correctly with proper defaults
3. Database URL is built correctly from settings
4. Login endpoint returns 200/401 as expected
"""

import os
import sys
import importlib
from unittest.mock import patch

import pytest

# conftest.py already adds the service root to sys.path and sets JWT_SECRET_KEY.

from crud import pwd_context, authenticate_user, create_user
from schemas import UserCreate
import models


# ---------------------------------------------------------------------------
# 1. Password hashing / verification (root cause validation)
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    """Verify that passlib CryptContext + bcrypt hash/verify roundtrip works.

    This is the most critical test class — it validates that the pinned
    bcrypt==3.2.2 + passlib==1.7.4 combination produces correct results.
    The original bug was pwd_context.verify() silently returning False
    due to bcrypt 4.0.x incompatibility.
    """

    def test_hash_and_verify_correct_password(self):
        """Hash a password and verify it succeeds with the same password."""
        password = "MySecretPassword123!"
        hashed = pwd_context.hash(password)

        assert hashed is not None
        assert hashed != password
        assert pwd_context.verify(password, hashed) is True

    def test_verify_wrong_password_fails(self):
        """Verify returns False for an incorrect password."""
        password = "CorrectPassword"
        wrong = "WrongPassword"
        hashed = pwd_context.hash(password)

        assert pwd_context.verify(wrong, hashed) is False

    def test_hash_produces_bcrypt_format(self):
        """Hash output must be a bcrypt $2b$ hash."""
        hashed = pwd_context.hash("test")
        assert hashed.startswith("$2b$")

    def test_different_hashes_for_same_password(self):
        """Two calls to hash() with the same password produce different salts."""
        h1 = pwd_context.hash("same")
        h2 = pwd_context.hash("same")
        assert h1 != h2
        # Both must still verify
        assert pwd_context.verify("same", h1) is True
        assert pwd_context.verify("same", h2) is True

    def test_empty_password_hashes_and_verifies(self):
        """Edge case: empty string password should still hash and verify."""
        hashed = pwd_context.hash("")
        assert pwd_context.verify("", hashed) is True
        assert pwd_context.verify("notempty", hashed) is False

    def test_unicode_password(self):
        """Unicode characters in password must hash and verify correctly."""
        password = "\u041f\u0430\u0440\u043e\u043b\u044c123\u2603"
        hashed = pwd_context.hash(password)
        assert pwd_context.verify(password, hashed) is True
        assert pwd_context.verify("wrong", hashed) is False


# ---------------------------------------------------------------------------
# 2. Config settings
# ---------------------------------------------------------------------------

class TestConfig:
    """Verify Settings class reads env vars and has correct defaults."""

    def test_default_values(self):
        """Settings must have sensible defaults matching docker-compose values."""
        from config import Settings

        # Remove DB env vars so defaults are used
        env_clean = {
            k: v for k, v in os.environ.items()
            if k not in ("DB_HOST", "DB_PORT", "DB_USERNAME", "DB_PASSWORD", "DB_DATABASE")
        }
        with patch.dict(os.environ, env_clean, clear=True):
            s = Settings()
            assert s.DB_HOST == "mysql"
            assert s.DB_PORT == 3306
            assert s.DB_USERNAME == "myuser"
            assert s.DB_PASSWORD == "mypassword"
            assert s.DB_DATABASE == "mydatabase"

    def test_env_vars_override_defaults(self):
        """Settings must pick up env var overrides."""
        from config import Settings

        custom_env = {
            "DB_HOST": "custom-host",
            "DB_PORT": "5432",
            "DB_USERNAME": "customuser",
            "DB_PASSWORD": "custompass",
            "DB_DATABASE": "customdb",
        }
        with patch.dict(os.environ, custom_env):
            s = Settings()
            assert s.DB_HOST == "custom-host"
            assert s.DB_PORT == 5432
            assert s.DB_USERNAME == "customuser"
            assert s.DB_PASSWORD == "custompass"
            assert s.DB_DATABASE == "customdb"


# ---------------------------------------------------------------------------
# 3. Database URL construction
# ---------------------------------------------------------------------------

class TestDatabaseURL:
    """Verify SQLALCHEMY_DATABASE_URL is built correctly from settings."""

    def test_url_contains_settings_values(self):
        """The module-level URL must reflect the config settings."""
        from database import SQLALCHEMY_DATABASE_URL
        from config import settings

        # Verify the URL is built from settings (not hardcoded)
        assert settings.DB_USERNAME in SQLALCHEMY_DATABASE_URL
        assert settings.DB_PASSWORD in SQLALCHEMY_DATABASE_URL
        assert settings.DB_HOST in SQLALCHEMY_DATABASE_URL
        assert str(settings.DB_PORT) in SQLALCHEMY_DATABASE_URL
        assert settings.DB_DATABASE in SQLALCHEMY_DATABASE_URL
        assert SQLALCHEMY_DATABASE_URL.startswith("mysql+pymysql://")

    def test_url_format_matches_expected_pattern(self):
        """URL format must be mysql+pymysql://user:pass@host:port/dbname."""
        from database import SQLALCHEMY_DATABASE_URL
        from config import settings

        expected = (
            f"mysql+pymysql://{settings.DB_USERNAME}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_DATABASE}"
        )
        assert SQLALCHEMY_DATABASE_URL == expected

    def test_engine_has_pool_settings(self):
        """Engine must have pool_recycle and pool_pre_ping configured."""
        from database import engine

        assert engine.pool._recycle == 3600
        assert engine.pool._pre_ping is True


# ---------------------------------------------------------------------------
# 4. authenticate_user (CRUD-level)
# ---------------------------------------------------------------------------

class TestAuthenticateUser:
    """Test authenticate_user function with real DB session (SQLite in-memory)."""

    def _create_test_user(self, db, username="testuser", email="test@example.com", password="secret123"):
        """Helper: create a user via the crud function."""
        user_data = UserCreate(email=email, username=username, password=password)
        return create_user(db, user_data)

    def test_authenticate_success_by_username(self, db_session):
        """authenticate_user returns the user when username + password are correct."""
        self._create_test_user(db_session)
        result = authenticate_user(db_session, "testuser", "secret123")
        assert result is not False
        assert result.username == "testuser"

    def test_authenticate_success_by_email(self, db_session):
        """authenticate_user returns the user when email + password are correct."""
        self._create_test_user(db_session)
        result = authenticate_user(db_session, "test@example.com", "secret123")
        assert result is not False
        assert result.email == "test@example.com"

    def test_authenticate_wrong_password(self, db_session):
        """authenticate_user returns False for wrong password."""
        self._create_test_user(db_session)
        result = authenticate_user(db_session, "testuser", "wrongpassword")
        assert result is False

    def test_authenticate_nonexistent_user(self, db_session):
        """authenticate_user returns False for a user that doesn't exist."""
        result = authenticate_user(db_session, "nobody", "whatever")
        assert result is False

    def test_authenticate_empty_password(self, db_session):
        """authenticate_user with empty password fails if user was created with a real password."""
        self._create_test_user(db_session)
        result = authenticate_user(db_session, "testuser", "")
        assert result is False


# ---------------------------------------------------------------------------
# 5. Login endpoint (integration)
# ---------------------------------------------------------------------------

class TestLoginEndpoint:
    """Integration tests for POST /users/login."""

    def _register_user(self, db, username="player1", email="player1@example.com", password="GoodPassword1"):
        """Helper: insert a user with a properly hashed password."""
        user_data = UserCreate(email=email, username=username, password=password)
        return create_user(db, user_data)

    @patch("main.send_notification_event")
    def test_login_success_returns_tokens(self, mock_notify, client, db_session):
        """POST /users/login with valid credentials returns 200 and tokens."""
        self._register_user(db_session)
        response = client.post("/users/login", json={
            "identifier": "player1",
            "password": "GoodPassword1",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @patch("main.send_notification_event")
    def test_login_with_email(self, mock_notify, client, db_session):
        """POST /users/login with email as identifier returns 200."""
        self._register_user(db_session)
        response = client.post("/users/login", json={
            "identifier": "player1@example.com",
            "password": "GoodPassword1",
        })
        assert response.status_code == 200

    @patch("main.send_notification_event")
    def test_login_wrong_password_returns_401(self, mock_notify, client, db_session):
        """POST /users/login with wrong password returns 401."""
        self._register_user(db_session)
        response = client.post("/users/login", json={
            "identifier": "player1",
            "password": "WrongPassword",
        })
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    def test_login_nonexistent_user_returns_401(self, client):
        """POST /users/login with unknown user returns 401."""
        response = client.post("/users/login", json={
            "identifier": "nobody",
            "password": "whatever",
        })
        assert response.status_code == 401

    def test_login_missing_fields_returns_422(self, client):
        """POST /users/login with missing fields returns 422 validation error."""
        response = client.post("/users/login", json={})
        assert response.status_code == 422

    @patch("main.send_notification_event")
    def test_login_sql_injection_in_identifier(self, mock_notify, client, db_session):
        """SQL injection attempt in identifier must not crash the service."""
        self._register_user(db_session)
        response = client.post("/users/login", json={
            "identifier": "'; DROP TABLE users; --",
            "password": "anything",
        })
        assert response.status_code in (401, 422)

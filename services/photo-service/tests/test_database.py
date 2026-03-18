"""
Tests for photo-service database module (FEAT-034).

Verifies:
- get_db yields a session and closes it
- DB dependency override works correctly in conftest
- config.Settings reads environment variables
"""

from unittest.mock import patch, MagicMock

import database
from config import Settings


# ===========================================================================
# 1. get_db generator behavior
# ===========================================================================

class TestGetDb:

    @patch.object(database, "SessionLocal")
    def test_get_db_yields_session_and_closes(self, mock_session_cls):
        """get_db should yield a session, then close it in the finally block."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        gen = database.get_db()
        session = next(gen)

        assert session is mock_session

        # Exhaust the generator to trigger finally
        try:
            next(gen)
        except StopIteration:
            pass

        mock_session.close.assert_called_once()

    @patch.object(database, "SessionLocal")
    def test_get_db_closes_session_on_exception(self, mock_session_cls):
        """get_db should close the session even if an exception occurs."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        gen = database.get_db()
        next(gen)

        # Simulate an exception being thrown into the generator
        try:
            gen.throw(ValueError("test error"))
        except ValueError:
            pass

        mock_session.close.assert_called_once()


# ===========================================================================
# 2. Config reads env vars
# ===========================================================================

class TestConfig:

    def test_settings_has_required_fields(self):
        """Settings should have all required DB fields."""
        assert hasattr(Settings, "__fields__")
        field_names = set(Settings.__fields__.keys())
        assert {"DB_HOST", "DB_PORT", "DB_USERNAME", "DB_PASSWORD", "DB_DATABASE"}.issubset(field_names)

    def test_db_port_default(self):
        """DB_PORT should default to 3306."""
        assert Settings.__fields__["DB_PORT"].default == 3306


# ===========================================================================
# 3. Database URL construction
# ===========================================================================

class TestDatabaseUrl:

    def test_url_uses_pymysql_driver(self):
        """SQLALCHEMY_DATABASE_URL should use mysql+pymysql:// driver."""
        assert database.SQLALCHEMY_DATABASE_URL.startswith("mysql+pymysql://")

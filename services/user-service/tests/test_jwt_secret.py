"""
Task 15 — QA for Bug #1: JWT secret key must be read from JWT_SECRET_KEY env var.

Tests:
1. SECRET_KEY reads from JWT_SECRET_KEY environment variable.
2. Missing env var raises an error at import time (fail-fast).
3. Token creation and verification work with env-configured secret.
"""

import importlib
import os
import sys
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Shared assertion: the fail-fast message must be readable, not a bare KeyError
# ---------------------------------------------------------------------------
# FEAT-169 QA #17: the point of replacing ``os.environ[...]`` was the operator
# experience — a crash-looping container whose log says *what* is wrong. A
# RuntimeError carrying only "JWT_SECRET_KEY" would be no better than the
# KeyError it replaced, so the explicit Russian sentence is part of the
# contract, not decoration.

def _assert_explicit_russian_message(exc: BaseException) -> None:
    message = str(exc)
    assert "JWT_SECRET_KEY" in message
    assert "не задан или пуст" in message, (
        f"the fail-fast message lost its explanation: {message!r}"
    )
    assert "user-service" in message
    # The remedy must be in the log too — this is what an operator acts on.
    assert ".env" in message and "openssl rand -hex 32" in message, (
        f"the fail-fast message no longer says how to fix it: {message!r}"
    )


def test_the_guard_is_a_truthiness_check_not_a_presence_check():
    """A regression guard on the *mechanism*: ``os.environ["JWT_SECRET_KEY"]``
    would accept an empty string, which is exactly what docker compose produces
    for an unset variable (``JWT_SECRET_KEY=``)."""
    import inspect

    import auth

    source = inspect.getsource(auth)
    assert 'os.environ["JWT_SECRET_KEY"]' not in source, (
        "auth.py is back to a presence check — an empty secret would sail "
        "through and user-service would sign tokens with \"\""
    )
    assert "if not SECRET_KEY" in source


# ---------------------------------------------------------------------------
# Test 1: SECRET_KEY is populated from the JWT_SECRET_KEY env var
# ---------------------------------------------------------------------------

def test_secret_key_reads_from_env():
    """auth.SECRET_KEY must equal the value of JWT_SECRET_KEY env var."""
    # conftest already sets JWT_SECRET_KEY="test-secret-key-for-tests"
    import auth

    assert auth.SECRET_KEY == os.environ["JWT_SECRET_KEY"]


def test_secret_key_reflects_custom_env_value():
    """When JWT_SECRET_KEY is changed, a fresh import of auth picks it up."""
    custom_value = "my-custom-secret-42"
    with patch.dict(os.environ, {"JWT_SECRET_KEY": custom_value}):
        # Force re-import so the module-level line re-evaluates
        if "auth" in sys.modules:
            auth_mod = importlib.reload(sys.modules["auth"])
        else:
            import auth as auth_mod

        assert auth_mod.SECRET_KEY == custom_value

    # Restore original module state for other tests
    importlib.reload(sys.modules["auth"])


# ---------------------------------------------------------------------------
# Test 2: Missing JWT_SECRET_KEY env var causes an error (fail-fast)
# ---------------------------------------------------------------------------

def test_missing_env_var_raises_error():
    """If JWT_SECRET_KEY is not set, importing auth must raise RuntimeError.

    FEAT-169: раньше это был голый ``KeyError`` без объяснения.
    """
    env_without_key = {k: v for k, v in os.environ.items() if k != "JWT_SECRET_KEY"}
    with patch.dict(os.environ, env_without_key, clear=True):
        # Remove cached module so it re-evaluates the module-level line
        saved = sys.modules.pop("auth", None)
        try:
            with pytest.raises(RuntimeError) as exc:
                importlib.import_module("auth")
            assert "JWT_SECRET_KEY" in str(exc.value)
            _assert_explicit_russian_message(exc.value)
        finally:
            # Restore the module so other tests are not affected
            if saved is not None:
                sys.modules["auth"] = saved
            else:
                sys.modules.pop("auth", None)


def test_empty_env_var_raises_error():
    """Пустая строка — не «ключ задан».

    FEAT-169: в docker compose незаданная переменная разворачивается в
    ``JWT_SECRET_KEY=`` (пустая строка), то есть ключ в окружении ПРИСУТСТВУЕТ.
    Проверка на наличие (``os.environ[...]``) такую конфигурацию пропускала, и
    сервис поднимался бы, подписывая токены пустым секретом.
    """
    with patch.dict(os.environ, {"JWT_SECRET_KEY": ""}):
        saved = sys.modules.pop("auth", None)
        try:
            with pytest.raises(RuntimeError) as exc:
                importlib.import_module("auth")
            assert "JWT_SECRET_KEY" in str(exc.value)
            _assert_explicit_russian_message(exc.value)
        finally:
            if saved is not None:
                sys.modules["auth"] = saved
            else:
                sys.modules.pop("auth", None)


# ---------------------------------------------------------------------------
# Test 3: Token creation and verification with env-configured secret
# ---------------------------------------------------------------------------

def test_create_and_decode_access_token():
    """create_access_token produces a JWT that can be decoded with the same secret."""
    from jose import jwt
    import auth

    token = auth.create_access_token(data={"sub": "user@example.com"}, role="admin")
    payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])

    assert payload["sub"] == "user@example.com"
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_create_and_decode_refresh_token():
    """create_refresh_token produces a JWT decodable with the env secret."""
    from jose import jwt
    import auth

    token = auth.create_refresh_token(data={"sub": "user@example.com"}, role="user")
    payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])

    assert payload["sub"] == "user@example.com"
    assert payload["role"] == "user"
    assert "exp" in payload


def test_token_invalid_with_wrong_secret():
    """A token created with one secret must not decode with another."""
    from jose import jwt, JWTError
    import auth

    token = auth.create_access_token(data={"sub": "a@b.com"}, role="user")

    with pytest.raises(JWTError):
        jwt.decode(token, "wrong-secret", algorithms=[auth.ALGORITHM])

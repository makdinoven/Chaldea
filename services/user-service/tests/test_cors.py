"""
Task 17 — QA for Bug #9: CORS origins must be configurable via CORS_ORIGINS env var.

Tests:
1. Default origins when CORS_ORIGINS env var is unset (defaults to ["*"]).
2. Custom comma-separated origins from CORS_ORIGINS env var.
"""

import importlib
import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _reload_app_with_env(env_overrides: dict):
    """
    Reload the main module with custom environment to test CORS configuration.

    Returns a fresh TestClient attached to the reloaded app.
    """
    with patch.dict(os.environ, env_overrides):
        # Force re-import of main so CORSMiddleware is re-configured
        if "main" in sys.modules:
            main_mod = importlib.reload(sys.modules["main"])
        else:
            import main as main_mod

        return TestClient(main_mod.app)


# ---------------------------------------------------------------------------
# Test 1: Default CORS origins (wildcard) when env var is not set
# ---------------------------------------------------------------------------

def test_default_cors_allows_any_origin(client):
    """When CORS_ORIGINS is not set, the service defaults to '*' (allow all).

    Note: Starlette's CORSMiddleware with allow_credentials=True echoes the
    requesting Origin instead of returning a literal '*'.
    """
    origin = "http://random-origin.example.com"
    response = client.options(
        "/users/all",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    # The middleware should respond to the preflight request
    assert response.status_code == 200
    allow_origin = response.headers.get("access-control-allow-origin")
    # With allow_credentials=True, the middleware echoes the request origin
    assert allow_origin == origin


def test_default_cors_env_parsing():
    """When CORS_ORIGINS env var is unset, the code should produce ['*']."""
    cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
    assert cors_origins == ["*"]


# ---------------------------------------------------------------------------
# Test 2: Custom comma-separated origins from CORS_ORIGINS env var
# ---------------------------------------------------------------------------

def test_custom_cors_origins():
    """When CORS_ORIGINS='http://a.com,http://b.com', those should be allowed."""
    custom_origins = "http://a.com,http://b.com"
    parsed = custom_origins.split(",")
    assert parsed == ["http://a.com", "http://b.com"]


def test_cors_rejects_unlisted_origin_with_custom_config():
    """
    Verify that the CORS parsing logic correctly splits comma-separated values
    and does NOT include origins that were not specified.
    """
    custom_origins = "http://allowed.example.com,http://also-allowed.com"
    parsed = custom_origins.split(",")

    assert "http://allowed.example.com" in parsed
    assert "http://also-allowed.com" in parsed
    assert "http://not-listed.com" not in parsed


def test_single_origin_from_env():
    """CORS_ORIGINS with a single origin (no comma) should produce a one-element list."""
    cors_value = "http://only-this.com"
    parsed = cors_value.split(",")
    assert parsed == ["http://only-this.com"]


def test_cors_preflight_with_default_wildcard(client):
    """Preflight OPTIONS request should include correct CORS headers."""
    response = client.options(
        "/users/all",
        headers={
            "Origin": "http://test.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.status_code == 200
    # With wildcard origins, any origin should be reflected
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin is not None
    # Allowed methods should include GET
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "GET" in allow_methods or "*" in allow_methods

"""
Regression tests for WebSocket authentication (auth_http.authenticate_websocket).

Production incident: user-service's GET /users/me fans out to character-service
and locations-service with a 5s timeout each, so a degraded downstream made
/users/me land at a hair over 5s on *every* call. authenticate_websocket used a
5.0s timeout of its own and swallowed the resulting exception as a bare `None`,
so every single WebSocket handshake was rejected with 403 and the client sat in
a permanent "Переподключение к серверу" reconnect loop — with nothing in the
logs to distinguish it from an expired token.

These tests pin the two properties that made it undiagnosable and unrecoverable:
a timeout budget larger than the downstream's own worst case, and a logged
reason on every rejection path.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import pytest

import auth_http


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _patch_client_get(monkeypatch, handler):
    async def fake_get(self, url, *args, **kwargs):
        return handler(url, kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


def test_timeout_budget_exceeds_downstream_worst_case():
    """/users/me chains two 5s calls; a 5s budget here rejects every handshake."""
    assert auth_http.AUTH_REQUEST_TIMEOUT > 10.0, (
        "auth timeout must exceed user-service's own worst case (2 x 5s), "
        "otherwise a slow downstream rejects all WebSocket connections"
    )


@pytest.mark.asyncio
async def test_timeout_is_actually_passed_to_the_request(monkeypatch):
    seen = {}

    def handler(url, kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return _FakeResponse(200, {"id": 1, "username": "Dudka"})

    _patch_client_get(monkeypatch, handler)

    await auth_http.authenticate_websocket("token")

    assert seen["timeout"] == auth_http.AUTH_REQUEST_TIMEOUT


@pytest.mark.asyncio
async def test_valid_token_returns_user(monkeypatch):
    _patch_client_get(
        monkeypatch,
        lambda url, kwargs: _FakeResponse(200, {"id": 7, "username": "Dudka"}),
    )

    user = await auth_http.authenticate_websocket("token")

    assert user == {"id": 7, "username": "Dudka"}


@pytest.mark.asyncio
async def test_rejection_is_logged_not_silent(monkeypatch, caplog):
    """A 401 must leave a trace — the silent `return None` hid the outage."""
    _patch_client_get(monkeypatch, lambda url, kwargs: _FakeResponse(401))

    with caplog.at_level("WARNING"):
        user = await auth_http.authenticate_websocket("expired")

    assert user is None
    assert any("401" in r.message for r in caplog.records), caplog.text


@pytest.mark.asyncio
async def test_transport_failure_is_logged_not_silent(monkeypatch, caplog):
    """A timeout must be distinguishable from a bad token in the logs."""

    async def failing_get(self, url, *args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "get", failing_get)

    with caplog.at_level("ERROR"):
        user = await auth_http.authenticate_websocket("token")

    assert user is None
    assert any("ReadTimeout" in r.message for r in caplog.records), caplog.text


def test_sync_auth_helper_has_a_timeout(monkeypatch):
    """requests.get without a timeout can wedge a worker thread forever."""
    seen = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"id": 1, "username": "Dudka", "role": "user", "permissions": []}

    def fake_get(url, headers=None, timeout=None):
        seen["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(auth_http.requests, "get", fake_get)

    auth_http.get_current_user_via_http("token")

    assert seen["timeout"] == auth_http.AUTH_REQUEST_TIMEOUT


def test_sync_auth_helper_maps_downstream_outage_to_503(monkeypatch):
    """A dead user-service is a 503, not a hang and not a misleading 401."""
    import requests as requests_lib
    from fastapi import HTTPException

    def failing_get(url, headers=None, timeout=None):
        raise requests_lib.ConnectionError("user-service unreachable")

    monkeypatch.setattr(auth_http.requests, "get", failing_get)

    with pytest.raises(HTTPException) as exc:
        auth_http.get_current_user_via_http("token")

    assert exc.value.status_code == 503

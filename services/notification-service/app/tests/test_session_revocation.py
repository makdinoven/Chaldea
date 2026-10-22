"""
Session revocation: user-service tells notification-service which login
sessions were revoked, and the WebSockets opened with those sessions' tokens
are closed with code 4001.

Covers:
- POST /notifications/internal/sessions/revoked: X-Internal-Token auth
  (missing / wrong / unconfigured), payload validation, delegation;
- ws_manager.close_revoked_sessions: matching by session_ids / all_except /
  close-all, legacy sockets without a session, close code 4001;
- auth_http.unverified_session_id parsing;
- the WS endpoint tags each socket with the handshake token's `sid`.
"""

import base64
import json
from unittest.mock import AsyncMock, patch

import pytest

import ws_manager
from auth_http import unverified_session_id

URL = "/notifications/internal/sessions/revoked"
TOKEN = "test-internal-token"


def _fake_jwt(payload: dict) -> str:
    def b64(obj):
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return f"{b64({'alg': 'HS256', 'typ': 'JWT'})}.{b64(payload)}.signature"


@pytest.fixture()
def internal_token(monkeypatch):
    import auth_http
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


@pytest.fixture()
def clean_ws_state():
    orig_conn = ws_manager.active_connections
    orig_subs = ws_manager.channel_subscriptions
    orig_sessions = ws_manager.socket_sessions
    ws_manager.active_connections = {}
    ws_manager.channel_subscriptions = {ch: set() for ch in ws_manager.CHAT_CHANNELS}
    ws_manager.socket_sessions = {}
    try:
        yield
    finally:
        ws_manager.active_connections = orig_conn
        ws_manager.channel_subscriptions = orig_subs
        ws_manager.socket_sessions = orig_sessions


# ── Internal endpoint ───────────────────────────────────────────────────


class TestInternalEndpointAuth:

    def test_missing_token_401(self, client, internal_token):
        resp = client.post(URL, json={"user_id": 1, "session_ids": ["a"]})
        assert resp.status_code == 401

    def test_wrong_token_401(self, client, internal_token):
        resp = client.post(URL, json={"user_id": 1, "session_ids": ["a"]},
                           headers={"X-Internal-Token": "nope"})
        assert resp.status_code == 401

    def test_unconfigured_token_503(self, client, monkeypatch):
        import auth_http
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        resp = client.post(URL, json={"user_id": 1, "session_ids": ["a"]},
                           headers={"X-Internal-Token": ""})
        assert resp.status_code == 503

    def test_regular_user_auth_is_not_enough(self, client, internal_token):
        """A Bearer token (overridden user auth in the fixture) does not open it."""
        resp = client.post(URL, json={"user_id": 1, "session_ids": ["a"]},
                           headers={"Authorization": "Bearer whatever"})
        assert resp.status_code == 401


class TestInternalEndpointBehaviour:

    def _post(self, client, body):
        return client.post(URL, json=body, headers={"X-Internal-Token": TOKEN})

    def test_session_ids_delegated(self, client, internal_token):
        with patch("main.ws_manager.close_revoked_sessions", new_callable=AsyncMock,
                   return_value=2) as close:
            resp = self._post(client, {"user_id": 5, "session_ids": ["a", "b"]})
        assert resp.status_code == 200
        assert resp.json() == {"closed": 2}
        close.assert_awaited_once_with(5, session_ids=["a", "b"], all_except=None)

    def test_all_except_delegated(self, client, internal_token):
        with patch("main.ws_manager.close_revoked_sessions", new_callable=AsyncMock,
                   return_value=0) as close:
            resp = self._post(client, {"user_id": 5, "all_except": "cur"})
        assert resp.status_code == 200
        close.assert_awaited_once_with(5, session_ids=None, all_except="cur")

    def test_neither_closes_all(self, client, internal_token):
        with patch("main.ws_manager.close_revoked_sessions", new_callable=AsyncMock,
                   return_value=1) as close:
            resp = self._post(client, {"user_id": 5})
        assert resp.status_code == 200
        close.assert_awaited_once_with(5, session_ids=None, all_except=None)

    def test_both_fields_422(self, client, internal_token):
        with patch("main.ws_manager.close_revoked_sessions", new_callable=AsyncMock) as close:
            resp = self._post(client, {"user_id": 5, "session_ids": ["a"], "all_except": "b"})
        assert resp.status_code == 422
        close.assert_not_awaited()

    def test_bad_payload_422(self, client, internal_token):
        assert self._post(client, {"session_ids": ["a"]}).status_code == 422


# ── ws_manager.close_revoked_sessions ───────────────────────────────────


@pytest.mark.usefixtures("clean_ws_state")
class TestCloseRevokedSessions:

    async def _setup(self):
        a, b, legacy, foreign = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        await ws_manager.connect(1, a, "sid-a")
        await ws_manager.connect(1, b, "sid-b")
        await ws_manager.connect(1, legacy, None)
        await ws_manager.connect(2, foreign, "sid-a")  # other user, same sid value
        return a, b, legacy, foreign

    @staticmethod
    def _closed_with_4001(ws):
        return any(c.kwargs.get("code") == 4001 for c in ws.close.call_args_list)

    @pytest.mark.asyncio
    async def test_by_session_ids(self):
        a, b, legacy, foreign = await self._setup()
        closed = await ws_manager.close_revoked_sessions(1, session_ids=["sid-a"])
        assert closed == 1
        assert self._closed_with_4001(a)
        assert not b.close.called and not legacy.close.called and not foreign.close.called
        assert ws_manager.active_connections[1] == {b, legacy}
        assert a not in ws_manager.socket_sessions
        assert ws_manager.active_connections[2] == {foreign}

    @pytest.mark.asyncio
    async def test_all_except_closes_legacy_too(self):
        a, b, legacy, foreign = await self._setup()
        closed = await ws_manager.close_revoked_sessions(1, all_except="sid-b")
        assert closed == 2
        assert self._closed_with_4001(a) and self._closed_with_4001(legacy)
        assert not b.close.called and not foreign.close.called
        assert ws_manager.active_connections[1] == {b}

    @pytest.mark.asyncio
    async def test_close_all(self):
        a, b, legacy, foreign = await self._setup()
        closed = await ws_manager.close_revoked_sessions(1)
        assert closed == 3
        assert 1 not in ws_manager.active_connections
        for ch in ws_manager.CHAT_CHANNELS:
            assert 1 not in ws_manager.channel_subscriptions[ch]
        assert not foreign.close.called

    @pytest.mark.asyncio
    async def test_unknown_user_or_session_noop(self):
        await self._setup()
        assert await ws_manager.close_revoked_sessions(99, session_ids=["sid-a"]) == 0
        assert await ws_manager.close_revoked_sessions(1, session_ids=["nope"]) == 0

    @pytest.mark.asyncio
    async def test_close_error_still_unregisters(self):
        a, *_ = await self._setup()
        a.close.side_effect = RuntimeError("already closed")
        assert await ws_manager.close_revoked_sessions(1, session_ids=["sid-a"]) == 1
        assert a not in ws_manager.active_connections[1]


# ── sid extraction ──────────────────────────────────────────────────────


class TestUnverifiedSessionId:

    def test_reads_sid(self):
        assert unverified_session_id(_fake_jwt({"sub": "x", "sid": "abc"})) == "abc"

    def test_no_sid(self):
        assert unverified_session_id(_fake_jwt({"sub": "x"})) is None

    @pytest.mark.parametrize("token", ["", "garbage", "a.b.c", "a.!!!.c"])
    def test_garbage(self, token):
        assert unverified_session_id(token) is None


# ── WS endpoint tags sockets ────────────────────────────────────────────


class TestWebSocketTagsSession:

    def test_socket_registered_with_sid(self, client, clean_ws_state):
        user_data = {"id": 7, "username": "u", "role": "user", "permissions": []}
        token = _fake_jwt({"sub": "u@x", "sid": "sid-77"})
        with patch("main.authenticate_websocket", new_callable=AsyncMock, return_value=user_data):
            with client.websocket_connect(f"/notifications/ws?token={token}") as ws:
                ws.send_text("hello")
                assert list(ws_manager.socket_sessions.values()) == ["sid-77"]

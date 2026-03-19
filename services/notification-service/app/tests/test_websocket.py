"""
Tests for WebSocket migration (FEAT-050).

Covers:
- WebSocket endpoint authentication (valid/invalid token)
- ws_manager functions: connect, disconnect, send_to_user, broadcast_to_channel, broadcast_to_all
- SSE endpoints removed (GET /notifications/stream, GET /notifications/chat/stream → 404/405)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.testclient import TestClient


# ── WebSocket endpoint auth ─────────────────────────────────────────────


class TestWebSocketAuth:

    def test_valid_token_connection_accepted(self, client):
        """WS connection with a valid token is accepted (server sends messages)."""
        user_data = {"id": 1, "username": "testuser", "role": "user", "permissions": []}

        with patch("main.authenticate_websocket", new_callable=AsyncMock, return_value=user_data):
            with client.websocket_connect("/notifications/ws?token=valid_token") as ws:
                # Connection accepted — server sends a ping after 30s timeout,
                # but we can verify the connection is open by simply connecting.
                # Send a text message; the server ignores it but doesn't crash.
                ws.send_text("hello")
                # Read the ping that comes after 30s timeout on receive_text.
                # We expect the server to send a ping dict.
                data = ws.receive_json()
                assert data["type"] == "ping"

    def test_invalid_token_connection_rejected(self, client):
        """WS connection with an invalid token is closed with code 4001."""
        with patch("main.authenticate_websocket", new_callable=AsyncMock, return_value=None):
            with pytest.raises(Exception) as exc_info:
                with client.websocket_connect("/notifications/ws?token=bad_token"):
                    pass  # Should not reach here
            # Starlette raises an exception when the server closes the WS during handshake
            # The close code should be 4001
            assert "4001" in str(exc_info.value) or "Unauthorized" in str(exc_info.value)

    def test_missing_token_returns_error(self, client):
        """WS connection without token query param is rejected (422 from FastAPI)."""
        with pytest.raises(Exception):
            with client.websocket_connect("/notifications/ws"):
                pass


# ── ws_manager unit tests ───────────────────────────────────────────────


class TestWsManagerConnect:

    @pytest.mark.asyncio
    async def test_connect_adds_user_to_active_connections(self):
        """connect() registers the user in active_connections and all channels."""
        import ws_manager

        # Save and reset state
        orig_connections = ws_manager.active_connections.copy()
        orig_subscriptions = {ch: s.copy() for ch, s in ws_manager.channel_subscriptions.items()}

        try:
            ws_manager.active_connections.clear()
            for ch in ws_manager.CHAT_CHANNELS:
                ws_manager.channel_subscriptions[ch] = set()

            mock_ws = AsyncMock()
            await ws_manager.connect(42, mock_ws)

            assert 42 in ws_manager.active_connections
            assert ws_manager.active_connections[42] is mock_ws
            for ch in ws_manager.CHAT_CHANNELS:
                assert 42 in ws_manager.channel_subscriptions[ch]
        finally:
            ws_manager.active_connections = orig_connections
            ws_manager.channel_subscriptions = orig_subscriptions

    @pytest.mark.asyncio
    async def test_connect_replaces_old_connection(self):
        """Duplicate connect() closes old WS and replaces with new one."""
        import ws_manager

        orig_connections = ws_manager.active_connections.copy()
        orig_subscriptions = {ch: s.copy() for ch, s in ws_manager.channel_subscriptions.items()}

        try:
            ws_manager.active_connections.clear()
            for ch in ws_manager.CHAT_CHANNELS:
                ws_manager.channel_subscriptions[ch] = set()

            old_ws = AsyncMock()
            new_ws = AsyncMock()

            await ws_manager.connect(42, old_ws)
            await ws_manager.connect(42, new_ws)

            assert ws_manager.active_connections[42] is new_ws
            # Old WS should have been closed
            old_ws.close.assert_called_once()
        finally:
            ws_manager.active_connections = orig_connections
            ws_manager.channel_subscriptions = orig_subscriptions


class TestWsManagerDisconnect:

    @pytest.mark.asyncio
    async def test_disconnect_removes_user(self):
        """disconnect() removes user from active_connections and all channels."""
        import ws_manager

        orig_connections = ws_manager.active_connections.copy()
        orig_subscriptions = {ch: s.copy() for ch, s in ws_manager.channel_subscriptions.items()}

        try:
            ws_manager.active_connections.clear()
            for ch in ws_manager.CHAT_CHANNELS:
                ws_manager.channel_subscriptions[ch] = set()

            mock_ws = AsyncMock()
            await ws_manager.connect(42, mock_ws)
            await ws_manager.disconnect(42)

            assert 42 not in ws_manager.active_connections
            for ch in ws_manager.CHAT_CHANNELS:
                assert 42 not in ws_manager.channel_subscriptions[ch]
        finally:
            ws_manager.active_connections = orig_connections
            ws_manager.channel_subscriptions = orig_subscriptions

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_user_no_error(self):
        """disconnect() for a user not in active_connections does not raise."""
        import ws_manager

        orig_connections = ws_manager.active_connections.copy()
        try:
            ws_manager.active_connections.clear()
            # Should not raise
            await ws_manager.disconnect(9999)
        finally:
            ws_manager.active_connections = orig_connections


class TestWsManagerSendToUser:

    def test_send_to_user_sends_data(self):
        """send_to_user() schedules send_json for the correct user's WebSocket."""
        import ws_manager

        orig_connections = ws_manager.active_connections.copy()
        orig_loop = ws_manager._loop

        try:
            mock_ws = AsyncMock()
            ws_manager.active_connections = {10: mock_ws}

            loop = asyncio.new_event_loop()
            ws_manager._loop = loop

            async def _test():
                ws_manager.send_to_user(10, {"type": "notification", "data": {"msg": "hi"}})
                await asyncio.sleep(0.05)
                mock_ws.send_json.assert_called_once_with({"type": "notification", "data": {"msg": "hi"}})

            loop.run_until_complete(_test())
            loop.close()
        finally:
            ws_manager.active_connections = orig_connections
            ws_manager._loop = orig_loop

    def test_send_to_user_no_op_for_disconnected(self):
        """send_to_user() does nothing if user has no active connection."""
        import ws_manager

        orig_connections = ws_manager.active_connections.copy()
        try:
            ws_manager.active_connections.clear()
            # Should not raise
            ws_manager.send_to_user(999, {"msg": "ignored"})
        finally:
            ws_manager.active_connections = orig_connections


class TestWsManagerBroadcastToChannel:

    def test_broadcast_to_channel_sends_to_subscribers(self):
        """broadcast_to_channel() sends data to all users in that channel."""
        import ws_manager

        orig_connections = ws_manager.active_connections.copy()
        orig_subscriptions = {ch: s.copy() for ch, s in ws_manager.channel_subscriptions.items()}
        orig_loop = ws_manager._loop

        try:
            mock_ws1 = AsyncMock()
            mock_ws2 = AsyncMock()
            mock_ws3 = AsyncMock()

            ws_manager.active_connections = {1: mock_ws1, 2: mock_ws2, 3: mock_ws3}
            ws_manager.channel_subscriptions["general"] = {1, 2}
            ws_manager.channel_subscriptions["trade"] = {3}
            ws_manager.channel_subscriptions["help"] = set()

            loop = asyncio.new_event_loop()
            ws_manager._loop = loop

            data = {"type": "chat_message", "data": {"content": "hello"}}

            async def _test():
                ws_manager.broadcast_to_channel("general", data)
                await asyncio.sleep(0.05)
                mock_ws1.send_json.assert_called_once_with(data)
                mock_ws2.send_json.assert_called_once_with(data)
                mock_ws3.send_json.assert_not_called()

            loop.run_until_complete(_test())
            loop.close()
        finally:
            ws_manager.active_connections = orig_connections
            ws_manager.channel_subscriptions = orig_subscriptions
            ws_manager._loop = orig_loop

    def test_broadcast_to_empty_channel_no_error(self):
        """broadcast_to_channel() with no subscribers does not raise."""
        import ws_manager

        orig_subscriptions = {ch: s.copy() for ch, s in ws_manager.channel_subscriptions.items()}
        try:
            ws_manager.channel_subscriptions["help"] = set()
            ws_manager.broadcast_to_channel("help", {"type": "test"})
        finally:
            ws_manager.channel_subscriptions = orig_subscriptions


class TestWsManagerBroadcastToAll:

    def test_broadcast_to_all_sends_to_everyone(self):
        """broadcast_to_all() sends data to ALL active connections."""
        import ws_manager

        orig_connections = ws_manager.active_connections.copy()
        orig_loop = ws_manager._loop

        try:
            mock_ws1 = AsyncMock()
            mock_ws2 = AsyncMock()

            ws_manager.active_connections = {1: mock_ws1, 2: mock_ws2}

            loop = asyncio.new_event_loop()
            ws_manager._loop = loop

            data = {"type": "chat_message_deleted", "data": {"id": 5, "channel": "general"}}

            async def _test():
                ws_manager.broadcast_to_all(data)
                await asyncio.sleep(0.05)
                mock_ws1.send_json.assert_called_once_with(data)
                mock_ws2.send_json.assert_called_once_with(data)

            loop.run_until_complete(_test())
            loop.close()
        finally:
            ws_manager.active_connections = orig_connections
            ws_manager._loop = orig_loop

    def test_broadcast_to_all_no_connections_no_error(self):
        """broadcast_to_all() with no active connections does not raise."""
        import ws_manager

        orig_connections = ws_manager.active_connections.copy()
        try:
            ws_manager.active_connections = {}
            ws_manager.broadcast_to_all({"type": "test"})
        finally:
            ws_manager.active_connections = orig_connections


# ── SSE endpoints removed ───────────────────────────────────────────────


class TestSSEEndpointsRemoved:

    def test_sse_notification_stream_removed(self, client):
        """GET /notifications/stream should return 404 (endpoint removed)."""
        resp = client.get("/notifications/stream")
        assert resp.status_code in (404, 405)

    def test_sse_chat_stream_removed(self, client):
        """GET /notifications/chat/stream should return 404 (endpoint removed)."""
        resp = client.get("/notifications/chat/stream")
        assert resp.status_code in (404, 405)

"""The run's live line says why it refuses: closed after accept(), so the browser sees 4001/4003, not 1006."""
from contextlib import asynccontextmanager

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main


class _NoMember:
    def scalars(self):
        return self

    def first(self):
        return None


class _Db:
    async def execute(self, *args, **kwargs):
        return _NoMember()


@asynccontextmanager
async def _session():
    yield _Db()


def _close_code(monkeypatch, user):
    async def auth(token):
        return user
    monkeypatch.setattr(main, "authenticate_websocket", auth)
    monkeypatch.setattr(main, "async_session", _session)
    client = TestClient(main.app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/dungeons/ws/1?token=t") as ws:
            ws.receive_json()
    return exc.value.code


def test_a_stale_token_is_told_so(monkeypatch):
    assert _close_code(monkeypatch, None) == 4001


def test_a_stranger_to_the_run_is_told_so(monkeypatch):
    assert _close_code(monkeypatch, {"id": 7}) == 4003

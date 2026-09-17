"""
FEAT-167 #17/#18 — character-service must send `X-Internal-Token` when it
creates a character's attributes and inventory.

`POST /attributes/` and `POST /inventory/` were reachable anonymously through
the gateway (they answered 422 on the body schema instead of 401, so anyone
could seed attribute rows and equipment slots for arbitrary character ids).
Both are internal-only now, and character-service is their **only** caller:

  * `crud.send_attributes_request`       -> POST /attributes/   (character
    creation — hard-fail, rolls the character back — and admin NPC creation)
  * `crud._sync_send_attributes_request` -> POST /attributes/   (mob spawn)
  * `crud.send_inventory_request`        -> POST /inventory/    (starter kit)

Nothing else in the repo posts to either bare base URL, so if these three drop
the header, character creation breaks outright and mob spawns and starter kits
break silently (they log and continue). The existing `test_http_helpers.py`
mocks the transport but never looked at the headers, which is why this file
asserts on the **real** helper functions.
"""

import asyncio

import pytest

import crud


TOKEN = "test-internal-token"


@pytest.fixture()
def token(monkeypatch):
    """`auth_http` reads the secret into a module constant at import time and
    `crud._internal_token_headers` imports it lazily — pin the constant."""
    import auth_http
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = "{}"

    def json(self):
        return {"id": 1}


def _patch_async_client(monkeypatch, response=None):
    calls = []
    resp = response or _Resp()

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return resp

    monkeypatch.setattr(crud.httpx, "AsyncClient", _Client)
    return calls


def _patch_sync_post(monkeypatch, response=None):
    calls = []
    resp = response or _Resp()

    def _post(url, **kwargs):
        calls.append((url, kwargs))
        return resp

    monkeypatch.setattr(crud.httpx, "post", _post)
    return calls


class TestInternalHeaderHelper:

    def test_helper_returns_the_configured_token(self, token):
        assert crud._internal_token_headers() == {"X-Internal-Token": TOKEN}

    def test_helper_reads_the_constant_at_call_time(self, monkeypatch):
        """A frozen copy taken at import time would make the tests above pass
        and production fail whenever the value is rotated."""
        import auth_http
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "first")
        assert crud._internal_token_headers()["X-Internal-Token"] == "first"
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "second")
        assert crud._internal_token_headers()["X-Internal-Token"] == "second"


class TestOutgoingCreationCallsSendTheToken:

    def test_send_attributes_request_sends_the_token(self, monkeypatch, token):
        calls = _patch_async_client(monkeypatch)
        result = asyncio.run(crud.send_attributes_request(7, {"strength": 10}))

        assert result is not None
        url, kwargs = calls[0]
        assert url.rstrip("/").endswith("/attributes"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "character-service dropped X-Internal-Token — character creation "
            "would fail with «Не удалось создать атрибуты»"
        )
        assert kwargs["json"]["character_id"] == 7

    def test_sync_send_attributes_request_sends_the_token(self, monkeypatch, token):
        """The mob-spawn path: fire-and-forget, so a missing header would mean
        mobs quietly spawning without attributes."""
        calls = _patch_sync_post(monkeypatch)
        result = crud._sync_send_attributes_request(9, {"strength": 10})

        assert result is not None
        url, kwargs = calls[0]
        assert url.rstrip("/").endswith("/attributes"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN
        assert kwargs["json"]["character_id"] == 9

    def test_send_inventory_request_sends_the_token(self, monkeypatch, token):
        calls = _patch_async_client(monkeypatch)
        result = asyncio.run(
            crud.send_inventory_request(7, [{"item_id": 1, "quantity": 2}])
        )

        assert result is not None
        url, kwargs = calls[0]
        assert url.rstrip("/").endswith("/inventory"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "character-service dropped X-Internal-Token — the starter kit would "
            "silently never be granted"
        )
        assert kwargs["json"]["character_id"] == 7

    @pytest.mark.parametrize("value", ["first", "second"])
    def test_the_token_is_not_frozen_at_import(self, monkeypatch, value):
        import auth_http
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", value)
        calls = _patch_async_client(monkeypatch)
        asyncio.run(crud.send_attributes_request(1, {}))
        assert calls[0][1]["headers"]["X-Internal-Token"] == value

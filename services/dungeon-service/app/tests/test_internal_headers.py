"""
FEAT-167 — dungeon-service's calls into the newly gated routes.

Three real client functions in `http_clients.py`:
  * `consume_stamina`        -> POST /attributes/{id}/consume_stamina  (gated)
  * `recover_character`      -> POST /attributes/{id}/recover          (gated)
  * `add_item_to_character`  -> POST /inventory/internal/characters/{id}/items
                                (new internal route, was the open one)

Without the header a dungeon run would stop charging stamina, stop healing at a
fountain and stop handing out loot. The assertions run against the real
functions with `httpx.AsyncClient` patched.
"""

import os

import pytest

import http_clients
from config import settings


TOKEN = "test-internal-token"


@pytest.fixture()
def token(monkeypatch):
    """`http_clients` reads the token from `settings` — pin the setting."""
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _patch_client(monkeypatch, response=None):
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

    monkeypatch.setattr(http_clients.httpx, "AsyncClient", _Client)
    return calls


@pytest.mark.asyncio
async def test_consume_stamina_sends_the_token(monkeypatch, token):
    calls = _patch_client(monkeypatch)
    assert await http_clients.consume_stamina(11, 4) is True

    url, kwargs = calls[0]
    assert url.endswith("/attributes/11/consume_stamina"), url
    assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
        "dungeon-service dropped X-Internal-Token on consume_stamina"
    )
    assert kwargs["json"] == {"amount": 4}


@pytest.mark.asyncio
async def test_recover_character_sends_the_token(monkeypatch, token):
    calls = _patch_client(monkeypatch)
    await http_clients.recover_character(11, health=5, mana=1)

    url, kwargs = calls[0]
    assert url.endswith("/attributes/11/recover"), url
    assert kwargs["headers"]["X-Internal-Token"] == TOKEN
    # the real payload keys of the endpoint — not `health`/`mana`
    assert kwargs["json"] == {
        "health_recovery": 5, "mana_recovery": 1,
        "energy_recovery": 0, "stamina_recovery": 0,
    }


@pytest.mark.asyncio
async def test_add_item_uses_the_internal_route_with_the_token(monkeypatch, token):
    calls = _patch_client(monkeypatch)
    await http_clients.add_item_to_character(11, 331, 2)

    url, kwargs = calls[0]
    assert "/inventory/internal/characters/11/items" in url, (
        f"dungeon loot still uses the admin-gated grant route: {url}"
    )
    assert kwargs["headers"]["X-Internal-Token"] == TOKEN
    assert kwargs["json"] == {"item_id": 331, "quantity": 2}


@pytest.mark.asyncio
async def test_missing_token_yields_an_empty_header_not_a_crash(monkeypatch):
    """Fail-closed on the callee side: with no token configured the call still
    goes out but carries an empty value, and the callee answers 401/503. The
    point of the assertion is that the header key is always present, so the
    failure is a clear 401 rather than a mystery."""
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", "")
    calls = _patch_client(monkeypatch)
    await http_clients.consume_stamina(11, 1)
    assert calls[0][1]["headers"]["X-Internal-Token"] == ""


class TestSourceSweep:
    """Every call in dungeon-service that targets a gated path must pass the
    header helper."""

    GATED = (
        "/consume_stamina",
        "/recover",
        "/inventory/internal/characters/",
    )

    def test_all_gated_calls_carry_the_header(self):
        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        path = os.path.join(app_dir, "http_clients.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read()

        offenders = []
        for gated in self.GATED:
            idx = 0
            while True:
                idx = source.find(gated, idx)
                if idx == -1:
                    break
                window = source[idx: idx + 900]
                if "_internal_token_headers()" not in window:
                    offenders.append(f"{gated} near offset {idx}")
                idx += len(gated)
        assert not offenders, (
            "gated call(s) without the internal header: " + "; ".join(offenders)
        )

    def test_the_grant_function_targets_the_internal_route(self):
        """`add_item_to_character` is the only item *grant* in dungeon-service
        (the other `/items` URLs here are GET reads, which stayed open). Its
        source must name the internal route — the admin-gated path would answer
        401 for a service token."""
        import inspect

        source = inspect.getsource(http_clients.add_item_to_character)
        assert "/inventory/internal/characters/" in source
        assert "_internal_token_headers()" in source
        assert "/inventory/{character_id}/items" not in source

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


@pytest.mark.asyncio
async def test_add_gold_sends_the_token(monkeypatch, token):
    """FEAT-169 — `POST /characters/{cid}/add_rewards` (`http_clients.py:406`)
    is gated now. Dungeon gold payouts run through it."""
    calls = _patch_client(monkeypatch, _Resp(200, {"new_balance": 150}))

    result = await http_clients.add_gold(11, 50)

    assert len(calls) == 1, "the dungeon gold payout never left dungeon-service"
    url, kwargs = calls[0]
    assert url.endswith("/characters/11/add_rewards"), url
    assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
        "dungeon-service dropped X-Internal-Token on add_rewards — "
        "character-service answers 401 and the dungeon gold is lost"
    )
    assert kwargs["json"] == {"xp": 0, "gold": 50}
    assert result == {"new_balance": 150}


@pytest.mark.asyncio
async def test_party_active_members_sends_the_token(monkeypatch, token):
    """FEAT-169 — the whole `/party/internal/` prefix is gated
    (`http_clients.py:63`). This caller swallows failures and returns `{}`,
    i.e. "you are solo" — a missing header would silently strip squads from
    every dungeon run, which is why the header VALUE is asserted here."""
    roster = {"party_id": 3, "member_character_ids": [11, 12]}
    calls = []

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return _Resp(200, roster)

    monkeypatch.setattr(http_clients.httpx, "AsyncClient", _Client)

    data = await http_clients.get_party_active_members(11, 77)

    assert data == roster
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url.endswith("/party/internal/active-members"), url
    assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
        "dungeon-service dropped X-Internal-Token on active-members — "
        "party-service answers 401, the caller swallows it and every dungeon "
        "run silently becomes solo"
    )
    assert kwargs["params"] == {"character_id": 11, "location_id": 77}


@pytest.mark.asyncio
async def test_token_is_read_at_call_time(monkeypatch):
    """Pinned via `settings`, which `_internal_token_headers` reads on every
    call — two values must produce two different headers."""
    calls = _patch_client(monkeypatch)
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", "first")
    await http_clients.add_gold(1, 1)
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", "second")
    await http_clients.add_gold(1, 1)
    assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
        ["first", "second"]


def _statement_window(source: str, idx: int) -> str:
    """The source of the call that starts at `idx`, and nothing after it.

    A fixed forward window bleeds into the *next* function, so a call that lost
    its header would still "see" the neighbour's `_internal_token_headers()` and
    the sweep would pass. Cutting at the first blank line keeps the window to
    one statement/`try` block — verified by deleting a header and watching the
    sweep go red.
    """
    window = source[idx: idx + 900]
    end = window.find(chr(10) * 2)
    return window if end == -1 else window[:end]


class TestSourceSweep:
    """Every call in dungeon-service that targets a gated path must pass the
    header helper."""

    GATED = (
        "/consume_stamina",
        "/recover",
        "/inventory/internal/characters/",
        # FEAT-169: обе ручки закрыты verify_internal_token на стороне
        # character-service и party-service
        "/add_rewards",
        "/party/internal/active-members",
        # FEAT-162: /characters/internal/* (spawn-dungeon-mobs, deduct-gold)
        "/characters/internal/",
    )

    def test_all_gated_calls_carry_the_header(self):
        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        path = os.path.join(app_dir, "http_clients.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read()

        lines = source.split("\n")
        offenders = []
        for gated in self.GATED:
            idx = 0
            while True:
                idx = source.find(gated, idx)
                if idx == -1:
                    break
                line_no = source.count("\n", 0, idx)
                # Only real URL construction counts; docstrings, comments and
                # log messages mention these paths too.
                if 'f"' in lines[line_no]:
                    window = _statement_window(source, idx)
                    if "_internal_token_headers()" not in window:
                        offenders.append(f"http_clients.py:{line_no + 1} -> {gated}")
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

"""
FEAT-167 — battle-pass-service must use the internal item-grant route and send
`X-Internal-Token`.

`POST /inventory/{cid}/items` is admin-gated now (`items:update`); services grant
items through `POST /inventory/internal/characters/{cid}/items` behind the
internal token. `_deliver_item` is the season-reward delivery path and had no
test at all before this feature, while battle-pass-service also had no
`INTERNAL_SERVICE_TOKEN` in either compose file — a missing header would have
turned every item reward into a logged error nobody reads.

Asserted on the real `crud._deliver_item`, with `httpx.AsyncClient` patched.
"""

import os

import pytest

import crud


TOKEN = "test-internal-token"


@pytest.fixture()
def token_env(monkeypatch):
    """The helper reads the env at call time."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {}


class _FailResp(_Resp):
    status_code = 401

    def raise_for_status(self):
        import httpx
        raise httpx.HTTPStatusError("401", request=None, response=None)


def _patch_client(monkeypatch, response=None):
    """Patch `crud.httpx.AsyncClient` and record every POST."""
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


class TestDeliverItem:

    @pytest.mark.asyncio
    async def test_uses_the_internal_route_with_the_token(self, monkeypatch, token_env):
        calls = _patch_client(monkeypatch)

        await crud._deliver_item(7, 331, 2)

        assert len(calls) == 1, "the season item reward never reached inventory"
        url, kwargs = calls[0]
        assert "/inventory/internal/characters/7/items" in url, (
            f"battle-pass still grants items through the admin-gated route: {url}"
        )
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-pass dropped X-Internal-Token — inventory-service would "
            "answer 401 and the season reward would be lost"
        )
        assert kwargs["json"] == {"item_id": 331, "quantity": 2}

    @pytest.mark.asyncio
    async def test_does_not_use_the_old_open_path(self, monkeypatch, token_env):
        calls = _patch_client(monkeypatch)
        await crud._deliver_item(7, 331, 1)
        url = calls[0][0]
        assert "/inventory/7/items" not in url

    @pytest.mark.asyncio
    async def test_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch_client(monkeypatch)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await crud._deliver_item(1, 2, 1)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await crud._deliver_item(1, 2, 1)
        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    @pytest.mark.asyncio
    async def test_failure_propagates(self, monkeypatch, token_env):
        """`_deliver_item` re-raises, so a 401 cannot pass as a delivered reward."""
        _patch_client(monkeypatch, response=_FailResp())
        with pytest.raises(Exception):
            await crud._deliver_item(7, 331, 1)


class TestDeliverGoldXp:
    """FEAT-169 — `POST /characters/{cid}/add_rewards` is gated now (`crud.py:542`).

    Season gold/XP rewards go through here. `_deliver_gold_xp` re-raises, but
    every caller of `claim_reward` logs and moves on, so without a header
    assertion a missing token would show up only as players quietly not getting
    their battle-pass rewards.
    """

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _patch_client(monkeypatch)

        await crud._deliver_gold_xp(7, xp=120, gold=45)

        assert len(calls) == 1, "the season gold/XP reward never reached character-service"
        url, kwargs = calls[0]
        assert url.endswith("/characters/7/add_rewards"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-pass dropped X-Internal-Token on add_rewards — "
            "character-service answers 401 and the season reward is lost"
        )
        assert kwargs["json"] == {
            "xp": 120,
            "gold": 45,
            "xp_source": crud.BATTLE_PASS_XP_SOURCE,
        }

    @pytest.mark.asyncio
    async def test_token_is_read_at_call_time(self, monkeypatch):
        """A constant captured at import would send an empty header in a
        container that got the variable later."""
        calls = _patch_client(monkeypatch)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await crud._deliver_gold_xp(7, xp=1, gold=0)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await crud._deliver_gold_xp(7, xp=1, gold=0)
        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    @pytest.mark.asyncio
    async def test_missing_token_still_sends_the_key(self, monkeypatch):
        """Fail-closed on the callee side: the key is always present, so the
        failure is a clear 401 rather than a mystery."""
        monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
        calls = _patch_client(monkeypatch)
        await crud._deliver_gold_xp(7, xp=1, gold=0)
        assert calls[0][1]["headers"]["X-Internal-Token"] == ""

    @pytest.mark.asyncio
    async def test_401_propagates(self, monkeypatch, token_env):
        """A rejected grant must not pass for a delivered reward."""
        _patch_client(monkeypatch, response=_FailResp())
        with pytest.raises(Exception):
            await crud._deliver_gold_xp(7, xp=1, gold=1)


class TestEveryInventoryGrantCarriesTheHeader:
    """Source sweep: any call in battle-pass-service that grants an item must
    target the internal route and pass `_internal_token_headers()`."""

    def test_source_sweep(self):
        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        with open(os.path.join(app_dir, "crud.py"), encoding="utf-8") as fh:
            source = fh.read()

        idx = 0
        offenders = []
        while True:
            idx = source.find("/items", idx)
            if idx == -1:
                break
            window = source[max(0, idx - 300): idx + 500]
            if "/inventory/internal/characters/" not in window:
                offenders.append(f"grant near offset {idx} is not the internal route")
            elif "_internal_token_headers()" not in window:
                offenders.append(f"grant near offset {idx} has no internal header")
            idx += len("/items")
        assert not offenders, "; ".join(offenders)


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


class TestEveryGatedCallCarriesTheHeader:
    """FEAT-169 source sweep over `crud.py`.

    Paths deliberately **not** listed: `/users/internal/{uid}/diamonds/add` and
    `/users/internal/{uid}/cosmetics/unlock` (`crud.py:580`, `:594`). Those
    user-service routes are explicitly out of FEAT-169's scope (§3.10 item 3 —
    they still rely on nginx alone) and today send no header. When that sweep
    happens, add them here and the assertions will hold the callers honest.
    """

    GATED = (
        "/add_rewards",
        "/inventory/internal/characters/",
    )

    def test_source_sweep(self):
        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        with open(os.path.join(app_dir, "crud.py"), encoding="utf-8") as fh:
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
                # Only real URL construction counts — docstrings and comments
                # name these paths too.
                if 'f"' in lines[line_no]:
                    window = _statement_window(source, idx)
                    if "_internal_token_headers()" not in window:
                        offenders.append(f"crud.py:{line_no + 1} -> {gated}")
                idx += len(gated)
        assert not offenders, (
            "gated call(s) without the internal header: " + "; ".join(offenders)
        )

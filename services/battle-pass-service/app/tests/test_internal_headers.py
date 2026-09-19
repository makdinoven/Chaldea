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


class TestDeliverDiamonds:
    """FEAT-170 T3 — `POST /users/internal/{uid}/diamonds/add` (`crud.py:580`).

    Premium currency. `_deliver_diamonds` re-raises, and `claim_reward` delivers
    **before** writing the `BpUserReward` marker, so a 401 fails the claim
    without burning the reward — but the player sees a 500. The header is what
    keeps that from happening.
    """

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _patch_client(monkeypatch)

        await crud._deliver_diamonds(7, 150)

        assert len(calls) == 1, "the diamond reward never reached user-service"
        url, kwargs = calls[0]
        assert url.endswith("/users/internal/7/diamonds/add"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-pass dropped X-Internal-Token on diamonds/add — "
            "user-service answers 401 and the claim 500s"
        )
        assert kwargs["json"] == {"amount": 150, "reason": "battle_pass_reward"}

    @pytest.mark.asyncio
    async def test_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch_client(monkeypatch)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await crud._deliver_diamonds(7, 1)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await crud._deliver_diamonds(7, 1)
        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    @pytest.mark.asyncio
    async def test_401_propagates(self, monkeypatch, token_env):
        _patch_client(monkeypatch, response=_FailResp())
        with pytest.raises(Exception):
            await crud._deliver_diamonds(7, 10)


class TestDeliverCosmetic:
    """FEAT-170 T3 — `POST /users/internal/{uid}/cosmetics/unlock`
    (`crud.py:594`). Purchasable goods; also re-raises."""

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _patch_client(monkeypatch)

        await crud._deliver_cosmetic(7, "frame", "gold-frame")

        assert len(calls) == 1, "the cosmetic reward never reached user-service"
        url, kwargs = calls[0]
        assert url.endswith("/users/internal/7/cosmetics/unlock"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-pass dropped X-Internal-Token on cosmetics/unlock — "
            "user-service answers 401 and the claim 500s"
        )
        assert kwargs["json"] == {
            "cosmetic_type": "frame",
            "cosmetic_slug": "gold-frame",
            "source": "battlepass",
        }

    @pytest.mark.asyncio
    async def test_missing_token_still_sends_the_key(self, monkeypatch):
        monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
        calls = _patch_client(monkeypatch)
        await crud._deliver_cosmetic(7, "frame", "gold-frame")
        assert calls[0][1]["headers"]["X-Internal-Token"] == ""

    @pytest.mark.asyncio
    async def test_401_propagates(self, monkeypatch, token_env):
        _patch_client(monkeypatch, response=_FailResp())
        with pytest.raises(Exception):
            await crud._deliver_cosmetic(7, "frame", "gold-frame")


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


class TestEveryGatedCallCarriesTheHeader:
    """FEAT-170 T15 — inverted source sweep over every module in `app/`.

    This used to be an allowlist of gated path prefixes, carrying a to-do that
    asked the next feature to append its own targets to it — i.e. a new internal
    target nobody remembered to list passed silently, which is exactly the
    failure mode the sweep exists to catch. The rule is inverted now: *any*
    `httpx`/`client`/`requests` call whose **resolved** URL contains
    `/internal/` must pass `headers=`. There is no exemption list, and none may
    be reintroduced.

    URLs are resolved through simple `url = f"..."` assignments above the call,
    because that is how every call site in `crud.py` is written. Resolver copied
    from `inventory-service/app/tests/test_outgoing_internal_headers.py`.
    """

    #: every module in `app/` — not just `crud.py`. A new outgoing call added
    #: to `main.py` (or anywhere else) is covered the day it is written.
    _SCANNED = ("crud.py", "main.py", "auth_http.py", "config.py",
                "database.py", "models.py", "schemas.py")
    _CLIENT_BASES = ("httpx", "client", "requests")
    _METHODS = ("get", "post", "put", "patch", "delete")

    def _resolve(self, source, tree):
        """{(start, end): {variable: assigned source}} per function scope."""
        import ast

        env = {}

        class _V(ast.NodeVisitor):
            def _scope(self, node):
                local = {}
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assign) and len(sub.targets) == 1 \
                            and isinstance(sub.targets[0], ast.Name):
                        local[sub.targets[0].id] = \
                            ast.get_source_segment(source, sub.value) or ""
                env[(node.lineno, node.end_lineno)] = local
                self.generic_visit(node)

            visit_FunctionDef = _scope
            visit_AsyncFunctionDef = _scope

        _V().visit(tree)
        return env

    def _url_of(self, source, env, node):
        import ast

        raw = ast.get_source_segment(source, node.args[0]) if node.args else ""
        raw = raw or ""
        if "/" in raw:
            return raw
        # a URL-building helper — inline its `return`
        if node.args and isinstance(node.args[0], ast.Call) \
                and isinstance(node.args[0].func, ast.Name):
            builder = node.args[0].func.id
            for sub in ast.walk(self._tree):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name == builder:
                    for inner in ast.walk(sub):
                        if isinstance(inner, ast.Return) and inner.value is not None:
                            return ast.get_source_segment(self._source, inner.value) or raw
        # a bare name — look it up in the innermost enclosing function
        scopes = [(end - start, local) for (start, end), local in env.items()
                  if start <= node.lineno <= end]
        scopes.sort(key=lambda pair: pair[0])
        for _, local in scopes:
            if raw in local:
                return local[raw]
        return raw

    def _walk_calls(self):
        """Yield (module, lineno, base, method, url, has_headers) per HTTP call."""
        import ast

        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for module in self._SCANNED:
            path = os.path.join(app_dir, module)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            tree = ast.parse(source)
            self._source, self._tree = source, tree
            env = self._resolve(source, tree)
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr not in self._METHODS:
                    continue
                base = ast.get_source_segment(source, node.func.value)
                if base not in self._CLIENT_BASES:
                    continue
                url = self._url_of(source, env, node)
                yield (module, node.lineno, base, node.func.attr, url,
                       "headers" in {kw.arg for kw in node.keywords})

    def test_no_internal_call_is_missing_headers(self):
        offenders = []
        checked = 0
        for module, lineno, base, method, url, has_headers in self._walk_calls():
            if "/internal/" not in url:
                continue
            checked += 1
            if not has_headers:
                offenders.append(
                    f"{module}:{lineno} {base}.{method}({url[:70]}) без headers="
                )

        assert checked >= 3, (
            "свип перестал находить внутренние вызовы — URL отрефакторили, "
            f"и проверка стала пустой (найдено {checked})"
        )
        assert not offenders, (
            "межсервисный вызов на /internal/ без X-Internal-Token — целевой "
            "маршрут ответит 401, а награда боевого пропуска не дойдёт: "
            + "; ".join(offenders)
        )

    def test_add_rewards_also_carries_the_header(self):
        """`POST /characters/{cid}/add_rewards` is gated (FEAT-169) but has no
        `internal` segment in its path, so the inverted rule above cannot see
        it. Pinned separately rather than as an allowlist entry — an allowlist
        decides what is *checked*, this decides what must be *true*."""
        offenders = []
        checked = 0
        for module, lineno, base, method, url, has_headers in self._walk_calls():
            if "/add_rewards" not in url:
                continue
            checked += 1
            if not has_headers:
                offenders.append(f"{module}:{lineno} {base}.{method}({url[:70]})")
        assert checked >= 1, "вызов add_rewards исчез — свип пуст"
        assert not offenders, (
            "начисление золота/опыта без X-Internal-Token: " + "; ".join(offenders)
        )

    def test_every_outgoing_call_was_seen(self):
        """Guard for the sweep itself: if the client calls are refactored out of
        recognition (a session object, a wrapper) the two tests above match
        nothing and stay green. battle-pass makes 5 HTTP calls today — four
        reward deliveries in `crud.py` and the `/users/me` auth call."""
        seen = list(self._walk_calls())
        assert len(seen) >= 5, seen

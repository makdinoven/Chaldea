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

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


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
async def test_consume_dungeon_gate_sends_the_token(monkeypatch, token):
    """FEAT-170 T2 — `POST /locations/internal/action-gate/consume`
    (`http_clients.py:81`). This caller swallows failures and returns `False`,
    i.e. "entry refused": a missing header would lock every player out of every
    dungeon with no error in sight, so the header VALUE is what is asserted."""
    calls = _patch_client(monkeypatch, _Resp(200, {"consumed": True}))

    assert await http_clients.consume_dungeon_gate(11, 77, 5) is True

    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url.endswith("/locations/internal/action-gate/consume"), url
    assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
        "dungeon-service dropped X-Internal-Token on action-gate/consume — "
        "locations-service answers 401, the caller swallows it and dungeon "
        "entry is silently refused"
    )
    assert kwargs["json"] == {
        "character_id": 11, "location_id": 77,
        "action_type": "dungeon", "target_ref": 5,
    }


@pytest.mark.asyncio
async def test_get_battle_state_sends_the_token(monkeypatch, token):
    """FEAT-170 T2 — `GET /battles/internal/{id}/state`
    (`http_clients.py:377`), the loudest call site in the feature: it
    re-raises as 502/503, so a missing header aborts a dungeon run in progress.
    One client function serves both call paths (`gameplay.py` polling loop and
    `main.py`)."""
    state = {"battle_id": 9, "status": "finished"}
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
            return _Resp(200, state)

    monkeypatch.setattr(http_clients.httpx, "AsyncClient", _Client)

    assert await http_clients.get_battle_state(9) == state

    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url.endswith("/battles/internal/9/state"), url
    assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
        "dungeon-service dropped X-Internal-Token on the battle-state poll — "
        "battle-service answers 401, get_battle_state raises 502 and the "
        "running dungeon aborts"
    )


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


class TestEveryInternalCallSiteSendsHeaders:
    """FEAT-170 T15(iii) — the **inverted** sweep.

    This class replaces the FEAT-167/169 `GATED` allowlist, which named the
    prefixes known to be closed and therefore waved through any *new* internal
    target nobody had thought to add to the list. The rule now has no exemption
    list at all: any call in dungeon-service whose **resolved** URL contains
    `/internal/` must pass `headers=`. Variable URLs (`url = f"..."` a line or
    two above the call) are resolved with the AST helper from
    `inventory-service/app/tests/test_outgoing_internal_headers.py`.

    Scanned beyond `main.py`: `http_clients.py` is where every outgoing call
    actually lives, and `crud.py` / `gameplay.py` are the two modules most
    likely to grow one.
    """

    FILES = ("main.py", "crud.py", "http_clients.py", "gameplay.py")

    #: Floor so that a URL refactor cannot silently empty the sweep. All six
    #: live in `http_clients.py` as of FEAT-170: party active-members,
    #: locations action-gate/consume, characters spawn-dungeon-mobs, inventory
    #: item grant, battles state poll, characters deduct-gold.
    MIN_CHECKED = 6

    def _resolve(self, source, tree):
        """{(start, end) of a function: {variable: assigned source}}."""
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

    def _url_of(self, source, tree, env, node):
        import ast

        raw = ast.get_source_segment(source, node.args[0]) if node.args else ""
        raw = raw or ""
        if "/" in raw:
            return raw
        # a URL-building helper — inline its return
        if node.args and isinstance(node.args[0], ast.Call) \
                and isinstance(node.args[0].func, ast.Name):
            builder = node.args[0].func.id
            for sub in ast.walk(tree):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name == builder:
                    for inner in ast.walk(sub):
                        if isinstance(inner, ast.Return) and inner.value is not None:
                            return ast.get_source_segment(source, inner.value) or raw
        # a bare name — look it up in the innermost enclosing function
        scopes = [(end - start, local) for (start, end), local in env.items()
                  if start <= node.lineno <= end]
        scopes.sort(key=lambda pair: pair[0])
        for _, local in scopes:
            if raw in local:
                return local[raw]
        return raw

    def _sweep(self):
        import ast

        offenders, checked = [], []
        for filename in self.FILES:
            path = os.path.join(APP_DIR, filename)
            if not os.path.exists(path):
                continue
            source = open(path, encoding="utf-8").read()
            tree = ast.parse(source)
            env = self._resolve(source, tree)

            # `@app.post("/dungeons/internal/…")` is a route *declaration*, not
            # an outgoing call — skip every decorator expression.
            decorators = set()
            for owner in ast.walk(tree):
                if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    decorators.update(id(d) for d in owner.decorator_list)

            for node in ast.walk(tree):
                if id(node) in decorators:
                    continue
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr not in ("get", "post", "put", "patch", "delete"):
                    continue
                url = self._url_of(source, tree, env, node)
                if "/internal/" not in url:
                    continue
                base = ast.get_source_segment(source, node.func.value)
                where = f"{filename}:{node.lineno} {base}.{node.func.attr}"
                checked.append(where)
                if "headers" not in {kw.arg for kw in node.keywords}:
                    offenders.append(f"{where}({url[:70]}) без headers=")
        return checked, offenders

    def test_no_internal_call_is_missing_headers(self):
        checked, offenders = self._sweep()

        assert len(checked) >= self.MIN_CHECKED, (
            "свип перестал находить внутренние вызовы — URL отрефакторили, "
            f"и проверка стала пустой (найдено {len(checked)}, "
            f"ожидалось >= {self.MIN_CHECKED}): {checked}"
        )
        assert not offenders, (
            "межсервисный вызов на /internal/ без X-Internal-Token — целевой "
            "маршрут ответит 401, а вызывающий это проглотит (или, в случае "
            "опроса состояния боя, оборвёт подземелье): " + "; ".join(offenders)
        )

    def test_the_sweep_has_no_allowlist(self):
        """FEAT-170: the `GATED` allowlist is gone and must not come back —
        with one, a new internal target passes silently."""
        attrs = {name for name in dir(self) if not name.startswith("test_")}
        forbidden = {"GATED", "KNOWN_UNGATED_TARGETS", "_KNOWN_UNGATED_TARGETS",
                     "EXEMPT", "SKIP", "ALLOWLIST"}
        assert not (attrs & forbidden), (
            "an exemption list crept back into the inverted sweep: "
            f"{sorted(attrs & forbidden)}"
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

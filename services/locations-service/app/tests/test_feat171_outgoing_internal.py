"""
FEAT-171 task 19 (locations-service) — the five cross-service reads that moved
onto the internal twins.

locations-service is the heaviest caller in §3.5 and had **no** test on any of
these reads before this file:

| call site | was | now |
|---|---|---|
| `crud._read_current_stamina`        | `GET /attributes/{id}` | `/attributes/internal/{id}` (A1i) |
| `main._fetch_charisma`              | `GET /attributes/{id}` | `/attributes/internal/{id}` (A1i) |
| `crud._fetch_character_brief_map`   | `GET /characters/{id}/short_info` | `/characters/internal/{id}/short_info` (C4i) |
| `main.move_and_post` (inline)       | `GET /attributes/{id}` | `/attributes/internal/{id}` (A1i) |
| `main.quick_move` (inline)          | `GET /attributes/{id}` | `/attributes/internal/{id}` (A1i) |

The first three are **exactly** the silent-failure shape §3.5 warns about:
each one catches every exception, logs a warning and returns `None` / an empty
entry. A forgotten header would not raise anywhere — gathering would silently
report "no stamina data", the shop discount would silently vanish, and the
"who is here" list would render blank names. So each is driven through the real
function with `httpx` captured, and the assertion reads
`call.kwargs["headers"]["X-Internal-Token"]`.

The last two have no client function to call: the request is written inline
inside a large endpoint handler. They are pinned with an AST walk over the
handler bodies instead (`TestTheInlineCallSitesInMain`) — a weaker but honest
guard, and better than the nothing that was there before.
"""

import ast
import os

import pytest

import crud
import main


TOKEN = "test-internal-token"

CHARACTER_ID = 11

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def token(monkeypatch):
    """Both modules read a module-level constant, not the env var."""
    monkeypatch.setattr(crud, "INTERNAL_SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def _patch(monkeypatch, module, response=None):
    calls = []
    resp = response if response is not None else _Resp(200, {})

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return resp

    monkeypatch.setattr(module.httpx, "AsyncClient", _Client)
    return calls


# ═══════════════════════════════════════════════════════════════════════════
# crud._read_current_stamina -> A1i
# ═══════════════════════════════════════════════════════════════════════════

class TestReadCurrentStamina:
    """Returns `None` on any failure; the caller reads that as "unknown" and
    carries on. Nothing raises, so only the header assertion catches a drop."""

    @pytest.mark.asyncio
    async def test_targets_the_internal_twin(self, monkeypatch, token):
        calls = _patch(monkeypatch, crud, _Resp(200, {"current_stamina": 7}))
        await crud._read_current_stamina(CHARACTER_ID)
        assert calls[0][0].endswith(f"/attributes/internal/{CHARACTER_ID}"), calls

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token):
        calls = _patch(monkeypatch, crud, _Resp(200, {"current_stamina": 7}))
        await crud._read_current_stamina(CHARACTER_ID)
        assert calls[0][1]["headers"]["X-Internal-Token"] == TOKEN

    @pytest.mark.asyncio
    async def test_the_value_still_reaches_the_caller(self, monkeypatch, token):
        _patch(monkeypatch, crud, _Resp(200, {"current_stamina": 7}))
        assert await crud._read_current_stamina(CHARACTER_ID) == 7

    @pytest.mark.asyncio
    async def test_a_401_returns_none_which_is_why_the_header_is_tested(
        self, monkeypatch, token
    ):
        _patch(monkeypatch, crud, _Resp(401, {"detail": "Недействительный internal token"}))
        assert await crud._read_current_stamina(CHARACTER_ID) is None

    @pytest.mark.asyncio
    async def test_the_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch(monkeypatch, crud, _Resp(200, {"current_stamina": 1}))
        monkeypatch.setattr(crud, "INTERNAL_SERVICE_TOKEN", "first")
        await crud._read_current_stamina(CHARACTER_ID)
        monkeypatch.setattr(crud, "INTERNAL_SERVICE_TOKEN", "second")
        await crud._read_current_stamina(CHARACTER_ID)
        assert [kw["headers"]["X-Internal-Token"] for _u, kw in calls] == [
            "first", "second"
        ]


# ═══════════════════════════════════════════════════════════════════════════
# crud._fetch_character_brief_map -> C4i
# ═══════════════════════════════════════════════════════════════════════════

BRIEF = {"id": CHARACTER_ID, "name": "Аэлис", "avatar": "a.webp"}


class TestFetchCharacterBriefMap:
    """Returns `{"name": "", "avatar": None}` for a failed id — a blank row in
    the UI, never an error. The twin is needed because the public `short_info`
    lost `currency_balance` (D7) and may keep thinning."""

    @pytest.mark.asyncio
    async def test_targets_the_internal_twin(self, monkeypatch, token):
        calls = _patch(monkeypatch, crud, _Resp(200, dict(BRIEF)))
        await crud._fetch_character_brief_map([CHARACTER_ID])
        assert calls[0][0].endswith(
            f"/characters/internal/{CHARACTER_ID}/short_info"
        ), calls

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token):
        calls = _patch(monkeypatch, crud, _Resp(200, dict(BRIEF)))
        await crud._fetch_character_brief_map([CHARACTER_ID])
        assert calls[0][1]["headers"]["X-Internal-Token"] == TOKEN, (
            "locations-service dropped X-Internal-Token on short_info — every "
            "name in «Кто здесь» would render empty and nothing would raise"
        )

    @pytest.mark.asyncio
    async def test_the_names_still_arrive(self, monkeypatch, token):
        _patch(monkeypatch, crud, _Resp(200, dict(BRIEF)))
        result = await crud._fetch_character_brief_map([CHARACTER_ID])
        assert result[CHARACTER_ID]["name"] == "Аэлис"

    @pytest.mark.asyncio
    async def test_a_401_degrades_to_a_blank_entry(self, monkeypatch, token):
        _patch(monkeypatch, crud, _Resp(401, {"detail": "нет"}))
        result = await crud._fetch_character_brief_map([CHARACTER_ID])
        assert result[CHARACTER_ID] == {"name": "", "avatar": None}

    @pytest.mark.asyncio
    async def test_every_id_in_a_batch_carries_the_header(self, monkeypatch, token):
        calls = _patch(monkeypatch, crud, _Resp(200, dict(BRIEF)))
        await crud._fetch_character_brief_map([1, 2, 3])
        assert len(calls) == 3
        for url, kwargs in calls:
            assert "/characters/internal/" in url
            assert kwargs["headers"]["X-Internal-Token"] == TOKEN

    @pytest.mark.asyncio
    async def test_an_empty_list_makes_no_call(self, monkeypatch, token):
        calls = _patch(monkeypatch, crud, _Resp(200, dict(BRIEF)))
        assert await crud._fetch_character_brief_map([]) == {}
        assert calls == []


# ═══════════════════════════════════════════════════════════════════════════
# main._fetch_charisma -> A1i
# ═══════════════════════════════════════════════════════════════════════════

class TestFetchCharisma:
    """Returns `None` on failure, which the shop reads as "no discount" — the
    player silently pays full price."""

    @pytest.mark.asyncio
    async def test_targets_the_internal_twin(self, monkeypatch, token):
        calls = _patch(monkeypatch, main, _Resp(200, {"charisma": 12}))
        await main._fetch_charisma(CHARACTER_ID)
        assert calls[0][0].endswith(f"/attributes/internal/{CHARACTER_ID}"), calls

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token):
        calls = _patch(monkeypatch, main, _Resp(200, {"charisma": 12}))
        await main._fetch_charisma(CHARACTER_ID)
        assert calls[0][1]["headers"]["X-Internal-Token"] == TOKEN

    @pytest.mark.asyncio
    async def test_the_value_still_reaches_the_discount(self, monkeypatch, token):
        _patch(monkeypatch, main, _Resp(200, {"charisma": 12}))
        assert await main._fetch_charisma(CHARACTER_ID) == 12

    @pytest.mark.asyncio
    async def test_a_401_returns_none_silently(self, monkeypatch, token):
        _patch(monkeypatch, main, _Resp(401, {"detail": "нет"}))
        assert await main._fetch_charisma(CHARACTER_ID) is None

    @pytest.mark.asyncio
    async def test_the_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch(monkeypatch, main, _Resp(200, {"charisma": 1}))
        monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "first")
        await main._fetch_charisma(CHARACTER_ID)
        monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "second")
        await main._fetch_charisma(CHARACTER_ID)
        assert [kw["headers"]["X-Internal-Token"] for _u, kw in calls] == [
            "first", "second"
        ]


# ═══════════════════════════════════════════════════════════════════════════
# The two inline call sites in main.py
# ═══════════════════════════════════════════════════════════════════════════

class TestTheInlineCallSitesInMain:
    """`move_and_post` and `quick_move` build the attributes URL inline, so
    there is no function to drive. An AST walk over those two handlers is the
    honest substitute: it resolves the local `attr_url = f"..."` assignment and
    checks both the path and the `headers=` argument of the `client.get` that
    consumes it."""

    HANDLERS = ("move_and_post", "quick_move")

    @staticmethod
    def _handler_nodes():
        with open(os.path.join(APP_DIR, "main.py"), encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        found = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found[node.name] = (node, source)
        return found

    @pytest.mark.parametrize("handler", HANDLERS)
    def test_the_handler_exists(self, handler):
        assert handler in self._handler_nodes(), (
            f"{handler} was renamed — this guard went blind"
        )

    @pytest.mark.parametrize("handler", HANDLERS)
    def test_the_attributes_url_is_the_internal_twin(self, handler):
        node, source = self._handler_nodes()[handler]
        assignments = [
            ast.get_source_segment(source, sub.value)
            for sub in ast.walk(node)
            if isinstance(sub, ast.Assign)
            and len(sub.targets) == 1
            and isinstance(sub.targets[0], ast.Name)
            and sub.targets[0].id == "attr_url"
        ]
        assert assignments, f"{handler} no longer builds `attr_url`"
        for value in assignments:
            assert "/attributes/internal/" in value, (handler, value)

    @pytest.mark.parametrize("handler", HANDLERS)
    def test_the_attributes_read_passes_the_header_helper(self, handler):
        node, source = self._handler_nodes()[handler]
        gets = [
            sub for sub in ast.walk(node)
            if isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "get"
            and any(
                isinstance(a, ast.Name) and a.id == "attr_url" for a in sub.args
            )
        ]
        assert gets, f"{handler} no longer reads attributes"
        for call in gets:
            headers = [kw for kw in call.keywords if kw.arg == "headers"]
            assert headers, (
                f"{handler} reads the attributes twin WITHOUT headers — it "
                "would 401 and the move would report 'characteristics not found'"
            )
            assert "_internal_token_headers" in (
                ast.get_source_segment(source, headers[0].value) or ""
            ), handler


# ═══════════════════════════════════════════════════════════════════════════
# Source sweep — nothing anonymous survived Pass A
# ═══════════════════════════════════════════════════════════════════════════

class TestNoAnonymousReadSurvives:

    @pytest.mark.parametrize("filename", ["main.py", "crud.py"])
    def test_no_gated_read_is_still_on_a_public_path(self, filename):
        import re

        with open(os.path.join(APP_DIR, filename), encoding="utf-8") as fh:
            source = fh.read()

        # Every reference to a neighbour's attributes or short_info route.
        hits = re.findall(r"(/attributes/[^\"'\s]*|/characters/[^\"'\s]*short_info)", source)
        assert hits, f"{filename}: the sweep matched nothing — it went blind"

        offenders = [
            h for h in hits
            if "/internal/" not in h
            and (h.endswith("short_info") or re.fullmatch(r"/attributes/\{[^}]+\}", h))
        ]
        assert offenders == [], (
            f"{filename} still reads a FEAT-171-gated route anonymously: {offenders}"
        )

    def test_the_sweep_really_catches_a_public_path(self):
        """Red-proof: the same filter over a sample containing the old path
        flags it, so a green result above means something."""
        import re

        sample = 'url = f"{settings.ATTRIBUTES_SERVICE_URL}/attributes/{character_id}"'
        hits = re.findall(r"(/attributes/[^\"'\s]*|/characters/[^\"'\s]*short_info)", sample)
        offenders = [
            h for h in hits
            if "/internal/" not in h
            and (h.endswith("short_info") or re.fullmatch(r"/attributes/\{[^}]+\}", h))
        ]
        assert offenders == ["/attributes/{character_id}"]

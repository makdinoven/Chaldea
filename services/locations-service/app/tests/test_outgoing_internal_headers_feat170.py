"""
FEAT-170 §3.12 c/d — locations-service's five remaining headerless call sites.

    POST {battle}/battles/internal/party/leave-on-move   main.move_and_post
    POST {battle}/battles/internal/party/leave-on-move   main.quick_move
    POST {battle}/battles/internal/party/leave-on-move   main.character_left_location_route
    POST {bp}/battle-pass/internal/track-event           main.move_and_post
    POST {bp}/battle-pass/internal/track-event           main.quick_move

**All five swallow their errors** (`except Exception: pass`, or a WARNING plus
`party_pruned=False`). That is the whole problem: once the target routes are
token-gated, a missing header produces a 401 that nothing anywhere observes —
the move still succeeds, the player still arrives, and only the battle-pass
credit and the pre-battle party cleanup silently stop happening. "Nothing
raised" therefore proves nothing here, so every test below asserts the header
**value** on the real handler with only the HTTP transport replaced, and
`TestDroppingTheHeaderWouldBeInvisible` proves the assertions bite.

The outgoing helper `main._internal_token_headers()` reads the module-level
`main.INTERNAL_SERVICE_TOKEN` captured at import, so the fixture pins the
module attribute rather than the env var.

The class at the bottom is the **inverted** source sweep: any call in this
service whose resolved URL points at an `/internal/` route must pass
`headers=`. There is no allowlist — an allowlist-based sweep goes green for
the wrong reason the moment one of its exempted targets is gated, which is
exactly what happened to the inventory-service sweep this feature had to fix.
"""

import os

import pytest
from unittest.mock import MagicMock

from fastapi import BackgroundTasks

import main
import schemas


TOKEN = "test-internal-token"

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

BATTLE_URL = "http://battle-service:8010"
BP_URL = "http://battle-pass-service:8012"

CHARACTER_ID = 31
CURRENT_LOCATION = 100
DESTINATION = 200
LONG_CONTENT = "А" * 400


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.text = "{}"
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _Result:
    def __init__(self, first=None):
        self._first = first

    def scalars(self):
        holder = MagicMock()
        holder.first.return_value = self._first
        return holder

    def fetchone(self):
        return None

    def scalar(self):
        return 0


class _MoveSession:
    """Async session for the two movement handlers: the neighbour lookup gives
    a free transition, every other lookup gives the destination location."""

    def __init__(self):
        self.statements = []
        self.neighbor = MagicMock()
        self.neighbor.energy_cost = 0
        self.location = MagicMock()
        self.location.id = DESTINATION
        self.location.name = "Цитадель"
        self.location.no_quick_move = False

    async def execute(self, statement, params=None):
        text = str(statement)
        self.statements.append(text)
        if "LocationNeighbors" in text:
            return _Result(first=self.neighbor)
        return _Result(first=self.location)


@pytest.fixture()
def token(monkeypatch):
    monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


@pytest.fixture()
def service_urls(monkeypatch):
    monkeypatch.setattr(main.settings, "BATTLE_SERVICE_URL", BATTLE_URL)
    monkeypatch.setattr(main.settings, "BATTLEPASS_SERVICE_URL", BP_URL)


@pytest.fixture()
def http_calls(monkeypatch):
    """Replace only the transport: `main.httpx.AsyncClient`. Everything the
    handlers do around it — including building the headers — stays real."""
    calls = []

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            calls.append(("GET", url, kwargs))
            if "profile" in url:
                return _Resp(payload={
                    "current_location_id": CURRENT_LOCATION,
                    "character_name": "Воин",
                    "travel_cooldown_until": None,
                })
            if "attributes" in url:
                return _Resp(payload={"current_stamina": 100})
            return _Resp()

        async def post(self, url, **kwargs):
            calls.append(("POST", url, kwargs))
            return _Resp()

        async def put(self, url, **kwargs):
            calls.append(("PUT", url, kwargs))
            return _Resp()

    monkeypatch.setattr(main.httpx, "AsyncClient", _Client)
    return calls


@pytest.fixture()
def movement_stubs(monkeypatch):
    """Neutralise everything around the two internal calls under test: the
    ownership/battle/gathering guards and the CRUD writes. The HTTP call sites
    themselves are untouched."""
    async def _noop(*args, **kwargs):
        return None

    async def _zero(*args, **kwargs):
        return 0

    post = MagicMock()
    post.id = 1
    post.character_id = CHARACTER_ID
    post.location_id = DESTINATION

    async def _create_post(session, post_in):
        return post

    async def _favorites(session, location_id):
        return []

    monkeypatch.setattr(main, "verify_character_ownership", _noop)
    monkeypatch.setattr(main, "check_not_in_battle", _noop)
    monkeypatch.setattr(main, "check_not_gathering", _noop)
    monkeypatch.setattr(main, "_count_unique_locations", _zero)
    monkeypatch.setattr(main.crud, "create_post", _create_post)
    monkeypatch.setattr(main.crud, "archive_draft_on_post", _noop)
    monkeypatch.setattr(main.crud, "get_favorite_user_ids", _favorites)
    monkeypatch.setattr(main.crud, "expire_action_gates", _zero)
    monkeypatch.setattr(main.crud, "expire_gate_requests", _zero)
    return post


def _user(user_id=10):
    user = MagicMock()
    user.id = user_id
    return user


def _of(calls, fragment):
    return [c for c in calls if fragment in c[1]]


async def _run_move(background=None):
    return await main.move_and_post(
        destination_location_id=DESTINATION,
        movement=schemas.MovementPostRequest(
            character_id=CHARACTER_ID, content=LONG_CONTENT),
        background_tasks=background or BackgroundTasks(),
        session=_MoveSession(),
        current_user=_user(),
    )


async def _run_quick_move(background=None):
    return await main.quick_move(
        destination_location_id=DESTINATION,
        body=schemas.QuickMoveRequest(character_id=CHARACTER_ID),
        background_tasks=background or BackgroundTasks(),
        session=_MoveSession(),
        current_user=_user(),
    )


async def _run_character_left_location():
    return await main.character_left_location_route(
        body=schemas.CharacterLeftLocationRequest(
            character_id=CHARACTER_ID, from_location_id=None),
        session=_MoveSession(),
        _=None,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. `POST /battles/internal/party/leave-on-move` — three call sites
# ══════════════════════════════════════════════════════════════════════════════


class TestLeaveOnMoveCarriesTheToken:
    """A pre-battle party is location-bound, so leaving the location must prune
    the character from it (the leader leaving disbands it). All three call
    sites are fire-and-forget: without the header the party survives the move
    and the player fights from a location they already left, with no error
    anywhere."""

    @pytest.mark.asyncio
    async def test_move_and_post_sends_the_token(
            self, token, service_urls, http_calls, movement_stubs):
        await _run_move()

        leave = _of(http_calls, "leave-on-move")
        assert leave, "move_and_post never pruned the pre-battle party"
        method, url, kwargs = leave[0]
        assert method == "POST"
        assert url == f"{BATTLE_URL}/battles/internal/party/leave-on-move", url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "move_and_post dropped X-Internal-Token on leave-on-move — the "
            "call is `except Exception: pass`, so the party would silently "
            "survive the move"
        )
        assert kwargs["params"] == {"character_id": CHARACTER_ID}

    @pytest.mark.asyncio
    async def test_quick_move_sends_the_token(
            self, token, service_urls, http_calls, movement_stubs):
        await _run_quick_move()

        leave = _of(http_calls, "leave-on-move")
        assert leave, "quick_move never pruned the pre-battle party"
        method, url, kwargs = leave[0]
        assert method == "POST"
        assert url == f"{BATTLE_URL}/battles/internal/party/leave-on-move", url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "quick_move dropped X-Internal-Token on leave-on-move"
        )
        assert kwargs["params"] == {"character_id": CHARACTER_ID}

    @pytest.mark.asyncio
    async def test_character_left_location_sends_the_token(
            self, token, service_urls, http_calls):
        result = await _run_character_left_location()

        leave = _of(http_calls, "leave-on-move")
        assert leave, "character-left-location never pruned the party"
        method, url, kwargs = leave[0]
        assert method == "POST"
        assert url == f"{BATTLE_URL}/battles/internal/party/leave-on-move", url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "character-left-location dropped X-Internal-Token — this caller "
            "only logs a WARNING and reports party_pruned=False"
        )
        assert kwargs["params"] == {"character_id": CHARACTER_ID}
        assert result.party_pruned is True

    @pytest.mark.asyncio
    async def test_a_401_is_reported_as_not_pruned_not_as_success(
            self, token, service_urls, monkeypatch):
        """The one caller that looks at the response must not mistake an auth
        failure for a completed cleanup."""
        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, **kwargs):
                return _Resp(status_code=401)

        monkeypatch.setattr(main.httpx, "AsyncClient", _Client)
        result = await _run_character_left_location()
        assert result.ok is True
        assert result.party_pruned is False


# ══════════════════════════════════════════════════════════════════════════════
# 2. `POST /battle-pass/internal/track-event` — two call sites
# ══════════════════════════════════════════════════════════════════════════════


class TestTrackEventCarriesTheToken:
    """Battle-pass progress for a location visit. Both call sites are
    `except Exception: pass`, so a dropped header costs the player their
    battle-pass credit with no error and no log line."""

    @pytest.mark.asyncio
    async def test_move_and_post_sends_the_token(
            self, token, service_urls, http_calls, movement_stubs):
        await _run_move()

        tracked = _of(http_calls, "track-event")
        assert tracked, "move_and_post never credited the battle pass"
        method, url, kwargs = tracked[0]
        assert method == "POST"
        assert url == f"{BP_URL}/battle-pass/internal/track-event", url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "move_and_post dropped X-Internal-Token on track-event — the call "
            "is fire-and-forget, so the battle-pass credit would vanish"
        )
        assert kwargs["json"]["event_type"] == "location_visit"
        assert kwargs["json"]["character_id"] == CHARACTER_ID
        assert kwargs["json"]["metadata"] == {"location_id": DESTINATION}

    @pytest.mark.asyncio
    async def test_quick_move_sends_the_token(
            self, token, service_urls, http_calls, movement_stubs):
        await _run_quick_move()

        tracked = _of(http_calls, "track-event")
        assert tracked, "quick_move never credited the battle pass"
        method, url, kwargs = tracked[0]
        assert method == "POST"
        assert url == f"{BP_URL}/battle-pass/internal/track-event", url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "quick_move dropped X-Internal-Token on track-event"
        )
        assert kwargs["json"]["event_type"] == "location_visit"

    @pytest.mark.asyncio
    async def test_no_call_at_all_when_the_battle_pass_url_is_empty(
            self, token, http_calls, movement_stubs, monkeypatch):
        monkeypatch.setattr(main.settings, "BATTLE_SERVICE_URL", BATTLE_URL)
        monkeypatch.setattr(main.settings, "BATTLEPASS_SERVICE_URL", "")
        await _run_move()
        assert not _of(http_calls, "track-event")


# ══════════════════════════════════════════════════════════════════════════════
# 3. Negative control — "nothing raised" is not evidence
# ══════════════════════════════════════════════════════════════════════════════


class TestDroppingTheHeaderWouldBeInvisible:
    """With the header helper neutered every one of the five calls still
    happens, still carries the right URL and body, and still raises nothing —
    the handlers return 200 exactly as before. The header is the *only*
    observable difference, which is why the tests above assert it and never
    assert "the move succeeded"."""

    @pytest.mark.asyncio
    async def test_the_move_still_succeeds_without_the_header(
            self, token, service_urls, http_calls, movement_stubs, monkeypatch):
        monkeypatch.setattr(main, "_internal_token_headers", dict)

        post = await _run_move()

        assert post is not None, "the move still returns its post"
        assert len(_of(http_calls, "leave-on-move")) == 1
        assert len(_of(http_calls, "track-event")) == 1
        for _, _url, kwargs in _of(http_calls, "leave-on-move") + \
                _of(http_calls, "track-event"):
            assert "X-Internal-Token" not in kwargs.get("headers", {}), (
                "the header is the only observable difference, so it is what "
                "the positive tests must assert"
            )

    @pytest.mark.asyncio
    async def test_character_left_location_still_reports_ok(
            self, token, service_urls, http_calls, monkeypatch):
        monkeypatch.setattr(main, "_internal_token_headers", dict)
        result = await _run_character_left_location()
        assert result.ok is True
        assert "X-Internal-Token" not in \
            _of(http_calls, "leave-on-move")[0][2].get("headers", {})

    @pytest.mark.asyncio
    async def test_the_helper_tracks_the_module_constant(
            self, service_urls, http_calls, movement_stubs, monkeypatch):
        """A rotated secret must reach the next call — the helper reads
        `main.INTERNAL_SERVICE_TOKEN` rather than freezing a value."""
        monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "first")
        await _run_move()
        monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "second")
        await _run_move()

        sent = [kwargs["headers"]["X-Internal-Token"]
                for _, _url, kwargs in _of(http_calls, "leave-on-move")]
        assert sent == ["first", "second"]


# ══════════════════════════════════════════════════════════════════════════════
# 4. Inverted source sweep — no allowlist, no exemptions
# ══════════════════════════════════════════════════════════════════════════════


class TestEveryInternalCallSiteSendsHeaders:
    """Any call in this service aimed at another service's `/internal/` route
    must pass `headers=`. Variable URLs (`url = f"..."` a line above the call)
    are resolved with the AST resolver shared with
    `inventory-service/app/tests/test_outgoing_internal_headers.py`.

    This is deliberately **inverted** relative to
    `test_internal_auth.py::TestGatedOutgoingCallsSweep`, which checks a named
    list of targets: a list only covers the calls someone remembered to add to
    it, and goes green for the wrong reason as soon as a listed target is
    exempted. Here every internal URL is in scope by construction, so the call
    site nobody has written yet is covered too.
    """

    SCANNED_FILES = ("main.py", "crud.py", "auth_http.py")

    #: `_sweep()` parses several thousand-line modules; the result only depends
    #: on the files on disk, so it is computed once per session.
    _CACHE = {}

    def _segment(self, node):
        """`ast.get_source_segment` without its per-call `splitlines()`.

        The stdlib helper re-splits the whole module for every node, which on
        this service's `crud.py` turns the sweep into minutes. Offsets are
        UTF-8 **byte** offsets (the sources are full of Cyrillic strings), so
        the slicing is done on encoded lines.
        """
        if getattr(node, "lineno", None) is None:
            return ""
        lines = self._blines
        start, end = node.lineno - 1, node.end_lineno - 1
        if start == end:
            return lines[start][node.col_offset:node.end_col_offset].decode(
                "utf-8", "replace")
        parts = [lines[start][node.col_offset:]]
        parts.extend(lines[start + 1:end])
        parts.append(lines[end][:node.end_col_offset])
        return b"\n".join(parts).decode("utf-8", "replace")

    def _resolve(self, source, tree):
        """{(start, end): {variable: assigned source}} per function scope."""
        import ast

        env = {}
        segment = self._segment

        class _V(ast.NodeVisitor):
            def _scope(self, node):
                local = {}
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assign) and len(sub.targets) == 1 \
                            and isinstance(sub.targets[0], ast.Name):
                        local[sub.targets[0].id] = segment(sub.value)
                env[(node.lineno, node.end_lineno)] = local
                self.generic_visit(node)

            visit_FunctionDef = _scope
            visit_AsyncFunctionDef = _scope

        _V().visit(tree)
        return env

    def _url_of(self, source, env, node):
        import ast

        raw = self._segment(node.args[0]) if node.args else ""
        raw = raw or ""
        if "/" in raw:
            return raw
        # a URL-building helper: inline its return expression
        if node.args and isinstance(node.args[0], ast.Call) \
                and isinstance(node.args[0].func, ast.Name):
            builder = node.args[0].func.id
            for sub in ast.walk(self._tree):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name == builder:
                    for inner in ast.walk(sub):
                        if isinstance(inner, ast.Return) and inner.value is not None:
                            return self._segment(inner.value) or raw
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

        cached = type(self)._CACHE.get("sweep")
        if cached is not None:
            return cached

        offenders = []
        inspected = []
        for filename in self.SCANNED_FILES:
            path = os.path.join(_APP_DIR, filename)
            if not os.path.exists(path):
                continue
            source = open(path, encoding="utf-8").read()
            tree = ast.parse(source)
            self._source, self._tree = source, tree
            self._blines = [line.encode("utf-8") for line in source.splitlines()]
            env = self._resolve(source, tree)

            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr not in ("post", "put", "patch", "delete", "get"):
                    continue
                base = self._segment(node.func.value)
                if base not in ("httpx", "client", "requests"):
                    continue
                url = self._url_of(source, env, node)
                # `internal/` rather than `/internal/`: some service URLs
                # already end with a slash, so the literal has none.
                if "internal/" not in url:
                    continue
                inspected.append((filename, node.lineno, url))
                if "headers" not in {kw.arg for kw in node.keywords}:
                    offenders.append(
                        f"{filename}:{node.lineno} {base}.{node.func.attr}"
                        f"({url[:70]}) без headers="
                    )
        type(self)._CACHE["sweep"] = (inspected, offenders)
        return inspected, offenders

    def test_no_internal_call_is_missing_headers(self):
        inspected, offenders = self._sweep()
        assert not offenders, (
            "межсервисный вызов на /internal/ без X-Internal-Token — целевой "
            "маршрут ответит 401, а вызывающий это проглотит: "
            + "; ".join(offenders)
        )

    def test_the_sweep_actually_inspected_the_known_call_sites(self):
        """Floor, so a URL refactor cannot quietly empty the sweep. 12 internal
        call sites exist in this service today (3 leave-on-move, 2 track-event,
        2 update_location, 2 set_travel_cooldown and 3 item grants)."""
        inspected, _ = self._sweep()
        assert len(inspected) >= 12, (
            f"свип нашёл только {len(inspected)} внутренних вызовов — URL "
            "отрефакторили, и проверка стала пустой: "
            + "; ".join(f"{f}:{line}" for f, line, _url in inspected)
        )

    def test_the_five_feat170_call_sites_are_inside_the_sweep(self):
        inspected, _ = self._sweep()
        urls = [url for _f, _line, url in inspected]
        assert sum("leave-on-move" in url for url in urls) == 3, urls
        assert sum("track-event" in url for url in urls) == 2, urls

    def test_the_sweep_has_no_allowlist(self):
        """FEAT-170: pin the inversion. An allowlist here would exempt exactly
        the targets most likely to be freshly gated."""
        attrs = {name for name, value in vars(type(self)).items()
                 if isinstance(value, (tuple, list, set, frozenset))
                 and any(word in name.upper()
                         for word in ("UNGATED", "ALLOW", "EXEMPT", "SKIP"))
                 and name != "SCANNED_FILES"}
        assert not attrs, f"allowlist reintroduced into the sweep: {attrs}"

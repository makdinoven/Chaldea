"""
FEAT-170 T15 — char-attrs must send `X-Internal-Token` on its outgoing calls
into other services' `/internal/` routes.

The call this feature added is `perk_evaluator._fetch_quest_completed`
(`perk_evaluator.py:88`) -> `GET /locations/quests/internal/check-completed`,
now gated on the locations side. It **swallows every exception and returns
`False`** — "no, this character has not completed that quest" — so a dropped
header does not raise anything at all: perks with a quest condition simply stop
unlocking, forever, with one WARNING in the log. "Nothing blew up" therefore
proves nothing here, and the assertions below are on the header value itself
(`call.kwargs["headers"]["X-Internal-Token"]`), with
`test_dropping_the_header_would_be_caught` as the negative control proving the
assertion actually bites.

`perk_evaluator` builds the header locally from `config.settings` on purpose:
`main.py` imports this module lazily (`main.py:342, :694, :1410, :1446`,
`crud.py:729`, `regen.py:336`) because a top-level import cycles, so
`from main import _internal_token_headers` is forbidden. `TestNoImportCycle`
pins that the module still imports on its own.

The second half of the file is the **inverted source sweep**: instead of an
allowlist of known-gated prefixes (which a new internal target silently slips
past), *any* call in char-attrs whose resolved URL contains `/internal/` must
pass `headers=`. The AST URL resolver is the one from
`inventory-service/app/tests/test_outgoing_internal_headers.py`.
"""

import ast
import os
import subprocess
import sys

import httpx
import pytest

import perk_evaluator
from config import settings


APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

TOKEN = "test-internal-token"
QUEST_URL_SUFFIX = "/locations/quests/internal/check-completed"


@pytest.fixture()
def token(monkeypatch):
    """`_internal_token_headers` reads `settings`, captured at import."""
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = {} if payload is None else payload

    def json(self):
        return self._payload


def _patch_httpx_get(monkeypatch, response=None):
    """`_fetch_quest_completed` does `import httpx` *inside* the function, so
    the real module attribute is what has to be replaced."""
    calls = []
    resp = response or _Resp(200, {"completed": True})

    def _get(url, **kwargs):
        calls.append((url, kwargs))
        return resp

    monkeypatch.setattr(httpx, "get", _get)
    return calls


# ══════════════════════════════════════════════════════════════════════════════
# 1. The call site itself — assert the header, never "nothing raised"
# ══════════════════════════════════════════════════════════════════════════════


class TestFetchQuestCompletedSendsTheToken:

    def test_sends_the_internal_token(self, monkeypatch, token):
        calls = _patch_httpx_get(monkeypatch)

        assert perk_evaluator._fetch_quest_completed(11, 5) is True

        assert len(calls) == 1, "the quest-completion check never left char-attrs"
        url, kwargs = calls[0]
        assert url == f"{settings.LOCATIONS_SERVICE_URL}{QUEST_URL_SUFFIX}", url
        assert "headers" in kwargs, (
            "the check-completed call went out with no headers= at all — "
            "locations-service answers 401 and the perk never unlocks"
        )
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "char-attrs dropped X-Internal-Token on check-completed — "
            "locations-service answers 401, `_fetch_quest_completed` swallows "
            "it and returns False, and every quest-conditioned perk silently "
            "stops unlocking"
        )
        assert kwargs["params"] == {"character_id": 11, "quest_id": 5}

    def test_the_call_uses_mock_call_kwargs_shape(self, monkeypatch, token):
        """Same assertion written against `unittest.mock`, the shape §3.12(c)
        names explicitly — so a future reader cannot mistake the hand-rolled
        recorder above for a weaker check."""
        from unittest.mock import MagicMock

        mock_get = MagicMock(return_value=_Resp(200, {"completed": False}))
        monkeypatch.setattr(httpx, "get", mock_get)

        assert perk_evaluator._fetch_quest_completed(11, 5) is False

        call = mock_get.call_args
        assert call.args[0].endswith(QUEST_URL_SUFFIX), call.args
        assert call.kwargs["headers"]["X-Internal-Token"] == TOKEN

    def test_a_401_is_swallowed_but_the_header_was_still_sent(self, monkeypatch, token):
        """Documents why the header — not the return value — is the assertion:
        a gated route answering 401 is indistinguishable from "quest not
        completed" to every caller of this function."""
        calls = _patch_httpx_get(monkeypatch, _Resp(401, {"detail": "нет"}))

        assert perk_evaluator._fetch_quest_completed(11, 5) is False

        assert calls[0][1]["headers"]["X-Internal-Token"] == TOKEN

    def test_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch_httpx_get(monkeypatch)
        monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", "first")
        perk_evaluator._fetch_quest_completed(1, 1)
        monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", "second")
        perk_evaluator._fetch_quest_completed(1, 1)
        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    def test_missing_token_still_sends_the_key(self, monkeypatch):
        """Fail-closed on the callee side: the key is always present, so a
        misconfiguration surfaces as a clear 401 rather than a mystery."""
        monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", "")
        calls = _patch_httpx_get(monkeypatch)
        perk_evaluator._fetch_quest_completed(1, 1)
        assert calls[0][1]["headers"]["X-Internal-Token"] == ""

    def test_dropping_the_header_would_be_caught(self, monkeypatch, token):
        """Negative control for every assertion above.

        `_fetch_quest_completed` swallows its errors, so if a future edit
        removed `headers=_internal_token_headers()` the call count, the return
        value and the absence of an exception would all look exactly the same.
        The header is the only observable difference — this test proves the
        assertions are sensitive to it.
        """
        calls = _patch_httpx_get(monkeypatch)
        monkeypatch.setattr(perk_evaluator, "_internal_token_headers", dict)

        assert perk_evaluator._fetch_quest_completed(11, 5) is True

        assert len(calls) == 1, "the call still happens — a count assertion sees nothing"
        assert "X-Internal-Token" not in (calls[0][1].get("headers") or {}), (
            "the header is the only observable difference, so it is what the "
            "positive tests must assert"
        )


class TestTheHelperItself:

    def test_builds_the_header_from_settings(self, token):
        assert perk_evaluator._internal_token_headers() == {"X-Internal-Token": TOKEN}

    def test_the_public_reads_stay_header_free(self, monkeypatch, token):
        """`_fetch_character_level` / `_fetch_gold_balance` target the public
        `/characters/{id}/full_profile` — nobody may leak the service secret
        onto a public route "for symmetry"."""
        calls = _patch_httpx_get(monkeypatch, _Resp(200, {"level": 4, "currency_balance": 9}))

        assert perk_evaluator._fetch_character_level(11) == 4
        assert perk_evaluator._fetch_gold_balance(11) == 9

        for url, kwargs in calls:
            assert "/internal/" not in url, url
            assert "X-Internal-Token" not in (kwargs.get("headers") or {}), url


class TestNoImportCycle:
    """§3.6: the header must come from `config.settings`, never from `main`.

    `main` imports `perk_evaluator` lazily precisely because a top-level import
    cycles; importing `main` from here would re-create that cycle and take the
    service down at start-up. A fresh interpreter is used so that an already
    imported `main` in this process cannot mask the problem.
    """

    def test_module_imports_on_its_own(self):
        proc = subprocess.run(
            [sys.executable, "-c",
             "import perk_evaluator;"
             " assert perk_evaluator._internal_token_headers();"
             " print('IMPORT_OK')"],
            cwd=APP_DIR,
            env={**os.environ, "PYTHONPATH": APP_DIR},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert "IMPORT_OK" in proc.stdout

    def test_the_source_does_not_import_main(self):
        source = open(
            os.path.join(APP_DIR, "perk_evaluator.py"), encoding="utf-8",
        ).read()
        assert "from main import" not in source
        assert "import main" not in source


# ══════════════════════════════════════════════════════════════════════════════
# 2. Inverted source sweep — no allowlist, no exemptions
# ══════════════════════════════════════════════════════════════════════════════
#
# The per-call tests above pin the one call site that exists today. This sweep
# covers the ones nobody has written yet. The rule is deliberately inverted
# relative to the FEAT-167/169 sweeps, which listed the *gated* prefixes and so
# waved through any new internal target that was not on the list.


class TestEveryInternalCallSiteSendsHeaders:
    """Any call in char-attrs whose resolved URL contains `/internal/` must
    pass `headers=`. Variable URLs (`url = f"..."` a line above the call) are
    resolved, because that is how most call sites are written."""

    FILES = ("main.py", "crud.py", "perk_evaluator.py", "regen.py")

    #: Floor so that a URL refactor cannot silently empty the sweep.
    #: 6 in `main.py` + 1 in `perk_evaluator.py` as of FEAT-170.
    MIN_CHECKED = 7

    def _resolve(self, source, tree):
        """{(start, end) of a function: {variable: assigned source}}."""
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
        offenders, checked = [], []
        for filename in self.FILES:
            path = os.path.join(APP_DIR, filename)
            if not os.path.exists(path):
                continue
            source = open(path, encoding="utf-8").read()
            tree = ast.parse(source)
            env = self._resolve(source, tree)

            # `@app.get("/attributes/internal/...")` is a route *declaration*,
            # not an outgoing call — skip every decorator expression.
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
            "маршрут ответит 401, а вызывающий это проглотит: "
            + "; ".join(offenders)
        )

    def test_the_sweep_has_no_allowlist(self):
        """The FEAT-167/169 sweeps listed the *gated* prefixes, so a new
        internal target that nobody added to the list passed silently. This one
        must stay inverted — no exemption list may be re-introduced."""
        attrs = {name for name in dir(self) if not name.startswith("test_")}
        forbidden = {"GATED", "KNOWN_UNGATED_TARGETS", "_KNOWN_UNGATED_TARGETS",
                     "EXEMPT", "SKIP", "ALLOWLIST"}
        assert not (attrs & forbidden), (
            "an exemption list crept back into the inverted sweep: "
            f"{sorted(attrs & forbidden)}"
        )

    def test_the_known_internal_call_sites_are_still_there(self):
        """Guard for the sweep itself: if the URLs are refactored out of
        recognition the sweep silently matches nothing."""
        main_source = open(os.path.join(APP_DIR, "main.py"), encoding="utf-8").read()
        perk_source = open(
            os.path.join(APP_DIR, "perk_evaluator.py"), encoding="utf-8",
        ).read()
        assert "/characters/internal/evaluate-titles" in main_source
        assert "/characters/internal/{character_id}/logs" in main_source
        assert QUEST_URL_SUFFIX in perk_source
        assert "_internal_token_headers()" in perk_source

"""
FEAT-171 task 19 (character-attributes-service) — the three reads of
`full_profile` moved onto the C1i twin.

character-attributes-service reads character-service for two numbers — the
character's level and its gold balance — and both live on `full_profile`,
which became **style A**: a stranger gets a thinned body with no
`currency_balance` and no `level_progress` at all. This service has no user in
context, so the public route would hand it the *stranger* shape and the gold
condition would silently evaluate against `None`.

| call site | now |
|---|---|
| `perk_evaluator._fetch_character_level` | `GET /characters/internal/{id}/full_profile` (C1i) |
| `perk_evaluator._fetch_gold_balance`    | `GET /characters/internal/{id}/full_profile` (C1i) |
| `main.upgrade_attributes`               | `GET /characters/internal/{id}/full_profile` (C1i) |

The first two are the dangerous ones. They catch every exception, log and
return `None`, and `perk_evaluator.compare` treats a `None` as "condition not
met" — so a dropped header would not fail a request, it would quietly stop
granting every level-gated and gold-gated perk in the game. That is why the
assertions read the recorded request and not the return value.

The third is loud (404), but it is the stat-point spend path: a wrong header
there would tell the player «Character not found» while the character sits
right in front of them.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest

import perk_evaluator
from config import settings


TOKEN = "test-internal-token"
CHARACTER_ID = 11

FULL_PROFILE = {
    "name": "Герой", "level": 7, "currency_balance": 1234, "stat_points": 3,
}


@pytest.fixture()
def token(monkeypatch):
    """Both modules build the header from `settings` at call time."""
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.text = "{}"
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


@pytest.fixture()
def blocking_get():
    """`perk_evaluator` imports httpx *inside* the function (to avoid an import
    cycle), so the patch has to land on the httpx module itself."""
    with patch("httpx.get") as mock_get:
        mock_get.return_value = _Resp(200, dict(FULL_PROFILE))
        yield mock_get


READERS = [
    ("level", lambda: perk_evaluator._fetch_character_level(CHARACTER_ID), 7),
    ("gold", lambda: perk_evaluator._fetch_gold_balance(CHARACTER_ID), 1234),
]
_PARAMS = [pytest.param(*r, id=r[0]) for r in READERS]


# ═══════════════════════════════════════════════════════════════════════════
# perk_evaluator — the two silent readers
# ═══════════════════════════════════════════════════════════════════════════

class TestPerkEvaluatorReadsTheTwin:

    @pytest.mark.parametrize("label,call,expected", _PARAMS)
    def test_targets_the_internal_twin(self, token, blocking_get, label, call, expected):
        call()
        url = blocking_get.call_args.args[0]
        assert url.endswith(f"/characters/internal/{CHARACTER_ID}/full_profile"), (
            label, url
        )

    @pytest.mark.parametrize("label,call,expected", _PARAMS)
    def test_sends_the_internal_token(self, token, blocking_get, label, call, expected):
        call()
        headers = blocking_get.call_args.kwargs["headers"]
        assert headers["X-Internal-Token"] == TOKEN, (
            f"{label}: the header is gone — every level- and gold-gated perk "
            "would silently stop unlocking, with only a warning in the log"
        )

    @pytest.mark.parametrize("label,call,expected", _PARAMS)
    def test_never_uses_the_public_route(self, token, blocking_get, label, call, expected):
        """The public `full_profile` answers a stranger with the THIN shape —
        no `currency_balance` key at all — so a drift back there does not even
        fail: it reads `None` gold and quietly refuses every gold perk."""
        call()
        assert "/characters/internal/" in blocking_get.call_args.args[0]

    @pytest.mark.parametrize("label,call,expected", _PARAMS)
    def test_the_value_still_arrives(self, token, blocking_get, label, call, expected):
        assert call() == expected

    @pytest.mark.parametrize("label,call,expected", _PARAMS)
    def test_a_401_is_swallowed_which_is_why_the_header_is_tested(
        self, token, blocking_get, label, call, expected
    ):
        blocking_get.return_value = _Resp(401, {"detail": "нет"})
        assert call() is None

    @pytest.mark.parametrize("label,call,expected", _PARAMS)
    def test_a_thin_stranger_body_reads_as_none_not_as_an_error(
        self, token, blocking_get, label, call, expected
    ):
        """Exactly what the public route would return to this service: a 200
        whose private keys are absent. Nothing raises — the perk just never
        unlocks. This is the failure mode the twin exists to prevent."""
        blocking_get.return_value = _Resp(
            200, {"id": CHARACTER_ID, "name": "Герой", "level": 7}
        )
        result = call()
        if label == "gold":
            assert result is None, (
                "a thin body must not be mistaken for a real balance"
            )
        else:
            assert result == 7

    @pytest.mark.parametrize("label,call,expected", _PARAMS)
    def test_the_token_is_read_at_call_time(
        self, monkeypatch, blocking_get, label, call, expected
    ):
        monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", "first")
        call()
        first = blocking_get.call_args.kwargs["headers"]["X-Internal-Token"]
        monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", "second")
        call()
        second = blocking_get.call_args.kwargs["headers"]["X-Internal-Token"]
        assert (first, second) == ("first", "second")

    @pytest.mark.parametrize("label,call,expected", _PARAMS)
    def test_dropping_the_header_would_be_caught(
        self, token, blocking_get, label, call, expected
    ):
        """Red-proof kept in the suite: a headerless call looks like this, and
        the assertion above rejects it."""
        call()
        headers = dict(blocking_get.call_args.kwargs["headers"])
        headers.pop("X-Internal-Token")
        with pytest.raises(KeyError):
            headers["X-Internal-Token"]


# ═══════════════════════════════════════════════════════════════════════════
# main.upgrade_attributes — the stat-point spend path
# ═══════════════════════════════════════════════════════════════════════════

class TestUpgradeReadsTheTwin:
    """The read is written inline inside the handler, so it is pinned with an
    AST walk over that function rather than by driving the endpoint (which
    would need the whole attribute/ownership stack)."""

    @staticmethod
    def _handler():
        import ast

        path = os.path.join(os.path.dirname(__file__), "..", "main.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name == "upgrade_attributes":
                return node, source
        raise AssertionError("upgrade_attributes was renamed — guard went blind")

    def test_the_url_is_the_internal_twin(self):
        import ast

        node, source = self._handler()
        values = [
            ast.get_source_segment(source, sub.value)
            for sub in ast.walk(node)
            if isinstance(sub, ast.Assign)
            and len(sub.targets) == 1
            and isinstance(sub.targets[0], ast.Name)
            and sub.targets[0].id == "full_profile_url"
        ]
        assert values, "upgrade_attributes no longer builds `full_profile_url`"
        for value in values:
            assert "/characters/internal/" in value, value

    def test_the_read_passes_the_header_helper(self):
        import ast

        node, source = self._handler()
        gets = [
            sub for sub in ast.walk(node)
            if isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "get"
            and any(
                isinstance(a, ast.Name) and a.id == "full_profile_url"
                for a in sub.args
            )
        ]
        assert gets, "upgrade_attributes no longer reads the profile"
        for call in gets:
            headers = [kw for kw in call.keywords if kw.arg == "headers"]
            assert headers, (
                "the profile read has no headers= — the twin answers 401 and "
                "the player is told «Character not found»"
            )
            assert "_internal_token_headers" in (
                ast.get_source_segment(source, headers[0].value) or ""
            )


# ═══════════════════════════════════════════════════════════════════════════
# Source sweep
# ═══════════════════════════════════════════════════════════════════════════

class TestNoAnonymousProfileReadSurvives:

    @pytest.mark.parametrize("filename", ["main.py", "perk_evaluator.py", "crud.py"])
    def test_no_full_profile_read_is_still_public(self, filename):
        import re

        path = os.path.join(os.path.dirname(__file__), "..", filename)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()

        hits = re.findall(r"/characters/[^\"'\s]*full_profile", source)
        offenders = [h for h in hits if "/internal/" not in h]
        assert offenders == [], (
            f"{filename} still reads full_profile on the public path: {offenders}"
        )

    def test_the_sweep_really_catches_a_public_path(self):
        import re

        sample = 'url = f"{settings.CHARACTER_SERVICE_URL}/characters/{cid}/full_profile"'
        hits = re.findall(r"/characters/[^\"'\s]*full_profile", sample)
        assert [h for h in hits if "/internal/" not in h] == [
            "/characters/{cid}/full_profile"
        ]

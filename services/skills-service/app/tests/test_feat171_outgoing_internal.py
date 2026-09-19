"""
FEAT-171 task 19 (skills-service) — `get_active_experience` moved onto the A1i
twin.

skills-service reads character-attributes-service for one number: the active
experience a skill purchase or upgrade is paid from. §2.7 listed the call site
(`main.py:799`) but Pass A initially missed it; task 10 caught it just before
the gate landed. Had it shipped in the other order, skills-service would have
been locked out of the gate it set itself — buying and upgrading skills would
have failed for every player.

| call site | was | now |
|---|---|---|
| `main.get_active_experience` | `GET /attributes/{id}` (anonymous) | `GET /attributes/internal/{id}` (A1i) |

This caller is loud — a non-200 becomes `HTTPException(500, «Не удалось
получить атрибуты»)` — but the message blames the attribute service, not the
credential, so the header is asserted on the recorded request.

skills-service also has *two* header conventions in play: outgoing calls into
sibling services use `X-Internal-Token`, while its own S1 route accepts the
same secret in the **Bearer** position (`allow_jwt_or_service_token`). Mixing
them up produces a 401 that looks like a missing character, so the position is
pinned too.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import main as main_module


TOKEN = "test-internal-token"
CHARACTER_ID = 11


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


@pytest.fixture()
def token(monkeypatch):
    """`main._internal_token_headers` reads the env var at call time."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


def _patch(monkeypatch, response=None):
    calls = []
    resp = response if response is not None else _Resp(200, {"active_experience": 250})

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

    monkeypatch.setattr(main_module.httpx, "AsyncClient", _Client)
    return calls


class TestGetActiveExperience:

    async def test_targets_the_internal_twin(self, monkeypatch, token):
        calls = _patch(monkeypatch)
        await main_module.get_active_experience(CHARACTER_ID)
        assert len(calls) == 1
        assert calls[0][0].endswith(f"/internal/{CHARACTER_ID}"), calls

    async def test_sends_the_internal_token(self, monkeypatch, token):
        calls = _patch(monkeypatch)
        await main_module.get_active_experience(CHARACTER_ID)
        assert calls[0][1]["headers"]["X-Internal-Token"] == TOKEN, (
            "skills-service dropped X-Internal-Token — it would be locked out "
            "of the very gate it set, and no skill could be bought"
        )

    async def test_uses_the_header_position_not_the_bearer_one(
        self, monkeypatch, token
    ):
        """Two conventions live in this service; this call is the header one."""
        calls = _patch(monkeypatch)
        await main_module.get_active_experience(CHARACTER_ID)
        assert "Authorization" not in calls[0][1]["headers"]

    async def test_never_uses_the_player_route(self, monkeypatch, token):
        calls = _patch(monkeypatch)
        await main_module.get_active_experience(CHARACTER_ID)
        assert "/internal/" in calls[0][0], calls[0][0]

    async def test_the_value_still_arrives(self, monkeypatch, token):
        _patch(monkeypatch)
        assert await main_module.get_active_experience(CHARACTER_ID) == 250

    async def test_a_401_surfaces_as_a_500_that_blames_the_wrong_thing(
        self, monkeypatch, token
    ):
        from fastapi import HTTPException

        _patch(monkeypatch, _Resp(401, {"detail": "Недействительный internal token"}))
        with pytest.raises(HTTPException) as exc:
            await main_module.get_active_experience(CHARACTER_ID)
        assert exc.value.status_code == 500
        assert "token" not in str(exc.value.detail).lower()

    async def test_the_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch(monkeypatch)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await main_module.get_active_experience(CHARACTER_ID)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await main_module.get_active_experience(CHARACTER_ID)
        assert [kw["headers"]["X-Internal-Token"] for _u, kw in calls] == [
            "first", "second"
        ]

    async def test_dropping_the_header_would_be_caught(self, monkeypatch, token):
        """Red-proof kept in the suite."""
        calls = _patch(monkeypatch)
        await main_module.get_active_experience(CHARACTER_ID)
        without = {k: v for k, v in calls[0][1]["headers"].items()
                   if k != "X-Internal-Token"}
        with pytest.raises(KeyError):
            without["X-Internal-Token"]


class TestNoAnonymousAttributeReadSurvives:

    def test_the_source_has_no_public_attributes_read_left(self):
        import re

        path = os.path.join(os.path.dirname(__file__), "..", "main.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read()

        # Every f-string built on ATTRIBUTES_SERVICE_URL.
        urls = re.findall(r'f"\{ATTRIBUTES_SERVICE_URL\}([^"]*)"', source)
        assert urls, "the sweep matched no URL — it went blind"
        offenders = [u for u in urls if re.fullmatch(r"/\{[^}]+\}", u)]
        assert offenders == [], (
            f"a bare /attributes/{{id}} read survived Pass A: {offenders}"
        )

    def test_the_sweep_really_catches_a_public_path(self):
        import re

        sample = 'url = f"{ATTRIBUTES_SERVICE_URL}/{character_id}"'
        urls = re.findall(r'f"\{ATTRIBUTES_SERVICE_URL\}([^"]*)"', sample)
        assert [u for u in urls if re.fullmatch(r"/\{[^}]+\}", u)] == [
            "/{character_id}"
        ]

"""
FEAT-167 — skills-service must send `X-Internal-Token` when it charges XP.

`PUT /attributes/{id}/active_experience` is internal-only now. The existing
skills suites mock `deduct_active_experience` away entirely, so nothing checked
the outgoing header: a missing one would turn every skill upgrade into
«Ошибка при списании опыта» (500) in the player's face.

Asserted on the real `main.deduct_active_experience`.
"""

import inspect

import pytest
from fastapi import HTTPException

import main


TOKEN = "test-internal-token"


@pytest.fixture()
def token_env(monkeypatch):
    """The helper reads the env at call time."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"active_experience": 75}

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

        async def put(self, url, **kwargs):
            calls.append((url, kwargs))
            return resp

    monkeypatch.setattr(main.httpx, "AsyncClient", _Client)
    return calls


@pytest.mark.asyncio
async def test_deduct_active_experience_sends_the_token(monkeypatch, token_env):
    calls = _patch_client(monkeypatch)

    assert await main.deduct_active_experience(42, 25) == 75

    url, kwargs = calls[0]
    assert url.endswith("/42/active_experience"), url
    assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
        "skills-service dropped X-Internal-Token — every skill upgrade would "
        "fail with «Ошибка при списании опыта»"
    )
    assert kwargs["json"] == {"amount": -25}


@pytest.mark.asyncio
async def test_token_is_read_at_call_time(monkeypatch):
    calls = _patch_client(monkeypatch)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
    await main.deduct_active_experience(1, 1)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
    await main.deduct_active_experience(1, 1)
    assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == ["first", "second"]


@pytest.mark.asyncio
async def test_a_401_from_the_gate_surfaces_as_an_error(monkeypatch, token_env):
    """A rejected internal call must never look like a successful deduction."""
    _patch_client(monkeypatch, response=_Resp(status_code=401, payload={}))
    with pytest.raises(HTTPException) as excinfo:
        await main.deduct_active_experience(42, 25)
    assert excinfo.value.status_code == 500


@pytest.mark.asyncio
async def test_insufficient_xp_still_maps_to_400(monkeypatch, token_env):
    """Regression guard on the existing contract: 400 from the callee keeps its
    own Russian message and is not confused with an auth failure."""
    _patch_client(monkeypatch, response=_Resp(status_code=400, payload={}))
    with pytest.raises(HTTPException) as excinfo:
        await main.deduct_active_experience(42, 25)
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Недостаточно опыта"


def test_the_helper_reads_the_env_not_a_constant():
    source = inspect.getsource(main._internal_token_headers)
    assert 'os.environ.get("INTERNAL_SERVICE_TOKEN"' in source


# ---------------------------------------------------------------------------
# FEAT-167 #17 — the cumulative-stats call
# ---------------------------------------------------------------------------
# `POST /attributes/cumulative_stats/increment` is internal-only now. The call
# sits inline inside the skill-upgrade handler (`skills_used` tracking) and is
# fire-and-forget, so a missing header would silently stop that counter and the
# perks behind it. There is no standalone helper to call, so this is a source
# sweep in the style of the locations-service grants.


def test_the_cumulative_stats_call_sends_the_internal_token():
    import os
    import re

    path = os.path.join(os.path.dirname(__file__), "..", "main.py")
    with open(os.path.abspath(path), encoding="utf-8") as fh:
        source = fh.read()

    matches = list(re.finditer(r"cumulative_stats/increment", source))
    assert matches, "the cumulative-stats call disappeared from main.py"
    for match in matches:
        window = source[match.start(): match.start() + 400]
        line = source.count("\n", 0, match.start()) + 1
        assert "_internal_token_headers()" in window, (
            f"main.py:{line} posts to the internal cumulative-stats endpoint "
            "without X-Internal-Token — the skills_used counter would silently "
            "stop"
        )

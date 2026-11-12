"""
FEAT-212 Task 16 — `http_clients.get_character_profile` reads the internal twin
(`/characters/internal/{id}/profile` + X-Internal-Token): the public route masks a
caravan escort (frozen hire location, no lock), which would let him past the entry
checks. Old character-service without the twin (404) -> public route.
"""

import pytest
from fastapi import HTTPException

import http_clients
from config import settings

TOKEN = "test-internal-token"


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=httpx.Request("GET", "http://x"),
                                        response=httpx.Response(self.status_code))

    def json(self):
        return self._payload


def _patch(monkeypatch, responses):
    calls = []
    queue = list(responses)

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return queue.pop(0)

    monkeypatch.setattr(http_clients.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return calls


@pytest.mark.asyncio
async def test_profile_reads_the_internal_twin(monkeypatch):
    calls = _patch(monkeypatch, [_Resp(payload={"current_location_id": 9, "activity_lock": {"locked": True}})])
    prof = await http_clients.get_character_profile(5)
    assert prof["current_location_id"] == 9 and prof["activity_lock"]["locked"] is True
    assert calls == [(f"{settings.CHARACTER_SERVICE_URL}/characters/internal/5/profile",
                      {"headers": {"X-Internal-Token": TOKEN}})]


@pytest.mark.asyncio
async def test_profile_falls_back_to_public_on_old_character_service(monkeypatch):
    calls = _patch(monkeypatch, [_Resp(404), _Resp(payload={"user_id": 1})])
    assert (await http_clients.get_character_profile(5)) == {"user_id": 1}
    assert calls[1][0] == f"{settings.CHARACTER_SERVICE_URL}/characters/5/profile"


@pytest.mark.asyncio
async def test_missing_character_is_still_404(monkeypatch):
    _patch(monkeypatch, [_Resp(404), _Resp(404)])
    with pytest.raises(HTTPException) as exc:
        await http_clients.get_character_profile(5)
    assert exc.value.status_code == 404

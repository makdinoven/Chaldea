"""
FEAT-212 Task 16 — locations-service reads the character's REAL location from the
internal profile twin (`/characters/internal/{id}/profile`, X-Internal-Token): the public
`/characters/{id}/profile` masks a caravan escort with his frozen hire location.
Deploy skew: an old character-service without the twin answers 404 -> public route.
"""

import pytest

import main
from config import settings

TOKEN = "test-internal-token"


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.mark.asyncio
async def test_reads_the_internal_twin_with_the_token():
    client = _Client([_Resp(payload={"current_location_id": 7})])
    resp = await main._get_character_profile(client, 5)
    assert resp.json() == {"current_location_id": 7}
    assert client.calls == [
        (f"{settings.CHARACTER_SERVICE_URL}/characters/internal/5/profile", {"headers": {"X-Internal-Token": TOKEN}}),
    ]


@pytest.mark.asyncio
async def test_old_character_service_falls_back_to_the_public_route():
    client = _Client([_Resp(404), _Resp(payload={"current_location_id": 3})])
    resp = await main._get_character_profile(client, 5)
    assert resp.status_code == 200 and resp.json()["current_location_id"] == 3
    assert [c[0] for c in client.calls] == [
        f"{settings.CHARACTER_SERVICE_URL}/characters/internal/5/profile",
        f"{settings.CHARACTER_SERVICE_URL}/characters/5/profile",
    ]


@pytest.mark.asyncio
async def test_missing_character_stays_404():
    client = _Client([_Resp(404), _Resp(404)])
    assert (await main._get_character_profile(client, 5)).status_code == 404


@pytest.mark.asyncio
async def test_no_location_check_reads_the_public_profile_anymore():
    """Every `current_location_id` check in main.py goes through the helper (no raw public URL left)."""
    import inspect
    src = inspect.getsource(main)
    assert src.count("await _get_character_profile(client,") == 4
    assert 'characters/{body.character_id}/profile"' not in src
    assert 'characters/{movement.character_id}/profile"' not in src

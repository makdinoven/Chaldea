"""
(FEAT-125) Tests for the rewritten battle-service skills_client:

- get_resolved_skill(skill_id, character_id) -> GET /skills/{id}/resolved
- character_has_skill(character_id, skill_id) -> ownership check via /characters/{id}/skills
- character_skills(character_id) -> list of owned skills, normalized

skills-service is mocked at the httpx layer.
"""

import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Set env vars before importing config
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Drop any MagicMock-replaced skills_client left by other test files.
for _mod in ("skills_client",):
    if _mod in sys.modules and isinstance(sys.modules[_mod], MagicMock):
        del sys.modules[_mod]

import database  # noqa: E402
database.engine = MagicMock()

import skills_client  # noqa: E402

# Save direct references; later test files (e.g. test_battle_fixes.py) inject
# AsyncMock into sys.modules["skills_client"], which would otherwise hide
# the real functions when this module's tests run after them.
_real_get_resolved_skill = skills_client.get_resolved_skill
_real_character_has_skill = skills_client.character_has_skill
_real_character_skills = skills_client.character_skills


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_httpx_response(json_data):
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _make_mock_client(api_response):
    mock_resp = _mock_httpx_response(api_response)
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


_RESOLVED_PAYLOAD = {
    "skill_id": 7,
    "character_id": 100,
    "level": 2,
    "selected_perk_ids": [10, 11],
    "skill_type": "Attack",
    "cost_energy": 4,
    "cost_mana": 12,
    "cooldown": 0,
    "level_requirement": 1,
    "damage_entries": [
        {"damage_type": "fire", "amount": 10.0, "chance": 100,
         "target_side": "enemy", "weapon_slot": "main_weapon"},
    ],
    "effects": [
        {"effect_name": "burn", "target_side": "enemy",
         "chance": 100, "duration": 2, "magnitude": 1.0},
    ],
}


# ---------------------------------------------------------------------------
# get_resolved_skill
# ---------------------------------------------------------------------------

class TestGetResolvedSkill:

    @pytest.mark.asyncio
    async def test_calls_correct_url_with_params(self):
        mock_client = _make_mock_client(_RESOLVED_PAYLOAD)
        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            result = await _real_get_resolved_skill(skill_id=7, character_id=100)
        # Assert the URL ends with /skills/7/resolved and has correct query
        call_args = mock_client.get.call_args
        url = call_args[0][0]
        assert url.endswith("/skills/7/resolved")
        params = call_args[1]["params"]
        assert params == {"character_id": 100}
        # skill_type normalized to lowercase
        assert result["skill_type"] == "attack"
        assert result["damage_entries"][0]["damage_type"] == "fire"

    @pytest.mark.asyncio
    async def test_byte_compatible_damage_and_effect_fields(self):
        """Resolver output preserves byte-compatible field names (R1)."""
        mock_client = _make_mock_client(_RESOLVED_PAYLOAD)
        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            result = await _real_get_resolved_skill(skill_id=7, character_id=100)
        de = result["damage_entries"][0]
        for key in ("damage_type", "amount", "chance", "target_side", "weapon_slot"):
            assert key in de
        ef = result["effects"][0]
        for key in ("effect_name", "target_side", "chance", "duration", "magnitude"):
            assert key in ef


# ---------------------------------------------------------------------------
# character_has_skill
# ---------------------------------------------------------------------------

class TestCharacterHasSkill:

    @pytest.mark.asyncio
    async def test_returns_true_when_skill_owned(self):
        api = [
            {"character_skill_id": 1, "skill_id": 7, "level": 0, "selected_perk_ids": []},
            {"character_skill_id": 2, "skill_id": 9, "level": 1, "selected_perk_ids": []},
        ]
        mock_client = _make_mock_client(api)
        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            assert await _real_character_has_skill(100, 7) is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_owned(self):
        api = [{"character_skill_id": 1, "skill_id": 9, "level": 0, "selected_perk_ids": []}]
        mock_client = _make_mock_client(api)
        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            assert await _real_character_has_skill(100, 7) is False


# ---------------------------------------------------------------------------
# character_skills
# ---------------------------------------------------------------------------

class TestCharacterSkillsList:

    @pytest.mark.asyncio
    async def test_returns_normalized_list(self):
        api = [
            {
                "character_skill_id": 1, "skill_id": 7, "level": 1,
                "free_perk_points": 0, "selected_perk_ids": [10],
                "skill": {"id": 7, "name": "Fireball",
                          "skill_type": "Attack", "skill_image": "/img.png"},
            },
        ]
        mock_client = _make_mock_client(api)
        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            results = await _real_character_skills(100)

        assert len(results) == 1
        row = results[0]
        assert row["skill_id"] == 7
        # skill_type denormalized + lowercased
        assert row["skill_type"] == "attack"
        # `id` alias points to skill_id (consumed by autobattle/strategy)
        assert row["id"] == 7
        assert row["skill_image"] == "/img.png"

    @pytest.mark.asyncio
    async def test_empty_list(self):
        mock_client = _make_mock_client([])
        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            assert await _real_character_skills(100) == []

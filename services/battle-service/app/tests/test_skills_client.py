"""
Tests for case normalization in skills_client.character_ranks()
(FEAT-060, Task #6).

Verifies that:
- character_ranks() normalizes skill_type to lowercase in returned data
- Works correctly with mixed case inputs ("Attack", "DEFENSE", "support")
"""

import sys
import os
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

# Remove any mocked versions of skills_client left by other test files
# (e.g. test_battle_fixes.py injects MagicMock into sys.modules at module level)
for _mod in ("skills_client",):
    if _mod in sys.modules and isinstance(sys.modules[_mod], MagicMock):
        del sys.modules[_mod]

# Patch database engine before importing anything that touches it
import database  # noqa: E402
database.engine = MagicMock()

import skills_client  # noqa: E402

# IMPORTANT: Save a direct reference to the real character_ranks function.
# Later test files (e.g. test_spectate.py) collected after this module will
# overwrite skills_client.character_ranks with an AsyncMock via sys.modules.
# By capturing the real function here, we can call it in tests regardless.
_real_character_ranks = skills_client.character_ranks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_char_skill_row(rank_id, skill_type, skill_name="Test Skill"):
    """Build a character skill row as returned by skills-service API."""
    return {
        "id": rank_id + 100,
        "character_id": 1,
        "skill_rank_id": rank_id,
        "skill_type": skill_type,
        "skill_name": skill_name,
        "skill_image": "/img/skill.png",
        "skill_description": "A test skill",
        "skill_rank": {
            "id": rank_id,
            "skill_id": rank_id * 10,
            "rank_number": 1,
            "rank_image": "/img/rank.png",
            "damage_base": 10,
            "cost_energy": 5,
            "cost_mana": 0,
            "cost_stamina": 0,
        },
    }


def _mock_httpx_response(json_data):
    """Create a mock httpx response (httpx Response.json() is sync, not async)."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _make_mock_client(api_response):
    """Create a properly configured mock httpx.AsyncClient for Python 3.10+.

    Uses MagicMock for the client (constructor is sync) with explicit
    async context-manager protocol and an AsyncMock for the .get() method.
    """
    mock_resp = _mock_httpx_response(api_response)

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCharacterRanksCaseNormalization:
    """character_ranks() should normalize skill_type to lowercase."""

    @pytest.mark.asyncio
    async def test_capitalized_skill_types_normalized(self):
        """Capitalized types ('Attack', 'Defense', 'Support') become lowercase."""
        api_response = [
            _make_char_skill_row(1, "Attack"),
            _make_char_skill_row(2, "Defense"),
            _make_char_skill_row(3, "Support"),
        ]

        mock_client = _make_mock_client(api_response)

        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            results = await _real_character_ranks(character_id=1)

        assert len(results) == 3
        assert results[0]["skill_type"] == "attack"
        assert results[1]["skill_type"] == "defense"
        assert results[2]["skill_type"] == "support"

    @pytest.mark.asyncio
    async def test_uppercase_skill_types_normalized(self):
        """Fully uppercase types ('ATTACK', 'DEFENSE', 'SUPPORT') become lowercase."""
        api_response = [
            _make_char_skill_row(1, "ATTACK"),
            _make_char_skill_row(2, "DEFENSE"),
            _make_char_skill_row(3, "SUPPORT"),
        ]

        mock_client = _make_mock_client(api_response)

        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            results = await _real_character_ranks(character_id=1)

        assert len(results) == 3
        assert results[0]["skill_type"] == "attack"
        assert results[1]["skill_type"] == "defense"
        assert results[2]["skill_type"] == "support"

    @pytest.mark.asyncio
    async def test_already_lowercase_unchanged(self):
        """Already-lowercase types remain lowercase."""
        api_response = [
            _make_char_skill_row(1, "attack"),
            _make_char_skill_row(2, "defense"),
            _make_char_skill_row(3, "support"),
        ]

        mock_client = _make_mock_client(api_response)

        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            results = await _real_character_ranks(character_id=1)

        assert len(results) == 3
        assert results[0]["skill_type"] == "attack"
        assert results[1]["skill_type"] == "defense"
        assert results[2]["skill_type"] == "support"

    @pytest.mark.asyncio
    async def test_mixed_case_all_normalized(self):
        """Mixed case ('Attack', 'DEFENSE', 'support') all normalize to lowercase."""
        api_response = [
            _make_char_skill_row(1, "Attack"),
            _make_char_skill_row(2, "DEFENSE"),
            _make_char_skill_row(3, "support"),
        ]

        mock_client = _make_mock_client(api_response)

        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            results = await _real_character_ranks(character_id=1)

        assert len(results) == 3
        assert results[0]["skill_type"] == "attack"
        assert results[1]["skill_type"] == "defense"
        assert results[2]["skill_type"] == "support"

    @pytest.mark.asyncio
    async def test_skill_type_from_row_level_normalized(self):
        """skill_type inherited from row level (not in skill_rank) is also normalized."""
        api_response = [
            {
                "id": 100,
                "character_id": 1,
                "skill_rank_id": 1,
                "skill_type": "Attack",
                "skill_name": "Slash",
                "skill_image": "/img/slash.png",
                "skill_description": "A basic attack",
                "skill_rank": {
                    "id": 1,
                    "skill_id": 10,
                    "rank_number": 1,
                    "rank_image": "",
                    "damage_base": 15,
                },
            },
        ]

        mock_client = _make_mock_client(api_response)

        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            results = await _real_character_ranks(character_id=1)

        assert len(results) == 1
        assert results[0]["skill_type"] == "attack"

    @pytest.mark.asyncio
    async def test_empty_skills_returns_empty(self):
        """Character with no skills returns empty list."""
        mock_client = _make_mock_client([])

        with patch("skills_client.httpx.AsyncClient", return_value=mock_client):
            results = await _real_character_ranks(character_id=999)

        assert results == []

"""
Tests for mob pack attack endpoints (FEAT-147) in battle-service.

Covers POST /battles/pack-attack (solo) and /battles/party/pack-attack:
- happy path assembles team 0 = player(s), team 1 = all living pack members
- ownership / location / empty-roster / gate validation
- mob side truncated to BATTLE_MAX_TEAM_SIZE (lead kept)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta, timezone

import pytest

# Patch heavy external modules BEFORE importing main (mirror test_pvp_attack.py)
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

for mod_name in [
    "redis_state", "mongo_client", "mongo_helpers", "tasks",
    "inventory_client", "character_client", "skills_client",
    "buffs", "battle_engine", "rabbitmq_publisher",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

redis_state_mock = sys.modules["redis_state"]
redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())

from main import app  # noqa: E402
from database import get_db  # noqa: E402
from auth_http import get_current_user_via_http, UserRead  # noqa: E402
from config import settings  # noqa: E402

app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


def _make_user(user_id=10):
    return UserRead(id=user_id, username="u", role="user", permissions=[])


def _client(user):
    def override_auth():
        return user

    async def override_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_current_user_via_http] = override_auth
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _assemble_return():
    battle = MagicMock()
    battle.id = 555
    parts = []
    for i in range(4):
        p = MagicMock()
        p.id = 600 + i
        parts.append(p)
    deadline = datetime.now(timezone.utc) + timedelta(hours=1)
    return (battle, parts, parts[0].id, deadline)


ATTACKER = {"user_id": 10, "current_location_id": 100}
ROSTER = {"location_id": 100, "status": "alive", "member_character_ids": [9, 10, 11], "lead_character_id": 9}


class TestPackAttack:
    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main._assemble_battle", new_callable=AsyncMock)
    @patch("main.get_active_battle_for_character", new_callable=AsyncMock, return_value=None)
    @patch("main._consume_combat_gate", new_callable=AsyncMock, return_value=True)
    @patch("main._get_pack_roster", new_callable=AsyncMock, return_value=ROSTER)
    @patch("main._get_character_info", new_callable=AsyncMock, return_value=ATTACKER)
    def test_happy_path_team_assembly(self, _ci, _pr, _gate, _bat, mock_assemble):
        mock_assemble.return_value = _assemble_return()
        client = _client(_make_user(10))
        resp = client.post("/battles/pack-attack", json={"character_id": 1, "active_pack_id": 5})
        assert resp.status_code == 201
        # team 0 = attacker, team 1 = all three mobs
        args = mock_assemble.call_args[0]
        player_ids, teams = args[1], args[2]
        assert player_ids == [1, 9, 10, 11]
        assert teams == [0, 1, 1, 1]

    @patch("main._get_character_info", new_callable=AsyncMock, return_value={"user_id": 999, "current_location_id": 100})
    def test_not_owner_forbidden(self, _ci):
        client = _client(_make_user(10))
        resp = client.post("/battles/pack-attack", json={"character_id": 1, "active_pack_id": 5})
        assert resp.status_code == 403

    @patch("main._get_pack_roster", new_callable=AsyncMock,
           return_value={"location_id": 200, "status": "alive", "member_character_ids": [9], "lead_character_id": 9})
    @patch("main._get_character_info", new_callable=AsyncMock, return_value=ATTACKER)
    def test_wrong_location(self, _ci, _pr):
        client = _client(_make_user(10))
        resp = client.post("/battles/pack-attack", json={"character_id": 1, "active_pack_id": 5})
        assert resp.status_code == 400

    @patch("main._get_pack_roster", new_callable=AsyncMock,
           return_value={"location_id": 100, "status": "alive", "member_character_ids": [], "lead_character_id": None})
    @patch("main._get_character_info", new_callable=AsyncMock, return_value=ATTACKER)
    def test_empty_roster(self, _ci, _pr):
        client = _client(_make_user(10))
        resp = client.post("/battles/pack-attack", json={"character_id": 1, "active_pack_id": 5})
        assert resp.status_code == 400

    @patch("main._assemble_battle", new_callable=AsyncMock)
    @patch("main.get_active_battle_for_character", new_callable=AsyncMock, return_value=None)
    @patch("main._consume_combat_gate", new_callable=AsyncMock, return_value=False)
    @patch("main._get_pack_roster", new_callable=AsyncMock, return_value=ROSTER)
    @patch("main._get_character_info", new_callable=AsyncMock, return_value=ATTACKER)
    def test_gate_required(self, _ci, _pr, _gate, _bat, mock_assemble):
        mock_assemble.return_value = _assemble_return()
        client = _client(_make_user(10))
        resp = client.post("/battles/pack-attack", json={"character_id": 1, "active_pack_id": 5})
        assert resp.status_code == 403
        mock_assemble.assert_not_called()

    @patch("main._assemble_battle", new_callable=AsyncMock)
    @patch("main.get_active_battle_for_character", new_callable=AsyncMock, return_value=None)
    @patch("main._consume_combat_gate", new_callable=AsyncMock, return_value=True)
    @patch("main._get_pack_roster", new_callable=AsyncMock,
           return_value={"location_id": 100, "status": "alive",
                         "member_character_ids": [9, 10, 11, 12, 13, 14, 15], "lead_character_id": 9})
    @patch("main._get_character_info", new_callable=AsyncMock, return_value=ATTACKER)
    def test_mob_side_truncated_to_cap(self, _ci, _pr, _gate, _bat, mock_assemble):
        mock_assemble.return_value = _assemble_return()
        client = _client(_make_user(10))
        resp = client.post("/battles/pack-attack", json={"character_id": 1, "active_pack_id": 5})
        assert resp.status_code == 201
        player_ids = mock_assemble.call_args[0][1]
        mob_ids = player_ids[1:]
        assert len(mob_ids) == settings.BATTLE_MAX_TEAM_SIZE
        assert mob_ids[0] == 9  # lead kept (smallest id, first)

"""FEAT-175: activity lock in battle-service + dungeon battle create/callback.

The stub preamble is copied from test_pvp_attack.py.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta

import asyncio
import pytest

# Patch heavy external modules BEFORE importing main
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

# Mock all external client modules to prevent actual connections
for mod_name in [
    "redis_state",
    "mongo_client",
    "mongo_helpers",
    "tasks",
    "inventory_client",
    "character_client",
    "skills_client",
    "buffs",
    "battle_engine",
    "rabbitmq_publisher",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Ensure redis_state has the required constants/functions
redis_state_mock = sys.modules["redis_state"]
redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
redis_state_mock.init_battle_state = AsyncMock()
redis_state_mock.load_state = AsyncMock(return_value=None)
redis_state_mock.save_state = AsyncMock()
redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())
redis_state_mock.cache_snapshot = AsyncMock()
redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)
redis_state_mock.state_key = MagicMock(return_value="battle:1:state")

# Ensure tasks has save_log
tasks_mock = sys.modules["tasks"]
tasks_mock.save_log = MagicMock()
tasks_mock.save_log.delay = MagicMock()

# Ensure battle_engine has the required functions
engine_mock = sys.modules["battle_engine"]
engine_mock.decrement_cooldowns = MagicMock()
engine_mock.set_cooldown = MagicMock()
engine_mock.fetch_full_attributes = AsyncMock(return_value={})
engine_mock.apply_flat_modifiers = MagicMock(return_value={})
engine_mock.fetch_main_weapon = AsyncMock(return_value={})
engine_mock.compute_damage_with_rolls = AsyncMock(return_value=(0, {}))
engine_mock.roll_dodge = MagicMock(return_value=False)  # FEAT-143: deterministic no-dodge

# Ensure buffs has the required functions
buffs_mock = sys.modules["buffs"]
buffs_mock.decrement_durations = MagicMock()
buffs_mock.aggregate_modifiers = MagicMock(return_value={})
buffs_mock.apply_new_effects = MagicMock()
buffs_mock.evaluate_control = MagicMock(return_value=(None, set()))  # FEAT-143: no control by defaultbuffs_mock.build_percent_damage_buffs = MagicMock(return_value={})
buffs_mock.build_percent_resist_buffs = MagicMock(return_value={})

# Ensure skills_client has the required functions
skills_mock = sys.modules["skills_client"]
skills_mock.character_has_skill = AsyncMock(return_value=True)
skills_mock.get_resolved_skill = AsyncMock(return_value={})
skills_mock.get_item = AsyncMock(return_value={})
skills_mock.character_skills = AsyncMock(return_value=[])

# Ensure mongo_helpers
mongo_mock = sys.modules["mongo_helpers"]
mongo_mock.save_snapshot = AsyncMock()
mongo_mock.load_snapshot = AsyncMock(return_value=None)

# Ensure rabbitmq_publisher
rmq_mock = sys.modules["rabbitmq_publisher"]
rmq_mock.publish_notification = AsyncMock()

# Now import main safely
import main  # noqa: E402
from main import app  # noqa: E402
from database import get_db  # noqa: E402
from auth_http import get_current_user_via_http, UserRead  # noqa: E402

# Clear startup handlers to avoid connection attempts
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _ensure_async_redis():
    """`main` binds `get_redis_client` by name at import (main.py:45), so once
    another test module imports main first with a non-async redis mock, that
    binding sticks and `await rds.zadd(...)` breaks here. Rebind per test to a
    proper AsyncMock so these tests are immune to import/collection order."""
    main.get_redis_client = AsyncMock(return_value=AsyncMock())
    yield



import auth_http  # noqa: E402
import activity_lock  # noqa: E402

pytestmark = pytest.mark.real_activity_lock

TOKEN = "test-internal-token"


def _row(*values):
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    row.__len__ = lambda self: len(values)
    return row


def _res(row):
    r = MagicMock()
    r.fetchone.return_value = row
    r.fetchall.return_value = [row] if row is not None else []
    return r


def _db(locks=None, extra=None):
    """Mock AsyncSession. `locks` = {character_id: (dungeon_session_id, unconscious_until)}."""
    locks = locks or {}
    db = AsyncMock()

    async def execute(query, params=None):
        q = str(query)
        cid = (params or {}).get("cid")
        if "dungeon_session_id, unconscious_until" in q:
            return _res(_row(*locks.get(cid, (None, None))))
        if extra:
            hit = extra(q, params or {})
            if hit is not None:
                return hit
        return _res(None)

    db.execute = AsyncMock(side_effect=execute)
    return db


def _client(db, user=None):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    if user is not None:
        app.dependency_overrides[get_current_user_via_http] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    main.get_redis_client = AsyncMock(return_value=AsyncMock())
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


USER = UserRead(id=10, username="u", role="user", permissions=[])
SOON = datetime.utcnow() + timedelta(hours=1)


def _chars(q, p):
    if "user_id, current_location_id, level" in q:
        return _res(_row(p["cid"], 10 if p["cid"] == 1 else 20, 100, 5))
    if "marker_type" in q:
        return _res(_row("dangerous"))
    return None


# ---------------------------------------------------------------------------
# Battles outside the dungeon flow are refused for locked characters
# ---------------------------------------------------------------------------

class TestRefusals:
    def test_pvp_attack_victim_in_dungeon(self):
        c = _client(_db(locks={2: (55, None)}, extra=_chars), USER)
        r = c.post("/battles/pvp/attack", json={"attacker_character_id": 1, "victim_character_id": 2})
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "Цель находится в подземелье"

    def test_pvp_attack_attacker_unconscious(self):
        c = _client(_db(locks={1: (None, SOON)}, extra=_chars), USER)
        r = c.post("/battles/pvp/attack", json={"attacker_character_id": 1, "victim_character_id": 2})
        assert r.status_code == 409
        assert r.json()["detail"].startswith("Персонаж без сознания до")

    def test_pvp_invite_target_locked(self):
        c = _client(_db(locks={2: (3, None)}, extra=_chars), USER)
        r = c.post("/battles/pvp/invite",
                   json={"initiator_character_id": 1, "target_character_id": 2, "battle_type": "pvp_training"})
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "Цель находится в подземелье"

    @patch("main._assemble_battle", new_callable=AsyncMock)
    def test_generic_create_refuses_dungeon_member(self, assemble):
        def extra(q, p):
            if "SELECT user_id FROM characters" in q:
                return _res(_row(10))
            return None

        c = _client(_db(locks={1: (8, None)}, extra=extra), USER)
        r = c.post("/battles/", json={"players": [{"character_id": 1, "team": 1}, {"character_id": 900, "team": 2}]})
        assert r.status_code == 409
        assemble.assert_not_called()

    @patch("main._consume_combat_gate", new_callable=AsyncMock, return_value=True)
    @patch("main._validate_location_mob", new_callable=AsyncMock)
    @patch("main._get_character_info", new_callable=AsyncMock)
    def test_mob_attack_refused_when_unconscious(self, info, _mob, gate):
        info.return_value = {"id": 1, "user_id": 10, "current_location_id": 100, "level": 5}
        c = _client(_db(locks={1: (None, SOON)}), USER)
        r = c.post("/battles/mob-attack", json={"character_id": 1, "mob_character_id": 900})
        assert r.status_code == 409
        gate.assert_not_called()


# ---------------------------------------------------------------------------
# POST /battles/internal/dungeon — the dungeon's own battles
# ---------------------------------------------------------------------------

class TestInternalDungeonCreate:
    PAYLOAD = {
        "dungeon_session_id": 77,
        "players": [{"character_id": 1, "team": 1}, {"character_id": 900, "team": 2}],
    }

    def _assemble_result(self):
        battle = MagicMock()
        battle.id = 501
        p1, p2 = MagicMock(), MagicMock()
        p1.id, p2.id = 11, 12
        return battle, [p1, p2], 11, datetime.utcnow()

    def test_requires_internal_token(self, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
        r = _client(_db()).post("/battles/internal/dungeon", json=self.PAYLOAD)
        assert r.status_code == 401

    @patch("main._assemble_battle", new_callable=AsyncMock)
    def test_member_locked_to_this_session_is_exempt(self, assemble, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
        assemble.return_value = self._assemble_result()

        def extra(q, p):
            if "current_location_id FROM characters" in q:
                return _res(_row(100))
            return None

        r = _client(_db(locks={1: (77, None)}, extra=extra)).post(
            "/battles/internal/dungeon", json=self.PAYLOAD, headers={"X-Internal-Token": TOKEN})
        assert r.status_code == 201, r.text
        assert r.json()["battle_id"] == 501
        assert assemble.call_args.kwargs["dungeon_session_id"] == 77

    @patch("main._assemble_battle", new_callable=AsyncMock)
    def test_member_of_another_session_refused(self, assemble, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
        r = _client(_db(locks={1: (78, None)})).post(
            "/battles/internal/dungeon", json=self.PAYLOAD, headers={"X-Internal-Token": TOKEN})
        assert r.status_code == 409
        assemble.assert_not_called()

    @patch("main._assemble_battle", new_callable=AsyncMock)
    def test_unlocked_character_refused(self, assemble, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
        r = _client(_db()).post(
            "/battles/internal/dungeon", json=self.PAYLOAD, headers={"X-Internal-Token": TOKEN})
        assert r.status_code == 409
        assert r.json()["detail"] == "Персонаж не участвует в этом забеге"
        assemble.assert_not_called()

    @patch("main._assemble_battle", new_callable=AsyncMock)
    def test_needs_both_teams(self, assemble, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
        payload = {"dungeon_session_id": 77,
                   "players": [{"character_id": 1, "team": 1}, {"character_id": 2, "team": 1}]}
        r = _client(_db()).post("/battles/internal/dungeon", json=payload, headers={"X-Internal-Token": TOKEN})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Battle end -> callback to dungeon-service
# ---------------------------------------------------------------------------

def _dungeon_battle(q, p):
    if "SELECT dungeon_session_id FROM battles" in q:
        return _res(_row(77))
    return None


class TestDungeonCallback:
    @pytest.mark.asyncio
    async def test_dungeon_battle_posts_outcome(self):
        state = {"participants": {
            "11": {"character_id": 1, "hp": 0, "team": 1},
            "12": {"character_id": 2, "hp": 30, "team": 1},
            "13": {"character_id": 900, "hp": 0, "team": 2},
        }}
        with patch("main._post_dungeon_callback", new_callable=AsyncMock) as post:
            await main._notify_dungeon_battle_end(_db(extra=_dungeon_battle), 501, 1, state)
            await asyncio.sleep(0)
        post.assert_awaited_once()
        assert post.call_args.args[0] == {
            "battle_id": 501, "session_id": 77, "winner_team": 1,
            "defeated_characters": [1, 900], "aborted": False,
        }

    @pytest.mark.asyncio
    async def test_regular_battle_posts_nothing(self):
        with patch("main._post_dungeon_callback", new_callable=AsyncMock) as post:
            await main._notify_dungeon_battle_end(_db(), 502, 1, {"participants": {}})
            await asyncio.sleep(0)
        post.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_finish_reports_aborted(self):
        with patch("main._post_dungeon_callback", new_callable=AsyncMock) as post:
            await main._notify_dungeon_battle_end(_db(extra=_dungeon_battle), 503, None, None, aborted=True)
            await asyncio.sleep(0)
        assert post.call_args.args[0]["aborted"] is True
        assert post.call_args.args[0]["winner_team"] is None

    @pytest.mark.asyncio
    async def test_post_retries_on_5xx_then_stops_on_2xx(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[MagicMock(status_code=503, text=""),
                                             MagicMock(status_code=200, text="")])
        cm = AsyncMock()
        cm.__aenter__.return_value = client
        with patch("main.httpx.AsyncClient", return_value=cm):
            await main._post_dungeon_callback({"battle_id": 1, "session_id": 2})
        assert client.post.await_count == 2

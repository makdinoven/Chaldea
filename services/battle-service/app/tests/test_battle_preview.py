"""
Tests for GET /battles/{battle_id}/preview (FEAT-151, profile Battles tab).

Covers:
1.  200 — full compact DTO shape: battle_id, battle_type, turn_number,
    location_id/location_name, turn_order (is_current from next_actor),
    participants (is_ally, is_alive, hp/max_hp, mana/max_mana from Redis
    runtime, name/avatar from snapshot, team as string)
2.  200 — is_ally computed from the requester's own participant team
    (enemy perspective flips the flags)
3.  200 — dead participant (hp = 0) -> is_alive false
4.  200 — participant missing from snapshot -> fallback name "Участник #pid"
5.  200 — empty avatar in snapshot -> null
6.  200 — Locations row absent -> location_name null
7.  200 — battle without location_id -> location_name null, no Locations query
8.  401 — missing / invalid JWT
9.  403 — authenticated non-participant ("Вы не участвуете в этом бою")
10. 404 — battle row absent ("Бой не найден")
11. 404 — battle finished / forfeit ("Бой не найден или уже завершён"),
    returned even for non-participants (status gate precedes ownership)
12. 404 — Redis state missing (finished-battle race)
"""

import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches (same approach as test_spectate.py)
# ──────────────────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

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

# Configure redis_state mock
redis_state_mock = sys.modules["redis_state"]
redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
redis_state_mock.init_battle_state = AsyncMock()
redis_state_mock.load_state = AsyncMock(return_value=None)
redis_state_mock.save_state = AsyncMock()
redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())
redis_state_mock.cache_snapshot = AsyncMock()
redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)
redis_state_mock.state_key = MagicMock(side_effect=lambda bid: f"battle:{bid}:state")

# Configure tasks mock
tasks_mock = sys.modules["tasks"]
tasks_mock.save_log = MagicMock()
tasks_mock.save_log.delay = MagicMock()

# Configure battle_engine mock
engine_mock = sys.modules["battle_engine"]
engine_mock.decrement_cooldowns = MagicMock()
engine_mock.set_cooldown = MagicMock()
engine_mock.fetch_full_attributes = AsyncMock(return_value={})
engine_mock.apply_flat_modifiers = MagicMock(return_value={})
engine_mock.fetch_main_weapon = AsyncMock(return_value={})
engine_mock.compute_damage_with_rolls = AsyncMock(return_value=(0, {}))
engine_mock.roll_dodge = MagicMock(return_value=False)

# Configure buffs mock
buffs_mock = sys.modules["buffs"]
buffs_mock.decrement_durations = MagicMock()
buffs_mock.aggregate_modifiers = MagicMock(return_value={})
buffs_mock.apply_new_effects = MagicMock()
buffs_mock.evaluate_control = MagicMock(return_value=(None, set()))
buffs_mock.build_percent_damage_buffs = MagicMock(return_value={})
buffs_mock.build_percent_resist_buffs = MagicMock(return_value={})

# Configure skills_client mock
skills_mock = sys.modules["skills_client"]
skills_mock.character_has_skill = AsyncMock(return_value=True)
skills_mock.get_resolved_skill = AsyncMock(return_value={})
skills_mock.get_item = AsyncMock(return_value={})
skills_mock.character_skills = AsyncMock(return_value=[])

# Configure mongo_helpers mock
mongo_mock = sys.modules["mongo_helpers"]
mongo_mock.save_snapshot = AsyncMock()
mongo_mock.load_snapshot = AsyncMock(return_value=None)

# Now import main safely
from main import app  # noqa: E402
from database import get_db  # noqa: E402
from models import BattleStatus, BattleType  # noqa: E402

# Clear startup handlers to avoid connection attempts
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


AUTH_USER = {"id": 1, "username": "player", "role": "user", "permissions": []}
AUTH_HEADERS = {"Authorization": "Bearer fake-token"}


def _make_battle(
    battle_id=1,
    status=BattleStatus.in_progress,
    battle_type=BattleType.pve,
    location_id=44,
):
    """Return a mock Battle ORM row using REAL enums (status/battle_type)."""
    battle = MagicMock()
    battle.id = battle_id
    battle.status = status
    battle.battle_type = battle_type
    battle.location_id = location_id
    battle.is_paused = False
    return battle


def _make_state(next_actor=1, turn_number=4, participants=None, turn_order=None):
    """Fresh Redis runtime state per test (handler must not depend on extras)."""
    if participants is None:
        participants = {
            "1": {
                "character_id": 10, "team": 0,
                "hp": 180, "max_hp": 300, "mana": 40, "max_mana": 90,
                "energy": 100, "stamina": 100,
                "max_energy": 100, "max_stamina": 100,
                "cooldowns": {}, "fast_slots": [],
            },
            "2": {
                "character_id": 20, "team": 1,
                "hp": 45, "max_hp": 120, "mana": 0, "max_mana": 0,
                "energy": 80, "stamina": 70,
                "max_energy": 100, "max_stamina": 100,
                "cooldowns": {}, "fast_slots": [],
            },
        }
    if turn_order is None:
        turn_order = [1, 2]
    return {
        "turn_number": turn_number,
        "deadline_at": "2026-07-17T14:00:00",
        "next_actor": next_actor,
        "first_actor": 1,
        "turn_order": turn_order,
        "total_turns": 4,
        "last_turn": 2,
        "participants": participants,
        "active_effects": {},
    }


SAMPLE_SNAPSHOT = [
    {
        "participant_id": 1, "character_id": 10,
        "name": "Артур", "avatar": "https://s3.example/12.webp",
    },
    {
        "participant_id": 2, "character_id": 20,
        "name": "Гоблин-вожак", "avatar": "",  # empty avatar -> null in response
    },
]


def _make_preview_db(char_owner_map=None, location_name="Тёмный лес",
                     location_row_exists=True):
    """Async mock DB session for the preview handler's two raw-SQL queries.

    - ownership: SELECT user_id FROM characters WHERE id = :cid
      -> (user_id,) row from *char_owner_map* or None
    - location:  SELECT name FROM Locations WHERE id = :lid
      -> (*location_name*,) or None when *location_row_exists* is False
    """
    mock_db = AsyncMock()
    executed_params = []

    async def _execute(query, params=None):
        executed_params.append(params or {})
        result = MagicMock()
        if params and "cid" in params:
            uid = (char_owner_map or {}).get(params["cid"])
            result.fetchone.return_value = (uid,) if uid is not None else None
        elif params and "lid" in params:
            result.fetchone.return_value = (
                (location_name,) if location_row_exists else None
            )
        else:
            result.fetchone.return_value = None
        return result

    mock_db.execute = AsyncMock(side_effect=_execute)
    mock_db.executed_params = executed_params
    return mock_db


def _override_db(mock_db):
    async def _fake_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _fake_get_db


def _clear_db_override():
    app.dependency_overrides.pop(get_db, None)


# Decorator stack shared by the happy-path tests.
# Applied innermost-first, so injected mock args follow the same order:
# (mock_auth_get, mock_get_battle, mock_load_state,
#  mock_get_redis, mock_get_cached_snap, mock_load_snap)
def _preview_patches(fn):
    fn = patch("auth_http.requests.get")(fn)
    fn = patch("main.get_battle", new_callable=AsyncMock)(fn)
    fn = patch("main.load_state", new_callable=AsyncMock)(fn)
    fn = patch("main.get_redis_client", new_callable=AsyncMock)(fn)
    fn = patch("main.get_cached_snapshot", new_callable=AsyncMock)(fn)
    fn = patch("main.load_snapshot", new_callable=AsyncMock, return_value=None)(fn)
    return fn


# ═══════════════════════════════════════════════════════════════════════════
# Authentication / authorization
# ═══════════════════════════════════════════════════════════════════════════


class TestBattlePreviewAuth:
    """401/403 tests for GET /battles/{battle_id}/preview."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.get("/battles/1/preview")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth_get):
        mock_auth_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.get("/battles/1/preview", headers=AUTH_HEADERS)
        assert response.status_code == 401

    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_non_participant_returns_403(
        self, mock_auth_get, mock_get_battle, mock_load_state,
    ):
        """Authenticated user without a character in the battle -> 403."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 99, "username": "outsider", "role": "user", "permissions": []}
        )
        mock_get_battle.return_value = _make_battle()
        mock_load_state.return_value = _make_state()

        # chars 10 and 20 belong to users 1 and 2 — not to user 99
        mock_db = _make_preview_db({10: 1, 20: 2})
        _override_db(mock_db)
        try:
            with TestClient(app) as client:
                response = client.get("/battles/1/preview", headers=AUTH_HEADERS)
            assert response.status_code == 403
            assert response.json()["detail"] == "Вы не участвуете в этом бою"
        finally:
            _clear_db_override()


# ═══════════════════════════════════════════════════════════════════════════
# 404 variants
# ═══════════════════════════════════════════════════════════════════════════


class TestBattlePreviewNotFound:
    """404 tests for GET /battles/{battle_id}/preview."""

    @patch("main.get_battle", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_battle_row_absent_returns_404(self, mock_auth_get, mock_get_battle):
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)
        _override_db(_make_preview_db())
        try:
            with TestClient(app) as client:
                response = client.get("/battles/9999/preview", headers=AUTH_HEADERS)
            assert response.status_code == 404
            assert response.json()["detail"] == "Бой не найден"
        finally:
            _clear_db_override()

    @pytest.mark.parametrize("status", [BattleStatus.finished, BattleStatus.forfeit])
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_inactive_battle_returns_404(
        self, mock_auth_get, mock_get_battle, status,
    ):
        """Finished/forfeit battle -> 404 (expected finished-battle race signal)."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)
        mock_get_battle.return_value = _make_battle(status=status)
        _override_db(_make_preview_db())
        try:
            with TestClient(app) as client:
                response = client.get("/battles/1/preview", headers=AUTH_HEADERS)
            assert response.status_code == 404
            assert response.json()["detail"] == "Бой не найден или уже завершён"
        finally:
            _clear_db_override()

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_finished_battle_404_even_for_non_participant(
        self, mock_auth_get, mock_get_battle,
    ):
        """Status gate precedes the ownership check — outsider also gets 404."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 99, "username": "outsider", "role": "user", "permissions": []}
        )
        mock_get_battle.return_value = _make_battle(status=BattleStatus.finished)
        _override_db(_make_preview_db())
        try:
            with TestClient(app) as client:
                response = client.get("/battles/1/preview", headers=AUTH_HEADERS)
            assert response.status_code == 404
        finally:
            _clear_db_override()

    @patch("main.load_state", new_callable=AsyncMock, return_value=None)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_missing_redis_state_returns_404(
        self, mock_auth_get, mock_get_battle, mock_load_state,
    ):
        """Battle row still active but Redis state gone (race) -> 404."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)
        mock_get_battle.return_value = _make_battle()
        _override_db(_make_preview_db())
        try:
            with TestClient(app) as client:
                response = client.get("/battles/1/preview", headers=AUTH_HEADERS)
            assert response.status_code == 404
            assert response.json()["detail"] == "Бой не найден или уже завершён"
        finally:
            _clear_db_override()


# ═══════════════════════════════════════════════════════════════════════════
# 200 — response shape
# ═══════════════════════════════════════════════════════════════════════════


class TestBattlePreviewShape:
    """Happy-path DTO tests for GET /battles/{battle_id}/preview."""

    def _get_preview(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap,
        auth_user=None, battle=None, state=None, snapshot=SAMPLE_SNAPSHOT,
        db=None, battle_id=17,
    ):
        mock_auth_get.return_value = _mock_response(200, auth_user or AUTH_USER)
        mock_get_battle.return_value = battle or _make_battle(battle_id=battle_id)
        mock_load_state.return_value = state or _make_state()
        mock_get_redis.return_value = AsyncMock()
        mock_get_cached_snap.return_value = snapshot
        mock_db = db or _make_preview_db({10: 1, 20: 2})
        _override_db(mock_db)
        try:
            with TestClient(app) as client:
                response = client.get(
                    f"/battles/{battle_id}/preview", headers=AUTH_HEADERS,
                )
        finally:
            _clear_db_override()
        return response, mock_db

    @_preview_patches
    def test_full_dto_shape(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """Top-level fields, participants and turn_order per §3.1.2 contract."""
        response, _ = self._get_preview(
            mock_auth_get, mock_get_battle, mock_load_state,
            mock_get_redis, mock_get_cached_snap,
        )
        assert response.status_code == 200
        data = response.json()

        assert data["battle_id"] == 17
        assert data["battle_type"] == "pve"  # enum -> its string value
        assert data["turn_number"] == 4
        assert data["location_id"] == 44
        assert data["location_name"] == "Тёмный лес"

        # turn_order: ids as strings, names from snapshot, is_current = next_actor
        assert data["turn_order"] == [
            {"participant_id": "1", "name": "Артур", "is_current": True},
            {"participant_id": "2", "name": "Гоблин-вожак", "is_current": False},
        ]

        # participants: runtime hp/mana + max_*, snapshot name/avatar
        assert len(data["participants"]) == 2
        p1 = next(p for p in data["participants"] if p["participant_id"] == "1")
        assert p1["character_id"] == 10
        assert p1["name"] == "Артур"
        assert p1["avatar"] == "https://s3.example/12.webp"
        assert p1["team"] == "0"          # team emitted as string
        assert p1["is_ally"] is True      # requester (user 1) owns char 10
        assert p1["is_alive"] is True
        assert p1["hp"] == 180
        assert p1["max_hp"] == 300        # max_* from Redis runtime
        assert p1["mana"] == 40
        assert p1["max_mana"] == 90

        p2 = next(p for p in data["participants"] if p["participant_id"] == "2")
        assert p2["character_id"] == 20
        assert p2["name"] == "Гоблин-вожак"
        assert p2["avatar"] is None       # empty snapshot avatar -> null
        assert p2["team"] == "1"
        assert p2["is_ally"] is False
        assert p2["is_alive"] is True
        assert p2["hp"] == 45
        assert p2["max_hp"] == 120
        assert p2["mana"] == 0
        assert p2["max_mana"] == 0

        # Compact DTO — no heavy /state internals leak into the preview
        for heavy_key in ("snapshot", "runtime", "active_effects"):
            assert heavy_key not in data

    @_preview_patches
    def test_is_ally_from_enemy_perspective(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """Requester on team 1 (char 20) sees flags flipped vs team 0."""
        response, _ = self._get_preview(
            mock_auth_get, mock_get_battle, mock_load_state,
            mock_get_redis, mock_get_cached_snap,
            auth_user={"id": 2, "username": "enemy", "role": "user",
                       "permissions": []},
        )
        assert response.status_code == 200
        by_pid = {p["participant_id"]: p for p in response.json()["participants"]}
        assert by_pid["1"]["is_ally"] is False
        assert by_pid["2"]["is_ally"] is True

    @_preview_patches
    def test_dead_participant_is_alive_false(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """hp == 0 -> is_alive false (alive participants unaffected)."""
        state = _make_state()
        state["participants"]["2"]["hp"] = 0
        response, _ = self._get_preview(
            mock_auth_get, mock_get_battle, mock_load_state,
            mock_get_redis, mock_get_cached_snap,
            state=state,
        )
        assert response.status_code == 200
        by_pid = {p["participant_id"]: p for p in response.json()["participants"]}
        assert by_pid["2"]["is_alive"] is False
        assert by_pid["2"]["hp"] == 0
        assert by_pid["1"]["is_alive"] is True

    @_preview_patches
    def test_participant_missing_from_snapshot_gets_fallback_name(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """No snapshot entry -> name «Участник #pid», avatar null.

        Also covers an NPC participant with character_id=None: it must be
        skipped by the ownership check without breaking it.
        """
        state = _make_state(turn_order=[1, 2, 3])
        state["participants"]["3"] = {
            "character_id": None, "team": 1,
            "hp": 30, "max_hp": 60, "mana": 0, "max_mana": 0,
            "energy": 50, "stamina": 50,
            "max_energy": 50, "max_stamina": 50,
            "cooldowns": {}, "fast_slots": [],
        }
        response, _ = self._get_preview(
            mock_auth_get, mock_get_battle, mock_load_state,
            mock_get_redis, mock_get_cached_snap,
            state=state,
        )
        assert response.status_code == 200
        data = response.json()

        p3 = next(p for p in data["participants"] if p["participant_id"] == "3")
        assert p3["name"] == "Участник #3"
        assert p3["avatar"] is None
        assert p3["character_id"] is None
        assert p3["is_ally"] is False
        assert p3["is_alive"] is True

        t3 = next(t for t in data["turn_order"] if t["participant_id"] == "3")
        assert t3["name"] == "Участник #3"
        assert t3["is_current"] is False

    @_preview_patches
    def test_is_current_follows_next_actor(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """turn_order[].is_current is true exactly for the runtime next_actor."""
        response, _ = self._get_preview(
            mock_auth_get, mock_get_battle, mock_load_state,
            mock_get_redis, mock_get_cached_snap,
            state=_make_state(next_actor=2),
        )
        assert response.status_code == 200
        flags = {
            t["participant_id"]: t["is_current"]
            for t in response.json()["turn_order"]
        }
        assert flags == {"1": False, "2": True}

    @_preview_patches
    def test_location_name_null_when_locations_row_absent(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """Locations row missing -> location_name null, location_id kept."""
        response, _ = self._get_preview(
            mock_auth_get, mock_get_battle, mock_load_state,
            mock_get_redis, mock_get_cached_snap,
            db=_make_preview_db({10: 1, 20: 2}, location_row_exists=False),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["location_id"] == 44
        assert data["location_name"] is None

    @_preview_patches
    def test_no_location_id_skips_locations_query(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """battle.location_id null -> both location fields null, no SQL lookup."""
        response, mock_db = self._get_preview(
            mock_auth_get, mock_get_battle, mock_load_state,
            mock_get_redis, mock_get_cached_snap,
            battle=_make_battle(battle_id=17, location_id=None),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["location_id"] is None
        assert data["location_name"] is None
        assert not any("lid" in p for p in mock_db.executed_params)

    @_preview_patches
    def test_snapshot_mongo_fallback_when_cache_empty(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """Redis snapshot cache empty -> names come from the Mongo snapshot."""
        mock_load_snap.return_value = {"participants": SAMPLE_SNAPSHOT}
        response, _ = self._get_preview(
            mock_auth_get, mock_get_battle, mock_load_state,
            mock_get_redis, mock_get_cached_snap,
            snapshot=None,  # get_cached_snapshot -> None
        )
        assert response.status_code == 200
        p1 = next(
            p for p in response.json()["participants"]
            if p["participant_id"] == "1"
        )
        assert p1["name"] == "Артур"

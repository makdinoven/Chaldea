"""
Tests for battle history endpoint (FEAT-065, Task #5).

Covers:
1. GET /battles/history/{id} with no history -> empty list, zero stats
2. GET /battles/history/{id} with history data -> correct items returned
3. Pagination works (page, per_page)
4. Filter by battle_type
5. Filter by result (victory/defeat)
6. Stats calculation (wins, losses, winrate)
7. per_page max 50 enforced
"""

import sys
import os
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches (same approach as test_error_messages.py)
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

# Configure redis_state mock (required for main import)
redis_state_mock = sys.modules["redis_state"]
redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
redis_state_mock.init_battle_state = AsyncMock()
redis_state_mock.load_state = AsyncMock(return_value=None)
redis_state_mock.save_state = AsyncMock()
redis_state_mock.get_redis_client = AsyncMock(return_value=MagicMock())
redis_state_mock.cache_snapshot = AsyncMock()
redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)
redis_state_mock.state_key = MagicMock(return_value="battle:1:state")

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

# Configure buffs mock
buffs_mock = sys.modules["buffs"]
buffs_mock.decrement_durations = MagicMock()
buffs_mock.aggregate_modifiers = MagicMock(return_value={})
buffs_mock.apply_new_effects = MagicMock()
buffs_mock.build_percent_damage_buffs = MagicMock(return_value={})
buffs_mock.build_percent_resist_buffs = MagicMock(return_value={})

# Configure skills_client mock
skills_mock = sys.modules["skills_client"]
skills_mock.character_has_rank = AsyncMock(return_value=True)
skills_mock.get_rank = AsyncMock(return_value={})
skills_mock.get_item = AsyncMock(return_value={})
skills_mock.character_ranks = AsyncMock(return_value=[])

# Configure mongo_helpers
mongo_mock = sys.modules["mongo_helpers"]
mongo_mock.save_snapshot = AsyncMock()
mongo_mock.load_snapshot = AsyncMock(return_value=None)

# Configure rabbitmq_publisher
rmq_mock = sys.modules["rabbitmq_publisher"]
rmq_mock.publish_notification = AsyncMock()

# Configure inventory_client
inv_mock = sys.modules["inventory_client"]
inv_mock.get_fast_slots = AsyncMock(return_value=[])

# Configure character_client
char_mock = sys.modules["character_client"]
char_mock.get_character_profile = AsyncMock(return_value={
    "character_name": "Test",
    "character_photo": "",
})

# Now import main safely
from main import app  # noqa: E402
from database import get_db  # noqa: E402

# Clear startup handlers to avoid connection attempts
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _row(*values):
    """Create a mock row that supports index access."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    row.__len__ = lambda self: len(values)
    return row


def _result_with_row(row_data):
    """Create a mock result that returns a single row via fetchone."""
    result = MagicMock()
    result.fetchone.return_value = row_data
    result.scalar.return_value = row_data[0] if row_data else None
    return result


def _result_with_rows(rows):
    """Create a mock result that returns multiple rows."""
    result = MagicMock()
    result.fetchall.return_value = rows
    result.fetchone.return_value = rows[0] if rows else None
    return result


def _result_scalar(value):
    """Create a mock result that returns a scalar value."""
    result = MagicMock()
    result.scalar.return_value = value
    result.fetchone.return_value = _row(value)
    return result


def _make_mock_db(execute_side_effect):
    """Create an async mock DB session with a configurable execute side effect."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    return mock_db


SAMPLE_FINISHED_AT = datetime(2026, 3, 20, 14, 30, 0)

SAMPLE_HISTORY_ROW = _row(
    101,                         # battle_id
    ["Гоблин"],                  # opponent_names (JSON)
    [42],                        # opponent_character_ids (JSON)
    "pve",                       # battle_type
    "victory",                   # result
    SAMPLE_FINISHED_AT,          # finished_at
)


# ===========================================================================
# Test 1: Empty history
# ===========================================================================
class TestEmptyHistory:
    """GET /battles/history/{id} with no battle history."""

    def test_empty_history_returns_zero_stats(self):
        """Character with no battles returns empty list and zero stats."""
        call_count = [0]

        async def side_effect(query, params=None):
            call_count[0] += 1
            query_str = str(query)

            # Stats query — no battles
            if "COUNT(*)" in query_str and "SUM" in query_str:
                return _result_with_row(_row(0, 0, 0))

            # Count query (filtered)
            if "COUNT(*)" in query_str:
                return _result_scalar(0)

            # Paginated query — empty
            if "SELECT battle_id" in query_str:
                return _result_with_rows([])

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/999")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["history"] == []
        assert data["stats"]["total"] == 0
        assert data["stats"]["wins"] == 0
        assert data["stats"]["losses"] == 0
        assert data["stats"]["winrate"] == 0.0
        assert data["page"] == 1
        assert data["total_count"] == 0
        assert data["total_pages"] == 1


# ===========================================================================
# Test 2: History with data
# ===========================================================================
class TestHistoryWithData:
    """GET /battles/history/{id} with existing battle records."""

    def test_returns_correct_items(self):
        """History items are returned with correct fields."""
        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str and "SUM" in query_str:
                return _result_with_row(_row(3, 2, 1))

            if "COUNT(*)" in query_str:
                return _result_scalar(3)

            if "SELECT battle_id" in query_str:
                rows = [
                    _row(101, ["Гоблин"], [42], "pve", "victory", SAMPLE_FINISHED_AT),
                    _row(102, ["Маг"], [43], "pvp_training", "defeat", SAMPLE_FINISHED_AT),
                    _row(103, ["Волк", "Медведь"], [44, 45], "pve", "victory", SAMPLE_FINISHED_AT),
                ]
                return _result_with_rows(rows)

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert len(data["history"]) == 3

        first = data["history"][0]
        assert first["battle_id"] == 101
        assert first["opponent_names"] == ["Гоблин"]
        assert first["opponent_character_ids"] == [42]
        assert first["battle_type"] == "pve"
        assert first["result"] == "victory"

        third = data["history"][2]
        assert third["opponent_names"] == ["Волк", "Медведь"]
        assert third["opponent_character_ids"] == [44, 45]


# ===========================================================================
# Test 3: Pagination
# ===========================================================================
class TestPagination:
    """Verify page and per_page parameters work correctly."""

    def test_pagination_params_passed_to_query(self):
        """Page 2 with per_page=5 passes correct LIMIT/OFFSET."""
        captured_params = {}

        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str and "SUM" in query_str:
                return _result_with_row(_row(10, 6, 4))

            if "COUNT(*)" in query_str:
                return _result_scalar(10)

            if "SELECT battle_id" in query_str:
                if params:
                    captured_params.update(params)
                return _result_with_rows([])

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1?page=2&per_page=5")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["per_page"] == 5
        # Verify OFFSET = (page-1) * per_page = 5
        assert captured_params.get("offset") == 5
        assert captured_params.get("limit") == 5

    def test_total_pages_calculation(self):
        """total_pages is calculated correctly from total_count and per_page."""
        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str and "SUM" in query_str:
                return _result_with_row(_row(23, 12, 11))

            if "COUNT(*)" in query_str:
                return _result_scalar(23)

            if "SELECT battle_id" in query_str:
                return _result_with_rows([])

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1?per_page=10")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        # 23 items / 10 per page = 3 pages (ceil)
        assert data["total_pages"] == 3
        assert data["total_count"] == 23


# ===========================================================================
# Test 4: Filter by battle_type
# ===========================================================================
class TestFilterByBattleType:
    """Verify battle_type filter is applied to the query."""

    def test_battle_type_filter(self):
        """When battle_type=pve, only PvE battles are returned."""
        captured_params = {}

        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str and "SUM" in query_str:
                return _result_with_row(_row(10, 7, 3))

            if "COUNT(*)" in query_str:
                if params:
                    captured_params.update(params)
                return _result_scalar(5)

            if "SELECT battle_id" in query_str:
                return _result_with_rows([
                    _row(101, ["Гоблин"], [42], "pve", "victory", SAMPLE_FINISHED_AT),
                ])

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1?battle_type=pve")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        # Verify the filter parameter was passed
        assert captured_params.get("bt") == "pve"
        # History items should only be PvE
        for item in data["history"]:
            assert item["battle_type"] == "pve"


# ===========================================================================
# Test 5: Filter by result
# ===========================================================================
class TestFilterByResult:
    """Verify result filter is applied to the query."""

    def test_result_filter_victory(self):
        """When result=victory, only victories are returned."""
        captured_params = {}

        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str and "SUM" in query_str:
                return _result_with_row(_row(10, 7, 3))

            if "COUNT(*)" in query_str:
                if params:
                    captured_params.update(params)
                return _result_scalar(7)

            if "SELECT battle_id" in query_str:
                return _result_with_rows([
                    _row(101, ["Гоблин"], [42], "pve", "victory", SAMPLE_FINISHED_AT),
                ])

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1?result=victory")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert captured_params.get("res") == "victory"
        for item in data["history"]:
            assert item["result"] == "victory"

    def test_result_filter_defeat(self):
        """When result=defeat, only defeats are returned."""
        captured_params = {}

        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str and "SUM" in query_str:
                return _result_with_row(_row(10, 7, 3))

            if "COUNT(*)" in query_str:
                if params:
                    captured_params.update(params)
                return _result_scalar(3)

            if "SELECT battle_id" in query_str:
                return _result_with_rows([
                    _row(102, ["Маг"], [43], "pvp_training", "defeat", SAMPLE_FINISHED_AT),
                ])

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1?result=defeat")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert captured_params.get("res") == "defeat"
        for item in data["history"]:
            assert item["result"] == "defeat"


# ===========================================================================
# Test 6: Stats calculation
# ===========================================================================
class TestStatsCalculation:
    """Verify wins, losses, winrate are calculated correctly."""

    def test_stats_with_battles(self):
        """Stats reflect correct wins, losses, and winrate percentage."""
        async def side_effect(query, params=None):
            query_str = str(query)

            # total=10, wins=7, losses=3
            if "COUNT(*)" in query_str and "SUM" in query_str:
                return _result_with_row(_row(10, 7, 3))

            if "COUNT(*)" in query_str:
                return _result_scalar(10)

            if "SELECT battle_id" in query_str:
                return _result_with_rows([])

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        stats = response.json()["stats"]
        assert stats["total"] == 10
        assert stats["wins"] == 7
        assert stats["losses"] == 3
        # winrate = (7 / 10) * 100 = 70.0
        assert stats["winrate"] == 70.0

    def test_stats_zero_battles(self):
        """Stats with zero battles show 0.0 winrate (no division by zero)."""
        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str and "SUM" in query_str:
                return _result_with_row(_row(0, 0, 0))

            if "COUNT(*)" in query_str:
                return _result_scalar(0)

            if "SELECT battle_id" in query_str:
                return _result_with_rows([])

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        stats = response.json()["stats"]
        assert stats["total"] == 0
        assert stats["winrate"] == 0.0

    def test_stats_are_unfiltered(self):
        """Stats always reflect overall character stats, not filtered subset."""
        # Even when filter is applied, stats should still show all battles
        stats_params_seen = {}

        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str and "SUM" in query_str:
                # Stats query — should only have cid, not filter params
                if params:
                    stats_params_seen.update(params)
                return _result_with_row(_row(10, 7, 3))

            if "COUNT(*)" in query_str:
                return _result_scalar(5)

            if "SELECT battle_id" in query_str:
                return _result_with_rows([])

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1?battle_type=pve&result=victory")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        # Stats query should NOT have filter params (bt, res)
        assert "bt" not in stats_params_seen
        assert "res" not in stats_params_seen
        # Stats should show unfiltered totals
        stats = response.json()["stats"]
        assert stats["total"] == 10


# ===========================================================================
# Test 7: per_page max 50 enforced
# ===========================================================================
class TestPerPageLimit:
    """Verify per_page parameter is clamped at 50 via Query(le=50)."""

    def test_per_page_exceeds_50_rejected(self):
        """per_page > 50 should be rejected by FastAPI validation (422)."""
        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1?per_page=100")
        finally:
            app.dependency_overrides.clear()

        # FastAPI Query(le=50) returns 422 for values > 50
        assert response.status_code == 422

    def test_per_page_at_50_accepted(self):
        """per_page = 50 should be accepted."""
        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str and "SUM" in query_str:
                return _result_with_row(_row(0, 0, 0))

            if "COUNT(*)" in query_str:
                return _result_scalar(0)

            if "SELECT battle_id" in query_str:
                return _result_with_rows([])

            return _result_with_rows([])

        mock_db = _make_mock_db(side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1?per_page=50")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json()["per_page"] == 50

    def test_per_page_zero_rejected(self):
        """per_page = 0 should be rejected by FastAPI validation (422)."""
        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get("/battles/history/1?per_page=0")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422

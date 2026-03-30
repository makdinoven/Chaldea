"""
Tests for FEAT-106: Boss chest bugfix — phase overwrite, boss_loot key, item_name population.

Covers:
  Bug #1 — process_battle_completion skips clear_active_battle when dungeon_completed
  Bug #2 — get_session_state populates item_name via get_item_info; _handle_open_chest includes item_name
  Bug #3 — _handle_open_chest uses boss_loot key for boss rooms, loot_table for treasure rooms
"""

import random
from datetime import datetime
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import (
    Dungeon,
    DungeonRoom,
    DungeonRoomState,
    DungeonSession,
    DungeonSessionInventory,
    DungeonSessionMember,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scalar_result(value):
    """Mock db.execute result that returns scalar_one_or_none."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    mock_result.scalars.return_value.all.return_value = [value] if value else []
    mock_result.scalars.return_value.first.return_value = value
    mock_result.all.return_value = [value] if value else []
    return mock_result


def _scalars_result(values):
    """Mock db.execute result that returns scalars().all() and .all()."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = values
    mock_result.all.return_value = values
    return mock_result


def _mock_db() -> AsyncMock:
    """Create a mock async DB session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_session(
    session_id=100,
    dungeon_id=1,
    status="active",
    current_room_id=10,
    leader_character_id=200,
) -> MagicMock:
    s = MagicMock(spec=DungeonSession)
    s.id = session_id
    s.dungeon_id = dungeon_id
    s.status = status
    s.current_room_id = current_room_id
    s.leader_character_id = leader_character_id
    s.finished_at = None
    m1 = MagicMock(spec=DungeonSessionMember)
    m1.character_id = 200
    m1.user_id = 1
    m1.status = "alive"
    s.members = [m1]
    return s


def _make_dungeon(
    dungeon_id=1,
    loot_multiplier=1.0,
    mana_core_chance=0.0,
    stamina_multiplier=1.0,
    name="Test Dungeon",
    location_id=100,
) -> MagicMock:
    d = MagicMock(spec=Dungeon)
    d.id = dungeon_id
    d.loot_multiplier = loot_multiplier
    d.mana_core_chance = mana_core_chance
    d.stamina_multiplier = stamina_multiplier
    d.name = name
    d.location_id = location_id
    d.stability_type = "static"
    return d


def _make_room(
    room_id=10,
    room_type="boss",
    name="Boss Room",
    is_boss_room=True,
    is_mana_core_room=False,
    room_config=None,
) -> MagicMock:
    r = MagicMock(spec=DungeonRoom)
    r.id = room_id
    r.room_type = room_type
    r.name = name
    r.is_boss_room = is_boss_room
    r.is_mana_core_room = is_mana_core_room
    r.is_entrance = False
    r.description = "A room"
    r.image_url = None
    r.room_config = room_config or {}
    r.dungeon_id = 1
    r.position_x = None
    r.position_y = None
    r.sort_order = 0
    return r


def _make_room_state(
    session_id=100,
    room_id=10,
    is_cleared=True,
    loot_collected=False,
) -> MagicMock:
    rs = MagicMock(spec=DungeonRoomState)
    rs.session_id = session_id
    rs.room_id = room_id
    rs.is_cleared = is_cleared
    rs.loot_collected = loot_collected
    rs.event_choice_index = None
    return rs


# ---------------------------------------------------------------------------
# Bug #1 — Phase overwrite fix: process_battle_completion + clear_active_battle
# ---------------------------------------------------------------------------


class TestPhaseOverwriteFix:
    """
    Bug #1: process_battle_completion must NOT call clear_active_battle
    when results contain dungeon_completed=True (boss killed, dungeon completed).
    It MUST call clear_active_battle in other room-battle cases.
    """

    @pytest.mark.asyncio
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_skip_clear_active_battle_on_dungeon_completed(
        self, mock_ss, mock_http, mock_ws,
    ):
        """When boss is killed and dungeon_completed=True, clear_active_battle is NOT called."""
        from gameplay import process_battle_completion

        db = _mock_db()
        session_obj = _make_session(current_room_id=10)
        dungeon = _make_dungeon(mana_core_chance=0.0)
        boss_room = _make_room(room_id=10, room_type="boss", is_boss_room=True)

        # Redis state: room battle (no pending_target_room_id)
        redis_state = {
            "session_id": 100,
            "current_room_id": 10,
            "pending_target_room_id": None,
            "phase": "in_battle",
            "status": "active",
            "members": {"200": {"user_id": 1, "status": "alive"}},
        }
        mock_ss.get_session_state = AsyncMock(side_effect=[
            redis_state,  # First call at start of function
            redis_state,  # Second call for wipe check
        ])
        mock_ss.clear_active_battle = AsyncMock()
        mock_ss.update_session_state = AsyncMock()
        mock_ss.update_member_status = AsyncMock()

        # Battle state: party won (team1 alive, team2 dead)
        battle_state = {
            "runtime": {
                "participants": {
                    "p1": {"team": 1, "hp": 50, "character_id": 200},
                    "p2": {"team": 2, "hp": 0, "character_id": 999},
                },
            },
        }

        # DB execute side effects
        room_state_obj = _make_room_state(session_id=100, room_id=10, is_cleared=False)
        # No mana core room exists
        call_count = [0]

        async def execute_se(stmt, *a, **kw):
            call_count[0] += 1
            idx = call_count[0]
            if idx == 1:  # _get_session
                return _scalar_result(session_obj)
            elif idx == 2:  # _get_dungeon_for_session
                return _scalar_result(dungeon)
            elif idx == 3:  # room_state query
                return _scalar_result(room_state_obj)
            elif idx == 4:  # DungeonRoom query (boss check)
                return _scalar_result(boss_room)
            elif idx == 5:  # mana_core_room query (in _handle_boss_room_cleared)
                return _scalar_result(None)  # No mana core room
            else:
                return _scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_se)

        mock_ws.broadcast_to_session = AsyncMock()

        results = await process_battle_completion(db, 100, 999, battle_state)

        # Boss should be cleared and dungeon completed
        assert results.get("boss_cleared") is True
        assert results.get("dungeon_completed") is True

        # clear_active_battle must NOT have been called
        mock_ss.clear_active_battle.assert_not_awaited()

        # update_session_state SHOULD have been called (by _handle_boss_room_cleared)
        # to set phase="exploring" (boss chest must be opened first)
        mock_ss.update_session_state.assert_any_await(
            100, phase="exploring", status="active", active_battle_id=None,
        )

    @pytest.mark.asyncio
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_clear_active_battle_called_for_normal_room(
        self, mock_ss, mock_http, mock_ws,
    ):
        """For a normal (non-boss) room battle, clear_active_battle IS called."""
        from gameplay import process_battle_completion

        db = _mock_db()
        session_obj = _make_session(current_room_id=10)
        dungeon = _make_dungeon()
        normal_room = _make_room(
            room_id=10, room_type="battle", name="Battle Room",
            is_boss_room=False,
        )

        redis_state = {
            "session_id": 100,
            "current_room_id": 10,
            "pending_target_room_id": None,
            "phase": "in_battle",
            "status": "active",
            "members": {"200": {"user_id": 1, "status": "alive"}},
        }
        mock_ss.get_session_state = AsyncMock(side_effect=[redis_state, redis_state])
        mock_ss.clear_active_battle = AsyncMock()
        mock_ss.update_session_state = AsyncMock()
        mock_ss.update_member_status = AsyncMock()

        battle_state = {
            "runtime": {
                "participants": {
                    "p1": {"team": 1, "hp": 50, "character_id": 200},
                    "p2": {"team": 2, "hp": 0, "character_id": 999},
                },
            },
        }

        room_state_obj = _make_room_state(session_id=100, room_id=10, is_cleared=False)
        call_count = [0]

        async def execute_se(stmt, *a, **kw):
            call_count[0] += 1
            idx = call_count[0]
            if idx == 1:
                return _scalar_result(session_obj)
            elif idx == 2:
                return _scalar_result(dungeon)
            elif idx == 3:
                return _scalar_result(room_state_obj)
            elif idx == 4:
                return _scalar_result(normal_room)
            else:
                return _scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_se)
        mock_ws.broadcast_to_session = AsyncMock()

        results = await process_battle_completion(db, 100, 999, battle_state)

        # Not a boss room, so no dungeon_completed
        assert results.get("dungeon_completed") is None

        # clear_active_battle MUST have been called
        mock_ss.clear_active_battle.assert_awaited_once_with(100)


# ---------------------------------------------------------------------------
# Bug #3 — Boss loot key fix: _handle_open_chest
# ---------------------------------------------------------------------------


class TestBossLootKeyFix:
    """
    Bug #3: _handle_open_chest reads from 'boss_loot' key for boss rooms
    and 'loot_table' for treasure rooms.
    """

    @pytest.mark.asyncio
    @patch("gameplay.random")
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_boss_room_reads_boss_loot_key(
        self, mock_ss, mock_http, mock_ws, mock_random,
    ):
        """Boss room chest should read from boss_loot, not loot_table."""
        from gameplay import _handle_open_chest

        db = _mock_db()
        session_obj = _make_session()
        dungeon = _make_dungeon(loot_multiplier=1.0)
        boss_room = _make_room(
            room_id=10,
            room_type="boss",
            is_boss_room=True,
            room_config={
                "boss_loot": [
                    {"item_id": 42, "quantity": 1, "chance": 1.0},
                ],
                "loot_table": [
                    {"item_id": 99, "quantity": 5, "chance": 1.0},
                ],
            },
        )
        room_state = _make_room_state(is_cleared=True, loot_collected=False)
        redis_state = {"session_id": 100, "phase": "distributing_loot"}

        # random.random always returns 0 (below any chance) → loot always drops
        mock_random.random.return_value = 0.0

        # get_item_info returns name for item 42
        mock_http.get_item_info = AsyncMock(return_value={"name": "Boss Sword"})

        # DB execute for inventory queries
        db.execute = AsyncMock(return_value=_scalars_result([]))
        mock_ss.set_session_inventory = AsyncMock()
        mock_ss.update_session_state = AsyncMock()
        mock_ws.broadcast_to_session = AsyncMock()

        result = await _handle_open_chest(
            db, 100, session_obj, dungeon, boss_room, room_state, redis_state,
        )

        assert result.success is True
        # Should have gotten boss_loot item (42), NOT loot_table item (99)
        assert result.loot_gained is not None
        assert len(result.loot_gained) == 1
        assert result.loot_gained[0]["item_id"] == 42
        assert result.loot_gained[0]["item_name"] == "Boss Sword"

    @pytest.mark.asyncio
    @patch("gameplay.random")
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_treasure_room_reads_loot_table_key(
        self, mock_ss, mock_http, mock_ws, mock_random,
    ):
        """Treasure room chest should read from loot_table, not boss_loot."""
        from gameplay import _handle_open_chest

        db = _mock_db()
        session_obj = _make_session()
        dungeon = _make_dungeon(loot_multiplier=1.0)
        treasure_room = _make_room(
            room_id=20,
            room_type="treasure",
            name="Treasure Room",
            is_boss_room=False,
            room_config={
                "boss_loot": [
                    {"item_id": 42, "quantity": 1, "chance": 1.0},
                ],
                "loot_table": [
                    {"item_id": 77, "quantity": 3, "chance": 1.0},
                ],
            },
        )
        room_state = _make_room_state(
            room_id=20, is_cleared=True, loot_collected=False,
        )
        redis_state = {"session_id": 100, "phase": "exploring"}

        mock_random.random.return_value = 0.0
        mock_http.get_item_info = AsyncMock(return_value={"name": "Gold Coin"})
        db.execute = AsyncMock(return_value=_scalars_result([]))
        mock_ss.set_session_inventory = AsyncMock()
        mock_ws.broadcast_to_session = AsyncMock()

        result = await _handle_open_chest(
            db, 100, session_obj, dungeon, treasure_room, room_state, redis_state,
        )

        assert result.success is True
        assert result.loot_gained is not None
        assert len(result.loot_gained) == 1
        # Should be loot_table item (77), NOT boss_loot item (42)
        assert result.loot_gained[0]["item_id"] == 77
        assert result.loot_gained[0]["item_name"] == "Gold Coin"

    @pytest.mark.asyncio
    @patch("gameplay.random")
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_boss_room_empty_boss_loot_returns_no_loot(
        self, mock_ss, mock_http, mock_ws, mock_random,
    ):
        """Boss room with empty boss_loot should return no loot (no fallback to loot_table)."""
        from gameplay import _handle_open_chest

        db = _mock_db()
        session_obj = _make_session()
        dungeon = _make_dungeon(loot_multiplier=1.0)
        boss_room = _make_room(
            room_id=10,
            room_type="boss",
            is_boss_room=True,
            room_config={
                "boss_loot": [],
                "loot_table": [
                    {"item_id": 99, "quantity": 5, "chance": 1.0},
                ],
            },
        )
        room_state = _make_room_state(is_cleared=True, loot_collected=False)
        redis_state = {"session_id": 100, "phase": "distributing_loot"}

        mock_random.random.return_value = 0.0
        db.execute = AsyncMock(return_value=_scalars_result([]))
        mock_ss.set_session_inventory = AsyncMock()
        mock_ss.update_session_state = AsyncMock()
        mock_ws.broadcast_to_session = AsyncMock()

        result = await _handle_open_chest(
            db, 100, session_obj, dungeon, boss_room, room_state, redis_state,
        )

        assert result.success is True
        # No loot — boss_loot is empty, must NOT fall back to loot_table
        assert result.loot_gained is None
        assert "пустым" in result.message


# ---------------------------------------------------------------------------
# Bug #2 — item_name population
# ---------------------------------------------------------------------------


class TestItemNamePopulation:
    """
    Bug #2: get_session_state populates item_name in group inventory by calling
    get_item_info; _handle_open_chest includes item_name in loot_gained.
    """

    @pytest.mark.asyncio
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_get_session_state_populates_item_name(
        self, mock_ss, mock_http, mock_ws,
    ):
        """get_session_state fetches item_name via get_item_info for each unique item_id."""
        from gameplay import get_session_state

        db = _mock_db()
        session_obj = _make_session(current_room_id=10)
        dungeon = _make_dungeon()

        # Create inventory items (mocks)
        inv_item_1 = MagicMock(spec=DungeonSessionInventory)
        inv_item_1.item_id = 42
        inv_item_1.quantity = 2
        inv_item_1.source_description = "Boss chest"
        inv_item_2 = MagicMock(spec=DungeonSessionInventory)
        inv_item_2.item_id = 77
        inv_item_2.quantity = 1
        inv_item_2.source_description = "Treasure chest"

        # Redis state
        redis_state = {
            "session_id": 100,
            "phase": "distributing_loot",
            "active_battle_id": None,
            "members": {"200": {"user_id": 1, "status": "alive"}},
        }
        mock_ss.get_session_state = AsyncMock(return_value=redis_state)

        # Mock room and room state
        current_room = _make_room(
            room_id=10, room_type="boss", name="Boss Room",
        )
        room_state_obj = _make_room_state(is_cleared=True)

        # get_character_profile
        mock_http.get_character_profile = AsyncMock(
            return_value={"name": "Hero", "user_id": 1}
        )

        # get_item_info returns different names for different items
        async def item_info_side_effect(item_id):
            if item_id == 42:
                return {"name": "Boss Sword"}
            elif item_id == 77:
                return {"name": "Gold Coin"}
            return {"name": "Unknown"}

        mock_http.get_item_info = AsyncMock(side_effect=item_info_side_effect)

        # DB execute side effects
        # get_session_state flow:
        # 1: _get_session, 2: _get_dungeon_for_session, 3: current_room,
        # 4: room_state, 5-7: _get_room_exits (corridors_from, corridors_to, visits),
        # 8: inventory, 9: explored_rooms JOIN
        call_count = [0]

        async def execute_se(stmt, *a, **kw):
            call_count[0] += 1
            idx = call_count[0]
            if idx == 1:  # _get_session (selectinload)
                return _scalar_result(session_obj)
            elif idx == 2:  # _get_dungeon_for_session
                return _scalar_result(dungeon)
            elif idx == 3:  # current_room query
                return _scalar_result(current_room)
            elif idx == 4:  # room_state query
                return _scalar_result(room_state_obj)
            elif idx <= 7:  # _get_room_exits (corridors_from, corridors_to, visits)
                return _scalars_result([])
            elif idx == 8:  # inventory query
                return _scalars_result([inv_item_1, inv_item_2])
            elif idx == 9:  # explored_rooms JOIN query
                return _scalars_result([])
            else:
                return _scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_se)

        result = await get_session_state(db, 100, 200)

        # Verify item_name is populated
        assert len(result.group_inventory) == 2
        item_names = {item.item_id: item.item_name for item in result.group_inventory}
        assert item_names[42] == "Boss Sword"
        assert item_names[77] == "Gold Coin"

        # Verify get_item_info was called for each unique item_id
        assert mock_http.get_item_info.await_count == 2

    @pytest.mark.asyncio
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_get_session_state_item_info_failure_graceful(
        self, mock_ss, mock_http, mock_ws,
    ):
        """If get_item_info fails for an item, item_name is None but response succeeds."""
        from gameplay import get_session_state

        db = _mock_db()
        session_obj = _make_session(current_room_id=10)
        dungeon = _make_dungeon()

        inv_item = MagicMock(spec=DungeonSessionInventory)
        inv_item.item_id = 42
        inv_item.quantity = 1
        inv_item.source_description = "Boss chest"

        redis_state = {
            "session_id": 100,
            "phase": "distributing_loot",
            "active_battle_id": None,
            "members": {"200": {"user_id": 1, "status": "alive"}},
        }
        mock_ss.get_session_state = AsyncMock(return_value=redis_state)

        current_room = _make_room(room_id=10, room_type="boss", name="Boss Room")
        room_state_obj = _make_room_state(is_cleared=True)

        mock_http.get_character_profile = AsyncMock(
            return_value={"name": "Hero", "user_id": 1}
        )
        # get_item_info raises an exception
        mock_http.get_item_info = AsyncMock(side_effect=Exception("Service unavailable"))

        # get_session_state flow:
        # 1: _get_session, 2: _get_dungeon_for_session, 3: current_room,
        # 4: room_state, 5-7: _get_room_exits (corridors_from, corridors_to, visits),
        # 8: inventory, 9: explored_rooms JOIN
        call_count = [0]

        async def execute_se(stmt, *a, **kw):
            call_count[0] += 1
            idx = call_count[0]
            if idx == 1:
                return _scalar_result(session_obj)
            elif idx == 2:
                return _scalar_result(dungeon)
            elif idx == 3:
                return _scalar_result(current_room)
            elif idx == 4:
                return _scalar_result(room_state_obj)
            elif idx <= 7:  # _get_room_exits (3 calls)
                return _scalars_result([])
            elif idx == 8:  # inventory
                return _scalars_result([inv_item])
            elif idx == 9:  # explored_rooms JOIN
                return _scalars_result([])
            else:
                return _scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_se)

        # Should NOT raise — must handle the error gracefully
        result = await get_session_state(db, 100, 200)

        assert len(result.group_inventory) == 1
        # item_name should be None because get_item_info failed
        assert result.group_inventory[0].item_id == 42
        assert result.group_inventory[0].item_name is None

    @pytest.mark.asyncio
    @patch("gameplay.random")
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_handle_open_chest_includes_item_name_in_loot(
        self, mock_ss, mock_http, mock_ws, mock_random,
    ):
        """_handle_open_chest includes item_name in loot_gained dicts."""
        from gameplay import _handle_open_chest

        db = _mock_db()
        session_obj = _make_session()
        dungeon = _make_dungeon(loot_multiplier=1.0)
        treasure_room = _make_room(
            room_id=20,
            room_type="treasure",
            name="Treasure Room",
            is_boss_room=False,
            room_config={
                "loot_table": [
                    {"item_id": 77, "quantity": 2, "chance": 1.0},
                ],
            },
        )
        room_state = _make_room_state(
            room_id=20, is_cleared=True, loot_collected=False,
        )
        redis_state = {"session_id": 100, "phase": "exploring"}

        mock_random.random.return_value = 0.0
        mock_http.get_item_info = AsyncMock(return_value={"name": "Healing Potion"})
        db.execute = AsyncMock(return_value=_scalars_result([]))
        mock_ss.set_session_inventory = AsyncMock()
        mock_ws.broadcast_to_session = AsyncMock()

        result = await _handle_open_chest(
            db, 100, session_obj, dungeon, treasure_room, room_state, redis_state,
        )

        assert result.loot_gained is not None
        assert len(result.loot_gained) == 1
        # item_name must be present in the loot dict
        assert result.loot_gained[0]["item_name"] == "Healing Potion"
        assert result.loot_gained[0]["item_id"] == 77
        assert result.loot_gained[0]["quantity"] == 2


# ---------------------------------------------------------------------------
# Bug A fix (Task 6) — _handle_boss_room_cleared keeps exploring phase
# ---------------------------------------------------------------------------


class TestBossPhaseExploringFix:
    """
    Bug A: After boss kill, _handle_boss_room_cleared sets phase="exploring"
    and status="active" (not "distributing_loot"/"completed"), and clears
    active_battle_id=None so get_session_state won't re-process the battle.
    """

    @pytest.mark.asyncio
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_boss_cleared_sets_exploring_phase_and_clears_battle_id(
        self, mock_ss, mock_http, mock_ws,
    ):
        """After boss kill (no mana core), Redis state has phase='exploring',
        status='active', active_battle_id=None."""
        from gameplay import _handle_boss_room_cleared

        db = _mock_db()
        session_obj = _make_session(session_id=100, status="active")
        dungeon = _make_dungeon(mana_core_chance=0.0)
        boss_room = _make_room(room_id=10, room_type="boss", is_boss_room=True)

        # DB execute: mana_core_room query returns None
        db.execute = AsyncMock(return_value=_scalar_result(None))
        mock_ss.update_session_state = AsyncMock()
        mock_ws.broadcast_to_session = AsyncMock()

        result = await _handle_boss_room_cleared(db, 100, session_obj, dungeon, boss_room)

        assert result.get("dungeon_completed") is True

        # Verify update_session_state was called with exploring + active + battle cleared
        mock_ss.update_session_state.assert_awaited_once_with(
            100,
            phase="exploring",
            status="active",
            active_battle_id=None,
        )

    @pytest.mark.asyncio
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_mana_core_revealed_returns_early_without_update(
        self, mock_ss, mock_http, mock_ws,
    ):
        """When mana core is revealed, _handle_boss_room_cleared returns early
        without calling update_session_state (phase/status unchanged)."""
        from gameplay import _handle_boss_room_cleared

        db = _mock_db()
        session_obj = _make_session(session_id=100, status="active")
        dungeon = _make_dungeon(mana_core_chance=1.0)  # 100% chance
        boss_room = _make_room(room_id=10, room_type="boss", is_boss_room=True)

        mana_core_room = _make_room(
            room_id=99, room_type="mana_core", name="Mana Core Room",
            is_boss_room=False, is_mana_core_room=True,
        )

        call_count = [0]

        async def execute_se(stmt, *a, **kw):
            call_count[0] += 1
            if call_count[0] == 1:  # mana_core_room query
                return _scalar_result(mana_core_room)
            elif call_count[0] == 2:  # existing corridor check
                return _scalar_result(None)
            return _scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_se)
        mock_ss.update_session_state = AsyncMock()
        mock_ws.broadcast_to_session = AsyncMock()

        with patch("gameplay.random") as mock_random:
            mock_random.random.return_value = 0.0  # Below mana_core_chance=1.0
            result = await _handle_boss_room_cleared(db, 100, session_obj, dungeon, boss_room)

        # Mana core revealed — early return
        assert result.get("mana_core_revealed") is True
        assert result.get("dungeon_completed") is None

        # update_session_state should NOT have been called (early return path)
        mock_ss.update_session_state.assert_not_awaited()


# ---------------------------------------------------------------------------
# Bug B fix (Task 8) — Terminal-state guard in get_session_state
# ---------------------------------------------------------------------------


class TestTerminalStateGuard:
    """
    Bug B: get_session_state skips the battle-check block when the session
    is in a terminal state (completed/escaped/wiped), clearing stale
    active_battle_id instead of re-processing battles.
    """

    @pytest.mark.asyncio
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_completed_session_skips_battle_check_and_clears_battle_id(
        self, mock_ss, mock_http, mock_ws,
    ):
        """For a completed session with stale active_battle_id, the battle-check
        block is skipped and active_battle_id is cleared."""
        from gameplay import get_session_state

        db = _mock_db()
        session_obj = _make_session(session_id=100, status="completed", current_room_id=10)

        dungeon = _make_dungeon()
        current_room = _make_room(room_id=10, room_type="boss", name="Boss Room")
        room_state_obj = _make_room_state(is_cleared=True)

        # Redis state: completed session but with stale active_battle_id
        redis_state = {
            "session_id": 100,
            "phase": "distributing_loot",
            "status": "completed",
            "active_battle_id": 555,
            "members": {"200": {"user_id": 1, "status": "alive"}},
        }
        mock_ss.get_session_state = AsyncMock(return_value=redis_state)
        mock_ss.update_session_state = AsyncMock()

        mock_http.get_character_profile = AsyncMock(
            return_value={"name": "Hero", "user_id": 1},
        )
        mock_http.get_item_info = AsyncMock(return_value={"name": "Sword"})
        # get_battle_state should NOT be called
        mock_http.get_battle_state = AsyncMock()

        # get_session_state flow:
        # 1: _get_session, 2: _get_dungeon_for_session, 3: current_room,
        # 4: room_state, 5-7: _get_room_exits (corridors_from, corridors_to, visits),
        # 8: inventory, (battle check — terminal, no DB), 9: explored_rooms JOIN
        call_count = [0]

        async def execute_se(stmt, *a, **kw):
            call_count[0] += 1
            idx = call_count[0]
            if idx == 1:  # _get_session
                return _scalar_result(session_obj)
            elif idx == 2:  # _get_dungeon_for_session
                return _scalar_result(dungeon)
            elif idx == 3:  # current_room query
                return _scalar_result(current_room)
            elif idx == 4:  # room_state query
                return _scalar_result(room_state_obj)
            elif idx <= 7:  # _get_room_exits (3 calls)
                return _scalars_result([])
            elif idx == 8:  # inventory query
                return _scalars_result([])
            elif idx == 9:  # explored_rooms JOIN
                return _scalars_result([])
            else:
                return _scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_se)

        result = await get_session_state(db, 100, 200)

        # Battle state should NOT have been fetched
        mock_http.get_battle_state.assert_not_awaited()

        # active_battle_id should be cleared via update_session_state
        mock_ss.update_session_state.assert_awaited_once_with(100, active_battle_id=None)

    @pytest.mark.asyncio
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_active_session_with_battle_still_processes_normally(
        self, mock_ss, mock_http, mock_ws,
    ):
        """For an active session with active_battle_id, the battle-check
        logic still runs (fetches battle state)."""
        from gameplay import get_session_state

        db = _mock_db()
        session_obj = _make_session(session_id=100, status="active", current_room_id=10)

        dungeon = _make_dungeon()
        current_room = _make_room(room_id=10, room_type="battle", name="Battle Room",
                                  is_boss_room=False)
        room_state_obj = _make_room_state(is_cleared=False)

        # Redis state: active session with ongoing battle
        redis_state = {
            "session_id": 100,
            "phase": "in_battle",
            "status": "active",
            "active_battle_id": 777,
            "members": {"200": {"user_id": 1, "status": "alive"}},
        }
        mock_ss.get_session_state = AsyncMock(return_value=redis_state)
        mock_ss.update_session_state = AsyncMock()
        mock_ss.clear_active_battle = AsyncMock()

        mock_http.get_character_profile = AsyncMock(
            return_value={"name": "Hero", "user_id": 1},
        )
        # Battle is still ongoing — return valid battle state (both teams alive)
        mock_http.get_battle_state = AsyncMock(return_value={
            "runtime": {
                "participants": {
                    "p1": {"team": 1, "hp": 50, "character_id": 200},
                    "p2": {"team": 2, "hp": 30, "character_id": 999},
                },
            },
        })

        # get_session_state flow:
        # 1: _get_session, 2: _get_dungeon_for_session, 3: current_room,
        # 4: room_state, 5-7: _get_room_exits (corridors_from, corridors_to, visits),
        # 8: inventory, (battle check — active, ongoing battle), 9: explored_rooms JOIN
        call_count = [0]

        async def execute_se(stmt, *a, **kw):
            call_count[0] += 1
            idx = call_count[0]
            if idx == 1:  # _get_session
                return _scalar_result(session_obj)
            elif idx == 2:  # _get_dungeon_for_session
                return _scalar_result(dungeon)
            elif idx == 3:  # current_room query
                return _scalar_result(current_room)
            elif idx == 4:  # room_state query
                return _scalar_result(room_state_obj)
            elif idx <= 7:  # _get_room_exits (3 calls)
                return _scalars_result([])
            elif idx == 8:  # inventory query
                return _scalars_result([])
            elif idx == 9:  # explored_rooms JOIN
                return _scalars_result([])
            else:
                return _scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_se)

        result = await get_session_state(db, 100, 200)

        # Battle state SHOULD have been fetched (active session)
        mock_http.get_battle_state.assert_awaited_once_with(777)

        # Phase should reflect the battle
        assert result.phase == "in_battle"


# ---------------------------------------------------------------------------
# Bug C fix (Task 7) — _handle_open_chest transitions to distributing_loot
#                       for boss rooms
# ---------------------------------------------------------------------------


class TestChestTransitionFix:
    """
    Bug C: After opening a chest in a boss room, _handle_open_chest transitions
    phase to 'distributing_loot' and status to 'completed'. Treasure rooms
    do NOT get this transition.
    """

    @pytest.mark.asyncio
    @patch("gameplay.random")
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_boss_room_chest_transitions_to_distributing_loot(
        self, mock_ss, mock_http, mock_ws, mock_random,
    ):
        """Opening a chest in a boss room sets phase='distributing_loot'
        and status='completed', and sets session_obj.finished_at."""
        from gameplay import _handle_open_chest

        db = _mock_db()
        session_obj = _make_session(status="active")
        dungeon = _make_dungeon(loot_multiplier=1.0)
        boss_room = _make_room(
            room_id=10,
            room_type="boss",
            is_boss_room=True,
            room_config={
                "boss_loot": [
                    {"item_id": 42, "quantity": 1, "chance": 1.0},
                ],
            },
        )
        room_state = _make_room_state(is_cleared=True, loot_collected=False)
        redis_state = {"session_id": 100, "phase": "exploring"}

        mock_random.random.return_value = 0.0
        mock_http.get_item_info = AsyncMock(return_value={"name": "Boss Sword"})
        db.execute = AsyncMock(return_value=_scalars_result([]))
        mock_ss.set_session_inventory = AsyncMock()
        mock_ss.update_session_state = AsyncMock()
        mock_ws.broadcast_to_session = AsyncMock()

        result = await _handle_open_chest(
            db, 100, session_obj, dungeon, boss_room, room_state, redis_state,
        )

        assert result.success is True

        # Phase should transition to distributing_loot with status=completed
        mock_ss.update_session_state.assert_awaited_once_with(
            100,
            phase="distributing_loot",
            status="completed",
        )

        # session_obj should be marked completed with finished_at set
        assert session_obj.status == "completed"
        assert session_obj.finished_at is not None

    @pytest.mark.asyncio
    @patch("gameplay.random")
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_treasure_room_chest_does_not_transition_phase(
        self, mock_ss, mock_http, mock_ws, mock_random,
    ):
        """Opening a chest in a treasure room does NOT change phase to
        'distributing_loot' — phase stays as-is."""
        from gameplay import _handle_open_chest

        db = _mock_db()
        session_obj = _make_session(status="active")
        dungeon = _make_dungeon(loot_multiplier=1.0)
        treasure_room = _make_room(
            room_id=20,
            room_type="treasure",
            name="Treasure Room",
            is_boss_room=False,
            room_config={
                "loot_table": [
                    {"item_id": 77, "quantity": 3, "chance": 1.0},
                ],
            },
        )
        room_state = _make_room_state(
            room_id=20, is_cleared=True, loot_collected=False,
        )
        redis_state = {"session_id": 100, "phase": "exploring"}

        mock_random.random.return_value = 0.0
        mock_http.get_item_info = AsyncMock(return_value={"name": "Gold Coin"})
        db.execute = AsyncMock(return_value=_scalars_result([]))
        mock_ss.set_session_inventory = AsyncMock()
        mock_ss.update_session_state = AsyncMock()
        mock_ws.broadcast_to_session = AsyncMock()

        result = await _handle_open_chest(
            db, 100, session_obj, dungeon, treasure_room, room_state, redis_state,
        )

        assert result.success is True

        # update_session_state should NOT have been called (no phase transition for treasure)
        mock_ss.update_session_state.assert_not_awaited()

        # session_obj should still be active
        assert session_obj.status == "active"
        assert session_obj.finished_at is None

    @pytest.mark.asyncio
    @patch("gameplay.random")
    @patch("gameplay.ws_manager")
    @patch("gameplay.http_clients")
    @patch("gameplay.session_state")
    async def test_boss_room_chest_sets_finished_at(
        self, mock_ss, mock_http, mock_ws, mock_random,
    ):
        """Opening a boss room chest sets session_obj.finished_at to a datetime."""
        from gameplay import _handle_open_chest

        db = _mock_db()
        session_obj = _make_session(status="active")
        # Verify finished_at is initially None
        assert session_obj.finished_at is None

        dungeon = _make_dungeon(loot_multiplier=1.0)
        boss_room = _make_room(
            room_id=10,
            room_type="boss",
            is_boss_room=True,
            room_config={"boss_loot": []},
        )
        room_state = _make_room_state(is_cleared=True, loot_collected=False)
        redis_state = {"session_id": 100, "phase": "exploring"}

        mock_random.random.return_value = 0.0
        db.execute = AsyncMock(return_value=_scalars_result([]))
        mock_ss.set_session_inventory = AsyncMock()
        mock_ss.update_session_state = AsyncMock()
        mock_ws.broadcast_to_session = AsyncMock()

        await _handle_open_chest(
            db, 100, session_obj, dungeon, boss_room, room_state, redis_state,
        )

        # finished_at must be set (even with empty loot)
        assert session_obj.finished_at is not None
        assert isinstance(session_obj.finished_at, datetime)

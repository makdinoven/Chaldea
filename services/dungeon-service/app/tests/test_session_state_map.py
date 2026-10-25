"""
Tests for session state API changes: explored_rooms, position fields,
handle fields, fog of war, and backward compatibility (FEAT-108 Task 5).
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from models import (
    Dungeon,
    DungeonCorridor,
    DungeonRoom,
    DungeonRoomState,
    DungeonRoomVisit,
    DungeonSession,
    DungeonSessionMember,
)
from schemas import (
    ExploredRoomInfo,
    RoomExitResponse,
    RoomViewResponse,
    SessionStateResponse,
)


# ---------------------------------------------------------------------------
# Helpers to build mock ORM objects
# ---------------------------------------------------------------------------

def _make_dungeon(id=1, location_id=100, stability_type="static", name="Test Dungeon"):
    d = MagicMock(spec=Dungeon)
    d.id = id
    d.location_id = location_id
    d.is_active = True
    d.cooldown_hours = 24
    d.stability_type = stability_type
    d.name = name
    d.description = "A test dungeon"
    d.danger_level = "safe"
    d.recommended_level = 1
    d.recommended_party_size = 1
    d.mob_multiplier = 1.0
    d.loot_multiplier = 1.0
    d.stamina_multiplier = 1.0
    d.difficulty_modifier = 1.0
    d.disable_rest_rooms = False
    d.disable_merchants = False
    d.mana_core_chance = 0.0
    d.mana_core_item_id = None
    d.image_url = None
    return d


def _make_member(character_id=10, user_id=100, status="alive", session_id=1):
    m = MagicMock(spec=DungeonSessionMember)
    m.id = 1
    m.session_id = session_id
    m.character_id = character_id
    m.user_id = user_id
    m.status = status
    m.joined_at = datetime(2026, 1, 1, 0, 0, 0)
    return m


def _make_session(
    id=1,
    dungeon_id=1,
    leader_character_id=10,
    status="active",
    current_room_id=100,
    members=None,
):
    s = MagicMock(spec=DungeonSession)
    s.id = id
    s.dungeon_id = dungeon_id
    s.leader_character_id = leader_character_id
    s.status = status
    s.current_room_id = current_room_id
    s.members = members or [_make_member(character_id=leader_character_id)]
    s.started_at = datetime(2026, 1, 1)
    s.finished_at = None
    s.cooldown_until = None
    return s


def _make_room(
    id=100,
    dungeon_id=1,
    room_type="fork",
    name="Entrance Hall",
    position_x=0.0,
    position_y=0.0,
    is_entrance=True,
    is_boss_room=False,
):
    r = MagicMock(spec=DungeonRoom)
    r.id = id
    r.dungeon_id = dungeon_id
    r.room_type = room_type
    r.name = name
    r.description = "A room"
    r.image_url = None
    r.is_entrance = is_entrance
    r.is_boss_room = is_boss_room
    r.is_mana_core_room = False
    r.sort_order = 0
    r.room_config = None
    r.position_x = position_x
    r.position_y = position_y
    return r


def _make_corridor(
    id=1,
    dungeon_id=1,
    from_room_id=100,
    to_room_id=200,
    stamina_cost=5,
    is_bidirectional=True,
    source_handle="right-1",
    target_handle="left-1",
):
    c = MagicMock(spec=DungeonCorridor)
    c.id = id
    c.dungeon_id = dungeon_id
    c.from_room_id = from_room_id
    c.to_room_id = to_room_id
    c.stamina_cost = stamina_cost
    c.is_bidirectional = is_bidirectional
    c.random_battle_chance = 0.0
    c.random_battle_mob_ids = None
    c.trap_chance = 0.0
    c.trap_config = None
    c.description = None
    c.source_handle = source_handle
    c.target_handle = target_handle
    return c


def _make_room_state(session_id=1, room_id=100, is_cleared=False):
    rs = MagicMock(spec=DungeonRoomState)
    rs.session_id = session_id
    rs.room_id = room_id
    rs.is_cleared = is_cleared
    rs.loot_collected = False
    rs.event_choice_index = None
    rs.extra_data = None
    return rs


def _mock_db_result(return_value):
    """Create a mock for db.execute() -> result.scalar_one_or_none()."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = return_value
    mock_result.scalars.return_value.all.return_value = (
        [return_value] if return_value else []
    )
    mock_result.scalars.return_value.first.return_value = return_value
    return mock_result


def _mock_db_rows_result(rows):
    """Create a mock for db.execute() -> result.all() returning list of tuples."""
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    mock_result.scalars.return_value.all.return_value = rows
    return mock_result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Async mock for SQLAlchemy AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def patch_externals():
    """Patch http_clients, session_state, ws_manager for all tests."""
    with (
        patch("gameplay.http_clients") as mock_http,
        patch("gameplay.session_state") as mock_ss,
        patch("gameplay.ws_manager") as mock_ws,
    ):
        mock_ss.get_session_state = AsyncMock(return_value={
            "session_id": 1,
            "dungeon_id": 1,
            "current_room_id": 100,
            "status": "active",
            "leader_character_id": 10,
            "members": {"10": {"user_id": 100, "status": "alive"}},
            "active_battle_id": None,
            "dead_count": 0,
            "phase": "exploring",
        })
        mock_ss.set_phase = AsyncMock(return_value={})
        mock_ss.clear_active_battle = AsyncMock()
        mock_ss.update_session_state = AsyncMock()
        mock_ws.broadcast_to_session = AsyncMock()
        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 10, "name": "Hero", "current_location_id": 100, "user_id": 100,
        })
        mock_http.get_item_info = AsyncMock(return_value={"name": "Sword"})
        mock_http.get_battle_state = AsyncMock(return_value=None)

        yield mock_http, mock_ss, mock_ws


# =====================================================================
# Schema default tests (backward compatibility)
# =====================================================================


class TestSchemaDefaults:
    """New fields have Optional/default values — existing callers won't break."""

    def test_room_exit_response_defaults(self):
        """RoomExitResponse new fields default to None."""
        exit_resp = RoomExitResponse(
            corridor_id=1,
            to_room_id=2,
            to_room_name="Room",
            stamina_cost=5,
            explored=True,
        )
        assert exit_resp.position_x is None
        assert exit_resp.position_y is None
        assert exit_resp.source_handle is None
        assert exit_resp.target_handle is None

    def test_room_view_response_defaults(self):
        """RoomViewResponse new fields default to None."""
        room = RoomViewResponse(
            id=1,
            room_type="fork",
            name="Room",
            description="Desc",
            is_entrance=True,
            is_boss_room=False,
        )
        assert room.position_x is None
        assert room.position_y is None
        assert room.exits == []

    def test_session_state_response_defaults(self):
        """SessionStateResponse.explored_rooms defaults to empty list."""
        state = SessionStateResponse(
            session_id=1,
            dungeon_id=1,
            dungeon_name="Dungeon",
            status="active",
            phase="exploring",
        )
        assert state.explored_rooms == []
        assert state.current_room is None
        assert state.members == []
        assert state.group_inventory == []

    def test_explored_room_info_position_defaults(self):
        """ExploredRoomInfo position fields default to None."""
        info = ExploredRoomInfo(
            id=1,
            name="Room",
            room_type="battle",
            is_cleared=False,
        )
        assert info.position_x is None
        assert info.position_y is None


# =====================================================================
# RoomViewResponse position fields
# =====================================================================


class TestRoomViewPositionFields:
    """Current room includes position_x and position_y."""

    def test_room_view_with_positions(self):
        """RoomViewResponse includes position_x/y when provided."""
        room = RoomViewResponse(
            id=100,
            room_type="fork",
            name="Entrance",
            description="Entry point",
            is_entrance=True,
            is_boss_room=False,
            position_x=120.5,
            position_y=340.0,
        )
        assert room.position_x == 120.5
        assert room.position_y == 340.0

    def test_room_view_with_none_positions(self):
        """RoomViewResponse works with None positions (room has no editor coordinates)."""
        room = RoomViewResponse(
            id=100,
            room_type="battle",
            name="Battle",
            description="A battle room",
            is_entrance=False,
            is_boss_room=False,
            position_x=None,
            position_y=None,
        )
        assert room.position_x is None
        assert room.position_y is None


# =====================================================================
# RoomExitResponse handle and position fields
# =====================================================================


class TestRoomExitHandleFields:
    """Exits include source_handle, target_handle, position_x, position_y."""

    def test_exit_with_handles_and_positions(self):
        """RoomExitResponse includes all new fields when provided."""
        exit_resp = RoomExitResponse(
            corridor_id=1,
            to_room_id=200,
            to_room_name="Battle Room",
            stamina_cost=5,
            explored=True,
            position_x=240.0,
            position_y=120.0,
            source_handle="right-1",
            target_handle="left-2",
        )
        assert exit_resp.position_x == 240.0
        assert exit_resp.position_y == 120.0
        assert exit_resp.source_handle == "right-1"
        assert exit_resp.target_handle == "left-2"

    def test_exit_without_handles(self):
        """RoomExitResponse works with None handles (corridor has no editor handles)."""
        exit_resp = RoomExitResponse(
            corridor_id=1,
            to_room_id=200,
            to_room_name="???",
            stamina_cost=5,
            explored=False,
            position_x=240.0,
            position_y=120.0,
        )
        assert exit_resp.source_handle is None
        assert exit_resp.target_handle is None
        assert exit_resp.position_x == 240.0



# FEAT-175: the call-order-dependent mock tests of _get_room_exits and the
# explored-rooms payload were replaced by real-code tests on SQLite in
# test_feat175_rooms.py::test_map_payload_has_positions_grid_and_reliability.

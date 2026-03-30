"""
Tests for dungeon-service session management + party formation.

Tests gameplay functions: create_session, invite_member, leave_session,
enter_dungeon, get_session_state.

All inter-service HTTP calls, Redis state, and WebSocket are mocked.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from fastapi import HTTPException

import gameplay
from models import (
    Dungeon,
    DungeonRoom,
    DungeonSession,
    DungeonSessionMember,
    DungeonSessionInventory,
    DungeonRoomState,
)


# ---------------------------------------------------------------------------
# Helpers to build mock ORM objects
# ---------------------------------------------------------------------------

def _make_dungeon(
    id=1,
    location_id=100,
    is_active=True,
    cooldown_hours=24,
    stability_type="static",
    name="Test Dungeon",
    description="A test dungeon",
):
    d = MagicMock(spec=Dungeon)
    d.id = id
    d.location_id = location_id
    d.is_active = is_active
    d.cooldown_hours = cooldown_hours
    d.stability_type = stability_type
    d.name = name
    d.description = description
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


def _make_member(
    id=1,
    session_id=1,
    character_id=10,
    user_id=100,
    status="alive",
    joined_at=None,
):
    m = MagicMock(spec=DungeonSessionMember)
    m.id = id
    m.session_id = session_id
    m.character_id = character_id
    m.user_id = user_id
    m.status = status
    m.joined_at = joined_at or datetime(2026, 1, 1, 0, 0, 0)
    return m


def _make_session(
    id=1,
    dungeon_id=1,
    leader_character_id=10,
    status="forming",
    current_room_id=None,
    members=None,
):
    s = MagicMock(spec=DungeonSession)
    s.id = id
    s.dungeon_id = dungeon_id
    s.leader_character_id = leader_character_id
    s.status = status
    s.current_room_id = current_room_id
    s.members = members or []
    s.started_at = None
    s.finished_at = None
    s.cooldown_until = None
    return s


def _make_entrance_room(id=50, dungeon_id=1):
    r = MagicMock(spec=DungeonRoom)
    r.id = id
    r.dungeon_id = dungeon_id
    r.room_type = "fork"
    r.name = "Entrance Hall"
    r.description = "The entrance to the dungeon."
    r.image_url = None
    r.is_entrance = True
    r.is_boss_room = False
    r.is_mana_core_room = False
    r.sort_order = 0
    return r


def _mock_db_execute_chain(return_value):
    """Create a mock for db.execute() -> result.scalar_one_or_none()."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = return_value
    mock_result.scalars.return_value.all.return_value = (
        [return_value] if return_value else []
    )
    mock_result.scalars.return_value.first.return_value = return_value
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


# Patch all external dependencies at module level
@pytest.fixture(autouse=True)
def patch_externals():
    """Patch http_clients, session_state, ws_manager for all tests."""
    with patch("gameplay.http_clients") as mock_http, \
         patch("gameplay.session_state") as mock_ss, \
         patch("gameplay.ws_manager") as mock_ws:
        # Set default return values for session_state
        mock_ss.check_dungeon_cooldown = AsyncMock(return_value=(False, 0))
        mock_ss.get_character_active_session = AsyncMock(return_value=None)
        mock_ss.set_character_active_session = AsyncMock()
        mock_ss.clear_character_active_session = AsyncMock()
        mock_ss.init_session_state = AsyncMock()
        mock_ss.set_current_room = AsyncMock(return_value={})
        mock_ss.set_phase = AsyncMock(return_value={})
        mock_ss.get_session_state = AsyncMock(return_value=None)
        mock_ss.set_session_inventory = AsyncMock()
        mock_ss.get_session_inventory = AsyncMock(return_value=None)

        # Set default return values for ws_manager
        mock_ws.broadcast_to_session = AsyncMock()
        mock_ws.cleanup_session = AsyncMock()

        # Set default return values for http_clients
        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 10,
            "name": "Hero",
            "current_location_id": 100,
            "user_id": 100,
            "level": 5,
        })

        yield mock_http, mock_ss, mock_ws


# ===================================================================
# CREATE SESSION
# ===================================================================

class TestCreateSession:
    """Tests for gameplay.create_session."""

    @pytest.mark.asyncio
    async def test_create_session_success(self, mock_db, patch_externals):
        mock_http, mock_ss, _ = patch_externals
        dungeon = _make_dungeon(id=1, location_id=100, is_active=True)

        # db.execute returns dungeon on first call, None on second (latest session)
        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # select Dungeon
                return _mock_db_execute_chain(dungeon)
            elif call_count == 2:
                # select latest session with cooldown
                return _mock_db_execute_chain(None)
            return _mock_db_execute_chain(None)

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        # Ensure character profile returns matching location + user
        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 10,
            "name": "Hero",
            "current_location_id": 100,
            "user_id": 100,
        })

        # Patch _build_session_response to avoid SQLAlchemy ORM backref issues
        # when setting .members on a real DungeonSession object with mock members
        from schemas import SessionResponse, SessionMemberResponse

        expected_response = SessionResponse(
            session_id=1,
            dungeon_id=1,
            status="forming",
            leader_character_id=10,
            members=[
                SessionMemberResponse(
                    character_id=10, name="Hero", status="alive",
                    is_leader=True, user_id=100,
                ),
            ],
        )
        with patch("gameplay._build_session_response", AsyncMock(return_value=expected_response)):
            result = await gameplay.create_session(
                db=mock_db, character_id=10, dungeon_id=1, user_id=100,
            )

        assert result.status == "forming"
        assert result.dungeon_id == 1
        assert len(result.members) == 1
        assert result.members[0].character_id == 10
        assert result.members[0].is_leader is True

        # Verify Redis active_session was set
        mock_ss.set_character_active_session.assert_awaited_once()
        # Verify DB operations happened
        mock_db.add.assert_called()
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_session_dungeon_inactive(self, mock_db, patch_externals):
        dungeon = _make_dungeon(id=1, is_active=False)
        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(dungeon)
        )

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.create_session(
                db=mock_db, character_id=10, dungeon_id=1, user_id=100,
            )
        assert exc_info.value.status_code == 400
        assert "неактивно" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_create_session_dungeon_not_found(self, mock_db, patch_externals):
        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(None)
        )

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.create_session(
                db=mock_db, character_id=10, dungeon_id=999, user_id=100,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_session_on_cooldown(self, mock_db, patch_externals):
        _, mock_ss, _ = patch_externals
        dungeon = _make_dungeon(id=1, is_active=True)
        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(dungeon)
        )

        # Dungeon is on cooldown
        mock_ss.check_dungeon_cooldown = AsyncMock(return_value=(True, 7200))

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.create_session(
                db=mock_db, character_id=10, dungeon_id=1, user_id=100,
            )
        assert exc_info.value.status_code == 403
        assert "кулдаун" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_create_session_wrong_location(self, mock_db, patch_externals):
        mock_http, mock_ss, _ = patch_externals
        dungeon = _make_dungeon(id=1, location_id=100, is_active=True)

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_execute_chain(dungeon)
            elif call_count == 2:
                return _mock_db_execute_chain(None)
            return _mock_db_execute_chain(None)

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        # Character is at location 999, not 100
        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 10,
            "name": "Hero",
            "current_location_id": 999,
            "user_id": 100,
        })

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.create_session(
                db=mock_db, character_id=10, dungeon_id=1, user_id=100,
            )
        assert exc_info.value.status_code == 400
        assert "локации" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_create_session_already_in_session(self, mock_db, patch_externals):
        mock_http, mock_ss, _ = patch_externals
        dungeon = _make_dungeon(id=1, location_id=100, is_active=True)

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_execute_chain(dungeon)
            elif call_count == 2:
                return _mock_db_execute_chain(None)
            return _mock_db_execute_chain(None)

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 10,
            "name": "Hero",
            "current_location_id": 100,
            "user_id": 100,
        })

        # Character already in another session
        mock_ss.get_character_active_session = AsyncMock(return_value=42)

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.create_session(
                db=mock_db, character_id=10, dungeon_id=1, user_id=100,
            )
        assert exc_info.value.status_code == 409
        assert "сессии" in exc_info.value.detail.lower()


# ===================================================================
# INVITE MEMBER
# ===================================================================

class TestInviteMember:
    """Tests for gameplay.invite_member."""

    @pytest.mark.asyncio
    async def test_invite_member_success(self, mock_db, patch_externals):
        mock_http, mock_ss, mock_ws = patch_externals

        leader = _make_member(
            id=1, character_id=10, user_id=100, session_id=1,
        )
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="forming", members=[leader],
        )
        dungeon = _make_dungeon(id=1, location_id=100)

        # _get_session (with selectinload) and _get_dungeon_for_session
        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # _get_session
                return _mock_db_execute_chain(session)
            elif call_count == 2:
                # _get_dungeon_for_session
                return _mock_db_execute_chain(dungeon)
            return _mock_db_execute_chain(None)

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        # Inviter profile (leader)
        def profile_side_effect(char_id):
            if char_id == 10:
                return {"id": 10, "name": "Hero", "current_location_id": 100, "user_id": 100}
            elif char_id == 20:
                return {"id": 20, "name": "Ally", "current_location_id": 100, "user_id": 200}
            return {}

        mock_http.get_character_profile = AsyncMock(side_effect=profile_side_effect)

        # Invitee not in any session
        mock_ss.get_character_active_session = AsyncMock(return_value=None)

        # After commit + refresh, session now has 2 members
        invitee_member = _make_member(
            id=2, character_id=20, user_id=200, session_id=1,
        )

        async def refresh_side_effect(obj, attrs=None):
            if hasattr(obj, 'members'):
                obj.members = [leader, invitee_member]
        mock_db.refresh = AsyncMock(side_effect=refresh_side_effect)

        result = await gameplay.invite_member(
            db=mock_db,
            session_id=1,
            inviter_character_id=10,
            invitee_character_id=20,
            user_id=100,
        )

        assert len(result.members) == 2
        mock_ss.set_character_active_session.assert_awaited_once()
        mock_ws.broadcast_to_session.assert_awaited()

    @pytest.mark.asyncio
    async def test_invite_not_leader(self, mock_db, patch_externals):
        mock_http, _, _ = patch_externals

        leader = _make_member(character_id=10, user_id=100, session_id=1)
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="forming", members=[leader],
        )
        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(session)
        )

        # Non-leader trying to invite
        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 20, "name": "Ally", "current_location_id": 100, "user_id": 200,
        })

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.invite_member(
                db=mock_db,
                session_id=1,
                inviter_character_id=20,  # Not the leader
                invitee_character_id=30,
                user_id=200,
            )
        assert exc_info.value.status_code == 403
        assert "лидер" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invite_party_full(self, mock_db, patch_externals):
        mock_http, _, _ = patch_externals

        members = [
            _make_member(character_id=10 + i, user_id=100 + i, session_id=1)
            for i in range(4)
        ]
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="forming", members=members,
        )

        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(session)
        )

        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 10, "name": "Hero", "current_location_id": 100, "user_id": 100,
        })

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.invite_member(
                db=mock_db,
                session_id=1,
                inviter_character_id=10,
                invitee_character_id=50,
                user_id=100,
            )
        assert exc_info.value.status_code == 400
        assert "4" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invite_wrong_location(self, mock_db, patch_externals):
        mock_http, _, _ = patch_externals

        leader = _make_member(character_id=10, user_id=100, session_id=1)
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="forming", members=[leader],
        )
        dungeon = _make_dungeon(id=1, location_id=100)

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_execute_chain(session)
            elif call_count == 2:
                return _mock_db_execute_chain(dungeon)
            return _mock_db_execute_chain(None)

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        def profile_side_effect(char_id):
            if char_id == 10:
                return {"id": 10, "name": "Hero", "current_location_id": 100, "user_id": 100}
            elif char_id == 20:
                # Invitee at wrong location
                return {"id": 20, "name": "Ally", "current_location_id": 999, "user_id": 200}
            return {}

        mock_http.get_character_profile = AsyncMock(side_effect=profile_side_effect)

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.invite_member(
                db=mock_db,
                session_id=1,
                inviter_character_id=10,
                invitee_character_id=20,
                user_id=100,
            )
        assert exc_info.value.status_code == 400
        assert "локации" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invite_already_in_session(self, mock_db, patch_externals):
        mock_http, mock_ss, _ = patch_externals

        leader = _make_member(character_id=10, user_id=100, session_id=1)
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="forming", members=[leader],
        )
        dungeon = _make_dungeon(id=1, location_id=100)

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_execute_chain(session)
            elif call_count == 2:
                return _mock_db_execute_chain(dungeon)
            return _mock_db_execute_chain(None)

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        def profile_side_effect(char_id):
            if char_id == 10:
                return {"id": 10, "name": "Hero", "current_location_id": 100, "user_id": 100}
            elif char_id == 20:
                return {"id": 20, "name": "Ally", "current_location_id": 100, "user_id": 200}
            return {}

        mock_http.get_character_profile = AsyncMock(side_effect=profile_side_effect)

        # Invitee already in another session
        mock_ss.get_character_active_session = AsyncMock(return_value=42)

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.invite_member(
                db=mock_db,
                session_id=1,
                inviter_character_id=10,
                invitee_character_id=20,
                user_id=100,
            )
        assert exc_info.value.status_code == 409
        assert "сессии" in exc_info.value.detail.lower()


# ===================================================================
# LEAVE SESSION
# ===================================================================

class TestLeaveSession:
    """Tests for gameplay.leave_session."""

    @pytest.mark.asyncio
    async def test_leave_session_member(self, mock_db, patch_externals):
        mock_http, mock_ss, mock_ws = patch_externals

        leader = _make_member(
            id=1, character_id=10, user_id=100, session_id=1,
            joined_at=datetime(2026, 1, 1, 0, 0),
        )
        member = _make_member(
            id=2, character_id=20, user_id=200, session_id=1,
            joined_at=datetime(2026, 1, 1, 0, 5),
        )
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="forming", members=[leader, member],
        )

        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(session)
        )

        # After removing member, refresh returns session with leader only
        async def refresh_side_effect(obj, attrs=None):
            if hasattr(obj, 'members'):
                obj.members = [leader]
        mock_db.refresh = AsyncMock(side_effect=refresh_side_effect)

        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 10, "name": "Hero", "current_location_id": 100, "user_id": 100,
        })

        result = await gameplay.leave_session(
            db=mock_db, session_id=1, character_id=20,
        )

        assert result is not None
        assert result.leader_character_id == 10
        mock_ss.clear_character_active_session.assert_awaited_once_with(20)
        mock_ws.broadcast_to_session.assert_awaited()

    @pytest.mark.asyncio
    async def test_leave_session_leader_transfers(self, mock_db, patch_externals):
        mock_http, mock_ss, mock_ws = patch_externals

        leader = _make_member(
            id=1, character_id=10, user_id=100, session_id=1,
            joined_at=datetime(2026, 1, 1, 0, 0),
        )
        member2 = _make_member(
            id=2, character_id=20, user_id=200, session_id=1,
            joined_at=datetime(2026, 1, 1, 0, 5),
        )
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="forming", members=[leader, member2],
        )

        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(session)
        )

        # After leader leaves, refresh returns session with member2
        async def refresh_side_effect(obj, attrs=None):
            if hasattr(obj, 'members'):
                obj.members = [member2]
        mock_db.refresh = AsyncMock(side_effect=refresh_side_effect)

        # Profile for building response
        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 20, "name": "Ally", "current_location_id": 100, "user_id": 200,
        })

        result = await gameplay.leave_session(
            db=mock_db, session_id=1, character_id=10,
        )

        assert result is not None
        # Leadership should have been transferred to member2
        assert session.leader_character_id == 20
        mock_ss.clear_character_active_session.assert_awaited_once_with(10)
        # Should have broadcast leader_changed + member_left
        assert mock_ws.broadcast_to_session.await_count >= 2

    @pytest.mark.asyncio
    async def test_leave_session_last_member(self, mock_db, patch_externals):
        _, mock_ss, mock_ws = patch_externals

        leader = _make_member(
            id=1, character_id=10, user_id=100, session_id=1,
            joined_at=datetime(2026, 1, 1, 0, 0),
        )
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="forming", members=[leader],
        )

        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(session)
        )

        result = await gameplay.leave_session(
            db=mock_db, session_id=1, character_id=10,
        )

        # Session should be deleted — function returns None
        assert result is None
        mock_db.delete.assert_awaited()
        mock_ss.clear_character_active_session.assert_awaited_once_with(10)
        mock_ws.broadcast_to_session.assert_awaited()
        mock_ws.cleanup_session.assert_awaited_once_with(1)


# ===================================================================
# ENTER DUNGEON
# ===================================================================

class TestEnterDungeon:
    """Tests for gameplay.enter_dungeon."""

    @pytest.mark.asyncio
    async def test_enter_dungeon_success(self, mock_db, patch_externals):
        mock_http, mock_ss, mock_ws = patch_externals

        leader = _make_member(
            id=1, character_id=10, user_id=100, session_id=1,
        )
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="forming", members=[leader],
        )
        entrance_room = _make_entrance_room(id=50, dungeon_id=1)

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # _get_session
                return _mock_db_execute_chain(session)
            elif call_count == 2:
                # find entrance room
                return _mock_db_execute_chain(entrance_room)
            return _mock_db_execute_chain(None)

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 10, "name": "Hero", "current_location_id": 100, "user_id": 100,
        })

        # Patch get_session_state to avoid complex nested DB interactions
        from schemas import SessionStateResponse, SessionMemberResponse

        expected_state = SessionStateResponse(
            session_id=1,
            dungeon_id=1,
            dungeon_name="Test Dungeon",
            status="active",
            phase="exploring",
            current_room=None,
            members=[
                SessionMemberResponse(
                    character_id=10, name="Hero", status="alive",
                    is_leader=True, user_id=100,
                ),
            ],
            group_inventory=[],
            active_battle_id=None,
        )

        with patch("gameplay.get_session_state", AsyncMock(return_value=expected_state)):
            result = await gameplay.enter_dungeon(
                db=mock_db, session_id=1, character_id=10,
            )

        assert result.status == "active"
        assert result.phase == "exploring"
        # Verify session status was changed
        assert session.status == "active"
        assert session.current_room_id == entrance_room.id
        mock_ss.init_session_state.assert_awaited_once()
        mock_ss.set_current_room.assert_awaited()
        mock_ss.set_phase.assert_awaited()
        mock_ws.broadcast_to_session.assert_awaited()

    @pytest.mark.asyncio
    async def test_enter_dungeon_not_leader(self, mock_db, patch_externals):
        leader = _make_member(character_id=10, user_id=100, session_id=1)
        member = _make_member(character_id=20, user_id=200, session_id=1)
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="forming", members=[leader, member],
        )

        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(session)
        )

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.enter_dungeon(
                db=mock_db, session_id=1, character_id=20,
            )
        assert exc_info.value.status_code == 403
        assert "лидер" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_enter_dungeon_wrong_status(self, mock_db, patch_externals):
        leader = _make_member(character_id=10, user_id=100, session_id=1)
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="active",  # Already active
            members=[leader],
        )

        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(session)
        )

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.enter_dungeon(
                db=mock_db, session_id=1, character_id=10,
            )
        assert exc_info.value.status_code == 400
        assert "формирования" in exc_info.value.detail.lower()


# ===================================================================
# GET SESSION STATE
# ===================================================================

class TestGetSessionState:
    """Tests for gameplay.get_session_state."""

    @pytest.mark.asyncio
    async def test_get_session_state(self, mock_db, patch_externals):
        mock_http, mock_ss, _ = patch_externals

        leader = _make_member(character_id=10, user_id=100, session_id=1)
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="active", current_room_id=50,
            members=[leader],
        )
        dungeon = _make_dungeon(id=1, location_id=100, name="Dark Cave")
        room = _make_entrance_room(id=50, dungeon_id=1)
        room_state = MagicMock(spec=DungeonRoomState)
        room_state.is_cleared = False

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # _get_session
                return _mock_db_execute_chain(session)
            elif call_count == 2:
                # _get_dungeon_for_session
                return _mock_db_execute_chain(dungeon)
            elif call_count == 3:
                # select DungeonRoom (current room)
                return _mock_db_execute_chain(room)
            elif call_count == 4:
                # select DungeonRoomState
                return _mock_db_execute_chain(room_state)
            else:
                # Remaining queries (corridors, visits, inventory)
                result = MagicMock()
                result.scalar_one_or_none.return_value = None
                result.scalars.return_value.all.return_value = []
                return result

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        mock_ss.get_session_state = AsyncMock(return_value={
            "session_id": 1,
            "dungeon_id": 1,
            "current_room_id": 50,
            "status": "active",
            "phase": "exploring",
            "leader_character_id": 10,
            "members": {"10": {"user_id": 100, "status": "alive"}},
            "active_battle_id": None,
            "dead_count": 0,
        })

        mock_http.get_character_profile = AsyncMock(return_value={
            "id": 10, "name": "Hero", "current_location_id": 100, "user_id": 100,
        })

        result = await gameplay.get_session_state(
            db=mock_db, session_id=1, character_id=10,
        )

        assert result.session_id == 1
        assert result.dungeon_id == 1
        assert result.dungeon_name == "Dark Cave"
        assert result.status == "active"
        assert result.phase == "exploring"
        assert len(result.members) == 1
        assert result.members[0].character_id == 10
        assert result.active_battle_id is None

    @pytest.mark.asyncio
    async def test_get_session_state_not_member(self, mock_db, patch_externals):
        leader = _make_member(character_id=10, user_id=100, session_id=1)
        session = _make_session(
            id=1, dungeon_id=1, leader_character_id=10,
            status="active", members=[leader],
        )

        mock_db.execute = AsyncMock(
            return_value=_mock_db_execute_chain(session)
        )

        with pytest.raises(HTTPException) as exc_info:
            await gameplay.get_session_state(
                db=mock_db, session_id=1, character_id=999,  # Not a member
            )
        assert exc_info.value.status_code == 403
        assert "участником" in exc_info.value.detail.lower()

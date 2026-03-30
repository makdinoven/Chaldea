"""
Tests for dungeon-service gameplay functions:
movement, corridors, battles, room interactions, flee, loot distribution, finalization.
"""

import math
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import (
    DungeonCorridor,
    DungeonRoom,
    DungeonRoomState,
    DungeonSession,
    DungeonSessionInventory,
    DungeonSessionMember,
    DungeonRoomVisit,
)


# Helper to build a mock db.execute result that returns a scalar_one_or_none
def _scalar_result(value):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    mock_result.scalars.return_value.all.return_value = [value] if value else []
    return mock_result


def _scalars_result(values):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = values
    return mock_result


# =====================================================================
# Movement tests
# =====================================================================


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_move_success(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_corridor, sample_redis_state,
    sample_room, sample_room_state,
):
    """Successful move: stamina consumed, room changed, fog of war updated."""
    from gameplay import move_to_room

    # Setup: session query returns our sample session
    target_room = MagicMock()
    target_room.id = 11
    target_room.room_type = "fork"
    target_room.name = "Вторая комната"
    target_room.description = "Ещё одна комната"
    target_room.image_url = None
    target_room.is_entrance = False
    target_room.is_boss_room = False
    target_room.is_mana_core_room = False
    target_room.room_config = None

    # DB execute side effects: session, corridor, dungeon, visits, room_state, room
    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        idx = call_count[0]
        if idx == 1:  # session query
            return _scalar_result(sample_session)
        elif idx == 2:  # corridor query
            return _scalar_result(sample_corridor)
        elif idx == 3:  # dungeon query
            return _scalar_result(sample_dungeon)
        elif idx <= 5:  # get_character_attributes calls (check stamina)
            return _scalar_result(None)
        else:
            # visits, room_state, room - return None for "not found" (new visit)
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
            return result

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)

    # Redis state
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.set_current_room = AsyncMock(return_value=sample_redis_state)

    # HTTP clients: attrs check + stamina consume
    mock_http.get_character_attributes = AsyncMock(return_value={"current_stamina": 100})
    mock_http.consume_stamina = AsyncMock(return_value=True)
    mock_http.get_character_profile = AsyncMock(return_value={"name": "Тест", "user_id": 1})

    # Broadcast
    mock_ws.broadcast_to_session = AsyncMock()

    result = await move_to_room(mock_db, 100, 200, 50)

    # Stamina consumed for both alive members
    assert mock_http.consume_stamina.call_count == 2
    assert result.stamina_consumed == 5  # base cost, multiplier=1, dead_count=0
    assert result.corridor_event is not None
    assert result.corridor_event.type == "safe"


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_move_stamina_calculation(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_corridor,
):
    """Stamina cost = base_cost * multiplier * (1 + 0.25 * dead_count)."""
    from gameplay import move_to_room

    # Set dungeon stamina_multiplier = 2.0 and dead_count = 2
    sample_dungeon.stamina_multiplier = 2.0

    redis_state = {
        "session_id": 100,
        "dungeon_id": 1,
        "current_room_id": 10,
        "status": "active",
        "leader_character_id": 200,
        "members": {
            "200": {"user_id": 1, "status": "alive"},
            "201": {"user_id": 2, "status": "dead"},
            "202": {"user_id": 3, "status": "dead"},
            "203": {"user_id": 4, "status": "alive"},
        },
        "active_battle_id": None,
        "dead_count": 2,
        "phase": "exploring",
    }

    # Update session members accordingly
    m1 = MagicMock(); m1.character_id = 200; m1.user_id = 1; m1.status = "alive"
    m2 = MagicMock(); m2.character_id = 201; m2.user_id = 2; m2.status = "dead"
    m3 = MagicMock(); m3.character_id = 202; m3.user_id = 3; m3.status = "dead"
    m4 = MagicMock(); m4.character_id = 203; m4.user_id = 4; m4.status = "alive"
    sample_session.members = [m1, m2, m3, m4]

    sample_corridor.stamina_cost = 10

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        idx = call_count[0]
        if idx == 1:
            return _scalar_result(sample_session)
        elif idx == 2:
            return _scalar_result(sample_corridor)
        elif idx == 3:
            return _scalar_result(sample_dungeon)
        else:
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            r.scalars.return_value.all.return_value = []
            return r

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=redis_state)
    mock_ss.set_current_room = AsyncMock(return_value=redis_state)
    mock_http.get_character_attributes = AsyncMock(return_value={"current_stamina": 200})
    mock_http.consume_stamina = AsyncMock(return_value=True)
    mock_http.get_character_profile = AsyncMock(return_value={"name": "T"})
    mock_ws.broadcast_to_session = AsyncMock()

    result = await move_to_room(mock_db, 100, 200, 50)

    # Expected: ceil(10 * 2.0 * (1 + 0.25*2)) = ceil(10 * 2.0 * 1.5) = ceil(30) = 30
    expected = math.ceil(10 * 2.0 * (1 + 0.25 * 2))
    assert result.stamina_consumed == expected


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_move_insufficient_stamina(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_corridor, sample_redis_state,
):
    """Move rejected when alive member has insufficient stamina."""
    from gameplay import move_to_room
    from fastapi import HTTPException

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(sample_corridor)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        r.scalars.return_value.all.return_value = []
        return r

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)

    # First member has enough, second does not
    call_attr_count = [0]
    async def attrs_side_effect(cid):
        call_attr_count[0] += 1
        if cid == 200:
            return {"current_stamina": 100}
        return {"current_stamina": 2}  # Not enough

    mock_http.get_character_attributes = AsyncMock(side_effect=attrs_side_effect)
    mock_http.get_character_profile = AsyncMock(return_value={"name": "Слабый"})

    with pytest.raises(HTTPException) as exc_info:
        await move_to_room(mock_db, 100, 200, 50)

    assert exc_info.value.status_code == 400
    assert "стамины" in exc_info.value.detail.lower() or "стамин" in exc_info.value.detail.lower()

    # No stamina consumed since we check all before consuming
    mock_http.consume_stamina.assert_not_called()


@pytest.mark.asyncio
@patch("gameplay.session_state")
async def test_move_not_leader(mock_ss, mock_db, sample_session, sample_redis_state):
    """Move rejected when character is not the leader (403)."""
    from gameplay import move_to_room
    from fastapi import HTTPException

    mock_db.execute = AsyncMock(return_value=_scalar_result(sample_session))
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)

    # character_id 201 is not the leader (leader is 200)
    with pytest.raises(HTTPException) as exc_info:
        await move_to_room(mock_db, 100, 201, 50)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_move_invalid_corridor(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    """Move rejected when corridor doesn't connect from current room."""
    from gameplay import move_to_room
    from fastapi import HTTPException

    # Corridor from room 20 to 21 (not from current room 10)
    bad_corridor = MagicMock()
    bad_corridor.id = 55
    bad_corridor.from_room_id = 20
    bad_corridor.to_room_id = 21
    bad_corridor.is_bidirectional = False

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(bad_corridor)
        return _scalar_result(None)

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)

    with pytest.raises(HTTPException) as exc_info:
        await move_to_room(mock_db, 100, 200, 55)

    assert exc_info.value.status_code == 400
    assert "недоступен" in exc_info.value.detail.lower() or "коридор" in exc_info.value.detail.lower()


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_move_bidirectional(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    """Bidirectional corridor can be traversed in reverse direction."""
    from gameplay import move_to_room

    # Corridor from 11 to 10, bidirectional — current room is 10
    # So reverse direction means going from 10 (to_room_id) to 11 (from_room_id)
    reverse_corridor = MagicMock()
    reverse_corridor.id = 60
    reverse_corridor.from_room_id = 11
    reverse_corridor.to_room_id = 10  # current room
    reverse_corridor.is_bidirectional = True
    reverse_corridor.stamina_cost = 3
    reverse_corridor.random_battle_chance = 0.0
    reverse_corridor.trap_chance = 0.0
    reverse_corridor.trap_config = None
    reverse_corridor.random_battle_mob_ids = None

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(reverse_corridor)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        r.scalars.return_value.all.return_value = []
        return r

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.set_current_room = AsyncMock(return_value=sample_redis_state)
    mock_http.get_character_attributes = AsyncMock(return_value={"current_stamina": 100})
    mock_http.consume_stamina = AsyncMock(return_value=True)
    mock_http.get_character_profile = AsyncMock(return_value={"name": "Тест"})
    mock_ws.broadcast_to_session = AsyncMock()

    result = await move_to_room(mock_db, 100, 200, 60)

    assert result.stamina_consumed == 3
    assert result.corridor_event.type == "safe"


# =====================================================================
# Corridor events tests
# =====================================================================


@pytest.mark.asyncio
@patch("gameplay.random")
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_corridor_trap_pass(
    mock_ss, mock_http, mock_ws, mock_random,
    mock_db, sample_session, sample_dungeon, sample_corridor, sample_redis_state,
):
    """Trap in corridor: stat check passes -> no damage."""
    from gameplay import move_to_room

    # Corridor has trap (no battle chance, only trap)
    sample_corridor.random_battle_chance = 0.0
    sample_corridor.trap_chance = 0.5
    sample_corridor.trap_config = {
        "stat_check": "agility",
        "difficulty": 10,
        "fail_damage": 20,
    }

    # Random: only trap roll (battle check skipped because chance=0.0)
    mock_random.random.return_value = 0.1  # < 0.5 => trap triggers

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(sample_corridor)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        r.scalars.return_value.all.return_value = []
        return r

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.set_current_room = AsyncMock(return_value=sample_redis_state)

    # Character attributes with high agility (passes the check)
    mock_http.get_character_attributes = AsyncMock(return_value={
        "current_stamina": 100,
        "cumulative_stats": {"agility": 20},
    })
    mock_http.consume_stamina = AsyncMock(return_value=True)
    mock_http.get_character_profile = AsyncMock(return_value={"name": "Ловкач"})
    mock_ws.broadcast_to_session = AsyncMock()

    result = await move_to_room(mock_db, 100, 200, 50)

    assert result.corridor_event.type == "trap"
    assert result.corridor_event.details["passed"] is True


@pytest.mark.asyncio
@patch("gameplay.random")
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_corridor_trap_fail(
    mock_ss, mock_http, mock_ws, mock_random,
    mock_db, sample_session, sample_dungeon, sample_corridor, sample_redis_state,
):
    """Trap in corridor: stat check fails -> damage noted."""
    from gameplay import move_to_room

    sample_corridor.random_battle_chance = 0.0
    sample_corridor.trap_chance = 0.5
    sample_corridor.trap_config = {
        "stat_check": "agility",
        "difficulty": 50,
        "fail_damage": 25,
    }

    # Only trap roll (battle check skipped because chance=0.0)
    mock_random.random.return_value = 0.1  # < 0.5 => trap triggers

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(sample_corridor)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        r.scalars.return_value.all.return_value = []
        return r

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.set_current_room = AsyncMock(return_value=sample_redis_state)

    # Character attributes with low agility (fails the check)
    mock_http.get_character_attributes = AsyncMock(return_value={
        "current_stamina": 100,
        "cumulative_stats": {"agility": 5},
    })
    mock_http.consume_stamina = AsyncMock(return_value=True)
    mock_http.get_character_profile = AsyncMock(return_value={"name": "Неуклюжий"})
    mock_ws.broadcast_to_session = AsyncMock()

    result = await move_to_room(mock_db, 100, 200, 50)

    assert result.corridor_event.type == "trap"
    assert result.corridor_event.details["passed"] is False
    assert result.corridor_event.details["fail_damage"] == 25


@pytest.mark.asyncio
@patch("gameplay.random")
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_corridor_random_battle(
    mock_ss, mock_http, mock_ws, mock_random,
    mock_db, sample_session, sample_dungeon, sample_corridor, sample_redis_state,
):
    """Corridor random battle is initiated when roll < chance."""
    from gameplay import move_to_room

    sample_corridor.random_battle_chance = 0.5
    sample_corridor.random_battle_mob_ids = [1, 2]

    # Random: battle roll < chance (battle triggers)
    mock_random.random.return_value = 0.1

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(sample_corridor)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        r.scalars.return_value.all.return_value = []
        return r

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.update_session_state = AsyncMock(return_value=sample_redis_state)

    mock_http.get_character_attributes = AsyncMock(return_value={"current_stamina": 100})
    mock_http.consume_stamina = AsyncMock(return_value=True)
    mock_http.spawn_dungeon_mobs = AsyncMock(return_value=[300, 301])
    mock_http.create_battle = AsyncMock(return_value={"battle_id": 777})
    mock_ws.broadcast_to_session = AsyncMock()

    result = await move_to_room(mock_db, 100, 200, 50)

    assert result.corridor_event.type == "battle"
    assert result.corridor_event.details["battle_id"] == 777
    assert result.new_room is None  # Didn't reach target room


# =====================================================================
# Room Interaction tests
# =====================================================================


@pytest.mark.asyncio
@patch("gameplay.random")
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_open_chest_success(
    mock_ss, mock_http, mock_ws, mock_random,
    mock_db, sample_session, sample_dungeon, sample_room_state, sample_redis_state,
):
    """Open chest: loot added to group inventory."""
    from gameplay import interact_with_room

    treasure_room = MagicMock()
    treasure_room.id = 10
    treasure_room.room_type = "treasure"
    treasure_room.name = "Сокровищница"
    treasure_room.room_config = {
        "loot_table": [
            {"item_id": 101, "quantity": 2, "chance": 1.0},
            {"item_id": 102, "quantity": 1, "chance": 1.0},
        ]
    }

    sample_room_state.loot_collected = False

    # random.random() always returns 0.1 (below all chances)
    mock_random.random.return_value = 0.1

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(treasure_room)  # current room
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)  # dungeon
        elif call_count[0] == 4:
            return _scalar_result(sample_room_state)  # room state
        else:
            return _scalars_result([])  # inventory query
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.set_session_inventory = AsyncMock()
    mock_ws.broadcast_to_session = AsyncMock()

    result = await interact_with_room(mock_db, 100, 200, "open_chest")

    assert result.success is True
    assert result.action == "open_chest"
    assert result.loot_gained is not None
    assert len(result.loot_gained) == 2
    assert sample_room_state.loot_collected is True


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_open_chest_already_collected(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_room_state, sample_redis_state,
):
    """Open chest when already collected -> error."""
    from gameplay import interact_with_room
    from fastapi import HTTPException

    treasure_room = MagicMock()
    treasure_room.id = 10
    treasure_room.room_type = "treasure"
    treasure_room.name = "Сокровищница"
    treasure_room.room_config = {"loot_table": []}

    sample_room_state.loot_collected = True  # Already collected

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(treasure_room)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 4:
            return _scalar_result(sample_room_state)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)

    with pytest.raises(HTTPException) as exc_info:
        await interact_with_room(mock_db, 100, 200, "open_chest")

    assert exc_info.value.status_code == 400
    assert "уже" in exc_info.value.detail.lower()


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_event_choice(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_room_state, sample_redis_state,
):
    """Event choice: choice recorded, outcome applied."""
    from gameplay import interact_with_room

    event_room = MagicMock()
    event_room.id = 10
    event_room.room_type = "event"
    event_room.name = "Загадочный алтарь"
    event_room.room_config = {
        "choices": [
            {
                "text": "Прикоснуться к алтарю",
                "outcome_type": "reward",
                "outcome_text": "Алтарь одарил вас!",
                "outcome_data": {"items": [{"item_id": 50, "quantity": 1}]},
            },
            {
                "text": "Уйти",
                "outcome_type": "nothing",
                "outcome_text": "Вы прошли мимо.",
                "outcome_data": {},
            },
        ]
    }

    sample_room_state.event_choice_index = None

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(event_room)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 4:
            return _scalar_result(sample_room_state)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ws.broadcast_to_session = AsyncMock()

    result = await interact_with_room(mock_db, 100, 200, "event_choice", choice_index=0)

    assert result.success is True
    assert result.action == "event_choice"
    assert result.message == "Алтарь одарил вас!"
    assert sample_room_state.event_choice_index == 0


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_event_choice_already_made(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_room_state, sample_redis_state,
):
    """Event choice already made -> error."""
    from gameplay import interact_with_room
    from fastapi import HTTPException

    event_room = MagicMock()
    event_room.id = 10
    event_room.room_type = "event"
    event_room.name = "Алтарь"
    event_room.room_config = {"choices": [{"text": "A", "outcome_type": "nothing", "outcome_text": "", "outcome_data": {}}]}

    sample_room_state.event_choice_index = 0  # Already chosen

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(event_room)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 4:
            return _scalar_result(sample_room_state)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)

    with pytest.raises(HTTPException) as exc_info:
        await interact_with_room(mock_db, 100, 200, "event_choice", choice_index=0)

    assert exc_info.value.status_code == 400
    assert "уже" in exc_info.value.detail.lower()


@pytest.mark.asyncio
@patch("time.time")
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_rest_start_and_complete(
    mock_ss, mock_http, mock_ws, mock_time_time,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    """Rest: start sets timer, complete after enough time applies recovery."""
    from gameplay import interact_with_room

    rest_room = MagicMock()
    rest_room.id = 10
    rest_room.room_type = "rest"
    rest_room.name = "Комната отдыха"
    rest_room.room_config = {
        "heal_percent": 30,
        "wait_seconds": 60,
        "gold_cost": 0,
    }

    room_state = MagicMock()
    room_state.id = 1
    room_state.session_id = 100
    room_state.room_id = 10
    room_state.is_cleared = False
    room_state.loot_collected = False
    room_state.event_choice_index = None
    room_state.extra_data = {}

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(rest_room)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 4:
            return _scalar_result(room_state)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.set_phase = AsyncMock()
    mock_ws.broadcast_to_session = AsyncMock()

    # Start rest
    mock_time_time.return_value = 1000.0

    result = await interact_with_room(mock_db, 100, 200, "start_rest")
    assert result.success is True
    assert result.action == "start_rest"
    assert room_state.extra_data.get("rest_started_at") == 1000.0
    mock_ss.set_phase.assert_called_with(100, "resting")

    # Now complete rest — need to re-set execute for the second call
    # Simulate 61 seconds passed
    mock_time_time.return_value = 1061.0

    # Update redis_state phase to resting
    resting_state = {**sample_redis_state, "phase": "resting"}
    mock_ss.get_session_state = AsyncMock(return_value=resting_state)

    call_count[0] = 0
    def execute_side_effect_2(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(rest_room)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 4:
            return _scalar_result(room_state)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect_2)

    mock_http.get_character_attributes = AsyncMock(return_value={"max_health": 100})
    mock_http.recover_character = AsyncMock(return_value={})

    result2 = await interact_with_room(mock_db, 100, 200, "complete_rest")
    assert result2.success is True
    assert result2.action == "complete_rest"
    assert room_state.extra_data.get("rest_used") is True
    # recover_character called for 2 alive members
    assert mock_http.recover_character.call_count == 2


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_revive_member(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_room_state, sample_redis_state,
):
    """Revive dead member in rest room: status alive, gold deducted."""
    from gameplay import interact_with_room

    rest_room = MagicMock()
    rest_room.id = 10
    rest_room.room_type = "rest"
    rest_room.name = "Комната отдыха"
    rest_room.room_config = {"revive_gold_cost": 500}

    # One member is dead
    redis_with_dead = {**sample_redis_state}
    redis_with_dead["members"] = {
        "200": {"user_id": 1, "status": "alive"},
        "201": {"user_id": 2, "status": "dead"},
    }
    redis_with_dead["dead_count"] = 1

    member_obj = MagicMock()
    member_obj.status = "dead"

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(rest_room)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 4:
            return _scalar_result(sample_room_state)
        elif call_count[0] == 5:
            return _scalar_result(member_obj)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=redis_with_dead)
    mock_ss.update_member_status = AsyncMock(return_value=redis_with_dead)
    mock_http.deduct_gold = AsyncMock(return_value=True)
    mock_http.get_character_attributes = AsyncMock(return_value={"max_health": 100})
    mock_http.recover_character = AsyncMock(return_value={})
    mock_http.get_character_profile = AsyncMock(return_value={"name": "Павший"})
    mock_ws.broadcast_to_session = AsyncMock()

    result = await interact_with_room(
        mock_db, 100, 200, "revive_member", target_character_id=201,
    )

    assert result.success is True
    assert result.gold_spent == 500
    mock_http.deduct_gold.assert_called_once_with(200, 500)
    mock_ss.update_member_status.assert_called_once_with(100, "201", "alive")
    assert member_obj.status == "alive"


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_merchant_buy(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    """Merchant buy: item added, gold deducted, stock decremented."""
    from gameplay import interact_with_room

    merchant_room = MagicMock()
    merchant_room.id = 10
    merchant_room.room_type = "merchant"
    merchant_room.name = "Торговец"
    merchant_room.room_config = {
        "items": [
            {"item_id": 77, "price": 100, "stock": 5},
        ]
    }

    room_state = MagicMock()
    room_state.id = 1
    room_state.session_id = 100
    room_state.room_id = 10
    room_state.is_cleared = False
    room_state.loot_collected = False
    room_state.event_choice_index = None
    room_state.extra_data = {}

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(merchant_room)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 4:
            return _scalar_result(room_state)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_http.deduct_gold = AsyncMock(return_value=True)
    mock_ws.broadcast_to_session = AsyncMock()

    result = await interact_with_room(
        mock_db, 100, 200, "merchant_buy", item_id=77, quantity=2,
    )

    assert result.success is True
    assert result.gold_spent == 200  # 100 * 2
    assert result.loot_gained == [{"item_id": 77, "quantity": 2}]
    # Stock decremented
    assert room_state.extra_data["merchant_stock"]["77"] == 3  # 5 - 2


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_merchant_insufficient_gold(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    """Merchant buy with insufficient gold -> error."""
    from gameplay import interact_with_room
    from fastapi import HTTPException

    merchant_room = MagicMock()
    merchant_room.id = 10
    merchant_room.room_type = "merchant"
    merchant_room.name = "Торговец"
    merchant_room.room_config = {
        "items": [{"item_id": 77, "price": 1000, "stock": 5}]
    }

    room_state = MagicMock()
    room_state.extra_data = {}

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(merchant_room)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 4:
            return _scalar_result(room_state)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_http.deduct_gold = AsyncMock(return_value=False)  # No gold

    with pytest.raises(HTTPException) as exc_info:
        await interact_with_room(mock_db, 100, 200, "merchant_buy", item_id=77, quantity=1)

    assert exc_info.value.status_code == 400
    assert "золот" in exc_info.value.detail.lower()


@pytest.mark.asyncio
@patch("gameplay.random")
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_mana_core_success(
    mock_ss, mock_http, mock_ws, mock_random,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    """Mana core: successful destruction, crystal gained, dungeon deactivated."""
    from gameplay import interact_with_room

    mana_core_room = MagicMock()
    mana_core_room.id = 10
    mana_core_room.room_type = "event"
    mana_core_room.name = "Комната ядра маны"
    mana_core_room.is_mana_core_room = True
    mana_core_room.room_config = {}

    sample_dungeon.mana_core_chance = 0.8
    sample_dungeon.mana_core_item_id = 999

    # random.random() returns 0.1 (below 0.8 => success)
    mock_random.random.return_value = 0.1

    room_state = MagicMock()
    room_state.extra_data = {}

    boss_room = MagicMock()
    boss_room.id = 5
    boss_room.is_boss_room = True

    boss_room_state = MagicMock()
    boss_room_state.is_cleared = True

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(mana_core_room)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 4:
            return _scalar_result(room_state)
        elif call_count[0] == 5:
            # Boss room query (scalars().all())
            return _scalars_result([boss_room])
        elif call_count[0] == 6:
            # Boss room state check
            return _scalar_result(boss_room_state)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.set_dungeon_cooldown = AsyncMock()
    mock_ss.update_session_state = AsyncMock()
    mock_ws.broadcast_to_session = AsyncMock()

    result = await interact_with_room(mock_db, 100, 200, "search_mana_core")

    assert result.success is True
    assert result.loot_gained is not None
    assert result.loot_gained[0]["item_id"] == 999
    assert sample_dungeon.is_active is False
    assert sample_session.status == "completed"


@pytest.mark.asyncio
@patch("gameplay.random")
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_mana_core_fail(
    mock_ss, mock_http, mock_ws, mock_random,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    """Mana core: failure, no crystal, session completed."""
    from gameplay import interact_with_room

    mana_core_room = MagicMock()
    mana_core_room.id = 10
    mana_core_room.room_type = "event"
    mana_core_room.name = "Ядро маны"
    mana_core_room.is_mana_core_room = True
    mana_core_room.room_config = {}

    sample_dungeon.mana_core_chance = 0.3
    sample_dungeon.mana_core_item_id = 999

    # random.random() returns 0.9 (above 0.3 => failure)
    mock_random.random.return_value = 0.9

    room_state = MagicMock()
    room_state.extra_data = {}

    boss_room = MagicMock()
    boss_room.id = 5
    boss_room.is_boss_room = True

    boss_room_state = MagicMock()
    boss_room_state.is_cleared = True

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(mana_core_room)
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 4:
            return _scalar_result(room_state)
        elif call_count[0] == 5:
            return _scalars_result([boss_room])
        elif call_count[0] == 6:
            return _scalar_result(boss_room_state)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.update_session_state = AsyncMock()
    mock_ws.broadcast_to_session = AsyncMock()

    result = await interact_with_room(mock_db, 100, 200, "search_mana_core")

    assert result.success is False
    assert result.loot_gained is None
    assert sample_session.status == "completed"


# =====================================================================
# Flee tests
# =====================================================================


@pytest.mark.asyncio
@patch("gameplay.random")
@patch("gameplay.ws_manager")
@patch("gameplay.session_state")
async def test_flee_50_percent_loss(mock_ss, mock_ws, mock_random, mock_db, sample_session, sample_redis_state):
    """Flee: mock random to verify ~50% items lost."""
    from gameplay import flee_dungeon

    inv_item1 = MagicMock()
    inv_item1.item_id = 10
    inv_item1.quantity = 3

    inv_item2 = MagicMock()
    inv_item2.item_id = 20
    inv_item2.quantity = 1

    inv_item3 = MagicMock()
    inv_item3.item_id = 30
    inv_item3.quantity = 2

    # Random: first item lost (0.3 < 0.5), second kept (0.8 >= 0.5), third lost (0.2 < 0.5)
    mock_random.random.side_effect = [0.3, 0.8, 0.2]

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalars_result([inv_item1, inv_item2, inv_item3])
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.update_session_state = AsyncMock()
    mock_ss.set_session_inventory = AsyncMock()
    mock_ws.broadcast_to_session = AsyncMock()

    result = await flee_dungeon(mock_db, 100, 200)

    assert result.status == "escaped"
    assert len(result.items_lost) == 2  # items 10 and 30
    assert len(result.items_remaining) == 1  # item 20
    assert result.items_remaining[0].item_id == 20
    assert sample_session.status == "escaped"


@pytest.mark.asyncio
@patch("gameplay.random")
@patch("gameplay.ws_manager")
@patch("gameplay.session_state")
async def test_flee_empty_inventory(mock_ss, mock_ws, mock_random, mock_db, sample_session, sample_redis_state):
    """Flee with no items: status escaped, no losses."""
    from gameplay import flee_dungeon

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalars_result([])
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.update_session_state = AsyncMock()
    mock_ss.set_session_inventory = AsyncMock()
    mock_ws.broadcast_to_session = AsyncMock()

    result = await flee_dungeon(mock_db, 100, 200)

    assert result.status == "escaped"
    assert len(result.items_lost) == 0
    assert len(result.items_remaining) == 0
    assert "пуст" in result.message.lower()


@pytest.mark.asyncio
@patch("gameplay.session_state")
async def test_flee_not_leader(mock_ss, mock_db, sample_session, sample_redis_state):
    """Flee by non-leader -> 403."""
    from gameplay import flee_dungeon
    from fastapi import HTTPException

    mock_db.execute = AsyncMock(return_value=_scalar_result(sample_session))
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)

    with pytest.raises(HTTPException) as exc_info:
        await flee_dungeon(mock_db, 100, 201)  # 201 is not leader

    assert exc_info.value.status_code == 403


# =====================================================================
# Loot Distribution tests
# =====================================================================


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_distribute_loot_success(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_redis_state,
):
    """Loot distribution: items added to character inventories."""
    from gameplay import distribute_loot

    sample_session.status = "completed"
    redis_completed = {**sample_redis_state, "phase": "distributing_loot", "status": "completed"}

    inv_item = MagicMock()
    inv_item.item_id = 10
    inv_item.quantity = 3
    inv_item.source_description = "Сундук"

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalars_result([inv_item])
        elif call_count[0] == 3:
            return _scalars_result([])  # remaining after distribution
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=redis_completed)
    mock_ss.set_session_inventory = AsyncMock()
    mock_http.add_item_to_character = AsyncMock(return_value={})
    mock_ws.broadcast_to_session = AsyncMock()

    distributions = [
        {"item_id": 10, "quantity": 2, "to_character_id": 200},
        {"item_id": 10, "quantity": 1, "to_character_id": 201},
    ]

    result = await distribute_loot(mock_db, 100, 200, distributions)

    assert result.success is True
    assert mock_http.add_item_to_character.call_count == 2
    mock_http.add_item_to_character.assert_any_call(200, 10, 2)
    mock_http.add_item_to_character.assert_any_call(201, 10, 1)


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_distribute_loot_insufficient_quantity(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_redis_state,
):
    """Loot distribution: error when requested quantity exceeds available."""
    from gameplay import distribute_loot
    from fastapi import HTTPException

    sample_session.status = "completed"
    redis_completed = {**sample_redis_state, "phase": "distributing_loot", "status": "completed"}

    inv_item = MagicMock()
    inv_item.item_id = 10
    inv_item.quantity = 2
    inv_item.source_description = "Сундук"

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalars_result([inv_item])
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=redis_completed)

    distributions = [
        {"item_id": 10, "quantity": 5, "to_character_id": 200},  # Only 2 available
    ]

    with pytest.raises(HTTPException) as exc_info:
        await distribute_loot(mock_db, 100, 200, distributions)

    assert exc_info.value.status_code == 400
    assert "5" in exc_info.value.detail and "2" in exc_info.value.detail


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_distribute_loot_invalid_member(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_redis_state,
):
    """Loot distribution: error when target character is not a session member."""
    from gameplay import distribute_loot
    from fastapi import HTTPException

    sample_session.status = "completed"
    redis_completed = {**sample_redis_state, "phase": "distributing_loot", "status": "completed"}

    inv_item = MagicMock()
    inv_item.item_id = 10
    inv_item.quantity = 2
    inv_item.source_description = "Сундук"

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalars_result([inv_item])
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.get_session_state = AsyncMock(return_value=redis_completed)

    distributions = [
        {"item_id": 10, "quantity": 1, "to_character_id": 999},  # Not a member
    ]

    with pytest.raises(HTTPException) as exc_info:
        await distribute_loot(mock_db, 100, 200, distributions)

    assert exc_info.value.status_code == 400
    assert "999" in exc_info.value.detail


# =====================================================================
# Finalization tests
# =====================================================================


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.session_state")
async def test_finalize_success(
    mock_ss, mock_ws,
    mock_db, sample_session, sample_dungeon,
):
    """Finalize: cooldown set, Redis cleaned."""
    from gameplay import finalize_session

    sample_session.status = "completed"

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalars_result([])  # No remaining items
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.set_dungeon_cooldown = AsyncMock()
    mock_ss.cleanup_session = AsyncMock()
    mock_ws.cleanup_session = AsyncMock()

    result = await finalize_session(mock_db, 100, 200)

    assert "кулдаун" in result.message.lower() or "пройдено" in result.message.lower()
    assert result.cooldown_until is not None
    mock_ss.set_dungeon_cooldown.assert_called_once_with(1, 100, 24)
    mock_ss.cleanup_session.assert_called_once()
    mock_ws.cleanup_session.assert_called_once_with(100)


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.session_state")
async def test_finalize_inventory_not_empty(
    mock_ss, mock_ws,
    mock_db, sample_session,
):
    """Finalize with remaining items (no force) -> error."""
    from gameplay import finalize_session
    from fastapi import HTTPException

    sample_session.status = "completed"

    remaining_item = MagicMock()
    remaining_item.item_id = 10
    remaining_item.quantity = 1

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalars_result([remaining_item])
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)

    with pytest.raises(HTTPException) as exc_info:
        await finalize_session(mock_db, 100, 200, force=False)

    assert exc_info.value.status_code == 400
    assert "нераспределённые" in exc_info.value.detail.lower()


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.session_state")
async def test_finalize_force(
    mock_ss, mock_ws,
    mock_db, sample_session, sample_dungeon,
):
    """Finalize with force=True: discards remaining items."""
    from gameplay import finalize_session

    sample_session.status = "completed"

    remaining_item = MagicMock()
    remaining_item.item_id = 10
    remaining_item.quantity = 1

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalars_result([remaining_item])
        elif call_count[0] == 3:
            return _scalar_result(sample_dungeon)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ss.set_dungeon_cooldown = AsyncMock()
    mock_ss.cleanup_session = AsyncMock()
    mock_ws.cleanup_session = AsyncMock()

    result = await finalize_session(mock_db, 100, 200, force=True)

    assert result.cooldown_until is not None
    # Item was deleted
    mock_db.delete.assert_called_with(remaining_item)
    mock_ss.cleanup_session.assert_called_once()


@pytest.mark.asyncio
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_cooldown_blocks_new_session(mock_ss, mock_http, mock_db):
    """After finalize, new session creation is blocked by cooldown."""
    from gameplay import create_session
    from fastapi import HTTPException

    dungeon = MagicMock()
    dungeon.id = 1
    dungeon.is_active = True
    dungeon.location_id = 10

    mock_db.execute = AsyncMock(return_value=_scalar_result(dungeon))
    mock_ss.check_dungeon_cooldown = AsyncMock(return_value=(True, 3600))

    with pytest.raises(HTTPException) as exc_info:
        await create_session(mock_db, 200, 1, 1)

    assert exc_info.value.status_code == 403
    assert "кулдаун" in exc_info.value.detail.lower()


# =====================================================================
# Battle integration tests
# =====================================================================


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_initiate_room_battle(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    """initiate_room_battle spawns mobs, creates battle, updates Redis."""
    from gameplay import initiate_room_battle

    battle_room = MagicMock()
    battle_room.id = 15
    battle_room.room_type = "battle"
    battle_room.name = "Логово мобов"
    battle_room.room_config = {"mob_template_ids": [1, 2, 3]}

    mock_http.spawn_dungeon_mobs = AsyncMock(return_value=[300, 301, 302])
    mock_http.create_battle = AsyncMock(return_value={"battle_id": 555})
    mock_ss.set_active_battle = AsyncMock()
    mock_ws.broadcast_to_session = AsyncMock()

    battle_id = await initiate_room_battle(
        mock_db, 100, battle_room, sample_dungeon, sample_redis_state,
    )

    assert battle_id == 555
    mock_http.spawn_dungeon_mobs.assert_called_once_with([1, 2, 3], 10)
    mock_ss.set_active_battle.assert_called_once_with(100, 555)

    # Verify battle was created with correct players
    create_call = mock_http.create_battle.call_args
    players = create_call.kwargs.get("players") or create_call[1].get("players")
    team1_ids = [p["character_id"] for p in players if p["team"] == 1]
    team2_ids = [p["character_id"] for p in players if p["team"] == 2]
    assert set(team1_ids) == {200, 201}
    assert set(team2_ids) == {300, 301, 302}


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_process_battle_completion(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    """process_battle_completion marks room cleared on party victory."""
    from gameplay import process_battle_completion

    battle_state_data = {
        "runtime": {
            "participants": {
                "1": {"character_id": 200, "team": 1, "hp": 50},
                "2": {"character_id": 201, "team": 1, "hp": 30},
                "3": {"character_id": 300, "team": 2, "hp": 0},
            },
        },
    }

    room_state_obj = MagicMock()
    room_state_obj.is_cleared = False

    room_obj = MagicMock()
    room_obj.is_boss_room = False

    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.clear_active_battle = AsyncMock()
    mock_ss.update_member_status = AsyncMock()

    call_count = [0]
    def execute_side_effect(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _scalar_result(sample_session)
        elif call_count[0] == 2:
            return _scalar_result(sample_dungeon)
        elif call_count[0] == 3:
            return _scalar_result(room_state_obj)
        elif call_count[0] == 4:
            return _scalar_result(room_obj)
        return _scalar_result(None)
    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_ws.broadcast_to_session = AsyncMock()

    results = await process_battle_completion(mock_db, 100, 777, battle_state_data)

    assert results["party_won"] is True
    assert results["casualties"] == []
    assert room_state_obj.is_cleared is True

# helpers.py - Shared test data factory functions for dungeon-service tests.
# Extracted from conftest.py to avoid `from conftest import` anti-pattern.


def _dungeon_payload(**overrides) -> dict:
    """Return a valid DungeonCreate payload."""
    base = {
        "name": "Test Dungeon",
        "description": "A dark test dungeon",
        "lore_text": "Ancient halls of testing",
        "stability_type": "static",
        "danger_level": "safe",
        "location_id": 1,
        "recommended_level": 5,
        "recommended_party_size": 2,
        "cooldown_hours": 24,
        "mob_multiplier": 1.0,
        "loot_multiplier": 1.0,
        "stamina_multiplier": 1.0,
        "difficulty_modifier": 1.0,
        "disable_rest_rooms": False,
        "disable_merchants": False,
        "mana_core_chance": 0.1,
        "mana_core_item_id": None,
        "image_url": None,
    }
    base.update(overrides)
    return base


def _room_payload(room_type="battle", **overrides) -> dict:
    """Return a valid DungeonRoomCreate payload."""
    base = {
        "room_type": room_type,
        "name": "Room (" + room_type + ")",
        "description": "A " + room_type + " room",
        "sort_order": 0,
        "is_entrance": False,
        "is_boss_room": False,
        "is_mana_core_room": False,
        "room_config": None,
    }
    base.update(overrides)
    return base


def _corridor_payload(from_room_id, to_room_id, **overrides) -> dict:
    """Return a valid DungeonCorridorCreate payload."""
    base = {
        "from_room_id": from_room_id,
        "to_room_id": to_room_id,
        "stamina_cost": 5,
        "is_bidirectional": True,
        "random_battle_chance": 0.0,
        "random_battle_mob_ids": None,
        "trap_chance": 0.0,
        "trap_config": None,
        "description": None,
    }
    base.update(overrides)
    return base

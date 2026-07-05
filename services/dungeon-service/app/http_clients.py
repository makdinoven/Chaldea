"""
HTTP clients for dungeon-service to call other microservices.

All functions use httpx.AsyncClient with a 10-second timeout.
Errors are logged and re-raised as fastapi.HTTPException with Russian messages.
"""

import logging
from typing import List, Optional

import httpx
from fastapi import HTTPException

from config import settings

logger = logging.getLogger("dungeon-service.http_clients")

DEFAULT_TIMEOUT = 10.0


def _client(timeout: float = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    """Create a new httpx.AsyncClient with the given timeout."""
    return httpx.AsyncClient(timeout=timeout)


# =====================================================================
# Character Service  (http://character-service:8005)
# =====================================================================

async def get_character_profile(character_id: int) -> dict:
    """
    GET /characters/{character_id}/profile
    Returns character profile dict (avatar, name, level, class, race, location, etc.)
    """
    url = f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/profile"
    try:
        async with _client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при получении профиля персонажа %d: %s", character_id, e)
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Персонаж не найден")
        raise HTTPException(status_code=502, detail="Ошибка при получении данных персонажа")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с character-service (profile %d): %s", character_id, e)
        raise HTTPException(status_code=503, detail="Сервис персонажей недоступен")


async def get_party_active_members(character_id: int, location_id: int) -> dict:
    """GET party-service /party/internal/active-members — the character's
    co-located accepted squad (FEAT-144 Ф3). Returns {} on failure (solo)."""
    url = f"{settings.PARTY_SERVICE_URL}/party/internal/active-members"
    try:
        async with _client() as client:
            resp = await client.get(
                url, params={"character_id": character_id, "location_id": location_id},
            )
            if resp.status_code == 200:
                return resp.json()
    except httpx.RequestError as e:
        logger.warning("party active-members failed for %d: %s", character_id, e)
    return {}


async def consume_dungeon_gate(character_id: int, location_id: int, dungeon_id: int) -> bool:
    """Consume a 'dungeon' action-gate naming THIS dungeon (FEAT-145 v2).
    Returns True if a gate was consumed (entry allowed)."""
    url = f"{settings.LOCATIONS_SERVICE_URL}/locations/internal/action-gate/consume"
    try:
        async with _client() as client:
            resp = await client.post(url, json={
                "character_id": character_id, "location_id": location_id,
                "action_type": "dungeon", "target_ref": dungeon_id,
            })
            if resp.status_code == 200:
                return bool(resp.json().get("consumed"))
    except httpx.RequestError as e:
        logger.warning("dungeon gate consume failed for %d: %s", character_id, e)
    return False


async def get_characters_at_location(location_id: int) -> list:
    """
    GET /characters/by_location?location_id={id}
    Returns list of characters at the given location.
    """
    url = f"{settings.CHARACTER_SERVICE_URL}/characters/by_location"
    try:
        async with _client() as client:
            resp = await client.get(url, params={"location_id": location_id})
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при получении персонажей на локации %d: %s", location_id, e)
        raise HTTPException(status_code=502, detail="Ошибка при получении персонажей на локации")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с character-service (by_location %d): %s", location_id, e)
        raise HTTPException(status_code=503, detail="Сервис персонажей недоступен")


async def spawn_dungeon_mobs(mob_template_ids: List[int], location_id: int) -> List[int]:
    """
    POST /characters/internal/spawn-dungeon-mobs
    Spawns ActiveMob entries from the given mob templates at the location.

    Request body: {"mob_template_ids": [1,2,3], "location_id": 42}
    Returns: list of character_ids for the spawned mobs.

    Note: this internal endpoint in character-service is created as part
    of the dungeon system integration (Task #11).
    """
    url = f"{settings.CHARACTER_SERVICE_URL}/characters/internal/spawn-dungeon-mobs"
    payload = {
        "mob_template_ids": mob_template_ids,
        "location_id": location_id,
    }
    try:
        async with _client() as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("character_ids", [])
    except httpx.HTTPStatusError as e:
        logger.error(
            "Ошибка при спавне мобов (templates=%s, location=%d): %s",
            mob_template_ids, location_id, e,
        )
        raise HTTPException(status_code=502, detail="Ошибка при создании мобов для подземелья")
    except httpx.RequestError as e:
        logger.error(
            "Ошибка соединения с character-service (spawn mobs, location=%d): %s",
            location_id, e,
        )
        raise HTTPException(status_code=503, detail="Сервис персонажей недоступен")


# =====================================================================
# Character Attributes Service  (http://character-attributes-service:8002)
# =====================================================================

async def get_character_attributes(character_id: int) -> dict:
    """
    GET /attributes/{character_id}
    Returns full character attributes (HP, mana, energy, stamina, stats, etc.)
    """
    url = f"{settings.CHAR_ATTRS_SERVICE_URL}/attributes/{character_id}"
    try:
        async with _client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при получении атрибутов персонажа %d: %s", character_id, e)
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Атрибуты персонажа не найдены")
        raise HTTPException(status_code=502, detail="Ошибка при получении атрибутов персонажа")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с attributes-service (character %d): %s", character_id, e)
        raise HTTPException(status_code=503, detail="Сервис атрибутов недоступен")


async def consume_stamina(character_id: int, amount: int) -> bool:
    """
    POST /attributes/{character_id}/consume_stamina
    Body: {"amount": N}

    Returns True if stamina was successfully consumed.
    Returns False if the character has insufficient stamina (400 from attributes-service).
    Raises HTTPException on other errors.
    """
    url = f"{settings.CHAR_ATTRS_SERVICE_URL}/attributes/{character_id}/consume_stamina"
    try:
        async with _client() as client:
            resp = await client.post(url, json={"amount": amount})
            if resp.status_code == 400:
                # Insufficient stamina — not a server error, return False
                return False
            resp.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при списании стамины персонажа %d: %s", character_id, e)
        raise HTTPException(status_code=502, detail="Ошибка при списании стамины")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с attributes-service (consume_stamina %d): %s", character_id, e)
        raise HTTPException(status_code=503, detail="Сервис атрибутов недоступен")


async def recover_character(
    character_id: int,
    health: int = 0,
    mana: int = 0,
    energy: int = 0,
    stamina: int = 0,
) -> dict:
    """
    POST /attributes/{character_id}/recover
    Body: {"health_recovery": N, "mana_recovery": N, "energy_recovery": N, "stamina_recovery": N}

    Recovers the specified resources (capped at max values by the attributes-service).
    Returns the response dict from attributes-service.
    """
    url = f"{settings.CHAR_ATTRS_SERVICE_URL}/attributes/{character_id}/recover"
    payload = {
        "health_recovery": health,
        "mana_recovery": mana,
        "energy_recovery": energy,
        "stamina_recovery": stamina,
    }
    try:
        async with _client() as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при восстановлении ресурсов персонажа %d: %s", character_id, e)
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Атрибуты персонажа не найдены")
        raise HTTPException(status_code=502, detail="Ошибка при восстановлении ресурсов персонажа")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с attributes-service (recover %d): %s", character_id, e)
        raise HTTPException(status_code=503, detail="Сервис атрибутов недоступен")


# =====================================================================
# Inventory Service  (http://inventory-service:8004)
# =====================================================================

async def add_item_to_character(character_id: int, item_id: int, quantity: int) -> dict:
    """
    POST /inventory/{character_id}/items
    Body: {"item_id": N, "quantity": N}

    Adds the item to the character's inventory (with stack support).
    Returns the response from inventory-service.
    """
    url = f"{settings.INVENTORY_SERVICE_URL}/inventory/{character_id}/items"
    payload = {"item_id": item_id, "quantity": quantity}
    try:
        async with _client() as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(
            "Ошибка при добавлении предмета %d (x%d) персонажу %d: %s",
            item_id, quantity, character_id, e,
        )
        raise HTTPException(status_code=502, detail="Ошибка при добавлении предмета в инвентарь")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с inventory-service (add_item, character %d): %s", character_id, e)
        raise HTTPException(status_code=503, detail="Сервис инвентаря недоступен")


async def get_character_items(character_id: int) -> list:
    """
    GET /inventory/{character_id}/items
    Returns list of items in the character's inventory.
    """
    url = f"{settings.INVENTORY_SERVICE_URL}/inventory/{character_id}/items"
    try:
        async with _client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при получении инвентаря персонажа %d: %s", character_id, e)
        raise HTTPException(status_code=502, detail="Ошибка при получении инвентаря персонажа")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с inventory-service (get_items, character %d): %s", character_id, e)
        raise HTTPException(status_code=503, detail="Сервис инвентаря недоступен")


async def get_item_info(item_id: int) -> dict:
    """
    GET /inventory/items/{item_id}
    Returns item catalog info (name, type, rarity, stats, etc.)
    """
    url = f"{settings.INVENTORY_SERVICE_URL}/inventory/items/{item_id}"
    try:
        async with _client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при получении информации о предмете %d: %s", item_id, e)
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Предмет не найден")
        raise HTTPException(status_code=502, detail="Ошибка при получении информации о предмете")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с inventory-service (get_item %d): %s", item_id, e)
        raise HTTPException(status_code=503, detail="Сервис инвентаря недоступен")


# =====================================================================
# Battle Service  (http://battle-service:8010)
# =====================================================================

async def create_battle(
    players: List[dict],
    battle_type: str = "pve",
    context: Optional[dict] = None,
    auth_token: Optional[str] = None,
) -> dict:
    """
    POST /battles/
    Body: BattleCreate schema — {"players": [{"character_id": N, "team": N}, ...], "battle_type": "pve"}

    Creates a new battle and returns the BattleCreated response
    (battle_id, participants, next_actor, deadline_at).

    The `context` parameter is kept for future use (dungeon_session_id, room_id)
    but is NOT sent to battle-service as BattleCreate does not include it.
    auth_token is the user's JWT token, required by battle-service.
    """
    url = f"{settings.BATTLE_SERVICE_URL}/battles/"
    payload = {
        "players": players,
        "battle_type": battle_type,
    }
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    try:
        async with _client(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при создании боя (type=%s): %s", battle_type, e)
        detail = "Ошибка при создании боя"
        if e.response.status_code == 400:
            # Try to extract a more specific message from battle-service
            try:
                detail = e.response.json().get("detail", detail)
            except Exception:
                pass
        raise HTTPException(status_code=502, detail=detail)
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с battle-service (create_battle): %s", e)
        raise HTTPException(status_code=503, detail="Боевая система недоступна")


async def get_battle_state(battle_id: int) -> Optional[dict]:
    """
    GET /battles/internal/{battle_id}/state
    Returns the current battle state (participants, turn order, HP, status, etc.)
    Uses the internal endpoint (no JWT required) for service-to-service calls.
    Used to poll battle completion status from the dungeon gameplay loop.

    Returns None if battle state not found (404) — means battle is finished
    and Redis state has been cleaned up.
    """
    url = f"{settings.BATTLE_SERVICE_URL}/battles/internal/{battle_id}/state"
    try:
        async with _client() as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                # Battle finished, Redis state expired
                return None
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при получении состояния боя %d: %s", battle_id, e)
        raise HTTPException(status_code=502, detail="Ошибка при получении состояния боя")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с battle-service (get_state %d): %s", battle_id, e)
        raise HTTPException(status_code=503, detail="Боевая система недоступна")


# =====================================================================
# Character Service — Gold Operations  (http://character-service:8005)
# =====================================================================

async def add_gold(character_id: int, gold: int) -> dict:
    """
    POST /characters/{character_id}/add_rewards
    Body: {"xp": 0, "gold": N}

    Adds gold to the character's currency_balance via the existing add_rewards endpoint.
    Returns the response from character-service.
    """
    url = f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/add_rewards"
    payload = {"xp": 0, "gold": gold}
    try:
        async with _client() as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при начислении золота персонажу %d: %s", character_id, e)
        raise HTTPException(status_code=502, detail="Ошибка при начислении золота")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с character-service (add_gold %d): %s", character_id, e)
        raise HTTPException(status_code=503, detail="Сервис персонажей недоступен")


async def deduct_gold(character_id: int, amount: int) -> bool:
    """
    POST /characters/internal/deduct-gold
    Body: {"character_id": N, "amount": N}

    Deducts gold from the character's currency_balance.
    Returns True if successful, False if insufficient gold (400).

    Note: this internal endpoint in character-service needs to be created.
    The existing add_rewards endpoint validates gold >= 0 so it cannot be
    used for deductions. The new endpoint should:
    1. Check currency_balance >= amount
    2. Subtract amount from currency_balance
    3. Log gold_transaction with negative amount
    """
    url = f"{settings.CHARACTER_SERVICE_URL}/characters/internal/deduct-gold"
    payload = {"character_id": character_id, "amount": amount}
    try:
        async with _client() as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 400:
                # Insufficient gold
                return False
            resp.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        logger.error("Ошибка при списании золота у персонажа %d: %s", character_id, e)
        raise HTTPException(status_code=502, detail="Ошибка при списании золота")
    except httpx.RequestError as e:
        logger.error("Ошибка соединения с character-service (deduct_gold %d): %s", character_id, e)
        raise HTTPException(status_code=503, detail="Сервис персонажей недоступен")

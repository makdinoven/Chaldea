"""
Асинхронные лёгкие врапперы поверх боевого сервиса.
"""
from typing import Any, Optional
import httpx
from config import settings

_BATTLE = settings.BATTLE_SERVICE_URL.rstrip("/")
_CHARACTER = settings.CHARACTER_SERVICE_URL.rstrip("/")


async def get_battle_state(battle_id: int) -> dict[str, Any]:
    async with httpx.AsyncClient() as c:
        # Use internal endpoint (no JWT required) for service-to-service calls
        r = await c.get(f"{_BATTLE}/battles/internal/{battle_id}/state")
        r.raise_for_status()
        return r.json()


async def post_battle_action(battle_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as c:
        # Use internal endpoint (no JWT required) for service-to-service calls
        r = await c.post(f"{_BATTLE}/battles/internal/{battle_id}/action", json=payload)
        r.raise_for_status()
        return r.json()


async def get_character_owner(character_id: int) -> Optional[int]:
    """
    Возвращает user_id владельца персонажа, обращаясь к character-service.
    Возвращает None, если персонаж не найден или сервис недоступен.
    """
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{_CHARACTER}/characters/{character_id}/profile")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("user_id")

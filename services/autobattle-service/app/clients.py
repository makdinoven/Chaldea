"""
Асинхронные лёгкие врапперы поверх боевого сервиса.
"""
from typing import Any
import httpx
from config import settings

_BATTLE = settings.BATTLE_SERVICE_URL.rstrip("/")


async def get_battle_state(battle_id: int) -> dict[str, Any]:
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{_BATTLE}/battles/{battle_id}/state")
        r.raise_for_status()
        return r.json()


async def post_battle_action(battle_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{_BATTLE}/battles/{battle_id}/action", json=payload)
        r.raise_for_status()
        return r.json()

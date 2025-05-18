# inventory_client.py
import httpx
from config import settings          # INVENTORY_SERVICE_URL

async def get_fast_slots(char_id: int, *, timeout: float = 5.0) -> list[dict]:
    """
    Возвращает только занятые fast_slot_* у персонажа.
    """
    url = f"{settings.INVENTORY_SERVICE_URL}/inventory/{char_id}/equipment"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        slots = resp.json()

    fast = [
        s for s in slots
        if s["slot_type"].startswith("fast_slot")
           and s["is_enabled"]
           and s["item_id"] is not None
    ]
    return fast

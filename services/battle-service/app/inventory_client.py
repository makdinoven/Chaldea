# inventory_client.py
import asyncio
import httpx
from config import settings

BASE = settings.INVENTORY_URL.rstrip("/")

async def get_item(item_id: int) -> dict:
    if item_id <= 0:
        raise ValueError("item_id must be > 0")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/inventory/items/{item_id}")
        r.raise_for_status()
        return r.json()

async def get_fast_slots(character_id: int) -> list[dict]:
    """
    Возвращает список слотов вида:
    [
      {
        "slot_type": "fast_slot_1",
        "item_id": 3,
        "quantity": 5
      }, …
    ]
    и подмешивает recovery-поля из самого предмета.
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/inventory/characters/{character_id}/fast_slots")
        r.raise_for_status()
        slots = r.json()

    # Параллельно тянем данные по каждому item_id
    coros = [get_item(s["item_id"]) for s in slots]
    items = await asyncio.gather(*coros)

    out = []
    for slot, item in zip(slots, items):
        # оставляем только нужные recovery-поля
        rec = {k: item.get(k, 0) for k in (
            "health_recovery",
            "mana_recovery",
            "energy_recovery",
            "stamina_recovery",
        ) if item.get(k)}
        out.append({
            "slot_type": slot["slot_type"],
            "item_id": slot["item_id"],
            "quantity": slot.get("quantity", 0),
            **rec
        })
    return out

# skills_client.py
import asyncio
import httpx
from config import settings

BASE = settings.SKILLS_URL.rstrip("/")


# -----------------------------------------------------------
# 1.  Rank → dict  + skill_type
# -----------------------------------------------------------
async def get_rank(rank_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/skills/admin/skill_ranks/{rank_id}")
        r.raise_for_status()
        rank_json = r.json()

        # если skill_type уже есть — возвращаем как есть
        if "skill_type" in rank_json:
            return rank_json

        # иначе запрашиваем сам skill
        skill_id = rank_json["skill_id"]
        rs = await client.get(f"{BASE}/skills/admin/skills/{skill_id}")
        rs.raise_for_status()
        skill_json = rs.json()

        rank_json["skill_type"] = skill_json["skill_type"]
        return rank_json


# -----------------------------------------------------------
# 2.  Проверка владения ранком
# -----------------------------------------------------------
async def character_has_rank(character_id: int, rank_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/skills/characters/{character_id}/skills")
        r.raise_for_status()
        owned = {cs["skill_rank"]["id"] for cs in r.json()}
    return rank_id in owned


# -----------------------------------------------------------
# 3.  Все ранги персонажа  (каждый с skill_type)
# -----------------------------------------------------------
async def character_ranks(character_id: int) -> list[dict]:
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BASE}/skills/characters/{character_id}/skills")
        r.raise_for_status()
        char_skill_rows = r.json()                      # [{'skill_rank_id': …}, …]

    # параллельные запросы + skill_type уже будет добавлен в get_rank
    coro_list = [get_rank(row["skill_rank_id"]) for row in char_skill_rows]
    return await asyncio.gather(*coro_list)


# -----------------------------------------------------------
# 4.  Информация о предмете
# -----------------------------------------------------------
async def get_item(item_id: int) -> dict:
    if not item_id or item_id <= 0:
        raise ValueError("item_id must be > 0")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{settings.INVENTORY_URL}/inventory/items/{item_id}")
        r.raise_for_status()
        return r.json()

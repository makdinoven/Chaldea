# skills_client.py
import asyncio

import httpx
from config import settings

# -----------------------------------------------------------
# 1.  Rank → dict  (как было)
# -----------------------------------------------------------
async def get_rank(rank_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.SKILLS_URL}/skills/admin/skill_ranks/{rank_id}"
        )
        r.raise_for_status()
        return r.json()

# -----------------------------------------------------------
# 2.  Проверка: есть ли у персонажа rank_id
#     (исправили путь к вложенному полю)
# -----------------------------------------------------------
async def character_has_rank(character_id: int, rank_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.SKILLS_URL}/skills/characters/{character_id}/skills"
        )
        r.raise_for_status()
        # >>> CharacterSkillRead содержит вложенный skill_rank
        owned = {cs["skill_rank"]["id"] for cs in r.json()}
    return rank_id in owned

# -----------------------------------------------------------
# 3.  Все ранги персонажа (добавили)
#     пригодится для snapshot’а до старта боя
# -----------------------------------------------------------
BASE = settings.SKILLS_URL.rstrip("/")

async def character_ranks(character_id: int) -> list[dict]:
    """
    Возвращает полный список рангов персонажа
    (каждый элемент = JSON, который приходит с /skill_ranks/{id})
    """
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BASE}/skills/characters/{character_id}/skills")
        r.raise_for_status()
        char_skill_rows = r.json()          # [{'skill_rank_id': …}, …]

    # параллельно скачиваем все ранги
    coro_list = [get_rank(row["skill_rank_id"]) for row in char_skill_rows]
    return await asyncio.gather(*coro_list)

# -----------------------------------------------------------
# 4.  Информация о предмете (как была)
# -----------------------------------------------------------
async def get_item(item_id: int) -> dict:
    if not item_id:
        raise ValueError("item_id must be > 0")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.INVENTORY_URL}/inventory/items/{item_id}"
        )
        r.raise_for_status()
        return r.json()

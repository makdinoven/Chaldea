# skills_client.py
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
async def character_ranks(character_id: int) -> list[dict]:
    """
    Возвращает «плоский» список рангов персонажа:
        [
          { "rank_id": 207,
            "skill_id": 5,
            "rank_number": 1,
            "rank_name": "Удар воителя – 1 ранг" },
          ...
        ]
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.SKILLS_URL}/skills/characters/{character_id}/skills"
        )
        r.raise_for_status()
        rows = r.json()                         # -> List[CharacterSkillRead]
    flat: list[dict] = []
    for cs in rows:
        rk = cs["skill_rank"]
        flat.append(
            {
                "rank_id":      rk["id"],
                "skill_id":     rk["skill_id"],
                "rank_number":  rk["rank_number"],
                "rank_name":    rk.get("rank_name"),
            }
        )
    return flat

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

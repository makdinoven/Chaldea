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
        r = await client.get(f"{BASE}/skills/skill_ranks/{rank_id}")
        r.raise_for_status()
        rank_json = r.json()

        # если skill_type уже есть — возвращаем как есть
        if "skill_type" in rank_json:
            return rank_json

        # иначе запрашиваем сам skill через публичный endpoint
        skill_id = rank_json["skill_id"]
        rs = await client.get(f"{BASE}/skills/skills/{skill_id}/full_tree")
        rs.raise_for_status()
        skill_json = rs.json()

        rank_json["skill_type"] = skill_json.get("skill_type", "")
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
        char_skill_rows = r.json()

    # Публичный эндпоинт уже возвращает полные данные ранга (skill_rank)
    # и skill_type — используем их напрямую, без повторных запросов к admin API
    results = []
    for row in char_skill_rows:
        rank_data = row.get("skill_rank", {})
        if not rank_data:
            continue
        # Добавляем поля из верхнего уровня ответа (CharacterSkillRead),
        # которых нет в skill_rank (SkillRankRead)
        for field in ("skill_type", "skill_image", "skill_name", "skill_description"):
            if field not in rank_data and field in row and row[field]:
                rank_data[field] = row[field]
        # Normalize skill_type to lowercase for consistent downstream usage
        if "skill_type" in rank_data and isinstance(rank_data["skill_type"], str):
            rank_data["skill_type"] = rank_data["skill_type"].lower()
        # Фоллбэк: если rank_image пуст, используем skill_image
        if not rank_data.get("rank_image") and rank_data.get("skill_image"):
            rank_data["rank_image"] = rank_data["skill_image"]
        results.append(rank_data)
    return results


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

import httpx, os, asyncio

SKILLS_URL = os.getenv("SKILLS_SERVICE_URL", "http://skills-service:8003")
INVENTORY_URL = os.getenv("INVENTORY_SERVICE_URL", "http://skills-service:8004")

async def get_rank(rank_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{SKILLS_URL}/skills/admin/skill_ranks/{rank_id}")
        r.raise_for_status()
        return r.json()

async def character_has_rank(character_id: int, rank_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SKILLS_URL}/skills/characters/{character_id}/skills"
        )
        r.raise_for_status()
        ranks = {cs["skill_rank_id"] for cs in r.json()}
    return rank_id in ranks

async def get_item(item_id: int) -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{INVENTORY_URL}/inventory/items/{item_id}")
        r.raise_for_status()
        return r.json()

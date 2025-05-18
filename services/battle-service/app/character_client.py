# character_client.py
import httpx
from config import settings    # CHARACTER_SERVICE_URL храните здесь

async def get_character_profile(char_id: int, *, timeout: float = 5.0) -> dict:
    """
    avatar, nickname, current title, …
    """
    url = f"{settings.CHARACTER_SERVICE_URL}/characters/{char_id}/profile"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

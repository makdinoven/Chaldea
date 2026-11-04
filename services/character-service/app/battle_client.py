"""Small HTTP client to battle-service (FEAT-198 guard battles).

* :func:`create_guard_battle` — ``POST /battles/internal/guard`` (async; the encounter choice «драться»);
* :func:`get_battle_result`   — ``GET /battles/internal/{id}/result`` (sync; the law pass polls lost callbacks).

Both send ``X-Internal-Token``. Errors are raised as :class:`BattleServiceError` (the caller decides what the player
sees); a 404 battle is reported as :data:`BATTLE_NOT_FOUND`.
"""

import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger("character-service.battle_client")

BATTLE_TIMEOUT_SECONDS = 10.0
BATTLE_NOT_FOUND = "not_found"


class BattleServiceError(Exception):
    """battle-service refused or could not answer. ``status_code`` is None on a transport failure."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail=None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def _base_url() -> str:
    return settings.BATTLE_SERVICE_URL.rstrip("/")


def _internal_headers() -> dict:
    # Imported lazily: auth_http reads the env var at import time and tests override the module attribute there.
    import auth_http
    return {"X-Internal-Token": auth_http.INTERNAL_SERVICE_TOKEN}


def _detail(response) -> object:
    try:
        return (response.json() or {}).get("detail")
    except Exception:
        return None


async def create_guard_battle(law_encounter_id: int, character_id: int, guard_npc_id: int) -> int:
    """Start the guard fight; returns ``battle_id``. Raises :class:`BattleServiceError`."""
    url = f"{_base_url()}/battles/internal/guard"
    payload = {"law_encounter_id": int(law_encounter_id), "character_id": int(character_id),
               "guard_npc_id": int(guard_npc_id)}
    try:
        async with httpx.AsyncClient(timeout=BATTLE_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=_internal_headers())
    except Exception as e:
        logger.error("guard battle create failed (encounter %s): %s", law_encounter_id, e)
        raise BattleServiceError("battle-service unavailable") from e
    if response.status_code >= 400:
        logger.warning("guard battle create refused (encounter %s): %s %s", law_encounter_id,
                       response.status_code, response.text[:200])
        raise BattleServiceError("guard battle refused", response.status_code, _detail(response))
    try:
        return int(response.json()["battle_id"])
    except Exception as e:
        raise BattleServiceError("bad battle-service answer", response.status_code) from e


def get_battle_result(battle_id: int):
    """``GET /battles/internal/{id}/result`` -> the dict, or :data:`BATTLE_NOT_FOUND` on 404.
    Raises :class:`BattleServiceError` on any other failure."""
    url = f"{_base_url()}/battles/internal/{int(battle_id)}/result"
    try:
        response = httpx.get(url, headers=_internal_headers(), timeout=BATTLE_TIMEOUT_SECONDS)
    except Exception as e:
        raise BattleServiceError("battle-service unavailable") from e
    if response.status_code == 404:
        return BATTLE_NOT_FOUND
    if response.status_code >= 400:
        raise BattleServiceError("battle result refused", response.status_code)
    try:
        return response.json() or {}
    except Exception as e:
        raise BattleServiceError("bad battle-service answer", response.status_code) from e

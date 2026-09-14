"""
Small HTTP client to locations-service (FEAT-154).

Two reads are needed by character-service:

1. ``probe_starting_point`` — validate that a location the player picked is part
   of the curated starting-point list (``GET /locations/starting-points/{id}``).
2. ``get_current_game_year`` — read the current in-game year from the public
   ``GET /locations/game-time`` endpoint (field ``computed.year``).

Both are **graceful on transport failure**: locations-service being unreachable
must never block a character request. The callers distinguish

* ``True`` / a number  — the answer is known,
* ``False``            — the answer is known and negative (404),
* ``None``             — the answer is unknown (transport/HTTP failure), skip the check.

The in-game calendar is never re-implemented here — the year always comes from
locations-service at runtime (see §3.5 of FEAT-154: no hardcoded year anywhere).
"""

import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger("character-service.locations_client")

# Keep the timeout short: these are soft, best-effort validation probes on a
# player-facing request path.
LOCATIONS_TIMEOUT_SECONDS = 5.0


def _base_url() -> str:
    return settings.LOCATIONS_SERVICE_URL.rstrip("/")


async def probe_starting_point(location_id: int) -> Optional[bool]:
    """
    Check that ``location_id`` is a curated starting point.

    :return: ``True`` — it is; ``False`` — it is not (404);
             ``None`` — locations-service could not answer (check is skipped).
    """
    url = f"{_base_url()}/locations/starting-points/{location_id}"
    try:
        async with httpx.AsyncClient(timeout=LOCATIONS_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.RequestError as e:
        logger.warning(f"locations-service недоступен при проверке стартовой точки {location_id}: {e}")
        return None
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Не удалось проверить стартовую точку {location_id}: {e}")
        return None

    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    logger.warning(
        f"Неожиданный ответ locations-service при проверке стартовой точки "
        f"{location_id}: {response.status_code}"
    )
    return None


async def get_current_game_year() -> Optional[int]:
    """
    Read the current in-game year from ``GET /locations/game-time``.

    :return: the year from ``computed.year``, or ``None`` when it is unavailable
             (locations-service down, or an older build without the block).
    """
    url = f"{_base_url()}/locations/game-time"
    try:
        async with httpx.AsyncClient(timeout=LOCATIONS_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.RequestError as e:
        logger.warning(f"locations-service недоступен при чтении игрового времени: {e}")
        return None
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Не удалось прочитать игровое время: {e}")
        return None

    if response.status_code != 200:
        logger.warning(f"locations-service вернул {response.status_code} на /locations/game-time")
        return None

    try:
        computed = (response.json() or {}).get("computed") or {}
        year = computed.get("year")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Некорректный ответ /locations/game-time: {e}")
        return None

    if isinstance(year, int):
        return year
    logger.warning("Ответ /locations/game-time не содержит computed.year")
    return None


async def get_default_starting_point_id() -> Optional[int]:
    """
    Read the first curated starting point from ``GET /locations/starting-points``.

    The list is already ordered by ``sort_order`` on the locations-service side,
    so "the default" is simply its first element. Used by step 2 of the approve
    fallback chain (FEAT-154 §3.6).

    :return: the id of the default starting point, or ``None`` when it is
             unknown (locations-service unreachable, non-200, empty list or a
             malformed payload). ``None`` sends the caller to step 3, which
             leaves ``current_location_id`` NULL — never an error.
    """
    url = f"{_base_url()}/locations/starting-points"
    try:
        async with httpx.AsyncClient(timeout=LOCATIONS_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.RequestError as e:
        logger.warning(f"locations-service недоступен при чтении списка стартовых точек: {e}")
        return None
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Не удалось прочитать список стартовых точек: {e}")
        return None

    if response.status_code != 200:
        logger.warning(
            f"locations-service вернул {response.status_code} на /locations/starting-points"
        )
        return None

    try:
        points = response.json() or []
        if not points:
            logger.warning("Список стартовых точек пуст — стартовая локация не будет назначена")
            return None
        point_id = points[0].get("id")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Некорректный ответ /locations/starting-points: {e}")
        return None

    if isinstance(point_id, int):
        return point_id
    logger.warning("Первая стартовая точка не содержит корректного id")
    return None


# ============================================================
# FEAT-162 — internal calls to locations-service
# ============================================================
# Unlike the probes above, these are *state-changing* internal calls guarded by
# `X-Internal-Token` (see `auth_http.verify_internal_token` for the receiving
# side of the same contract).
#
# Two flavours on purpose:
#   * the async ones (`cancel_gathering` / `notify_character_left_location`)
#     raise `LocationsServiceError` so the admin teleport can abort BEFORE it
#     writes anything — the invariant of FEAT-162 §3.3;
#   * the sync one (`notify_character_left_location_sync`) never raises, for
#     `crud.execute_teleport` (§3.5).

INTERNAL_TIMEOUT_SECONDS = 5.0


class LocationsServiceError(Exception):
    """locations-service could not perform a *mandatory* cleanup step."""


def _internal_headers() -> dict:
    # Imported lazily: auth_http reads the env var at import time and tests
    # override the module attribute there.
    import auth_http
    return {"X-Internal-Token": auth_http.INTERNAL_SERVICE_TOKEN}


async def cancel_gathering(character_id: int, reason: Optional[str] = None) -> dict:
    """`POST /locations/internal/cancel-gathering` — idempotent.

    :raises LocationsServiceError: transport failure or non-2xx answer.
    """
    url = f"{_base_url()}/locations/internal/cancel-gathering"
    payload = {"character_id": character_id}
    if reason is not None:
        payload["reason"] = reason
    try:
        async with httpx.AsyncClient(timeout=INTERNAL_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=_internal_headers())
    except Exception as e:
        logger.error(f"cancel-gathering недоступен для персонажа {character_id}: {e}")
        raise LocationsServiceError("отмена сбора ресурсов") from e

    if response.status_code >= 400:
        logger.error(
            f"cancel-gathering вернул {response.status_code} для персонажа {character_id}"
        )
        raise LocationsServiceError("отмена сбора ресурсов")
    try:
        return response.json() or {}
    except Exception:  # pragma: no cover - defensive
        return {}


async def notify_character_left_location(
    character_id: int, from_location_id: Optional[int]
) -> dict:
    """`POST /locations/internal/character-left-location` — idempotent.

    Expires the character's open action gates and pending gate requests in the
    location being left, then prunes a forming party (best-effort on the
    locations-service side).

    :raises LocationsServiceError: transport failure or non-2xx answer. The
        caller MUST abort the move — a moved character still holding live gates
        in the old location is exactly the bug this feature exists to prevent.
    """
    url = f"{_base_url()}/locations/internal/character-left-location"
    payload = {"character_id": character_id, "from_location_id": from_location_id}
    try:
        async with httpx.AsyncClient(timeout=INTERNAL_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=_internal_headers())
    except Exception as e:
        logger.error(f"character-left-location недоступен для персонажа {character_id}: {e}")
        raise LocationsServiceError("гашение намерений в покидаемой локации") from e

    if response.status_code >= 400:
        logger.error(
            f"character-left-location вернул {response.status_code} "
            f"для персонажа {character_id}"
        )
        raise LocationsServiceError("гашение намерений в покидаемой локации")
    try:
        return response.json() or {}
    except Exception:  # pragma: no cover - defensive
        return {}


def notify_character_left_location_sync(
    character_id: int, from_location_id: Optional[int]
) -> bool:
    """Best-effort sync twin of :func:`notify_character_left_location`.

    Used by `crud.execute_teleport`, which is sync, has already charged the
    player gold and must not hold its `with_for_update` lock across an HTTP
    call — so the cleanup runs AFTER the commit and can only log on failure.

    Trade-off, recorded deliberately (FEAT-162 §3.5): this leaves a window of
    milliseconds in which the character is already in the new location while
    the gates in the old one are still live. That is strictly better than
    today's behaviour, where those gates leak permanently. The admin teleport
    (`POST /characters/admin/{id}/move`) does not take this trade-off: there
    the cleanup is blocking and aborts the move on failure.

    :return: True when the cleanup was acknowledged, False otherwise.
    """
    import requests

    url = f"{_base_url()}/locations/internal/character-left-location"
    try:
        response = requests.post(
            url,
            json={"character_id": character_id, "from_location_id": from_location_id},
            headers=_internal_headers(),
            timeout=INTERNAL_TIMEOUT_SECONDS,
        )
    except Exception as e:
        logger.warning(
            f"Не удалось погасить намерения персонажа {character_id} "
            f"в локации {from_location_id} после телепорта: {e}"
        )
        return False

    if response.status_code >= 400:
        logger.warning(
            f"Гашение намерений после телепорта персонажа {character_id} "
            f"вернуло {response.status_code}"
        )
        return False
    return True

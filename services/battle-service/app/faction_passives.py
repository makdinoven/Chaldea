"""FEAT-207: faction rank passives in the battle snapshot (features/FEAT-207 §3.5).

character-service sums every rank passive of the character's ACTIVE memberships (``{key: int}``, keys are battle
attributes only); here they are folded into the snapshot attributes at battle start, so they hold for the whole
battle like initiative. A primary stat also moves its derived stats exactly like character-attributes-service does
(``buffs._DERIVED_PER_POINT``, the FEAT-195 caps through ``stat_caps.effective_delta``). Nothing is written to
``character_attributes``. Soft-fail: character-service down -> the participant fights without faction passives.
"""

import logging
import os
from typing import Dict, Mapping

import httpx

from buffs import _DERIVED_PER_POINT
from config import settings
from stat_caps import effective_delta

logger = logging.getLogger(__name__)

LOOKUP_TIMEOUT_S = 3.0


def _internal_headers() -> dict:
    # read at call time, like main._internal_token_headers
    return {"X-Internal-Token": os.environ.get("INTERNAL_SERVICE_TOKEN", "")}


async def fetch_faction_passives(character_id: int) -> Dict[str, int]:
    """GET character-service /characters/internal/factions/{cid}/passive-modifiers. {} on any failure."""
    url = f"{settings.CHARACTER_SERVICE_URL}/characters/internal/factions/{int(character_id)}/passive-modifiers"
    try:
        async with httpx.AsyncClient(timeout=LOOKUP_TIMEOUT_S) as client:
            resp = await client.get(url, headers=_internal_headers())
        if resp.status_code != 200:
            logger.warning("faction passives of character %s: HTTP %s", character_id, resp.status_code)
            return {}
        mods = resp.json().get("modifiers") or {}
    except (httpx.HTTPError, ValueError, AttributeError) as e:
        logger.warning("faction passives of character %s not loaded: %s", character_id, e)
        return {}
    out: Dict[str, int] = {}
    if isinstance(mods, dict):
        for key, value in mods.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value:
                out[str(key)] = value
    return out


def apply(attributes: dict, modifiers: Mapping[str, float]) -> dict:
    """Fold the passive into ``attributes`` (mutated and returned). Every key is added; a primary also adds its
    derived stats by the capped worth of the change (from the stored total, which already includes equipment)."""
    if not modifiers or not isinstance(attributes, dict):
        return attributes
    for key, value in modifiers.items():
        before = attributes.get(key) or 0
        attributes[key] = before + value
        derived = _DERIVED_PER_POINT.get(key)
        if derived:
            worth = effective_delta(before, before + value)
            for dkey, per_point in derived.items():
                attributes[dkey] = (attributes.get(dkey) or 0) + worth * per_point
    return attributes

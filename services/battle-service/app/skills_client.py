# skills_client.py — FEAT-125 (perk system) rewrite.
#
# The rank era is gone. This client now talks to the new skills-service
# contract:
#   - GET /skills/{skill_id}/resolved?character_id=...  (server-authoritative
#     merged base + picked perks). Returns `ResolvedSkillRead` (see
#     `docs/services/skills-service.md`). Field names for `damage_entries`
#     and `effects` are byte-compatible with the old `SkillRankDamageRead` /
#     `SkillRankEffectRead` — battle math is unchanged.
#   - GET /skills/characters/{character_id}/skills — list of character's
#     owned skills with the new flat `CharacterSkillRead` shape.
#
#   - GET /skills/internal/characters/{character_id}/subclass (FEAT-188) —
#     character's subclass + passive, read once per participant at battle
#     start.
#
# Header styles (the file deliberately uses both):
#   - the public skills routes above accept the INTERNAL_SERVICE_TOKEN in the
#     `Authorization: Bearer` position (`_service_headers()`, skills-service
#     `allow_jwt_or_service_token`);
#   - `/skills/internal/*` routes use `verify_internal_token`, which accepts
#     ONLY `X-Internal-Token` (`_internal_headers()`) and rejects Bearer;
#   - `get_item` (inventory-service internal route) also uses X-Internal-Token.
#
# All internal service-to-service calls carry the INTERNAL_SERVICE_TOKEN. The token is read from the env at import
# time; if missing a warning is logged so the service stays bootable for
# local tests (DevSecOps will wire the env var in docker-compose.*).
import logging
import os
from typing import Any

import httpx

from config import settings

logger = logging.getLogger("battle-service.skills_client")

BASE = settings.SKILLS_URL.rstrip("/")
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")

if not INTERNAL_SERVICE_TOKEN:
    logger.warning(
        "INTERNAL_SERVICE_TOKEN is not set — skills-service calls will be "
        "unauthenticated. DevSecOps must wire it in docker-compose."
    )


def _service_headers() -> dict:
    if INTERNAL_SERVICE_TOKEN:
        return {"Authorization": f"Bearer {INTERNAL_SERVICE_TOKEN}"}
    return {}


def _internal_headers() -> dict:
    """Header for skills-service `/skills/internal/*` routes (FEAT-188).

    Those routes use `verify_internal_token`, which accepts ONLY the
    `X-Internal-Token` header and rejects the Bearer position with 401 —
    so `_service_headers()` must not be used for them.
    """
    return {"X-Internal-Token": INTERNAL_SERVICE_TOKEN}


# Timeout for the per-participant subclass lookup at battle start: a hanging
# skills-service must not stall the battle start for long (the lookup is
# soft-fail — the participant just fights without a passive).
SUBCLASS_LOOKUP_TIMEOUT_S = 3.0


# -----------------------------------------------------------
# 1. Resolved skill (merged base + picked perks, server-authoritative)
# -----------------------------------------------------------
async def get_resolved_skill(skill_id: int, character_id: int) -> dict:
    """
    Fetch a resolved skill for a given character.

    Returns a dict with (at least) these keys:
      - skill_id, character_id, level, selected_perk_ids
      - skill_type
      - cost_energy, cost_mana, cooldown, level_requirement
      - damage_entries: list of damage dicts (same shape as old rank damage)
      - effects: list of effect dicts (same shape as old rank effects)

    `skill_type` is normalized to lowercase for downstream consumers.
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/skills/{skill_id}/resolved",
            params={"character_id": character_id},
            headers=_service_headers(),
        )
        r.raise_for_status()
        data = r.json()

    if isinstance(data.get("skill_type"), str):
        data["skill_type"] = data["skill_type"].lower()
    return data


# -----------------------------------------------------------
# 2. Ownership check
# -----------------------------------------------------------
async def character_has_skill(character_id: int, skill_id: int) -> bool:
    """Return True if the character owns `skill_id`."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/skills/characters/{character_id}/skills",
            headers=_service_headers(),
        )
        r.raise_for_status()
        owned = {row.get("skill_id") for row in r.json() if row.get("skill_id") is not None}
    return skill_id in owned


# -----------------------------------------------------------
# 3. Character's owned skills (list)
# -----------------------------------------------------------
async def character_skills(character_id: int) -> list[dict]:
    """
    Return the list of character skills in the new flat shape:
      {character_skill_id, skill_id, level, free_perk_points,
       selected_perk_ids, skill: {id, name, skill_type, skill_image}}

    For compatibility with battle snapshot consumers (who access
    `skill_type` directly on each entry), we denormalize `skill_type`
    and `skill_image` onto the top-level dict and normalize `skill_type`
    to lowercase.
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/skills/characters/{character_id}/skills",
            headers=_service_headers(),
        )
        r.raise_for_status()
        rows = r.json()

    results: list[dict] = []
    for row in rows:
        nested = row.get("skill") or {}
        skill_type = row.get("skill_type") or nested.get("skill_type") or ""
        if isinstance(skill_type, str):
            skill_type = skill_type.lower()
        entry = dict(row)
        entry["skill_type"] = skill_type
        if nested.get("skill_image") and not entry.get("skill_image"):
            entry["skill_image"] = nested.get("skill_image")
        if nested.get("name") and not entry.get("skill_name"):
            entry["skill_name"] = nested.get("name")
        # Strategy and autobattle code paths index by `id` — provide an alias
        # that maps to the stable skill_id (battle engine also uses skill_id
        # now as the cooldown key).
        entry.setdefault("id", entry.get("skill_id"))
        results.append(entry)
    return results


# -----------------------------------------------------------
# 3b. Character subclass + passive (FEAT-188)
# -----------------------------------------------------------
async def get_character_subclass(character_id: int) -> dict:
    """Subclass and passive of a character, from skills-service.

    Returns `CharacterSubclassRead`:
      {character_id, is_npc, subclass_key, subclass_name,
       passive: {key, name, description, implemented} | None}
    `subclass_key`/`passive` are None when no subclass is chosen yet.
    Raises on HTTP / network errors — the caller treats that as "no passive".
    """
    async with httpx.AsyncClient(timeout=SUBCLASS_LOOKUP_TIMEOUT_S) as client:
        r = await client.get(
            f"{BASE}/skills/internal/characters/{character_id}/subclass",
            headers=_internal_headers(),
        )
        r.raise_for_status()
        return r.json()


# -----------------------------------------------------------
# 4. Inventory item lookup (unchanged)
# -----------------------------------------------------------
async def get_item(item_id: int) -> dict:
    """Полный шаблон предмета (FEAT-171 I3i).

    Публичный `/inventory/items/{id}` отдаёт тонкую карточку без цифр, поэтому
    читаем внутренний двойник с X-Internal-Token (заголовок другой, чем у
    вызовов в skills-service выше: там токен идёт в позиции Bearer).
    """
    if not item_id or item_id <= 0:
        raise ValueError("item_id must be > 0")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.INVENTORY_URL}/inventory/internal/items/{item_id}",
            headers={"X-Internal-Token": os.environ.get("INTERNAL_SERVICE_TOKEN", "")},
        )
        r.raise_for_status()
        return r.json()

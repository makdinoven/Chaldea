"""Mirror of features/FEAT-171 §3.1. Keep the five copies byte-identical in behaviour.

Async twin for skills-service (AsyncSession + `await db.execute`).

There are FIVE copies — grep for all of them before editing one:

  services/character-service/app/visibility.py             (sync)
  services/character-attributes-service/app/visibility.py  (sync)
  services/inventory-service/app/visibility.py             (sync)
  services/skills-service/app/visibility.py                (async twin)
  services/locations-service/app/visibility.py             (async twin)

Consistency is enforced by the parametrised QA matrix
(`app/tests/test_feat171_predicate_parity.py`, one per service, FEAT-171 task 20),
not by imports: the repo has no shared Python library and inventing one inside a
security feature would be exactly the "hidden refactor along the way" CLAUDE.md
§5 forbids.
"""

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth_http import UserRead

CHARACTER_PRIVATE_PERMISSION = "characters:read"
PRIVILEGED_ROLES = ("admin", "moderator")


async def can_view_private(
    db: AsyncSession, character_id: int, user: Optional[UserRead]
) -> bool:
    """May `user` (or nobody, if None) see the PRIVATE layer of this character?

    404 if the character does not exist  — §1: never reveal existence.
    True  for an NPC/mob (`user_id IS NULL`) — Q6: an NPC has no private layer.
    True  for the owner.
    True  for admin/moderator that also holds `characters:read`.
    False otherwise (guest, or another player).
    """
    result = await db.execute(
        text("SELECT user_id FROM characters WHERE id = :cid"), {"cid": character_id}
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    owner_id = row[0]
    if owner_id is None:                                   # NPC / mob — public (Q6)
        return True
    if user is None:
        return False
    if user.id == owner_id:
        return True
    return (
        user.role in PRIVILEGED_ROLES
        and CHARACTER_PRIVATE_PERMISSION in (user.permissions or [])
    )


async def require_private_access(
    db: AsyncSession, character_id: int, user: Optional[UserRead]
) -> None:
    """Hard gate wrapper: 404 for a missing character, 403 for a stranger."""
    if not await can_view_private(db, character_id, user):
        raise HTTPException(
            status_code=403, detail="Эти данные доступны только владельцу персонажа"
        )

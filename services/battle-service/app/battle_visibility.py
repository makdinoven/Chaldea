"""Who may read the turn-by-turn log of a battle.

FEAT-171 §5 issue #2. `GET /battles/battles/{id}/logs` and
`.../logs/{turn_number}` had **no** auth dependency at all and are proxied by
nginx, so a guest could walk sequential `battle_id`s and read
`{"event": "pve_rewards", "xp": 30, "gold": 5}` and
`{"event": "skill_use", "skill_id": 9003}` — exactly the XP, gold and skills
§1 declares private.

The rule mirrors what battle-service already enforces on the two neighbouring
reads, so the log panel stays in step with the state it annotates:

* **participant** — the viewer owns a character in `battle_participants`
  (same notion of "participant" as `GET /{battle_id}/state`); works for
  finished battles too, so a player keeps their own battle history.
* **co-located spectator** — the battle is still active and the viewer has a
  character standing in `battles.location_id`; this is verbatim the rule of
  `GET /{battle_id}/spectate` (`main.py`), which the spectator UI uses to load
  the very state these logs describe. Narrowing the logs without narrowing
  `/spectate` would only break the spectator log panel while leaking the
  richer payload anyway — see the open `docs/ISSUES.md` entry about the
  spectator snapshot; if that rule is ever tightened, tighten this one with it.
* **admin / moderator** holding `characters:read` — the same privileged branch
  as `can_view_private` in the four FEAT-171 services (role alone is **not**
  enough).

Everyone else gets 403. A missing battle gets 404 **before** the 403, matching
the 404-before-403 discipline of the rest of the feature.
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth_http import UserRead

# Mirror of visibility.CHARACTER_PRIVATE_PERMISSION in the four FEAT-171
# services. Reusing the existing permission — no migration, no new RBAC row.
BATTLE_PRIVATE_PERMISSION = "characters:read"
PRIVILEGED_ROLES = ("admin", "moderator")

ACTIVE_BATTLE_STATUSES = ("pending", "in_progress")

FORBIDDEN_DETAIL = "Логи боя доступны только участникам и наблюдателям"
NOT_FOUND_DETAIL = "Бой не найден"


def _is_privileged(user: Optional[UserRead]) -> bool:
    return (
        user is not None
        and user.role in PRIVILEGED_ROLES
        and BATTLE_PRIVATE_PERMISSION in (user.permissions or [])
    )


async def can_view_battle_logs(
    db: AsyncSession, battle_id: int, user: UserRead
) -> bool:
    """May `user` read the logs of this battle?

    Raises 404 when the battle does not exist. Never raises 403 — the caller
    decides, so the predicate stays usable from other call sites.
    """
    row = (
        await db.execute(
            text("SELECT location_id, status FROM battles WHERE id = :bid"),
            {"bid": battle_id},
        )
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)

    if _is_privileged(user):
        return True

    location_id, battle_status = row[0], row[1]
    # SQLAlchemy may hand back the Enum member or the raw string, depending on
    # how the row was loaded; normalise before comparing.
    status_value = getattr(battle_status, "value", battle_status)

    participant = (
        await db.execute(
            text(
                "SELECT 1 FROM battle_participants bp "
                "JOIN characters c ON c.id = bp.character_id "
                "WHERE bp.battle_id = :bid AND c.user_id = :uid LIMIT 1"
            ),
            {"bid": battle_id, "uid": user.id},
        )
    ).fetchone()
    if participant is not None:
        return True

    if location_id is None or status_value not in ACTIVE_BATTLE_STATUSES:
        return False

    spectator = (
        await db.execute(
            text(
                "SELECT 1 FROM characters "
                "WHERE user_id = :uid AND current_location_id = :loc LIMIT 1"
            ),
            {"uid": user.id, "loc": location_id},
        )
    ).fetchone()
    return spectator is not None


async def require_battle_log_access(
    db: AsyncSession, battle_id: int, user: UserRead
) -> None:
    """404 for a missing battle, 403 for an outsider, otherwise return."""
    if not await can_view_battle_logs(db, battle_id, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_DETAIL
        )

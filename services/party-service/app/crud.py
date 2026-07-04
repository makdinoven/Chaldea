from typing import Optional

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session

import models


# ---------------------------------------------------------------------------
# Character info — read straight from the shared `characters` table (owned by
# character-service, but all services share one MySQL). Matches how
# battle-service resolves ownership/location for its party lobby.
# ---------------------------------------------------------------------------
def get_character_info(db: Session, character_id: int) -> Optional[dict]:
    row = db.execute(
        text(
            "SELECT id, user_id, current_location_id, name, avatar "
            "FROM characters WHERE id = :id"
        ),
        {"id": character_id},
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "current_location_id": row[2],
        "name": row[3],
        "avatar": row[4],
    }


def get_characters_map(db: Session, character_ids: list) -> dict:
    if not character_ids:
        return {}
    rows = db.execute(
        text(
            "SELECT id, user_id, current_location_id, name, avatar "
            "FROM characters WHERE id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": list(character_ids)},
    ).fetchall()
    return {
        r[0]: {
            "id": r[0],
            "user_id": r[1],
            "current_location_id": r[2],
            "name": r[3],
            "avatar": r[4],
        }
        for r in rows
    }


# ---------------------------------------------------------------------------
# Party queries
# ---------------------------------------------------------------------------
def get_accepted_membership(db: Session, character_id: int) -> Optional[models.PartyMember]:
    """The single party a character actually belongs to (accepted)."""
    return (
        db.query(models.PartyMember)
        .filter(
            models.PartyMember.character_id == character_id,
            models.PartyMember.status == models.MemberStatus.accepted,
        )
        .first()
    )


def get_party(db: Session, party_id: int) -> Optional[models.Party]:
    return db.query(models.Party).filter(models.Party.id == party_id).first()


def get_members(db: Session, party_id: int) -> list:
    return (
        db.query(models.PartyMember)
        .filter(models.PartyMember.party_id == party_id)
        .order_by(models.PartyMember.is_leader.desc(), models.PartyMember.joined_at.asc())
        .all()
    )


def count_committed_members(db: Session, party_id: int) -> int:
    """Members that occupy a slot: the leader + accepted + still-pending invites."""
    return (
        db.query(models.PartyMember)
        .filter(models.PartyMember.party_id == party_id)
        .count()
    )


def build_party_out(db: Session, party: models.Party) -> dict:
    members = get_members(db, party.id)
    info = get_characters_map(db, [m.character_id for m in members])
    member_dicts = []
    for m in members:
        ci = info.get(m.character_id, {})
        member_dicts.append({
            "character_id": m.character_id,
            "user_id": m.user_id,
            "name": ci.get("name"),
            "avatar": ci.get("avatar"),
            "is_leader": m.is_leader,
            "status": m.status.value if hasattr(m.status, "value") else str(m.status),
            "current_location_id": ci.get("current_location_id"),
        })
    return {
        "id": party.id,
        "name": party.name,
        "avatar": party.avatar,
        "leader_character_id": party.leader_character_id,
        "members": member_dicts,
    }

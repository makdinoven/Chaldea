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
            "SELECT c.id, c.user_id, c.current_location_id, c.name, c.avatar, "
            "c.level, cl.name AS class_name "
            "FROM characters c LEFT JOIN classes cl ON cl.id_class = c.id_class "
            "WHERE c.id = :id"
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
        "level": row[5],
        "class_name": row[6],
    }


def get_characters_map(db: Session, character_ids: list) -> dict:
    if not character_ids:
        return {}
    rows = db.execute(
        text(
            "SELECT c.id, c.user_id, c.current_location_id, c.name, c.avatar, "
            "c.level, cl.name AS class_name "
            "FROM characters c LEFT JOIN classes cl ON cl.id_class = c.id_class "
            "WHERE c.id IN :ids"
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
            "level": r[5],
            "class_name": r[6],
        }
        for r in rows
    }


def get_attributes_map(db: Session, character_ids: list) -> dict:
    """Batched read of the shared `character_attributes` table (FEAT-151).

    A character may legitimately lack an attributes row (attributes are created
    on approval) — such members simply get no entry here and the enrichment
    fields stay null.
    """
    if not character_ids:
        return {}
    rows = db.execute(
        text(
            "SELECT character_id, current_health, max_health, "
            "current_mana, max_mana "
            "FROM character_attributes WHERE character_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": list(character_ids)},
    ).fetchall()
    return {
        r[0]: {
            "current_health": r[1],
            "max_health": r[2],
            "current_mana": r[3],
            "max_mana": r[4],
        }
        for r in rows
    }


# ---------------------------------------------------------------------------
# Party queries
# ---------------------------------------------------------------------------
def get_character_ids_at_location(db: Session, location_id: int) -> list:
    """Player character ids currently on a location (excludes NPCs/mobs)."""
    rows = db.execute(
        text(
            "SELECT id FROM characters "
            "WHERE current_location_id = :loc AND (is_npc = 0 OR is_npc IS NULL)"
        ),
        {"loc": location_id},
    ).fetchall()
    return [r[0] for r in rows]


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
    member_ids = [m.character_id for m in members]
    info = get_characters_map(db, member_ids)
    attrs = get_attributes_map(db, member_ids)
    member_dicts = []
    for m in members:
        ci = info.get(m.character_id, {})
        ai = attrs.get(m.character_id, {})
        member_dicts.append({
            "character_id": m.character_id,
            "user_id": m.user_id,
            "name": ci.get("name"),
            "avatar": ci.get("avatar"),
            "is_leader": m.is_leader,
            "status": m.status.value if hasattr(m.status, "value") else str(m.status),
            "current_location_id": ci.get("current_location_id"),
            "level": ci.get("level"),
            "class_name": ci.get("class_name"),
            "current_health": ai.get("current_health"),
            "max_health": ai.get("max_health"),
            "current_mana": ai.get("current_mana"),
            "max_mana": ai.get("max_mana"),
        })
    return {
        "id": party.id,
        "name": party.name,
        "avatar": party.avatar,
        "leader_character_id": party.leader_character_id,
        "members": member_dicts,
    }

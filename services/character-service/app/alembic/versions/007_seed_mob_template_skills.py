"""Seed mob_template_skills and fix existing mobs with no skills.

For each mob template, find rank_number=1 skill_ranks whose parent skill
matches the template's class (via skills.class_limitations) and insert them
into mob_template_skills. Then retroactively assign those skills to already-
spawned mob characters that have zero entries in character_skills.

Revision ID: 007_seed_mob_template_skills
Revises: 006_seed_mob_templates
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa

revision = '007_seed_mob_template_skills'
down_revision = '006_seed_mob_templates'
branch_labels = None
depends_on = None


def _find_skill_rank_ids_for_class(conn, id_class: int) -> list[int]:
    """Return skill_rank ids (rank_number=1) available for the given class.

    A skill matches if:
      - skills.class_limitations IS NULL  (universal skill), OR
      - skills.class_limitations contains the class id
        (FIND_IN_SET handles comma-separated strings like "1,2,3")
    We pick the first rank (rank_number=1) of each matching skill.
    """
    rows = conn.execute(
        sa.text(
            "SELECT sr.id, s.skill_type "
            "FROM skill_ranks sr "
            "JOIN skills s ON sr.skill_id = s.id "
            "WHERE sr.rank_number = 1 "
            "  AND (s.class_limitations IS NULL OR FIND_IN_SET(:cls, s.class_limitations) > 0)"
        ),
        {"cls": str(id_class)},
    ).fetchall()
    return rows


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Get all mob templates
    templates = conn.execute(
        sa.text("SELECT id, id_class FROM mob_templates")
    ).fetchall()

    for tmpl_id, id_class in templates:
        # Find matching skill_ranks for this class
        skill_rows = _find_skill_rank_ids_for_class(conn, id_class)

        if not skill_rows:
            continue

        # Group by skill_type to ensure we pick at least one of each type
        by_type: dict[str, list[int]] = {}
        for rank_id, skill_type in skill_rows:
            by_type.setdefault(skill_type, []).append(rank_id)

        # Collect skill_rank_ids: one per type (Attack, Defense, Support)
        # plus any remaining types
        selected_ids: list[int] = []
        for stype in ("Attack", "Defense", "Support"):
            candidates = by_type.get(stype, [])
            if candidates:
                selected_ids.append(candidates[0])

        # If we still have other types, include them too
        for stype, candidates in by_type.items():
            if stype not in ("Attack", "Defense", "Support"):
                selected_ids.append(candidates[0])

        # Insert into mob_template_skills (idempotent: skip duplicates)
        for rank_id in selected_ids:
            exists = conn.execute(
                sa.text(
                    "SELECT 1 FROM mob_template_skills "
                    "WHERE mob_template_id = :tid AND skill_rank_id = :rid"
                ),
                {"tid": tmpl_id, "rid": rank_id},
            ).fetchone()
            if not exists:
                conn.execute(
                    sa.text(
                        "INSERT INTO mob_template_skills (mob_template_id, skill_rank_id) "
                        "VALUES (:tid, :rid)"
                    ),
                    {"tid": tmpl_id, "rid": rank_id},
                )

    # 2. Fix existing spawned mobs that have zero character_skills
    # Find mob characters (via active_mobs) with no skills
    mobs_without_skills = conn.execute(
        sa.text(
            "SELECT am.character_id, am.mob_template_id "
            "FROM active_mobs am "
            "JOIN characters c ON c.id = am.character_id "
            "WHERE c.is_npc = 1 "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM character_skills cs WHERE cs.character_id = am.character_id"
            "  )"
        )
    ).fetchall()

    for char_id, tmpl_id in mobs_without_skills:
        # Get this template's skills from mob_template_skills (just populated above)
        template_skills = conn.execute(
            sa.text(
                "SELECT skill_rank_id FROM mob_template_skills "
                "WHERE mob_template_id = :tid"
            ),
            {"tid": tmpl_id},
        ).fetchall()

        for (rank_id,) in template_skills:
            # Idempotent: skip if already exists
            exists = conn.execute(
                sa.text(
                    "SELECT 1 FROM character_skills "
                    "WHERE character_id = :cid AND skill_rank_id = :rid"
                ),
                {"cid": char_id, "rid": rank_id},
            ).fetchone()
            if not exists:
                conn.execute(
                    sa.text(
                        "INSERT INTO character_skills (character_id, skill_rank_id) "
                        "VALUES (:cid, :rid)"
                    ),
                    {"cid": char_id, "rid": rank_id},
                )


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Remove character_skills for mob characters that were populated by this migration.
    # We identify mob characters via active_mobs + is_npc flag.
    conn.execute(
        sa.text(
            "DELETE cs FROM character_skills cs "
            "JOIN active_mobs am ON am.character_id = cs.character_id "
            "JOIN characters c ON c.id = cs.character_id "
            "WHERE c.is_npc = 1"
        )
    )

    # 2. Remove all rows from mob_template_skills
    conn.execute(sa.text("DELETE FROM mob_template_skills"))

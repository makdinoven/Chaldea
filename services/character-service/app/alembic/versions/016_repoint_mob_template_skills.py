"""Repoint mob_template_skills from skill_rank_id to skill_id (FEAT-125).

Revision ID: 016_repoint_mob_template_skills
Revises: 015_teleport_cooldown

This migration is the second half of the FEAT-125 rank->perk transition.
skills-service migration `003_perk_system.py` is responsible for the
cross-table backfill of `mob_template_skills.skill_id` while `skill_ranks`
still exists. This migration only:

1. Ensures the `skill_id` column is present (defensive add if missing).
2. If the column exists but is all-NULL, short-polls up to 30 seconds for
   the skills-service migration to populate it (handles Compose race
   condition where both containers start at once — Compose waits for
   container start, not for Alembic completion).
3. Drops the old `skill_rank_id` FK + column.
4. Promotes `skill_id` to NOT NULL with an FK to `skills.id` and recreates
   the UNIQUE constraint on `(mob_template_id, skill_id)`.

All steps guarded with `_has_column` / inspector introspection so the
migration is idempotent and re-runnable.
"""
import time

from alembic import op
import sqlalchemy as sa


revision = "016_repoint_mob_template_skills"
down_revision = "015_teleport_cooldown"
branch_labels = None
depends_on = None


TABLE = "mob_template_skills"
OLD_COL = "skill_rank_id"
NEW_COL = "skill_id"
OLD_UQ = "uq_mob_template_skill"


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _fk_name_for_column(inspector, table: str, column: str) -> str | None:
    for fk in inspector.get_foreign_keys(table):
        if column in (fk.get("constrained_columns") or []):
            return fk.get("name")
    return None


def _unique_name_on_columns(inspector, table: str, columns: set) -> str | None:
    for uq in inspector.get_unique_constraints(table):
        if set(uq.get("column_names") or []) == columns:
            return uq.get("name")
    return None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE not in inspector.get_table_names():
        # Fresh DB with no mobs yet (test env); nothing to do.
        return

    # 1. Ensure skill_id column exists (defensive — skills-service 003 normally adds it)
    if not _has_column(inspector, TABLE, NEW_COL):
        op.add_column(TABLE, sa.Column(NEW_COL, sa.Integer(), nullable=True))
        inspector = sa.inspect(bind)

    # 2. Short-poll for skills-service backfill (Compose race condition safeguard).
    #    If all rows have NULL skill_id but rows exist, wait up to 30s for skills-service
    #    migration 003 to fill them. Acceptable for test data (see feature file section E.3).
    deadline = time.time() + 30.0
    while time.time() < deadline:
        row = bind.execute(
            sa.text(
                f"SELECT COUNT(*) AS total, "
                f"SUM(CASE WHEN {NEW_COL} IS NULL THEN 1 ELSE 0 END) AS nulls "
                f"FROM {TABLE}"
            )
        ).fetchone()
        if row is None:
            break
        total = int(row[0] or 0)
        nulls = int(row[1] or 0)
        if total == 0 or nulls == 0:
            break
        # If we still have OLD_COL we can self-heal here from skill_ranks (if it exists too)
        if _has_column(inspector, TABLE, OLD_COL) and "skill_ranks" in inspector.get_table_names():
            bind.execute(
                sa.text(
                    f"UPDATE {TABLE} mts "
                    f"JOIN skill_ranks sr ON mts.{OLD_COL} = sr.id "
                    f"SET mts.{NEW_COL} = sr.skill_id "
                    f"WHERE mts.{NEW_COL} IS NULL"
                )
            )
            break
        time.sleep(1.0)

    # 3. Drop old UNIQUE on (mob_template_id, skill_rank_id) if still present.
    uq_name = _unique_name_on_columns(inspector, TABLE, {"mob_template_id", OLD_COL})
    if uq_name:
        op.drop_constraint(uq_name, TABLE, type_="unique")
    else:
        # Try the legacy well-known name just in case inspector missed it.
        try:
            op.drop_constraint(OLD_UQ, TABLE, type_="unique")
        except Exception:
            pass
    inspector = sa.inspect(bind)

    # 4. Drop old FK on skill_rank_id if present.
    if _has_column(inspector, TABLE, OLD_COL):
        fk_name = _fk_name_for_column(inspector, TABLE, OLD_COL)
        if fk_name:
            op.drop_constraint(fk_name, TABLE, type_="foreignkey")
        op.drop_column(TABLE, OLD_COL)
        inspector = sa.inspect(bind)

    # 5. Promote skill_id to NOT NULL (only if no nulls remain).
    null_count = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE {NEW_COL} IS NULL")
    ).scalar()
    if null_count == 0:
        op.alter_column(
            TABLE, NEW_COL,
            existing_type=sa.Integer(),
            nullable=False,
        )

    # 6. Add FK to skills.id (skip if already present).
    existing_fk = _fk_name_for_column(inspector, TABLE, NEW_COL)
    if not existing_fk:
        op.create_foreign_key(
            "fk_mts_skill_id",
            TABLE, "skills",
            [NEW_COL], ["id"],
            ondelete="CASCADE",
        )
        inspector = sa.inspect(bind)

    # 7. Recreate UNIQUE on (mob_template_id, skill_id).
    new_uq_name = _unique_name_on_columns(
        inspector, TABLE, {"mob_template_id", NEW_COL}
    )
    if not new_uq_name:
        op.create_unique_constraint(
            OLD_UQ, TABLE, ["mob_template_id", NEW_COL]
        )


def downgrade():
    # Lossy downgrade — feature file section E.4 states rollback is via DB backup.
    # We restore the old column as nullable for minimal parity.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    if not _has_column(inspector, TABLE, OLD_COL):
        op.add_column(TABLE, sa.Column(OLD_COL, sa.Integer(), nullable=True))

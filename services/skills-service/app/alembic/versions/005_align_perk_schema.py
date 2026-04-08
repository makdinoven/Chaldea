"""Align perk-system tables with models (FEAT-125 hotfix #2)

Revision ID: 005_align_perk_schema
Revises: 004_skill_base_cols
Create Date: 2026-04-08

After 003_perk_system + 004_skill_base_cols a full audit of every table
owned by skills-service models.py against the live MySQL schema was run.

Audit result (model -> DB drift):
  - character_skills.created_at  : declared in models.py:134 as
        Column(DateTime, server_default=func.now())
    MISSING in DB. Reads via the ORM trigger
        (1054, "Unknown column 'character_skills.created_at' in 'field list'").

All other perk-system tables (skills, skill_perks, skill_base_damage,
skill_base_effects, skill_perk_damage, skill_perk_effects,
character_skill_perks) match their models exactly.

This migration adds only the missing column. Idempotent via inspector.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005_align_perk_schema'
down_revision = '004_skill_base_cols'
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c['name'] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, 'character_skills', 'created_at'):
        op.add_column(
            'character_skills',
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=True,
                server_default=sa.func.now(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, 'character_skills', 'created_at'):
        op.drop_column('character_skills', 'created_at')

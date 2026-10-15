"""Add secondary_magnitude to skill effect tables

Revision ID: 010_effect_secondary_mag
Revises: 009_subrace_skill
Create Date: 2026-10-15

Adds a nullable Float `secondary_magnitude` to `skill_base_effects` and
`skill_perk_effects`. It is a generic, effect-specific second value
(e.g. Burn: dodge reduction in percentage points, while `magnitude` stays
the damage per turn). Inspector-guarded so it is safe to re-run on
partially-migrated dev DBs.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010_effect_secondary_mag'
down_revision = '009_subrace_skill'
branch_labels = None
depends_on = None


TABLES = ('skill_base_effects', 'skill_perk_effects')
COLUMN = 'secondary_magnitude'


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c['name'] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in TABLES:
        if table not in inspector.get_table_names():
            continue
        if not _has_column(inspector, table, COLUMN):
            op.add_column(table, sa.Column(COLUMN, sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in TABLES:
        if table not in inspector.get_table_names():
            continue
        if _has_column(inspector, table, COLUMN):
            op.drop_column(table, COLUMN)

"""Add item_effects.secondary_magnitude (generic second effect value).

A nullable Float column mirroring skills-service
`skill_base_effects/skill_perk_effects.secondary_magnitude`. It carries an
effect-specific second value — e.g. Burn: `magnitude` = damage per turn,
`secondary_magnitude` = dodge reduction in percentage points. Nullable
trailing column => INSTANT DDL on MySQL 8; existing rows stay NULL.

Inspector-guarded so it is safe to re-run on partially-migrated dev DBs.

Upgrade: add the column. Downgrade: drop it.

Revision ID: 026_item_effect_secondary_mag
Revises: 025_item_xp_buffs
Create Date: 2026-10-15

"""
from alembic import op
import sqlalchemy as sa

revision = '026_item_effect_secondary_mag'
down_revision = '025_item_xp_buffs'
branch_labels = None
depends_on = None

TABLE = 'item_effects'
COLUMN = 'secondary_magnitude'


def _has_column(inspector, table, column):
    if table not in inspector.get_table_names():
        return False
    return any(c['name'] == column for c in inspector.get_columns(table))


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if TABLE in inspector.get_table_names() and not _has_column(inspector, TABLE, COLUMN):
        op.add_column(TABLE, sa.Column(COLUMN, sa.Float(), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if _has_column(inspector, TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)

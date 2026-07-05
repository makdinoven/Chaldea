"""Add AoE columns to skill damage tables (FEAT-146)

Revision ID: 007_aoe_damage
Revises: 006_add_subclass_key
Create Date: 2026-07-06

Adds `aoe_shape`, `aoe_falloff`, `aoe_max_targets` to `skill_base_damage` and
`skill_perk_damage` so an attack's damage entry can hit more than the primary
target (single | splash | cleave | all | random_n). Inspector-guarded so it is
safe to re-run on partially-migrated dev DBs.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007_aoe_damage'
down_revision = '006_add_subclass_key'
branch_labels = None
depends_on = None


TABLES = ('skill_base_damage', 'skill_perk_damage')
NEW_COLUMNS = (
    ('aoe_shape', sa.String(length=12), "'single'"),
    ('aoe_falloff', sa.Integer(), '50'),
    ('aoe_max_targets', sa.Integer(), '3'),
)


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
        for col_name, col_type, default in NEW_COLUMNS:
            if not _has_column(inspector, table, col_name):
                op.add_column(
                    table,
                    sa.Column(col_name, col_type, nullable=False, server_default=default),
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in TABLES:
        if table not in inspector.get_table_names():
            continue
        for col_name, _type, _default in NEW_COLUMNS:
            if _has_column(inspector, table, col_name):
                op.drop_column(table, col_name)

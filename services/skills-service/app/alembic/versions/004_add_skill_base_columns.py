"""No-op placeholder (FEAT-125)

Revision ID: 004_skill_base_cols
Revises: 003_perk_system
Create Date: 2026-04-08

Historically this migration added `cost_energy`, `cost_mana`, `cooldown`,
`level_requirement` to the `skills` table because 003_perk_system had
forgotten them. 003 has since been amended to add these columns AND
backfill them from rank-1 of `skill_ranks` BEFORE dropping the rank tables,
so by the time we get here the columns already exist.

This file is retained (not deleted) to preserve Alembic chain integrity:
any environment that has already stamped `004_skill_base_cols` as head
must still find the revision. The body is a pure inspector-guarded no-op —
if columns somehow don't exist yet (e.g. partial 003 run on a dev DB),
we still add them with safe defaults as a belt-and-braces fallback.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004_skill_base_cols'
down_revision = '003_perk_system'
branch_labels = None
depends_on = None


NEW_COLUMNS = (
    ('cost_energy', '0'),
    ('cost_mana', '0'),
    ('cooldown', '0'),
    ('level_requirement', '1'),
)


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c['name'] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'skills' not in inspector.get_table_names():
        return

    # Fallback: if 003 did not add the columns for any reason, add them now.
    # Normally all four already exist and this loop is a pure no-op.
    for col_name, default in NEW_COLUMNS:
        if not _has_column(inspector, 'skills', col_name):
            op.add_column(
                'skills',
                sa.Column(
                    col_name,
                    sa.Integer(),
                    nullable=False,
                    server_default=default,
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'skills' not in inspector.get_table_names():
        return

    for col_name, _ in NEW_COLUMNS:
        if _has_column(inspector, 'skills', col_name):
            op.drop_column('skills', col_name)

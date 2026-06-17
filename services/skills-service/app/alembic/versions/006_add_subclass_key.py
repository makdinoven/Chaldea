"""Add subclass_key to tree_nodes and class_skill_trees

Revision ID: 006_add_subclass_key
Revises: 005_align_perk_schema
Create Date: 2026-06-17

Replaces the old fragile node->subclass linking (player-side name matching with a
"first tree" fallback) with an explicit stable key. A subclass_choice node and the
subclass tree it opens now both reference the same subclass_key (see subclasses.py
and docs/SUBCLASS-PASSIVES.md).

Idempotent via inspector so re-runs are safe.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_add_subclass_key'
down_revision = '005_align_perk_schema'
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c['name'] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, 'tree_nodes', 'subclass_key'):
        op.add_column(
            'tree_nodes',
            sa.Column('subclass_key', sa.String(length=50), nullable=True),
        )

    if not _has_column(inspector, 'class_skill_trees', 'subclass_key'):
        op.add_column(
            'class_skill_trees',
            sa.Column('subclass_key', sa.String(length=50), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, 'class_skill_trees', 'subclass_key'):
        op.drop_column('class_skill_trees', 'subclass_key')

    if _has_column(inspector, 'tree_nodes', 'subclass_key'):
        op.drop_column('tree_nodes', 'subclass_key')

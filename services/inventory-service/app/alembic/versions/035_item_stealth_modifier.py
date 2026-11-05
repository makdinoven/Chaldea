"""Item stealth modifier (FEAT-201): `items.stealth_modifier`.

Stealth is the 11th primary character stat. Items/food grant it like any other
main stat via `build_modifiers_dict` (key "stealth"); it is sharpenable and
socketable (in MAIN_STAT_FIELDS). Same shape as the other `*_modifier` columns
(nullable INT, default 0). No `item_type` ENUM change. Idempotent.

Upgrade: add the column. Downgrade: drop it.

Revision ID: 035_item_stealth_modifier
Revises: 034_item_mask
Create Date: 2026-11-04

"""
from alembic import op
import sqlalchemy as sa

revision = '035_item_stealth_modifier'
down_revision = '034_item_mask'
branch_labels = None
depends_on = None


def _has_column(table, column):
    inspector = sa.inspect(op.get_bind())
    return column in {c['name'] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column('items', 'stealth_modifier'):
        op.add_column(
            'items',
            sa.Column('stealth_modifier', sa.Integer(), nullable=True, server_default=sa.text('0')),
        )


def downgrade():
    if _has_column('items', 'stealth_modifier'):
        op.drop_column('items', 'stealth_modifier')

"""House gardens (FEAT-180, stage 6a): seed fields on items.

A resource with these set is a seed: planted in a house garden, greenhouse or
apiary (`seed_room_type`), it grows in `seed_grow_hours` into
`seed_result_quantity` of `seed_result_item_id` and gives `seed_herbalism_xp`
herbalism experience. All NULL for everything else.

Downgrade drops the columns.

Revision ID: 031_house_seeds
Revises: 030_furniture_items
Create Date: 2026-10-28

"""
from alembic import op
import sqlalchemy as sa

revision = '031_house_seeds'
down_revision = '030_furniture_items'
branch_labels = None
depends_on = None

COLUMNS = (
    ('seed_result_item_id', sa.Integer()),
    ('seed_result_quantity', sa.Integer()),
    ('seed_grow_hours', sa.Integer()),
    ('seed_room_type', sa.String(20)),
    ('seed_herbalism_xp', sa.Integer()),
)


def upgrade():
    for name, type_ in COLUMNS:
        op.add_column('items', sa.Column(name, type_, nullable=True))


def downgrade():
    for name, _ in reversed(COLUMNS):
        op.drop_column('items', name)

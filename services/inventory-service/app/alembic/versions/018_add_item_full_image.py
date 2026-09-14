"""Add items.full_image: the uncropped original picture of an item.

`items.image` keeps its meaning (the picture shown everywhere as an icon), but it
is now a square area cut from `full_image` by photo-service. Item detail windows
show `full_image`. Existing rows stay NULL and fall back to `image`.

Revision ID: 018_add_item_full_image
Revises: 017_remove_shield_slot
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa

revision = '018_add_item_full_image'
down_revision = '017_remove_shield_slot'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('items', sa.Column('full_image', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('items', 'full_image')

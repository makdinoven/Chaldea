"""Item mask (FEAT-199): `items.is_mask`.

A mask is a head item marked `is_mask` (it takes the helmet slot). While worn,
witnesses of a crime see only "an unknown in a mask"; character-service reads
the flag by SQL over `equipment_slots` + `items`. No `item_type` ENUM change.

Upgrade: add the column. Downgrade: drop it.

Revision ID: 034_item_mask
Revises: 033_auction_listing_region
Create Date: 2026-11-04

"""
from alembic import op
import sqlalchemy as sa

revision = '034_item_mask'
down_revision = '033_auction_listing_region'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('items', sa.Column('is_mask', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade():
    op.drop_column('items', 'is_mask')

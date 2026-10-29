"""Auction listing region (FEAT-181): where a listing was put up.

`location_id` / `region_id` are filled at listing creation from the seller's
auctioneer location. The 5 % commission of a sale goes to that region's
treasury (econ ledger); legacy rows stay NULL and pay the world treasury.

Revision ID: 033_auction_listing_region
Revises: 032_house_6b_items
Create Date: 2026-10-29

"""
from alembic import op
import sqlalchemy as sa

revision = '033_auction_listing_region'
down_revision = '032_house_6b_items'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('auction_listings', sa.Column('location_id', sa.BigInteger(), nullable=True))
    op.add_column('auction_listings', sa.Column('region_id', sa.BigInteger(), nullable=True))
    op.create_index('ix_auction_listings_region', 'auction_listings', ['region_id'])


def downgrade():
    op.drop_index('ix_auction_listings_region', table_name='auction_listings')
    op.drop_column('auction_listings', 'region_id')
    op.drop_column('auction_listings', 'location_id')

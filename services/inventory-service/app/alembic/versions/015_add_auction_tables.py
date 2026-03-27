"""Add auction_listings, auction_bids, auction_storage tables.

Revision ID: 015_add_auction_tables
Revises: 014_add_durability_system
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa

revision = '015_add_auction_tables'
down_revision = '014_add_durability_system'
branch_labels = None
depends_on = None


def _table_exists(conn, table: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tbl"
    ), {"tbl": table})
    return result.scalar() > 0


def upgrade() -> None:
    conn = op.get_bind()

    # 1) auction_listings
    if not _table_exists(conn, "auction_listings"):
        op.create_table(
            'auction_listings',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('seller_character_id', sa.Integer(), nullable=False),
            sa.Column('item_id', sa.Integer(), nullable=False),
            sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('enhancement_data', sa.Text(), nullable=True),
            sa.Column('start_price', sa.Integer(), nullable=False),
            sa.Column('buyout_price', sa.Integer(), nullable=True),
            sa.Column('current_bid', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('current_bidder_id', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['item_id'], ['items.id']),
        )
        op.create_index('ix_auction_listings_seller', 'auction_listings', ['seller_character_id'])
        op.create_index('ix_auction_listings_item', 'auction_listings', ['item_id'])
        op.create_index('ix_auction_listings_status', 'auction_listings', ['status'])
        op.create_index('ix_auction_listings_expires', 'auction_listings', ['expires_at'])
        op.create_index('ix_auction_listings_status_expires', 'auction_listings', ['status', 'expires_at'])

    # 2) auction_bids
    if not _table_exists(conn, "auction_bids"):
        op.create_table(
            'auction_bids',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('listing_id', sa.Integer(), nullable=False),
            sa.Column('bidder_character_id', sa.Integer(), nullable=False),
            sa.Column('amount', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['listing_id'], ['auction_listings.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_auction_bids_listing', 'auction_bids', ['listing_id'])
        op.create_index('ix_auction_bids_bidder', 'auction_bids', ['bidder_character_id'])

    # 3) auction_storage
    if not _table_exists(conn, "auction_storage"):
        op.create_table(
            'auction_storage',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('item_id', sa.Integer(), nullable=True),
            sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('enhancement_data', sa.Text(), nullable=True),
            sa.Column('gold_amount', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('source', sa.String(20), nullable=False),
            sa.Column('listing_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['item_id'], ['items.id']),
            sa.ForeignKeyConstraint(['listing_id'], ['auction_listings.id'], ondelete='SET NULL'),
        )
        op.create_index('ix_auction_storage_character', 'auction_storage', ['character_id'])


def downgrade() -> None:
    op.drop_table('auction_storage')
    op.drop_table('auction_bids')
    op.drop_table('auction_listings')

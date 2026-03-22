"""Add trade_offers and trade_offer_items tables

Revision ID: 003_add_trade_tables
Revises: 002_add_shield
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

revision = '003_add_trade_tables'
down_revision = '002_add_shield'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if trade_offers table already exists (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'trade_offers' not in existing_tables:
        op.create_table(
            'trade_offers',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('initiator_character_id', sa.Integer, nullable=False),
            sa.Column('target_character_id', sa.Integer, nullable=False),
            sa.Column('location_id', sa.Integer, nullable=False),
            sa.Column('initiator_gold', sa.Integer, nullable=False, server_default='0'),
            sa.Column('target_gold', sa.Integer, nullable=False, server_default='0'),
            sa.Column('initiator_confirmed', sa.Boolean, nullable=False, server_default='0'),
            sa.Column('target_confirmed', sa.Boolean, nullable=False, server_default='0'),
            sa.Column('status',
                       sa.Enum('pending', 'negotiating', 'completed', 'cancelled', 'expired',
                               name='trade_status_enum'),
                       nullable=False, server_default='pending'),
            sa.Column('created_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_initiator_status', 'trade_offers',
                         ['initiator_character_id', 'status'])
        op.create_index('idx_target_status', 'trade_offers',
                         ['target_character_id', 'status'])

    if 'trade_offer_items' not in existing_tables:
        op.create_table(
            'trade_offer_items',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('trade_offer_id', sa.Integer, nullable=False),
            sa.Column('character_id', sa.Integer, nullable=False),
            sa.Column('item_id', sa.Integer, nullable=False),
            sa.Column('quantity', sa.Integer, nullable=False, server_default='1'),
            sa.ForeignKeyConstraint(['trade_offer_id'], ['trade_offers.id'],
                                     ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['item_id'], ['items.id']),
        )
        op.create_index('idx_trade_offer', 'trade_offer_items', ['trade_offer_id'])


def downgrade() -> None:
    op.drop_table('trade_offer_items')
    op.drop_table('trade_offers')

"""Add npc_shop_items table for NPC trading system

Revision ID: 018_add_npc_shop_items
Revises: 017_add_dialogue_tables
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '018_add_npc_shop_items'
down_revision = '017_add_dialogue_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if 'npc_shop_items' not in insp.get_table_names():
        op.create_table(
            'npc_shop_items',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('npc_id', sa.Integer(), nullable=False, index=True),
            sa.Column('item_id', sa.Integer(), nullable=False),
            sa.Column('buy_price', sa.Integer(), nullable=False),
            sa.Column('sell_price', sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column('stock', sa.Integer(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table('npc_shop_items')

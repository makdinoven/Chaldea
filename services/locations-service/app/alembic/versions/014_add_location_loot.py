"""Add location_loot table

Revision ID: 014_add_location_loot
Revises: 013_add_post_likes
Create Date: 2026-03-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '014_add_location_loot'
down_revision = '013_add_post_likes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if 'location_loot' not in insp.get_table_names():
        op.create_table(
            'location_loot',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('location_id', sa.BigInteger(), sa.ForeignKey('Locations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('item_id', sa.Integer(), nullable=False),
            sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('dropped_by_character_id', sa.Integer(), nullable=True),
            sa.Column('dropped_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_location_loot_location_id', 'location_loot', ['location_id'])


def downgrade() -> None:
    op.drop_index('ix_location_loot_location_id', table_name='location_loot')
    op.drop_table('location_loot')

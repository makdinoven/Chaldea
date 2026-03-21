"""Add location_favorites table

Revision ID: 015_add_location_favorites
Revises: 014_add_location_loot
Create Date: 2026-03-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '015_add_location_favorites'
down_revision = '014_add_location_loot'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if 'location_favorites' not in insp.get_table_names():
        op.create_table(
            'location_favorites',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('location_id', sa.BigInteger(),
                      sa.ForeignKey('Locations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('user_id', 'location_id', name='uq_user_location_favorite'),
        )
        op.create_index('ix_location_favorites_user_id', 'location_favorites', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_location_favorites_user_id', table_name='location_favorites')
    op.drop_table('location_favorites')

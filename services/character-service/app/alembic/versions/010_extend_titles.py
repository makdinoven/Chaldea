"""Extend titles and character_titles tables for title system.

Add rarity, conditions, bonuses, icon, sort_order, is_active,
created_at, updated_at to titles table.
Add is_custom to character_titles table.
Add indexes on rarity and is_active.

Revision ID: 010_extend_titles
Revises: 009_add_mob_kills
Create Date: 2026-03-25

"""
from alembic import op
import sqlalchemy as sa

revision = '010_extend_titles'
down_revision = '009_add_mob_kills'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- titles table ---
    op.add_column('titles', sa.Column('rarity', sa.String(20), nullable=False, server_default='common'))
    op.add_column('titles', sa.Column('conditions', sa.JSON(), nullable=True))
    op.add_column('titles', sa.Column('bonuses', sa.JSON(), nullable=True))
    op.add_column('titles', sa.Column('icon', sa.String(255), nullable=True))
    op.add_column('titles', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('titles', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'))
    op.add_column('titles', sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=True))
    op.add_column('titles', sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=True))

    op.create_index('idx_titles_rarity', 'titles', ['rarity'])
    op.create_index('idx_titles_is_active', 'titles', ['is_active'])

    # --- character_titles table ---
    op.add_column('character_titles', sa.Column('is_custom', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    # --- character_titles table ---
    op.drop_column('character_titles', 'is_custom')

    # --- titles table ---
    op.drop_index('idx_titles_is_active', table_name='titles')
    op.drop_index('idx_titles_rarity', table_name='titles')

    op.drop_column('titles', 'updated_at')
    op.drop_column('titles', 'created_at')
    op.drop_column('titles', 'is_active')
    op.drop_column('titles', 'sort_order')
    op.drop_column('titles', 'icon')
    op.drop_column('titles', 'bonuses')
    op.drop_column('titles', 'conditions')
    op.drop_column('titles', 'rarity')

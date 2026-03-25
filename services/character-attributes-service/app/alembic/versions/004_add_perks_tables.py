"""Add perks, character_perks, and character_cumulative_stats tables

Revision ID: 004_add_perks_tables
Revises: 003_backfill_null_defaults
Create Date: 2026-03-25

"""
from alembic import op
import sqlalchemy as sa

revision = '004_add_perks_tables'
down_revision = '003_backfill_null_defaults'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'perks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('rarity', sa.String(20), nullable=False, server_default='common'),
        sa.Column('icon', sa.String(255), nullable=True),
        sa.Column('conditions', sa.JSON(), nullable=False),
        sa.Column('bonuses', sa.JSON(), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_category', 'perks', ['category'])
    op.create_index('idx_rarity', 'perks', ['rarity'])

    op.create_table(
        'character_perks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('perk_id', sa.Integer(), sa.ForeignKey('perks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('unlocked_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_custom', sa.Boolean(), server_default='0'),
    )
    op.create_unique_constraint('uq_char_perk', 'character_perks', ['character_id', 'perk_id'])
    op.create_index('idx_character_perks_character_id', 'character_perks', ['character_id'])
    op.create_index('idx_character_perks_perk_id', 'character_perks', ['perk_id'])

    op.create_table(
        'character_cumulative_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('character_id', sa.Integer(), nullable=False, unique=True),
        # Battle stats (Phase 1)
        sa.Column('total_damage_dealt', sa.BigInteger(), server_default='0'),
        sa.Column('total_damage_received', sa.BigInteger(), server_default='0'),
        sa.Column('pve_kills', sa.Integer(), server_default='0'),
        sa.Column('pvp_wins', sa.Integer(), server_default='0'),
        sa.Column('pvp_losses', sa.Integer(), server_default='0'),
        sa.Column('total_battles', sa.Integer(), server_default='0'),
        sa.Column('max_damage_single_battle', sa.BigInteger(), server_default='0'),
        sa.Column('max_win_streak', sa.Integer(), server_default='0'),
        sa.Column('current_win_streak', sa.Integer(), server_default='0'),
        sa.Column('total_rounds_survived', sa.Integer(), server_default='0'),
        sa.Column('low_hp_wins', sa.Integer(), server_default='0'),
        # Economic stats (Phase 3)
        sa.Column('total_gold_earned', sa.BigInteger(), server_default='0'),
        sa.Column('total_gold_spent', sa.BigInteger(), server_default='0'),
        sa.Column('items_bought', sa.Integer(), server_default='0'),
        sa.Column('items_sold', sa.Integer(), server_default='0'),
        # Exploration stats (Phase 3)
        sa.Column('locations_visited', sa.Integer(), server_default='0'),
        sa.Column('total_transitions', sa.Integer(), server_default='0'),
        # Skill stats (Phase 3)
        sa.Column('skills_used', sa.Integer(), server_default='0'),
        sa.Column('items_equipped', sa.Integer(), server_default='0'),
    )
    op.create_index('idx_cumulative_stats_character_id', 'character_cumulative_stats', ['character_id'])


def downgrade() -> None:
    op.drop_table('character_cumulative_stats')
    op.drop_table('character_perks')
    op.drop_table('perks')

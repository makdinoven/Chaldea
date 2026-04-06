"""Add total_posts and quests_completed to character_cumulative_stats

Revision ID: 005_add_posts_quests_stats
Revises: 004_add_perks_tables
Create Date: 2026-04-06

"""
from alembic import op
import sqlalchemy as sa

revision = '005_add_posts_quests_stats'
down_revision = '004_add_perks_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'character_cumulative_stats',
        sa.Column('total_posts', sa.Integer(), server_default='0'),
    )
    op.add_column(
        'character_cumulative_stats',
        sa.Column('quests_completed', sa.Integer(), server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('character_cumulative_stats', 'quests_completed')
    op.drop_column('character_cumulative_stats', 'total_posts')

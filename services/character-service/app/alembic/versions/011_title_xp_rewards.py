"""Replace title bonuses with XP reward columns.

DROP column bonuses from titles.
ADD column reward_passive_exp INT NOT NULL DEFAULT 0.
ADD column reward_active_exp INT NOT NULL DEFAULT 0.

Revision ID: 011_title_xp_rewards
Revises: 010_extend_titles
Create Date: 2026-03-25

"""
from alembic import op
import sqlalchemy as sa

revision = '011_title_xp_rewards'
down_revision = '010_extend_titles'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('titles', 'bonuses')
    op.add_column('titles', sa.Column('reward_passive_exp', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('titles', sa.Column('reward_active_exp', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('titles', 'reward_active_exp')
    op.drop_column('titles', 'reward_passive_exp')
    op.add_column('titles', sa.Column('bonuses', sa.JSON(), nullable=True))

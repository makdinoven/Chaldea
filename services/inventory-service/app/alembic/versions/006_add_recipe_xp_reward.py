"""Add xp_reward column to recipes table.

Revision ID: 006_add_recipe_xp_reward
Revises: 005_add_recipe_item_type
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = '006_add_recipe_xp_reward'
down_revision = '005_add_recipe_item_type'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('recipes', sa.Column('xp_reward', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('recipes', 'xp_reward')

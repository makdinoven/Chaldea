"""Add quest tables for NPC quest system

Revision ID: 019_add_quest_tables
Revises: 018_add_npc_shop_items
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '019_add_quest_tables'
down_revision = '018_add_npc_shop_items'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = insp.get_table_names()

    if 'quests' not in existing_tables:
        op.create_table(
            'quests',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('npc_id', sa.Integer(), nullable=False, index=True),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('quest_type', sa.String(50), nullable=False, server_default=sa.text("'standard'")),
            sa.Column('min_level', sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column('reward_currency', sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column('reward_exp', sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column('reward_items', sa.JSON(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        )

    if 'quest_objectives' not in existing_tables:
        op.create_table(
            'quest_objectives',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('quest_id', sa.BigInteger(), sa.ForeignKey('quests.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('description', sa.String(500), nullable=False),
            sa.Column('objective_type', sa.String(50), nullable=False),
            sa.Column('target_id', sa.Integer(), nullable=True),
            sa.Column('target_count', sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text("0")),
        )

    if 'character_quests' not in existing_tables:
        op.create_table(
            'character_quests',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('character_id', sa.Integer(), nullable=False, index=True),
            sa.Column('quest_id', sa.BigInteger(), sa.ForeignKey('quests.id', ondelete='CASCADE'), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'active'")),
            sa.Column('accepted_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.Column('completed_at', sa.TIMESTAMP(), nullable=True),
            sa.UniqueConstraint('character_id', 'quest_id', name='uq_character_quest'),
        )

    if 'character_quest_progress' not in existing_tables:
        op.create_table(
            'character_quest_progress',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('character_quest_id', sa.BigInteger(), sa.ForeignKey('character_quests.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('objective_id', sa.BigInteger(), sa.ForeignKey('quest_objectives.id', ondelete='CASCADE'), nullable=False),
            sa.Column('current_count', sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column('is_completed', sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    op.drop_table('character_quest_progress')
    op.drop_table('character_quests')
    op.drop_table('quest_objectives')
    op.drop_table('quests')

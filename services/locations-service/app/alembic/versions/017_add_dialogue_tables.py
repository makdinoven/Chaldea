"""Add dialogue_trees, dialogue_nodes, dialogue_options tables

Revision ID: 017_add_dialogue_tables
Revises: 016_add_post_moderation
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '017_add_dialogue_tables'
down_revision = '016_add_post_moderation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if 'dialogue_trees' not in insp.get_table_names():
        op.create_table(
            'dialogue_trees',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('npc_id', sa.Integer(), nullable=False, index=True),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        )

    if 'dialogue_nodes' not in insp.get_table_names():
        op.create_table(
            'dialogue_nodes',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('tree_id', sa.BigInteger(),
                      sa.ForeignKey('dialogue_trees.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('npc_text', sa.Text(), nullable=False),
            sa.Column('is_root', sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column('action_type', sa.String(50), nullable=True),
            sa.Column('action_data', sa.JSON(), nullable=True),
        )

    if 'dialogue_options' not in insp.get_table_names():
        op.create_table(
            'dialogue_options',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('node_id', sa.BigInteger(),
                      sa.ForeignKey('dialogue_nodes.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('text', sa.String(500), nullable=False),
            sa.Column('next_node_id', sa.BigInteger(),
                      sa.ForeignKey('dialogue_nodes.id', ondelete='SET NULL'), nullable=True),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column('condition', sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table('dialogue_options')
    op.drop_table('dialogue_nodes')
    op.drop_table('dialogue_trees')

"""Add character_logs table for character event tracking.

Stores all character events (RP posts, battles, items, quests, etc.)
with extensible event_type discriminator. Phase 1 of FEAT-095.

Revision ID: 012_add_character_logs
Revises: 011_title_xp_rewards
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa

revision = '012_add_character_logs'
down_revision = '011_title_xp_rewards'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'character_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_character_logs_char_created',
        'character_logs',
        ['character_id', sa.text('created_at DESC')],
    )
    op.create_index(
        'idx_character_logs_event_type',
        'character_logs',
        ['event_type'],
    )


def downgrade() -> None:
    op.drop_table('character_logs')

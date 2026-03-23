"""Add mob_kills table for bestiary kill tracker.

Tracks which mob templates each player character has killed.
Used by the bestiary feature to unlock mob information.

Revision ID: 009_add_mob_kills
Revises: 008_add_npc_status
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

revision = '009_add_mob_kills'
down_revision = '008_add_npc_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'mob_kills',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('mob_template_id', sa.Integer(), nullable=False),
        sa.Column('killed_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['mob_template_id'],
            ['mob_templates.id'],
            name='fk_mob_kills_template',
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint('character_id', 'mob_template_id', name='uq_character_mob_kill'),
    )
    op.create_index('idx_mob_kills_character', 'mob_kills', ['character_id'])
    op.create_index('idx_mob_kills_template', 'mob_kills', ['mob_template_id'])


def downgrade() -> None:
    op.drop_table('mob_kills')

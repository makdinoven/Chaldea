"""Add pinned_at column to conversation_participants

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-16

Per-user pinning of conversations to the top of the messenger list. When set,
the participant has pinned that conversation; ordering puts pinned first.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'conversation_participants',
        sa.Column('pinned_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conversation_participants', 'pinned_at')

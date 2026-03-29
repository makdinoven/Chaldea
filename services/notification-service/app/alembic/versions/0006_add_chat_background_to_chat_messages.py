"""Add chat_background column to chat_messages table

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-29

Stores the user's active chat background slug at the time the message was sent,
following the same per-message snapshot pattern as avatar_frame.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'chat_messages',
        sa.Column('chat_background', sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('chat_messages', 'chat_background')

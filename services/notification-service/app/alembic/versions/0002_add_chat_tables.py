"""Add chat_messages and chat_bans tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-19

Creates chat_messages table for storing global chat messages across channels,
and chat_bans table for tracking user bans from the chat system.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('channel', sa.Enum('general', 'trade', 'help', name='chat_channel'), nullable=False),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('avatar', sa.String(500), nullable=True),
        sa.Column('avatar_frame', sa.String(50), nullable=True),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('reply_to_id', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_foreign_key(
        'fk_chat_messages_reply_to',
        'chat_messages', 'chat_messages',
        ['reply_to_id'], ['id'],
        ondelete='SET NULL',
    )

    op.create_index('idx_channel_created', 'chat_messages', ['channel', 'created_at'])
    op.create_index('idx_user_id', 'chat_messages', ['user_id'])

    op.create_table(
        'chat_bans',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer, nullable=False, unique=True),
        sa.Column('banned_by', sa.Integer, nullable=False),
        sa.Column('reason', sa.String(500), nullable=True),
        sa.Column('banned_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table('chat_bans')
    op.drop_index('idx_user_id', table_name='chat_messages')
    op.drop_index('idx_channel_created', table_name='chat_messages')
    op.drop_constraint('fk_chat_messages_reply_to', 'chat_messages', type_='foreignkey')
    op.drop_table('chat_messages')

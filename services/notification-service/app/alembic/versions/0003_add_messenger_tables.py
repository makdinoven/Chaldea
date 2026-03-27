"""Add messenger tables (conversations, conversation_participants, private_messages)

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-27

Creates tables for the private messenger feature: conversations, conversation_participants,
and private_messages. Supports direct (1-on-1) and group conversations with unread tracking.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('type', sa.Enum('direct', 'group', name='conversation_type'), nullable=False),
        sa.Column('title', sa.String(100), nullable=True),
        sa.Column('created_by', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'conversation_participants',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('conversation_id', sa.Integer, nullable=False),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('joined_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('last_read_at', sa.DateTime, nullable=True),
    )

    op.create_foreign_key(
        'fk_conv_participants_conv',
        'conversation_participants', 'conversations',
        ['conversation_id'], ['id'],
        ondelete='CASCADE',
    )

    op.create_unique_constraint(
        'uq_conv_participant',
        'conversation_participants',
        ['conversation_id', 'user_id'],
    )

    op.create_index('ix_conv_participants_user', 'conversation_participants', ['user_id'])

    op.create_table(
        'private_messages',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('conversation_id', sa.Integer, nullable=False),
        sa.Column('sender_id', sa.Integer, nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime, nullable=True),
    )

    op.create_foreign_key(
        'fk_pm_conv',
        'private_messages', 'conversations',
        ['conversation_id'], ['id'],
        ondelete='CASCADE',
    )

    op.create_index('ix_pm_conv_created', 'private_messages', ['conversation_id', 'created_at'])
    op.create_index('ix_pm_sender', 'private_messages', ['sender_id'])


def downgrade() -> None:
    op.drop_index('ix_pm_sender', table_name='private_messages')
    op.drop_index('ix_pm_conv_created', table_name='private_messages')
    op.drop_constraint('fk_pm_conv', 'private_messages', type_='foreignkey')
    op.drop_table('private_messages')

    op.drop_index('ix_conv_participants_user', table_name='conversation_participants')
    op.drop_constraint('uq_conv_participant', 'conversation_participants', type_='unique')
    op.drop_constraint('fk_conv_participants_conv', 'conversation_participants', type_='foreignkey')
    op.drop_table('conversation_participants')

    op.drop_table('conversations')

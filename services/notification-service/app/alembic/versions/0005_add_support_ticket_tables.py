"""Add support ticket tables (support_tickets, support_ticket_messages)

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-28

Creates tables for the support ticket system: support_tickets for ticket metadata
and support_ticket_messages for the conversation thread within each ticket.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'support_tickets',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column(
            'category',
            sa.Enum('bug', 'question', 'suggestion', 'complaint', 'other', name='ticket_category'),
            nullable=False,
            server_default='other',
        ),
        sa.Column(
            'status',
            sa.Enum('open', 'in_progress', 'awaiting_reply', 'closed', name='ticket_status'),
            nullable=False,
            server_default='open',
        ),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('closed_at', sa.DateTime, nullable=True),
        sa.Column('closed_by', sa.Integer, nullable=True),
    )

    op.create_index('ix_tickets_user_id', 'support_tickets', ['user_id'])
    op.create_index('ix_tickets_status', 'support_tickets', ['status'])
    op.create_index('ix_tickets_created_at', 'support_tickets', ['created_at'])

    op.create_table(
        'support_ticket_messages',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ticket_id', sa.Integer, nullable=False),
        sa.Column('sender_id', sa.Integer, nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('attachment_url', sa.String(512), nullable=True),
        sa.Column('is_admin', sa.Boolean, nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_foreign_key(
        'fk_ticket_messages_ticket',
        'support_ticket_messages', 'support_tickets',
        ['ticket_id'], ['id'],
        ondelete='CASCADE',
    )

    op.create_index(
        'ix_ticket_messages_ticket_created',
        'support_ticket_messages',
        ['ticket_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_ticket_messages_ticket_created', table_name='support_ticket_messages')
    op.drop_constraint('fk_ticket_messages_ticket', 'support_ticket_messages', type_='foreignkey')
    op.drop_table('support_ticket_messages')

    op.drop_index('ix_tickets_created_at', table_name='support_tickets')
    op.drop_index('ix_tickets_status', table_name='support_tickets')
    op.drop_index('ix_tickets_user_id', table_name='support_tickets')
    op.drop_table('support_tickets')

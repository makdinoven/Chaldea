"""Add edited_at and reply_to_id columns to private_messages

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-27

Adds support for message editing (edited_at timestamp) and reply-to/quote
(reply_to_id foreign key referencing the same table).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'private_messages',
        sa.Column('edited_at', sa.DateTime, nullable=True),
    )
    op.add_column(
        'private_messages',
        sa.Column('reply_to_id', sa.Integer, nullable=True),
    )
    op.create_foreign_key(
        'fk_pm_reply_to',
        'private_messages', 'private_messages',
        ['reply_to_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_pm_reply_to', 'private_messages', ['reply_to_id'])


def downgrade() -> None:
    op.drop_index('ix_pm_reply_to', table_name='private_messages')
    op.drop_constraint('fk_pm_reply_to', 'private_messages', type_='foreignkey')
    op.drop_column('private_messages', 'reply_to_id')
    op.drop_column('private_messages', 'edited_at')

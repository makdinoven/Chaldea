"""Add message_reactions table

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-16

Emoji reactions on private messages. Unique per (message, user, emoji).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'message_reactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('emoji', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['private_messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'user_id', 'emoji', name='uq_reaction'),
    )
    op.create_index('ix_reaction_message', 'message_reactions', ['message_id'])


def downgrade() -> None:
    op.drop_index('ix_reaction_message', table_name='message_reactions')
    op.drop_table('message_reactions')

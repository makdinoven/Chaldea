"""Add gold_transactions table for tracking all gold earn/spend events.

Required for battle pass earn_gold / spend_gold missions and
general gold audit trail. Part of FEAT-102.

Revision ID: 013_add_gold_transactions
Revises: 012_add_character_logs
Create Date: 2026-03-29

"""
from alembic import op
import sqlalchemy as sa

revision = '013_add_gold_transactions'
down_revision = '012_add_character_logs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gold_transactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('transaction_type', sa.String(50), nullable=False),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_gold_transactions_id', 'gold_transactions', ['id'])
    op.create_index('ix_gold_transactions_character_id', 'gold_transactions', ['character_id'])
    op.create_index(
        'idx_gold_tx_character_created',
        'gold_transactions',
        ['character_id', 'created_at'],
    )
    op.create_index(
        'idx_gold_tx_type',
        'gold_transactions',
        ['transaction_type'],
    )


def downgrade() -> None:
    op.drop_table('gold_transactions')

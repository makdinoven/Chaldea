"""Add user_blocks table and message_privacy column to users

Revision ID: 0020
Revises: 0019
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add message_privacy enum column to users table
    op.add_column(
        'users',
        sa.Column(
            'message_privacy',
            sa.Enum('all', 'friends', 'nobody', name='message_privacy_enum'),
            nullable=False,
            server_default='all',
        ),
    )

    # Create user_blocks table
    op.create_table(
        'user_blocks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('blocked_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'blocked_user_id', name='uq_user_block'),
    )
    op.create_index('ix_user_blocks_id', 'user_blocks', ['id'])


def downgrade() -> None:
    op.drop_index('ix_user_blocks_id', table_name='user_blocks')
    op.drop_table('user_blocks')
    op.drop_column('users', 'message_privacy')
    # Drop the enum type (MySQL doesn't have standalone enums, but this is safe)

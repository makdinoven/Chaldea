"""Add user_sessions and users.tokens_valid_after

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-22

- user_sessions: one row per login (device/browser). The row id is put into
  access and refresh tokens as the `sid` claim; deleting the row revokes them.
- users.tokens_valid_after: tokens without `sid` (issued before this
  migration) are accepted only while it is NULL.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE', name='fk_user_sessions_user_id'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=False),
        sa.Column('user_agent', sa.String(255), nullable=True),
    )
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])
    op.add_column('users', sa.Column('tokens_valid_after', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'tokens_valid_after')
    # Dropping the table drops its FK and index with it (MySQL refuses to drop
    # an index that backs a FK on its own).
    op.drop_table('user_sessions')

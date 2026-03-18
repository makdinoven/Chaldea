"""Add last_active_at column to users table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]
    if 'last_active_at' not in columns:
        op.add_column('users', sa.Column('last_active_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]
    if 'last_active_at' in columns:
        op.drop_column('users', 'last_active_at')

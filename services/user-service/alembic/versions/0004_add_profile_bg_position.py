"""Add profile_bg_position column to users table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]

    if 'profile_bg_position' not in columns:
        op.add_column('users', sa.Column('profile_bg_position', sa.String(20), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]

    if 'profile_bg_position' in columns:
        op.drop_column('users', 'profile_bg_position')

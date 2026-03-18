"""Add profile customization columns to users table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]

    if 'profile_bg_color' not in columns:
        op.add_column('users', sa.Column('profile_bg_color', sa.String(7), nullable=True))
    if 'profile_bg_image' not in columns:
        op.add_column('users', sa.Column('profile_bg_image', sa.String(512), nullable=True))
    if 'nickname_color' not in columns:
        op.add_column('users', sa.Column('nickname_color', sa.String(7), nullable=True))
    if 'avatar_frame' not in columns:
        op.add_column('users', sa.Column('avatar_frame', sa.String(50), nullable=True))
    if 'avatar_effect_color' not in columns:
        op.add_column('users', sa.Column('avatar_effect_color', sa.String(7), nullable=True))
    if 'status_text' not in columns:
        op.add_column('users', sa.Column('status_text', sa.String(100), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]

    for col in ['profile_bg_color', 'profile_bg_image', 'nickname_color',
                'avatar_frame', 'avatar_effect_color', 'status_text']:
        if col in columns:
            op.drop_column('users', col)

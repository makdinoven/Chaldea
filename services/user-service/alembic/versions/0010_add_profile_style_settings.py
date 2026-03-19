"""Add post_color and profile_style_settings columns to users table

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('post_color', sa.String(7), nullable=True))
    op.add_column('users', sa.Column('profile_style_settings', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'profile_style_settings')
    op.drop_column('users', 'post_color')

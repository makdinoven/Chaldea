"""Add notification category and per-user notification preferences

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-22

- notifications.category: nullable String(20); NULL for pre-existing rows.
- notification_preferences: one row per user, JSON {category: mode}.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'notifications',
        sa.Column('category', sa.String(20), nullable=True),
    )
    op.create_table(
        'notification_preferences',
        sa.Column('user_id', sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column('settings', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('notification_preferences')
    op.drop_column('notifications', 'category')

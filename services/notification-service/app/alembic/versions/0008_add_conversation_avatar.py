"""Add avatar column to conversations

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-16

Group chat avatar URL (uploaded via photo-service to S3). Nullable; direct
conversations don't use it.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column('avatar', sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conversations', 'avatar')

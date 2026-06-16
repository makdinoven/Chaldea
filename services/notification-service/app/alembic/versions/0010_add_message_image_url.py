"""Add image_url column to private_messages

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-16

Optional image attachment URL (uploaded via photo-service to S3).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'private_messages',
        sa.Column('image_url', sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('private_messages', 'image_url')

"""Initial baseline for notification-service tables

Revision ID: 0001
Revises:
Create Date: 2026-03-19

This migration captures the existing DB schema state for notification-service.
The notifications table already exists in production, so upgrade() is
intentionally empty (stamp this revision to mark it as applied).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The notifications table already exists in production DB
    # (created by Base.metadata.create_all). This migration is a
    # baseline snapshot — stamp only.
    pass


def downgrade() -> None:
    pass

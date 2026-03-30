"""Add source_handle, target_handle to dungeon_corridors for visual editor

Revision ID: 003
Revises: 002
Create Date: 2026-03-30

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dungeon_corridors", sa.Column("source_handle", sa.String(16), nullable=True))
    op.add_column("dungeon_corridors", sa.Column("target_handle", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("dungeon_corridors", "target_handle")
    op.drop_column("dungeon_corridors", "source_handle")

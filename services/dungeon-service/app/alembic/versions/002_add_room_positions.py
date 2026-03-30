"""Add position_x, position_y to dungeon_rooms for visual editor

Revision ID: 002
Revises: 001
Create Date: 2026-03-30

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dungeon_rooms", sa.Column("position_x", sa.Float, nullable=True))
    op.add_column("dungeon_rooms", sa.Column("position_y", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("dungeon_rooms", "position_y")
    op.drop_column("dungeon_rooms", "position_x")

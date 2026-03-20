"""Add marker_type to Districts, add 'farm' to Location marker_type enum

Revision ID: 011_district_marker_farm
Revises: 010_add_sort_order
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

# revision identifiers, used by Alembic.
revision = '011_district_marker_farm'
down_revision = '010_add_sort_order'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # 1. Add marker_type column to Districts (if not exists)
    district_columns = [c['name'] for c in insp.get_columns('Districts')]
    if 'marker_type' not in district_columns:
        bind.execute(text(
            "ALTER TABLE Districts ADD COLUMN marker_type "
            "ENUM('safe','dangerous','dungeon','farm') DEFAULT 'safe'"
        ))

    # 2. Alter Location marker_type ENUM to add 'farm' value
    # MySQL requires MODIFY COLUMN to change ENUM values
    bind.execute(text(
        "ALTER TABLE Locations MODIFY COLUMN marker_type "
        "ENUM('safe','dangerous','dungeon','farm') NOT NULL DEFAULT 'safe'"
    ))


def downgrade() -> None:
    bind = op.get_bind()

    # Remove 'farm' from Locations marker_type
    bind.execute(text(
        "ALTER TABLE Locations MODIFY COLUMN marker_type "
        "ENUM('safe','dangerous','dungeon') NOT NULL DEFAULT 'safe'"
    ))

    # Drop marker_type from Districts
    op.drop_column('Districts', 'marker_type')

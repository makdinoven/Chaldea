"""Add map_icon_url, map_x, map_y to Locations

Revision ID: 006_add_location_map_fields
Revises: 005_clickable_zone_enhancements
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006_add_location_map_fields'
down_revision = '005_clickable_zone_enhancements'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = [col['name'] for col in inspector.get_columns('Locations')]

    if 'map_icon_url' not in existing_columns:
        op.execute("ALTER TABLE Locations ADD COLUMN map_icon_url VARCHAR(255) NULL")

    if 'map_x' not in existing_columns:
        op.execute("ALTER TABLE Locations ADD COLUMN map_x FLOAT NULL")

    if 'map_y' not in existing_columns:
        op.execute("ALTER TABLE Locations ADD COLUMN map_y FLOAT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE Locations DROP COLUMN map_icon_url")
    op.execute("ALTER TABLE Locations DROP COLUMN map_x")
    op.execute("ALTER TABLE Locations DROP COLUMN map_y")

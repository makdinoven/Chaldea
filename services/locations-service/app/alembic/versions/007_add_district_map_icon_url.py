"""Add map_icon_url to Districts

Revision ID: 007_add_district_map_icon_url
Revises: 006_add_location_map_fields
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007_add_district_map_icon_url'
down_revision = '006_add_location_map_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = [col['name'] for col in inspector.get_columns('Districts')]

    if 'map_icon_url' not in existing_columns:
        op.execute("ALTER TABLE Districts ADD COLUMN map_icon_url VARCHAR(255) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE Districts DROP COLUMN map_icon_url")

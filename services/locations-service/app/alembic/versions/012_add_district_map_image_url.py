"""Add map_image_url to Districts table

Revision ID: 012_district_map_image
Revises: 011_district_marker_farm
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

# revision identifiers, used by Alembic.
revision = '012_district_map_image'
down_revision = '011_district_marker_farm'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    district_columns = [c['name'] for c in insp.get_columns('Districts')]
    if 'map_image_url' not in district_columns:
        op.add_column('Districts', sa.Column('map_image_url', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('Districts', 'map_image_url')

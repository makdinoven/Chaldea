"""Precise coastline outlines for clickable map zones.

- ClickableZones.precise_path: SVG path (0..100 space, like zone_data) of the land
  inside the rough zone polygon, with every island. Computed by photo-service.
- Areas/Countries.map_land_settings: the water colour samples and tolerance the
  admin picked for that map, so outlines can be recomputed when the image changes.
- ClickableZones.land_settings: the same, for one zone that needs its own samples.

Revision ID: 041_precise_map_outlines
Revises: 040_post_versions
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '041_precise_map_outlines'
down_revision = '040_post_versions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ClickableZones', sa.Column('precise_path', mysql.MEDIUMTEXT(), nullable=True))
    op.add_column('ClickableZones', sa.Column('land_settings', sa.Text(), nullable=True))
    op.add_column('Areas', sa.Column('map_land_settings', sa.Text(), nullable=True))
    op.add_column('Countries', sa.Column('map_land_settings', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('Countries', 'map_land_settings')
    op.drop_column('Areas', 'map_land_settings')
    op.drop_column('ClickableZones', 'land_settings')
    op.drop_column('ClickableZones', 'precise_path')

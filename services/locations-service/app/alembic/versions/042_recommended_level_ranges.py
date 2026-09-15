"""Manual recommended level range for countries and regions.

The map card shows a recommended level range per country/region. By default it is
computed from the locations inside; these columns let an admin override either
bound. NULL = computed.

Revision ID: 042_recommended_level_ranges
Revises: 041_precise_map_outlines
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa

revision = '042_recommended_level_ranges'
down_revision = '041_precise_map_outlines'
branch_labels = None
depends_on = None

TABLES = ("Countries", "Regions")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column('recommended_level_min', sa.Integer(), nullable=True))
        op.add_column(table, sa.Column('recommended_level_max', sa.Integer(), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, 'recommended_level_max')
        op.drop_column(table, 'recommended_level_min')

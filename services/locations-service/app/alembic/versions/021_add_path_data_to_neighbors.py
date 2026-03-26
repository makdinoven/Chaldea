"""Add path_data JSON column to LocationNeighbors for storing waypoints

Revision ID: 021_add_path_data_to_neighbors
Revises: 020_add_archive_tables
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '021_add_path_data_to_neighbors'
down_revision = '020_add_archive_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns('LocationNeighbors')]

    if 'path_data' not in columns:
        op.add_column('LocationNeighbors', sa.Column('path_data', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('LocationNeighbors', 'path_data')

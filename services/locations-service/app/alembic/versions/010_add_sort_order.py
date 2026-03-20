"""Add sort_order to Districts and Locations

Revision ID: 010_add_sort_order
Revises: 009_district_parent_id
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '010_add_sort_order'
down_revision = '009_district_parent_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    district_columns = [c['name'] for c in insp.get_columns('Districts')]
    if 'sort_order' not in district_columns:
        op.add_column('Districts', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))

    location_columns = [c['name'] for c in insp.get_columns('Locations')]
    if 'sort_order' not in location_columns:
        op.add_column('Locations', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('Locations', 'sort_order')
    op.drop_column('Districts', 'sort_order')

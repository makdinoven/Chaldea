"""Add no_quick_move to Locations

Revision ID: 030_add_no_quick_move_to_locations
Revises: 029_floating_structure_area_id
Create Date: 2026-04-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '030_add_no_quick_move_to_locations'
down_revision = '029_floating_structure_area_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c['name'] for c in insp.get_columns('Locations')}
    if 'no_quick_move' in cols:
        return

    op.add_column(
        'Locations',
        sa.Column('no_quick_move', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('Locations', 'no_quick_move')

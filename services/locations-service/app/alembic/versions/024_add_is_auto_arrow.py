"""Add is_auto_arrow column to LocationNeighbors

Revision ID: 024_add_is_auto_arrow
Revises: 023_add_region_transition_arrows
Create Date: 2026-03-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '024_add_is_auto_arrow'
down_revision = '023_add_region_transition_arrows'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns('LocationNeighbors')]

    if 'is_auto_arrow' not in columns:
        op.add_column(
            'LocationNeighbors',
            sa.Column('is_auto_arrow', sa.Boolean(), nullable=False, server_default='0'),
        )


def downgrade() -> None:
    op.drop_column('LocationNeighbors', 'is_auto_arrow')

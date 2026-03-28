"""Add rotation column to region_transition_arrows

Revision ID: 026_arrow_rotation
Revises: 025_cover_text_color
Create Date: 2026-03-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '026_arrow_rotation'
down_revision = '025_cover_text_color'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns('region_transition_arrows')]

    if 'rotation' not in columns:
        op.add_column(
            'region_transition_arrows',
            sa.Column('rotation', sa.Float, nullable=True, server_default='0'),
        )


def downgrade() -> None:
    op.drop_column('region_transition_arrows', 'rotation')

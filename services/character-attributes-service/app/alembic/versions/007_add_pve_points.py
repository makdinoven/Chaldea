"""Add pve_points to character_cumulative_stats (level-weighted PvE score)

PvE points = sum of the levels of defeated mobs (killing a lvl-5 mob grants +5,
a lvl-25 mob grants +25), distinct from the existing pve_kills count. Backfilled
to 0; accrues going forward as battle-service records new kills.

Revision ID: 007_add_pve_points
Revises: 006_perk_derived_topup
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa

revision = '007_add_pve_points'
down_revision = '006_perk_derived_topup'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'character_cumulative_stats',
        sa.Column('pve_points', sa.Integer(), server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('character_cumulative_stats', 'pve_points')

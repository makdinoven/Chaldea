"""Player houses (FEAT-180), stage 2: empty plots, building and room levels, workshops.

* `house_plots.kind` ready|empty (existing plots are ready);
* `house_rooms.level` (existing rooms are level 1), `upgrade_to_level`,
  `upgrade_complete_at`, `workshop_profession_id`;
* `house_build_costs` (+ `house_build_cost_items`): what building a room type
  up to a level costs, seeded with gold and hours for every type and level 1..3
  and no materials — admins set those.

Downgrade drops the cost tables and the new columns (rooms keep existing).

Revision ID: 047_house_building
Revises: 046_player_houses
Create Date: 2026-10-27

"""
from alembic import op
import sqlalchemy as sa

revision = '047_house_building'
down_revision = '046_player_houses'
branch_labels = None
depends_on = None

ROOM_TYPES = ('hall', 'bedroom', 'storage', 'workshop')
# level: (gold, build hours)
DEFAULT_COSTS = {1: (200, 6), 2: (800, 24), 3: (2500, 72)}


def upgrade() -> None:
    op.add_column('house_plots', sa.Column('kind', sa.Enum('ready', 'empty', name='house_plot_kind'),
                                           nullable=False, server_default='ready'))
    op.add_column('house_rooms', sa.Column('level', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('house_rooms', sa.Column('upgrade_to_level', sa.Integer(), nullable=True))
    op.add_column('house_rooms', sa.Column('upgrade_complete_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('house_rooms', sa.Column('workshop_profession_id', sa.Integer(), nullable=True))
    costs = op.create_table(
        'house_build_costs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('room_type', sa.Enum(*ROOM_TYPES, name='house_room_type'), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('gold', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('build_hours', sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint('room_type', 'level', name='uq_house_build_cost'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_build_cost_items',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('cost_id', sa.BigInteger(),
                  sa.ForeignKey('house_build_costs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        mysql_engine='InnoDB',
    )
    op.bulk_insert(costs, [
        {'room_type': t, 'level': lvl, 'gold': gold, 'build_hours': hours}
        for t in ROOM_TYPES for lvl, (gold, hours) in DEFAULT_COSTS.items()
    ])


def downgrade() -> None:
    op.drop_table('house_build_cost_items')
    op.drop_table('house_build_costs')
    for col in ('workshop_profession_id', 'upgrade_complete_at', 'upgrade_to_level', 'level'):
        op.drop_column('house_rooms', col)
    op.drop_column('house_plots', 'kind')

"""Player houses (FEAT-180), stage 1: plots, houses, rooms, residents, posts.

Seven new tables, nothing existing is touched. Downgrade drops them child-first;
their FK-backing indexes go with the tables. The storage's items live in
inventory-service (`house_storage`, its own migration).

Revision ID: 046_player_houses
Revises: 045_episodes
Create Date: 2026-10-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = '046_player_houses'
down_revision = '045_episodes'
branch_labels = None
depends_on = None

ROOM_TYPES = ('hall', 'bedroom', 'storage', 'workshop')


def _id():
    return sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True)


def _room_type():
    return sa.Column('room_type', sa.Enum(*ROOM_TYPES, name='house_room_type'), nullable=False)


def _room_text():
    return [
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('image_url', sa.String(512), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        'house_plots', _id(),
        sa.Column('location_id', sa.BigInteger(),
                  sa.ForeignKey('Locations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('region_id', sa.BigInteger(), nullable=True),
        *_room_text(),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('max_rooms', sa.Integer(), nullable=False),
        sa.Column('map_x', sa.Float(), nullable=True),
        sa.Column('map_y', sa.Float(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Index('ix_house_plots_location', 'location_id'),
        sa.Index('ix_house_plots_region', 'region_id'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_plot_rooms', _id(),
        sa.Column('plot_id', sa.BigInteger(),
                  sa.ForeignKey('house_plots.id', ondelete='CASCADE'), nullable=False),
        _room_type(), *_room_text(),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'houses', _id(),
        sa.Column('plot_id', sa.BigInteger(), sa.ForeignKey('house_plots.id'), nullable=False, unique=True),
        sa.Column('owner_character_id', sa.Integer(), nullable=False),
        *_room_text(),
        sa.Column('purchased_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Index('ix_houses_owner', 'owner_character_id'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_rooms', _id(),
        sa.Column('house_id', sa.BigInteger(),
                  sa.ForeignKey('houses.id', ondelete='CASCADE'), nullable=False),
        _room_type(), *_room_text(),
        sa.Column('is_open', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Index('ix_house_rooms_house', 'house_id'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_residents', _id(),
        sa.Column('house_id', sa.BigInteger(),
                  sa.ForeignKey('houses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('can_take', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('can_put', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('added_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('house_id', 'character_id', name='uq_house_resident'),
        sa.Index('ix_house_residents_character', 'character_id'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_resident_rooms', _id(),
        sa.Column('resident_id', sa.BigInteger(),
                  sa.ForeignKey('house_residents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('room_id', sa.BigInteger(),
                  sa.ForeignKey('house_rooms.id', ondelete='CASCADE'), nullable=False),
        sa.UniqueConstraint('resident_id', 'room_id', name='uq_house_resident_room'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_posts', _id(),
        sa.Column('room_id', sa.BigInteger(),
                  sa.ForeignKey('house_rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('content', MEDIUMTEXT(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('edited_at', sa.TIMESTAMP(), nullable=True),
        sa.Index('ix_house_posts_room', 'room_id', 'id'),
        mysql_engine='InnoDB',
    )


def downgrade() -> None:
    for table in ('house_posts', 'house_resident_rooms', 'house_residents', 'house_rooms',
                  'houses', 'house_plot_rooms', 'house_plots'):
        op.drop_table(table)

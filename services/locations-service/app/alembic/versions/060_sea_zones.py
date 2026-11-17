"""Sea geography (FEAT-213 v2): ports, sea zones and the port -> zone link.

* `Locations.is_port` (+ index): the admin marks a location as a port.
* `Locations.is_sea_zone` (+ index): a sea zone — a location of the hidden
  «Моря» country; zones link only to zones (LocationNeighbors / arrows).
* `Locations.port_sea_zone_id` (+ explicit index, FK -> Locations.id
  ON DELETE SET NULL): the zone a port opens to.

Ships, stops and passes are character-service's (052_sea_ships); this service
reads them by raw SQL (`sea_read.py`). The v1 `sea_routes` table is gone.

Every step checks the schema first, so a half-applied run can be repeated.
Downgrade drops the FK, the indexes and the three columns (no data is kept).

Revision ID: 060_sea_zones
Revises: 059_location_neighbor_unique
Create Date: 2026-11-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '060_sea_zones'
down_revision = '059_location_neighbor_unique'
branch_labels = None
depends_on = None

LOCATIONS = 'Locations'
PORT_INDEX = 'ix_locations_is_port'
ZONE_INDEX = 'ix_locations_is_sea_zone'
PORT_ZONE_INDEX = 'ix_locations_port_sea_zone'
PORT_ZONE_FK = 'fk_locations_port_sea_zone'


def _columns(bind) -> set:
    return {c['name'] for c in inspect(bind).get_columns(LOCATIONS)}


def _index_names(bind) -> set:
    insp = inspect(bind)
    names = {i['name'] for i in insp.get_indexes(LOCATIONS)}
    names |= {u['name'] for u in insp.get_unique_constraints(LOCATIONS)}
    return names


def _fk_names(bind) -> set:
    return {fk['name'] for fk in inspect(bind).get_foreign_keys(LOCATIONS)}


def upgrade() -> None:
    bind = op.get_bind()

    if 'is_port' not in _columns(bind):
        op.add_column(LOCATIONS, sa.Column('is_port', sa.Boolean(), nullable=False, server_default='0'))
    if PORT_INDEX not in _index_names(bind):
        op.create_index(PORT_INDEX, LOCATIONS, ['is_port'])

    if 'is_sea_zone' not in _columns(bind):
        op.add_column(LOCATIONS, sa.Column('is_sea_zone', sa.Boolean(), nullable=False, server_default='0'))
    if ZONE_INDEX not in _index_names(bind):
        op.create_index(ZONE_INDEX, LOCATIONS, ['is_sea_zone'])

    if 'port_sea_zone_id' not in _columns(bind):
        op.add_column(LOCATIONS, sa.Column('port_sea_zone_id', sa.BigInteger(), nullable=True))
    # Explicit index for the FK (MySQL would otherwise invent one and block the drop later).
    if PORT_ZONE_INDEX not in _index_names(bind):
        op.create_index(PORT_ZONE_INDEX, LOCATIONS, ['port_sea_zone_id'])
    if PORT_ZONE_FK not in _fk_names(bind):
        op.create_foreign_key(PORT_ZONE_FK, LOCATIONS, LOCATIONS, ['port_sea_zone_id'], ['id'],
                              ondelete='SET NULL')


def downgrade() -> None:
    bind = op.get_bind()

    if PORT_ZONE_FK in _fk_names(bind):
        op.drop_constraint(PORT_ZONE_FK, LOCATIONS, type_='foreignkey')
    if PORT_ZONE_INDEX in _index_names(bind):
        op.drop_index(PORT_ZONE_INDEX, table_name=LOCATIONS)
    if 'port_sea_zone_id' in _columns(bind):
        op.drop_column(LOCATIONS, 'port_sea_zone_id')

    if ZONE_INDEX in _index_names(bind):
        op.drop_index(ZONE_INDEX, table_name=LOCATIONS)
    if 'is_sea_zone' in _columns(bind):
        op.drop_column(LOCATIONS, 'is_sea_zone')

    if PORT_INDEX in _index_names(bind):
        op.drop_index(PORT_INDEX, table_name=LOCATIONS)
    if 'is_port' in _columns(bind):
        op.drop_column(LOCATIONS, 'is_port')

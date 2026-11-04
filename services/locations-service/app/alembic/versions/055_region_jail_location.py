"""Region jail location (FEAT-198 §3.1).

* Regions.jail_location_id BIGINT NULL — the region's jail (assigned by an admin); NULL = the region has no
  jail, so the guards only fine or fight. FK Locations.id ON DELETE SET NULL, with its own index (MySQL
  gotcha). BIGINT to match Locations.id (same as entrance_location_id).

The law tables themselves belong to character-service (039_law); this service only owns the column.
No backfill. Downgrade drops the FK, the index and the column.

Revision ID: 055_region_jail_location
Revises: 054_reputation_gates
Create Date: 2026-11-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '055_region_jail_location'
down_revision = '054_reputation_gates'
branch_labels = None
depends_on = None

TABLE = 'Regions'
COLUMN = 'jail_location_id'
INDEX = 'ix_regions_jail_location_id'
FK = 'fk_regions_jail_location'


def _columns(bind) -> set:
    return {c['name'] for c in inspect(bind).get_columns(TABLE)}


def _indexes(bind) -> set:
    return {i['name'] for i in inspect(bind).get_indexes(TABLE)}


def _fks(bind) -> set:
    return {f['name'] for f in inspect(bind).get_foreign_keys(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if COLUMN not in _columns(bind):
        op.add_column(TABLE, sa.Column(COLUMN, sa.BigInteger(), nullable=True))
    if INDEX not in _indexes(bind):
        op.create_index(INDEX, TABLE, [COLUMN])
    if FK not in _fks(bind):
        op.create_foreign_key(FK, TABLE, 'Locations', [COLUMN], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    bind = op.get_bind()
    if FK in _fks(bind):
        op.drop_constraint(FK, TABLE, type_='foreignkey')
    if INDEX in _indexes(bind):
        op.drop_index(INDEX, table_name=TABLE)
    if COLUMN in _columns(bind):
        op.drop_column(TABLE, COLUMN)

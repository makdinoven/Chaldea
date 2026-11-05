"""Country prison district (FEAT-202 §3.1).

* Countries.prison_district_id BIGINT NULL — the country's prison (тюрьма страны): a district whose subtree
  (nested sub-districts + their locations) holds the heavy offenders; assigned by an admin, NULL = the
  country has no prison. FK Districts.id ON DELETE SET NULL, with its own index (MySQL gotcha). BIGINT to
  match Districts.id.

The law tables belong to character-service (042_country_prison); this service only owns the column.
No backfill. Downgrade drops the FK, the index and the column.

Revision ID: 057_country_prison_district
Revises: 056_quest_fame
Create Date: 2026-11-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '057_country_prison_district'
down_revision = '056_quest_fame'
branch_labels = None
depends_on = None

TABLE = 'Countries'
COLUMN = 'prison_district_id'
INDEX = 'ix_countries_prison_district_id'
FK = 'fk_countries_prison_district'


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
        op.create_foreign_key(FK, TABLE, 'Districts', [COLUMN], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    bind = op.get_bind()
    if FK in _fks(bind):
        op.drop_constraint(FK, TABLE, type_='foreignkey')
    if INDEX in _indexes(bind):
        op.drop_index(INDEX, table_name=TABLE)
    if COLUMN in _columns(bind):
        op.drop_column(TABLE, COLUMN)

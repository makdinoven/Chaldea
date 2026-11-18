"""Customs posts (FEAT-216): `Locations.is_customs` (+ index).

The admin marks a land location as a customs post («Таможня»). Legal caravans
crossing into the post's country stop there for inspection and duty;
contraband routes avoid it (character-service reads the flag by raw SQL with a
"column missing -> no posts" fallback). Ships' decks and sea zones never carry
the flag (validated in `crud.validate_customs_flag`).

Every step checks the schema first, so a half-applied run can be repeated.
Downgrade drops the index and the column (no data is kept).

Revision ID: 061_customs_posts
Revises: 060_sea_zones
Create Date: 2026-11-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '061_customs_posts'
down_revision = '060_sea_zones'
branch_labels = None
depends_on = None

LOCATIONS = 'Locations'
COLUMN = 'is_customs'
CUSTOMS_INDEX = 'ix_locations_is_customs'


def _columns(bind) -> set:
    return {c['name'] for c in inspect(bind).get_columns(LOCATIONS)}


def _index_names(bind) -> set:
    return {i['name'] for i in inspect(bind).get_indexes(LOCATIONS)}


def upgrade() -> None:
    bind = op.get_bind()
    if COLUMN not in _columns(bind):
        op.add_column(LOCATIONS, sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default='0'))
    if CUSTOMS_INDEX not in _index_names(bind):
        op.create_index(CUSTOMS_INDEX, LOCATIONS, [COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    if CUSTOMS_INDEX in _index_names(bind):
        op.drop_index(CUSTOMS_INDEX, table_name=LOCATIONS)
    if COLUMN in _columns(bind):
        op.drop_column(LOCATIONS, COLUMN)

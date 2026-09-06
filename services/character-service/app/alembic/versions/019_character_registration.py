"""Character registration overhaul (FEAT-154): origin, start location, in-game tenure.

Alter:
  character_requests + origin_id, start_location_id, skitaltsy_since_year,
                       skitaltsy_since_segment, rejection_reason
  characters         + origin_id, registered_at, skitaltsy_since_year,
                       skitaltsy_since_segment
  subraces           + distinctive_features, height_min, height_max,
                       typical_origin_ids

Every column is additive and NULLable with no server default, so an older
service image keeps running against the new schema (rollback-safe both ways).
No FK on origin_id: origin_countries is owned by locations-service.
No backfill: characters.registered_at stays NULL for NPCs and pre-existing rows.

Revision ID: 019_char_registration
Revises: 018_add_mob_packs
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa


revision = "019_char_registration"
down_revision = "018_add_mob_packs"
branch_labels = None
depends_on = None


# (table -> [(column name, type factory)]).  The type is built lazily so the
# same revision can be upgraded/downgraded repeatedly inside one process.
NEW_COLUMNS = {
    "character_requests": [
        ("origin_id", sa.Integer),
        ("start_location_id", sa.BigInteger),
        ("skitaltsy_since_year", sa.Integer),
        ("skitaltsy_since_segment", sa.SmallInteger),
        ("rejection_reason", sa.Text),
    ],
    "characters": [
        ("origin_id", sa.Integer),
        ("registered_at", sa.TIMESTAMP),
        ("skitaltsy_since_year", sa.Integer),
        ("skitaltsy_since_segment", sa.SmallInteger),
    ],
    "subraces": [
        ("distinctive_features", sa.Text),
        ("height_min", sa.Integer),
        ("height_max", sa.Integer),
        ("typical_origin_ids", sa.JSON),
    ],
}


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, columns in NEW_COLUMNS.items():
        if table not in inspector.get_table_names():
            continue
        for name, type_ in columns:
            if not _has_column(inspector, table, name):
                op.add_column(table, sa.Column(name, type_(), nullable=True, server_default=None))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, columns in NEW_COLUMNS.items():
        if table not in inspector.get_table_names():
            continue
        for name, _type in reversed(columns):
            if _has_column(inspector, table, name):
                op.drop_column(table, name)

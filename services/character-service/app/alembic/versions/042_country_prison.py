"""FEAT-202: the country prison (a district) next to the region guard station.

* `law_settings`:
  - `country_prison_min_level` — the wanted level code from which the country prison is preferred;
  - `country_escape_multiplier` — × the station escape chance (after its min/max clamp);
  - `country_escape_cooldown_hours` — the escape cooldown in the country prison (instead of `escape_cooldown_hours`).
* `law_jail_terms`: `facility` (`station` | `country`, VARCHAR not ENUM), `country_id`, `district_id` — the facility
  snapshot of the term (`region_id` keeps meaning the crime / wanted region).
* `characters.jail_district_id` — the movement whitelist snapshot (the prison district; consulted only while the
  activity-lock reason is `jail`).

No FKs to locations-service tables (039 convention). Every step is guarded (information_schema), so a re-run is a
no-op. Existing terms become `facility='station'` through the default; no backfill. Downgrade drops the 7 columns.

Revision ID: 042_country_prison
Revises: 041_stealth
"""

import sqlalchemy as sa
from alembic import op


revision = "042_country_prison"
down_revision = "041_stealth"
branch_labels = None
depends_on = None


_COLUMNS = [
    ("law_settings", "country_prison_min_level", "VARCHAR(20) NOT NULL DEFAULT 'villain'"),
    ("law_settings", "country_escape_multiplier", "DECIMAL(5,2) NOT NULL DEFAULT 0.50"),
    ("law_settings", "country_escape_cooldown_hours", "INT NOT NULL DEFAULT 12"),
    ("law_jail_terms", "facility", "VARCHAR(10) NOT NULL DEFAULT 'station'"),
    ("law_jail_terms", "country_id", "INT NULL"),
    ("law_jail_terms", "district_id", "INT NULL"),
    ("characters", "jail_district_id", "INT NULL"),
]


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def _has_table(conn, table: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t"
    ), {"t": table}).scalar())


def upgrade():
    conn = op.get_bind()
    for table, column, ddl in _COLUMNS:
        if _has_table(conn, table) and not _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def downgrade():
    conn = op.get_bind()
    for table, column, _ddl in reversed(_COLUMNS):
        if _has_table(conn, table) and _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

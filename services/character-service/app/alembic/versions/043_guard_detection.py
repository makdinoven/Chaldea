"""FEAT-203: guards do not always notice a wanted character (the guard-detection roll on entry).

* `law_settings`:
  - `detect_enabled` — off = the guards always notice (the FEAT-198 behaviour);
  - `detect_base_{safe,farm,dangerous,dungeon,default}_pct` — the base chance by `Locations.marker_type`
    (own columns, same initial values as the FEAT-201 witness bases);
  - `detect_per_guard_pct` — + per extra live guard (multiplicative);
  - `detect_mask_factor_pct` — × for a worn mask (fame does not count under a mask);
  - `detect_min_pct` / `detect_max_pct` — the clamp.
* `law_levels.detect_pct` — the severity multiplier, % (seeded 60/80/100/120/140 only when the column is added).

Every step is guarded (information_schema), so a re-run is a no-op. No ENUM, no FK. Downgrade drops the 11 columns
(values lost — acceptable pre-beta).

Revision ID: 043_guard_detection
Revises: 042_country_prison
"""

import sqlalchemy as sa
from alembic import op


revision = "043_guard_detection"
down_revision = "042_country_prison"
branch_labels = None
depends_on = None


_COLUMNS = [
    ("law_settings", "detect_enabled", "TINYINT(1) NOT NULL DEFAULT 1"),
    ("law_settings", "detect_base_safe_pct", "DECIMAL(5,2) NOT NULL DEFAULT 100.00"),
    ("law_settings", "detect_base_farm_pct", "DECIMAL(5,2) NOT NULL DEFAULT 70.00"),
    ("law_settings", "detect_base_dangerous_pct", "DECIMAL(5,2) NOT NULL DEFAULT 40.00"),
    ("law_settings", "detect_base_dungeon_pct", "DECIMAL(5,2) NOT NULL DEFAULT 25.00"),
    ("law_settings", "detect_base_default_pct", "DECIMAL(5,2) NOT NULL DEFAULT 50.00"),
    ("law_settings", "detect_per_guard_pct", "DECIMAL(5,2) NOT NULL DEFAULT 10.00"),
    ("law_settings", "detect_mask_factor_pct", "DECIMAL(5,2) NOT NULL DEFAULT 75.00"),
    ("law_settings", "detect_min_pct", "DECIMAL(5,2) NOT NULL DEFAULT 5.00"),
    ("law_settings", "detect_max_pct", "DECIMAL(5,2) NOT NULL DEFAULT 100.00"),
]

_LEVEL_COLUMN = ("law_levels", "detect_pct", "DECIMAL(5,2) NOT NULL DEFAULT 100.00")

_SEED_LEVELS = (
    "UPDATE law_levels SET detect_pct = CASE code WHEN 'suspect' THEN 60 WHEN 'offender' THEN 80 "
    "WHEN 'criminal' THEN 100 WHEN 'villain' THEN 120 WHEN 'enemy' THEN 140 ELSE 100 END"
)


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
    table, column, ddl = _LEVEL_COLUMN
    if _has_table(conn, table) and not _has_column(conn, table, column):
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        op.execute(_SEED_LEVELS)


def downgrade():
    conn = op.get_bind()
    for table, column, _ddl in [_LEVEL_COLUMN] + list(reversed(_COLUMNS)):
        if _has_table(conn, table) and _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

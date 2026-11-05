"""FEAT-204: guard patrols.

* `guard_patrols` — one patrol config per guard NPC (mode post / route / zone, style, zone source, interval, jitter,
  scheduling state: next_move_at, route_index / route_dir, last_location_id, last_moved_at);
* `guard_patrol_points` — ordered route points and zone locations (kind route | zone), both kept whatever the mode;
* `law_settings.patrols_enabled` — the global switch «Патрули стражи ходят»;
* `law_settings.patrol_encounter_hold_min` — how long an open encounter may hold a patrol guard in place (PM, 30 min);
* `law_encounters` index `ix_law_enc_guard (guard_npc_id, status)` — «is this guard held by an open encounter?».

Every step is guarded (information_schema), so a re-run is a no-op. No ENUM, no FK (the NPC delete cleans up
explicitly). Downgrade drops the index, the columns and both tables (configs lost — acceptable pre-beta).

Revision ID: 044_guard_patrols
Revises: 043_guard_detection
"""

import sqlalchemy as sa
from alembic import op


revision = "044_guard_patrols"
down_revision = "043_guard_detection"
branch_labels = None
depends_on = None


_CREATE_PATROLS = (
    "CREATE TABLE guard_patrols ("
    " npc_id INT NOT NULL,"
    " mode VARCHAR(10) NOT NULL DEFAULT 'post',"
    " route_style VARCHAR(10) NOT NULL DEFAULT 'loop',"
    " zone_kind VARCHAR(10) NOT NULL DEFAULT 'district',"
    " zone_district_id BIGINT NULL,"
    " interval_min SMALLINT NOT NULL DEFAULT 20,"
    " jitter_pct SMALLINT NOT NULL DEFAULT 25,"
    " next_move_at DATETIME NULL,"
    " route_index SMALLINT NOT NULL DEFAULT 0,"
    " route_dir SMALLINT NOT NULL DEFAULT 1,"
    " last_location_id BIGINT NULL,"
    " last_moved_at DATETIME NULL,"
    " updated_at DATETIME NOT NULL,"
    " updated_by_user_id INT NULL,"
    " PRIMARY KEY (npc_id),"
    " KEY ix_guard_patrols_due (mode, next_move_at)"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
)

_CREATE_POINTS = (
    "CREATE TABLE guard_patrol_points ("
    " id BIGINT NOT NULL AUTO_INCREMENT,"
    " npc_id INT NOT NULL,"
    " kind VARCHAR(10) NOT NULL,"
    " position SMALLINT NOT NULL,"
    " location_id BIGINT NOT NULL,"
    " PRIMARY KEY (id),"
    " UNIQUE KEY uq_guard_patrol_point (npc_id, kind, position),"
    " KEY ix_guard_patrol_point_loc (location_id)"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
)

_COLUMNS = [
    ("law_settings", "patrols_enabled", "TINYINT(1) NOT NULL DEFAULT 1"),
    ("law_settings", "patrol_encounter_hold_min", "INT NOT NULL DEFAULT 30"),
]

_INDEX = ("law_encounters", "ix_law_enc_guard", "(guard_npc_id, status)")


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def _has_table(conn, table: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t"
    ), {"t": table}).scalar())


def _has_index(conn, table: str, index: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = :t AND index_name = :i"
    ), {"t": table, "i": index}).scalar())


def upgrade():
    conn = op.get_bind()
    if not _has_table(conn, "guard_patrols"):
        op.execute(_CREATE_PATROLS)
    if not _has_table(conn, "guard_patrol_points"):
        op.execute(_CREATE_POINTS)
    for table, column, ddl in _COLUMNS:
        if _has_table(conn, table) and not _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    table, index, cols = _INDEX
    if _has_table(conn, table) and not _has_index(conn, table, index):
        op.execute(f"CREATE INDEX {index} ON {table} {cols}")


def downgrade():
    conn = op.get_bind()
    table, index, _cols = _INDEX
    if _has_table(conn, table) and _has_index(conn, table, index):
        op.execute(f"DROP INDEX {index} ON {table}")
    for table, column, _ddl in reversed(_COLUMNS):
        if _has_table(conn, table) and _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    for name in ("guard_patrol_points", "guard_patrols"):
        if _has_table(conn, name):
            op.execute(f"DROP TABLE {name}")

"""FEAT-214: sea storms and sea monster raids (features/FEAT-214 §3.3 CS).

* ``sea_settings`` + 19 global columns: the weather step base time, storm duration / movement / slowdown / drift /
  damage / departure postpone / sailor relief, the four season multipliers, raid chance / hold / repelled delay;
* ``sea_ships`` + 4 state columns: raid hold, postponed departure, storm delay of the current zone, sailor relief floor;
* ``sea_storm_seas`` — per-sea storm config keyed by the locations-service ``Regions.id`` of the sea;
* ``sea_storms`` / ``sea_storm_zones`` — storms and the zones they cover;
* ``sea_raids`` — one row per monster battle group on a deck.

No ENUM, no FK (style of the econ tables: zones / regions / ships / characters may disappear). Every step is guarded
(information_schema), so a re-run is a no-op. Downgrade drops the four tables and the 23 columns.

Revision ID: 053_sea_storms_raids
Revises: 052_sea_ships
"""

import sqlalchemy as sa
from alembic import op


revision = "053_sea_storms_raids"
down_revision = "052_sea_ships"
branch_labels = None
depends_on = None

_TAIL = ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

_SETTINGS_COLUMNS = [
    ("weather_last_run_at", "DATETIME NULL"),
    ("storm_min_minutes", "INT NOT NULL DEFAULT 60"),
    ("storm_max_minutes", "INT NOT NULL DEFAULT 180"),
    ("storm_move_pct", "DECIMAL(5,2) NOT NULL DEFAULT 30"),
    ("storm_max_moves", "INT NOT NULL DEFAULT 2"),
    ("storm_slow_mult", "DECIMAL(4,2) NOT NULL DEFAULT 2.00"),
    ("storm_drift_pct", "DECIMAL(5,2) NOT NULL DEFAULT 15"),
    ("storm_hp_pct", "DECIMAL(5,2) NOT NULL DEFAULT 10"),
    ("storm_stamina_pct", "DECIMAL(5,2) NOT NULL DEFAULT 20"),
    ("storm_postpone_minutes", "INT NOT NULL DEFAULT 15"),
    ("storm_postpone_max_minutes", "INT NOT NULL DEFAULT 240"),
    ("storm_sailor_relief_pct", "DECIMAL(5,2) NOT NULL DEFAULT 50"),
    ("season_mult_spring", "DECIMAL(4,2) NOT NULL DEFAULT 1.00"),
    ("season_mult_summer", "DECIMAL(4,2) NOT NULL DEFAULT 0.50"),
    ("season_mult_autumn", "DECIMAL(4,2) NOT NULL DEFAULT 1.50"),
    ("season_mult_winter", "DECIMAL(4,2) NOT NULL DEFAULT 2.00"),
    ("raid_chance_mult", "DECIMAL(4,2) NOT NULL DEFAULT 1.00"),
    ("raid_hold_max_minutes", "INT NOT NULL DEFAULT 120"),
    ("raid_repelled_delay_minutes", "INT NOT NULL DEFAULT 5"),
]

_SHIP_COLUMNS = [
    ("hold_until", "DATETIME NULL"),
    ("storm_hold_since", "DATETIME NULL"),
    ("storm_extra_minutes", "INT NOT NULL DEFAULT 0"),
    ("storm_post_floor_id", "BIGINT NULL"),
]

_TABLES = [
    ("sea_storm_seas", (
        "CREATE TABLE sea_storm_seas ("
        " region_id BIGINT NOT NULL,"
        " is_enabled TINYINT(1) NOT NULL DEFAULT 0,"
        " chance_per_hour_pct DECIMAL(5,2) NOT NULL DEFAULT 0,"
        " radius INT NOT NULL DEFAULT 1,"
        " updated_at DATETIME NOT NULL,"
        " PRIMARY KEY (region_id)" + _TAIL)),
    ("sea_storms", (
        "CREATE TABLE sea_storms ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " region_id BIGINT NULL,"
        " center_zone_id BIGINT NOT NULL,"
        " status VARCHAR(10) NOT NULL,"
        " source VARCHAR(10) NOT NULL,"
        " moves INT NOT NULL DEFAULT 0,"
        " started_at DATETIME NOT NULL,"
        " ends_at DATETIME NOT NULL,"
        " ended_at DATETIME NULL,"
        " PRIMARY KEY (id),"
        " KEY ix_sea_storms_active (status, ends_at),"
        " KEY ix_sea_storms_region (region_id, status)" + _TAIL)),
    ("sea_storm_zones", (
        "CREATE TABLE sea_storm_zones ("
        " storm_id BIGINT NOT NULL,"
        " zone_id BIGINT NOT NULL,"
        " PRIMARY KEY (storm_id, zone_id),"
        " KEY ix_sea_storm_zones_zone (zone_id)" + _TAIL)),
    ("sea_raids", (
        "CREATE TABLE sea_raids ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " ship_id BIGINT NOT NULL,"
        " attack_key VARCHAR(48) NOT NULL,"
        " group_no INT NOT NULL,"
        " deck_location_id BIGINT NOT NULL,"
        " zone_id BIGINT NOT NULL,"
        " mob_template_id INT NOT NULL,"
        " monster_name VARCHAR(255) NULL,"
        " player_ids JSON NOT NULL,"
        " placed_ids JSON NULL,"
        " mob_ids JSON NULL,"
        " battle_id BIGINT NULL,"
        " status VARCHAR(10) NOT NULL,"
        " mobs_despawned TINYINT(1) NOT NULL DEFAULT 0,"
        " created_at DATETIME NOT NULL,"
        " started_at DATETIME NULL,"
        " ended_at DATETIME NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_sea_raids_group (attack_key, group_no),"
        " KEY ix_sea_raids_ship (ship_id, status),"
        " KEY ix_sea_raids_status (status, created_at),"
        " KEY ix_sea_raids_battle (battle_id)" + _TAIL)),
]


def _has_table(conn, table: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t"
    ), {"t": table}).scalar())


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() "
        "AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def upgrade():
    conn = op.get_bind()
    for table, columns in (("sea_settings", _SETTINGS_COLUMNS), ("sea_ships", _SHIP_COLUMNS)):
        for name, ddl in columns:
            if not _has_column(conn, table, name):
                op.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    for name, ddl in _TABLES:
        if not _has_table(conn, name):
            op.execute(ddl)


def downgrade():
    conn = op.get_bind()
    for name, _ddl in reversed(_TABLES):
        if _has_table(conn, name):
            op.execute(f"DROP TABLE {name}")
    for table, columns in (("sea_ships", _SHIP_COLUMNS), ("sea_settings", _SETTINGS_COLUMNS)):
        for name, _ddl in reversed(columns):
            if _has_column(conn, table, name):
                op.execute(f"ALTER TABLE {table} DROP COLUMN {name}")

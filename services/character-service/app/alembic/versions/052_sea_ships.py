"""FEAT-213: sea routes — ships are real locations (features/FEAT-213 §3.3 CS).

* ``sea_ships`` — a ship bound 1:1 to a deck location (``Locations`` row of locations-service) and to a Captain NPC,
  with its schedule settings and its state (docked / sailing, current sea zone, trip counter, leg snapshot);
* ``sea_ship_stops`` — the ordered line of ports of a ship (+ an optional manual zone path per leg);
* ``sea_passes`` — the right to be aboard for a range of trips: ticket / sailor job / stowaway attempt;
* ``sea_settings`` — one seeded row (id = 1): the sea pass claim and the global sea numbers.

No ENUM, no FK (style of the econ tables: decks / ports / NPCs / characters may disappear). No ``characters`` column.
Every step is guarded (information_schema), so a re-run is a no-op. Downgrade drops the four tables.

Revision ID: 052_sea_ships
Revises: 051_caravan_escorts
"""

import sqlalchemy as sa
from alembic import op


revision = "052_sea_ships"
down_revision = "051_caravan_escorts"
branch_labels = None
depends_on = None

_TAIL = ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

_TABLES = [
    ("sea_ships", (
        "CREATE TABLE sea_ships ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " name VARCHAR(100) NOT NULL,"
        " captain_npc_id INT NULL,"
        " deck_location_id BIGINT NOT NULL,"
        " capacity INT NOT NULL DEFAULT 10,"
        " crew_slots INT NOT NULL DEFAULT 2,"
        " boarding_minutes INT NOT NULL DEFAULT 30,"
        " zone_minutes INT NOT NULL DEFAULT 10,"
        " fare_base INT NOT NULL DEFAULT 10,"
        " fare_per_zone INT NOT NULL DEFAULT 5,"
        " is_loop TINYINT(1) NOT NULL DEFAULT 0,"
        " is_active TINYINT(1) NOT NULL DEFAULT 1,"
        " status VARCHAR(10) NOT NULL DEFAULT 'docked',"
        " stop_index INT NOT NULL DEFAULT 0,"
        " next_stop_index INT NULL,"
        " direction TINYINT NOT NULL DEFAULT 1,"
        " trip_no INT NOT NULL DEFAULT 0,"
        " docked_port_id BIGINT NULL,"
        " next_port_id BIGINT NULL,"
        " current_zone_id BIGINT NULL,"
        " leg_path JSON NULL,"
        " leg_pos INT NOT NULL DEFAULT 0,"
        " departs_at DATETIME NULL,"
        " next_zone_at DATETIME NULL,"
        " last_port_id BIGINT NULL,"
        " blocked_reason VARCHAR(64) NULL,"
        " created_at DATETIME NOT NULL,"
        " updated_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_sea_ships_deck (deck_location_id),"
        " UNIQUE KEY uq_sea_ships_captain (captain_npc_id),"
        " KEY ix_sea_ships_depart (status, departs_at),"
        " KEY ix_sea_ships_sail (status, next_zone_at),"
        " KEY ix_sea_ships_port (docked_port_id),"
        " KEY ix_sea_ships_zone (current_zone_id)" + _TAIL)),
    ("sea_ship_stops", (
        "CREATE TABLE sea_ship_stops ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " ship_id BIGINT NOT NULL,"
        " idx INT NOT NULL,"
        " port_location_id BIGINT NOT NULL,"
        " path_override JSON NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_sea_ship_stops (ship_id, idx),"
        " KEY ix_sea_ship_stops_port (port_location_id)" + _TAIL)),
    ("sea_passes", (
        "CREATE TABLE sea_passes ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " ship_id BIGINT NOT NULL,"
        " character_id INT NOT NULL,"
        " kind VARCHAR(10) NOT NULL,"
        " first_trip INT NOT NULL,"
        " last_trip INT NOT NULL,"
        " from_port_id BIGINT NOT NULL,"
        " to_port_id BIGINT NOT NULL,"
        " from_name VARCHAR(255) NULL,"
        " to_name VARCHAR(255) NULL,"
        " zones INT NOT NULL DEFAULT 0,"
        " fare BIGINT NOT NULL DEFAULT 0,"
        " fare_op_id BIGINT NULL,"
        " refund_op_id BIGINT NULL,"
        " post_floor_id BIGINT NULL,"
        " status VARCHAR(12) NOT NULL,"
        " created_at DATETIME NOT NULL,"
        " ended_at DATETIME NULL,"
        " PRIMARY KEY (id),"
        " KEY ix_sea_passes_ship (ship_id, status, first_trip),"
        " KEY ix_sea_passes_char (character_id, status)" + _TAIL)),
    ("sea_settings", (
        "CREATE TABLE sea_settings ("
        " id INT NOT NULL,"
        " pass_last_run_at DATETIME NULL,"
        " sailor_post_min_chars INT NOT NULL DEFAULT 800,"
        " stowaway_base_pct DECIMAL(5,2) NOT NULL DEFAULT 60,"
        " stowaway_wanted_points INT NOT NULL DEFAULT 50,"
        " path_max_zones INT NOT NULL DEFAULT 200,"
        " PRIMARY KEY (id)" + _TAIL)),
]


def _has_table(conn, table: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t"
    ), {"t": table}).scalar())


def upgrade():
    conn = op.get_bind()
    for name, ddl in _TABLES:
        if not _has_table(conn, name):
            op.execute(ddl)
    conn.execute(sa.text(
        "INSERT INTO sea_settings (id) SELECT 1 FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM sea_settings WHERE id = 1)"))


def downgrade():
    conn = op.get_bind()
    for name, _ddl in reversed(_TABLES):
        if _has_table(conn, name):
            op.execute(f"DROP TABLE {name}")

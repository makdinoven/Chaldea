"""FEAT-215: sea caravans (features/FEAT-215 §3.2).

* ``econ_caravans`` + 12 sea columns: the sea stage (NULL = land caravan), the boarding-port split index in ``route``,
  boarding / landing ports, the ship that took the cargo, wait / board / unload timestamps, reserved and charged
  freight (+ its ``caravan_freight`` operation) and the units lost to sea monsters; two indexes;
* ``sea_ships.cargo_capacity`` — caravans per trip (0 = no cargo);
* ``sea_raids`` + ``caravan_ids`` (caravans in the hold when the attack was planned) and ``cargo_settled_at``;
* ``econ_caravan_sea_losses`` — one row per (caravan, monster attack): idempotency of the cargo loss.

Locations / ships: no FK (style of the econ tables). Every step is guarded (information_schema), so a re-run is a
no-op. Downgrade drops everything added.

Revision ID: 054_sea_caravans
Revises: 053_sea_storms_raids
"""

import sqlalchemy as sa
from alembic import op


revision = "054_sea_caravans"
down_revision = "053_sea_storms_raids"
branch_labels = None
depends_on = None

_TAIL = ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

_COLUMNS = [
    ("econ_caravans", "sea_stage", "VARCHAR(12) NULL"),
    ("econ_caravans", "sea_split_index", "INT NULL"),
    ("econ_caravans", "sea_board_port_id", "BIGINT NULL"),
    ("econ_caravans", "sea_alight_port_id", "BIGINT NULL"),
    ("econ_caravans", "sea_ship_id", "BIGINT NULL"),
    ("econ_caravans", "sea_waiting_since", "DATETIME NULL"),
    ("econ_caravans", "sea_boarded_at", "DATETIME NULL"),
    ("econ_caravans", "sea_unloaded_at", "DATETIME NULL"),
    ("econ_caravans", "freight", "INT NOT NULL DEFAULT 0"),
    ("econ_caravans", "freight_paid", "INT NOT NULL DEFAULT 0"),
    ("econ_caravans", "freight_op_id", "BIGINT NULL"),
    ("econ_caravans", "sunk_units", "DECIMAL(16,3) NOT NULL DEFAULT 0"),
    ("sea_ships", "cargo_capacity", "INT NOT NULL DEFAULT 2"),
    ("sea_raids", "caravan_ids", "JSON NULL"),
    ("sea_raids", "cargo_settled_at", "DATETIME NULL"),
]

_INDEXES = [
    ("econ_caravans", "ix_econ_caravans_sea_wait", "sea_stage, sea_board_port_id"),
    ("econ_caravans", "ix_econ_caravans_sea_ship", "sea_ship_id, sea_stage"),
]

_TABLES = [
    ("econ_caravan_sea_losses", (
        "CREATE TABLE econ_caravan_sea_losses ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " caravan_id BIGINT NOT NULL,"
        " ship_id BIGINT NULL,"
        " attack_key VARCHAR(48) NOT NULL,"
        " lost_groups INT NOT NULL DEFAULT 0,"
        " decided_groups INT NOT NULL DEFAULT 0,"
        " loss_pct DECIMAL(6,2) NOT NULL DEFAULT 0,"
        " units_lost DECIMAL(16,3) NOT NULL DEFAULT 0,"
        " created_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_caravan_sea_loss (caravan_id, attack_key),"
        " CONSTRAINT fk_econ_caravan_sea_losses_caravan FOREIGN KEY (caravan_id)"
        " REFERENCES econ_caravans (id) ON DELETE CASCADE" + _TAIL)),
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


def _has_index(conn, table: str, index: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = :t AND index_name = :i"
    ), {"t": table, "i": index}).scalar())


def upgrade():
    conn = op.get_bind()
    for table, column, ddl in _COLUMNS:
        if _has_table(conn, table) and not _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    for table, index, cols in _INDEXES:
        if _has_table(conn, table) and not _has_index(conn, table, index):
            op.execute(f"CREATE INDEX {index} ON {table} ({cols})")
    for name, ddl in _TABLES:
        if not _has_table(conn, name):
            op.execute(ddl)


def downgrade():
    conn = op.get_bind()
    for name, _ddl in reversed(_TABLES):
        if _has_table(conn, name):
            op.execute(f"DROP TABLE {name}")
    for table, index, _cols in reversed(_INDEXES):
        if _has_table(conn, table) and _has_index(conn, table, index):
            op.execute(f"DROP INDEX {index} ON {table}")
    for table, column, _ddl in reversed(_COLUMNS):
        if _has_table(conn, table) and _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

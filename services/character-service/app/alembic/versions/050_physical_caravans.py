"""FEAT-211: physical caravans and raids (features/FEAT-211 §3.15).

* ``econ_caravans`` + physical state: ``is_physical``, ``route`` (JSON list of Locations ids), ``route_index``,
  ``current_location_id``, ``next_move_at``, ``arrived_at``, ``hold_started_at``, ``guard_count``, ``stolen_units``,
  ``raid_paid``; indexes ``ix_econ_caravans_move`` / ``ix_econ_caravans_loc``;
* ``econ_caravan_raids`` (one raid per caravan, UNIQUE caravan_id), ``econ_caravan_raid_shares`` (per raider);
* ``econ_caravan_guard_templates`` (pool of guard mob templates, FK mob_templates ON DELETE CASCADE);
* ``econ_regions.trade_gate_location_id`` (admin override of the region trade gate, no FK — LS table);
* ``econ_fences`` (settings of fence NPCs, role ``fence``);
* ``econ_sim_settings.caravan_pass_last_run_at`` (claim of the caravan pass);
* builtin reputation action ``caravan_attack`` gets ``has_source = 1`` (raids now apply it).

No ENUM; cross-service ids (locations, regions, battles, characters) have no FK. Every step is guarded
(information_schema), so a re-run is a no-op. Downgrade drops everything above (data loss accepted pre-beta; a raided
caravan still in transit would break the escrow sub-invariant after a downgrade — documented).

Revision ID: 050_physical_caravans
Revises: 049_mob_admin_ready
"""

import sqlalchemy as sa
from alembic import op


revision = "050_physical_caravans"
down_revision = "049_mob_admin_ready"
branch_labels = None
depends_on = None

_TAIL = ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

# builtin reputation actions whose has_source flips to 1 here (reputation_core.DEFAULT_ACTIONS follows)
HAS_SOURCE_ACTIONS = ("caravan_attack",)

_COLUMNS = [
    ("econ_caravans", "is_physical", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("econ_caravans", "route", "JSON NULL"),
    ("econ_caravans", "route_index", "SMALLINT NOT NULL DEFAULT 0"),
    ("econ_caravans", "current_location_id", "BIGINT NULL"),
    ("econ_caravans", "next_move_at", "DATETIME NULL"),
    ("econ_caravans", "arrived_at", "DATETIME NULL"),
    ("econ_caravans", "hold_started_at", "DATETIME NULL"),
    ("econ_caravans", "guard_count", "SMALLINT NOT NULL DEFAULT 0"),
    ("econ_caravans", "stolen_units", "DECIMAL(16,3) NOT NULL DEFAULT 0"),
    ("econ_caravans", "raid_paid", "BIGINT NOT NULL DEFAULT 0"),
    ("econ_regions", "trade_gate_location_id", "BIGINT NULL"),
    ("econ_sim_settings", "caravan_pass_last_run_at", "DATETIME NULL"),
]

_INDEXES = [
    ("econ_caravans", "ix_econ_caravans_move", "is_physical, status, next_move_at"),
    ("econ_caravans", "ix_econ_caravans_loc", "current_location_id, status"),
]

_TABLES = [
    ("econ_caravan_raids", (
        "CREATE TABLE econ_caravan_raids ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " caravan_id BIGINT NOT NULL,"
        " leader_character_id INT NOT NULL,"
        " is_group TINYINT(1) NOT NULL DEFAULT 0,"
        " location_id BIGINT NOT NULL,"
        " region_id BIGINT NULL,"
        " status VARCHAR(16) NOT NULL,"
        " battle_id INT NULL,"
        " attacker_ids JSON NULL,"
        " guard_ids JSON NULL,"
        " guard_template_id INT NULL,"
        " guard_mult DECIMAL(6,3) NULL,"
        " marks BIGINT NOT NULL DEFAULT 0,"
        " stolen_units DECIMAL(16,3) NOT NULL DEFAULT 0,"
        " stolen_value BIGINT NOT NULL DEFAULT 0,"
        " bales INT NOT NULL DEFAULT 0,"
        " payout_op_id BIGINT NULL,"
        " law_done TINYINT(1) NOT NULL DEFAULT 0,"
        " guards_despawned TINYINT(1) NOT NULL DEFAULT 0,"
        " created_at DATETIME NOT NULL,"
        " started_at DATETIME NULL,"
        " finished_at DATETIME NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_econ_caravan_raids_caravan (caravan_id),"
        " KEY ix_econ_caravan_raids_battle (battle_id),"
        " KEY ix_econ_caravan_raids_status (status, id)" + _TAIL)),
    ("econ_caravan_raid_shares", (
        "CREATE TABLE econ_caravan_raid_shares ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " raid_id BIGINT NOT NULL,"
        " character_id INT NOT NULL,"
        " marks BIGINT NOT NULL DEFAULT 0,"
        " bales INT NOT NULL DEFAULT 0,"
        " bale_item_id INT NULL,"
        " bales_delivered_at DATETIME NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_econ_caravan_raid_shares (raid_id, character_id)" + _TAIL)),
    ("econ_caravan_guard_templates", (
        "CREATE TABLE econ_caravan_guard_templates ("
        " mob_template_id INT NOT NULL,"
        " created_at DATETIME NOT NULL,"
        " PRIMARY KEY (mob_template_id),"
        " CONSTRAINT fk_econ_caravan_guard_tpl FOREIGN KEY (mob_template_id) REFERENCES mob_templates (id)"
        " ON DELETE CASCADE" + _TAIL)),
    ("econ_fences", (
        "CREATE TABLE econ_fences ("
        " npc_id INT NOT NULL,"
        " is_active TINYINT(1) NOT NULL DEFAULT 1,"
        " price_pct SMALLINT NOT NULL DEFAULT 40,"
        " accepted_groups JSON NULL,"
        " cash_target BIGINT NOT NULL DEFAULT 2000,"
        " updated_at DATETIME NULL,"
        " updated_by INT NULL,"
        " PRIMARY KEY (npc_id)" + _TAIL)),
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


def _has_index(conn, table: str, index: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = :t AND index_name = :i"
    ), {"t": table, "i": index}).scalar())


def _set_has_source(conn, value: int) -> None:
    if not _has_table(conn, "reputation_actions"):
        return
    for code in HAS_SOURCE_ACTIONS:
        conn.execute(sa.text("UPDATE reputation_actions SET has_source = :v WHERE code = :c"),
                     {"v": int(value), "c": code})


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
    _set_has_source(conn, 1)


def downgrade():
    conn = op.get_bind()
    _set_has_source(conn, 0)
    for name, _ddl in reversed(_TABLES):
        if _has_table(conn, name):
            op.execute(f"DROP TABLE {name}")
    for table, index, _cols in reversed(_INDEXES):
        if _has_table(conn, table) and _has_index(conn, table, index):
            op.execute(f"DROP INDEX {index} ON {table}")
    for table, column, _ddl in reversed(_COLUMNS):
        if _has_table(conn, table) and _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

"""FEAT-216: customs posts and smuggling (features/FEAT-216 §3.4).

* ``econ_caravans`` + 12 columns: the contraband flag and its markup, the customs post on the route (index + location),
  the inspection state / end, the duty paid physically at the post (+ its ``caravan_duty`` operation), the open
  detection alert (officer + deadline) and where a seized caravan was confiscated; index ``(is_contraband, status)``;
* ``econ_caravan_raids`` + ``kind`` (raid | customs | patrol), ``officer_paid`` and the ``seized_done`` followup claim
  (``uq_econ_caravan_raids_caravan`` stays: one fight per caravan, whatever the kind);
* ``econ_country_bans`` — goods groups a country forbids to import (no FK, ``econ_mints`` style);
* ``econ_customs_officers`` — players' customs jobs (no activity lock);
* builtin reputation action ``customs_seizure`` (``reputation_core.DEFAULT_ACTIONS``) and the NPC kill weight of the
  ``customs`` role (``reputation_core.DEFAULT_NPC_ROLE_WEIGHTS``) — the weight row only when the table already has
  role rows (an empty table means "code defaults", which already contain it).

No ENUM, no FK. Every step is guarded (information_schema), so a re-run is a no-op. Downgrade drops everything added.

Revision ID: 055_customs_smuggling
Revises: 054_sea_caravans
"""

import sqlalchemy as sa
from alembic import op


revision = "055_customs_smuggling"
down_revision = "054_sea_caravans"
branch_labels = None
depends_on = None

_TAIL = ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

# (code, name, points, daily_cap, has_source, sort_order) — mirrors reputation_core.DEFAULT_ACTIONS
ACTIONS = (
    ("customs_seizure", "Конфискация контрабанды", 20, None, 1, 57),
)

# (role, points) — mirrors reputation_core.DEFAULT_NPC_ROLE_WEIGHTS
ROLE_WEIGHTS = (
    ("customs", -300),
)

_COLUMNS = [
    ("econ_caravans", "is_contraband", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("econ_caravans", "markup_pct", "DECIMAL(6,2) NULL"),
    ("econ_caravans", "customs_index", "INT NULL"),
    ("econ_caravans", "customs_location_id", "BIGINT NULL"),
    ("econ_caravans", "customs_state", "VARCHAR(16) NULL"),
    ("econ_caravans", "customs_until", "DATETIME NULL"),
    ("econ_caravans", "duty_paid", "INT NOT NULL DEFAULT 0"),
    ("econ_caravans", "duty_op_id", "BIGINT NULL"),
    ("econ_caravans", "customs_alert_officer_id", "INT NULL"),
    ("econ_caravans", "customs_alert_until", "DATETIME NULL"),
    ("econ_caravans", "seized_region_id", "INT NULL"),
    ("econ_caravans", "seized_country_id", "INT NULL"),
    ("econ_caravan_raids", "kind", "VARCHAR(16) NOT NULL DEFAULT 'raid'"),
    ("econ_caravan_raids", "officer_paid", "BIGINT NOT NULL DEFAULT 0"),
    ("econ_caravan_raids", "seized_done", "TINYINT(1) NOT NULL DEFAULT 0"),
]

_INDEXES = [
    ("econ_caravans", "ix_econ_caravans_contraband", "is_contraband, status"),
]

_TABLES = [
    ("econ_country_bans", (
        "CREATE TABLE econ_country_bans ("
        " country_id INT NOT NULL,"
        " group_code VARCHAR(32) NOT NULL,"
        " created_at DATETIME NOT NULL,"
        " PRIMARY KEY (country_id, group_code)" + _TAIL)),
    ("econ_customs_officers", (
        "CREATE TABLE econ_customs_officers ("
        " character_id INT NOT NULL,"
        " country_id INT NOT NULL,"
        " npc_id INT NULL,"
        " location_id BIGINT NULL,"
        " status VARCHAR(16) NOT NULL,"
        " enlisted_at DATETIME NOT NULL,"
        " ended_at DATETIME NULL,"
        " seizures INT NOT NULL DEFAULT 0,"
        " earned BIGINT NOT NULL DEFAULT 0,"
        " PRIMARY KEY (character_id),"
        " KEY ix_econ_customs_officers_country (status, country_id)" + _TAIL)),
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
    if _has_table(conn, "reputation_actions"):
        for code, name, points, cap, has_source, order in ACTIONS:
            conn.execute(sa.text(
                "INSERT INTO reputation_actions (code, name, points, daily_cap, is_builtin, has_source, sort_order) "
                "SELECT :c, :n, :p, :cap, 1, :src, :o FROM DUAL "
                "WHERE NOT EXISTS (SELECT 1 FROM reputation_actions WHERE code = :c)"),
                {"c": code, "n": name, "p": points, "cap": cap, "src": has_source, "o": order})
    if _has_table(conn, "reputation_npc_role_weights") and conn.execute(sa.text(
            "SELECT COUNT(*) FROM reputation_npc_role_weights")).scalar():
        for role, points in ROLE_WEIGHTS:
            conn.execute(sa.text(
                "INSERT INTO reputation_npc_role_weights (role, points) SELECT :r, :p FROM DUAL "
                "WHERE NOT EXISTS (SELECT 1 FROM reputation_npc_role_weights WHERE role = :r)"),
                {"r": role, "p": points})


def downgrade():
    conn = op.get_bind()
    if _has_table(conn, "reputation_npc_role_weights"):
        for role, _points in ROLE_WEIGHTS:
            conn.execute(sa.text("DELETE FROM reputation_npc_role_weights WHERE role = :r"), {"r": role})
    if _has_table(conn, "reputation_actions"):
        for code, *_rest in ACTIONS:
            conn.execute(sa.text("DELETE FROM reputation_actions WHERE code = :c"), {"c": code})
    for name, _ddl in reversed(_TABLES):
        if _has_table(conn, name):
            op.execute(f"DROP TABLE {name}")
    for table, index, _cols in reversed(_INDEXES):
        if _has_table(conn, table) and _has_index(conn, table, index):
            op.execute(f"DROP INDEX {index} ON {table}")
    for table, column, _ddl in reversed(_COLUMNS):
        if _has_table(conn, table) and _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

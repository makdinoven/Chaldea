"""FEAT-212: player escorts of physical caravans (features/FEAT-212 §3.3).

* ``characters.escort_caravan_id`` (activity lock reason ``caravan_escort``) + index ``ix_characters_escort_caravan``;
* ``econ_caravan_escorts`` (one row per caravan x character, UNIQUE = no rejoin after «Сойти»);
* ``econ_caravan_messages`` (the caravan channel, escorts only);
* ``econ_caravan_raids.escort_ids`` (JSON) and ``faction_done`` (followup claim); existing raids are marked
  ``faction_done = 1`` (no retroactive faction points);
* builtin reputation actions ``caravan_escort`` / ``caravan_defense`` (``reputation_core.DEFAULT_ACTIONS``).

No ENUM, no FK (style of the econ tables). Every step is guarded (information_schema), so a re-run is a no-op.
Downgrade drops everything above (active escorts simply lose the lock; pre-beta data loss accepted).

Revision ID: 051_caravan_escorts
Revises: 050_physical_caravans
"""

import sqlalchemy as sa
from alembic import op


revision = "051_caravan_escorts"
down_revision = "050_physical_caravans"
branch_labels = None
depends_on = None

_TAIL = ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

# (code, name, points, daily_cap, has_source, sort_order) — mirrors reputation_core.DEFAULT_ACTIONS
ACTIONS = (
    ("caravan_escort", "Охрана каравана", 10, 40, 1, 55),
    ("caravan_defense", "Отбит налёт на караван", 25, None, 1, 56),
)

_COLUMNS = [
    ("characters", "escort_caravan_id", "BIGINT NULL"),
    ("econ_caravan_raids", "escort_ids", "JSON NULL"),
    ("econ_caravan_raids", "faction_done", "TINYINT(1) NOT NULL DEFAULT 0"),
]

_INDEXES = [
    ("characters", "ix_characters_escort_caravan", "escort_caravan_id"),
]

_TABLES = [
    ("econ_caravan_escorts", (
        "CREATE TABLE econ_caravan_escorts ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " caravan_id BIGINT NOT NULL,"
        " character_id INT NOT NULL,"
        " status VARCHAR(16) NOT NULL,"
        " hire_location_id BIGINT NULL,"
        " in_raid TINYINT(1) NOT NULL DEFAULT 0,"
        " fee BIGINT NOT NULL DEFAULT 0,"
        " bonus BIGINT NOT NULL DEFAULT 0,"
        " payout_op_id BIGINT NULL,"
        " rewards_done TINYINT(1) NOT NULL DEFAULT 0,"
        " joined_at DATETIME NOT NULL,"
        " ended_at DATETIME NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_caravan_escort (caravan_id, character_id),"
        " KEY ix_econ_caravan_escorts_char (character_id, status),"
        " KEY ix_econ_caravan_escorts_rewards (status, rewards_done)" + _TAIL)),
    ("econ_caravan_messages", (
        "CREATE TABLE econ_caravan_messages ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " caravan_id BIGINT NOT NULL,"
        " character_id INT NOT NULL,"
        " body VARCHAR(500) NOT NULL,"
        " created_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " KEY ix_econ_caravan_messages_caravan (caravan_id, id),"
        " KEY ix_econ_caravan_messages_char (character_id, created_at)" + _TAIL)),
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


def upgrade():
    conn = op.get_bind()
    raids_had_flag = _has_table(conn, "econ_caravan_raids") and _has_column(conn, "econ_caravan_raids",
                                                                            "faction_done")
    for table, column, ddl in _COLUMNS:
        if _has_table(conn, table) and not _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    for table, index, cols in _INDEXES:
        if _has_table(conn, table) and not _has_index(conn, table, index):
            op.execute(f"CREATE INDEX {index} ON {table} ({cols})")
    for name, ddl in _TABLES:
        if not _has_table(conn, name):
            op.execute(ddl)
    if not raids_had_flag and _has_table(conn, "econ_caravan_raids"):
        # no retroactive faction points for raids settled before this deploy
        conn.execute(sa.text("UPDATE econ_caravan_raids SET faction_done = 1"))
    if _has_table(conn, "reputation_actions"):
        for code, name, points, cap, has_source, order in ACTIONS:
            conn.execute(sa.text(
                "INSERT INTO reputation_actions (code, name, points, daily_cap, is_builtin, has_source, sort_order) "
                "SELECT :c, :n, :p, :cap, 1, :src, :o FROM DUAL "
                "WHERE NOT EXISTS (SELECT 1 FROM reputation_actions WHERE code = :c)"),
                {"c": code, "n": name, "p": points, "cap": cap, "src": has_source, "o": order})


def downgrade():
    conn = op.get_bind()
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

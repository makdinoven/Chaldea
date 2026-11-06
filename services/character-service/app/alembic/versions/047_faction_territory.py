"""FEAT-207: factions — stage 3 (territory, rank passives, enemies, outlaw regions, item donations).
features/FEAT-207 §3.2.

* ``faction_access_rules`` — closed locations / dungeons (one faction per target, optional minimum rank);
* ``faction_ranks`` + ``passive_name`` / ``passive_description`` / ``passive_modifiers`` (battle-time passive);
* ``faction_enemies`` (mob template / NPC / «members of hostile factions» -> points), ``factions.kill_points_daily_cap``
  (per-faction override), ``faction_donation_days.kill_points`` (own day counter), ``faction_pvp_kills`` (24 h rule);
* ``faction_outlaw_regions`` (membership = crime in a region, severity = law level code);
* ``faction_item_stock`` (donated items waiting for the tick sale);
* ``faction_settings`` + kill cap / PvP repeat hours / outlaw check cooldown / item sale share;
* ``faction_economy.last_item_sales``, ``faction_econ_history.item_sales`` / ``items_sold``.

No ENUM; FK columns carry explicit indexes; cross-service ids (locations, dungeons, regions, items, mob templates) have
no FK. Every step is guarded (information_schema), so a re-run is a no-op. Downgrade drops the tables in reverse order
and the added columns (data loss accepted pre-beta).

Revision ID: 047_faction_territory
Revises: 046_faction_economy
"""

import sqlalchemy as sa
from alembic import op


revision = "047_faction_territory"
down_revision = "046_faction_economy"
branch_labels = None
depends_on = None

_TAIL = ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

_COLUMNS = [
    ("faction_ranks", "passive_name", "VARCHAR(100) NULL"),
    ("faction_ranks", "passive_description", "VARCHAR(500) NULL"),
    ("faction_ranks", "passive_modifiers", "JSON NULL"),
    ("factions", "kill_points_daily_cap", "INT NULL"),
    ("faction_donation_days", "kill_points", "INT NOT NULL DEFAULT 0"),
    ("faction_settings", "kill_points_daily_cap", "INT NOT NULL DEFAULT 50"),
    ("faction_settings", "pvp_kill_repeat_hours", "INT NOT NULL DEFAULT 24"),
    ("faction_settings", "outlaw_check_cooldown_hours", "INT NOT NULL DEFAULT 24"),
    ("faction_settings", "econ_item_sale_share_pct", "INT NOT NULL DEFAULT 2"),
    ("faction_economy", "last_item_sales", "BIGINT NOT NULL DEFAULT 0"),
    ("faction_econ_history", "item_sales", "BIGINT NOT NULL DEFAULT 0"),
    ("faction_econ_history", "items_sold", "INT NOT NULL DEFAULT 0"),
]

_TABLES = [
    ("faction_access_rules", (
        "CREATE TABLE faction_access_rules ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " kind VARCHAR(10) NOT NULL,"
        " target_id BIGINT NOT NULL,"
        " faction_id INT NOT NULL,"
        " min_rank_id INT NULL,"
        " created_at DATETIME NOT NULL,"
        " updated_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_access_target (kind, target_id),"
        " KEY ix_faction_access_faction (faction_id),"
        " KEY ix_faction_access_rank (min_rank_id),"
        " CONSTRAINT fk_faction_access_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_access_rank FOREIGN KEY (min_rank_id) REFERENCES faction_ranks (id)"
        " ON DELETE RESTRICT" + _TAIL)),
    ("faction_enemies", (
        "CREATE TABLE faction_enemies ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " faction_id INT NOT NULL,"
        " kind VARCHAR(10) NOT NULL,"
        " ref_id BIGINT NOT NULL DEFAULT 0,"
        " points INT NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_enemy (faction_id, kind, ref_id),"
        " CONSTRAINT fk_faction_enemy_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_pvp_kills", (
        "CREATE TABLE faction_pvp_kills ("
        " character_id INT NOT NULL,"
        " faction_id INT NOT NULL,"
        " victim_id INT NOT NULL,"
        " last_at DATETIME NOT NULL,"
        " PRIMARY KEY (character_id, faction_id, victim_id),"
        " KEY ix_faction_pvp_kills_faction (faction_id),"
        " KEY ix_faction_pvp_kills_victim (victim_id),"
        " CONSTRAINT fk_faction_pvp_character FOREIGN KEY (character_id) REFERENCES characters (id)"
        " ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_pvp_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_pvp_victim FOREIGN KEY (victim_id) REFERENCES characters (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_outlaw_regions", (
        "CREATE TABLE faction_outlaw_regions ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " faction_id INT NOT NULL,"
        " region_id BIGINT NOT NULL,"
        " level_code VARCHAR(16) NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_outlaw_region (faction_id, region_id),"
        " KEY ix_faction_outlaw_region (region_id),"
        " CONSTRAINT fk_faction_outlaw_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_item_stock", (
        "CREATE TABLE faction_item_stock ("
        " faction_id INT NOT NULL,"
        " item_id INT NOT NULL,"
        " quantity INT NOT NULL DEFAULT 0,"
        " updated_at DATETIME NOT NULL,"
        " PRIMARY KEY (faction_id, item_id),"
        " CONSTRAINT fk_faction_item_stock_faction FOREIGN KEY (faction_id) REFERENCES factions (id)"
        " ON DELETE CASCADE" + _TAIL)),
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
    for name, ddl in _TABLES:
        if not _has_table(conn, name):
            op.execute(ddl)


def downgrade():
    conn = op.get_bind()
    for name, _ddl in reversed(_TABLES):
        if _has_table(conn, name):
            op.execute(f"DROP TABLE {name}")
    for table, column, _ddl in reversed(_COLUMNS):
        if _has_table(conn, table) and _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

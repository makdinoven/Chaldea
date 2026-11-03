"""FEAT-197: region reputation (stage 1).

* `character_reputation`        — value per (character, region); no row = 0 («Скиталец»). `decay_at` is the anchor of
                                  the negative decay (NULL when value >= 0). FK characters ON DELETE CASCADE.
* `reputation_log`              — every change (origin + echo rows share `event_key`; UNIQUE(event_key, region_id) is
                                  the idempotency guarantee). FK characters ON DELETE CASCADE.
* `reputation_settings`         — single row id=1: range, echo %, decay points/day, decay pass throttle.
* `reputation_tiers`            — exactly 8 rows with fixed codes (names / thresholds / price modifiers editable).
* `reputation_actions`          — action -> points (+ optional daily cap); builtin rows are referenced from code.
* `reputation_npc_role_weights` — NPC kill weight per `characters.npc_role` ('*' = any other / NULL role).
* columns: `characters.reputation_min_tier` (NPC gate), `characters.reputation_kill_points` (per-NPC kill weight),
           `econ_banks.loan_min_reputation_tier`, `teleport_links.min_reputation_tier`.

No FK to Regions (owned by locations-service). The FK columns lead an index (MySQL FK-index gotcha). No ENUM.
Every statement is re-runnable (MySQL DDL is not transactional: tables use IF NOT EXISTS, column adds check
information_schema first, seeds insert only missing keys). Downgrade drops exactly what was added.

Revision ID: 038_reputation
Revises: 037_econ_social_classes
"""

import sqlalchemy as sa
from alembic import op


revision = "038_reputation"
down_revision = "037_econ_social_classes"
branch_labels = None
depends_on = None


_TABLE_OPTS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"

# table -> [(column, DDL)]
_COLUMNS = {
    "characters": [
        ("reputation_min_tier", "VARCHAR(20) NULL"),
        ("reputation_kill_points", "INT NULL"),
    ],
    "econ_banks": [("loan_min_reputation_tier", "VARCHAR(20) NULL")],
    "teleport_links": [("min_reputation_tier", "VARCHAR(20) NULL")],
}

# code, sort_order, name, min_value, price_pct, sell_pct, trade_refused (user decision 2026-11-03, §3.14 A1)
TIERS = [
    ("outlaw", 1, "Вне закона", None, 0, 0, 1),
    ("outcast", 2, "Изгой", -599, -25, -25, 0),
    ("watched", 3, "На заметке", -299, -10, -10, 0),
    ("wanderer", 4, "Скиталец", -99, 0, 0, 0),
    ("familiar", 5, "Знакомое лицо", 100, 0, 0, 0),
    ("trusted", 6, "Свой человек", 300, 5, 0, 0),
    ("defender", 7, "Заступник", 600, 10, 0, 0),
    ("legend", 8, "Легенда края", 900, 15, 0, 0),
]

# code, name, points, daily_cap, has_source, sort_order (all builtin)
ACTIONS = [
    ("quest_complete", "Выполнено задание", 10, None, 1, 10),
    ("guild_delivery", "Поставка по заказу гильдии", 2, 20, 1, 20),
    ("npc_kill", "Убийство жителя", 0, None, 1, 30),
    ("region_event_help", "Помощь краю", 5, None, 0, 40),
    ("caravan_attack", "Нападение на караван", -100, None, 0, 50),
    ("crime", "Преступление", -50, None, 0, 60),
    ("admin_manual", "Решение властей", 0, None, 0, 70),
]

_PEACEFUL = ("merchant", "blacksmith", "alchemist", "bard", "sage", "priest", "healer", "hunter", "wanderer",
             "auctioneer", "banker", "minter", "guild", "teleport_master", "hero")
ROLE_WEIGHTS = [("bandit", 20), ("mercenary", -30), ("guard", -300), ("ruler", -1000), ("king", -1000)] + \
               [(role, -150) for role in _PEACEFUL] + [("*", -150)]


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def upgrade():
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS character_reputation (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            character_id INT NOT NULL,
            region_id INT NOT NULL,
            value INT NOT NULL DEFAULT 0,
            decay_at DATETIME NULL,
            updated_at DATETIME NOT NULL,
            UNIQUE KEY uq_char_rep (character_id, region_id),
            KEY ix_char_rep_decay (decay_at),
            CONSTRAINT fk_char_rep_character FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS reputation_log (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            character_id INT NOT NULL,
            region_id INT NOT NULL,
            action VARCHAR(40) NOT NULL,
            event_key VARCHAR(191) NOT NULL,
            is_echo TINYINT(1) NOT NULL DEFAULT 0,
            origin_region_id INT NULL,
            requested_delta INT NOT NULL,
            applied_delta INT NOT NULL,
            value_after INT NOT NULL,
            tier_before VARCHAR(20) NOT NULL,
            tier_after VARCHAR(20) NOT NULL,
            reason VARCHAR(500) NULL,
            actor_user_id INT NULL,
            created_at DATETIME NOT NULL,
            UNIQUE KEY uq_rep_log_event (event_key, region_id),
            KEY ix_rep_log_char (character_id, created_at),
            KEY ix_rep_log_cap (character_id, region_id, action, created_at),
            CONSTRAINT fk_rep_log_character FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS reputation_settings (
            id INT NOT NULL PRIMARY KEY,
            min_value INT NOT NULL DEFAULT -1000,
            max_value INT NOT NULL DEFAULT 1000,
            echo_pct DECIMAL(5,2) NOT NULL DEFAULT 20.00,
            decay_per_day DECIMAL(8,2) NOT NULL DEFAULT 10.00,
            decay_last_run_at DATETIME NULL,
            updated_at DATETIME NOT NULL
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS reputation_tiers (
            code VARCHAR(20) NOT NULL PRIMARY KEY,
            sort_order INT NOT NULL,
            name VARCHAR(60) NOT NULL,
            min_value INT NULL,
            price_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
            sell_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
            trade_refused TINYINT(1) NOT NULL DEFAULT 0,
            UNIQUE KEY uq_rep_tiers_sort (sort_order)
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS reputation_actions (
            code VARCHAR(40) NOT NULL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            points INT NOT NULL DEFAULT 0,
            daily_cap INT NULL,
            is_builtin TINYINT(1) NOT NULL DEFAULT 0,
            has_source TINYINT(1) NOT NULL DEFAULT 0,
            sort_order INT NOT NULL DEFAULT 0
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS reputation_npc_role_weights (
            role VARCHAR(50) NOT NULL PRIMARY KEY,
            points INT NOT NULL
        ) {_TABLE_OPTS}
    """)

    conn = op.get_bind()
    for table, columns in _COLUMNS.items():
        for column, ddl in columns:
            if not _has_column(conn, table, column):
                op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # seeds (only missing keys)
    conn.execute(sa.text(
        "INSERT INTO reputation_settings (id, min_value, max_value, echo_pct, decay_per_day, updated_at) "
        "SELECT 1, -1000, 1000, 20.00, 10.00, UTC_TIMESTAMP() FROM DUAL "
        "WHERE NOT EXISTS (SELECT 1 FROM reputation_settings WHERE id = 1)"))
    for code, order, name, min_value, price, sell, refused in TIERS:
        conn.execute(sa.text(
            "INSERT INTO reputation_tiers (code, sort_order, name, min_value, price_pct, sell_pct, trade_refused) "
            "SELECT :c, :o, :n, :m, :p, :s, :r FROM DUAL "
            "WHERE NOT EXISTS (SELECT 1 FROM reputation_tiers WHERE code = :c)"),
            {"c": code, "o": order, "n": name, "m": min_value, "p": price, "s": sell, "r": refused})
    for code, name, points, cap, has_source, order in ACTIONS:
        conn.execute(sa.text(
            "INSERT INTO reputation_actions (code, name, points, daily_cap, is_builtin, has_source, sort_order) "
            "SELECT :c, :n, :p, :cap, 1, :src, :o FROM DUAL "
            "WHERE NOT EXISTS (SELECT 1 FROM reputation_actions WHERE code = :c)"),
            {"c": code, "n": name, "p": points, "cap": cap, "src": has_source, "o": order})
    for role, points in ROLE_WEIGHTS:
        conn.execute(sa.text(
            "INSERT INTO reputation_npc_role_weights (role, points) SELECT :r, :p FROM DUAL "
            "WHERE NOT EXISTS (SELECT 1 FROM reputation_npc_role_weights WHERE role = :r)"),
            {"r": role, "p": points})


def downgrade():
    conn = op.get_bind()
    for table, columns in reversed(list(_COLUMNS.items())):
        for column, _ddl in reversed(columns):
            if _has_column(conn, table, column):
                op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    op.execute("DROP TABLE IF EXISTS reputation_npc_role_weights")
    op.execute("DROP TABLE IF EXISTS reputation_actions")
    op.execute("DROP TABLE IF EXISTS reputation_tiers")
    op.execute("DROP TABLE IF EXISTS reputation_settings")
    op.execute("DROP TABLE IF EXISTS reputation_log")
    op.execute("DROP TABLE IF EXISTS character_reputation")

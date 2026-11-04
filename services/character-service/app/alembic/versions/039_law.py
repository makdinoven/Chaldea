"""FEAT-198: law — wanted level, guards, jail (reputation stage 2a).

* `character_wanted` — wanted value per (character, region), lazy linear decay from `decay_at` (NULL at 0).
* `law_settings`     — single row id=1: scale, decay, flee / escape formulas, timeouts, bail multiplier, pass claim.
* `law_levels`       — exactly 5 severity levels with fixed codes (name / threshold / fine / jail term editable).
* `law_crimes`       — crime events (idempotent `event_key`; the stage 2b witness step slots in by `status`).
* `law_encounters`   — a guard stopping a wanted / outlaw character; `from_location_id` + `cooldown_until` serve the
                       flee rule (§3.14-ANSWERED A7: back to the origin, no new stop there for 1 h).
* `law_jail_terms`   — jail terms (serving / served / bailed / escaped / released).
* `law_log`          — journal of every law change (idempotent `event_key`).
* columns on `characters`: `jailed_until`, `jail_region_id`, `law_encounter_id` (activity-lock reasons `jail` and
  `law_encounter`; no FK on `law_encounter_id` to avoid a cycle).

No FK to Regions / Locations (owned by locations-service). Every FK column leads an index (MySQL FK-index gotcha).
Re-runnable: tables use IF NOT EXISTS, column adds check information_schema first, seeds insert only missing keys.
Downgrade drops exactly what was added. No backfill: everyone starts with wanted 0.

Revision ID: 039_law
Revises: 038_reputation
"""

import sqlalchemy as sa
from alembic import op


revision = "039_law"
down_revision = "038_reputation"
branch_labels = None
depends_on = None


_TABLE_OPTS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"

_CHARACTER_COLUMNS = [
    ("jailed_until", "DATETIME NULL"),
    ("jail_region_id", "INT NULL"),
    ("law_encounter_id", "INT NULL"),
]

# code, sort_order, name, min_value, fine, jail_hours (§3.14-ANSWERED A1)
LEVELS = [
    ("suspect", 1, "Подозреваемый", 1, 50, 2),
    ("offender", 2, "Нарушитель", 100, 150, 12),
    ("criminal", 3, "Преступник", 300, 400, 24),
    ("villain", 4, "Злодей", 600, 1000, 72),
    ("enemy", 5, "Враг края", 900, 2500, 168),
]

_TABLES_DROP_ORDER = ("law_log", "law_jail_terms", "law_encounters", "law_crimes", "law_levels", "law_settings",
                      "character_wanted")


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def upgrade():
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS character_wanted (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            character_id INT NOT NULL,
            region_id INT NOT NULL,
            value INT NOT NULL DEFAULT 0,
            decay_at DATETIME NULL,
            updated_at DATETIME NOT NULL,
            UNIQUE KEY uq_char_wanted (character_id, region_id),
            KEY ix_char_wanted_region (region_id),
            CONSTRAINT fk_char_wanted_character FOREIGN KEY (character_id) REFERENCES characters (id)
                ON DELETE CASCADE
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS law_settings (
            id INT NOT NULL PRIMARY KEY,
            max_wanted INT NOT NULL DEFAULT 1000,
            decay_per_day DECIMAL(8,2) NOT NULL DEFAULT 50.00,
            heavy_wanted INT NOT NULL DEFAULT 600,
            outlaw_min_level VARCHAR(20) NOT NULL DEFAULT 'criminal',
            encounter_timeout_hours INT NOT NULL DEFAULT 24,
            guard_ko_hours INT NOT NULL DEFAULT 6,
            flee_base_pct DECIMAL(5,2) NOT NULL DEFAULT 20.00,
            flee_per_point_pct DECIMAL(6,3) NOT NULL DEFAULT 0.250,
            flee_min_pct DECIMAL(5,2) NOT NULL DEFAULT 5.00,
            flee_max_pct DECIMAL(5,2) NOT NULL DEFAULT 85.00,
            escape_base_pct DECIMAL(5,2) NOT NULL DEFAULT 5.00,
            escape_per_point_pct DECIMAL(6,3) NOT NULL DEFAULT 0.150,
            escape_min_pct DECIMAL(5,2) NOT NULL DEFAULT 2.00,
            escape_max_pct DECIMAL(5,2) NOT NULL DEFAULT 50.00,
            escape_cooldown_hours INT NOT NULL DEFAULT 6,
            escape_fail_extend_pct DECIMAL(5,2) NOT NULL DEFAULT 50.00,
            max_remaining_jail_hours INT NOT NULL DEFAULT 168,
            bail_multiplier DECIMAL(5,2) NOT NULL DEFAULT 2.00,
            pass_last_run_at DATETIME NULL,
            updated_at DATETIME NOT NULL
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS law_levels (
            code VARCHAR(20) NOT NULL PRIMARY KEY,
            sort_order INT NOT NULL,
            name VARCHAR(60) NOT NULL,
            min_value INT NOT NULL,
            fine INT NOT NULL,
            jail_hours INT NOT NULL,
            UNIQUE KEY uq_law_levels_sort (sort_order)
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS law_crimes (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            event_key VARCHAR(191) NOT NULL,
            crime_type VARCHAR(30) NOT NULL,
            character_id INT NOT NULL,
            region_id INT NOT NULL,
            location_id INT NULL,
            victim_character_id INT NULL,
            battle_id INT NULL,
            wanted_points INT NOT NULL,
            wanted_applied INT NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL,
            created_at DATETIME NOT NULL,
            resolved_at DATETIME NULL,
            UNIQUE KEY uq_law_crime_key (event_key),
            KEY ix_law_crime_char (character_id, created_at),
            KEY ix_law_crime_status (status),
            CONSTRAINT fk_law_crime_character FOREIGN KEY (character_id) REFERENCES characters (id)
                ON DELETE CASCADE
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS law_encounters (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            character_id INT NOT NULL,
            region_id INT NOT NULL,
            location_id INT NOT NULL,
            from_location_id INT NULL,
            guard_npc_id INT NULL,
            is_outlaw TINYINT(1) NOT NULL,
            has_jail TINYINT(1) NOT NULL,
            level_code VARCHAR(20) NOT NULL,
            wanted_value INT NOT NULL,
            fine INT NOT NULL,
            jail_hours INT NOT NULL,
            flee_used TINYINT(1) NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL,
            battle_id INT NULL,
            source VARCHAR(20) NOT NULL,
            created_at DATETIME NOT NULL,
            expires_at DATETIME NOT NULL,
            fight_started_at DATETIME NULL,
            resolved_at DATETIME NULL,
            cooldown_until DATETIME NULL,
            KEY ix_law_enc_char (character_id, created_at),
            KEY ix_law_enc_status (status, expires_at),
            KEY ix_law_enc_battle (battle_id),
            KEY ix_law_enc_cooldown (character_id, location_id, cooldown_until),
            CONSTRAINT fk_law_enc_character FOREIGN KEY (character_id) REFERENCES characters (id)
                ON DELETE CASCADE
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS law_jail_terms (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            character_id INT NOT NULL,
            region_id INT NOT NULL,
            location_id INT NOT NULL,
            encounter_id INT NULL,
            level_code VARCHAR(20) NOT NULL,
            fine_base INT NOT NULL,
            bail_price INT NOT NULL,
            started_at DATETIME NOT NULL,
            until DATETIME NOT NULL,
            status VARCHAR(20) NOT NULL,
            escape_attempts INT NOT NULL DEFAULT 0,
            next_escape_at DATETIME NULL,
            bailed_by_character_id INT NULL,
            resolved_at DATETIME NULL,
            notified TINYINT(1) NOT NULL DEFAULT 0,
            KEY ix_law_jail_char (character_id, status),
            KEY ix_law_jail_status (status, until),
            CONSTRAINT fk_law_jail_character FOREIGN KEY (character_id) REFERENCES characters (id)
                ON DELETE CASCADE
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS law_log (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            event_key VARCHAR(191) NOT NULL,
            character_id INT NOT NULL,
            region_id INT NULL,
            action VARCHAR(30) NOT NULL,
            wanted_before INT NULL,
            wanted_after INT NULL,
            amount INT NULL,
            chance_pct DECIMAL(5,2) NULL,
            roll_pct DECIMAL(5,2) NULL,
            ref_id INT NULL,
            reason VARCHAR(500) NULL,
            actor_user_id INT NULL,
            created_at DATETIME NOT NULL,
            UNIQUE KEY uq_law_log_key (event_key),
            KEY ix_law_log_char (character_id, created_at),
            CONSTRAINT fk_law_log_character FOREIGN KEY (character_id) REFERENCES characters (id)
                ON DELETE CASCADE
        ) {_TABLE_OPTS}
    """)

    conn = op.get_bind()
    for column, ddl in _CHARACTER_COLUMNS:
        if not _has_column(conn, "characters", column):
            op.execute(f"ALTER TABLE characters ADD COLUMN {column} {ddl}")

    conn.execute(sa.text(
        "INSERT INTO law_settings (id, updated_at) SELECT 1, UTC_TIMESTAMP() FROM DUAL "
        "WHERE NOT EXISTS (SELECT 1 FROM law_settings WHERE id = 1)"))
    for code, order, name, min_value, fine, hours in LEVELS:
        conn.execute(sa.text(
            "INSERT INTO law_levels (code, sort_order, name, min_value, fine, jail_hours) "
            "SELECT :c, :o, :n, :m, :f, :h FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM law_levels WHERE code = :c)"),
            {"c": code, "o": order, "n": name, "m": min_value, "f": fine, "h": hours})


def downgrade():
    conn = op.get_bind()
    for column, _ddl in reversed(_CHARACTER_COLUMNS):
        if _has_column(conn, "characters", column):
            op.execute(f"ALTER TABLE characters DROP COLUMN {column}")
    for table in _TABLES_DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table}")

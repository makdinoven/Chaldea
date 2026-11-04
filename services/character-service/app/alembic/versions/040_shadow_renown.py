"""FEAT-199: the shadow — witnesses, hidden crimes, masks, region suspicion, fame and infamy (reputation stage 2b).

* `law_crimes` gets the deferred-crime snapshot (reputation delta + exact idem key + reason, wanted floor, mask flag,
  witness chance / roll, reveal deadline, next daily reveal roll, attempts, revealed_at) and the index
  `ix_law_crime_reveal (status, next_roll_at)` for the reveal step of the law pass.
  Statuses (VARCHAR, no ENUM): reported | unwitnessed | masked | closed. Existing rows stay `reported`.
* `shadow_settings`   — single row id=1: witness / reveal / suspicion / infamy / fame weights.
* `region_suspicion`  — suspicion per region (lazy linear decay from `decay_at`, NULL at 0). No FK (Regions).
* `character_renown`  — fame (public as a tier) and infamy (owner + staff) per character.
* `renown_tiers`      — 5 fixed codes per scale (`fame` / `infamy`); name / threshold / witness_pct editable.
* `renown_log`        — journal of every renown change (idempotent `event_key`).

Every FK column leads an index or the PK (MySQL FK-index gotcha). Re-runnable: tables use IF NOT EXISTS, column
adds check information_schema first, seeds insert only missing keys. Downgrade drops exactly what was added.

Revision ID: 040_shadow_renown
Revises: 039_law
"""

import sqlalchemy as sa
from alembic import op


revision = "040_shadow_renown"
down_revision = "039_law"
branch_labels = None
depends_on = None


_TABLE_OPTS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"

_CRIME_COLUMNS = [
    ("reputation_delta", "INT NULL"),
    ("reputation_key", "VARCHAR(191) NULL"),
    ("reputation_reason", "VARCHAR(255) NULL"),
    ("wanted_floor", "INT NULL"),
    ("masked", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("witness_chance_pct", "DECIMAL(5,2) NULL"),
    ("witness_roll_pct", "DECIMAL(5,2) NULL"),
    ("reveal_until", "DATETIME NULL"),
    ("next_roll_at", "DATETIME NULL"),
    ("reveal_attempts", "INT NOT NULL DEFAULT 0"),
    ("revealed_at", "DATETIME NULL"),
]

# scale, code, sort_order, name, min_value, witness_pct (§3.1)
TIERS = [
    ("fame", "nameless", 1, "Безвестный", 0, 0),
    ("fame", "familiar", 2, "Знакомое имя", 50, 2),
    ("fame", "known", 3, "Известный", 200, 5),
    ("fame", "famous", 4, "Знаменитый", 600, 10),
    ("fame", "legend", 5, "Легенда", 1500, 15),
    ("infamy", "none", 1, "О вас не говорят", 0, 0),
    ("infamy", "whispers", 2, "Шёпот в тавернах", 100, 0),
    ("infamy", "rumored", 3, "О вас ходят слухи", 400, 0),
    ("infamy", "notorious", 4, "Дурная слава", 1000, 0),
    ("infamy", "dreaded", 5, "Имя, которое произносят шёпотом", 2500, 0),
]

_TABLES_DROP_ORDER = ("renown_log", "renown_tiers", "character_renown", "region_suspicion", "shadow_settings")


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def _has_index(conn, table: str, index: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = :t AND index_name = :i"
    ), {"t": table, "i": index}).scalar())


def upgrade():
    conn = op.get_bind()
    for column, ddl in _CRIME_COLUMNS:
        if not _has_column(conn, "law_crimes", column):
            op.execute(f"ALTER TABLE law_crimes ADD COLUMN {column} {ddl}")
    if not _has_index(conn, "law_crimes", "ix_law_crime_reveal"):
        op.execute("CREATE INDEX ix_law_crime_reveal ON law_crimes (status, next_roll_at)")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS shadow_settings (
            id INT NOT NULL PRIMARY KEY,
            witness_enabled TINYINT(1) NOT NULL DEFAULT 1,
            witness_base_safe_pct DECIMAL(5,2) NOT NULL DEFAULT 70.00,
            witness_base_farm_pct DECIMAL(5,2) NOT NULL DEFAULT 45.00,
            witness_base_dangerous_pct DECIMAL(5,2) NOT NULL DEFAULT 25.00,
            witness_base_dungeon_pct DECIMAL(5,2) NOT NULL DEFAULT 15.00,
            witness_base_default_pct DECIMAL(5,2) NOT NULL DEFAULT 50.00,
            witness_stealth_per_point_pct DECIMAL(6,3) NOT NULL DEFAULT 0.100,
            witness_agent_pct DECIMAL(5,2) NOT NULL DEFAULT 10.00,
            witness_assassin_pct DECIMAL(5,2) NOT NULL DEFAULT 15.00,
            witness_trickster_pct DECIMAL(5,2) NOT NULL DEFAULT 15.00,
            witness_mask_pct DECIMAL(5,2) NOT NULL DEFAULT 10.00,
            witness_group_per_extra_pct DECIMAL(5,2) NOT NULL DEFAULT 10.00,
            witness_min_pct DECIMAL(5,2) NOT NULL DEFAULT 5.00,
            witness_max_pct DECIMAL(5,2) NOT NULL DEFAULT 95.00,
            reveal_days INT NOT NULL DEFAULT 3,
            reveal_base_pct DECIMAL(5,2) NOT NULL DEFAULT 15.00,
            reveal_per_suspicion_pct DECIMAL(6,3) NOT NULL DEFAULT 0.400,
            reveal_mask_factor_pct DECIMAL(5,2) NOT NULL DEFAULT 50.00,
            reveal_min_pct DECIMAL(5,2) NOT NULL DEFAULT 1.00,
            reveal_max_pct DECIMAL(5,2) NOT NULL DEFAULT 90.00,
            suspicion_max INT NOT NULL DEFAULT 100,
            suspicion_unwitnessed INT NOT NULL DEFAULT 10,
            suspicion_masked INT NOT NULL DEFAULT 20,
            suspicion_decay_per_day DECIMAL(8,2) NOT NULL DEFAULT 5.00,
            suspicion_uneasy_at INT NOT NULL DEFAULT 20,
            suspicion_alarmed_at INT NOT NULL DEFAULT 50,
            suspicion_fear_at INT NOT NULL DEFAULT 80,
            infamy_ratio DECIMAL(6,3) NOT NULL DEFAULT 1.000,
            infamy_min_gain INT NOT NULL DEFAULT 10,
            fame_quest_default INT NOT NULL DEFAULT 5,
            fame_rep_ratio DECIMAL(6,3) NOT NULL DEFAULT 0.500,
            fame_guild_ratio DECIMAL(6,3) NOT NULL DEFAULT 0.000,
            updated_at DATETIME NOT NULL
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS region_suspicion (
            region_id INT NOT NULL PRIMARY KEY,
            value INT NOT NULL DEFAULT 0,
            decay_at DATETIME NULL,
            updated_at DATETIME NOT NULL
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS character_renown (
            character_id INT NOT NULL PRIMARY KEY,
            fame INT NOT NULL DEFAULT 0,
            infamy INT NOT NULL DEFAULT 0,
            updated_at DATETIME NOT NULL,
            CONSTRAINT fk_char_renown_character FOREIGN KEY (character_id) REFERENCES characters (id)
                ON DELETE CASCADE
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS renown_tiers (
            scale VARCHAR(10) NOT NULL,
            code VARCHAR(20) NOT NULL,
            sort_order INT NOT NULL,
            name VARCHAR(60) NOT NULL,
            min_value INT NOT NULL,
            witness_pct DECIMAL(5,2) NOT NULL DEFAULT 0.00,
            PRIMARY KEY (scale, code),
            UNIQUE KEY uq_renown_tier_order (scale, sort_order)
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS renown_log (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            event_key VARCHAR(191) NOT NULL,
            character_id INT NOT NULL,
            scale VARCHAR(10) NOT NULL,
            source VARCHAR(30) NOT NULL,
            delta INT NOT NULL,
            value_after INT NOT NULL,
            tier_before VARCHAR(20) NOT NULL,
            tier_after VARCHAR(20) NOT NULL,
            ref_id BIGINT NULL,
            reason VARCHAR(500) NULL,
            actor_user_id INT NULL,
            created_at DATETIME NOT NULL,
            UNIQUE KEY uq_renown_log_key (event_key),
            KEY ix_renown_log_char (character_id, created_at),
            CONSTRAINT fk_renown_log_character FOREIGN KEY (character_id) REFERENCES characters (id)
                ON DELETE CASCADE
        ) {_TABLE_OPTS}
    """)

    conn.execute(sa.text(
        "INSERT INTO shadow_settings (id, updated_at) SELECT 1, UTC_TIMESTAMP() FROM DUAL "
        "WHERE NOT EXISTS (SELECT 1 FROM shadow_settings WHERE id = 1)"))
    for scale, code, order, name, min_value, witness in TIERS:
        conn.execute(sa.text(
            "INSERT INTO renown_tiers (scale, code, sort_order, name, min_value, witness_pct) "
            "SELECT :s, :c, :o, :n, :m, :w FROM DUAL "
            "WHERE NOT EXISTS (SELECT 1 FROM renown_tiers WHERE scale = :s AND code = :c)"),
            {"s": scale, "c": code, "o": order, "n": name, "m": min_value, "w": witness})


def downgrade():
    conn = op.get_bind()
    for table in _TABLES_DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table}")
    if _has_index(conn, "law_crimes", "ix_law_crime_reveal"):
        op.execute("DROP INDEX ix_law_crime_reveal ON law_crimes")
    for column, _ddl in reversed(_CRIME_COLUMNS):
        if _has_column(conn, "law_crimes", column):
            op.execute(f"ALTER TABLE law_crimes DROP COLUMN {column}")

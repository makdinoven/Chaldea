"""FEAT-191: the mint (one per country, in its capital) and the season quota.

* `econ_mints`        — per-country mint settings: manual capital override (NULL = auto: the single region of the
                        country with the 'capital' template), season limit override (NULL = sim param
                        `mint_season_limit`), enabled flag. No FK (Countries / Regions are owned by locations-service).
* `econ_mint_items`   — ore accepted from players at a «Монетчик» NPC, with marks per piece. No FK to items
                        (same convention as econ_item_groups).
* `econ_mint_seasons` — the lockable shared season limit counter of a country (court + players), one row per
                        (country, game season index). Rows are tiny and never purged.

New sim params (`quota_season_amount`, `mint_season_limit`, `mint_court_marks_per_unit`,
`mint_court_threshold_pct`) and op types (`mint_court`, `mint_player`, `season_quota`) need no migration.

No FKs -> no FK-index pitfalls. Every statement is re-runnable (MySQL DDL is not transactional). Nothing seeded.
Downgrade drops the three tables (settings and counters are lost; ledger operations stay).

Revision ID: 034_econ_mint
Revises: 033_econ_region_events
"""

from alembic import op


revision = "034_econ_mint"
down_revision = "033_econ_region_events"
branch_labels = None
depends_on = None


_TABLE_OPTS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"


def upgrade():
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS econ_mints (
            country_id INT NOT NULL PRIMARY KEY,
            capital_region_id INT NULL,
            season_limit BIGINT NULL,
            is_enabled TINYINT(1) NOT NULL DEFAULT 1,
            updated_at DATETIME NULL,
            updated_by INT NULL
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS econ_mint_items (
            item_id INT NOT NULL PRIMARY KEY,
            marks_per_item INT NOT NULL,
            is_enabled TINYINT(1) NOT NULL DEFAULT 1,
            updated_at DATETIME NULL,
            updated_by INT NULL
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS econ_mint_seasons (
            country_id INT NOT NULL,
            period_index INT NOT NULL,
            minted_court BIGINT NOT NULL DEFAULT 0,
            minted_players BIGINT NOT NULL DEFAULT 0,
            ore_units_court DECIMAL(16,3) NOT NULL DEFAULT 0,
            ore_units_players DECIMAL(16,3) NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NULL,
            PRIMARY KEY (country_id, period_index)
        ) {_TABLE_OPTS}
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS econ_mint_seasons")
    op.execute("DROP TABLE IF EXISTS econ_mint_items")
    op.execute("DROP TABLE IF EXISTS econ_mints")

"""FEAT-193: guild orders (economy stage 5c).

* `econ_guild_orders`  — one opening of a region's order for a goods group (history kept). `open_key`
                         ('r<region>:<group>') is set only while the order is open; its UNIQUE key allows many
                         NULLs, so at most one OPEN order exists per region / group. No FK (Regions are owned by
                         locations-service).
* `econ_guild_xp_days` — per character and UTC day: the base guild XP already granted (the daily cap).
* `econ_regions.guild_budget` / `guild_food_budget` — the per-recount allowance of the guild (shares of the
                         residents' purse / the positive treasury for food), lockable with the region row.

New sim params (`guild_*`) and the op type `guild_order` need no migration.

No FKs -> no FK-index pitfalls; no ENUM. Every statement is re-runnable (MySQL DDL is not transactional; the
column adds check information_schema first). Nothing seeded: budgets stay 0 until the first recount, so no order
exists and nothing can be handed in before it. Downgrade drops the two columns and both tables (ledger operations
and granted XP stay).

Revision ID: 036_econ_guild_orders
Revises: 035_econ_caravans
"""

import sqlalchemy as sa
from alembic import op


revision = "036_econ_guild_orders"
down_revision = "035_econ_caravans"
branch_labels = None
depends_on = None


_TABLE_OPTS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
_BUDGET_COLUMNS = ("guild_budget", "guild_food_budget")


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def upgrade():
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS econ_guild_orders (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            region_id INT NOT NULL,
            group_code VARCHAR(32) NOT NULL,
            open_key VARCHAR(48) NULL,
            status VARCHAR(16) NOT NULL,
            close_reason VARCHAR(32) NULL,
            units_total DECIMAL(16,3) NOT NULL,
            units_left DECIMAL(16,3) NOT NULL,
            units_filled DECIMAL(16,3) NOT NULL DEFAULT 0,
            price_mult DECIMAL(10,3) NOT NULL,
            markup_pct DECIMAL(6,2) NOT NULL,
            pieces INT NOT NULL DEFAULT 0,
            paid_total BIGINT NOT NULL DEFAULT 0,
            paid_treasury BIGINT NOT NULL DEFAULT 0,
            hand_ins INT NOT NULL DEFAULT 0,
            opened_run_id INT NOT NULL,
            last_run_id INT NOT NULL,
            closed_run_id INT NULL,
            opened_at DATETIME NOT NULL,
            updated_at DATETIME NULL,
            closed_at DATETIME NULL,
            UNIQUE KEY uq_econ_guild_orders_open (open_key),
            KEY ix_econ_guild_orders_region (region_id, status),
            KEY ix_econ_guild_orders_status (status, id),
            KEY ix_econ_guild_orders_closed (closed_at)
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS econ_guild_xp_days (
            character_id INT NOT NULL,
            day DATE NOT NULL,
            xp INT NOT NULL DEFAULT 0,
            PRIMARY KEY (character_id, day)
        ) {_TABLE_OPTS}
    """)
    conn = op.get_bind()
    for column in _BUDGET_COLUMNS:
        if not _has_column(conn, "econ_regions", column):
            op.execute(f"ALTER TABLE econ_regions ADD COLUMN {column} BIGINT NOT NULL DEFAULT 0")


def downgrade():
    conn = op.get_bind()
    for column in reversed(_BUDGET_COLUMNS):
        if _has_column(conn, "econ_regions", column):
            op.execute(f"ALTER TABLE econ_regions DROP COLUMN {column}")
    op.execute("DROP TABLE IF EXISTS econ_guild_xp_days")
    op.execute("DROP TABLE IF EXISTS econ_guild_orders")

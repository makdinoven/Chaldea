"""FEAT-192: NPC caravans (economy stage 5b).

* `econ_trade_pairs` — symmetric trade permission of two countries (`country_a < country_b`, enforced by the app)
                       with the import duty in percent. No row = trade forbidden (default 10 % when enabled).
                       No FK (Countries are owned by locations-service).
* `econ_caravans`    — one caravan: route, goods group, units, agreed price, value / duty and who paid it, travel
                       counters and status (in_transit | delivered | cancelled). The UNIQUE dispatch key is the
                       idempotency marker of a resumed run; rows are kept as history (future «газета»).

New sim params (`caravans_enabled`, `caravan_*`) and op types (`caravan_dispatch`, `caravan_delivery`,
`caravan_cancel`) plus the singleton account `caravan_escrow` need no migration (created lazily).

No FKs -> no FK-index pitfalls; no ENUM. Every statement is re-runnable (MySQL DDL is not transactional). Nothing
seeded. Downgrade drops both tables (ledger operations stay). Before a downgrade with caravans on the road set
`caravans_enabled = 0` and wait until nothing is in transit — otherwise their money stays in «Караваны в пути».

Revision ID: 035_econ_caravans
Revises: 034_econ_mint
"""

from alembic import op


revision = "035_econ_caravans"
down_revision = "034_econ_mint"
branch_labels = None
depends_on = None


_TABLE_OPTS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"


def upgrade():
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS econ_trade_pairs (
            country_a INT NOT NULL,
            country_b INT NOT NULL,
            is_enabled TINYINT(1) NOT NULL DEFAULT 0,
            duty_pct DECIMAL(5,2) NOT NULL DEFAULT 10.00,
            updated_at DATETIME NULL,
            updated_by INT NULL,
            PRIMARY KEY (country_a, country_b)
        ) {_TABLE_OPTS}
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS econ_caravans (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            dispatch_run_id INT NOT NULL,
            from_region_id INT NOT NULL,
            to_region_id INT NOT NULL,
            from_country_id INT NOT NULL,
            to_country_id INT NOT NULL,
            group_code VARCHAR(32) NOT NULL,
            units DECIMAL(16,3) NOT NULL,
            unit_price DECIMAL(14,4) NOT NULL,
            value BIGINT NOT NULL,
            duty BIGINT NOT NULL DEFAULT 0,
            duty_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
            paid_purse BIGINT NOT NULL DEFAULT 0,
            paid_treasury BIGINT NOT NULL DEFAULT 0,
            travel_runs TINYINT NOT NULL,
            runs_left TINYINT NOT NULL,
            last_run_id INT NOT NULL,
            status VARCHAR(16) NOT NULL,
            cancel_reason VARCHAR(32) NULL,
            goods_returned TINYINT(1) NULL,
            dispatch_op_id BIGINT NULL,
            finish_op_id BIGINT NULL,
            created_at DATETIME NOT NULL,
            finished_at DATETIME NULL,
            finished_run_id INT NULL,
            UNIQUE KEY uq_econ_caravans_dispatch (dispatch_run_id, from_region_id, to_region_id, group_code),
            KEY ix_econ_caravans_status (status, id),
            KEY ix_econ_caravans_to (to_region_id, status),
            KEY ix_econ_caravans_from (from_region_id, status),
            KEY ix_econ_caravans_finished (finished_at)
        ) {_TABLE_OPTS}
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS econ_caravans")
    op.execute("DROP TABLE IF EXISTS econ_trade_pairs")

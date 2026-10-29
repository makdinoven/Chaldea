"""FEAT-184 stage 4: banks — one bank per region, player deposits and loans.

Tables (all owned by character-service; no FK to Regions / characters — other owners, the deletion
hook and the tick's orphan purge close the rows):
* `econ_banks`     — one row per bank region: «Банк есть» flag, deposit-rate factor, residents'
                     aggregate deposits / loans (numbers; money moves population_purse <-> bank),
                     accrual clock, one-time capital seed marker, last pass guard + stats.
* `bank_deposits`  — player deposits (demand / term). `demand_owner_id` = character_id while the
                     row is an open demand deposit, else NULL -> UNIQUE (region_id, demand_owner_id)
                     allows one open demand deposit per character and bank (NULLs are free).
* `bank_loans`     — player loans. `active_character_id` = character_id while active|overdue, else
                     NULL -> UNIQUE gives one open loan per character.

Money lives in the ledger: accounts `bank` (the bank's own money) and `bank_deposits` (the vault of
player deposits), ref = region id (econ_core). No data migration: banks start empty, every region
starts without a bank. Sim params (20 `bank_*` keys) need no migration — missing keys of the stored
params JSON fall back to econ_sim.SimParams defaults.

FK columns get explicit indexes (MySQL would otherwise create implicit ones that a later DROP INDEX
cannot remove). Every statement is re-runnable (CREATE TABLE IF NOT EXISTS) because MySQL DDL is not
transactional. Downgrade drops the three tables; the `bank` / `bank_deposits` ledger accounts and
their postings stay — downgrade only with empty banks.

Revision ID: 031_econ_banks
Revises: 030_currency_short_mark
"""

from alembic import op
import sqlalchemy as sa


revision = "031_econ_banks"
down_revision = "030_currency_short_mark"
branch_labels = None
depends_on = None


_TABLE_OPTS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_banks (
          region_id           BIGINT        NOT NULL PRIMARY KEY,
          is_enabled          TINYINT(1)    NOT NULL DEFAULT 0,
          deposit_rate_factor DECIMAL(5,4)  NOT NULL DEFAULT 1.0000,
          resident_deposits   BIGINT        NOT NULL DEFAULT 0,
          resident_loans      BIGINT        NOT NULL DEFAULT 0,
          resident_dep_carry  DECIMAL(16,6) NOT NULL DEFAULT 0,
          resident_loan_carry DECIMAL(16,6) NOT NULL DEFAULT 0,
          accrued_at          DATETIME      NULL,
          capital_seeded_at   DATETIME      NULL,
          last_run_id         BIGINT        NULL,
          last_tick_at        DATETIME      NULL,
          last_stats          JSON          NULL,
          created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          CONSTRAINT ck_econ_banks_res CHECK (resident_deposits >= 0 AND resident_loans >= 0)
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS bank_deposits (
          id               BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
          character_id     INT           NOT NULL,
          region_id        BIGINT        NOT NULL,
          kind             VARCHAR(8)    NOT NULL,
          status           VARCHAR(8)    NOT NULL DEFAULT 'open',
          amount           BIGINT        NOT NULL DEFAULT 0,
          interest_base    BIGINT        NOT NULL DEFAULT 0,
          interest_accrued BIGINT        NOT NULL DEFAULT 0,
          interest_total   BIGINT        NOT NULL DEFAULT 0,
          interest_carry   DECIMAL(16,6) NOT NULL DEFAULT 0,
          rate_day         DECIMAL(8,6)  NULL,
          term_days        SMALLINT      NULL,
          opened_at        DATETIME      NOT NULL,
          matures_at       DATETIME      NULL,
          accrued_at       DATETIME      NOT NULL,
          closed_at        DATETIME      NULL,
          demand_owner_id  INT           NULL,
          updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY ix_bank_deposits_region_status (region_id, status),
          KEY ix_bank_deposits_char_status (character_id, status),
          CONSTRAINT uq_bank_deposits_demand UNIQUE (region_id, demand_owner_id),
          CONSTRAINT fk_bank_deposits_bank FOREIGN KEY (region_id) REFERENCES econ_banks (region_id),
          CONSTRAINT ck_bank_deposits_kind CHECK (kind IN ('demand', 'term')),
          CONSTRAINT ck_bank_deposits_status CHECK (status IN ('open', 'closed')),
          CONSTRAINT ck_bank_deposits_amounts
            CHECK (amount >= 0 AND interest_accrued >= 0 AND interest_base >= 0)
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS bank_loans (
          id                  BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
          character_id        INT           NOT NULL,
          region_id           BIGINT        NOT NULL,
          status              VARCHAR(12)   NOT NULL DEFAULT 'active',
          principal           BIGINT        NOT NULL,
          debt                BIGINT        NOT NULL,
          interest_total      BIGINT        NOT NULL DEFAULT 0,
          penalty_total       BIGINT        NOT NULL DEFAULT 0,
          paid_total          BIGINT        NOT NULL DEFAULT 0,
          collected_total     BIGINT        NOT NULL DEFAULT 0,
          written_off         BIGINT        NOT NULL DEFAULT 0,
          rate_day            DECIMAL(8,6)  NOT NULL,
          penalty_rate_day    DECIMAL(8,6)  NOT NULL,
          term_days           SMALLINT      NOT NULL,
          issued_at           DATETIME      NOT NULL,
          due_at              DATETIME      NOT NULL,
          accrued_at          DATETIME      NOT NULL,
          interest_carry      DECIMAL(16,6) NOT NULL DEFAULT 0,
          closed_at           DATETIME      NULL,
          closed_by_user_id   INT           NULL,
          note                VARCHAR(500)  NULL,
          active_character_id INT           NULL,
          updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY ix_bank_loans_region_status (region_id, status),
          KEY ix_bank_loans_char (character_id),
          KEY ix_bank_loans_status_due (status, due_at),
          CONSTRAINT uq_bank_loans_active UNIQUE (active_character_id),
          CONSTRAINT fk_bank_loans_bank FOREIGN KEY (region_id) REFERENCES econ_banks (region_id),
          CONSTRAINT ck_bank_loans_amounts CHECK (principal > 0 AND debt >= 0),
          CONSTRAINT ck_bank_loans_status CHECK (status IN ('active', 'overdue', 'closed', 'written_off'))
        ) {_TABLE_OPTS}
    """))


def downgrade() -> None:
    conn = op.get_bind()
    # Children first; whole tables are dropped (never drop an FK-backing index on its own).
    for table in ("bank_loans", "bank_deposits", "econ_banks"):
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))

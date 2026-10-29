"""FEAT-181 stage 1: world economy ledger (double entry) + genesis emission.

* `characters.currency_balance` -> BIGINT NOT NULL DEFAULT 0 (NULL -> 0 first).
* `econ_settings` (singleton id=1): currency word forms + region->country tax rate.
* `econ_accounts` (kind, ref_id): treasuries, auction escrow/storage, money sources;
  character accounts keep their balance in `characters.currency_balance`.
* `econ_operations` (journal header, unique idempotency_key) and `econ_postings`
  (legs from -> to, amount > 0). Append-only.
* Genesis (idempotent, skipped when an operation with idempotency_key='genesis'
  exists): singleton accounts, a treasury account per existing Regions / Countries
  row, a character account per non-zero balance, and one `genesis` operation that
  issues from `emission` every existing character balance plus the active auction
  bids (-> auction_escrow) and the unclaimed auction storage gold (-> auction_storage).
  After it: sum(characters.currency_balance) + sum(econ_accounts.balance) = 0.

Every statement is written so a partially applied run (MySQL DDL is not
transactional) can simply be re-run. Tables owned by other services (Regions,
Countries -> locations-service; auction_* -> inventory-service) are guarded with
information_schema so an empty database does not fail.

Downgrade drops the four tables and returns the balance column to INT NULL
DEFAULT 0 (lossless while balances stay below 2^31).

Revision ID: 027_world_economy
Revises: 026_house_presence
"""

from alembic import op
import sqlalchemy as sa


revision = "027_world_economy"
down_revision = "026_house_presence"
branch_labels = None
depends_on = None


GENESIS_KEY = "genesis"

# (kind, display name, allow_negative) — mirrors econ_core.SINGLETON_NAMES / NEGATIVE_ALLOWED_KINDS.
SINGLETONS = [
    ("emission", "Эмиссия", 1),
    ("adjustment", "Корректировки", 1),
    ("world_treasury", "Казна Скитальцев", 1),
    ("auction_escrow", "Ставки аукциона", 0),
    ("auction_storage", "Хранилище аукциона", 0),
]


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :name"
    ), {"name": name}).scalar())


def _scalar_int(conn, sql: str) -> int:
    return int(conn.execute(sa.text(sql)).scalar() or 0)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Balances: BIGINT NOT NULL.
    conn.execute(sa.text("UPDATE characters SET currency_balance = 0 WHERE currency_balance IS NULL"))
    conn.execute(sa.text("ALTER TABLE characters MODIFY currency_balance BIGINT NOT NULL DEFAULT 0"))

    # 2. Settings singleton.
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS econ_settings (
          id                 TINYINT      NOT NULL PRIMARY KEY,
          currency_name      VARCHAR(50)  NOT NULL,
          currency_genitive  VARCHAR(50)  NOT NULL,
          currency_one       VARCHAR(50)  NOT NULL,
          currency_few       VARCHAR(50)  NOT NULL,
          currency_many      VARCHAR(50)  NOT NULL,
          currency_short     VARCHAR(20)  NOT NULL,
          country_tax_rate   DECIMAL(5,4) NOT NULL DEFAULT 0.1000,
          updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          updated_by_user_id INT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """))
    # Word forms as bound parameters (not DDL defaults): keeps the Cyrillic out of the DDL text.
    conn.execute(sa.text("""
        INSERT IGNORE INTO econ_settings
          (id, currency_name, currency_genitive, currency_one, currency_few, currency_many, currency_short,
           country_tax_rate)
        VALUES (1, :name, :genitive, :one, :few, :many, :short, 0.1000)
    """), {"name": "Золото", "genitive": "золота", "one": "золотой", "few": "золотых",
           "many": "золотых", "short": "зол."})

    # 3. Accounts.
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS econ_accounts (
          id             BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
          kind           VARCHAR(32)  NOT NULL,
          ref_id         BIGINT       NOT NULL DEFAULT 0,
          name           VARCHAR(255) NULL,
          balance        BIGINT       NOT NULL DEFAULT 0,
          allow_negative TINYINT(1)   NOT NULL DEFAULT 0,
          is_active      TINYINT(1)   NOT NULL DEFAULT 1,
          created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uq_econ_accounts_kind_ref (kind, ref_id),
          KEY ix_econ_accounts_kind (kind)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """))

    # 4. Operations (journal header).
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS econ_operations (
          id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
          op_type         VARCHAR(50)  NOT NULL,
          idempotency_key VARCHAR(128) NULL,
          location_id     BIGINT       NULL,
          region_id       BIGINT       NULL,
          actor_user_id   INT          NULL,
          source_service  VARCHAR(32)  NOT NULL,
          comment         VARCHAR(500) NULL,
          metadata        JSON         NULL,
          created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          UNIQUE KEY uq_econ_operations_idem (idempotency_key),
          KEY ix_econ_operations_created (created_at),
          KEY ix_econ_operations_type_created (op_type, created_at),
          KEY ix_econ_operations_region_created (region_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """))

    # 5. Postings (legs). Every FK column leads an explicit index.
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS econ_postings (
          id              BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
          operation_id    BIGINT      NOT NULL,
          from_account_id BIGINT      NOT NULL,
          to_account_id   BIGINT      NOT NULL,
          amount          BIGINT      NOT NULL,
          leg_type        VARCHAR(32) NOT NULL DEFAULT 'main',
          created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          KEY ix_econ_postings_operation (operation_id),
          KEY ix_econ_postings_from_created (from_account_id, created_at),
          KEY ix_econ_postings_to_created (to_account_id, created_at),
          CONSTRAINT fk_econ_postings_operation FOREIGN KEY (operation_id)    REFERENCES econ_operations (id),
          CONSTRAINT fk_econ_postings_from      FOREIGN KEY (from_account_id) REFERENCES econ_accounts (id),
          CONSTRAINT fk_econ_postings_to        FOREIGN KEY (to_account_id)   REFERENCES econ_accounts (id),
          CONSTRAINT ck_econ_postings_amount    CHECK (amount > 0),
          CONSTRAINT ck_econ_postings_distinct  CHECK (from_account_id <> to_account_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """))

    _genesis(conn)


def _genesis(conn) -> None:
    # Accounts are idempotent on their own (UNIQUE (kind, ref_id) + INSERT IGNORE).
    for kind, name, allow_negative in SINGLETONS:
        conn.execute(sa.text(
            "INSERT IGNORE INTO econ_accounts (kind, ref_id, name, balance, allow_negative, is_active) "
            "VALUES (:kind, 0, :name, 0, :neg, 1)"
        ), {"kind": kind, "name": name, "neg": allow_negative})
    if _table_exists(conn, "Regions"):
        conn.execute(sa.text(
            "INSERT IGNORE INTO econ_accounts (kind, ref_id, name, balance, allow_negative, is_active) "
            "SELECT 'region_treasury', id, name, 0, 1, 1 FROM Regions"
        ))
    if _table_exists(conn, "Countries"):
        conn.execute(sa.text(
            "INSERT IGNORE INTO econ_accounts (kind, ref_id, name, balance, allow_negative, is_active) "
            "SELECT 'country_treasury', id, name, 0, 1, 1 FROM Countries"
        ))

    already = conn.execute(sa.text(
        "SELECT id FROM econ_operations WHERE idempotency_key = :key"
    ), {"key": GENESIS_KEY}).scalar()
    if already:
        return

    conn.execute(sa.text(
        "INSERT IGNORE INTO econ_accounts (kind, ref_id, name, balance, allow_negative, is_active) "
        "SELECT 'character', id, name, 0, 0, 1 FROM characters WHERE currency_balance <> 0"
    ))
    conn.execute(sa.text(
        "INSERT INTO econ_operations (op_type, idempotency_key, source_service, comment) "
        "VALUES ('genesis', :key, 'character-service', :comment)"
    ), {"key": GENESIS_KEY, "comment": "Начальная эмиссия"})
    op_id = conn.execute(sa.text(
        "SELECT id FROM econ_operations WHERE idempotency_key = :key"
    ), {"key": GENESIS_KEY}).scalar()

    emission_id = conn.execute(sa.text(
        "SELECT id FROM econ_accounts WHERE kind = 'emission' AND ref_id = 0"
    )).scalar()

    # Characters: emission -> character for positive balances, character -> emission for negative ones.
    conn.execute(sa.text(
        "INSERT INTO econ_postings (operation_id, from_account_id, to_account_id, amount, leg_type) "
        "SELECT :op, :em, a.id, c.currency_balance, 'main' FROM characters c "
        "JOIN econ_accounts a ON a.kind = 'character' AND a.ref_id = c.id "
        "WHERE c.currency_balance > 0 ORDER BY c.id"
    ), {"op": op_id, "em": emission_id})
    conn.execute(sa.text(
        "INSERT INTO econ_postings (operation_id, from_account_id, to_account_id, amount, leg_type) "
        "SELECT :op, a.id, :em, -c.currency_balance, 'main' FROM characters c "
        "JOIN econ_accounts a ON a.kind = 'character' AND a.ref_id = c.id "
        "WHERE c.currency_balance < 0 ORDER BY c.id"
    ), {"op": op_id, "em": emission_id})
    characters_total = _scalar_int(conn, "SELECT COALESCE(SUM(currency_balance), 0) FROM characters")

    escrow_total = 0
    if _table_exists(conn, "auction_listings"):
        escrow_total = _scalar_int(conn, (
            "SELECT COALESCE(SUM(current_bid), 0) FROM auction_listings "
            "WHERE status = 'active' AND current_bidder_id IS NOT NULL"
        ))
    storage_total = 0
    if _table_exists(conn, "auction_storage"):
        storage_total = _scalar_int(conn, "SELECT COALESCE(SUM(gold_amount), 0) FROM auction_storage")

    for kind, total in (("auction_escrow", escrow_total), ("auction_storage", storage_total)):
        if total <= 0:
            continue
        conn.execute(sa.text(
            "INSERT INTO econ_postings (operation_id, from_account_id, to_account_id, amount, leg_type) "
            "SELECT :op, :em, id, :amount, 'main' FROM econ_accounts WHERE kind = :kind AND ref_id = 0"
        ), {"op": op_id, "em": emission_id, "amount": total, "kind": kind})
        conn.execute(sa.text(
            "UPDATE econ_accounts SET balance = :amount WHERE kind = :kind AND ref_id = 0"
        ), {"amount": total, "kind": kind})

    issued = characters_total + max(escrow_total, 0) + max(storage_total, 0)
    conn.execute(sa.text("UPDATE econ_accounts SET balance = :b WHERE id = :id"),
                 {"b": -issued, "id": emission_id})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS econ_postings"))
    conn.execute(sa.text("DROP TABLE IF EXISTS econ_operations"))
    conn.execute(sa.text("DROP TABLE IF EXISTS econ_accounts"))
    conn.execute(sa.text("DROP TABLE IF EXISTS econ_settings"))
    conn.execute(sa.text("ALTER TABLE characters MODIFY currency_balance INT NULL DEFAULT 0"))

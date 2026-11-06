"""FEAT-206: factions — stage 2 (faction economy). features/FEAT-206 §3.3.

* ``faction_ranks`` + ``reward_marks`` (paid through the debt queue on grant) and ``qm_discount_pct``;
* ``faction_settings`` + donation rate / daily points cap, the global economy switch, the regional purse / treasury
  caps, the members' leave / grow rates and the quartermaster restock take share;
* ``faction_econ_templates`` (seeded: «Орден», «Гильдия торговцев», «Тёмная гильдия», «Храм», «Академия»);
* ``faction_economy`` (1:1 with ``factions``, backfilled for the existing factions);
* ``faction_econ_history`` (one row per tick run and faction), ``faction_debts`` (payout queue),
  ``faction_donation_days`` (daily points cap counter), ``faction_quartermasters`` (NPC <-> faction),
  ``faction_qm_items`` (assortment), ``faction_qm_purchases`` (purchase journal + delivery outbox).

The treasury itself is a ledger account (``faction_treasury``, created lazily) — no DDL. No ENUM; FK columns carry
explicit indexes; FKs to ``characters`` / ``factions`` are ON DELETE CASCADE. Every step is guarded
(information_schema), so a re-run is a no-op. Downgrade drops the tables in reverse FK order and the added columns
(data loss accepted pre-beta; faction treasury accounts / journal stay — the ledger is append-only).

Revision ID: 046_faction_economy
Revises: 045_factions_core
"""

import json

import sqlalchemy as sa
from alembic import op


revision = "046_faction_economy"
down_revision = "045_factions_core"
branch_labels = None
depends_on = None

_TAIL = ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

_COLUMNS = [
    ("faction_ranks", "reward_marks", "INT NOT NULL DEFAULT 0"),
    ("faction_ranks", "qm_discount_pct", "INT NOT NULL DEFAULT 0"),
    ("faction_settings", "donation_marks_per_point", "INT NOT NULL DEFAULT 10"),
    ("faction_settings", "donation_points_daily_cap", "INT NOT NULL DEFAULT 50"),
    ("faction_settings", "econ_enabled", "TINYINT(1) NOT NULL DEFAULT 1"),
    ("faction_settings", "econ_purse_share_pct", "INT NOT NULL DEFAULT 2"),
    ("faction_settings", "econ_treasury_share_pct", "INT NOT NULL DEFAULT 1"),
    ("faction_settings", "members_leave_pct", "INT NOT NULL DEFAULT 5"),
    ("faction_settings", "members_grow_pct", "INT NOT NULL DEFAULT 1"),
    ("faction_settings", "qm_take_share_pct", "INT NOT NULL DEFAULT 5"),
]

_TABLES = [
    ("faction_econ_templates", (
        "CREATE TABLE faction_econ_templates ("
        " code VARCHAR(32) NOT NULL,"
        " name VARCHAR(100) NOT NULL,"
        " description VARCHAR(500) NULL,"
        " params JSON NOT NULL,"
        " sort_order INT NOT NULL DEFAULT 0,"
        " updated_at DATETIME NOT NULL,"
        " PRIMARY KEY (code)" + _TAIL)),
    ("faction_economy", (
        "CREATE TABLE faction_economy ("
        " faction_id INT NOT NULL,"
        " template_code VARCHAR(32) NULL,"
        " overrides JSON NULL,"
        " econ_enabled TINYINT(1) NOT NULL DEFAULT 1,"
        " members_count INT NOT NULL DEFAULT 0,"
        " members_carry DECIMAL(10,4) NOT NULL DEFAULT 0,"
        " members_min INT NOT NULL DEFAULT 10,"
        " members_max INT NOT NULL DEFAULT 5000,"
        " payout_seq INT NOT NULL DEFAULT 0,"
        " last_run_id BIGINT NULL,"
        " last_tick_at DATETIME NULL,"
        " last_dues BIGINT NOT NULL DEFAULT 0,"
        " last_profile BIGINT NOT NULL DEFAULT 0,"
        " last_wages_due BIGINT NOT NULL DEFAULT 0,"
        " last_wages_paid BIGINT NOT NULL DEFAULT 0,"
        " last_restock BIGINT NOT NULL DEFAULT 0,"
        " last_debts_paid BIGINT NOT NULL DEFAULT 0,"
        " last_members_delta INT NOT NULL DEFAULT 0,"
        " last_wealth INT NOT NULL DEFAULT 0,"
        " updated_at DATETIME NOT NULL,"
        " PRIMARY KEY (faction_id),"
        " KEY ix_faction_economy_template (template_code),"
        " CONSTRAINT fk_faction_econ_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_econ_template FOREIGN KEY (template_code) REFERENCES faction_econ_templates (code)"
        " ON DELETE RESTRICT" + _TAIL)),
    ("faction_econ_history", (
        "CREATE TABLE faction_econ_history ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " run_id BIGINT NOT NULL,"
        " faction_id INT NOT NULL,"
        " balance_before BIGINT NOT NULL DEFAULT 0,"
        " balance_after BIGINT NOT NULL DEFAULT 0,"
        " dues BIGINT NOT NULL DEFAULT 0,"
        " profile BIGINT NOT NULL DEFAULT 0,"
        " wages_due BIGINT NOT NULL DEFAULT 0,"
        " wages_paid BIGINT NOT NULL DEFAULT 0,"
        " restock_spent BIGINT NOT NULL DEFAULT 0,"
        " restock_items INT NOT NULL DEFAULT 0,"
        " debts_paid BIGINT NOT NULL DEFAULT 0,"
        " members_before INT NOT NULL DEFAULT 0,"
        " members_after INT NOT NULL DEFAULT 0,"
        " wealth INT NOT NULL DEFAULT 0,"
        " created_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_econ_hist_run (run_id, faction_id),"
        " KEY ix_faction_econ_hist_faction (faction_id, id),"
        " CONSTRAINT fk_faction_econ_hist_faction FOREIGN KEY (faction_id) REFERENCES factions (id)"
        " ON DELETE CASCADE" + _TAIL)),
    ("faction_debts", (
        "CREATE TABLE faction_debts ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " character_id INT NOT NULL,"
        " faction_id INT NOT NULL,"
        " source VARCHAR(10) NOT NULL,"
        " source_key VARCHAR(64) NOT NULL,"
        " amount BIGINT NOT NULL,"
        " paid BIGINT NOT NULL DEFAULT 0,"
        " status VARCHAR(8) NOT NULL,"
        " unpaid_notified TINYINT(1) NOT NULL DEFAULT 0,"
        " created_at DATETIME NOT NULL,"
        " paid_at DATETIME NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_debt_source (source_key),"
        " KEY ix_faction_debts_queue (faction_id, status, id),"
        " KEY ix_faction_debts_character (character_id, status),"
        " CONSTRAINT fk_faction_debt_character FOREIGN KEY (character_id) REFERENCES characters (id)"
        " ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_debt_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_donation_days", (
        "CREATE TABLE faction_donation_days ("
        " character_id INT NOT NULL,"
        " faction_id INT NOT NULL,"
        " day DATE NOT NULL,"
        " marks BIGINT NOT NULL DEFAULT 0,"
        " points INT NOT NULL DEFAULT 0,"
        " PRIMARY KEY (character_id, faction_id, day),"
        " KEY ix_faction_donation_days_faction (faction_id),"
        " CONSTRAINT fk_faction_don_character FOREIGN KEY (character_id) REFERENCES characters (id)"
        " ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_don_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_quartermasters", (
        "CREATE TABLE faction_quartermasters ("
        " npc_id INT NOT NULL,"
        " faction_id INT NOT NULL,"
        " created_at DATETIME NOT NULL,"
        " PRIMARY KEY (npc_id),"
        " KEY ix_faction_qms_faction (faction_id),"
        " CONSTRAINT fk_faction_qm_npc FOREIGN KEY (npc_id) REFERENCES characters (id) ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_qm_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_qm_items", (
        "CREATE TABLE faction_qm_items ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " faction_id INT NOT NULL,"
        " item_id INT NOT NULL,"
        " price INT NOT NULL,"
        " min_rank_id INT NULL,"
        " stock INT NOT NULL DEFAULT 0,"
        " restock_target INT NOT NULL DEFAULT 0,"
        " is_active TINYINT(1) NOT NULL DEFAULT 1,"
        " sort_order INT NOT NULL DEFAULT 0,"
        " updated_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_qm_item (faction_id, item_id),"
        " KEY ix_faction_qm_items_order (faction_id, sort_order),"
        " KEY ix_faction_qm_items_min_rank (min_rank_id),"
        " CONSTRAINT fk_faction_qm_item_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_qm_item_rank FOREIGN KEY (min_rank_id) REFERENCES faction_ranks (id)"
        " ON DELETE RESTRICT" + _TAIL)),
    ("faction_qm_purchases", (
        "CREATE TABLE faction_qm_purchases ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " character_id INT NOT NULL,"
        " faction_id INT NOT NULL,"
        " qm_item_id INT NULL,"
        " npc_id INT NULL,"
        " item_id INT NOT NULL,"
        " quantity INT NOT NULL,"
        " price_total BIGINT NOT NULL,"
        " op_key VARCHAR(128) NOT NULL,"
        " status VARCHAR(10) NOT NULL,"
        " attempts INT NOT NULL DEFAULT 0,"
        " next_attempt_at DATETIME NOT NULL,"
        " last_error VARCHAR(255) NULL,"
        " created_at DATETIME NOT NULL,"
        " updated_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_qm_purchase_key (op_key),"
        " KEY ix_faction_qm_purchases_due (status, next_attempt_at),"
        " KEY ix_faction_qm_purchases_character (character_id),"
        " KEY ix_faction_qm_purchases_faction (faction_id),"
        " KEY ix_faction_qm_purchases_item (qm_item_id),"
        " CONSTRAINT fk_faction_qmp_character FOREIGN KEY (character_id) REFERENCES characters (id)"
        " ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_qmp_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_qmp_item FOREIGN KEY (qm_item_id) REFERENCES faction_qm_items (id)"
        " ON DELETE SET NULL" + _TAIL)),
]


def _params(start, norm, per_member, dues, wage, kind, per_profile, rate, qm_share):
    return {
        "start_members": start, "norm_per_member": norm, "start_treasury_per_member": per_member,
        "dues_per_member": dues, "wage_per_member": wage, "profile_kind": kind,
        "profile_per_member": per_profile, "profile_rate": rate, "qm_budget_share": qm_share,
    }


# (code, name, description, params, sort_order) — features/FEAT-206 §3.4 (decimals stored as strings).
TEMPLATES = [
    ("order", "Орден", "Охраняет край: край платит за охрану из своей казны",
     _params(300, 30, 30, "1.0", "1.0", "treasury_share", "0", "0.005", "0.10"), 1),
    ("merchants_guild", "Гильдия торговцев", "Живёт с оборота рынка края",
     _params(200, 40, 40, "1.5", "1.0", "income_share", "0", "0.01", "0.15"), 2),
    ("dark_guild", "Тёмная гильдия", "Живёт «заказами» жителей края",
     _params(100, 40, 40, "0.5", "1.0", "members_purse", "1.0", "0", "0.10"), 3),
    ("temple", "Храм", "Живёт пожертвованиями жителей края",
     _params(150, 30, 30, "0.5", "0.75", "members_purse", "0.75", "0", "0.05"), 4),
    ("academy", "Академия", "Живёт платой жителей за обучение",
     _params(120, 40, 40, "1.0", "1.0", "members_purse", "0.5", "0", "0.10"), 5),
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
    for code, name, description, params, order in TEMPLATES:
        exists = conn.execute(sa.text("SELECT COUNT(*) FROM faction_econ_templates WHERE code = :c"),
                              {"c": code}).scalar()
        if not exists:
            conn.execute(sa.text(
                "INSERT INTO faction_econ_templates (code, name, description, params, sort_order, updated_at) "
                "VALUES (:c, :n, :d, :p, :o, UTC_TIMESTAMP())"),
                {"c": code, "n": name, "d": description, "p": json.dumps(params, ensure_ascii=False), "o": order})
    # backfill: one economy row per existing faction (no template, no members)
    conn.execute(sa.text(
        "INSERT INTO faction_economy (faction_id, updated_at) "
        "SELECT f.id, UTC_TIMESTAMP() FROM factions f "
        "LEFT JOIN faction_economy e ON e.faction_id = f.id WHERE e.faction_id IS NULL"))


def downgrade():
    conn = op.get_bind()
    for name, _ddl in reversed(_TABLES):
        if _has_table(conn, name):
            op.execute(f"DROP TABLE {name}")
    for table, column, _ddl in reversed(_COLUMNS):
        if _has_table(conn, table) and _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

"""FEAT-205: factions — stage 1 (core).

Nine tables (features/FEAT-205 §3.2): ``factions``, ``faction_ranks``, ``faction_conditions``, ``faction_hostilities``,
``faction_members``, ``faction_applications``, ``faction_rank_grants``, ``faction_reward_deliveries``, ``faction_log``
and the single-row ``faction_settings`` (seeded with id=1: 3 d warning / 7 d rejoin / 50 % burn / 50 % hostile
penalty / 24 h re-apply).

Every FK to ``characters.id`` is ON DELETE CASCADE (character deletion cleanup); FK columns carry explicit indexes
(MySQL); status / type columns are VARCHAR (no ENUM). Each step is guarded (information_schema) so a re-run is a no-op.
Downgrade drops the tables in reverse FK order (data loss accepted pre-beta).

Revision ID: 045_factions_core
Revises: 044_guard_patrols
"""

import sqlalchemy as sa
from alembic import op


revision = "045_factions_core"
down_revision = "044_guard_patrols"
branch_labels = None
depends_on = None

_TAIL = ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

_TABLES = [
    ("factions", (
        "CREATE TABLE factions ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " name VARCHAR(100) NOT NULL,"
        " description TEXT NULL,"
        " emblem_url VARCHAR(512) NULL,"
        " hq_location_id BIGINT NULL,"
        " leader_npc_ids JSON NULL,"
        " member_limit INT NULL,"
        " is_invite_only TINYINT(1) NOT NULL DEFAULT 0,"
        " is_secret TINYINT(1) NOT NULL DEFAULT 0,"
        " is_active TINYINT(1) NOT NULL DEFAULT 0,"
        " sort_order INT NOT NULL DEFAULT 0,"
        " created_at DATETIME NOT NULL,"
        " updated_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_factions_name (name)" + _TAIL)),
    ("faction_ranks", (
        "CREATE TABLE faction_ranks ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " faction_id INT NOT NULL,"
        " name VARCHAR(100) NOT NULL,"
        " description TEXT NULL,"
        " sort_order INT NOT NULL,"
        " min_points INT NOT NULL DEFAULT 0,"
        " min_level INT NOT NULL DEFAULT 0,"
        " required_quest_id BIGINT NULL,"
        " reward_xp INT NOT NULL DEFAULT 0,"
        " reward_title_id INT NULL,"
        " reward_items JSON NULL,"
        " reward_house_location_id BIGINT NULL,"
        " reward_plot_location_id BIGINT NULL,"
        " created_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " KEY ix_faction_ranks_order (faction_id, sort_order),"
        " CONSTRAINT fk_faction_rank_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_conditions", (
        "CREATE TABLE faction_conditions ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " faction_id INT NOT NULL,"
        " cond_type VARCHAR(30) NOT NULL,"
        " params JSON NOT NULL,"
        " sort_order INT NOT NULL DEFAULT 0,"
        " PRIMARY KEY (id),"
        " KEY ix_faction_conditions_faction_id (faction_id),"
        " CONSTRAINT fk_faction_cond_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_hostilities", (
        "CREATE TABLE faction_hostilities ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " faction_a_id INT NOT NULL,"
        " faction_b_id INT NOT NULL,"
        " irreconcilable TINYINT(1) NOT NULL DEFAULT 0,"
        " created_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_hostility (faction_a_id, faction_b_id),"
        " KEY ix_faction_host_b (faction_b_id),"
        " CONSTRAINT fk_faction_host_a FOREIGN KEY (faction_a_id) REFERENCES factions (id) ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_host_b FOREIGN KEY (faction_b_id) REFERENCES factions (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_members", (
        "CREATE TABLE faction_members ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " character_id INT NOT NULL,"
        " faction_id INT NOT NULL,"
        " status VARCHAR(10) NOT NULL,"
        " points INT NOT NULL DEFAULT 0,"
        " rank_id INT NULL,"
        " joined_at DATETIME NOT NULL,"
        " left_at DATETIME NULL,"
        " rejoin_after DATETIME NULL,"
        " warning_at DATETIME NULL,"
        " warning_reasons JSON NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_member (character_id, faction_id),"
        " KEY ix_faction_members_status (faction_id, status),"
        " KEY ix_faction_members_warning (status, warning_at),"
        " KEY ix_faction_members_rank_id (rank_id),"
        " CONSTRAINT fk_faction_member_character FOREIGN KEY (character_id) REFERENCES characters (id)"
        " ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_member_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_member_rank FOREIGN KEY (rank_id) REFERENCES faction_ranks (id) ON DELETE SET NULL"
        + _TAIL)),
    ("faction_applications", (
        "CREATE TABLE faction_applications ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " character_id INT NOT NULL,"
        " faction_id INT NOT NULL,"
        " status VARCHAR(10) NOT NULL,"
        " message VARCHAR(500) NULL,"
        " pending_key VARCHAR(40) NULL,"
        " reject_reason VARCHAR(500) NULL,"
        " decided_by_user_id INT NULL,"
        " decided_at DATETIME NULL,"
        " created_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_app_pending (pending_key),"
        " KEY ix_faction_app_status (status, created_at),"
        " KEY ix_faction_applications_character_id (character_id),"
        " KEY ix_faction_applications_faction_id (faction_id),"
        " CONSTRAINT fk_faction_app_character FOREIGN KEY (character_id) REFERENCES characters (id)"
        " ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_app_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_rank_grants", (
        "CREATE TABLE faction_rank_grants ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " character_id INT NOT NULL,"
        " faction_id INT NOT NULL,"
        " rank_id INT NOT NULL,"
        " granted_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_grant (character_id, rank_id),"
        " KEY ix_faction_rank_grants_faction_id (faction_id),"
        " KEY ix_faction_rank_grants_rank_id (rank_id),"
        " CONSTRAINT fk_faction_grant_character FOREIGN KEY (character_id) REFERENCES characters (id)"
        " ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_grant_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_grant_rank FOREIGN KEY (rank_id) REFERENCES faction_ranks (id) ON DELETE RESTRICT"
        + _TAIL)),
    ("faction_reward_deliveries", (
        "CREATE TABLE faction_reward_deliveries ("
        " id INT NOT NULL AUTO_INCREMENT,"
        " grant_id INT NOT NULL,"
        " character_id INT NOT NULL,"
        " kind VARCHAR(15) NOT NULL,"
        " payload JSON NOT NULL,"
        " status VARCHAR(10) NOT NULL,"
        " attempts INT NOT NULL DEFAULT 0,"
        " next_attempt_at DATETIME NOT NULL,"
        " last_error VARCHAR(255) NULL,"
        " updated_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " KEY ix_faction_delivery_due (status, next_attempt_at),"
        " KEY ix_faction_reward_deliveries_grant_id (grant_id),"
        " KEY ix_faction_reward_deliveries_character_id (character_id),"
        " CONSTRAINT fk_faction_delivery_grant FOREIGN KEY (grant_id) REFERENCES faction_rank_grants (id)"
        " ON DELETE CASCADE"
        + _TAIL)),
    ("faction_log", (
        "CREATE TABLE faction_log ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " character_id INT NOT NULL,"
        " faction_id INT NOT NULL,"
        " event_type VARCHAR(30) NOT NULL,"
        " points_delta INT NULL,"
        " points_after INT NULL,"
        " rank_id INT NULL,"
        " event_key VARCHAR(120) NULL,"
        " reason VARCHAR(500) NULL,"
        " actor_user_id INT NULL,"
        " created_at DATETIME NOT NULL,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_faction_log_key (event_key, faction_id),"
        " KEY ix_faction_log_char (character_id, id),"
        " KEY ix_faction_log_faction_id (faction_id),"
        " CONSTRAINT fk_faction_log_character FOREIGN KEY (character_id) REFERENCES characters (id)"
        " ON DELETE CASCADE,"
        " CONSTRAINT fk_faction_log_faction FOREIGN KEY (faction_id) REFERENCES factions (id) ON DELETE CASCADE"
        + _TAIL)),
    ("faction_settings", (
        "CREATE TABLE faction_settings ("
        " id INT NOT NULL,"
        " warning_days INT NOT NULL DEFAULT 3,"
        " rejoin_cooldown_days INT NOT NULL DEFAULT 7,"
        " leave_burn_pct INT NOT NULL DEFAULT 50,"
        " hostile_penalty_pct INT NOT NULL DEFAULT 50,"
        " reapply_cooldown_hours INT NOT NULL DEFAULT 24,"
        " pass_last_run_at DATETIME NULL,"
        " PRIMARY KEY (id)" + _TAIL)),
]

_SEED_SETTINGS = (
    "INSERT INTO faction_settings (id, warning_days, rejoin_cooldown_days, leave_burn_pct, hostile_penalty_pct, "
    "reapply_cooldown_hours) VALUES (1, 3, 7, 50, 50, 24)"
)


def _has_table(conn, table: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t"
    ), {"t": table}).scalar())


def upgrade():
    conn = op.get_bind()
    for name, ddl in _TABLES:
        if not _has_table(conn, name):
            op.execute(ddl)
    if not conn.execute(sa.text("SELECT COUNT(*) FROM faction_settings WHERE id = 1")).scalar():
        op.execute(_SEED_SETTINGS)


def downgrade():
    conn = op.get_bind()
    for name, _ddl in reversed(_TABLES):
        if _has_table(conn, name):
            op.execute(f"DROP TABLE {name}")

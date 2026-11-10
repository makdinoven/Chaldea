"""FEAT-210: admin «Готов» mark on mob templates (features/FEAT-210 §3.2).

Three columns on ``mob_templates``: ``admin_ready`` (flag), ``admin_ready_at`` (UTC naive, set when the flag becomes true),
``admin_ready_by`` (username snapshot of the admin who set it). Admin-only data, never exposed by public schemas.
Guarded (information_schema), so a re-run is a no-op. Downgrade drops the columns (flags lost — accepted pre-beta).

Revision ID: 049_mob_admin_ready
Revises: 048_npc_admin_ready
"""

import sqlalchemy as sa
from alembic import op


revision = "049_mob_admin_ready"
down_revision = "048_npc_admin_ready"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("mob_templates", "admin_ready", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("mob_templates", "admin_ready_at", "DATETIME NULL"),
    ("mob_templates", "admin_ready_by", "VARCHAR(255) NULL"),
]


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def upgrade():
    conn = op.get_bind()
    for table, column, ddl in _COLUMNS:
        if not _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def downgrade():
    conn = op.get_bind()
    for table, column, _ddl in reversed(_COLUMNS):
        if _has_column(conn, table, column):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

"""FEAT-209: admin «Готов» mark on NPCs (features/FEAT-209 §3.1).

Three columns on ``characters``: ``npc_ready`` (flag), ``npc_ready_at`` (UTC naive, set when the flag becomes true),
``npc_ready_by`` (username snapshot of the admin who set it). Admin-only data, never exposed by public schemas.
Guarded (information_schema), so a re-run is a no-op. Downgrade drops the columns (flags lost — accepted pre-beta).

Revision ID: 048_npc_admin_ready
Revises: 047_faction_territory
"""

import sqlalchemy as sa
from alembic import op


revision = "048_npc_admin_ready"
down_revision = "047_faction_territory"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("characters", "npc_ready", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("characters", "npc_ready_at", "DATETIME NULL"),
    ("characters", "npc_ready_by", "VARCHAR(255) NULL"),
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

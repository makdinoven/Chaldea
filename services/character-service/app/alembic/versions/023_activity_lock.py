"""FEAT-175: activity lock columns on characters + dungeon mob leak cleanup.

* `characters.dungeon_session_id` (INT NULL) — the dungeon run the character
  is locked into; written only by character-service internal endpoints that
  dungeon-service calls.
* `characters.unconscious_until` (DATETIME NULL, naive UTC) — knock-out after a
  dungeon wipe. A past value means "not locked", so no cleanup job is needed.
* Data: dungeon mobs (`active_mobs.spawn_type = 'dungeon'`) must never live on
  the surface. Before this feature a dead dungeon mob got a `respawn_at` and
  came back as a normal location mob. Rows that are not in a running battle are
  deleted (their hidden `npc_role='mob'` character rows stay, as with the
  runtime despawn). Not restored on downgrade — they were garbage.

Revision ID: 023_activity_lock
Revises: 022_char_titles_cascade
"""

from alembic import op
import sqlalchemy as sa


revision = "023_activity_lock"
down_revision = "022_char_titles_cascade"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "characters", "dungeon_session_id"):
        op.add_column("characters", sa.Column("dungeon_session_id", sa.Integer(), nullable=True))
    if not _has_column(inspector, "characters", "unconscious_until"):
        op.add_column("characters", sa.Column("unconscious_until", sa.DateTime(), nullable=True))

    if "active_mobs" in inspector.get_table_names():
        op.execute(
            "DELETE FROM active_mobs WHERE spawn_type = 'dungeon' AND status <> 'in_battle'"
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "characters", "unconscious_until"):
        op.drop_column("characters", "unconscious_until")
    if _has_column(inspector, "characters", "dungeon_session_id"):
        op.drop_column("characters", "dungeon_session_id")

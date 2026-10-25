"""FEAT-175: locked doors and keys

* `dungeon_corridors.lock_config` (JSON NULL) — the corridor is a locked door:
  which key opens it, whether it can be picked, how hard, for how much stamina.
* `dungeon_sessions.keys_found` (JSON NULL) — key kinds found during the run.
* `dungeon_sessions.unlocked_corridor_ids` (JSON NULL) — locked corridors the
  party has opened (with a key or by picking) during the run.

Revision ID: 005
Revises: 004
Create Date: 2026-10-25

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def _columns(table: str) -> list:
    return [c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if "lock_config" not in _columns("dungeon_corridors"):
        op.add_column("dungeon_corridors", sa.Column("lock_config", sa.JSON(), nullable=True))
    cols = _columns("dungeon_sessions")
    if "keys_found" not in cols:
        op.add_column("dungeon_sessions", sa.Column("keys_found", sa.JSON(), nullable=True))
    if "unlocked_corridor_ids" not in cols:
        op.add_column("dungeon_sessions", sa.Column("unlocked_corridor_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("dungeon_sessions", "unlocked_corridor_ids")
    op.drop_column("dungeon_sessions", "keys_found")
    op.drop_column("dungeon_corridors", "lock_config")

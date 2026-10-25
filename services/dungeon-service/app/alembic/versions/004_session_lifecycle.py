"""FEAT-175: session lifecycle columns + 3D room footprint

* `last_activity_at` — last player action / battle result; a run idle for 24 h
  is treated as an escape by the sweeper.
* `active_battle_id` — durable copy of the Redis field; a compare-and-set on it
  makes battle-completion processing exactly-once (callback vs polling).
* `dungeon_rooms.grid_w` / `grid_d` (INT NULL) — room footprint in floor
  squares for the 3D diorama (NULL = frontend default for the room type).
* `finalized_at` — the session is fully closed (loot handed out, Redis/WS
  cleaned up). `completed`/`escaped` sessions without it still await loot
  distribution.

Data: every pre-existing session is history (the old flow left them in
`forming`/`escaped`/... forever) — mark them finalized; orphan `forming`
sessions become `escaped`.

Revision ID: 004
Revises: 003
Create Date: 2026-10-22

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def _columns() -> list:
    return [c["name"] for c in sa.inspect(op.get_bind()).get_columns("dungeon_sessions")]


def upgrade() -> None:
    cols = _columns()
    if "last_activity_at" not in cols:
        op.add_column("dungeon_sessions", sa.Column("last_activity_at", sa.TIMESTAMP(), nullable=True))
    if "active_battle_id" not in cols:
        op.add_column("dungeon_sessions", sa.Column("active_battle_id", sa.BigInteger(), nullable=True))
    if "finalized_at" not in cols:
        op.add_column("dungeon_sessions", sa.Column("finalized_at", sa.TIMESTAMP(), nullable=True))

    room_cols = [c["name"] for c in sa.inspect(op.get_bind()).get_columns("dungeon_rooms")]
    if "grid_w" not in room_cols:
        op.add_column("dungeon_rooms", sa.Column("grid_w", sa.Integer(), nullable=True))
    if "grid_d" not in room_cols:
        op.add_column("dungeon_rooms", sa.Column("grid_d", sa.Integer(), nullable=True))

    op.execute(
        "UPDATE dungeon_sessions SET status = 'escaped', "
        "finished_at = COALESCE(finished_at, created_at) WHERE status = 'forming'"
    )
    op.execute(
        "UPDATE dungeon_sessions SET finalized_at = COALESCE(finished_at, created_at) "
        "WHERE status IN ('completed', 'escaped', 'wiped') AND finalized_at IS NULL"
    )


def downgrade() -> None:
    cols = _columns()
    for name in ("finalized_at", "active_battle_id", "last_activity_at"):
        if name in cols:
            op.drop_column("dungeon_sessions", name)
    room_cols = [c["name"] for c in sa.inspect(op.get_bind()).get_columns("dungeon_rooms")]
    for name in ("grid_d", "grid_w"):
        if name in room_cols:
            op.drop_column("dungeon_rooms", name)

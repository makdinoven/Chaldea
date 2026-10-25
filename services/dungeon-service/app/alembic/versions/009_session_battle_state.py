"""The battle a run is fighting, in the DB (it lived only in Redis)

* `dungeon_sessions.battle_mob_ids` (JSON NULL) — the battle's spawned mobs.
* `dungeon_sessions.pending_target_room_id` (BIGINT NULL) — a corridor ambush: the room the party was heading for.
* `dungeon_sessions.pending_corridor_id` (BIGINT NULL) — and the corridor it was caught in.

Revision ID: 009
Revises: 008
Create Date: 2026-10-25

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

COLUMNS = (
    ("battle_mob_ids", sa.JSON()),
    ("pending_target_room_id", sa.BigInteger()),
    ("pending_corridor_id", sa.BigInteger()),
)


def upgrade() -> None:
    cols = [c["name"] for c in sa.inspect(op.get_bind()).get_columns("dungeon_sessions")]
    for name, kind in COLUMNS:
        if name not in cols:
            op.add_column("dungeon_sessions", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("dungeon_sessions", name)

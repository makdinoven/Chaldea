"""FEAT-175: floors, passages between them, depth scaling

* `dungeon_rooms.floor` (INT, default 1) — 1 is the top floor.
* `dungeon_corridors.passage_type` (VARCHAR(16), default 'corridor') —
  corridor | stairs | drop | lift; the last three join neighbouring floors.
* `dungeon_corridors.passage_config` (JSON NULL) — a drop's hidden trap.
* `dungeons.floor_mob_step` / `floor_loot_step` / `floor_flee_step` (FLOAT) —
  per floor below the first: + mob strength, + loot chances, + flee loss.

Revision ID: 006
Revises: 005
Create Date: 2026-10-25

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def _columns(table: str) -> list:
    return [c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if "floor" not in _columns("dungeon_rooms"):
        op.add_column("dungeon_rooms", sa.Column("floor", sa.Integer(), nullable=False, server_default="1"))
    cols = _columns("dungeon_corridors")
    if "passage_type" not in cols:
        op.add_column("dungeon_corridors",
                      sa.Column("passage_type", sa.String(16), nullable=False, server_default="corridor"))
    if "passage_config" not in cols:
        op.add_column("dungeon_corridors", sa.Column("passage_config", sa.JSON(), nullable=True))
    cols = _columns("dungeons")
    for name, default in (("floor_mob_step", "0.2"), ("floor_loot_step", "0.15"), ("floor_flee_step", "0.1")):
        if name not in cols:
            op.add_column("dungeons", sa.Column(name, sa.Float(), nullable=False, server_default=default))


def downgrade() -> None:
    for name in ("floor_flee_step", "floor_loot_step", "floor_mob_step"):
        op.drop_column("dungeons", name)
    op.drop_column("dungeon_corridors", "passage_config")
    op.drop_column("dungeon_corridors", "passage_type")
    op.drop_column("dungeon_rooms", "floor")

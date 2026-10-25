"""FEAT-176: a dungeon's random finds when a room is searched

* `dungeons.search_loot` (JSON NULL) — [{item_id, quantity, chance}]: what a
  search may turn up by luck, stash or not (one entry picked at random).

Revision ID: 007
Revises: 006
Create Date: 2026-10-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = [c["name"] for c in sa.inspect(op.get_bind()).get_columns("dungeons")]
    if "search_loot" not in cols:
        op.add_column("dungeons", sa.Column("search_loot", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("dungeons", "search_loot")

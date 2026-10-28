"""FEAT-180 stage 7: where a character stands inside a house.

* `characters.house_room_id` (BIGINT NULL, indexed) — the house room
  (locations-service `house_rooms.id`, no FK, like `reading_house_room_id`)
  the character is in. Set by locations-service (enter / walk / leave),
  cleared by character-service whenever the location changes. It counts only
  while the room's house stands in the character's current location.

Additive; downgrade drops the index and the column (everyone is simply
outside their houses).

Revision ID: 026_house_presence
Revises: 025_house_reading
"""

from alembic import op
import sqlalchemy as sa


revision = "026_house_presence"
down_revision = "025_house_reading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("house_room_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_characters_house_room_id", "characters", ["house_room_id"])


def downgrade() -> None:
    op.drop_index("ix_characters_house_room_id", table_name="characters")
    op.drop_column("characters", "house_room_id")

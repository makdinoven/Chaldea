"""FEAT-180 stage 6b: a character reading in a house library.

* `characters.reading_since` (DATETIME NULL, naive UTC) — locks activity like
  `asleep_since`;
* `characters.reading_house_room_id` (BIGINT NULL) — the library (locations-service
  `house_rooms.id`, no FK).

Additive; downgrade drops the two columns (readers simply stop reading, the
bonus not yet earned is lost).

Revision ID: 025_house_reading
Revises: 024_house_sleep
"""

from alembic import op
import sqlalchemy as sa


revision = "025_house_reading"
down_revision = "024_house_sleep"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("reading_since", sa.DateTime(), nullable=True))
    op.add_column("characters", sa.Column("reading_house_room_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("characters", "reading_house_room_id")
    op.drop_column("characters", "reading_since")

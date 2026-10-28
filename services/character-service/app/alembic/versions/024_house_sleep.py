"""FEAT-180: a character asleep in a house bedroom.

* `characters.asleep_since` (DATETIME NULL, naive UTC) — locks activity like
  `dungeon_session_id` / `unconscious_until`;
* `characters.sleep_regen_factor` (FLOAT NULL) — the rest multiplier of that bedroom;
* `characters.sleep_house_room_id` (BIGINT NULL) — the bedroom (locations-service
  `house_rooms.id`, no FK).

Additive; downgrade drops the three columns (sleepers simply wake up).

Revision ID: 024_house_sleep
Revises: 023_activity_lock
"""

from alembic import op
import sqlalchemy as sa


revision = "024_house_sleep"
down_revision = "023_activity_lock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("asleep_since", sa.DateTime(), nullable=True))
    op.add_column("characters", sa.Column("sleep_regen_factor", sa.Float(), nullable=True))
    op.add_column("characters", sa.Column("sleep_house_room_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("characters", "sleep_house_room_id")
    op.drop_column("characters", "sleep_regen_factor")
    op.drop_column("characters", "asleep_since")

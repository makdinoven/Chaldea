"""Add 'dungeon' to active_mobs spawn_type enum

Revision ID: 014
Revises: 013
"""
from alembic import op

revision = "014_add_dungeon_spawn_type"
down_revision = "013_add_gold_transactions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE active_mobs MODIFY COLUMN spawn_type "
        "ENUM('random','manual','dungeon') NOT NULL DEFAULT 'random'"
    )


def downgrade():
    op.execute(
        "ALTER TABLE active_mobs MODIFY COLUMN spawn_type "
        "ENUM('random','manual') NOT NULL DEFAULT 'random'"
    )

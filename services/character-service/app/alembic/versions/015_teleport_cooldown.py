"""Add teleport_links table and last_teleport_at column on characters

Revision ID: 015_add_teleport_links_and_cooldown
Revises: 014_add_dungeon_spawn_type
"""
from alembic import op
import sqlalchemy as sa


revision = "015_teleport_cooldown"
down_revision = "014_add_dungeon_spawn_type"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teleport_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("from_npc_id", sa.Integer(), nullable=False),
        sa.Column("to_npc_id", sa.Integer(), nullable=False),
        sa.Column("cost_gold", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(
            ["from_npc_id"], ["characters.id"],
            name="fk_tlink_from", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_npc_id"], ["characters.id"],
            name="fk_tlink_to", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("from_npc_id", "to_npc_id", name="uq_tlink_pair"),
    )
    op.create_index("idx_tlink_from", "teleport_links", ["from_npc_id"])

    op.add_column(
        "characters",
        sa.Column("last_teleport_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column("characters", "last_teleport_at")
    op.drop_index("idx_tlink_from", table_name="teleport_links")
    op.drop_table("teleport_links")

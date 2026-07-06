"""Add mob packs (FEAT-147): named heterogeneous groups of mobs.

Tables: mob_packs, mob_pack_members, active_mob_packs.
Alter: active_mobs + pack_group_id (FK -> active_mob_packs.id, SET NULL).

Revision ID: 018_add_mob_packs
Revises: 017_add_travel_cooldown_until
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa


revision = "018_add_mob_packs"
down_revision = "017_add_travel_cooldown_until"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "mob_packs"):
        op.create_table(
            "mob_packs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("avatar", sa.String(length=255), nullable=True),
            sa.Column("respawn_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("respawn_seconds", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_mob_packs_name", "mob_packs", ["name"])

    if not _has_table(inspector, "mob_pack_members"):
        op.create_table(
            "mob_pack_members",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("pack_id", sa.Integer(), nullable=False),
            sa.Column("mob_template_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["pack_id"], ["mob_packs.id"],
                name="fk_mob_pack_members_pack", ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["mob_template_id"], ["mob_templates.id"],
                name="fk_mob_pack_members_template", ondelete="CASCADE",
            ),
        )
        op.create_index("idx_mob_pack_members_pack", "mob_pack_members", ["pack_id"])

    if not _has_table(inspector, "active_mob_packs"):
        op.create_table(
            "active_mob_packs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("pack_id", sa.Integer(), nullable=False),
            sa.Column("location_id", sa.BigInteger(), nullable=False),
            sa.Column(
                "status",
                sa.Enum("alive", "in_battle", "dead"),
                nullable=False,
                server_default="alive",
            ),
            sa.Column("spawned_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=True),
            sa.Column("killed_at", sa.TIMESTAMP(), nullable=True),
            sa.Column("respawn_at", sa.TIMESTAMP(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["pack_id"], ["mob_packs.id"],
                name="fk_active_mob_packs_pack", ondelete="CASCADE",
            ),
        )
        op.create_index("idx_active_mob_packs_location", "active_mob_packs", ["location_id", "status"])
        op.create_index("idx_active_mob_packs_respawn", "active_mob_packs", ["respawn_at", "status"])

    if not _has_column(inspector, "active_mobs", "pack_group_id"):
        op.add_column(
            "active_mobs",
            sa.Column("pack_group_id", sa.Integer(), nullable=True),
        )
        op.create_index("idx_active_mobs_pack_group", "active_mobs", ["pack_group_id"])
        op.create_foreign_key(
            "fk_active_mobs_pack_group",
            "active_mobs", "active_mob_packs",
            ["pack_group_id"], ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "active_mobs", "pack_group_id"):
        try:
            op.drop_constraint("fk_active_mobs_pack_group", "active_mobs", type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_index("idx_active_mobs_pack_group", table_name="active_mobs")
        except Exception:
            pass
        op.drop_column("active_mobs", "pack_group_id")

    if _has_table(inspector, "active_mob_packs"):
        op.drop_table("active_mob_packs")
    if _has_table(inspector, "mob_pack_members"):
        op.drop_table("mob_pack_members")
    if _has_table(inspector, "mob_packs"):
        op.drop_table("mob_packs")

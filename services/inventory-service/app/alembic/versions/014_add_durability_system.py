"""Add durability system: max_durability, repair_power on items; current_durability on character_inventory and equipment_slots; seed repair kits.

Revision ID: 014_add_durability_system
Revises: 013_add_rune_type
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = '014_add_durability_system'
down_revision = '013_add_rune_type'
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tbl AND COLUMN_NAME = :col"
    ), {"tbl": table, "col": column})
    return result.scalar() > 0


def upgrade() -> None:
    conn = op.get_bind()

    # 1) items.max_durability
    if not _column_exists(conn, "items", "max_durability"):
        op.add_column("items", sa.Column("max_durability", sa.Integer(), nullable=False, server_default="0"))

    # 2) items.repair_power
    if not _column_exists(conn, "items", "repair_power"):
        op.add_column("items", sa.Column("repair_power", sa.Integer(), nullable=True))

    # 3) character_inventory.current_durability
    if not _column_exists(conn, "character_inventory", "current_durability"):
        op.add_column("character_inventory", sa.Column("current_durability", sa.Integer(), nullable=True))

    # 4) equipment_slots.current_durability
    if not _column_exists(conn, "equipment_slots", "current_durability"):
        op.add_column("equipment_slots", sa.Column("current_durability", sa.Integer(), nullable=True))

    # 5) Seed repair kit items (idempotent — skip if already exist)
    repair_kits = [
        ("Обычный ремонт-комплект", "common", 25, "Восстанавливает 25% прочности предмета"),
        ("Редкий ремонт-комплект", "rare", 50, "Восстанавливает 50% прочности предмета"),
        ("Эпический ремонт-комплект", "epic", 75, "Восстанавливает 75% прочности предмета"),
        ("Легендарный ремонт-комплект", "legendary", 100, "Восстанавливает 100% прочности предмета"),
    ]

    for name, rarity, power, desc in repair_kits:
        exists = conn.execute(
            sa.text("SELECT COUNT(*) FROM items WHERE name = :name"),
            {"name": name},
        ).scalar()
        if not exists:
            conn.execute(sa.text(
                "INSERT INTO items (name, item_type, item_rarity, item_level, max_stack_size, "
                "is_unique, repair_power, description, max_durability) "
                "VALUES (:name, 'resource', :rarity, 1, 99, 0, :power, :desc, 0)"
            ), {"name": name, "rarity": rarity, "power": power, "desc": desc})


def downgrade() -> None:
    op.drop_column("equipment_slots", "current_durability")
    op.drop_column("character_inventory", "current_durability")
    op.drop_column("items", "repair_power")
    op.drop_column("items", "max_durability")

    conn = op.get_bind()
    for name in [
        "Обычный ремонт-комплект",
        "Редкий ремонт-комплект",
        "Эпический ремонт-комплект",
        "Легендарный ремонт-комплект",
    ]:
        conn.execute(sa.text("DELETE FROM items WHERE name = :name"), {"name": name})

"""Add gem sockets system: gem item_type, socket_count, socketed_gems, seed junk item.

Revision ID: 010_add_gem_sockets
Revises: 009_add_transmutation_items
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = '010_add_gem_sockets'
down_revision = '009_add_transmutation_items'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column exists in a table (MySQL)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :column"
    ), {"table": table, "column": column})
    return result.scalar() > 0


def upgrade() -> None:
    # 1. Add 'gem' to items.item_type ENUM (idempotent — only if not already present)
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'items' AND COLUMN_NAME = 'item_type'"
    ))
    col_type = result.scalar()
    if col_type and "'gem'" not in col_type:
        op.execute(
            "ALTER TABLE items MODIFY COLUMN item_type "
            "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
            "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield',"
            "'blueprint','recipe','gem') "
            "NOT NULL"
        )

    # 2. Add socket_count to items
    if not _column_exists('items', 'socket_count'):
        op.add_column('items', sa.Column('socket_count', sa.Integer(), nullable=False, server_default='0'))

    # 3. Add socketed_gems to character_inventory
    if not _column_exists('character_inventory', 'socketed_gems'):
        op.add_column('character_inventory', sa.Column('socketed_gems', sa.Text(), nullable=True))

    # 4. Add socketed_gems to equipment_slots
    if not _column_exists('equipment_slots', 'socketed_gems'):
        op.add_column('equipment_slots', sa.Column('socketed_gems', sa.Text(), nullable=True))

    # 5. Seed "Ювелирный лом" item (idempotent via INSERT IGNORE)
    op.execute("""
        INSERT IGNORE INTO items (name, image, item_level, item_type, item_rarity, price, max_stack_size,
                           is_unique, description, fast_slot_bonus, socket_count,
                           strength_modifier, agility_modifier, intelligence_modifier,
                           endurance_modifier, health_modifier, energy_modifier,
                           mana_modifier, stamina_modifier, charisma_modifier,
                           luck_modifier, damage_modifier, dodge_modifier)
        VALUES
            ('Ювелирный лом', NULL, 0, 'resource', 'common', 10, 99,
             0, 'Ювелирный лом, полученный при переплавке украшений. Используется как ресурс для крафта.', 0, 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    """)


def downgrade() -> None:
    # Remove seed item
    op.execute("DELETE FROM items WHERE name = 'Ювелирный лом'")

    # Remove socketed_gems columns
    if _column_exists('equipment_slots', 'socketed_gems'):
        op.drop_column('equipment_slots', 'socketed_gems')

    if _column_exists('character_inventory', 'socketed_gems'):
        op.drop_column('character_inventory', 'socketed_gems')

    # Remove socket_count
    if _column_exists('items', 'socket_count'):
        op.drop_column('items', 'socket_count')

    # Remove 'gem' from item_type ENUM
    op.execute(
        "ALTER TABLE items MODIFY COLUMN item_type "
        "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
        "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield',"
        "'blueprint','recipe') "
        "NOT NULL"
    )

"""Add identification system: is_identified on character_inventory, identify_level on items, seed scrolls.

Revision ID: 011_add_identification_system
Revises: 010_add_gem_sockets
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = '011_add_identification_system'
down_revision = '010_add_gem_sockets'
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
    # 1. Add is_identified to character_inventory (default True for backwards compat)
    if not _column_exists('character_inventory', 'is_identified'):
        op.add_column('character_inventory', sa.Column(
            'is_identified', sa.Boolean(), nullable=False, server_default='1'
        ))

    # 2. Add identify_level to items (nullable — only scrolls have a value)
    if not _column_exists('items', 'identify_level'):
        op.add_column('items', sa.Column(
            'identify_level', sa.Integer(), nullable=True
        ))

    # 3. Seed identification scroll items (idempotent via INSERT IGNORE)
    op.execute("""
        INSERT IGNORE INTO items (name, image, item_level, item_type, item_rarity, price, max_stack_size,
                           is_unique, description, identify_level, fast_slot_bonus, socket_count,
                           strength_modifier, agility_modifier, intelligence_modifier,
                           endurance_modifier, health_modifier, energy_modifier,
                           mana_modifier, stamina_modifier, charisma_modifier,
                           luck_modifier, damage_modifier, dodge_modifier)
        VALUES
            ('Свиток идентификации (обычный)', NULL, 0, 'scroll', 'common', 50, 99,
             0, 'Свиток для опознания предметов обычной и редкой редкости.', 1, 0, 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Свиток идентификации (редкий)', NULL, 0, 'scroll', 'rare', 200, 99,
             0, 'Свиток для опознания предметов эпической и мифической редкости.', 2, 0, 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Свиток идентификации (легендарный)', NULL, 0, 'scroll', 'legendary', 1000, 99,
             0, 'Свиток для опознания предметов легендарной, божественной и демонической редкости.', 3, 0, 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    """)


def downgrade() -> None:
    # Remove seed scroll items
    op.execute("DELETE FROM items WHERE name IN ("
               "'Свиток идентификации (обычный)', "
               "'Свиток идентификации (редкий)', "
               "'Свиток идентификации (легендарный)')")

    # Remove identify_level from items
    if _column_exists('items', 'identify_level'):
        op.drop_column('items', 'identify_level')

    # Remove is_identified from character_inventory
    if _column_exists('character_inventory', 'is_identified'):
        op.drop_column('character_inventory', 'is_identified')

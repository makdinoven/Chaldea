"""Add essence extraction: essence_result_item_id on items; seed 7 crystals + 7 essences.

Revision ID: 008_add_essence_extraction
Revises: 007_add_sharpening_system
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = '008_add_essence_extraction'
down_revision = '007_add_sharpening_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add essence_result_item_id column to items table (idempotent)
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'items' AND COLUMN_NAME = 'essence_result_item_id'"
    ))
    if result.scalar() == 0:
        op.add_column('items', sa.Column(
            'essence_result_item_id', sa.Integer(), nullable=True
        ))
        op.create_foreign_key(
            'fk_items_essence_result_item_id',
            'items', 'items',
            ['essence_result_item_id'], ['id'],
            ondelete='SET NULL',
        )

    # Seed 7 essence items first (they are the targets) — idempotent via IGNORE
    op.execute("""
        INSERT IGNORE INTO items (name, image, item_level, item_type, item_rarity, price, max_stack_size,
                           is_unique, description, fast_slot_bonus,
                           strength_modifier, agility_modifier, intelligence_modifier,
                           endurance_modifier, health_modifier, energy_modifier,
                           mana_modifier, stamina_modifier, charisma_modifier,
                           luck_modifier, damage_modifier, dodge_modifier)
        VALUES
            ('Эссенция огня', NULL, 1, 'resource', 'common', 100, 99,
             0, 'Магическая эссенция, извлечённая из кристалла огня. Используется для крафта.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Эссенция воды', NULL, 1, 'resource', 'common', 100, 99,
             0, 'Магическая эссенция, извлечённая из кристалла воды. Используется для крафта.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Эссенция воздуха', NULL, 1, 'resource', 'common', 100, 99,
             0, 'Магическая эссенция, извлечённая из кристалла воздуха. Используется для крафта.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Эссенция молнии', NULL, 1, 'resource', 'common', 100, 99,
             0, 'Магическая эссенция, извлечённая из кристалла молнии. Используется для крафта.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Эссенция льда', NULL, 1, 'resource', 'common', 100, 99,
             0, 'Магическая эссенция, извлечённая из кристалла льда. Используется для крафта.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Эссенция света', NULL, 1, 'resource', 'common', 100, 99,
             0, 'Магическая эссенция, извлечённая из кристалла света. Используется для крафта.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Эссенция тьмы', NULL, 1, 'resource', 'common', 100, 99,
             0, 'Магическая эссенция, извлечённая из кристалла тьмы. Используется для крафта.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    """)

    # Seed 7 crystal items (without essence_result_item_id first — MySQL can't INSERT+SELECT same table)
    op.execute("""
        INSERT IGNORE INTO items (name, image, item_level, item_type, item_rarity, price, max_stack_size,
                           is_unique, description, fast_slot_bonus,
                           strength_modifier, agility_modifier, intelligence_modifier,
                           endurance_modifier, health_modifier, energy_modifier,
                           mana_modifier, stamina_modifier, charisma_modifier,
                           luck_modifier, damage_modifier, dodge_modifier)
        VALUES
            ('Кристалл огня', NULL, 1, 'resource', 'common', 50, 99,
             0, 'Магический кристалл, содержащий огненную энергию. Алхимик может извлечь эссенцию.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Кристалл воды', NULL, 1, 'resource', 'common', 50, 99,
             0, 'Магический кристалл, содержащий водную энергию. Алхимик может извлечь эссенцию.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Кристалл воздуха', NULL, 1, 'resource', 'common', 50, 99,
             0, 'Магический кристалл, содержащий воздушную энергию. Алхимик может извлечь эссенцию.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Кристалл молнии', NULL, 1, 'resource', 'common', 50, 99,
             0, 'Магический кристалл, содержащий электрическую энергию. Алхимик может извлечь эссенцию.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Кристалл льда', NULL, 1, 'resource', 'common', 50, 99,
             0, 'Магический кристалл, содержащий ледяную энергию. Алхимик может извлечь эссенцию.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Кристалл света', NULL, 1, 'resource', 'common', 50, 99,
             0, 'Магический кристалл, содержащий светлую энергию. Алхимик может извлечь эссенцию.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Кристалл тьмы', NULL, 1, 'resource', 'common', 50, 99,
             0, 'Магический кристалл, содержащий тёмную энергию. Алхимик может извлечь эссенцию.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    """)

    # Link crystals to essences via UPDATE (MySQL workaround for same-table INSERT+SELECT)
    pairs = [
        ('Кристалл огня', 'Эссенция огня'),
        ('Кристалл воды', 'Эссенция воды'),
        ('Кристалл воздуха', 'Эссенция воздуха'),
        ('Кристалл молнии', 'Эссенция молнии'),
        ('Кристалл льда', 'Эссенция льда'),
        ('Кристалл света', 'Эссенция света'),
        ('Кристалл тьмы', 'Эссенция тьмы'),
    ]
    for crystal, essence in pairs:
        op.execute(f"""
            UPDATE items SET essence_result_item_id = (
                SELECT id FROM (SELECT id FROM items WHERE name = '{essence}') AS t
            ) WHERE name = '{crystal}'
        """)


def downgrade() -> None:
    # Remove seeded crystals
    op.execute("""
        DELETE FROM items WHERE name IN (
            'Кристалл огня', 'Кристалл воды', 'Кристалл воздуха',
            'Кристалл молнии', 'Кристалл льда', 'Кристалл света', 'Кристалл тьмы'
        )
    """)

    # Remove seeded essences
    op.execute("""
        DELETE FROM items WHERE name IN (
            'Эссенция огня', 'Эссенция воды', 'Эссенция воздуха',
            'Эссенция молнии', 'Эссенция льда', 'Эссенция света', 'Эссенция тьмы'
        )
    """)

    op.drop_constraint('fk_items_essence_result_item_id', 'items', type_='foreignkey')
    op.drop_column('items', 'essence_result_item_id')

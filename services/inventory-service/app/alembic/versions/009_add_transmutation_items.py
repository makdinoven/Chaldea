"""Seed 4 transmuted resource items for the transmutation system.

Revision ID: 009_add_transmutation_items
Revises: 008_add_essence_extraction
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = '009_add_transmutation_items'
down_revision = '008_add_essence_extraction'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Seed 4 transmuted resource items (one per target rarity) — idempotent via IGNORE
    op.execute("""
        INSERT IGNORE INTO items (name, image, item_level, item_type, item_rarity, price, max_stack_size,
                           is_unique, description, fast_slot_bonus,
                           strength_modifier, agility_modifier, intelligence_modifier,
                           endurance_modifier, health_modifier, energy_modifier,
                           mana_modifier, stamina_modifier, charisma_modifier,
                           luck_modifier, damage_modifier, dodge_modifier)
        VALUES
            ('Трансмутированный ресурс (редкий)', NULL, 1, 'resource', 'rare', 200, 99,
             0, 'Ресурс, полученный путём алхимической трансмутации. Редкое качество.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Трансмутированный ресурс (эпический)', NULL, 1, 'resource', 'epic', 500, 99,
             0, 'Ресурс, полученный путём алхимической трансмутации. Эпическое качество.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Трансмутированный ресурс (легендарный)', NULL, 1, 'resource', 'legendary', 1000, 99,
             0, 'Ресурс, полученный путём алхимической трансмутации. Легендарное качество.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Трансмутированный ресурс (мифический)', NULL, 1, 'resource', 'mythical', 2500, 99,
             0, 'Ресурс, полученный путём алхимической трансмутации. Мифическое качество.', 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM items WHERE name IN (
            'Трансмутированный ресурс (редкий)',
            'Трансмутированный ресурс (эпический)',
            'Трансмутированный ресурс (легендарный)',
            'Трансмутированный ресурс (мифический)'
        )
    """)

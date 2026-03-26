"""Add sharpening system: enhancement_points_spent, enhancement_bonuses on
character_inventory and equipment_slots; whetstone_level on items; seed whetstones.

Revision ID: 007_add_sharpening_system
Revises: 006_add_recipe_xp_reward
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = '007_add_sharpening_system'
down_revision = '006_add_recipe_xp_reward'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # character_inventory: enhancement tracking
    op.add_column('character_inventory', sa.Column(
        'enhancement_points_spent', sa.Integer(), nullable=False, server_default="0"
    ))
    op.add_column('character_inventory', sa.Column(
        'enhancement_bonuses', sa.Text(), nullable=True
    ))

    # equipment_slots: enhancement tracking (travels with item on equip/unequip)
    op.add_column('equipment_slots', sa.Column(
        'enhancement_points_spent', sa.Integer(), nullable=False, server_default="0"
    ))
    op.add_column('equipment_slots', sa.Column(
        'enhancement_bonuses', sa.Text(), nullable=True
    ))

    # items: whetstone identification
    op.add_column('items', sa.Column(
        'whetstone_level', sa.Integer(), nullable=True
    ))

    # Seed 3 whetstone items
    op.execute("""
        INSERT INTO items (name, image, item_level, item_type, item_rarity, price, max_stack_size,
                           is_unique, description, whetstone_level, fast_slot_bonus,
                           strength_modifier, agility_modifier, intelligence_modifier,
                           endurance_modifier, health_modifier, energy_modifier,
                           mana_modifier, stamina_modifier, charisma_modifier,
                           luck_modifier, damage_modifier, dodge_modifier)
        VALUES
            ('Обычный точильный камень', NULL, 1, 'resource', 'common', 50, 99,
             0, 'Простой точильный камень. Шанс успешной заточки: 25%.', 1, 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Редкий точильный камень', NULL, 1, 'resource', 'rare', 200, 99,
             0, 'Качественный точильный камень. Шанс успешной заточки: 50%.', 2, 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            ('Легендарный точильный камень', NULL, 1, 'resource', 'legendary', 500, 99,
             0, 'Превосходный точильный камень. Шанс успешной заточки: 75%.', 3, 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    """)


def downgrade() -> None:
    # Remove seeded whetstones
    op.execute("""
        DELETE FROM items WHERE name IN (
            'Обычный точильный камень',
            'Редкий точильный камень',
            'Легендарный точильный камень'
        )
    """)

    op.drop_column('items', 'whetstone_level')
    op.drop_column('equipment_slots', 'enhancement_bonuses')
    op.drop_column('equipment_slots', 'enhancement_points_spent')
    op.drop_column('character_inventory', 'enhancement_bonuses')
    op.drop_column('character_inventory', 'enhancement_points_spent')

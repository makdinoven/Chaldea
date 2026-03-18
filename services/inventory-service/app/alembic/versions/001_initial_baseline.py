"""Initial baseline for inventory-service tables

Revision ID: 001_initial_baseline
Revises:
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'items' not in existing_tables:
        op.create_table(
            'items',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(100), unique=True, index=True),
            sa.Column('image', sa.String(255), nullable=True),
            sa.Column('item_level', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('item_type', sa.Enum(
                'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet',
                'main_weapon', 'consumable', 'additional_weapons', 'resource',
                'scroll', 'misc',
            ), nullable=False),
            sa.Column('item_rarity', sa.Enum(
                'common', 'rare', 'epic', 'legendary', 'mythical', 'divine', 'demonic',
            ), nullable=False),
            sa.Column('price', sa.Integer(), nullable=True),
            sa.Column('max_stack_size', sa.Integer(), server_default='1'),
            sa.Column('is_unique', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('description', sa.Text()),
            sa.Column('fast_slot_bonus', sa.Integer(), server_default='0'),
            sa.Column('armor_subclass', sa.Enum(
                'cloth', 'light_armor', 'medium_armor', 'heavy_armor',
                name='armor_subclass_enum',
            ), nullable=True),
            sa.Column('weapon_subclass', sa.Enum(
                'one_handed_weapon', 'two_handed_weapon', 'maces', 'axes',
                'battle_axes', 'hammers', 'polearms', 'scythes',
                'daggers', 'twin_daggers', 'short_swords', 'rapiers',
                'spears', 'bows', 'firearms', 'knuckledusters',
                'one_handed_staffs', 'two_handed_staffs', 'grimoires',
                'catalysts', 'spheres', 'wands', 'amulets', 'magic_weapon',
                name='weapon_subclass_enum',
            ), nullable=True),
            sa.Column('primary_damage_type', sa.Enum(
                'physical', 'catting', 'crushing', 'piercing', 'magic',
                'fire', 'ice', 'watering', 'electricity', 'wind',
                'sainting', 'damning',
                name='primary_damage_type_enum',
            ), nullable=True),
            sa.Column('strength_modifier', sa.Integer(), server_default='0'),
            sa.Column('agility_modifier', sa.Integer(), server_default='0'),
            sa.Column('intelligence_modifier', sa.Integer(), server_default='0'),
            sa.Column('endurance_modifier', sa.Integer(), server_default='0'),
            sa.Column('health_modifier', sa.Integer(), server_default='0'),
            sa.Column('energy_modifier', sa.Integer(), server_default='0'),
            sa.Column('mana_modifier', sa.Integer(), server_default='0'),
            sa.Column('stamina_modifier', sa.Integer(), server_default='0'),
            sa.Column('charisma_modifier', sa.Integer(), server_default='0'),
            sa.Column('luck_modifier', sa.Integer(), server_default='0'),
            sa.Column('damage_modifier', sa.Integer(), server_default='0'),
            sa.Column('dodge_modifier', sa.Integer(), server_default='0'),
            sa.Column('res_effects_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_physical_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_catting_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_crushing_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_piercing_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_magic_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_fire_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_ice_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_watering_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_electricity_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_wind_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_sainting_modifier', sa.Float(), server_default='0.0'),
            sa.Column('res_damning_modifier', sa.Float(), server_default='0.0'),
            sa.Column('critical_hit_chance_modifier', sa.Float(), server_default='0.0'),
            sa.Column('critical_damage_modifier', sa.Float(), server_default='0.0'),
            sa.Column('health_recovery', sa.Integer(), server_default='0'),
            sa.Column('energy_recovery', sa.Integer(), server_default='0'),
            sa.Column('mana_recovery', sa.Integer(), server_default='0'),
            sa.Column('stamina_recovery', sa.Integer(), server_default='0'),
            sa.Column('vul_effects_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_physical_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_catting_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_crushing_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_piercing_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_magic_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_fire_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_ice_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_watering_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_electricity_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_sainting_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_wind_modifier', sa.Float(), server_default='0.0'),
            sa.Column('vul_damning_modifier', sa.Float(), server_default='0.0'),
        )

    if 'character_inventory' not in existing_tables:
        op.create_table(
            'character_inventory',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('item_id', sa.Integer(), sa.ForeignKey('items.id'), nullable=False),
            sa.Column('quantity', sa.Integer(), server_default='1'),
        )

    if 'equipment_slots' not in existing_tables:
        op.create_table(
            'equipment_slots',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('slot_type', sa.Enum(
                'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet',
                'main_weapon', 'additional_weapons',
                'fast_slot_1', 'fast_slot_2', 'fast_slot_3', 'fast_slot_4',
                'fast_slot_5', 'fast_slot_6', 'fast_slot_7', 'fast_slot_8',
                'fast_slot_9', 'fast_slot_10',
            ), nullable=False),
            sa.Column('item_id', sa.Integer(), sa.ForeignKey('items.id'), nullable=True),
            sa.Column('is_enabled', sa.Boolean(), server_default='1'),
        )


def downgrade() -> None:
    op.drop_table('equipment_slots')
    op.drop_table('character_inventory')
    op.drop_table('items')

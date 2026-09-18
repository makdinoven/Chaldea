"""FEAT-168: боевые эффекты расходников — item_effects, item_damage_entries.

Two child tables whose row shape mirrors skills-service `skill_perk_effects` /
`skill_perk_damage`, so battle-service can hand item rows straight to
`buffs.apply_new_effects` and `battle_engine.compute_damage_with_rolls` without
any translation.

Plus three nullable columns on `items` describing *how* a consumable is used:
`consumable_action` (NULL/'instant' | 'weapon_coating' | 'cleanse'),
`coating_turns` and `coating_bonus_damage`. They are VARCHAR/INT/FLOAT and
deliberately NOT an ENUM — an ENUM change locks `items` (FEAT-165 hit exactly
that), while nullable trailing columns are INSTANT DDL on MySQL 8.

Upgrade: create the two tables, add the three columns.
Downgrade: drop the three columns and both tables. No backfill in either
direction — items that existed before this revision simply have zero effect
rows, so a downgrade only loses data created by this feature.

Revision ID: 024_item_battle_effects
Revises: 023_weapon_damage_backfill
Create Date: 2026-09-18

"""
from alembic import op
import sqlalchemy as sa

revision = '024_item_battle_effects'
down_revision = '023_weapon_damage_backfill'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'item_effects',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('target_side', sa.String(length=10), nullable=False, server_default='self'),
        sa.Column('effect_name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('chance', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('duration', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('magnitude', sa.Float(), nullable=False, server_default='0'),
        sa.Column('attribute_key', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(
            ['item_id'], ['items.id'],
            name='fk_item_effects_item', ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_item_effects_item_id', 'item_effects', ['item_id'])

    op.create_table(
        'item_damage_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('damage_type', sa.String(length=50), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('weapon_slot', sa.String(length=20), nullable=False, server_default='no_weapon'),
        sa.Column('target_side', sa.String(length=10), nullable=False, server_default='enemy'),
        sa.Column('chance', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('aoe_shape', sa.String(length=12), nullable=False, server_default='single'),
        sa.Column('aoe_falloff', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('aoe_max_targets', sa.Integer(), nullable=False, server_default='3'),
        sa.ForeignKeyConstraint(
            ['item_id'], ['items.id'],
            name='fk_item_damage_entries_item', ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_item_damage_entries_item_id', 'item_damage_entries', ['item_id'])

    op.add_column('items', sa.Column('consumable_action', sa.String(length=20), nullable=True))
    op.add_column('items', sa.Column('coating_turns', sa.Integer(), nullable=True))
    op.add_column('items', sa.Column('coating_bonus_damage', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('items', 'coating_bonus_damage')
    op.drop_column('items', 'coating_turns')
    op.drop_column('items', 'consumable_action')

    # The indexes are dropped with their tables. Dropping them separately fails
    # on MySQL with «needed in a foreign key constraint» (errno 1553).
    op.drop_table('item_damage_entries')
    op.drop_table('item_effects')

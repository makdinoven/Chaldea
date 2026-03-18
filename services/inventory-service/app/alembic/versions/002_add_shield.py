"""Add shield to item_type and slot_type ENUMs, create shield slots for existing characters

Revision ID: 002_add_shield
Revises: 001_initial_baseline
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa

revision = '002_add_shield'
down_revision = '001_initial_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) ALTER items.item_type ENUM to include 'shield'
    op.execute(
        "ALTER TABLE items MODIFY COLUMN item_type "
        "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
        "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield') "
        "NOT NULL"
    )

    # 2) ALTER equipment_slots.slot_type ENUM to include 'shield'
    op.execute(
        "ALTER TABLE equipment_slots MODIFY COLUMN slot_type "
        "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
        "'main_weapon','additional_weapons','shield',"
        "'fast_slot_1','fast_slot_2','fast_slot_3','fast_slot_4',"
        "'fast_slot_5','fast_slot_6','fast_slot_7','fast_slot_8',"
        "'fast_slot_9','fast_slot_10') "
        "NOT NULL"
    )

    # 3) INSERT shield slot for all existing characters that have equipment_slots but no shield slot
    op.execute(
        "INSERT INTO equipment_slots (character_id, slot_type, item_id, is_enabled) "
        "SELECT DISTINCT es.character_id, 'shield', NULL, 1 "
        "FROM equipment_slots es "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM equipment_slots es2 "
        "  WHERE es2.character_id = es.character_id AND es2.slot_type = 'shield'"
        ")"
    )


def downgrade() -> None:
    # 1) Remove shield slots (only empty ones to avoid data loss)
    op.execute(
        "DELETE FROM equipment_slots WHERE slot_type = 'shield' AND item_id IS NULL"
    )

    # 2) Revert equipment_slots.slot_type ENUM (remove 'shield')
    # NOTE: This will fail if any rows still have slot_type='shield' (with items equipped)
    op.execute(
        "ALTER TABLE equipment_slots MODIFY COLUMN slot_type "
        "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
        "'main_weapon','additional_weapons',"
        "'fast_slot_1','fast_slot_2','fast_slot_3','fast_slot_4',"
        "'fast_slot_5','fast_slot_6','fast_slot_7','fast_slot_8',"
        "'fast_slot_9','fast_slot_10') "
        "NOT NULL"
    )

    # 3) Revert items.item_type ENUM (remove 'shield')
    # NOTE: This will fail if any items with item_type='shield' exist
    op.execute(
        "ALTER TABLE items MODIFY COLUMN item_type "
        "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
        "'main_weapon','consumable','additional_weapons','resource','scroll','misc') "
        "NOT NULL"
    )

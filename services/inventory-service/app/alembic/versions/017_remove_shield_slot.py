"""Remove shield equipment slot (FEAT-149, Option A): shields keep item_type='shield'
but now equip into the 'additional_weapons' slot. Data migration: move any equipped
shield into a free off-hand slot, otherwise return it to character_inventory
(preserving enhancement/sockets/durability), delete all shield slot rows
(players + NPC — same equipment_slots table), then shrink the slot_type ENUM.

Reverse of 002_add_shield (slot_type part only; items.item_type is NOT touched).

Revision ID: 017_remove_shield_slot
Revises: 016_add_gathering_system
Create Date: 2026-07-17

"""
from alembic import op

revision = '017_remove_shield_slot'
down_revision = '016_add_gathering_system'
branch_labels = None
depends_on = None


# slot_type ENUM WITHOUT 'shield' (state AFTER this migration)
SLOT_TYPE_ENUM_NEW = (
    "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
    "'main_weapon','additional_weapons',"
    "'fast_slot_1','fast_slot_2','fast_slot_3','fast_slot_4',"
    "'fast_slot_5','fast_slot_6','fast_slot_7','fast_slot_8',"
    "'fast_slot_9','fast_slot_10')"
)

# slot_type ENUM WITH 'shield' (state BEFORE this migration) — used by downgrade()
SLOT_TYPE_ENUM_OLD = (
    "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
    "'main_weapon','additional_weapons','shield',"
    "'fast_slot_1','fast_slot_2','fast_slot_3','fast_slot_4',"
    "'fast_slot_5','fast_slot_6','fast_slot_7','fast_slot_8',"
    "'fast_slot_9','fast_slot_10')"
)


def upgrade() -> None:
    # Order matters: MySQL ENUM shrink fails if any row still carries the removed
    # value, so all data cleanup runs BEFORE the ALTER. All steps operate only on
    # slot_type='shield' rows, so a re-run after a mid-migration failure is safe.

    # 1) Move each equipped shield into the character's off-hand slot if it is free
    #    (item stays equipped — attribute modifiers remain applied, no desync).
    op.execute(
        "UPDATE equipment_slots aw "
        "JOIN equipment_slots sh "
        "  ON sh.character_id = aw.character_id "
        " AND sh.slot_type = 'shield' "
        " AND sh.item_id IS NOT NULL "
        "SET aw.item_id = sh.item_id, "
        "    aw.enhancement_points_spent = sh.enhancement_points_spent, "
        "    aw.enhancement_bonuses = sh.enhancement_bonuses, "
        "    aw.socketed_gems = sh.socketed_gems, "
        "    aw.current_durability = sh.current_durability, "
        "    sh.item_id = NULL, "
        "    sh.enhancement_points_spent = 0, "
        "    sh.enhancement_bonuses = NULL, "
        "    sh.socketed_gems = NULL, "
        "    sh.current_durability = NULL "
        "WHERE aw.slot_type = 'additional_weapons' AND aw.item_id IS NULL"
    )

    # 2) Off-hand occupied: return the remaining equipped shields to inventory,
    #    preserving enhancement/sockets/durability. Equipped items are always
    #    identified. Known accepted limitation (see FEAT-149 §3.1): attribute
    #    modifiers of these shields are NOT subtracted from character_attributes
    #    (no HTTP calls from a migration). Dev/prod counts verified ~0 — safety net.
    op.execute(
        "INSERT INTO character_inventory "
        "(character_id, item_id, quantity, is_identified, "
        " enhancement_points_spent, enhancement_bonuses, socketed_gems, current_durability) "
        "SELECT character_id, item_id, 1, 1, "
        "       enhancement_points_spent, enhancement_bonuses, socketed_gems, current_durability "
        "FROM equipment_slots "
        "WHERE slot_type = 'shield' AND item_id IS NOT NULL"
    )

    # 3) Delete all shield slot rows (now all empty or just copied out) —
    #    covers both player and NPC slots (same table).
    op.execute("DELETE FROM equipment_slots WHERE slot_type = 'shield'")

    # 4) Shrink the ENUM. items.item_type is intentionally NOT touched —
    #    'shield' survives as an item type (Option A).
    op.execute(
        "ALTER TABLE equipment_slots MODIFY COLUMN slot_type "
        + SLOT_TYPE_ENUM_NEW +
        " NOT NULL"
    )


def downgrade() -> None:
    # Mirror of 002_add_shield.upgrade() (slot_type part).
    # 1) Re-add 'shield' to the ENUM.
    op.execute(
        "ALTER TABLE equipment_slots MODIFY COLUMN slot_type "
        + SLOT_TYPE_ENUM_OLD +
        " NOT NULL"
    )

    # 2) Re-insert one empty shield slot per character that has equipment slots
    #    and lacks one. Items moved to the off-hand/inventory by upgrade() are
    #    intentionally not moved back (lossless for data).
    op.execute(
        "INSERT INTO equipment_slots (character_id, slot_type, item_id, is_enabled) "
        "SELECT DISTINCT es.character_id, 'shield', NULL, 1 "
        "FROM equipment_slots es "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM equipment_slots es2 "
        "  WHERE es2.character_id = es.character_id AND es2.slot_type = 'shield'"
        ")"
    )

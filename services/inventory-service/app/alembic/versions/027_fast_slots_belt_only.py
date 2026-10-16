"""Fast slots only from a belt: re-fit every character's slots to their gear.

`BASE_FAST_SLOTS` drops from 4 to 0 — a character gets as many fast slots as
the `fast_slot_bonus` of their equipped items (a belt), at most 10. Slots are
only re-counted on equip / unequip, so this migration does it once for every
character now: slots past their bonus are disabled and whatever lies in them
goes back to the bag (stacked onto an unfilled stack of the same item when
there is one, else a new row — like crud.return_item_to_inventory). Nothing is
lost; a bag may go past its soft 50-row limit, as unequipping already can.

Upgrade: re-fit the slots. Downgrade: no-op — which items sat in which slot
is not kept, and the old base of 4 would be restored by the code, not data.

Revision ID: 027_fast_slots_belt_only
Revises: 026_item_effect_secondary_mag
Create Date: 2026-10-16

"""
from alembic import op
import sqlalchemy as sa

revision = '027_fast_slots_belt_only'
down_revision = '026_item_effect_secondary_mag'
branch_labels = None
depends_on = None

MAX_FAST_SLOTS = 10


def _slot_number(slot_type):
    return int(slot_type.rsplit('_', 1)[1])


def upgrade():
    conn = op.get_bind()

    bonus_by_character = dict(conn.execute(sa.text(
        "SELECT es.character_id, COALESCE(SUM(i.fast_slot_bonus), 0) "
        "FROM equipment_slots es JOIN items i ON i.id = es.item_id "
        "GROUP BY es.character_id"
    )).fetchall())

    slots = conn.execute(sa.text(
        "SELECT es.id, es.character_id, es.slot_type, es.item_id, es.is_enabled, "
        "       i.max_stack_size "
        "FROM equipment_slots es LEFT JOIN items i ON i.id = es.item_id "
        "WHERE es.slot_type LIKE 'fast_slot_%'"
    )).fetchall()

    for slot_id, character_id, slot_type, item_id, is_enabled, max_stack in slots:
        available = max(0, min(MAX_FAST_SLOTS, int(bonus_by_character.get(character_id, 0) or 0)))
        keep = _slot_number(slot_type) <= available
        if keep:
            if not is_enabled:
                conn.execute(sa.text("UPDATE equipment_slots SET is_enabled = 1 WHERE id = :id"), {"id": slot_id})
            continue

        if item_id is not None:
            stack = None
            if (max_stack or 1) > 1:
                stack = conn.execute(sa.text(
                    "SELECT id FROM character_inventory "
                    "WHERE character_id = :c AND item_id = :i AND quantity < :m "
                    "ORDER BY quantity DESC LIMIT 1"
                ), {"c": character_id, "i": item_id, "m": max_stack}).scalar()
            if stack is not None:
                conn.execute(sa.text(
                    "UPDATE character_inventory SET quantity = quantity + 1 WHERE id = :id"
                ), {"id": stack})
            else:
                conn.execute(sa.text(
                    "INSERT INTO character_inventory (character_id, item_id, quantity) VALUES (:c, :i, 1)"
                ), {"c": character_id, "i": item_id})
        conn.execute(sa.text(
            "UPDATE equipment_slots SET item_id = NULL, is_enabled = 0 WHERE id = :id"
        ), {"id": slot_id})


def downgrade():
    pass

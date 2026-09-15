"""Rework weapon item types and kinds; drop the 'shield' item type.

- items.item_type loses 'shield'. A shield is an ordinary weapon now, told apart
  by its kind (buckler / targe / tower_shield).
- 'main_weapon' and 'additional_weapons' item types merge into one 'weapon':
  which hand a weapon may go into is decided by class/subclass equipment rules,
  not by the item. Equipment SLOT types are unchanged.
- items.weapon_subclass gets the current weapon taxonomy: one kind per value,
  each kind belonging to exactly one category (one-handed, one-and-a-half,
  two-handed, polearm, ranged, shields, other, magic). The category is derived
  from the kind in code, so it is not stored.

The old class-bound subclasses (warrior/rogue/mage lists) do not map onto the
new kinds one to one, so they are reset to NULL and re-set by hand in the admin
(agreed with the game owner; prod had 3 such items). Shield-typed items become
additional_weapons with no kind.

Order matters for MySQL ENUMs: widen, clean data, then shrink.

Revision ID: 019_rework_item_weapon_types
Revises: 018_add_item_full_image
Create Date: 2026-09-15

"""
from alembic import op

revision = '019_rework_item_weapon_types'
down_revision = '018_add_item_full_image'
branch_labels = None
depends_on = None


def _enum(values):
    return "ENUM(" + ",".join(f"'{v}'" for v in values) + ")"


ITEM_TYPES_OLD = [
    'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet', 'main_weapon',
    'consumable', 'additional_weapons', 'resource', 'scroll', 'misc', 'shield',
    'blueprint', 'recipe', 'gem', 'rune', 'gathering_tool',
]
ITEM_TYPES_NEW = [
    'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet', 'weapon',
    'consumable', 'resource', 'scroll', 'misc',
    'blueprint', 'recipe', 'gem', 'rune', 'gathering_tool',
]
ITEM_TYPES_UNION = ITEM_TYPES_OLD + ['weapon']

WEAPON_KINDS_OLD = [
    'one_handed_weapon', 'two_handed_weapon', 'maces', 'axes', 'battle_axes', 'hammers',
    'polearms', 'scythes', 'daggers', 'twin_daggers', 'short_swords', 'rapiers', 'spears',
    'bows', 'firearms', 'knuckledusters', 'one_handed_staffs', 'two_handed_staffs',
    'grimoires', 'catalysts', 'spheres', 'wands', 'amulets', 'magic_weapon',
]

WEAPON_KINDS_NEW = [
    # one-handed
    'sword', 'hatchet', 'mace', 'sabre', 'dagger', 'espada', 'tanto', 'war_pick',
    # one-and-a-half
    'bastard_sword', 'axe', 'katana', 'broadsword', 'rapier', 'war_hammer',
    # two-handed
    'zweihander', 'maul', 'battle_axe', 'scythe', 'nodachi',
    # polearms
    'halberd', 'glaive', 'pike', 'spear', 'naginata',
    # ranged
    'bow', 'pistol', 'musket',
    # shields
    'buckler', 'targe', 'tower_shield',
    # other
    'lute', 'knuckledusters',
    # magic
    'staff', 'grimoire', 'amulet', 'rod', 'magic_weapon', 'catalyst', 'wand',
]

# 'magic_weapon' exists in both lists; keep a de-duplicated union for the widen step
WEAPON_KINDS_UNION = WEAPON_KINDS_OLD + [k for k in WEAPON_KINDS_NEW if k not in WEAPON_KINDS_OLD]


def _in_list(values):
    return "(" + ",".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.execute("ALTER TABLE items MODIFY COLUMN item_type " + _enum(ITEM_TYPES_UNION) + " NOT NULL")
    op.execute("ALTER TABLE items MODIFY COLUMN weapon_subclass " + _enum(WEAPON_KINDS_UNION) + " NULL")

    stale = [k for k in WEAPON_KINDS_OLD if k not in WEAPON_KINDS_NEW]
    op.execute("UPDATE items SET weapon_subclass = NULL WHERE weapon_subclass IN " + _in_list(stale))
    # Old magic_weapon meant "any mage weapon"; the new one is a specific kind.
    # Reset it too so every legacy value gets reviewed by hand.
    op.execute("UPDATE items SET weapon_subclass = NULL WHERE weapon_subclass = 'magic_weapon'")
    op.execute(
        "UPDATE items SET item_type = 'weapon', weapon_subclass = NULL WHERE item_type = 'shield'"
    )
    op.execute(
        "UPDATE items SET item_type = 'weapon' "
        "WHERE item_type IN ('main_weapon', 'additional_weapons')"
    )

    op.execute("ALTER TABLE items MODIFY COLUMN weapon_subclass " + _enum(WEAPON_KINDS_NEW) + " NULL")
    op.execute("ALTER TABLE items MODIFY COLUMN item_type " + _enum(ITEM_TYPES_NEW) + " NOT NULL")


def downgrade() -> None:
    # Which hand a merged weapon used to be is lost; they all come back as main weapons
    op.execute("ALTER TABLE items MODIFY COLUMN item_type " + _enum(ITEM_TYPES_UNION) + " NOT NULL")
    op.execute("UPDATE items SET item_type = 'main_weapon' WHERE item_type = 'weapon'")
    op.execute("ALTER TABLE items MODIFY COLUMN item_type " + _enum(ITEM_TYPES_OLD) + " NOT NULL")
    op.execute("ALTER TABLE items MODIFY COLUMN weapon_subclass " + _enum(WEAPON_KINDS_UNION) + " NULL")
    fresh = [k for k in WEAPON_KINDS_NEW if k not in WEAPON_KINDS_OLD]
    op.execute("UPDATE items SET weapon_subclass = NULL WHERE weapon_subclass IN " + _in_list(fresh))
    op.execute("ALTER TABLE items MODIFY COLUMN weapon_subclass " + _enum(WEAPON_KINDS_OLD) + " NULL")

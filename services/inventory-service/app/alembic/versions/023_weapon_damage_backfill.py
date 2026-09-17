"""FEAT-167: take equipped weapons' damage out of character_attributes.damage.

Data-only revision, no schema change.

Until FEAT-167 every equipped item's effective damage (template
`items.damage_modifier` + sharpening + socketed gems) was folded into
`character_attributes.damage`. From FEAT-167 on, weapon damage is accounted per
hand (`effective_damage` on `GET /inventory/{cid}/equipment`) and is no longer
added to the attribute, so equip/unequip deltas would never again cancel the
historical amount that is already stored — it would stay in the attribute
forever. This revision subtracts it once.

Upgrade: for every `equipment_slots` row in `main_weapon` / `additional_weapons`
holding an item, compute that weapon's effective damage and subtract the sum per
character from `character_attributes.damage`, clamped at 0. Any character whose
value would have gone negative is logged as a warning (data anomaly — the value
is clamped, never silently wrapped).

Downgrade: recompute the same amounts and add them back. Exact only as long as
the equipment did not change in between (a weapon equipped/unequipped/sharpened
after the upgrade shifts the number). The rollback of record for prod is the DB
dump taken by `backup.sh` before the deploy; this downgrade is the convenience
path.

Cross-service write (documented deliberately): `character_attributes` is owned
by character-attributes-service, but inventory-service is the only service that
can compute the number (it owns `equipment_slots`, the sharpening JSON, the gem
sockets and durability). Single shared MySQL database, no schema change, and no
ordering dependency on char-attrs' own revision tree.

The arithmetic is INLINED on purpose: a migration must not import app code that
can change later (`crud.compute_item_damage`). QA pins the two against each
other on a fixture.

Revision ID: 023_weapon_damage_backfill
Revises: 022_profession_rework
Create Date: 2026-09-18

"""
import json
import logging

from alembic import op
import sqlalchemy as sa

revision = '023_weapon_damage_backfill'
down_revision = '022_profession_rework'
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

WEAPON_SLOTS = ('main_weapon', 'additional_weapons')

# Same query for both directions.
_SELECT_WEAPON_SLOTS = sa.text(
    """
    SELECT es.character_id AS character_id,
           es.slot_type AS slot_type,
           es.enhancement_bonuses AS enhancement_bonuses,
           es.socketed_gems AS socketed_gems,
           es.current_durability AS current_durability,
           i.damage_modifier AS damage_modifier,
           i.max_durability AS max_durability
    FROM equipment_slots es
    JOIN items i ON i.id = es.item_id
    WHERE es.slot_type IN ('main_weapon', 'additional_weapons')
      AND es.item_id IS NOT NULL
    """
)

_SELECT_GEM_DAMAGE = sa.text(
    "SELECT id, damage_modifier FROM items WHERE id IN :ids"
).bindparams(sa.bindparam("ids", expanding=True))


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("FEAT-167 backfill: не удалось разобрать JSON %r, использую пустое значение", raw)
        return default


def _gem_damage_map(conn, gem_ids):
    """{item_id: damage_modifier} for the gem/rune templates actually socketed."""
    if not gem_ids:
        return {}
    rows = conn.execute(_SELECT_GEM_DAMAGE, {"ids": sorted(gem_ids)}).fetchall()
    return {row[0]: int(row[1] or 0) for row in rows}


def _damage_per_character(conn) -> dict:
    """Effective weapon damage to remove, summed per character_id.

    Inlined copy of `crud.compute_item_damage`:
        damage_modifier + 1 x sharpening count on damage_modifier
        + sum(socketed gems' damage_modifier);
        0 when the weapon is broken (max_durability > 0 and current_durability <= 0).
    """
    slots = conn.execute(_SELECT_WEAPON_SLOTS).fetchall()
    if not slots:
        return {}

    parsed = []
    all_gem_ids = set()
    for row in slots:
        row = row._mapping
        gems = _parse_json(row["socketed_gems"], [])
        gem_ids = [g for g in gems if g]
        all_gem_ids.update(gem_ids)
        parsed.append((row, gem_ids))

    gem_damage = _gem_damage_map(conn, all_gem_ids)

    per_character = {}
    for row, gem_ids in parsed:
        max_durability = int(row["max_durability"] or 0)
        current_durability = row["current_durability"]
        if max_durability > 0 and current_durability is not None and int(current_durability) <= 0:
            continue  # broken weapon never contributed anything

        bonuses = _parse_json(row["enhancement_bonuses"], {})
        sharpen_count = 0
        if isinstance(bonuses, dict):
            try:
                sharpen_count = int(bonuses.get("damage_modifier", 0) or 0)
            except (TypeError, ValueError):
                logger.warning(
                    "FEAT-167 backfill: некорректная заточка damage_modifier=%r у персонажа %s",
                    bonuses.get("damage_modifier"), row["character_id"],
                )

        damage = int(row["damage_modifier"] or 0) + sharpen_count
        for gem_id in gem_ids:
            damage += gem_damage.get(gem_id, 0)

        if damage:
            per_character[row["character_id"]] = per_character.get(row["character_id"], 0) + damage

    return per_character


def _shift_damage(sign: int):
    """sign=-1 for upgrade (remove weapon damage), +1 for downgrade (put it back)."""
    conn = op.get_bind()
    per_character = _damage_per_character(conn)
    if not per_character:
        logger.info("FEAT-167 backfill: экипированного оружия с уроном не найдено, нечего пересчитывать")
        return

    changed = 0
    for character_id, amount in sorted(per_character.items()):
        row = conn.execute(
            sa.text("SELECT damage FROM character_attributes WHERE character_id = :cid"),
            {"cid": character_id},
        ).fetchone()
        if row is None:
            logger.warning(
                "FEAT-167 backfill: у персонажа %s есть оружие, но нет строки character_attributes — пропускаю",
                character_id,
            )
            continue

        old_damage = int(row[0] or 0)
        new_damage = old_damage + sign * int(amount)
        if new_damage < 0:
            logger.warning(
                "FEAT-167 backfill: у персонажа %s урон %s меньше урона оружия %s — обрезаю до 0 (аномалия данных)",
                character_id, old_damage, amount,
            )
            new_damage = 0

        conn.execute(
            sa.text("UPDATE character_attributes SET damage = :dmg WHERE character_id = :cid"),
            {"dmg": new_damage, "cid": character_id},
        )
        changed += 1

    logger.info(
        "FEAT-167 backfill: пересчитан урон у %s персонажей (знак %s)",
        changed, "-" if sign < 0 else "+",
    )


def upgrade():
    _shift_damage(-1)


def downgrade():
    _shift_damage(+1)

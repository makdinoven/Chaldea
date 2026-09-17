/**
 * FEAT-167 — the three damage values of the game, in one place.
 *
 * The model (see the feature's §3.1): weapon damage is NOT part of the
 * `damage` attribute any more. `character_attributes.damage` is the «base»
 * (stats, perks, armour/jewellery with their sharpening and gems, buffs/food),
 * and each weapon slot carries its own effective damage, delivered by
 * inventory-service as `effective_damage` on `GET /inventory/{id}/equipment`
 * (already sharpening-, gem- and durability-aware — a broken weapon is 0).
 *
 *   base                = <class main attribute> + attributes.damage
 *   Основной урон       = base + effective_damage(main_weapon)
 *   Дополнительный урон = base + effective_damage(additional_weapons)
 *   Урон без оружия     = base
 *
 * The battle engine (`battle-service/app/battle_engine.py`) computes exactly
 * the same three numbers from exactly the same two inputs, so the profile and
 * the battle log must never disagree. Anything else that needs a damage number
 * must call this helper instead of re-summing the terms — the duplicated third
 * term is what caused the double-count bug this feature fixes.
 */

import type { CharacterAttributes } from '../../../redux/slices/profileSlice';
import { CLASS_MAIN_ATTRIBUTE } from '../constants';

/** Weapon slots that contribute their own damage. */
export type WeaponSlotType = 'main_weapon' | 'additional_weapons';

/**
 * Minimal shape this helper needs from an equipment slot. Both
 * `profileSlice.EquipmentSlotData` and the admin `EquipmentSlot` satisfy it,
 * and synthetic empty-slot placeholders (which omit `effective_damage`) too.
 */
export interface DamageSlotLike {
  slot_type: string;
  effective_damage?: number | null;
  /** Current durability of the equipped item (absent on placeholders). */
  current_durability?: number | null;
  /** Only the one field needed to tell a broken weapon from an empty slot. */
  item?: { max_durability?: number | null } | null;
}

export interface DamageValues {
  /** Everything except weapons: class main attribute + the `damage` attribute. */
  base: number;
  /** base + the weapon in the main hand. */
  main: number;
  /** base + the weapon in the off hand. */
  additional: number;
  /** base only — what `weapon_slot: "no_weapon"` skills deal. */
  unarmed: number;
  /** The main-hand weapon is equipped but broken → it adds nothing. */
  mainBroken: boolean;
  /** The off-hand weapon is equipped but broken → it adds nothing. */
  additionalBroken: boolean;
}

const toNumber = (value: unknown): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

/** Effective damage of the weapon in `slotType` (0 when empty, broken or absent). */
export const weaponDamage = (
  equipment: readonly DamageSlotLike[] | null | undefined,
  slotType: WeaponSlotType,
): number => {
  const slot = (equipment ?? []).find((entry) => entry.slot_type === slotType);
  return toNumber(slot?.effective_damage);
};

/**
 * Is the weapon in `slotType` broken?
 *
 * Mirrors the backend rule (`inventory-service/app/crud.py::compute_item_damage`):
 * an item counts as broken when it *has* a durability pool (`max_durability > 0`)
 * and that pool is exhausted (`current_durability <= 0`). A broken weapon
 * contributes no damage and no other modifier, so without this flag «Осн. урон»
 * silently equals «Без оружия» and the player cannot tell why (FEAT-167 §3.9.3).
 *
 * An empty slot, an indestructible item or a slot whose `current_durability`
 * the payload omits is **not** reported as broken — we never guess.
 */
export const isWeaponBroken = (
  equipment: readonly DamageSlotLike[] | null | undefined,
  slotType: WeaponSlotType,
): boolean => {
  const slot = (equipment ?? []).find((entry) => entry.slot_type === slotType);
  if (!slot?.item) return false;
  const maxDurability = Number(slot.item.max_durability ?? 0);
  if (!(maxDurability > 0)) return false;
  const current = slot.current_durability;
  if (current === null || current === undefined) return false;
  return Number(current) <= 0;
};

/**
 * The «base» damage: class main attribute + the flat `damage` attribute.
 * Weapon damage is deliberately excluded — it lives on the slot.
 */
export const baseDamage = (
  attributes: CharacterAttributes | null | undefined,
  classId: number | null | undefined,
): number => {
  if (!attributes) return 0;
  const mainAttrKey =
    (classId != null && CLASS_MAIN_ATTRIBUTE[classId]) || 'strength';
  const mainAttrValue = toNumber(attributes[mainAttrKey as keyof CharacterAttributes]);
  return mainAttrValue + toNumber(attributes.damage);
};

/** All three damage values at once — the only supported way to display them. */
export const computeDamageValues = (
  attributes: CharacterAttributes | null | undefined,
  classId: number | null | undefined,
  equipment: readonly DamageSlotLike[] | null | undefined,
): DamageValues => {
  const base = baseDamage(attributes, classId);
  return {
    base,
    main: base + weaponDamage(equipment, 'main_weapon'),
    additional: base + weaponDamage(equipment, 'additional_weapons'),
    unarmed: base,
    mainBroken: isWeaponBroken(equipment, 'main_weapon'),
    additionalBroken: isWeaponBroken(equipment, 'additional_weapons'),
  };
};

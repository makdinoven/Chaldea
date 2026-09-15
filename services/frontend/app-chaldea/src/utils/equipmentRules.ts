/**
 * Client-side mirror of the class/subclass equipment rules enforced by
 * inventory-service. Used only for hints (greying out, drop targets): the
 * server stays the authority and answers 400 with the reason.
 */
import { TWO_HANDED_WEAPON_CATEGORIES, WEAPON_KIND_CATEGORY } from '../constants/items';

export interface EquipmentRules {
  restricted: boolean;
  class_id: number | null;
  subclass_key: string | null;
  /** null = no restriction */
  armor_classes: string[] | null;
  main_hand_kinds: string[] | null;
  off_hand_kinds: string[] | null;
  two_handed_kinds: string[];
}

export const MAIN_HAND_SLOT = 'main_weapon';
export const OFF_HAND_SLOT = 'additional_weapons';
export const HAND_SLOTS: readonly string[] = [MAIN_HAND_SLOT, OFF_HAND_SLOT];

/** Item types whose armor class is subject to the rules */
const ARMOR_RULE_TYPES: readonly string[] = ['head', 'body'];

interface RuleItem {
  item_type: string;
  weapon_subclass?: string | null;
  armor_subclass?: string | null;
}

const FALLBACK_TWO_HANDED_KINDS: readonly string[] = Object.entries(WEAPON_KIND_CATEGORY)
  .filter(([, category]) => TWO_HANDED_WEAPON_CATEGORIES.includes(category))
  .map(([kind]) => kind);

export const isTwoHandedKind = (kind: string | null | undefined, rules: EquipmentRules | null): boolean => {
  if (!kind) return false;
  const list = rules?.two_handed_kinds?.length ? rules.two_handed_kinds : FALLBACK_TWO_HANDED_KINDS;
  return list.includes(kind);
};

const allowedBy = (list: string[] | null | undefined, value: string | null | undefined) =>
  !value || !list || list.includes(value);

/** Hand slots a weapon may go into for this character (ignores what is equipped now) */
export const allowedHandSlots = (item: RuleItem, rules: EquipmentRules | null): string[] => {
  const kind = item.weapon_subclass;
  const slots: string[] = [];
  if (allowedBy(rules?.main_hand_kinds, kind)) slots.push(MAIN_HAND_SLOT);
  if (!isTwoHandedKind(kind, rules) && allowedBy(rules?.off_hand_kinds, kind)) slots.push(OFF_HAND_SLOT);
  return slots;
};

/** Whether the rules let this character wear a head/body item */
export const armorAllowed = (item: RuleItem, rules: EquipmentRules | null): boolean =>
  !ARMOR_RULE_TYPES.includes(item.item_type) || allowedBy(rules?.armor_classes, item.armor_subclass);

/**
 * True when the item is equipment the character's class/subclass cannot wear
 * in any slot. Non-equipment items are never "forbidden".
 */
export const isForbiddenForCharacter = (item: RuleItem, rules: EquipmentRules | null): boolean => {
  if (!rules?.restricted) return false;
  if (item.item_type === 'weapon') return allowedHandSlots(item, rules).length === 0;
  return !armorAllowed(item, rules);
};

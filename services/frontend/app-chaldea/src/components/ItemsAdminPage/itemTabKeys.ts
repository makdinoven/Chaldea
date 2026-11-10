import { rulesFor } from "./itemFormRules";

/* FEAT-210: tabs of the expanded item panel. They are sections of ONE form (one «Сохранить»),
   the set follows the LIVE item type of the form. */

export type ItemTabKey = "general" | "props" | "modifiers" | "effects" | "xp" | "conversions";

export const ITEM_TAB_KEYS: readonly ItemTabKey[] = ["general", "props", "modifiers", "effects", "xp", "conversions"];

export const ITEM_TAB_LABELS: Record<ItemTabKey, string> = {
  general: "Основное",
  props: "Свойства",
  modifiers: "Модификаторы",
  effects: "Боевые эффекты",
  xp: "Бафы опыта",
  conversions: "Переработка",
};

export const isItemTabKey = (value: string | null): value is ItemTabKey =>
  value !== null && (ITEM_TAB_KEYS as readonly string[]).includes(value);

/** Whether the «Свойства» tab has at least one section for this type (mirrors ItemForm's section conditions). */
const hasPropsSections = (itemType: string, isFood: boolean): boolean => {
  const r = rulesFor(itemType, isFood);
  const equipment =
    (r.armorSubclass || r.weaponFields || r.durability || Boolean(r.sockets) || r.fastSlotBonus) && !r.gatheringTool;
  return (
    equipment ||
    r.food ||
    itemType === "cloak" ||
    itemType === "head" ||
    r.recovery ||
    itemType === "scroll" ||
    r.identify ||
    r.resource ||
    r.gatheringTool ||
    r.furniture
  );
};

export const itemTabsFor = (itemType: string, isFood: boolean, hasConversions: boolean): ItemTabKey[] => {
  const r = rulesFor(itemType, isFood);
  const tabs: ItemTabKey[] = ["general"];
  if (hasPropsSections(itemType, isFood)) tabs.push("props");
  if (r.modifiers) tabs.push("modifiers");
  if (r.battleEffects) tabs.push("effects");
  if (r.buff) tabs.push("xp");
  if (hasConversions) tabs.push("conversions");
  return tabs;
};

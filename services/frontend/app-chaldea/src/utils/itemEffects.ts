// FEAT-168 — one shared reading of an item's battle configuration, so the
// battle screen (fast-slot picker, log) and the inventory (item card, cell
// tooltip) never describe the same potion differently.
//
// Every field is optional on purpose: battles snapshotted before this feature
// carry fast slots without any of these keys, and the backend reads them with
// `.get(..., default)` too. Nothing here may assume a key exists.

import {
  CLEANSE_EFFECT_NAME,
  damageLabel,
  describeEffect,
  pluralizeTurn,
} from "../components/pages/BattlePage/battleEffects";

/* ── Shapes (mirror of §3.3.1 in FEAT-168) ── */

/** NULL / "instant" — used on the spot; the other two are the new mechanics. */
export type ConsumableAction = "instant" | "weapon_coating" | "cleanse";

export interface ItemEffect {
  id?: number;
  target_side?: string | null;
  effect_name: string;
  description?: string | null;
  chance?: number | null;
  duration?: number | null;
  magnitude?: number | null;
  attribute_key?: string | null;
}

export interface ItemDamageEntry {
  id?: number;
  damage_type: string;
  amount?: number | null;
  description?: string | null;
  weapon_slot?: string | null;
  target_side?: string | null;
  chance?: number | null;
  aoe_shape?: string | null;
  aoe_falloff?: number | null;
  aoe_max_targets?: number | null;
}

/** The battle-relevant part of an item, as returned by inventory-service. */
export interface ItemBattleConfig {
  consumable_action?: string | null;
  coating_turns?: number | null;
  coating_bonus_damage?: number | null;
  effects?: ItemEffect[] | null;
  damage_entries?: ItemDamageEntry[] | null;
  // XP books (§3.9-bis). `xp_buffs` wins; the legacy triple is the fallback for
  // items saved before the feature and never re-edited.
  xp_buffs?: ItemXpBuff[] | null;
  buff_type?: string | null;
  buff_value?: number | null;
  buff_duration_minutes?: number | null;
}

/**
 * One «ускорение опыта» row on an item (FEAT-168 §3.9-bis). `value` is a share:
 * 0.25 = +25 %. An item may carry up to 8 rows, one per type.
 */
export interface ItemXpBuff {
  id?: number;
  buff_type: string;
  value: number;
  duration_minutes: number;
}

/** The eight XP sources a book may accelerate. */
export const XP_BUFF_PROFESSION = "xp_bonus";
export const XP_BUFF_GATHERING = "gathering_xp_bonus";
export const XP_BUFF_CHARACTER_ALL = "character_xp_bonus";
export const XP_BUFF_CHARACTER_BATTLE = "character_xp_battle_bonus";
export const XP_BUFF_CHARACTER_POST = "character_xp_post_bonus";
export const XP_BUFF_CHARACTER_QUEST = "character_xp_quest_bonus";
export const XP_BUFF_CHARACTER_TITLE = "character_xp_title_bonus";
export const XP_BUFF_CHARACTER_PASS = "character_xp_pass_bonus";

/** Dative form, reads as «+25% к опыту профессии» after a percentage. */
export const XP_BUFF_TYPE_LABELS: Record<string, string> = {
  [XP_BUFF_PROFESSION]: "к опыту профессии",
  [XP_BUFF_GATHERING]: "к опыту сбора",
  [XP_BUFF_CHARACTER_ALL]: "ко всему опыту персонажа",
  [XP_BUFF_CHARACTER_BATTLE]: "к опыту персонажа за бои",
  [XP_BUFF_CHARACTER_POST]: "к опыту персонажа за отыгрыш",
  [XP_BUFF_CHARACTER_QUEST]: "к опыту персонажа за задания",
  [XP_BUFF_CHARACTER_TITLE]: "к опыту персонажа за титулы",
  [XP_BUFF_CHARACTER_PASS]: "к опыту персонажа за боевой пропуск",
};

/** Nominative form for the admin select, where the group already says «Опыт персонажа». */
export const XP_BUFF_TYPE_GROUPS: {
  label: string | null;
  options: { value: string; label: string }[];
}[] = [
  {
    label: null,
    options: [
      { value: XP_BUFF_PROFESSION, label: "Опыт профессии" },
      { value: XP_BUFF_GATHERING, label: "Опыт сбора" },
    ],
  },
  {
    label: "Опыт персонажа",
    options: [
      // Umbrella first: it stacks on top of every granular source below.
      { value: XP_BUFF_CHARACTER_ALL, label: "Весь опыт персонажа" },
      { value: XP_BUFF_CHARACTER_BATTLE, label: "За бои" },
      { value: XP_BUFF_CHARACTER_POST, label: "За отыгрыш" },
      { value: XP_BUFF_CHARACTER_QUEST, label: "За задания" },
      { value: XP_BUFF_CHARACTER_TITLE, label: "За титулы" },
      { value: XP_BUFF_CHARACTER_PASS, label: "За боевой пропуск" },
    ],
  },
];

export const XP_BUFF_TYPES: string[] = XP_BUFF_TYPE_GROUPS.flatMap((g) =>
  g.options.map((o) => o.value),
);

export const MAX_XP_BUFF_ROWS = XP_BUFF_TYPES.length;
/** 10.0 = +1000 % */
export const MAX_XP_BUFF_VALUE = 10;
/** 7 days */
export const MAX_XP_BUFF_DURATION_MINUTES = 7 * 24 * 60;

export const xpBuffLabel = (buffType: string): string =>
  XP_BUFF_TYPE_LABELS[buffType] ?? buffType;

/** «+25% к опыту персонажа за задания на 60 мин» */
export const describeXpBuff = (buff: ItemXpBuff): string => {
  const pct = Math.round(Number(buff.value ?? 0) * 100);
  const minutes = Number(buff.duration_minutes ?? 0);
  const head = `+${pct}% ${xpBuffLabel(buff.buff_type)}`;
  return minutes > 0 ? `${head} на ${minutes} мин` : head;
};

/** Poison currently on the participant's weapon (Redis battle state). */
export interface WeaponCoating {
  item_id?: number;
  name?: string;
  bonus_damage?: number;
  turns_left?: number;
  effects?: ItemEffect[];
}

/* ── Labels ── */

export const CONSUMABLE_ACTION_OPTIONS: { value: ConsumableAction; label: string }[] = [
  { value: "instant", label: "Обычное применение" },
  { value: "weapon_coating", label: "Нанесение на оружие (яд)" },
  { value: "cleanse", label: "Очищение / противоядие" },
];

export const CONSUMABLE_ACTION_LABELS: Record<string, string> = Object.fromEntries(
  CONSUMABLE_ACTION_OPTIONS.map(({ value, label }) => [value, label]),
);

const TARGET_SIDE_SUFFIX: Record<string, string> = {
  enemy: "по врагу",
  ally: "на союзника",
  all_allies: "на команду",
};

const targetSuffix = (side: string | null | undefined): string =>
  TARGET_SIDE_SUFFIX[side ?? "self"] ?? "";

const chanceSuffix = (chance: number | null | undefined): string => {
  const value = Number(chance ?? 100);
  return Number.isFinite(value) && value < 100 ? `шанс ${Math.round(value)}%` : "";
};

const joinParts = (parts: (string | null | undefined)[]): string =>
  parts.filter((p): p is string => Boolean(p && p.trim())).join(", ");

export const normalizeAction = (
  action: string | null | undefined,
): ConsumableAction => (action === "weapon_coating" || action === "cleanse" ? action : "instant");

/* ── Single rows ── */

/** «+5 Сила (3 хода) по врагу, шанс 50%» */
export const describeItemEffect = (effect: ItemEffect): string => {
  const described = describeEffect({
    name: effect.effect_name,
    attribute: effect.attribute_key ?? undefined,
    magnitude: effect.magnitude ?? undefined,
    duration: effect.duration ?? undefined,
  });
  const head = described.detail ? `${described.label} (${described.detail})` : described.label;
  return joinParts([head, targetSuffix(effect.target_side), chanceSuffix(effect.chance)]);
};

/**
 * «Урон: 40 (Огонь)». No chance is shown: the engine does not roll `chance` on
 * an item damage row — it only rolls the target's dodge and resists.
 */
export const describeItemDamage = (entry: ItemDamageEntry): string => {
  const amount = Math.round(Number(entry.amount ?? 0));
  const type = entry.damage_type && entry.damage_type !== "all" ? damageLabel(entry.damage_type) : "";
  return `Урон: ${amount}${type ? ` (${type})` : ""}`;
};

/**
 * «Яд на оружие, +12 к урону, 4 хода». The coating already buffs the attack of
 * the turn it is applied on, so the count includes that turn.
 */
export const describeCoating = (config: ItemBattleConfig): string => {
  const turns = Number(config.coating_turns ?? 0);
  const bonus = Number(config.coating_bonus_damage ?? 0);
  return joinParts([
    "Яд на оружие",
    bonus ? `+${Math.round(bonus)} к урону` : "",
    turns > 0 ? `${pluralizeTurn(turns)}, считая текущий` : "",
  ]);
};

/* ── Whole item ── */

/**
 * The item's XP rows, applying the server's precedence rule: `xp_buffs` wins,
 * and an item with no rows falls back to the legacy single-buff columns.
 */
export const resolveXpBuffs = (
  config: ItemBattleConfig | null | undefined,
): ItemXpBuff[] => {
  const rows = config?.xp_buffs ?? [];
  if (rows.length > 0) return rows;
  if (config?.buff_type && config.buff_value != null) {
    return [
      {
        buff_type: config.buff_type,
        value: Number(config.buff_value),
        duration_minutes: Number(config.buff_duration_minutes ?? 60),
      },
    ];
  }
  return [];
};

export const describeXpBuffLines = (
  config: ItemBattleConfig | null | undefined,
): string[] => resolveXpBuffs(config).map(describeXpBuff);

export const hasItemBattleConfig = (config: ItemBattleConfig | null | undefined): boolean => {
  if (!config) return false;
  if ((config.effects ?? []).length > 0) return true;
  if ((config.damage_entries ?? []).length > 0) return true;
  return normalizeAction(config.consumable_action) === "weapon_coating";
};

/**
 * Every battle line of an item, in reading order: what it does to a weapon,
 * what damage it deals, what effects it grants or strips.
 */
export const describeItemBattleLines = (
  config: ItemBattleConfig | null | undefined,
): string[] => {
  if (!config) return [];
  const lines: string[] = [];
  if (normalizeAction(config.consumable_action) === "weapon_coating") {
    lines.push(describeCoating(config));
  }
  for (const entry of config.damage_entries ?? []) lines.push(describeItemDamage(entry));
  for (const effect of config.effects ?? []) lines.push(describeItemEffect(effect));
  return lines.filter(Boolean);
};

/** One-line version for tooltips and list rows. */
export const itemBattleSummary = (config: ItemBattleConfig | null | undefined): string =>
  describeItemBattleLines(config).join(" · ");

/** True when this item may not be used right now (a second coating). */
export const isCoatingBlocked = (
  config: ItemBattleConfig | null | undefined,
  coating: WeaponCoating | null | undefined,
): boolean =>
  normalizeAction(config?.consumable_action) === "weapon_coating" &&
  Boolean(coating) &&
  Number(coating?.turns_left ?? 0) > 0;

export const COATING_BLOCKED_MESSAGE =
  "На оружии уже действует яд — новый нельзя нанести, пока прежний не выдохнется.";

/** «Яд гадюки на оружии — осталось 3 хода» */
export const describeActiveCoating = (coating: WeaponCoating | null | undefined): string => {
  if (!coating) return "";
  const turns = Number(coating.turns_left ?? 0);
  const name = coating.name?.trim() || "Яд";
  return turns > 0 ? `${name} на оружии — осталось ${pluralizeTurn(turns)}` : `${name} на оружии`;
};

export { CLEANSE_EFFECT_NAME };

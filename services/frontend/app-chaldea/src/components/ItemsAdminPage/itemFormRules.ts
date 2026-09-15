/**
 * Which item fields the game actually reads for each item type.
 * The admin form shows only these, and the payload resets the rest so a type
 * switch never leaves stale values behind (e.g. armor class on a ring).
 */
import { ARMOR_SUBCLASS_TYPES, WEAPON_SUBCLASS_TYPES } from "../../constants/items";

export const EQUIPMENT_TYPES: readonly string[] = [
  "head", "body", "cloak", "belt", "weapon",
];
export const JEWELRY_TYPES: readonly string[] = ["ring", "necklace", "bracelet"];

/** Types that start with durability 100 when picked in the form */
export const DEFAULT_DURABILITY_TYPES: readonly string[] = [
  "head", "body", "cloak", "weapon",
];
export const DEFAULT_DURABILITY = 100;
export const DEFAULT_TOOL_DURABILITY = 50;

/* ── Modifier groups ── */

export interface ModDef {
  key: string;
  label: string;
  /** Float column: allow fractions in the input */
  fractional?: boolean;
}

export const ATTR_MODS: ModDef[] = [
  { key: "strength_modifier", label: "Сила" },
  { key: "agility_modifier", label: "Ловкость" },
  { key: "intelligence_modifier", label: "Интеллект" },
  { key: "endurance_modifier", label: "Живучесть" },
  { key: "health_modifier", label: "Здоровье" },
  { key: "energy_modifier", label: "Энергия" },
  { key: "mana_modifier", label: "Мана" },
  { key: "stamina_modifier", label: "Выносливость" },
  { key: "charisma_modifier", label: "Харизма" },
  { key: "luck_modifier", label: "Удача" },
  { key: "damage_modifier", label: "Урон" },
  { key: "dodge_modifier", label: "Уклонение" },
  { key: "critical_hit_chance_modifier", label: "Шанс крит. удара", fractional: true },
  { key: "critical_damage_modifier", label: "Урон крит. удара", fractional: true },
];

export const RES_MODS: ModDef[] = [
  { key: "res_effects_modifier", label: "Эффектам" },
  { key: "res_physical_modifier", label: "Физическому" },
  { key: "res_catting_modifier", label: "Режущему" },
  { key: "res_crushing_modifier", label: "Дробящему" },
  { key: "res_piercing_modifier", label: "Колющему" },
  { key: "res_magic_modifier", label: "Магии" },
  { key: "res_fire_modifier", label: "Огню" },
  { key: "res_ice_modifier", label: "Льду" },
  { key: "res_watering_modifier", label: "Воде" },
  { key: "res_electricity_modifier", label: "Молнии" },
  { key: "res_wind_modifier", label: "Ветру" },
  { key: "res_sainting_modifier", label: "Святому" },
  { key: "res_damning_modifier", label: "Проклятому" },
].map((m) => ({ ...m, fractional: true }));

export const VUL_MODS: ModDef[] = RES_MODS.map((m) => ({
  ...m,
  key: m.key.replace("res_", "vul_"),
}));

export const RECOVERY_FIELDS: ModDef[] = [
  { key: "health_recovery", label: "Здоровье" },
  { key: "mana_recovery", label: "Мана" },
  { key: "energy_recovery", label: "Энергия" },
  { key: "stamina_recovery", label: "Выносливость" },
];

/* ── Resource kinds ── */

export type ResourceKind = "plain" | "repair_kit" | "whetstone" | "crystal";

export const RESOURCE_KIND_LABELS: Record<ResourceKind, string> = {
  plain: "Обычный ресурс",
  repair_kit: "Ремкомплект",
  whetstone: "Точильный камень",
  crystal: "Кристалл (даёт эссенцию)",
};

export const REPAIR_POWER_OPTIONS = [25, 50, 75, 100] as const;

export const WHETSTONE_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: "1 — Обычный (25% успеха)" },
  { value: 2, label: "2 — Редкий (50% успеха)" },
  { value: 3, label: "3 — Легендарный (75% успеха)" },
];

export const IDENTIFY_LEVEL_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: "1 — обычные и редкие" },
  { value: 2, label: "2 — до мифических" },
  { value: 3, label: "3 — любые" },
];

/** The only buff the backend applies today (crud.py: xp_bonus) */
export const BUFF_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "xp_bonus", label: "Бонус к опыту" },
];

const isSet = (v: unknown) => v !== null && v !== undefined && v !== "";

/** Which resource kind a loaded item is, judging by the field it carries */
export const detectResourceKind = (item: Record<string, unknown>): ResourceKind => {
  if (isSet(item.repair_power)) return "repair_kit";
  if (isSet(item.whetstone_level)) return "whetstone";
  if (isSet(item.essence_result_item_id)) return "crystal";
  return "plain";
};

/* ── Per-type visibility ── */

export interface FieldRules {
  modifiers: boolean;
  durability: boolean;
  /** "runes" for armor/weapons, "gems" for jewelry */
  sockets: "runes" | "gems" | null;
  fastSlotBonus: boolean;
  armorSubclass: boolean;
  weaponFields: boolean;
  recovery: boolean;
  buff: boolean;
  identify: boolean;
  resourceKind: boolean;
  blueprintRecipe: boolean;
  recipeAuto: boolean;
  gatheringTool: boolean;
}

export const rulesFor = (itemType: string): FieldRules => {
  const equipment = EQUIPMENT_TYPES.includes(itemType);
  const jewelry = JEWELRY_TYPES.includes(itemType);
  return {
    modifiers: equipment || jewelry || itemType === "gem" || itemType === "rune",
    durability: equipment || itemType === "gathering_tool",
    sockets: equipment ? "runes" : jewelry ? "gems" : null,
    fastSlotBonus: equipment || jewelry,
    armorSubclass: ARMOR_SUBCLASS_TYPES.includes(itemType),
    weaponFields: WEAPON_SUBCLASS_TYPES.includes(itemType),
    recovery: itemType === "consumable" || itemType === "scroll",
    buff: itemType === "consumable",
    identify: itemType === "scroll",
    resourceKind: itemType === "resource",
    blueprintRecipe: itemType === "blueprint",
    recipeAuto: itemType === "recipe",
    gatheringTool: itemType === "gathering_tool",
  };
};

/* ── Payload ── */

const num = (v: unknown): number => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

const numOrNull = (v: unknown): number | null =>
  v === null || v === undefined || v === "" ? null : num(v);

/**
 * Normalise raw form state (inputs keep strings) into the API payload and
 * reset every field the chosen type does not use.
 */
export const buildItemPayload = (
  item: Record<string, unknown>,
  resourceKind: ResourceKind,
): Record<string, unknown> => {
  const type = String(item.item_type);
  const rules = rulesFor(type);
  const payload: Record<string, unknown> = { ...item };

  // Response-only fields the API does not accept
  delete payload.id;
  delete payload.image;
  delete payload.full_image;

  payload.item_level = num(item.item_level);
  payload.price = num(item.price);
  payload.max_stack_size = Math.max(1, num(item.max_stack_size));

  for (const { key } of [...ATTR_MODS, ...RES_MODS, ...VUL_MODS]) {
    payload[key] = rules.modifiers ? num(item[key]) : 0;
  }
  for (const { key } of RECOVERY_FIELDS) {
    payload[key] = rules.recovery ? num(item[key]) : 0;
  }

  payload.max_durability = rules.durability ? num(item.max_durability) : 0;
  payload.socket_count = rules.sockets ? num(item.socket_count) : 0;
  payload.fast_slot_bonus = rules.fastSlotBonus ? num(item.fast_slot_bonus) : 0;

  payload.armor_subclass = rules.armorSubclass ? item.armor_subclass || null : null;
  payload.weapon_subclass = rules.weaponFields ? item.weapon_subclass || null : null;
  payload.primary_damage_type = rules.weaponFields ? item.primary_damage_type || null : null;

  const hasBuff = rules.buff && Boolean(item.buff_type);
  payload.buff_type = hasBuff ? item.buff_type : null;
  payload.buff_value = hasBuff ? num(item.buff_value) : null;
  payload.buff_duration_minutes = hasBuff ? num(item.buff_duration_minutes) : null;

  payload.identify_level = rules.identify ? numOrNull(item.identify_level) : null;

  payload.repair_power =
    rules.resourceKind && resourceKind === "repair_kit" ? numOrNull(item.repair_power) : null;
  payload.whetstone_level =
    rules.resourceKind && resourceKind === "whetstone" ? numOrNull(item.whetstone_level) : null;
  payload.essence_result_item_id =
    rules.resourceKind && resourceKind === "crystal" ? numOrNull(item.essence_result_item_id) : null;

  // Recipe items are managed by the recipe editor: keep their link untouched
  if (!rules.recipeAuto) {
    payload.blueprint_recipe_id = rules.blueprintRecipe ? numOrNull(item.blueprint_recipe_id) : null;
  }

  payload.tool_category = rules.gatheringTool ? item.tool_category || null : null;
  for (const key of ["gather_double_chance_bonus", "gather_speed_bonus_pct", "gather_stamina_bonus_pct"]) {
    payload[key] = rules.gatheringTool ? num(item[key]) : 0;
  }

  return payload;
};

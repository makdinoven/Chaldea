/**
 * Which item fields the game actually reads for each item type.
 * The admin form shows only these, and the payload resets the rest so a type
 * switch never leaves stale values behind (e.g. armor class on a ring).
 */
import {
  ARMOR_SUBCLASS_TYPES,
  ITEM_RARITIES,
  WEAPON_SUBCLASS_TYPES,
  isEquipmentOnlyRarity,
  isWearableType,
} from "../../constants/items";
import {
  JEWELRY_SOCKET_TYPES,
  RAW_RESOURCE_SUBCATEGORIES,
  RESOURCE_SUBCATEGORY_LABELS,
  RUNE_SOCKET_TYPES,
  WHETSTONE_GROUPS,
  WHETSTONE_GROUP_LABELS,
  WHETSTONE_GROUP_TARGETS,
  type ResourceSubcategory,
  type WhetstoneGroup,
} from "../../constants/professions";

export const EQUIPMENT_TYPES: readonly string[] = [
  "head", "body", "cloak", "belt", "weapon",
];
export const JEWELRY_TYPES: readonly string[] = ["ring", "necklace", "bracelet"];

/**
 * Rarities the admin may pick for a type: mythical/divine/demonic exist only
 * on wearable equipment (FEAT-164). A set check, not a ranking.
 */
export const allowedRaritiesFor = (itemType: string): readonly string[] =>
  isWearableType(itemType)
    ? ITEM_RARITIES
    : ITEM_RARITIES.filter((r) => !isEquipmentOnlyRarity(r));

export const RARITY_CAP_MESSAGE =
  "Мифическая, божественная и демоническая редкость доступны только для снаряжения";

export const FOOD_HINT =
  "Сытость на 24 ч. Бонус к восстановлению по редкости: обычная +50%, редкая +100%, эпическая +150%, легендарная +200%. " +
  "Характеристики ниже действуют, пока активна сытость; восстановление срабатывает сразу при еде.";

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

/* ── Resources ── */

export const WHETSTONE_GROUP_OPTIONS: { value: WhetstoneGroup; label: string }[] = WHETSTONE_GROUPS.map((g) => ({
  value: g,
  label: `${WHETSTONE_GROUP_LABELS[g]} — ${WHETSTONE_GROUP_TARGETS[g]}`,
}));

export const isResourceSubcategory = (value: unknown): value is ResourceSubcategory =>
  typeof value === "string" && value in RESOURCE_SUBCATEGORY_LABELS;

export const isRawSubcategory = (value: unknown): value is ResourceSubcategory =>
  typeof value === "string" && (RAW_RESOURCE_SUBCATEGORIES as readonly string[]).includes(value);

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
  /** Resource subcategory select (+ whetstone / repair kit fields, refining config) */
  resource: boolean;
  recipeAuto: boolean;
  gatheringTool: boolean;
  /** "Еда" checkbox (consumables only) */
  food: boolean;
}

export const rulesFor = (itemType: string, isFood = false): FieldRules => {
  const equipment = EQUIPMENT_TYPES.includes(itemType);
  const jewelry = JEWELRY_TYPES.includes(itemType);
  const food = itemType === "consumable";
  const eatable = food && isFood;
  return {
    // Food bonuses use the same modifier columns as equipment
    modifiers: equipment || jewelry || itemType === "gem" || itemType === "rune" || eatable,
    durability: equipment || itemType === "gathering_tool",
    // Belts have no sockets (quick slots only, FEAT-165)
    sockets: RUNE_SOCKET_TYPES.has(itemType) ? "runes" : JEWELRY_SOCKET_TYPES.has(itemType) ? "gems" : null,
    fastSlotBonus: equipment || jewelry,
    armorSubclass: ARMOR_SUBCLASS_TYPES.includes(itemType),
    weaponFields: WEAPON_SUBCLASS_TYPES.includes(itemType),
    recovery: itemType === "consumable" || itemType === "scroll",
    // Food cannot be a buff item
    buff: itemType === "consumable" && !eatable,
    identify: itemType === "scroll",
    resource: itemType === "resource",
    recipeAuto: itemType === "recipe",
    gatheringTool: itemType === "gathering_tool",
    food,
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
export const buildItemPayload = (item: Record<string, unknown>): Record<string, unknown> => {
  const type = String(item.item_type);
  const rules = rulesFor(type, Boolean(item.is_food));
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

  payload.is_food = rules.food && Boolean(item.is_food);

  payload.identify_level = rules.identify ? numOrNull(item.identify_level) : null;

  const subcategory = rules.resource && item.resource_subcategory ? String(item.resource_subcategory) : null;
  payload.resource_subcategory = subcategory;
  payload.repair_power = subcategory === "repair_kit" ? numOrNull(item.repair_power) : null;
  const whetstone = subcategory === "whetstone";
  payload.whetstone_level = whetstone ? numOrNull(item.whetstone_level) : null;
  payload.whetstone_group = whetstone ? item.whetstone_group || null : null;

  // Recipe items are managed by the recipe editor: keep their link untouched
  if (!rules.recipeAuto) {
    payload.blueprint_recipe_id = null;
  }

  payload.tool_category = rules.gatheringTool ? item.tool_category || null : null;
  for (const key of ["gather_double_chance_bonus", "gather_speed_bonus_pct", "gather_stamina_bonus_pct"]) {
    payload[key] = rules.gatheringTool ? num(item[key]) : 0;
  }

  return payload;
};

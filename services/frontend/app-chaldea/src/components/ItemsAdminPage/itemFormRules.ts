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
import { STAT_MODIFIERS } from "../AdminSkillsPage/skillConstants";
import { STAT_MODIFIER_NAME } from "../AdminSkillsPage/SkillEffectSections";
import {
  CLEANSE_EFFECT_NAME,
  CLEANSE_SELECTORS,
} from "../pages/BattlePage/battleEffects";
import {
  MAX_XP_BUFF_DURATION_MINUTES,
  MAX_XP_BUFF_ROWS,
  MAX_XP_BUFF_VALUE,
  XP_BUFF_TYPES,
  normalizeAction,
  resolveXpBuffs,
  type ItemDamageEntry,
  type ItemEffect,
  type ItemXpBuff,
} from "../../utils/itemEffects";

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

/* ── XP books (FEAT-168 §3.9-bis): a repeatable list, not one buff ── */

export const newXpBuff = (buffType: string): ItemXpBuff => ({
  buff_type: buffType,
  value: 0.25,
  duration_minutes: 60,
});

/** The first type not already used in another row, or null when all 8 are taken. */
export const firstFreeXpBuffType = (rows: ItemXpBuff[]): string | null =>
  XP_BUFF_TYPES.find((t) => !rows.some((r) => r.buff_type === t)) ?? null;

/**
 * Client-side mirror of the server rules in §3.9-bis C, with the same Russian
 * messages. Server errors are still surfaced — this only saves a round trip.
 */
export const validateXpBuffs = (
  rows: ItemXpBuff[],
  itemType: string,
  isFood: boolean,
): string | null => {
  if (rows.length === 0) return null;
  if (rows.length > MAX_XP_BUFF_ROWS) return `Не больше ${MAX_XP_BUFF_ROWS} строк опыта у предмета`;

  const seen = new Set<string>();
  for (const row of rows) {
    if (!XP_BUFF_TYPES.includes(row.buff_type)) return "Недопустимый тип опыта";
    if (seen.has(row.buff_type))
      return "Один тип опыта можно указать у предмета только один раз";
    seen.add(row.buff_type);

    const value = Number(row.value ?? 0);
    if (!Number.isFinite(value) || value <= 0 || value > MAX_XP_BUFF_VALUE)
      return `Прибавка к опыту должна быть больше 0 и не больше ${MAX_XP_BUFF_VALUE * 100} %`;

    const minutes = Number(row.duration_minutes ?? 0);
    if (!Number.isFinite(minutes) || minutes < 1 || minutes > MAX_XP_BUFF_DURATION_MINUTES)
      return `Длительность баффа опыта должна быть от 1 до ${MAX_XP_BUFF_DURATION_MINUTES} минут`;
  }

  if (isFood) return "Еда не может ускорять опыт";
  if (itemType !== "consumable" && itemType !== "scroll")
    return "Ускорение опыта доступно только для расходников и свитков";
  return null;
};

/* ── Battle effects on consumables / scrolls (FEAT-168) ── */

export const MAX_ITEM_EFFECTS = 20;
export const MAX_ITEM_DAMAGE_ENTRIES = 10;
export const MAX_COATING_TURNS = 50;
export const MAX_COATING_BONUS_DAMAGE = 10000;
export const MAX_EFFECT_MAGNITUDE = 10000;
/** Defaults written into the state when the admin picks «яд на оружие» */
export const DEFAULT_COATING_TURNS = 1;
export const DEFAULT_COATING_BONUS_DAMAGE = 0;

export const newItemEffect = (): ItemEffect => ({
  target_side: "self",
  effect_name: STAT_MODIFIER_NAME,
  description: "",
  chance: 100,
  duration: 3,
  magnitude: 0,
  attribute_key: STAT_MODIFIERS[0].key,
});

export const newCleanseEffect = (): ItemEffect => ({
  target_side: "self",
  effect_name: CLEANSE_EFFECT_NAME,
  description: "",
  chance: 100,
  duration: 0,
  magnitude: 0,
  attribute_key: CLEANSE_SELECTORS[0].value,
});

export const newItemDamageEntry = (): ItemDamageEntry => ({
  damage_type: "fire",
  amount: 0,
  description: "",
  weapon_slot: "no_weapon",
  target_side: "enemy",
  chance: 100,
  aoe_shape: "single",
  aoe_falloff: 50,
  aoe_max_targets: 3,
});

const inRange = (value: unknown, min: number, max: number): boolean => {
  const n = Number(value ?? 0);
  return Number.isFinite(n) && n >= min && n <= max;
};

/**
 * Client-side mirror of the server validation (§3.12). Returns a Russian error
 * for the first problem found, or null when the configuration is acceptable.
 *
 * The strings are **verbatim copies of the inventory-service messages** so the
 * admin reads the same sentence whether the form or the API catches the
 * problem. Changing one without the other is the bug this comment prevents.
 */
export const validateBattleConfig = (item: Record<string, unknown>): string | null => {
  const effects = (item.effects as ItemEffect[] | undefined) ?? [];
  const damage = (item.damage_entries as ItemDamageEntry[] | undefined) ?? [];

  if (effects.length > MAX_ITEM_EFFECTS)
    return `Не больше ${MAX_ITEM_EFFECTS} эффектов у предмета`;
  if (damage.length > MAX_ITEM_DAMAGE_ENTRIES)
    return `Не больше ${MAX_ITEM_DAMAGE_ENTRIES} строк урона у предмета`;

  for (const row of effects) {
    if (!row.effect_name || !String(row.effect_name).trim())
      return "Название эффекта обязательно";
    if (!inRange(row.chance ?? 100, 0, 100))
      return "Шанс эффекта должен быть от 0 до 100";
    if (!inRange(row.duration ?? 0, 0, 100))
      return "Длительность эффекта должна быть от 0 до 100 ходов";
    if (!inRange(row.magnitude ?? 0, -MAX_EFFECT_MAGNITUDE, MAX_EFFECT_MAGNITUDE))
      return `Сила эффекта должна быть от -${MAX_EFFECT_MAGNITUDE} до ${MAX_EFFECT_MAGNITUDE}`;
  }

  for (const row of damage) {
    if (!inRange(row.chance ?? 100, 0, 100)) return "Шанс урона должен быть от 0 до 100";
    if (!inRange(row.amount ?? 0, -MAX_EFFECT_MAGNITUDE, MAX_EFFECT_MAGNITUDE))
      return `Урон должен быть от -${MAX_EFFECT_MAGNITUDE} до ${MAX_EFFECT_MAGNITUDE}`;
    if (!inRange(row.aoe_falloff ?? 50, 0, 100))
      return "Затухание области должно быть от 0 до 100";
    if (!inRange(row.aoe_max_targets ?? 3, 1, 10))
      return "Число целей области должно быть от 1 до 10";
  }

  if (normalizeAction(item.consumable_action as string | null) === "weapon_coating") {
    if (!inRange(item.coating_turns ?? 0, 1, MAX_COATING_TURNS))
      return `Длительность яда должна быть от 1 до ${MAX_COATING_TURNS} ходов`;
    if (!inRange(item.coating_bonus_damage ?? 0, 0, MAX_COATING_BONUS_DAMAGE))
      return `Прибавка урона от яда должна быть от 0 до ${MAX_COATING_BONUS_DAMAGE}`;
  }

  return null;
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
  /** Resource subcategory select (+ whetstone / repair kit fields, refining config) */
  resource: boolean;
  recipeAuto: boolean;
  gatheringTool: boolean;
  /** "Еда" checkbox (consumables only) */
  food: boolean;
  /** Battle effect editor: potions, poisons, scrolls — never food (FEAT-168) */
  battleEffects: boolean;
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
    // XP books: consumables and scrolls, never food (§3.9-bis E)
    buff: (itemType === "consumable" || itemType === "scroll") && !eatable,
    identify: itemType === "scroll",
    resource: itemType === "resource",
    recipeAuto: itemType === "recipe",
    gatheringTool: itemType === "gathering_tool",
    food,
    battleEffects: (itemType === "consumable" || itemType === "scroll") && !eatable,
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

  // XP books (§3.9-bis): `xp_buffs` is the single source of truth and is always
  // sent; the backend clears the legacy columns when the list is non-empty. The
  // legacy triple is never written from the form any more.
  const xpRows = rules.buff ? ((item.xp_buffs as ItemXpBuff[] | undefined) ?? []) : [];
  payload.xp_buffs = xpRows.map(({ id: _id, ...row }) => ({
    buff_type: row.buff_type,
    value: Number(row.value ?? 0),
    duration_minutes: Math.round(num(row.duration_minutes)),
  }));
  // Clear the legacy columns only when the admin actually left rows behind: the
  // backend clears them itself for a non-empty list, and nulling them on an
  // empty list would silently strip the book from an item this form never
  // touched (a type without the editor, or a row the admin did not open).
  if (!rules.buff || xpRows.length > 0) {
    payload.buff_type = null;
    payload.buff_value = null;
    payload.buff_duration_minutes = null;
  }

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

  // Battle effects (FEAT-168) — replace-all lists. A type without the editor
  // sends empty lists so switching a poison to a ring never leaves rows behind.
  const action = rules.battleEffects ? normalizeAction(item.consumable_action as string | null) : "instant";
  const coating = action === "weapon_coating";
  payload.consumable_action = rules.battleEffects && action !== "instant" ? action : null;
  payload.coating_turns = coating ? Math.max(1, num(item.coating_turns)) : null;
  payload.coating_bonus_damage = coating ? num(item.coating_bonus_damage) : null;
  payload.effects = rules.battleEffects
    ? ((item.effects as ItemEffect[] | undefined) ?? []).map(({ id: _id, ...row }) => ({
        ...row,
        chance: num(row.chance ?? 100),
        duration: num(row.duration ?? 0),
        magnitude: num(row.magnitude ?? 0),
        target_side: row.target_side || "self",
      }))
    : [];
  payload.damage_entries = rules.battleEffects
    ? ((item.damage_entries as ItemDamageEntry[] | undefined) ?? []).map(({ id: _id, ...row }) => ({
        ...row,
        amount: num(row.amount ?? 0),
        chance: num(row.chance ?? 100),
        aoe_falloff: num(row.aoe_falloff ?? 50),
        aoe_max_targets: Math.max(1, num(row.aoe_max_targets ?? 3)),
        weapon_slot: row.weapon_slot || "no_weapon",
        target_side: row.target_side || "enemy",
      }))
    : [];

  payload.tool_category = rules.gatheringTool ? item.tool_category || null : null;
  for (const key of ["gather_double_chance_bonus", "gather_speed_bonus_pct", "gather_stamina_bonus_pct"]) {
    payload[key] = rules.gatheringTool ? num(item[key]) : 0;
  }

  return payload;
};

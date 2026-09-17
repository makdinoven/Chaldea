/* ── Profession mechanics: shared UI constants (FEAT-165) ── */

export type WhetstoneGroup = 'weapon_armor' | 'cloak_belt' | 'jewelry';

export const WHETSTONE_GROUPS: WhetstoneGroup[] = ['weapon_armor', 'cloak_belt', 'jewelry'];

// UI labels only — rename here, nothing else changes
export const WHETSTONE_GROUP_LABELS: Record<WhetstoneGroup, string> = {
  weapon_armor: 'Точильный камень', // blacksmith: weapon, body armor, helmet
  cloak_belt: 'Камень чар', // enchanter: cloak, belt
  jewelry: 'Гравировальный резец', // jeweler: ring, necklace, bracelet
};

export const WHETSTONE_GROUP_TARGETS: Record<WhetstoneGroup, string> = {
  weapon_armor: 'оружие, броня, шлем',
  cloak_belt: 'плащ, пояс',
  jewelry: 'кольцо, ожерелье, браслет',
};

// Mirrors the backend constant; used only to decide menu visibility.
// The backend is authoritative and returns the group in sharpen-info.
export const SHARPEN_GROUP_BY_ITEM_TYPE: Record<string, WhetstoneGroup> = {
  weapon: 'weapon_armor',
  body: 'weapon_armor',
  head: 'weapon_armor',
  cloak: 'cloak_belt',
  belt: 'cloak_belt',
  ring: 'jewelry',
  necklace: 'jewelry',
  bracelet: 'jewelry',
};

export const SHARPENABLE_ITEM_TYPES = new Set(Object.keys(SHARPEN_GROUP_BY_ITEM_TYPE));

export const RUNE_SOCKET_TYPES = new Set(['weapon', 'body', 'head', 'cloak']);
export const JEWELRY_SOCKET_TYPES = new Set(['ring', 'necklace', 'bracelet']);

export const MAX_ENHANCEMENT_POINTS = 15;

export type ResourceSubcategory =
  | 'ore'
  | 'herb'
  | 'wood'
  | 'ingredient'
  | 'trophy'
  | 'ingot'
  | 'magic_dust'
  | 'essence'
  | 'reagent'
  | 'material'
  | 'whetstone'
  | 'repair_kit';

export const RESOURCE_SUBCATEGORY_LABELS: Record<ResourceSubcategory, string> = {
  ore: 'Руда',
  herb: 'Травы',
  wood: 'Древесина',
  ingredient: 'Ингредиенты',
  trophy: 'Трофеи',
  ingot: 'Слитки',
  magic_dust: 'Магическая пыль',
  essence: 'Эссенции',
  reagent: 'Алхимические реагенты',
  material: 'Материалы',
  whetstone: 'Камни заточки',
  repair_kit: 'Ремкомплекты',
};

export const RESOURCE_SUBCATEGORY_GROUPS: { label: string; items: readonly ResourceSubcategory[] }[] = [
  { label: 'Сырьё', items: ['ore', 'herb', 'wood', 'ingredient', 'trophy'] },
  { label: 'Продукты переработки', items: ['ingot', 'magic_dust', 'essence', 'reagent', 'material'] },
  { label: 'Расходники профессий', items: ['whetstone', 'repair_kit'] },
];

export const RAW_RESOURCE_SUBCATEGORIES: readonly ResourceSubcategory[] = RESOURCE_SUBCATEGORY_GROUPS[0].items;

export const RESOURCE_SUBCATEGORY_NONE_LABEL = 'Прочее';

/**
 * Default ratio pre-filled when the admin enables refining for a profession
 * (examples from the design; the admin can change them per item).
 */
export const REFINING_DEFAULT_RATIOS: Record<string, { source: number; result: number }> = {
  blacksmith: { source: 2, result: 1 },
  alchemist: { source: 2, result: 1 },
  cook: { source: 1, result: 2 },
  jeweler: { source: 1, result: 1 },
  scholar: { source: 1, result: 1 },
};

export const CONVERSION_QTY_MIN = 1;
export const CONVERSION_QTY_MAX = 100;

export const resourceSubcategoryLabel = (value: string | null | undefined): string =>
  value && value in RESOURCE_SUBCATEGORY_LABELS
    ? RESOURCE_SUBCATEGORY_LABELS[value as ResourceSubcategory]
    : RESOURCE_SUBCATEGORY_NONE_LABEL;

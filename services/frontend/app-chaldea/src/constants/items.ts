/**
 * Item catalogue dictionaries shared by the admin item pages and player UI.
 * Mirrors the backend `items` ENUMs (inventory-service models.py / schemas.py).
 */

export const ITEM_TYPES = [
  'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet',
  'weapon', 'consumable', 'resource',
  'scroll', 'misc', 'blueprint', 'recipe', 'gem', 'rune', 'gathering_tool',
] as const;

export type ItemType = (typeof ITEM_TYPES)[number];

export const ITEM_TYPE_LABELS: Record<string, string> = {
  head: 'Шлем',
  body: 'Броня',
  cloak: 'Плащ',
  belt: 'Пояс',
  ring: 'Кольцо',
  necklace: 'Ожерелье',
  bracelet: 'Браслет',
  weapon: 'Оружие',
  consumable: 'Расходуемое',
  resource: 'Ресурс',
  scroll: 'Свиток',
  misc: 'Разное',
  blueprint: 'Чертёж',
  recipe: 'Рецепт',
  gem: 'Камень',
  rune: 'Руна',
  gathering_tool: 'Инструмент сбора',
};

/* ── Categories (admin item catalogue) ── */

export type ItemCategoryKey = 'equipment' | 'jewelry' | 'consumables' | 'craft' | 'tools' | 'misc';

export interface ItemCategory {
  key: ItemCategoryKey;
  label: string;
  types: readonly ItemType[];
}

export const ITEM_CATEGORIES: readonly ItemCategory[] = [
  { key: 'equipment', label: 'Экипировка', types: ['head', 'body', 'cloak', 'belt', 'weapon'] },
  { key: 'jewelry', label: 'Украшения', types: ['ring', 'necklace', 'bracelet'] },
  { key: 'consumables', label: 'Расходуемое', types: ['consumable', 'scroll'] },
  { key: 'craft', label: 'Крафт', types: ['resource', 'blueprint', 'recipe', 'gem', 'rune'] },
  { key: 'tools', label: 'Инструменты сбора', types: ['gathering_tool'] },
  { key: 'misc', label: 'Разное', types: ['misc'] },
];

export const categoryOfType = (itemType: string): ItemCategory | undefined =>
  ITEM_CATEGORIES.find((c) => (c.types as readonly string[]).includes(itemType));

/* ── Rarity ── */

export const ITEM_RARITIES = [
  'common', 'rare', 'epic', 'mythical', 'legendary', 'divine', 'demonic',
] as const;

export const RARITY_LABELS: Record<string, string> = {
  common: 'Обычный',
  rare: 'Редкий',
  epic: 'Эпический',
  mythical: 'Мифический',
  legendary: 'Легендарный',
  divine: 'Божественный',
  demonic: 'Демонический',
};

export const RARITY_ORDER: Record<string, number> = Object.fromEntries(
  ITEM_RARITIES.map((r, i) => [r, i]),
);

export const RARITY_TEXT_COLORS: Record<string, string> = {
  common: 'text-rarity-common',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  mythical: 'text-rarity-mythical',
  legendary: 'text-rarity-legendary',
  divine: 'text-[#FFD700]',
  demonic: 'text-[#B22222]',
};

/* ── Armor class / weapon subclass ── */

/** Armor class only applies to these types (cloak and belt have none) */
export const ARMOR_SUBCLASS_TYPES: readonly string[] = ['head', 'body'];
export const WEAPON_SUBCLASS_TYPES: readonly string[] = ['weapon'];

export const ARMOR_SUBCLASS_LABELS: Record<string, string> = {
  cloth: 'Ткань',
  light_armor: 'Лёгкая броня',
  medium_armor: 'Средняя броня',
  heavy_armor: 'Тяжёлая броня',
};

export type WeaponCategoryKey =
  | 'one_handed' | 'one_and_half' | 'two_handed' | 'polearm'
  | 'ranged' | 'shield' | 'other' | 'magic';

/**
 * Weapon kinds grouped by category. Each kind belongs to exactly one category
 * (mirrors WEAPON_KIND_CATEGORY in inventory-service schemas.py).
 */
export const WEAPON_SUBCLASS_GROUPS: readonly { key: WeaponCategoryKey; label: string; options: Record<string, string> }[] = [
  {
    key: 'one_handed',
    label: 'Одноручное оружие',
    options: {
      sword: 'Меч', hatchet: 'Топорик', mace: 'Булава', sabre: 'Сабля',
      dagger: 'Кинжал', espada: 'Шпага', tanto: 'Танто', war_pick: 'Клевец',
    },
  },
  {
    key: 'one_and_half',
    label: 'Полуторное оружие',
    options: {
      bastard_sword: 'Бастард', axe: 'Топор', katana: 'Катана',
      broadsword: 'Палаш', rapier: 'Рапира', war_hammer: 'Боевой молот',
    },
  },
  {
    key: 'two_handed',
    label: 'Двуручное оружие',
    options: {
      zweihander: 'Цвайхандер', maul: 'Молот', battle_axe: 'Секира', scythe: 'Коса', nodachi: 'Нодати',
    },
  },
  {
    key: 'polearm',
    label: 'Древковое оружие',
    options: {
      halberd: 'Алебарда', glaive: 'Глефа', pike: 'Пика', spear: 'Копьё', naginata: 'Нагината',
    },
  },
  {
    key: 'ranged',
    label: 'Стрелковое оружие',
    options: { bow: 'Лук', pistol: 'Пистолет', musket: 'Ружьё' },
  },
  {
    key: 'shield',
    label: 'Щиты',
    options: { buckler: 'Баклер', targe: 'Тарч', tower_shield: 'Ростовой щит' },
  },
  {
    key: 'other',
    label: 'Другое',
    options: { lute: 'Лютня', knuckledusters: 'Кастет' },
  },
  {
    key: 'magic',
    label: 'Магическое',
    options: {
      staff: 'Посох', grimoire: 'Гримуар', amulet: 'Амулет', rod: 'Жезл',
      magic_weapon: 'Магическое оружие', catalyst: 'Катализатор', wand: 'Волшебная палочка',
    },
  },
];

export const WEAPON_SUBCLASS_LABELS: Record<string, string> = Object.assign(
  {},
  ...WEAPON_SUBCLASS_GROUPS.map((g) => g.options),
);

export const WEAPON_KIND_CATEGORY: Record<string, WeaponCategoryKey> = Object.fromEntries(
  WEAPON_SUBCLASS_GROUPS.flatMap((g) => Object.keys(g.options).map((kind) => [kind, g.key])),
);

/** Weapons of these categories take both hands: main hand only, off-hand locked */
export const TWO_HANDED_WEAPON_CATEGORIES: readonly WeaponCategoryKey[] = ['two_handed', 'polearm'];

export const DAMAGE_TYPE_LABELS: Record<string, string> = {
  physical: 'Физический',
  catting: 'Режущий',
  crushing: 'Дробящий',
  piercing: 'Колющий',
  magic: 'Магический',
  fire: 'Огненный',
  ice: 'Ледяной',
  watering: 'Водный',
  electricity: 'Электрический',
  wind: 'Воздушный',
  sainting: 'Святой',
  damning: 'Проклятый',
};

/* ── Gathering tools ── */

export const TOOL_CATEGORIES = ['pickaxe', 'sickle', 'axe'] as const;

export const TOOL_CATEGORY_LABELS: Record<string, string> = {
  pickaxe: 'Кирка',
  sickle: 'Серп',
  axe: 'Топор',
};

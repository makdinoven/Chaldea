export const DND_TYPES = {
  INVENTORY_ITEM: 'inventory-item',
  EQUIPMENT_ITEM: 'equipment-item',
} as const;

// Item types that go to fast slots (not equipment slots)
export const FAST_SLOT_ITEM_TYPES = new Set(['consumable', 'scroll', 'misc', 'resource']);

// Item types that go to equipment slots (item_type -> slot_type).
// FEAT-149: the 'shield' slot no longer exists — shield items equip into
// the 'additional_weapons' slot (mirrors backend find_equipment_slot_for_item).
export const EQUIPMENT_ITEM_TYPES: Record<string, string> = {
  head: 'head',
  body: 'body',
  cloak: 'cloak',
  belt: 'belt',
  shield: 'additional_weapons',
  ring: 'ring',
  necklace: 'necklace',
  bracelet: 'bracelet',
  main_weapon: 'main_weapon',
  additional_weapons: 'additional_weapons',
};

/**
 * Full set of item types known to the client. Mirrors the backend
 * `items.item_type` ENUM. Includes `gathering_tool` from FEAT-128.
 */
export const ITEM_TYPES = [
  'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet',
  'main_weapon', 'additional_weapons', 'shield', 'consumable', 'resource',
  'scroll', 'misc', 'blueprint', 'recipe', 'gem', 'rune', 'gathering_tool',
] as const;

/** Russian labels for `items.item_type`. */
export const ITEM_TYPE_LABELS: Record<string, string> = {
  head: 'Голова',
  body: 'Тело',
  cloak: 'Плащ',
  belt: 'Пояс',
  ring: 'Кольцо',
  necklace: 'Ожерелье',
  bracelet: 'Браслет',
  main_weapon: 'Основное оружие',
  additional_weapons: 'Доп. оружие',
  shield: 'Щит',
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

/** Tool category enum used by gathering_tool items (FEAT-128). */
export const TOOL_CATEGORIES = ['pickaxe', 'sickle', 'axe'] as const;

/** Russian labels for tool categories. */
export const TOOL_CATEGORY_LABELS: Record<string, string> = {
  pickaxe: 'Кирка',
  sickle: 'Серп',
  axe: 'Топор',
};

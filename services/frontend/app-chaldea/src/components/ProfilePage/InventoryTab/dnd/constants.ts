export const DND_TYPES = {
  INVENTORY_ITEM: 'inventory-item',
  EQUIPMENT_ITEM: 'equipment-item',
} as const;

// Item types that go to fast slots (not equipment slots)
export const FAST_SLOT_ITEM_TYPES = new Set(['consumable', 'scroll', 'misc', 'resource']);

// Item types that go to equipment slots (item_type -> slot_type).
// A weapon may go into either hand; 'main_weapon' is the default target and the
// hand rules (equipment-rules endpoint) decide what is actually allowed.
export const EQUIPMENT_ITEM_TYPES: Record<string, string> = {
  head: 'head',
  body: 'body',
  cloak: 'cloak',
  belt: 'belt',
  ring: 'ring',
  necklace: 'necklace',
  bracelet: 'bracelet',
  weapon: 'main_weapon',
};

// Item dictionaries live in one place; re-exported for existing imports.
export {
  ITEM_TYPES,
  ITEM_TYPE_LABELS,
  TOOL_CATEGORIES,
  TOOL_CATEGORY_LABELS,
} from '../../../../constants/items';

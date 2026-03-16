export const DND_TYPES = {
  INVENTORY_ITEM: 'inventory-item',
  EQUIPMENT_ITEM: 'equipment-item',
} as const;

// Item types that go to fast slots (not equipment slots)
export const FAST_SLOT_ITEM_TYPES = new Set(['consumable', 'scroll', 'misc', 'resource']);

// Item types that go to equipment slots (1:1 mapping)
export const EQUIPMENT_ITEM_TYPES: Record<string, string> = {
  head: 'head',
  body: 'body',
  cloak: 'cloak',
  belt: 'belt',
  shield: 'shield',
  ring: 'ring',
  necklace: 'necklace',
  bracelet: 'bracelet',
  main_weapon: 'main_weapon',
  additional_weapons: 'additional_weapons',
};

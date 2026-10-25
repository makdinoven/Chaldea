import axios from 'axios';

/*
  FEAT-178: the camp backpack — a cloak that holds a few stacks of consumables
  the character takes into a dungeon. In a run the bag is closed: only what is
  in the backpack can be used (out of battle) or put on the belt.
*/

export interface BackpackEntry {
  id: number;
  item_id: number;
  quantity: number;
  name: string;
  description: string | null;
  image_url: string | null;
  rarity: string | null;
  max_stack_size: number;
  is_food: boolean;
  health_recovery: number;
  mana_recovery: number;
  energy_recovery: number;
  stamina_recovery: number;
}

export interface BeltSlot {
  slot_type: string;
  item_id: number | null;
  name: string | null;
  image_url: string | null;
}

export interface BackpackState {
  backpack: { item_id: number; name: string; image_url: string | null; rarity: string | null } | null;
  capacity: number;
  items: BackpackEntry[];
  belt: BeltSlot[];
  in_dungeon: boolean;
}

/** Tells every backpack view on the page to reload (packing, use, a find handed over…). */
export const BACKPACK_CHANGED = 'chaldea:backpack-changed';
export const announceBackpackChange = () => window.dispatchEvent(new Event(BACKPACK_CHANGED));

export const fetchBackpack = async (characterId: number): Promise<BackpackState> => {
  const { data } = await axios.get<BackpackState>(`/inventory/${characterId}/backpack`);
  return data;
};

export const packIntoBackpack = async (
  characterId: number,
  inventoryItemId: number,
  quantity: number,
): Promise<BackpackState> => {
  const { data } = await axios.post<BackpackState>(`/inventory/${characterId}/backpack/pack`, {
    inventory_item_id: inventoryItemId,
    quantity,
  });
  announceBackpackChange();
  return data;
};

export const unpackFromBackpack = async (
  characterId: number,
  backpackItemId: number,
  quantity: number,
): Promise<BackpackState> => {
  const { data } = await axios.post<BackpackState>(`/inventory/${characterId}/backpack/unpack`, {
    backpack_item_id: backpackItemId,
    quantity,
  });
  announceBackpackChange();
  return data;
};

/** Use one item of a packed stack (food, a book, a potion) — out of battle. */
export const consumeFromBackpack = async (
  characterId: number,
  backpackItemId: number,
): Promise<{ message?: string; detail?: string }> => {
  const { data } = await axios.post(`/inventory/${characterId}/backpack/use`, {
    backpack_item_id: backpackItemId,
  });
  announceBackpackChange();
  return data;
};

/** Put one item of a packed stack on the belt (the first free fast slot). */
export const beltFromBackpack = async (characterId: number, itemId: number, backpackItemId: number) => {
  await axios.post(`/inventory/${characterId}/equip`, { item_id: itemId, backpack_item_id: backpackItemId });
  announceBackpackChange();
};

/** Take an item off the belt — in a run it goes back into the backpack. */
export const takeOffBelt = async (characterId: number, slotType: string) => {
  await axios.post(`/inventory/${characterId}/unequip`, null, { params: { slot_type: slotType } });
  announceBackpackChange();
};

/** Stacks a backpack holds, by rarity (as the server counts). */
export const BACKPACK_CAPACITY_HINT = 'Обычный — 4 слота, редкий — 6, эпический — 8, легендарный и выше — 10';

import { GARDEN_ROOM_PLACE, isGardenRoom } from '../api/houses';

/*
  FEAT-180 stage 6a — seeds: resource items planted in a house garden,
  greenhouse or apiary that grow into another item after some hours.
*/

/** The seed fields an item row carries (inventory-service `items`). */
export interface SeedItemFields {
  item_type?: string;
  seed_result_item_id?: number | null;
  seed_result_quantity?: number | null;
  seed_grow_hours?: number | null;
  seed_room_type?: string | null;
  seed_herbalism_xp?: number | null;
}

/** «Семена: растут 12 ч в огороде, урожай ×3» for a seed item; null for other items. */
export const seedItemSummary = (item: SeedItemFields): string | null => {
  if (item.item_type !== 'resource' || item.seed_result_item_id == null || !isGardenRoom(item.seed_room_type ?? '')) {
    return null;
  }
  const place = GARDEN_ROOM_PLACE[item.seed_room_type as keyof typeof GARDEN_ROOM_PLACE];
  const qty = item.seed_result_quantity ?? 1;
  return `Семена: растут ${item.seed_grow_hours ?? 0} ч ${place}${qty > 1 ? `, урожай ×${qty}` : ''}`;
};

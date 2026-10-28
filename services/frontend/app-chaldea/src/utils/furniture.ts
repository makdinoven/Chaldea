import { FURNITURE_GROUPS, type FurnitureGroup, type HouseRoom } from '../api/houses';

/*
  FEAT-180 stage 3 — furniture: items of type `furniture` placed into house
  rooms. Each piece belongs to one furniture group (stage 6a: a cellar takes
  storage pieces, every profession room takes workshop pieces) and gives the room a bonus
  (hall pieces are pure decoration).
*/

/** Bonus values of one piece of furniture (item fields or a placed piece). */
export interface FurnitureBonus {
  sleep_bonus?: number | null;
  storage_stacks?: number | null;
  xp_bonus_pct?: number | null;
  refine_bonus_pct?: number | null;
}

/** «гостиной», «спальни»… — for «Мебель для спальни». */
export const FURNITURE_GROUP_GENITIVE: Record<FurnitureGroup, string> = {
  hall: 'гостиной',
  bedroom: 'спальни',
  storage: 'кладовой и погреба',
  workshop: 'мастерской профессии',
};

export const isFurnitureGroup = (value: unknown): value is FurnitureGroup =>
  typeof value === 'string' && (FURNITURE_GROUPS as string[]).includes(value);

const fmt = (n: number) => n.toLocaleString('ru-RU', { maximumFractionDigits: 2 });

/** «ячейка / ячейки / ячеек» for a count. */
export const cellsWord = (n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'ячейка';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'ячейки';
  return 'ячеек';
};

/**
 * Short bonus text by furniture group (null = decoration): «Сон +0,5», «+10 ячеек»,
 * «Опыт +40%, удвоение +5%», «Украшение».
 */
export const furnitureBonusText = (group: FurnitureGroup | null, bonus: FurnitureBonus): string => {
  if (group === 'bedroom') return `Сон +${fmt(bonus.sleep_bonus ?? 0)}`;
  if (group === 'storage') {
    const n = Math.round(bonus.storage_stacks ?? 0);
    return `+${n} ${cellsWord(n)}`;
  }
  if (group === 'workshop') {
    const parts: string[] = [];
    if ((bonus.xp_bonus_pct ?? 0) > 0) parts.push(`Опыт +${fmt(bonus.xp_bonus_pct ?? 0)}%`);
    if ((bonus.refine_bonus_pct ?? 0) > 0) {
      parts.push(`${parts.length ? 'удвоение' : 'Удвоение'} +${fmt(bonus.refine_bonus_pct ?? 0)}%`);
    }
    return parts.join(', ') || 'Без бонуса';
  }
  return 'Украшение';
};

/** The furniture fields an item row carries (inventory-service `items`). */
export interface FurnitureItemFields {
  item_type?: string;
  furniture_room_type?: string | null;
  furniture_sleep_bonus?: number | null;
  furniture_storage_stacks?: number | null;
  furniture_xp_bonus_pct?: number | null;
  furniture_refine_bonus_pct?: number | null;
}

/** Bonus values of a furniture item, in the placed-piece shape. */
export const itemFurnitureBonus = (item: FurnitureItemFields): FurnitureBonus => ({
  sleep_bonus: item.furniture_sleep_bonus,
  storage_stacks: item.furniture_storage_stacks,
  xp_bonus_pct: item.furniture_xp_bonus_pct,
  refine_bonus_pct: item.furniture_refine_bonus_pct,
});

/** «Мебель для спальни · Сон +0,5» for a furniture item; null for other items. */
export const furnitureItemSummary = (item: FurnitureItemFields): string | null => {
  if (item.item_type !== 'furniture') return null;
  const room = item.furniture_room_type;
  if (!isFurnitureGroup(room)) return 'Мебель';
  return `Мебель для ${FURNITURE_GROUP_GENITIVE[room]} · ${furnitureBonusText(room, itemFurnitureBonus(item))}`;
};

/** Whether a furniture item fits a room (the room's group equals the item's). */
export const furnitureFitsRoom = (item: FurnitureItemFields, room: Pick<HouseRoom, 'furniture_group'>): boolean =>
  room.furniture_group != null && item.furniture_room_type === room.furniture_group;

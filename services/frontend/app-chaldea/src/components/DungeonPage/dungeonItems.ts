import { useEffect, useState } from 'react';
import axios from 'axios';

/** The public card of an item: enough to draw its cell. */
export interface ItemCard {
  id: number;
  name: string;
  description?: string | null;
  image_url?: string | null;
  rarity?: string | null;
  type?: string | null;
}

const cards = new Map<number, ItemCard>();
const BULK_MAX = 100;

/** Cards for these item ids (cached for the page's life); missing ones come in as they load. */
export const useItemCards = (ids: number[]): Map<number, ItemCard> => {
  const [, setTick] = useState(0);
  const key = [...new Set(ids)].sort((a, b) => a - b).join(',');
  useEffect(() => {
    const missing = key ? key.split(',').map(Number).filter((id) => !cards.has(id)) : [];
    if (!missing.length) return;
    let alive = true;
    (async () => {
      for (let i = 0; i < missing.length; i += BULK_MAX) {
        const { data } = await axios.get<ItemCard[]>('/inventory/items/bulk', {
          params: { ids: missing.slice(i, i + BULK_MAX).join(',') },
        });
        data.forEach((c) => cards.set(c.id, c));
      }
      if (alive) setTick((t) => t + 1);
    })().catch(() => undefined); // a missing picture falls back to the type's icon
    return () => {
      alive = false;
    };
  }, [key]);
  return cards;
};

/** What a consumable restores, in a few words: "+50 здоровья, +20 маны". */
export const recoveryLine = (item: {
  health_recovery?: number;
  mana_recovery?: number;
  energy_recovery?: number;
  stamina_recovery?: number;
}): string =>
  [
    [item.health_recovery, 'здоровья'],
    [item.mana_recovery, 'маны'],
    [item.energy_recovery, 'энергии'],
    [item.stamina_recovery, 'выносливости'],
  ]
    .filter(([v]) => typeof v === 'number' && v > 0)
    .map(([v, what]) => `+${v} ${what}`)
    .join(', ');

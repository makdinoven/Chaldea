import type { MouseEvent, ReactNode } from 'react';
import { shownRarity } from '../../../constants/items';
import { ITEM_TYPE_ICONS } from '../../ProfilePage/constants';

/*
  One round item cell, as in the profile inventory: the picture (or the type's
  icon), the rarity ring, the count in the corner. An empty slot is a dim ring.
*/

interface ItemSlotProps {
  name?: string | null;
  image?: string | null;
  rarity?: string | null;
  itemType?: string | null;
  quantity?: number;
  /** An empty place (a free backpack or belt slot). */
  empty?: boolean;
  /** A small mark in the top corner (e.g. "1" for the belt slot number). */
  badge?: ReactNode;
  selected?: boolean;
  title?: string;
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
}

const ItemSlot = ({
  name, image, rarity, itemType = 'consumable', quantity = 1, empty = false, badge, selected = false, title, onClick,
}: ItemSlotProps) => {
  if (empty) {
    return (
      <div className="relative">
        <div className="item-cell item-cell-empty w-full h-auto aspect-square" title={title} />
        {badge && <span className="absolute -top-1 -left-1 text-[9px] text-white/40">{badge}</span>}
      </div>
    );
  }
  const visible = shownRarity(itemType, rarity);
  const rarityClass = visible && visible !== 'common' ? `rarity-${visible}` : '';
  const icon = ITEM_TYPE_ICONS[itemType ?? 'consumable'] ?? ITEM_TYPE_ICONS.consumable;
  return (
    <div className="relative">
      <button
        type="button"
        onClick={onClick}
        title={title ?? name ?? undefined}
        aria-label={name ?? 'Предмет'}
        className={`item-cell w-full h-auto aspect-square ${rarityClass} cursor-pointer transition-transform duration-150 hover:scale-105 ${
          selected ? 'ring-2 ring-gold/70' : ''
        }`}
      >
        {image ? (
          <img src={image} alt={name ?? ''} className="w-full h-full object-cover" draggable={false} />
        ) : (
          <img src={icon} alt="" className="w-1/2 h-1/2 opacity-70" draggable={false} />
        )}
      </button>
      {quantity > 1 && (
        <span className="absolute -bottom-1 -right-1 z-10 min-w-[20px] h-[20px] flex items-center justify-center text-[10px] font-medium text-white bg-site-bg rounded-full border border-white/30 px-1 pointer-events-none">
          {quantity}
        </span>
      )}
      {badge && <span className="absolute -top-1 -left-1 z-10 text-[9px] text-white/50 pointer-events-none">{badge}</span>}
    </div>
  );
};

export default ItemSlot;

import React from 'react';
import { motion } from 'motion/react';
import { useAppDispatch } from '../../../redux/store';
import { openContextMenu, InventoryItem } from '../../../redux/slices/profileSlice';
import { ITEM_TYPE_ICONS } from '../constants';

interface ItemCellProps {
  inventoryItem?: InventoryItem;
  placeholderType?: string;
}

const ItemCell = ({ inventoryItem, placeholderType }: ItemCellProps) => {
  const dispatch = useAppDispatch();

  if (!inventoryItem) {
    // Empty cell
    const iconSrc = placeholderType ? ITEM_TYPE_ICONS[placeholderType] : undefined;
    return (
      <div className="item-cell item-cell-empty">
        {iconSrc && (
          <img
            src={iconSrc}
            alt=""
            className="w-8 h-8 opacity-40"
            draggable={false}
          />
        )}
      </div>
    );
  }

  const { item, quantity } = inventoryItem;
  const rarityClass = item.item_rarity && item.item_rarity !== 'common'
    ? `rarity-${item.item_rarity}`
    : '';

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    dispatch(
      openContextMenu({
        x: e.clientX,
        y: e.clientY,
        item: inventoryItem,
      }),
    );
  };

  const iconSrc = ITEM_TYPE_ICONS[item.item_type];

  return (
    <motion.div
      className={`item-cell ${rarityClass} cursor-pointer hover:scale-105`}
      onClick={handleClick}
      whileHover={{ scale: 1.05 }}
      transition={{ duration: 0.15 }}
    >
      {item.image ? (
        <img
          src={item.image}
          alt={item.name}
          className="w-full h-full object-cover"
          draggable={false}
        />
      ) : iconSrc ? (
        <img
          src={iconSrc}
          alt={item.name}
          className="w-10 h-10 opacity-70"
          draggable={false}
        />
      ) : null}

      {quantity > 1 && (
        <span className="absolute bottom-0.5 right-1 text-xs font-medium text-white bg-black/60 rounded-full px-1.5 py-0.5 leading-none">
          {quantity}
        </span>
      )}
    </motion.div>
  );
};

export default ItemCell;

import React, { useCallback } from 'react';
import { motion } from 'motion/react';
import { useDraggable } from '@dnd-kit/core';
import toast from 'react-hot-toast';
import { useAppDispatch } from '../../../redux/store';
import { openContextMenu, equipItem, InventoryItem } from '../../../redux/slices/profileSlice';
import { ITEM_TYPE_ICONS } from '../constants';
import { EQUIPMENT_ITEM_TYPES, FAST_SLOT_ITEM_TYPES } from './dnd/constants';
import { useInventoryCharacterId } from './dnd/InventoryDndContext';
import type { DragItemData } from './dnd/InventoryDndContext';
import useClickHandler from './dnd/useClickHandler';

interface ItemCellProps {
  inventoryItem?: InventoryItem;
  placeholderType?: string;
}

const ItemCell = ({ inventoryItem, placeholderType }: ItemCellProps) => {
  const dispatch = useAppDispatch();
  const characterId = useInventoryCharacterId();

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

  /* eslint-disable react-hooks/rules-of-hooks -- early return above is for empty cells only */
  const { item, quantity, is_identified, current_durability } = inventoryItem;
  const rarityClass = item.item_rarity && item.item_rarity !== 'common'
    ? `rarity-${item.item_rarity}`
    : '';
  const isUnidentified = is_identified === false;
  const maxDurability = item.max_durability ?? 0;
  const hasDurability = maxDurability > 0;
  const effectiveDurability = current_durability ?? maxDurability;
  const durabilityPct = hasDurability ? (effectiveDurability / maxDurability) * 100 : 100;
  const isBroken = hasDurability && effectiveDurability === 0;

  const isEquippable =
    item.item_type in EQUIPMENT_ITEM_TYPES || FAST_SLOT_ITEM_TYPES.has(item.item_type);

  // --- Draggable setup ---
  const dragData: DragItemData = {
    source: 'inventory',
    inventoryItem,
    itemType: item.item_type,
  };

  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `inventory-${inventoryItem.id}`,
    data: dragData,
  });

  // --- Click handlers ---
  const handleSingleClick = useCallback(
    (e: React.MouseEvent) => {
      dispatch(
        openContextMenu({
          x: e.clientX,
          y: e.clientY,
          item: inventoryItem,
        }),
      );
    },
    [dispatch, inventoryItem],
  );

  const handleDoubleClick = useCallback(
    async () => {
      if (!characterId) return;
      if (isUnidentified) {
        toast.error('Предмет не опознан');
        return;
      }
      try {
        const result = await dispatch(
          equipItem({ characterId, itemId: item.id, inventoryItemId: inventoryItem.id }),
        );
        if (result.meta.requestStatus === 'fulfilled') {
          toast.success('Предмет экипирован');
        } else {
          const payload = result.payload as string | undefined;
          toast.error(payload ?? 'Не удалось экипировать предмет');
        }
      } catch {
        toast.error('Произошла ошибка при экипировке');
      }
    },
    [dispatch, characterId, item.id, isUnidentified],
  );

  const clickHandlers = useClickHandler({
    item: inventoryItem,
    onSingleClick: handleSingleClick,
    onDoubleClick: handleDoubleClick,
    isEquippable,
  });

  const iconSrc = ITEM_TYPE_ICONS[item.item_type];

  return (
    <div className="relative">
      <motion.div
        ref={setNodeRef}
        className={`item-cell ${rarityClass} cursor-pointer hover:scale-105 ${isDragging ? 'opacity-50' : ''} ${isUnidentified ? 'opacity-60' : ''}`}
        {...attributes}
        {...listeners}
        {...clickHandlers}
        whileHover={isDragging ? undefined : { scale: 1.05 }}
        transition={{ duration: 0.15 }}
      >
        {item.image ? (
          <img
            src={item.image}
            alt={item.name}
            className={`w-full h-full object-cover ${isUnidentified ? 'grayscale' : ''}`}
          />
        ) : iconSrc ? (
          <img
            src={iconSrc}
            alt={item.name}
            className={`w-10 h-10 opacity-70 ${isUnidentified ? 'grayscale' : ''}`}
          />
        ) : null}
        {isUnidentified && (
          <span
            className="
              absolute inset-0 flex items-center justify-center
              text-lg font-medium text-gold drop-shadow-lg
              pointer-events-none
            "
          >
            ???
          </span>
        )}
      </motion.div>

      {/* Low durability warning pulse (<25%) */}
      {hasDurability && !isBroken && durabilityPct < 25 && (
        <div className="absolute inset-0 rounded-full pointer-events-none z-10 animate-pulse border-2 border-site-red/60" />
      )}

      {/* Broken overlay with icon */}
      {isBroken && (
        <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 pointer-events-none z-10">
          <svg className="w-8 h-8 text-site-red/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10 2v4.5L7.5 8l-4 2.5L2 12l1.5 1.5 4 2.5L10 17.5V22" />
            <path d="M14 2v4.5L16.5 8l4 2.5L22 12l-1.5 1.5-4 2.5L14 17.5V22" />
            <path d="M12 8v8" />
          </svg>
        </div>
      )}

      {quantity > 1 && (
        <span
          className="
            absolute -bottom-1 -right-1 z-10 min-w-[20px] h-[20px]
            flex items-center justify-center
            text-[10px] font-medium text-white
            bg-site-bg rounded-full
            border border-white/30 px-1
          "
        >
          {quantity}
        </span>
      )}

      {(inventoryItem.enhancement_points_spent ?? 0) > 0 && (
        <span
          className="
            absolute -top-1 -right-1 z-10 min-w-[20px] h-[20px]
            flex items-center justify-center
            text-[10px] font-medium text-gold
            bg-site-bg rounded-full
            border border-gold/40 px-1
          "
        >
          +{inventoryItem.enhancement_points_spent}
        </span>
      )}
    </div>
  );
  /* eslint-enable react-hooks/rules-of-hooks */
};

export default ItemCell;

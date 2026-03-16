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
  const { item, quantity } = inventoryItem;
  const rarityClass = item.item_rarity && item.item_rarity !== 'common'
    ? `rarity-${item.item_rarity}`
    : '';

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
      try {
        const result = await dispatch(
          equipItem({ characterId, itemId: item.id }),
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
    [dispatch, characterId, item.id],
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
        className={`item-cell ${rarityClass} cursor-pointer hover:scale-105 ${isDragging ? 'opacity-50' : ''}`}
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
            className="w-full h-full object-cover"
          />
        ) : iconSrc ? (
          <img
            src={iconSrc}
            alt={item.name}
            className="w-10 h-10 opacity-70"
          />
        ) : null}
      </motion.div>

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
    </div>
  );
  /* eslint-enable react-hooks/rules-of-hooks */
};

export default ItemCell;

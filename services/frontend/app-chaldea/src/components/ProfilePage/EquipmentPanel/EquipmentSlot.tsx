import { useDraggable, useDroppable } from '@dnd-kit/core';
import { useAppDispatch } from '../../../redux/store';
import { openContextMenu } from '../../../redux/slices/profileSlice';
import type { EquipmentSlotData, InventoryItem } from '../../../redux/slices/profileSlice';
import { ITEM_TYPE_ICONS, EQUIPMENT_SLOT_LABELS } from '../constants';
import { useCompatibleSlots, useActiveDrag } from '../InventoryTab/dnd/InventoryDndContext';
import type { DragItemData } from '../InventoryTab/dnd/InventoryDndContext';

interface EquipmentSlotProps {
  slot: EquipmentSlotData;
  /** Size variant: 'normal' (80px) or 'small' (56px) */
  size?: 'normal' | 'small';
}

export default function EquipmentSlot({ slot, size = 'normal' }: EquipmentSlotProps) {
  const dispatch = useAppDispatch();
  const compatibleSlots = useCompatibleSlots();
  const activeDrag = useActiveDrag();

  const isEmpty = !slot.item;
  const placeholderIcon = ITEM_TYPE_ICONS[slot.slot_type] ?? ITEM_TYPE_ICONS['misc'];
  const label = EQUIPMENT_SLOT_LABELS[slot.slot_type] ?? slot.slot_type;
  const rarityClass = slot.item ? `rarity-${slot.item.item_rarity}` : '';

  const sizeClasses = size === 'small'
    ? 'w-[56px] h-[56px] !w-[56px] !h-[56px]'
    : '';

  // --- Droppable: accept inventory items matching this slot type ---
  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `drop-equipment-${slot.slot_type}`,
    data: { slotType: slot.slot_type },
  });

  // --- Draggable: only when slot has an item ---
  const constructedInventoryItem: InventoryItem | undefined = slot.item
    ? {
        id: 0,
        character_id: slot.character_id,
        item_id: slot.item_id!,
        quantity: 1,
        item: slot.item,
      }
    : undefined;

  const dragData: DragItemData | undefined = !isEmpty && constructedInventoryItem
    ? {
        source: 'equipment' as const,
        inventoryItem: constructedInventoryItem,
        slot,
        itemType: slot.item!.item_type,
      }
    : undefined;

  const {
    attributes: dragAttributes,
    listeners: dragListeners,
    setNodeRef: setDragRef,
    isDragging,
  } = useDraggable({
    id: `equipment-${slot.slot_type}`,
    data: dragData,
    disabled: isEmpty,
  });

  // --- Check if this slot is compatible with the currently dragged item ---
  const isCompatible = compatibleSlots.includes(slot.slot_type);
  const isDragActive = activeDrag !== null;
  const isIncompatible = isDragActive && !isCompatible;

  // --- Click handler: open context menu for equipped items ---
  const handleClick = (e: React.MouseEvent) => {
    if (!slot.item || !constructedInventoryItem) return;
    dispatch(openContextMenu({
      x: e.clientX,
      y: e.clientY,
      item: constructedInventoryItem,
      slotType: slot.slot_type,
    }));
  };

  // --- Merge refs: the outer div is droppable, the button inside is draggable ---
  return (
    <div className="flex flex-col items-center gap-1" ref={setDropRef}>
      <button
        ref={setDragRef}
        onClick={handleClick}
        {...(isEmpty ? {} : dragAttributes)}
        {...(isEmpty ? {} : dragListeners)}
        className={`
          item-cell ${isEmpty ? 'item-cell-empty' : rarityClass}
          ${sizeClasses}
          ${isCompatible ? 'slot-pulse-compatible' : ''}
          ${isIncompatible ? 'opacity-30 brightness-50' : ''}
          ${isOver ? 'ring-2 ring-gold/60' : ''}
          cursor-pointer hover:scale-105 transition-transform duration-200 ease-site
        `}
        style={{
          ...(size === 'small' ? { width: 56, height: 56 } : undefined),
          ...(isDragging ? { opacity: 0.4 } : undefined),
        }}
        title={isEmpty ? label : slot.item!.name}
      >
        {isEmpty ? (
          <img
            src={placeholderIcon}
            alt={label}
            className="w-8 h-8 opacity-40"
          />
        ) : (
          slot.item!.image ? (
            <img
              src={slot.item!.image}
              alt={slot.item!.name}
              className="w-full h-full object-cover rounded-full"
              draggable={false}
            />
          ) : (
            <img
              src={placeholderIcon}
              alt={slot.item!.name}
              className="w-8 h-8 opacity-70"
              draggable={false}
            />
          )
        )}
      </button>
      {size === 'normal' && (
        <span className="text-xs text-white/60 text-center max-w-[90px] leading-tight">
          {label}
        </span>
      )}
    </div>
  );
}

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

  // Durability
  const maxDurability = slot.item?.max_durability ?? 0;
  const hasDurability = maxDurability > 0;
  const effectiveDurability = slot.current_durability ?? maxDurability;
  const durabilityPct = hasDurability ? (effectiveDurability / maxDurability) * 100 : 100;
  const isBroken = hasDurability && effectiveDurability === 0;

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
        id: slot.id ?? 0,
        character_id: slot.character_id,
        item_id: slot.item_id!,
        quantity: 1,
        current_durability: slot.current_durability ?? null,
        enhancement_points_spent: slot.enhancement_points_spent ?? 0,
        is_identified: true,
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
    <div className="relative flex flex-col items-center gap-1" ref={setDropRef}>
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
      {/* Low durability warning pulse (<25%) */}
      {!isEmpty && hasDurability && !isBroken && durabilityPct < 25 && (
        <div className="absolute inset-0 rounded-full pointer-events-none z-10 animate-pulse border-2 border-site-red/60" />
      )}

      {/* Broken overlay with icon */}
      {!isEmpty && isBroken && (
        <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 pointer-events-none z-10">
          <svg className="w-6 h-6 text-site-red/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10 2v4.5L7.5 8l-4 2.5L2 12l1.5 1.5 4 2.5L10 17.5V22" />
            <path d="M14 2v4.5L16.5 8l4 2.5L22 12l-1.5 1.5-4 2.5L14 17.5V22" />
            <path d="M12 8v8" />
          </svg>
        </div>
      )}

      {(slot.enhancement_points_spent ?? 0) > 0 && !isEmpty && (
        <span
          className="
            absolute -top-1 -right-1 z-10 min-w-[20px] h-[20px]
            flex items-center justify-center
            text-[10px] font-medium text-gold
            bg-site-bg rounded-full
            border border-gold/40 px-1
          "
        >
          +{slot.enhancement_points_spent}
        </span>
      )}
      {size === 'normal' && (
        <span className="text-xs text-white/60 text-center max-w-[90px] leading-tight">
          {label}
        </span>
      )}
    </div>
  );
}

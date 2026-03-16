import { useDroppable, useDraggable } from '@dnd-kit/core';
import { useAppSelector, useAppDispatch } from '../../../redux/store';
import { selectEquipment, selectFastSlots, openContextMenu } from '../../../redux/slices/profileSlice';
import type { EquipmentSlotData, InventoryItem } from '../../../redux/slices/profileSlice';
import { useCompatibleSlots, useActiveDrag } from '../InventoryTab/dnd/InventoryDndContext';
import type { DragItemData } from '../InventoryTab/dnd/InventoryDndContext';
import { FAST_SLOT_ITEM_TYPES } from '../InventoryTab/dnd/constants';
import { ITEM_TYPE_ICONS } from '../constants';
import swapBagIcon from '../../../assets/icons/equipment/swap-bag.svg';

const FAST_SLOT_COUNT = 10;

interface MergedFastSlot extends EquipmentSlotData {
  quantity: number;
}

// --- Per-slot wrapper component (hooks can't be called in loops) ---

interface FastSlotDropTargetProps {
  slot: MergedFastSlot;
  slotIndex: number;
}

const FastSlotDropTarget = ({ slot, slotIndex }: FastSlotDropTargetProps) => {
  const dispatch = useAppDispatch();
  const compatibleSlots = useCompatibleSlots();
  const activeDrag = useActiveDrag();

  const isDisabled = !slot.is_enabled;
  const isFilled = !!slot.item;
  const isCompatible = !isDisabled && compatibleSlots.includes(slot.slot_type);
  const isDragActive = activeDrag !== null;
  const isIncompatible = isDragActive && !isDisabled && !isCompatible;

  // Droppable setup for enabled slots
  const { setNodeRef: setDropRef } = useDroppable({
    id: `drop-fast_slot-${slotIndex}`,
    disabled: isDisabled,
    data: {
      slotType: slot.slot_type,
      accepts: FAST_SLOT_ITEM_TYPES,
    },
  });

  // Draggable setup for filled slots
  const dragData: DragItemData = {
    source: 'fast_slot',
    slot,
    itemType: slot.item?.item_type ?? '',
  };

  const {
    attributes: dragAttributes,
    listeners: dragListeners,
    setNodeRef: setDragRef,
    isDragging,
  } = useDraggable({
    id: `fast-equipment-${slot.slot_type}`,
    disabled: isDisabled || !isFilled,
    data: dragData,
  });

  // Merge refs: droppable on the outer div, draggable on the button/content
  const placeholderIcon = ITEM_TYPE_ICONS[slot.slot_type] ?? ITEM_TYPE_ICONS['misc'];

  const handleClick = (e: React.MouseEvent) => {
    if (!slot.item) return;
    const inventoryItem: InventoryItem = {
      id: 0,
      character_id: slot.character_id,
      item_id: slot.item_id!,
      quantity: 1,
      item: slot.item,
    };
    dispatch(openContextMenu({
      x: e.clientX,
      y: e.clientY,
      item: inventoryItem,
      slotType: slot.slot_type,
    }));
  };

  // Disabled slot - dimmed, no DnD
  if (isDisabled) {
    return (
      <div
        className="item-cell item-cell-empty opacity-30"
        title="Слот недоступен"
      />
    );
  }

  const rarityClass = slot.item ? `rarity-${slot.item.item_rarity}` : '';
  const pulseClass = isCompatible ? 'slot-pulse-compatible' : '';

  // Enabled empty slot
  if (!isFilled) {
    return (
      <div
        ref={setDropRef}
        className={`item-cell item-cell-empty ${pulseClass} ${isIncompatible ? 'opacity-30 brightness-50' : ''}`}
      />
    );
  }

  // Enabled filled slot - both droppable and draggable
  return (
    <div ref={setDropRef} className={`relative ${pulseClass} ${isIncompatible ? 'opacity-30 brightness-50' : ''}`}>
      <button
        ref={setDragRef}
        {...dragListeners}
        {...dragAttributes}
        onClick={handleClick}
        className={`
          item-cell ${rarityClass}
          cursor-pointer hover:scale-105 transition-transform duration-200 ease-site
          ${isDragging ? 'opacity-40' : ''}
        `}
        title={slot.item!.name}
      >
        {slot.item!.image ? (
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
        )}
      </button>
    </div>
  );
};

// --- Main FastSlots component ---

export default function FastSlots() {
  const equipment = useAppSelector(selectEquipment);
  const fastSlotData = useAppSelector(selectFastSlots);

  // Get all fast_slot equipment entries (for enabled/disabled status)
  const fastSlotEquipment: EquipmentSlotData[] = [];
  for (let i = 1; i <= FAST_SLOT_COUNT; i++) {
    const slotType = `fast_slot_${i}`;
    const equipSlot = equipment.find((s) => s.slot_type === slotType);
    if (equipSlot) {
      fastSlotEquipment.push(equipSlot);
    }
  }

  // Merge fast slot data (which has quantity info) into equipment slots
  const mergedSlots: MergedFastSlot[] = fastSlotEquipment.map((eqSlot) => {
    const fsData = fastSlotData.find((fs) => fs.slot_type === eqSlot.slot_type);
    return {
      ...eqSlot,
      quantity: fsData?.quantity ?? 0,
    };
  });

  if (mergedSlots.length === 0) return null;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="flex items-center gap-1.5">
        <img src={swapBagIcon} alt="" className="w-5 h-5 opacity-70" />
        <span className="text-xs text-white/60 font-medium uppercase tracking-wider">
          Быстрые слоты
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {mergedSlots.map((slot, index) => (
          <FastSlotDropTarget
            key={slot.slot_type}
            slot={slot}
            slotIndex={index + 1}
          />
        ))}
      </div>
    </div>
  );
}

import { createContext, useContext, useState, useCallback, useMemo } from 'react';
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
} from '@dnd-kit/core';
import toast from 'react-hot-toast';
import { useAppDispatch } from '../../../../redux/store';
import { equipItem, unequipItem } from '../../../../redux/slices/profileSlice';
import type { InventoryItem, EquipmentSlotData } from '../../../../redux/slices/profileSlice';
import { EQUIPMENT_ITEM_TYPES, FAST_SLOT_ITEM_TYPES } from './constants';
import { ITEM_TYPE_ICONS } from '../../constants';

// --- Drag data types ---

export type DragSource = 'inventory' | 'equipment' | 'fast_slot';

export interface DragItemData {
  source: DragSource;
  inventoryItem?: InventoryItem;
  slot?: EquipmentSlotData;
  itemType: string;
}

// --- Character ID context ---

const InventoryCharacterContext = createContext<number>(0);

export const useInventoryCharacterId = () => useContext(InventoryCharacterContext);

// --- Compatible slots context ---

const CompatibleSlotsContext = createContext<string[]>([]);

export const useCompatibleSlots = () => useContext(CompatibleSlotsContext);

// --- Active drag item context (for DragOverlay) ---

const ActiveDragContext = createContext<DragItemData | null>(null);

export const useActiveDrag = () => useContext(ActiveDragContext);

// --- Helper: compute compatible slots for a given item_type ---

function getCompatibleSlots(itemType: string): string[] {
  // Equipment items map 1:1 to their slot
  if (itemType in EQUIPMENT_ITEM_TYPES) {
    return [EQUIPMENT_ITEM_TYPES[itemType]];
  }
  // Fast-slot items are compatible with all fast slots
  if (FAST_SLOT_ITEM_TYPES.has(itemType)) {
    return Array.from({ length: 10 }, (_, i) => `fast_slot_${i + 1}`);
  }
  return [];
}

// --- DragOverlay content ---

interface DragOverlayContentProps {
  data: DragItemData;
}

const DragOverlayContent = ({ data }: DragOverlayContentProps) => {
  const item = data.inventoryItem?.item ?? data.slot?.item;
  if (!item) return null;

  const iconSrc = item.image || ITEM_TYPE_ICONS[item.item_type];
  const rarityClass = item.item_rarity && item.item_rarity !== 'common'
    ? `rarity-${item.item_rarity}`
    : '';

  return (
    <div
      className={`item-cell ${rarityClass} pointer-events-none`}
      style={{ opacity: 0.85 }}
    >
      {iconSrc ? (
        <img
          src={iconSrc}
          alt={item.name}
          className={item.image ? 'w-full h-full object-cover' : 'w-10 h-10 opacity-70'}
          draggable={false}
        />
      ) : null}
    </div>
  );
};

// --- Main Provider ---

interface InventoryDndProviderProps {
  characterId: number;
  children: React.ReactNode;
}

const InventoryDndProvider = ({ characterId, children }: InventoryDndProviderProps) => {
  const dispatch = useAppDispatch();
  const [compatibleSlots, setCompatibleSlots] = useState<string[]>([]);
  const [activeDragData, setActiveDragData] = useState<DragItemData | null>(null);

  const pointerSensor = useSensor(PointerSensor, {
    activationConstraint: { distance: 8 },
  });
  const touchSensor = useSensor(TouchSensor, {
    activationConstraint: { delay: 200, tolerance: 5 },
  });
  const sensors = useSensors(pointerSensor, touchSensor);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const data = event.active.data.current as DragItemData | undefined;
    if (!data) return;

    setActiveDragData(data);
    setCompatibleSlots(getCompatibleSlots(data.itemType));
  }, []);

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const { active, over } = event;

      // Clear drag state
      setActiveDragData(null);
      setCompatibleSlots([]);

      if (!over) return;

      const dragData = active.data.current as DragItemData | undefined;
      if (!dragData) return;

      const overId = over.id as string;

      try {
        // Case: inventory/equipment/fast_slot -> equipment slot
        if (overId.startsWith('drop-equipment-')) {
          if (dragData.source === 'inventory' && dragData.inventoryItem) {
            const result = await dispatch(
              equipItem({ characterId, itemId: dragData.inventoryItem.item.id }),
            );
            if (result.meta.requestStatus === 'fulfilled') {
              toast.success('Предмет экипирован');
            } else {
              const payload = result.payload as string | undefined;
              toast.error(payload ?? 'Не удалось экипировать предмет');
            }
          }
          return;
        }

        // Case: inventory -> fast slot
        if (overId.startsWith('drop-fast_slot-')) {
          if (dragData.source === 'inventory' && dragData.inventoryItem) {
            const result = await dispatch(
              equipItem({ characterId, itemId: dragData.inventoryItem.item.id }),
            );
            if (result.meta.requestStatus === 'fulfilled') {
              toast.success('Предмет экипирован');
            } else {
              const payload = result.payload as string | undefined;
              toast.error(payload ?? 'Не удалось экипировать предмет');
            }
          }
          return;
        }

        // Case: equipment/fast_slot -> inventory grid (unequip)
        if (overId === 'drop-inventory-grid') {
          if (
            (dragData.source === 'equipment' || dragData.source === 'fast_slot') &&
            dragData.slot
          ) {
            const result = await dispatch(
              unequipItem({ characterId, slotType: dragData.slot.slot_type }),
            );
            if (result.meta.requestStatus === 'fulfilled') {
              toast.success('Предмет снят');
            } else {
              const payload = result.payload as string | undefined;
              toast.error(payload ?? 'Не удалось снять предмет');
            }
          }
          return;
        }
      } catch {
        toast.error('Произошла ошибка');
      }
    },
    [characterId, dispatch],
  );

  const handleDragCancel = useCallback(() => {
    setActiveDragData(null);
    setCompatibleSlots([]);
  }, []);

  const compatibleSlotsMemo = useMemo(() => compatibleSlots, [compatibleSlots]);

  return (
    <InventoryCharacterContext.Provider value={characterId}>
      <CompatibleSlotsContext.Provider value={compatibleSlotsMemo}>
        <ActiveDragContext.Provider value={activeDragData}>
          <DndContext
            sensors={sensors}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
          >
            {children}
            <DragOverlay dropAnimation={null}>
              {activeDragData ? <DragOverlayContent data={activeDragData} /> : null}
            </DragOverlay>
          </DndContext>
        </ActiveDragContext.Provider>
      </CompatibleSlotsContext.Provider>
    </InventoryCharacterContext.Provider>
  );
};

export default InventoryDndProvider;

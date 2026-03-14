import { useAppDispatch } from '../../../redux/store';
import { openContextMenu } from '../../../redux/slices/profileSlice';
import type { EquipmentSlotData, InventoryItem } from '../../../redux/slices/profileSlice';
import { ITEM_TYPE_ICONS, EQUIPMENT_SLOT_LABELS } from '../constants';

interface EquipmentSlotProps {
  slot: EquipmentSlotData;
  /** Size variant: 'normal' (80px) or 'small' (56px) */
  size?: 'normal' | 'small';
}

export default function EquipmentSlot({ slot, size = 'normal' }: EquipmentSlotProps) {
  const dispatch = useAppDispatch();
  const isEmpty = !slot.item;
  const placeholderIcon = ITEM_TYPE_ICONS[slot.slot_type] ?? ITEM_TYPE_ICONS['misc'];
  const label = EQUIPMENT_SLOT_LABELS[slot.slot_type] ?? slot.slot_type;

  const rarityClass = slot.item ? `rarity-${slot.item.item_rarity}` : '';

  const sizeClasses = size === 'small'
    ? 'w-[56px] h-[56px] !w-[56px] !h-[56px]'
    : '';

  const handleClick = (e: React.MouseEvent) => {
    if (!slot.item) return;
    // Construct an InventoryItem-like object for context menu
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
    }));
  };

  return (
    <div className="flex flex-col items-center gap-1">
      <button
        onClick={handleClick}
        className={`
          item-cell ${isEmpty ? 'item-cell-empty' : rarityClass}
          ${sizeClasses}
          cursor-pointer hover:scale-105 transition-transform duration-200 ease-site
        `}
        title={isEmpty ? label : slot.item!.name}
        style={size === 'small' ? { width: 56, height: 56 } : undefined}
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
            />
          ) : (
            <img
              src={placeholderIcon}
              alt={slot.item!.name}
              className="w-8 h-8 opacity-70"
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

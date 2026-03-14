import { useAppSelector } from '../../../redux/store';
import { selectEquipment, selectFastSlots } from '../../../redux/slices/profileSlice';
import type { EquipmentSlotData } from '../../../redux/slices/profileSlice';
import EquipmentSlot from './EquipmentSlot';
import swapBagIcon from '../../../assets/icons/equipment/swap-bag.svg';

const FAST_SLOT_COUNT = 10;

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
  const mergedSlots = fastSlotEquipment.map((eqSlot) => {
    const fsData = fastSlotData.find((fs) => fs.slot_type === eqSlot.slot_type);
    // If we have fast slot data, enrich the equipment slot with quantity
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
        {mergedSlots.map((slot) => {
          if (!slot.is_enabled) {
            // Disabled slot - dimmed
            return (
              <div
                key={slot.slot_type}
                className="item-cell item-cell-empty opacity-30"
                title="Слот недоступен"
              />
            );
          }

          if (!slot.item) {
            // Enabled but empty
            return (
              <div
                key={slot.slot_type}
                className="item-cell item-cell-empty"
              />
            );
          }

          // Filled fast slot
          return (
            <div key={slot.slot_type} className="relative">
              <EquipmentSlot slot={slot} />
              {slot.quantity > 1 && (
                <span
                  className="
                    absolute -bottom-1 -right-1 min-w-[20px] h-[20px]
                    flex items-center justify-center
                    text-[10px] font-medium text-white
                    bg-site-bg rounded-full
                    border border-white/30 px-1
                  "
                >
                  {slot.quantity}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

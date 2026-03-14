import { useAppSelector } from '../../../redux/store';
import { selectEquipmentSlots } from '../../../redux/slices/profileSlice';
import type { EquipmentSlotData } from '../../../redux/slices/profileSlice';
import EquipmentSlot from './EquipmentSlot';
import { motion } from 'motion/react';

/**
 * EquipmentPanel — Center column of the profile page.
 * Renders equipment slots in a structured 2-column grid layout.
 *
 * Layout:
 *   Row 1: Основное оружие | Дополнительное оружие
 *   Row 2: Шлем            | Броня
 *   Row 3: Плащ            | Пояс
 *   ---separator---
 *   Row 4: Щит             | Кольцо
 *   Row 5: Ожерелье        | Браслет
 */
export default function EquipmentPanel() {
  const equipmentSlots = useAppSelector(selectEquipmentSlots);

  // Helper to find a slot by type
  const getSlot = (slotType: string): EquipmentSlotData | undefined =>
    equipmentSlots.find((s) => s.slot_type === slotType);

  // Provide a default empty slot if not found
  const slotOrEmpty = (slotType: string): EquipmentSlotData => {
    return getSlot(slotType) ?? {
      character_id: 0,
      slot_type: slotType,
      item_id: null,
      is_enabled: true,
      item: null,
    };
  };

  // Weapons + Armor group (top grid)
  const topSlots = ['main_weapon', 'additional_weapons', 'head', 'body', 'cloak', 'belt'];
  // Accessory group (bottom grid)
  const accessorySlots = ['shield', 'ring', 'necklace', 'bracelet'];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col items-center gap-2 pt-1.5 pb-4"
    >
      {/* Weapons + Armor: 2-column grid */}
      <div className="grid grid-cols-2 gap-1.5">
        {topSlots.map((slotType) => (
          <EquipmentSlot key={slotType} slot={slotOrEmpty(slotType)} />
        ))}
      </div>

      {/* Separator line between armor and accessories */}
      <div className="w-16 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent my-1" />

      {/* Accessory slots: 2-column grid */}
      <div className="grid grid-cols-2 gap-1.5">
        {accessorySlots.map((slotType) => (
          <EquipmentSlot key={slotType} slot={slotOrEmpty(slotType)} />
        ))}
      </div>
    </motion.div>
  );
}

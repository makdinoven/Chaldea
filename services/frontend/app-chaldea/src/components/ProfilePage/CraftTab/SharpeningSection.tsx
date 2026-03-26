import { useState, useMemo } from 'react';
import { motion } from 'motion/react';
import { useAppSelector } from '../../../redux/store';
import { selectInventory, selectEquipmentSlots } from '../../../redux/slices/profileSlice';
import type { InventoryItem, EquipmentSlotData } from '../../../redux/slices/profileSlice';
import SharpeningModal from './SharpeningModal';

const SHARPENABLE_TYPES = new Set([
  'head', 'body', 'cloak', 'belt',
  'main_weapon', 'additional_weapons', 'shield',
]);

const MAX_POINTS = 15;

interface SharpenablItem {
  rowId: number;
  itemId: number;
  name: string;
  image: string | null;
  itemType: string;
  itemRarity: string;
  pointsSpent: number;
  source: 'inventory' | 'equipment';
}

interface SharpeningSectionProps {
  characterId: number;
}

const SharpeningSection = ({ characterId }: SharpeningSectionProps) => {
  const inventory = useAppSelector(selectInventory);
  const equipment = useAppSelector(selectEquipmentSlots);
  const [selectedItem, setSelectedItem] = useState<SharpenablItem | null>(null);

  const sharpenableItems = useMemo(() => {
    const items: SharpenablItem[] = [];

    // Items from inventory
    for (const inv of inventory) {
      if (SHARPENABLE_TYPES.has(inv.item.item_type)) {
        items.push({
          rowId: inv.id,
          itemId: inv.item.id,
          name: inv.item.name,
          image: inv.item.image,
          itemType: inv.item.item_type,
          itemRarity: inv.item.item_rarity,
          pointsSpent: inv.enhancement_points_spent ?? 0,
          source: 'inventory',
        });
      }
    }

    // Items from equipment
    for (const slot of equipment) {
      if (slot.item && SHARPENABLE_TYPES.has(slot.item.item_type)) {
        items.push({
          rowId: slot.id ?? 0,
          itemId: slot.item.id,
          name: slot.item.name,
          image: slot.item.image,
          itemType: slot.item.item_type,
          itemRarity: slot.item.item_rarity,
          pointsSpent: slot.enhancement_points_spent ?? 0,
          source: 'equipment',
        });
      }
    }

    return items;
  }, [inventory, equipment]);

  const rarityBorder = (rarity: string) => {
    switch (rarity) {
      case 'rare': return 'border-rarity-rare';
      case 'epic': return 'border-rarity-epic';
      case 'mythical': return 'border-rarity-mythical';
      case 'legendary': return 'border-rarity-legendary';
      default: return 'border-white/20';
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <h3 className="gold-text text-lg font-medium uppercase">Заточка</h3>
        <p className="text-white/60 text-sm mt-1">
          Выберите оружие или броню для заточки. Каждый предмет имеет бюджет {MAX_POINTS} поинтов.
        </p>
      </div>

      {sharpenableItems.length === 0 ? (
        <p className="text-white/40 text-sm py-4 text-center">
          Нет подходящих предметов для заточки
        </p>
      ) : (
        <motion.div
          className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2"
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.04 } } }}
        >
          {sharpenableItems.map((item) => (
            <motion.button
              key={`${item.source}-${item.rowId}`}
              variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}
              onClick={() => setSelectedItem(item)}
              className={`
                flex flex-col items-center gap-1.5 p-2 rounded-card
                bg-white/[0.04] hover:bg-white/[0.08]
                border ${rarityBorder(item.itemRarity)}
                transition-all duration-200 ease-site cursor-pointer
                text-center
              `}
            >
              <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-full overflow-hidden bg-white/[0.05] flex items-center justify-center">
                {item.image ? (
                  <img src={item.image} alt={item.name} className="w-full h-full object-cover" />
                ) : (
                  <span className="text-white/30 text-2xl">?</span>
                )}
              </div>
              <span className="text-white text-xs leading-tight line-clamp-2">{item.name}</span>
              <span className={`text-xs font-medium ${item.pointsSpent >= MAX_POINTS ? 'text-site-red' : 'text-gold'}`}>
                [{item.pointsSpent}/{MAX_POINTS}]
              </span>
              {item.source === 'equipment' && (
                <span className="text-[10px] text-site-blue">экипировано</span>
              )}
            </motion.button>
          ))}
        </motion.div>
      )}

      {selectedItem && (
        <SharpeningModal
          characterId={characterId}
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </div>
  );
};

export default SharpeningSection;

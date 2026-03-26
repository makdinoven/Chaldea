import { useState, useMemo } from 'react';
import { motion } from 'motion/react';
import { useAppSelector } from '../../../redux/store';
import { selectInventory, selectEquipmentSlots } from '../../../redux/slices/profileSlice';
import type { InventoryItem, EquipmentSlotData } from '../../../redux/slices/profileSlice';
import GemSocketModal from './GemSocketModal';

const JEWELRY_TYPES = new Set(['ring', 'necklace', 'bracelet']);

interface JewelryItem {
  rowId: number;
  itemId: number;
  name: string;
  image: string | null;
  itemType: string;
  itemRarity: string;
  socketCount: number;
  socketedGems: (number | null)[];
  enhancementPointsSpent: number;
  source: 'inventory' | 'equipment';
}

function parseSocketedGems(raw: string | null): (number | null)[] {
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

interface GemSocketSectionProps {
  characterId: number;
}

const GemSocketSection = ({ characterId }: GemSocketSectionProps) => {
  const inventory = useAppSelector(selectInventory);
  const equipment = useAppSelector(selectEquipmentSlots);
  const [selectedItem, setSelectedItem] = useState<JewelryItem | null>(null);

  const jewelryItems = useMemo(() => {
    const items: JewelryItem[] = [];

    for (const inv of inventory) {
      if (JEWELRY_TYPES.has(inv.item.item_type) && inv.item.socket_count > 0) {
        const gems = parseSocketedGems(inv.socketed_gems);
        items.push({
          rowId: inv.id,
          itemId: inv.item.id,
          name: inv.item.name,
          image: inv.item.image,
          itemType: inv.item.item_type,
          itemRarity: inv.item.item_rarity,
          socketCount: inv.item.socket_count,
          socketedGems: gems,
          enhancementPointsSpent: inv.enhancement_points_spent ?? 0,
          source: 'inventory',
        });
      }
    }

    for (const slot of equipment) {
      if (slot.item && JEWELRY_TYPES.has(slot.item.item_type) && slot.item.socket_count > 0) {
        const gems = parseSocketedGems(slot.socketed_gems);
        items.push({
          rowId: slot.id ?? 0,
          itemId: slot.item.id,
          name: slot.item.name,
          image: slot.item.image,
          itemType: slot.item.item_type,
          itemRarity: slot.item.item_rarity,
          socketCount: slot.item.socket_count,
          socketedGems: gems,
          enhancementPointsSpent: slot.enhancement_points_spent ?? 0,
          source: 'equipment',
        });
      }
    }

    return items;
  }, [inventory, equipment]);

  const filledCount = (gems: (number | null)[]) => gems.filter((g) => g !== null).length;

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
        <h3 className="gold-text text-lg font-medium uppercase">Камни и слоты</h3>
        <p className="text-white/60 text-sm mt-1">
          Вставляйте камни в слоты украшений для усиления характеристик.
        </p>
      </div>

      {jewelryItems.length === 0 ? (
        <p className="text-white/40 text-sm py-4 text-center">
          Нет украшений со слотами
        </p>
      ) : (
        <motion.div
          className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2"
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.04 } } }}
        >
          {jewelryItems.map((item) => {
            const filled = filledCount(item.socketedGems);
            return (
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

                {/* Socket indicators */}
                <div className="flex items-center gap-1">
                  {Array.from({ length: item.socketCount }, (_, i) => (
                    <span
                      key={i}
                      className={`w-3 h-3 rounded-full border ${
                        i < filled
                          ? 'bg-gold border-gold-dark'
                          : 'bg-transparent border-white/30'
                      }`}
                    />
                  ))}
                </div>

                <span className="text-xs text-white/50">
                  {filled}/{item.socketCount} камней
                </span>

                {item.enhancementPointsSpent > 0 && (
                  <span className="text-[10px] text-gold">+{item.enhancementPointsSpent} заточка</span>
                )}
                {item.source === 'equipment' && (
                  <span className="text-[10px] text-site-blue">экипировано</span>
                )}
              </motion.button>
            );
          })}
        </motion.div>
      )}

      {selectedItem && (
        <GemSocketModal
          characterId={characterId}
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </div>
  );
};

export default GemSocketSection;

import { useState, useMemo } from 'react';
import { motion } from 'motion/react';
import { useAppSelector } from '../../../redux/store';
import { selectInventory } from '../../../redux/slices/profileSlice';
import SmeltingModal from './SmeltingModal';

const JEWELRY_TYPES = new Set(['ring', 'necklace', 'bracelet']);

function parseSocketedGems(raw: string | null): (number | null)[] {
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

interface SmeltableItem {
  rowId: number;
  itemId: number;
  name: string;
  image: string | null;
  itemType: string;
  itemRarity: string;
  hasGems: boolean;
  gemCount: number;
}

interface SmeltingSectionProps {
  characterId: number;
}

const SmeltingSection = ({ characterId }: SmeltingSectionProps) => {
  const inventory = useAppSelector(selectInventory);
  const [selectedItem, setSelectedItem] = useState<SmeltableItem | null>(null);

  const smeltableItems = useMemo(() => {
    const items: SmeltableItem[] = [];

    for (const inv of inventory) {
      if (JEWELRY_TYPES.has(inv.item.item_type)) {
        const gems = parseSocketedGems(inv.socketed_gems);
        const filledGems = gems.filter((g) => g !== null).length;
        items.push({
          rowId: inv.id,
          itemId: inv.item.id,
          name: inv.item.name,
          image: inv.item.image,
          itemType: inv.item.item_type,
          itemRarity: inv.item.item_rarity,
          hasGems: filledGems > 0,
          gemCount: filledGems,
        });
      }
    }

    return items;
  }, [inventory]);

  const rarityBorder = (rarity: string) => {
    switch (rarity) {
      case 'rare': return 'border-rarity-rare';
      case 'epic': return 'border-rarity-epic';
      case 'mythical': return 'border-rarity-mythical';
      case 'legendary': return 'border-rarity-legendary';
      default: return 'border-white/20';
    }
  };

  const rarityLabel = (rarity: string) => {
    switch (rarity) {
      case 'common': return 'Обычный';
      case 'rare': return 'Редкий';
      case 'epic': return 'Эпический';
      case 'mythical': return 'Мифический';
      case 'legendary': return 'Легендарный';
      default: return rarity;
    }
  };

  const rarityTextColor = (rarity: string) => {
    switch (rarity) {
      case 'rare': return 'text-rarity-rare';
      case 'epic': return 'text-rarity-epic';
      case 'mythical': return 'text-rarity-mythical';
      case 'legendary': return 'text-rarity-legendary';
      default: return 'text-white/60';
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <h3 className="gold-text text-lg font-medium uppercase">Переплавка</h3>
        <p className="text-white/60 text-sm mt-1">
          Разберите украшения на материалы. Экипированные предметы нужно сначала снять.
        </p>
      </div>

      {smeltableItems.length === 0 ? (
        <p className="text-white/40 text-sm py-4 text-center">
          Нет украшений для переплавки в инвентаре
        </p>
      ) : (
        <motion.div
          className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2"
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.04 } } }}
        >
          {smeltableItems.map((item) => (
            <motion.button
              key={`smelt-${item.rowId}`}
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
              <span className={`text-[10px] ${rarityTextColor(item.itemRarity)}`}>
                {rarityLabel(item.itemRarity)}
              </span>
              {item.hasGems && (
                <span className="text-[10px] text-site-red font-medium">
                  &#9888; {item.gemCount} камн.
                </span>
              )}
            </motion.button>
          ))}
        </motion.div>
      )}

      {selectedItem && (
        <SmeltingModal
          characterId={characterId}
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </div>
  );
};

export default SmeltingSection;

import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import { ITEM_TYPE_ICONS } from '../../ProfilePage/constants';
import type { InventoryItem } from '../../../redux/slices/profileSlice';

interface SelectedItem {
  item_id: number;
  quantity: number;
}

interface TradeItemSelectorProps {
  characterId: number;
  selectedItems: SelectedItem[];
  onItemsChange: (items: SelectedItem[]) => void;
}

const MIN_TRADE_CELLS = 16;

const getRarityClass = (rarity: string | null | undefined): string => {
  if (!rarity || rarity === 'common') return '';
  const map: Record<string, string> = {
    rare: 'rarity-rare',
    epic: 'rarity-epic',
    mythical: 'rarity-mythical',
    legendary: 'rarity-legendary',
  };
  return map[rarity] || '';
};

const containerVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.03 },
  },
};

const cellVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0 },
};

const TradeItemSelector = ({
  characterId,
  selectedItems,
  onItemsChange,
}: TradeItemSelectorProps) => {
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchItems = async () => {
      setLoading(true);
      try {
        const { data } = await axios.get<InventoryItem[]>(
          `/inventory/${characterId}/items`,
        );
        if (!cancelled) setInventory(data);
      } catch {
        if (!cancelled) toast.error('Не удалось загрузить инвентарь');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchItems();
    return () => { cancelled = true; };
  }, [characterId]);

  const getSelectedQuantity = useCallback(
    (itemId: number): number => {
      const found = selectedItems.find((s) => s.item_id === itemId);
      return found ? found.quantity : 0;
    },
    [selectedItems],
  );

  const toggleItem = useCallback(
    (invItem: InventoryItem) => {
      const existing = selectedItems.find((s) => s.item_id === invItem.item_id);
      if (existing) {
        onItemsChange(selectedItems.filter((s) => s.item_id !== invItem.item_id));
      } else {
        onItemsChange([...selectedItems, { item_id: invItem.item_id, quantity: 1 }]);
      }
    },
    [selectedItems, onItemsChange],
  );

  const changeQuantity = useCallback(
    (itemId: number, maxQty: number, delta: number) => {
      onItemsChange(
        selectedItems.map((s) => {
          if (s.item_id !== itemId) return s;
          const next = Math.max(1, Math.min(maxQty, s.quantity + delta));
          return { ...s, quantity: next };
        }),
      );
    },
    [selectedItems, onItemsChange],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (inventory.length === 0) {
    return (
      <p className="text-white/50 text-sm text-center py-4">
        Инвентарь пуст
      </p>
    );
  }

  const emptyCellsCount = Math.max(0, MIN_TRADE_CELLS - inventory.length);

  return (
    <motion.div
      className="gold-scrollbar-wide overflow-y-auto max-h-[240px] sm:max-h-[300px] pr-1 rounded-lg"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      <div className="grid grid-cols-4 gap-1.5 p-1.5">
        {inventory.map((invItem) => {
          const selected = getSelectedQuantity(invItem.item_id) > 0;
          const selQty = getSelectedQuantity(invItem.item_id);
          const iconSrc = ITEM_TYPE_ICONS[invItem.item.item_type];

          return (
            <motion.div key={invItem.id} variants={cellVariants} className="relative">
              <button
                type="button"
                onClick={() => toggleItem(invItem)}
                className={`
                  item-cell cursor-pointer transition-all duration-200 hover:scale-105
                  ${getRarityClass(invItem.item.item_rarity)}
                  ${selected ? 'ring-2 ring-site-blue ring-offset-1 ring-offset-transparent shadow-[0_0_8px_rgba(118,166,189,0.4)]' : ''}
                `}
                title={invItem.item.name}
              >
                {invItem.item.image ? (
                  <img
                    src={invItem.item.image}
                    alt={invItem.item.name}
                    className="w-full h-full object-cover"
                    draggable={false}
                  />
                ) : iconSrc ? (
                  <img
                    src={iconSrc}
                    alt={invItem.item.name}
                    className="w-10 h-10 opacity-70"
                    draggable={false}
                  />
                ) : null}
              </button>

              {/* Quantity badge (like ItemCell) */}
              {invItem.quantity > 1 && (
                <span
                  className="
                    absolute -bottom-1 -right-1 z-10 min-w-[20px] h-[20px]
                    flex items-center justify-center
                    text-[10px] font-medium text-white
                    bg-site-bg rounded-full
                    border border-white/30 px-1
                  "
                >
                  {invItem.quantity}
                </span>
              )}

              {/* Selected quantity controls overlay */}
              {selected && invItem.quantity > 1 && (
                <div className="absolute -top-1 left-1/2 -translate-x-1/2 z-20 flex items-center gap-0.5 bg-site-bg/90 rounded-full px-1 py-0.5 border border-white/20">
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); changeQuantity(invItem.item_id, invItem.quantity, -1); }}
                    className="w-4 h-4 flex items-center justify-center text-[10px] text-white hover:text-site-blue transition-colors"
                  >
                    -
                  </button>
                  <span className="text-[10px] text-white min-w-[14px] text-center font-medium">
                    {selQty}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); changeQuantity(invItem.item_id, invItem.quantity, 1); }}
                    className="w-4 h-4 flex items-center justify-center text-[10px] text-white hover:text-site-blue transition-colors"
                  >
                    +
                  </button>
                </div>
              )}

              {/* Selected checkmark */}
              {selected && (
                <div className="absolute top-0 right-0 z-10 w-4 h-4 bg-site-blue rounded-full flex items-center justify-center">
                  <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              )}
            </motion.div>
          );
        })}

        {/* Empty placeholder cells */}
        {Array.from({ length: emptyCellsCount }).map((_, idx) => (
          <motion.div key={`empty-${idx}`} variants={cellVariants}>
            <div className="item-cell item-cell-empty" />
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
};

export default TradeItemSelector;

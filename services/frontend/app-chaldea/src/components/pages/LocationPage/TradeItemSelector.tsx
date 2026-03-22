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
        // Remove item
        onItemsChange(selectedItems.filter((s) => s.item_id !== invItem.item_id));
      } else {
        // Add item with quantity 1
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

  return (
    <div className="gold-scrollbar-wide overflow-y-auto max-h-[240px] sm:max-h-[300px]">
      <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
        {inventory.map((invItem) => {
          const selected = getSelectedQuantity(invItem.item_id) > 0;
          const selQty = getSelectedQuantity(invItem.item_id);
          const iconSrc = ITEM_TYPE_ICONS[invItem.item.item_type];

          return (
            <motion.div
              key={invItem.id}
              className="flex flex-col items-center gap-1"
              whileHover={{ scale: 1.05 }}
              transition={{ duration: 0.15 }}
            >
              {/* Item cell */}
              <button
                type="button"
                onClick={() => toggleItem(invItem)}
                className={`
                  item-cell cursor-pointer transition-all duration-200
                  ${getRarityClass(invItem.item.item_rarity)}
                  ${selected ? 'ring-2 ring-site-blue ring-offset-1 ring-offset-transparent' : ''}
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

              {/* Item name (truncated) */}
              <span className="text-[10px] text-white/70 text-center truncate w-full max-w-[60px]">
                {invItem.item.name}
              </span>

              {/* Quantity selector — shown only when selected and stackable */}
              {selected && invItem.quantity > 1 && (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => changeQuantity(invItem.item_id, invItem.quantity, -1)}
                    className="w-5 h-5 flex items-center justify-center text-xs text-white bg-white/10 rounded hover:bg-white/20 transition-colors"
                  >
                    -
                  </button>
                  <span className="text-xs text-white min-w-[18px] text-center">
                    {selQty}
                  </span>
                  <button
                    type="button"
                    onClick={() => changeQuantity(invItem.item_id, invItem.quantity, 1)}
                    className="w-5 h-5 flex items-center justify-center text-xs text-white bg-white/10 rounded hover:bg-white/20 transition-colors"
                  >
                    +
                  </button>
                </div>
              )}

              {/* Owned quantity badge */}
              {invItem.quantity > 1 && (
                <span className="text-[9px] text-white/40">
                  x{invItem.quantity}
                </span>
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
};

export default TradeItemSelector;

import { motion, AnimatePresence } from 'motion/react';
import type { GroupInventoryItem } from '../../api/dungeons';

// --- Types ---

interface DungeonInventoryProps {
  items: GroupInventoryItem[];
  compact?: boolean;
}

// --- Component ---

const DungeonInventory = ({ items, compact = false }: DungeonInventoryProps) => {
  if (items.length === 0) {
    return (
      <div className={`bg-black/40 rounded-card backdrop-blur-sm ${compact ? 'p-3' : 'p-4'}`}>
        <h3 className="gold-text text-sm font-medium uppercase mb-2">
          Групповой инвентарь
        </h3>
        <p className="text-white/40 text-xs italic">Пусто</p>
      </div>
    );
  }

  return (
    <div className={`bg-black/40 rounded-card backdrop-blur-sm ${compact ? 'p-3' : 'p-4'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="gold-text text-sm font-medium uppercase">
          Групповой инвентарь
        </h3>
        <span className="text-white/30 text-xs">
          {items.length} {items.length === 1 ? 'предмет' : items.length < 5 ? 'предмета' : 'предметов'}
        </span>
      </div>

      <div className={`flex flex-col gap-1 ${compact ? 'max-h-32' : 'max-h-48'} overflow-y-auto gold-scrollbar`}>
        <AnimatePresence mode="popLayout">
          {items.map((item) => (
            <motion.div
              key={item.item_id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="flex items-center justify-between py-1.5 px-2 rounded bg-white/5 hover:bg-white/[0.07] transition-colors"
            >
              <span className="text-white text-xs truncate mr-2">
                {item.item_name}
              </span>
              <span className="text-white/40 text-xs shrink-0">
                x{item.quantity}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default DungeonInventory;

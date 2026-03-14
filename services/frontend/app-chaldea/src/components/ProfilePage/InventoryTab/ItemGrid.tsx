import { motion } from 'motion/react';
import { useAppSelector } from '../../../redux/store';
import { selectFilteredInventory } from '../../../redux/slices/profileSlice';
import ItemCell from './ItemCell';
import { MIN_GRID_CELLS } from '../constants';

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

const ItemGrid = () => {
  const items = useAppSelector(selectFilteredInventory);

  const emptyCellsCount = Math.max(0, MIN_GRID_CELLS - items.length);

  return (
    <motion.div
      className="gold-scrollbar-wide overflow-y-auto max-h-[516px] pr-1"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      <div className="grid grid-cols-4 gap-1.5 p-1.5 pb-4">
        {items.map((inventoryItem) => (
          <motion.div key={inventoryItem.id} variants={cellVariants}>
            <ItemCell inventoryItem={inventoryItem} />
          </motion.div>
        ))}
        {Array.from({ length: emptyCellsCount }).map((_, idx) => (
          <motion.div key={`empty-${idx}`} variants={cellVariants}>
            <ItemCell />
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
};

export default ItemGrid;

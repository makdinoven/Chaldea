import { motion } from 'motion/react';
import { useDroppable } from '@dnd-kit/core';
import { useAppSelector } from '../../../redux/store';
import { selectFilteredInventory } from '../../../redux/slices/profileSlice';
import ItemCell from './ItemCell';
import { MIN_GRID_CELLS } from '../constants';
import { useActiveDrag } from './dnd/InventoryDndContext';

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
  const activeDrag = useActiveDrag();

  const { setNodeRef, isOver } = useDroppable({
    id: 'drop-inventory-grid',
  });

  const emptyCellsCount = Math.max(0, MIN_GRID_CELLS - items.length);

  // Show visual feedback only when dragging from equipment/fast_slot
  const isFromEquipment =
    activeDrag !== null &&
    (activeDrag.source === 'equipment' || activeDrag.source === 'fast_slot');
  const showDropHighlight = isFromEquipment && isOver;

  return (
    <motion.div
      ref={setNodeRef}
      className={`gold-scrollbar-wide overflow-y-auto max-h-[516px] lg:max-h-full lg:h-full pr-1 rounded-lg transition-colors duration-200 ${
        showDropHighlight ? 'slot-pulse-compatible' : ''
      }`}
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

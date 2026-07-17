import { motion } from 'motion/react';
import { useDroppable } from '@dnd-kit/core';
import { useAppSelector } from '../../../redux/store';
import { selectFilteredInventory } from '../../../redux/slices/profileSlice';
import ItemCell from './ItemCell';
import { useActiveDrag } from './dnd/InventoryDndContext';
import bagIcon from '../../../assets/icons/equipment/bag.svg';

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

/**
 * FEAT-149: circular item cells in an auto-fill 64px grid (no filler cells);
 * an empty category shows a Russian empty state. The `drop-inventory-grid`
 * droppable stays on the whole scroll container so unequip-by-drop keeps
 * working even with few (or zero) items.
 */
const ItemGrid = () => {
  const items = useAppSelector(selectFilteredInventory);
  const activeDrag = useActiveDrag();

  const { setNodeRef, isOver } = useDroppable({
    id: 'drop-inventory-grid',
  });

  // Show visual feedback only when dragging from equipment/fast_slot
  const isFromEquipment =
    activeDrag !== null &&
    (activeDrag.source === 'equipment' || activeDrag.source === 'fast_slot');
  const showDropHighlight = isFromEquipment && isOver;

  return (
    <motion.div
      ref={setNodeRef}
      className={`gold-scrollbar-wide overflow-y-auto max-h-[516px] lg:max-h-none lg:flex-1 lg:min-h-0 pr-1 rounded-card transition-colors duration-200 ${
        showDropHighlight ? 'slot-pulse-compatible' : ''
      }`}
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      {items.length > 0 ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(64px,1fr))] gap-3 p-1.5 pb-4">
          {items.map((inventoryItem) => (
            <motion.div key={inventoryItem.id} variants={cellVariants}>
              <ItemCell inventoryItem={inventoryItem} />
            </motion.div>
          ))}
        </div>
      ) : (
        <div className="h-full min-h-[180px] flex flex-col items-center justify-center gap-2.5 px-5 py-14 text-center">
          <img src={bagIcon} alt="" className="w-10 h-10 opacity-20" draggable={false} />
          <span className="text-white/40 text-sm">В этой категории пусто</span>
        </div>
      )}
    </motion.div>
  );
};

export default ItemGrid;

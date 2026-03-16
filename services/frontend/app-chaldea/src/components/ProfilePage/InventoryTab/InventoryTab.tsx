import { motion } from 'motion/react';
import CategorySidebar from './CategorySidebar';
import ItemGrid from './ItemGrid';
import ItemContextMenu from './ItemContextMenu';
import EquipmentPanel from '../EquipmentPanel/EquipmentPanel';
import FastSlots from '../EquipmentPanel/FastSlots';
import CharacterInfoPanel from '../CharacterInfoPanel/CharacterInfoPanel';
import InventoryDndProvider from './dnd/InventoryDndContext';

interface InventoryTabProps {
  characterId: number;
}

const InventoryTab = ({ characterId }: InventoryTabProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="relative"
    >
      <InventoryDndProvider characterId={characterId}>
        {/*
          Layout from Figma (left to right):
          [CategorySidebar] | [ItemGrid (scrollable)] | [EquipmentSlots] | [FastSlots] | [CharacterInfo]
        */}
        <div className="relative z-10 flex gap-4 items-start">
          {/* Left: Category sidebar + Item grid */}
          <div className="flex gap-2 shrink-0">
            <CategorySidebar />
            <div>
              <ItemGrid />
            </div>
          </div>

          {/* Center: Equipment slots (vertical layout) */}
          <div className="flex justify-center shrink-0">
            <EquipmentPanel />
          </div>

          {/* Right-center: Fast slots (vertical column) */}
          <div className="flex justify-center shrink-0 py-4">
            <FastSlots />
          </div>

          {/* Far right: Character info (portrait + stats) — pulled up to align with tab menu */}
          <div className="min-w-[240px] ml-auto -mt-[72px]">
            <CharacterInfoPanel />
          </div>
        </div>
      </InventoryDndProvider>

      {/* Context menu rendered at fixed position */}
      <ItemContextMenu characterId={characterId} />
    </motion.div>
  );
};

export default InventoryTab;

import { motion } from 'motion/react';
import InventoryDndProvider from '../InventoryTab/dnd/InventoryDndContext';
import ItemContextMenu from '../InventoryTab/ItemContextMenu';
import ItemDetailModal from '../InventoryTab/ItemDetailModal';
import LeftColumn from './LeftColumn';
import CenterColumn from './CenterColumn';
import RightColumn from './RightColumn';

interface CharacterTabProps {
  characterId: number;
}

const CharacterTab = ({ characterId }: CharacterTabProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="relative"
    >
      <InventoryDndProvider characterId={characterId}>
        {/* Single responsive layout — flex-wrap rearranges on smaller screens */}
        <div className="flex flex-wrap lg:grid lg:grid-cols-[1fr_auto_1fr] gap-4 items-start relative z-10">
          <LeftColumn characterId={characterId} />
          <CenterColumn />
          <RightColumn />
        </div>

        <ItemContextMenu characterId={characterId} />
        <ItemDetailModal characterId={characterId} />
      </InventoryDndProvider>
    </motion.div>
  );
};

export default CharacterTab;

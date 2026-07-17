import { motion } from 'motion/react';
import InventoryDndProvider from '../InventoryTab/dnd/InventoryDndContext';
import ItemContextMenu from '../InventoryTab/ItemContextMenu';
import ItemDetailModal from '../InventoryTab/ItemDetailModal';
import CharacterPanel from './CharacterPanel';
import IndicatorsPanel from './IndicatorsPanel';
import InventoryPanel from './InventoryPanel';

interface CharacterTabProps {
  characterId: number;
}

/**
 * «Персонаж» tab — FEAT-149 3-panel layout:
 * paper doll (392px) / indicators (minmax(300px,352px)) / inventory (1fr)
 * on desktop (lg+), single column below.
 */
const CharacterTab = ({ characterId }: CharacterTabProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="relative"
    >
      <InventoryDndProvider characterId={characterId}>
        <div className="grid grid-cols-1 lg:grid-cols-[392px_minmax(300px,352px)_1fr] gap-5 items-start relative z-10">
          <CharacterPanel />
          <IndicatorsPanel characterId={characterId} />
          <InventoryPanel />
        </div>

        <ItemContextMenu characterId={characterId} />
        <ItemDetailModal characterId={characterId} />
      </InventoryDndProvider>
    </motion.div>
  );
};

export default CharacterTab;

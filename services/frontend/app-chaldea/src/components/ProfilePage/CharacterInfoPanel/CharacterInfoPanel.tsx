import { motion } from 'motion/react';
import CharacterCard from './CharacterCard';
import StatsPanel from './StatsPanel';

/**
 * CharacterInfoPanel — Right column of the profile page.
 * Contains the CharacterCard (portrait, name, race, class, level)
 * and the StatsPanel (resource bars + primary stats).
 */
export default function CharacterInfoPanel() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut', delay: 0.1 }}
      className="flex flex-col gap-2"
    >
      <CharacterCard />
      <div className="gradient-divider-h relative pb-2" />
      <StatsPanel />
    </motion.div>
  );
}

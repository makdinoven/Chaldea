import { motion } from 'motion/react';
import { useAppSelector } from '../../../redux/store';
import {
  selectAttributes,
  selectProfile,
} from '../../../redux/slices/profileSlice';
import PrimaryStatsSection from './PrimaryStatsSection';
import ResourceStatsSection from './ResourceStatsSection';
import DerivedStatsSection from './DerivedStatsSection';
import StatDistributionPanel from './StatDistributionPanel';

interface StatsTabProps {
  characterId: number;
}

const StatsTab = ({ characterId }: StatsTabProps) => {
  const attributes = useAppSelector(selectAttributes);
  const profile = useAppSelector(selectProfile);

  if (!attributes) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const statPoints = profile?.stat_points ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-8 py-6 px-1"
    >
      {statPoints > 0 && (
        <section className="gray-bg p-5 sm:p-6">
          <StatDistributionPanel
            characterId={characterId}
            statPoints={statPoints}
            attributes={attributes}
          />
        </section>
      )}

      <section className="gray-bg p-5 sm:p-6">
        <PrimaryStatsSection attributes={attributes} />
      </section>

      <section className="gray-bg p-5 sm:p-6">
        <ResourceStatsSection attributes={attributes} />
      </section>

      <section className="gray-bg p-5 sm:p-6">
        <DerivedStatsSection attributes={attributes} />
      </section>
    </motion.div>
  );
};

export default StatsTab;

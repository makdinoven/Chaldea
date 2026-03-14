import { motion } from 'motion/react';

interface PlaceholderTabProps {
  tabName: string;
}

const PlaceholderTab = ({ tabName }: PlaceholderTabProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col items-center justify-center py-32"
    >
      <h2 className="gold-text text-3xl font-medium uppercase mb-4">
        {tabName}
      </h2>
      <p className="text-white/50 text-lg">Скоро...</p>
    </motion.div>
  );
};

export default PlaceholderTab;

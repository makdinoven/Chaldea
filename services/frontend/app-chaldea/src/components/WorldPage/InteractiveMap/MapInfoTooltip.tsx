import { motion } from 'motion/react';

interface MapInfoTooltipProps {
  label: string;
  x: number;
  y: number;
}

const MapInfoTooltip = ({ label, x, y }: MapInfoTooltipProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
      className="site-tooltip gold-outline pointer-events-none absolute z-30 whitespace-nowrap"
      style={{
        left: `${x}%`,
        top: `${y}%`,
        transform: 'translate(-50%, -120%)',
      }}
    >
      {label}
    </motion.div>
  );
};

export default MapInfoTooltip;

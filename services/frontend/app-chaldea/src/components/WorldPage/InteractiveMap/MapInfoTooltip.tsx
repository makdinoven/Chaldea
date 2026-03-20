import { motion } from 'motion/react';

interface MapInfoTooltipProps {
  label: string;
  x: number;
  y: number;
  emblemUrl?: string | null;
}

const MapInfoTooltip = ({ label, x, y, emblemUrl }: MapInfoTooltipProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
      className="site-tooltip gold-outline pointer-events-none absolute z-30 whitespace-nowrap text-center"
      style={{
        left: `${x}%`,
        top: `${y}%`,
        transform: 'translate(-50%, -120%)',
      }}
    >
      {emblemUrl && (
        <div className="flex justify-center mb-1">
          <div className="w-8 h-8 rounded-full overflow-hidden">
            <img
              src={emblemUrl}
              alt=""
              className="w-full h-full object-cover"
            />
          </div>
        </div>
      )}
      {label}
    </motion.div>
  );
};

export default MapInfoTooltip;

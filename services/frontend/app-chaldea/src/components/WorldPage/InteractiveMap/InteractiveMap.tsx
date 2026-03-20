import { motion } from 'motion/react';
import type { ClickableZone } from '../../../redux/actions/worldMapActions';
import ClickableZoneOverlay from './ClickableZoneOverlay';

interface InteractiveMapProps {
  mapImageUrl: string | null;
  clickableZones: ClickableZone[];
  onZoneClick: (zone: ClickableZone) => void;
  title?: string;
  countries?: Array<{ id: number; emblem_url: string | null }>;
}

const InteractiveMap = ({ mapImageUrl, clickableZones, onZoneClick, title, countries }: InteractiveMapProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex-1 min-w-0"
    >
      {title && (
        <h2 className="gold-text text-2xl font-medium uppercase mb-4 text-center">
          {title}
        </h2>
      )}

      <div className="relative w-full min-h-[300px] md:min-h-[500px] rounded-map overflow-hidden bg-site-dark">
        {mapImageUrl ? (
          <>
            <img
              src={mapImageUrl}
              alt={title ?? 'Карта'}
              className="w-full h-full object-cover select-none"
              draggable={false}
            />
            {clickableZones.length > 0 && (
              <ClickableZoneOverlay
                zones={clickableZones}
                onZoneClick={onZoneClick}
                countries={countries}
              />
            )}
          </>
        ) : (
          /* Placeholder for missing map image */
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
            <svg
              className="w-16 h-16 text-white/20"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1}
                d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
              />
            </svg>
            <p className="text-white/40 text-sm">
              Карта ещё не загружена
            </p>
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default InteractiveMap;

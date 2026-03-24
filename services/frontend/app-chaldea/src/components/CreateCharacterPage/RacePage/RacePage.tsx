import { motion, AnimatePresence } from 'motion/react';
import VerticalCarousel from '../VerticalCarousel/VerticalCarousel';
import type { RacePageProps, CarouselItem } from '../types';

export default function RacePage({
  races,
  selectedRaceId,
  onSelectRaceId,
}: RacePageProps) {
  if (!races || races.length === 0) return null;

  const carouselItems: CarouselItem[] = races.map((race) => ({
    id: race.id_race,
    name: race.name,
    image: race.image,
  }));

  const selectedRace = races.find((r) => r.id_race === selectedRaceId);

  return (
    <div className="w-full grid grid-cols-1 md:grid-cols-[220px_1fr] gap-6 px-4 md:px-[60px]">
      {/* Left panel — vertical carousel */}
      <div className="md:order-1 order-2">
        <VerticalCarousel
          items={carouselItems}
          selectedId={selectedRaceId}
          onSelect={onSelectRaceId}
        />
      </div>

      {/* Right panel — description */}
      <div className="md:order-2 order-1">
        <AnimatePresence mode="wait">
          {selectedRace && (
            <motion.div
              key={selectedRace.id_race}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="gray-bg rounded-card p-6 flex flex-col md:flex-row gap-6"
            >
              {/* Race image */}
              {selectedRace.image && (
                <div className="shrink-0 w-full md:w-64 h-64 md:h-80 rounded-card overflow-hidden">
                  <img
                    src={selectedRace.image}
                    alt={selectedRace.name}
                    className="w-full h-full object-cover"
                  />
                </div>
              )}

              {/* Race info */}
              <div className="flex flex-col gap-4 flex-1 min-w-0">
                <h3 className="gold-text text-2xl font-medium uppercase">
                  {selectedRace.name}
                </h3>

                {selectedRace.description && (
                  <p className="text-white text-base font-normal leading-relaxed whitespace-pre-line">
                    {selectedRace.description}
                  </p>
                )}

                {!selectedRace.description && (
                  <p className="text-white/40 text-sm">
                    Описание расы отсутствует
                  </p>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

import { motion, AnimatePresence } from 'motion/react';
import VerticalCarousel from '../VerticalCarousel/VerticalCarousel';
import StatPreviewPanel from './StatPreviewPanel/StatPreviewPanel';
import type { SubracePageProps, CarouselItem } from '../types';

const SubracePage = ({
  selectedRace,
  selectedSubraceId,
  onSelectSubraceId,
}: SubracePageProps) => {
  const carouselItems: CarouselItem[] = selectedRace.subraces.map((s) => ({
    id: s.id_subrace,
    name: s.name,
    image: s.image,
  }));

  const selectedSubrace = selectedRace.subraces.find(
    (s) => s.id_subrace === selectedSubraceId,
  );

  return (
    <div className="w-full grid grid-cols-1 md:grid-cols-[220px_1fr] gap-6 px-4 md:px-[60px]">
      {/* Left panel — vertical carousel */}
      <div className="md:order-1 order-2">
        <VerticalCarousel
          items={carouselItems}
          selectedId={selectedSubraceId ?? carouselItems[0]?.id ?? 0}
          onSelect={onSelectSubraceId}
        />
      </div>

      {/* Right panel — description + stats */}
      <div className="md:order-2 order-1">
        <AnimatePresence mode="wait">
          {selectedSubrace ? (
            <motion.div
              key={selectedSubrace.id_subrace}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="flex flex-col gap-6"
            >
              {/* Description card */}
              <div className="gray-bg rounded-card p-6 flex flex-col md:flex-row gap-6">
                {/* Subrace image */}
                {selectedSubrace.image && (
                  <div className="shrink-0 w-full md:w-64 h-64 md:h-80 rounded-card overflow-hidden">
                    <img
                      src={selectedSubrace.image}
                      alt={selectedSubrace.name}
                      className="w-full h-full object-cover"
                    />
                  </div>
                )}

                {/* Subrace info */}
                <div className="flex flex-col gap-4 flex-1 min-w-0">
                  <h3 className="gold-text text-2xl font-medium uppercase">
                    {selectedSubrace.name}
                  </h3>

                  {selectedSubrace.description && (
                    <p className="text-white text-base font-normal leading-relaxed whitespace-pre-line">
                      {selectedSubrace.description}
                    </p>
                  )}

                  {!selectedSubrace.description && (
                    <p className="text-white/40 text-sm">
                      Описание подрасы отсутствует
                    </p>
                  )}
                </div>
              </div>

              {/* Stat preview panel */}
              <StatPreviewPanel
                statPreset={selectedSubrace.stat_preset}
                subraceName={selectedSubrace.name}
              />
            </motion.div>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="gray-bg rounded-card p-6"
            >
              <p className="text-white/50 text-sm text-center">
                Выберите подрасу для просмотра описания и характеристик
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default SubracePage;

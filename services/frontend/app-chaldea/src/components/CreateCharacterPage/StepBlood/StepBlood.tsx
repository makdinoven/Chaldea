import { useMemo } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import VerticalCarousel from '../VerticalCarousel/VerticalCarousel';
import StatExplainer from './StatExplainer';
import type { CarouselItem, RaceData, StatPreset } from '../types';

/**
 * FEAT-154 (task #17) — step 1, «Кровь».
 *
 * Race and subrace live in ONE panel: picking a race unfolds its subraces right
 * underneath the race blurb, so the player never loses sight of what the race
 * was while choosing the branch of it. Nothing here is hardcoded — races,
 * subraces, presets and images all come from `GET /characters/races`.
 */

interface StepBloodProps {
  races: RaceData[];
  selectedRaceId: number;
  selectedSubraceId: number | null;
  onSelectRace: (raceId: number) => void;
  onSelectSubrace: (subraceId: number) => void;
}

const StepBlood = ({
  races,
  selectedRaceId,
  selectedSubraceId,
  onSelectRace,
  onSelectSubrace,
}: StepBloodProps) => {
  const carouselItems: CarouselItem[] = useMemo(
    () => races.map((race) => ({ id: race.id_race, name: race.name, image: race.image })),
    [races],
  );

  const selectedRace = races.find((race) => race.id_race === selectedRaceId);
  const selectedSubrace = selectedRace?.subraces.find(
    (subrace) => subrace.id_subrace === selectedSubraceId,
  );

  /** Baseline for the «выше/ниже среднего» comparison (rule 7): every subrace in the game. */
  const allPresets = useMemo<StatPreset[]>(
    () =>
      races.flatMap((race) =>
        race.subraces
          .map((subrace) => subrace.stat_preset)
          .filter((preset): preset is StatPreset => Boolean(preset)),
      ),
    [races],
  );

  if (races.length === 0) {
    return (
      <p className="text-white/60 text-sm text-center py-10">
        Список рас пуст. Обратитесь к администрации.
      </p>
    );
  }

  return (
    <div className="w-full grid grid-cols-1 md:grid-cols-[220px_1fr] gap-6 px-4 md:px-[60px]">
      {/* Race rail */}
      <div className="order-2 md:order-1">
        <VerticalCarousel
          items={carouselItems}
          selectedId={selectedRaceId}
          onSelect={onSelectRace}
        />
      </div>

      {/* Race blurb → subraces → stats, all in one column */}
      <div className="order-1 md:order-2 min-w-0">
        <AnimatePresence mode="wait">
          {selectedRace && (
            <motion.div
              key={selectedRace.id_race}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="flex flex-col gap-6"
            >
              {/* Race card — text only: the portrait lives in the subrace card below */}
              <div className="gray-bg rounded-card p-4 sm:p-6 flex flex-col gap-4 min-w-0">
                <h3 className="gold-text text-xl sm:text-2xl font-medium uppercase break-words">
                  {selectedRace.name}
                </h3>

                <p className="text-white text-sm sm:text-base leading-relaxed whitespace-pre-line">
                  {selectedRace.description || 'Описание расы отсутствует.'}
                </p>

                {/* Subraces of THIS race — the same panel, no separate step */}
                <div className="flex flex-col gap-2">
                  <span className="text-white/50 text-xs uppercase tracking-[0.08em]">
                    Ветви крови
                  </span>

                  {selectedRace.subraces.length === 0 ? (
                    <p className="text-white/40 text-sm">
                      У этой расы пока не заведено ни одной подрасы.
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {selectedRace.subraces.map((subrace) => (
                        <button
                          key={subrace.id_subrace}
                          type="button"
                          onClick={() => onSelectSubrace(subrace.id_subrace)}
                          aria-pressed={subrace.id_subrace === selectedSubraceId}
                          className={`chip-outline rounded-full px-3 py-1.5 text-xs sm:text-sm font-medium max-w-full break-words ${
                            subrace.id_subrace === selectedSubraceId
                              ? 'chip-outline-active'
                              : ''
                          }`}
                        >
                          {subrace.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Subrace card */}
              {selectedSubrace ? (
                <motion.div
                  key={selectedSubrace.id_subrace}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                  className="flex flex-col gap-6"
                >
                  <div className="gray-bg rounded-card p-4 sm:p-6 flex flex-col md:flex-row gap-5">
                    {selectedSubrace.image && (
                      <div className="shrink-0 w-full md:w-56 h-56 md:h-72 rounded-card overflow-hidden">
                        <img
                          src={selectedSubrace.image}
                          alt={selectedSubrace.name}
                          className="w-full h-full object-cover"
                        />
                      </div>
                    )}

                    <div className="flex flex-col gap-3 flex-1 min-w-0">
                      <h4 className="gold-text text-lg sm:text-xl font-medium uppercase">
                        {selectedSubrace.name}
                      </h4>

                      <p className="text-white text-sm sm:text-base leading-relaxed whitespace-pre-line">
                        {selectedSubrace.description || 'Описание подрасы отсутствует.'}
                      </p>

                      {selectedSubrace.distinctive_features && (
                        <div className="flex flex-col gap-1">
                          <span className="text-white/50 text-xs uppercase tracking-[0.08em]">
                            Как выглядит
                          </span>
                          <p className="text-white/80 text-sm leading-relaxed whitespace-pre-line">
                            {selectedSubrace.distinctive_features}
                          </p>
                        </div>
                      )}

                      {(selectedSubrace.height_min || selectedSubrace.height_max) && (
                        <p className="text-white/50 text-xs">
                          Обычный рост:{' '}
                          {selectedSubrace.height_min ?? '—'}–{selectedSubrace.height_max ?? '—'} см
                        </p>
                      )}
                    </div>
                  </div>

                  <StatExplainer
                    statPreset={selectedSubrace.stat_preset}
                    subraceName={selectedSubrace.name}
                    allPresets={allPresets}
                  />
                </motion.div>
              ) : (
                <div className="gray-bg rounded-card p-6">
                  <p className="text-white/50 text-sm text-center">
                    Выберите ветвь крови — тогда станут видны характеристики.
                  </p>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default StepBlood;

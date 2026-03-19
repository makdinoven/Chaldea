import { useState, useEffect } from 'react';
import ArrowButton from './ArrowButton/ArrowButton';
import type { RaceData } from '../../types';

interface RaceCarouselProps {
  races: RaceData[];
  onRaceChange: (id: number) => void;
  selectedRaceId: number;
}

export default function RaceCarousel({
  races,
  onRaceChange,
  selectedRaceId,
}: RaceCarouselProps) {
  const [currentRaceId, setCurrentRaceId] = useState(selectedRaceId);
  const [visibleRaces, setVisibleRaces] = useState<RaceData[]>([]);

  useEffect(() => {
    setVisibleRaces(calculateVisibleRaces(currentRaceId));
    onRaceChange?.(currentRaceId);
  }, [currentRaceId, races]);

  const getRaceIndexById = (id: number) => {
    return races.findIndex((race) => race.id_race === id);
  };

  const handlePrev = () => {
    const currentIndex = getRaceIndexById(currentRaceId);
    const prevIndex = (currentIndex - 1 + races.length) % races.length;
    setCurrentRaceId(races[prevIndex].id_race);
  };

  const handleNext = () => {
    const currentIndex = getRaceIndexById(currentRaceId);
    const nextIndex = (currentIndex + 1) % races.length;
    setCurrentRaceId(races[nextIndex].id_race);
  };

  const calculateVisibleRaces = (id: number) => {
    const index = getRaceIndexById(id);
    if (index === -1) return [];

    const total = races.length;
    const prev = (index - 1 + total) % total;
    const next = (index + 1) % total;

    return [races[prev], races[index], races[next]];
  };

  return (
    <div className="z-[1] w-full flex items-center relative">
      {/* Arrow buttons */}
      <div className="z-[2] absolute top-1/2 left-1/2 flex justify-between w-[45%] -translate-x-1/2 -translate-y-1/2">
        <ArrowButton text="&lt;" onClick={handlePrev} />
        <ArrowButton text="&gt;" onClick={handleNext} />
      </div>

      {/* Race images */}
      <div className="overflow-hidden grid grid-cols-3 w-full justify-between mb-[45px]">
        {visibleRaces.map((race, index) => (
          <div
            key={race.id_race}
            className={`self-center justify-self-center transition-all duration-200 ease-site flex rounded-full justify-center items-center w-[180px] h-[180px] sm:w-[220px] sm:h-[220px] md:w-[281px] md:h-[281px] overflow-hidden ${
              index === 1
                ? 'opacity-60'
                : 'opacity-30 scale-[0.6]'
            } ${!race.image ? 'bg-[#878787]' : ''}`}
          >
            {race.image ? (
              <img
                src={race.image}
                alt={race.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-white/50 text-sm uppercase">
                {race.name}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

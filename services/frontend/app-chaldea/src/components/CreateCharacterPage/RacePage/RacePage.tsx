import RaceCarousel from './RaceCarousel/RaceCarousel';
import RaceDescription from './RaceDescription/RaceDescription';
import type { RaceData } from '../types';

interface RacePageProps {
  races: RaceData[];
  onSelectRaceId: (id: number) => void;
  onSelectSubraceId: (id: number) => void;
  selectedRaceId: number;
  selectedSubraceId: number | null;
}

export default function RacePage({
  races,
  onSelectRaceId,
  onSelectSubraceId,
  selectedRaceId,
  selectedSubraceId,
}: RacePageProps) {
  if (!races || races.length === 0) return null;

  const selectedRace = races.find((race) => race.id_race === selectedRaceId);

  return (
    <>
      <RaceCarousel
        races={races}
        onRaceChange={(id) => onSelectRaceId(id)}
        selectedRaceId={selectedRaceId}
      />
      {selectedRace && (
        <RaceDescription
          raceData={selectedRace}
          onSubraceChange={(id) => onSelectSubraceId(id)}
          selectedSubraceId={selectedSubraceId}
        />
      )}
    </>
  );
}

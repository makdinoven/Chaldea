import { useState, useEffect } from 'react';
import RaceCarousel from './RaceCarousel/RaceCarousel';
import RaceDescription from './RaceDescription/RaceDescription';

export default function RacePage({
  races,
  onSelectRaceId,
  onSelectSubraceId,
  selectedRaceId,
  selectedSubraceId,
}) {
  const [currentRaceId, setCurrentRaceId] = useState(selectedRaceId);
  const [currentSubraceId, setCurrentSubraceId] = useState(selectedSubraceId);

  // console.log(races);

  const handleRaceChange = (id) => {
    setCurrentRaceId(id);
    onSelectRaceId(id);
  };

  const handleSubraceChange = (id) => {
    setCurrentSubraceId(id);
    onSelectSubraceId(id);
  };

  return (
    <>
      <RaceCarousel
        races={races}
        onRaceChange={handleRaceChange}
        selectedRace={currentRaceId}
      />
      <RaceDescription
        raceData={races[currentRaceId]}
        onSubraceChange={handleSubraceChange}
        selectedSubraceId={currentSubraceId}
      />
    </>
  );
}

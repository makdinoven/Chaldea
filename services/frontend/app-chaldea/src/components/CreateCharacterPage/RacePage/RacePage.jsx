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

  // useEffect(() => {
  //   setCurrentRaceId(selectedRaceId);
  // }, [selectedRaceId]);

  // useEffect(() => {
  //   setCurrentSubraceId(selectedSubraceId);
  // }, [selectedSubraceId]);

  // useEffect(() => {
  //   console.log('RacePage rendered');
  // }, []);

  // useEffect(() => {
  //   console.log(
  //     'Раса:',
  //     races[currentRaceId].raceName,

  //     'Подраса:',
  //     races[currentRaceId].subraces[currentSubraceId].subraceName
  //   );
  // }, [currentRaceId, currentSubraceId]);

  // useEffect(() => {
  //   // Сброс индекса подрасы на 0 при изменении расы
  //   setCurrentSubraceId(0);
  // }, [currentRaceId]);

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

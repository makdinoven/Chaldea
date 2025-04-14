import {useState, useEffect} from 'react';
import RaceCarousel from './RaceCarousel/RaceCarousel';
import RaceDescription from './RaceDescription/RaceDescription';

export default function RacePage({
                                     races,
                                     onSelectRaceId,
                                     onSelectSubraceId,
                                     selectedRaceId,
                                     selectedSubraceId,
                                 }) {
    return (
        races &&
        <>
            <RaceCarousel
                races={races}
                onRaceChange={(id) => onSelectRaceId(id)}
                selectedRaceId={selectedRaceId}
            />
            <RaceDescription
                raceData={races.find(race => race.id_race === selectedRaceId)}
                onSubraceChange={(id) => onSelectSubraceId(id)}
                selectedSubraceId={selectedSubraceId}
            />
        </>
    );
}

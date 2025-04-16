import {useState, useEffect} from 'react';
import ArrowButton from './ArrowButton/ArrowButton';
import styles from './RaceCarousel.module.scss';

export default function RaceCarousel({races, onRaceChange, selectedRaceId}) {
    const [currentRaceId, setCurrentRaceId] = useState(selectedRaceId);
    const [visibleRaces, setVisibleRaces] = useState([]);

    useEffect(() => {
        setVisibleRaces(calculateVisibleRaces(currentRaceId));
        onRaceChange?.(currentRaceId);
    }, [currentRaceId, races]);

    const getRaceIndexById = (id) => {
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

    const calculateVisibleRaces = (id) => {
        const index = getRaceIndexById(id);
        if (index === -1) return [];

        const total = races.length;
        const prev = (index - 1 + total) % total;
        const next = (index + 1) % total;

        return [races[prev], races[index], races[next]];
    };

    return (
        <div className={styles.carousel}>
            <div className={styles.buttons_container}>
                <ArrowButton text='&lt;' onClick={handlePrev}/>
                <ArrowButton text='&gt;' onClick={handleNext}/>
            </div>

            <div className={styles.images_container}>
                {visibleRaces.map((race, index) => (
                    <div
                        key={race.id_race}
                        className={`${styles.race_img} ${index === 1 ? styles.active : ''}`}
                    >
                        <img src={race.raceImg} alt={`Race ${race.id_race}`}/>
                    </div>
                ))}
            </div>
        </div>
    );
}

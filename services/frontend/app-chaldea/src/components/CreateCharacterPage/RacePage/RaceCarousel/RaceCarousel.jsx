import { useState, useEffect } from 'react';
import ArrowButton from './ArrowButton/ArrowButton';
import styles from './RaceCarousel.module.css';

export default function RaceCarousel({ races, onRaceChange, selectedRace }) {
  const [currentIndex, setCurrentIndex] = useState(selectedRace);
  const [visibleImages, setVisibleImages] = useState([]);

  // useEffect(() => {
  //   console.log('RaceId changed');
  // }, [currentIndex]);

  useEffect(() => {
    setVisibleImages(calculateVisibleImages(currentIndex));
    // console.log(currentIndex);
    if (onRaceChange) {
      onRaceChange(currentIndex);
    }
  }, [currentIndex, races]);

  const handlePrev = () => {
    setCurrentIndex((prevIndex) =>
      prevIndex === 0 ? races.length - 1 : prevIndex - 1
    );
  };

  const handleNext = () => {
    setCurrentIndex((prevIndex) =>
      prevIndex === races.length - 1 ? 0 : prevIndex + 1
    );
  };

  const calculateVisibleImages = (index) => {
    const totalImages = races.length;
    const prevIndex = (index - 1 + totalImages) % totalImages;
    const nextIndex = (index + 1) % totalImages;

    return [
      races[prevIndex].raceImg,
      races[index].raceImg,
      races[nextIndex].raceImg,
    ];
  };

  return (
    <div className={styles.carousel}>
      <div className={styles.buttons_container}>
        <ArrowButton
          disabled={currentIndex === 0}
          text='&lt;'
          onClick={handlePrev}
        />
        <ArrowButton
          disabled={currentIndex === races.length - 1}
          text='&gt;'
          onClick={handleNext}
        />
      </div>

      <div className={styles.images_container}>
        {visibleImages.map((img, index) => (
          <img
            className={`${styles.race_img} ${index === 1 ? styles.active : ''}`}
            key={index}
            src={img}
            alt={`Image ${index}`}
          />
        ))}
      </div>
    </div>
  );
}

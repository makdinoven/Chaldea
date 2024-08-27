import React, { useState } from 'react';
import SliderCircleButton from './SliderCircleButton/SliderCircleButton';
import SliderArrowButton from './SliderArrowButton/SliderArrowButton';
import styles from './Slider.module.css';

export default function Slider({ pages }) {
  const [currentIndex, setCurrentIndex] = useState(0);

  const handlePrev = (e) => {
    e.stopPropagation();

    setCurrentIndex((prevIndex) =>
      prevIndex === 0 ? pages.length - 1 : prevIndex - 1
    );
  };

  const handleNext = (e) => {
    e.stopPropagation();

    setCurrentIndex((prevIndex) =>
      prevIndex === pages.length - 1 ? 0 : prevIndex + 1
    );
  };

  const handleCircleClick = (index, e) => {
    e.stopPropagation();

    setCurrentIndex(index);
  };

  return (
    <div className={styles.container}>
      <div
        className={styles.page}
        style={{
          background: `url(${pages[currentIndex].img})`,
        }}
        onClick={() => {
          console.log('click page');
          window.location.href = pages[currentIndex].link;
        }}
      >
        <div className={styles.top_container}>
          <div className={styles.pagination_container}>
            <SliderArrowButton text='<' onClick={handlePrev} />
            <div className={styles.circle_buttons_container}>
              {pages.map((_, index) => (
                <SliderCircleButton
                  key={index}
                  isActive={index === currentIndex}
                  onClick={(e) => handleCircleClick(index, e)}
                />
              ))}
            </div>
            <SliderArrowButton text='>' onClick={handleNext} />
          </div>
          <span className={styles.tag}>{pages[currentIndex].tag}</span>
        </div>
        <div className={styles.text_container}>
          <h2 className={styles.title}>{pages[currentIndex].title}</h2>
          <p className={styles.description}>
            {pages[currentIndex].description}
          </p>
        </div>
      </div>
    </div>
  );
}

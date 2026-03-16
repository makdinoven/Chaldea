import { useState } from 'react';

import CircleButton from '../../HomePage/Slider/CircleButton/CircleButton';
import PaginationButton from './PaginationButton/PaginationButton';

import styles from './Pagination.module.scss';

export default function Pagination({ pages, currentIndex, onIndexChange }) {
  const handlePrev = () => {
    onIndexChange(currentIndex === 0 ? 0 : currentIndex - 1);
  };

  const handleNext = () => {
    onIndexChange(
      currentIndex === pages.length - 1 ? currentIndex : currentIndex + 1
    );
  };

  const handleCircleClick = (index) => {
    onIndexChange(index);
  };

  return (
    <div className={styles.pagination_container}>
      <PaginationButton
        isDisabled={currentIndex === 0}
        text='Назад'
        onClick={handlePrev}
      />

      <div className={styles.circle_buttons_container}>
        {pages.map((_, index) => (
          <CircleButton
            key={index}
            isActive={index === currentIndex}
            onClick={() => handleCircleClick(index)}
          />
        ))}
      </div>

      <PaginationButton
        isDisabled={currentIndex === pages.length - 1}
        text='Вперед'
        onClick={handleNext}
      />
    </div>
  );
}

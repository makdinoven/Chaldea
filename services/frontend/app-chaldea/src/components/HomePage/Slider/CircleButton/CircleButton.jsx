import styles from './CircleButton.module.css';

export default function SliderCircleButton({ isActive, onClick }) {
  const handleClick = (e) => {
    e.stopPropagation(); // Остановить распространение клика
    if (onClick) onClick(e); // Передаем объект события в обработчик
  };

  return (
    <button
      onClick={handleClick}
      className={`${styles.button} ${
        isActive ? styles.active : styles.inactive
      }`}
    ></button>
  );
}

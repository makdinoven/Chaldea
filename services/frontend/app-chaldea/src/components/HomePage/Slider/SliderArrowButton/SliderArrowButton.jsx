import styles from './SliderArrowButton.module.css';

export default function SliderArrowButton({ text, onClick }) {
  const handleClick = (e) => {
    e.stopPropagation();
    if (onClick) onClick(e);
  };

  return (
    <button onClick={handleClick} className={styles.button}>
      {text}
    </button>
  );
}

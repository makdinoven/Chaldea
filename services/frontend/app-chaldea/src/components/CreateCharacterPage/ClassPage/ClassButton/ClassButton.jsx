import styles from './ClassButton.module.css';

export default function ClassButton({
  text,
  index,
  currentIndex,
  setCurrentIndex,
}) {
  function handleClick() {
    setCurrentIndex(index);
  }

  return (
    <button
      onClick={handleClick}
      className={`${styles.btn} ${
        currentIndex === index ? styles.active : styles.inactive
      }`}
    >
      {text}
    </button>
  );
}

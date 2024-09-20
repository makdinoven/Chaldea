import styles from './SubraceButton.module.css';

export default function SubraceButton({
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
      className={currentIndex === index ? styles.active : styles.inactive}
    >
      {text}
    </button>
  );
}

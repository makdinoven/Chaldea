import styles from './ArrowButton.module.css';

export default function ArrowButton({ text, onClick }) {
  const handleClick = (e) => {
    e.stopPropagation();
    onClick(e);
  };

  return (
    <button data-text={text} onClick={handleClick} className={styles.button}>
      {text}
    </button>
  );
}

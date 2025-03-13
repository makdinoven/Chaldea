import styles from './ArrowButton.module.scss';

export default function ArrowButton({ text, onClick }) {
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

import styles from './ArrowButton.module.css';

export default function ArrowButton({ text, onClick, disabled }) {
  const handleClick = (e) => {
    e.stopPropagation();
    if (!disabled && onClick) {
      onClick(e);
    }
  };

  return (
    <button
      onClick={handleClick}
      className={`${styles.button} ${disabled ? styles.inactive : ''}`}
    >
      {text}
    </button>
  );
}

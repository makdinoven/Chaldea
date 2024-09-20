import styles from './PaginationButton.module.css';

export default function PaginationButton({ text, isDisabled, onClick }) {
  return (
    <button
      className={`${styles.button} ${
        isDisabled ? styles.disabled : styles.active
      }`}
      onClick={onClick}
    >
      {text}
    </button>
  );
}

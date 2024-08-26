import styles from './SmallHomePageButton.module.css';

export default function SmallHomePageButton({ title, backgroundImg }) {
  const additionalStyles = {
    backgroundImage: `url(${backgroundImg})`,
  };

  return (
    <button className={styles.button} style={additionalStyles}>
      <span className={styles.title}>{title}</span>
    </button>
  );
}

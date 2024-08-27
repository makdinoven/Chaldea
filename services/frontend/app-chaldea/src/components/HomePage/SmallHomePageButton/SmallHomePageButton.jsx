import styles from './SmallHomePageButton.module.css';

export default function SmallHomePageButton({ title, backgroundImg, link }) {
  const additionalStyles = {
    backgroundImage: `url(${backgroundImg})`,
  };

  return (
    <a href={link} className={styles.button} style={additionalStyles}>
      <span className={styles.title}>{title}</span>
    </a>
  );
}

import styles from './CharacterInfoSmall.module.css';

export default function CharacterInfoSmall({ text }) {
  return (
    <div className={styles.info_container}>
      <p className={styles.title}>{text}</p>
    </div>
  );
}

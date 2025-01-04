import styles from './CharacterInfo.module.scss';

export default function CharacterInfo({ title, text }) {
  return (
    <div className={styles.info_container}>
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.text}>{text}</p>
    </div>
  );
}

import styles from './UserAvatar.module.scss';

export default function UserAvatar({ img, name }) {
  return (
    <div
      style={{ backgroundImage: `url(${img})` }}
      className={styles.user_avatar}
    >
      <div className={styles.name_container}>
        <span>{name}</span>
      </div>
    </div>
  );
}

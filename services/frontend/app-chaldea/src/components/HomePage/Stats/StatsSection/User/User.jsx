import styles from './User.module.css';

export default function User({ data }) {
  return (
    <div className={styles.user_wrapper}>
      <img src={data.avatar} alt='user avatar' />
      <div className={styles.name_points_wrapper}>
        <div className={styles.user_name}> {data.name}</div>
        <div className={styles.user_points}>{data.points}</div>
      </div>
    </div>
  );
}

import User from './User/User';

import styles from './StatsSection.module.css';

export default function StatsSection({ data }) {
  return (
    <div className={styles.section}>
      <h3 className={styles.section_title}>{data.sectionName}</h3>
      <div className={styles.user_container}>
        {data.users.map((user, index) => (
          <User key={index} data={user} />
        ))}
      </div>
    </div>
  );
}

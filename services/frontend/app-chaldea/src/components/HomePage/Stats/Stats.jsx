import StatsSection from './StatsSection/StatsSection';

import styles from './Stats.module.scss';

export default function Stats({ statsData }) {
  return (
    <div className={styles.stats_container}>
      <div
        style={{ backgroundImage: `url(${statsData.img})` }}
        className={styles.top_container}
      >
        <h2 className={styles.stats_title}>{statsData.title}</h2>
      </div>
      <div className={styles.sections_container}>
        {statsData.sections.map((sectionData, index) => (
          <StatsSection key={index} data={sectionData} />
        ))}
      </div>
    </div>
  );
}

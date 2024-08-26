import styles from './HomePageButton.module.css';

export default function HomePageButton({ title, links, backgroundImg }) {
  const additionalStyles = {
    backgroundImage: `url(${backgroundImg})`,
  };

  return (
    <button className={styles.container} style={additionalStyles}>
      <div className={styles.button}>
        <h3 className={styles.title}>{title}</h3>

        <div className={styles.links}>
          {links.map((item, index) => (
            <a key={index} className={styles.link} href={item.link}>
              {item.name}
            </a>
          ))}
        </div>
      </div>
    </button>
  );
}

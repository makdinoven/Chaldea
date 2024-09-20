import styles from './HomePageButton.module.css';

export default function HomePageButton({
  titleName,
  titleLink,
  links,
  backgroundImg,
}) {
  const additionalStyles = {
    backgroundImage: `url(${backgroundImg})`,
  };

  return (
    <button
      className={styles.container}
      style={additionalStyles}
      onClick={() => {
        window.location.href = titleLink;
      }}
    >
      <div className={styles.button}>
        <h3 className={styles.title}>{titleName}</h3>

        <div className={styles.links_container}>
          {links.map((link, index) => (
            <a
              key={index}
              className={styles.link}
              href={link.link}
              onClick={(e) => e.stopPropagation()}
            >
              {link.name}
            </a>
          ))}
        </div>
      </div>
    </button>
  );
}

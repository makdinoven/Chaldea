import useNavigateTo from '../../../hooks/useNavigateTo';

import styles from './Button.module.css';

export default function Button({ data }) {
  const navigateTo = useNavigateTo();

  const additionalStyles = {
    backgroundImage: `url(${data.img})`,
  };

  if (data.type === 'small') {
    return (
      <button
        onClick={() => navigateTo(data.titleLink)}
        className={styles.small_button}
        style={additionalStyles}
      >
        <span className={styles.small_button_title}>{data.titleName}</span>
      </button>
    );
  }

  return (
    <div
      className={styles.container}
      style={additionalStyles}
      onClick={() => navigateTo(data.titleLink)}
    >
      <div className={styles.button}>
        <h3 className={styles.title}>{data.titleName}</h3>

        <div className={styles.bottom_buttons_container}>
          {data.links.map((link, index) => (
            <button
              key={index}
              className={styles.bottom_button}
              onClick={(e) => {
                e.stopPropagation();
                navigateTo(link.link);
              }}
            >
              {link.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

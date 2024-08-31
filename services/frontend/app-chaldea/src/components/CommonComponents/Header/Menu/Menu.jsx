import useNavigateTo from '../../../../hooks/useNavigateTo';

import styles from './Menu.module.css';

export default function Menu({ title, backgroundImg, menuButtons }) {
  const navigateTo = useNavigateTo();

  const additionalStyles = {
    backgroundImage: `url(${backgroundImg})`,
    gridTemplateRows: `repeat(${menuButtons.length}, 1fr)`,
  };

  return (
    <div className={styles.container}>
      <div className={styles.menu} style={additionalStyles}>
        <div className={styles.menu_items}>
          {menuButtons.map((button, index) => (
            <button
              key={index}
              className={styles.menu_item}
              onClick={() => navigateTo(button.link)}
            >
              {button.name}
            </button>
          ))}
        </div>
      </div>
      <span className={styles.title}>{title}</span>
    </div>
  );
}

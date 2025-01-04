import styles from './Menu.module.scss';
import {Link} from "react-router-dom";

export default function Menu({ title, backgroundImg, menuButtons }) {

  const additionalStyles = {
    backgroundImage: `url(${backgroundImg})`,
    gridTemplateRows: `repeat(${menuButtons.length}, 1fr)`,
  };

  return (
    <div className={styles.container}>
      <div className={styles.menu} style={additionalStyles}>
        <div className={styles.menu_items}>
          {menuButtons.map((button, index) => (
            <Link to={button.link} key={index} className={styles.menu_item}
            >
              {button.name}
            </Link>
          ))}
        </div>
      </div>
      <span className={styles.title}>{title}</span>
    </div>
  );
}

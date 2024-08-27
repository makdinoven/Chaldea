import styles from './Menu.module.css';

export default function Menu({ title, backgroundImg, menuItems }) {
  const additionalStyles = {
    backgroundImage: `url(${backgroundImg})`,
    gridTemplateRows: `repeat(${menuItems.length}, 1fr)`,
  };

  return (
    <div className={styles.container}>
      <div className={styles.menu} style={additionalStyles}>
        <div className={styles.menu_items}>
          {menuItems.map((item, index) => (
            <a key={index} className={styles.menu_item} href={item.link}>
              {item.name}
            </a>
          ))}
        </div>
      </div>
      <span className={styles.title}>{title}</span>
    </div>
  );
}

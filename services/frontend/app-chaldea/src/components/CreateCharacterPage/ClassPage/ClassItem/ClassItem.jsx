import useNavigateTo from '../../../../hooks/useNavigateTo';

import styles from './ClassItem.module.css';

export default function ClassItem({
  onClick,
  data,
  index,
  currentIndex,
  setCurrentIndex,
}) {
  const navigateTo = useNavigateTo();

  function handleClick() {
    setCurrentIndex(index);
    onClick(); // Добавлено вызов функции onClick
  }

  console.log(data);

  // Условное присвоение класса
  const itemClass = currentIndex === index ? styles.active : styles.inactive;

  return (
    <div onClick={handleClick} className={`${styles.class_item} ${itemClass}`}>
      <h3 className={styles.class_title}>{data.name}</h3>
      <img className={styles.class_img} src={data.img} alt='class image' />
      <div className={styles.class_item_section}>
        <h4 className={styles.section_title}>Особенности</h4>
        <p className={styles.features}>{data.features}</p>
      </div>
      <div className={styles.class_item_section}>
        <h4 className={styles.section_title}>
          Инвентарь{' '}
          <a
            className={styles.question_mark}
            onClick={() => navigateTo('/rules')}
          ></a>
        </h4>

        <div className={styles.section_images}>
          {data.inventory.map((item) => (
            <img
              key={item.name}
              src={item.img}
              onClick={() => navigateTo(item.link)}
              alt={item.name}
            ></img>
          ))}
        </div>
      </div>
      <div className={styles.class_item_section}>
        <h4 className={styles.section_title}>
          Навыки
          <a
            className={styles.question_mark}
            onClick={() => navigateTo('/rules')}
          ></a>
        </h4>

        <div className={styles.section_images}>
          {data.skills.map((item) => (
            <img
              width={50}
              height={50}
              key={item.name}
              src={item.img}
              onClick={() => navigateTo(item.link)}
              alt={item.name}
            ></img>
          ))}
        </div>
      </div>
    </div>
  );
}

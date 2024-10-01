import UserAvatar from '../../CommonComponents/UserAvatar/UserAvatar';
import CharacterInfo from '../../CreateCharacterPage/SubmitPage/CharacterInfo/CharacterInfo';

import styles from './Request.module.css';

export default function Request({ data }) {
  const biographyItems = [
    { title: 'Биография', text: 'Биография' },
    { title: 'Личность', text: 'Личность' },
    { title: 'Внешность', text: 'Внешность' },
  ];
  return (
    <div className={styles.request}>
      <div className={styles.left}>
        <UserAvatar img={data.img} name={data.name} />
      </div>
      <div className={styles.center}>
        {biographyItems.map((item, index) => (
          <CharacterInfo key={index} title={item.title} text={item.text} />
        ))}
      </div>
      <div className={styles.right}>кнопки</div>
    </div>
  );
}

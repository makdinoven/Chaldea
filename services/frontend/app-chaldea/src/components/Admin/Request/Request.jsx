import UserAvatar from '../../CommonComponents/UserAvatar/UserAvatar';
import CharacterInfo from '../../CreateCharacterPage/SubmitPage/CharacterInfo/CharacterInfo';

import styles from './Request.module.css';
import RequestButton from './RequestButton/RequestButton';

export default function Request({ data }) {
  console.log(data);
  const biographyItems = [
    { title: 'Биография', text: 'Биография' },
    { title: 'Личность', text: 'Личность' },
    { title: 'Внешность', text: 'Внешность' },
  ];

  const buttons = [
    { type: 'confirm', text: 'Одобрить' },
    { type: 'cancel', text: 'Отклонить' },
    { type: 'open', text: 'Просмотреть' },
  ];

  const handleButtonClick = (type) => {
    console.log('click', type);
  };

  return (
    <div className={styles.request}>
      <div className={styles.left}>
        <UserAvatar img={data.avatar} name={data.name} />
      </div>
      <div className={styles.center}>
        {biographyItems.map((item, index) => (
          <CharacterInfo key={index} title={item.title} text={item.text} />
        ))}
      </div>
      <div className={styles.right}>
        {buttons.map((button) => (
          <RequestButton
            key={button.type}
            text={button.text}
            onClick={() => handleButtonClick(button.type)}
          />
        ))}
      </div>
    </div>
  );
}

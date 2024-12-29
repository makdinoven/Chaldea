import UserAvatar from '../../CommonComponents/UserAvatar/UserAvatar';
import CharacterInfo from '../../CreateCharacterPage/SubmitPage/CharacterInfo/CharacterInfo';
import axios from 'axios';
import styles from './Request.module.css';
import RequestButton from './RequestButton/RequestButton';
import CharacterInfoSmall from "../../CreateCharacterPage/SubmitPage/CharacterInfoSmall/CharacterInfoSmall.jsx";

export default function Request({ data }) {
  // console.log(data);
  const biographyItems = [
    { title: 'Биография', text: data.biography },
    { title: 'Личность', text: data.background },
    { title: 'Внешность', text: data.appearance },
  ];

  const buttons = [
    { type: 'confirm', text: 'Одобрить' },
    { type: 'cancel', text: 'Отклонить' },
    // { type: 'open', text: 'Просмотреть' },
  ];

    const characterItemsSmall = [
        {
            text: `${data.race_name} - ${data.subrace_name}`,
        },
        { text: data.class_name },
        { text: data.age ? `Возраст : ${data.age}` : null },
        { text: data.height ? `Рост : ${data.height}` : null },
        { text: data.sex ? `Пол : ${data.sex}` : null },
        { text: data.background || null },
    ];

  const handleButtonClick = (type) => {
    if (type === 'confirm') {
        console.log(data);
        axios.post(`/characters/requests/${data.request_id}/approve`).then((res) => {
            console.log(res);
        })
    }
    if (type === 'cancel') {
        console.log(data);
        axios.post(`/characters/requests/${data.request_id}/reject`).then((res) => {
            console.log(res);
        })
    }
  };

  return (
    <div className={styles.request}>
        <div className={styles.left}>
            <UserAvatar img={data.avatar} name={data.name}/>
            <div className={styles.smallInfo_container}>
                {characterItemsSmall.map(
                    (item, index) =>
                        item.text && (
                            <CharacterInfoSmall
                                key={index}
                                title={item.title}
                                text={item.text}
                            />
                        )
                )}
            </div>
        </div>
        <div className={styles.center}>
            {biographyItems.map((item, index) => (
                <CharacterInfo key={index} title={item.title} text={item.text}/>
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

import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

import FormButton from '../../CommonComponents/BlueGradientButton/BlueGradientButton';
import CharacterInfo from './CharacterInfo/CharacterInfo';
import CharacterInfoSmall from './CharacterInfoSmall/CharacterInfoSmall';

import styles from './SubmitPage.module.css';

export default function SubmitPage({
  biography,
  selectedRace,
  selectedSubrace,
  selectedClass,
}) {
  const fileInputRef = useRef(null);
  const [avatarUrl, setAvatarUrl] = useState('');

  const handlePhotoInputClick = () => {
    fileInputRef.current.click();
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    console.log('Selected Race:', selectedRace);
    console.log('Selected Subrace:', selectedSubrace);
    console.log('Selected Class:', selectedClass);
    console.log('Form:', biography);
  };

  const biographyItems = [
    { title: 'Биография', text: biography.biography },
    { title: 'Личность', text: biography.personality },
    { title: 'Внешность', text: biography.appearance },
  ];

  const sendPhoto = () => {
    const file = fileInputRef.current.files[0];
    const user_id = 1; // Идентификатор пользователя

    if (!file) {
      console.log('Файл не выбран');
      return;
    }

    const formData = new FormData();
    formData.append('file', file); // 'file' — это ключ для файла, как ожидается сервером
    formData.append('user_id', user_id); // Передаем также user_id отдельно

    axios
      .post('/photo/upload-photo_user_avatar', formData, {
        headers: {
          'Content-Type': 'multipart/form-data', // Указывает, что передаём данные формы
        },
      })
      .then((response) => {
        const { avatar_url } = response.data; // Получаем URL аватара из ответа
        setAvatarUrl(avatar_url); // Сохраняем его в состоянии
        console.log('Фото загружено успешно:', avatar_url);
      })
      .catch((error) => {
        console.error('Ошибка загрузки фото:', error);
      });
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      sendPhoto(file); // Отправляем фото сразу после выбора
    }
  };

  const characterItemsSmall = [
    { text: `${selectedRace} - ${selectedSubrace}` },
    { text: selectedClass },
    { text: `Возраст : ${biography.age}` },
    { text: `Рост : ${biography.height}` },
    { text: `Пол : ${biography.sex}` },
    { text: biography.origin },
  ];

  return (
    <>
      <div className={styles.submit_container}>
        <div className={styles.left}>
          <div
            // style={{ backgroundImage: url('../../../assets/menu2.png') }}
            className={styles.custom_file_upload}
            onClick={handlePhotoInputClick}
            style={{
              backgroundImage: `url(${avatarUrl})`,
            }}
          >
            <div className={styles.character_name_container}>
              <span className={styles.character_name}>{biography.name}</span>
            </div>
            <label htmlFor='fileInput'>Сменить аватар</label>
            <input
              onChange={handleFileChange}
              ref={fileInputRef}
              type='file'
              id='fileInput'
              accept='image/*'
            />
          </div>

          <div className={styles.smallInfo_container}>
            {characterItemsSmall.map((item, index) => (
              <CharacterInfoSmall
                key={index}
                title={item.title}
                text={item.text}
              />
            ))}
          </div>
        </div>
        <div className={styles.right}>
          {biographyItems.map((item, index) => (
            <CharacterInfo key={index} title={item.title} text={item.text} />
          ))}
        </div>
      </div>
      <div className={styles.button_container}>
        <FormButton text='Отправить анкету' onClick={handleSubmit} />
      </div>
    </>
  );
}

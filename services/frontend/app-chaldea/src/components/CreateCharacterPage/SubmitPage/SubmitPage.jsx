import { useState, useEffect, useRef } from 'react';

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
            className={styles.custom_file_upload}
            onClick={handlePhotoInputClick}
          >
            <div className={styles.character_name_container}>
              <span className={styles.character_name}>{biography.name}</span>
            </div>
            <label htmlFor='fileInput'>Сменить аватар</label>
            <input
              style={{ display: 'none' }}
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

import {useState, useEffect, useRef} from 'react';
import axios from 'axios';
import useNavigateTo from '../../../hooks/useNavigateTo';

import FormButton from '../../CommonComponents/BlueGradientButton/BlueGradientButton';
import CharacterInfo from './CharacterInfo/CharacterInfo';
import CharacterInfoSmall from './CharacterInfoSmall/CharacterInfoSmall';

import styles from './SubmitPage.module.scss';

import defaultAvatar from '../../../assets/menu2.png';
import {useUser} from "../../../hooks/UserContext.jsx";

export default function SubmitPage({
                                       biography,
                                       selectedRace,
                                       selectedRaceId,
                                       selectedSubrace,
                                       selectedSubraceId,
                                       selectedClass,
                                       selectedClassId,
                                   }) {
    const {user, setUser} = useUser();
    const navigateTo = useNavigateTo();
    const fileInputRef = useRef(null);
    const [avatarUrl, setAvatarUrl] = useState(defaultAvatar);

    const handlePhotoInputClick = () => {
        fileInputRef.current.click();
    };

    const handleSubmit = (e) => {
        e.preventDefault();

        const data = {
            ...biography,
            user_id: user.id,
            avatar: 'string',
            id_subrace: selectedSubraceId,
            id_class: selectedClassId,
            id_race: selectedRaceId,
        };

        console.log(data);

        axios
            .post('http://4452515-co41851.twc1.net:8005/characters/requests/', data)
            .then((response) => {
                response.status === 200 ? navigateTo('/home') : console.log(response);
            })
            .catch((error) => {
                console.error('Ошибка', error);
            });
    };

    const sendPhoto = () => {
        const file = fileInputRef.current.files[0];
        const user_id = 1;

        if (!file) {
            console.log('Файл не выбран');
            return;
        }

        const formData = new FormData();
        formData.append('file', file); // 'file' — это ключ для файла, как ожидается сервером
        formData.append('user_id', user_id); // Передаем также user_id отдельно

        axios
            .post('/photo/character_avatar_preview', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data', // Указывает, что передаём данные формы
                },
            })
            .then((response) => {
                const {avatar_url} = response.data; // Получаем URL аватара из ответа
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
            sendPhoto(file);
        }
    };

    const biographyItems = [
        {title: 'Биография', text: biography.biography},
        {title: 'Личность', text: biography.personality},
        {title: 'Внешность', text: biography.appearance},
    ];

    const characterItemsSmall = [
        {
            text: `${selectedRace} - ${selectedSubrace}`,
        },
        {text: selectedClass},
        {text: biography.age ? `Возраст : ${biography.age}` : null},
        {text: biography.height ? `Рост : ${biography.height}` : null},
        {text: biography.sex ? `Пол : ${biography.sex}` : null},
        {text: biography.background || null},
    ];

    return (
        <>
            <div className={styles.submit_container}>
                <div className={styles.left}>
                    <div
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
                            style={{display: 'none'}}
                            onChange={handleFileChange}
                            ref={fileInputRef}
                            type='file'
                            id='fileInput'
                            accept='image/*'
                        />
                    </div>

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
                <div className={styles.right}>
                    {biographyItems.map((item, index) => (
                        <CharacterInfo key={index} title={item.title} text={item.text}/>
                    ))}
                </div>
            </div>
            <div className={styles.button_container}>
                <FormButton text='Отправить анкету' onClick={handleSubmit}/>
            </div>
        </>
    );
}

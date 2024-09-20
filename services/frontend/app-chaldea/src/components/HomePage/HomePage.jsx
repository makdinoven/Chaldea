import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

import Header from '../CommonComponents/Header/Header';
import HomePageButton from './HomePageButton/HomePageButton';
import SmallHomePageButton from './SmallHomePageButton/SmallHomePageButton';
import Slider from './Slider/Slider';

import styles from './HomePage.module.css';

import button1img from '../../assets/homepagebutton1.png';
import button2img from '../../assets/homepagebutton2.png';
import button3img from '../../assets/homepagebutton3.png';
import smallbuttonimg1 from '../../assets/smallhomebutton1.png';
import smallbuttonimg2 from '../../assets/smallhomebutton2.png';
import smallbuttonimg3 from '../../assets/smallhomebutton3.png';
import smallbuttonimg4 from '../../assets/smallhomebutton4.png';
import sliderImg1 from '../../assets/sliderimg1.png';

export default function HomePage() {
  // const [user, setUser] = useState(null); // Состояние для хранения информации о пользователе
  // const [selectedFile, setSelectedFile] = useState(null); // Состояние для хранения выбранного файла
  // const [message, setMessage] = useState(''); // Состояние для сообщений об успехе или ошибке
  // const navigate = useNavigate();

  // useEffect(() => {
  //   const fetchUserData = async () => {
  //     const token = localStorage.getItem('accessToken'); // Получаем токен из локального хранилища
  //     if (!token) {
  //       navigate('/'); // Перенаправляем на страницу входа, если токен отсутствует
  //       return;
  //     }

  //     try {
  //       // Отправляем запрос на сервер для получения данных текущего пользователя
  //       const response = await axios.get('/api/users/me', {
  //         headers: {
  //           Authorization: `Bearer ${token}`, // Передаем токен в заголовках запроса
  //         },
  //       });
  //       setUser(response.data); // Сохраняем данные пользователя в состоянии
  //     } catch (error) {
  //       console.error('Failed to fetch user data:', error);
  //       localStorage.removeItem('accessToken'); // Удаляем токен в случае ошибки
  //       navigate('/'); // Перенаправляем на страницу входа
  //     }
  //   };

  //   fetchUserData();
  // }, [navigate]);

  // // Обработчик выбора файла
  // const handleFileChange = (event) => {
  //   setSelectedFile(event.target.files[0]); // Устанавливаем выбранный файл в состояние
  // };

  // // Обработчик загрузки файла
  // const handleUpload = async () => {
  //   if (!selectedFile) {
  //     setMessage('Please select a file first.');
  //     return;
  //   }

  //   const formData = new FormData();
  //   formData.append('file', selectedFile);

  //   try {
  //     const token = localStorage.getItem('accessToken');
  //     const response = await axios.post('/api/upload-avatar/', formData, {
  //       headers: {
  //         'Content-Type': 'multipart/form-data',
  //         Authorization: `Bearer ${token}`,
  //       },
  //     });

  //     // Обновляем аватарку пользователя
  //     setUser((prevUser) => ({
  //       ...prevUser,
  //       avatar: response.data.avatar_url,
  //     }));
  //     setMessage('Avatar updated successfully!');
  //   } catch (error) {
  //     console.error('Error uploading avatar:', error);
  //     setMessage('Failed to upload avatar.');
  //   }
  // };

  // // Обработчик выхода из аккаунта
  // const handleLogout = () => {
  //   localStorage.removeItem('accessToken'); // Удаляем токен из localStorage
  //   navigate('/'); // Перенаправляем пользователя на страницу входа
  // };

  // if (!user) return null; // Отображаем пустую страницу, пока загружаются данные

  // return (
  //   <div>
  //     <h2>Welcome to Your Dashboard</h2>
  //     <img
  //       src={user.avatar || '/assets/avatars/avatar.jpg'}
  //       alt='User Avatar'
  //       width='100'
  //       height='100'
  //     />{' '}
  //     {/* Отображаем аватарку */}
  //     <p>Username: {user.username}</p>
  //     {user.role === 'admin' && <p>You have admin privileges.</p>}{' '}
  //     {/* Если пользователь администратор, отображаем сообщение */}
  //     {/* Кнопка выбора файла и загрузки новой аватарки */}
  //     <input type='file' onChange={handleFileChange} />
  //     <button onClick={handleUpload}>Upload New Avatar</button>
  //     {message && <p>{message}</p>}{' '}
  //     {/* Отображаем сообщение об успехе или ошибке */}
  //     {/* Кнопка выхода из аккаунта */}
  //     <button onClick={handleLogout}>Logout</button>
  //   </div>
  // );

  const buttonsInfo = [
    {
      id: 1,
      titleName: 'Игровой мир',
      titleLink: '#',
      img: button1img,
      links: [
        { name: 'Персонажи', link: '#' },
        { name: 'Навыки', link: '#' },
        { name: 'Аукцион', link: '#' },
      ],
    },
    {
      id: 2,
      titleName: 'Руководство',
      titleLink: '#',
      img: button2img,
      links: [
        { name: 'Обучение', link: '#' },
        { name: 'Консультант', link: '#' },
        { name: 'Фандом', link: '#' },
      ],
    },
    {
      id: 3,
      titleName: 'Магазин',
      titleLink: '#',
      img: button3img,
      links: [
        { name: 'Рулетка', link: '#' },
        { name: 'События', link: '#' },
        { name: 'Валюта', link: '#' },
      ],
    },
  ];

  const smallButtonsInfo = [
    {
      id: 1,
      link: '#',
      title: 'Предложения',
      img: smallbuttonimg1,
    },
    {
      id: 2,
      link: '#',
      title: 'Администрация',
      img: smallbuttonimg2,
    },
    {
      id: 3,
      link: '#',
      title: 'Бестиарий',
      img: smallbuttonimg3,
    },
    {
      id: 4,
      link: '#',
      title: 'Поиск игрока',
      img: smallbuttonimg4,
    },
  ];

  const sliderPages = [
    {
      index: 1,
      title: 'Мы открываемся !',
      description: 'Все что нужно знать о запуске проекта',
      link: '#',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 2,
      title: 'Мы закрываемся !',
      description: 'Идите нахуй!',
      link: '#',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 3,
      title: 'Снова открываемся !',
      description: 'извинити пж',
      link: '#',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 4,
      title: 'Сосал?',
      description: 'да..',
      link: '#',
      img: sliderImg1,
      tag: 'Технобук',
    },
  ];

  return (
    <>
      <Header showMenu={true} profileName={'говно'} />

      <section className={styles.main}>
        {buttonsInfo.map((button, key) => (
          <HomePageButton
            key={button.id}
            titleName={button.titleName}
            titleLink={button.titleLink}
            backgroundImg={button.img}
            links={button.links}
          />
        ))}

        <Slider pages={sliderPages} />

        <div className={styles.small_buttons}>
          {smallButtonsInfo.map((button, key) => (
            <SmallHomePageButton
              key={button.id}
              link={button.link}
              title={button.title}
              backgroundImg={button.img}
            />
          ))}
        </div>
      </section>
    </>
  );
}

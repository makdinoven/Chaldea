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

  return (
    <>
      <Header showMenu={true} profileName={'dudka'} />
      <section className={styles.main}>
        <HomePageButton
          title='Игровой мир'
          links={[
            { name: 'Персонажи', link: '#' },
            { name: 'Навыки', link: '#' },
            { name: 'Аукцион', link: '#' },
          ]}
          backgroundImg={button1img}
        />
        <HomePageButton
          title='Руководство'
          links={[
            { name: 'Обучение', link: '#' },
            { name: 'Консультант', link: '#' },
            { name: 'Фандом', link: '#' },
          ]}
          backgroundImg={button2img}
        />
        <HomePageButton
          title='Магазин'
          links={[
            { name: 'Рулетка', link: '#' },
            { name: 'События', link: '#' },
            { name: 'Валюта', link: '#' },
          ]}
          backgroundImg={button3img}
        />
        <Slider />
        <div className={styles.small_buttons}>
          <SmallHomePageButton
            title='Предложения'
            backgroundImg={smallbuttonimg1}
          />
          <SmallHomePageButton
            title='Администрация'
            backgroundImg={smallbuttonimg2}
          />
          <SmallHomePageButton
            title='Бестиарий'
            backgroundImg={smallbuttonimg3}
          />
          <SmallHomePageButton
            title='Поиск Игрока'
            backgroundImg={smallbuttonimg4}
          />
        </div>
      </section>
    </>
  );
}

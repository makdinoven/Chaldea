import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

import Header from '../CommonComponents/Header/Header';
import Button from './Button/Button';
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
  const [user, setUser] = useState(null); // Состояние для хранения информации о пользователе
  const [selectedFile, setSelectedFile] = useState(null); // Состояние для хранения выбранного файла
  const [message, setMessage] = useState(''); // Состояние для сообщений об успехе или ошибке
  const navigate = useNavigate();

  useEffect(() => {
    const fetchUserData = async () => {
      const token = localStorage.getItem('accessToken'); // Получаем токен из локального хранилища
      if (!token) {
        navigate('/'); // Перенаправляем на страницу входа, если токен отсутствует
        return;
      }

      try {
        // Отправляем запрос на сервер для получения данных текущего пользователя
        const response = await axios.get('/api/users/me', {
          headers: {
            Authorization: `Bearer ${token}`, // Передаем токен в заголовках запроса
          },
        });
        setUser(response.data); // Сохраняем данные пользователя в состоянии
      } catch (error) {
        console.error('Failed to fetch user data:', error);
        localStorage.removeItem('accessToken'); // Удаляем токен в случае ошибки
        navigate('/'); // Перенаправляем на страницу входа
      }
    };

    fetchUserData();
  }, [navigate]);

  // Обработчик выбора файла
  const handleFileChange = (event) => {
    setSelectedFile(event.target.files[0]); // Устанавливаем выбранный файл в состояние
  };

  // Обработчик загрузки файла
  const handleUpload = async () => {
    if (!selectedFile) {
      setMessage('Please select a file first.');
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const token = localStorage.getItem('accessToken');
      const response = await axios.post('/api/upload-avatar/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
          Authorization: `Bearer ${token}`,
        },
      });

      // Обновляем аватарку пользователя
      setUser((prevUser) => ({
        ...prevUser,
        avatar: response.data.avatar_url,
      }));
      setMessage('Avatar updated successfully!');
    } catch (error) {
      console.error('Error uploading avatar:', error);
      setMessage('Failed to upload avatar.');
    }
  };

  if (!user) return null; // Отображаем пустую страницу, пока загружаются данные

  const buttonsData = [
    {
      id: 1,
      titleName: 'Игровой мир',
      titleLink: '/world',
      img: button1img,
      links: [
        { name: 'Персонажи', link: '/characters' },
        { name: 'Навыки', link: '/skills' },
        { name: 'Аукцион', link: '/auction' },
      ],
      type: 'large',
    },
    {
      id: 2,
      titleName: 'Руководство',
      titleLink: '/guide',
      img: button2img,
      links: [
        { name: 'Обучение', link: '/learning' },
        { name: 'Консультант', link: '/consultant' },
        { name: 'Фандом', link: '/fandom' },
      ],
      type: 'large',
    },
    {
      id: 3,
      titleName: 'Магазин',
      titleLink: '/shop',
      img: button3img,
      links: [
        { name: 'Рулетка', link: '/roulette' },
        { name: 'События', link: '/events' },
        { name: 'Валюта', link: '/currency' },
      ],
      type: 'large',
    },
    {
      id: 4,
      titleLink: '/offers',
      titleName: 'Предложения',
      img: smallbuttonimg1,
      type: 'small',
    },
    {
      id: 5,
      titleLink: '/administration',
      titleName: 'Администрация',
      img: smallbuttonimg2,
      type: 'small',
    },
    {
      id: 6,
      titleLink: '/bestiary',
      titleName: 'Бестиарий',
      img: smallbuttonimg3,
      type: 'small',
    },
    {
      id: 7,
      titleLink: '/findaplayer',
      titleName: 'Поиск игрока',
      img: smallbuttonimg4,
      type: 'small',
    },
  ];

  const sliderData = [
    {
      index: 1,
      title: 'cdd',
      description: 'Все что нужно знать о запуске проекта',
      link: '/sliderlink1',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 2,
      title: 'Мы закрываемся !',
      description: 'Идите нахуй!',
      link: '/sliderlink2',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 3,
      title: 'Снова открываемся !',
      description: 'извинити пж',
      link: '/sliderlink3',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 4,
      title: 'Сосал?',
      description: 'да..',
      link: '/sliderlink4',
      img: sliderImg1,
      tag: 'Технобук',
    },
  ];

  return (
    <>
      <Header showMenu={true} profileName={user.username} />

      <section className={styles.main}>
        {buttonsData
          .filter((button) => button.type === 'large')
          .map((buttonData) => (
            <Button key={buttonData.id} data={buttonData} />
          ))}

        <Slider pages={sliderData} />

        <div className={styles.small_buttons}>
          {buttonsData
            .filter((button) => button.type === 'small')
            .map((buttonData) => (
              <Button key={buttonData.id} data={buttonData} />
            ))}
        </div>
      </section>
    </>
  );
}

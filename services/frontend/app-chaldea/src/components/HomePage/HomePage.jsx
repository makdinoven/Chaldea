import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useUser } from '../../hooks/UserContext';
import { useFetchUserData } from '../../hooks/useFetchUserData';

import Header from '../CommonComponents/Header/Header';
import Button from './Button/Button';
import Slider from './Slider/Slider';
import Stats from './Stats/Stats';

import styles from './HomePage.module.css';

import button1img from '../../assets/homepagebutton1.png';
import button2img from '../../assets/homepagebutton2.png';
import button3img from '../../assets/homepagebutton3.png';
import smallbuttonimg1 from '../../assets/smallhomebutton1.png';
import smallbuttonimg2 from '../../assets/smallhomebutton2.png';
import smallbuttonimg3 from '../../assets/smallhomebutton3.png';
import smallbuttonimg4 from '../../assets/smallhomebutton4.png';
import sliderImg1 from '../../assets/sliderimg1.png';
import statsBg from '../../assets/stats_bg.png';
import statsUserImg from '../../assets/stats_user_img.png';

export default function HomePage() {
  const navigate = useNavigate();
  const { user, setUser } = useUser();

  useFetchUserData(navigate, setUser);

  if (!user) return null;

  const buttonsData = [
    {
      id: 1,
      titleName: 'Игровой мир',
      titleLink: '/world',
      img: button1img,
      links: [
        { name: 'Персонажи', link: '/characters' },
        { name: 'Навыки', link: 'admin/skills' },
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
      title: 'Мы открываемся!',
      description: 'Все что нужно знать о запуске проекта',
      link: '/sliderlink1',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 2,
      title: 'Мы открываемся!2',
      description: 'Все что нужно знать о запуске проекта2',
      link: '/sliderlink2',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 3,
      title: 'Мы открываемся!3',
      description: 'Все что нужно знать о запуске проекта3',
      link: '/sliderlink3',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 4,
      title: 'Мы открываемся!4',
      description: 'Все что нужно знать о запуске проекта',
      link: '/sliderlink4',
      img: sliderImg1,
      tag: 'Технобук',
    },
  ];

  const statsData = {
    img: statsBg,
    title: 'Статистика',
    sections: [
      {
        sectionName: 'Лучшие ролевики',
        users: [
          { name: 'Фармила', points: 895, avatar: statsUserImg },
          { name: 'Сгущенка', points: 654, avatar: statsUserImg },
          { name: 'Тушенка', points: 432, avatar: statsUserImg },
        ],
      },
      {
        sectionName: 'Лучшие боевики',
        users: [
          { name: 'Бэбрик Йохансон', points: 545, avatar: statsUserImg },
          { name: 'Чебурашка', points: 322, avatar: statsUserImg },
          { name: 'Сгущенка', points: 212, avatar: statsUserImg },
        ],
      },
      {
        sectionName: 'Лучшие писатели',
        users: [
          { name: 'Фармила', points: 8495, avatar: statsUserImg },
          { name: 'Сгущенка', points: 654, avatar: statsUserImg },
          { name: 'Тушенка', points: 432, avatar: statsUserImg },
        ],
      },
    ],
  };

  return (
    <>

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

      <Stats statsData={statsData} />
    </>
  );
}

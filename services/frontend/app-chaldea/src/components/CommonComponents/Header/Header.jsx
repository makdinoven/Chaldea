import React, { useEffect } from 'react';

import Menu from './Menu/Menu';
import { useUser } from '../../../hooks/UserContext';

import styles from './Header.module.scss';

import logo from '../../../assets/logo.png';
import menuImg1 from '../../../assets/menu1.png';
import menuImg2 from '../../../assets/menu2.png';
import menuImg3 from '../../../assets/menuImg.png';
import {Link} from "react-router-dom";

export default function Header() {
  const { user, setUser } = useUser();
  const menuData = [
    {
      id: 1,
      menuButtons: [
        { name: 'Сообщения', link: '/messages' },
        { name: 'Поддержка', link: '/support' },
        { name: 'Профиль', link: '/profile' },
        { name: 'Выход', link: '/' },
      ],
      img: menuImg1,
      title: user?.username,
    },
    {
      id: 2,
      menuButtons: [
        { name: 'Создать', link: '/createCharacter' },
        { name: 'Выбрать', link: '/selectCharacter' },
      ],
      img: menuImg2,
      title: 'Персонаж',
    },
    {
      id: 3,
      menuButtons: [{ name: 'Заявки', link: '/requestsPage' }],
      img: menuImg3,
      title: 'Заявки',
    },
  ];

  return (
    <>
      <header className={styles.header}>
          <div className={styles.menu_container_left}>
            {menuData.slice(0, 2).map((menu) => (
              <Menu
                key={menu.id}
                title={menu.title}
                menuButtons={menu.menuButtons}
                backgroundImg={menu.img}
              />
            ))}
          </div>
        <Link to={'/home'} className={styles.logo}>
          <img
              src={logo}
              alt='Logo'
          />
        </Link>

        <div className={styles.menu_container_right}>
          {menuData.slice(2).map((menu) => (
              user.role === 'admin' &&
              <Menu
                key={menu.id}
                title={menu.title}
                menuButtons={menu.menuButtons}
                backgroundImg={menu.img}
              />
            ))}
          </div>
      </header>
    </>
  );
}

import React, { useEffect } from 'react';

import Menu from './Menu/Menu';
import Search from './Search/Search';
import useNavigateTo from '../../../hooks/useNavigateTo';
import { useUser } from '../../../hooks/UserContext';

import styles from './Header.module.css';

import logo from '../../../assets/logo.png';
import menuImg1 from '../../../assets/menu1.png';
import menuImg2 from '../../../assets/menu2.png';

export default function Header({ showMenu }) {
  const navigateTo = useNavigateTo();
  const { user, setUser } = useUser();
  // useEffect(() => {
  //   // Чтение имени пользователя из localStorage
  //   const storedUsername = localStorage.getItem('username');
  //   if (storedUsername && !user) {
  //     // Устанавливаем пользователя в контексте, если он не установлен
  //     setUser({ username: storedUsername });
  //   }
  // }, [user, setUser]);

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
  ];

  return (
    <>
      <header className={styles.header}>
        {showMenu && (
          <div className={styles.menu_container}>
            {menuData.map((menu) => (
              <Menu
                key={menu.id}
                title={menu.title}
                menuButtons={menu.menuButtons}
                backgroundImg={menu.img}
              />
            ))}
          </div>
        )}
        <img
          onClick={() => navigateTo('/home')}
          className={styles.logo}
          src={logo}
          alt='Logo'
        />
        {showMenu && <Search />}
      </header>
    </>
  );
}

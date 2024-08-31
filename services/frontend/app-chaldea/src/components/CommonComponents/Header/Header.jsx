import React from 'react';

import Menu from './Menu/Menu';
import Search from './Search/Search';
import useNavigateTo from '../../../hooks/useNavigateTo';

import styles from './Header.module.css';

import logo from '../../../assets/logo.png';
import menuImg1 from '../../../assets/menu1.png';
import menuImg2 from '../../../assets/menu2.png';

export default function Header({ showMenu, profileName }) {
  const navigateTo = useNavigateTo();

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
      title: profileName,
    },
    {
      id: 2,
      menuButtons: [
        { name: 'Создать', link: '/createCharacter' },
        { name: 'Выбрать', link: '/selectCharacter' },
      ],
      img: menuImg2,
      title: 'Профиль',
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
          onClick={navigateTo('./home')}
          className={styles.logo}
          src={logo}
          alt='Logo'
        />
        {showMenu && <Search />}
      </header>
    </>
  );
}

import React from 'react';

import Menu from './Menu/Menu';
import Search from './Search/Search';

import styles from './Header.module.css';

import logo from '../../../assets/logo.png';
import menuImg1 from '../../../assets/menu1.png';
import menuImg2 from '../../../assets/menu2.png';

export default function Header({ showMenu, profileName }) {
  const menuInfo = [
    {
      id: 1,
      menuItems: [
        { name: 'Сообщения', link: '#' },
        { name: 'Поддержка', link: '#' },
        { name: 'Профиль', link: '#' },
        { name: 'Выход', link: '#' },
      ],
      img: menuImg1,
      title: profileName,
    },
    {
      id: 2,
      menuItems: [
        { name: 'Создать', link: '#' },
        { name: 'Выбрать', link: '#' },
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
            {menuInfo.map((menu) => (
              <Menu
                key={menu.id}
                title={menu.title}
                menuItems={menu.menuItems}
                backgroundImg={menu.img}
              />
            ))}
          </div>
        )}
        <img className={styles.logo} src={logo} alt='Logo' />
        {showMenu && <Search />}
      </header>
    </>
  );
}

import React from 'react';

import Menu from './Menu/Menu';
import Search from './Search/Search';

import styles from './Header.module.css';

import logo from '../../../assets/logo.png';
import menuImg1 from '../../../assets/menu1.png';
import menuImg2 from '../../../assets/menu2.png';

export default function Header({ showMenu, profileName }) {
  return (
    <>
      <header className={styles.header}>
        {showMenu && (
          <div className={styles.menu_container}>
            <Menu
              menuItems={[
                { name: 'Сообщения', link: '#' },
                { name: 'Поддержка', link: '#' },
                { name: 'Профиль', link: '#' },
                { name: 'Выход', link: '#' },
              ]}
              backgroundImg={menuImg1}
              title={profileName}
            />
            <Menu
              menuItems={[
                { name: 'Создать', link: '#' },
                { name: 'Выбрать', link: '#' },
              ]}
              backgroundImg={menuImg2}
              title='Персонаж'
            />
          </div>
        )}
        <img className={styles.logo} src={logo} alt='Logo' />
        {showMenu && <Search />}
      </header>
    </>
  );
}

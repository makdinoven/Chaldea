import React from 'react';

import styles from './Header.module.css';

import logo from '../../../assets/logo.png';

export default function Header() {
  return (
    <>
      <header className={styles.header}>
        <img className='logo' src={logo} alt='Logo' />
      </header>
    </>
  );
}

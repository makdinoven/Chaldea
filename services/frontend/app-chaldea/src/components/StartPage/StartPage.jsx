import React from 'react';
import Header from '../CommonComponents/Header/Header.jsx';
import LogButton from './LogButton/LogButton.jsx';
import AuthForm from './AuthForm/AuthFrom.jsx';

import styles from './StartPage.module.css';

export default function StartPage() {
  const [activeButton, setActiveButton] = React.useState('login');

  const handleButtonClick = (buttonName) => {
    setActiveButton(buttonName);
  };

  return (
    <>
      <Header />

      <section className={styles.content}>
        <h1 className={styles.title}>Ваше приключение начинается здесь</h1>
        <p className={styles.description}>
          Войдите или зарегистрируйтесь, чтобы начать свой путь и исследовать
          новые горизонты.
        </p>
      </section>

      <section className={styles.form_window}>
        <LogButton
          text='Вход'
          isActive={activeButton === 'login'}
          onClick={() => handleButtonClick('login')}
        />
        <LogButton
          text='Регистрация'
          isActive={activeButton === 'register'}
          onClick={() => handleButtonClick('register')}
        />

        <AuthForm activeForm={activeButton} />
      </section>
    </>
  );
}

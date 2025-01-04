import React, { useEffect } from 'react';
import LogButton from './LogButton/LogButton.jsx';
import AuthForm from './AuthForm/AuthForm.jsx';

import styles from './StartPage.module.scss';

export default function StartPage() {
  const [activeButton, setActiveButton] = React.useState('login');

  useEffect(() => {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
  }, []);

  const handleButtonClick = (buttonName) => {
    setActiveButton(buttonName);
  };

  return (
    <div className={styles.content}>
      <section className={styles.content}>
        <h1 className={styles.title}>Ваше приключение начинается здесь</h1>
        <p className={styles.description}>
          Войдите или зарегистрируйтесь, чтобы начать свой путь и исследовать
          новые горизонты.
        </p>
      </section>
      <section className={styles.form_window_container}>
        <div className={styles.form_window}>
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
        </div>
      </section>
    </div>
  );
}

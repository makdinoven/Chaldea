import React from 'react';
import LogButton from './LogButton/LogButton.jsx';
import AuthForm from './AuthForm/AuthFrom.jsx';

import './StartPage.css';

import logo from '../../assets/logo.png';

export default function StartPage() {
  const [activeButton, setActiveButton] = React.useState('login');

  const handleButtonClick = (buttonName) => {
    setActiveButton(buttonName);
  };

  return (
    <>
      <header className='header'>
        <img className='logo' src={logo} alt='Logo' />
      </header>
      <section className='content'>
        <h1 className='title'>
          <span
            data-text='Ваше приключение начинается здесь'
            className='title__text'
          >
            Ваше приключение начинается здесь
          </span>
        </h1>
        <p className='description'>
          Войдите или зарегистрируйтесь, чтобы начать свой путь и исследовать
          новые горизонты.
        </p>
      </section>

      <section className='form-window'>
        <div className='buttons'>
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
        </div>
        <AuthForm activeForm={activeButton} />
      </section>
    </>
  );
}

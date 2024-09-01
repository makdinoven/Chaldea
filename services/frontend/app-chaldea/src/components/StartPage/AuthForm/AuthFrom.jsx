import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Input from './Input/Input.jsx';
import FormButton from './FormButton/FormButton.jsx';

import useNavigateTo from '../../../hooks/useNavigateTo.js';

import styles from './AuthForm.module.css';

export default function AuthForm({ activeForm }) {
  const [formHeight, setFormHeight] = useState('279px');
  const [email, setEmail] = useState(''); // Состояние для хранения email
  const [username, setUsername] = useState(''); // Состояние для хранения логина
  const [password, setPassword] = useState(''); // Состояние для хранения пароля
  const [confirmPassword, setConfirmPassword] = useState(''); // Состояние для подтверждения пароля
  const [error, setError] = useState(''); // Состояние для ошибок
  const navigateTo = useNavigateTo(); // Используем hook для перенаправления

  useEffect(() => {
    // Изменение высоты формы в зависимости от активной формы
    if (activeForm === 'login') {
      setFormHeight('279px');
    } else {
      setFormHeight('373px');
    }
  }, [activeForm]);

  const handleSubmit = async (e) => {
    e.preventDefault(); // Предотвращаем перезагрузку страницы

    try {
      // Определяем URL в зависимости от формы входа или регистрации
      const url = activeForm === 'login' ? '/api/login' : '/api/register';

      // Формируем данные для отправки
      const data =
        activeForm === 'login'
          ? { identifier: username, password } // Используем 'identifier' для входа
          : { email, username, password }; // Для регистрации используем email, логин и пароли

      console.log('Отправка данных:', data);

      // Отправляем запрос на сервер
      const response = await axios.post(url, data);

      console.log('Ответ сервера:', response);

      if (response.status === 200) {
        // Сохраняем токен доступа в локальное хранилище
        localStorage.setItem('accessToken', response.data.access_token);
        if (response.data.refresh_token) {
          localStorage.setItem('refreshToken', response.data.refresh_token); // Сохраняем refresh token, если он возвращается
        }

        console.log(
          'Токен успешно сохранен в localStorage:',
          localStorage.getItem('accessToken')
        );

        // Перенаправляем на главную страницу после успешного входа
        navigateTo('/home');
      } else {
        setError('Ошибка аутентификации. Проверьте введенные данные.');
      }
    } catch (error) {
      console.error('Ошибка аутентификации:', error);

      // Проверка на наличие ответа от сервера и его данных
      if (error.response) {
        console.error('Ответ сервера:', error.response);
        setError(
          `Ошибка: ${
            JSON.stringify(error.response.data) ||
            'Не удалось выполнить запрос.'
          }`
        );
      } else {
        setError('Ошибка аутентификации. Проверьте введенные данные.'); // Обработка ошибки
      }

      // Проверка на удаление токена после ошибки
      console.log('Токен после ошибки:', localStorage.getItem('accessToken'));
      localStorage.removeItem('accessToken'); // Удаляем токен в случае ошибки
    }
  };

  return (
    <div className={styles.container} style={{ height: formHeight }}>
      <form className={styles.auth_form} onSubmit={handleSubmit}>
        {activeForm === 'login' ? (
          <>
            <Input
              id='login'
              text='Логин*'
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <Input
              id='password'
              text='Пароль*'
              type='password'
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </>
        ) : (
          <>
            <Input
              id='email'
              text='Email*'
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Input
              id='reglogin'
              text='Логин*'
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <Input
              id='regpassword'
              text='Пароль*'
              type='password'
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Input
              id='regpasswordagain'
              text='Пароль еще раз*'
              type='password'
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </>
        )}
        <label className={styles.policy} htmlFor='policy'>
          <input className={styles.real_checkbox} id='policy' type='checkbox' />
          <span className={styles.custom_checkbox}></span>
          <span className={styles.policy_text}>
            Я соглашаюсь с{' '}
            <a className={styles.policy_link} href='#'>
              Политикой конфиденциальности
            </a>{' '}
            и даю согласие на обработку моих данных для получения рассылок.
          </span>
        </label>
        {error && <p className={styles.error_message}>{error}</p>}{' '}
        {/* Отображение сообщения об ошибке */}
        {activeForm === 'login' ? (
          <FormButton text='Вход' />
        ) : (
          <FormButton text='Регистрация' />
        )}
      </form>
    </div>
  );
}

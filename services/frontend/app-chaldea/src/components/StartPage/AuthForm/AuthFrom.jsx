import React from 'react';
import Input from './Input/Input.jsx';
import FormButton from './FormButton/FormButton.jsx';

import './AuthForm.css';

export default function AuthForm({ activeForm }) {
  const [formHeight, setFormHeight] = React.useState('279px');

  React.useEffect(() => {
    if (activeForm === 'login') {
      setFormHeight('279px');
    } else {
      setFormHeight('373px');
    }
  }, [activeForm]);

  return (
    <div className='auth-form-container' style={{ height: formHeight }}>
      <form className='auth-form' action=''>
        {activeForm === 'login' ? (
          <>
            <Input text='Логин*' />
            <Input text='Пароль*' />
          </>
        ) : (
          <>
            <Input text='Email*' />
            <Input text='Логин*' />
            <Input text='Пароль*' />
            <Input text='Пароль еще раз*' />
          </>
        )}

        <label className='policy-label' htmlFor='policy'>
          <input className='real-checkbox' id='policy' type='checkbox' />
          <span className='custom-checkbox'></span>
          <span className='policy-text'>
            Я соглашаюсь с{' '}
            <a className='policy-link' href='#'>
              {' '}
              Политикой конфиденциальности{' '}
            </a>
            и даю согласие на обработку моих данных для получения рассылок.
          </span>
        </label>

        {activeForm === 'login' ? (
          <>
            <FormButton text='Вход' />
          </>
        ) : (
          <>
            <FormButton text='Регистрация' />
          </>
        )}
      </form>
    </div>
  );
}

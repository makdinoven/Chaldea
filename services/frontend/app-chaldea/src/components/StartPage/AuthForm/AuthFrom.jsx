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
            <Input id='login' type='text' text='Логин*' />
            <Input id='password' type='text' text='Пароль*' />
          </>
        ) : (
          <>
            <Input id='email' type='text' text='Email*' />
            <Input id='login' type='text' text='Логин*' />
            <Input id='password' type='text' text='Пароль*' />
            <Input id='passwordAgain' type='text' text='Пароль еще раз*' />
          </>
        )}

        <div className='policy-container'>
          <div className='custom-radio'>
            <input className='policy-input' id='policy' type='radio' />
          </div>
          <label className='policy-label' htmlFor='policy'>
            Я соглашаюсь с{' '}
            <a className='policy-link' href='#'>
              {' '}
              Политикой конфиденциальности{' '}
            </a>
            и даю согласие на обработку моих данных для получения рассылок.
          </label>
        </div>
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

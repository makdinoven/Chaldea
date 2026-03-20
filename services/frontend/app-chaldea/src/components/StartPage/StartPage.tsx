import { useState } from 'react';
import LogButton from './LogButton/LogButton';
import AuthForm from './AuthForm/AuthForm';

const StartPage = () => {
  const [activeButton, setActiveButton] = useState<'login' | 'register'>('login');

  return (
    <div className="pt-[20vh]">
      <section>
        <h1 className="gold-text m-0 mb-[5px] font-bold text-[40px] text-center uppercase leading-tight">
          Ваше приключение начинается здесь
        </h1>
        <p className="m-0 mb-10 font-normal text-base tracking-[-0.03em] text-center text-white drop-shadow-[0_4px_4px_rgba(0,0,0,0.25)]">
          Войдите или зарегистрируйтесь, чтобы начать свой путь и исследовать
          новые горизонты.
        </p>
      </section>
      <section className="flex justify-center">
        <div className="w-full max-w-[960px] rounded-[10px] bg-site-bg overflow-hidden mb-[100px] mx-4 sm:mx-0">
          <LogButton
            text="Вход"
            isActive={activeButton === 'login'}
            onClick={() => setActiveButton('login')}
          />
          <LogButton
            text="Регистрация"
            isActive={activeButton === 'register'}
            onClick={() => setActiveButton('register')}
          />

          <AuthForm activeForm={activeButton} />
        </div>
      </section>
    </div>
  );
};

export default StartPage;

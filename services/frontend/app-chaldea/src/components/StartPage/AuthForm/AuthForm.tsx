import { useState, useEffect, FormEvent, ChangeEvent } from 'react';
import axios from 'axios';
import Input from '../../CommonComponents/Input/Input';
import FormButton from '../../CommonComponents/BlueGradientButton/BlueGradientButton';
import useNavigateTo from '../../../hooks/useNavigateTo';

interface AuthFormProps {
  activeForm: 'login' | 'register';
}

interface PydanticValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

const extractErrorMessage = (error: unknown): string => {
  if (!axios.isAxiosError(error)) {
    return 'Произошла ошибка. Попробуйте позже.';
  }

  const data = error.response?.data;
  if (!data) {
    return 'Ошибка соединения. Попробуйте позже.';
  }

  // Plain text error response (e.g., "Internal Server Error")
  if (typeof data === 'string') {
    return data;
  }

  // FastAPI HTTPException format: {"detail": "message"}
  if (typeof data.detail === 'string') {
    return data.detail;
  }

  // Pydantic validation error format: {"detail": [{"msg": "...", ...}]}
  if (Array.isArray(data.detail) && data.detail.length > 0) {
    return (data.detail as PydanticValidationError[])
      .map((err) => err.msg)
      .join('. ');
  }

  return 'Не удалось выполнить запрос.';
};

const AuthForm = ({ activeForm }: AuthFormProps) => {
  const [formHeight, setFormHeight] = useState('279px');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const navigateTo = useNavigateTo();

  useEffect(() => {
    if (activeForm === 'login') {
      setFormHeight('279px');
    } else {
      setFormHeight('373px');
    }
  }, [activeForm]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    setError('');

    // Client-side validation for registration
    if (activeForm === 'register') {
      if (password.length < 6) {
        setError('Пароль должен содержать минимум 6 символов');
        return;
      }
      if (password !== confirmPassword) {
        setError('Пароли не совпадают');
        return;
      }
    }

    try {
      const url = activeForm === 'login' ? '/users/login' : '/users/register';

      const data =
        activeForm === 'login'
          ? { identifier: username, password }
          : { email, username, password };

      const response = await axios.post(url, data);

      if (response.status === 200) {
        localStorage.setItem('accessToken', response.data.access_token);

        if (response.data.refresh_token) {
          localStorage.setItem('refreshToken', response.data.refresh_token);
        }

        navigateTo('/home');
      } else {
        setError('Ошибка аутентификации. Проверьте введенные данные.');
      }
    } catch (err: unknown) {
      const message = extractErrorMessage(err);
      setError(message);
      localStorage.removeItem('accessToken');
    }
  };

  return (
    <div
      className="overflow-hidden flex justify-center transition-all duration-[400ms] ease-in-out"
      style={{ height: formHeight }}
    >
      <form
        className="w-[383px] pt-[50px] px-5 pb-10 flex flex-col items-center"
        onSubmit={handleSubmit}
      >
        <div className="flex flex-col gap-3 mb-6">
          {activeForm === 'login' ? (
            <>
              <Input
                isRequired={true}
                id="login"
                text="Логин*"
                value={username}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)}
                name="username"
                autoComplete="username"
              />
              <Input
                isRequired={true}
                id="password"
                text="Пароль*"
                type="password"
                value={password}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                name="password"
                autoComplete="current-password"
              />
            </>
          ) : (
            <>
              <Input
                isRequired={true}
                id="email"
                text="Email*"
                type="email"
                value={email}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
                name="email"
                autoComplete="email"
              />
              <Input
                isRequired={true}
                id="reglogin"
                text="Логин*"
                value={username}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)}
                name="username"
                autoComplete="username"
              />
              <Input
                isRequired={true}
                id="regpassword"
                text="Пароль*"
                type="password"
                value={password}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                name="new-password"
                autoComplete="new-password"
              />
              <Input
                isRequired={true}
                id="regpasswordagain"
                text="Пароль еще раз*"
                type="password"
                value={confirmPassword}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)}
                name="confirm-password"
                autoComplete="new-password"
              />
            </>
          )}
          <label
            className="w-full grid grid-cols-[16px_auto] items-center gap-1.5 text-[10px] font-normal tracking-[-0.03em] text-white"
            htmlFor="policy"
          >
            <input
              className="m-0 w-0 h-0 opacity-0 absolute -z-10 peer"
              id="policy"
              type="checkbox"
            />
            <span className="gold-checkbox relative flex outline outline-1 outline-[#fefefe] rounded-[2px] overflow-hidden w-4 h-4 shadow-[0_4px_4px_0_rgba(0,0,0,0.25)] bg-transparent" />
            <span className="block">
              Я соглашаюсь с{' '}
              <a className="underline" href="#">
                Политикой конфиденциальности
              </a>{' '}
              и даю согласие на обработку моих данных для получения рассылок.
            </span>
          </label>
        </div>
        {error && (
          <p className="text-site-red text-xs text-center mb-3">{error}</p>
        )}
        {activeForm === 'login' ? (
          <FormButton text="Вход" onClick={handleSubmit} />
        ) : (
          <FormButton text="Регистрация" onClick={handleSubmit} />
        )}
      </form>
    </div>
  );
};

export default AuthForm;

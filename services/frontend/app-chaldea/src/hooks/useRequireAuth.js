import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export const useRequireAuth = () => {
  const navigate = useNavigate();

  useEffect(() => {
    const token = localStorage.getItem('accessToken'); // Получаем токен из локального хранилища
    if (!token) {
      navigate('/'); // Перенаправляем на страницу входа, если токен отсутствует
    }
  }, [navigate]); // Хук срабатывает при первом рендере компонента
};

import { useEffect } from 'react';
import axios from 'axios';

export const useFetchUserData = (navigate, setUser) => {
  useEffect(() => {
    const fetchUserData = async () => {
      const token = localStorage.getItem('accessToken'); // Получаем токен из локального хранилища
      if (!token) {
        navigate('/'); // Перенаправляем на страницу входа, если токен отсутствует
        return;
      }

      try {
        // Отправляем запрос на сервер для получения данных текущего пользователя
        const response = await axios.get('/api/users/me', {
          headers: {
            Authorization: `Bearer ${token}`, // Передаем токен в заголовках запроса
          },
        });
        setUser(response.data); // Обновляем состояние пользователя
      } catch (error) {
        console.error('Failed to fetch user data:', error);
        localStorage.removeItem('accessToken'); // Удаляем токен в случае ошибки
        navigate('/'); // Перенаправляем на страницу входа
      }
    };

    fetchUserData();
  }, [navigate, setUser]); // Обновление эффекта при изменении navigate или setUser
};

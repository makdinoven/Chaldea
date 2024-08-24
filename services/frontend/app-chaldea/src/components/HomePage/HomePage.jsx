import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const HomePage = () => {
  const [user, setUser] = useState(null); // Состояние для хранения информации о пользователе
  const [selectedFile, setSelectedFile] = useState(null); // Состояние для хранения выбранного файла
  const [message, setMessage] = useState(''); // Состояние для сообщений об успехе или ошибке
  const navigate = useNavigate();

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
            Authorization: `Bearer ${token}` // Передаем токен в заголовках запроса
          }
        });
        setUser(response.data); // Сохраняем данные пользователя в состоянии
      } catch (error) {
        console.error('Failed to fetch user data:', error);
        localStorage.removeItem('accessToken'); // Удаляем токен в случае ошибки
        navigate('/'); // Перенаправляем на страницу входа
      }
    };

    fetchUserData();
  }, [navigate]);

  // Обработчик выбора файла
  const handleFileChange = (event) => {
    setSelectedFile(event.target.files[0]); // Устанавливаем выбранный файл в состояние
  };

  // Обработчик загрузки файла
  const handleUpload = async () => {
    if (!selectedFile) {
      setMessage('Please select a file first.');
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const token = localStorage.getItem('accessToken');
      const response = await axios.post('/api/upload-avatar/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
          Authorization: `Bearer ${token}`
        }
      });

      // Обновляем аватарку пользователя
      setUser((prevUser) => ({
        ...prevUser,
        avatar: response.data.avatar_url
      }));
      setMessage('Avatar updated successfully!');
    } catch (error) {
      console.error('Error uploading avatar:', error);
      setMessage('Failed to upload avatar.');
    }
  };

  // Обработчик выхода из аккаунта
  const handleLogout = () => {
    localStorage.removeItem('accessToken'); // Удаляем токен из localStorage
    navigate('/'); // Перенаправляем пользователя на страницу входа
  };

  if (!user) return null; // Отображаем пустую страницу, пока загружаются данные

  return (
    <div>
      <h2>Welcome to Your Dashboard</h2>
      <img src={user.avatar || '/assets/avatars/avatar.jpg'} alt="User Avatar" width="100" height="100" /> {/* Отображаем аватарку */}
      <p>Username: {user.username}</p>
      {user.role === 'admin' && <p>You have admin privileges.</p>} {/* Если пользователь администратор, отображаем сообщение */}

      {/* Кнопка выбора файла и загрузки новой аватарки */}
      <input type="file" onChange={handleFileChange} />
      <button onClick={handleUpload}>Upload New Avatar</button>
      {message && <p>{message}</p>} {/* Отображаем сообщение об успехе или ошибке */}

      {/* Кнопка выхода из аккаунта */}
      <button onClick={handleLogout}>Logout</button>
    </div>
  );
};

export default HomePage;

import React, { createContext, useState, useContext, useEffect } from 'react';

// Создаем контекст
const UserContext = createContext();

// Создаем провайдер для контекста
export const UserProvider = ({ children }) => {
  const [user, setUser] = useState(() => {
    // Инициализируем состояние пользователя из localStorage, если оно есть
    const storedUsername = localStorage.getItem('username');
    return storedUsername ? { username: storedUsername } : null;
  });

  useEffect(() => {
    // Сохраняем имя пользователя в localStorage при изменении состояния
    if (user && user.username) {
      localStorage.setItem('username', user.username);
    } else {
      localStorage.removeItem('username');
    }
  }, [user]);

  return (
    <UserContext.Provider value={{ user, setUser }}>
      {children}
    </UserContext.Provider>
  );
};

// Хук для использования контекста
export const useUser = () => useContext(UserContext);

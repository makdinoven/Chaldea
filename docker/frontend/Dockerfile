# Используем официальный образ Node.js для этапа сборки
FROM node:18-alpine AS build

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем package.json и package-lock.json для установки зависимостей
COPY services/frontend/app-chaldea/package*.json ./

# Устанавливаем зависимости
RUN npm install --legacy-peer-deps

# Копируем исходный код приложения
COPY services/frontend/app-chaldea .

# Сборка приложения
RUN npm run build

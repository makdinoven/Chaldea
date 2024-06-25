# Используем минимальный образ Nginx для раздачи статики
FROM nginx:alpine

# Копируем конфигурационный файл Nginx
COPY ./docker/nginx/nginx.conf /etc/nginx/conf.d/default.conf

# Копируем статические файлы из собранного фронтенда
COPY ./services/frontend/app-chaldea/dist /usr/share/nginx/html

# Открываем порт 80
EXPOSE 80

# Запускаем Nginx
CMD ["nginx", "-g", "daemon off;"]

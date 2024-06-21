# Используем минимальный образ Nginx для раздачи статики
FROM nginx:alpine

# Копируем конфигурационный файл Nginx
COPY ./nginx.conf /etc/nginx/conf.d/default.conf

# Открываем порт 80
EXPOSE 80

# Запускаем Nginx
CMD ["nginx", "-g", "daemon off;"]

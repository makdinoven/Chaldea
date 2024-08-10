FROM nginx:alpine

# Копируем конфигурационный файл Nginx
COPY ./docker/api-gateway/nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

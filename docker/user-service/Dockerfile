FROM php:8.1-fpm

# Устанавливаем системные зависимости и необходимые PHP-расширения
RUN apt-get update && apt-get install -y \
        git \
        unzip \
        libpq-dev \
        libzip-dev \
        zip \
        libxml2-dev \
        && docker-php-ext-install \
        pdo \
        pdo_mysql \
        xml \
        && docker-php-ext-enable pdo_mysql


# Устанавливаем Composer
COPY --from=composer:latest /usr/bin/composer /usr/bin/composer

# Создаем рабочую директорию
WORKDIR /var/www

# Копируем файлы и устанавливаем зависимости
COPY ./services/user-service /var/www
RUN composer install

# Устанавливаем права
RUN chown -R www-data:www-data /var/www
RUN chmod -R 755 /var/www

# Открываем порт
EXPOSE 9000

CMD ["php-fpm"]

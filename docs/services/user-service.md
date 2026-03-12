# user-service

**Порт:** 8000
**Технологии:** FastAPI, SQLAlchemy (sync), PyMySQL, JWT (python-jose), bcrypt, pika (RabbitMQ), httpx
**Путь:** `/home/dudka/chaldea/services/user-service/`

## Назначение

Регистрация, аутентификация, управление пользователями. Центральный сервис авторизации.

## Структура файлов

```
user-service/
├── main.py          # FastAPI app, все роуты
├── auth.py          # JWT токены, аутентификация
├── models.py        # SQLAlchemy модели
├── schemas.py       # Pydantic схемы
├── crud.py          # CRUD-операции
├── database.py      # Подключение к БД
├── producer.py      # RabbitMQ producer
├── alembic/         # Миграции
└── requirements.txt
```

## API Endpoints

| Метод | Путь | Описание | Auth |
|-------|------|----------|------|
| POST | `/users/register` | Регистрация нового пользователя | Нет |
| POST | `/users/login` | Логин (JWT access + refresh токены) | Нет |
| POST | `/users/refresh` | Обновление access-токена | Нет |
| GET | `/users/me` | Текущий пользователь + данные персонажа и локации | Да |
| POST | `/users/upload-avatar/` | Загрузка аватара пользователя | Да |
| PUT | `/users/{user_id}/update_character` | Установка текущего персонажа | Нет |
| POST | `/users/user_characters/` | Создание связи user-character | Нет |
| GET | `/users/all` | Все пользователи | Нет |
| GET | `/users/admins` | Все админы | Нет |
| GET | `/users/{user_id}` | Пользователь по ID | Нет |

## Таблицы БД

### users
| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer, PK | ID |
| email | String, unique | Email |
| username | String, unique | Логин |
| hashed_password | String | Bcrypt-хеш пароля |
| registered_at | DateTime | Дата регистрации |
| role | String | 'user' или 'admin' |
| avatar | String | URL аватара |
| balance | Integer | Донатный баланс |
| current_character | Integer | ID текущего персонажа |

### users_character
Связь many-to-many: `user_id` + `character_id` (composite PK)

### users_avatar_preview / users_avatar_character_preview
Превью аватаров (создаются при регистрации, но нигде не используются)

## Аутентификация (JWT)

- **Алгоритм:** HS256
- **Secret key:** `"your-secret-key"` (ЗАХАРДКОЖЕН)
- **Access token TTL:** 20 часов
- **Refresh token TTL:** 7 дней
- **Payload:** `{sub: email, role: string, current_character: int, exp: timestamp}`
- **Пароли:** bcrypt через passlib

## Коммуникация с другими сервисами

### HTTP (исходящие)
- `character-service:8005` -> `GET /characters/{id}/short_info` (в `/users/me`)
- `locations-service:8006` -> `GET /locations/{id}/details` (в `/users/me`)

### RabbitMQ (исходящие)
- Queue `user_registration` -> отправляет `{user_id}` при регистрации
- Потребитель: notification-service (создаёт welcome-уведомление)

## Известные проблемы

1. **Захардкоженный SECRET_KEY** - критическая проблема безопасности
2. **Эндпоинты без аутентификации** - `/update_character`, `/user_characters/`, `/all`, `/admins` доступны без токена
3. **Загрузка файлов без валидации** - нет проверки типа и размера файла, возможен path traversal
4. **Блокирующий RabbitMQ** - `BlockingConnection` в async-контексте FastAPI
5. **Неиспользуемые таблицы** - `users_avatar_preview` и `users_avatar_character_preview` создаются но не читаются
6. **Нет пагинации** для `/users/all` и `/users/admins`
7. **Silent failure** при недоступности locations-service (exception подавляется через `pass`)

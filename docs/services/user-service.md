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
| POST | `/users/refresh` | Обновление пары токенов: JSON body `{refresh_token}` -> `{access_token, refresh_token, token_type}` (stateless-ротация refresh-токена) | Нет (refresh-токен в body и есть credential) |
| GET | `/users/me` | Текущий пользователь + данные персонажа и локации | Да |
| POST | `/users/upload-avatar/` | Загрузка аватара пользователя | Да |
| PUT | `/users/{user_id}/update_character` | Установка текущего персонажа | Нет |
| POST | `/users/user_characters/` | Создание связи user-character | Нет |
| GET | `/users/all` | Все пользователи | Нет |
| GET | `/users/admins` | Все админы | Нет |
| GET | `/users/{user_id}` | Пользователь по ID | Нет |
| POST | `/users/internal/{user_id}/activity/increment` | Начислить очки активности. **FEAT-169:** маршрут переехал с `/users/{user_id}/activity/increment` (старый путь удалён, отдаёт 404) под закрытый префикс `/users/internal/` и требует заголовок `X-Internal-Token`. `points` теперь валидируется: `Field(1, ge=1, le=100)` — раньше принимались отрицательные значения и очки можно было списать. Единственный вызывающий — notification-service после сообщения в чат | `X-Internal-Token` |
| GET | `/users/internal/{user_id}/diamonds` | Баланс алмазов. **FEAT-170:** закрыт `X-Internal-Token`. Вызывающих в репозитории нет — маршрут закрыт, но не удалён | `X-Internal-Token` |
| POST | `/users/internal/{user_id}/diamonds/add` | Начислить алмазы (премиальная валюта, сумма не ограничена сверху). **FEAT-170:** закрыт `X-Internal-Token`. Единственный вызывающий — battle-pass-service (`crud.py` `_deliver_diamonds`) | `X-Internal-Token` |
| POST | `/users/internal/{user_id}/diamonds/spend` | Списать алмазы. **FEAT-170:** закрыт `X-Internal-Token`. Вызывающих в репозитории нет — маршрут закрыт, но не удалён | `X-Internal-Token` |
| POST | `/users/internal/{user_id}/cosmetics/unlock` | Разблокировать косметику (рамка / фон чата). **FEAT-170:** закрыт `X-Internal-Token`. Единственный вызывающий — battle-pass-service (`crud.py` `_deliver_cosmetic`) | `X-Internal-Token` |

### Internal-токен (FEAT-169, расширен в FEAT-170)

`auth.verify_internal_token` — fail-closed проверка заголовка `X-Internal-Token` против переменной окружения `INTERNAL_SERVICE_TOKEN`. Поведение то же, что в character-service / character-attributes-service / inventory-service: пустая/неустановленная переменная → **503** «Internal service token не настроен», отсутствующий или чужой заголовок → **401** «Недействительный internal token». Константа `auth.INTERNAL_SERVICE_TOKEN` читается на импорте — тесты подменяют именно её (`monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", ...)`), а не только env.

**FEAT-170:** закрыты оставшиеся четыре маршрута префикса — `GET /users/internal/{uid}/diamonds`, `POST .../diamonds/add`, `POST .../diamonds/spend`, `POST .../cosmetics/unlock`. Проверка навешивается через `dependencies=[Depends(verify_internal_token)]` в декораторе, чтобы не менять сигнатуру обработчика и тело ответа. Теперь **ни один** маршрут под `/users/internal/` не отвечает без токена; nginx (`return 403`) остаётся внешним слоем.

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
- **Secret key:** только из переменной окружения `JWT_SECRET_KEY` (`auth.py`). **FEAT-169:** fail-fast на импорте — если переменная не задана **или пуста**, сервис падает с понятным `RuntimeError` и не поднимается. Проверяется именно «правдивость», а не наличие ключа: в compose незаданная переменная разворачивается в пустую строку, и старый `os.environ["JWT_SECRET_KEY"]` пропустил бы пустой секрет. Публичный fallback `your-secret-key` из compose убран; сгенерировать значение: `openssl rand -hex 32`
- **Access token TTL:** 20 часов
- **Refresh token TTL:** 7 дней
- **Payload:** `{sub: email, role: string, current_character: int, type: "access"|"refresh", exp: timestamp}`
- **Claim `type`:** access-токены с `type=refresh` отклоняются в `get_current_user`; refresh-токены с `type=access` отклоняются в `/users/refresh`. Токены без claim (выданные до FEAT-150) принимаются везде (legacy, самоустраняется за 7 дней).
- **`/users/refresh`:** принимает `{refresh_token}` в JSON body (не query — токен не попадает в логи Nginx), возвращает новую пару access (20ч) + refresh (7д), `current_character` перечитывается из БД. Все ошибки — единый ответ 401 «Недействительный или истёкший refresh-токен».
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

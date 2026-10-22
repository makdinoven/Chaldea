# notification-service

**Порт:** 8007
**Технологии:** FastAPI, SQLAlchemy (sync), PyMySQL, pika (RabbitMQ), SSE (Server-Sent Events)
**Путь:** `/home/dudka/chaldea/services/notification-service/`

## Назначение

Уведомления в реальном времени через SSE. Приём событий через RabbitMQ (регистрация пользователей, общие уведомления). Хранение уведомлений в БД.

## Структура файлов

```
notification-service/app/
├── main.py                           # FastAPI app, SSE endpoint, CRUD endpoints
├── models.py                         # Notification модель
├── schemas.py                        # Pydantic схемы
├── database.py                       # SQLAlchemy подключение
├── auth_http.py                      # OAuth2 через HTTP-вызов к user-service
├── sse_manager.py                    # Глобальный dict connections, send_to_sse()
└── consumers/
    ├── general_notification.py       # RabbitMQ consumer: рассылки
    └── user_registration.py          # RabbitMQ consumer: welcome-уведомления
```

## API Endpoints

| Метод | Путь | Описание | Auth |
|-------|------|----------|------|
| GET | `/notifications/stream` | SSE-подключение для реальных уведомлений | Да |
| POST | `/notifications/create` | Создать общее уведомление (admin only) | Да |
| GET | `/notifications/{user_id}/unread` | Непрочитанные уведомления | Нет |
| GET | `/notifications/{user_id}/full` | Все уведомления | Нет |
| PUT | `/notifications/{user_id}/mark-as-read` | Отметить как прочитанные | Нет |
| PUT | `/notifications/{user_id}/mark-all-as-read` | Отметить все как прочитанные | Нет |
| GET | `/notifications/me/preferences` | Настройки уведомлений текущего пользователя: `{"preferences": {"messages","social","trade","party","world","progress": "all"|"bell"|"off"}}`. Отсутствующие ключи → `all`, неизвестные сохранённые ключи игнорируются | Да |
| PUT | `/notifications/me/preferences` | Частичное обновление: тело `{"preferences": {...}}`, ответ — полная форма. Неизвестная категория, недопустимый режим или обязательная категория (`battle`, `system`) → **422** «Недопустимое значение настройки уведомлений», ничего не сохраняется | Да |
| GET | `/notifications/messenger/presence/{user_id}` | `{user_id, online}` — есть ли у пользователя активное WS-подключение. Если пользователь скрыл онлайн-статус (`show_online = false` в user-service), другим всегда отдаётся `online: false`; сам пользователь видит свой статус. Флаг читается из user-service `GET /users/{id}/presence-visibility` (`messenger_routes._get_show_online`); при ошибке или не-200 — `online: false` (fail closed) | Да |
| GET | `/notifications/chat/messages?channel=` | История канала чата, постранично. **FEAT-171 (N1):** закрыта от неавторизованных — гость получает **401** «Войдите в аккаунт, чтобы читать чат» (зависимость `chat_routes.require_chat_reader`: схема с `auto_error=False` + собственное русское сообщение, дальше обычная проверка токена через user-service). Тело ответа для вошедшего не изменилось. `POST` на том же роутере уже требовал JWT, `DELETE` — `chat:delete` | Да |

## Таблица БД

### notifications
| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer, PK | ID |
| user_id | Integer | ID пользователя |
| message | Text | Текст уведомления |
| status | Enum | "unread" / "read" |
| created_at | DateTime | Дата создания |
| category | String(20), NULL | Категория (см. ниже); NULL у старых записей. Отдаётся в `/unread` и `/full` (миграция 0011) |

### notification_preferences (миграция 0011)
| Поле | Тип | Описание |
|------|-----|----------|
| user_id | Integer, PK | ID пользователя |
| settings | Text (JSON) | `{категория: режим}` |
| updated_at | DateTime | Дата изменения |

## Категории уведомлений (`notification_categories.py`)

- Настраиваемые: `messages`, `social`, `trade`, `party`, `world`, `progress`. Обязательные (никогда не фильтруются): `battle`, `system`.
- Режимы: `all` — колокольчик + всплывашка; `bell` — только колокольчик (WS-пуш с `silent: true`); `off` — не сохраняется и не пушится.
- `messages` бэкенд не фильтрует — мессенджер идёт своим WS-каналом, настройку применяет фронтенд.
- Категория сообщения = `payload.category`, если валидна; иначе по `ws_type` (`WS_TYPE_CATEGORY_MAP`); иначе `system`.
- Ошибка чтения настроек → режим `all` (fail open, уведомление не теряется).

## SSE (Server-Sent Events)

- `connections: dict[user_id, asyncio.Queue]` - in-memory маппинг
- Клиент подключается к `/notifications/stream` с Bearer-токеном
- Сервер отправляет `data: {json}\n\n` при появлении уведомлений
- Если пользователь не подключён - уведомление только в БД

## RabbitMQ Consumers (2 daemon-потока)

### user_registration consumer
- Queue: `user_registration` (durable)
- Payload: `{user_id: int}`
- Действие: создаёт welcome-уведомление "Welcome to our platform!"
- **Нет try-except** - может упасть при ошибке парсинга

### general_notifications consumer
- Queue: `general_notifications` (durable)
- Payload: `{target_type: "user"|"all"|"admins", target_value: int, message: str, category?: str, ws_type?: str, ws_data?: dict}`
- Логика в `handle_notification()`: для `user` применяется режим из `notification_preferences` (`off` → пропуск, `bell` → `silent: true`); `all`/`admins` не фильтруются (категория `system`, если не указана).
- Каждый WS-пуш содержит в `data` поля `category` и `silent` (и для `{type: ws_type}`, и для `{type: "notification"}`).
- Производители и категории: character-service → `progress`; battle-service → `battle` (события боевых групп `party_*`, кроме `party_started`, → `party`); party-service → `party`; inventory-service (обмен, аукцион) → `trade`; locations-service → `world`; user-service (`friend_request`, `friend_accepted`, `wall_post`) → `social`; тикеты, админская рассылка `/create`, приветствие при регистрации → `system`.
- Роутинг:
  - `user`: уведомление одному пользователю
  - `all`: HTTP -> user-service `/users/all`, уведомление каждому
  - `admins`: HTTP -> user-service `/users/admins`, уведомление каждому админу

## Аутентификация

**Через HTTP-вызов к user-service** (не локальная JWT-валидация):
- OAuth2 Bearer -> HTTP GET `user-service:8000/users/me` с тем же токеном
- Возвращает UserRead с id, username, role

## Коммуникация

### HTTP (исходящие)
- `user-service:8000` -> GET `/users/me` (валидация токена)
- `user-service:8000` -> GET `/users/all` (рассылка всем)
- `user-service:8000` -> GET `/users/admins` (рассылка админам)
- `user-service:8000` -> GET `/users/{uid}/presence-visibility` (скрытие онлайн-статуса в `/messenger/presence`, fail closed)
- `user-service:8000` -> POST `/users/internal/{uid}/activity/increment` (+ `X-Internal-Token`) — очки активности за сообщение в чат, `chat_routes.send_message` шаг 9. FEAT-169: маршрут переехал с открытого `/users/{uid}/activity/increment` под закрытый префикс `/users/internal/` и требует internal-токен. У notification-service раньше не было ни переменной `INTERNAL_SERVICE_TOKEN`, ни хелпера заголовка — добавлен локальный `chat_routes.internal_token_headers()` (читает env **на момент вызова**), переменная заведена в обоих compose-файлах. Вызов остаётся best-effort (отправка сообщения не падает), но `except: pass` заменён на `logger.warning` — иначе потеря заголовка навсегда и молча остановила бы начисление очков

### RabbitMQ (входящие)
- Queue `user_registration` <- user-service
- Queue `general_notifications` <- любой сервис (через POST `/create`)

## Известные проблемы

1. **Thread safety** - `send_to_sse()` через `asyncio.run_coroutine_threadsafe()` из sync consumer threads
2. **Нет error handling** в user_registration consumer
3. **Нет пагинации** - GET endpoints возвращают все уведомления сразу
4. **Session leak** - consumers вызывают `next(get_db())` без cleanup при exception
5. **Нет валидации** user_id при создании уведомления

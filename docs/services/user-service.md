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
| POST | `/users/logout` | Выход: body `{refresh_token}` → удаляет сессию (`sid`) этого токена, закрывает её сокеты. Подпись проверяется, срок — нет; идемпотентно (уже удалённая сессия / legacy-токен без `sid` → тоже 200 `{"detail": "Вы вышли из аккаунта"}`); битый токен → 401 | Токен в body |
| GET | `/users/me/sessions` | `{"sessions": [{id, created_at, last_used_at, user_agent, current}]}`, сначала недавно использованные; `current` — сессия этого токена. Протухшие (>7 дней без использования) удаляются перед выдачей | Да |
| DELETE | `/users/me/sessions/{id}` | Завершить свою сессию (текущую — тоже, это выход). Чужая/несуществующая → 404 «Сессия не найдена». 200 `{"detail": "Сессия завершена"}` | Да |
| POST | `/users/me/sessions/revoke-others` | Завершить все сессии, кроме текущей, + `tokens_valid_after = now` (убивает legacy-токены). 200 `{"detail": "Остальные сеансы завершены", "revoked": N}` | Да |
| PUT | `/users/me/password` | `{current_password, new_password}`. 400: «Неверный текущий пароль» / правило регистрации (6–128) / «Новый пароль совпадает с текущим». Успех: остальные сессии завершены, `tokens_valid_after = now`, 200 `{"detail": "Пароль изменён"}`; текущая сессия остаётся | Да |
| PUT | `/users/me/email` | `{new_email, password}`. 400 «Неверный пароль» / «Это ваша текущая почта» (без учёта регистра); 409 «Эта почта уже занята» (без учёта регистра); 422 — невалидный адрес. Успех: `{access_token, refresh_token, token_type}` — новая пара **той же** сессии, клиент обязан заменить токены. Письмо не отправляется (почтового стека нет) | Да |
| GET | `/users/me` | Текущий пользователь + данные персонажа и локации | Да |
| POST | `/users/upload-avatar/` | Загрузка аватара пользователя | Да |
| PUT | `/users/{user_id}/update_character` | Установка текущего персонажа | Нет |
| POST | `/users/user_characters/` | Создание связи user-character | Нет |
| GET | `/users/all` | Все пользователи | Нет |
| GET | `/users/admins` | Все админы. **FEAT-171 (фикс по ревью #2):** отвечает `schemas.UserPublicRead` — без `email`. Раньше отдавал `UserRead` и одним анонимным запросом раскрывал адреса всех администраторов | Нет |
| GET | `/users/{user_id}` | Карточка пользователя по ID. **FEAT-171 (фикс по ревью #2):** `email` — персональные данные и отдаётся только самому пользователю и админу/модератору с правом `users:read` (`schemas.UserRead`); всем остальным, включая гостя, уходит `schemas.UserPublicRead`, где ключа `email` **нет вовсе** (не null). Межсервисные вызывающие читают отсюда только `username`, поэтому внутренний двойник не нужен | Опционально (`get_optional_user`) |
| GET | `/users/{user_id}/profile` | Профиль пользователя со стеной, статистикой постов и карточкой активного персонажа. **FEAT-171 (U1):** золото персонажа приватно — ключ `character.currency_balance` есть только у самого владельца профиля и у админа/модератора **с правом `characters:read`** (`schemas.UserProfileResponse`); все остальные, включая гостя и модератора с отозванным правом, получают `schemas.UserProfileStrangerResponse` с `CharacterShortPublic`, где этого ключа **нет вовсе** (не null). `/users/me` баланс сохраняет. **Фикс по ревью #4/#5:** правило приведено к той же формуле, что и `visibility.can_view_private` в четырёх сервисах фичи (роль **и** разрешение — одной роли мало), а наследование схем перевёрнуто: публичная `UserProfileStrangerResponse` теперь база, приватная `UserProfileResponse` её расширяет, поэтому новое приватное поле не может просочиться чужому зрителю по наследству. Та же инверсия сделана в паре `UserPublicRead` → `UserRead` | Опционально (`get_optional_user`) |
| GET | `/users/me/privacy` | Все настройки приватности: `{message_privacy, wall_view_privacy, wall_post_privacy, friends_list_privacy, friend_request_privacy, show_online}` | Да |
| PUT | `/users/me/privacy` | Частичное обновление тех же шести полей (только переданные). Недопустимое значение (или `null`) → **422** «Недопустимое значение настройки приватности», ничего не применяется. `friend_request_privacy` принимает только `all`/`nobody`, `show_online` — строго bool. Ответ — полный набор. Старый `PUT /users/me/message-privacy` работает как раньше | Да |
| GET | `/users/{user_id}/presence-visibility` | `{show_online: bool}`; 404, если пользователя нет. Используется notification-service для `/messenger/presence` | Нет |
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
| message_privacy | Enum(all, friends, nobody) | Кто может писать в личку (0020) |
| wall_view_privacy | String(10), default 'all' | Кто видит стену: all/friends/nobody (0030) |
| wall_post_privacy | String(10), default 'all' | Кто может писать на стене: all/friends/nobody (0030) |
| friends_list_privacy | String(10), default 'all' | Кто видит список друзей: all/friends/nobody (0030) |
| friend_request_privacy | String(10), default 'all' | Принимать ли заявки в друзья: all/nobody (0030) |
| show_online | Boolean, default true | Показывать ли онлайн-статус и `last_active_at` другим (0030) |
| site_background_url | String(512), NULL | Личный фон всего сайта (настройки аккаунта, 0030) |
| tokens_valid_after | DateTime, NULL | Пока NULL — legacy-токены без `sid` принимаются; ставится при «завершить остальные сеансы» и смене пароля (0031) |

### user_sessions (миграция 0031)
| Поле | Тип | Описание |
|------|-----|----------|
| id | String(32), PK | uuid4 hex — уходит в claim `sid` обоих токенов |
| user_id | Integer, FK users.id ON DELETE CASCADE, index | Владелец |
| created_at | DateTime | Вход |
| last_used_at | DateTime | Последнее использование (обновляется не чаще раза в 5 минут; refresh — всегда) |
| user_agent | String(255), NULL | Заголовок User-Agent при входе (обрезается) |

## Приватность (миграция 0030)

**Правило аудитории** (`main._audience_allows`, одно на все настройки): владелец — всегда; `all` — любой, включая гостя; `friends` — у зрителя есть дружба `accepted` с владельцем (в любом направлении); `nobody` — только владелец. Обхода для админа/модератора **нет**. Неизвестное значение трактуется как `nobody` (fail closed).

Применение:
- `GET /users/{id}/wall/posts` — опциональный зритель; запрет → **403** «Пользователь скрыл свою стену».
- `POST /users/{id}/wall/posts` — блокировка в любую сторону → **403** «Вы не можете писать на стене этого пользователя»; иначе запрет по `wall_post_privacy` → **403** «Пользователь ограничил записи на своей стене». Владелец на своей стене пишет всегда.
- `GET /users/{id}/friends` — опциональный зритель; запрет → **403** «Пользователь скрыл список друзей».
- `POST /users/friends/request` — после поиска цели: блокировка в любую сторону → **403** «Нельзя отправить заявку этому пользователю»; `friend_request_privacy = nobody` → **403** «Пользователь не принимает заявки в друзья». Прежние 400/404 сохранены (самого себя → 400 идёт раньше, 404 — раньше 403, «уже друзья»/«запрос уже существует» — после).
- `show_online = false`: пользователь не попадает в `GET /users/online`, не считается в `online_users` у `GET /users/stats`, его `last_active_at` = null в `GET /users/all`, `GET /users/{id}/friends` и `GET /users/{id}/profile` — для всех, кроме него самого (в `/all` и `/friends` зритель определяется опционально по токену). notification-service скрывает его в `/messenger/presence`.
- `GET /users/{id}/profile` отдаёт `viewer_permissions: {can_view_wall, can_post_wall, can_view_friends, can_send_friend_request}` для текущего (опционального) зрителя. `can_post_wall` требует логина и отсутствия блокировки; `can_send_friend_request` — логин, не владелец, `friend_request_privacy = all`, нет блокировки и нет существующей дружбы/заявки. Если `can_view_wall = false`, `post_stats` = null (иначе раскрывалась бы активность стены).

**Фон сайта:** `PUT /users/me/settings` принимает `site_background_url` — пустая строка/`null` очищают (NULL в БД); иначе ссылка обязана начинаться с `http://`/`https://` (**422** «Ссылка на фон сайта должна начинаться с http:// или https://»), быть не длиннее 512 символов (**422** «...слишком длинная...») и не содержать пробелов, кавычек, скобок, `<>`, `\` (**422** «...содержит недопустимые символы» — защита от выхода из CSS `url(...)`). Возвращается в `ProfileSettingsResponse` и в `GET /users/me`.

### users_character
Связь many-to-many: `user_id` + `character_id` (composite PK)

### users_avatar_preview / users_avatar_character_preview
Превью аватаров (создаются при регистрации, но нигде не используются)

## Аутентификация (JWT)

- **Алгоритм:** HS256
- **Secret key:** только из переменной окружения `JWT_SECRET_KEY` (`auth.py`). **FEAT-169:** fail-fast на импорте — если переменная не задана **или пуста**, сервис падает с понятным `RuntimeError` и не поднимается. Проверяется именно «правдивость», а не наличие ключа: в compose незаданная переменная разворачивается в пустую строку, и старый `os.environ["JWT_SECRET_KEY"]` пропустил бы пустой секрет. Публичный fallback `your-secret-key` из compose убран; сгенерировать значение: `openssl rand -hex 32`
- **Access token TTL:** 20 часов
- **Refresh token TTL:** 7 дней
- **Payload:** `{sub: email, uid: int, sid: str, role: string, current_character: int, type: "access"|"refresh", iat, exp}`. Пользователь ищется по `uid` (если есть), иначе по `sub` (legacy).
- **Сессии (миграция 0031, `sessions.py`):** login/register создают строку `user_sessions`; её id — claim `sid` в обоих токенах пары. `get_current_user` (а значит `/users/me`, через который все сервисы проверяют токен) требует, чтобы сессия существовала, принадлежала пользователю и не простаивала дольше 7 дней — иначе **401 «Сессия завершена. Войдите снова.»**. `last_used_at` обновляется не чаще раза в 5 минут. `get_optional_user` применяет ту же проверку (отозванный токен = гость).
- **Legacy-токены без `sid`** (выданы до 0031) принимаются, пока `users.tokens_valid_after` NULL. Legacy refresh-токен в `/users/refresh` создаёт новую сессию и выдаёт пару с `sid` — так действующие игроки мигрируют без разлогина. После «завершить остальные сеансы»/смены пароля legacy-токены отклоняются.
- **Протухшие сессии** (>7 дней без использования) удаляются лениво — при логине, refresh и выдаче списка сессий (только для этого пользователя).
- **Закрытие WebSocket-ов:** после отзыва сессий (DELETE сессии, revoke-others, смена пароля, logout) user-service фоновой задачей шлёт `POST notification-service /notifications/internal/sessions/revoked` с `X-Internal-Token` (`sessions.notify_sessions_revoked`, таймаут 3с). Best effort: недоступность notification-service только логируется. URL — `NOTIFICATION_SERVICE_URL` (по умолчанию `http://notification-service:8007`).
- **Rate limit (nginx, оба конфига):** `/users/login`, `/users/register`, `/users/me/password`, `/users/me/email` — зона `auth_limit` 5 r/m, burst 4 (6-я быстрая попытка → 429); `/users/refresh` — `refresh_limit` 60 r/m, burst 30. 429 отдаётся JSON `{"detail":"Слишком много попыток. Подождите минуту и попробуйте снова."}`.
- **Claim `type`:** access-токены с `type=refresh` отклоняются в `get_current_user`; refresh-токены с `type=access` отклоняются в `/users/refresh`. Токены без claim (выданные до FEAT-150) принимаются везде (legacy, самоустраняется за 7 дней).
- **`/users/refresh`:** принимает `{refresh_token}` в JSON body (не query — токен не попадает в логи Nginx), возвращает новую пару access (20ч) + refresh (7д) с тем же `sid`, `current_character` перечитывается из БД. Отозванная сессия → 401. Все ошибки — единый ответ 401 «Недействительный или истёкший refresh-токен».
- **Пароли:** bcrypt через passlib

## Коммуникация с другими сервисами

### HTTP (исходящие)
- `character-service:8005` -> `GET /characters/internal/{id}/short_info` (+ `X-Internal-Token`, в `/users/me` и `/users/{id}/profile`). **FEAT-171:** публичный `short_info` больше не отдаёт `currency_balance`, а счётчик золота в шапке собирается именно из него — поэтому `_fetch_character_short` ходит во внутренний двойник. Вызов best-effort (ошибка → персонаж просто не подставится), но теперь пишет WARNING с URL двойника, чтобы потеря заголовка не выглядела как «золота нет»
- `locations-service:8006` -> `GET /locations/{id}/details` (в `/users/me`)

### RabbitMQ (исходящие)
- Queue `user_registration` -> отправляет `{user_id}` при регистрации
- Потребитель: notification-service (создаёт welcome-уведомление)
- Queue `general_notifications` -> социальные уведомления (`producer.send_social_notification`, категория `social`, через `BackgroundTasks`, ошибки RabbitMQ только логируются):
  - `POST /users/friends/request` → цели: «{username} хочет добавить вас в друзья», `ws_type: friend_request`, `ws_data: {from_user_id, from_username, friendship_id}`
  - `PUT /users/friends/request/{id}/accept` → отправителю заявки: «{username} теперь у вас в друзьях», `ws_type: friend_accepted`, `ws_data: {user_id, username}`
  - `POST /users/{id}/wall/posts` (не на своей стене) → владельцу стены: «Новая запись на вашей стене от {username}», `ws_type: wall_post`, `ws_data: {author_id, author_username, post_id}`

## Известные проблемы

1. **Захардкоженный SECRET_KEY** - критическая проблема безопасности
2. **Эндпоинты без аутентификации** - `/update_character`, `/user_characters/`, `/all`, `/admins` доступны без токена (утечка e-mail через `/admins` и `/{user_id}` закрыта в FEAT-171, но сами маршруты по-прежнему анонимны)
3. **Загрузка файлов без валидации** - нет проверки типа и размера файла, возможен path traversal
4. **Блокирующий RabbitMQ** - `BlockingConnection` в async-контексте FastAPI
5. **Неиспользуемые таблицы** - `users_avatar_preview` и `users_avatar_character_preview` создаются но не читаются
6. **Нет пагинации** для `/users/all` и `/users/admins`
7. **Silent failure** при недоступности locations-service (exception подавляется через `pass`)


## FEAT-175: блокировка активности в `/users/me`

`character.activity_lock` (из `/characters/internal/{id}/short_info`):
`{"locked": bool, "reason": "dungeon"|"unconscious"|null, "until": iso|null, "dungeon_session_id": int|null}` —
для баннера «в подземелье» / «без сознания до …». Публичный профиль поле не отдаёт.

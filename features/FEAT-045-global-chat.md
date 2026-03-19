# FEAT-045: Глобальный чат

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-19 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-045-global-chat.md` → `DONE-FEAT-045-global-chat.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Глобальный чат на сайте в виде выдвижного виджета. Игроки общаются в реальном времени от лица своего профиля. Чат доступен на всех страницах сайта.

### Бизнес-правила
- Чат-виджет расположен в левом нижнем углу сайта, открывается по клику на заметную иконку
- 3 канала с переключением вверху: "Общий", "Торговля", "Помощь"
- Сообщения от лица профиля пользователя: отображается аватарка профиля (квадратная) и настроенная рамка профиля
- Поле ввода сообщений вверху виджета
- Кнопка-заглушка для смайликов (в будущем — picker как в Discord/Telegram)
- Новые сообщения всегда вверху (обратный хронологический порядок)
- Функция "Ответить" и "Цитировать" на сообщения
- Сообщения обновляются мгновенно у всех онлайн-игроков (real-time)
- Хранятся последние 500 сообщений на канал
- В виджете — последняя страница сообщений; кнопка "История чата" открывает отдельную страницу с полноценным просмотром и пагинацией
- Модерация: админы/модераторы могут удалять сообщения и банить пользователей в чате
- Чат доступен на всех страницах сайта (для всех посетителей, писать — только залогиненным)

### UX / Пользовательский сценарий
1. Игрок видит иконку чата в левом нижнем углу на любой странице
2. Кликает — раскрывается виджет чата
3. Вверху виджета — вкладки "Общий" / "Торговля" / "Помощь"
4. Видит последние сообщения (новые сверху)
5. Вводит сообщение в поле ввода вверху, отправляет
6. Сообщение мгновенно появляется у всех
7. Может навести на чужое сообщение → "Ответить" / "Цитировать"
8. Цитата отображается как вложенный блок (аналог Discord)
9. Кнопка "История чата" → переход на отдельную страницу с пагинацией
10. Админ/модератор видит кнопку удаления на каждом сообщении

### Edge Cases
- Что если пользователь не залогинен? → Видит чат (read-only), не может писать
- Что если пользователь забанен в чате? → Видит сообщения, но не может писать, отображается уведомление
- Что если сообщение удалено модератором? → Исчезает у всех в реальном времени
- Что если канал пуст? → Показать placeholder "Нет сообщений"
- Что если превышен лимит 500 сообщений? → Самые старые удаляются автоматически

### Вопросы к пользователю (если есть)
- Все вопросы уточнены.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Key Files |
|---------|----------------|-----------|
| notification-service | Extend with chat SSE broadcast, new chat endpoints, new models | `app/main.py`, `app/models.py`, `app/schemas.py`, `app/sse_manager.py`, `app/database.py`, `app/auth_http.py` |
| user-service | New Alembic migration for `chat:*` permissions, possible chat-ban field | `models.py`, `alembic/versions/` |
| frontend | New chat widget component, new chat history page, new Redux slice, new SSE channel, new route | `src/components/App/Layout/Layout.tsx`, `src/components/App/App.tsx`, `src/redux/store.ts`, `src/hooks/useSSE.ts` (reuse) |
| api-gateway (Nginx) | No changes needed — chat endpoints live under `/notifications/` prefix (existing SSE-enabled route) or a new `/chat/` prefix if a separate service is created |
| Docker | If new service: new Dockerfile + docker-compose entries. If extending notification-service: no Docker changes |

### Investigation: notification-service SSE Infrastructure

**Current SSE architecture** (`services/notification-service/app/`):
- `sse_manager.py`: Global in-memory dict `connections: dict[user_id, asyncio.Queue]`. Function `send_to_sse(user_id, data)` puts JSON into the user's queue using `asyncio.run_coroutine_threadsafe()` (called from sync RabbitMQ consumer threads).
- `main.py:52-69`: SSE endpoint `GET /notifications/stream` — authenticates via `get_current_user_via_http`, creates `asyncio.Queue` per user, returns `StreamingResponse` with `text/event-stream`. Yields `data: {json}\n\n` format.
- **Key limitation**: Current SSE is **per-user unicast** — each user has their own queue. There is NO broadcast/channel mechanism. For chat, we need to broadcast a message to ALL connected users (or all users subscribed to a channel).
- **RabbitMQ consumers** run in daemon threads (`threading.Thread`), using `pika.BlockingConnection`. They call `send_to_sse()` from sync context via `asyncio.run_coroutine_threadsafe()`.
- **No Alembic** — notification-service uses `Base.metadata.create_all(bind=engine)` in startup (line 44). Per T2 rules, Alembic must be added if this service is modified.
- **Sync SQLAlchemy** with PyMySQL — `database.py` uses standard sync `create_engine` + `sessionmaker`.
- **Auth**: `auth_http.py` validates JWT by calling `GET user-service:8000/users/me` with Bearer token. Returns `UserRead(id, username, role, permissions)`. Has `require_permission()` dependency factory.

**Can notification-service be extended for chat?**
- **Pros**: Already has SSE infrastructure, auth, RabbitMQ integration, FastAPI setup. Adding chat endpoints here avoids a new service.
- **Cons**: Current SSE is unicast (per-user). Chat requires broadcast to all connected users on a channel. The `connections` dict and `send_to_sse()` need significant changes (channel subscriptions, broadcast). Notification-service also has known issues (thread safety, session leaks). Adding chat increases complexity.
- **Recommendation for Architect**: Either extend notification-service with a broadcast mechanism (add a `broadcast_to_all()` function that iterates all connected queues), OR create a new `chat-service` on a dedicated port. The broadcast approach in notification-service is feasible but needs careful design to avoid performance issues with many connections.

### Investigation: user-service Auth & RBAC

**JWT Authentication** (`services/user-service/auth.py`):
- HS256, hardcoded secret key `"your-secret-key"`
- Access token TTL: 20 hours, Refresh: 7 days
- Payload: `{sub: email, role: string, current_character: int, exp: timestamp}`
- Token stored in `localStorage` on frontend

**User model** (`services/user-service/models.py`):
- `User` table fields relevant to chat: `id`, `username`, `avatar` (S3 URL string), `avatar_frame` (string, e.g. "gold", "silver", "fire"), `role` (string), `role_id` (FK to `roles`)
- Avatar frame is stored as a string ID (e.g. "gold") in `users.avatar_frame`. The frame rendering logic (border style, shadow) is **defined on the frontend** in `ProfileSettingsModal.tsx` as `AVATAR_FRAMES` constant array.
- No `chat_banned` or similar field exists currently.

**RBAC system** (`services/user-service/models.py` lines 6-45):
- Tables: `roles` (name, level), `permissions` (module, action), `role_permissions` (many-to-many), `user_permissions` (per-user overrides with grant/revoke)
- Admin (level=100) auto-gets ALL permissions
- Existing permission modules: `characters`, `items`, `skills`, `locations`, `users`, `notifications`, `battles`, `rules`, `races`
- Pattern for adding permissions: Alembic migration that inserts into `permissions` table and `role_permissions` for relevant roles (see `0007_add_remaining_permissions.py`, `0009_add_races_permissions.py`)
- `require_permission("module:action")` dependency used in notification-service and other services via `auth_http.py`
- Frontend: `hasPermission()`, `hasModuleAccess()` from `src/utils/permissions.ts`, `ProtectedRoute` component

**For chat moderation, we need:**
- New permissions: `chat:delete` (delete messages), `chat:ban` (ban users from chat)
- New Alembic migration in user-service to insert these permissions and assign to admin/moderator roles

### Investigation: photo-service & Avatar Rendering

**Avatar URLs**: Stored as full S3 URLs in `users.avatar` column. Photo-service uploads to S3 (`s3.twcstorage.ru`) under `user_avatars/` prefix. URLs look like `https://s3.twcstorage.ru/bucket/user_avatars/user_1_abc123.webp`.

**Avatar frame rendering** (frontend-only):
- Frame data defined in `src/components/UserProfilePage/ProfileSettingsModal.tsx`:
  ```
  AVATAR_FRAMES = [
    { id: 'gold', borderStyle: '3px solid #f0d95c', shadow: '0 0 12px rgba(240,217,92,0.4)' },
    { id: 'silver', borderStyle: '3px solid #c0c0c0', shadow: '0 0 12px rgba(192,192,192,0.4)' },
    { id: 'fire', borderStyle: '3px solid #ff6347', shadow: '0 0 15px rgba(255,99,71,0.5)' },
  ]
  ```
- `AvatarFramePreview.tsx`: Renders a 60x60 rounded-[12px] container with `border` and `boxShadow` inline styles from frame data.
- `UserProfilePage.tsx` (line 168-178): Looks up `AVATAR_FRAMES.find(f => f.id === profile.avatar_frame)` and applies as inline CSS.
- **For chat**: The chat widget needs to render user avatar + frame. It must import/share the `AVATAR_FRAMES` constant and render a small (e.g. 32-40px) square avatar with the appropriate border/shadow style. The `avatar_frame` string ID needs to be included in chat message data.

### Investigation: Frontend Layout & Structure

**Layout** (`src/components/App/Layout/Layout.tsx`):
- Wraps all authenticated pages with `<Header />`, `<Outlet />`, `<Footer />`
- The chat widget should be placed in `Layout.tsx` as a sibling of `<Outlet />`, positioned fixed in the bottom-left corner.
- Layout already uses `useSSE('/notifications/stream', handleSSEEvent)` — chat SSE can be a separate connection or multiplexed on the same stream with event types.

**App routing** (`src/components/App/App.tsx`):
- All routes under `/*` use `<Layout />` — chat widget will be visible everywhere.
- StartPage (`/`) does NOT use Layout — chat will NOT be visible on the login page (correct behavior).
- Chat history page needs a new route, e.g. `<Route path="chat/history" element={<ChatHistoryPage />} />`

**Existing SSE hook** (`src/hooks/useSSE.ts`):
- Custom hook using `fetch` + `ReadableStream` (not native EventSource) to support `Authorization` header.
- Reconnection with exponential backoff (1s to 30s max).
- Parses `data: {json}\n\n` SSE format.
- **Reusable for chat** — can either: (a) add a second `useSSE('/chat/stream', ...)` call, or (b) multiplex events on the existing notification stream with an event `type` field to distinguish notifications from chat messages.

**Redux store** (`src/redux/store.ts`):
- 16 slices currently registered. A new `chatSlice` needs to be added.
- Pattern: `createSlice` + `createAsyncThunk` + typed selectors. All slices use TypeScript.
- `notificationSlice.ts` is a good template for the chat slice (has SSE event handling, pagination, async thunks).

**Design system** (`docs/DESIGN-SYSTEM.md`):
- Dark fantasy RPG theme. Gold accent, blue for interaction, airy backgrounds.
- Key classes for chat widget: `gray-bg` (container background), `gold-text` (channel titles), `gold-scrollbar` (message list scroll), `dropdown-menu`/`dropdown-item` (context menus for reply/quote), `input-underline` (message input), `btn-blue` (send button), `modal-overlay`/`modal-content` (if needed for ban confirmation), `site-tooltip` (hover actions).
- Motion animations: use `AnimatePresence` for widget open/close, `motion.div` for message enter animations.
- Must be responsive (360px+ per T5).

### Investigation: Database Changes Needed

**New tables** (in shared MySQL `mydatabase`):

1. **`chat_messages`** — Core message storage
   - `id` (Integer, PK, auto-increment)
   - `channel` (Enum: "general", "trade", "help")
   - `user_id` (Integer, FK to `users.id`)
   - `username` (String — denormalized for fast reads)
   - `avatar` (String — denormalized, S3 URL at time of send)
   - `avatar_frame` (String — denormalized, frame ID at time of send)
   - `content` (Text, message body)
   - `reply_to_id` (Integer, nullable, FK to `chat_messages.id` — for reply/quote)
   - `created_at` (DateTime)
   - Indexes: `(channel, created_at)` for pagination, `(user_id)` for ban lookups

2. **`chat_bans`** — Chat ban tracking
   - `id` (Integer, PK)
   - `user_id` (Integer, FK to `users.id`, unique)
   - `banned_by` (Integer, FK to `users.id`)
   - `reason` (String, nullable)
   - `banned_at` (DateTime)
   - `expires_at` (DateTime, nullable — null = permanent)

**Alembic considerations**:
- notification-service does NOT have Alembic (per T2, it must be added).
- If chat tables are owned by notification-service, Alembic must be initialized there with `version_table = "alembic_version_notification"`.
- user-service needs a new migration for `chat:delete` and `chat:ban` permissions.

**Message retention**: Business rule is 500 messages per channel. This can be enforced by a cleanup task (delete oldest when count > 500 per channel) either via a periodic cron/celery task or triggered on insert.

### Investigation: Pagination Pattern

Existing pagination pattern used in notification-service and other services:
```python
page: int = Query(1, ge=1)
page_size: int = Query(50, ge=1, le=100)
total = query.count()
items = query.offset((page - 1) * page_size).limit(page_size).all()
return {"items": items, "total": total, "page": page, "page_size": page_size}
```
Chat history page should follow this exact pattern.

### Investigation: Docker/Nginx

**If extending notification-service** (recommended path):
- No Docker changes needed — notification-service already exists in `docker-compose.yml` and `docker-compose.prod.yml`.
- Nginx already has `/notifications/` route with SSE-friendly config (no buffering, 3600s timeout). Chat endpoints under this prefix would inherit these settings automatically.
- If chat uses a separate SSE endpoint (e.g. `/notifications/chat/stream`), Nginx SSE config already covers it.

**If creating a new chat-service**:
- New Dockerfile in `docker/chat-service/Dockerfile`
- New entries in both `docker-compose.yml` and `docker-compose.prod.yml`
- New Nginx upstream + location block in both `nginx.conf` and `nginx.prod.conf` (must include SSE settings: `proxy_buffering off`, `chunked_transfer_encoding off`, `proxy_read_timeout 3600`)
- New entry in CI/CD matrix (`.github/workflows/ci.yml`)
- More operational overhead

### Existing Patterns Summary

| Pattern | Where Found | Details |
|---------|------------|---------|
| SSE real-time push | notification-service `sse_manager.py` | In-memory dict per user, asyncio.Queue, StreamingResponse |
| RabbitMQ consumers | notification-service `consumers/` | Daemon threads with pika.BlockingConnection, call send_to_sse() |
| Pagination | notification-service, inventory-service, character-service | `page`/`page_size` Query params, returns `{items, total, page, page_size}` |
| Auth via HTTP proxy | notification-service `auth_http.py` | Bearer token forwarded to `user-service:8000/users/me` |
| Permission check | notification-service, locations-service, character-service | `require_permission("module:action")` dependency |
| Admin endpoints | locations-service, character-service, notification-service | `Depends(require_permission(...))` on route |
| Alembic migrations | user-service (10 migrations) | Sequential numbering `0001_...`, `0002_...` |
| Permission seeding | user-service `alembic/versions/0007_*.py` | `op.bulk_insert()` into `permissions` + `role_permissions` |
| Frontend SSE hook | `src/hooks/useSSE.ts` | fetch + ReadableStream, auth header, reconnect with backoff |
| Redux slice | `src/redux/slices/notificationSlice.ts` | TypeScript, createAsyncThunk, typed selectors, PaginatedResponse |
| Avatar frame render | `UserProfilePage.tsx`, `AvatarFramePreview.tsx` | Lookup by frame ID string, apply border/shadow inline CSS |
| Design system | `docs/DESIGN-SYSTEM.md`, `src/index.css` | gold-text, gray-bg, gold-scrollbar, btn-blue, input-underline, dropdown-menu |

### Cross-Service Dependencies

- **Chat -> user-service** (auth): Chat endpoints need JWT validation via `get_current_user_via_http()` (existing pattern in notification-service)
- **Chat -> user-service** (RBAC): Moderation endpoints need `require_permission("chat:delete")` / `require_permission("chat:ban")`
- **Chat -> user-service** (user data): Need user's `avatar`, `avatar_frame`, `username` for message display — available from auth response or fetched separately
- **Frontend -> notification-service/chat**: SSE stream for real-time messages, REST for history/send/delete/ban
- **No dependency on**: character-service, inventory-service, skills-service, locations-service, battle-service

### Risks

| Risk | Description | Mitigation |
|------|-------------|------------|
| SSE broadcast scalability | Current SSE is unicast. Broadcasting to all connected users (iterating all queues) could be slow with many users | Use RabbitMQ fanout exchange or Redis Pub/Sub for broadcast. Keep SSE queues but feed them from a shared broadcast channel |
| notification-service complexity | Adding chat to notification-service significantly increases its scope | Keep chat code in separate files (e.g. `chat_models.py`, `chat_routes.py`). Alternatively, create a dedicated chat-service |
| No Alembic in notification-service | T2 requires adding Alembic when modifying this service. Must be done as a separate commit | Initialize Alembic with `version_table="alembic_version_notification"`, create initial migration for existing `notifications` table, then add chat tables in a follow-up migration |
| Denormalized user data in messages | Username/avatar stored in message for fast reads. If user changes avatar, old messages show old avatar | This is standard chat behavior (Discord/Telegram do the same). Acceptable tradeoff |
| Message retention cleanup | 500 messages per channel limit needs enforcement | Periodic cleanup after each insert, or a scheduled task. Must handle the case where delete cascades to reply_to_id references |
| Mixed sync/async in notification-service | Service uses sync SQLAlchemy but async SSE. RabbitMQ consumers are sync threads. Chat broadcast adds more async/sync boundary complexity | Follow existing pattern: sync DB operations, async SSE via `run_coroutine_threadsafe()` |
| Frontend bundle size | New chat widget + history page + Redux slice | Lazy-load chat history page. Widget itself should be small |
| Mobile UX | Chat widget must work on 360px+ screens | Use responsive Tailwind classes, collapsible widget, possibly full-screen on mobile |

---

## 3. Architecture Decision (filled by Architect — in English)

### Decision 1: Extend notification-service (not a new service)

**Choice:** Extend notification-service with chat functionality.

**Justification:**
- notification-service already has SSE infrastructure, JWT auth via HTTP proxy, CORS, and Nginx SSE-friendly routing (`/notifications/` prefix with `proxy_buffering off`, 3600s timeout).
- Creating a new chat-service would require: new Dockerfile, two docker-compose entries, two Nginx config changes, CI/CD matrix update — significant operational overhead for a feature that shares the same real-time delivery pattern.
- The scope increase is manageable by keeping chat code in dedicated files (`chat_models.py`, `chat_schemas.py`, `chat_routes.py`, `chat_crud.py`) separate from notification logic.
- Both notification-service and chat share the same auth pattern and SSE transport.

**Risk mitigation:** Strict file separation — all chat logic in `chat_*.py` files. If notification-service becomes too large in the future, extracting chat into its own service will be straightforward because the code is already isolated.

### Decision 2: SSE Broadcast via In-Memory Channel Subscriptions

**Choice:** Extend `sse_manager.py` with channel-based subscriptions and a `broadcast_to_channel()` function. No RabbitMQ fanout or Redis Pub/Sub for broadcast.

**Justification:**
- The current SSE system uses in-memory `asyncio.Queue` per user. For chat broadcast, we add a second dict: `channel_subscriptions: dict[str, set[int]]` mapping channel name to a set of user_ids.
- When a user subscribes to a chat SSE stream, they are added to a channel set. `broadcast_to_channel(channel, data)` iterates the subscribed user_ids and puts the message into each user's queue.
- This is simple, has no external dependency, and is sufficient for a single-instance deployment (which Chaldea is — one Docker Compose on one VPS).
- RabbitMQ fanout or Redis Pub/Sub would add complexity without benefit for a single-instance setup. If Chaldea ever scales to multiple instances, Redis Pub/Sub can be added then.

**Implementation:**
- Add `chat_connections: dict[int, asyncio.Queue]` — separate from notification connections (so chat SSE is a separate stream endpoint).
- Add `channel_subscriptions: dict[str, set[int]]` — tracks which users are subscribed to which channels.
- `subscribe(user_id, channel)` / `unsubscribe(user_id, channel)` / `broadcast_to_channel(channel, data)` functions.
- Separate SSE endpoint: `GET /notifications/chat/stream?channel=general` — one SSE connection per user, they switch channels by closing and re-opening or by receiving all subscribed channel events on one connection.

**Refined approach:** Single SSE connection per user that delivers messages for ALL channels. The frontend filters by the currently active tab. This avoids reconnecting when switching tabs and is simpler to implement. The user subscribes to all 3 channels on connect.

### Decision 3: API Contracts

All chat endpoints live under the existing `/notifications` router prefix (Nginx already routes this).

#### `POST /notifications/chat/messages`
Send a new chat message. Auth required.

**Request:**
```json
{
  "channel": "general",       // "general" | "trade" | "help"
  "content": "Hello world!",  // string, 1-500 chars
  "reply_to_id": null          // int | null — ID of message being replied to
}
```

**Response (201):**
```json
{
  "id": 42,
  "channel": "general",
  "user_id": 1,
  "username": "PlayerOne",
  "avatar": "https://s3.twcstorage.ru/.../avatar.webp",
  "avatar_frame": "gold",
  "content": "Hello world!",
  "reply_to_id": null,
  "reply_to": null,
  "created_at": "2026-03-19T12:00:00"
}
```

**Errors:** 400 (validation), 401 (not authenticated), 403 (banned in chat)

**Security:**
- Auth: required (JWT via `get_current_user_via_http`)
- Rate limit: max 1 message per 2 seconds per user (enforced in application code via in-memory timestamp tracking per user_id)
- Input validation: `content` — strip whitespace, 1-500 chars, no empty messages
- XSS prevention: content is stored as-is in DB, frontend must render as text (not HTML). React's JSX escaping handles this by default.
- Ban check: query `chat_bans` table before allowing send

**Side effects:**
- After DB insert, broadcast message to all connected SSE clients via `broadcast_to_channel()`
- Trigger message retention cleanup if channel exceeds 500 messages

#### `GET /notifications/chat/messages`
Get paginated chat messages. No auth required (read-only for guests).

**Query params:** `channel` (required), `page` (default 1), `page_size` (default 50, max 100)

**Response (200):**
```json
{
  "items": [
    {
      "id": 42,
      "channel": "general",
      "user_id": 1,
      "username": "PlayerOne",
      "avatar": "https://...",
      "avatar_frame": "gold",
      "content": "Hello world!",
      "reply_to_id": 41,
      "reply_to": {
        "id": 41,
        "username": "PlayerTwo",
        "content": "Hey there!"
      },
      "created_at": "2026-03-19T12:00:00"
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 50
}
```

**Notes:** Messages ordered by `created_at DESC` (newest first). `reply_to` is a nested object with minimal info about the replied-to message (null if the original was deleted or reply_to_id is null).

#### `DELETE /notifications/chat/messages/{message_id}`
Delete a chat message (moderation). Auth required + `chat:delete` permission.

**Response (200):**
```json
{ "detail": "Сообщение удалено" }
```

**Errors:** 401, 403 (no permission), 404 (message not found)

**Side effects:** Broadcast a `message_deleted` event to all SSE clients so the message disappears in real-time.

#### `POST /notifications/chat/bans`
Ban a user from chat. Auth required + `chat:ban` permission.

**Request:**
```json
{
  "user_id": 5,
  "reason": "Спам",            // string | null
  "expires_at": null            // ISO datetime | null (null = permanent)
}
```

**Response (201):**
```json
{
  "id": 1,
  "user_id": 5,
  "banned_by": 1,
  "reason": "Спам",
  "banned_at": "2026-03-19T12:00:00",
  "expires_at": null
}
```

**Errors:** 401, 403 (no permission), 409 (user already banned)

#### `DELETE /notifications/chat/bans/{user_id}`
Unban a user from chat. Auth required + `chat:ban` permission.

**Response (200):**
```json
{ "detail": "Пользователь разбанен" }
```

**Errors:** 401, 403, 404 (ban not found)

#### `GET /notifications/chat/bans/{user_id}`
Check if a user is banned. Auth required.

**Response (200):**
```json
{
  "is_banned": true,
  "reason": "Спам",
  "expires_at": null
}
```

or `{ "is_banned": false }` if not banned.

#### `GET /notifications/chat/stream`
SSE stream for real-time chat messages. Auth required.

**SSE event types (sent as JSON in `data:` field):**

New message:
```json
{
  "type": "chat_message",
  "data": {
    "id": 42, "channel": "general", "user_id": 1,
    "username": "PlayerOne", "avatar": "...", "avatar_frame": "gold",
    "content": "Hello!", "reply_to_id": null, "reply_to": null,
    "created_at": "2026-03-19T12:00:00"
  }
}
```

Message deleted:
```json
{
  "type": "chat_message_deleted",
  "data": { "id": 42, "channel": "general" }
}
```

**Connection:** Client connects once, receives events for ALL channels. Frontend filters by active tab.

### Decision 4: DB Schema

#### Table `chat_messages` (owned by notification-service)

```sql
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    channel ENUM('general', 'trade', 'help') NOT NULL,
    user_id INTEGER NOT NULL,
    username VARCHAR(100) NOT NULL,
    avatar VARCHAR(500) NULL,
    avatar_frame VARCHAR(50) NULL,
    content TEXT NOT NULL,
    reply_to_id INTEGER NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_channel_created (channel, created_at DESC),
    INDEX idx_user_id (user_id),
    FOREIGN KEY (reply_to_id) REFERENCES chat_messages(id) ON DELETE SET NULL
);
```

**Notes:**
- `username`, `avatar`, `avatar_frame` are denormalized (snapshot at message send time). This is standard chat behavior — old messages show the avatar the user had when they sent the message.
- `reply_to_id` uses `ON DELETE SET NULL` — if the replied-to message is deleted, the reply reference becomes null (the reply block shows "Сообщение удалено").
- No FK to `users.id` — notification-service doesn't own the users table, and cross-service FKs are fragile. `user_id` is validated at the application level via JWT auth.

#### Table `chat_bans` (owned by notification-service)

```sql
CREATE TABLE chat_bans (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    banned_by INTEGER NOT NULL,
    reason VARCHAR(500) NULL,
    banned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NULL
);
```

**Notes:**
- `UNIQUE` on `user_id` — a user can only have one active ban.
- `expires_at = NULL` means permanent ban. Application code checks: if `expires_at` is not null and `expires_at < now()`, the ban is expired (treat as unbanned).

### Decision 5: Message Retention (500 per channel)

**Strategy:** After each message insert, run a cleanup query:

```sql
DELETE FROM chat_messages
WHERE channel = :channel
  AND id NOT IN (
    SELECT id FROM (
      SELECT id FROM chat_messages WHERE channel = :channel
      ORDER BY created_at DESC LIMIT 500
    ) AS keep
  );
```

This runs synchronously after each insert. For 500 messages, this is fast enough (indexed on `channel, created_at`). No Celery/cron needed.

**Alternative considered:** Celery periodic task — rejected because notification-service doesn't use Celery, and adding it for one cleanup query is overkill.

### Decision 6: Rate Limiting

**Application-level rate limiting** for `POST /notifications/chat/messages`:
- In-memory dict `_last_message_time: dict[int, float]` mapping `user_id` to `time.time()` of last sent message.
- Before processing: check if `time.time() - _last_message_time[user_id] < 2.0`. If yes, return 429 "Подождите перед отправкой следующего сообщения".
- This is per-instance (in-memory), sufficient for single-instance deployment.

### Decision 7: Frontend Components

#### Component Tree

```
Layout.tsx
├── ... (existing)
└── ChatWidget (fixed position, bottom-left)
    ├── ChatToggleButton — icon button to open/close
    └── ChatPanel (shown when open)
        ├── ChatHeader
        │   ├── Channel tabs: "Общий" | "Торговля" | "Помощь"
        │   └── "История" link → /chat/history
        ├── ChatInput (top of panel)
        │   ├── Reply preview (shown when replying)
        │   ├── Text input (input-underline)
        │   ├── Emoji button (stub, disabled)
        │   └── Send button (btn-blue)
        └── ChatMessages (scrollable, gold-scrollbar)
            └── ChatMessage (repeated)
                ├── Avatar + frame (32px square)
                ├── Username (gold-text)
                ├── Timestamp
                ├── Content
                ├── ReplyBlock (if reply_to exists)
                └── Actions (hover): Reply, Quote, Delete (mod only)

ChatHistoryPage (route: /chat/history)
├── ChatHeader (channel tabs)
├── ChatMessages (full-page, paginated)
└── Pagination controls
```

#### Redux Slice: `chatSlice`

```typescript
interface ChatMessage {
  id: number;
  channel: 'general' | 'trade' | 'help';
  user_id: number;
  username: string;
  avatar: string | null;
  avatar_frame: string | null;
  content: string;
  reply_to_id: number | null;
  reply_to: { id: number; username: string; content: string } | null;
  created_at: string;
}

interface ChatState {
  messages: Record<string, ChatMessage[]>;  // keyed by channel
  activeChannel: 'general' | 'trade' | 'help';
  isOpen: boolean;
  replyingTo: ChatMessage | null;
  isLoading: boolean;
  error: string | null;
  pagination: Record<string, { total: number; page: number; pageSize: number }>;
}
```

**Async thunks:**
- `fetchMessages({ channel, page, pageSize })` — `GET /notifications/chat/messages`
- `sendMessage({ channel, content, reply_to_id })` — `POST /notifications/chat/messages`
- `deleteMessage(messageId)` — `DELETE /notifications/chat/messages/{id}`
- `banUser({ user_id, reason, expires_at })` — `POST /notifications/chat/bans`
- `unbanUser(user_id)` — `DELETE /notifications/chat/bans/{user_id}`
- `checkBan(user_id)` — `GET /notifications/chat/bans/{user_id}`

**SSE integration:** In `Layout.tsx` (or a dedicated `useChatSSE` hook), connect to `/notifications/chat/stream`. On `chat_message` event, dispatch `chatSlice.actions.addMessage(data)`. On `chat_message_deleted`, dispatch `chatSlice.actions.removeMessage({ id, channel })`.

#### Shared Constants

Extract `AVATAR_FRAMES` from `ProfileSettingsModal.tsx` into a shared utility file `src/utils/avatarFrames.ts` so both `UserProfilePage` and chat components can import it.

### Decision 8: Security Considerations

| Endpoint | Auth | Rate Limit | Input Validation | Authorization |
|----------|------|------------|------------------|---------------|
| POST /chat/messages | Required | 1 msg/2s per user | content: 1-500 chars, channel: enum | Ban check |
| GET /chat/messages | Not required | None | channel: enum, page/pageSize: int | None |
| DELETE /chat/messages/{id} | Required | None | message_id: int | `chat:delete` permission |
| POST /chat/bans | Required | None | user_id: int, reason: 0-500 chars | `chat:ban` permission |
| DELETE /chat/bans/{user_id} | Required | None | user_id: int | `chat:ban` permission |
| GET /chat/bans/{user_id} | Required | None | user_id: int | Own ban or `chat:ban` |
| GET /chat/stream | Required | None | — | None |

**XSS:** React renders text content safely by default (JSX escaping). No `dangerouslySetInnerHTML`. Content stored as plain text.

**Input sanitization:** Strip leading/trailing whitespace from `content`. Reject empty messages. Max 500 characters. Channel must be one of the enum values.

### Decision 9: RBAC Permissions

New permissions to add in user-service Alembic migration:

| ID | Module | Action | Description | Roles |
|----|--------|--------|-------------|-------|
| 32 | chat | delete | Удаление сообщений в чате | Admin, Moderator |
| 33 | chat | ban | Бан/разбан пользователей в чате | Admin, Moderator |

### Data Flow Diagrams

**Send message:**
```
User types message → Frontend dispatches sendMessage()
  → POST /notifications/chat/messages (with JWT)
  → notification-service: validate auth, check ban, validate input, rate limit
  → INSERT into chat_messages
  → cleanup old messages if >500
  → broadcast_to_channel() → all SSE-connected users receive event
  → Frontend: chatSlice.addMessage() → UI updates
```

**Delete message (moderation):**
```
Moderator clicks delete → Frontend dispatches deleteMessage()
  → DELETE /notifications/chat/messages/{id} (with JWT + chat:delete permission)
  → notification-service: validate auth + permission, DELETE from chat_messages
  → broadcast chat_message_deleted event → all SSE clients
  → Frontend: chatSlice.removeMessage() → message disappears
```

**SSE connection:**
```
User opens page with Layout → useChatSSE hook
  → GET /notifications/chat/stream (with JWT)
  → notification-service: auth, create asyncio.Queue, add to chat_connections + channel_subscriptions
  → StreamingResponse yields events
  → On disconnect: remove from chat_connections + channel_subscriptions
```

### Decision 10: Alembic Setup for notification-service

Per T2 rules, notification-service needs Alembic initialized. Steps:
1. Add `alembic` to `requirements.txt`
2. Create `alembic.ini` and `alembic/` directory with `env.py`, `script.py.mako`
3. Use `version_table = "alembic_version_notification"` to avoid collisions
4. Initial migration: create `notifications` table (existing) — empty migration since table exists
5. Second migration: create `chat_messages` and `chat_bans` tables
6. Update Dockerfile CMD: `alembic upgrade head && uvicorn ...`
7. Remove `Base.metadata.create_all(bind=engine)` from `main.py`

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **Initialize Alembic for notification-service.** Add `alembic` to `requirements.txt`. Create `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/` directory. Use `version_table="alembic_version_notification"`. Create initial empty migration `0001_initial.py` that represents the existing `notifications` table (stamp only, no operations — table already exists). Remove `Base.metadata.create_all(bind=engine)` from `main.py` startup. Update Dockerfile CMD to run `alembic upgrade head &&` before uvicorn. | Backend Developer | TODO | `services/notification-service/app/requirements.txt`, `services/notification-service/app/alembic.ini`, `services/notification-service/app/alembic/env.py`, `services/notification-service/app/alembic/script.py.mako`, `services/notification-service/app/alembic/versions/0001_initial.py`, `services/notification-service/app/main.py`, `docker/notification-service/Dockerfile` | — | `alembic upgrade head` runs without errors. notification-service starts successfully. `alembic_version_notification` table exists in DB with revision `0001`. |
| 2 | **Add chat_messages and chat_bans tables via Alembic migration.** Create migration `0002_add_chat_tables.py` in notification-service. Create `chat_messages` table (id, channel ENUM, user_id, username, avatar, avatar_frame, content, reply_to_id FK self-ref ON DELETE SET NULL, created_at, indexes on (channel, created_at) and (user_id)). Create `chat_bans` table (id, user_id UNIQUE, banned_by, reason, banned_at, expires_at). Add SQLAlchemy models in `chat_models.py`. Add Pydantic schemas in `chat_schemas.py`. | Backend Developer | TODO | `services/notification-service/app/alembic/versions/0002_add_chat_tables.py`, `services/notification-service/app/chat_models.py`, `services/notification-service/app/chat_schemas.py` | #1 | `alembic upgrade head` creates both tables. Models and schemas importable without errors. `python -m py_compile` passes on all files. |
| 3 | **Add chat:delete and chat:ban permissions via Alembic migration in user-service.** Create migration `0011_add_chat_permissions.py`. Insert permissions (id=32 module=chat action=delete, id=33 module=chat action=ban). Assign both to Admin (role_id=4) and Moderator (role_id=3) in role_permissions. | Backend Developer | TODO | `services/user-service/alembic/versions/0011_add_chat_permissions.py` | — | `alembic upgrade head` succeeds. Permissions `chat:delete` and `chat:ban` exist in DB. Admin and Moderator roles have these permissions. |
| 4 | **Implement chat SSE broadcast in sse_manager.py.** Add `chat_connections: dict[int, asyncio.Queue]` for chat-specific SSE connections. Add `channel_subscriptions: dict[str, set[int]]` tracking channel membership. Implement `add_chat_connection(user_id)`, `remove_chat_connection(user_id)`, `broadcast_to_channel(channel, data)` (iterates all chat_connections and puts message into their queues), `broadcast_to_all_channels(data)` (for events like message_deleted that need to reach everyone). | Backend Developer | DONE | `services/notification-service/app/sse_manager.py` | — | Functions exist and are importable. `broadcast_to_channel` puts data into all connected user queues. `python -m py_compile` passes. |
| 5 | **Implement chat REST endpoints and SSE stream.** Create `chat_routes.py` with APIRouter prefix `/notifications/chat`. Implement: (1) `POST /messages` — auth, ban check, rate limit (2s per user), validate input (1-500 chars, enum channel), insert into DB, cleanup if >500, broadcast via SSE, return message; (2) `GET /messages` — paginated (page/page_size), ordered by created_at DESC, include reply_to nested object, no auth required; (3) `DELETE /messages/{message_id}` — auth + `chat:delete` permission, delete from DB, broadcast deletion event; (4) `POST /bans` — auth + `chat:ban` permission, create ban, return 409 if exists; (5) `DELETE /bans/{user_id}` — auth + `chat:ban`, delete ban; (6) `GET /bans/{user_id}` — auth, return ban status (own or `chat:ban` permission); (7) `GET /stream` — auth, SSE endpoint using chat_connections from sse_manager, subscribe to all channels, yield events as `data: {json}\n\n`. Create `chat_crud.py` for DB operations. Include router in `main.py`. | Backend Developer | TODO | `services/notification-service/app/chat_routes.py`, `services/notification-service/app/chat_crud.py`, `services/notification-service/app/main.py` | #2, #4 | All 7 endpoints respond correctly. Rate limiting works (429 on rapid sends). Ban check prevents banned users from sending. Message retention enforced at 500/channel. SSE stream delivers real-time events. `python -m py_compile` passes on all files. |
| 6 | **Extract AVATAR_FRAMES to shared utility and create chat Redux slice.** Move `AVATAR_FRAMES` constant from `ProfileSettingsModal.tsx` to `src/utils/avatarFrames.ts`. Update imports in `ProfileSettingsModal.tsx`, `UserProfilePage.tsx`, `AvatarFramePreview.tsx`. Create `src/redux/slices/chatSlice.ts` with state (messages by channel, activeChannel, isOpen, replyingTo, isLoading, error, pagination), async thunks (fetchMessages, sendMessage, deleteMessage, banUser, unbanUser, checkBan), reducers (addMessage, removeMessage, setActiveChannel, toggleChat, setReplyingTo, clearReply). Register slice in `store.ts`. Create TypeScript interfaces for ChatMessage, ChatState, ChatBanStatus. Create `src/api/chatApi.ts` with Axios calls for all chat endpoints. | Frontend Developer | TODO | `src/utils/avatarFrames.ts`, `src/components/UserProfilePage/ProfileSettingsModal.tsx`, `src/components/UserProfilePage/UserProfilePage.tsx`, `src/components/UserProfilePage/AvatarFramePreview.tsx`, `src/redux/slices/chatSlice.ts`, `src/redux/store.ts`, `src/api/chatApi.ts` | #5 | Redux slice compiles. All thunks make correct API calls. `AVATAR_FRAMES` importable from shared location. `npx tsc --noEmit` passes. |
| 7 | **Implement ChatWidget component (fixed position, collapsible).** Create `src/components/Chat/ChatWidget.tsx` — fixed bottom-left, toggle button with chat icon, animated open/close (AnimatePresence). Create `ChatPanel.tsx` — contains ChatHeader, ChatInput, ChatMessages. Create `ChatHeader.tsx` — 3 channel tabs ("Общий"/"Торговля"/"Помощь"), "История" link to `/chat/history`. Create `ChatInput.tsx` — text input (input-underline), reply preview block, emoji stub button (disabled), send button (btn-blue). Disable input for unauthenticated users (show "Войдите, чтобы писать") and banned users (show "Вы заблокированы в чате"). Create `ChatMessages.tsx` — scrollable message list (gold-scrollbar), newest first. Create `ChatMessage.tsx` — avatar+frame (32px), username (gold-text), timestamp, content, ReplyBlock, hover actions (Reply, Delete for mods). Add ChatWidget to `Layout.tsx`. Use Tailwind only, responsive (360px+: full-width on mobile, fixed-width ~350px on desktop). | Frontend Developer | TODO | `src/components/Chat/ChatWidget.tsx`, `src/components/Chat/ChatPanel.tsx`, `src/components/Chat/ChatHeader.tsx`, `src/components/Chat/ChatInput.tsx`, `src/components/Chat/ChatMessages.tsx`, `src/components/Chat/ChatMessage.tsx`, `src/components/App/Layout/Layout.tsx` | #6 | Widget renders in bottom-left corner. Opens/closes on click. Channel switching works. Messages display with avatars and frames. Reply and delete actions visible. Responsive on 360px+. `npx tsc --noEmit` and `npm run build` pass. All errors displayed to user in Russian. |
| 8 | **Implement ChatHistoryPage and SSE integration.** Create `src/components/Chat/ChatHistoryPage.tsx` — full-page chat history with channel tabs, paginated message list, pagination controls. Add route `/chat/history` in `App.tsx`. Create `src/hooks/useChatSSE.ts` — hook that connects to `/notifications/chat/stream`, dispatches `addMessage` and `removeMessage` actions to Redux on events. Integrate `useChatSSE` into `Layout.tsx` (runs for authenticated users). Handle reconnection with exponential backoff (reuse pattern from `useSSE.ts`). | Frontend Developer | TODO | `src/components/Chat/ChatHistoryPage.tsx`, `src/components/App/App.tsx`, `src/hooks/useChatSSE.ts`, `src/components/App/Layout/Layout.tsx` | #7 | Chat history page loads at `/chat/history` with pagination. SSE connection established on page load for authenticated users. New messages appear in real-time. Deleted messages disappear in real-time. `npx tsc --noEmit` and `npm run build` pass. |
| 9 | **Write backend tests for chat endpoints.** Create `tests/test_chat.py` in notification-service. Test: (1) send message — success, validation errors (empty content, too long, invalid channel), auth required, banned user blocked; (2) get messages — pagination, channel filter, reply_to nesting, empty channel; (3) delete message — success, 404, permission required; (4) ban/unban — success, already banned (409), permission required, check ban status; (5) rate limiting — second message within 2s returns 429; (6) message retention — verify oldest messages deleted when exceeding 500 per channel (use smaller limit in test). Mock `get_current_user_via_http` and `broadcast_to_channel`. Use SQLite for test DB (existing pattern in notification-service tests). | QA Test | TODO | `services/notification-service/app/tests/test_chat.py` | #5 | All tests pass with `pytest`. Covers happy paths and error cases. At least 15 test functions. |
| 10 | **Write Alembic migration test for chat permissions.** Add test in user-service to verify permissions 32 and 33 exist after migration and are assigned to Admin and Moderator roles. | QA Test | TODO | `services/user-service/tests/test_chat_permissions.py` | #3 | Test passes with `pytest`. Verifies permissions exist and role assignments are correct. |
| 11 | **Final review** — verify all tasks, run full test suite, check cross-service contracts, verify live functionality. | Reviewer | TODO | all | #1, #2, #3, #4, #5, #6, #7, #8, #9, #10 | All checks from Review template pass. No TypeScript errors. No Python compile errors. All tests pass. Live verification: chat widget works, messages send/receive in real-time, moderation works. |

---

## 5. Review Log (filled by Reviewer — in English)

*Pending...*

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-19 10:00 — PM: фича создана, запускаю анализ кодовой базы
[LOG] 2026-03-19 10:30 — Analyst: начал анализ, изучаю notification-service (SSE), user-service (auth/RBAC), photo-service (аватары), frontend (layout/Redux/SSE), Nginx, Docker
[LOG] 2026-03-19 11:15 — Analyst: анализ завершён, затронуто 3 сервиса (notification-service, user-service, frontend) + Nginx/Docker при создании нового сервиса. Ключевые находки: SSE инфраструктура есть но unicast (нужен broadcast), Alembic отсутствует в notification-service (T2), аватар-рамки рендерятся на фронтенде по строковому ID
[LOG] 2026-03-19 12:00 — Architect: начал проектирование, изучаю notification-service (SSE, models, auth, DB), user-service (permissions pattern), frontend (layout, Redux)
[LOG] 2026-03-19 13:30 — Architect: проектирование завершено. 10 ключевых решений, 7 API-контрактов, 2 таблицы БД, 11 задач. Решение: расширяем notification-service (не новый сервис), broadcast через in-memory channel subscriptions, отдельный SSE-эндпоинт для чата. Задачи: 5 Backend, 3 Frontend, 2 QA, 1 Review.
[LOG] 2026-03-19 14:00 — Backend Dev: начал задачу #3 — добавление chat:delete и chat:ban permissions
[LOG] 2026-03-19 14:10 — Backend Dev: задача #3 завершена. Создана миграция 0011_add_chat_permissions.py (down_revision=0010, permission IDs 32-33, назначены Admin и Moderator). py_compile пройден.
[LOG] 2026-03-19 14:30 — Backend Dev: начал задачу #4 — расширение sse_manager.py для chat broadcast
[LOG] 2026-03-19 14:45 — Backend Dev: задача #4 завершена. Добавлены chat_connections, channel_subscriptions, add_chat_connection(), remove_chat_connection(), broadcast_to_channel(), broadcast_to_all(). Очередь с maxsize=256, обработка stale connections и QueueFull. py_compile и import-проверка пройдены.
[LOG] 2026-03-19 15:00 — Backend Dev: начал задачу #1 — инициализация Alembic для notification-service
[LOG] 2026-03-19 15:20 — Backend Dev: задача #1 завершена. Добавлен alembic в requirements.txt, создан alembic.ini, env.py (version_table=alembic_version_notification), script.py.mako, 0001_initial.py (пустая baseline миграция). Удалён Base.metadata.create_all из main.py, обновлён Dockerfile CMD с alembic upgrade head. py_compile пройден на всех файлах.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*

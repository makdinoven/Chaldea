# FEAT-006: New header, toast system, SSE notifications

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-12 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Три связанные задачи:
1. **Toast-система** — заменить все `alert()` на стилизуемые тосты
2. **SSE-уведомления** — подключить фронтенд к notification-service через SSE, показывать уведомления
3. **Новый хедер** — редизайн по макету Figma с навигацией в линию, поиском, аватарами и иконками уведомлений

### Дизайн хедера (из Figma)

Горизонтальная полоса на всю ширину, max-width 1360px, высота 80px:

**Левая часть (Frame 124):**
- Логотип: 80x80px, скруглённый квадрат (border-radius: 20px)
- Навигация в линию с gap 40px: ГЛАВНАЯ, ПРАВИЛА, СОБЫТИЯ, ТИКЕТ
- Шрифт: Montserrat 500, 16px, uppercase, letter-spacing 0.06em, белый

**Правая часть (Frame 127):**
- Поиск: инпут с border-bottom 1px solid white, плейсхолдер "поиск" (Montserrat 500, 14px, uppercase), иконка лупы
- Два круглых аватара 80x80px (персонаж + юзер) с gap 20px
- Иконки: колокольчик (уведомления) + сообщения (stroke 2px white)

### Маппинг текущих ссылок на новый хедер
Текущие ссылки из хедера, которые нужно сохранить:
- **В линию**: ГЛАВНАЯ → `/home`, ПРАВИЛА → (новая, пока без роута), СОБЫТИЯ → (новая), ТИКЕТ → `/support`
- **При наведении на аватар юзера**: Профиль `/profile`, Сообщения `/messages`, Выход (с реальным разлогиниванием)
- **При наведении на аватар персонажа**: Профиль `/`, Создать `/createCharacter`, Выбрать `/selectCharacter` (если нет персонажа)
- **Админка**: кнопка/ссылка (видна только admin-роли): Заявки, Айтемы, Локации, Навыки
- **Текущая локация**: если персонаж на локации — показать переход

### Бизнес-правила
- Тосты: success (зелёный), error (красный), info (синий/нейтральный), позиция — top-right
- SSE: подключение при логине, показ badge на колокольчике с числом непрочитанных
- Хедер: адаптивный, кнопка админки видна ТОЛЬКО для role=admin
- Выход должен реально очищать токен и редиректить на стартовую

### UX
1. Пользователь логинится → SSE подключается → badge на колокольчике
2. Приходит уведомление → toast + обновление badge
3. Клик по колокольчику → выпадающий список уведомлений

### Вебсокет (Vite HMR)
Ошибка `WebSocket connection to 'ws://localhost/?token=...'` — это Vite dev-сервер HMR. Нужно исправить конфиг Vite, чтобы HMR работал корректно через Nginx.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Current Header Architecture
- **Files:** `Header.jsx` + `Header.module.scss`, `Menu/Menu.jsx` + `Menu/Menu.module.scss`
- **Layout:** 3-column CSS Grid: left menus | centered logo (369px) | right menus
- **Menu squares:** 128x128px with hover-reveal overlay links (image backgrounds)
- **Data:** `menuData` array built from Redux `state.user` (username, avatar, character, role)
- **Admin menu:** Always pushed to `menuData` — visible to ALL users (no role check)
- **Logout:** Just navigates to `/` — does NOT clear token from localStorage
- **Redux:** `userSlice.js` has `getMe` thunk (fetches `/users/me` with JWT), `logout` reducer (clears state but not token)

### Current Layout
- `Layout.jsx` at `src/components/App/Layout/` renders `<Header />` + `<Outlet />`
- `App.jsx` wraps authenticated routes under `<Layout />`
- StartPage is outside Layout (no header)

### Notification Service (Backend)
- **SSE endpoint:** `GET /notifications/stream` — requires JWT via `OAuth2PasswordBearer`
- **Auth:** `auth_http.py` calls `http://user-service:8000/users/me` with Bearer token
- **SSE transport:** `sse_manager.py` uses `asyncio.Queue()` per user_id in global `connections` dict
- **CRUD endpoints:**
  - `GET /notifications/{user_id}/unread` — returns unread notifications (404 if none)
  - `GET /notifications/{user_id}/full` — returns all notifications (404 if none)
  - `PUT /notifications/{user_id}/mark-as-read` — mark specific IDs as read
  - `PUT /notifications/{user_id}/mark-all-as-read` — mark all as read
- **Nginx:** SSE block already configured with `proxy_buffering off`, `proxy_read_timeout 3600`

### alert() Calls (11 total, 4 files)
1. `LocationNeighborsEditor.jsx:46` — 'Сосед уже есть'
2. `Request.jsx:36` — 'Заявка одобрена'
3. `Request.jsx:43` — 'Заявка отклонена'
4. `AdminSkillsPage.jsx:58` — 'Не удалось создать навык'
5. `AdminSkillsPage.jsx:72` — 'Не удалось удалить навык'
6. `AdminSkillsPage.jsx:83` — 'Изменения успешно сохранены!'
7. `AdminSkillsPage.jsx:86` — 'Произошла ошибка при сохранении'
8. `LocationPage.jsx:63` — 'пост отправлен'
9. `LocationPage.jsx:67` — 'ошибка пост не отправлен'
10. `LocationPage.jsx:88` — 'битва началась'
11. `LocationPage.jsx:90` — 'ошибка битва не началась'

### Existing Infrastructure
- **Icons:** `react-feather` already installed (has Bell, Search, MessageSquare, etc.)
- **TypeScript:** `tsconfig.json` present, `strict: false`, `allowJs: true` — mixed JS/TS works
- **Tailwind:** Installed and configured (`tailwind.config.js` + `postcss.config.js`)
- **Vite:** No `server.hmr` config — HMR WebSocket fails through Nginx (connects to `ws://localhost/` instead of direct to Vite)
- **Font Montserrat:** Not currently loaded — must be added (Google Fonts or local)

### Vite HMR Issue
Current `vite.config.js` has no `server.hmr` setting. When accessed through Nginx (port 80), Vite tries to open WebSocket at `ws://localhost/` which hits Nginx and fails. Nginx has no WebSocket upgrade configuration for the frontend location block.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Toast Library: `react-hot-toast`

**Decision:** Use `react-hot-toast` (v2).

**Rationale:**
- Lightweight (~5KB gzipped), no heavy dependencies
- Highly customizable styling — works well with Tailwind classes
- Simple API: `toast.success()`, `toast.error()`, `toast()` for info
- Supports promise-based toasts for async operations
- Already widely adopted, stable, minimal API surface
- `sonner` is newer but heavier and its defaults are opinionated about styling

**Usage pattern:**
```tsx
import toast from 'react-hot-toast';
toast.success('Заявка одобрена');
toast.error('Не удалось создать навык');
```

**Provider:** `<Toaster />` placed in `App.tsx` (wraps entire app, above Router).

### 3.2 SSE Connection Strategy

**Problem:** `EventSource` API does not support custom headers. The notification-service SSE endpoint requires JWT via `Authorization: Bearer <token>`.

**Decision:** Use `fetch()`-based SSE via a custom React hook (`useSSE`).

**Rationale:**
- Native `EventSource` cannot send Authorization headers
- Query-param approach (`?token=xxx`) exposes JWT in server logs and browser history — security risk
- A lightweight fetch-based approach using `ReadableStream` API gives full header control
- No need for a polyfill library — modern browsers support `fetch` + `ReadableStream`

**Implementation:**
```tsx
// Custom hook: useSSE(url, token)
// Uses fetch() with headers: { Authorization: `Bearer ${token}` }
// Reads response.body as ReadableStream, parses SSE format ("data: ...\n\n")
// Returns parsed events via callback
// Handles reconnection with exponential backoff (1s, 2s, 4s, max 30s)
// Cleans up on unmount
```

**SSE lifecycle:**
1. User logs in → token stored in localStorage
2. Layout mounts → `useSSE` hook connects to `/notifications/stream`
3. Event received → dispatch to Redux → show toast + update badge
4. User logs out → hook cleanup closes connection
5. Connection lost → auto-reconnect with backoff

### 3.3 Notification Redux Slice

**New file:** `src/redux/slices/notificationSlice.ts`

**State shape:**
```typescript
interface NotificationItem {
  id: number;
  user_id: number;
  message: string;
  status: 'unread' | 'read';
  created_at: string;
}

interface NotificationState {
  items: NotificationItem[];
  unreadCount: number;
  sseConnected: boolean;
  dropdownOpen: boolean;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}
```

**Async thunks:**
- `fetchUnreadNotifications(userId)` — GET `/notifications/{userId}/unread`
- `markNotificationsAsRead(userId, ids)` — PUT `/notifications/{userId}/mark-as-read`
- `markAllAsRead(userId)` — PUT `/notifications/{userId}/mark-all-as-read`

**Reducers:**
- `addNotification(notification)` — from SSE event, prepend to items, increment unreadCount
- `setSSEConnected(boolean)`
- `toggleDropdown()`
- `closeDropdown()`

**Selectors:**
- `selectUnreadCount(state)`
- `selectNotifications(state)`
- `selectDropdownOpen(state)`

### 3.4 Header Component Architecture

**Replace:** `Header.jsx` + `Header.module.scss` + `Menu/Menu.jsx` + `Menu/Menu.module.scss`

**New files (all TypeScript + Tailwind, no CSS files):**

```
src/components/CommonComponents/Header/
├── Header.tsx              # Main header component
├── NavLinks.tsx            # Inline nav links (left section)
├── SearchInput.tsx         # Search input with icon (right section)
├── AvatarDropdown.tsx      # Circular avatar with hover dropdown (reusable)
├── NotificationBell.tsx    # Bell icon + badge + dropdown
├── AdminMenu.tsx           # Admin link (role-gated)
└── types.ts                # Shared TypeScript interfaces
```

**Delete:** `Header.jsx`, `Header.module.scss`, `Menu/Menu.jsx`, `Menu/Menu.module.scss`

**Header layout (Tailwind):**
```
<header> — w-full, max-w-[1360px], h-20, mx-auto, flex items-center justify-between
  <div class="left"> — flex items-center gap-10
    <Logo /> — 80x80, rounded-[20px]
    <NavLinks /> — flex gap-10, uppercase, tracking-wider, font-medium
  </div>
  <div class="right"> — flex items-center gap-5
    <SearchInput /> — border-b border-white, placeholder "поиск"
    <AvatarDropdown /> — character avatar (80x80 rounded-full)
    <AvatarDropdown /> — user avatar (80x80 rounded-full)
    <NotificationBell /> — Bell icon + red badge
    <MessageIcon /> — MessageSquare icon (placeholder, no functionality yet)
    <AdminMenu /> — visible only if role === 'admin'
  </div>
</header>
```

**AvatarDropdown behavior:**
- Circular avatar image (80x80)
- Hover reveals dropdown with links (absolute positioned below)
- User avatar dropdown: Профиль, Сообщения, Выход
- Character avatar dropdown: Профиль / Создать+Выбрать (conditional on character existence)
- Current location link shown in character dropdown if `character.current_location` exists

**NotificationBell behavior:**
- Bell icon from react-feather
- Red badge circle with unread count (hidden when 0)
- Click toggles dropdown panel
- Dropdown shows list of recent notifications
- "Mark all as read" button in dropdown
- Click outside closes dropdown

**Logout fix:**
- "Выход" calls: `localStorage.removeItem('accessToken')`, dispatch `logout()`, navigate to `/`

**Admin menu:**
- Conditionally rendered: `{role === 'admin' && <AdminMenu />}`
- Shows admin link, hover dropdown with: Заявки, Айтемы, Локации, Навыки

### 3.5 Font: Montserrat

Add Google Fonts import to `index.html`:
```html
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600&display=swap" rel="stylesheet">
```

Add to Tailwind config `theme.extend.fontFamily`:
```js
fontFamily: { montserrat: ['Montserrat', 'sans-serif'] }
```

### 3.6 Vite HMR Fix

**Problem:** Vite dev server WebSocket for HMR goes through Nginx which doesn't have WebSocket upgrade for `/`. The WebSocket URL collides with the token query parameter.

**Solution (two parts):**

1. **vite.config.js** — add `server.hmr` config:
```js
server: {
  hmr: {
    host: 'localhost',
    port: 5555,
    protocol: 'ws',
  }
}
```
This tells the Vite client to connect directly to `ws://localhost:5555` for HMR, bypassing Nginx entirely. Works for local development.

2. **Nginx** — add WebSocket upgrade for Vite HMR (in the `location /` block):
```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### 3.7 Data Flow Diagrams

**Toast flow (replacing alert):**
```
User action → API call → success/error → toast.success()/toast.error()
```

**SSE notification flow:**
```
Backend event → RabbitMQ → notification-service consumer
  → save to DB → send_to_sse(user_id, data)
  → SSE stream → frontend useSSE hook
  → dispatch addNotification → Redux store
  → NotificationBell re-renders (badge count)
  → toast.info(message) shown
```

**Header logout flow:**
```
Click "Выход" → localStorage.removeItem('accessToken')
  → dispatch(logout()) → Redux clears user state
  → SSE hook detects no token → closes connection
  → navigate('/') → StartPage
```

### 3.8 Security Considerations

- **SSE auth:** JWT passed via fetch headers (not query params) — no token leakage in logs
- **Admin menu:** Frontend hides admin links for non-admin, but backend endpoints already have role checks (notification-service `/create` checks `role != admin`)
- **Token cleanup:** Logout properly removes token from localStorage
- **CORS:** notification-service needs frontend origin in CORS config (already handles this via FastAPI CORS middleware — verify during implementation)
- **Reconnection:** SSE reconnect uses exponential backoff to avoid hammering the server

### 3.9 Files Modified/Created Summary

| Action | File | Notes |
|--------|------|-------|
| CREATE | `src/components/CommonComponents/Header/Header.tsx` | Replaces Header.jsx |
| CREATE | `src/components/CommonComponents/Header/NavLinks.tsx` | New |
| CREATE | `src/components/CommonComponents/Header/SearchInput.tsx` | New |
| CREATE | `src/components/CommonComponents/Header/AvatarDropdown.tsx` | New |
| CREATE | `src/components/CommonComponents/Header/NotificationBell.tsx` | New |
| CREATE | `src/components/CommonComponents/Header/AdminMenu.tsx` | New |
| CREATE | `src/components/CommonComponents/Header/types.ts` | New |
| DELETE | `src/components/CommonComponents/Header/Header.jsx` | Replaced by .tsx |
| DELETE | `src/components/CommonComponents/Header/Header.module.scss` | Migrated to Tailwind |
| DELETE | `src/components/CommonComponents/Header/Menu/Menu.jsx` | Replaced by AvatarDropdown |
| DELETE | `src/components/CommonComponents/Header/Menu/Menu.module.scss` | Migrated to Tailwind |
| CREATE | `src/redux/slices/notificationSlice.ts` | New Redux slice |
| CREATE | `src/hooks/useSSE.ts` | New SSE hook |
| MODIFY | `src/redux/store.js` → `store.ts` | Add notification reducer |
| MODIFY | `src/components/App/App.jsx` → `App.tsx` | Add Toaster provider |
| MODIFY | `src/components/App/Layout/Layout.jsx` → `Layout.tsx` | Update Header import, add SSE init |
| MODIFY | `src/components/pages/LocationPage/LocationPage.jsx` → `.tsx` | Replace alert() with toast |
| MODIFY | `src/components/AdminSkillsPage/AdminSkillsPage.jsx` → `.tsx` | Replace alert() with toast |
| MODIFY | `src/components/Admin/Request/Request.jsx` → `.tsx` | Replace alert() with toast |
| MODIFY | `src/components/AdminLocationsPage/EditForms/.../LocationNeighborsEditor.jsx` → `.tsx` | Replace alert() with toast |
| MODIFY | `vite.config.js` | Add server.hmr config |
| MODIFY | `docker/api-gateway/nginx.conf` | Add WebSocket upgrade headers |
| MODIFY | `tailwind.config.js` | Add Montserrat font family |
| MODIFY | `index.html` | Add Google Fonts link |
| MODIFY | `package.json` | Add react-hot-toast dependency |

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: Fix Vite HMR WebSocket configuration

| Field | Value |
|-------|-------|
| **#** | 1 |
| **Description** | Fix Vite HMR WebSocket that fails through Nginx. Add `server.hmr` config to `vite.config.js` to direct HMR WebSocket to connect directly to Vite dev server. Add WebSocket upgrade headers to Nginx `location /` block. |
| **Agent** | DevSecOps |
| **Status** | TODO |
| **Files** | `services/frontend/app-chaldea/vite.config.js`, `docker/api-gateway/nginx.conf` |
| **Depends On** | — |
| **Acceptance Criteria** | Vite HMR works without WebSocket errors in browser console when accessing app through Nginx (port 80). No `WebSocket connection to 'ws://localhost/?token=...'` errors. |

### Task 2: Install react-hot-toast, add Toaster provider, add Montserrat font

| Field | Value |
|-------|-------|
| **#** | 2 |
| **Description** | Install `react-hot-toast` package. Migrate `App.jsx` to `App.tsx` and add `<Toaster position="top-right" />` component wrapping the Router. Add Montserrat font via Google Fonts link in `index.html`. Add `fontFamily: { montserrat: ['Montserrat', 'sans-serif'] }` to `tailwind.config.js` theme extend. Migrate `Layout.jsx` to `Layout.tsx`. Delete old `.jsx` files and their SCSS files (`Layout.scss`). |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `package.json`, `src/components/App/App.jsx` → `App.tsx`, `src/components/App/Layout/Layout.jsx` → `Layout.tsx`, `src/components/App/Layout/Layout.scss` (delete), `index.html`, `tailwind.config.js` |
| **Depends On** | — |
| **Acceptance Criteria** | `react-hot-toast` installed. `App.tsx` renders `<Toaster />`. `toast.success('test')` works from any component. Montserrat font loads. Layout.tsx compiles. Old .jsx/.scss files deleted. |

### Task 3: Create notification Redux slice and SSE hook

| Field | Value |
|-------|-------|
| **#** | 3 |
| **Description** | Create `notificationSlice.ts` with state shape from architecture (items, unreadCount, sseConnected, dropdownOpen). Implement async thunks: `fetchUnreadNotifications`, `markNotificationsAsRead`, `markAllAsRead`. Create `useSSE.ts` hook that connects to `/notifications/stream` using fetch-based SSE with JWT from localStorage. Hook dispatches `addNotification` on events and shows toast. Migrate `store.js` to `store.ts`, register notification reducer. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `src/redux/slices/notificationSlice.ts` (create), `src/hooks/useSSE.ts` (create), `src/redux/store.js` → `store.ts` |
| **Depends On** | 2 |
| **Acceptance Criteria** | Notification slice registered in store. `useSSE` hook connects to SSE endpoint with auth header. Incoming SSE events dispatched to Redux and trigger toast. Reconnect with exponential backoff on connection loss. Hook cleanup on unmount. |

### Task 4: Build new Header component with Tailwind

| Field | Value |
|-------|-------|
| **#** | 4 |
| **Description** | Build complete new header per Figma design and architecture spec (section 3.4). Create all sub-components: `Header.tsx`, `NavLinks.tsx`, `SearchInput.tsx`, `AvatarDropdown.tsx`, `NotificationBell.tsx`, `AdminMenu.tsx`, `types.ts`. All styled with Tailwind only (no CSS/SCSS). Use `react-feather` icons (Bell, Search, MessageSquare). Admin menu gated by `role === 'admin'`. Implement real logout (clear localStorage token, dispatch logout action, navigate to `/`). Character dropdown shows location link if `character.current_location` exists. NotificationBell shows badge from Redux `unreadCount`, click toggles dropdown with notification list. Update `Layout.tsx` to initialize SSE connection via `useSSE` hook. Delete old files: `Header.jsx`, `Header.module.scss`, `Menu/Menu.jsx`, `Menu/Menu.module.scss`. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `src/components/CommonComponents/Header/Header.tsx` (create), `NavLinks.tsx` (create), `SearchInput.tsx` (create), `AvatarDropdown.tsx` (create), `NotificationBell.tsx` (create), `AdminMenu.tsx` (create), `types.ts` (create), `Layout.tsx` (modify — add useSSE), `Header.jsx` (delete), `Header.module.scss` (delete), `Menu/Menu.jsx` (delete), `Menu/Menu.module.scss` (delete) |
| **Depends On** | 2, 3 |
| **Acceptance Criteria** | Header renders per Figma: logo left with inline nav links, right section with search + avatars + icons. Avatar hover shows dropdown links. Admin menu only for admin role. Logout clears token + redirects. NotificationBell shows unread badge and dropdown. SSE connected on layout mount. All Tailwind, no CSS/SCSS. Old files deleted. |

### Task 5: Replace all alert() calls with toasts

| Field | Value |
|-------|-------|
| **#** | 5 |
| **Description** | Migrate 4 files from `.jsx` to `.tsx` and replace all 11 `alert()` calls with `react-hot-toast` calls. Migrate each file's styles from SCSS modules to Tailwind. Files: `LocationNeighborsEditor.jsx` (1 alert), `Request.jsx` (2 alerts), `AdminSkillsPage.jsx` (4 alerts), `LocationPage.jsx` (4 alerts). Use `toast.success()` for positive, `toast.error()` for negative outcomes. Delete old `.jsx` and `.module.scss` files after migration. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `LocationNeighborsEditor.jsx` → `.tsx` + delete `.module.scss`, `Request.jsx` → `.tsx` + delete `.module.scss`, `AdminSkillsPage.jsx` → `.tsx` + delete `.module.scss`, `LocationPage.jsx` → `.tsx` + delete `.module.scss` |
| **Depends On** | 2 |
| **Acceptance Criteria** | Zero `alert()` calls remain in codebase. All 4 files migrated to `.tsx` with TypeScript types. All styles migrated to Tailwind. Toast notifications appear in top-right corner with appropriate type (success/error). Old `.jsx` and `.module.scss` files deleted. |

### Task 6: QA — Backend tests for notification-service SSE and CRUD

| Field | Value |
|-------|-------|
| **#** | 6 |
| **Description** | Write pytest tests for notification-service endpoints: SSE stream connection (mock auth), CRUD operations (get unread, get all, mark-as-read, mark-all-as-read), admin notification creation (role check). Test SSE event delivery via sse_manager. No backend code was changed in this feature but SSE is being integrated for the first time — tests ensure the existing backend works correctly as documented. |
| **Agent** | QA Test |
| **Status** | TODO |
| **Files** | `services/notification-service/tests/` (create test files) |
| **Depends On** | — |
| **Acceptance Criteria** | Tests cover: SSE stream returns 200 with valid auth, 401 without auth. CRUD endpoints return expected data. Admin create rejects non-admin. `send_to_sse` delivers data to connected user queue. All tests pass. |

### Task 7: Review all changes

| Field | Value |
|-------|-------|
| **#** | 7 |
| **Description** | Review all changes from tasks 1-6. Verify: Tailwind-only styles (no new CSS/SCSS), TypeScript for all modified files, no `alert()` remaining, admin menu role-gated, logout clears token, SSE connects with auth headers (not query params), toast notifications work, HMR fix works, tests pass. |
| **Agent** | Reviewer |
| **Status** | TODO |
| **Files** | All files from tasks 1-6 |
| **Depends On** | 1, 2, 3, 4, 5, 6 |
| **Acceptance Criteria** | All acceptance criteria from tasks 1-6 met. No regressions. Code follows project conventions. Security checklist passed. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-12
**Result:** PASS (with minor notes)

#### Review Summary

All 6 tasks have been verified. The implementation is solid, follows project conventions, and meets acceptance criteria. Changes are ready for completion.

#### Checklist Results

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 1 | Tailwind only — no new CSS/SCSS created | PASS | All new Header components use Tailwind. AdminSkillsPage.module.scss correctly retained (used by 13 child .jsx files not in scope). |
| 2 | TypeScript — all modified/new frontend files are .tsx/.ts | PASS | Header/*.tsx, notificationSlice.ts, useSSE.ts, store.ts, App.tsx, Layout.tsx, LocationPage.tsx, Request.tsx, AdminSkillsPage.tsx, LocationNeighborsEditor.tsx — all TypeScript. |
| 3 | No alert() — zero calls remaining | PASS | Grep confirms 0 `alert()` calls in `src/`. Note: `window.confirm()` calls remain in AdminLocationsPage.jsx and AdminSkillsPage.tsx — these are intentional confirmation dialogs, not alerts. |
| 4 | Admin menu gated by role === 'admin' | PASS | AdminMenu.tsx line 21: `if (role !== 'admin') return null;` |
| 5 | Logout clears token + dispatches + navigates | PASS | Header.tsx lines 26-29: `localStorage.removeItem('accessToken')`, `dispatch(logout())`, `navigate('/')` |
| 6 | SSE uses fetch with Authorization header | PASS | useSSE.ts line 49-51: `fetch(fullUrl, { headers: { Authorization: \`Bearer ${token}\` } })` — no query params. |
| 7 | Reconnection with exponential backoff | PASS | useSSE.ts: INITIAL=1000ms, doubles each retry, MAX=30000ms. Abort on unmount. |
| 8 | Toaster in App.tsx | PASS | App.tsx lines 21-30: `<Toaster position="top-right" />` with dark theme styling. |
| 9 | Vite HMR configured | PASS | vite.config.js: `server.hmr: { host: 'localhost', port: 5555, protocol: 'ws' }` |
| 10 | Nginx WebSocket upgrade headers | PASS | nginx.conf lines 177-179: `Upgrade $http_upgrade`, `Connection "upgrade"` in `location /` block. |
| 11 | Montserrat font | PASS | index.html has Google Fonts link. tailwind.config.js has `fontFamily: { montserrat: [...] }`. Used in NavLinks, SearchInput, NotificationBell, AdminMenu, AvatarDropdown. |
| 12 | Notification bell with badge + dropdown | PASS | NotificationBell.tsx: red badge with unread count (hidden when 0, caps at 99+), click-to-toggle dropdown with notification list, "mark all as read" button, click-outside closes. |
| 13 | Header layout matches Figma | PASS | Logo left (80x80, rounded-[20px]) + inline nav (gap-10, uppercase, Montserrat). Right: search + character avatar + user avatar + bell + messages icon + admin menu. max-w-[1360px], h-20. |
| 14 | Tests cover CRUD, SSE, auth, security | PASS | 24 tests across 7 classes: unread, full, mark-as-read, mark-all-as-read, admin create (role check + 403), SSE stream (200 + 401), send_to_sse, security (SQL injection, XSS, edge cases). |
| 15 | No broken imports | PASS | main.jsx updated to import App.tsx and store.ts. Layout.tsx imports Header from new path. All cross-imports verified. |
| 16 | User-facing strings in Russian | PASS | All UI text is Russian: nav links, placeholders, dropdown labels, toast messages, notification labels. |

#### Code Quality Notes (non-blocking)

1. **`as unknown as any` pattern** in AdminSkillsPage.tsx and LocationNeighborsEditor.tsx — pragmatic workaround for JS-based Redux actions called from TS files. Acceptable during incremental migration.
2. **`console.log(error)`** in LocationPage.tsx (lines 113, 138) — should be `console.error` for consistency. Pre-existing pattern, not introduced by this feature.
3. **`fetchLocationData` missing try/catch** in LocationPage.tsx (lines 92-98) — pre-existing issue, not introduced by this feature.
4. **Explicit `.ts`/`.tsx` extensions in imports** (store.ts:13, main.jsx:3,5) — Vite resolves these correctly but TypeScript convention omits extensions. Non-blocking since `allowImportingTsExtensions` or Vite handles it.
5. **useSSE circular dependency between `connect` and `scheduleReconnect`** — both are `useCallback` referencing each other. Works correctly in practice because `url` is stable (never changes after mount) and `scheduleReconnect` only uses refs. Not a runtime bug but could be cleaner with a single combined callback.

#### Task Status Inconsistency

Tasks 1 and 6 have status `TODO` in the feature file but are actually completed per logs and code evidence. PM should update these to `DONE`.

#### Security Review

- SSE auth via headers (not query params) — no token leakage
- Admin menu client-side gated + backend role check exists
- Token properly cleared on logout
- SQL injection tests present for notification endpoints
- XSS storage test confirms frontend must escape (which React does by default)
- No secrets hardcoded in new code
- Error messages are user-friendly Russian text, no internal details leaked

#### Old Files Deletion Verified

- `Header.jsx` — deleted
- `Header.module.scss` — deleted
- `Menu/Menu.jsx` — deleted
- `Menu/Menu.module.scss` — deleted
- `Search/Search.jsx` — deleted
- `Search/Search.module.css` — deleted
- `Layout.scss` — deleted
- `Layout.jsx` — deleted (replaced by .tsx)
- `App.jsx` — deleted (replaced by .tsx)
- `store.js` — deleted (replaced by .ts)
- `Request.jsx` — deleted (replaced by .tsx)
- `LocationNeighborsEditor.jsx` — deleted (replaced by .tsx)
- `LocationPage.jsx` — deleted (replaced by .tsx)
- `AdminSkillsPage.jsx` — deleted (replaced by .tsx)

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-12 17:00 — PM: фича создана, запускаю архитектора
[LOG] 2026-03-12 17:30 — Architect: начал проектирование, изучил Header.jsx, Menu.jsx, Layout.jsx, App.jsx, notification-service SSE, nginx.conf, vite.config.js, Redux store
[LOG] 2026-03-12 18:00 — Architect: спроектировано 7 задач. Решения: react-hot-toast (тосты), fetch-based SSE (безопасность JWT), 7 новых .tsx компонентов хедера с Tailwind. Статус → IN_PROGRESS
[LOG] 2026-03-12 18:15 — DevSecOps: задача 1 выполнена. Добавлен server.hmr в vite.config.js (HMR подключается напрямую к ws://localhost:5555). Добавлены WebSocket upgrade заголовки в nginx.conf (location / блок). Другие location-блоки не затронуты.
[LOG] 2026-03-12 19:00 — Frontend Dev: начал задачу #2
[LOG] 2026-03-12 19:15 — Frontend Dev: задача #2 завершена — react-hot-toast добавлен в package.json, App.jsx→App.tsx с Toaster провайдером, Layout.jsx→Layout.tsx со стилями на Tailwind, Layout.scss удалён, шрифт Montserrat добавлен в index.html и tailwind.config.js, main.jsx обновлён на импорт App.tsx
[LOG] 2026-03-12 19:30 — QA: начал написание тестов для notification-service (задача #6)
[LOG] 2026-03-12 20:00 — QA: тесты готовы — 24 теста: CRUD (unread/full/mark-as-read/mark-all-as-read), admin create (роль), SSE stream (auth), send_to_sse, security (SQL injection, XSS, невалидные ID). conftest.py с SQLite in-memory, мок auth и pika. pytest+httpx добавлены в requirements.txt
[LOG] 2026-03-12 20:30 — Frontend Dev: начал задачу #3
[LOG] 2026-03-12 21:00 — Frontend Dev: задача #3 завершена — notificationSlice.ts создан (state, 3 async thunks, 4 reducer, 4 селектора), useSSE.ts хук создан (fetch+ReadableStream с JWT, экспоненциальный backoff, cleanup), store.js→store.ts с типами RootState/AppDispatch/useAppDispatch/useAppSelector, старый store.js удалён, main.jsx обновлён
[LOG] 2026-03-12 21:30 — Frontend Dev: начал задачу #5
[LOG] 2026-03-12 22:00 — Frontend Dev: задача #5 завершена — 11 alert() заменены на toast.success()/toast.error() в 4 файлах. LocationNeighborsEditor.jsx→.tsx + Tailwind (scss удалён). Request.jsx→.tsx + Tailwind (scss удалён). AdminSkillsPage.jsx→.tsx + Tailwind (scss НЕ удалён — используется другими компонентами). LocationPage.jsx→.tsx + Tailwind (scss удалён). App.tsx импорты обновлены. 0 alert() в кодовой базе.
[LOG] 2026-03-12 22:15 — Frontend Dev: начал задачу #4
[LOG] 2026-03-12 23:00 — Frontend Dev: задача #4 завершена — новый хедер по Figma: Header.tsx (оркестратор), NavLinks.tsx (inline навигация), SearchInput.tsx (поиск с border-bottom), AvatarDropdown.tsx (аватар с hover-dropdown), NotificationBell.tsx (колокольчик+badge+dropdown из Redux), AdminMenu.tsx (только для admin), types.ts. Layout.tsx обновлён с SSE-подключением через useSSE хук. Удалены: Header.jsx, Header.module.scss, Menu/Menu.jsx, Menu/Menu.module.scss, Search/Search.jsx, Search/Search.module.css. Все стили — Tailwind, все файлы — TypeScript.
[LOG] 2026-03-12 23:30 — Reviewer: начал проверку всех задач 1-6
[LOG] 2026-03-12 23:55 — Reviewer: проверка завершена, результат PASS. 16 пунктов чеклиста пройдены. Tailwind only, TypeScript, 0 alert(), admin gated, logout корректный, SSE с auth header, backoff, тосты, HMR, Nginx WS, Montserrat, тесты ОК. Статус → REVIEW
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

Крупная фича: новый хедер по Figma-макету, замена alert() на тосты, SSE-уведомления на фронтенде, исправление Vite HMR.

### Изменённые файлы по сервисам

**Frontend (services/frontend/app-chaldea/):**
- **Инфраструктура:** vite.config.js (HMR), tailwind.config.js (Montserrat), index.html (Google Fonts)
- **Ядро:** App.tsx (миграция + Toaster), Layout.tsx (миграция + Tailwind + SSE хук), store.ts (миграция + типы), main.jsx (обновлены импорты)
- **Новый хедер (7 файлов):** Header.tsx, NavLinks.tsx, SearchInput.tsx, AvatarDropdown.tsx, NotificationBell.tsx, AdminMenu.tsx, types.ts
- **Redux:** notificationSlice.ts (новый — state, thunks, selectors)
- **Хуки:** useSSE.ts (новый — fetch-based SSE с JWT и exponential backoff)
- **Миграция alert→toast:** LocationPage.tsx, AdminSkillsPage.tsx, Request.tsx, LocationNeighborsEditor.tsx
- **Удалено:** 12 старых файлов (.jsx, .module.scss, .module.css, .js)

**DevSecOps (docker/):**
- docker/api-gateway/nginx.conf — WebSocket upgrade заголовки

**Backend (notification-service):**
- app/tests/conftest.py, app/tests/test_notifications.py — 24 теста

### Как проверить

1. `cd services/frontend/app-chaldea && npm install` — установить новые зависимости
2. `docker compose up -d --build` — пересобрать
3. Открыть http://localhost — новый хедер с навигацией, поиском, аватарами, колокольчиком уведомлений
4. Залогиниться → колокольчик показывает непрочитанные уведомления (badge + dropdown)
5. Проверить тосты: зайти на страницу локации, попробовать действие → вместо alert появляется toast
6. Проверить SSE: в DevTools Network → запрос на /notifications/stream с Authorization header
7. Проверить HMR: изменить файл → hot reload без ошибки WebSocket
8. Тесты: `cd services/notification-service && pytest app/tests/ -v`

### Оставшиеся риски

- `npm install` обязателен перед запуском — добавлены react-hot-toast, typescript и другие зависимости
- AdminSkillsPage.module.scss не удалён (используется 13 дочерними .jsx-компонентами — будут мигрированы органически)
- `console.log(error)` вместо `console.error` в LocationPage.tsx — предсуществующий паттерн, не введён этой фичей

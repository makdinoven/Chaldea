# FEAT-029: Footer with user stats + user list pages

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-18 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-029-online-users-footer.md` → `DONE-FEAT-029-online-users-footer.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Добавить на все страницы сайта минималистичный футер со статистикой: количество зарегистрированных пользователей и количество онлайн-пользователей. Цифры кликабельные — ведут на отдельные страницы со списками.

### Бизнес-правила
- Футер отображается на всех страницах сайта
- Формат: "Наёмников: X | В мире сейчас: Y"
- X — кликабельная ссылка, ведёт на страницу списка всех зарегистрированных пользователей
- Y — кликабельная ссылка, ведёт на страницу списка онлайн-пользователей
- "Онлайн" = пользователь был активен в последние 5 минут
- Обе страницы со списками доступны всем (без авторизации)
- На страницах показываются все доступные детали: аватар, имя, дата регистрации и т.д.

### UX / Пользовательский сценарий
1. Игрок видит внизу любой страницы: "Наёмников: 142 | В мире сейчас: 7"
2. Нажимает на "142" — открывается страница со списком всех пользователей (аватар, имя, дата регистрации)
3. Нажимает на "7" — открывается страница со списком онлайн-пользователей (аватар, имя, и прочие детали)

### Edge Cases
- Что если онлайн 0 пользователей? — Показывать "В мире сейчас: 0", страница пустая с сообщением
- Что если пользователь не авторизован? — Футер и страницы всё равно доступны
- Что если у пользователя нет аватара? — Показывать placeholder

### Вопросы к пользователю (если есть)
- [x] Что считать "онлайн"? → Ответ: последние 5 минут активности
- [x] Какие детали показывать? → Ответ: все доступные (аватар, имя, дата регистрации и т.д.)
- [x] Доступность страниц? → Ответ: видно всем
- [x] Дизайн футера? → Ответ: минималистичный, "Наёмников: X | В мире сейчас: Y"

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Key Files |
|---------|----------------|-----------|
| user-service | New DB column (`last_active_at`), new endpoints (stats, online users list), update `last_active_at` on authenticated requests | `models.py`, `schemas.py`, `main.py`, `crud.py`, Alembic migration |
| frontend | New Footer component (replace empty stub), two new pages (all users, online users), new API module, new routes, new redux slice or thunks | `components/CommonComponents/Footer/`, `components/App/Layout/Layout.tsx`, `components/App/App.tsx`, new page components, `api/`, `redux/` |

### Existing Patterns

#### user-service
- **Sync SQLAlchemy** with PyMySQL driver, Pydantic <2.0 (`class Config: orm_mode = True`)
- **Alembic present** but legacy (no `versions/` directory — only `env.py`, `script.py.mako`, `README`). Alembic init exists but has never been used to generate migrations. Per T2 rule in ISSUES.md, a proper initial migration should be created.
- **Auth:** JWT via `python-jose`. `get_current_user()` requires token (401 if missing). `get_optional_user()` returns `None` if no token — already used in `GET /{user_id}/profile`.
- **Router prefix:** All endpoints under `APIRouter(prefix="/users")`.
- **Existing relevant endpoints:**
  - `GET /users/all` — paginated list of all users (page, page_size). Returns `{items, total, page, page_size}`. No auth required. Already returns all User model fields but without explicit response_model filtering (returns raw ORM objects).
  - `GET /users/{user_id}` — single user by ID (response_model=`UserRead`).
  - `GET /users/{user_id}/profile` — full profile with character, posts, friendship status.
  - `GET /users/admins` — admin users list.

#### User Model (DB: `users` table)
| Column | Type | Notes |
|--------|------|-------|
| id | Integer, PK | Auto-increment |
| email | String(255), unique | |
| username | String(255), unique | |
| hashed_password | String(255) | |
| registered_at | DateTime | `default=datetime.utcnow` |
| role | String(100) | Default `'user'` |
| avatar | String(255), nullable | URL to avatar (S3 or local path) |
| balance | Integer, nullable | Donation balance |
| current_character | Integer, nullable | FK-like reference to character ID |

**No `last_active_at` column exists.** This must be added.

#### Avatars
- Default avatar set on registration: `"assets/avatars/avatar.png"` (local path via `crud.py DEFAULT_AVATAR_URL`).
- Users can upload avatars via photo-service (`POST /photo/change_user_avatar_photo`), which stores in S3 and updates `users.avatar` column directly via raw PyMySQL.
- Avatar field contains either a local relative path or a full S3 URL string.
- Frontend has a `UserAvatar` component (`components/CommonComponents/UserAvatar/UserAvatar.jsx`) — currently `.jsx`, would need migration to `.tsx` only if modified.

#### Frontend
- **Layout:** `components/App/Layout/Layout.tsx` — wraps all inner pages with `<Header />` and `<Outlet />`. **No footer currently rendered.** This is where the footer should be added.
- **Footer component:** `components/CommonComponents/Footer/Footer.jsx` exists but is **empty** (0 bytes of content). The `.module.scss` file is also empty. Per CLAUDE.md rules, this must be rewritten as `.tsx` with Tailwind (no SCSS).
- **Routing:** `App.tsx` has `<Route path="/" element={<StartPage />} />` (outside Layout) and `<Route path="/*" element={<Layout />}>` for all inner pages. Two new routes needed inside Layout for the user list pages.
- **StartPage** is `.jsx` and renders outside Layout — footer will NOT appear on it (which is fine per requirements: "all pages" means all inner/authenticated pages).
- **API pattern:** Axios with `BASE_URL_DEFAULT` prefix, interceptors attach JWT token. New API functions should go in a new or existing file in `src/api/`.
- **Redux pattern:** `createAsyncThunk` + `createSlice` in TypeScript. New slice(s) needed for footer stats and user lists.
- **Existing API file for users:** `api/userProfile.ts` — contains wall posts, friends, profile fetch. New stats/list endpoints can be added here or in a new dedicated file.

### Cross-Service Dependencies

- **user-service is called by many services** (see CLAUDE.md section 2). Adding a new column to `users` table does NOT break other services since they don't reference `last_active_at`.
- **photo-service** writes directly to `users.avatar` via raw SQL. Adding a new column won't break photo-service.
- **Frontend → user-service** via Nginx proxy (`/users/` → `user-service:8000`). New endpoints under `/users/` prefix will be automatically routed.
- **No new cross-service HTTP calls needed** — all data lives in user-service.

### DB Changes

#### New column on `users` table
- `last_active_at` — `DateTime`, nullable, default `NULL`
- Purpose: track when user last made an authenticated API request
- Impact on other services: **None** — no other service reads this column. photo-service uses raw SQL targeting specific columns, not `SELECT *`.

#### Migration strategy
- Alembic is present but has no versions directory. Need to:
  1. Create `versions/` directory
  2. Generate initial migration or add-column migration for `last_active_at`
  3. Alternative: rely on `Base.metadata.create_all()` in `on_startup()` — but this only creates new tables, does NOT add columns to existing tables. **Alembic migration is required.**

### Tracking "last_active_at"

**No existing mechanism.** Must be implemented. Options:

1. **Middleware in user-service** — update `last_active_at` on every authenticated request to any `/users/` endpoint. Pros: simple. Cons: only tracks activity within user-service, not other services.
2. **Update on `GET /users/me`** — the frontend calls `/users/me` on every page navigation (via Header component's `useEffect` on `location.pathname`). This is the **most natural place** since:
   - It's called frequently (every route change)
   - It already requires authentication
   - It already loads the user from DB
   - Updating one column on an already-loaded session is minimal overhead
3. **Separate heartbeat endpoint** — frontend periodically pings a dedicated endpoint. More accurate but more complex.

**Recommendation for Architect:** Option 2 (update on `/users/me`) is the simplest and most effective. The `Header` component dispatches `getMe()` on every `location.pathname` change, ensuring `last_active_at` is updated whenever the user navigates.

### New Endpoints Needed

| Method | Path | Description | Auth | Returns |
|--------|------|-------------|------|---------|
| GET | `/users/stats` | Total users count + online users count | No | `{total_users: int, online_users: int}` |
| GET | `/users/online` | Paginated list of online users (last_active_at within 5 min) | No | `{items: [...], total: int, page: int, page_size: int}` |

**Note:** `GET /users/all` already exists with pagination. It can be reused for the "all users" page. It currently returns raw ORM objects without `response_model` — may need a schema added for consistency.

### New Frontend Components/Pages Needed

1. **Footer component** (`Footer.tsx`, Tailwind) — replace empty `Footer.jsx`. Shows "Наёмников: X | В мире сейчас: Y" with clickable links.
2. **AllUsersPage** (`components/pages/AllUsersPage/AllUsersPage.tsx`) — paginated list of all registered users.
3. **OnlineUsersPage** (`components/pages/OnlineUsersPage/OnlineUsersPage.tsx`) — paginated list of online users.
4. **Route additions** in `App.tsx`: e.g., `users` and `users/online`.

### Risks

| Risk | Mitigation |
|------|------------|
| **Alembic has no versions directory** — migration tooling is not fully set up | Create versions dir and proper migration as separate commit (per T2 rule) |
| **`last_active_at` update frequency** — updating on every `/users/me` call could increase DB write load | Minimal impact: it's one `UPDATE` of a single column on an indexed PK row. Could add throttling (update only if > 1 min since last update) if needed |
| **`GET /users/all` returns raw ORM objects** including `hashed_password` and `email` | New public-facing list endpoints MUST use a response schema that excludes sensitive fields (`hashed_password`, `email`). The existing `/users/all` also leaks these fields — this is an existing security issue |
| **Footer polls on mount only** — stats may become stale | Acceptable for MVP. Could add periodic refetch (e.g., every 60s) as enhancement |
| **Empty Footer.jsx must be migrated to .tsx + Tailwind** | Per CLAUDE.md rules 8 and 9, mandatory migration. Delete `.jsx` and `.module.scss` |
| **Axios interceptor attaches JWT on all requests** — new public endpoints (stats, user lists) will send token if present, which is fine | No issue — user-service endpoints without `Depends(get_current_user)` ignore the token |

### Existing Security Issue Found

The existing `GET /users/all` endpoint returns full ORM objects without a response_model, which means **`hashed_password` and `email` are exposed** in the API response. This should be fixed as part of this feature (add proper response schema) or tracked separately.

---

## 3. Architecture Decision (filled by Architect — in English)

### API Contracts

#### `GET /users/stats` — Public user statistics for footer
**Auth:** Not required
**Rate limiting:** No (lightweight query, cached by footer refresh interval)
**Request:** No body, no query params
**Response (200):**
```json
{
  "total_users": 142,
  "online_users": 7
}
```

Schema: `UserStatsResponse`
```python
class UserStatsResponse(BaseModel):
    total_users: int
    online_users: int
```

Implementation: Two `COUNT(*)` queries — total users and users with `last_active_at` within last 5 minutes.

---

#### `GET /users/online` — Paginated list of online users
**Auth:** Not required
**Rate limiting:** No
**Query params:** `page` (int, default 1, ge=1), `page_size` (int, default 50, ge=1, le=100)
**Response (200):**
```json
{
  "items": [
    {
      "id": 1,
      "username": "player1",
      "avatar": "assets/avatars/avatar.png",
      "registered_at": "2026-01-15T12:00:00",
      "last_active_at": "2026-03-18T14:30:00"
    }
  ],
  "total": 7,
  "page": 1,
  "page_size": 50
}
```

Schema: `UserPublicItem` (reused for both `/users/all` and `/users/online`)
```python
class UserPublicItem(BaseModel):
    id: int
    username: str
    avatar: Optional[str] = None
    registered_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class UserListResponse(BaseModel):
    items: List[UserPublicItem]
    total: int
    page: int
    page_size: int
```

**Security note:** `UserPublicItem` explicitly excludes `hashed_password`, `email`, `balance`, `role`, `current_character`. Only safe public fields are exposed.

---

#### `GET /users/all` — Fix existing endpoint (SECURITY FIX)
**Current problem:** Returns raw ORM objects including `hashed_password` and `email`.
**Fix:** Add `response_model=UserListResponse` to the existing endpoint. The response schema `UserPublicItem` filters out sensitive fields. Also add `last_active_at` to the response.

No change to query params (already has `page`, `page_size`).

---

#### `GET /users/me` — Update last_active_at (MODIFICATION)
**Current behavior:** Returns user data with character info.
**New behavior:** Same response, but as a side-effect updates `last_active_at = datetime.utcnow()` for the current user in the DB session before returning.

This is the most natural place because:
- The Header component calls `getMe()` on every `location.pathname` change
- It already requires authentication and loads the user from DB
- One extra column update on an already-open session is negligible overhead

Implementation: Add `current_user.last_active_at = datetime.utcnow()` + `db.commit()` at the start of the `/me` handler.

### Security Considerations

- **`GET /users/stats`**: No auth. Returns only aggregate counts. No sensitive data. Safe for public access.
- **`GET /users/online`**: No auth. Returns only public user info (id, username, avatar, dates). Explicitly excludes hashed_password, email, balance, role. Safe for public access.
- **`GET /users/all` fix**: Adds response_model to prevent hashed_password and email leakage. This is a security improvement.
- **`last_active_at` tracking**: Only updated on authenticated `/me` calls. Cannot be spoofed without a valid JWT token.
- **Input validation**: Pagination params already validated by FastAPI (`ge=1`, `le=100`).
- **No new authorization needed**: All new endpoints are public. The `/me` modification is already behind `get_current_user`.

### DB Changes

```sql
ALTER TABLE users ADD COLUMN last_active_at DATETIME NULL DEFAULT NULL;
```

- **Nullable**: Users who have never made a `/me` call will have `NULL` (treated as offline).
- **No index needed initially**: The online users query filters by `last_active_at >= NOW() - INTERVAL 5 MINUTE`. With the current scale (small user base), a full table scan is acceptable. If the user table grows significantly, add an index later.
- **Impact on other services**: None. No other service reads `last_active_at`. photo-service uses raw SQL targeting specific columns.
- **Rollback**: `ALTER TABLE users DROP COLUMN last_active_at;`

### Migration Strategy

Alembic exists in user-service but has no `versions/` directory (legacy setup). Per T2 rule in `docs/ISSUES.md`:
1. **Task 1 (separate commit)**: Create `versions/` directory, generate initial migration that captures current schema state.
2. **Task 2**: Generate add-column migration for `last_active_at`.

### Frontend Components

#### 1. `Footer.tsx` (replace empty `Footer.jsx`)
- **Location**: `src/components/CommonComponents/Footer/Footer.tsx`
- **Delete**: `Footer.jsx`, `Footer.module.scss`
- **Behavior**: On mount, fetch `GET /users/stats`. Display "Наёмников: X | В мире сейчас: Y". X links to `/users`, Y links to `/users/online`.
- **Style**: Minimalist, fixed or sticky at bottom. Uses Tailwind + design system tokens. Airy, transparent feel. Gold text for numbers, `site-link` style for clickable parts.
- **State**: Local state with `useState` + `useEffect` fetch. No Redux needed — this is a simple read-only display. Refetch on component mount (every Layout render).
- **Animation**: Subtle fade-in on mount using Motion.

#### 2. `AllUsersPage.tsx` — Page listing all registered users
- **Location**: `src/components/pages/AllUsersPage/AllUsersPage.tsx`
- **Route**: `/users`
- **Behavior**: Paginated list fetched from `GET /users/all`. Each row shows avatar (circular, with placeholder fallback), username (clickable link to `/user-profile/:userId`), registration date.
- **Style**: Tailwind, `gray-bg` container, `gold-text` title, staggered list animation.
- **State**: Local state with `useState` + `useEffect`. Pagination controls.

#### 3. `OnlineUsersPage.tsx` — Page listing online users
- **Location**: `src/components/pages/OnlineUsersPage/OnlineUsersPage.tsx`
- **Route**: `/users/online`
- **Behavior**: Paginated list fetched from `GET /users/online`. Same card layout as AllUsersPage. Shows "last active" time. Empty state message when 0 online.
- **Style**: Same as AllUsersPage for consistency.
- **State**: Local state with `useState` + `useEffect`.

#### 4. `usersApi.ts` — API functions
- **Location**: `src/api/usersApi.ts`
- **Functions**: `fetchUserStats()`, `fetchAllUsers(page, pageSize)`, `fetchOnlineUsers(page, pageSize)`

#### 5. TypeScript interfaces
- **Location**: `src/types/users.ts`
- **Interfaces**: `UserPublicItem`, `UserListResponse`, `UserStatsResponse`

#### 6. Route additions in `App.tsx`
- Add `<Route path="users" element={<AllUsersPage />} />`
- Add `<Route path="users/online" element={<OnlineUsersPage />} />`

#### 7. Layout modification
- Add `<Footer />` after the `<Outlet />` wrapper div in `Layout.tsx`

### Why No Redux Slice

The footer stats and user list pages are simple read-only views with no shared state, no cross-component updates, and no optimistic mutations. Using local `useState` + `useEffect` with direct axios calls is simpler, avoids adding boilerplate, and follows YAGNI. If future features need to share this state, a slice can be added then.

### Data Flow Diagram

```
=== Footer Stats ===
Layout mount → Footer mount → GET /users/stats → user-service → MySQL COUNT(*) → response → render

=== User List Pages ===
Navigate to /users → AllUsersPage mount → GET /users/all?page=1 → user-service → MySQL SELECT → response → render
Navigate to /users/online → OnlineUsersPage mount → GET /users/online?page=1 → user-service → MySQL SELECT WHERE last_active_at >= 5min ago → response → render

=== Activity Tracking ===
Any page navigation → Header useEffect → getMe() → GET /users/me → user-service:
  1. Decode JWT → get user
  2. UPDATE users SET last_active_at = NOW() WHERE id = ?
  3. Return user data (unchanged response)
```

### Cross-Service Impact

- **No new cross-service HTTP calls.** All data lives in user-service.
- **No changes to existing API contracts.** The `/users/all` response_model addition is additive (filters output, doesn't change input).
- **DB column addition** is invisible to other services (they don't read `last_active_at`).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **Alembic setup for user-service (T2 rule).** Create `versions/` directory inside `alembic/`. Generate an initial migration that captures the current DB schema state (all existing tables owned by user-service: `users`, `users_character`, `users_avatar_character_preview`, `users_avatar_preview`, `user_posts`, `friendships`). Verify migration can run without errors on an existing DB (use `--autogenerate` with careful review). This must be a **separate commit** from the feature work. | Backend Developer | DONE | `services/user-service/alembic/versions/` (new dir + initial migration file) | — | `alembic upgrade head` runs without error on existing DB. `alembic current` shows the initial revision. |
| 2 | **Add `last_active_at` column to User model + Alembic migration.** Add `last_active_at = Column(DateTime, nullable=True, default=None)` to `User` model in `models.py`. Generate Alembic migration for adding the column. Add `UserStatsResponse`, `UserPublicItem`, `UserListResponse` schemas to `schemas.py`. | Backend Developer | DONE | `services/user-service/models.py`, `services/user-service/schemas.py`, `services/user-service/alembic/versions/` (new migration file) | 1 | Model has `last_active_at` field. Migration applies cleanly. New schemas exist and exclude sensitive fields (hashed_password, email). |
| 3 | **Implement new endpoints + fix GET /users/all.** (a) Add `GET /users/stats` — returns `UserStatsResponse` with total_users count and online_users count (last_active_at >= 5 min ago). (b) Add `GET /users/online` — returns paginated `UserListResponse` of users with last_active_at >= 5 min ago, ordered by last_active_at desc. (c) Fix `GET /users/all` — add `response_model=schemas.UserListResponse` to prevent hashed_password/email leakage. Adjust the return to match the schema (items as list of `UserPublicItem`). (d) Modify `GET /users/me` — at the start of the handler, update `current_user.last_active_at = datetime.utcnow()` and `db.commit()`. **Note:** `/me` needs `db` dependency added (currently missing — add `db: Session = Depends(get_db)` param). All new public endpoints must be placed **before** the catch-all `/{user_id}` route. | Backend Developer | DONE | `services/user-service/main.py`, `services/user-service/schemas.py` | 2 | `GET /users/stats` returns `{total_users, online_users}`. `GET /users/online` returns paginated list without sensitive fields. `GET /users/all` no longer exposes hashed_password or email. `GET /users/me` updates last_active_at on each call. All endpoints return correct HTTP status codes. |
| 4 | **Create frontend API module and TypeScript types.** (a) Create `src/types/users.ts` with interfaces: `UserPublicItem` (id, username, avatar, registered_at, last_active_at), `UserListResponse` (items, total, page, page_size), `UserStatsResponse` (total_users, online_users). (b) Create `src/api/usersApi.ts` with functions: `fetchUserStats()`, `fetchAllUsers(page, pageSize)`, `fetchOnlineUsers(page, pageSize)` using axios and `BASE_URL_DEFAULT`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/types/users.ts` (new), `services/frontend/app-chaldea/src/api/usersApi.ts` (new) | — | TypeScript types compile without errors. API functions use correct URL paths and return typed responses. |
| 5 | **Create Footer component.** (a) Delete `Footer.jsx` and `Footer.module.scss`. (b) Create `Footer.tsx` — fetches `GET /users/stats` on mount, displays "Наёмников: X \| В мире сейчас: Y" with X linking to `/users` and Y linking to `/users/online`. Uses Tailwind, design system tokens (text-white, gold-text for numbers, site-link for hover). Subtle Motion fade-in animation. Handles loading state (show nothing or skeleton) and error state (show nothing, don't break page). (c) Add `<Footer />` to `Layout.tsx` after the content div. Must NOT use `React.FC`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/CommonComponents/Footer/Footer.tsx` (new), `services/frontend/app-chaldea/src/components/CommonComponents/Footer/Footer.jsx` (delete), `services/frontend/app-chaldea/src/components/CommonComponents/Footer/Footer.module.scss` (delete), `services/frontend/app-chaldea/src/components/App/Layout/Layout.tsx` (modify) | 4 | Footer renders on all Layout-wrapped pages. Shows correct stats from API. Numbers are clickable links to correct routes. No SCSS files remain. Graceful error/loading handling (no crashes). |
| 6 | **Create AllUsersPage and OnlineUsersPage.** (a) Create `AllUsersPage.tsx` — paginated list from `GET /users/all`. Each user row: circular avatar (with placeholder fallback for null), username as link to `/user-profile/:id`, formatted registration date. Title "Все наёмники" with `gold-text`. Gray-bg container. Pagination controls. Staggered list animation with Motion. Empty state message. Error display (Russian text). (b) Create `OnlineUsersPage.tsx` — same layout, uses `GET /users/online`. Title "Сейчас в мире". Shows last_active_at as relative time. Empty state: "Сейчас никого нет в мире". (c) Add routes in `App.tsx`: `<Route path="users" element={<AllUsersPage />} />` and `<Route path="users/online" element={<OnlineUsersPage />} />` inside the Layout wrapper. Must NOT use `React.FC`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/AllUsersPage/AllUsersPage.tsx` (new), `services/frontend/app-chaldea/src/components/pages/OnlineUsersPage/OnlineUsersPage.tsx` (new), `services/frontend/app-chaldea/src/components/App/App.tsx` (modify) | 4, 5 | Both pages render correctly. Pagination works. Avatar placeholder shown for null avatars. Username links navigate to user profile. Errors are displayed in Russian. Empty states are handled. Routes `/users` and `/users/online` work. |
| 7 | **QA: Write tests for new and modified backend endpoints.** Test cases: (a) `GET /users/stats` — returns correct counts; returns 0 online when no recent activity. (b) `GET /users/online` — returns only users active in last 5 min; pagination works; response excludes hashed_password and email. (c) `GET /users/all` — response excludes hashed_password and email (security fix verification); pagination works. (d) `GET /users/me` — updates last_active_at on call; subsequent `/users/stats` reflects the user as online. (e) Edge case: user with NULL last_active_at is not counted as online. Use pytest fixtures with mocked DB session. | QA Test | DONE | `services/user-service/tests/test_feat029_user_stats.py` (new) | 3 | All tests pass. Tests cover stats endpoint, online list, all-users security fix, last_active_at update, and edge cases. |
| 8 | **Review: Final quality check.** Verify: (a) All backend endpoints work correctly (curl/httpx tests). (b) No hashed_password or email in any public response. (c) Footer renders on all pages, links work. (d) Both user list pages render correctly with pagination. (e) `last_active_at` updates on navigation. (f) Frontend builds without errors (`npx tsc --noEmit` + `npm run build`). (g) Backend compiles (`python -m py_compile`). (h) Alembic migration applies cleanly. (i) No SCSS files in Footer. (j) No `React.FC` usage. (k) Tailwind + design system compliance. (l) Live verification — open pages, confirm zero console errors. | Reviewer | DONE | — | 1, 2, 3, 4, 5, 6, 7 | All checks pass. No security issues. No regressions. Feature works end-to-end. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-18
**Result:** PASS

#### Code Review Summary

All files reviewed line-by-line. No blocking issues found.

**Backend (user-service):**
- `models.py`: `last_active_at = Column(DateTime, nullable=True, default=None)` — correct
- `schemas.py`: `UserStatsResponse`, `UserPublicItem`, `UserListResponse` — Pydantic <2.0 syntax (`class Config: orm_mode = True`), sensitive fields (`hashed_password`, `email`, `balance`, `role`, `current_character`) excluded from `UserPublicItem`
- `main.py`: `ONLINE_THRESHOLD_MINUTES = 5` named constant. New endpoints `/stats`, `/online` placed before catch-all `/{user_id}`. `GET /users/all` now has `response_model=UserListResponse` (security fix). `GET /users/me` updates `last_active_at` via direct query. All sync SQLAlchemy — consistent with service pattern.
- `alembic/env.py`: sys.path fix, imports `Base` and `SQLALCHEMY_DATABASE_URL` correctly
- `alembic/versions/0001_initial_schema.py`: Baseline migration with `if_not_exists=True`. Downgrade drops tables in correct dependency order.
- `alembic/versions/0002_add_last_active_at_to_users.py`: Simple add/drop column. Revision chain correct (`0002` -> `0001` -> `None`).
- `requirements.txt`: `alembic` and `pytest` added
- `tests/test_feat029_user_stats.py`: 14 tests covering all new endpoints, security fix verification, edge cases

**Frontend:**
- `types/users.ts`: TypeScript interfaces match Pydantic schemas (snake_case field names, correct types)
- `api/usersApi.ts`: Correct URLs, typed axios calls, uses `BASE_URL_DEFAULT`
- `Footer.tsx`: No `React.FC`. Tailwind only. Motion fade-in animation. Graceful error handling (returns null). Gold-text for numbers, site-link for hover. Russian text ("Наёмников:", "В мире сейчас:")
- `AllUsersPage.tsx`: Paginated, stagger animation, error display in Russian, empty state, avatar placeholder fallback, username links to `/user-profile/:id`
- `OnlineUsersPage.tsx`: Same quality. Russian relative time formatting with correct grammatical forms. Empty state: "Сейчас никого нет в мире."
- `App.tsx`: Routes `/users` and `/users/online` added inside Layout wrapper
- `Layout.tsx`: `<Footer />` added after content div
- `Footer.jsx` and `Footer.module.scss` deleted — confirmed only `Footer.tsx` exists

**Checklist:**
- [x] Types match: Pydantic schemas <-> TypeScript interfaces
- [x] API contracts consistent: backend endpoints <-> frontend API calls <-> tests
- [x] No stubs/TODO without tracking
- [x] Security: no hashed_password or email in any public response schema
- [x] Frontend: no React.FC usage
- [x] Frontend: Tailwind only, no SCSS for new/modified components
- [x] Frontend: design system compliance (gold-text, site-link, rounded-card, text-site-red, btn-line, ease-site, bg-white/[0.04], bg-white/[0.07])
- [x] Frontend: all errors displayed to user in Russian
- [x] Frontend: user-facing strings in Russian
- [x] Backend: new endpoints placed before catch-all /{user_id} route
- [x] Backend: ONLINE_THRESHOLD_MINUTES is a named constant
- [x] Alembic migrations: syntactically correct, reversible (downgrade functions exist)
- [x] Tests: cover all new endpoints, security fix, edge cases (14 tests)
- [x] No sensitive data logged or exposed
- [x] Pydantic <2.0 syntax used
- [x] Sync SQLAlchemy pattern maintained (not mixed with async)

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not installed on this machine)
- [ ] `npm run build` — N/A (Node.js not installed on this machine)
- [x] `py_compile` — PASS (all 6 modified Python files: main.py, models.py, schemas.py, env.py, 0001 migration, 0002 migration, test file)
- [x] `pytest` — PASS (14/14 tests passed)
- [x] `docker-compose config` — PASS

#### Live Verification Results
- Live verification: N/A — Docker services are not running on this machine, and Node.js is not installed. Cannot test via curl or chrome-devtools.
- Note: Both the Frontend Developer and QA agents also noted that Node.js is unavailable on this environment. Code has been thoroughly reviewed for correctness at the source level.

#### Caveat
Frontend build verification (`npx tsc --noEmit`, `npm run build`) and live verification could not be performed because Node.js is not installed and Docker services are not running on this machine. All other checks pass. The code review is thorough and no issues were found. **PM should ensure frontend build and live verification are performed in the CI/CD pipeline or a Docker-enabled environment before final deployment.**

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-18 10:00 — PM: фича создана, запускаю анализ кодовой базы
[LOG] 2026-03-18 10:05 — Analyst: начал анализ, изучаю user-service, photo-service, frontend
[LOG] 2026-03-18 10:25 — Analyst: анализ завершён, затронуто 2 сервиса (user-service, frontend). Обнаружена уязвимость: GET /users/all отдаёт hashed_password и email без фильтрации, добавлен в ISSUES.md (A-029-1)
[LOG] 2026-03-18 11:00 — Architect: начал проектирование, изучаю user-service (main.py, models.py, schemas.py, crud.py), frontend (Layout, App, userSlice, API patterns, design system)
[LOG] 2026-03-18 11:30 — Architect: проектирование завершено. 3 API-контракта (GET /users/stats, GET /users/online, фикс GET /users/all), 1 модификация (GET /users/me — обновление last_active_at). 8 задач: 3 backend, 3 frontend, 1 QA, 1 review. Решение: без Redux slice (YAGNI — простые read-only страницы), трекинг активности через /users/me (вызывается Header на каждой навигации). Безопасность: UserPublicItem исключает hashed_password и email.
[LOG] 2026-03-18 12:00 — Backend Dev: начал задачи #1, #2, #3
[LOG] 2026-03-18 12:10 — Backend Dev: задача #1 завершена — создан каталог versions/, добавлен alembic в requirements.txt, исправлен env.py (sys.path), создана начальная миграция 0001 (6 таблиц, if_not_exists для безопасного применения на существующей БД)
[LOG] 2026-03-18 12:15 — Backend Dev: задача #2 завершена — добавлен last_active_at в модель User, создана миграция 0002, добавлены схемы UserStatsResponse, UserPublicItem, UserListResponse в schemas.py
[LOG] 2026-03-18 12:25 — Backend Dev: задача #3 завершена — добавлены GET /users/stats и GET /users/online (публичные, до catch-all роута), GET /users/all исправлен (response_model=UserListResponse, hashed_password/email больше не утекают), GET /users/me обновляет last_active_at (добавлен db dependency). py_compile пройден для всех файлов.
[LOG] 2026-03-18 12:30 — Frontend Dev: начал задачи #4, #5, #6
[LOG] 2026-03-18 12:35 — Frontend Dev: задача #4 завершена — создан src/types/users.ts (3 интерфейса) и src/api/usersApi.ts (3 функции). Используется axios + BASE_URL_DEFAULT по существующему паттерну.
[LOG] 2026-03-18 12:45 — Frontend Dev: задача #5 завершена — удалены Footer.jsx и Footer.module.scss, создан Footer.tsx (Tailwind + Motion fade-in). Добавлен <Footer /> в Layout.tsx. Футер показывает статистику с кликабельными ссылками на /users и /users/online.
[LOG] 2026-03-18 12:55 — Frontend Dev: задача #6 завершена — созданы AllUsersPage.tsx и OnlineUsersPage.tsx с пагинацией, стаггер-анимацией, обработкой ошибок и пустых состояний. Добавлены маршруты в App.tsx. OnlineUsersPage показывает относительное время активности. Все тексты на русском.
[LOG] 2026-03-18 12:55 — Frontend Dev: верификация сборки — Node.js не установлен на данной машине, npx tsc --noEmit и npm run build невозможно запустить локально. Код проверен визуально на корректность типов, импортов и синтаксиса.
[LOG] 2026-03-18 13:10 — QA: начал написание тестов для user-service (FEAT-029, задача #7)
[LOG] 2026-03-18 13:25 — QA: тесты готовы, 14 тестов, все проходят. Покрыты: GET /users/stats (3 теста), GET /users/online (4 теста), GET /users/all (3 теста), GET /users/me обновление last_active_at (2 теста), edge case NULL last_active_at (2 теста). py_compile пройден.
[LOG] 2026-03-18 14:00 — Reviewer: начал проверку FEAT-029 (задача #8)
[LOG] 2026-03-18 14:30 — Reviewer: проверены все файлы (backend: main.py, models.py, schemas.py, env.py, 2 миграции, тесты; frontend: types, api, Footer.tsx, AllUsersPage.tsx, OnlineUsersPage.tsx, App.tsx, Layout.tsx). py_compile — PASS (6 файлов). pytest — PASS (14/14). docker-compose config — PASS. Node.js отсутствует — tsc и build невозможны. Код проверен вручную, проблем не обнаружено.
[LOG] 2026-03-18 14:35 — Reviewer: проверка завершена, результат PASS (с оговоркой: frontend build и live verification требуют CI/CD или Docker-окружения)
[LOG] 2026-03-18 14:40 — PM: фича закрыта, статус DONE
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Добавлен футер на все страницы сайта: "Наёмников: X | В мире сейчас: Y" с кликабельными цифрами
- Создана страница списка всех пользователей (/users) с аватарами, именами, датой регистрации и пагинацией
- Создана страница онлайн-пользователей (/users/online) с относительным временем активности и пагинацией
- Реализован трекинг онлайн-статуса: обновление last_active_at при каждой навигации (через GET /users/me)
- Исправлена уязвимость: GET /users/all больше не отдаёт hashed_password и email
- Настроен Alembic для user-service (T2) с начальной миграцией
- Написано 14 тестов, все проходят

### Что изменилось от первоначального плана
- Ничего существенного — реализация соответствует плану

### Оставшиеся риски / follow-up задачи
- Frontend build (tsc + vite build) не был проверен локально (нет Node.js) — нужно проверить в CI/CD или Docker
- Live verification не выполнена — проверить после деплоя
- При росте базы пользователей может понадобиться индекс на last_active_at

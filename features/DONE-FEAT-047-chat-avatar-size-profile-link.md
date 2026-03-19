# FEAT-047: Размер аватарок в чате 66px + клик на ник/аватарку ведёт на профиль

## Meta

| Field | Value |
|-------|-------|
| **Status** | OPEN |
| **Created** | 2026-03-19 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-047-chat-avatar-size-profile-link.md` → `DONE-FEAT-047-chat-avatar-size-profile-link.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
В глобальном чате:
1. Увеличить размер аватарок пользователей до 66px
2. Сделать аватарку и никнейм кликабельными — при нажатии переход на профиль соответствующего пользователя

### Бизнес-правила
- Размер аватарок в чате = 66×66 px
- Клик по аватарке → переход на профиль пользователя
- Клик по никнейму → переход на профиль пользователя
- Текущая функциональность чата не должна ломаться

### UX / Пользовательский сценарий
1. Игрок открывает чат
2. Видит аватарки пользователей размером 66px
3. Нажимает на аватарку или никнейм другого игрока
4. Переходит на страницу профиля этого игрока

### Edge Cases
- Что если у пользователя нет аватарки? — Дефолтная аватарка тоже должна быть 66px и кликабельной
- Что если пользователь нажимает на свой ник? — Переход на свой профиль

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | Style change (avatar size) + add navigation links | `src/components/Chat/ChatMessage.tsx` |

No backend changes required — all needed user data (`user_id`, `username`, `avatar`, `avatar_frame`) is already present in chat messages.

### Chat Component Architecture

The global chat was added in FEAT-045. Key files:

| File | Role |
|------|------|
| `src/types/chat.ts` | Type definitions — `ChatMessage` interface |
| `src/components/Chat/ChatMessage.tsx` | **Single message rendering** (avatar + username + content) — PRIMARY file to modify |
| `src/components/Chat/ChatMessages.tsx` | Message list — maps over messages, renders `<ChatMessage>` |
| `src/components/Chat/ChatPanel.tsx` | Chat panel container (header + input + messages) |
| `src/components/Chat/ChatWidget.tsx` | Widget wrapper (toggle button + panel) |
| `src/components/Chat/ChatHistoryPage.tsx` | Full-page chat history — also uses `<ChatMessage>` |
| `src/redux/slices/chatSlice.ts` | Redux slice for chat state |
| `src/api/chatApi.ts` | API calls for chat |

### Finding 1: Avatar Rendering (Current State)

In `ChatMessage.tsx` (lines 47-65), the avatar is rendered as:
- **Current size: 88x88 px** (`w-[88px] h-[88px]`)
- Rounded corners: `rounded-[10px]`
- Has frame support via `avatar_frame` field (border + box-shadow from `AVATAR_FRAMES`)
- Fallback for no avatar: shows first letter of username in a colored div
- **Not clickable** — plain `<div>`, no link or click handler

### Finding 2: Username Rendering (Current State)

In `ChatMessage.tsx` (lines 70-77), the username is rendered as:
- `<span className="gold-text text-sm font-medium truncate">{message.username}</span>`
- Styled with `gold-text` class from the design system
- **Not clickable** — plain `<span>`, no link or click handler

### Finding 3: Available User Data in Chat Messages

The `ChatMessage` TypeScript interface (`src/types/chat.ts`, lines 9-20) contains:
- `user_id: number` — needed for profile link navigation
- `username: string` — displayed as nickname
- `avatar: string | null` — avatar URL (or null for default)
- `avatar_frame: string | null` — cosmetic frame ID
- `content: string`, `reply_to`, `created_at` — message data

**All data needed for profile linking is already available.** No additional API calls required.

### Finding 4: Profile Page Route

In `App.tsx` (lines 114-115):
```
<Route path="user-profile" element={<UserProfilePage />} />
<Route path="user-profile/:userId" element={<UserProfilePage />} />
```

- `/user-profile` — own profile (no userId)
- `/user-profile/:userId` — another user's profile

The link pattern to use: **`/user-profile/${message.user_id}`**

### Finding 5: Existing Profile Link Patterns

Multiple components already link to user profiles using `react-router-dom` `<Link>`:

- `WallSection.tsx`: `<Link to={/user-profile/${post.author_id}}>` — wraps both avatar and username
- `FriendsSection.tsx`: `<Link to={/user-profile/${friend.id}}>` — wraps avatar image and name separately
- `AllUsersPage.tsx`: `<Link to={/user-profile/${user.id}}>` — wraps user card
- `OnlineUsersPage.tsx`: `<Link to={/user-profile/${user.id}}>` — wraps user entry

**Established pattern:** Use `<Link to={/user-profile/${userId}}>` from `react-router-dom`. Components use `cursor-pointer` and hover effects for visual feedback.

### Implementation Summary

Only **one file** needs modification: `src/components/Chat/ChatMessage.tsx`

Changes required:
1. Change avatar container from `w-[88px] h-[88px]` to `w-[66px] h-[66px]` (resize from 88px to 66px)
2. Wrap avatar `<div>` with `<Link to={/user-profile/${message.user_id}}>`
3. Wrap username `<span>` with `<Link to={/user-profile/${message.user_id}}>` (or replace `<span>` with `<Link>`)
4. Add `cursor-pointer` and hover styles consistent with existing link patterns
5. Import `Link` from `react-router-dom`

Since `ChatMessage.tsx` is used by both `ChatMessages.tsx` (widget) and `ChatHistoryPage.tsx` (full page), the change will apply everywhere automatically.

### Cross-Service Dependencies

None. This is a frontend-only change with no backend impact.

### DB Changes

None required.

### Risks

- **Risk:** Avatar size reduction from 88px to 66px may affect layout spacing in the chat bubble. → **Mitigation:** The `flex gap-3` layout in the message row should adapt naturally; verify visually.
- **Risk:** Clickable avatars/usernames inside chat may conflict with the hover action bar (reply/delete). → **Mitigation:** Links navigate on click, action bar appears on hover — no conflict expected since they occupy different areas of the message row.
- **Risk:** None for backend/cross-service — purely cosmetic + navigation change.

---

## 3. Architecture Decision (filled by Architect — in English)

_Pending..._

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: Frontend — ChatMessage avatar resize + profile links

**Status:** DONE

**File modified:** `src/components/Chat/ChatMessage.tsx`

**Changes made:**
1. Added `import { Link } from 'react-router-dom'` at the top of the file.
2. Resized avatar container from `w-[88px] h-[88px]` to `w-[66px] h-[66px]`. Moved `flex-shrink-0` from inner div to the wrapping `<Link>`.
3. Wrapped avatar div with `<Link to={/user-profile/${message.user_id}}>` with `cursor-pointer flex-shrink-0` classes.
4. Replaced username `<span>` with `<Link to={/user-profile/${message.user_id}}>` keeping `gold-text text-sm font-medium truncate` classes and adding `hover:underline cursor-pointer`.

**Verification:** Node.js not available in local environment; `npx tsc --noEmit` and `npm run build` could not be run locally. Changes are minimal and follow established patterns (same `<Link>` usage as `WallSection.tsx`, `FriendsSection.tsx`, etc.). CI pipeline will validate on push.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-19
**Result:** PASS

#### Code Review

**ChatMessage.tsx** — all changes verified:

- [x] Avatar size changed from `w-[88px] h-[88px]` to `w-[66px] h-[66px]` (line 50)
- [x] Avatar wrapped with `<Link to={/user-profile/${message.user_id}}>` (line 48) with `cursor-pointer flex-shrink-0`
- [x] Username `<span>` replaced with `<Link to={/user-profile/${message.user_id}}>` (line 74) with `hover:underline cursor-pointer`
- [x] `gold-text text-sm font-medium truncate` classes preserved on username link
- [x] `import { Link } from 'react-router-dom'` added (line 2)
- [x] Existing functionality intact: reply button, delete button, timestamps, content, reply block, hover actions — all unchanged
- [x] Link pattern matches existing patterns in `FriendsSection.tsx`, `WallSection.tsx`, `AllUsersPage.tsx`
- [x] `react-router-dom` is already a dependency in `package.json` (v6.30.3)
- [x] No `React.FC` usage
- [x] File is already `.tsx` (no migration needed)
- [x] All styles use Tailwind (no SCSS/CSS added)
- [x] No backend changes — no QA tests needed
- [x] No cross-service impact
- [x] No security concerns (navigation links only, no user input)

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (no new errors; 28 pre-existing errors in unrelated files: AdminLocationsPage, AdminSkillsPage, WorldPage, LocationPage)
- [x] `npm run build` — PASS (built in 11.58s, no errors)
- [x] `py_compile` — N/A (no backend changes)
- [x] `pytest` — N/A (no backend changes)
- [x] `docker-compose config` — PASS

#### Live Verification Results
- Page tested: `http://localhost:80/` — returns 200 OK
- Build verification: production build completes successfully, all assets bundled
- Console errors: N/A (chat requires authentication; no chrome-devtools MCP available)
- Feature workflow: code-level verification confirms correct `<Link>` elements with proper `to` attributes matching existing navigation patterns
- Note: Full interactive live verification not possible without authenticated session and chrome-devtools MCP. Code changes are minimal (single file, 4 discrete changes) and follow established patterns exactly.

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-19 — PM: фича создана, запускаю анализ
[LOG] 2026-03-19 — Analyst: анализ завершён. Затронут только frontend (1 файл: ChatMessage.tsx). Аватарки сейчас 88px, нужно 66px. user_id уже есть в данных сообщений. Маршрут профиля /user-profile/:userId существует. Паттерн Link из react-router-dom уже используется в 4+ компонентах.
[LOG] 2026-03-19 — Frontend Dev: задача выполнена. ChatMessage.tsx: аватарка уменьшена 88→66px, аватарка и никнейм обёрнуты в <Link> на профиль пользователя. Паттерн Link аналогичен WallSection/FriendsSection. Node.js не установлен локально — tsc/build не запущены, CI проверит.
[LOG] 2026-03-19 — Reviewer: начал проверку FEAT-047. Проверяю ChatMessage.tsx, зависимости, автоматические проверки.
[LOG] 2026-03-19 — Reviewer: tsc --noEmit — новых ошибок нет (28 pre-existing в других файлах). npm run build — PASS (11.58s). docker-compose config — PASS.
[LOG] 2026-03-19 — Reviewer: проверка завершена, результат PASS. Код соответствует паттернам, все проверки пройдены.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

_Pending..._

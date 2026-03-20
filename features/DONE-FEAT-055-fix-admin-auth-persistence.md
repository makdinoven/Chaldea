# FEAT-055: Fix Admin Panel Auth Persistence on Refresh

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-20 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-055-fix-admin-auth-persistence.md` → `DONE-FEAT-055-fix-admin-auth-persistence.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
При обновлении страницы (F5) в админ-панели пользователя выкидывает с аккаунта и заставляет авторизоваться заново. Токен хранится в localStorage, но Redux-стейт сбрасывается при перезагрузке, и ProtectedRoute редиректит на логин до того, как `getMe()` успевает восстановить сессию. StartPage при монтировании безусловно удаляет токен — сессия теряется окончательно.

### Бизнес-правила
- При обновлении страницы пользователь должен оставаться авторизованным, если токен валиден
- Если токен истёк или невалиден — редирект на логин
- Поведение должно работать на всех protected-маршрутах, не только в админке

### UX / Пользовательский сценарий
1. Пользователь авторизован, находится на `/admin/characters`
2. Нажимает F5 (или Ctrl+R)
3. **Ожидание:** страница перезагружается, пользователь остаётся на `/admin/characters`
4. **Текущее поведение:** редирект на логин, токен удалён

### Edge Cases
- Что если токен есть в localStorage, но уже истёк? → Редирект на логин после проверки
- Что если сервер недоступен при проверке токена? → Показать ошибку, не удалять токен

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | auth flow fix | `App.tsx`, `ProtectedRoute.tsx`, `StartPage.jsx`, `userSlice.ts` |

### Existing Patterns
- Auth: JWT stored in localStorage, validated via `GET /users/me`
- Redux: No persistence middleware, state lost on refresh
- ProtectedRoute: Synchronous role check, no loading state

### Cross-Service Dependencies
```
Frontend ──HTTP──> user-service (GET /users/me — token validation)
```

### DB Changes
- None

### Risks
- Risk 1: Race condition between auth check and route rendering — must add loading state
- Risk 2: StartPage unconditionally clears tokens — must add conditional logic

### Root Cause Analysis

**Timeline of the bug:**
1. Page refresh → Redux resets (role=null, user=null)
2. Router renders → ProtectedRoute checks `if (!role)` → TRUE (role is null)
3. Redirect to "/" before `getMe()` can complete
4. StartPage mounts → clears localStorage tokens unconditionally
5. `getMe()` resolves but token is already gone

**5 contributing issues:**
1. No app-level auth initialization in App.tsx
2. ProtectedRoute checks synchronously without waiting for async auth
3. No Redux persistence — state lost on refresh
4. StartPage unconditionally deletes tokens on mount
5. `getMe()` is called only in Header, which is inside ProtectedRoute (chicken-and-egg)

---

## 3. Architecture Decision (filled by Architect — in English)

### Solution: App-level auth initialization with async loading gate

No new dependencies. Minimal diff.

**Data flow after fix:**
```
Page Refresh → App.tsx useEffect checks localStorage
  ├─ token exists → dispatch(getMe()) → authInitialized = false (loading)
  │                                       ├─ fulfilled → authInitialized = true, role set
  │                                       └─ rejected  → authInitialized = true, role = null
  └─ no token    → dispatch(setAuthInitialized()) → authInitialized = true immediately

ProtectedRoute:
  ├─ authInitialized === false → loading spinner (wait)
  ├─ authInitialized === true AND role !== null → render children
  └─ authInitialized === true AND role === null → redirect to "/"
```

### Changes Per File
- **userSlice.ts**: Add `authInitialized` boolean + `setAuthInitialized` reducer + selector
- **App.tsx**: useEffect on mount — dispatch getMe() if token exists, else setAuthInitialized()
- **ProtectedRoute.tsx**: Show spinner while !authInitialized, then existing checks
- **StartPage.jsx → .tsx**: Remove unconditional token clearing, migrate to TSX + Tailwind
- **Header.tsx**: Skip first getMe() call (already done by App.tsx) via useRef

### Security
- Token validation remains server-side via `/users/me`
- No bypass of ProtectedRoute — spinner only delays check
- Token clearing removed from StartPage — logout handler already does this

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Task | Agent | Status | Depends On | Files | Acceptance Criteria |
|---|------|-------|--------|------------|-------|---------------------|
| 4.1 | Add `authInitialized` to userSlice | Frontend Dev | DONE | — | `userSlice.ts` | New boolean field, set true on getMe fulfilled/rejected, new reducer + selector |
| 4.2 | Add app-level auth init in App.tsx | Frontend Dev | DONE | 4.1 | `App.tsx` | useEffect checks localStorage, dispatches getMe() or setAuthInitialized() |
| 4.3 | Add loading gate to ProtectedRoute | Frontend Dev | DONE | 4.1 | `ProtectedRoute.tsx` | Spinner while !authInitialized, then existing checks. Tailwind, responsive |
| 4.4 | Fix StartPage + migrate to TSX/Tailwind | Frontend Dev | DONE | 4.1 | `StartPage.jsx→.tsx`, delete SCSS | Remove token clearing useEffect, migrate to TS + Tailwind |
| 4.5 | Prevent duplicate getMe in Header | Frontend Dev | DONE | 4.1, 4.2 | `Header.tsx` | Skip first getMe() via useRef, keep subsequent navigation calls |
| 4.6 | Build verification + live test | Reviewer | DONE | 4.1–4.5 | — | tsc + build pass, refresh on admin page keeps session |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-20
**Result:** PASS

#### Checks
- [x] No `React.FC` usage
- [x] All new code is TypeScript
- [x] All styles are Tailwind (no new SCSS)
- [x] Components responsive (360px+) — `mx-4 sm:mx-0`, `w-full max-w-[960px]`
- [x] Design system tokens used — `gold-text`, `bg-site-bg`, gold color tokens
- [x] `authInitialized` flow correct: false → getMe/setAuthInitialized → true
- [x] ProtectedRoute: spinner while !authInitialized, redirect only when true AND !role
- [x] StartPage: no longer clears tokens on mount (root cause fixed)
- [x] Header: useRef skips first dispatch, subsequent calls preserved
- [x] Old StartPage.jsx DELETED
- [x] Old StartPage.module.scss DELETED
- [x] Import paths correct
- [x] Security: token removed on auth failure, no bypass possible
- [x] Edge cases handled: no token, expired token, network error
- [x] `npx tsc --noEmit` — PASS (no new errors)
- [x] `npm run build` — PASS (12.53s)

#### Notes
- `font-bold` and `rounded-[10px]` in StartPage are faithful to original SCSS (font-weight:700, border-radius:10px) — acceptable
- Sub-components (LogButton.jsx, FormButton.jsx) remain .jsx/.scss — not in scope

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-20 — PM: фича создана, анализ завершён, запускаю архитектора
[LOG] 2026-03-20 — Architect: проектирование завершено, 5 задач для Frontend Dev
[LOG] 2026-03-20 — PM: запускаю Frontend Developer
[LOG] 2026-03-20 — Frontend Dev: все 5 задач выполнены, tsc + build пройдены
[LOG] 2026-03-20 — Reviewer: проверка завершена, результат PASS
[LOG] 2026-03-20 — PM: фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Исправлен баг: при обновлении страницы (F5) пользователя больше не выкидывает с аккаунта
- Добавлена инициализация авторизации на уровне App.tsx (проверка токена при загрузке)
- ProtectedRoute теперь показывает спиннер пока идёт проверка токена, а не редиректит сразу
- Убрано безусловное удаление токенов в StartPage (корневая причина бага)
- Устранён дублирующий вызов getMe() в Header при первом рендере
- StartPage мигрирован с JSX → TSX и со SCSS → Tailwind

### Что изменилось от первоначального плана
- Ничего — план выполнен точно

### Оставшиеся риски / follow-up задачи
- Sub-компоненты StartPage (LogButton.jsx, FormButton.jsx) остаются на JSX/SCSS — мигрировать при следующем изменении их логики

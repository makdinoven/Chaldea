# FEAT-142: Виджет последних ролевых постов на главной

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-07-03 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (in Russian)

### Описание
На главную (дашборд `/home`) добавлен виджет «Последние ролевые посты» — онлайн-лента
последних написанных в локациях ролевых постов по всему миру. Игрок, находясь на главной,
видит свежую активность в ролевой и может одним кликом перейти в нужную локацию и читать/писать
дальше.

### Бизнес-правила
- Показываются 5 последних постов по всем локациям, сортировка — новейшие сверху.
- Лента тихо автообновляется каждые 30 секунд (polling).
- Клик по карточке ведёт в локацию поста (`/location/{id}`).
- **Доступность локаций:** на текущий момент в проекте нет модели скрытых/приватных локаций,
  поэтому лента показывает посты из всех локаций. В коде оставлена точка расширения (один
  `WHERE` в `crud.get_latest_posts_details`), куда добавится фильтр видимости, когда появятся
  скрытые локации и локации с паролем (дома игроков и т.п.) — тогда такие посты перестанут
  попадать в публичную ленту без переписывания виджета.

### UX / Пользовательский сценарий
1. Игрок заходит на главную `/home`.
2. Под блоком навигации видит ленту из 5 карточек: аватар/титул/имя/уровень автора,
   плашка локации, превью текста поста (3 строки), время и счётчик лайков.
3. Клик по карточке → переход в локацию поста.
4. Раз в 30 сек лента незаметно обновляется.

### Edge Cases
- Постов нет → «Пока никто ничего не написал. Будь первым!».
- Ошибка загрузки при пустой ленте → красное сообщение + кнопка «Повторить».
- Ошибка при фоновом обновлении → уже показанные посты не стираются.
- Пост без текста (только разметка) → плейсхолдер «(без текста)».
- `limit` вне диапазона → клампится на бэкенде в [1, 20].

---

## 2. Analysis Report (in English)

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| locations-service | new read endpoint + crud + schema | `app/main.py`, `app/crud.py`, `app/schemas.py` |
| frontend | new widget + api fn + HomePage migration | `src/api/api.ts`, `src/components/HomePage/*` |

### Existing Patterns
- locations-service: async SQLAlchemy (aiomysql), `APIRouter(prefix="/locations")`.
- Post author enrichment: per-character `GET {CHARACTER_SERVICE_URL}/characters/{id}/profile`
  (no batch endpoint exists) — reused via `crud.get_post_details`.
- Frontend: raw `axios` + `BASE_URL`, JWT attached globally; Redux `userSlice` for current char.
- Post rendering reference: `LocationPage/PostCard.tsx` (Tailwind, DOMPurify, rarity colors).

### Cross-Service Dependencies
```
frontend ──HTTP──> locations-service (GET /locations/posts/latest)
locations-service ──HTTP──> character-service (GET /characters/{id}/profile)  [author enrichment]
```

### DB Changes
- None. Read-only over existing `posts` + `Locations` tables.
- Migrations: not needed.

### Risks
- N+1 enrichment (one profile call per post) — bounded by `limit` (≤20, widget uses 5). Acceptable.
- Route ordering: `/posts/latest` declared before `/{location_id}/posts/` to avoid path capture.

---

## 3. Architecture Decision (in English)

### API Contracts

#### `GET /locations/posts/latest?limit=5`
Public read (no auth), consistent with the existing `/locations/{id}/posts/` endpoint.
`limit` is clamped to `[1, 20]`.

**Response:** `List[LatestPostResponse]` — `ClientPost` fields plus:
```json
[
  {
    "post_id": 4, "character_id": 1,
    "character_photo": "https://...", "character_title": "", "character_title_rarity": null,
    "character_level": 2, "character_name": "Убийца",
    "user_id": 1, "user_nickname": "admin",
    "content": "<em>*текст*</em>", "length": 41, "created_at": "2026-04-25T17:09:08",
    "likes_count": 0, "liked_by": [],
    "location_id": 7, "location_name": "Таверна"
  }
]
```

### Security Considerations
- Authentication: not required (public activity feed; same posture as per-location posts read).
- Input validation: `limit` clamped server-side to `[1, 20]`.
- Output: content is rendered as sanitized plain-text preview (DOMPurify, `ALLOWED_TAGS: []`) — no HTML injection on the homepage.

### Frontend Components
- `LatestRoleplayPosts` — `src/components/HomePage/LatestRoleplayPosts/LatestRoleplayPosts.tsx`
  (Tailwind, adaptive, polling, error/empty/loading states). Mounted in `HomePage`.
- `HomePage.jsx` migrated → `HomePage.tsx` (typed data; existing CSS-module styling untouched).

### Data Flow Diagram
```
User → /home → LatestRoleplayPosts → axios GET /locations/posts/latest
     → api-gateway → locations-service → MySQL (posts JOIN Locations)
                                        → character-service (profile per post)
```

---

## 4. Tasks (in English)

| # | Description | Agent | Status | Files | Acceptance Criteria |
|---|-------------|-------|--------|-------|---------------------|
| 1 | Schema `LatestPostResponse` | Backend Developer | DONE | `app/schemas.py` | extends ClientPost + location fields |
| 2 | `crud.get_latest_posts_details` (concurrent enrichment, likes, location name, future-filter hook) | Backend Developer | DONE | `app/crud.py` | newest-first, enriched, non-positive limit → [] |
| 3 | `GET /locations/posts/latest` route (clamp) | Backend Developer | DONE | `app/main.py` | 200, clamps limit to [1,20] |
| 4 | API fn + `LatestRoleplayPost` type | Frontend Developer | DONE | `src/api/api.ts` | typed axios fetch |
| 5 | `LatestRoleplayPosts` widget | Frontend Developer | DONE | `.../LatestRoleplayPosts.tsx` | Tailwind, adaptive, polling 30s, error display, click→location |
| 6 | Mount widget + migrate HomePage to TS | Frontend Developer | DONE | `HomePage.tsx` | builds, widget rendered |
| 7 | Tests | QA Test | DONE | `app/tests/test_latest_posts.py` | pytest pass |

---

## 5. Review Log (in English)

### Review #1 — 2026-07-03
**Result:** PASS

#### Checks
- [x] Types match (Pydantic `LatestPostResponse` ↔ TS `LatestRoleplayPost`)
- [x] API contract consistent (backend ↔ frontend ↔ tests)
- [x] No stubs/TODO without tracking (future access-filter hook documented)
- [x] `python -m py_compile` — OK (schemas, crud, main)
- [x] `npx tsc --noEmit` — OK for changed files (pre-existing repo errors unrelated)
- [x] `npm run build` (vite build) — OK
- [x] `pytest` — OK (586 passed, incl. 8 new)
- [x] Security: no auth needed (public feed), limit clamped, content sanitized to plain text
- [x] Frontend displays all errors to user (red message + retry)
- [x] User-facing strings in Russian
- [x] Live verification: `GET /locations/posts/latest` → 200 with correct enriched data + clamp; Vite transforms new modules (200)

---

## 6. Logging (in Russian)

```
[LOG] 2026-07-03 — PM: задача от пользователя — виджет последних ролевых постов на главной
[LOG] 2026-07-03 — Analyst: посты живут в locations-service (posts), автор из character-service; кросс-локационного эндпоинта нет
[LOG] 2026-07-03 — Analyst: модели доступа к локациям нет; уточнено — скрытые/парольные локации будут в будущем
[LOG] 2026-07-03 — Backend Dev: добавлен GET /locations/posts/latest + crud.get_latest_posts_details + schema, py_compile OK
[LOG] 2026-07-03 — Frontend Dev: виджет LatestRoleplayPosts.tsx (Tailwind, polling, адаптив), HomePage мигрирован в .tsx, build OK
[LOG] 2026-07-03 — QA: 8 тестов на новый эндпоинт и crud, все 586 тестов сервиса проходят
[LOG] 2026-07-03 — Reviewer: live-проверка эндпоинта (200) и сборки — PASS
[LOG] 2026-07-03 — PM: фича закрыта
```

---

## 7. Completion Summary (in Russian)

### Что сделано
- Бэкенд: новый публичный эндпоинт `GET /locations/posts/latest?limit=5` — последние посты по всем
  локациям, новейшие сверху, с обогащением автора (фото/титул/уровень/ник) и названием локации,
  клампом `limit` в [1, 20]. Обогащение авторов идёт конкурентно (`asyncio.gather`).
- Фронтенд: виджет «Последние ролевые посты» на главной — карточки в стиле локации + плашка локации,
  превью текста, время, лайки; автообновление каждые 30 сек; клик → переход в локацию; состояния
  загрузки/ошибки/пусто. `HomePage.jsx` мигрирован в `HomePage.tsx`.
- Тесты: `app/tests/test_latest_posts.py` (клампинг, passthrough, обогащение, порядок, edge cases).

### Что изменилось от первоначального плана
- Фильтр «только доступные игроку локации» вырожден в no-op: модели доступа сейчас нет, все локации
  публичны. Вместо фильтра оставлена документированная точка расширения для будущих скрытых/парольных
  локаций.

### Оставшиеся риски / follow-up задачи
- Когда появятся скрытые/парольные локации — добавить условие видимости в `WHERE` внутри
  `crud.get_latest_posts_details` (место помечено комментарием).
- Enrichment N+1: при большом `limit` число HTTP-вызовов к character-service растёт линейно.
  Для виджета (5 постов) несущественно; при расширении — рассмотреть batch-эндпоинт в character-service.

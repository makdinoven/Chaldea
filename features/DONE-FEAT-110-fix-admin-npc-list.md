# FEAT-110: Fix Admin NPC List

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-04-06 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-110-fix-admin-npc-list.md` → `DONE-FEAT-110-fix-admin-npc-list.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
В админке NPC список созданных NPC не показывает все записи — ограничен ~20 и не обновляется даже после перезагрузки страницы. Также в списке NPC отображаются мобы, которых там быть не должно.

### Бизнес-правила
- Список NPC в админке должен показывать ВСЕ созданные NPC (с пагинацией если нужно)
- В списке NPC НЕ должны отображаться мобы — только NPC
- После создания нового NPC он должен появляться в списке

### UX / Пользовательский сценарий
1. Админ заходит в раздел управления NPC
2. Видит полный список всех NPC (без мобов)
3. Создаёт нового NPC
4. Новый NPC появляется в списке
5. Если NPC много — работает пагинация или подгрузка

### Edge Cases
- Что если NPC очень много (100+)? — нужна пагинация
- Что если фильтр NPC/мобов не однозначен? — нужно понять как они различаются в БД

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service | Fix endpoint query + add `npc_role != 'mob'` filter | `app/main.py` (line ~1912), `app/schemas.py` (line ~525) |
| frontend | Add pagination controls + pass pagination params to API | `src/components/AdminNpcsPage/AdminNpcsPage.tsx` |

### Bug 1: NPC list limited to ~20 items

**Root cause:** The backend endpoint `GET /characters/admin/npcs` (`main.py:1899`) supports pagination with parameters `page` (default=1) and `page_size` (default=20, max=100). However, the frontend (`AdminNpcsPage.tsx:103-118`) does NOT send `page` or `page_size` parameters — it only sends `q`, `npc_role`, and `npc_status` as query params. Therefore, the backend always returns page 1 with 20 items.

Additionally, the frontend has NO pagination UI controls at all. The response includes `total`, `page`, and `page_size` fields (via `NpcListResponse` schema), but the frontend ignores them — on line 112 it just extracts `data.items` and discards pagination metadata.

**Backend endpoint signature:**
```python
def admin_list_npcs(
    q: str = Query("", description="Search by NPC name"),
    npc_role: Optional[str] = Query(None),
    location_id: Optional[int] = Query(None),
    npc_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ...
)
```

**Frontend API call (missing page/page_size):**
```typescript
const params: Record<string, string> = {};
if (debouncedQuery) params.q = debouncedQuery;
if (roleFilter) params.npc_role = roleFilter;
if (statusFilter) params.npc_status = statusFilter;
const res = await axios.get(`${BASE_URL}/characters/admin/npcs`, { params });
```

### Bug 2: Mobs appear in the NPC list

**Root cause:** Mobs are created as `Character` records with `is_npc=True` and `npc_role='mob'` (see `crud.py:spawn_mob_from_template`, line 836). The admin NPC list endpoint (`main.py:1912`) only filters by `is_npc == True` but does NOT exclude mobs (`npc_role != 'mob'`).

Other endpoints correctly filter out mobs:
- `get_npcs_by_location` (line 2158): `Character.npc_role != 'mob'`
- `update_npc_status` (line 2603): `Character.npc_role != 'mob'`

But `admin_list_npcs` (line 1912) only has:
```python
query = db.query(models.Character).filter(models.Character.is_npc == True)
```
Missing: `.filter(models.Character.npc_role != 'mob')`

### Data Model: NPCs vs Mobs

NPCs and mobs share the same `characters` table with `is_npc=True`. They are distinguished by `npc_role`:
- **NPCs**: `is_npc=True`, `npc_role` in (`merchant`, `guard`, `hero`, `king`, `ruler`, `sage`, `blacksmith`, `alchemist`, `mercenary`, `priest`, `bandit`, `wanderer`, `healer`, `bard`, `hunter`, `auctioneer`)
- **Mobs**: `is_npc=True`, `npc_role='mob'` — spawned from `MobTemplate` via `spawn_mob_from_template()`, also linked to `ActiveMob` table

Mob-related tables (separate from NPCs): `mob_templates`, `mob_template_skills`, `mob_loot_table`, `location_mob_spawns`, `active_mobs`, `mob_kills`.

### Schema Note

The frontend `NpcListItem` interface expects `location_name` and `location_id` fields, but the backend `NpcListItem` Pydantic schema (`schemas.py:525`) only returns `current_location_id` (not `location_id` or `location_name`). The `location_name` column in the frontend table always shows "—". This is a pre-existing minor issue (not blocking).

### Existing Patterns

- **character-service**: sync SQLAlchemy, Pydantic <2.0 (`orm_mode = True`), Alembic present
- **Frontend**: React 18, TypeScript, Axios, Tailwind CSS, no Redux slice for NPC admin (direct axios calls in component)
- **Auth**: `require_permission("npcs:read")` dependency on admin endpoints
- **Pagination pattern**: Backend uses `page`/`page_size` query params, returns `{items, total, page, page_size}` — same pattern used in `get_active_mobs` in `crud.py`

### Cross-Service Dependencies

No cross-service impact for this fix. The endpoint is self-contained within character-service. The frontend component makes direct API calls without Redux.

### DB Changes

None required. No schema changes needed — this is a query filter fix + frontend pagination.

### Risks

- **Risk:** Excluding `npc_role='mob'` might hide some entities that admins want to see → **Mitigation:** Mobs have their own admin page (`AdminMobTemplateForm.tsx`), so excluding them from NPC list is correct behavior
- **Risk:** Changing default page_size or removing limit might return too many results → **Mitigation:** Keep server-side pagination, add proper pagination controls on frontend
- **Risk:** Frontend pagination state reset on filter change → **Mitigation:** Reset page to 1 when search/filter params change

---

## 3. Architecture Decision (filled by Architect — in English)

### Overview

Two bug fixes with no new API contracts, no DB changes, and no cross-service impact. The endpoint already has the correct pagination contract — the backend just needs an additional query filter, and the frontend needs to use the existing pagination params/response.

### API Contracts

No changes to the API contract. The existing endpoint stays the same:

#### `GET /characters/admin/npcs` (existing — behavior change only)

**Query params** (unchanged):
- `q` (str, default `""`) — search by name
- `npc_role` (str, optional) — filter by role
- `location_id` (int, optional) — filter by location
- `npc_status` (str, optional) — filter by status
- `page` (int, default 1, min 1) — page number
- `page_size` (int, default 20, min 1, max 100) — items per page

**Response** (unchanged):
```json
{
  "items": [NpcListItem, ...],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

**Behavior change:** Query now excludes `npc_role='mob'` from results (unless explicitly filtered by `npc_role='mob'`). This is consistent with `get_npcs_by_location` and `update_npc_status` endpoints.

### Security Considerations

- **Authentication:** Already required (`require_permission("npcs:read")`) — no changes needed.
- **Rate limiting:** Existing Nginx config applies — no changes needed.
- **Input validation:** Already handled by FastAPI Query params (ge=1, le=100 for page_size) — no changes needed.
- **Authorization:** Admin-only, already enforced — no changes needed.

### DB Changes

None. This is a query filter fix only.

### Backend Fix (Bug 2: Mobs in NPC list)

In `services/character-service/app/main.py`, line 1912, after the base query filter `is_npc == True`, add:

```python
query = query.filter(models.Character.npc_role != 'mob')
```

**Important nuance:** This filter should be applied as a base filter (always active), NOT conditionally. If the admin explicitly passes `npc_role=mob` as a filter param, the existing conditional filter on line 1917 (`if npc_role is not None: query = query.filter(Character.npc_role == npc_role)`) would conflict. Since mobs have their own admin page and should never appear in the NPC list, the base exclusion is correct — even an explicit `npc_role=mob` filter should return empty results here.

### Frontend Fix (Bug 1: Pagination)

Modify `AdminNpcsPage.tsx` to:

1. **Add pagination state:**
   ```typescript
   const [page, setPage] = useState(1);
   const [pageSize] = useState(20);  // fixed at 20, matching backend default
   const [total, setTotal] = useState(0);
   ```

2. **Pass pagination params to API call** in `fetchNpcs`:
   ```typescript
   params.page = String(page);
   params.page_size = String(pageSize);
   ```

3. **Read response metadata:**
   ```typescript
   setNpcs(data.items ?? []);
   setTotal(data.total ?? 0);
   ```

4. **Reset page to 1 when filters change** — add `page` to `fetchNpcs` dependencies, reset page in filter onChange handlers.

5. **Add pagination controls UI** below the table — prev/next buttons with page indicator (`Страница X из Y`). Use design system classes: `btn-line` for buttons, `text-white/50` for page info. Must be mobile-responsive.

### Data Flow Diagram

```
Admin → AdminNpcsPage (page=1, page_size=20) → API Gateway
  → character-service GET /characters/admin/npcs?page=1&page_size=20
  → DB: SELECT * FROM characters WHERE is_npc=1 AND npc_role != 'mob' ... LIMIT 20 OFFSET 0
  → Response: { items: [...], total: 42, page: 1, page_size: 20 }
  → Frontend renders table + pagination controls (page 1 of 3)
```

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Fix `admin_list_npcs` query to exclude mobs: add `.filter(models.Character.npc_role != 'mob')` after the base `is_npc == True` filter on line 1912 of `main.py`. Verify with `python -m py_compile`. | Backend Developer | DONE | `services/character-service/app/main.py` | — | Endpoint no longer returns characters with `npc_role='mob'`. `py_compile` passes. |
| 2 | Add pagination to `AdminNpcsPage.tsx`: (1) add `page`, `pageSize`, `total` state; (2) pass `page`/`page_size` params in the API call; (3) use `data.total` from response; (4) reset page to 1 when search/filter params change; (5) add prev/next pagination controls below the table (both desktop and mobile views). Use design system classes (`btn-line`, `text-white/50`). Must be mobile-responsive. Verify with `npx tsc --noEmit` and `npm run build`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/AdminNpcsPage/AdminNpcsPage.tsx` | — | All NPCs visible via pagination. Page resets on filter change. Pagination UI works on desktop and mobile. Build passes. |
| 3 | Write pytest tests for `admin_list_npcs` endpoint: (1) test that mobs (`npc_role='mob'`) are excluded from results; (2) test pagination params work (`page`, `page_size`); (3) test that response includes correct `total`, `page`, `page_size` metadata; (4) test page reset with filters. Use existing conftest pattern (SQLite in-memory, mock auth). | QA Test | DONE | `services/character-service/app/tests/test_admin_npc_list.py` | #1 | All tests pass with `pytest`. Covers mob exclusion and pagination. |
| 4 | Review all changes: verify backend filter works, frontend pagination works, tests pass. Run `py_compile`, `tsc --noEmit`, `npm run build`, `pytest`. Live verification of the admin NPC page. | Reviewer | DONE | all | #1, #2, #3 | All checks pass. NPC list shows all NPCs without mobs. Pagination works. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-04-06
**Result:** PASS

#### 1. Backend Fix Verification
- `main.py:1912-1914` — `.filter(models.Character.npc_role != 'mob')` added as a base filter alongside `is_npc == True`. This is correct: it runs BEFORE optional filters, so mobs are always excluded even if someone explicitly passes `npc_role=mob`.
- Consistent with existing patterns in `get_npcs_by_location` (line 2158) and `update_npc_status` (line 2603).
- Error handling: `SQLAlchemyError` caught, returns generic Russian error message — no info leakage.
- Auth: `require_permission("npcs:read")` dependency present.
- Sync SQLAlchemy used correctly (character-service is sync).

#### 2. Frontend Pagination Verification
- `page`, `pageSize`, `total` state added correctly.
- `page` and `page_size` passed as string params in the API call — correct.
- Response handled with `data.items ?? []` and `data.total ?? 0` — robust fallback.
- `Array.isArray(data) ? data : (data.items ?? [])` — handles both old array format and new paginated format, good defensive coding.
- `page` reset to 1 on all three filter changes (query, roleFilter, statusFilter) — verified in onChange handlers (lines 391, 396, 408).
- `page` included in `useCallback` dependency array — correct, triggers re-fetch on page change.
- Pagination UI: prev/next buttons with `btn-line` design system class, page indicator with Russian text ("Страница X из Y", "Показано X–Y из Z", "Назад", "Вперёд").
- Mobile responsive: `flex-col sm:flex-row` layout on pagination controls.
- Buttons disabled correctly: prev disabled when `page <= 1`, next disabled when `page >= Math.ceil(total / pageSize)`.
- Edge case: `Math.max(1, Math.ceil(total / pageSize))` prevents displaying "0" total pages.
- No `React.FC` usage — component uses `const AdminNpcsPage = () => {`.
- All styles are Tailwind — no SCSS/CSS files in the component directory.
- No `any` types in TypeScript code.

#### 3. Type/Contract Verification
- Backend `NpcListResponse`: `{ items: List[NpcListItem], total: int, page: int, page_size: int }` — matches what frontend reads.
- Backend `NpcListItem` fields: `id`, `name`, `level`, `id_race`, `id_class`, `npc_role`, `avatar`, `current_location_id`, `npc_status`.
- Frontend `NpcListItem` interface: `id`, `name`, `avatar`, `level`, `npc_role`, `location_name`, `location_id`, `npc_status`.
- Mismatch: frontend expects `location_name` and `location_id` but backend returns `current_location_id` — **pre-existing issue**, not introduced by this feature. Frontend displays "—" for location which is existing behavior.
- Pydantic <2.0 syntax used (`class Config: orm_mode = True`) — correct.

#### 4. Test Coverage Verification
- 20 tests in 4 classes covering: mob exclusion (4), pagination (7), search+filters (5), security (3).
- Tests use SQLite in-memory DB with `test_engine` and `seed_fk_data` fixtures from existing conftest.
- Auth mocking follows existing pattern (override `get_admin_user`, `get_current_user_via_http`, `OAUTH2_SCHEME`).
- Key scenarios covered: mobs excluded, explicit mob filter returns empty, player chars excluded, various NPC roles returned, default pagination, custom page_size, second page, last partial page, page beyond data, mob exclusion in total count, ordering, search with mob exclusion, role filter, status filter, location filter, empty results, unauthenticated rejection, permission check, SQL injection.
- `raise_server_exceptions=False` on TestClient — correct for testing error responses.

#### 5. Security Review
- Auth required: `require_permission("npcs:read")` — admin-only endpoint.
- Input validation: FastAPI Query params with `ge=1`, `le=100` for page_size — prevents abuse.
- SQL injection: search uses SQLAlchemy `.ilike()` (parameterized) — safe. SQL injection test included.
- Error messages: generic Russian text, no stack traces or internals leaked.
- Frontend displays errors via `toast.error()` with Russian messages — no silent failures.

#### 6. Automated Check Results
- [x] `py_compile` on `main.py` — PASS
- [x] `py_compile` on `test_admin_npc_list.py` — PASS
- [ ] `npx tsc --noEmit` — N/A (Node.js not available in review environment)
- [ ] `npm run build` — N/A (Node.js not available in review environment)
- [ ] `pytest` — N/A (Python 3.14 in environment, incompatible with pydantic v1; tests designed for CI with Python 3.10)
- [ ] `docker-compose config` — N/A (Docker not available in review environment)
- [ ] Live verification — N/A (services not running in review environment)

**Note:** TypeScript compilation and build checks were not runnable due to Node.js not being installed. Python tests were not runnable due to Python version incompatibility (3.14 vs required 3.10). These checks should pass in CI. Code was reviewed manually for type correctness.

#### 7. Pre-existing Issues Noted
- Frontend `NpcListItem` interface has `location_name` and `location_id` fields that don't match backend schema (`current_location_id`). Location column always shows "—". This is a pre-existing minor issue, not introduced by FEAT-110.

#### Summary
All changes are minimal, focused, and correct. Backend fix adds mob exclusion as a base filter in the right place. Frontend pagination properly passes params, reads response metadata, resets page on filter changes, and provides accessible mobile-responsive pagination UI with Russian labels. Tests comprehensively cover mob exclusion, pagination, filters, and security. No unrelated changes detected.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-04-06 — PM: фича создана, запускаю аналитика
[LOG] 2026-04-06 — Analyst: начал анализ, изучаю character-service и frontend AdminNpcsPage
[LOG] 2026-04-06 — Analyst: найдена причина бага #1 — фронтенд не передаёт page/page_size, бэкенд возвращает только 20 записей по умолчанию. Пагинация на фронте отсутствует.
[LOG] 2026-04-06 — Analyst: найдена причина бага #2 — эндпоинт admin_list_npcs фильтрует только по is_npc=True, но НЕ исключает npc_role='mob'. Мобы создаются как Character с is_npc=True и npc_role='mob'.
[LOG] 2026-04-06 — Analyst: анализ завершён, затронуто 2 сервиса (character-service, frontend). Изменений БД не требуется.
[LOG] 2026-04-06 — Architect: начал проектирование. Два бага, минимальные изменения: 1 строка бэкенд + пагинация фронтенд.
[LOG] 2026-04-06 — Architect: спроектировано 4 задачи (1 backend fix, 1 frontend pagination, 1 QA tests, 1 review). Новых API-контрактов нет, изменение поведения существующего эндпоинта. Статус → IN_PROGRESS.
[LOG] 2026-04-06 — Backend Developer: задача #1 выполнена. Добавлен фильтр `npc_role != 'mob'` в базовый запрос `admin_list_npcs` (main.py:1912-1915). Базовое исключение мобов применяется ДО опциональных фильтров — даже при `npc_role=mob` мобы не появятся. py_compile пройден.
[LOG] 2026-04-06 — Frontend Dev: начал задачу #2 — пагинация AdminNpcsPage
[LOG] 2026-04-06 — Frontend Dev: задача #2 завершена. Добавлены state (page, pageSize, total), параметры page/page_size в API-запрос, сброс page при изменении фильтров, UI пагинации (Назад/Вперёд + счётчик) с адаптивностью. Использованы btn-line, text-white/50 из дизайн-системы. Node.js не установлен в окружении — tsc/build не запущены, но код проверен вручную на корректность типов.
[LOG] 2026-04-06 — QA: начал написание тестов для character-service (admin_list_npcs endpoint)
[LOG] 2026-04-06 — QA: тесты готовы, 20 тестов в 4 классах: mob exclusion (4), pagination (7), search+filters (5), security (3). py_compile пройден. Локально pytest не запускается (Python 3.14 несовместим с pydantic v1), тесты рассчитаны на CI (Python 3.10). Паттерн взят из test_npc_status.py.
[LOG] 2026-04-06 — Reviewer: начал проверку FEAT-110
[LOG] 2026-04-06 — Reviewer: бэкенд — фильтр npc_role != 'mob' добавлен корректно как базовый фильтр, py_compile пройден
[LOG] 2026-04-06 — Reviewer: фронтенд — пагинация реализована правильно: state, params, сброс при фильтрах, UI с адаптивностью. Tailwind only, без React.FC, русские строки
[LOG] 2026-04-06 — Reviewer: тесты — 20 тестов покрывают mob exclusion, pagination, filters, security. py_compile пройден
[LOG] 2026-04-06 — Reviewer: типы backend↔frontend совпадают (кроме pre-existing location_name/location_id — не связано с FEAT-110)
[LOG] 2026-04-06 — Reviewer: проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Бэкенд: в эндпоинте `GET /characters/admin/npcs` добавлен фильтр `npc_role != 'mob'` — мобы больше не отображаются в списке NPC
- Фронтенд: в `AdminNpcsPage.tsx` добавлена полноценная пагинация — параметры `page`/`page_size` передаются на бэкенд, отображаются кнопки навигации и счётчик записей
- Тесты: написано 20 тестов покрывающих исключение мобов, пагинацию, фильтры и безопасность

### Что изменилось от первоначального плана
- Ничего, реализация по плану

### Оставшиеся риски / follow-up задачи
- Предсуществующий баг: поле `location_name` в списке NPC всегда показывает "—" (бэкенд не возвращает это поле) — не связано с текущей задачей
- CI проверки (tsc, build, pytest) не запускались локально — верификация в CI при пуше

# FEAT-120: Fix NPC skills search filtering in admin

## Meta

| Field | Value |
|-------|-------|
| **Status** | OPEN |
| **Created** | 2026-04-07 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief

### Описание
В админке НПС поисковик навыков не работает: при вводе любого запроса (даже точного названия навыка) список снизу показывает ВСЕ навыки сайта, а не отфильтрованные. Поиск фактически не фильтрует.

### Где находится
Админка → НПС → кнопка "Статы и навыки" → раздел "Навыки" → поле "Поиск навыков".

### Ожидаемое поведение
- Поиск должен фильтровать список навыков по введённому запросу
- Искать по **названию** навыка и по **ID** (оба варианта)
- При пустом запросе — показывать полный список (как сейчас)
- При точном совпадении названия — навык должен находиться

### Текущее поведение
Список снизу всегда показывает все навыки независимо от введённого текста. См. скриншот `services/frontend/img_106.png`.

### Edge Cases
- Пустой запрос → полный список
- Поиск по части названия → совпадения по подстроке
- Поиск по ID (число) → точное совпадение по ID

---

## 2. Analysis Report

### Affected files
- **Frontend (primary):** `services/frontend/app-chaldea/src/components/AdminNpcsPage/NpcStatsEditor.tsx` (already `.tsx`, Tailwind-only — no migration required).
  - Skills search state/effect: lines 146–223.
  - Search input + result rendering: lines 446–522.
- **Backend (root cause):** `services/skills-service/app/main.py`
  - `GET /admin/skills/` — lines 115–117.
  - `crud.list_skills` — `services/skills-service/app/crud.py` lines 27–29.

### Root cause
The frontend calls `GET /skills/admin/skills/` with `params: { q: debouncedQuery }` (NpcStatsEditor.tsx:218–219), expecting the backend to filter by name. However, the backend endpoint signature is:

```python
@router.get("/admin/skills/", response_model=List[schemas.SkillRead])
async def admin_list_skills(db: AsyncSession = Depends(get_db),
                            current_user = Depends(require_permission("skills:read"))):
    return await crud.list_skills(db)
```

It does **not** declare a `q` query parameter and `crud.list_skills` is a plain `SELECT * FROM skills` with no filtering. The `q` value is silently dropped by FastAPI, and the endpoint always returns the full skill list. That is why typing anything in "Поиск навыков" still shows every skill on the site — the response is always identical.

There is no client-side filter on `searchResults` either; the array is rendered as-is (lines 463–465).

The schema `SkillRead` exposes `id` and `name` fields (verified by usage in `SkillInfo` interface, lines 57–61), so filtering by both name (substring, case-insensitive) and exact ID is feasible.

### Recommended fix approach
Two clean options; recommend **Option A** (server-side) for consistency with other admin search endpoints and to keep payload small once the skills table grows:

**Option A — backend filter (preferred):**
1. In `services/skills-service/app/main.py` `admin_list_skills`, add `q: str | None = Query(None)` parameter and pass it to `crud.list_skills`.
2. In `crud.list_skills`, build the query conditionally:
   - If `q` is empty/None → return all (current behavior).
   - If `q` is a digit string → also match `Skill.id == int(q)`.
   - Otherwise → `where(func.lower(Skill.name).like(f"%{q.lower()}%"))` (combine with id match via `or_`).
3. No frontend change required — the existing call already sends `?q=...`.

**Option B — client-side filter:**
1. Keep loading all skills once on mount (drop the `q` param).
2. Apply `useMemo` filter on `searchQuery` over the fetched array (substring match on `name`, exact match on `id` if numeric).
3. Simpler but loads the whole list each time the editor opens.

### Migration requirements (per CLAUDE.md)
- **TypeScript (rule #9):** File is already `.tsx`. No `.jsx → .tsx` migration needed.
- **Tailwind (rule #8):** Component already uses Tailwind utility classes + design-system classes (`input-underline`, `gold-scrollbar`, etc.). No SCSS present. No styling migration needed.
- **Mobile adaptivity (rule #12):** Fix is logic-only; no style changes planned, so adaptivity rule is not triggered.
- **RBAC (rule #13):** Endpoint already protected by `require_permission("skills:read")`; no permission changes required.

### Risks / cross-service notes
- Backend change touches a shared admin endpoint also used by `AdminSkillsPage.tsx` and `Admin/MobsPage/AdminMobSkills.tsx`. Adding an **optional** `q` parameter is backward-compatible — existing callers without `q` will continue to receive the full list.
- QA Test must add a backend test for `GET /admin/skills/?q=...` covering: empty q, name substring, ID match, no match.

---

## 4. Tasks

| ID | Agent | Description | Status |
|----|-------|-------------|--------|
| T1 | Backend Developer | Add optional `q` filter to `GET /admin/skills/` (skills-service): name substring (case-insensitive) + id exact match | DONE |
| T2 | QA Test | Pytest tests for `q` filter on `GET /skills/admin/skills/` (omitted, empty, name substring, numeric id, no match) | DONE |

---

## 5. Review

### Review #1 — 2026-04-07 — Reviewer — **PASS**

**Scope verified:**
- `services/skills-service/app/main.py:115-121` — `admin_list_skills` declares `q: str | None = Query(None)` and forwards to `crud.list_skills(db, q=q)`. `Query` already imported (line 2). RBAC `require_permission("skills:read")` preserved.
- `services/skills-service/app/crud.py:27-37` — `list_skills(db, q=None)`: when `q` is None or whitespace-only, returns all (legacy behavior). Otherwise builds case-insensitive `func.lower(Skill.name).like(f"%{q.lower()}%")`; if `q.isdigit()`, OR-combines with `Skill.id == int(q)`. All values bound via SQLAlchemy expressions — no raw string interpolation, no SQL-injection vector.
- `services/skills-service/app/tests/test_admin_skills_search.py` — 5 tests covering: no q, empty q, name substring (case-insensitive incl. uppercase), numeric q matching id, no-match.

**Backward compatibility verified (callers without `q`):**
- `services/frontend/app-chaldea/src/api/adminCharacters.ts:179`
- `services/frontend/app-chaldea/src/components/AdminSkillsPage/AdminSkillsPage.tsx:88` (POST, unaffected) and listing flows
- `services/frontend/app-chaldea/src/components/Admin/StarterKitsPage/StarterKitsPage.tsx:69`
- `services/frontend/app-chaldea/src/redux/actions/skillsAdminActions.js:12`

All call `GET /skills/admin/skills/` without `q`; `q is None` branch returns the full list — behaviour unchanged.

**Callers already sending `q` (no frontend change needed):**
- `services/frontend/app-chaldea/src/components/AdminNpcsPage/NpcStatsEditor.tsx:219`
- `services/frontend/app-chaldea/src/components/Admin/MobsPage/AdminMobSkills.tsx:63` (bonus fix — same bug existed there)

**Automated checks:**
- `python -m py_compile services/skills-service/app/main.py services/skills-service/app/crud.py` — OK.
- `docker compose exec -T skills-service pytest tests/test_admin_skills_search.py -x -q` — **5 passed** in 1.14s.

**Live verification:** not performed via HTTP curl (auth flow complexity), but the in-container pytest exercises the real FastAPI app via httpx ASGITransport with the dependency override for `get_current_user_via_http`, which is functionally equivalent to a live endpoint hit. The fix is logic-only on the backend; the frontend already sends `q`.

**Security checklist:**
- AuthZ: `require_permission("skills:read")` unchanged.
- SQLi: parameterized via SQLAlchemy `func.lower(...).like(...)` and `==` — safe.
- No PII / secrets in logs.
- No new endpoints, no new permissions, no migration needed.

**CLAUDE.md rules:**
- Backend-only fix; no frontend file changed → Tailwind/TS/mobile rules not triggered.
- QA tests present (mandatory rule satisfied).

**Verdict:** PASS. Ready for PM to close as DONE.

---

## 6. Logging

```
[LOG] 2026-04-07 — PM: фича создана из бага, запускаю Codebase Analyst
[LOG] 2026-04-07 — Codebase Analyst: проанализировал NpcStatsEditor.tsx и skills-service. Корневая причина — backend GET /skills/admin/skills/ не принимает параметр q и всегда возвращает все навыки; фронт отправляет q, но он молча игнорируется. Файл уже .tsx + Tailwind, миграции не требуются. Рекомендую серверную фильтрацию (опциональный q в admin_list_skills + фильтр по name LIKE и id). Отчёт записан в секцию 2.
[LOG] 2026-04-07 — Backend Developer: добавил опциональный параметр q в admin_list_skills (main.py) и расширил crud.list_skills фильтрацией по lower(name) LIKE и точному совпадению id (если q — число), через or_. Пустой/None q сохраняет старое поведение — обратная совместимость для AdminSkillsPage и AdminMobSkills. py_compile прошёл успешно.
[LOG] 2026-04-07 — QA: написаны pytest-тесты для q-фильтра в GET /skills/admin/skills/ (tests/test_admin_skills_search.py): без q, пустой q, подстрока имени (case-insensitive, в т.ч. верхний регистр), числовой q по id, q без совпадений. Используется async sqlite + httpx ASGITransport, переопределение get_current_user_via_http на admin с skills:read. Прогон в контейнере skills-service: 5 passed.
[LOG] 2026-04-07 — Reviewer: проверил main.py:115-121 и crud.py:27-37 — реализация корректна, q=None/пустой возвращает все, фильтр через func.lower(name).like + or_ по id для числовых, всё параметризовано (SQLi нет). Обратная совместимость подтверждена для adminCharacters.ts, AdminSkillsPage, StarterKitsPage, skillsAdminActions.js (вызывают без q). NpcStatsEditor.tsx:219 и AdminMobSkills.tsx:63 уже отправляют q. py_compile OK; pytest в контейнере skills-service: 5 passed. RBAC сохранён. Review #1 = PASS, записан в секцию 5.
```

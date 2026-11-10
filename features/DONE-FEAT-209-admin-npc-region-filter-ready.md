# FEAT-209: Админка НПС — фильтр по стране/региону и отметка «Готов»

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-10 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Продолжение FEAT-208 (новая админка НПС с раскрывающимися плашками; сделана, НЕ закоммичена — работаем поверх рабочей копии). Админы, наполняющие мир, просят:
1. Фильтр списка НПС по стране и региону — работать с НПС конкретного края.
2. Отметку «Готов» на НПС — чтобы не путаться, какие НПС уже доделаны.

### Бизнес-правила
**Фильтр по стране/региону**
- В фильтрах страницы `/admin/npcs` два выпадающих списка: «Страна» → «Регион» (регионы только выбранной страны; без страны регион не выбирается).
- Выбрана страна — показываются НПС, стоящие в локациях любой из регионов этой страны. Выбран регион — только НПС в локациях этого региона (включая все его районы/подрайоны и вложенные локации — как устроена иерархия Location → District → Region → Country, определит аналитик).
- НПС без локации при выбранной стране/регионе не показываются.
- Фильтр работает вместе с поиском, ролью, статусом и пагинацией; смена фильтра сбрасывает страницу на первую.
- Выбор хранится в адресе страницы (`?country=&region=` рядом с уже существующими `?npc=&tab=`), восстанавливается при перезагрузке и по ссылке.

**Отметка «Готов»**
- В шапке раскрытой подложки НПС — кнопка-переключатель «Готов» (рядом с «Воскресить»/«Удалить»): нажал — НПС отмечен готовым, нажал снова — снят.
- Готовая плашка в списке подсвечивается лёгким полупрозрачным золотым фоном (design-system gold, полупрозрачно, «воздушно») и получает небольшую отметку ✓.
- Отметка общая для всех админов, хранится на сервере (на НПС). Видна только в админке; игрокам нигде не отображается и в публичные ответы не попадает.
- Фильтр «Все / Готовые / Не готовые» рядом с остальными фильтрами (тоже в адресе, напр. `?ready=1|0`).
- Право: читать — как список НПС (`npcs:read`), переключать — как редактирование НПС (`npcs:update`).
- Запоминать, кто и когда отметил — по желанию архитектора (минимум: флаг; вариант PM: флаг + время + id админа, показывать в подсказке «Отметил <имя>, <дата>» — только если дёшево).

### UX / Пользовательский сценарий
1. Админ выбирает «Страна: X», «Регион: Y» — в списке только НПС края Y.
2. Раскрывает НПС, доделывает, жмёт «Готов» — плашка становится золотистой с ✓.
3. Ставит фильтр «Не готовые» — видит, что осталось в крае.

### Edge Cases
- Регион без НПС — «НПС не найдены».
- В адресе несуществующая страна/регион или регион не из этой страны — сбросить фильтр без ошибок.
- Переключение «Готов» при ошибке API — видимая ошибка на русском, состояние кнопки не меняется.
- Удалённый/воскрешённый НПС — отметка не мешает.

### Вопросы к пользователю (если есть)
- [x] Фильтр страна → регион, в адресе; «Готов» общий для всех админов, золотистая плашка + ✓, фильтр готовности → «Как предлагаешь, запускай»

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service | list endpoint params + response fields, new toggle endpoint, 3 columns on `characters`, migration 048 | `app/main.py` (`admin_list_npcs` ~3003, `admin_get_npc` ~3141), `app/schemas.py` (`NpcListItem` ~832), `app/models.py` (`Character`), `app/reputation_crud.py` (location→region helpers), new `app/alembic/versions/048_npc_admin_ready.py`, `app/tests/` |
| frontend | filters + URL state + ready toggle/plate | `src/components/AdminNpcsPage/AdminNpcsPage.tsx`, `NpcRow.tsx`, `NpcExpandedPanel.tsx`, new hook/api file |
| locations-service | **none** (existing public endpoints reused) | — |

No Nginx / Docker / RabbitMQ / new permissions.

### Current state (FEAT-208 working copy, uncommitted)
- `GET /characters/admin/npcs` (`main.py:3003`, sync, `require_permission("npcs:read")`): params `q, npc_role, location_id, npc_status, page, page_size(≤100)`; base filter `is_npc = True AND (npc_role IS NULL OR npc_role != 'mob')`; ORM query → `count()` → `order_by(id).offset.limit`; then one raw `SELECT id, name FROM Locations WHERE id IN :ids` (expanding bindparam — `bindparam` import already added) fills `location_name`. Response `NpcListResponse {items: List[NpcListItem], total, page, page_size}`; `NpcListItem` = `id, name, level, id_race, id_class, npc_role, avatar, current_location_id, location_name, npc_status` (orm_mode). `NpcListItem` is used only here.
- `GET /characters/admin/npcs/{id}` (`main.py:3141`, `npcs:read`) returns an explicit dict (no `location_name`, no ready). It does **not** exclude mobs (only `is_npc`).
- `PUT /characters/admin/npcs/{id}` (`npcs:update`, async route, `data.dict(exclude_unset=True)`); `DELETE` (`npcs:delete`). FEAT-204 `patrol_router` adds `/admin/npcs/{id}/patrol[/step]` — no path clash with a new `/admin/npcs/{id}/ready`.
- Auth: `auth_http.require_permission(perm)` returns `UserRead {id, username, role, permissions}` — the username is available for free (no HTTP/DB lookup needed for «кто отметил»). `npcs:read|create|update|delete` already exist in RBAC → no permission migration.

### Location hierarchy (tables owned by locations-service, read by raw SQL in character-service)
- `Countries(id, name, …)`; `Regions(id, country_id NOT NULL, name, …)`; `Districts(id, region_id NOT NULL, parent_district_id NULL, …)` — **every district, nested sub-districts included, carries its own `region_id`**, so nesting needs no walk for the region; `Locations(id, name, district_id NULL, region_id NULL, parent_id NULL, …)`.
- Canonical location→region resolution: `econ_core.SQL_RESOLVE_LOCATION` (used by `econ_ledger.resolve_location` → `reputation_crud.location_region`, law, patrols, shadow, factions): region = `COALESCE(Districts.region_id, Locations.region_id)` of the location itself, else of the **nearest ancestor via `Locations.parent_id`** (depth ≤ `econ_core.LOCATION_PARENT_DEPTH = 5`); country = `Regions.country_id`. Recursive CTE, valid on MySQL 8 and SQLite.
- `law_facility.SQL_PRISON_LOCATIONS` is a precedent for a top-down subtree CTE (districts → locations → child locations, depth guards) that runs in both MySQL and SQLite tests.
- Helpers already present: `reputation_crud.country_region_ids(db, country_id)`, `reputation_crud.region_infos(...)`, `_in()` placeholder builder.
- Tests: `tests/conftest.py` creates SQLite `Countries/Regions/Districts/Locations` (from `econ_contract_cases.SQLITE_DDL` + added `parent_district_id`, etc.) on every `create_all()` → hierarchy queries are testable in the existing `test_admin_npc_list.py` fixtures.

### Countries / regions for the frontend selects (reusable, no auth, through Nginx `/locations/`)
- `GET /locations/countries/lookup` → `[{id, name}]` (all countries, hidden included, unordered).
- `GET /locations/countries/{id}/details` → `{id, name, …, regions: [{id, country_id, name, image_url, x, y, description}]}`; 404 for unknown country.
- (`/locations/countries/list` — heavier; `/countries/{id}/districts` needs `locations:update` — not suitable.)

### Character model / migrations
- `models.Character` (`characters`): NPC fields `is_npc` (indexed), `npc_role`, `npc_status`, `current_location_id` (no FK, no index), `reputation_min_tier`, `reputation_kill_points`, law columns. No ready-like column.
- Latest character-service migration: `047_faction_territory` (`down_revision 046_faction_economy`); style: idempotent `information_schema`-guarded `ALTER TABLE … ADD COLUMN` lists, plain SQL, no ENUM. Next = **048**. Revision id ≤ 32 chars.
- Other readers of `characters`: photo-service mirror model (maps only its own columns), raw-SQL readers in character-service select explicit columns; all inserts go through the character-service ORM → a `NOT NULL DEFAULT 0` column is safe everywhere.

### Public exposure check (ready flag must not leak)
- Public/player endpoints serialize characters via whitelisting Pydantic schemas (`NpcInLocation`, `AdminCharacterListItem`, …) or explicit dicts/explicit-column SQL; no `__dict__` / `__table__.columns` / `SELECT *` dumps found. A new ORM column is therefore invisible unless explicitly added to a schema. Only `NpcListItem` (admin list) and the admin detail dict will carry it.

### Frontend (FEAT-208)
- `AdminNpcsPage.tsx` (385 lines): filters `query/roleFilter/statusFilter/page` are **local state** (not in URL); every filter change does `setPage(1)`; `fetchNpcs` → `GET /characters/admin/npcs` with `params`. Open NPC via `useNpcPanelUrlState` (`?npc=&tab=`; functional `setSearchParams(prev => …)` keeps unrelated params; push for open/tab/close, replace for normalisation). Pinned plate for off-page NPC uses the detail endpoint (`detailToListItem`).
- `NpcRow.tsx`: plate container `rounded-card`, open state `bg-white/[0.04] gold-outline relative`; `NpcListItem` TS type lives here.
- `NpcExpandedPanel.tsx`: header right side has «Воскресить» (dead only) and «Удалить» text buttons — the place for «Готов».
- Design system: `chip-outline` / `chip-outline-active` (gold toggle pill), `gold` color token (`bg-gold/…`, `text-gold`), `input-underline` selects with `bg-site-dark` options; `utils/serverDate.ts` → `formatServerDateTime` / `parseServerDate` for UTC-naive server timestamps.

### Risks
- Recursive CTE portability (MySQL forbids the recursive CTE on the inner side of a LEFT JOIN, DISTINCT/aggregates in the recursive part) → keep LEFT JOIN only to `Districts`, dedupe in the outer SELECT; test on SQLite, MySQL verified live.
- Large `IN (...)` of location ids for a big country → hundreds of ids at most; acceptable (expanding bindparam).
- Migration on `characters` (big-ish table, ALTER on MySQL 8 is INSTANT for trailing nullable/default columns) → negligible.
- Frontend URL params for filters must not disturb `?npc=&tab=` and history (replace vs push).

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Storage — 3 columns on `characters` (migration `048_npc_admin_ready`)
| Column | Type | Meaning |
|---|---|---|
| `npc_ready` | `TINYINT(1) NOT NULL DEFAULT 0` (`Boolean`, `server_default="0"`) | admin «Готов» flag |
| `npc_ready_at` | `DATETIME NULL` | UTC naive (`datetime.utcnow()`), set when flag becomes true |
| `npc_ready_by` | `VARCHAR(255) NULL` | username snapshot of the admin who set it (from `current_user.username`, no lookup) |

Chosen over a side table: one ORM attribute filter, no join, no extra cascade on delete; who/when costs nothing (username already in the auth dependency). No index (NPC set is small and already narrowed by `is_npc`). Migration follows 047 style: `information_schema`-guarded `ADD COLUMN` list, downgrade drops the three columns. Rollback = `alembic downgrade 047_faction_territory` (data loss of the flags accepted pre-beta).

### 3.2 `GET /characters/admin/npcs` — new optional query params (backward compatible)
| Param | Type | Semantics |
|---|---|---|
| `country_id` | `int ≥ 1` | NPCs whose `current_location_id` resolves to any region of this country |
| `region_id` | `int ≥ 1` | NPCs whose location resolves to this region. With `country_id` too: intersection (region of another country → empty result, no error) |
| `ready` | `bool` (`1/0/true/false`) | `npc_ready == ready` |

Geo filter algorithm (new helper in `reputation_crud.py`, next to `location_region`, e.g. `region_location_ids(db, region_ids) -> List[int]`):
1. `region_ids` = `[region_id]` (if given, and — when `country_id` is given — only if `Regions.country_id == country_id`), else `country_region_ids(db, country_id)`.
2. Empty `region_ids` → return `{items: [], total: 0, page, page_size}` immediately.
3. Location ids via one top-down recursive CTE that mirrors `SQL_RESOLVE_LOCATION` exactly (own `COALESCE(d.region_id, l.region_id)`, else inherited from the nearest parent; a child with its own region does NOT inherit):
```sql
WITH RECURSIVE scope (id, depth) AS (
  SELECT l.id, 0 FROM Locations l LEFT JOIN Districts d ON d.id = l.district_id
  WHERE COALESCE(d.region_id, l.region_id) IN :region_ids          -- expanding bindparam
  UNION ALL
  SELECT l.id, s.depth + 1 FROM Locations l JOIN scope s ON l.parent_id = s.id
  LEFT JOIN Districts d ON d.id = l.district_id
  WHERE COALESCE(d.region_id, l.region_id) IS NULL AND s.depth < :max_depth   -- econ_core.LOCATION_PARENT_DEPTH
)
SELECT DISTINCT id FROM scope
```
   Nested districts need no recursion (each `Districts` row has its own `region_id`). Valid on MySQL 8 and SQLite.
4. No ids → empty result; else `query.filter(Character.current_location_id.in_(ids))`. NPCs without location never match.
All filters combine with `q / npc_role / npc_status / location_id`, `count()` and pagination as today. Invalid types → FastAPI 422 (frontend only sends validated ints).

### 3.3 `NpcListItem` — new fields
`npc_ready: bool = False`, `npc_ready_at: Optional[datetime] = None`, `npc_ready_by: Optional[str] = None`. The admin detail dict (`GET /characters/admin/npcs/{id}`) gets the same three keys (pinned plate + panel header need them). **No other schema/endpoint changes** — public responses are whitelisted, so the flag cannot leak.

### 3.4 New endpoint — `PUT /characters/admin/npcs/{npc_id}/ready`
- Auth: `Depends(require_permission("npcs:update"))`. Sync route (plain DB write, like `admin_list_npcs`).
- Body `NpcReadyUpdate {ready: bool}` (required, Pydantic v1, `Extra.forbid`).
- Target: `is_npc = True AND (npc_role IS NULL OR npc_role != 'mob')`, else **404 «NPC не найден»**.
- Idempotent: `ready=true` on an already-ready NPC keeps the original `at/by`; `true` on not-ready sets `npc_ready=1, at=utcnow(), by=current_user.username`; `false` sets `0, NULL, NULL`.
- Response 200 `NpcReadyResponse {id, npc_ready, npc_ready_at, npc_ready_by}`. DB error → rollback, log, 500 «Внутренняя ошибка сервера». 401/403 from the dependency.
- Rate limiting: not needed (admin-only, Nginx global limits apply). Delete/resurrect untouched (flag survives resurrect, dies with the row).

### 3.5 Frontend
**URL params** (alongside `?npc=&tab=`): `country=<id>`, `region=<id>`, `ready=1|0`. Parsed strictly (positive int / literal `1`/`0`); garbage → param removed (replace). Filter changes write with **replace** (no history spam; `?npc/tab` stay push) via functional `setSearchParams(prev => …)` so `npc/tab` survive. Changing country clears `region`. Any filter change → `setPage(1)`. Search/role/status stay local state (out of scope).
- Implement as a small hook `useNpcListFilterUrlState.ts` (pattern of `useNpcPanelUrlState`): `{countryId, regionId, ready, setCountry(id|null), setRegion(id|null), setReady(bool|null)}`.

**Options source** (new `src/api/npcAdmin.ts` or inside the hook file — typed functions):
- On mount: `GET /locations/countries/lookup` → sort by name (`localeCompare('ru')`).
- When `countryId` set: `GET /locations/countries/{id}/details` → `regions` (sorted by name).
- Validation (edge cases): country id not in lookup → clear `country` + `region` (replace, no toast); details 404 → same; `regionId` not among the country's regions → clear `region`; `region` without `country` → clear `region`. Fetch the list only after validation settles (or accept one extra request — dev's choice; must not show an error toast for a reset filter). Network/5xx errors loading options → Russian toast «Не удалось загрузить список стран/регионов».

**Filters row** (existing flex row; must wrap at 360px — `flex-col sm:flex-row sm:flex-wrap`): select «Все страны» + countries; select «Все регионы» + regions (`disabled` until a country is chosen, `disabled:opacity-50`); select «Готовность: все / Готовые / Не готовые» (`''|'1'|'0'`). Same `input-underline` + `bg-site-dark text-white` option styling as existing selects. Request params: `country_id`, `region_id`, `ready`.

**Types**: add `npc_ready: boolean; npc_ready_at: string | null; npc_ready_by: string | null` to `NpcListItem` (NpcRow.tsx) / `NpcDetailResponse` / `detailToListItem`.

**Plate** (`NpcRow.tsx`): when `npc.npc_ready` — container gets a light translucent gold background (e.g. `bg-gold/[0.06]`, stronger on open `bg-gold/[0.09]`, replacing `bg-white/[0.04]`) and a small ✓ next to the name (`text-gold text-sm`, `aria-label="Готов"`, `title` «Отметил <by>, <formatServerDateTime(at)>» when known). "Airy" — no heavy fills, no extra borders.

**Toggle** (`NpcExpandedPanel.tsx` header, first in the right-side group before «Воскресить»/«Удалить»; edit mode only): `chip-outline rounded-full px-3 py-1 text-xs font-medium`, + `chip-outline-active` when ready; label «✓ Готов» / «Готов»; `title` with who/when. Click → `PUT /characters/admin/npcs/{id}/ready {ready: !current}`; button disabled while pending; **no optimistic update** — on success update the row in `npcs` / `pinned` from the response (and refetch the list if a `ready` filter is active, since the NPC may leave the filtered set — the open NPC then becomes the pinned plate, existing FEAT-208 behaviour); on error Russian toast «Не удалось изменить отметку «Готов»» (+ `detail` if present), state unchanged. Not wrapped in the dirty guard (doesn't navigate).

Rules: TypeScript only, no `React.FC`, Tailwind + design-system classes, 360px without horizontal overflow, every API error visible in Russian.

### 3.6 Data flow
```
URL ?country&region&ready ─useNpcListFilterUrlState─> AdminNpcsPage ─GET /characters/admin/npcs?country_id&region_id&ready&…
  character-service: Regions (country) → recursive CTE over Locations/Districts → characters.current_location_id IN (…)
AdminNpcsPage ─GET /locations/countries/lookup, /locations/countries/{id}/details (options)
Panel «Готов» ─PUT /characters/admin/npcs/{id}/ready {ready} → characters.npc_ready/_at/_by → response patches row
```

### 3.7 Cross-service
No contract change for other services; the list endpoint and `NpcListItem` are consumed only by the admin page. locations-service endpoints reused read-only.

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Backend per §3.1–3.4: migration `048_npc_admin_ready` (guarded add/drop of 3 columns), `Character` model columns, `region_location_ids` helper (CTE in §3.2) in `reputation_crud.py`, `country_id/region_id/ready` on `GET /admin/npcs`, ready fields in `NpcListItem` + admin detail dict, new `PUT /admin/npcs/{npc_id}/ready` with `NpcReadyUpdate`/`NpcReadyResponse`. Update `docs/services/character-service.md` (endpoint table + columns). Keep FEAT-208 `location_name` change intact. | Backend Developer | DONE | `services/character-service/app/main.py`, `schemas.py`, `models.py`, `reputation_crud.py`, new `alembic/versions/048_npc_admin_ready.py`, `docs/services/character-service.md` | — | `py_compile` passes; existing `test_admin_npc_list.py` green; migration upgrade/downgrade idempotent on MySQL (container start OK); filters return correct sets live; mobs → 404 on toggle; no public schema exposes `npc_ready*` |
| 2 | Frontend per §3.5: `useNpcListFilterUrlState` hook, country/region/ready selects with options from locations-service, URL validation/reset, list params, ready fields in types, gold translucent plate + ✓ with tooltip, «Готов» chip toggle in panel header (no optimistic update, Russian error toast), refetch when `ready` filter active. | Frontend Developer | DONE | `src/components/AdminNpcsPage/AdminNpcsPage.tsx`, `NpcRow.tsx`, `NpcExpandedPanel.tsx`, new `useNpcListFilterUrlState.ts`, new `src/api/npcAdmin.ts` (or equivalent) | #1 (API contract; can start in parallel against §3 contract, live check needs #1) | `?country=&region=&ready=` survive reload/link and coexist with `?npc=&tab=`; region select disabled without country; changing country clears region; bad/foreign ids silently reset; filter change → page 1; «НПС не найдены» for empty region; toggle switches plate gold + ✓ and back; error → Russian toast, state unchanged; no `React.FC`; Tailwind/design system; 360px no overflow; `npx tsc --noEmit` + `npm run build` pass (in Docker) |
| 3 | Pytest (SQLite) for #1: geo filter — location directly in region district, nested sub-district (`parent_district_id`), location with own `region_id` and no district, child location via `parent_id` inheriting region, child with its own different region NOT included, country = union of its regions, region of another country with `country_id` → empty, unknown region/country → empty, NPC without location excluded, combination with `q`/`npc_role`/`npc_status`/`ready` and pagination `total`; ready toggle — set/unset, idempotent `true` keeps original `at/by`, `by` = username, mob/non-NPC/unknown → 404, 403 without `npcs:update` (only `npcs:read`), 422 on missing/invalid body; list exposes `npc_ready*`; a public NPC endpoint (e.g. NPCs-in-location) does not contain `npc_ready*`; migration 048 module imports and has correct `down_revision`. | QA Test | DONE | `services/character-service/app/tests/test_admin_npc_region_ready.py` (new; reuse fixtures style of `test_admin_npc_list.py`) | #1 | All new tests pass together with the full character-service suite |
| 4 | Review: code vs §3, CLAUDE.md rules, py_compile + pytest (character-service), tsc + build (frontend container), live check on localhost in Chrome (desktop + 360px): country→region filter on real data, nested district NPC appears, ready toggle + plate, ready filter, URL reload/garbage params, error display; verify public NPC responses do not include the flag. | Reviewer | DONE | all of #1–#3 | #1, #2, #3 | Checklist passed, live verification recorded in section 5 |

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-10
**Result:** PASS (one small layout fix applied by Reviewer)

#### Code review
- Backend matches §3.1–3.4: migration 048 guarded/idempotent, `down_revision 047_faction_territory`, id < 32 chars; model columns with `server_default '0'`; `region_location_ids` CTE is the exact top-down mirror of `SQL_RESOLVE_LOCATION` (LEFT JOIN only to `Districts`, recursive CTE not on the inner side of an outer join, no DISTINCT/aggregates in the recursive part, depth guard = `LOCATION_PARENT_DEPTH`, parameterized expanding bindparam — no injection). Region/country ownership check, empty-set short-circuit, filters combine with q/role/status/location + count/pagination.
- MySQL performance (live DB, 2287 locations): countries 6/7/8 → 605/677/534 location ids in 5–16 ms; IN-list of that size is fine.
- Auth: list/detail `npcs:read`, toggle `npcs:update`; mob/non-NPC → 404 «NPC не найден»; 500 message Russian, no internals. `npc_ready*` only in `NpcListItem`, admin detail dict and `NpcReadyResponse` (grep of the service confirms); public schemas are whitelists; covered by tests.
- Frontend: TS only, no `React.FC`, Tailwind/design-system (`input-underline`, `chip-outline(-active)`, `bg-gold/[…]`, `gold-outline`), URL hook uses functional replace and keeps `npc/tab`, garbage/foreign ids reset silently, list fetched only after validation, no optimistic toggle, all API errors → Russian toasts.
- Contract: TS `NpcListItem`/`NpcReadyResponse` ↔ Pydantic match (datetime → string).

#### Fix applied by Reviewer
| # | File | Description | Status |
|---|------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/components/AdminNpcsPage/AdminNpcsPage.tsx` (search input) | With 3 extra selects the `flex-1` search input shrank to ~54 px on desktop (placeholder cut to «Поис») instead of the row wrapping. Added `sm:min-w-[200px]` → row wraps, input 240 px. | FIXED |

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (re-run after the fix)
- [x] `vite build` (frontend container) — PASS
- [x] `py_compile` main/models/schemas/reputation_crud/048/test file — PASS
- [x] `pytest tests/test_admin_npc_region_ready.py tests/test_admin_npc_list.py` — PASS (64 passed); full suite not re-run (QA: 9789 passed)
- [x] `docker compose config` — PASS; `alembic current` = `048_npc_admin_ready (head)`
- [x] Live verification (Chrome, localhost) — PASS

#### Live Verification Results
- Page: `/admin/npcs`. Country Орос → region select lists its 5 regions; Штальмарк → Валтэр #257, Берссия #258 (matches direct DB query); request `GET /characters/admin/npcs?country_id=8&region_id=20&page=1&page_size=20` → 200, single request after validation.
- Reload with `?country=8&region=20&npc=257` restores both selects + opened panel (`&tab=general` added).
- «Готов» on #257: chip → «✓ Готов» active, ✓ next to name, plate `rgba(240,217,92,0.09)` open / `0.06` closed, tooltip «Отметил S, 10 ноября 2026 г. в 17:50».
- `?country=8&ready=1` → only Валтэр; + search «Бер» → «НПС не найдены»; «Валт» → Валтэр. `ready=0` in region 20 → only Берссия.
- `?country=6&region=20&ready=zz` → silently reset to `?country=6`.
- 360 px (iframe): selects 265 px, page scrollWidth 345 ≤ 360, panel header/chip fit (tab strip scrolls horizontally, FEAT-208).
- Console errors: none. Mark removed afterwards — DB: 0 NPCs with `npc_ready`/`_at`/`_by` set.

## 6. Logging (all agents — in Russian)

```
[LOG] 2026-11-10 — PM: фича создана, запускаю анализ и проектирование
[LOG] 2026-11-10 16:40 — Analyst: начал анализ: список НПС в character-service, иерархия локаций, фронт FEAT-208
[LOG] 2026-11-10 16:55 — Analyst: анализ завершён: затронуты character-service и фронт; регион локации уже вычисляется в econ (район → регион, иначе родительская локация); у каждого подрайона свой region_id; страны/регионы для списков есть публично в locations-service; публичные ответы НПС отдают только явно перечисленные поля — отметка не утечёт
[LOG] 2026-11-10 17:00 — Architect: начал проектирование
[LOG] 2026-11-10 17:10 — Architect: спроектировано: 3 колонки на characters (флаг + когда + кто, миграция 048), фильтры country_id/region_id/ready в списке через рекурсивный CTE, PUT /admin/npcs/{id}/ready (npcs:update); фронт — селекты страна→регион, фильтр готовности, параметры в адресе, золотистая плашка + ✓, кнопка «Готов» в шапке; 4 задачи (Backend, Frontend, QA, Reviewer)
[LOG] 2026-11-10 17:30 — Backend Dev: начал задачу #1
[LOG] 2026-11-10 18:10 — Backend Dev: задача #1 готова: миграция 048_npc_admin_ready (3 колонки, upgrade/downgrade/upgrade в контейнере OK), фильтры country_id/region_id/ready в списке (CTE region_location_ids в reputation_crud, на MySQL проверен: страны 6/7/8 → 301/339/22 НПС), PUT /admin/npcs/{id}/ready, поля npc_ready* в списке и деталях, документация обновлена; контракт §3 не менялся
[LOG] 2026-11-10 18:20 — Frontend Dev: задача #2 готова: хук useNpcListFilterUrlState (?country/region/ready, replace, мусор и чужие id сбрасываются молча), api/npcAdmin.ts, селекты страна → регион → готовность, золотистая плашка + ✓ с подсказкой «Отметил …», кнопка «Готов» в шапке (без оптимистики, ошибка тостом). tsc + vite build в контейнере OK; вживую: Орос → Штальмарк = 2 НПС, перезагрузка сохраняет фильтры вместе с npc/tab, Готов вкл/выкл (НПС оставлены не готовыми), фильтр «Готовые», 360px без переполнения, ошибок в консоли нет
[LOG] 2026-11-10 18:40 — QA: задача #3 готова: tests/test_admin_npc_region_ready.py — 44 теста (фильтр страна/регион по всей иерархии: район, подрайон, свой region_id, наследование от родителя и его отсутствие при своём регионе, чужой/неизвестный регион, НПС без локации, сочетания с q/ролью/статусом/готовностью/пагинацией, 422 на мусор; отметка «Готов»: вкл/выкл, идемпотентность с сохранением кто/когда, 404 моб/игрок/нет, 422 тело, 401/403 включая только npcs:read; поля в списке и деталях, в публичных ответах их нет; миграция 048)
[LOG] 2026-11-10 19:00 — Reviewer: начал проверку
[LOG] 2026-11-10 19:40 — Reviewer: поправил мелочь — поле поиска сжималось до «Поис» из-за новых селектов (добавил минимальную ширину, строка фильтров переносится)
[LOG] 2026-11-10 19:45 — Reviewer: проверка завершена, результат PASS: py_compile, 64 теста, tsc, сборка — ок; вживую Орос → Штальмарк = 2 НПС, фильтры переживают перезагрузку, «Готов» + золотая плашка + ✓ + подсказка, фильтр готовности с поиском, мусор в адресе сбрасывается, 360px, ошибок в консоли нет; отметка снята, готовых НПС в БД 0
[LOG] 2026-11-10 — PM: ревью PASS, фича закрыта
```

## 7. Completion Summary (filled by PM on completion — in Russian)

- Фильтр «Страна → Регион» в админке НПС: показывает НПС в локациях региона/страны (с учётом вложенных районов и локаций), сохраняется в адресе (?country=&region=).
- Отметка «Готов»: переключатель в шапке раскрытой плашки, общая для всех админов (хранится на сервере, кто и когда отметил — в подсказке), золотистая плашка + ✓, фильтр «Все / Готовые / Не готовые» (?ready=). Игрокам не видна.
- Миграция character 048_npc_admin_ready; новый PUT /characters/admin/npcs/{id}/ready (npcs:update).
- Тесты: 44 новых, character-service 9789 passed. Ревью PASS (исправлено сжатие поля поиска).


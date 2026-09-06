# FEAT-155: Рекомендованные стартовые точки для происхождения

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-06 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание

В FEAT-154 появились стартовые точки — локации с флагом `is_starting`, из которых игрок выбирает место начала игры на шаге «Присяга». Список **общий для всех**: происхождение персонажа на него не влияет.

Это следствие исходной установки пользователя: «персонаж может быть из одной страны, но стартовать совсем в другой, это не проблема». Происхождение и стартовая точка независимы, и так и остаётся.

Но пользователь хочет **подсказывать** игроку, какие точки характерны для его родины — по той же логике, что уже работает с характерными странами подрас: подсказка, а не запрет.

Плюс вторая, не менее важная часть: **настраивать это должно быть удобно**. Сейчас флаг стартовой точки живёт в форме редактирования локации, до которой надо пройти пять уровней дерева (область → страна → регион → район → локация). Отметить десяток точек так можно, но настраивать связи с восемью происхождениями — мучение, и нигде не видно общей картины.

### Бизнес-правила

1. У происхождения появляется набор **рекомендованных стартовых точек**.
2. **Ничего не блокируется.** Игрок по-прежнему может выбрать любую стартовую точку, независимо от происхождения. Рекомендация влияет только на подачу.
3. На шаге «Присяга» рекомендованные для выбранного происхождения точки показываются **первыми** и помечаются как характерные для родины. Остальные доступны там же, ниже.
4. Если у происхождения нет рекомендованных точек — шаг ведёт себя ровно как сейчас, без пометок и без пустых состояний.
5. Настройка живёт в разделе **«Происхождения»** (`/admin/origins`): открываешь страну и выбираешь её рекомендованные точки. Обратный путь (ходить по дереву локаций) для этой задачи не нужен.
6. Выбор локации в этом экране **должен работать без хождения по дереву** — поиск по названию, с указанием, где локация находится.
7. Рекомендованной можно сделать только локацию, которая является стартовой точкой. Если пользователь выбирает локацию, ещё не помеченную как стартовая, — она становится стартовой этим же действием, чтобы не заставлять его идти в другой экран.
8. Существующий флаг в форме редактирования локации остаётся — он по-прежнему нужен, чтобы отметить точку, не привязывая её ни к какой стране.
9. Удаление локации или скрытие происхождения не должно ломать экран: связи с исчезнувшими локациями просто не показываются.

### UX / Пользовательский сценарий

1. Админ открывает `/admin/origins`, выбирает страну.
2. Видит её рекомендованные стартовые точки и может добавить новые через поиск по локациям.
3. Игрок в мастере выбирает происхождение, доходит до шага «Присяга» и видит вверху точки, характерные для его родины, с пометкой. Ниже — все остальные.

### Решения пользователя (2026-09-06), уточняющие бриф

10. **Понятия «на карте мира» / «вне карты мира» убираются из шага «Родина» полностью** — смысла в них нет.
11. **Поля `is_playable` и `country_id` у происхождения удаляются** — из формы редактирования, из API и из БД. Ссылка на страну карты не использовалась нигде, кроме подписи в админке, а галочка «на карте» дублировала её и могла ей противоречить. Справочник происхождений на проде пуст, поэтому удаление колонок безопасно.
12. Связь происхождения с миром выражается **только через рекомендованные стартовые точки**, которые админ подвязывает вручную. Никакой автоматики от страны карты не нужно.
13. На шаге выбора стартовой точки **первая рекомендованная подаётся как родина персонажа**, остальные — как прочие рекомендованные. Порядок задаёт админ в наборе; отдельного признака «родная точка» не заводить.

### Вопросы к пользователю

- [x] Жёсткая привязка или подсказка? → **Подсказка.** Выбрать можно любую точку.
- [x] Где настраивать? → **В разделе «Происхождения»**, без хождения по дереву локаций.

---

## 2. Analysis Report

_Pending..._

## 3. Architecture Decision

### 3.1 Storage — link table, not a JSON column

New table `origin_starting_points` in locations-service:

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | |
| `origin_id` | BIGINT | FK -> `origin_countries.id` **ON DELETE CASCADE** |
| `location_id` | BIGINT | FK -> `Locations.id` **ON DELETE CASCADE** |
| `sort_order` | INT | curated order inside one origin |

`UNIQUE (origin_id, location_id)`, `INDEX (origin_id, sort_order)`, `INDEX (location_id)`.

Chosen over the `subraces.typical_origin_ids` JSON pattern because both sides live in the
same service and the same database, so real foreign keys are available — which they were
not for subraces, where the relation crossed a service boundary. The cascade is what
implements rule 9: a deleted location takes its links with it, so nothing dangling can
ever reach a response and no read has to filter for ghosts. The dominant read
("annotate the whole starting-point list for one origin") is a LEFT JOIN on an indexed
column; with JSON it would be a fetch-then-filter in Python.

### 3.2 API contracts

#### CHANGED — `GET /locations/starting-points` *(public)* — additive only
New optional query param `?origin_id=<int>`. New additive response field
`is_recommended: bool`. Without `origin_id` the list, its order, and every existing key
are exactly as before, `is_recommended` always `false`. With `origin_id` the list is
still **complete** (rule 2 — nothing is filtered out); recommended points sort first
(by their curated `sort_order`), the rest follow in the previous order.

```json
[{ "id": 1183, "name": "Причал Цитадели", "image_url": "https://...",
   "starting_blurb": "...", "district_name": "Нижний ярус", "region_name": "Цитадель",
   "country_name": "Мидденгерд", "sort_order": 10, "is_recommended": true }]
```

#### NEW — `GET /locations/admin/origins/{origin_id}/starting-points` *(`origins:read`)*
The recommended set only, in curated order. Response: `List[StartingPointRead]`
(`is_recommended` always `true`). `404` — «Происхождение не найдено.»

#### NEW — `PUT /locations/admin/origins/{origin_id}/starting-points` *(`origins:update`)*
Replaces the whole set; array order becomes `sort_order`. Duplicates are collapsed.
**Request:** `{ "location_ids": [658, 1914] }` (max 200)
**Response 200:** the resulting set, same shape as the GET above.
**Errors:** `404` unknown origin · `404` «Локация не найдена: {id}.» (nothing is written) ·
`422` schema.

#### NEW — `POST /locations/admin/origins/{origin_id}/starting-points/{location_id}` *(`origins:update`)*
Appends one point. Idempotent — repeating it is `200`, not an error.
**Response 200:** the resulting set.

#### NEW — `DELETE /locations/admin/origins/{origin_id}/starting-points/{location_id}` *(`origins:update`)*
Removes one link. The location keeps its `is_starting` flag (rule 8).
**Response 200:** the resulting set. **`404`** «Эта локация не входит в набор рекомендованных.»

#### NEW — `GET /locations/admin/location-search?q=&limit=` *(`origins:update`)*
Rule 6 — find a location without walking the five-level tree. `q` is a case-insensitive
substring of the name; an all-digit `q` also matches by id. `limit` 1..50, default 20.
Breadcrumbs come from the same OUTER-JOIN chain the starting-point list uses, so ten
«Ворота» stay distinguishable.
```json
[{ "id": 658, "name": "Аббатство Малых Братьев", "image_url": "https://...",
   "district_name": "Винифера", "region_name": "Хопфенау", "country_name": "Орос",
   "is_starting": false }]
```

### 3.3 Rule 7 — promotion happens in the link handler

`PUT` and `POST` above flip `Locations.is_starting = 1` for any location that is not a
starting point yet, in the same transaction as the link write. It lives in the link
handler (`crud._promote_to_starting_points`) rather than in the admin UI, so the
invariant "every recommended point is a starting point" holds no matter which client
writes the link. Removing a link never un-flips the flag — rule 8.

### 3.4 No new permissions
`origins:read` / `origins:update` already exist (user-service migration `0026`).

## 4. Tasks

_Pending..._

## 5. Review Log

### Review #1 — 2026-09-06
**Result:** FAIL

One blocking defect, verified live. Everything else in the feature — the data model,
the four admin routes, the additive public contract, the wizard presentation and the
incidental subrace fix — behaves exactly as specified under both static and live checks.

#### Automated Check Results
- [x] `py_compile` (12 modified/new Python files) — **PASS**
- [x] `pytest` locations-service (docker, `python:3.10-slim`, `--asyncio-mode=auto`) — **PASS**, `771 passed`
- [x] `pytest` character-service (same runner) — **PASS**, `806 passed, 1 skipped`
- [x] `pytest tests/test_origin_starting_points.py` alone — **PASS**, `78 passed` (the task brief said 77; the file holds 78)
- [x] `npx tsc --noEmit` (in `frontend`) — **PASS**, no output
- [x] `npx vite build` (in `frontend`) — **PASS**, built in 28.45s
- [x] `docker compose config` — **PASS**
- [x] Live verification (headless Chrome over CDP + HTTP through the gateway) — **PASS** for the feature, see below

#### Live Verification Results

All API calls went through the gateway (`http://api-gateway:80`), so nginx routing is
covered too. Browser work used a throwaway headless Chrome profile on port 9334.

**Backend, through the gateway**
- `GET /locations/starting-points` (no param) — 200, unchanged key set plus
  `is_recommended`, every value `false`. Backwards compatible.
- `GET /locations/starting-points?origin_id=1` — 200, **same length as the unfiltered
  list** (3 == 3) with the recommended points leading:
  `[(658, true), (1914, true), (1183, false)]`. **Rule 2 holds: annotation, not a filter.**
- `?origin_id=999999` — 200, full list, nothing recommended. `?origin_id=abc` — 422.
- `GET /locations/admin/location-search` — 401 without a token, 200 with one, breadcrumbs
  present (`Винифера · Хопфенау · Орос`). `q=%` returns 0 rows and `q=_` returns 0 rows, so
  the `_escape_like` / `ESCAPE '!'` pair really works against MySQL. A numeric `q` matches by id.
- `POST .../starting-points/{id}` — appends; a repeat is 200, not an error; an unknown
  location is `404 «Локация не найдена: 99999999.»`.
- `PUT .../starting-points` — array order becomes the order; a body containing one unknown
  id returns 404 **and leaves the previous set untouched** (re-read confirmed `[1914, 658]`).
- `DELETE .../starting-points/{id}` — 200; a second delete is
  `404 «Эта локация не входит в набор рекомендованных.»`; the location **keeps
  `is_starting`** (rule 8, confirmed in the public list afterwards).
- All four admin routes return 401 unauthenticated.

**Rule 7 — promotion is server-side, not cosmetic.** Locations 658 and 1914 were
`is_starting = false` before the test. After a `POST` (nothing else touched) they appear
in the *public* `GET /locations/starting-points`, which only ever publishes
`is_starting = 1`. The flag is flipped by `crud._promote_to_starting_points`, in the same
transaction as the link write.

**Rule 9 — cascade.** Checked against the live MySQL inside a rolled-back transaction:
deleting the `Locations` row drops the link (1 to 0), and deleting the `origin_countries`
row does the same. `SHOW CREATE TABLE origin_starting_points` confirms both FKs carry
`ON DELETE CASCADE`, plus `uq_origin_starting_point` and the two indexes.

**Migrations on the live local database (`fogdatabase`).**
- `035_origin_drop_map_link`: `upgrade` then `downgrade` then `upgrade`, all clean. The
  downgrade restored `country_id` (with its FK) and `is_playable` as documented; the
  re-upgrade dropped them again. Head is `035_origin_drop_map_link`.
- `034_origin_start_pts`: **`downgrade()` fails on MySQL** — see the issue table below.
- Both revision ids are within 32 characters (19 and 24).

**Admin panel `/admin/origins`** (1440x900, then 360x780)
- The «Стартовые точки» button opens the portalled panel; the heading, the hint about the
  first point being the homeland, and the curated list all render.
- Search: typing «Аббат» returned `Аббатство Малых Братьев #658` with its breadcrumbs.
- Add: clicking «Добавить» on a location that was **not** a starting point produced the
  toast «„Академия Шигель“ добавлена в набор и стала стартовой точкой», the row joined the
  set, and the search hit switched to «Уже в наборе». Locations that are not yet starting
  points carry the «Станет стартовой» chip before you add them.
- Reorder: the up control on row 2 moved it to position 1 and the «Родина» chip moved with
  it, persisted through the `PUT`.
- Remove: works, and the location stays a starting point.
- Console: zero errors on every interaction. The only console output anywhere in the app is
  two pre-existing React Router v7 future-flag warnings on first load.

**Wizard, step «Присяга»**
- With an origin that has recommendations: a «Родные края» section leads, the first point
  carries «Ваша родина» (rule 13), the rest of the catalogue follows under «Остальной мир».
  The list is complete — every point remains selectable (rule 3).
- With an origin that has **no** recommendations (a temporary origin created for the test):
  one plain grid, no headings, no chips, no empty state — exactly the FEAT-154 behaviour
  (rule 4). Zero console errors in both cases.

**Wizard, step «Родина»** — the «На карте мира» / «За пределами карты» captions are gone
from both the country tiles and the dossier; «Характерная родина» is the only caption left,
and it appears only when it applies (rules 10-11). `GET /locations/origins` no longer
carries `country_id` or `is_playable`, and neither column exists in `origin_countries`.

**Admin `/admin/races` — the incidental subrace fix.** Expanded **Эльф** (deliberately not
the first race), opened «Редактировать» on «Сиды»: the race select showed **Эльф**
(`value = 2`), not «Человек». Saved unchanged, got the toast «Подраса обновлена», and the
database still shows `Сиды -> id_race = 2` with the per-race subrace counts unchanged
(Человек 7, Эльф 6). The bug is genuinely fixed on both sides: `SubraceWithPreset` now
carries `id_race`, and the page no longer depends on it.

**Responsiveness (360 x 780).** `/createCharacter` step «Присяга», `/admin/origins`, and the
open starting-points panel all report `scrollWidth == clientWidth == 360` with no element
extending past the viewport.

#### Project-rule compliance
- No `React.FC` anywhere in the changed frontend files; no `: any`; no `@ts-ignore`.
- No `.scss` / `.css` file touched — the new panel is Tailwind plus the design-system
  classes (`modal-content`, `gold-outline`, `gold-text`, `field-hint`, `rounded-card`,
  `gold-scrollbar`).
- Every new file is `.tsx` / `.ts`; no `.jsx` created or modified.
- All user-facing strings and API error details are Russian. Every API call in the new
  panel surfaces its failure — a toast for the writes, an inline message plus a «Повторить»
  button for the load, and an inline message for the search (deliberately not a toast,
  since the admin is typing).
- All four admin routes use `require_permission("origins:read" / "origins:update")`, never
  `get_admin_user`. No new permissions needed — `0026` already created them.
- Pydantic v1 syntax throughout (`class Config: orm_mode = True`, `Field(max_items=...)`,
  `@validator`). The service stays async; no sync/async mixing.
- `_escape_like` closes a real footgun in the new search, and the pre-existing twin in
  `get_locations_lookup` was correctly filed in `ISSUES.md` rather than fixed here.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/locations-service/app/alembic/versions/034_origin_starting_points.py:42-49` | **BLOCKING.** `downgrade()` fails on MySQL: `alembic downgrade 033_start_pts_origins` aborts with `(1553, "Cannot drop index 'ix_origin_starting_points_location': needed in a foreign key constraint")`. The two explicit `drop_index` calls run before `drop_table`, and InnoDB refuses to drop an index an FK still depends on. SQLite (the test backend) does not enforce this, so the suite stays green while the real rollback is broken. Fix: drop the two `op.drop_index` calls and let `op.drop_table('origin_starting_points')` remove the indexes with the table (or drop the two FK constraints first). Verified live: `035` up/down/up is clean, `034` down is not. The same pattern exists in `031_add_gathering_nodes.py`, so it is a repo habit rather than a one-off — but `034` is new code and demonstrably fails. | Backend Developer | FIXED (Review #2) |
| 2 | `services/locations-service/app/crud.py` (`get_origin_starting_points`) vs feature file §3.2 | Contract deviation. §3.2 specifies `GET /locations/admin/origins/{origin_id}/starting-points` returns `404 «Происхождение не найдено.»` for an unknown origin. It returns `200 []` instead (confirmed live, and pinned by `test_unknown_origin_returns_empty`). `_require_origin` exists and is used by the three write handlers but not by this read. Harmless in the current UI, but code and spec disagree — either call `_require_origin` here, or have the Architect amend §3.2. | Backend Developer / Architect | FIXED (Review #2) |
| 3 | `services/frontend/app-chaldea/src/redux/slices/racesSlice.ts:22-28` | Stale doc-comment. It states `id_race` is "NOT on the nested rows of `GET /characters/races` — `SubraceWithPreset` omits it", but this same change adds `id_race` to `SubraceWithPreset` (required, non-optional). Keeping the optional type and the `?? raceId` fallback as belt-and-braces is fine; the comment now misleads the next reader. | Frontend Developer | FIXED (Review #2) |

#### Pre-existing issues noted (not blocking)
- Two React Router v7 future-flag warnings on every page load — cosmetic, unrelated.
- `vite build` warns about a 3.2 MB main chunk — pre-existing, unrelated.

#### Test data created and cleaned up
All of it removed; the database is back to its pre-review state (one origin
«Республика Белый Клин», one starting point «Подземелье Замка Кёджо», zero links).
- `origin_starting_points`: links from origin 1 to locations 658, 1914 and 635 — **deleted**.
- `Locations.is_starting` promoted by rule 7 on ids 658, 1914, 635 — **reset to 0**.
- `origin_countries` row «ЯЯ Тест Ревьюера FEAT-155» (id 3), created to test the
  no-recommendations branch — **deleted**.
- Subrace «Сиды» was saved unchanged through the admin form (no field edited).
- A character-creation draft in the throwaway Chrome profile — discarded with the profile.

### Review #2 — 2026-09-06
**Result:** PASS

All three findings from Review #1 are fixed, re-verified from scratch rather than on
report. The blocker was re-checked where it actually failed — on the live local MySQL,
not on the SQLite the suite runs against.

#### Automated Check Results (all re-run)
- [x] `py_compile` (12 modified/new Python files) — **PASS**
- [x] `pytest` locations-service (docker, `python:3.10-slim`, `--asyncio-mode=auto`) — **PASS**, `771 passed`
- [x] `npx tsc --noEmit` — **PASS**, no output
- [x] `npx vite build` — **PASS**, built in 26.90s
- [x] Live verification (headless Chrome over CDP + HTTP through the gateway) — **PASS**

#### Issue 1 — migration 034 downgrade (was BLOCKING) — **FIXED**

Both `op.drop_index` calls are gone from `downgrade()`, leaving `op.drop_table` to take the
indexes and constraints with the table, with a comment naming the InnoDB 1553 reason.

Re-run end to end against the live `fogdatabase`:
- `alembic downgrade 034_origin_start_pts` — clean.
- `alembic downgrade 033_start_pts_origins` — **clean this time** (this is the exact command
  that aborted with `(1553, "Cannot drop index 'ix_origin_starting_points_location': needed
  in a foreign key constraint")` in Review #1).
- Confirmed in `information_schema`, not by inference: `TABLES` count for
  `origin_starting_points` is `0`, and `STATISTICS` count is `0` — the table is genuinely
  gone and no index survived it. `origin_countries.country_id` and `.is_playable` are back,
  as 035's downgrade promises.
- `alembic upgrade head` — both revisions re-applied, head is `035_origin_drop_map_link`.
  `SHOW CREATE TABLE origin_starting_points` afterwards shows the primary key,
  `uq_origin_starting_point`, both indexes and both `ON DELETE CASCADE` foreign keys; the
  two dropped columns are absent again (`information_schema` count `0`).

Leaving `031_add_gathering_nodes.py` alone and filing the pattern as a rule in
`docs/ISSUES.md` is the right call — the entry names the SQLite blind spot and requires an
`upgrade → downgrade → upgrade` cycle on real MySQL for any migration touching indexes or
foreign keys, which is what would have caught this.

#### Issue 2 — contract mismatch (was MEDIUM) — **FIXED**

`get_origin_starting_points` now calls `_require_origin` first. Verified through the gateway:
- `GET /locations/admin/origins/999999/starting-points` → **`404 {"detail": "Происхождение не найдено."}`**, matching §3.2.
- `GET /locations/admin/origins/1/starting-points` on a real origin with an empty set → **`200 []`**. Both branches stay distinguishable, and both are pinned (`test_unknown_origin_is_404`, `test_origin_without_links_returns_empty`).
- The three write handlers still answer with the resulting set (`POST` → `[2305, 1795]`, `PUT` reorder → `[1795, 2305]`, `DELETE` → `[1795]`), and all three answer `404 «Происхождение не найдено.»` on an unknown origin.
- **The 404 did not leak into the public route:** `GET /locations/starting-points?origin_id=999999` still returns `200` with the complete list and nothing marked. Rule 2 is unaffected — with a real `origin_id` the annotated list is still the same length as the unfiltered one (3 == 3), recommended first.
- **Hiding an origin still does not break the screen (rule 9).** `_require_origin` resolves through `get_origin_country_by_id`, which does not filter on `is_active`, so a deactivated origin keeps serving its set: soft-deleted origin 1 returned `200 []`, not a 404. Checked deliberately, since a stricter helper would have regressed this.

**On the redundant origin lookup — I agree with the developer's judgement, no change needed.**
Each write handler now reads the origin twice: once in its own `_require_origin`, once inside
the `get_origin_starting_points` it returns. That is one extra primary-key read on an
admin-only endpoint that already performs a write and a commit — immeasurable next to the
join it precedes. The alternative (an internal variant that skips the guard) buys nothing and
adds a second code path where the guard could be forgotten. One nuance worth recording rather
than fixing: the second lookup happens *after* the commit, so if an origin were deleted
concurrently between the write and the response, the client would get a 404 for a write that
did land. On a single-admin screen this is theoretical, and 404 is arguably the more honest
answer at that point.

#### Issue 3 — stale comment (was LOW) — **FIXED**

`racesSlice.ts` now states that `id_race` is present on `SubraceWithPreset` since FEAT-155
and that the optional type plus the `?? raceId` fallback are a deliberate historical
safeguard. Type and fallback unchanged, as intended — the comment no longer contradicts the
schema.

#### Live re-verification of the feature itself

Everything from Review #1's live pass was re-exercised after the code changes, since `crud`
was touched:
- `/admin/origins` → «Стартовые точки» opens on an empty set and shows the «Набор пуст…»
  copy; adding a location that is not yet a starting point produced the toast
  «„Академия Шигель“ добавлена в набор и стала стартовой точкой» and the «Родина» chip;
  «Убрать» returned the panel to the empty state and the search hit went back to «Добавить».
- Zero console errors throughout; `scrollWidth == clientWidth == 360` at mobile width.
- The public contract is byte-compatible: `GET /locations/starting-points` without a
  parameter returns the full list with every `is_recommended` false.

Everything checked in Review #1 that was not touched by these fixes — the wizard's «Присяга»
and «Родина» steps, rule 7 promotion, rule 9 cascade, the subrace fix in `/admin/races`,
`_escape_like`, permissions, Tailwind/TypeScript/`React.FC` compliance — stands as recorded
there.

#### Test data created and cleaned up
Database returned to its pre-review state: one origin («Республика Белый Клин», visible),
one starting point («Подземелье Замка Кёджо»), zero links, head `035_origin_drop_map_link`.
- `origin_starting_points` rows created during the API and UI passes — **deleted**.
- `Locations.is_starting` promoted by rule 7 on ids 2305, 1795, 635, 658, 1914 — **reset to 0**.
- Origin 1 was soft-deleted and restored while testing the hidden-origin branch —
  **`is_active` back to 1**.
- The migration cycle dropped and recreated `origin_starting_points`; it held no production
  data, and the schema after the re-upgrade is identical to the schema before.
- Throwaway Chrome profile — discarded, browser closed.

## 6. Logging

```
[LOG] 2026-09-06 — PM: фича заведена по итогам осмотра FEAT-154 на проде
[LOG] 2026-09-06 21:20 — Reviewer: начал проверку
[LOG] 2026-09-06 21:45 — Reviewer: автопроверки перезапущены самостоятельно — py_compile OK, pytest locations 771 passed, pytest character 806 passed / 1 skipped, tsc и vite build чисто, docker compose config OK
[LOG] 2026-09-06 22:15 — Reviewer: живая проверка — админская панель набора (поиск, добавление, перестановка, удаление), шаг «Присяга» с рекомендациями и без них, шаг «Родина» без бейджей карты, админка рас (подраса «Сиды» не съехала на «Человека»), 360px и 1440px, консоль чистая
[LOG] 2026-09-06 22:30 — Reviewer: миграции на живой БД — 035 upgrade/downgrade/upgrade чисто, у 034 downgrade падает на MySQL (1553, индекс нужен внешнему ключу)
[LOG] 2026-09-06 22:35 — Reviewer: тестовые данные убраны (связи, флаги is_starting у 658/1914/635, временное происхождение id=3)
[LOG] 2026-09-06 22:40 — Reviewer: проверка завершена, результат FAIL — 1 блокирующая проблема (downgrade миграции 034) и 2 мелких
[LOG] 2026-09-06 23:05 — Reviewer: начал повторную проверку после исправлений
[LOG] 2026-09-06 23:15 — Reviewer: автопроверки перезапущены самостоятельно — py_compile OK, pytest locations 771 passed, tsc и vite build чисто
[LOG] 2026-09-06 23:25 — Reviewer: блокер закрыт — цикл upgrade/downgrade/upgrade на живом MySQL прошёл целиком, таблица и индексы исчезают и восстанавливаются полностью (проверено по information_schema)
[LOG] 2026-09-06 23:35 — Reviewer: админский GET на несуществующее происхождение теперь 404, пустой набор реального — 200 []; публичный маршрут не затронут, скрытое происхождение по-прежнему отдаёт свой набор
[LOG] 2026-09-06 23:45 — Reviewer: живая проверка панели повторена (пустой набор, добавление с промоушеном, удаление, 360px) — консоль чистая
[LOG] 2026-09-06 23:50 — Reviewer: тестовые данные убраны, БД в исходном состоянии
[LOG] 2026-09-06 23:55 — Reviewer: повторная проверка завершена, результат PASS
[LOG] 2026-09-06 — Reviewer: Review #2 — PASS, блокер отката миграции закрыт и проверен на живом MySQL
[LOG] 2026-09-06 — PM: фича закрыта
```

## 7. Completion Summary

### Что сделано

У происхождения появился набор **рекомендованных стартовых точек**. Это подсказка, а не ограничение: список на шаге «Присяга» остаётся полным, рекомендованные идут первыми, первая подаётся как родина персонажа. Порядок задаёт админ.

Настройка живёт в разделе «Происхождения» — открыл страну, нашёл локации поиском с хлебными крошками, собрал набор, расставил порядок. Ходить по пятиуровневому дереву локаций больше не нужно. Если добавляемая локация ещё не помечена стартовой, бэкенд помечает её в той же транзакции — инвариант «рекомендованная всегда стартовая» держится независимо от клиента.

Попутно удалены два поля происхождения, оказавшиеся лишними: `country_id` (ссылка на страну карты, не использовалась нигде, кроме подписи в админке) и `is_playable` (галочка «на карте мира», дублировала ссылку и могла ей противоречить). Понятия «на карте» / «вне карты» убраны с шага «Родина».

### Что изменилось от первоначального плана

- **Правила 10-13 добавлены по ходу** — решение убрать оба поля и подавать первую рекомендованную точку как родину принято уже после начала работы.
- **Хранение — таблица связи, а не JSON.** Обе таблицы в одном сервисе, поэтому доступны настоящие внешние ключи; каскадное удаление и есть реализация правила 9, фильтровать мусор на чтении не нужно.
- **Отдельного эндпоинта для рекомендованных не завели** — мастеру нужен весь список с пометкой, а не подмножество, поэтому расширен существующий.

### Сопутствующая правка вне фичи

Исправлен предсуществующий баг админки рас (из FEAT-043): публичный `GET /characters/races` не отдавал `id_race` у подрасы, из-за чего форма подставляла первую расу, и **сохранение молча переподчиняло подрасу «Человеку»**. Починено с обеих сторон — фронт берёт родителя из строки списка, бэкенд отдаёт поле.

### Оставшиеся риски и follow-up

1. **Набор нужно наполнить** — по восьми происхождениям, вручную, после заведения самих происхождений.
2. **Неэкранированные подстановочные знаки в публичном лукапе локаций** (`get_locations_lookup`) — предсуществующее, запись в `docs/ISSUES.md`, чинится двумя строками готовым хелпером.
3. **Явные `drop_index` перед `drop_table` в старой миграции 031** — та же природа, что блокер этой фичи; запись с правилом в `docs/ISSUES.md`.

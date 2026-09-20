# FEAT-173: Раздел «Руководство» с тремя сводами правил

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-20 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-173-slug.md` → `DONE-FEAT-173-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Кнопка «Руководство» на главной ведёт на несуществующую страницу `/guide` — то есть в пустоту. Пункт «Технобук» в мегаменю новостей тоже ведёт в никуда. Правила сейчас лежат единым списком на `/rules`, без деления.

Нужен раздел «Руководство» с тремя сводами: **Правила сайта**, **Правила ролевой**, **Технобук**. Вид разделов пользователь просил не полировать — «переделаем позже»; сейчас нужны структура, навигация и возможность вести содержимое через админку.

### Бизнес-правила
- **Три раздела:** «Правила сайта», «Правила ролевой», «Технобук».
- **Раздел — свойство самого правила.** При создании правила админ выбирает раздел; **селектор нужен и в форме редактирования**, иначе уже написанные правила будет нечем разложить. Пользователь разложит существующие сам.
- Существующие правила после миграции попадают в «Правила сайта» и остаются доступными.
- В верхнем меню пункт **«ПРАВИЛА» заменяется на «РУКОВОДСТВО»** и ведёт на выбор из трёх разделов.
- **«Технобук» убирается из мегаменю НОВОСТИ** — там остаются только новости сайта (Обновления, Анонсы, Ивенты).
- Подссылка **«Обучение»** на главной ведёт на технобук.
- Подссылка **«Консультант»** — отдельная сущность, в этой задаче не трогаем (её маршрута по-прежнему нет).
- **Ссылка «правилами» при создании персонажа** ведёт на «Руководство» и открывается **в новой вкладке**. Это удобство, а не починка бага: визард автосохраняется в `localStorage` (`useCharacterDraft.ts`, ключ `chaldea:character-draft:v1`), и заполненное не теряется ни при уходе по ссылке, ни при F5. Новая вкладка просто избавляет от лишнего возврата.
- Старый адрес `/rules` остаётся рабочим (редирект), чтобы не ломать закладки.

### UX / Пользовательский сценарий
1. Игрок жмёт «Руководство» на главной или в верхнем меню → видит три раздела.
2. Заходит в раздел → список правил этого свода, клик открывает текст.
3. Админ создаёт правило и выбирает раздел; существующее правило может перенести в другой раздел через редактирование.
4. Игрок в процессе создания персонажа открывает руководство в новой вкладке и возвращается к заполненной анкете (черновик и так уцелел бы — см. бизнес-правила).

### Edge Cases
- Пустой раздел (например, технобук до наполнения) — понятное пустое состояние, а не ошибка.
- Старые ссылки на `/rules`.
- Невалидный раздел в адресе.

### Вопросы к пользователю (если есть)
- [x] Откуда содержимое разделов → раздел выбирается у правила, существующие пользователь разложит сам
- [x] «Обучение» → технобук
- [x] «Консультант» → отдельная сущность, не трогаем
- [x] «Технобук» в мегаменю новостей → убрать
- [x] Ссылка при создании персонажа → на «Руководство», в новой вкладке

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

_Разведка выполнена QA-агентом до заведения карточки; Architect должен проверить факты по коду перед проектированием._

Ключевые факты (все с `file:line`, проверены по коду на 2026-09-20):
- `HomePage.tsx:32-33` — кнопка «Руководство» ведёт на `/guide`; маршрута `/guide` в `App.tsx` **нет** (отсюда пустая страница). Подссылки `/learning` и `/consultant` тоже не существуют, `/archive` работает.
- `navData.ts:70-73` — пункт `ПРАВИЛА → /rules`; `navData.ts:36-41` — `Технобук → /news/technobook` (маршрута нет). Файл — единый источник для десктопного хедера и мобильного аккордеона.
- `RulesPage.tsx` + `RuleOverlay.tsx:47` — сетка карточек и оверлей с HTML через DOMPurify (санитайзинг уже есть).
- `locations-service/app/models.py:293-302` — таблица `game_rules`: `id, title, image_url, content, sort_order`; колонки раздела нет. `GET /rules/list` — `main.py:1932`. Админка правил и RBAC-модуль `rules` уже существуют.
- Alembic head locations-service: `043_gathering_ingredient`.
- `CreateCharacterPage.tsx:373-380` — ссылка «правилами» как `<a onClick={navigateTo('/rules')}>` без `href`. **ИСПРАВЛЕНО PM 2026-09-20:** утверждение «визард нигде не сохраняется» было ошибкой разведки. Шаги визарда действительно лежат в `useState`, но снимок автосохраняется в `localStorage` — `useCharacterDraft.ts` (`useCharacterDraftAutosave` на `:192`, восстановление на `:137`, очистка после отправки на `:259-264`). Комментарий на `:82-84` относится только к `kitPreview` — единственному полю, намеренно не попадающему в черновик.
- `HomePage.tsx:84-116` — теги «Технобук» в слайдере это заглушечные данные (`/sliderlink1..4`), не таксономия новостей.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Verification of the Analysis Report

Every load-bearing claim in section 2 was re-checked against the code. Result: **all facts confirmed**, with four corrections / additions that change how the work must be done.

| Claim (section 2) | Verdict |
|---|---|
| `game_rules` columns = `id, title, image_url, content, sort_order` | **Confirmed** (`services/locations-service/app/models.py:293-302`). Plus `created_at`, `updated_at`. No section column. |
| Alembic head of locations-service = `043_gathering_ingredient` | **Confirmed.** `043_gathering_ingredient_category.py` declares `revision = '043_gathering_ingredient'`, `down_revision = '042_recommended_level_ranges'`, and no other file claims it as a parent → single head. |
| `navData.ts` is the single source for desktop header **and** mobile accordion | **Confirmed** (file header comment; `ПРАВИЛА → /rules`, `Технобук → /news/technobook` both present). |
| `GET /rules/list` at `main.py:1932`, no filtering | **Confirmed**; delegates to `crud.get_all_rules` (`crud.py:3090`), ordered by `sort_order ASC, id ASC`. |
| `RulesPage.tsx` grid + `RuleOverlay.tsx` DOMPurify | **Confirmed** (`RuleOverlay.tsx:2,48`). Sanitizing is already in place; **do not** add a second sanitizer. |
| `CreateCharacterPage.tsx` link is `<a onClick={navigateTo('/rules')}>` with no `href`; wizard state is local `useState` | **Half wrong — corrected by PM.** The link and the `useState` steps are real, but the wizard **is** persisted: `useCharacterDraft.ts` autosaves a snapshot to `localStorage` (debounced 500 ms, 30-day TTL, keyed by `userId`), wired at `CreateCharacterPage.tsx:192` and restored at `:137`. The "deliberately not persisted" comment at `:82-84` covers `kitPreview` alone. **There is no state-loss bug**; see §3.5. |
| Route `/guide` absent from `App.tsx` | **Confirmed**; only `<Route path="rules" element={<RulesPage />} />` (`App/App.tsx:196`). |

**Corrections and additions the recon missed:**

1. **Migration path.** locations-service migrations live in `services/locations-service/app/alembic/versions/` (not `alembic/versions/`). The new file goes there.
2. **WRONG — corrected by PM after the review.** The claim below said `/rules` (no trailing slash) falls through to `location /`. It does not: nginx issues its own `301` to `/rules/` for the proxied prefix block, and locations-service has no bare `/rules` route, so a bookmark got a 404. The business rule "старый адрес `/rules` остаётся рабочим" was therefore unmet. **Fixed in this feature** by adding exact-match blocks `location = /rules` and `location = /rules/`, both `return 301 /guide`, ahead of the `/rules/` prefix block in **both** `nginx.conf` and `nginx.prod.conf`. Exact matches outrank prefixes, so the API paths (`/rules/list`, `/rules/create`, …) are untouched — verified live after rebuilding the gateway. The original (incorrect) reasoning follows:

   **nginx already handles this — no DevSecOps work.** `location /rules/` (with a trailing slash) proxies to locations-service in **both** `nginx.conf:420` and `nginx.prod.conf:435`. The SPA route `/rules` (no trailing slash) falls through to `location /`. `/guide` and `/guide/:section` match no backend prefix, and prod's `location /` does `try_files $uri $uri/ /index.html` (`nginx.prod.conf:552-555`) while dev proxies to Vite — so deep links work in both environments **without touching either nginx file**. Nobody should edit nginx for this feature.
3. **`crud.create_rule` silently drops `image_url`** (`crud.py:3106-3116` sets only title/content/sort_order); the image is written later by photo-service `POST /photo/change_rule_image` (`services/photo-service/main.py:766`). This is expected, not a bug to fix here — but the Backend Dev must add `section` to `create_rule` explicitly, or it will be dropped the same way. This is exactly the silent-failure shape that has bitten this repo before.
4. **photo-service is unaffected.** It only updates `image_url` on `game_rules`; a new column with a server default is invisible to it. No mirror-model change, no photo-service migration.

### 3.1 Scope boundary — read this first

The user explicitly asked **not to polish the visuals**: "вид разделов переделаем позже". This feature delivers **structure, data model and navigation only**. Reuse the existing rules grid as-is. Do not redesign cards, do not invent iconography, do not restyle `RuleOverlay`. Mandatory frontend rules (Tailwind only, `.tsx`, no `React.FC`, works at 360px, design-system classes first) still apply to everything that is written — but "apply the design system" means *reuse existing tokens and classes*, not *design something new*. Gold-plating is a review failure here, same as under-delivering.

### 3.2 Data model — `game_rules.section`

```sql
ALTER TABLE game_rules
  ADD COLUMN section ENUM('site','roleplay','technobook')
  NOT NULL DEFAULT 'site'
  AFTER title;
```

**ENUM vs VARCHAR — deliberate decision: ENUM.** The project memo warns against ENUM *on the big `items` table*, where an ENUM change takes a table-rebuild lock. That reasoning does not transfer here:

- `game_rules` is an editorial table of a few dozen rows at most; a rebuild is instantaneous.
- The value set is closed by the product definition (three sections, fixed).
- The direct precedent in this same service — `gathering_nodes.category` (`models.py:667-668`) — is an ENUM with a parity test (`test_gathering_ingredient.py::TestMigration043`) that we are told to mirror. Matching the precedent keeps one pattern in one service instead of two.
- ENUM gives DB-level rejection of a bad value, which is the cheapest possible guard against the "typo in a value" failure mode.

If the section list ever needs to grow, follow the 043 pattern: `ALTER TABLE ... MODIFY COLUMN` appending the value (safe on MySQL, append-only), and bump the parity test.

**No index.** Filtering three sections across a few dozen rows is a full scan either way; an index would only add a downgrade hazard (the project has already been burned dropping indexes — errno 1553). The column is deliberately un-indexed. If the table ever grows past a few hundred rules, add `(section, sort_order)` as a separate change.

**ORM** (`models.py`, `GameRule`):
```python
section = Column(
    Enum('site', 'roleplay', 'technobook', name='game_rule_section'),
    nullable=False,
    server_default='site',
)
```
Placed after `title`. `server_default` (not `default`) so the DB itself backfills any writer that forgets the field.

### 3.3 Migration `044_game_rule_section`

File: `services/locations-service/app/alembic/versions/044_game_rule_section.py`

```python
revision = '044_game_rule_section'          # 22 chars — well under the 32-char limit
down_revision = '043_gathering_ingredient'
SECTIONS = ('site', 'roleplay', 'technobook')
DEFAULT_SECTION = 'site'
```

- **upgrade:** a single `op.execute("ALTER TABLE game_rules ADD COLUMN section ENUM(...) NOT NULL DEFAULT 'site' AFTER title")`. MySQL fills every existing row with `'site'` as part of the same statement — **no separate UPDATE pass is needed, and none should be written.** That is the entire "existing rules land in Правила сайта" requirement.
- **downgrade:** `op.execute("ALTER TABLE game_rules DROP COLUMN section")`, unconditional.

**Why the downgrade is unconditional and not fail-fast like 043.** Migration 043 refuses to shrink an ENUM while rows hold the doomed value, because shrinking would corrupt surviving rows. Here the whole column goes away: every rule remains intact and the page reverts to one undivided list — which is precisely the pre-feature state. A fail-fast guard would make rollback impossible the moment an admin files one rule under «Технобук», i.e. it would turn a working rollback into a broken one. The only thing lost is the section assignment, and that is inherent to removing the column; it is stated here so it is a decision, not an accident.

Constants `SECTIONS` / `DEFAULT_SECTION` are module-level **so the parity test can import them** (the 043 test imports `CATEGORIES_NEW` the same way).

Revision-id length, single-head chain and the `alembic_version_locations` version table are all respected; auto-migration on container start means no manual step.

### 3.4 API contract (locations-service, async SQLAlchemy, Pydantic <2.0)

Shared type in `schemas.py`, next to the existing `GatheringCategory` precedent (`schemas.py:1547`):

```python
RuleSection = Literal["site", "roleplay", "technobook"]
```

#### `GET /rules/list` — modified (public)

| | |
|---|---|
| Query | `section: Optional[RuleSection] = None` |
| Auth | none (public, unchanged) |
| 200 | `List[GameRuleRead]` — unchanged shape, now with `section` |
| 422 | section not one of the three values (FastAPI validates the `Literal`) |

**Backward compatibility is the contract, not a nicety.** With no `section` parameter the endpoint must return **every** rule in **exactly** today's order (`sort_order ASC, id ASC`) — no implicit `section='site'` default. During a rolling deploy an old frontend bundle calls `/rules/list` with no parameter and must keep seeing the full list. Implement as an optional `WHERE` in `crud.get_all_rules(session, section: Optional[str] = None)` — the default argument keeps every existing caller compiling and behaving identically.

#### `GET /rules/{rule_id}` — unchanged code, response gains `section`

Additive field; safe for any existing consumer.

#### `POST /rules/create` — modified (`rules:create`)

`GameRuleCreate` gains `section: RuleSection = "site"`. Omitting it is still valid and yields `site`, so no existing caller breaks. **`crud.create_rule` must pass `section=data.section` explicitly** (see 3.0 note 3).

#### `PUT /rules/{rule_id}/update` — modified (`rules:update`)

`GameRuleUpdate` gains `section: Optional[RuleSection] = None`. The existing `data.dict(exclude_unset=True)` loop (`crud.py:3128`) already handles it: a payload without `section` leaves the field untouched, a payload with it moves the rule. **This is the mechanism that lets the user redistribute the rules they have already written** — it is the feature's stated goal, not a bonus.

#### `PUT /rules/reorder`, `DELETE /rules/{id}/delete` — untouched.

**Security review of the change:** no new endpoint, no new permission. The read path stays public (rules are public content by definition); writes keep their existing `require_permission("rules:create" / "rules:update" / "rules:delete")` RBAC gates, so the RBAC-seeding rule in CLAUDE.md §7 does not apply — no new `permissions` row, no new migration for `role_permissions`, no new `test_rbac_permissions.py` section. Input validation for the new field is total: `Literal` at the edge, ENUM at the DB. No user-supplied string ever reaches SQL — the filter is a bound parameter on a validated value, so the query is injection-proof by construction. Rate limiting is unchanged (same public read surface, no new cost per request).

### 3.5 Frontend design

#### Section metadata — one source of truth

New `src/constants/guideSections.ts`:

```ts
export type GuideSection = 'site' | 'roleplay' | 'technobook';

export interface GuideSectionMeta {
  slug: GuideSection;
  label: string;        // 'Правила сайта' | 'Правила ролевой' | 'Технобук'
  description: string;  // one short Russian line for the card
}

export const GUIDE_SECTIONS: GuideSectionMeta[] = [...];
export const isGuideSection = (v: string | undefined): v is GuideSection => ...;
```

The **URL slug is the DB enum value** — `/guide/site`, `/guide/roleplay`, `/guide/technobook`. One vocabulary from the ENUM through the Pydantic `Literal` and the TS union to the URL; no mapping table to drift.

#### Routing (`components/App/App.tsx`)

| Path | Element |
|---|---|
| `/guide` | `GuidePage` — three cards |
| `/guide/:section` | `GuideSectionPage` |
| `/rules` | `<Navigate to="/guide" replace />` — old bookmarks keep working |

`RulesPage.tsx` is removed and its import dropped; `RuleOverlay.tsx` **stays where it is** so its path and its DOMPurify call are untouched.

#### Components

- `src/components/GuidePage/GuidePage.tsx` — maps `GUIDE_SECTIONS` to three `<Link>` cards. Static; no API call, so no loading/error state to get wrong.
- `src/components/GuidePage/GuideSectionPage.tsx` — reads `useParams`, validates with `isGuideSection`; an unknown slug renders `<Navigate to="/guide" replace />` (a wrong URL lands on the section picker — never a 422, never a crash). Valid slug → `fetchRules(section)` → title + `<RulesGrid>` + `RuleOverlay`, plus a "← Руководство" back link.
- `src/components/RulesPage/RulesGrid.tsx` — the card grid lifted verbatim out of today's `RulesPage.tsx` (same `motion` stagger, same `image-card rounded-card shadow-card`, same `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`). Props: `rules`, `onSelect`. **Lift, do not redesign.**

**Empty section is a state, not an error** (the technobook will be empty on day one): `rules.length === 0` → a calm Russian line in the existing muted style, e.g. «В этом разделе пока нет материалов» — same treatment as today's «Правила пока не добавлены». A 200 with an empty array is a success; it must never render the red `text-site-red` error branch or fire a `toast.error`.

**Error handling is still mandatory**: the fetch keeps today's `try/catch` → visible Russian message **and** `toast.error`. Nothing silent.

#### Navigation changes

| File | Change |
|---|---|
| `navData.ts` | `{ label: 'ПРАВИЛА', path: '/rules' }` → `{ label: 'РУКОВОДСТВО', path: '/guide' }`. Drop `{ label: 'Технобук', path: '/news/technobook' }` from the `НОВОСТИ` category, leaving Обновления / Анонсы / Ивенты. One edit covers desktop header and mobile accordion. |
| `HomePage.tsx` | `Обучение`: `/learning` → `/guide/technobook`. `Руководство` already points at `/guide`, which now exists. **`Консультант` is not touched** — it stays a dead link by explicit user decision; do not "fix" it. |
| `CreateCharacterPage.tsx` | See below. |

The «Технобук» tags in the HomePage slider (`HomePage.tsx:84-116`) are placeholder slide data, not taxonomy — **out of scope, leave them alone.**

#### The character-creation link — a convenience change, NOT a bug fix

Today: `<a onClick={() => navigateTo('/rules')}>правилами</a>` — no `href`, same-tab navigation.

**Correction to this design's first draft.** It claimed the wizard loses its state on that click. It does not: `useCharacterDraft.ts` autosaves every step to `localStorage` (debounced 500 ms, keyed by `userId`, 30-day TTL), wired at `CreateCharacterPage.tsx:192` and restored at `:137`. A player who navigates away in the same tab and comes back finds race, origin, class, application and location intact. **There is no state-loss bug here — do not write a fix for one, do not touch `docs/ISSUES.md`, and do not claim one in the commit message.**

Change, on its own merits: a real anchor, `href="/guide"`, `target="_blank"`, `rel="noopener noreferrer"`, `onClick` removed. The point is the link target (`/rules` → `/guide`) plus a real `href`, which restores middle-click, Ctrl+click and "copy link address" and shows the URL in the status bar; the new tab merely saves the player a trip back. The link text stays «правилами».

**Note for the Frontend Dev:** there is an uncommitted edit on `main`'s working tree that already converted this `<a onClick>` into `<Link to="/rules">`. Build on whatever is on disk; the end state is the anchor described above.

### 3.6 Data flow

```
Admin: RuleForm (section <select>)
  → PUT /rules/{id}/update {section:"technobook"}  [rules:update]
  → crud.update_rule → exclude_unset loop → UPDATE game_rules.section
                                                    │
Player: /guide → three cards → /guide/technobook    │
  → GET /rules/list?section=technobook  (public) ◄───┘
  → crud.get_all_rules(section) → SELECT ... WHERE section=:s ORDER BY sort_order, id
  → RulesGrid → click → RuleOverlay (DOMPurify)
```

No inter-service HTTP call is added or changed. No queue, no cache, no Celery task. The only service touched is locations-service; photo-service, user-service and the rest are untouched.

### 3.7 Risks

| Risk | Handling |
|---|---|
| Rolling deploy: old bundle hits new backend | No-parameter call returns everything, exactly as before — covered by an explicit QA test. |
| New bundle hits old backend (nginx caching a stale upstream, see prod-502 memo) | `?section=` is ignored by an old backend → the section page shows all rules instead of a subset. Degraded, never broken. |
| `section` silently dropped on create | `crud.create_rule` ignores unlisted fields today; QA asserts the created rule comes back with the requested section. |
| Enum drifts between ORM / migration / Pydantic / TS | Parity test (Task 6) pins ORM ↔ migration ↔ `Literal`; the TS union is pinned by `tsc` against `GuideSection`. |
| Downgrade loses section assignments | Accepted and documented (3.3) — it restores the exact pre-feature state. |
| Someone "improves" the visuals | Called out in 3.1 and in the acceptance criteria of every frontend task. |

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Parallelism plan.** Tasks 1 and 2 start together (backend and the small shared frontend foundation touch disjoint files). Tasks 3, 4 and 5 then run in parallel — they were split along file boundaries specifically so three frontend agents never edit the same file. Task 6 (QA) needs Task 1. Task 7 (Review) is last.

```
T1 (backend) ─────────────┬─> T6 (QA) ─┐
T2 (shared FE constants) ─┼─> T3 (admin FE)   ─┤
                          ├─> T4 (public FE)  ─┼─> T7 (Review)
                          └─> T5 (navigation) ─┘
```

**No DevSecOps task.** nginx, docker-compose and env vars need no change — verified in §3.0 note 2. Nobody should edit `nginx.conf` / `nginx.prod.conf` for this feature.

---

### Task 1 — Backend: `section` column, migration, filter

| Field | Value |
|---|---|
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Depends On** | — |
| **Files** | `services/locations-service/app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, **new** `app/alembic/versions/044_game_rule_section.py` |

**Description**
1. `models.py` — add `section` to `GameRule` per §3.2 (ENUM, `nullable=False`, `server_default='site'`, placed after `title`).
2. New migration `044_game_rule_section.py` per §3.3: `revision = '044_game_rule_section'`, `down_revision = '043_gathering_ingredient'`, module-level `SECTIONS` and `DEFAULT_SECTION`, upgrade = one `ADD COLUMN ... NOT NULL DEFAULT 'site'` (no separate UPDATE pass), downgrade = unconditional `DROP COLUMN`.
3. `schemas.py` — `RuleSection = Literal["site", "roleplay", "technobook"]` (mirror the `GatheringCategory` style at `schemas.py:1547`); `section: RuleSection = "site"` on `GameRuleCreate`, `section: Optional[RuleSection] = None` on `GameRuleUpdate`, `section: RuleSection` on `GameRuleRead`. Pydantic **v1** syntax; keep `class Config: orm_mode = True`.
4. `crud.py` — `get_all_rules(session, section: Optional[str] = None)` applies `WHERE` only when `section` is given, ordering untouched. **`create_rule` must set `section=data.section`** — it builds the model field-by-field and will otherwise drop it silently (§3.0 note 3). `update_rule` needs no change; confirm the `exclude_unset` loop moves the rule.
5. `main.py` — `get_rules_list(section: Optional[schemas.RuleSection] = None, ...)`, passed through to crud. Keep the route order (`/list` before `/{rule_id}`).

**Acceptance Criteria**
- `python -m py_compile` passes on every modified file.
- `GET /rules/list` with no parameter returns all rules in `sort_order ASC, id ASC` — byte-identical behaviour to today.
- `GET /rules/list?section=roleplay` returns only that section; `?section=nonsense` → 422.
- Revision id ≤ 32 chars; `044` is the only child of `043`; single head.
- `downgrade()` is a plain `DROP COLUMN` with no fail-fast guard.
- No new RBAC permission, no `permissions` row, no nginx/compose change.

---

### Task 2 — Frontend foundation: section constants + API types

| Field | Value |
|---|---|
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Depends On** | — (contract is fixed in §3.4; do not wait for Task 1) |
| **Files** | **new** `src/constants/guideSections.ts`, `src/api/rules.ts` |

**Description**
1. New `guideSections.ts` per §3.5: `GuideSection` union, `GuideSectionMeta`, `GUIDE_SECTIONS` (three entries, Russian labels «Правила сайта» / «Правила ролевой» / «Технобук» plus a one-line Russian description each), and the `isGuideSection` type guard.
2. `src/api/rules.ts`: add `section: GuideSection` to `GameRule`, `section?: GuideSection` to `GameRuleCreate` and `GameRuleUpdate`; `fetchRules(section?: GuideSection)` sends `?section=` **only when the argument is given** (no parameter = today's behaviour).

**Acceptance Criteria**
- `npx tsc --noEmit` passes.
- Slugs are exactly `site` / `roleplay` / `technobook` — identical to the DB enum.
- `fetchRules()` with no argument produces a request with no query string.
- This task owns these two files; Tasks 3–5 only import from them.

---

### Task 3 — Admin: pick a section on create **and** on edit, see it in the list

| Field | Value |
|---|---|
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Depends On** | 2 |
| **Files** | `src/components/Admin/RulesAdminPage/RuleForm.tsx`, `RuleList.tsx`, `RulesAdminPage.tsx` (only if wiring requires it) |

**Description**
1. `RuleForm.tsx` — a section `<select>` in the existing `grid-cols-1 sm:grid-cols-2` field block, labelled «Раздел», options from `GUIDE_SECTIONS`. `useState<GuideSection>(rule?.section ?? 'site')`. Send `section` in **both** the create and the update payload. **The edit path is the point of this task**: without it the user cannot redistribute the rules they have already written, which is their stated goal — a form that only sets the section on create is a FAIL.
2. `RuleList.tsx` — a «Раздел» column showing the Russian label, and a way to narrow the list by section (a small filter control above the table; "Все" is the default and shows everything). Client-side filter over the already-fetched list, or `fetchRules(section)` — either is fine; the empty result must read as «Нет правил в этом разделе», not as an error.

**Acceptance Criteria**
- `npx tsc --noEmit` and `npm run build` both pass.
- Creating a rule with «Технобук» selected → it appears under technobook.
- Editing an existing rule's section → saved and reflected in the list (the redistribution path works end to end).
- Filtering to an empty section shows a calm Russian message, never an error or a toast.
- Tailwind only — no new SCSS. No `React.FC`. Works at 360px: the select is full-width when the grid collapses to one column, and the table stays usable (`overflow-x-auto` if it needs it). Reuse `input-underline`, `gray-bg`, `btn-blue`, `gold-text` — **do not invent new visual language** (§3.1).
- Errors from the API stay visible (`toast.error` + message), nothing swallowed.

---

### Task 4 — Public: `/guide`, `/guide/:section`, `/rules` redirect

| Field | Value |
|---|---|
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Depends On** | 2 |
| **Files** | **new** `src/components/GuidePage/GuidePage.tsx`, **new** `src/components/GuidePage/GuideSectionPage.tsx`, **new** `src/components/RulesPage/RulesGrid.tsx`, `src/components/App/App.tsx`, delete `src/components/RulesPage/RulesPage.tsx` |

**Description**
1. Extract today's card grid from `RulesPage.tsx` into `RulesGrid.tsx` (props `rules`, `onSelect`) **verbatim** — same motion stagger, same classes, same markup.
2. `GuidePage.tsx` — three `<Link>` cards from `GUIDE_SECTIONS`, page title «Руководство». Static, no fetch.
3. `GuideSectionPage.tsx` — `useParams`, `isGuideSection` guard (unknown slug → `<Navigate to="/guide" replace />`), `fetchRules(section)`, keep the existing loading / error / toast pattern, render `RulesGrid` + `RuleOverlay`, add a back link to `/guide`. Empty array → «В этом разделе пока нет материалов» in the muted style — **success, not an error branch** (the technobook ships empty).
4. `App.tsx` — add `/guide` and `/guide/:section`; replace the `rules` route with `<Navigate to="/guide" replace />`; drop the `RulesPage` import; delete `RulesPage.tsx`. **Leave `RuleOverlay.tsx` untouched** — its DOMPurify sanitizing is already correct and must not be duplicated or modified.

**Acceptance Criteria**
- `npx tsc --noEmit` and `npm run build` both pass.
- `/guide` shows three cards; each opens its section; a rule opens in the overlay with HTML rendered as today.
- `/rules` redirects to `/guide`; `/guide/garbage` lands on `/guide` (no crash, no 422 surfaced to the user).
- Empty section = calm message, no red text, no toast.
- Tailwind only, `.tsx`, no `React.FC`, readable at 360px (cards stack to one column).
- **Structure only** — the grid is lifted, not redesigned; no new visual treatment (§3.1).

---

### Task 5 — Navigation and entry points

| Field | Value |
|---|---|
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Depends On** | 2 |
| **Files** | `src/components/CommonComponents/Header/navData.ts`, `src/components/HomePage/HomePage.tsx`, `src/components/CreateCharacterPage/CreateCharacterPage.tsx` |

**Description**
1. `navData.ts` — `ПРАВИЛА /rules` → `РУКОВОДСТВО /guide`; remove `Технобук → /news/technobook` from the `НОВОСТИ` category (Обновления / Анонсы / Ивенты remain).
2. `HomePage.tsx` — `Обучение`: `/learning` → `/guide/technobook`. **Do not touch `Консультант`** (explicit user decision) and **do not touch the slider's «Технобук» placeholder tags** (§3.5).
3. `CreateCharacterPage.tsx` — replace the «правилами» link (currently `<a onClick={() => navigateTo('/rules')}>`, possibly already a `<Link to="/rules">` in the working tree) with a real anchor: `href="/guide"`, `target="_blank"`, `rel="noopener noreferrer"`, no `onClick`. Keep the text and the existing classes. **This is a convenience change, not a bug fix** — the wizard already autosaves via `useCharacterDraft.ts`, so nothing is lost either way. Do **not** add or close a `docs/ISSUES.md` entry for it and do not describe it as a state-loss fix.

**Acceptance Criteria**
- `npx tsc --noEmit` and `npm run build` both pass.
- Header (desktop **and** mobile accordion) shows «РУКОВОДСТВО» → `/guide`; «Технобук» is gone from the news mega-menu.
- Home page «Обучение» → `/guide/technobook`; «Консультант» unchanged.
- The character-creation link opens `/guide` in a new tab, and the original tab still shows the filled-in wizard (which the existing autosave already guaranteed).
- The link is a real `href` (middle-click and Ctrl+click open a new tab; the URL shows in the status bar).

---

### Task 6 — QA: backend tests

| Field | Value |
|---|---|
| **Agent** | QA Test |
| **Status** | DONE |
| **Depends On** | 1 |
| **Files** | **new** `services/locations-service/app/tests/test_rule_sections.py` |

**Description** Follow the house style in `tests/test_gathering_ingredient.py` (module loader for the migration, `conftest.py`'s mocked async session). Required cases:

1. **Parity — ORM ↔ migration ↔ Pydantic**, modelled on `TestMigration043`:
   - `tuple(models.GameRule.__table__.c.section.type.enums) == migration.SECTIONS`
   - `set(schemas.RuleSection.__args__) == set(models.GameRule.__table__.c.section.type.enums)`
   - `migration.DEFAULT_SECTION == 'site'` and is a member of `SECTIONS`
2. **Revision chain:** `revision == '044_game_rule_section'`, `len(revision) <= 32`, `down_revision == '043_gathering_ingredient'`, and `044` is the sole child of `043` (reuse the directory-scan test).
3. **Migration SQL:** upgrade adds the column `NOT NULL DEFAULT 'site'` (so existing rows are backfilled by the ALTER itself — assert no separate `UPDATE` statement is issued); downgrade drops the column **unconditionally**, with no fail-fast guard.
4. **No parameter = today's behaviour:** `GET /rules/list` with no query returns every rule and applies no section filter.
5. **Filter behaviour:** `?section=roleplay` returns only that section's rules, ordering preserved.
6. **Invalid section:** `?section=nonsense` (and a mixed-case / empty variant) → 422, no DB query.
7. **Backward compatibility of existing rows:** a rule whose `section` was never set reads back as `site` (server default), and `GameRuleCreate` without `section` validates to `'site'`.
8. **`section` is changeable via update:** `PUT /rules/{id}/update` with `{"section": "technobook"}` moves the rule; a payload **without** `section` leaves it untouched (`exclude_unset`).
9. **Create honours the field:** `POST /rules/create` with `section='technobook'` persists it — the regression guard for `crud.create_rule` dropping unlisted fields.
10. **Security:** create/update/delete still require their `rules:*` permissions; `GET /rules/list` is still public.

**Acceptance Criteria**
- `pytest services/locations-service/app/tests/test_rule_sections.py` passes inside the container.
- The full locations-service suite still passes (no regression in existing rules tests).
- Adding a fourth section later fails test 1 loudly until every layer is updated.

---

### Task 7 — Review

| Field | Value |
|---|---|
| **Agent** | Reviewer |
| **Status** | DONE |
| **Depends On** | 1, 2, 3, 4, 5, 6 |
| **Files** | all of the above |

**Description & Acceptance Criteria**
- Re-run `py_compile`, `npx tsc --noEmit`, `npm run build`, and the locations-service pytest suite. Record the results — a review without them is invalid.
- **Live verification** (chrome-devtools or curl): `/guide` renders three cards; each section page loads; an empty section shows the empty state, not an error; `/rules` redirects; `/guide/garbage` lands on `/guide`; admin can set a section on create **and** change it on an existing rule; the character-creation link opens a new tab on `/guide`. Zero console errors, zero 500s.
- Verify the migration ran on container start and existing rules came back as `site`.
- `curl /rules/list` with **no** parameter returns the full list (mid-deploy safety).
- Frontend rules: Tailwind only (no new SCSS), `.tsx` only, no `React.FC`, usable at 360px, design-system classes reused.
- **Scope check:** confirm nobody redesigned the rules cards or overlay, nobody touched «Консультант», the slider tags or nginx. Over-delivery here is as much a FAIL as under-delivery (§3.1).
- Confirm `docs/ISSUES.md` reflects the character-creation link fix.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-20
**Result:** PASS

All seven tasks deliver what section 3 designed, nothing more. Two non-blocking notes are recorded below.

#### Automated Check Results
- `npx tsc --noEmit` (container `frontend`) — **PASS**
- `npm run build` (container `frontend`) — **PASS** (`✓ built in 32.76s`; only the pre-existing >500 kB chunk warning)
- `python -m py_compile models.py schemas.py crud.py main.py alembic/versions/044_game_rule_section.py` (container `locations-service`) — **PASS**
- `pytest tests/ --asyncio-mode=auto` (container `locations-service`) — **PASS**, `1499 passed, 7 warnings in 23.95s`, 0 failed
- `docker compose config` — **PASS**
- Live verification (curl; chrome-devtools MCP and the Chrome extension are both unavailable in this session) — **PASS**, see below

#### Live Verification Results
Schema / migration (MySQL `fogdatabase`):
- `alembic_version_locations = 044_game_rule_section` — the migration ran on container start.
- `SHOW COLUMNS FROM game_rules LIKE 'section'` → `enum('site','roleplay','technobook')`, `NO` null, default `site`.
- `SELECT section, COUNT(*) … GROUP BY section` → `site: 4` — every pre-existing rule landed in «Правила сайта», backfilled by the ALTER alone.

API (through the gateway on :80):
- `GET /rules/list` (no parameter) → 200, all 4 rules in `sort_order ASC, id ASC` (ids 2, 5, 3, 4) — mid-deploy safety holds.
- `GET /rules/list?section=site` → 200, the same 4; `?section=technobook` → 200 `[]` (empty section is a success, not an error); `?section=nonsense` → **422**.
- `POST /rules/create {"section":"technobook"}` as admin → 200, response `section: "technobook"`, and the rule shows up under `?section=technobook` — `crud.create_rule` does **not** drop the field.
- `PUT /rules/6/update {"section":"roleplay"}` → the rule moves; a follow-up `{"title": …}` **without** `section` leaves it on `roleplay` (`exclude_unset` works). **The redistribution path — the point of the feature — works end to end.**
- `PUT /rules/{id}/update` with no token → **401**; reads stay public. Test rule deleted afterwards; the DB is back to 4 `site` rules.

SPA routes: `/guide` → 200, `/guide/technobook` → 200, `/guide/garbage` → 200 (client-side `<Navigate to="/guide" replace />`).

Built bundle (`dist/assets/index-*.js`) — string-level confirmation of the navigation changes that could not be clicked without a browser: `РУКОВОДСТВО` present, `Правила ролевой` present, `В этом разделе пока нет материалов` present, `guide/technobook` present, `news/technobook` **absent** (Технобук removed from the news mega-menu), `/learning` **absent**, `/consultant` **still present** (the dead link is preserved, as the user decided).

No 500 on any call. Browser console could not be inspected (no browser automation available in this session) — the runtime surface was verified through HTTP status codes, response bodies and the built bundle instead.

#### Scope check
- **Visuals not polished.** `RulesGrid.tsx` is a verbatim lift of the old grid (same motion stagger, same `image-card rounded-card shadow-card`, same `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`). `GuidePage` cards reuse `gray-bg rounded-card shadow-card` + `gold-text`; no new visual language, no new tokens, no new CSS layer.
- `RuleOverlay.tsx` untouched — one DOMPurify call, no second sanitizer.
- «Консультант» untouched (`HomePage.tsx:35`); the slider's placeholder «Технобук» tags untouched. `HomePage.tsx` diff is a single line.
- nginx, docker-compose, photo-service, user-service, RBAC (`permissions` / `role_permissions`) — **not touched**, as designed in §3.0 note 2 and §3.4.
- No `docs/ISSUES.md` entry was written about the character-creation link, and no agent described it as a state-loss fix — correct per the PM correction. (T7's own criterion «Confirm `docs/ISSUES.md` reflects the character-creation link fix» is a leftover from the Architect's first draft and was deliberately **not** acted on; it contradicts §3.5 and the PM log of 15:40.)

#### Standards check
- Tailwind only — no `.css` / `.scss` added or modified anywhere in the diff.
- All new files are `.tsx` / `.ts`; no `.jsx` created or left behind.
- No `React.FC` / `React.FunctionComponent` in any new or modified component.
- 360px: `RuleList` filter row is `flex-col sm:flex-row` with a full-width select, the table sits in `overflow-x-auto` with `min-w-[640px]`; `RuleForm`'s select is `w-full` inside the existing collapsing grid; both card grids start at `grid-cols-1`.
- Error handling: `GuideSectionPage` keeps `try/catch` → visible Russian `text-site-red` message **and** `toast.error`; the empty list is a separate calm branch, never the error branch. `RuleList` and `RuleForm` keep their `toast.error` paths. Nothing swallowed.
- Contracts line up: Pydantic `RuleSection = Literal["site","roleplay","technobook"]` ↔ DB ENUM ↔ TS `GuideSection` ↔ URL slug — one vocabulary, pinned by the parity tests and by `tsc`. Pydantic v1 syntax preserved (`class Config: orm_mode = True` untouched).
- QA: T6 exists and is done — `tests/test_rule_sections.py`, 494 lines, 38 test functions / **55 test cases** (parametrized), covering parity, the revision chain, the migration SQL, real-aiosqlite crud behaviour, route behaviour and RBAC gating. Run on its own: `55 passed`.

#### Notes (non-blocking)
1. **`/rules` is not reachable by a direct URL — pre-existing, not a regression.** nginx answers `301` for the slash-less form of the proxied `location /rules/` block, so `GET /rules` → `301 /rules/` → locations-service → `404` (verified with `curl -sL`). The `<Navigate to="/guide" replace />` route at `App.tsx:200` therefore only fires for in-app navigation, not for a real bookmark. The same was true of the old `RulesPage` before this feature, so nothing got worse — but §3.0 note 2's claim that «`/rules` falls through to `location /`» is factually wrong, and the business rule «старые закладки продолжают работать» is not actually satisfied. Fixing it needs an nginx change, which this feature was explicitly told not to make. Logged in `docs/ISSUES.md` (MEDIUM) as a separate task.
2. `test_rules.py`'s `_make_rule` fixture had to gain `section="site"`; without it the `MagicMock` fails `GameRuleRead` validation. Correct and minimal — noted only because it is the "wrong-shaped fixture" pattern that has bitten this repo before, and here it was handled properly.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-20 — PM: фича заведена по результатам разведки и ответов пользователя, запускаю архитектора
[LOG] 2026-09-20 14:10 — Architect: начал проектирование, перепроверяю факты раздела 2 по коду
[LOG] 2026-09-20 14:35 — Architect: разведка подтверждена полностью (колонки game_rules, head 043_gathering_ingredient, navData как единый источник, DOMPurify в RuleOverlay); четыре уточнения: миграции лежат в app/alembic/versions, nginx менять не нужно (location /rules/ со слешем + try_files на проде уже всё покрывают), crud.create_rule молча теряет незаявленные поля, photo-service не затронут
[LOG] 2026-09-20 14:50 — Architect: выбран ENUM, а не VARCHAR — таблица крошечная, набор значений закрыт, в этом же сервисе есть прецедент gathering_nodes.category с parity-тестом; индекс намеренно не добавляем, чтобы не плодить риск при откате
[LOG] 2026-09-20 15:05 — Architect: откат миграции сделан безусловным DROP COLUMN (fail-fast как в 043 здесь сломал бы сам откат, как только админ положит правило в технобук)
[LOG] 2026-09-20 15:20 — Architect: спроектировано 7 задач, 4 изменённых API-контракта (list с фильтром, create, update, read); задачи 3-5 разведены по файлам, чтобы три фронтенд-агента шли параллельно и не конфликтовали
[LOG] 2026-09-20 15:25 — Architect: отдельно зафиксировано, что визуал не полируем (просьба пользователя) — это вынесено в критерии приёмки каждой фронтенд-задачи и в чек-лист ревьюера
[LOG] 2026-09-20 15:40 — PM: исправлена ложная посылка разведки и архитектора — визард создания персонажа НЕ теряет состояние, он автосохраняется в localStorage (useCharacterDraft.ts, подключён на CreateCharacterPage.tsx:192, восстановление на :137). Комментарий на :82-84 относится только к kitPreview. Ссылка «правилами» в новой вкладке остаётся, но как удобство, а не починка бага: ISSUES.md не трогаем, в коммите про потерю состояния не пишем. Поправлены разделы 1, 2, 3.0, 3.5, задача T5 и критерии приёмки
[LOG] 2026-09-20 16:10 — Frontend Dev: задача T2 завершена — создан src/constants/guideSections.ts (тип GuideSection, GuideSectionMeta, GUIDE_SECTIONS с русскими названиями, guard isGuideSection) и расширен src/api/rules.ts (section в GameRule/Create/Update, fetchRules(section?) шлёт ?section= только при переданном аргументе). Слаги совпадают с ENUM БД: site/roleplay/technobook. npx tsc --noEmit и npm run build прошли в контейнере frontend без ошибок
[LOG] 2026-09-20 16:20 — Backend Dev: T1 завершена, изменено 5 файлов + 1 новый. game_rules.section (ENUM site/roleplay/technobook, NOT NULL, server_default 'site', после title), миграция 044_game_rule_section (один ADD COLUMN, откат — безусловный DROP COLUMN), RuleSection в схемах, необязательный фильтр в get_all_rules, section явно передан в create_rule (иначе молча терялся бы, как image_url). py_compile прошёл на всех файлах; tests/test_rules.py — 28 passed (пришлось добавить section в фикстуру _make_rule, иначе MagicMock ломал валидацию ответа); остальные 36 падений в test_feat171_predicate_parity.py воспроизводятся и без моих правок
[LOG] 2026-09-20 16:35 — Frontend Dev: T5 завершена — navData.ts: «ПРАВИЛА» /rules → «РУКОВОДСТВО» /guide, «Технобук» убран из мегаменю НОВОСТИ (остались Обновления / Анонсы / Ивенты), одна правка покрывает и десктопный хедер, и мобильный аккордеон; HomePage.tsx: «Обучение» /learning → /guide/technobook («Консультант» и теги слайдера не тронуты); CreateCharacterPage.tsx: ссылка «правилами» стала настоящим якорем href="/guide" target="_blank" rel="noopener noreferrer" без onClick (удобство, не починка бага — черновик визарда и так автосохраняется), неиспользуемый импорт Link удалён. npx tsc --noEmit и npm run build прошли в контейнере frontend без ошибок
[LOG] 2026-09-20 16:40 — Frontend Dev: задача T3 завершена — в RuleForm.tsx добавлен селектор «Раздел» (options из GUIDE_SECTIONS, значение по умолчанию rule?.section ?? 'site'), section уходит в payload И при создании, И при редактировании — то есть уже написанные правила можно переложить в другой раздел. В RuleList.tsx добавлена колонка «Раздел» с русским названием и фильтр «Все разделы» над таблицей (клиентский, по уже загруженному списку); пустая выборка показывает спокойное «Нет правил в этом разделе» без ошибок и тостов. Таблица обёрнута в overflow-x-auto для 360px. Визуал не трогал: только существующие классы input-underline / btn-blue / gray-bg, новых стилей и SCSS нет. npx tsc --noEmit и npm run build прошли в контейнере frontend
[LOG] 2026-09-20 17:05 — Frontend Dev: задача T4 завершена — сетка карточек дословно вынесена из RulesPage.tsx в RulesPage/RulesGrid.tsx (props rules/onSelect, та же motion-лесенка и те же классы), созданы GuidePage/GuidePage.tsx (три карточки-ссылки из GUIDE_SECTIONS, статика без запросов) и GuidePage/GuideSectionPage.tsx (useParams + isGuideSection, невалидный слаг → Navigate на /guide, fetchRules(section), загрузка и ошибка с русским текстом + toast.error, пустой раздел — спокойное «В этом разделе пока нет материалов», это успех, а не ветка ошибки). В App.tsx добавлены маршруты /guide и /guide/:section, старый /rules стал редиректом на /guide ради закладок, импорт RulesPage убран, сам RulesPage.tsx удалён. RuleOverlay.tsx не трогал — DOMPurify в нём как был, второго санитайзера нет. Визуал не полировал: только перенос структуры и существующие классы дизайн-системы. npx tsc --noEmit и npm run build прошли в контейнере frontend без ошибок
[LOG] 2026-09-20 17:25 — QA: задача T6 завершена — новый файл tests/test_rule_sections.py, 55 тестов. Три слоя: (1) parity в стиле TestMigration043 — ORM ENUM ↔ SECTIONS миграции ↔ Pydantic Literal обязаны совпадать, плюс цепочка ревизий (044 — единственный потомок 043, id ≤ 32), один ALTER без отдельного UPDATE-прохода и безусловный DROP COLUMN на откате (проверено, что op.get_bind не вызывается, то есть fail-fast-защиты нет); (2) crud на реальном aiosqlite — отдельная регрессия на create_rule (раздел реально доезжает до БД, а не теряется молча, как image_url), строка, вставленная без section, читается как 'site', фильтр отдаёт только свой раздел, запрос без параметра отдаёт всё в порядке sort_order ASC, id ASC, update переносит правило в другой раздел и без section не трогает его; (3) маршрут GET /rules/list — параметр прокидывается в crud, невалидный раздел (включая регистр, пустую строку и инъекции) → 422 до обращения к БД, чтение осталось публичным, записи по-прежнему требуют rules:create / rules:update. Прогон в контейнере locations-service: свой файл 55 passed, весь набор 1499 passed, 0 failed (базовая линия была 1444) — регрессий нет
[LOG] 2026-09-20 17:40 — Reviewer: начал проверку T7 — читаю карточку целиком и диффы всех шести задач
[LOG] 2026-09-20 17:55 — Reviewer: автоматические проверки зелёные — tsc --noEmit и npm run build в контейнере frontend, py_compile на пяти изменённых python-файлах, pytest tests/ --asyncio-mode=auto = 1499 passed / 0 failed, свой файл test_rule_sections.py = 55 passed, docker compose config без ошибок
[LOG] 2026-09-20 18:10 — Reviewer: живая проверка через curl (chrome-devtools в этой сессии недоступен) — миграция доехала (alembic_version_locations = 044_game_rule_section), колонка section ENUM NOT NULL DEFAULT 'site', все 4 существующих правила стали «site»; /rules/list без параметра отдаёт все 4 в прежнем порядке, ?section=technobook — пустой список 200, ?section=nonsense — 422; создание правила с разделом «technobook» реально сохраняет раздел, PUT со section переносит правило, PUT без section его не трогает, без токена — 401. Временное тестовое правило удалено, база возвращена в исходное состояние
[LOG] 2026-09-20 18:20 — Reviewer: проверка границ пройдена — визуал не полировали (RulesGrid перенесён дословно, карточки «Руководства» собраны из существующих классов), RuleOverlay не тронут, «Консультант» остался мёртвой ссылкой, теги слайдера на месте, nginx / compose / photo-service / RBAC не тронуты, ISSUES.md по ссылке при создании персонажа никто не правил и как починку бага её не описывал. Новых SCSS нет, React.FC нет, все новые файлы .tsx/.ts, адаптивность от 360px есть, ошибки API видны пользователю по-русски
[LOG] 2026-09-20 18:25 — Reviewer: обнаружен баг, добавлен в ISSUES.md (MEDIUM) — прямой заход на /rules отдаёт 404: nginx сам делает 301 на /rules/ для проксируемого блока, и SPA-редирект на /guide срабатывает только при навигации внутри приложения. Баг существовал и до фичи (старая страница правил была недостижима по закладке так же), это не регрессия, но утверждение архитектора из §3.0 про «/rules падает в location /» неверно, и обещание про закладки фактически не выполняется. Правка требует изменения nginx, которое фиче было прямо запрещено — вынесено отдельной задачей
[LOG] 2026-09-20 18:30 — Reviewer: проверка завершена, результат PASS (два незакрывающих замечания зафиксированы в разделе 5)
[LOG] 2026-09-20 18:45 — PM: перепроверил замечание ревьюера про /rules — подтвердилось (301 на /rules/ → 404 с бэкенда). Посылка архитектора в §3.0 п.2 была неверной, а «закладки не ломаем» — прямое требование пользователя из этой же задачи, поэтому починил здесь, а не отдельной задачей: в nginx.conf и nginx.prod.conf добавлены точные блоки `location = /rules` и `location = /rules/` с `return 301 /guide` перед префиксным `/rules/`. Точное совпадение приоритетнее префикса, API правил не затронут. Проверено вживую после пересборки шлюза: /rules и /rules/ → 301 /guide, /rules/list → 200 (4 правила), /rules/list?section=site → 200 (4). §3.0 п.2 помечен как ошибочный, запись в ISSUES.md закрыта, раздел 7 обновлён
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

**Раздел «Руководство» с тремя сводами правил готов и работает.**

- **Правила теперь делятся на разделы.** У правила появилось поле «Раздел» с тремя значениями: «Правила сайта», «Правила ролевой», «Технобук». Все 4 уже написанных правила автоматически попали в «Правила сайта» и остались доступны — ничего не потерялось.
- **Админка умеет раскладывать правила.** Селектор раздела есть и при создании правила, и при редактировании уже существующего — то есть написанное раньше можно разложить по сводам вручную, как и планировалось. В списке правил появилась колонка «Раздел» и фильтр «Все разделы» над таблицей.
- **Новые страницы.** `/guide` — выбор из трёх разделов, `/guide/site`, `/guide/roleplay`, `/guide/technobook` — списки правил внутри свода. Пустой раздел (технобук пока пуст) показывает спокойное «В этом разделе пока нет материалов», а не ошибку. Неправильный адрес вроде `/guide/что-угодно` молча возвращает на выбор разделов.
- **Навигация.** В верхнем меню «ПРАВИЛА» стало «РУКОВОДСТВО» и ведёт на `/guide` (и на десктопе, и в мобильном аккордеоне). «Технобук» убран из мегаменю НОВОСТИ — там остались Обновления, Анонсы, Ивенты. На главной «Обучение» ведёт на технобук. «Консультант» намеренно оставлен как есть.
- **При создании персонажа** ссылка «правилами» теперь открывает руководство в новой вкладке настоящей ссылкой (работает средний клик и «копировать адрес»). Анкета при этом и так не терялась — визард автосохраняется; новая вкладка просто избавляет от лишнего возврата.
- **Старый адрес `/rules`** внутри сайта перекидывает на `/guide`.

### Как проверено

Автоматика: сборка и типы фронтенда зелёные, весь набор тестов locations-service — **1499 прошли, 0 упали** (добавлено 55 новых проверок специально под разделы). Живая проверка через curl: миграция применилась сама при старте контейнера, старые правила стали «Правилами сайта», фильтр по разделу работает, несуществующий раздел даёт понятную ошибку 422, создание и перенос правила между разделами реально сохраняются в базе, без авторизации записать ничего нельзя. Ни одной 500-й.

### Что осталось за рамками

1. **Вид разделов не полировали** — по вашей просьбе. Сейчас это структура и навигация на существующих стилях; переделаем внешний вид отдельной задачей, когда дойдут руки.
2. **Раскладывание правил по сводам — за вами.** Сейчас все 4 правила лежат в «Правилах сайта»; перенести нужное в «Правила ролевой» или «Технобук» можно через админку (Правила → Редактировать → Раздел).
3. **Закладки на `/rules` — починены здесь же.** Ревью нашло, что прямой заход по старому адресу отдавал 404: nginx уводил его на бэкенд, не доводя до сайта (внутри сайта переход при этом работал). Баг был и до задачи, но обещание «старые закладки продолжают работать» — ваше требование из этой же задачи, поэтому починил: в оба nginx-конфига добавлены точные правила для `/rules` и `/rules/`, оба ведут на `/guide`. API правил не затронут. Проверено вживую после пересборки шлюза; запись в `ISSUES.md` закрыта.

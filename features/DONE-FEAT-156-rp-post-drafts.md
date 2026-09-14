# FEAT-156: Черновики ролевых постов

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-13 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас текст ролевого поста живёт только в памяти React-компонента. При любой ошибке отправки
(не соседняя локация, нехватка выносливости, кулдаун перехода, пост короче 300 символов, 500-я,
обрыв сети) форма ведёт себя как при успехе: очищает поле и перемонтирует редактор TipTap.
Текст уничтожается безвозвратно — Ctrl+Z уже нечего отменять. То же самое происходит при
закрытии вкладки, обновлении страницы или случайном переходе по ссылке.

Живой инцидент: игрок писал пост за персонажа Лоен (id 764, стоял в локации 294 «Бар "Три Галки"»)
в локацию 1034 «Воронья Церковь». Локации не соседние, бэкенд вернул 400, фронтенд стёр текст.
Потеряно ~2 часа работы. Восстановление невозможно — подтверждено проверкой прод-БД и логов
(см. раздел 2).

Делаем систему черновиков на сервере, чтобы текст нельзя было потерять по ошибке пользователя.

### Бизнес-правила
- Черновик привязан к паре **персонаж + локация**. У каждого персонажа в каждой локации свой черновик.
- Автосохранение по ходу набора (с debounce). Возврат в локацию восстанавливает текст в поле ввода.
- Хранится до **10** последних текстов на персонажа — как недописанных (черновики), так и
  дописанных (уже отправленных постов).
- Черновики живут бессрочно, пока пользователь их не удалит.
- Успешная отправка поста очищает поле ввода, но текст остаётся в истории как «дописанный».
- При превышении лимита в 10 вытесняется самый старый по времени последнего изменения.
- Есть явная кнопка очистки текущего черновика.
- Игрок видит и меняет только черновики **своих** персонажей.

### UX / Пользовательский сценарий
1. Игрок пишет пост в локации — текст автоматически уходит в черновик на сервере.
2. Игрок закрывает вкладку / ловит ошибку отправки / обновляет страницу / уходит на карту мира.
3. Возвращается в локацию — текст на месте, в поле ввода.
4. В поле ввода есть вкладка «Черновики». По нажатию открывается список ранее написанных
   текстов (дописанных и недописанных) с превью и датой.
5. Игрок выбирает любой из них — текст подставляется в поле ввода.

### Edge Cases
- В поле уже есть текст, игрок выбирает черновик из списка → спросить подтверждение замены.
- Игрок пишет с двух устройств одновременно → выигрывает последнее сохранение (last-write-wins).
- Персонаж удалён → черновики удаляются каскадно. При удалении персонажа character-service
  вызывает admin-эндпоинт очистки в locations-service — тот же graceful-паттерн, что уже
  применяется для инвентаря, навыков и характеристик. Сбой очистки не отменяет удаление
  персонажа (см. 3.12).
- Локация удалена → черновик не должен ломать страницу локации.
- Текст пустой → пустой черновик не создаём и не храним.
- Пост отправлен успешно → поле очищается, текст остаётся в истории как «дописанный».
- Сервер черновиков недоступен → игрок должен продолжать писать без блокировки UI, ошибка
  автосохранения показывается ненавязчиво, но заметно.
- Посты от NPC (`/locations/posts/as-npc`) → тот же баг с потерей текста, тоже нужно закрыть.

### Вопросы к пользователю
- [x] Черновик на локацию или общий? → **Отдельный на локацию**
- [x] Привязка к персонажу или аккаунту? → **К персонажу**
- [x] Срок хранения? → **Бессрочно, пока не удалят**
- [x] Локально или на сервере? → **На сервере, до 10 текстов, вкладка в поле ввода со списком ранее написанных текстов (дописанных и недописанных)**

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Pre-filled by PM from the initial read-only investigation. Architect must verify and extend.

### Root cause of the data loss (two independent bugs)
1. `services/frontend/app-chaldea/src/components/pages/LocationPage/LocationPage.tsx:410-416`
   — `handleSubmitPost` catches every error, shows `toast.error(...)` and **never rethrows**.
   The child therefore cannot distinguish success from failure. Same defect in
   `handleSubmitNpcPost` (`:434-440`).
2. `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCreateForm.tsx:135-144`
   — clear-on-success (`setContent('')` at `:138`, `setEditorKey(k => k + 1)` at `:139`) runs
   unconditionally because the awaited promise always resolves. The `editorKey` bump remounts
   TipTap, destroying the in-memory document as well.

### Post creation flow
- Editor: `WysiwygEditor` (TipTap) — `src/components/CommonComponents/WysiwygEditor/WysiwygEditor.tsx:330` (`useEditor`), `onUpdate` at `:355`. Rendered from `PostCreateForm.tsx:345-350`.
- Form state: plain `useState` — `PostCreateForm.tsx:63` (`content`), `:64` (`submitting`), `:66` (`editorKey`), `:70` (`selectedGates`). No Redux, no persistence.
- Submit call: `axios.post` to `${BASE_URL}/locations/${locationId}/move_and_post` with body `{ character_id, location_id, content, gates }` — `LocationPage.tsx:392-397`.
- NPC path: `axios.post` to `${BASE_URL}/locations/posts/as-npc` with body `{ npc_id, location_id, content }` — `LocationPage.tsx:427-431`.
- Styling: Tailwind (project tokens `btn-blue`, `rounded-card`, `bg-site-bg`). No SCSS in these files. Both files already `.tsx`.
- Error display: `react-hot-toast` only (`LocationPage.tsx:411-415`, `PostCreateForm.tsx:131`, `:153`).

### Backend
- Service: `locations-service` (port 8006), async SQLAlchemy (aiomysql), Alembic present (`alembic_version_locations`).
- `POST /locations/{destination_location_id}/move_and_post` — `app/main.py:973-1240` (the endpoint the UI uses).
- Validation order: ownership/battle/gathering `:995-997`, profile `:1000-1006`, travel cooldown `:1013-1029`, adjacency `:1040-1051`, stamina `:1055-1063`, min length 300 `:1066-1072`, gates `:1080`. Insert only at `:1083-1090` via `crud.create_post` (`app/crud.py:947-957`).
- The error hit in the incident: **400 `"Destination is not adjacent to current location"`** — `app/main.py:1047-1051`. **Untranslated English shown directly to the user via toast — violates the Russian user-facing strings rule.** Related: 403 `"Вы не находитесь в этой локации"` (`:691-692`), 400 `"Целевая локация не является соседней"` (`:1310-1314`, `quick_move`).
- `posts` table — `app/models.py:158-172`: `id`, `character_id`, `location_id` (BigInteger, FK `Locations.id` ON DELETE CASCADE), `content` (Text), `post_type` (String(20), default `'regular'`), `created_at`. **No status/draft/soft-delete column.**

### Recovery verdict — NOT POSSIBLE (confirmed against prod on 2026-09-13)
Prod DB is `fogdatabase` (not `mydatabase` as CLAUDE.md states). A scan of `posts` for the last
3 hours returned exactly one row — `id=145, character_id=762 (Венти), location_id=173`. Nothing
from character 764 (Лоен). The rejected post was never persisted.

| Candidate | Verdict |
|---|---|
| MySQL `posts` | No — insert strictly after validation; rejected requests never reach it. Verified on prod. |
| Draft/audit/soft-delete table | Does not exist (checked `models.py` + all alembic versions) |
| `locations-service` logs | No request-logging middleware; no `logger.*` call receives `content` |
| Nginx logs | Built-in `combined` format only — no `log_format` / `client_body_in_file_only` in `nginx.conf` / `nginx.prod.conf`; bodies never written |
| MongoDB / Redis | `locations-service` has no Mongo or Redis client at all (battle-service only) |
| RabbitMQ | Publish at `main.py:1164` happens after successful insert; payload is only the notification string |
| Browser | TipTap in-memory only, destroyed by the `editorKey` remount. No localStorage/IndexedDB draft |

### Existing pattern to reuse
- `src/components/CreateCharacterPage/useCharacterDraft.ts:155,176,200` — the only draft
  implementation in the codebase (localStorage-based, character creation). Useful structural
  template for the hook API, though this feature is server-backed.

### Risks
- New table + Alembic migration in `locations-service` (async env, `version_table='alembic_version_locations'`).
- Autosave traffic: debounce is mandatory, otherwise every keystroke hits the API.
- Ownership enforcement: `locations-service` does not verify JWT itself for most routes
  (CLAUDE.md §10.7). **[Architect correction, 2026-09-13 — this is factually
  wrong for this service: `app/auth_http.py:24` `get_current_user_via_http` validates the
  Bearer token against `user-service /users/me`, and `main.py` applies it on ~30 routes
  including `move_and_post` (`:979`). See sections 3.0 / 3.4.]** Architect must decide how ownership is enforced for draft endpoints and
  follow the pattern `move_and_post` already uses for `character_id` ownership (`main.py:995-997`).
- Prod DB name differs from the documented one (`fogdatabase` vs `mydatabase`) — worth a separate
  docs fix, not part of this feature.

---

## 3. Architecture Decision (filled by Architect — in English)

The feature splits into three independently shippable slices. **Slice A (stop
destroying the text) must ship first** — it is a two-file frontend change that
removes the data-loss bug on its own, with no backend, no migration and no
deploy coupling. Slice C (Russian errors) is a self-contained backend change.
Slice B (server-side drafts) is the full feature and builds on A.

### 3.0 Correction to Section 2

Section 2 "Risks" states that *"`locations-service` does not verify JWT itself
for most routes (CLAUDE.md §10.7)"*. **Verified and false for this service.**
`services/locations-service/app/auth_http.py:24` defines
`get_current_user_via_http`, which validates the Bearer token by calling
`user-service GET /users/me`, and `main.py` uses it on ~30 routes including
`move_and_post` (`:979`). CLAUDE.md §10.7 is stale with respect to
locations-service. No new auth mechanism is needed — see 3.4.

---

### 3.1 Slice A — clear the editor only on genuine success

Two defects, two one-file fixes:

1. `LocationPage.tsx` — `handleSubmitPost` (`:389-419`) and `handleSubmitNpcPost`
   (`:423-441`) catch, toast and **swallow**. Fix: keep the toast (the user-facing
   Russian message stays exactly where it is) and **`throw err;`** as the last
   statement of each `catch`. The callback contract changes from
   "always resolves" to "resolves on success, rejects on failure" — the type
   `(content, gates) => Promise<void>` is unchanged, so no prop-type churn.

2. `PostCreateForm.tsx` — `handleSubmit` (`:110-144`). Both branches currently run
   `setContent('')` / `setEditorKey(k => k + 1)` / `setIsEditorOpen(false)`
   unconditionally after the `await`. Fix: the reset block runs only after a
   resolved promise, and an explicit
   `catch { /* parent already toasted; keep the text */ }` is added next to the
   existing `finally { setSubmitting(false) }`. The `catch` is **required** —
   without it the now-rejecting promise becomes an unhandled rejection. The editor
   must **stay open** on failure so the text is visibly still there.

3. Third data-loss path found while designing, same file: `resetForm` (`:161-169`),
   bound to the «Отмена» button (`:396`), wipes `content` + remounts TipTap with no
   confirmation. Fix: when `!isContentEmpty(content)`, ask for confirmation before
   resetting. Use the design-system modal (`modal-overlay` / `modal-content`), not
   `window.confirm`. Slice B reuses the same confirm component for
   "overwrite the editor with a chosen draft".

Nothing else in these two files changes. Both are already `.tsx` + Tailwind, so
the TS/Tailwind migration mandates are already satisfied.

---

### 3.2 Slice B — data model

New table owned by `locations-service`.

```sql
CREATE TABLE post_drafts (
  id            BIGINT      NOT NULL AUTO_INCREMENT,
  character_id  INT         NOT NULL,
  location_id   BIGINT      NOT NULL,
  content       MEDIUMTEXT  NOT NULL,
  active        TINYINT     NULL,          -- 1 = live draft of (character, location); NULL = archived
  sent_at       TIMESTAMP   NULL,          -- NOT NULL  =>  text of a successfully posted RP post
  created_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_post_drafts_location FOREIGN KEY (location_id)
      REFERENCES Locations (id) ON DELETE CASCADE,
  UNIQUE KEY uq_post_drafts_active (character_id, location_id, active),
  KEY idx_post_drafts_char_updated (character_id, updated_at)
);
```

Design notes, each deliberate:

- **`active` is a nullable flag, not a boolean.** MySQL has no partial unique
  indexes, but it treats `NULL`s as distinct inside a unique key. So
  `UNIQUE (character_id, location_id, active)` enforces *at most one live draft
  per (character, location)* while allowing unlimited archived rows for the same
  pair. This is what makes the upsert race-safe at the DB level instead of
  relying on read-then-write in application code (the "two devices at once" edge
  case). Application code writes literally `1` or `NULL`, never `0`.
- **One column, one idea.** `active` and `sent_at` do not overlap: `active = 1`
  means "this is the text currently in the editor for that location";
  `sent_at IS NOT NULL` means "this text became a real post" (the brief's
  «дописанный»). An archived row with `sent_at IS NULL` is a draft evicted from
  the live slot but still inside the 10-item history. No contradictory pair of
  columns (the FEAT-155 lesson).
- **`MEDIUMTEXT`, not `TEXT`.** `TEXT` is 64 **KB**, and Cyrillic in `utf8mb4`
  costs 2 bytes per character plus TipTap's HTML markup — a long RP post plus
  formatting can realistically approach that ceiling, and silently truncating a
  draft would reproduce the very bug this feature exists to kill. Application
  validation caps content at **100 000 characters** with a Russian 400.
  `posts.content` is still plain `TEXT` — a pre-existing risk, **out of scope**,
  to be filed in `docs/ISSUES.md` (task T14).
- **No FK on `character_id`; cleanup is an explicit cross-service call.**
  Consistent with every other table in this service (`posts`, `action_gates`,
  `post_likes` all carry a bare `character_id`; `models.py` contains zero foreign
  keys to `characters`). The brief's cascade-on-character-deletion requirement is
  delivered the way this codebase already does it — a graceful admin cleanup call
  from character-service — rather than by introducing this service's first
  cross-service foreign key. See **3.12**.
- **`updated_at` is set explicitly in `crud`** (`datetime.now(timezone.utc)`)
  rather than via MySQL `ON UPDATE CURRENT_TIMESTAMP`, so eviction ordering is
  deterministic and testable with a mocked session.
- **Location deleted** → `ON DELETE CASCADE` removes its drafts, so the location
  page cannot break on a dangling draft (brief edge case).

#### Lifecycle

| Event | Effect |
|---|---|
| User types in location X | Upsert the row `(char, X, active=1)`; `updated_at = now`. Then evict. |
| Content becomes empty | **Delete** the live row. Empty drafts are never stored (brief edge case). |
| Post sent successfully in X | The live row for `(char, X)` is archived: `active = NULL`, `sent_at = now`, `content` overwritten with the posted content. If no live row exists (draft API was down while typing), insert an archived row directly. Then evict. |
| Explicit «Очистить черновик» | Hard-delete the live row for `(char, X)`. |
| Draft chosen from the «Черновики» list | Read-only on the server — the client inserts the text into the editor, which triggers a normal autosave into the *current* location's live slot. The source row is untouched. |
| Eviction | After any insert, while `COUNT(*) WHERE character_id = c` exceeds **10**, delete the row with the smallest `updated_at`. Bounded loop, executed inside the same transaction as the insert. |

The evictor may in principle delete another location's live draft. That is
correct and intended: it can only ever be the *least recently updated* of the
character's ten texts, so it is never the one being typed into.

**NPC posts are out of the draft model.** `POST /locations/posts/as-npc` writes
under an `npc_id`, not under a player character, and is admin-only. Autosave is
disabled while `npcMode` is on, and nothing is archived after an NPC post. NPC
mode still gets the slice-A fix (its text survives a failed send), which is what
the brief's last edge case actually asks for.

---

### 3.3 Slice B — API contract

All routes hang off the existing `router` (`APIRouter(prefix="/locations")`), so
the Nginx `location /locations/` block already routes them — **no new upstream,
no new proxy block** (only a rate-limit block, T8). Pydantic **v1** syntax
(`class Config: orm_mode = True`).

Schemas (`app/schemas.py`, appended in a `POST DRAFT SCHEMAS` section):

```python
class PostDraftSave(BaseModel):
    character_id: int
    content: str

class PostDraftRead(BaseModel):
    id: int
    character_id: int
    location_id: int
    content: str
    is_sent: bool          # sent_at IS NOT NULL
    is_active: bool        # active == 1
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class PostDraftListItem(BaseModel):
    id: int
    location_id: int
    location_name: Optional[str] = None
    preview: str           # plain text, first 180 chars, ellipsised
    char_count: int        # plain-text length
    is_sent: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

`preview` / `char_count` are computed server-side with the existing
`crud.strip_html_tags`. The list deliberately **does not** carry `content`:
ten rows × a long RP post is a wasteful payload for a panel where the user reads
one item at a time.

| # | Method & path | Auth | Body | 2xx | Errors |
|---|---|---|---|---|---|
| D1 | `GET /locations/drafts?character_id={id}` | JWT + owner | — | 200 `List[PostDraftListItem]`, ≤10, ordered `updated_at DESC` | 401, 403 «Вы можете управлять только своими персонажами», 404 «Персонаж не найден» |
| D2 | `GET /locations/drafts/{draft_id}` | JWT + owner **of the row** | — | 200 `PostDraftRead` | 401, 403, 404 «Черновик не найден» |
| D3 | `GET /locations/{location_id}/draft?character_id={id}` | JWT + owner | — | 200 `Optional[PostDraftRead]` — `null` when there is no live draft | 401, 403, 404 |
| D4 | `PUT /locations/{location_id}/draft` | JWT + owner | `PostDraftSave` | 200 `Optional[PostDraftRead]` — `null` when the content was empty and the draft was deleted | 400 «Черновик слишком длинный — максимум 100000 символов», 401, 403, 404 |
| D5 | `DELETE /locations/{location_id}/draft?character_id={id}` | JWT + owner | — | 204 (idempotent — 204 even if nothing existed) | 401, 403, 404 |
| D6 | `DELETE /locations/drafts/{draft_id}` | JWT + owner of the row | — | 204 | 401, 403, 404 «Черновик не найден» |
| **D7** | `DELETE /locations/admin/drafts/by_character/{character_id}` | JWT + `require_permission("locations:delete")` — **service-to-service**, not user-facing | — | 200 `{"detail": "...", "count": N}`; idempotent, `count: 0` when there was nothing | 401, 403 |

D7 is the character-deletion cleanup hook — see 3.12. It is deliberately **not**
ownership-scoped: the character row is being destroyed, so
`verify_character_ownership` would fail by the time anyone could call it.

`PUT` (not `POST`) on D4 because autosave is an idempotent upsert of a singleton
resource identified by `(character_id, location_id)`; retrying it is always safe.

**Route-declaration order.** `/locations/drafts` and `/locations/drafts/{draft_id}`
must be declared in `main.py` *before* any single-segment `/{location_id}`-style
route. Today no such bare route exists (only `/{location_id}/details`,
`/{location_id}/children`, `/{location_id}/posts/`, `/{location_id}/client/details`,
`/{location_id}/neighbors/`), so there is no live conflict — but declaring the
draft routes in a block ahead of them keeps it that way.

**Archive-on-send is not an endpoint.** It happens inside
`move_and_post` right after `crud.create_post` succeeds (`main.py:1090`),
by calling `crud.archive_draft_on_post(session, character_id, location_id, content)`.
Wrapped in `try/except Exception` + `logger.warning`, exactly like the adjacent
`create_action_gates` call (`:1091-1097`): **a draft-bookkeeping failure must
never fail a post that the database already accepted.** This also removes a
round-trip and a client-side failure mode from the success path.

---

### 3.4 Slice B — authorization

**Decision: reuse the existing pattern verbatim; no new mechanism.**

Every draft route declares `current_user = Depends(get_current_user_via_http)`
(`app/auth_http.py:24` — validates the Bearer token against
`user-service GET /users/me`) and then calls
`await verify_character_ownership(session, character_id, current_user.id)`
(`app/main.py:116` — reads `characters.user_id` from the shared MySQL DB and
raises 404/403). This is exactly what `move_and_post` does at `main.py:995-997`
and what ~30 other routes in this file already do.

- For D1, D3, D4, D5 the `character_id` comes from the request (query or body)
  and is checked directly.
- For D2 and D6 the row is loaded **first**, then
  `verify_character_ownership(session, row.character_id, current_user.id)` runs
  on the row's own `character_id`. A draft id belonging to another player
  therefore returns 403, never content. **Never trust a client-supplied
  `character_id` to authorise a row-addressed route.**

The pattern is sufficient — there is no draft-specific privilege, no admin path,
and no cross-character sharing in this feature. No RBAC permission rows are
needed (CLAUDE.md §7 applies to admin functionality; these are player-owned
resources gated by ownership, like gathering or post likes).

Input validation: `content` length-capped (100 000 chars) and stored verbatim.
The stored HTML is the same TipTap output already stored in `posts.content` and
is rendered by the same sanitising editor, so drafts introduce no new XSS
surface beyond what post creation already has. `character_id` / `location_id` are
typed `int` by FastAPI; all DB access goes through SQLAlchemy constructs or
bound `text()` parameters — no string interpolation.

Rate limiting: Nginx zone on `PUT /locations/{id}/draft` (T8) — see 3.5.

---

### 3.5 Slice B — autosave behaviour (client)

Requirements: never block typing, never flood the API, never lose text when the
draft API is down.

- **Debounce 2500 ms** of inactivity, with a **max-wait flush at 15 s** of
  continuous typing. Trailing edge only. Worst case ≈ 4 requests/minute per
  writer.
- **Skip unchanged content.** The hook keeps `lastSavedRef`; if the current HTML
  equals the last value that was successfully persisted, no request is made.
- **Skip empty→empty.** If the stripped content is empty and no draft is known to
  exist server-side, do nothing.
- **Flush on `visibilitychange → hidden`** and on unmount / location change.
  `navigator.sendBeacon` is deliberately **not** used: it cannot set the
  `Authorization` header the gateway requires. A hard tab kill can therefore lose
  at most the last 2.5 s of typing — closed by the local mirror below.
- **localStorage mirror (the real safety net).** Every debounce tick also writes
  `chaldea:post-draft:{characterId}:{locationId}` = `{ content, savedAt }`
  synchronously. This costs nothing, works while the server is down, and survives
  a tab close. On mount the hook reads both sources and takes the **newer by
  timestamp**; if the local copy wins it is pushed to the server on the next tick.
  Cleared on successful send and on explicit clear. Structural template:
  `src/components/CreateCharacterPage/useCharacterDraft.ts`.
- **Failure is visible but non-blocking.** Autosave is fire-and-forget. On error
  the hook exposes `saveState: 'error'` and the form renders an inline Russian
  indicator next to the character counter — `Черновик не сохранён` in
  `text-site-red` with a «Повторить» button — plus **one** `toast.error` on the
  first failure of a session (no toast storm on repeated failures). The editor is
  never disabled, the submit button is never blocked, and the local mirror keeps
  working. On success: `Черновик сохранён · HH:MM` in `text-white/40`.
- **Nginx:** `limit_req_zone $binary_remote_addr zone=draft_limit:10m rate=60r/m;`
  with `limit_req zone=draft_limit burst=20 nodelay; limit_req_status 429;` on
  `~ ^/locations/[0-9]+/draft$`. Generous on purpose — the limit exists to stop a
  broken client looping, not to throttle a writer. Per-IP (stock Nginx has no
  per-JWT keying), which is why the burst is wide: several players behind one NAT
  must not collide.

---

### 3.6 Slice B — frontend structure

No Redux. Drafts are local to the post form; the only precedent for a draft in
this codebase (`useCharacterDraft.ts`) is a plain hook, and a slice would add
global state nothing else reads (YAGNI, minimal diff).

| File | Kind | Responsibility |
|---|---|---|
| `src/types/postDrafts.ts` | new | `PostDraftRead`, `PostDraftListItem`, `PostDraftSave` TS interfaces mirroring 3.3 |
| `src/api/postDrafts.ts` | new | Typed REST client for D1–D6. Same shape as `src/api/gatheringApi.ts`; auth comes from the global axios interceptor. Errors propagate to callers. |
| `src/hooks/usePostDraft.ts` | new | Debounced autosave, localStorage mirror, restore-on-mount, `clearDraft`, `markSent`, `saveState`, `lastSavedAt`, `error`, `retry` |
| `src/components/pages/LocationPage/DraftsPanel.tsx` | new | The «Черновики» tab body |
| `src/components/pages/LocationPage/ConfirmDialog.tsx` | new | Shared confirm modal used by slice A (Отмена) and slice B (overwrite / delete) |
| `PostCreateForm.tsx` | modify | Tab header, wiring, save indicator, clear button |
| `LocationPage.tsx` | modify | Rethrow (slice A) only |

**Tabs.** Inside the expanded editor, above `WysiwygEditor`, a two-item switch
«Пост» | «Черновики» built from the design system's chip classes —
`chip-outline rounded-full px-4 py-1.5 text-xs font-medium` and
`chip-outline-active` for the selected one (DESIGN-SYSTEM §4 "Chip Outline").
No new SCSS, no new component class needed. The «Черновики» chip carries a
count badge when the history is non-empty.

**DraftsPanel.** Vertical list, `gold-scrollbar overflow-y-auto max-h-[55vh]`.
Each row: location name + date (`text-white/40 text-[11px]`), a 2-line clamped
preview, a badge — «Отправлен» (`text-stat-energy`) or «Черновик»
(`text-site-blue`) — and two actions, «Вставить» (`btn-blue !py-1.5 !px-4 !text-xs`)
and «Удалить» (ghost button, `hover:text-site-red`). Empty state:
«Сохранённых текстов пока нет». Load error: Russian message + «Повторить».
Delete confirms through the same `ConfirmDialog`.

**Overwrite confirmation.** «Вставить» on a non-empty editor opens
`ConfirmDialog` («Заменить текст в поле ввода? Текущий текст останется в
черновиках.»). On confirm the text is inserted via `setContent(...)` +
`setEditorKey(k => k + 1)` — the TipTap remount is the correct tool *here*
(that is how `handleApplySuggestion` at `:155-160` already replaces content);
it was only wrong on the error path.

**Responsiveness (360px+).** Tabs wrap; the panel is a single column with
`flex-col` action buttons below `sm:`; previews use `line-clamp-2 break-words`;
the modal uses `w-[min(92vw,480px)]`. No horizontal scroll on the page body.

---

### 3.7 Slice C — Russian user-facing errors

`move_and_post` (`main.py:973-1240`) leaks six English strings straight into the
player's toast. All six are user-facing (`HTTPException.detail` is rendered by
`LocationPage.tsx:411-414`).

| Line | Current | Replacement |
|---|---|---|
| 1004 | `Character profile not found` | `Профиль персонажа не найден` |
| 1050 | `Destination is not adjacent to current location` | `Целевая локация не является соседней` |
| 1059 | `Character attributes not found` | `Характеристики персонажа не найдены` |
| 1063 | `Not enough stamina to move` | `Недостаточно выносливости для перехода` |
| 1107 | `Failed to update character location` | `Не удалось обновить локацию персонажа` |
| 1122 | `Failed to deduct stamina for movement` | `Не удалось списать выносливость за переход` |

Line 1050 intentionally reuses the exact wording already used by `quick_move`
(`:1310-1314`) so the same situation reads the same way in both flows.

**Audited and already correct — do not touch:** `create_post_as_npc`
(`:1434-1466`: «NPC не найден», «Локация не найдена»), `_validate_intent_post`
(`:632-652`), `POST /locations/posts/` (`:676+`), `verify_character_ownership`
(`:116-127`), the travel-cooldown message (`:1027`), the minimum-length message
(`:1069`).

No test in `services/locations-service/app/tests/` asserts any of the six English
strings (verified by grep), and no frontend code matches on them, so the change
is safe. It is nonetheless a user-visible contract change — QA covers it (T4).

---

### 3.8 Migration & rollback

- `services/locations-service/app/alembic/versions/036_add_post_drafts.py`,
  `revision = '036_add_post_drafts'`, `down_revision = '035_origin_drop_map_link'`.
- **Hand-written**, not autogenerated — every migration in this service is
  hand-written, and `env.py` is async (autogenerate needs a live DB connection).
  `version_table='alembic_version_locations'` is already configured in
  `env.py:62,73` — nothing to change there.
- `upgrade()`: `op.create_table('post_drafts', ...)` with the FK to `Locations.id`
  `ondelete='CASCADE'`, `op.create_index('uq_post_drafts_active', unique=True)`,
  `op.create_index('idx_post_drafts_char_updated')`.
  `content` as `sa.dialects.mysql.MEDIUMTEXT()`.
- `downgrade()`: drop the two indexes, drop the table. **Lossless for pre-existing
  data** — nothing outside the new table is touched. Rolling back only discards
  drafts written after the deploy.
- The model must be added to `models.py` so `target_metadata` stays in sync with
  the DB (a future autogenerate would otherwise want to drop the table).
- Auto-migration already runs from the service Dockerfile CMD
  (`alembic upgrade head && uvicorn …`) — no infrastructure change.

### 3.9 Cross-service impact

**None.** No existing request or response shape changes; six error *strings*
change but no status code does. `post_drafts` is read and written only by
`locations-service`. No new inter-service HTTP call, no RabbitMQ message, no
Celery task, no RBAC permission row, no new env var, no Docker change. The only
infrastructure delta is the Nginx rate-limit block (T8), which must be applied to
**both** `nginx.conf` and `nginx.prod.conf` per CLAUDE.md §8.1.

### 3.10 Data flow (autosave → restore → send)

```
typing → PostCreateForm.setContent
           ├─ localStorage[chaldea:post-draft:{char}:{loc}]      (synchronous, always)
           └─ usePostDraft debounce 2.5s / max 15s
                 └─ PUT /locations/{loc}/draft {character_id, content}
                       → Nginx (draft_limit 60r/m, burst 20)
                       → locations-service  get_current_user_via_http → user-service /users/me
                                            verify_character_ownership (SQL on characters)
                                            crud.upsert_draft  → UPSERT post_drafts (active=1)
                                            crud.evict_drafts  → keep newest 10 by updated_at

reopen location → GET /locations/{loc}/draft?character_id=…  ─┐
                  localStorage read                          ─┴─ newer timestamp wins → editor

send post → POST /locations/{loc}/move_and_post
              → validations … → crud.create_post
              → crud.archive_draft_on_post (active=NULL, sent_at=now)   [try/except, non-fatal]
            success → PostCreateForm clears editor + clears localStorage
            failure → toast (Russian) + text stays in the editor and in the draft
```

### 3.11 Questions raised — all resolved by the user (2026-09-13)

- **Q1 — cascade on character deletion. RESOLVED: real cleanup, not orphan rows.**
  The user wants the drafts actually removed. Designed in **3.12**: an admin
  cleanup endpoint (D7) on locations-service, called by character-service inside
  the fan-out that already exists in `delete_character`. The earlier
  "orphan rows are acceptable" assumption is **withdrawn**. Tasks T16–T18.
- **Q2 — the 10-item limit is per character, not per account. RESOLVED:
  confirmed as designed.** A player with five characters may hold up to 50 texts.
  No change.
- **Q3 — the «Черновики» list spans all locations. RESOLVED: confirmed as
  designed.** The list shows all of the character's texts with the location name
  on each row (D1 needs no `location_id` filter). No change.

### 3.12 Cascade cleanup when a character is deleted

#### How character deletion works today (verified)

`DELETE /characters/{character_id}` — `services/character-service/app/main.py:1121-1218`,
guarded by `require_permission("characters:delete")`. It is a **hard delete**
(`db.delete(character)` at `:1210`), not a soft flag. Before dropping the row it
already fans out to the other owners of the character's data, and **a precedent
for exactly this problem already exists**:

| Step | Call | Owner |
|---|---|---|
| 1 (`:1138-1148`) | `DELETE {INVENTORY_SERVICE_URL}{cid}/all` | inventory-service `main.py:832`, `require_permission("items:delete")` |
| 2 (`:1151-1162`) | `DELETE {SKILLS_SERVICE_URL}admin/character_skills/by_character/{cid}` | skills-service `main.py:309`, `require_permission("skills:delete")` |
| 3 (`:1165-1176`) | `DELETE {ATTRIBUTES_SERVICE_URL}{cid}` | character-attributes-service |
| 4 (`:1180-1206`) | `DELETE /users/user_characters/{uid}/{cid}` + `POST /users/{uid}/clear_current_character` | user-service |
| 5 (`:1209-1216`) | `db.delete(character)` | character-service |

Every one of steps 1–4 has the same shape: an `httpx.AsyncClient(timeout=10.0)`
call, the **caller's Bearer token forwarded** in `headers`, the whole block
wrapped in `try/except Exception` with `logger.warning` on both a non-200 and an
exception — **failure is logged and ignored, never propagated**. Each target is
an admin cleanup endpoint on the service that owns the table, keyed by
`character_id`, idempotent, returning a count.

**locations-service is absent from this fan-out.** `posts`, `post_likes` and
`action_gates` rows of a deleted character are therefore already orphaned today —
a pre-existing gap, filed to `docs/ISSUES.md` in T14, **not** fixed here (see
"Why drafts only" below).

#### Mechanism chosen: follow the existing precedent exactly

**An admin cleanup endpoint on locations-service (D7), called by
character-service as a new step 4.5 in the existing fan-out.**

Justification against the alternatives:

- **Cross-service FK (`character_id → characters.id ON DELETE CASCADE`)** —
  rejected. It would be the first foreign key from locations-service into a table
  owned by another service, and the shared-database layout (CLAUDE.md §10.5) is
  already the system's weakest seam; a schema-level cascade makes the coupling
  permanent and invisible, and it would be the only one of its kind in the
  codebase. It also cannot be applied consistently — the sibling services all
  solved this with HTTP, not FKs.
- **RabbitMQ** — rejected. The only active queues are `user_registration` and
  `general_notifications` (CLAUDE.md §2); there is no character-lifecycle event
  stream to hook into, and locations-service has **no** consumer at all. Building
  one for a single cleanup would be a new subsystem and a second, divergent
  pattern for a problem this codebase has already solved four times over.
- **HTTP admin cleanup endpoint** — chosen. It is the established pattern, the
  dependency edge `character-service → locations-service` already exists
  (CLAUDE.md §2), and `LOCATIONS_SERVICE_URL` is **already defined** in
  `services/character-service/app/config.py:13`, so there is **no new env var, no
  new compose entry, no new Docker or Nginx change**.

#### Contract and placement

D7 = `DELETE /locations/admin/drafts/by_character/{character_id}` →
`200 {"detail": "...", "count": N}`, idempotent (`count: 0` when nothing matched).
Mirrors the skills-service endpoint's shape (`main.py:309-316`) down to the path
segment naming (`admin/…/by_character/{id}`) and the counted response.

The call is inserted in `delete_character` as **step 4.5**, after the user-service
cleanup and **before** `db.delete(character)` at `:1209`, using the identical
block shape as steps 1–4:

```
try:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(
            f"{settings.LOCATIONS_SERVICE_URL}/locations/admin/drafts/by_character/{character_id}",
            headers=headers,
        )
        ... log info on 200, logger.warning otherwise
except Exception as e:
    logger.warning(...)
```

**Draft cleanup can never fail the character deletion** — same defensive reasoning
as archive-on-send (3.3): the `try/except Exception` + `logger.warning` swallow is
mandatory, and it is what every sibling step already does. A dead or slow
locations-service must not leave a half-deleted character. The 10-second timeout
matches steps 1–4.

#### Authorization for a service-to-service call

This is the one place in the feature where ownership checking is impossible: the
character row is about to vanish (and in the reverse-order failure case may
already be gone), so `verify_character_ownership` — which 404s on a missing
character — cannot guard it.

**Decision: RBAC permission, not ownership.** D7 declares
`Depends(require_permission("locations:delete"))` from
`services/locations-service/app/auth_http.py:75`. The caller's Bearer token is
forwarded by character-service, so the effective authorisation is "whoever was
allowed to delete the character". This is precisely how inventory-service
(`items:delete`) and skills-service (`skills:delete`) guard their equivalents.

`locations:delete` **already exists** in the RBAC registry — it guards ten
routes in `main.py` (`:230`, `:284`, `:362`, `:457`, `:565`, `:1510`, `:1560`,
`:3020`, `:3065`, …) and is consumed by the frontend at
`WorldMapPage.tsx:57`. So **no new `permissions` row and no RBAC Alembic
migration are required** (CLAUDE.md §7 satisfied — the permission is registered
already, and Admin holds it automatically).

There is no unauthenticated internal path: the endpoint is reachable through the
gateway like any other `/locations/` route, so it must be, and is, token-guarded.

#### Why drafts only, and not posts

D7 deletes rows from `post_drafts` and nothing else. Deleting the character's
`posts` would tear holes in the shared RP history that other players' posts in the
same location read as narrative context — a destructive, irreversible change to
content that is not the deleted character's private property. Drafts are private
scratch space and carry no such dependency. Widening the cleanup to `posts` /
`post_likes` / `action_gates` is a product decision, filed as an ISSUES entry
(T14), not made here.

### 3.13 «Отмена» retires the draft instead of destroying it (user ruling, 2026-09-13)

**Ruling.** «Отмена» clears the input field but the text must stay retrievable
from the «Черновики» list. This supersedes the behaviour shipped in T13, where
`resetForm` calls `scheduleSave('')` (`PostCreateForm.tsx:283`) and the empty
upsert hard-deletes the live row (`crud.upsert_draft` → `delete_active_draft`).

**Why "just don't delete it" is wrong.** Leaving the row in the **live** slot
keeps it visible in the list, but the next post written in that same location
upserts over that very row (`uq_post_drafts_active` permits exactly one live row
per `(character_id, location_id)`) and the text is gone — the precise loss this
feature exists to prevent. Cancelling must therefore **free the live slot** so the
next post starts a fresh row, while the text survives as an archived one.

#### Mechanism: one optional query parameter on D5

`DELETE /locations/{location_id}/draft?character_id={id}&keep_in_history={bool}`
— `keep_in_history` defaults to `false`, which is exactly today's behaviour.

- `false` (default) — «Очистить черновик». Hard-deletes the row, as now.
- `true` — «Отмена». Frees the live slot and keeps the row: `active = NULL`,
  `sent_at` **stays NULL**, `content` untouched, `updated_at = now`.

Both still return **204** and stay idempotent.

Justification, held to the same standard as the rest of this design:

- **A new endpoint was rejected.** It would duplicate D5's entire preamble —
  `get_current_user_via_http`, `verify_character_ownership`, the idempotent
  no-op — to change one bit of what happens to a row. The addressed resource is
  identical: *the live draft of this location*.
- **`DELETE` with `keep_in_history=true` is not a contradiction.** The resource
  `/locations/{id}/draft` **is** the live slot, and it genuinely ceases to exist
  in both cases. The parameter governs only the text's afterlife.
- **Default-false keeps it backwards compatible.** The shipped
  «Очистить черновик» button, `api/postDrafts.ts:66` and the existing T9 tests
  all keep working with no change.

#### CRUD

New `crud.archive_active_draft(session, character_id, location_id) -> int`:
load the live row, set `active = None` and `updated_at = now`, leave `sent_at`
and `content` alone, then `evict_drafts` + commit. Returns the number of rows
retired (0 when there was no live draft — nothing to keep).

`archive_draft_on_post` is **not** refactored to share code with it. The overlap
is about four lines, it is implemented, tested and on the critical path of post
creation, and the two differ in three ways (sent_at, content overwrite, and
create-if-missing). Minimal diff beats a DRY refactor of working code. The one
thing they must keep in common is calling `evict_drafts` before the commit.

#### What the flags mean for a cancelled draft — no third state

| Field | Value | Rendered as |
|---|---|---|
| `active` | `NULL` | `is_active: false` |
| `sent_at` | `NULL` | `is_sent: false` |
| badge | — | **«Черновик»** |

`DraftsPanel.tsx:164-167` renders «Отправлен» when `is_sent`, «Черновик`»
otherwise. **That still reads correctly and needs no change.** A cancelled text
*is* an unfinished draft — the badge is the truth, not an approximation. It is
indistinguishable from a draft that aged out of the live slot by eviction, which
is also correct: from the writer's side both are "a text I wrote and didn't
send".

So this addition needs **no migration, no schema change, no new column, no new
Pydantic field and no `DraftsPanel` edit.** A third state («Отменён») was
considered and rejected: it would buy a distinction the user never asked to see,
at the cost of a column, a migration and a third badge.

#### Eviction still behaves

`archive_active_draft` sets `updated_at = now` and calls `evict_drafts` like
every other writer, so a cancelled draft is simply one of the ≤10 and ages out
by the same rule. Bumping `updated_at` is deliberate — the writer just
interacted with that text, so it sorts to the top of the list and is the last
of the ten to be evicted, not the first.

#### It must not come back in the editor — three conditions, all required

1. **Server.** `crud.get_active_draft` filters on `active == DRAFT_ACTIVE`, so
   D3 returns `null` for that location on the next visit and the field opens
   empty. Satisfied by `active = NULL` alone.
2. **The `localStorage` mirror must be dropped.** This is the real trap: the
   hook restores whichever of server/local is newer (3.5), so an orphaned local
   copy would resurrect the cancelled text and hand it straight back to the
   editor, defeating the whole change. `usePostDraft.markSent` (`:459-474`)
   already performs exactly the right local bookkeeping — cancel timers, bump
   `saveSeqRef` to invalidate in-flight saves, clear `pendingRef` /
   `lastSavedRef`, `removeLocalMirror`, reset `saveState` / `lastSavedAt` /
   `error`. The new `archiveDraft()` is that same bookkeeping plus the one
   server call.
3. **The debounced empty save must be removed, not merely ignored.**
   `resetForm`'s `scheduleSave('')` has to go: if it survives, a trailing
   debounced empty upsert fires *after* the archive call and hard-deletes the
   row we just retired. `archiveDraft()` cancelling timers and bumping
   `saveSeqRef` before its request closes the race from the other side too.

#### Copy change (the dialog currently promises the opposite)

`PostCreateForm.tsx:657-666` tells the user «Написанный текст будет удалён без
возможности восстановления» with a `danger` confirm labelled «Удалить текст».
That is now false. New copy: title «Отменить пост?», message «Текст останется в
черновиках — его можно вернуть из вкладки «Черновики».», confirm «Убрать из
поля», cancel «Продолжить писать», and **`danger` removed** — the action is no
longer destructive. «Очистить черновик» keeps its `danger` styling and its
wording, because that one really does destroy the text.

#### Follow-up edits to already-completed tasks

| Shipped task | What this supersedes |
|---|---|
| T6 (crud) | adds `archive_active_draft`; `upsert_draft` / `archive_draft_on_post` unchanged — **T19** |
| T7 (endpoints) | D5 gains the `keep_in_history` query parameter — **T19** |
| T13 (frontend) | `resetForm` archives instead of `scheduleSave('')`; new `archiveDraft` in the hook; api client gains an optional argument; cancel-dialog copy — **T20** |
| T9 (tests) | extended with the archive-on-cancel cases — **T21** |
| T12 (`DraftsPanel`) | **no change** — the two-badge logic already tells the truth |

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Shipping order.** T1–T2 (slice A) are the data-loss fix and depend on nothing —
they can be merged and deployed on their own, before anything else. T3–T4 (slice C)
are likewise independent. T5–T13, T16–T18 and T19–T21 (slice B) are the drafts
feature; T14–T15 close it out.

All paths are relative to the repo root
`D:\zdesyalyajitdudka\Chaldea`. Frontend root:
`services/frontend/app-chaldea/`. Backend root: `services/locations-service/app/`.

### Slice A — stop destroying the text (ship first, standalone)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| **T1** | Rethrow submit errors so the form can tell success from failure. In `handleSubmitPost` (`:389-419`) and `handleSubmitNpcPost` (`:423-441`), keep the existing Russian `toast.error(message)` and add `throw err;` as the final statement of each `catch`. Do not change the toast text, the success path, or the prop types. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/LocationPage/LocationPage.tsx` | — | Both handlers rethrow. `npx tsc --noEmit` and `npm run build` pass. No other behaviour in the file changes (diff ≤ ~6 lines). |
| **T2** | Clear the editor **only** on genuine success, and confirm before discarding text. (a) In `handleSubmit` (`:110-144`) move the reset block (`setContent('')`, `setEditorKey`, `setIsEditorOpen(false)`, `setSelectedGates({})`, NPC-mode resets) so it runs only after the awaited call resolves; add an explicit `catch` that keeps the content, keeps the editor **open**, and does nothing else (the parent already toasted — add a code comment saying so). Keep `finally { setSubmitting(false) }`. Apply to **both** the NPC branch and the regular branch. (b) Create `ConfirmDialog.tsx` — a small reusable confirm modal using `modal-overlay` / `modal-content` / `gold-outline` / `btn-blue` from the design system, `w-[min(92vw,480px)]`, no `React.FC`, Tailwind only — and use it in `resetForm` (`:161-169`) so «Отмена» asks for confirmation when the editor is not empty. | Frontend Developer | DONE | `…/LocationPage/PostCreateForm.tsx` (modify), `…/LocationPage/ConfirmDialog.tsx` (new) | T1 | A failed send leaves the text in the editor and the editor open; a successful send clears it. «Отмена» on non-empty content shows the modal; on empty content it closes immediately. Renders correctly at 360 px. `npx tsc --noEmit` + `npm run build` pass. No SCSS added. |

### Slice C — Russian error messages (independent of A and B)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| **T3** | Translate the six English `HTTPException` details in `move_and_post` per the table in section 3.7 (lines 1004, 1050, 1059, 1063, 1107, 1122). Line 1050 must use the exact wording already used by `quick_move` at `:1310-1314`. Change nothing else — no status codes, no control flow. Do **not** touch the NPC path or `_validate_intent_post`; they are already Russian (audited in 3.7). | Backend Developer | DONE | `services/locations-service/app/main.py` | — | `grep -n 'detail="[A-Za-z]' ` over `move_and_post` returns nothing. `python -m py_compile app/main.py` passes. Existing `locations-service` pytest suite still green. |
| **T4** | pytest covering the translated messages: at least the adjacency 400 and the stamina 400 from `move_and_post`, asserting the Russian `detail` text and the 400 status. Mock the character-service / attributes-service `httpx` calls and the DB session per the existing `conftest.py` pattern; override `get_current_user_via_http` and `verify_character_ownership` the way `test_endpoint_auth.py` / `test_action_gates.py` do. Add a guard test that asserts no `detail=` string inside `move_and_post` is pure ASCII Latin. | QA Test | DONE | `services/locations-service/app/tests/test_move_and_post_messages.py` (new) | T3 | `pytest app/tests/test_move_and_post_messages.py` passes inside the `locations-service` container. Full service suite still green. |

### Slice B — server-side drafts (backend)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| **T5** | Add the `PostDraft` ORM model exactly as specified in 3.2 — `content` as `sqlalchemy.dialects.mysql.MEDIUMTEXT`, `active` nullable `TINYINT` (`sa.SmallInteger`/`mysql.TINYINT`), FK `location_id → Locations.id ON DELETE CASCADE`, no FK on `character_id`, `UniqueConstraint('character_id','location_id','active', name='uq_post_drafts_active')`, `Index('idx_post_drafts_char_updated','character_id','updated_at')`. Write the hand-made Alembic migration `036_add_post_drafts` (`down_revision='035_origin_drop_map_link'`) with a working `downgrade()`. Do **not** use autogenerate. | Backend Developer | DONE | `services/locations-service/app/models.py`, `services/locations-service/app/alembic/versions/036_add_post_drafts.py` (new) | — | `alembic upgrade head` then `alembic downgrade -1` both succeed against the dev MySQL container. `version_table` stays `alembic_version_locations` (env.py untouched). Model metadata matches the migration. `py_compile` passes on both files. |
| **T6** | Add the Pydantic **v1** schemas from 3.3 (`PostDraftSave`, `PostDraftRead`, `PostDraftListItem`) and the async CRUD layer in a new `POST DRAFTS` section of `crud.py`: `get_active_draft`, `list_drafts` (≤10, `updated_at DESC`, joined to `Locations.name`, preview + char_count via the existing `strip_html_tags`), `get_draft_by_id`, `upsert_draft` (sets `updated_at` explicitly; deletes the row when the stripped content is empty), `delete_active_draft`, `delete_draft_by_id`, `archive_draft_on_post` (`active=NULL`, `sent_at=now`, content overwritten; inserts an archived row if none existed), and `evict_drafts` (keep the newest 10 by `updated_at`, called from `upsert_draft` and `archive_draft_on_post` in the same transaction). Define `MAX_DRAFTS_PER_CHARACTER = 10`, `MAX_DRAFT_LENGTH = 100_000` and `DRAFT_PREVIEW_LENGTH = 180` as named module constants — no magic numbers. | Backend Developer | DONE | `services/locations-service/app/schemas.py`, `services/locations-service/app/crud.py` | T5 | Pydantic v1 syntax (`class Config: orm_mode = True`), async SQLAlchemy throughout, no sync session usage. `py_compile` passes. Constants named, not inlined. |
| **T7** | Implement endpoints D1–D6 from 3.3 in `main.py`, declared as one block placed **before** the `/{location_id}/…` routes. Every route: `current_user=Depends(get_current_user_via_http)` + `await verify_character_ownership(...)`; for D2/D6 load the row first and authorise on `row.character_id` (never on a client-supplied id). D4 rejects content over `MAX_DRAFT_LENGTH` with a Russian 400. D5/D6 return 204 and are idempotent. Additionally, wire `archive_draft_on_post` into `move_and_post` immediately after `crud.create_post` succeeds (`:1090`), wrapped in `try/except Exception` + `logger.warning` mirroring the adjacent `create_action_gates` block (`:1091-1097`). | Backend Developer | DONE | `services/locations-service/app/main.py` | T6 | All six routes appear in `/openapi.json` with the documented paths, methods and status codes. A draft failure inside `move_and_post` (simulated by raising in `archive_draft_on_post`) still returns 200 and still creates the post. `py_compile` passes. |
| **T8** | Add a per-IP rate-limit for the autosave endpoint: `limit_req_zone $binary_remote_addr zone=draft_limit:10m rate=60r/m;` in the `http` block, and a regex `location ~ ^/locations/[0-9]+/draft$` with `limit_req zone=draft_limit burst=20 nodelay; limit_req_status 429;` proxying to `locations-service_backend`. The regex block must be declared **before** `location /locations/`, next to the existing `gathering-nodes` regex block. Apply the identical change to **both** files (CLAUDE.md §8.1). | DevSecOps | DONE | `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` | — | `nginx -t` passes in the api-gateway container for both configs. `PUT /locations/1/draft` still routes to locations-service; a burst of >80 requests/min from one IP gets 429; all other `/locations/` routes are unaffected. |
| **T9** | pytest for the draft API. Cover: upsert creates then updates the live draft; empty content deletes it and returns `null`; the 10-item cap evicts the oldest by `updated_at`; a successful post archives the live draft (`active=NULL`, `sent_at` set) and the post still succeeds when archiving raises; D2/D6 return **403** for a draft belonging to another user (the key security case); every route returns 401 without a token; oversized content returns 400 with the Russian message; D5 is idempotent (204 twice). Follow the mocking style of `conftest.py` + `test_action_gates.py`. | QA Test | DONE | `services/locations-service/app/tests/test_post_drafts.py` (new) | T7 | All listed cases present and passing. Full `locations-service` suite green. The cross-user 403 case and the "archiving failure does not fail the post" case are both explicitly asserted. |

### Slice B — drafts (frontend)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| **T10** | TypeScript types + REST client for D1–D6. Types mirror 3.3 exactly (`snake_case` field names as the API returns them). The client follows `src/api/gatheringApi.ts`: axios, no manual `Authorization` header (the global interceptor supplies it), errors propagated to the caller. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/types/postDrafts.ts` (new), `services/frontend/app-chaldea/src/api/postDrafts.ts` (new) | T7 | `npx tsc --noEmit` passes. No `any`. One exported function per endpoint, names matching the contract. |
| **T11** | `usePostDraft(characterId, locationId, enabled)` hook implementing 3.5: debounce 2500 ms with a 15 s max-wait flush, skip-if-unchanged via `lastSavedRef`, skip empty→empty, flush on `visibilitychange → hidden` and on unmount, synchronous `localStorage` mirror under `chaldea:post-draft:{characterId}:{locationId}`, restore-on-mount taking the newer of server vs local by timestamp, plus `clearDraft()`, `markSent()`, `retry()` and exposed `{ initialContent, loading, saveState, lastSavedAt, error }`. Never throws into render; never blocks typing. Structural template: `src/components/CreateCharacterPage/useCharacterDraft.ts`. All debounce/limit numbers as named constants. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/hooks/usePostDraft.ts` (new) | T10 | `npx tsc --noEmit` + `npm run build` pass. With the network offline the hook still stores locally, sets `saveState: 'error'`, and never rejects unhandled. Unchanged content produces zero requests (verifiable in DevTools Network). |
| **T12** | `DraftsPanel` — the «Черновики» tab body per 3.6. Props: `characterId`, `onInsert(content)`, `onClose`. Loads D1 on open, renders ≤10 rows (location name, date, 2-line clamped preview, «Отправлен»/«Черновик» badge), «Вставить» (fetches D2 for the full content, then calls `onInsert`) and «Удалить» (D6, confirmed through `ConfirmDialog`). Empty state and a Russian error state with «Повторить». Tailwind only, design-system classes (`gold-scrollbar`, `chip-outline`, `btn-blue`, `rounded-card`), no `React.FC`, responsive from 360 px. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/LocationPage/DraftsPanel.tsx` (new) | T10, T2 | Renders list / empty / loading / error states. Every API failure shows a visible Russian message — no silent catch. No horizontal overflow at 360 px. `npx tsc --noEmit` + `npm run build` pass. |
| **T13** | Wire drafts into `PostCreateForm`: the «Пост» / «Черновики» chip tab switch above `WysiwygEditor`; call `usePostDraft` (disabled while `npcMode` is on) and seed `content` + `editorKey` from `initialContent` once loading finishes; push every `setContent` into the hook's scheduler; render the inline save indicator («Черновик сохранён · HH:MM» / «Черновик не сохранён» + «Повторить») next to the existing character counter; add an «Очистить черновик» action (D5 + local clear, confirmed through `ConfirmDialog`); on «Вставить» from `DraftsPanel` with non-empty content, confirm first, then replace via `setContent` + `editorKey` bump; call `markSent()` on a successful send so the local mirror is cleared. Autosave must never disable the editor or the submit button. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCreateForm.tsx` | T11, T12 | Typing autosaves; reloading the page restores the text; a failed send leaves both editor and draft intact; a successful send clears the editor and the text appears in «Черновики» as «Отправлен». Draft API down ⇒ typing still works, one toast + a persistent inline error. 360 px layout intact. `npx tsc --noEmit` + `npm run build` pass. No SCSS. |

### Slice B — cascade cleanup on character deletion (per 3.12)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| **T16** | Add the admin cleanup endpoint **D7** `DELETE /locations/admin/drafts/by_character/{character_id}` guarded by `Depends(require_permission("locations:delete"))` (already-registered permission — **no RBAC migration**), plus `crud.delete_drafts_by_character(session, character_id) -> int`. Returns `200 {"detail": ..., "count": N}`, idempotent (`count: 0` when nothing matched). Mirror the shape of skills-service `main.py:309-316`. Deletes from `post_drafts` **only** — not `posts`, `post_likes` or `action_gates` (see 3.12 "Why drafts only"). Declare it with the other `/locations/admin/...` routes, ahead of the `/{location_id}/…` block. | Backend Developer | DONE | `services/locations-service/app/main.py`, `services/locations-service/app/crud.py` | T6 | Route present in `/openapi.json`; returns 200 + count for a character with drafts, 200 + `count: 0` for one without (idempotent on a second call), 403 for a token lacking `locations:delete`, 401 without a token. Only `post_drafts` rows are touched. `py_compile` passes. |
| **T17** | Wire the cleanup into character deletion. In `delete_character` (`services/character-service/app/main.py:1121-1218`), insert a new **step 4.5** after the user-service block (`:1206`) and **before** `db.delete(character)` (`:1209`), calling D7 at `{settings.LOCATIONS_SERVICE_URL}/locations/admin/drafts/by_character/{character_id}` with `headers` (the forwarded Bearer token) and `httpx.AsyncClient(timeout=10.0)`. Copy the block shape of steps 1–4 **exactly**: `try/except Exception`, `logger.info` on 200, `logger.warning` on a non-200 or an exception, and **never re-raise**. `LOCATIONS_SERVICE_URL` already exists at `config.py:13` — do **not** add an env var, a compose entry or a settings field. | Backend Developer | DONE | `services/character-service/app/main.py` | T16 | Deleting a character removes its `post_drafts` rows. With locations-service stopped (or D7 returning 500), the character is still deleted, the endpoint still returns 200, and a `logger.warning` is emitted — the character delete **never** fails because of drafts. No new env var or config field. `python -m py_compile` passes. |
| **T18** | pytest for the cleanup, on both sides. **locations-service:** D7 deletes only the target character's drafts and leaves other characters' rows intact; idempotent second call returns `count: 0`; 403 without `locations:delete`; 401 without a token; `posts` rows are untouched. **character-service:** `delete_character` calls the locations cleanup URL exactly once with the forwarded token (assert on a mocked `httpx.AsyncClient`), and — the key case — **the character is still deleted and 200 still returned when that call raises or returns 500**. Follow the existing mocking style in each service's `tests/conftest.py`. | QA Test | DONE | `services/locations-service/app/tests/test_post_drafts.py` (extend), `services/character-service/app/tests/test_delete_character_cleanup.py` (new or extend the existing delete test if one exists) | T17 | All listed cases pass in both services' suites; both full suites stay green. The "cleanup failure does not fail the character deletion" case is explicitly asserted. |

### Slice B — «Отмена» retires the draft (user ruling, per 3.13)

Additive follow-up to already-completed work. T19–T21 supersede parts of T6/T7
(backend), T13 (frontend) and T9 (tests); **T12 `DraftsPanel` needs no change**.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| **T19** | Add `crud.archive_active_draft(session, character_id, location_id) -> int` — load the live row, set `active = None` and `updated_at = now`, leave `sent_at` **NULL** and `content` untouched, call `evict_drafts`, commit; return the rows retired (0 when there was no live draft). Do **not** refactor `archive_draft_on_post` or `upsert_draft` (3.13 — they are shipped, tested and on the post-creation critical path). Add an optional query parameter `keep_in_history: bool = Query(False, ...)` to D5 `DELETE /locations/{location_id}/draft` (`main.py:485-496`): when true call `archive_active_draft`, otherwise keep calling `delete_active_draft`. Still 204, still idempotent. No schema change, no migration, no new Pydantic field. | Backend Developer | DONE | `services/locations-service/app/crud.py`, `services/locations-service/app/main.py` | — (T6, T7 done) | `DELETE …/draft?character_id=N&keep_in_history=true` returns 204 and leaves the row with `active IS NULL`, `sent_at IS NULL`, content intact; the same call without the parameter still hard-deletes (unchanged default). `GET /locations/{id}/draft` then returns `null`. `GET /locations/drafts` still lists the row with `is_sent: false`, `is_active: false`. `python -m py_compile` passes; the existing suite stays green. |
| **T20** | Wire «Отмена» to the new behaviour. (a) `api/postDrafts.ts:66` `deleteActiveDraft` gains an optional `keepInHistory = false` argument mapped to the query parameter. (b) `usePostDraft` exports a new `archiveDraft(): Promise<void>` — the body of `clearDraft` (`:429-457`) but calling `deleteActiveDraft(locId, charId, true)`; it must keep **all** of `markSent`'s local bookkeeping (cancel timers, bump `saveSeqRef`, clear `pendingRef`/`lastSavedRef`, `removeLocalMirror`, reset `saveState`/`lastSavedAt`/`error`) so the mirror cannot resurrect the text, and it must surface a failure through `error` without rejecting. (c) `PostCreateForm.resetForm` (`:271-285`) — **delete the `scheduleSave('')` call** and call `void archiveDraft()` instead, keeping the `if (!npcMode)` guard. (d) Update the cancel `ConfirmDialog` (`:657-666`) to the copy in 3.13 and **remove `danger`**. Do not touch «Очистить черновик» or `DraftsPanel`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/api/postDrafts.ts`, `services/frontend/app-chaldea/src/hooks/usePostDraft.ts`, `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCreateForm.tsx` | T19 | Write a post, press «Отмена», confirm → field empties; reloading the location shows an **empty** field; the text appears in «Черновики» badged «Черновик»; «Вставить» brings it back. Writing a new post in the same location afterwards does not overwrite or remove that archived text. «Очистить черновик» still destroys the draft. No stray `PUT …/draft` fires after the cancel (check DevTools Network). `npx tsc --noEmit` + `npm run build` pass. No SCSS, no `React.FC`. |
| **T21** | Extend the draft tests. **Backend:** `keep_in_history=true` retires the live row (`active IS NULL`, `sent_at IS NULL`, content preserved) and 204; the default and `false` still hard-delete; idempotent (204 twice, second call retires nothing); the retired row still appears in D1 with `is_sent: false`; a subsequent `upsert_draft` in the same location creates a **new** row and leaves the retired one intact (the core regression — proves the slot was freed); eviction still caps at 10 after a cancel. Ownership/401 cases already covered by T9 need no duplication. | QA Test | DONE | `services/locations-service/app/tests/test_post_drafts.py` (extend) | T19 | All listed cases pass; full `locations-service` suite green. The "cancel then write again does not clobber the cancelled text" case is explicitly asserted. |

### Docs & review

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| **T14** | Document the feature and file the incidental findings. (a) Add the `post_drafts` table and endpoints D1–D7 to `docs/services/locations-service.md`, and note the new `character-service → locations-service` cleanup call in `docs/ARCHITECTURE.md`'s dependency graph. (b) Add three `docs/ISSUES.md` entries found during design and **not** fixed here: `posts.content` is `TEXT` (64 KB) and can silently truncate a long RP post — MEDIUM, `services/locations-service/app/models.py:162`; `delete_character` does not clean up `posts` / `post_likes` / `action_gates`, so those rows are orphaned today (widening the cleanup is a product decision — see 3.12 "Why drafts only") — MEDIUM, `services/character-service/app/main.py:1121`; CLAUDE.md §10.7 is stale — locations-service *does* verify JWT via `auth_http.py` — LOW, docs. | Backend Developer | DONE | `docs/services/locations-service.md`, `docs/ARCHITECTURE.md`, `docs/ISSUES.md` | T7, T17 | All docs updated; no stale entries introduced; each ISSUES entry names service, file and priority. |
| **T15** | Final review of all slices. Re-run `npx tsc --noEmit`, `npm run build`, `python -m py_compile` on every modified backend file, and the full `locations-service` **and** `character-service` pytest suites. **Live verification is mandatory:** log in, open a location, type a post, confirm the autosave request fires once per debounce window and not per keystroke; force a 400 (post into a non-adjacent location) and confirm the text survives **and** the error toast is Russian; reload and confirm restore; open «Черновики», insert an older text (confirm dialog appears), delete one; send a valid post and confirm it lands in the list as «Отправлен»; press «Отмена» on a written post and confirm the field empties, the location reopens **empty**, the text is in «Черновики» badged «Черновик», and writing a new post there afterwards does not clobber it (3.13); delete a test character and confirm its `post_drafts` rows are gone while its `posts` remain; check the console for zero errors and the layout at 360 px. Verify the security checklist: cross-user draft access returns 403, D7 returns 403 without `locations:delete`, no route is reachable without a token, no secrets in logs. | Reviewer | DONE | — | T1–T14, T16–T21 | All automated checks recorded with their output. Every live step above confirmed with evidence. Any FAIL routed back to the owning agent (max 3 iterations). |

### Parallelism notes for PM

- **T1 → T2** are strictly sequential (same feature, T2 relies on T1's rethrow).
- **T3** and **T5** can start at the same time as T1 — different files, no overlap.
  T3 and T7 both edit `main.py`; land **T3 before T7** to avoid a conflict.
- **T8** (DevSecOps) has no code dependency and can run any time before T15.
- **T10** unblocks T11 and T12, which can run in parallel; T13 needs both.
- **T16 → T17 → T18** are the cascade-cleanup chain. T16 needs only T6 (the CRUD
  layer), so it can run in parallel with T7 and with the whole frontend track.
  T16 and T7 both edit `locations-service/app/main.py` — land **T7 before T16**.
  T17 is the only task in this feature that touches `character-service`.
- **T4**, **T9** and **T18** are the mandatory QA tasks (backend Python changed in
  T3, T5, T6, T7, T16, T17). None may be skipped.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-13 (T15)

**Result: FAIL** — one blocking data-loss path (issue #1). Everything else in
T1–T14 and T16–T21 re-verified and correct.

The bar applied throughout: *this feature exists because a player lost two hours
of writing.* Any path that still destroys a player's text is blocking, not a
nitpick — especially one where the UI promises the opposite.

---

#### Automated Check Results (all re-run by the Reviewer, not taken from task reports)

| Check | Command | Result |
|---|---|---|
| TypeScript | `docker exec frontend sh -lc 'cd /app && npx tsc --noEmit'` | **PASS** — exit 0, no output |
| Frontend build | `docker exec frontend sh -lc 'cd /app && npm run build'` | **PASS** — `✓ built in 30.25s`; only the pre-existing >500 kB chunk warning |
| Vite module compile | `GET http://localhost:5555/src/...` for all 7 new/modified frontend modules | **PASS** — 200 on every one (`usePostDraft.ts`, `api/postDrafts.ts`, `types/postDrafts.ts`, `DraftsPanel.tsx`, `ConfirmDialog.tsx`, `PostCreateForm.tsx`, `LocationPage.tsx`) |
| Python syntax | `py_compile` on `main.py crud.py models.py schemas.py alembic/versions/036_add_post_drafts.py tests/test_post_drafts.py tests/test_move_and_post_messages.py` (locations-service) and `main.py tests/test_delete_character_cleanup.py` (character-service) | **PASS** — `LOC_COMPILE_OK`, `CHAR_COMPILE_OK` |
| pytest locations-service | `docker exec locations-service sh -lc 'cd /app && python -m pytest tests/ --asyncio-mode=auto -q'` | **PASS** — `849 passed, 3 warnings in 10.88s` (matches the expected 849) |
| pytest character-service | `docker exec character-service sh -lc 'cd /app && python -m pytest tests/ --asyncio-mode=auto -q'` | **PASS** — `835 passed, 1 skipped, 2 warnings in 33.40s` (matches the expected 835/1) |
| nginx dev | `docker exec api-gateway nginx -t` | **PASS** — `syntax is ok` / `test is successful`; the running gateway really carries the block (`draft_limit` at `/etc/nginx/nginx.conf:40`, regex location at `:262`) |
| nginx prod | `nginx -t -c` on a copy of `nginx.prod.conf` | **PASS** — `syntax is ok` / `test is successful`. The only failure on the verbatim file was `cannot load certificate /etc/letsencrypt/live/fallofgods.top/fullchain.pem` — a missing-file artifact of the dev box, not a config defect; with the four `ssl_*` directives stubbed the whole file parses |
| Alembic | `docker exec locations-service alembic current` / `heads` | **PASS** — both `036_add_post_drafts (head)`; chain `035_origin_drop_map_link → 036` verified; table live in MySQL with `uq_post_drafts_active`, `idx_post_drafts_char_updated`, `content mediumtext`, `active tinyint NULL`, FK `ON DELETE CASCADE` |

#### Code-standards checks

- `React.FC` / `React.FunctionComponent` in new or modified frontend files — **none**.
- New `.jsx` files or new `.scss`/`.css` — **none**; every new frontend file is `.tsx`/`.ts` and Tailwind-only.
- `: any` / `<any>` in the new frontend modules — **none**.
- `TODO` / `FIXME` / `HACK` in the changed files — **none**.
- Pydantic v1 syntax — `class Config: orm_mode = True`; no `model_config` anywhere in `schemas.py`.
- Design-system classes actually exist and ship: `chip-outline` / `chip-outline-active` (`index.css:495`), `modal-overlay` (`:243`), `modal-content` (`:256`), `btn-line` (`:170`), `btn-blue` (`:150`), `gold-text` (`:14`), `gold-outline-thick` (`:44`), `gold-scrollbar` (`:322`); `chip-outline-active`, `line-clamp-2`, `text-stat-energy`, `text-site-red`, `text-site-blue`, `ease-site`, `gold-scrollbar` all present in the built `dist/assets/index-*.css`.
- Async/sync discipline respected: locations-service stays async, character-service stays sync + `httpx.AsyncClient`.

#### Cross-service contract verification

- **Live `/openapi.json` vs the API client.** locations-service publishes exactly `/locations/drafts`, `/locations/drafts/{draft_id}`, `/locations/{location_id}/draft`, `/locations/admin/drafts/by_character/{character_id}` — byte-identical to the paths in `src/api/postDrafts.ts`.
- **Pydantic vs TypeScript.** `PostDraftRead` (id, character_id, location_id, content, is_sent, is_active, created_at, updated_at — all required) and `PostDraftListItem` (…, location_name optional, preview, char_count) match `src/types/postDrafts.ts` field-for-field, `snake_case` preserved, no conversion layer needed. `location_name` is optional in the schema and `string | null` in TS — safe.
- **D5 `keep_in_history`.** Present in the live spec as an optional boolean query parameter with `"default": false` — backwards compatible, and `deleteActiveDraft(locId, charId, keepInHistory = false)` mirrors it.
- **character-service step 4.5 URL.** `settings.LOCATIONS_SERVICE_URL` resolves at runtime to `http://locations-service:8006` (confirmed inside the container), so the call is `http://locations-service:8006/locations/admin/drafts/by_character/{id}` — exactly D7's registered path. Failure is swallowed with `logger.warning`, matching steps 1–4.
- No new env var, compose entry, RabbitMQ queue or RBAC permission row — as designed (`locations:delete` already exists).

#### Live Verification Results

**Scope disclosure — read this before trusting the list below.** The Claude-in-Chrome
extension is not connected in this session, so **no step was performed by clicking in a
real browser.** Everything below was driven through the api-gateway on `:80` with the
real JWT of `chaldea@admin.com` (user 4, character 765), plus Vite module-compile checks
and direct MySQL inspection. The consequences are stated explicitly in
"Not verified" at the end of this section.

Environment: full dev stack up; DB `fogdatabase`.

| # | Step | Actual output |
|---|---|---|
| 1 | Login | `POST /users/login` 200, access token issued; `GET /users/me` → `id=4 role=admin` |
| 2 | D3 read live draft | `GET /locations/1306/draft?character_id=765` → 200, `id=55 is_active=True is_sent=False len=7122` |
| 3 | D4 autosave | `PUT /locations/1306/draft` → 200, `id=55 is_active=True updated=2026-09-13T14:55:22` (same row updated, not duplicated) |
| 4 | D1 list | `GET /locations/drafts?character_id=765` → 200, 1 row, `location_name` joined, `char_count=119`, preview is plain text (no HTML) |
| 5 | **Force a 400 — post into a non-adjacent location** | `POST /locations/28/move_and_post` (char 765 stands in 1306) → **400** `detail = "Целевая локация не является соседней"` — Russian, matches T3 |
| 6 | **Text survives the 400** | `GET /locations/1306/draft?character_id=765` immediately after → 200, `id=55 len=202 active=True`. **The draft was untouched by the rejected post.** |
| 7 | **Cancel flow (T19–T21)** | `DELETE /locations/1306/draft?character_id=765&keep_in_history=true` → **204** |
| 8 | Field is empty on return | `GET /locations/1306/draft?character_id=765` → 200, body literally `null` |
| 9 | Text retrievable as «Черновик» | D1 → `id=55 active=False sent=False` → `DraftsPanel` renders the «Черновик» badge (`is_sent=false`) |
| 10 | **Write again in that location — cancelled text survives** | `PUT /locations/1306/draft` → **new row `id=56`**, `active=True`; D1 then shows both `id=56 active=True` and `id=55 active=False sent=False`. The live slot was genuinely freed. |
| 11 | Cancel is idempotent | `DELETE …/1304/draft?...&keep_in_history=true` with no live row → **204** |
| 12 | **Send a valid post → archived as «Отправлен»** | draft `id=57` written in 1304, then `POST /locations/1304/move_and_post` → 200 `post id=141`; D1 then shows `id=57 active=False sent=True chars=519` |
| 13 | Empty content deletes the live row | `PUT` with `<p></p>` → 200, body `null`; row gone from the DB |
| 14 | Oversize content | `PUT` with 100 001 chars → **400** `"Черновик слишком длинный — максимум 100000 символов"` |
| 15 | **10-item eviction cap** | ~870 autosaves across distinct locations for character 765 → `SELECT COUNT(*) … WHERE character_id=765` = **10**, and the ten retained are exactly the newest by `updated_at` (`id 206…215`) |
| 16 | **Nginx rate limit (T8) actually fires** | the same burst produced **867 × HTTP 429** once `burst=20` was exhausted, i.e. `location ~ ^/locations/[0-9]+/draft$` matches and `limit_req_status 429` is applied |
| 17 | Draft API down → typing unaffected | Verified by code path, not by killing the service — see "Not verified" |

#### Security checklist

| Check | Actual output |
|---|---|
| No token on any draft route | D1/D2/D3/D5/D6/**D7** → **401 `Not authenticated`** (FastAPI's built-in `HTTPBearer` message; the frontend's axios interceptor turns 401 into a Russian toast, so no new user-facing English) |
| Ownership on id-in-request routes | D1/D3/D5 with `character_id=11` (owned by user 1) using user 4's **admin** token → **403 «Вы можете управлять только своими персонажами»**. Admin does *not* bypass ownership — correct for player-private data. |
| Unknown character | D1 with `character_id=99999999` → **404 «Персонаж не найден»** |
| **Cross-user row-addressed access (the key case)** | a draft row (`id=58`) was inserted for character 11; `GET /locations/drafts/58` → **403**, **no content leaked**; a second, plain non-admin account got **403** on the same row |
| **Row survives a rejected DELETE** | `DELETE /locations/drafts/58` → 403, then `SELECT` → row 58 still present with `active=1`. Nothing was destroyed by the rejected call. |
| Missing row | D2/D6 with `id=99999999` → **404 «Черновик не найден»** (no distinction leak between "missing" and "someone else's" beyond the standard 403/404 split, which is the project's existing convention) |
| **D7 without `locations:delete`** | plain `user`-role account → **403 «Недостаточно прав»** |
| D7 with permission | admin → **200 `{"detail":"All post drafts deleted","count":1}`**; second call → **200 `count:0`** (idempotent) |
| SQL injection | all draft queries are SQLAlchemy constructs with bound parameters; no f-string SQL. `test_sql_injection_in_content_is_stored_as_data` covers storage-as-data. |
| XSS | draft content is the same TipTap HTML already stored in `posts.content`, is never passed to `dangerouslySetInnerHTML` by the new code, and is fed back into the same sanitising editor. No new surface. |
| Secrets in logs | the new `logger.warning` calls carry only ids, status codes and exception text — no tokens, no content. |
| Rate limiting | present on the only high-frequency route (D4), verified firing (step 16). |
| Russian user-facing strings | all six T3 translations confirmed live for the adjacency case; every new 400/403/404 detail is Russian; every frontend failure path renders a Russian message (`DraftsPanel` load/insert/delete, `usePostDraft` save/load/clear/archive, the one-per-session autosave toast). |

#### QA coverage

Backend changed in T3/T5/T6/T7/T16/T17/T19 → QA is mandatory and present:
`test_post_drafts.py` (**61** test functions incl. the T21 "Layer 4" cancel block),
`test_move_and_post_messages.py` (**5**), `test_delete_character_cleanup.py` (**7**
functions, 13 cases with parametrisation). Every endpoint D1–D7, both `keep_in_history`
branches, eviction, archive-on-send, archive-on-cancel, and the 401/403 security cases
are covered. **QA requirement satisfied.**

---

#### Issues Found

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCreateForm.tsx:653-661` (dialog copy) + `:287-300` (`confirmInsertDraft` / `replaceContent`) | **BLOCKING — "Вставить" from «Черновики» destroys the text currently in the editor, while the dialog promises the opposite.** The dialog says «Текущий текст останется в черновиках.» In fact `confirmInsertDraft` calls `replaceContent(next)`, whose `scheduleSave(html)` upserts the chosen text into the **same live row** that was holding the current text (`uq_post_drafts_active` allows exactly one live row per character+location, and `crud.upsert_draft` updates it in place). The current text is overwritten and is in no history row. **Reproduced live:** live row `id=216` held «ТЕКСТ A»; a second `PUT` simulating the insert returned the **same `id=216`** with «ТЕКСТ B»; `GET /locations/drafts?character_id=765` then contained **0** rows mentioning «ТЕКСТ A». Root cause is the architecture's own lifecycle row in §3.2 ("the client inserts the text into the editor, which triggers a normal autosave into the current location's live slot") combined with the §3.6 copy. Fix shape: archive the live row before inserting — `await archiveDraft()` (which already frees the slot, drops the local mirror, cancels timers and resets `lastSavedRef`) *then* `replaceContent(next)`, so the subsequent autosave creates a new row; keep the dialog copy, which then becomes true. Needs a QA case mirroring `test_cancel_then_write_again_keeps_the_cancelled_text`. Deliberately **not fixed by the Reviewer** — it is a behaviour change with an async ordering race, not a trivial in-scope edit. **RESOLVED 2026-09-13 (Frontend Dev).** `handleInsertDraft` / `confirmInsertDraft` now funnel through `insertDraftContent`, which `await`s `archiveDraft()` *before* `replaceContent(next)`, so the live slot is freed (`active = NULL`, the text stays in the history as «Черновик») and the insert's autosave necessarily starts a **new** row. `archiveDraft` now returns `Promise<boolean>`: on a server failure it rolls its local bookkeeping back (the `localStorage` mirror included) and the insert is abandoned with a Russian toast, so a failed archive never leaves the player worse off than before. Re-verified live through the api-gateway: `PUT` «ТЕКСТ A» → `id=226`; `DELETE /locations/1306/draft?character_id=765&keep_in_history=true` → 204; `PUT` «ТЕКСТ B» → **`id=227`**; `GET /locations/drafts` then held **both** rows (`227 active=True` «ТЕКСТ B», `226 active=False sent=False` «ТЕКСТ A»), and `GET /locations/drafts/226` returned «ТЕКСТ A» verbatim. A control run without the archive reproduced the old loss (`PUT` A → `id=228`, `PUT` B → the same `id=228`, zero rows mentioning «ТЕКСТ A»). Test rows cleaned up. The dialog copy is kept and is now true. | Frontend Developer (copy/flow originally specified by Architect, §3.2 + §3.6) | RESOLVED |
| 2 | `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCreateForm.tsx:498-513` | **NON-BLOCKING (spec deviation).** §3.6 specifies that "the «Черновики» chip carries a count badge when the history is non-empty". The chip is rendered without one. Cosmetic; the panel loads its own list on open. Fix or formally drop the requirement. | Frontend Developer | NOTED |
| 3 | `services/locations-service/app/main.py:1235-1241` | **NON-BLOCKING (observation, pre-existing pattern).** If `archive_draft_on_post` raises *mid-flush*, the `except` swallows it but the async session may be left in a failed transaction, and `crud.create_action_gates` at `:1247` reuses that same session. The post itself is already committed, so no text is lost; the blast radius is a possible 500 after a successful post. Identical exposure already exists for `create_action_gates`, so this feature does not make it worse. Worth a `session.rollback()` in the handler at some point. | — (note only) | NOTED |

#### Not verified (be explicit — these are the gaps in this review)

The Claude-in-Chrome extension is unavailable in this session, so the following
**could not** be checked and must not be read as passing:

1. **"Autosave fires once per debounce window, not per keystroke."** Verified by reading the implementation only — trailing-edge 2500 ms debounce with a single 15 s max-wait timer per burst, plus `shouldSkip` (`usePostDraft.ts:243-246`, `:303-343`). No network trace from a real editor was captured. The logic is correct on inspection, but this was the explicit ask and it remains browser-unverified.
2. **Browser console cleanliness** (zero `console.error`, no unhandled rejections). Mitigated indirectly: `tsc`, the production build and Vite module compilation all pass, every `usePostDraft` network call swallows its own rejection, and both `handleSubmit` branches now have a `catch`.
3. **Layout at 360 px.** Verified only by reading the classes — `flex-wrap`, `basis-full sm:basis-auto`, `flex-col sm:flex-row`, `line-clamp-2 break-words`, `w-[min(92vw,480px)]`, `min-w-0` throughout, no fixed widths. Not rendered.
4. **Killing the draft API while typing.** `locations-service` was not stopped, because doing so on the shared dev stack would have disrupted other work. The behaviour is covered by inspection (`persist` catches everything and only sets `saveState='error'`; the `localStorage` mirror is written synchronously *before* any network call at `:311-317`; the editor and the submit button are never disabled) and by the failed-load branch at `:380-394` — but not exercised.
5. The three end-to-end UI dialogs (cancel confirm, overwrite confirm, delete confirm) were reviewed as code and their server effects exercised via the API; the modals themselves were never rendered.

#### State restored

All rows created during this review were removed and the environment put back:
test drafts for character 765 deleted (`post_drafts` now holds **0** rows — note that a
pre-existing test row `id=55`, written at 14:42 by an earlier task's own live check, was
consumed by the eviction test and is gone); test post `id=141` deleted; character 765's
`current_location_id` restored to **1306**; the throwaway account `feat156review`
deleted; the foreign-owner row `id=58` removed via D7; the temporary nginx test files
inside the gateway container removed. Final check:
`drafts_left=0  post141=0  testuser=0  loc765=1306`.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-13 13:30 — PM: фича создана по обращению пользователя о потере ролевого поста
[LOG] 2026-09-13 13:35 — PM: анализ выполнен, причина потери найдена (2 бага во фронтенде)
[LOG] 2026-09-13 13:45 — PM: проверен прод, потерянный пост не сохранился нигде, восстановление невозможно
[LOG] 2026-09-13 13:50 — PM: требования уточнены у пользователя, запускаю архитектора
[LOG] 2026-09-13 14:00 — Architect: начал проектирование, изучил locations-service, PostCreateForm, LocationPage, alembic и дизайн-систему
[LOG] 2026-09-13 14:15 — Architect: исправлена фактическая ошибка в разделе 2 — locations-service всё же проверяет JWT через auth_http.py, отдельный механизм авторизации не нужен
[LOG] 2026-09-13 14:20 — Architect: найден третий путь потери текста — кнопка «Отмена» (resetForm) стирает пост без подтверждения, включён в задачу T2
[LOG] 2026-09-13 14:35 — Architect: спроектирована таблица post_drafts (частично-уникальный индекс через NULL, MEDIUMTEXT, вытеснение по updated_at) и 6 эндпоинтов D1-D6
[LOG] 2026-09-13 14:45 — Architect: проектирование завершено — 15 задач, 6 API-контрактов, 1 миграция (036), 2 QA-задачи; 3 вопроса к пользователю в разделе 3.11
[LOG] 2026-09-13 15:10 — Architect: получены ответы пользователя — лимит на персонажа и общий список по всем локациям подтверждены без изменений; по каскаду требуется реальная очистка
[LOG] 2026-09-13 15:20 — Architect: изучено удаление персонажа — character-service main.py:1121 делает hard delete и уже рассылает graceful-очистку в inventory/skills/attributes/user; locations-service в этой цепочке отсутствует
[LOG] 2026-09-13 15:30 — Architect: выбран существующий паттерн — admin-эндпоинт D7 в locations-service под require_permission('locations:delete') и вызов из character-service шагом 4.5; FK и RabbitMQ отклонены с обоснованием (раздел 3.12)
[LOG] 2026-09-13 15:35 — Architect: разрешение locations:delete уже есть в RBAC, новая миграция permissions не нужна; LOCATIONS_SERVICE_URL уже есть в config.py:13, новых env-переменных нет
[LOG] 2026-09-13 15:45 — Architect: добавлен раздел 3.12, эндпоинт D7 и задачи T16-T18 (включая QA на «персонаж удалён -> черновики удалены»); раздел 3.11 переписан — допущение про orphan-строки снято, раздел 1 Edge Cases обновлён
[LOG] 2026-09-13 15:50 — Architect: обнаружен смежный баг — delete_character не чистит posts/post_likes/action_gates, строки осиротевают уже сейчас; внесён в T14 для записи в ISSUES.md, в этой фиче не чиним
[LOG] 2026-09-13 16:05 — Backend Dev: T5 выполнена — модель PostDraft (MEDIUMTEXT, nullable active, FK на Locations с CASCADE) и рукописная миграция 036_add_post_drafts; upgrade/downgrade/upgrade прогнаны на dev-MySQL, version_table остался alembic_version_locations, env.py не тронут
[LOG] 2026-09-13 16:20 — Backend Dev: T6 выполнена — схемы Pydantic v1 (PostDraftSave/Read/ListItem) и async-CRUD черновиков в crud.py с константами MAX_DRAFTS_PER_CHARACTER/MAX_DRAFT_LENGTH/DRAFT_PREVIEW_LENGTH; проверено дымовым прогоном по реальной БД (upsert, пустой текст, вытеснение 10, архивация, идемпотентные удаления, лимит длины) и полным pytest locations-service — 777 passed
[LOG] 2026-09-13 16:05 — Backend Dev: T3 выполнена — шесть английских сообщений об ошибках в move_and_post переведены на русский (строки 1004, 1050, 1059, 1063, 1107, 1122); формулировка про несоседнюю локацию взята дословно из quick_move; py_compile и полный набор тестов locations-service (771 passed) зелёные
[LOG] 2026-09-13 16:20 — QA: T4 выполнена — создан tests/test_move_and_post_messages.py (6 тестов): русский detail и статус 400 для несоседней локации и нехватки выносливости, плюс статический guard через ast, который падает, если внутри move_and_post появится английский detail=. Новый файл — 6 passed; полный набор locations-service — 777 passed (было 771)
[LOG] 2026-09-13 14:15 — DevSecOps: T8 выполнен — добавлена зона draft_limit (60r/m) и regex-локация ~ ^/locations/[0-9]+/draft$ с burst=20 nodelay и 429 в оба конфига (nginx.conf и nginx.prod.conf); nginx -t прошёл для обоих (прод — с временным самоподписанным сертификатом), маршрутизация остальных /locations/ не задета, burst-тест: 22x404 + 78x429
[LOG] 2026-09-13 17:05 — Backend Dev: T7 выполнена — в main.py добавлен блок эндпоинтов черновиков D1–D6 перед маршрутами `/{location_id}/...`; на D2/D6 строка читается первой, владелец проверяется по row.character_id, чужой черновик отдаёт 403; D4 дублирует проверку длины из той же константы crud.MAX_DRAFT_LENGTH; D5/D6 идемпотентны и отдают 204
[LOG] 2026-09-13 17:10 — Backend Dev: в move_and_post сразу после crud.create_post вызывается crud.archive_draft_on_post в try/except с logger.warning — по образцу соседнего create_action_gates; проверено симуляцией падения архивации: пост 138 создан, ответ 200, в логе warning
[LOG] 2026-09-13 17:15 — Backend Dev: проверки T7 — py_compile в контейнере, все шесть маршрутов видны в /openapi.json с нужными кодами, живой прогон через api-gateway (создание/обновление/чтение/список/пустой текст/лимит длины/удаления/401/403/404), полный pytest locations-service — 777 passed
[LOG] 2026-09-13 16:40 — Frontend Dev: T10 выполнена — созданы src/types/postDrafts.ts (типы PostDraftSave/PostDraftRead/PostDraftListItem в snake_case, строго по разделу 3.3) и src/api/postDrafts.ts (listDrafts, getDraftById, getActiveDraft, saveDraft, deleteActiveDraft, deleteDraftById по образцу gatheringApi.ts, без ручного Authorization, ошибки пробрасываются вызывающему). npx tsc --noEmit в контейнере frontend — 0 ошибок; клиент сверен с живым /openapi.json locations-service (T7 уже задеплоен) — расхождений с контрактом нет
[LOG] 2026-09-13 17:05 — Frontend Dev: T12 выполнена — создан DraftsPanel.tsx (вкладка «Черновики»): загрузка списка через D1, «Вставить» тянет полный текст через D2, «Удалить» — D6 под ConfirmDialog. Состояния: загрузка, пустой список (тихий, без рамки) и ошибка загрузки (красный блок + «Повторить») — специально визуально разные, чтобы сбой не читался как «черновики пропали»; ошибки действий — toast + инлайн-баннер. Только Tailwind и классы дизайн-системы, адаптив от 360px. npx tsc --noEmit — 0 ошибок, npm run build — успешно (оба в контейнере frontend)
[LOG] 2026-09-13 17:15 — Frontend Dev: T11 выполнена — создан src/hooks/usePostDraft.ts: debounce 2500 мс с принудительным сбросом на 15 с, пропуск неизменённого текста и пустого→пустого, синхронное зеркало в localStorage (всё чтение/запись в try/catch), восстановление при монтировании по более свежей метке времени (наивные даты сервера трактуются как UTC), сброс на visibilitychange→hidden и при размонтировании/смене локации. Автосохранение fire-and-forget: при недоступном API текст остаётся локально, saveState='error', русское сообщение через apiErrorMessage, ни одного необработанного reject и никакой блокировки ввода. Все тайминги и лимиты — именованные константы. npx tsc --noEmit — 0 ошибок, npm run build — успешно (оба в контейнере frontend)
[LOG] 2026-09-13 17:40 — QA: T9 выполнена — создан app/tests/test_post_drafts.py, 42 теста. Crud-слой проверяется на реальном aiosqlite (upsert создаёт и обновляет живой черновик, пустой текст удаляет строку и возвращает None, лимит в 10 вытесняет самый старый именно по updated_at — id специально идут вразрез с датами, архивация после поста снимает active и ставит sent_at, архив освобождает живой слот). Маршруты D1–D6 — через TestClient с замоканным crud: 401 без токена на всех шести, 403 на чужом черновике с проверкой, что владелец сверяется по character_id строки (777), а не по данным клиента, и что после отклонённого DELETE строка на месте, 404 «Черновик не найден», 400 с русским сообщением о длине до похода в БД, D5 идемпотентен (204 дважды). Отдельно: падение archive_draft_on_post внутри move_and_post не роняет пост — ответ 200 и пост создан. Прогоны в контейнере locations-service: test_post_drafts.py — 42 passed; полный набор — 819 passed (было 777). Багов в чужом коде не найдено
[LOG] 2026-09-13 18:05 — Backend Dev: T16 выполнена — добавлен crud.delete_drafts_by_character (bulk delete с rowcount, идемпотентный) и эндпоинт D7 DELETE /locations/admin/drafts/by_character/{character_id} под require_permission("locations:delete"); форма ответа скопирована со skills-service (detail + count), новой RBAC-миграции не потребовалось — разрешение уже зарегистрировано
[LOG] 2026-09-13 18:10 — Backend Dev: проверки T16 — py_compile в контейнере, маршрут виден в /openapi.json; живой прогон: 200 count=2 для персонажа с черновиками, 200 count=0 на повторном вызове, 403 «Недостаточно прав» для токена без locations:delete, 401 без токена. Удалены только post_drafts целевого персонажа: черновик соседнего персонажа и пост персонажа остались на месте
[LOG] 2026-09-13 18:20 — Backend Dev: T17 выполнена — в delete_character добавлен шаг 4.5 (после очистки user-service, до db.delete): httpx.AsyncClient(timeout=10.0), проброшенный Bearer, try/except Exception, logger.info на 200 и logger.warning на всё остальное, исключение не пробрасывается. Новых env-переменных и полей settings нет — LOCATIONS_SERVICE_URL уже был в config.py:13
[LOG] 2026-09-13 18:30 — Backend Dev: проверено главное требование — при остановленном locations-service удаление персонажа 767 вернуло 200, персонаж действительно удалён, в логе WARNING «Error clearing post drafts ... Name or service not known». На живом стенде удаление персонажа 766 снесло его черновики, но оставило его пост и черновики другого персонажа. Полные наборы тестов: locations-service 777 passed, character-service 822 passed, 1 skipped. Тестовые строки (персонажи, посты, черновики, временный пользователь) удалены
[LOG] 2026-09-13 18:50 — Frontend Dev: T13 выполнена — черновики подключены в PostCreateForm: чип-переключатель «Пост»/«Черновики» над редактором, usePostDraft(characterId, locationId, !npcMode), посев content + editorKey из initialContent после загрузки (только в пустое поле и один раз на пару персонаж+локация, с автораскрытием редактора), каждый onChange уходит в scheduleSave, markSent() после успешной отправки
[LOG] 2026-09-13 18:52 — Frontend Dev: индикатор сохранения встроен в строку счётчика символов — «Сохраняем черновик…» / «Черновик сохранён · ЧЧ:ММ» (text-white/40) / «Черновик не сохранён» + «Повторить» (text-site-red); draftError выводится отдельным красным блоком независимо от saveState, чтобы сбой загрузки не читался как «не сохранён»; один toast на сессию при первом сбое автосохранения
[LOG] 2026-09-13 18:54 — Frontend Dev: добавлена кнопка «Очистить черновик» (D5 + локальная очистка) под ConfirmDialog, вставка из DraftsPanel в непустое поле спрашивает подтверждение замены; автосохранение нигде не блокирует ввод и не отключает кнопку отправки — все состояния черновика чисто информационные
[LOG] 2026-09-13 18:56 — Frontend Dev: locationId берётся из useParams (маршрут location/:locationId) — LocationPage не трогался; вкладка «Пост» скрывается через hidden, а не размонтируется, чтобы не терять историю отмены TipTap; в режиме НПС черновики полностью выключены (enabled=false, вкладки и индикатор скрыты). npx tsc --noEmit — 0 ошибок, npm run build — успешно (оба в контейнере frontend)
[LOG] 2026-09-13 18:58 — Frontend Dev: допущение — счётчик-бейдж на чипе «Черновики» (раздел 3.6) не сделан: DraftsPanel не отдаёт количество наружу, а дублировать запрос D1 ради бейджа означало бы лишний вызов на каждое открытие редактора
[LOG] 2026-09-13 19:15 — Backend Dev: T14 (а) выполнена — в docs/services/locations-service.md добавлены раздел «Черновики ролевых постов (FEAT-156)» с D1–D7, таблица post_drafts со всеми проектными решениями (MEDIUMTEXT, nullable active как частично-уникальный индекс, явный updated_at, вытеснение), шаг 5.1 в описании move_and_post и входящий вызов D7 от character-service; в docs/ARCHITECTURE.md post_drafts добавлена в таблицы locations-service, а в граф зависимостей — ребро character-service → locations-service (очистка черновиков при удалении персонажа, graceful)
[LOG] 2026-09-13 19:20 — Backend Dev: документировано по фактическому коду, а не по проекту; попутно поправлена ссылка на verify_character_ownership (main.py:114, а не :116) и на posts.content (models.py:165, а не :162 — в задаче номер был смещён)
[LOG] 2026-09-13 19:30 — Backend Dev: T14 (b) выполнена — в docs/ISSUES.md добавлены пять записей: три MEDIUM (posts.content = TEXT и молчаливое обрезание; delete_character не чистит posts/post_likes/action_gates — со ссылкой на 3.12 «Why drafts only» и пометкой «требуется решение пользователя»; move_and_post коммитит пост до перемещения и списания стамины — main.py:1213 против :1241 и :1256, найдено QA в T4) и две LOW (устаревший п.10.7 CLAUDE.md — locations-service проверяет JWT через auth_http.py; прод-база называется fogdatabase, а не mydatabase). Дубликатов не было — ни одной из пяти тем в ISSUES.md не оказалось. CLAUDE.md не правился: это запись в ISSUES, а не изменение файла
[LOG] 2026-09-13 18:00 — Architect: решение пользователя — «Отмена» очищает поле, но текст остаётся доступным во вкладке «Черновики»; спроектировано дополнение (раздел 3.13)
[LOG] 2026-09-13 18:10 — Architect: механизм — необязательный query-параметр keep_in_history у существующего D5 плюс crud.archive_active_draft (active=NULL, sent_at остаётся NULL); отдельный эндпоинт отклонён как дублирование преамбулы D5
[LOG] 2026-09-13 18:15 — Architect: третий статус «Отменён» не вводим — отменённый текст и есть недописанный черновик, двух бейджей хватает; миграции, новой колонки и правок DraftsPanel не требуется
[LOG] 2026-09-13 18:25 — Architect: зафиксирована главная ловушка — localStorage-зеркало воскресит отменённый текст, если его не снести; в T20 требование убрать scheduleSave('') из resetForm и повторить всю локальную уборку markSent
[LOG] 2026-09-13 18:30 — Architect: добавлены задачи T19-T21, обновлён T15; текст диалога «Отменить пост?» переписан — старая формулировка про безвозвратное удаление стала неправдой
[LOG] 2026-09-13 19:45 — QA: T18 выполнена, locations-service — в test_post_drafts.py добавлен блок из 10 тестов на D7. Crud-слой на реальном aiosqlite: удаляются и живой, и архивные черновики персонажа, черновики соседнего персонажа (2 строки в двух локациях) остаются нетронутыми, posts обоих персонажей остаются на месте (страховка на решение 3.12 «Why drafts only»), повторный вызов возвращает 0, неизвестный персонаж — тоже 0. Маршрут через TestClient: 200 с count и проверкой, что в crud ушёл именно character_id из пути; идемпотентность 200/count=0 на втором вызове; 403 «Недостаточно прав» для токена с locations:read вместо locations:delete (crud не вызывается); 401 без токена; отдельный тест на то, что /locations/admin/... не перехватывается маршрутами с числовым {location_id}
[LOG] 2026-09-13 19:50 — QA: T18, character-service — создан app/tests/test_delete_character_cleanup.py (13 тестов, sync-стиль этого сервиса: SQLite из conftest.py, auth через dependency_overrides, httpx.AsyncClient замокан целиком). Шаг 4.5 зовётся ровно один раз по адресу LOCATIONS_SERVICE_URL/locations/admin/drafts/by_character/{id} с проброшенным заголовком Bearer; порядок подтверждён — после вызовов user-service и до удаления строки; очистка идёт и для персонажа без user_id; для несуществующего персонажа (404) исходящих вызовов нет вовсе. Ключевой случай разложен на два параметризованных: при ответах 500/502/403/401/404 и при исключениях ConnectionError/TimeoutError/RuntimeError персонаж всё равно удалён и ответ всё равно 200, без повторных попыток; отдельно проверено, что сбой попадает в logger.warning. Ошибка навешивается только на URL черновиков, остальной fan-out отвечает 200 — иначе тест не доказывал бы, какой именно сбой стерпели
[LOG] 2026-09-13 19:55 — QA: прогоны в контейнерах — locations-service tests/test_post_drafts.py 52 passed, полный набор 829 passed (было 819); character-service tests/test_delete_character_cleanup.py 13 passed, полный набор 835 passed, 1 skipped (было 822, 1 skipped). Багов в коде T16/T17 не найдено
```
[LOG] 2026-09-13 20:10 — Backend Dev: T19 выполнена. В crud.py добавлена archive_active_draft — живая строка уходит в архив (active=NULL), sent_at остаётся NULL, content не трогается, updated_at поднимается, вызывается evict_drafts; идемпотентна (нет живого черновика — возвращает 0). archive_draft_on_post и upsert_draft не тронуты (решение 3.13). D5 DELETE /locations/{location_id}/draft получил необязательный параметр keep_in_history (по умолчанию false — прежнее жёсткое удаление). Проверено вживую на dev-стенде по всем четырём случаям: без параметра и с false строка исчезает; с true строка остаётся (active NULL, sent_at NULL, текст цел), D3 отдаёт null, D1 показывает её как «Черновик»; повторный вызов с true — 204 без изменений. Ключевое: следующий PUT в ту же локацию заводит НОВУЮ строку (id 54) и не перетирает отменённую (id 53) — слот действительно освобождён. py_compile прошёл, pytest locations-service — 829 passed. Тестовые строки из БД убраны.
[LOG] 2026-09-13 20:35 — Frontend Dev: T20 выполнена. deleteActiveDraft получил необязательный аргумент keepInHistory (по умолчанию false — поведение «Очистить черновик» не изменилось), он уходит в query-параметр keep_in_history. В usePostDraft добавлен archiveDraft(): полная локальная уборка как в markSent (гасит таймеры, инкрементит saveSeqRef, чистит pendingRef/lastSavedRef, удаляет localStorage-зеркало, сбрасывает saveState/lastSavedAt/error) плюс DELETE с keep_in_history=true; промис не реджектится, ошибка уходит в error русским текстом.
[LOG] 2026-09-13 20:35 — Frontend Dev: в PostCreateForm.resetForm вызов scheduleSave('') удалён и заменён на void archiveDraft() (guard if (!npcMode) сохранён) — иначе отложенный пустой PUT сработал бы после архивации и снёс бы только что сохранённую строку. Текст диалога отмены переписан: «Текст останется в черновиках — его можно вернуть из вкладки «Черновики».», кнопка «Убрать из поля», пропс danger убран. «Очистить черновик» и DraftsPanel не тронуты.
[LOG] 2026-09-13 20:35 — Frontend Dev: проверки в контейнере frontend — npx tsc --noEmit без ошибок, npm run build успешно (built in 27.21s).
[LOG] 2026-09-13 20:55 — QA: T21 выполнена. test_post_drafts.py расширен блоком «Layer 4» из 20 тестов (52 -> 72), структура и нумерация выше не тронуты. Crud-слой на реальном aiosqlite: keep_in_history=true уводит живую строку в архив (active NULL, sent_at так и остаётся NULL, текст цел, created_at не тронут, updated_at поднят); ключевая регрессия — отмена, затем новый пост в той же локации заводит НОВУЮ строку, а отменённый текст остаётся нетронутым (слот действительно освобождён); после отмены get_active_draft отдаёт null, то есть редактор открывается пустым; строка попадает в список как «Черновик» (is_sent false, is_active false), а не «Отправлен»; идемпотентность — без живого черновика возвращается 0 и ничего не меняется, второй вызов подряд не трогает уже сохранённую строку; отмена не задевает другую локацию и соседнего персонажа; уже отправленная строка в той же локации сохраняет sent_at; вытеснение работает по-прежнему — отменённый черновик остаётся одним из десяти и идёт первым в списке. Маршрут D5: true/True/1 зовут archive_active_draft и никогда delete_active_draft; отсутствие параметра и false/False/0 по-прежнему жёстко удаляют (обратная совместимость кнопки «Очистить черновик»); два вызова с true — 204 и пустое тело оба раза; мусорное значение — 422 и ни одна из веток не вызывается; 403 на чужого персонажа и 401 без токена, в обоих случаях crud не трогается. Настоящих багов не найдено. pytest: файл — 72 passed; полный набор locations-service — 849 passed (было 829).
[LOG] 2026-09-13 21:05 — Reviewer: начал финальную проверку T15 — перечитал CLAUDE.md, reviewer.md, cross-service-validator, live-verification-auth, typescript-expert и весь файл фичи, включая поздние разделы 3.13 и задачи T19–T21.
[LOG] 2026-09-13 21:10 — Reviewer: автопроверки перезапущены самостоятельно, не со слов задач. tsc --noEmit — чисто; npm run build — успешно (30.25s); py_compile по всем изменённым backend-файлам — ок; pytest locations-service — 849 passed; pytest character-service — 835 passed, 1 skipped; nginx -t на dev-конфиге — ок, на prod-конфиге — ок (единственная ошибка на исходном файле — отсутствующий SSL-сертификат dev-машины, не дефект конфига); alembic current/heads — 036_add_post_drafts (head), таблица в БД совпадает со спецификацией 3.2.
[LOG] 2026-09-13 21:20 — Reviewer: контракты сверены по живому /openapi.json — все четыре пути черновиков публикуются ровно так, как их зовёт src/api/postDrafts.ts; поля PostDraftRead/PostDraftListItem совпадают с TS-типами один в один; keep_in_history присутствует как необязательный boolean с default false; URL шага 4.5 в character-service совпадает с фактическим путём D7 (LOCATIONS_SERVICE_URL резолвится в http://locations-service:8006).
[LOG] 2026-09-13 21:35 — Reviewer: живая проверка через шлюз под реальным JWT. Отправка в несоседнюю локацию даёт 400 «Целевая локация не является соседней», и черновик после отказа цел. Отмена с keep_in_history=true — 204, D3 возвращает null, строка остаётся в списке как «Черновик», следующий пост в той же локации заводит НОВУЮ строку и отменённый текст не трогает. Успешная отправка архивирует черновик как «Отправлен». Пустой текст удаляет живую строку, 100001 символ даёт русскую 400. Вытеснение держит ровно 10 строк. Лимит Nginx на автосейв реально срабатывает — 867 ответов 429 после исчерпания burst.
[LOG] 2026-09-13 21:45 — Reviewer: безопасность. Без токена все маршруты, включая D7, отдают 401. Чужой персонаж — 403 даже под админом (владение выше роли, это правильно). Чужая строка по id — 403 и без утечки текста, а сама строка после отклонённого DELETE остаётся в БД. D7 без locations:delete — 403 «Недостаточно прав», с правом — 200 и count, повторный вызов — count 0. Секретов в логах нет, SQL только через bound-параметры, новой XSS-поверхности нет.
[LOG] 2026-09-13 21:55 — Reviewer: найден блокирующий дефект. Диалог «Заменить текст в поле ввода?» обещает «Текущий текст останется в черновиках», но вставка из вкладки «Черновики» запускает обычный автосейв в тот же живой слот — строка перезаписывается, и текущий текст исчезает бесследно. Воспроизведено вживую: живая строка id=216 с «ТЕКСТ A» после вставки вернулась тем же id=216 с «ТЕКСТ B», и в списке черновиков не осталось ни одной строки с «ТЕКСТ A». Это ровно та потеря текста, ради которой делалась фича, да ещё и с ложным обещанием в интерфейсе. Сам не чинил — правка меняет поведение и требует аккуратности с гонкой автосейва.
[LOG] 2026-09-13 22:00 — Reviewer: браузерная проверка выполнена НЕ была — расширение Claude-in-Chrome в этой сессии недоступно. Всё проверено через API-шлюз, компиляцию модулей во Vite и прямые запросы к MySQL. Непроверенным осталось: срабатывание автосейва один раз за окно debounce в живом редакторе, чистота консоли, вёрстка на 360px, поведение при остановленном locations-service и сами модальные окна. Это честно зафиксировано в разделе 5.
[LOG] 2026-09-13 22:05 — Reviewer: тестовые данные убраны, состояние восстановлено (post_drafts пуст, тестовый пост 141 удалён, персонаж 765 возвращён в локацию 1306, временный аккаунт удалён, временные файлы в контейнере шлюза удалены).
[LOG] 2026-09-13 22:05 — Reviewer: проверка завершена, результат FAIL — один блокирующий дефект (перезапись текущего текста при вставке черновика) и два незначительных замечания. Остальные задачи T1–T14 и T16–T21 перепроверены и подтверждены.
[LOG] 2026-09-13 23:10 — Frontend Dev: начал правки после ревью — блокирующий дефект вставки черновика, T22 и T23.
[LOG] 2026-09-13 23:25 — Frontend Dev: блокирующий дефект исправлен. Вставка текста из «Черновиков» теперь сначала освобождает живой слот (`await archiveDraft()`), и только потом подставляет текст в поле. Порядок важен: `archiveDraft` снимает таймеры и инвалидирует висящие сохранения ДО запроса, а автосейв вставленного текста планируется уже после подтверждения, что слот свободен — гонки между ними нет, и следующее сохранение заводит НОВУЮ строку. `archiveDraft` теперь возвращает `Promise<boolean>`: при ошибке сервера он откатывает локальное состояние (включая зеркало в localStorage) и возвращает false, а вставка отменяется с русским тостом — неудачная архивация не делает игроку хуже, чем было.
[LOG] 2026-09-13 23:30 — Frontend Dev: T22 — кнопка «Отмена» в форме поста переименована в «Очистить поле». Поведение, диалог подтверждения и archiveDraft() не тронуты. Вёрстка на 360px цела: кнопки живут во flex-wrap-группе внутри flex-col sm:flex-row, более длинная подпись помещается, горизонтального переполнения нет.
[LOG] 2026-09-13 23:40 — Frontend Dev: T23 — «Очистить черновик» убрана из формы поста и перенесена в шапку вкладки «Черновики» вместе со своим danger-диалогом и прежним текстом. В области ввода осталось ровно одно действие очистки — «Очистить поле», обратимое. Закрыта ловушка с зеркалом: DraftsPanel получил currentLocationId и по нему узнаёт строку, которая является текущим живым черновиком; удаление такой строки через D6 теперь дёргает onCurrentDraftDeleted, форма зовёт новый forgetLocalDraft() из хука (тот же код, что и markSent — формат ключа localStorage нигде не дублируется) и очищает поле. Удалённый текст больше не может вернуться при следующем заходе.
[LOG] 2026-09-13 23:50 — Frontend Dev: проверки. docker exec frontend npx tsc --noEmit — чисто (exit 0), npm run build — успешно (30.07s, только давняя ворнинга про чанк >500 kB). Живая проверка через шлюз на :80 под реальным JWT (chaldea@admin.com, персонаж 765, локация 1306): «ТЕКСТ A» сохранён строкой id=226, затем новый клиентский сценарий вставки (DELETE keep_in_history=true → 204, PUT с «ТЕКСТ B») дал НОВУЮ строку id=227, а в GET /locations/drafts остались обе — id=227 живая с «ТЕКСТ B» и id=226 архивная с «ТЕКСТ A»; GET /locations/drafts/226 вернул «ТЕКСТ A» дословно. Контрольный прогон без архивации воспроизвёл старую потерю: PUT A → id=228, PUT B → тот же id=228, строк с «ТЕКСТ A» не осталось. Все созданные строки удалены, в базе остался только предсуществовавший id=223.
[LOG] 2026-09-13 23:55 — Frontend Dev: замечание для PM — заголовок диалога подтверждения у переименованной кнопки остался прежним («Отменить пост?»), потому что T22 разрешал менять только подпись кнопки. Если нужна согласованность формулировок — это отдельная однострочная правка. Замечание №2 из ревью (счётчик на чипе «Черновики») не трогал: в T22/T23 оно не входит.

[LOG] 2026-09-13 23:58 — Frontend Dev: согласовал текст диалога подтверждения с новым названием кнопки: заголовок «Отменить пост?» → «Очистить поле?», подпись подтверждения «Убрать из поля» → «Очистить поле». Сообщение («Текст останется в черновиках…») и отмена «Продолжить писать» оставлены как есть, danger-стиль не добавлялся — действие обратимое. Диалог «Очистить черновик» в DraftsPanel не тронут. Правка только текстовая, логика не менялась. Проверки: docker exec frontend npx tsc --noEmit — чисто (exit 0), npm run build — успешно (31.29s, только давняя ворнинга про чанк >500 kB).

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

**Главное — текст больше нельзя потерять.** Исходный инцидент (пост в несоседнюю локацию →
400 → поле очищено → два часа работы уничтожены) закрыт тремя независимыми слоями защиты:

1. **Поле очищается только при реальном успехе.** Ошибка отправки больше не выглядит для формы
   как успех: `handleSubmitPost` / `handleSubmitNpcPost` пробрасывают ошибку, форма ловит её
   и оставляет текст и открытый редактор. Покрыт и путь постов от NPC.
2. **Черновики на сервере.** Таблица `post_drafts`, автосохранение с debounce 2.5 с и
   принудительным сбросом раз в 15 с, до 10 текстов на персонажа (живых и отправленных),
   вкладка «Черновики» со списком, вставкой и удалением. Плюс синхронное зеркало в
   `localStorage` — сеть может лежать, текст всё равно уцелеет.
3. **Необратимых действий не осталось.** «Очистить поле» откладывает текст в историю
   (`active = NULL`, `sent_at` остаётся NULL — в списке это «Черновик»), а не удаляет.
   Единственное действительно разрушительное действие — «Очистить черновик» — уехало во
   вкладку «Черновики», подальше от кнопки отправки, и подтверждается отдельным диалогом.

**Сопутствующее:** шесть английских текстов ошибок в `move_and_post` переведены на русский
(включая ту, что видел игрок); rate-limit на автосохранение в обоих nginx-конфигах;
каскадная уборка черновиков при удалении персонажа (D7 + шаг 4.5 в `character-service`),
устроенная так, что её сбой не может сорвать удаление персонажа.

**Тесты:** `locations-service` 849 (было 771), `character-service` 835. Обе сюиты зелёные.

### Что изменилось от первоначального плана

- **«Отмена» перестала удалять черновик** (решение пользователя по ходу работы). Наивное
  «просто не удалять» не подошло бы: текст остался бы в живом слоте и был бы затёрт следующим
  же автосохранением. Пришлось добавить `keep_in_history` на D5 и `crud.archive_active_draft`
  (задачи T19–T21, раздел 3.13) — освобождение слота, а не сохранение строки.
- **Кнопки переименованы и перегруппированы** (T22, T23): «Отмена» → «Очистить поле»,
  «Очистить черновик» перенесена в панель черновиков.
- **Ревью вернуло FAIL** и поймало вторую потерю текста того же класса: вставка черновика из
  списка затирала то, что было в поле, хотя диалог обещал обратное. Починено тем же приёмом
  (сначала отложить текущий текст, потом вставлять), с контрольным замером, что старое
  поведение действительно воспроизводилось.
- **Раздел 2 содержал фактическую ошибку**, найденную архитектором: утверждение из CLAUDE.md
  §10.7, что `locations-service` не проверяет JWT, неверно — проверяет, через `auth_http.py`.
  Исправлено на месте, расхождение занесено в `ISSUES.md`.

### Оставшиеся риски / follow-up

- **Живая проверка в браузере ревьюером не выполнялась** — расширение Chrome не было
  подключено, всё гонялось через API. Пользователь прощёлкал интерфейс сам и подтвердил, что
  всё работает, но это было **до** фикса вставки и переименования кнопок. Связку
  «написать текст → открыть "Черновики" → вставить другой → убедиться, что первый на месте»
  стоит проверить руками после выката.
- **Бейдж со счётчиком** на чипе «Черновики» (раздел 3.6) не реализован — непринципиально,
  требовал бы лишнего запроса на каждое открытие редактора.
- **Пять находок занесены в `ISSUES.md`** и намеренно не чинились здесь: `posts.content` типа
  `TEXT` (64 КБ) может молча обрезать длинный кириллический пост; `delete_character` не чистит
  `posts` / `post_likes` / `action_gates`; `move_and_post` коммитит пост **до** перемещения
  персонажа и списания выносливости; CLAUDE.md §10.7 устарел; имя прод-базы в документации
  не совпадает с реальным (`fogdatabase`, а не `mydatabase`).
- **Посты удалённых персонажей** остаются в локациях. Это осознанное решение (пост — часть
  общей ролевой истории, на него опираются посты других игроков), вопрос задан пользователю
  и остаётся открытым.
- **FEAT-157** заведена на три бага редактора, найденных по ходу: цвет, принудительно
  накладываемый на жирный и курсив при отрисовке поста; неработающая проверка правописания;
  дублирование слов при применении исправлений.

---

## 8. Follow-up — правки после ревью (added by PM)

| # | Description | Agent | Status | Files | Acceptance Criteria |
|---|-------------|-------|--------|-------|---------------------|
| **T22** | Rename the «Отмена» button in the post form to **«Очистить поле»**. User request — the old label no longer matches the behaviour (since T20 it clears the field and retires the text into «Черновики» rather than cancelling anything). Label text only; do not change behaviour, the confirm dialog flow, or `archiveDraft()`. Must land **after** T15's live verification so the review is not invalidated. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCreateForm.tsx` | Button reads «Очистить поле». Behaviour unchanged. `npx tsc --noEmit` + `npm run build` pass. Layout intact at 360 px (the new label is longer than «Отмена»). |

| **T23** | Move «Очистить черновик» out of the post form and into the «Черновики» tab. User request — it resolves the two-similar-buttons problem: the input area keeps exactly one clearing action («Очистить поле», reversible), and all management of stored texts lives in the panel. Keep the destructive copy and `danger` styling wherever it ends up. **Critical — must be handled, not discovered later:** the panel's existing per-row «Удалить» calls D6 (delete-by-id) and does **not** clear the `localStorage` mirror. Deleting the *active* draft that way lets `usePostDraft`'s restore-on-mount resurrect it from the local copy on the next visit — a deleted text coming back is the mirror image of the bug this whole feature exists to fix. Ensure that deleting the row which is the current live draft also drops its mirror (`usePostDraft` already has the right local bookkeeping in `archiveDraft`/`markSent`; expose or reuse it rather than duplicating the key format). | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCreateForm.tsx`, `.../DraftsPanel.tsx`, `src/hooks/usePostDraft.ts` | «Очистить черновик» no longer appears in the post form. Deleting the current live draft from the panel clears both the server row and the browser mirror — verified by deleting it, leaving the location, returning, and confirming the field is empty. Other rows behave as before. `npx tsc --noEmit` + `npm run build` pass. 360 px layout intact. |

**Примечание:** T22 и T23 делаются вместе (обе трогают `PostCreateForm.tsx`) и обе — после T15.

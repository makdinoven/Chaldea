# FEAT-158: Раздел модерации постов недоступен и показывает пустые данные

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-13 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

**Блокирует FEAT-159** (редактирование постов): заявки на гейты складывать некуда,
пока раздел модерации не работает.

---

## 1. Feature Brief (filled by PM — in Russian)

Два независимых бага в одном разделе. Сообщил пользователь: «запрос удаления поста есть,
в админке модерация постов выкидывает на главную».

### Баг 1 — клик по «Модерации» выбрасывает на главную

Маршрут `/admin/moderation` требует разрешение **`moderation:read`, которого не существует**.
По всему репозиторию эта строка встречается ровно один раз — в объявлении самого маршрута
(`services/frontend/app-chaldea/src/components/App/App.tsx:221-225`). Ни одна из 26 миграций
user-service не заводит модуль `moderation`.

Механика отказа: админ получает все разрешения автоматически, но **выборкой из таблицы
`permissions`** (`services/user-service/crud.py:14-35`) — нет строки, нет и разрешения.
`ProtectedRoute` (`.../ProtectedRoute/ProtectedRoute.tsx:56-58`) не имеет обхода для роли
админа и делает `<Navigate to="/home" replace />`.

При этом плитка «Модерация» в админке **видна**, потому что `AdminPage.tsx:82-84` фильтрует
через `role === 'admin' || hasModuleAccess(...)` — обход для админа там есть, а в
`ProtectedRoute` его нет. Поэтому плитка есть, а клик по ней выбрасывает.

Бэкенд в порядке: все шесть эндпоинтов существуют и защищены `get_admin_user`
(`services/locations-service/app/main.py:2151-2207`), nginx проксирует верно, фронт зовёт
правильные пути.

**Решение пользователя:** чинить **правильно**, а не быстрым обходом по роли — завести
разрешения миграцией и перевести эндпоинты на проверку разрешений, как требует CLAUDE.md §10.13
(«при добавлении нового модуля/эндпоинта создать разрешения в таблице `permissions`»).
Сейчас код нарушает собственный стандарт проекта, и на следующем админ-разделе мина повторится.

**Важно:** в user-service **нет эндпоинта, создающего строки разрешений** — есть только
`GET /permissions` и назначение существующих. Значит нужна Alembic-миграция.

### Баг 2 — раздел был бы пустым даже после починки

Расхождение контрактов, проверено с обеих сторон:

| Фронт ждёт (`AdminModerationPage.tsx:14-34`) | Бэкенд отдаёт (`schemas.py:723-749`) |
|---|---|
| `character_id`, `character_name` | `user_id` |
| `reporter_character_id`, `reporter_character_name` | `user_id` |
| вложенный `post: { content, character_name, created_at }` | `post_content`, `post_character_id`, `post_location_id` |

В итоге `req.post` всегда `undefined`, и на экране рендерится «Пост удален» и «Неизвестный»
(`AdminModerationPage.tsx:188, 195, 256, 263`).

Просто переименовать поля **нельзя**: таблицы модерации хранят `user_id`, а не `character_id`
(`alembic/versions/016_add_post_moderation.py:28, 42`), поэтому имени персонажа на сервере
физически нет. Нужен либо запрос в character-service, либо join.

### Баг 3 (найден при анализе гейтов) — удаление поста не отзывает выданные им права

Модерация удаляет пост сырым `DELETE FROM posts` (`crud.py:2641`, `:2671`), а внешний ключ
`action_gates.post_id` стоит на **`ON DELETE SET NULL`** (`models.py:184`). Строки гейтов
переживают удаление со статусом `open` — игрок по-прежнему может атаковать, собирать ресурсы
и входить в подземелье по правам, выданным удалённым постом.

**То есть наказание за абузный пост сегодня не работает.** Это существующая проблема,
не связанная с багами 1-2, но чинить её логично здесь же: FEAT-159 сделает её критичной
(при отклонении заявки на гейт права обязаны исчезать).

### Edge Cases
- Модератор (не админ) — бэкенд пускает и админа, и модератора (`auth_http.py:46-55`).
  Новые разрешения должны сохранить это, а не сузить доступ.
- Существующие установки: миграция должна выдать новые разрешения нужным ролям, иначе после
  выката раздел останется недоступен уже по другой причине.
- Пост удалён, а заявка на него осталась — фронт должен показать это внятно, а не «Неизвестный».
- Персонаж удалён, а его заявка осталась — имя не резолвится.

### Вопросы к пользователю
- [x] Чинить разрешения быстро (по роли) или правильно (миграция + `require_permission`)?
      → **Правильно, через миграцию.**

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

_Pre-analysis by PM is in section 1. The Architect re-verified every file:line reference against
the current code; corrections and the full permission-registration audit are in section 3.0 and 3.5._

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Verification of section 1 against current code (line drift corrected)

| Claim in section 1 | Verified | Correction |
|---|---|---|
| `moderation:read` declared only in `App.tsx:221-225` | YES | route block is `App.tsx:221-225`; the `requiredPermission` itself is on **line 222** |
| No migration registers module `moderation` | YES | all 26 user-service migrations **plus** `locations-service/app/alembic/versions/004_game_time_config.py` audited — see 3.5 |
| Admin perms come from a `permissions` SELECT | YES | `services/user-service/crud.py:14-35`; admin branch at `crud.py:31-33` |
| `ProtectedRoute` has no admin bypass | YES | file is `components/`**`CommonComponents`**`/ProtectedRoute/ProtectedRoute.tsx`, permission check at **lines 73-75** (not 56-58) |
| `AdminPage.tsx:82-84` has `role === 'admin' \|\|` | YES | `visibleSections` filter, lines 82-84. The same bypass also appears at lines ~57, ~60, ~72 (badge-count fetches) |
| Six moderation endpoints guarded by `get_admin_user` | PARTLY | only the **four admin** endpoints use `get_admin_user` (`main.py:2151, 2160, 2169, 2189`). The two player endpoints use `get_current_user_via_http`: `main.py:2107` `POST /locations/posts/{post_id}/request-deletion` and `main.py:2128` `POST /locations/posts/{post_id}/report` — correct as-is, must stay open to ordinary players |
| `get_admin_user` admits admin + moderator | YES | `locations-service/app/auth_http.py:46-55`. A `require_permission` factory already exists in the same file at `auth_http.py:72-82` |
| Frontend/backend contract mismatch | YES | `AdminModerationPage.tsx:6-33` vs `schemas.py:723-751`. The component lives in `components/AdminModerationPage/`, not `components/Admin/` |
| Post deleted by raw `DELETE FROM posts` | ALMOST | it is a SQLAlchemy **bulk** `delete(Post)` (`crud.py:2641`, `crud.py:2671`). Effect is identical — a bulk delete bypasses ORM cascades, so the DB-level FK rule is what applies |
| `action_gates.post_id` is `ON DELETE SET NULL` | YES | `models.py:`**`185`** (not 184) |

Additional facts established for this design:

- `crud.expire_action_gates()` (`crud.py:1079-1088`) is the existing "revoke gates" primitive — a raw `UPDATE action_gates SET status='expired' … WHERE status='open'`. Bug 3 reuses its shape.
- `crud._fetch_character_brief_map()` (`crud.py:5490-5521`) already batch-resolves `{character_id: {name, avatar}}` from character-service, deduping ids and swallowing failures. Bug 2 reuses it — no new character helper.
- `locations-service` has **no** `USER_SERVICE_URL` in `app/config.py`, but every field there carries a default, so adding one requires **no** docker-compose / env change ⇒ **no DevSecOps task in this feature**.
- `user-service` exposes `GET /users/{user_id}` (`main.py:2162`) returning `UserRead` incl. `username`. There is no batch users endpoint.
- There is **no** player-facing `DELETE /locations/posts/{id}`. The only two code paths that delete a post are the two moderation review paths, so Bug 3 has exactly two call sites.

---

### 3.1 Bug 1 — permissions for the moderation module

**Decision: two permission strings, read/act split.**

| Permission | Guards | Rationale |
|---|---|---|
| `moderation:read` | `GET /locations/admin/moderation/deletion-requests` (`main.py:2151`), `GET /locations/admin/moderation/reports` (`main.py:2160`) | matches the string already hardcoded at `App.tsx:222` — no frontend route change needed |
| `moderation:review` | `PUT /locations/admin/moderation/deletion-requests/{id}/review` (`main.py:2169`), `PUT /locations/admin/moderation/reports/{id}/review` (`main.py:2189`) | reviewing **destroys a post**; it must be separable from merely reading the queue |

The two player POSTs (`request-deletion`, `report`) keep `get_current_user_via_http` — **unchanged**. They are ordinary-player actions and must never require a moderation permission.

**Role grants (critical — must not narrow today's access).** Today `get_admin_user` admits `admin` **and** `moderator`. Therefore:

| Role | role_id | `moderation:read` | `moderation:review` |
|---|---|---|---|
| Admin | 4 | automatic (`get_effective_permissions` returns every row of `permissions`) | automatic |
| Moderator | 3 | **granted explicitly by the migration** | **granted explicitly by the migration** |
| Editor | 2 | not granted (see Q1 in 3.8) | not granted |
| User | 1 | no | no |

Net effect on access: **identical to today** for admin and moderator; editors gain nothing (they have no backend access today either).

**Migration.** `services/user-service/alembic/versions/0027_add_moderation_permissions.py`, `revision = '0027'`, `down_revision = '0026'`. Copy the idempotent SELECT-then-INSERT shape of `0026_add_origin_permissions.py` verbatim. Do **not** hardcode permission ids — ids are hardcoded only in the pre-0013 migrations; everything from 0013 on uses `LAST_INSERT_ID()`, and we follow that.

```
PERMISSIONS = [
    ("moderation", "read",   "Просмотр очереди модерации постов"),
    ("moderation", "review", "Рассмотрение жалоб и запросов на удаление постов"),
]
ROLE_ACTIONS = {3: ["read", "review"]}   # admin (4) implicit; editor (2) none
```

`downgrade()` deletes the `role_permissions` rows, then the `permissions` rows, for `module='moderation'` (same as 0026).

**Rollback plan.** `alembic downgrade 0026` removes both rows; a migration rollback must be accompanied by a code rollback, otherwise the four endpoints 403 for everyone. Both ship in the same commit and migrations run at container start (`alembic upgrade head` in the Dockerfile CMD, fail-fast), so a partially-migrated state is not reachable in steady state. Worst case during a rolling restart: a moderator gets a transient 403 — never a privilege escalation.

**Security.** No new endpoint, no new input surface, no rate-limiting change (admin-only, low traffic). The change strictly narrows *how* authorization is decided (role string → permission string). `require_permission` returns 403 with the generic Russian `"Недостаточно прав"` — no information leak.

---

### 3.2 Bug 1b — should `ProtectedRoute` gain an admin bypass? **No.**

**Decision: keep `ProtectedRoute` strict. Instead remove the `role === 'admin' ||` bypass from the `visibleSections` filter in `AdminPage.tsx:82-84`, so the two surfaces agree.**

Justification:

1. **The strict guard is what found this bug.** An admin bypass in `ProtectedRoute` would have opened the route while the backend still 403'd on `require_permission` — converting a loud, obvious redirect into a silent page full of failed requests. That is strictly worse.
2. **A bypass hides the next occurrence.** With one, a future unregistered permission stays invisible until a *moderator* complains; without one, the first admin click surfaces it.
3. **The asymmetry is the reported symptom.** Removing the bypass in `AdminPage` makes tile visibility an exact preview of route access: a module whose permissions are missing shows **no tile**, so there is no dead link to click.
4. **It is behaviour-preserving.** `hasModuleAccess()` is permission-derived and admins receive every registered permission automatically, so after task 1 lands admins see exactly the tiles they see today.

**Scope of the removal: the `visibleSections` filter only** (`AdminPage.tsx:82-84`). The three `role === 'admin' ||` guards inside the badge-count `useEffect` (lines ~57, ~60, ~72) are deliberately left alone — they gate best-effort count fetches whose failures are already swallowed by `.catch(() => {})`, and changing them is diff for no behavioural gain. Documented here as intentional.

---

### 3.3 Bug 2 — contract alignment and name resolution

**Decision: fix the backend to carry the names, and rewrite the frontend types to the backend's flat shape. Do not change the moderation tables.**

Rejected alternatives:

- *Add `character_id` columns to `post_deletion_requests` / `post_reports`* — a schema change plus a backfill that is not computable for historical rows (a user may have had several characters). Rejected.
- *Change only the frontend to show raw ids* — the moderator screen would read «Запросил: 412», unusable for the actual moderation job. Rejected.

**Server-side enrichment, purely additive** (no existing field renamed or removed — nothing else consumes these schemas, but additive keeps the deploy order free). `PostDeletionRequestRead` and `PostReportRead` each gain:

| Field | Type | Source |
|---|---|---|
| `post_character_name` | `Optional[str]` | character-service, via existing `_fetch_character_brief_map` on `post.character_id` |
| `post_created_at` | `Optional[datetime]` | `posts.created_at` — already joined, simply not selected today |
| `requester_username` | `Optional[str]` | user-service `GET /users/{user_id}` |

Existing `id`, `post_id`, `user_id`, `reason`, `status`, `created_at`, `reviewed_at`, `post_content`, `post_character_id`, `post_location_id` all stay. Both schemas keep `class Config: orm_mode = True` (**Pydantic v1** — no `model_config`).

**Name resolution — where and how.**

- **Post author (character):** reuse `crud._fetch_character_brief_map(ids)` unchanged. It already dedupes with `set()`, uses a 5s timeout, and degrades to `{"name": ""}` on failure. Map an empty name to `None` in the response.
- **Requester (user):** new sibling helper in the same file, `crud._fetch_username_map(user_ids) -> Dict[int, Optional[str]]`, mirroring `_fetch_character_brief_map` exactly (dedupe, `httpx.AsyncClient(timeout=5.0)`, `logger.warning` + `None` on failure), calling `{settings.USER_SERVICE_URL}/users/{uid}`. Add `USER_SERVICE_URL: str = "http://user-service:8000"` to `locations-service/app/config.py` (defaulted ⇒ no compose/env change).

**N+1 risk — bounded and accepted, with mandatory mitigations.** Both list endpoints filter `status == 'pending'`, so the queue is inherently small and drains as moderators work. Both helpers are called **once per request with a deduped id set**, not once per row, so the worst case is `distinct(post.character_id) + distinct(user_id)` HTTP calls, not `2 × rows`. The implementer must:

- dedupe before calling (`set()`), skipping `None` ids;
- keep the 5s timeout and the non-fatal failure policy → the field comes back `null`, never a 500;
- run both enrichment passes **after** the SQL query completes, so a slow character-service does not hold a DB session open.

A batch lookup endpoint in character-service / user-service is the real fix; it is **out of scope** here and must be logged to `docs/ISSUES.md` (MEDIUM).

**Missing-entity display (Russian, mandatory):**

| Condition | Server returns | UI shows |
|---|---|---|
| post row gone (`outerjoin` miss) | `post_content`, `post_character_name`, `post_created_at` all `null` | «Пост уже удалён» in the preview block; the author line is hidden entirely |
| post exists, character gone or lookup failed | `post_character_name = null` | «Персонаж #{post_character_id}» |
| requester gone or lookup failed | `requester_username = null` | «Пользователь #{user_id}» |

Note: on a *deletion request* the post author and the requester are normally the same person (a player asking to delete their own post); on a *report* they are normally different. The existing Russian labels («Пост от», «Запросил», «Пожаловался») stay.

**Frontend.** Replace the `DeletionRequest` / `Report` / `PostPreview` interfaces (`AdminModerationPage.tsx:6-33`) with a flat shape mirroring the backend exactly; the `req.post?.` / `report.post?.` accesses (lines 188, 191, 195, ~250-263) disappear along with `PostPreview`. Constraints: **no `React.FC`** (the component is already a plain arrow function — keep it), **Tailwind only** (no SCSS added), keep the existing responsive classes (`flex-col sm:flex-row`, `grid-cols-1 sm:grid-cols-2`) and verify at 360px. Both `catch` blocks already raise Russian toasts — keep them and add a 403 branch: «Недостаточно прав для раздела модерации».

---

### 3.4 Bug 3 — deleting a post must revoke the gates it granted

**Decision: expire, do not delete. In scope for this feature.**

New primitive in `locations-service/app/crud.py`, modelled on `expire_action_gates` (`crud.py:1079`):

```
async def expire_action_gates_for_post(session, post_id: int) -> None:
    """Revoke rights granted by a post that is being removed (FEAT-158)."""
    UPDATE action_gates SET status='expired'
    WHERE post_id = :p AND status = 'open'
```

Called **immediately before** the post row is deleted, in both paths:

- `review_deletion_request`, inside the `action == "approve"` branch, before `crud.py:2641`;
- `review_report`, inside the `action == "resolve"` branch, before `crud.py:2671`.

**Order matters:** the FK is `ON DELETE SET NULL`, so after the delete the `post_id` link is gone and the rows can no longer be found. The helper must **not** `commit()` — the enclosing review function already commits, which keeps revocation and deletion in **one transaction**.

Explicit decisions:

- **`open` → `expired`, not row deletion.** The row survives as an audit trail of what was granted and revoked, and `post_id` naturally becomes `NULL` on the subsequent delete.
- **`consumed` rows are left untouched.** The action already fired; there is nothing to revoke, and rewriting that history would corrupt the record.
- **`reject` / `dismiss` paths touch nothing** — the post survives, so its gates must survive too.
- **The FK stays `ON DELETE SET NULL`.** Switching it to `CASCADE` would destroy the audit trail and needs a schema migration; expiring in application code is the smaller, reversible change. Considered and rejected.

**Why here rather than its own feature:** FEAT-159 turns a *rejected gate request* into a case where rights must provably not survive, and it reuses this exact primitive. Shipping it separately would leave FEAT-159 blocked on a one-function change.

---

### 3.5 Audit — every `requiredPermission` in `App.tsx` vs the registered permission set

Registered set assembled from **all 26 user-service migrations plus `locations-service/app/alembic/versions/004_game_time_config.py`**:

`users:read|update|delete|manage`, `items:create|read|update|delete`, `characters:create|read|update|delete|approve`, `skills:create|read|update|delete`, `locations:create|read|update|delete`, `rules:create|read|update|delete`, `photos:upload`, `notifications:create`, `battles:manage`, `races:create|update|delete`, `chat:delete|ban`, `skill_trees:create|read|update|delete`, `npcs:create|read|update|delete`, `mobs:manage`, `archive:create|read|update|delete`, `perks:create|read|update|delete|grant`, `titles:create|read|update|delete|grant`, `professions:create|read|update|delete|manage`, `tickets:read|manage|reply`, `battlepass:create|read|update|delete`, `cosmetics:create|read|update|delete`, `dungeons:view|create|edit|delete`, `gathering:create|read|update|delete`, `origins:create|read|update|delete`, `gametime:read|update`.

All 30 `requiredPermission` occurrences in `App.tsx` (lines 132-330) were checked:

| Result | Strings |
|---|---|
| **Registered — OK (29 occurrences, 25 distinct)** | `characters:approve`, `characters:read`, `characters:update`, `locations:read`, `locations:update`, `skills:read`, `skill_trees:read`, `items:read`, `rules:read`, `users:manage`, `races:create`, `origins:read`, `gametime:read`, `npcs:read`, `mobs:manage`, `battles:manage`, `archive:read`, `perks:read`, `titles:read`, `professions:read`, `battlepass:read`, `cosmetics:read`, `dungeons:view`, `dungeons:create`, `dungeons:edit`, `tickets:read` |
| **UNREGISTERED — the bug** | `moderation:read` (`App.tsx:222`) — **the only one** |

`AdminPage.tsx`'s `sections[]` `module` values were audited the same way: every one maps to at least one registered permission except `moderation`. **No other latent time bomb exists in either file.**

**Two findings worth recording anyway (not defects; no fix in this feature):**

1. **`gametime:read|update` are seeded from a locations-service migration** (`004_game_time_config.py:45-66`), not from user-service — the only permissions in the system registered outside the RBAC owner. It works (single shared MySQL database) but it is inconsistent with CLAUDE.md §10.13, and it makes "grep `user-service/alembic` for the permission set" — the exact check that would have caught this bug — unreliable. → `docs/ISSUES.md`, priority LOW.
2. **`gametime` is granted to the `admin` role only** (`004_game_time_config.py:56-62` joins `roles r WHERE r.name = 'admin'`), so a **moderator cannot open `/admin/game-time`**. Tile and route agree, so this is a product question, not a defect. → `docs/ISSUES.md`, priority LOW, plus Q3 below.

**Structural guard against the next occurrence:** QA task 7 adds a test that parses every `requiredPermission="…"` out of `App.tsx` and asserts each is registered by a migration. It `pytest.skip`s when the frontend file is not reachable from the test's working directory, so it can never break a per-service CI job.

---

### 3.6 Data flow (after the fix)

```
Admin/Moderator clicks «Модерация постов»
  └─ AdminPage visibleSections: hasModuleAccess(permissions, 'moderation')   ← tile shown only if the permission exists
  └─ ProtectedRoute requiredPermission="moderation:read"                     ← strict, no admin bypass
       └─ GET /locations/admin/moderation/deletion-requests   (nginx → locations-service)
            └─ require_permission("moderation:read")
                 └─ GET user-service /users/me → {role, permissions[]}       ← admin: every row of `permissions`
            └─ SELECT PostDeletionRequest OUTER JOIN Post WHERE status='pending'
            └─ _fetch_character_brief_map({post.character_id})  → character-service /characters/{id}/short_info
            └─ _fetch_username_map({req.user_id})               → user-service   /users/{id}
            └─ 200 [{…, post_content, post_character_name, post_created_at, requester_username}]

Moderator presses «Одобрить»
  └─ PUT …/deletion-requests/{id}/review {action:"approve"}
       └─ require_permission("moderation:review")
       └─ expire_action_gates_for_post(post_id)      ← open → expired    (same transaction)
       └─ DELETE FROM posts WHERE id = post_id       ← FK sets action_gates.post_id = NULL
       └─ req.status = 'approved'; COMMIT
```

---

### 3.7 Bug 4 (found during implementation) — approve/resolve has ALWAYS returned 500

**Reported by the Backend Developer, reproduced on a clean checkout of `crud.py` at HEAD — not caused by anything in tasks 1-6.**

`post_deletion_requests.post_id` and `post_reports.post_id` are `ON DELETE CASCADE` (`models.py:263`, `models.py:276`; created that way in `app/alembic/versions/016_add_post_moderation.py:27-28` and `:40-41`). In `review_deletion_request` / `review_report` the handler deletes the post **and then** updates `status` / `reviewed_by_user_id` / `reviewed_at` on the moderation row it is holding. The cascade has already removed that row, so the flush raises

```
sqlalchemy.orm.exc.StaleDataError: UPDATE statement on table 'post_reports'
expected to update 1 row(s); 0 were matched
```

the transaction rolls back, the post survives, the request stays `pending`, and the client gets a 500. `reject` / `dismiss` are unaffected (nothing is deleted).

**This is why FEAT-158's live verification could not exercise the approve/resolve buttons at all.** The redirect (bug 1) hid the page; had anyone reached it, every «Одобрить» and «Решена» click would have failed. Task 10's live walkthrough was blocked by this and is **unblocked** by the tasks below.

**Decision: change both FKs to `ON DELETE SET NULL`** (PM's call, and it is the right one — a moderation system that destroys its own decision history on the one action that matters is worse than a nullable column). Designed to, with three corrections the FK swap alone does not cover:

#### 3.7.1 The migration is not a one-liner — three concrete obstacles

1. **The FKs are unnamed.** `016_add_post_moderation.py` declares them inline as `sa.ForeignKey('posts.id', ondelete='CASCADE')` with no `name=`, so MySQL auto-generated them (`post_deletion_requests_ibfk_1` / `post_reports_ibfk_1` on a normally-ordered create, but that is **not guaranteed**). The migration **must introspect** — `sa.inspect(bind).get_foreign_keys('post_deletion_requests')`, pick the entry whose `constrained_columns == ['post_id']`, and use its `name` — never hardcode. If no such FK is found the migration must skip that table rather than fail (some installs may already have been repaired by hand).
2. **`post_id` is `nullable=False`.** MySQL refuses `ON DELETE SET NULL` on a `NOT NULL` column (`ERROR 1830: Column 'post_id' cannot be NOT NULL: needed in a foreign key constraint 'SET NULL'`). The column must be made nullable, and it can only be altered while the FK is dropped. Required order per table: **drop FK → `alter_column(post_id, nullable=True)` → create FK named explicitly with `ondelete='SET NULL'`.** Give the new constraints stable names so future migrations do not have to introspect again: `fk_post_deletion_requests_post_id`, `fk_post_reports_post_id`.
3. **`uq_post_report_user` (`post_id`, `user_id`) is unaffected** — MySQL permits multiple rows with `NULL` in a unique index, so orphaned reports cannot collide, and a user can still report a *new* post afterwards. Verified against `models.py:284-286`. No change needed.

`downgrade()` reverses it symmetrically and must be genuinely runnable: drop the named FK → `UPDATE <table> SET post_id = <?> WHERE post_id IS NULL` … which is **impossible** (the original post ids are gone). Therefore downgrade must **delete the orphaned rows** (`DELETE FROM post_deletion_requests WHERE post_id IS NULL`, same for `post_reports`) before `alter_column(..., nullable=False)` and recreating the FK with `ondelete='CASCADE'`. This is lossy **by necessity** and must be stated in the migration docstring — downgrading discards exactly the audit rows the upgrade was added to preserve.

Revision: `037_post_moderation_fk_set_null`, `down_revision = '036_add_post_drafts'` (verified current head of locations-service). `models.py:263` and `models.py:276` must be updated in the same task to `ondelete="SET NULL", nullable=True` so the ORM matches the schema.

#### 3.7.2 The handler does need changes — the FK swap alone is NOT sufficient

Verified against the actual code, three separate problems remain after the FK change:

1. **`post_id: int` is non-`Optional` in both read schemas** (`schemas.py:724`, `schemas.py:739`). The handler does `await session.refresh(req)` after commit (`crud.py:2647`, `crud.py:2676`), which reloads `post_id` as `NULL`, and `main.py:2180-2188` / `:2200-2208` then build the response dict from it. Pydantic v1 would raise `none is not an allowed value` → **still a 500, just from a different line**. Both schemas must become `post_id: Optional[int] = None`.
2. **`expire_action_gates_for_post` (task 6) must read `post_id` into a local before the delete.** After the delete the attribute is stale in-session and `NULL` in the DB. The task-6 call site is already before `delete(Post)`, so capturing `post_id = req.post_id` at the top of the branch is the safe form — the implementer must confirm it, not assume it.
3. **A stale row must not re-run the delete.** With `SET NULL`, a moderation row can now reach `review_*` with `post_id IS NULL` (see 3.7.3). `delete(Post).where(Post.id == None)` compiles to `WHERE id IS NULL`, matches nothing and is harmless, but it is accidental correctness. Guard it explicitly: if `req.post_id is None`, skip both the gate expiry and the delete, just record the decision and return 200.

No reordering of `status` assignment vs. delete is required once the row survives — the existing order is fine.

#### 3.7.3 What the queue does with `post_id IS NULL` rows

- **The row that was just decided drops out on its own.** `get_pending_deletion_requests` / `get_pending_reports` filter `status == 'pending'` (`crud.py:2575`, `crud.py:2601`); an approved/resolved row is no longer pending. Confirmed.
- **Sibling rows do not.** Two players can report the same post. Resolving report A deletes the post; under the old CASCADE report B vanished silently, under `SET NULL` it survives as `pending` with `post_id = NULL`. This is a **new** (and correct) visibility of rows that used to be destroyed.
- **Rendering is already covered.** The 3.3 fallback triggers on `post_content == null`; with `post_id = NULL` the `outerjoin` in `crud.py:2573-2578` / `:2599-2604` simply matches nothing, so `post_content`, `post_character_name` and `post_created_at` all come back `null` and the UI shows «Пост уже удалён». `_fetch_character_brief_map` receives no id for such rows (`None` is skipped per 3.3). Confirmed — no additional frontend work beyond task 5.
- **Queue hygiene — decision:** when a review deletes a post, **also close the sibling pending rows for that same post** in both tables, in the same transaction: deletion requests → `approved`, reports → `resolved`, with `reviewed_by_user_id` = the acting moderator and `reviewed_at` = now. Rationale: the outcome each of them asked for (the post is gone) has in fact been achieved by a real moderator decision, so recording it that way is honest, keeps the queue clean, and preserves the audit trail. The alternative — leaving them `pending` so a human dismisses each one — is also defensible; see Q4. The `post_id IS NULL` fallback stays regardless, because rows orphaned **before** this feature ships will still exist on prod.

#### 3.7.4 Ordering and risk

Tasks 11-12 must land **together** — the migration without the schema fix trades one 500 for another. The migration is forward-safe on a database where the bug has never been worked around (no manual FK edits) and is idempotent-by-introspection where it has. Deploy order is the usual one: `alembic upgrade head` runs in the locations-service container CMD before uvicorn serves traffic, and both the migration and the code ship in one commit.

---

### 3.8 Open questions for PM (designed around; assumptions stated)

1. **Should the Editor role (level 20) receive `moderation:read`?** Assumption: **no** — editors have no moderation access today (`get_admin_user` rejects them), and read-only visibility into user reports is a policy decision, not part of a bug fix. Trivially added later with a two-line migration.
2. **Who is «Запросил» — the user account or a character?** Assumption: **the user account's `username`**, because that is what the table stores and it survives character deletion. Showing a character would require guessing which of the user's characters was active at request time — data we do not have.
3. **Should a moderator be able to open `/admin/game-time`?** Assumption: **leave as is** (admin-only). Logged to ISSUES, not changed here.

4. **Sibling pending moderation rows on a post that a moderator just deleted — close them automatically or leave them for a human?** Assumption: **close them** (deletion requests → `approved`, reports → `resolved`, attributed to the acting moderator), because the outcome they asked for has actually been achieved and leaving them pending clutters the queue with rows whose post no longer exists. Under the old `CASCADE` these rows were silently destroyed, so any behaviour here is an improvement; the alternative (leave them `pending`, moderator dismisses each) is a one-line change if the user prefers it.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Ordering rationale: **tasks 1-3 are the redirect fix and can ship on their own** (task 3 is only reachable after 1 because `hasModuleAccess` needs the permission rows to exist). Tasks 4-5 fix the empty page, task 6 fixes the gates, tasks 7-9 are QA, task 10 is review.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | **Register the `moderation` module permissions.** Alembic migration `0027`, `down_revision='0026'`, idempotent SELECT-then-INSERT copied from `0026_add_origin_permissions.py`. Inserts `moderation:read` and `moderation:review` with Russian descriptions; grants both to role_id 3 (Moderator). Admin (4) needs no explicit grant. `downgrade()` removes role_permissions rows then permissions rows for `module='moderation'`. Do not hardcode permission ids. | Backend Developer | DONE | `services/user-service/alembic/versions/0027_add_moderation_permissions.py` (new) | — | `alembic upgrade head` and `alembic downgrade 0026` both succeed against a MySQL with 0026 applied; running upgrade twice is a no-op; `SELECT * FROM permissions WHERE module='moderation'` returns 2 rows and `role_permissions` has 2 rows for role_id=3; `python -m py_compile` passes |
| 2 | **Move the four moderation admin endpoints onto permission checks.** Replace `Depends(get_admin_user)` with `Depends(require_permission("moderation:read"))` on the two GETs (`main.py:2151`, `:2160`) and `Depends(require_permission("moderation:review"))` on the two PUTs (`main.py:2169`, `:2189`). `require_permission` is already imported-or-importable from `app/auth_http.py:72`. **Do not touch** the two player endpoints at `main.py:2107` and `main.py:2128`. | Backend Developer | DONE | `services/locations-service/app/main.py` | 1 | The four endpoints 403 for a `user`-role token, 200 for `moderator` and `admin`; the two player POSTs still work for a plain player; `python -m py_compile` passes |
| 3 | **Align admin tile visibility with route access.** Remove `role === 'admin' ||` from the `visibleSections` filter (`AdminPage.tsx:82-84`) so tiles are permission-driven only. Leave the three `role === 'admin' ||` guards in the badge-count `useEffect` alone (intentional, see 3.2). Do **not** add an admin bypass to `ProtectedRoute`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/Admin/AdminPage.tsx` | 1 | `npx tsc --noEmit` and `npm run build` both pass; logged in as admin, every tile that was visible before is still visible, including «Модерация постов»; clicking it reaches `/admin/moderation` instead of bouncing to `/home` |
| 4 | **Enrich the moderation list responses.** Add `USER_SERVICE_URL` (defaulted) to `config.py`. Add `_fetch_username_map(user_ids)` to `crud.py`, mirroring `_fetch_character_brief_map` (`crud.py:5490`): dedupe, `httpx.AsyncClient(timeout=5.0)`, `logger.warning` + `None` on failure. In `get_pending_deletion_requests` (`crud.py:2571`) and `get_pending_reports` (`crud.py:2597`), select `post.created_at` and run both enrichment passes once per request on deduped id sets **after** the query. Add `post_character_name`, `post_created_at`, `requester_username` (all `Optional`) to `PostDeletionRequestRead` and `PostReportRead` (`schemas.py:723-751`) — additive only, Pydantic v1 `orm_mode` preserved. An empty name from character-service maps to `None`. | Backend Developer | DONE | `services/locations-service/app/config.py`, `app/crud.py`, `app/schemas.py` | 2 | Both GETs return the three new fields; a request whose post was deleted returns all three post fields as `null` without a 500; character-service or user-service being down yields `null` names, not an error; number of outbound HTTP calls equals the count of *distinct* ids, verified in the QA test; `python -m py_compile` passes |
| 5 | **Rewrite the moderation page against the real contract.** Replace `PostPreview` / `DeletionRequest` / `Report` (`AdminModerationPage.tsx:6-33`) with flat interfaces mirroring the backend; drop every `req.post?.` / `report.post?.` access. Render the fallbacks from 3.3: «Пост уже удалён» (hide the author line entirely), «Персонаж #{id}», «Пользователь #{id}». Add a 403 branch to both `catch` blocks: «Недостаточно прав для раздела модерации». Tailwind only, no `React.FC`, keep/verify the 360px layout. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/AdminModerationPage/AdminModerationPage.tsx` | 4 | `npx tsc --noEmit` and `npm run build` pass; with real pending rows the page shows post text, author name, requester name and dates — no «Неизвестный» and no «Пост удален» for rows whose post exists; a row with a deleted post renders the fallback; no console errors; layout holds at 360px |
| 6 | **Revoke gates when a post is deleted.** Add `expire_action_gates_for_post(session, post_id)` to `crud.py` (shape of `expire_action_gates`, `crud.py:1079`; **no internal commit**) setting `status='expired'` for `post_id = :p AND status='open'`. Call it immediately **before** `delete(Post)` in the `approve` branch of `review_deletion_request` (`crud.py:2641`) and the `resolve` branch of `review_report` (`crud.py:2671`). Leave `consumed` rows untouched; the `reject`/`dismiss` branches must not call it. FK stays `ON DELETE SET NULL`. | Backend Developer | DONE | `services/locations-service/app/crud.py` | — (parallel with 1-5) | After approving a deletion for a post with an `open` gate, that gate row is `expired` with `post_id IS NULL`; a `consumed` gate stays `consumed`; rejecting leaves the gate `open`; revocation and deletion commit together (a failure rolls back both); `python -m py_compile` passes |
| 7 | **Pytest: permission registration + the App.tsx consistency guard.** Test that migration 0027 registers `moderation:read`/`moderation:review` and grants both to role_id 3, that an admin's effective permissions include them (extends the existing admin-has-everything assertion), and a guard test that parses every `requiredPermission="…"` from `App.tsx` and asserts each is registered by a migration — `pytest.skip` if the frontend file is not reachable from the test cwd. | QA Test | DONE | `services/user-service/tests/test_rbac_permissions.py`, new `services/user-service/tests/test_moderation_permissions.py` | 1 | Tests fail against the pre-0027 schema and pass after; the guard test fails if a bogus `requiredPermission` is introduced, and skips cleanly when `App.tsx` is absent |
| 8 | **Pytest: moderation endpoint authorization + response contract.** Cover the four admin endpoints: 401 without a token, 403 for `user` role, 200 for `moderator` **and** `admin` (explicitly assert moderator access is preserved), plus 403 for a moderator whose token lacks `moderation:review` on the PUTs. Cover the enriched response: names resolved from mocked character-service/user-service, `null` fallbacks when a post row is missing, `null` (not 500) when a downstream service errors or times out, and that outbound calls are deduped. Assert the two player POSTs remain reachable by a plain player. Follow the fixture style of `tests/test_rbac_enforcement.py` / `tests/test_endpoint_auth.py`. | QA Test | DONE | new `services/locations-service/app/tests/test_post_moderation.py` | 2, 4 | All cases pass; `pytest services/locations-service` is green |
| 9 | **Pytest: gate revocation on post deletion.** Approving a deletion request expires the post's `open` gates; resolving a report does the same; `consumed` gates are untouched; `reject`/`dismiss` leave gates `open`; gates belonging to other posts are unaffected; the expire+delete pair is atomic. Extend `tests/test_action_gates.py` or add a dedicated module. | QA Test | DONE | new `services/locations-service/app/tests/test_gate_revocation.py` | 6 | All cases pass; `pytest services/locations-service` is green |
| 10 | **Review.** Re-run `python -m py_compile` on every touched Python file, `npx tsc --noEmit` + `npm run build`, and the full pytest suites for user-service and locations-service. **Live verification is mandatory:** log in as admin, open `/admin/moderation`, confirm no redirect, real data rendered, zero console errors, 360px layout intact; then repeat as a **moderator** account to prove access was not narrowed. Verify the security checklist and that no new SCSS was introduced. Log the two audit findings from 3.5 and the batch-lookup follow-up from 3.3 into `docs/ISSUES.md`. | Reviewer | DONE | — | 1-9 | All automated checks pass **and** both live walkthroughs (admin + moderator) are recorded in section 5; `docs/ISSUES.md` updated |

**Parallelism:** task 6 is independent of 1-5 and can start immediately. Tasks 1 and 2 are the critical path for the redirect fix; task 3 unblocks the admin UI. Tasks 4-5 are sequential (frontend needs the contract). QA tasks 7-9 follow their respective backend tasks and can run in parallel with each other.

**No DevSecOps task:** `USER_SERVICE_URL` is added as a defaulted Pydantic setting, so no docker-compose, nginx, or env change is required. No new Python or npm dependency is introduced (`httpx` is already a locations-service dependency).


### Added after implementation started — Bug 4 (see 3.7)

Tasks 1-10 stand as designed. Tasks 11-14 are additions; **11 and 12 must land together.**

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 11 | **Migration: `post_id` FKs `CASCADE` → `SET NULL` on both moderation tables.** New locations-service revision `037_post_moderation_fk_set_null`, `down_revision='036_add_post_drafts'`. Per table: **introspect** the existing FK name via `sa.inspect(bind).get_foreign_keys(<table>)` picking `constrained_columns == ['post_id']` (the constraints from `016_add_post_moderation.py` are **unnamed** — MySQL auto-named them; do **not** hardcode `*_ibfk_1`), skip the table if no such FK exists; drop it; `alter_column('post_id', existing_type=sa.Integer(), nullable=True)` (MySQL rejects `SET NULL` on a `NOT NULL` column); recreate it named `fk_post_deletion_requests_post_id` / `fk_post_reports_post_id` with `ondelete='SET NULL'`. `downgrade()` must be runnable and is **lossy by necessity** — document that in the docstring: drop the named FK, `DELETE FROM <table> WHERE post_id IS NULL`, `alter_column(nullable=False)`, recreate with `ondelete='CASCADE'`. Update `models.py:263` and `models.py:276` to `ondelete="SET NULL", nullable=True` in the same commit. Do not touch `uq_post_report_user` (MySQL allows repeated NULLs — verified). | Backend Developer | DONE | `services/locations-service/app/alembic/versions/037_post_moderation_fk_set_null.py` (new), `services/locations-service/app/models.py` | — | `alembic upgrade head` then `downgrade 036_add_post_drafts` then `upgrade head` all succeed on MySQL; after upgrade, `SHOW CREATE TABLE` reports `ON DELETE SET NULL` and a nullable `post_id` on both tables; deleting a post leaves the moderation rows in place with `post_id IS NULL`; `python -m py_compile` passes |
| 12 | **Make the review handlers survive a surviving row.** (a) `post_id` → `Optional[int] = None` in `PostDeletionRequestRead` and `PostReportRead` (`schemas.py:724`, `:739`) — without this, `session.refresh()` reloads `post_id` as `NULL` and Pydantic v1 turns the old 500 into a new one. (b) In `review_deletion_request` (`crud.py:2623`) and `review_report` (`crud.py:2653`), capture `post_id = req.post_id` into a local **before** `delete(Post)`, and confirm the task-6 `expire_action_gates_for_post` call uses that local. (c) Guard the stale case: if `post_id is None`, skip both the gate expiry and the delete, record the decision, return 200. (d) In the same transaction, close sibling **pending** rows for the same post in both tables — deletion requests → `approved`, reports → `resolved`, with `reviewed_by_user_id` = acting moderator and `reviewed_at` = now (see 3.7.3 and Q4). Do not reorder the `status` assignment relative to the delete — it is correct once the row survives. | Backend Developer | DONE | `services/locations-service/app/crud.py`, `app/schemas.py` | 11, 6 | Approving a deletion request returns **200**, the post is gone, the moderation row survives with `status='approved'`, a populated `reviewed_at`/`reviewed_by_user_id` and `post_id IS NULL`; same for resolving a report; a sibling pending report on the same post comes back `resolved` rather than lingering in the queue; reviewing a row that already has `post_id IS NULL` returns 200 and deletes nothing; `reject`/`dismiss` unchanged; `python -m py_compile` passes |
| 13 | **Frontend: `post_id` is now nullable.** Type `post_id` as `number \| null` in the moderation interfaces and make sure nothing renders a bare `post_id`. The «Пост уже удалён» fallback from 3.3 already covers these rows (it keys off `post_content == null`) — verify, do not duplicate it. **If task 5 has not started, fold this into task 5 instead of opening a second diff.** | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/AdminModerationPage/AdminModerationPage.tsx` | 5, 12 | `npx tsc --noEmit` and `npm run build` pass; a queue containing a `post_id: null` row renders «Пост уже удалён» with no console error and no `null` leaking into the DOM |
| 14 | **Pytest: the approve/resolve path end to end.** A regression test that **fails on the pre-037 schema** and passes after. Cover: approving a deletion request returns 200 (not 500 / no `StaleDataError`), the post row is actually deleted, the moderation row survives with `status`, `reviewed_at` and `reviewed_by_user_id` set and `post_id IS NULL`; the same for resolving a report; tying into task 6 — that post's `open` action gates are `expired` while `consumed` ones are untouched and gates on other posts are unaffected; `reject`/`dismiss` still return 200 and delete nothing; a sibling pending report on the same post is closed; reviewing a row whose `post_id` is already `NULL` returns 200; and the queue endpoints render such a row with `post_content`/`post_character_name`/`post_created_at` all `null`. Extend the task-9 module or `tests/test_post_moderation.py` rather than opening a third file. | QA Test | DONE | `services/locations-service/app/tests/test_post_moderation.py` | 12 | All cases pass; `pytest services/locations-service` is green; the test demonstrably fails if migration 037 is reverted |

**Task 10 (Review) now also depends on 11-14**, and its live walkthrough — previously blocked by this bug — must explicitly click «Одобрить» on a real deletion request and «Решена» on a real report, confirm a 200 and the post disappearing, and confirm the decided row is gone from the pending queue.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-13
**Result:** PASS

Tasks 1-9 and 11-14 re-verified independently against the running dev stack. Every
claim in section 6 was re-derived from actual output rather than taken on trust.
FEAT-157's files (`PostCard.tsx`, `api/spellcheck.ts`, `useSpellCheck.ts`,
`SpellCheckPanel.tsx`, `PostCreateForm.tsx`) were excluded from this review.

#### Automated Check Results

| Check | Result | Actual output |
|---|---|---|
| `npx tsc --noEmit` (in `frontend` container) | **PASS** | zero output, exit 0 |
| `npm run build` (in `frontend` container) | **PASS** | `built in 36.10s`, exit 0 |
| `py_compile` — locations-service (`config.py`, `crud.py`, `main.py`, `models.py`, `schemas.py`, `alembic/versions/037_*.py`, `tests/test_post_moderation.py`, `tests/test_gate_revocation.py`) | **PASS** | `LOCATIONS_PY_COMPILE_OK` |
| `py_compile` — user-service (`alembic/versions/0027_*.py`, `tests/test_moderation_permissions.py`, `tests/test_rbac_permissions.py`) | **PASS** | `USER_PY_COMPILE_OK` |
| `pytest` locations-service (`--asyncio-mode=auto`, CI args) | **PASS** | `903 passed, 3 warnings in 14.72s` — matches the expected baseline exactly |
| `pytest` locations-service, new modules only | **PASS** | `54 passed` (`test_post_moderation.py` + `test_gate_revocation.py`) |
| `pytest` user-service | **PASS (expected state)** | `1 failed, 482 passed, 5 skipped in 55.69s`; the single failure is `test_profile_customization.py::TestGetUserCharacters::test_get_user_characters_success` — **the only** failure, pre-existing and unrelated |
| `pytest` user-service RBAC modules **with the repo mounted** (`chaldea-user-service` image, `-v repo:/repo`) | **PASS** | `88 passed` — **0 skipped**, i.e. the `App.tsx` guard really executes when the frontend file is reachable, as it will be in CI |
| Guard negative control | **PASS** | `requiredPermission="moderation:read"` temporarily replaced with `"bogusmodule:read"` -> `3 failed, 11 passed`; `App.tsx` restored, `git diff` on it is empty |
| `docker compose config` | **PASS** | exit 0 |
| Vite module compile (`http://localhost:5555/src/...`) | **PASS** | `AdminModerationPage.tsx` 200, `AdminPage.tsx` 200 |

#### Migration State (live dev MySQL, `fogdatabase`)

- `SELECT * FROM alembic_version_user` -> **`0027`**
- `SELECT * FROM alembic_version_locations` -> **`037_post_moderation_fk_set_null`**
- `version_table` names unchanged — `git diff` on both `env.py` files is empty;
  `alembic_version_user` (`user-service/alembic/env.py:39,59`) and
  `alembic_version_locations` (`locations-service/app/alembic/env.py:61,72`).
- `permissions WHERE module='moderation'` -> 2 rows (ids 89, 90) with Russian descriptions.
- `role_permissions` -> `moderation:read` and `moderation:review` granted to **role_id 3**,
  and `SELECT id,name,level FROM roles` confirms `3 = moderator (level 50)`, `4 = admin (100)` —
  the grant landed on the intended role.
- `information_schema` -> `post_deletion_requests.post_id` and `post_reports.post_id` are
  `IS_NULLABLE=YES`; `fk_post_deletion_requests_post_id` / `fk_post_reports_post_id` both
  `DELETE_RULE = SET NULL`. Migration 037 introspects via
  `sa.inspect(bind).get_foreign_keys()` and skips a table with no `post_id` FK — no
  hardcoded `*_ibfk_1` anywhere (`037_post_moderation_fk_set_null.py:54-59`).
  `models.py:263-269` / `:282-288` match the DB (`ondelete="SET NULL"`, `nullable=True`).

#### Live Verification Results

**The `claude-in-chrome` extension is NOT connected in this session** (the skill reported
"Browser tools are not available … the extension is not set up"). No step below ran in a
real browser. Everything was driven through the **api-gateway on :80** with real JWTs, plus
direct MySQL inspection. What that leaves unverified is listed at the end of this section.

Test rig: two throwaway accounts registered via `POST /users/register` — `feat158mod`
(id 28, promoted to `moderator`/role_id 3) and `feat158usr` (id 29, plain `user`) — plus the
memory-noted admin `chaldea@admin.com` (id 4). Effective permissions from `GET /users/me`:

```
admin: id=4  role=admin     moderation_perms=[moderation:read,moderation:review]  total=88
moder: id=28 role=moderator moderation_perms=[moderation:read,moderation:review]  total=68
plain: id=29 role=user      moderation_perms=[]                                   total=0
```

**1. Authorization matrix — moderator access preserved (the main regression risk).**

```
GET  deletion-requests          : none=401 plain=403 moder=200 admin=200
GET  reports                    : none=401 plain=403 moder=200 admin=200
PUT  deletion-requests/{id}/rev.: none=401 plain=403 moder=404 admin=404
PUT  reports/{id}/review        : none=401 plain=403 moder=400 admin=400
```

The PUT 404/400 are *past* the guard (row-not-found / invalid action for that queue) —
authorization passed for both staff roles. **Moderator was not narrowed to admin-only.**
The two player POSTs (`main.py:2107` request-deletion, `main.py:2128` report) are untouched
in the diff and still use `get_current_user_via_http`.

**2. Contract — TS types vs live `/openapi.json` vs Pydantic.** Fetched
`http://localhost:8006/openapi.json`: `PostDeletionRequestRead` and `PostReportRead` each
expose exactly the 13 fields declared in `ModerationItem`
(`AdminModerationPage.tsx:16-33`), same names, same types, `required: id,user_id,status,created_at`
— `post_id` correctly absent from `required`. No mismatch.

**3. Name resolution, bounded N+1.** With three pending rows seeded, the queues returned:

```
post_character_name = "Проверка FEAT155"   (resolved via character-service)
post_created_at     = "2026-09-13T16:25:15"
requester_username  = "feat158usr" / "feat158mod"
```

`_fetch_character_brief_map` (`crud.py:5595-5626`) and `_fetch_username_map`
(`crud.py:5628-5651`) both iterate `set(ids)` with `httpx.AsyncClient(timeout=5.0)` and map
any failure to `None`/`""`; `_enrich_moderation_items` (`crud.py:2587-2620`) wraps both in
its own `try/except` and runs **after** the SQL query. Degradation checked live: a row whose
`user_id` is `999999` (no such user) returned **HTTP 200 in 162 ms** with
`requester_username` null — not a 500.

**4. «Пост уже удалён» vs «Персонаж #id» are genuinely distinct.**
`isPostMissing` keys off `post_id === null || post_content === null` and hides the author
line entirely (`AdminModerationPage.tsx:59-61, 110-131`), while `postAuthorLabel`
(`:63-68`) falls back to `Персонаж #{id}` only when the post exists. Confirmed live: an
orphan row (`post_id IS NULL`) came back with `post_content`, `post_character_id`,
`post_character_name` and `post_created_at` **all null** while `requester_username` still
resolved — the two conditions cannot be confused.

**5. «Одобрить» and «Решена» exercised for real — the check that was impossible before.**
Seeded three posts (P1/P2/P3), four `action_gates` (P1: one `open` + one `consumed`;
P2: one `open`; P3: one `open`), a deletion request + a sibling report on P1, a report +
a sibling deletion request on P2, and a control report on P3.

| Call | Actor | Result |
|---|---|---|
| `PUT deletion-requests/7/review {action:"approve"}` | **moderator** | **HTTP 200** (previously an unconditional 500) |
| `PUT reports/7/review {action:"resolve"}` | **admin** | **HTTP 200** |
| `PUT reports/8/review {action:"dismiss"}` (control, P3) | admin | HTTP 200 |

Resulting DB state:

```
posts:      only FEAT158-TEST-P3 survives (P1, P2 deleted; dismiss deleted nothing)
requests:   id 7 post_id=NULL status=approved reviewed_by=28 reviewed_at=16:25:36
            id 8 post_id=NULL status=approved reviewed_by=4    <- sibling on P2, closed
reports:    id 6 post_id=NULL status=resolved reviewed_by=28   <- sibling on P1, closed
            id 7 post_id=NULL status=resolved reviewed_by=4
            id 8 post_id=153  status=dismissed                 <- control, post intact
gates:      38 attack expired   (P1 open     -> expired)
            39 gather consumed  (P1 consumed -> UNTOUCHED)
            40 attack expired   (P2 open     -> expired)
            41 attack open      (P3 -> untouched by dismiss)
```

Every clause of the design holds: moderation rows survive their post, `reviewed_by_user_id`
is the actual acting moderator (28 for the moderator's approve, 4 for the admin's resolve),
siblings are closed, `open` gates revoked, `consumed` untouched, other posts unaffected,
`reject`/`dismiss` revoke nothing.

**6. Sibling ordering is correct and load-bearing.** `_close_sibling_moderation_rows`
(`crud.py:2678-2708`) is called **before** `delete(Post)` in both branches
(`crud.py:2731-2736`, `crud.py:2770-2775`). After the delete the FK has already nulled the
siblings' `post_id`, so the `WHERE post_id = :p` would match nothing — the live result
(sibling rows 6 and 8 closed, not left pending) proves the order is the working one.
`post_id` is captured into a local before the delete in both handlers
(`crud.py:2729`, `crud.py:2768`), and the `post_id is None` guard returns 200 while
deleting nothing — verified live on an orphan row (`PUT …/9/review` -> 200, nothing removed).

**7. Decided rows leave the queue.** After the three decisions both queues returned only
the deliberately-seeded orphan; after reviewing it, both were empty.

**8. Tile filter mirrors `ProtectedRoute`.** `AdminPage.tsx:82-86` is now
`sections.filter((s) => hasModuleAccess(permissions, s.module))` — the `role === 'admin' ||`
bypass is gone, and `ProtectedRoute.tsx:56-58` has none either. The three badge-count
bypasses (`AdminPage.tsx:57, 60, 72`) are still present, as 3.2 intended.

**9. Standards.** Pydantic v1 `class Config: orm_mode = True` preserved on both schemas;
locations-service stays fully async; no `React.FC`; no `any` (the error helper takes
`unknown`); no SCSS/CSS anywhere in the diff (`git diff --stat -- "*.scss" "*.css"` is
empty; `components/AdminModerationPage/` contains only the `.tsx`); all raw SQL is
parameterized (`crud.py:1091-1105`, `:2688-2707`); `require_permission` returns the generic
Russian «Недостаточно прав» with no leakage; every frontend `catch` surfaces a Russian
message via toast **and** an inline retry banner, so a failed load never masquerades as an
empty queue.

**10. QA coverage.** Backend changed and QA tasks 7-9 + 14 exist and are DONE:
`services/user-service/tests/test_moderation_permissions.py`,
`services/user-service/tests/test_rbac_permissions.py` (section 10),
`services/locations-service/app/tests/test_post_moderation.py`,
`services/locations-service/app/tests/test_gate_revocation.py` — 54 tests in the two
locations modules, all green.

#### The flagged contract inaccuracy — decided: real but harmless today, recorded

Both `PUT …/review` endpoints declare the full read schema as `response_model`
(`main.py:2169`, `main.py:2189`) yet hand-build a 7-key dict, so six fields serialize as
`null`. Live evidence that this is a genuine (not merely cosmetic) inaccuracy: the `dismiss`
of report 8 — whose post was **not** deleted — returned
`{"post_id":153, …, "post_content":null}`, which under the page's own `isPostMissing` rule
reads as "post deleted". It is harmless **now** because `handleDeletionAction` /
`handleReportAction` discard the PUT body and refetch the queue
(`AdminModerationPage.tsx:215-243`), and the confirmation toast is built from the action,
not the response. Verified, not guessed. Because `/openapi.json` publishes a contract the
endpoint does not honour, it is **recorded in `docs/ISSUES.md` (LOW)** rather than waved
through — it is not a blocker and needs no fix in this feature.

#### `docs/ISSUES.md` updated by the Reviewer

- **Removed (HIGH):** «одобрение запроса на удаление и разрешение жалобы на пост всегда
  возвращают 500» — fixed by tasks 11-12 and proven fixed live above; a stale entry for a
  fixed bug would violate the bug-tracking rule.
- **Added (MEDIUM):** N+1 name resolution in the moderation queues — the batch-endpoint
  follow-up from 3.3.
- **Added (LOW):** `gametime:read|update` registered from a locations-service migration
  (audit finding 3.5-1).
- **Added (LOW):** moderator cannot open `/admin/game-time` (audit finding 3.5-2, product
  question).
- **Added (LOW):** the PUT `response_model` inaccuracy described above.
- **Added (LOW):** tile visibility checks `module:*` while the route checks one exact
  permission — the same *class* of bug FEAT-158 fixed, currently not reachable because no
  role holds `review` without `read`. Noted as a latent risk, not a defect in this feature.

#### Fixed by the Reviewer

Documentation only: the `docs/ISSUES.md` edits listed above. **No code was changed.**

#### Not verifiable in this session

The Chrome extension is not connected, so these remain unverified by the Reviewer and
were checked only at the API/DB and static-analysis level:

- actual rendering of `/admin/moderation` in a browser, as admin and as moderator
  (the *authorization* half of both walkthroughs was verified against the API);
- browser console cleanliness (zero `console.error` / unhandled rejections);
- the 360 px layout — the responsive classes are present (`overflow-x-auto` +
  `whitespace-nowrap` tabs, `flex-col sm:flex-row`, `flex-wrap` buttons, `break-words`)
  and `tsc`/`build`/Vite all compile the module, but no viewport was measured;
- that the «Модерация постов» tile is visible and its click lands on the page rather than
  redirecting — the underlying condition (`hasModuleAccess(permissions,'moderation')` and
  `hasPermission(permissions,'moderation:read')`) is true for both accounts, confirmed from
  the live `GET /users/me` payloads.

#### State restored

All fixtures removed: the three test posts, four `action_gates`, six moderation rows and
both throwaway accounts are deleted (post-cleanup counts all zero). `App.tsx` restored
byte-for-byte after the guard negative control (`git diff` empty). No pre-existing
moderation rows existed before the test and none were touched.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-13 — PM: фича создана по сообщению пользователя о недоступной модерации
[LOG] 2026-09-13 — PM: анализ выполнен, найдены три бага (редирект, контракты, неотзываемые гейты)
[LOG] 2026-09-13 — PM: пользователь выбрал правильный путь починки разрешений (через миграцию)
[LOG] 2026-09-13 — Architect: начал проектирование, перепроверил все ссылки из раздела 1 (поправлен путь ProtectedRoute, models.py:185, число эндпоинтов под get_admin_user)
[LOG] 2026-09-13 — Architect: решение по багу 1 — модуль `moderation` с правами read/review, миграция 0027, модератору выдаются оба права явно (доступ не сужается)
[LOG] 2026-09-13 — Architect: ProtectedRoute оставлен строгим; вместо этого убран обход `role === 'admin'` в фильтре плиток AdminPage — плитка и маршрут теперь согласованы
[LOG] 2026-09-13 — Architect: аудит всех requiredPermission в App.tsx — незарегистрировано только `moderation:read`, других мин нет; два побочных наблюдения по gametime уходят в ISSUES.md
[LOG] 2026-09-13 — Architect: баг 2 — имена резолвятся на бэкенде (переиспользуем _fetch_character_brief_map + новый _fetch_username_map), контракт расширяется аддитивно
[LOG] 2026-09-13 — Architect: баг 3 — гейты гасятся (open -> expired) до удаления поста в одной транзакции; consumed не трогаем; чиним здесь, т.к. от этого зависит FEAT-159
[LOG] 2026-09-13 — Architect: спроектировано 10 задач, 3 вопроса к PM, статус -> IN_PROGRESS
[LOG] 2026-09-13 — Architect: PM сообщил о блокере — approve/resolve всегда падал в 500 (CASCADE на post_id сносил строку модерации, дальше StaleDataError и откат)
[LOG] 2026-09-13 — Architect: согласен с решением PM — FK переводим на ON DELETE SET NULL, история решений модерации сохраняется
[LOG] 2026-09-13 — Architect: проверил код — одной смены FK мало: FK безымянные (нужна интроспекция), post_id стоит NOT NULL (MySQL запретит SET NULL), а post_id в схемах не Optional — иначе 500 просто переедет в Pydantic
[LOG] 2026-09-13 — Architect: добавлены задачи 11-14 (миграция 037 + models, хендлеры и схемы, nullable post_id на фронте, регрессионный pytest), задача 10 теперь зависит и от них
[LOG] 2026-09-13 — Architect: живая проверка кнопок «Одобрить»/«Решена» была заблокирована этим багом — после задач 11-14 разблокирована; вопрос Q4 к PM про соседние pending-заявки
[LOG] 2026-09-13 — Frontend Dev: задача #3 выполнена — из фильтра visibleSections в AdminPage.tsx убран обход `role === 'admin' ||`, видимость плиток теперь полностью определяется правами и совпадает с ProtectedRoute; три обхода в useEffect со счётчиками оставлены намеренно (п. 3.2). Проверки: `npx tsc --noEmit` — 0 ошибок, `npm run build` — успешно (оба в контейнере frontend)
[LOG] 2026-09-13 18:45 — Backend Dev: задача #1 завершена — миграция 0027 заводит moderation:read и moderation:review, оба выданы роли moderator (role_id=3); цикл upgrade -> downgrade -> upgrade прогнан на dev, повторный upgrade идемпотентен (id не дублируются), version_table alembic_version_user не менялся
[LOG] 2026-09-13 18:45 — Backend Dev: задача #2 завершена — четыре admin-эндпоинта модерации переведены с get_admin_user на require_permission (два GET -> moderation:read, два PUT -> moderation:review); два игровых POST не тронуты
[LOG] 2026-09-13 18:45 — Backend Dev: матрица доступа проверена вживую через api-gateway — admin 200/200/404, moderator 200/200/404 (доступ НЕ сужен), обычный игрок 403, без токена 401
[LOG] 2026-09-13 18:45 — Backend Dev: задача #6 завершена — добавлен expire_action_gates_for_post (без внутреннего commit), вызывается перед delete(Post) в ветках approve и resolve; проверено: open -> expired + post_id NULL, consumed не тронут, reject/dismiss оставляют гейт open, чужие посты не задеты, откат транзакции откатывает и удаление, и отзыв
[LOG] 2026-09-13 18:45 — Backend Dev: обнаружен баг вне задачи, добавлен в ISSUES.md (HIGH) — ветки approve/resolve всегда отдают 500: post_deletion_requests.post_id и post_reports.post_id объявлены ON DELETE CASCADE, удаление поста стирает строку модерации, следующий UPDATE падает со StaleDataError. Воспроизведено и на чистом HEAD — баг существовал до FEAT-158. Модерация сегодня физически не может удалить пост; нужно решение Architect/PM
[LOG] 2026-09-13 18:45 — Backend Dev: pytest locations-service 849 passed; user-service 463 passed, 1 failed (test_profile_customization.py::test_get_user_characters_success — падает и без моих правок, не связан)
[LOG] 2026-09-13 19:20 — Backend Dev: задача #4 завершена — в config.py добавлен USER_SERVICE_URL (со значением по умолчанию, compose не трогали), в crud.py добавлены _fetch_username_map (GET /users/{id}, timeout 5 c, ошибка -> None) и _enrich_moderation_items; обе очереди теперь отдают post_character_name, post_created_at, requester_username; резолв идёт один раз за запрос по множеству уникальных id уже ПОСЛЕ SQL-запроса, любые сбои дают null, а не 500
[LOG] 2026-09-13 19:20 — Backend Dev: задача #11 завершена — миграция 037_post_moderation_fk_set_null (down_revision 036_add_post_drafts): FK интроспектируются через sa.inspect (имена не хардкодятся, таблица без FK пропускается), порядок drop FK -> nullable=True -> named FK с SET NULL; models.py приведён в соответствие; downgrade лоссовый (удаляет строки с post_id IS NULL), это описано в docstring. Прогон upgrade -> downgrade -1 -> upgrade прошёл, information_schema показывает SET NULL и IS_NULLABLE=YES на обеих таблицах
[LOG] 2026-09-13 19:20 — Backend Dev: задача #12 завершена — post_id в PostDeletionRequestRead/PostReportRead стал Optional, в обоих хендлерах post_id читается в локальную переменную ДО delete(Post), добавлена явная защита post_id is None (ничего не удаляем, решение записываем, 200), соседние pending-заявки закрываются в той же транзакции (запросы -> approved, жалобы -> resolved, с указанием модератора) — обязательно ДО удаления поста, иначе FK уже обнулит их post_id
[LOG] 2026-09-13 19:20 — Backend Dev: сквозная проверка через api-gateway — approve запроса на удаление и resolve жалобы отдают 200 (раньше всегда 500), посты реально удалены, строки модерации живы со статусом, reviewed_at, reviewed_by_user_id и post_id IS NULL; гейт open -> expired, consumed не тронут, гейт чужого поста остался open; соседние заявки закрыты, очереди опустели; reject/dismiss не изменились, пост цел; заявка с post_id IS NULL отдаёт 200 и ничего не удаляет. Тестовые строки удалены
[LOG] 2026-09-13 19:20 — Backend Dev: py_compile по всем изменённым файлам в контейнере — OK; pytest locations-service — 849 passed (базовый уровень сохранён)
[LOG] 2026-09-13 20:40 — QA: задача #7 выполнена — в test_rbac_permissions.py добавлена секция 10 (10 тестов: обе moderation-права заведены, админ получает их автоматически, модератор сохраняет read+review, редактор и игрок не получают ничего, require_permission отдаёт 403); новый test_moderation_permissions.py проверяет саму миграцию 0027 (цепочка ревизий, состав прав, русские описания, грант только роли 3, отсутствие хардкода id, идемпотентность, порядок удаления в downgrade)
[LOG] 2026-09-13 20:40 — QA: задача #7 — добавлен структурный guard: тест парсит все requiredPermission из App.tsx и требует, чтобы каждое право заводилось миграцией. Сканируются ОБА дерева миграций (user-service и locations-service), иначе gametime:read|update дали бы ложное срабатывание. Парсер понимает четыре стиля объявления прав (bulk_insert-словари, списки кортежей, литеральные bind-параметры, сырой SQL VALUES) — на нём сразу всплыл пропуск mobs:manage при первом прогоне, что доказывает: guard реально падает на незарегистрированном праве. Вне репозитория (внутри контейнера сервиса) тест корректно скипается, в CI выполняется по-настоящему
[LOG] 2026-09-13 20:40 — QA: задача #8 выполнена — новый tests/test_post_moderation.py, слой эндпоинтов: без токена 401, невалидный токен 401, обычный игрок 403 («Недостаточно прав») на всех четырёх admin-эндпоинтах, admin 200 и **moderator 200** (явно зафиксировано, что доступ не сужен ни на GET, ни на PUT), модератор только с moderation:read получает 403 на обоих PUT, кросс-модульная изоляция; оба игровых POST (request-deletion, report) остаются доступны обычному игроку и по-прежнему требуют токен
[LOG] 2026-09-13 20:40 — QA: задача #8 — контракт ответа: очереди отдают post_character_name, post_created_at, requester_username; строка с удалённым постом отдаёт все post-поля null и 200; отдельные тесты на резолв имён — падение или 404 downstream даёт null, а не 500, пустое имя тоже null, для строки без character_id исходящий вызов не делается, и исходящие вызовы дедуплицируются (3 строки, 2 уникальных персонажа и 2 пользователя = 4 запроса, не 6)
[LOG] 2026-09-13 20:40 — QA: задача #9 выполнена — новый tests/test_gate_revocation.py (13 тестов) на реальном aiosqlite с PRAGMA foreign_keys=ON: open -> expired, consumed не трогаем, уже expired не меняется, чужие посты не задеты, гасятся все open-гейты поста, хелпер не коммитит сам (rollback откатывает отзыв), через approve/resolve гейты гаснут и post_id обнуляется, reject/dismiss не отзывают ничего, гейт соседнего игрока цел, пара «отзыв + удаление» откатывается целиком, заявка с post_id IS NULL ничего не отзывает
[LOG] 2026-09-13 20:40 — QA: задача #14 выполнена — регрессия на 500 в тех же test_post_moderation.py: approve и resolve возвращают строку решения (не StaleDataError), пост реально удалён, строка модерации жива со status/reviewed_at/reviewed_by_user_id и post_id IS NULL и перечитывается с диска, соседние pending-заявки закрыты, чужие посты и их заявки не тронуты, reject/dismiss ничего не удаляют, строка с post_id IS NULL рассматривается без ошибки, рассмотренные строки выпадают из очереди, осиротевшая строка рендерится с post_content/post_character_name/post_created_at = null, а PUT-ответ переживает post_id = null (вторая половина бывшего 500 — Pydantic)
[LOG] 2026-09-13 20:40 — QA: доказано, что тесты падают на схеме ДО миграции 037 — временный откат models.py к ondelete=CASCADE/nullable=False даёт 14 failed (в т.ч. все ключевые approve/resolve), после возврата — снова зелено; models.py восстановлен байт-в-байт (git diff совпадает с правкой Backend Dev)
[LOG] 2026-09-13 20:40 — QA: прогоны в контейнерах — locations-service 903 passed (было 849, +54 новых), user-service 482 passed, 5 skipped (guard App.tsx вне репозитория), 1 failed — тот самый предсуществующий test_profile_customization.py::test_get_user_characters_success, других падений нет. py_compile по всем новым файлам — OK
[LOG] 2026-09-13 20:10 — Frontend Dev: задачи #5 и #13 выполнены одним диффом — интерфейсы AdminModerationPage переписаны под реальный контракт: плоский snake_case (post_id: number | null, user_id, post_content, post_character_id, post_character_name, post_created_at, requester_username, reviewed_at), PostPreview удалён, все обращения req.post?. / report.post?. убраны
[LOG] 2026-09-13 20:10 — Frontend Dev: фолбэки разведены по смыслу — «Пост уже удалён» (когда post_id или post_content = null; строка автора скрывается целиком), «Персонаж #id» (пост есть, но имя не отрезолвилось), «Пользователь #id» (не отрезолвился аккаунт заявителя); заявитель показывается как учётка, а не персонаж
[LOG] 2026-09-13 20:10 — Frontend Dev: ошибки API теперь видны всегда — общий errorMessage() с ветками 401/403 («Недостаточно прав для раздела модерации»)/404/5xx/нет сети, тост + инлайн-баннер с кнопкой «Повторить»; упавшая загрузка больше не выглядит как пустая очередь
[LOG] 2026-09-13 20:10 — Frontend Dev: карточка вынесена в локальный ModerationCard (без React.FC), только Tailwind, SCSS не добавлялся; адаптив под 360px — табы скроллятся горизонтально с whitespace-nowrap, кнопки flex-wrap, длинные имена/причины break-words
[LOG] 2026-09-13 20:10 — Frontend Dev: типы сверены с живым /openapi.json locations-service — расхождений с schemas.py нет, post_id отсутствует в required у обеих схем. Проверки в контейнере frontend: `npx tsc --noEmit` — 0 ошибок, `npm run build` — успешно (built in 49.35s)
[LOG] 2026-09-13 21:30 — Reviewer: начал проверку задачи #10, все проверки прогоняю сам
[LOG] 2026-09-13 21:30 — Reviewer: автопроверки — tsc 0 ошибок, npm run build успешно (36.10s), py_compile по всем изменённым файлам OK, docker compose config OK
[LOG] 2026-09-13 21:30 — Reviewer: pytest locations-service 903 passed (совпало с ожиданием), user-service 482 passed / 5 skipped / 1 failed — это тот самый предсуществующий test_get_user_characters_success, других падений нет
[LOG] 2026-09-13 21:30 — Reviewer: guard App.tsx проверен по-настоящему — прогон в образе user-service с примонтированным репозиторием дал 88 passed и НОЛЬ skipped; подмена moderation:read на несуществующее право уронила 3 теста, App.tsx восстановлен байт-в-байт
[LOG] 2026-09-13 21:30 — Reviewer: миграции — alembic_version_user=0027, alembic_version_locations=037_post_moderation_fk_set_null, имена version_table не менялись; в БД оба FK SET NULL и post_id nullable; права выданы role_id=3, и таблица roles подтверждает, что 3 — это moderator
[LOG] 2026-09-13 21:30 — Reviewer: расширение claude-in-chrome не подключено — живая проверка шла через api-gateway и MySQL; в браузере не проверялись рендер страницы, консоль и 360px (явно перечислено в разделе 5)
[LOG] 2026-09-13 21:30 — Reviewer: матрица доступа вживую — без токена 401, игрок 403, модератор и админ 200 на обоих GET и проходят guard на обоих PUT; доступ модератора НЕ сужен
[LOG] 2026-09-13 21:30 — Reviewer: «Одобрить» нажато от модератора, «Решена» от админа — оба 200 (раньше всегда 500); посты удалены, строки модерации живы с post_id NULL и настоящим reviewed_by, соседние заявки закрыты, гейты open -> expired, consumed не тронут, гейт чужого поста цел, dismiss ничего не удалил
[LOG] 2026-09-13 21:30 — Reviewer: контракт сверен с живым /openapi.json — 13 полей совпадают с TS-типами; «Пост уже удалён» и «Персонаж #id» действительно разведены; несуществующий user_id даёт null и 200, а не 500
[LOG] 2026-09-13 21:30 — Reviewer: неточность контракта на PUT подтверждена вживую (dismiss живого поста вернул post_content=null) — сегодня безвредна, т.к. фронт перезапрашивает очередь; заведена в ISSUES.md как LOW
[LOG] 2026-09-13 21:30 — Reviewer: ISSUES.md приведён в актуальное состояние — удалён HIGH про 500 на approve/resolve (исправлен этой фичей), добавлены MEDIUM про N+1 и четыре LOW (gametime x2, PUT response_model, разная гранулярность плитки и маршрута)
[LOG] 2026-09-13 21:30 — Reviewer: все тестовые данные и учётки удалены, состояние БД восстановлено
[LOG] 2026-09-13 21:30 — Reviewer: проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

Пользователь сообщил об одном симптоме — «в админке модерация постов выкидывает на главную».
За ним нашлось **четыре** бага, и раздел модерации не работал вообще никогда.

**Баг 1 — редирект.** Маршрут требовал разрешение `moderation:read`, которого не существовало
нигде, кроме самого объявления маршрута. Админ получает разрешения выборкой из таблицы
`permissions`, поэтому отсутствие строки означало отказ даже ему. Заведены `moderation:read` и
`moderation:review` миграцией `0027`, эндпоинты переведены на проверку разрешений. **Доступ
модератора сохранён** — раньше пускало по роли (админ + модератор), и сузить до одних админов
было бы тихой регрессией.

**Баг 2 — пустая страница.** Фронт ждал `character_id`, `character_name` и вложенный `post`,
бэкенд отдавал `user_id` и плоские поля. На экране было «Пост удален» и «Неизвестный» в каждой
строке. Имена теперь резолвятся на сервере с ограниченным N+1 (дедупликация id, таймаут 5 с,
отказ деградирует в `null`, а не в 500). На фронте разведены два разных случая: **пост удалён**
(строка автора не показывается) и **пост жив, имя не подтянулось** («Персонаж #id»).

**Баг 3 — модерация не могла удалить пост.** Одобрение удаления и разрешение жалобы **всегда**
возвращали 500: внешние ключи стояли на `ON DELETE CASCADE`, удаление поста сносило саму строку
заявки, и следующее обновление её статуса падало со `StaleDataError`, откатывая транзакцию
целиком. Ключи переведены на `SET NULL`, строка заявки теперь переживает удаление поста и
остаётся журнальной записью.

Одной смены ключа было **мало**, и это выяснилось при проектировании: ключи безымянные (миграция
ищет их интроспекцией), колонка была `NOT NULL` (MySQL отказывается вешать `SET NULL`), а в
схемах ответа `post_id` был обязательным — то есть 500-я просто переехала бы в Pydantic.

**Баг 4 — гейты не отзывались.** Удаление поста оставляло выданные им права `open`: игрок,
наказанный за абузный пост, продолжал атаковать, собирать ресурсы и входить в подземелья.
Теперь `open` становятся `expired`, а уже `consumed` не трогаются — это журнал того, что
действие состоялось.

**Сверх того:** видимость плитки в админке приведена в точное соответствие с проверкой маршрута,
поэтому мёртвых ссылок больше не будет. И «сестринские» заявки (два игрока пожаловались на один
пост) закрываются в той же транзакции, а не висят в очереди по уже удалённому посту.

### Что изменилось от первоначального плана

- Из двух багов получилось **четыре**: третий нашёл разработчик при проверке, четвёртый всплыл
  при анализе гейтов для FEAT-159.
- Порядок закрытия сестринских заявок пришлось развернуть: их надо закрывать **до** удаления
  поста, иначе внешний ключ уже обнулит у них ссылку и обновление не найдёт ни одной строки.
  Разработчик поймал это сам и поправил инструкцию.
- `ProtectedRoute` **намеренно оставлен строгим**, без обхода для админа. Именно строгая проверка
  и вскрыла незарегистрированное разрешение; обход превратил бы громкий редирект в тихо сломанную
  страницу.

### Проверка

- `locations-service` — **903** теста (было 849), `user-service` — 482 (единственное падение
  предсуществующее и не связано с фичей). Сборки фронта зелёные.
- **Регрессия на 500-ю доказана от обратного:** временный возврат старых внешних ключей уронил
  14 тестов, включая все случаи одобрения и разрешения.
- **Защитный тест проверен от обратного ревьюером:** подмена разрешения на несуществующее валит
  три теста. Тест разбирает `App.tsx`, вытаскивает все строки разрешений и проверяет их
  регистрацию — при написании он сразу нашёл четвёртый стиль объявления в миграции `0015`.
- **Живая проверка через API:** «Одобрить» от модератора и «Решена» от админа — 200, посты
  удалены, заявки сохранились с `reviewed_by_user_id`, гейты отозваны, отклонение и закрытие
  ничего не удаляют.

### Оставшиеся риски / follow-up

- **В браузере не проверялось** — расширение Chrome не подключено. Стоит один раз открыть раздел
  админом и модератором: увидеть очередь, нажать «Одобрить», проверить консоль и вид на 360px.
- Записано в `ISSUES.md`: резолв имён по одному вместо батча (нужен батч-эндпоинт в user-service);
  `gametime:*` регистрируются миграцией locations-service, а не владельца RBAC; модераторы не
  видят `/admin/game-time` (вопрос к пользователю); два `PUT …/review` объявляют полную схему
  ответа, а возвращают семь полей; и найденный ревьюером латентный случай — видимость плитки
  проверяет `модуль:*`, а маршрут одно конкретное разрешение, то есть тот же класс бага,
  который эта фича и чинила.
- Устаревшая запись про «одобрение всегда 500» из `ISSUES.md` удалена — баг исправлен.

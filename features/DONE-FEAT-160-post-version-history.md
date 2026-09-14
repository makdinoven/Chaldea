# FEAT-160: История версий поста

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-13 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

**Зависит от FEAT-159** — редактирование постов (фаза A закрыта, фаза B в работе).
Без правок истории не бывает.

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
FEAT-159 дала игрокам возможность править отправленные посты. Пометка «изменено» на посту
говорит, что правка была, но не говорит **что именно** изменилось. В ролевой игре это важно:
реплику могли процитировать до правки, и спор «ты написал не так» разрешить нечем.

Храним предыдущие версии текста и даём админам посмотреть, что поменялось.

### Бизнес-правила
- **Видят только админы.** Обычные игроки историю не видят — это инструмент разбора споров,
  а не публичный журнал. Правка для игроков остаётся «тихой», видна только пометка «изменено».
- **Хранятся все версии, пока жив пост.** Удаляется пост — удаляется история.
- **Показывается не просто старый текст, а различия** — что добавлено и что убрано.
- История копится **с момента выката**. У постов, отредактированных до него, её не будет —
  восстанавливать неоткуда. Это надо честно показывать, а не делать вид, что правок не было.

### UX / Пользовательский сценарий
1. Админ видит на посту пометку «изменено».
2. Открывает историю версий.
3. Видит список правок с датами и автором каждой.
4. Выбирает версию — видит различия: что добавлено, что убрано.

### Edge Cases
- Пост правили 20 раз — список должен оставаться читаемым.
- Правку делал админ, а не автор — должно быть видно, кто именно.
- Пост удалён модерацией — история уходит вместе с ним.
- Персонаж или аккаунт редактора удалён — имя не резолвится.
- Очень длинный пост: различия по 20 000 символов не должны вешать страницу.
- Пост отредактирован до выката фичи (`edited_at` есть, истории нет) — показать это явно.
- Правка изменила только разметку (курсив, цвет), а текст тот же — различия должны это
  осмысленно показывать, а не выдавать сплошную «замену всего».

### Вопросы к пользователю
- [x] Кто видит историю? → **Только админы.**
- [x] Сколько хранить? → **Все версии, пока жив пост.**
- [x] Показывать старый текст или различия? → **Различия (что добавлено / что убрано).**
- [x] Для показа различий обычно берут готовую библиотеку (например `diff` / `jsdiff`) вместо
      самописного алгоритма. CLAUDE.md требует спрашивать перед добавлением зависимостей.
      Ставить библиотеку или писать своё? → **Ставить библиотеку.** Разрешено пользователем
      2026-09-14. Выбор конкретной — за архитектором: маленькая, без собственных зависимостей,
      живая. Самописный алгоритм сравнения отклонён сознательно.
- [x] Различия считать по тексту или по HTML-разметке? Разметка нагляднее для правок
      оформления, но сравнение HTML заметно сложнее и шумнее. → **Решено архитектором 2026-09-14: по тексту (пословно), с отдельной плашкой и панелью разметки для правок оформления — см. 3.1.**

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

_Filled by Architect (who owns the analysis for this feature). Every claim below was
re-verified against the working tree on 2026-09-14._

### 2.1 Where an edit happens today

`crud.edit_post` — `services/locations-service/app/crud.py:1320-1594`. Shape, verified line by line:

1. `SELECT id, character_id, location_id, created_at, (created_at > NOW() - INTERVAL :hours HOUR)
   AS within_window FROM posts WHERE id = :pid FOR UPDATE` (`crud.py:1390-1398`).
   **It does not select `content`.** Adding `content, edited_at, edited_by_user_id` to this
   existing SELECT gives the history write everything it needs with **no extra query and no
   extra lock**.
2. Author lookup, authorisation (admin branch first, then owner, else 403) — `crud.py:1401-1438`.
3. Minimum-length check, applies to admins too — `crud.py:1440-1445`.
4. Phase-B gate validation and symbol budget — `crud.py:1450-1538`.
5. `UPDATE posts SET content = :content, edited_at = NOW(), edited_by_user_id = :uid`
   — `crud.py:1544-1550`.
6. Optional `PostGateRequest` row, `session.add` + `flush` — `crud.py:1558-1570`.
7. **A single `await session.commit()`** — `crud.py:1572`.
8. Re-read of the saved row for the response — `crud.py:1574-1582`.

**Conclusion: a history row can and must be written inside this same transaction**, between
step 4 and step 5, before the `UPDATE` overwrites the text. The function already has exactly one
commit, and FEAT-159 established the precedent in its own comment at `crud.py:1552-1555` («written
in the SAME transaction as the text it is about»). The `SELECT ... FOR UPDATE` at step 1 also
serialises concurrent edits of the same post, so computing `MAX(version_no) + 1` under that lock
is race-free by construction.

The route is `PUT /locations/posts/{post_id}` — `main.py:981-1020`, auth
`Depends(get_current_user_via_http)`, admin test done *inside* the handler because the endpoint
also serves owners.

### 2.2 Deletion semantics — CASCADE vs SET NULL

Posts are really deleted, not soft-deleted: `await session.execute(delete(Post).where(Post.id ==
post_id))` in both moderation branches — `crud.py:3266` (`review_deletion_request`) and
`crud.py:3303` (`review_report`). So a DB-level `ON DELETE` clause on `posts.id` actually fires.

Two conventions exist side by side in this service, and they are **not** in conflict:

| Table | `post_id` policy | Why |
|---|---|---|
| `post_deletion_requests`, `post_reports` (migration 037, FEAT-158) | `NULL` + `ON DELETE SET NULL` | the row is a **decision about** a post — who ruled what, and when. It has independent audit value after the post is gone. |
| `post_gate_requests` (migration 039, FEAT-159) | `NULL` + `ON DELETE SET NULL` | same class: a moderation decision. |
| `action_gates` (`models.py:184`) | `NULL` + `ON DELETE SET NULL` | a granted right outlives the text that bought it. |
| `post_likes` (`models.py:206`) | `NOT NULL` + `ON DELETE CASCADE` | the row is **an attribute of** the post. Meaningless without it. |

`post_versions` belongs to the second class, not the first — see 3.3.

### 2.3 The «изменено» marker and the post payload

* Columns: `posts.edited_at`, `posts.edited_by_user_id` — `models.py:173-176`, migration
  `038_post_edit_columns.py`. `edited_by_user_id` is documented as "never sent to clients".
* `edited_by_admin` is **derived**, not stored — `crud.py:2304-2310`, inside `get_post_details`.
* Frontend marker: `PostCard.tsx:286-294` («изменено» / «изменено администратором», exact time in
  the `title`). The card already receives `currentUserRole` (`LocationPage.tsx:922`) — the exact
  signal an admin-only menu entry needs, with no new plumbing.
* The post kebab menu is `PostCard.tsx:336-375`: «Пожаловаться», «Редактировать» (`canEdit`),
  «Запросить удаление» (`isAuthor`). A fourth, admin-only entry drops in here.
* `PostEditModal.tsx` (`components/pages/LocationPage/PostEditModal.tsx`) is the modal precedent;
  `LocationPage.tsx:947` is where modals are mounted.

### 2.4 Admin surfaces that could host this

* `AdminModerationPage.tsx` — three queues (`deletions` / `reports` / `gates`,
  `AdminModerationPage.tsx:84`). Every item already carries `post_id`, `post_content`,
  `post_character_name` and — for gate requests — `post_edited_at`
  (`AdminModerationPage.tsx:79`, rendered at `:311-316`). So the moderation queue **already
  tells an admin that the post was edited and gives no way to see what changed.**
* `AdminCharactersPage` deals with characters, not posts — wrong surface.
* Backend admin routes live on the same `APIRouter(prefix="/locations")` (`main.py:113`), so a new
  route needs **no nginx change**.

### 2.5 Permissions — the FEAT-162 trap

`services/user-service/alembic/versions/0027_add_moderation_permissions.py` creates
`moderation:read` and `moderation:review` and grants **both to Moderator (role_id=3)**. Reusing
either would hand post history to every moderator, contradicting «только админы».

Two primitives could carry this, and the difference matters:

* `get_strict_admin_user` (`auth_http.py:58-70`) — role must be literally `admin`, moderators
  rejected, already used at `main.py:1803`. It is the FEAT-159 precedent for post powers, but it
  is a hard gate: nothing short of a deploy can ever widen it.
* `require_permission("<module>:<action>")` (`auth_http.py:72-83`) — already the dominant pattern
  in this service (every `locations:*` admin route uses it). Combined with
  `crud.get_effective_permissions` (`user-service/crud.py:14-35`), which hands role `admin` every
  row of the `permissions` table, a permission with **zero `role_permissions` rows** means
  "admins, plus anyone the user explicitly names in `user_permissions`".

FEAT-162 hit exactly this and chose the second
(`0028_add_characters_teleport_permission.py`: `characters:teleport`, granted to no role, because
Moderator already held every other `characters:*`). **The user ruled the same way here** — see 3.9.

### 2.6 Storage reality

Measured on the dev database (`fogdatabase`) on 2026-09-14:

```
posts = 118 | edited = 0 | avg length = 598 | max length = 5597 | total content = 0.07 MB
```

Production is a different, larger dataset, but the whole production dump is ~15 MB. Full-copy
versioning is not a scale problem here — see 3.5.

### 2.7 Frontend dependency state

`services/frontend/app-chaldea/package.json` — **no diff library of any kind is present**
(checked the full dependency and devDependency lists). `dompurify@^3.2.4` is present and is the
project's sanitiser of record (`PostCard.tsx:315`). `package-lock.json` is tracked by git.
Dev container runs `npm install` on start; `docker/frontend/Dockerfile` builds with
`npm install --legacy-peer-deps`.

### 2.8 Cross-service impact

None. No other service reads `posts.content` history, and the endpoint is additive. The only
outbound call the feature makes is the existing `crud._fetch_username_map` (`crud.py:6493-6513`),
already used by the moderation queue to turn `user_id` into a username, with a documented
degrade-to-`None` on failure.
---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Ruling on the open question — diff the TEXT, and label formatting separately

**Decision: the diff shown to the admin is a word-level diff of the post's plain text. A
formatting-only edit is not hidden — it is stated in words and backed by an optional, escaped
HTML-source panel.**

The purpose of this feature, in the user's own framing, is to settle «ты написал не так». That is
a dispute about *what a character said*, and a character-level diff of TipTap HTML answers a
different question badly: wrapping one word in `<em>` rewrites the surrounding string and the diff
reports a wall of red and green. Section 1 names this exact edge case.

A text-only diff has the opposite failure — an edit that only recolours a word looks like "nothing
changed", which is dishonest. So the modal does three things:

1. **Word diff of plain text** (`diffWords`), rendered as added / removed runs. This is the
   headline and the default view.
2. **When the normalised plain text is identical but the HTML differs**, a Russian banner instead
   of an empty diff: «Текст не изменился — правка коснулась только оформления.»
3. **A collapsed «Показать различия в разметке» panel**, always available, showing a word diff of
   the raw HTML **rendered as escaped source text**, never as markup. This is where a formatting
   dispute is actually resolved, and it costs one `<pre>`.

Rejected: HTML-tree diff libraries (`htmldiff-js`, `diff-dom`). They are larger, less actively
maintained, and they emit *merged HTML* which would then have to pass through DOMPurify together
with untrusted post content — mixing "trusted diff markup" with "untrusted player markup" in one
sanitise call is a real XSS surface for a benefit the escaped-source panel already delivers.

**What the admin sees, per case:**

| Edit | What the modal shows |
|---|---|
| Words changed | word diff: removed runs struck through in red, added runs in green |
| Only formatting changed | the banner from (2), plus the markup panel showing the tag delta |
| Both | the word diff, plus the markup panel on demand |
| Post edited before deployment | «Более ранние версии не сохранились…» — see 3.6 |

### 3.2 Library choice — `diff` (jsdiff) `^9.0.0`

Verified with `npm view` inside the running `frontend` container on 2026-09-14:

| Criterion | Value |
|---|---|
| Package | `diff` (jsdiff, `github.com/kpdecker/jsdiff`) |
| Version to pin | `^9.0.0` |
| Runtime dependencies | **none** (`npm view diff@9.0.0 dependencies` returns nothing) |
| TypeScript types | **bundled** (`types = libcjs/index.d.ts`) — no `@types/diff` needed |
| Licence | BSD-3-Clause |
| Last published | 2026-04-13 — actively maintained |
| Already in `package.json`? | **No** (see 2.7) |
| Unpacked size | ~600 KB, but only `diffWords` is imported; the ESM build is tree-shaken by Vite |

Only `diffWords` is imported. No other jsdiff entry point may be pulled in.

**Long-post guard (section 1 edge case: 20 000 characters).** jsdiff is O(ND); it is fast for
ordinary edits but degenerates when the two texts share almost nothing. Call it as
`diffWords(before, after, { maxEditLength: DIFF_MAX_EDIT_LENGTH })` with
`DIFF_MAX_EDIT_LENGTH = 20000`. When the edit distance exceeds the cap jsdiff returns `undefined`
— the modal then shows both versions side by side with «Правка слишком велика для посимвольного
сравнения — версии показаны целиком.» The diff is computed in a `useMemo` keyed on the version
pair, so switching versions never recomputes the whole history.

### 3.3 New table — `post_versions` (locations-service migration 040)

```sql
CREATE TABLE post_versions (
  id                BIGINT       NOT NULL AUTO_INCREMENT,
  post_id           INT          NOT NULL,
  version_no        INT          NOT NULL,
  content           TEXT         NOT NULL,
  edited_by_user_id INT          NOT NULL,
  is_original       TINYINT(1)   NOT NULL DEFAULT 1,
  created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_post_versions_post_version (post_id, version_no),
  CONSTRAINT fk_post_versions_post_id FOREIGN KEY (post_id)
    REFERENCES posts (id) ON DELETE CASCADE
) ENGINE=InnoDB;
```

`revision = '040_post_versions'`, `down_revision = '039_post_gate_requests'`. Follow
`039_post_gate_requests.py` exactly: `inspector.get_table_names()` guard for idempotency,
`mysql_engine="InnoDB"`, and a `downgrade()` that only calls `op.drop_table` (dropping the index
first is impossible — `uq_post_versions_post_version` backs the FK, MySQL ERROR 1553).
Rollback: `DROP TABLE post_versions`; nothing else in the system reads it.

No separate `idx_post_versions_post` — the unique key's leading column is `post_id`, which serves
both the FK and every query this feature makes.

**`ON DELETE CASCADE` with `post_id NOT NULL` — the reasoning, not the convention.**
FEAT-158's `SET NULL` is right for its own tables and wrong here, and the difference is what the
row *is*:

* a `post_deletion_requests` / `post_reports` / `post_gate_requests` row is a **staff decision**.
  It is evidence of what a moderator did, it names a moderator, and it keeps that value after the
  post is gone. Orphaning it preserves an audit trail.
* a `post_versions` row is **a copy of the post itself**. Once the post is deleted — very often
  deleted *by moderation, for its content* — an orphaned row is not an audit trail, it is a
  surviving copy of removed content sitting in an admin view with nothing to attach it to. It
  answers no question and quietly defeats the deletion.

Section 1 states the rule («удаляется пост — удаляется история») and this is why it is the right
rule. `post_id` is therefore `NOT NULL`, making the orphan state unrepresentable rather than
merely unlikely, and the DB enforces the cascade so no future deletion path can forget it.

### 3.4 What a version row is — the text BEFORE the edit

**Decision: each row stores the content that the edit REPLACED, together with who replaced it and
when.** The post's *current* text is never duplicated into the table — it is read live from
`posts.content`.

This is the only choice that captures the original. If rows stored the text *after* each edit,
the first edit would record the new text and the original — precisely the wording that was quoted
and is now disputed — would be lost forever. Storing the superseded text means the very first edit
snapshots version 1 = the original, and the chain is complete:

```
post_versions row 1 : content = original text,      edited_by = editor of edit #1, created_at = edit #1
post_versions row 2 : content = text after edit #1, edited_by = editor of edit #2, created_at = edit #2
...
posts.content       : text after the last edit (= the current version)
posts.edited_at / edited_by_user_id : the last edit
```

Note the deliberate off-by-one: a row's `edited_by_user_id` / `created_at` describe the **edit that
destroyed** that text, not the edit that produced it. The API (3.6) flips this once, server-side,
into the shape the admin thinks in — «версия 2, автор правки X, 14:05» — so the frontend never
has to reason about it and QA can test the mapping directly.

`version_no` is computed as `SELECT COALESCE(MAX(version_no), 0) + 1 FROM post_versions WHERE
post_id = :pid` **inside the `SELECT ... FOR UPDATE` critical section** of `edit_post`. Every
writer goes through that lock, so the read-modify-write is serialised; the unique key is the
backstop.

### 3.5 Storage — full copies, no deltas, no cap

Measured: 118 dev posts, 598 characters average, 5597 maximum, 0.07 MB of content in total (2.6);
the whole production database is ~15 MB. A post edited twenty times costs ~20 × 600 B ≈ 12 KB, and
the hour-long edit window plus the "nobody replied yet" rule make twenty edits of one post a
pathological case, not a normal one. At any plausible growth of this game the table stays in the
low single-digit megabytes.

Therefore: **store the full text of every version. No delta chains, no truncation, no retention
policy, no compression.** A delta chain would make «показать версию 3» depend on every earlier row
surviving, would be unreadable in Adminer during an actual dispute, and would buy kilobytes. This
is a deliberate decision documented here so it is not "optimised" later without a reason.

### 3.6 API contract

```
GET /locations/posts/{post_id}/versions
Auth: Depends(require_permission("posts:history"))   # see 3.9
```

Pydantic **v1** (`class Config: orm_mode = True`), in `schemas.py`:

```python
class PostVersionEntry(BaseModel):
    version_no: int
    content: str                            # raw stored HTML
    created_at: Optional[datetime]          # when this text became the post's text
    author_user_id: Optional[int]           # who produced it; None for the untouched original
    author_username: Optional[str]
    is_current: bool = False

class PostVersionHistory(BaseModel):
    post_id: int
    post_edited_at: Optional[datetime]
    original_available: bool
    versions: List[PostVersionEntry]        # ascending version_no; the current text is last
```

**Server-side mapping** (the single place the off-by-one of 3.4 is resolved; `crud.get_post_versions`):

| Entry | `content` | `created_at` | `author_user_id` |
|---|---|---|---|
| `version_no = 1` | row 1 `.content` | `posts.created_at`, **or `None` when `original_available` is false** | `None` (the post's own author) |
| `version_no = k` (1 < k <= N) | row k `.content` | row k−1 `.created_at` | row k−1 `.edited_by_user_id` |
| `version_no = N+1`, `is_current = true` | `posts.content` | `posts.edited_at` | row N `.edited_by_user_id` |

With zero rows the response is a single `is_current` entry: the post as it stands.

`author_username` comes from the existing `crud._fetch_username_map` over the distinct editor ids
(one call per distinct id, degrades to `None` on failure — `crud.py:6493-6513`). A missing name is
rendered as «Пользователь #N», which covers the section-1 edge case of a deleted editor account.

| Code | Condition | Russian `detail` |
|---|---|---|
| 200 | history returned (possibly just the current version) | — |
| 401 | no / invalid token | from `get_current_user_via_http` |
| 403 | caller does not hold `posts:history` (moderator included) | «Недостаточно прав» |
| 404 | post does not exist | «Пост не найден» |

**Honesty about the pre-deployment gap — `is_original` / `original_available`.**
A post edited *before* this feature ships has `edited_at` set and no rows; its true original is
unrecoverable. Whether that is so cannot be derived after the fact, so it is **recorded at write
time**: when `edit_post` writes the *first* row for a post, it sets
`is_original = (posts.edited_at IS NULL)` — i.e. 1 when the text being snapshotted really is the
original, 0 when the post had already been edited in the dark. The column is meaningful only on
`version_no = 1` and must be documented as such. `original_available` in the response is that
flag (and `True` when there are no rows at all and `posts.edited_at IS NULL` — an untouched post
has nothing missing).

The UI states it plainly, never implying the post was untouched:

* `original_available = false`, rows exist → banner «Более ранние версии не сохранились: пост
  редактировали до появления истории правок», and version 1 is labelled «версия неизвестного
  времени» (its `created_at` is `null`).
* zero rows but `post_edited_at` set → «Пост редактировали до появления истории правок —
  сравнивать не с чем.»

**No diff endpoint.** The server ships both texts; the diff is the client's job. Keeping a diff
algorithm out of Python avoids a backend dependency and keeps the two sides from disagreeing.

### 3.7 Where the write goes

Inside `crud.edit_post`, in the same transaction, in this order:

1. extend the existing `SELECT ... FOR UPDATE` (`crud.py:1390-1398`) with
   `content, edited_at, edited_by_user_id` — no new query, no new lock;
2. after all validation passes and **immediately before** the `UPDATE posts …` at `crud.py:1544`,
   `INSERT INTO post_versions (...)` with the row's *old* `content`, the computed `version_no`,
   `edited_by_user_id = user_id` (the current editor) and
   `is_original = 1 if post_row.edited_at is None else 0`;
3. the existing single `await session.commit()` at `crud.py:1572` covers both.

A failure anywhere rolls both back together: there can be no edit without its record, and no
record without its edit. Writing it *after* the commit, or in a separate session, would break
exactly that.

**No-op edits.** If the submitted `content` is byte-identical to the stored one, write nothing and
skip the `UPDATE` — do **not** create a version row and do **not** move `edited_at`. Otherwise an
admin opening and saving the editor manufactures a fake «изменено» and a duplicate version. The
response is still 200 with the unchanged post.

### 3.8 Frontend design

New component `components/pages/LocationPage/PostVersionHistoryModal.tsx` (TypeScript, no
`React.FC`, Tailwind only), mounted next to `PostEditModal` in `LocationPage.tsx:947`.

* **Entry point (primary):** a fourth item in the post kebab menu (`PostCard.tsx:336-375`),
  «История правок», shown only when `hasPermission(permissions, 'posts:history') && post.edited_at`
  — the permission, never the role string, so a delegated grant works without a deploy. That is
  where the dispute actually happens — the admin is looking at the post — and `currentUserRole`
  is already passed to the card (`LocationPage.tsx:922`), and the user's permission list is
  already in Redux. No new route, no new admin page.
* **Entry point (secondary):** `AdminModerationPage.tsx` already shows «Пост изменён: …»
  (`:311-316`) and has `post_id`. The same modal is opened from a «Показать историю правок» link
  there, gated on `hasPermission(permissions, 'posts:history')` and on `post_id !== null`. The
  modal is therefore written self-contained: it takes `postId` and fetches its own data.
  Confirmed as in scope by the user (3.11 q2).
* **Layout:** `modal-overlay` / `modal-content gold-outline gold-outline-thick` per
  `docs/DESIGN-SYSTEM.md`. Left (or, below `sm:`, top) a scrollable version list — «Версия N ·
  автор · дата», newest first, capped in height so twenty edits stay readable (section 1 edge
  case). Right, the diff between the selected version and the one after it; the newest pair is
  selected on open.
* **Rendering safety:** diff output is inserted as **text nodes**, never
  `dangerouslySetInnerHTML`. The markup panel is a `<pre>` fed via `textContent`. Nothing in this
  modal renders post HTML as markup, so no new DOMPurify call site is introduced.
* **Plain-text extraction** lives in a new `src/utils/postText.ts`: DOMPurify-sanitise, parse into
  a detached node, turn `</p>`, `<br>`, `</blockquote>`, `</li>` boundaries into `\n`, read
  `textContent`. A regex tag strip is **not** acceptable on the client — HTML entities would
  survive it and show up as fake diff noise.
* **Errors (mandatory):** loading, empty, 403 and network failures each render a Russian message
  inside the modal. No silent failure, no blank panel.
* **Responsive from 360px:** single column stacked below `sm:`, list collapsed to a horizontal
  scroller of version chips; diff text wraps with `break-words`; the modal body scrolls, the page
  never scrolls horizontally.
* **Types:** `PostVersionEntry` / `PostVersionHistory` in
  `components/pages/LocationPage/types.ts`, mirroring the Pydantic schemas. No Redux slice —
  LocationPage keeps post state in `useState` (FEAT-159, 3.0) and this is read-only, modal-scoped.

### 3.9 Security and access — the `posts:history` permission

**Decision (user, 2026-09-14, answering 3.11 q1): a grantable permission, granted to no role.**
The endpoint is guarded by `Depends(require_permission("posts:history"))`
(`services/locations-service/app/auth_http.py:72-83`), **not** by `get_strict_admin_user`.

#### Why this satisfies «только админы» *and* CLAUDE.md §10.13

`crud.get_effective_permissions` (`services/user-service/crud.py:14-35`) gives role `admin`
**every row of the `permissions` table**, computed by selecting the table itself. Every other role
gets only its explicit `role_permissions` rows plus `user_permissions` overrides. So a permission
registered with **zero `role_permissions` rows** is, by construction:

* held by every admin, automatically and for ever, including admins created later;
* held by no moderator, no editor, no player;
* **delegable to one named person** through `user_permissions` if the user ever wants to hand post
  history to a specific trusted moderator, without touching code.

That last property is what the hard role gate could not offer. This is the same pattern FEAT-162
established for `characters:teleport`
(`services/user-service/alembic/versions/0028_add_characters_teleport_permission.py`) and this is
its **second** instance — the empty grant is the feature, not an oversight, and the migration
docstring must say so in as many words so nobody later "fixes" it by attaching it to a role.

#### Why the name is `posts:history` and not `moderation:post_history`

Module `posts` does not exist yet; `moderation` does. Putting the action under `moderation` would
be tidier on paper and wrong in practice:

* `AdminPage.tsx:33` renders the «Модерация постов» tile from `hasModuleAccess(perms,
  'moderation')`, i.e. *any* `moderation:*` permission, while the route itself demands
  `moderation:read` (`App.tsx:221-222`). A delegated user holding only `moderation:post_history`
  would therefore see the tile and be bounced back to `/home` on click — **exactly the FEAT-158
  bug, re-created by a naming choice.**
* Single-action modules are already normal here: `photos:upload`, `battles:manage`, `mobs:manage`.
* The admin tile list (`AdminPage.tsx:18-36`) is a hardcoded array, so a new `posts` module adds no
  stray tile anywhere.

New user-service migration `0029_add_posts_history_permission.py`
(`revision = '0029'`, `down_revision = '0028'`), mirroring 0028 exactly: idempotent
SELECT-then-INSERT, no hardcoded ids, **no `role_permissions` insert**, and a `downgrade()` that
deletes `role_permissions` and `user_permissions` rows before the `permissions` row.
Description: «Просмотр истории правок постов (админ)».

#### Checklist

| Question | Answer |
|---|---|
| Authentication | yes — `require_permission` wraps `get_current_user_via_http` |
| Authorisation | `posts:history`; admins hold it implicitly, moderators do not, individuals can be granted it explicitly |
| 403 wording | «Недостаточно прав» — the existing `require_permission` message |
| Input validation | `post_id` is a path `int`; nothing else is accepted |
| Rate limiting | none beyond the gateway defaults — an admin-only read of a small bounded row set |
| Data exposure | the endpoint returns post HTML the post already exposes publicly, plus editor usernames already shown in the moderation queue. No new data class. |
| XSS | diff output is rendered as text; the markup panel is escaped; no new sanitiser call site |
| Deleted content | cascades away with the post (3.3), so a moderation deletion actually deletes |
| Frontend gating | `hasPermission(permissions, 'posts:history')` — never a role string, so a delegated grant lights the UI up without a code change |

### 3.10 Data flow

```
admin opens post kebab -> «История правок»
  -> GET /locations/posts/{id}/versions   (Bearer JWT)
       -> require_permission("posts:history") -> user-service GET /users/me   (permission check)
       -> crud.get_post_versions: SELECT post_versions WHERE post_id ORDER BY version_no
                                + SELECT content, created_at, edited_at, edited_by_user_id FROM posts
                                + _fetch_username_map(distinct editor ids) -> user-service GET /users/{id}
  <- PostVersionHistory
  -> client: postText.toPlainText(v[k]) / (v[k+1]) -> diffWords -> rendered runs

player edits post
  -> PUT /locations/posts/{id}   (unchanged contract)
       -> crud.edit_post, ONE transaction:
            SELECT ... FOR UPDATE (now also returns content/edited_at)
            ... existing validation ...
            INSERT post_versions (old content, version_no, editor, is_original)
            UPDATE posts SET content, edited_at, edited_by_user_id
            [optional PostGateRequest]
            COMMIT

post deleted by moderation
  -> DELETE FROM posts -> InnoDB cascades post_versions away
```

### 3.11 Questions to PM — all three answered (user, 2026-09-14)

1. **Permission vs role gate → a grantable permission, granted to no role.** The user chose the
   second option, which removes the deviation rather than trading against it: see 3.9. A new
   user-service migration registers `posts:history` with zero `role_permissions` rows, the
   locations-service endpoint guards on it via `require_permission`, and the frontend gates on
   `hasPermission(..., 'posts:history')`. `get_strict_admin_user` is **not** used anywhere in this
   feature.
2. **The moderation-queue entry point is wanted — not optional.** The queue already prints «Пост
   изменён» and offers no way to see what changed, which is the moment the history is needed. It
   stays as a first-class task (T9) reusing the same self-contained modal. Note the interaction
   with (1): a moderator sitting in that queue does **not** hold `posts:history` and will not see
   the link unless the user explicitly grants it to them — which is now possible without a deploy.
3. **«Откатить к этой версии» is out of scope — settled, not omitted.** History is read-only. This
   is recorded here so it is not re-litigated: a rollback would have to decide whether it re-opens
   the one-hour edit window, whether it itself creates a version, and whether it may resurrect text
   a moderator removed. None of those questions have been asked, let alone answered, and the
   feature as specified settles disputes without them.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

The feature now spans **two backend services**: user-service registers the permission,
locations-service guards on it. Ordering rationale: T1 registers `posts:history` first, because
an endpoint guarding on a permission no migration created is a permission nobody has — the exact
FEAT-158 failure. T2+T3 then land the schema and the recording of history, which is the
irreversible part (history cannot be captured retroactively). T4 exposes it, T5-T6 test it, the
UI follows.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| **T1** | User-service Alembic migration `0029` registering the permission `posts:history` («Просмотр истории правок постов (админ)») with **no `role_permissions` rows at all**. Mirror `0028_add_characters_teleport_permission.py` exactly: idempotent SELECT-then-INSERT, no hardcoded ids, `downgrade()` deleting `role_permissions` then `user_permissions` then the `permissions` row. The module docstring must state that the empty grant **is the feature** (admins get it implicitly through `get_effective_permissions`; moderators must not; the user may delegate it per-person via `user_permissions`) and must cite `characters:teleport` as the precedent, so a later reader does not "fix" it by attaching it to a role. It must also record why the name is `posts:history` and not `moderation:post_history` (3.9 — the `hasModuleAccess` tile/route mismatch). | Backend Developer | DONE | create `services/user-service/alembic/versions/0029_add_posts_history_permission.py` | — | `docker compose restart user-service` applies it clean and re-running is a no-op; `SELECT * FROM permissions WHERE module='posts'` returns exactly one row; `SELECT * FROM role_permissions rp JOIN permissions p ON p.id=rp.permission_id WHERE p.module='posts'` returns **zero** rows; `alembic downgrade -1` removes the row; `python -m py_compile` passes. |
| **T2** | Alembic migration 040 creating `post_versions` exactly as specified in 3.3, plus the `PostVersion` ORM model. Copy the idempotency / downgrade style of `039_post_gate_requests.py`. Docstring must state **why** `ON DELETE CASCADE` here vs `SET NULL` in 037/039 (3.3), and that `is_original` is meaningful only on `version_no = 1`. | Backend Developer | DONE | create `services/locations-service/app/alembic/versions/040_post_versions.py`; edit `services/locations-service/app/models.py` | — (parallel with T1) | `docker compose restart locations-service` runs the migration clean; `SHOW CREATE TABLE post_versions` shows `ON DELETE CASCADE`, `NOT NULL` `post_id`, and `uq_post_versions_post_version`; re-running `alembic upgrade head` is a no-op; `alembic downgrade -1` drops the table; `python -m py_compile` passes on both files. |
| **T3** | Record a version inside `crud.edit_post` (3.7): extend the existing `SELECT ... FOR UPDATE` with `content, edited_at, edited_by_user_id`; compute `version_no` under that lock; `INSERT` the **old** content immediately before the `UPDATE posts`, in the same transaction, with `is_original = (post_row.edited_at is None)`. Add the no-op-edit short circuit (identical content -> no row, no `edited_at` move, still 200). Do not change the `PUT` request/response contract. | Backend Developer | DONE | `services/locations-service/app/crud.py` (`edit_post`, ~1320-1594) | T2 | Editing a post inserts exactly one row holding the text as it was **before** the edit; a second edit inserts `version_no = 2`; a failing validation inserts nothing; saving identical content inserts nothing and leaves `edited_at` untouched; `PUT /locations/posts/{id}` response body is byte-identical to before; `python -m py_compile` passes; existing `test_post_editing.py` and `test_post_gate_requests.py` still pass. |
| **T4** | `GET /locations/posts/{post_id}/versions` per 3.6: Pydantic v1 schemas `PostVersionEntry` / `PostVersionHistory`, `crud.get_post_versions` implementing the version-mapping table (including `created_at = None` when `original_available` is false), username enrichment through the existing `_fetch_username_map`, route registered next to the other `/posts/` routes and guarded by **`Depends(require_permission("posts:history"))`** — not `get_admin_user`, not `get_strict_admin_user`. 404 «Пост не найден». | Backend Developer | DONE | `services/locations-service/app/schemas.py`, `services/locations-service/app/crud.py`, `services/locations-service/app/main.py` (near `main.py:981-1020`) | T1, T3 | Admin token -> 200 with versions ascending and the current text last; moderator token -> 403 «Недостаточно прав»; player token -> 403; no token -> 401; a non-admin token carrying `posts:history` (delegated) -> 200; unknown id -> 404; an unedited post -> one `is_current` entry with `original_available = true`; a post edited before deployment -> `original_available = false`, version 1 `created_at = null`; a failed username lookup degrades to `author_username = null` and still returns 200; route does not shadow any existing `/posts/` route (check `/openapi.json`); `python -m py_compile` passes. |
| **T5** | User-service RBAC coverage for `posts:history`, in the shape FEAT-162 used — prove the **grant matrix**, not merely that someone gets a 403. Assert the migration's declarative content and its empty role grant (mirroring `test_moderation_permissions.py` layer 1), and assert the *effect* on `crud.get_effective_permissions`: an **admin holds `posts:history`**, a **moderator does not**, a plain user does not, and a user with an explicit `user_permissions` grant does. Extend `test_rbac_permissions.py` alongside the other per-module suites so the "admin has every permission" test keeps covering the new row. | QA Test | DONE | create `services/user-service/tests/test_posts_history_permission.py`; edit `services/user-service/tests/test_rbac_permissions.py` | T1 | `docker exec user-service python -m pytest tests/test_posts_history_permission.py tests/test_rbac_permissions.py -q` passes; a test fails if the migration ever gains a `role_permissions` insert; a test fails if the moderator role acquires the permission; the whole user-service suite still passes. |
| **T6** | Pytest coverage for T3 + T4 in locations-service. Follow `test_post_editing.py` conventions (real aiosqlite for DB facts, `TestClient` with mocked crud for the route). Cover: version row holds the **pre-edit** text; `version_no` increments; **the first edit of a never-edited post captures the original** and sets `is_original = 1`; a post with `edited_at` set and no rows gets `is_original = 0` on its first snapshot; no row on validation failure; no row on a no-op edit; version row and post `UPDATE` are in one transaction (a forced failure after the insert leaves neither); `DELETE FROM posts` cascades the rows away; the 3.6 mapping table including the `created_at = None` case; the auth matrix at the endpoint — admin 200, **moderator 403** (holding `moderation:read`/`moderation:review` but not `posts:history`), plain player 403, anonymous 401, delegated non-admin holding `posts:history` 200; 404. | QA Test | DONE | create `services/locations-service/app/tests/test_post_versions.py` | T4 | `docker exec locations-service python -m pytest app/tests/test_post_versions.py -q` passes; every bullet above has a named test; the whole locations-service suite still passes. |
| **T7** | Add `diff@^9.0.0` (3.2) and create the plain-text helper. Install **inside the container** (`docker exec frontend npm install diff@^9.0.0`) so `package-lock.json` is updated, and commit both files. `src/utils/postText.ts` exports `htmlToPlainText(html: string): string` per 3.8 (DOMPurify + detached DOM + block boundaries -> `\n`) and `isFormattingOnlyChange(a, b): boolean`. No `React.FC`, TypeScript only. | Frontend Developer | DONE | `services/frontend/app-chaldea/package.json`, `services/frontend/app-chaldea/package-lock.json`, create `services/frontend/app-chaldea/src/utils/postText.ts` | — (parallel with T1-T6) | `diff` appears in `dependencies` with no `@types/diff` added; `npx tsc --noEmit` and `npm run build` both pass inside the container; `htmlToPlainText('<p>a&amp;b</p><p>c</p>')` yields `a&b\nc` (entities decoded, block boundary preserved). |
| **T8** | `PostVersionHistoryModal.tsx` per 3.8 + the permission-gated kebab entry. Self-contained: takes `postId`, fetches `GET /locations/posts/{id}/versions`, owns loading / error / empty states in Russian. Version list + diff pane, newest pair preselected, `diffWords` with `maxEditLength` and the oversize fallback, formatting-only banner, collapsed escaped-markup panel, `original_available = false` banner. Add the «История правок» item to `PostCard.tsx`, shown only when `hasPermission(permissions, 'posts:history') && post.edited_at` — **gate on the permission, never on `role === 'admin'`**, so a delegated grant works with no code change. Mount the modal in `LocationPage.tsx`. Add the TS interfaces to `types.ts`. Tailwind only, no SCSS, no `React.FC`, responsive from 360px, diff rendered as text nodes only. | Frontend Developer | DONE | create `services/frontend/app-chaldea/src/components/pages/LocationPage/PostVersionHistoryModal.tsx`; edit `.../LocationPage/PostCard.tsx`, `.../LocationPage/LocationPage.tsx`, `.../LocationPage/types.ts` | T4, T7 | `npx tsc --noEmit` + `npm run build` pass; as admin the entry appears only on edited posts and opens the modal; as a moderator or player it never appears; a word edit shows added/removed runs; a formatting-only edit shows the banner and a non-empty markup panel; a pre-deployment-edited post shows the «не сохранились» banner; a 403/network failure shows a Russian error inside the modal; no console errors; no horizontal scroll at 360px width. |
| **T9** | Reuse the same modal from the moderation queue (confirmed by the user — 3.11 q2): next to the existing «Пост изменён: …» line, a «Показать историю правок» link shown when `hasPermission(permissions, 'posts:history')`, `post_id !== null` and `post_edited_at` is set. No new API, no duplicated component. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/AdminModerationPage/AdminModerationPage.tsx` | T8 | `npx tsc --noEmit` + `npm run build` pass; the link appears for an admin on items whose post was edited and still exists; it opens the same modal with the right `postId`; a moderator without the permission does not see it; no horizontal scroll at 360px. |
| **T10** | Document the new table, the endpoint, the `posts:history` permission and its deliberate zero-role grant, and the CASCADE-vs-SET-NULL rationale. | Backend Developer | DONE | `docs/services/locations-service.md`, `docs/services/user-service.md` (permissions list), `docs/ARCHITECTURE.md` (table list, if it enumerates tables) | T4 | `post_versions`, `GET /locations/posts/{id}/versions` and `posts:history` are documented with the access rule; the docs state that the permission is intentionally granted to no role; no stale claim that post history does not exist. |
| **T11** | Final review: re-run `py_compile`, the user-service and locations-service pytest suites, `npx tsc --noEmit`, `npm run build`; verify live — as an admin open an edited post and read the diff, and confirm a moderator account sees neither the menu entry nor the moderation-queue link and gets 403 from the endpoint — with zero console errors; check the security checklist in 3.9 and the CLAUDE.md §10 frontend rules (Tailwind, TypeScript, no `React.FC`, 360px, Russian strings, every error surfaced) and §10.13 (permission registered by migration). | Reviewer | DONE | — | T1-T10 | Every check above recorded with its result in section 5. A review without both automated results **and** live verification is invalid. |

**DevSecOps: no task.** The route lives under the already-proxied `/locations` prefix, no env var,
no Docker or Nginx change. The single new npm dependency is installed by the existing dev
`npm install` and the existing prod image build — T7 must still run the install inside the
container so the tracked lockfile stays in sync.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-14

**Result:** PASS — ready to ship, with one latent risk recorded in `docs/ISSUES.md` (LOW) and one
gap that no browser was available to close (listed at the end, for a manual pass).

Everything below was re-derived independently: nothing was accepted on the word of a previous
task's log. Where a claim could be settled by *executing* rather than reading, it was.

#### Automated Check Results

| Check | Command | Result |
|---|---|---|
| TypeScript | `docker exec frontend sh -c "cd /app && npx tsc --noEmit"` | **PASS** — exit 0, no output |
| Production build | `docker exec frontend sh -c "cd /app && npm run build"` | **PASS** — `built in 35.89s` |
| `py_compile` (locations) | `crud.py main.py models.py schemas.py alembic/versions/040_post_versions.py tests/test_post_versions.py tests/test_post_editing.py tests/test_post_gate_requests.py` | **PASS** — exit 0 |
| `py_compile` (user) | `alembic/versions/0029_add_posts_history_permission.py tests/test_posts_history_permission.py tests/test_rbac_permissions.py` | **PASS** — exit 0 |
| pytest locations-service (full) | `docker exec locations-service python -m pytest tests/ -q` | **PASS** — `1133 passed, 3 warnings in 22.10s` (matches the expected 1133) |
| pytest user-service (full) | `docker exec user-service python -m pytest tests/ -q` | **PASS** — `1 failed, 517 passed, 5 skipped in 55.21s`; the single failure is `test_profile_customization.py::TestGetUserCharacters::test_get_user_characters_success`, confirmed **the only one** and pre-existing / unrelated |
| pytest, feature suites alone | `tests/test_post_versions.py` / `tests/test_posts_history_permission.py tests/test_rbac_permissions.py` | **PASS** — 42 passed / 109 passed |
| `docker compose config` | — | **PASS** |
| Alembic heads | `alembic current` in both containers | **PASS** — locations `040_post_versions (head)`, user `0029 (head)` |
| `version_table` unchanged | `alembic/env.py` in both | **PASS** — `alembic_version_locations`, `VERSION_TABLE = "alembic_version_user"` |

`SHOW CREATE TABLE post_versions` on dev MySQL matches migration 040 exactly:
`post_id int NOT NULL`, `uq_post_versions_post_version (post_id, version_no)`,
`fk_post_versions_post_id ... ON DELETE CASCADE`, `is_original tinyint(1) NOT NULL DEFAULT '1'`,
`content text NOT NULL`, `ENGINE=InnoDB`.

#### Live Verification Results — backend (via `api-gateway`, real HTTP)

Executed from inside the `locations-service` container against `http://api-gateway` with JWTs minted
from the real `JWT_SECRET_KEY`, on a **purpose-made test post (id 224)** later deleted.

**1. The stored text is the pre-edit text, and the off-by-one is flipped exactly once.**
Three edits by **three different admin accounts** (user 4 «S», user 1 «Dudka», user 3 «Advena»).

Raw storage — each row holds the text the edit *destroyed*:

```
version_no  content(30)            edited_by_user_id  is_original
1           <p>ОРИГИНАЛЬНЫЙ Т...   4                  1
2           <p>ПРАВКА ОДИН ...     1                  0
3           <p>ПРАВКА ДВА ...      3                  0
posts.content = <p>ПРАВКА ТРИ ...  edited_by_user_id = 3
```

API response — the attribution the admin sees:

```
v1 cur=False at=2026-09-14T02:15:47 by=None/None   :: <p>ОРИГИНАЛЬНЫЙ ТЕКСТ…
v2 cur=False at=2026-09-14T02:16:18 by=4/S         :: <p>ПРАВКА ОДИН от админа4…
v3 cur=False at=2026-09-14T02:16:19 by=1/Dudka     :: <p>ПРАВКА ДВА от админа1…
v4 cur=True  at=2026-09-14T02:16:20 by=3/Advena    :: <p>ПРАВКА ТРИ от админа3…
```

«ПРАВКА ОДИН **от админа4**» is attributed to user 4, «ПРАВКА ДВА **от админа1**» to user 1,
«ПРАВКА ТРИ **от админа3**» to user 3. The text names its own author, so a flip in either direction
would have been visible. **Flipped exactly once; each version is blamed on the right person.**

**2. The access rule.** Same post, same endpoint:

| Caller | Result |
|---|---|
| anonymous (no token) | `401 {"detail":"Not authenticated"}` |
| admin (id 4) | `200` |
| **moderator (id 12), holding `moderation:read` AND `moderation:review`** (verified in `role_permissions` for `role_id=3`) | **`403 {"detail":"Недостаточно прав"}`** |
| plain player (id 6) | `403 {"detail":"Недостаточно прав"}` |
| plain player (id 7), **before** delegation | `403` |
| plain player (id 7), **after** `INSERT INTO user_permissions (7, 94, 1)` | **`200`** — no deploy, no code change |
| admin, `post_id = 99999999` | `404 {"detail":"Пост не найден"}` |

`SELECT ... WHERE p.module='posts'`: exactly **one** permission row (id 94, `posts:history`,
«Просмотр истории правок постов (админ)») and **zero** `role_permissions` rows. The delegated grant
was removed again afterwards (`permission_id=94` rows remaining: 0).

**3. The no-op rule.** Re-submitting byte-identical content:
`PUT` → `200`, `edited_at` stayed `2026-09-14T02:18:08`, version count stayed **4** — no row, no
fake «изменено». With a gate attached (`gathering`, on a post long enough to pay the 500-symbol
budget): `PUT` → `200`, version count still **4**, `edited_at` still `02:18:08`, **and**
`post_gate_requests` gained row id 17 with `status=pending`. The gate request is correctly outside
the short circuit.

**4. `original_available = false`.** A post inserted with `edited_at` set and zero version rows:
before any new edit → `original_available=false`, one `is_current` entry. After one edit →
`original_available=false`, `v1 created_at = None`, `v2` current. Exactly the contract in 3.6.

**5. CASCADE — by actual deletion, not by reading the FK.** `DELETE FROM posts WHERE id=225`
(1 version row) → `versions_left_225 = 0`, `versions_left_224 = 4` (untouched). Repeated at cleanup:
deleting post 224 took its 4 rows with it; `post_versions` is back to **0 rows** in the dev database.

#### The two items flagged for scrutiny

**(a) The Cyrillic diff fix — verified by executing a real Russian diff, not by reading the code.**
Run inside the `frontend` container with the actually-installed `diff@9`:

```
Intl.Segmenter available: true | resolved granularity: word

WITH segmenter    : Он [-непринужденно улыбался][+нервно усмехался], глядя на закат…   (2 changed runs)
WITHOUT (fallback): Он не[-п]р[-и][+в]н[-ужденн]о у[-лыб][+смех]ался, глядя на закат…  (6 changed runs)
```

The bug the Frontend Dev found is real and their fix works: the default tokenizer does shred
Cyrillic into per-character runs — the red-and-green wall decision 3.1 exists to avoid, in the only
language this game is written in — and `Intl.Segmenter('ru')` collapses it into two clean runs.

**The fallback path is sane.** Both outputs reconstruct *both* sides losslessly
(`old ok = true, new ok = true` for the segmenter path and for the fallback), so an engine without
`Intl.Segmenter` gets a noisier but still correct and non-crashing diff. The construction is wrapped
in `try/catch` and the type is declared locally rather than by widening the project's `lib` —
proportionate.

**(b) The `maxEditLength` grind — confirmed, and it is a latent risk worth recording.** Measured,
same container, real module:

```
1500 words  /  14 748 chars  ->     415 ms, 348 runs
6000 words  /  59 205 chars  ->   6 577 ms, 1389 runs
12000 words / 118 570 chars  ->  30 121 ms, undefined (cap tripped)
```

So the cap bounds the answer, not the wait: the thread is held for ~30 s before `undefined` comes
back. The modal handles `undefined` correctly (both versions shown whole, with a Russian notice), and
the threshold is unreachable at current post sizes — the longest post in the database is 5 597
characters and a pair of maximum-length posts diffs in well under a second. **Not a blocker, and the
Frontend Dev was right to raise it rather than deviate from 3.2 on their own.** Recorded as a LOW
entry in `docs/ISSUES.md` so it is not rediscovered the day `posts.content` gets longer.

#### Standards and security checklist

| Item | Result |
|---|---|
| No fourth DOMPurify **render** configuration | **OK** — `utils/sanitizePostHtml.ts` is the one post policy; `PostCard.tsx:435` and `AdminModerationPage.tsx:249` are the only two `dangerouslySetInnerHTML` post surfaces and both call it. `PostVersionHistoryModal.tsx` has **no** `dangerouslySetInnerHTML` at all — diff runs are text nodes, the markup panel is escaped source. (`utils/postText.ts:130` does sanitise with its own options before extracting `textContent`; it never renders, and converting it to the shared helper is already tracked in `docs/ISSUES.md` under the sanitiser entry.) |
| Gating reads the permission, never a role | **OK** — `PostCard.tsx:190` `hasPermission(permissions, 'posts:history') && post.edited_at`; `AdminModerationPage.tsx:446` `hasPermission(permissions, 'posts:history')`, plus `post_id !== null` and `post_edited_at`. No `role === 'admin'` anywhere in the feature. Proven live by the delegation test above. |
| `PostEditResponse.edited_at` → `Optional` is safe | **OK** — no other backend service calls `PUT /locations/posts/{id}` (grep over `services/*/app`); the sole client, `LocationPage.handleEditPost` (`LocationPage.tsx:412-431`), reads only `gate_request_id` and refetches; `Post.edited_at` is already `string \| null` in `types.ts`. |
| Pydantic v1 syntax | **OK** — `class Config: orm_mode = True` on both new schemas |
| Sync/async not mixed | **OK** — locations-service stays async throughout |
| Alembic | **OK** — 040 / 0029, both idempotent (`inspector.get_table_names()` / SELECT-then-INSERT), both with a real `downgrade()`; both heads applied |
| No CSS/SCSS added | **OK** — no `.css`/`.scss` file touched anywhere in the working tree |
| No `React.FC` | **OK** — zero occurrences in any feature file |
| Russian user-facing strings | **OK** — every banner, error, label and API `detail`; 401/403/404/5xx/offline each map to a distinct Russian message (`PostVersionHistoryModal.tsx:141-151`) |
| Every error path visible | **OK** — loading / error + «Повторить» / empty / «не сохранились» / «сравнивать не с чем» / oversize notice all render; nothing is swallowed |
| Input validation | **OK** — `post_id` is a path `int`; 422 on a non-numeric id |
| Data exposure | **OK** — post HTML the post already exposes, plus editor usernames already shown in the moderation queue; `_fetch_username_map` degrades to `null` rather than 500 |
| Rate limiting | N/A by design (3.9) — an admin-only read of a small bounded row set behind the gateway defaults |
| QA coverage (backend changed) | **OK** — T5 and T6 exist and are DONE; 42 + 109 tests; both re-run green here |
| Transaction integrity | **OK** — the `INSERT` sits between the existing `SELECT ... FOR UPDATE` and the `UPDATE posts`, under one commit; `version_no` is computed inside the lock with the unique key as backstop |

#### Issues Found

**None.** No file:line issue was found that blocks the feature.

#### Observations (non-blocking, no owner assigned)

1. `docs/services/user-service.md` is a 91-line document with **no permissions list at all** — T10
   named it as a file to edit, but there is no such list to extend, and `characters:teleport`
   (FEAT-162) is not there either. T10's acceptance criteria are met in
   `docs/services/locations-service.md`, which documents the permission, the zero-role grant and the
   naming rationale at length. Not worth inventing a section for one row; flagged only so the
   discrepancy between the task's file list and reality is on the record.
2. `utils/postText.ts:130` keeps its own `USE_PROFILES: { html: true }` sanitise call. It is not a
   render path (the output is `textContent`), so it introduces no XSS surface, and the follow-up is
   already written down in `docs/ISSUES.md`. Noted, not an issue.
3. `PostVersionHistoryModal.tsx:404` uses `versions.indexOf(entry)` inside a reversed `map` — O(n²)
   over the version list. Correct (entries are distinct objects) and irrelevant at any plausible
   version count. No action.

#### Bug tracking

- **Added** to `docs/ISSUES.md` (LOW): «Долг: при срабатывании `maxEditLength` jsdiff молотит ~30
  секунд, блокируя вкладку, и только потом сдаётся» — with the measured numbers above.
- No pre-existing `docs/ISSUES.md` entry is fixed by this feature, so nothing was removed.

#### NOT verified — no browser available

The `claude-in-chrome` extension is **not set up in this session**, so no page was ever opened. The
API, the diff algorithm, the build and the type check were all exercised directly and are covered
above; what remains needs a human with a browser:

1. **Console cleanliness** — open a location page as an admin, open «История правок», switch
   versions, expand «Показать различия в разметке»: there must be zero `console.error`, zero
   unhandled rejections and no 4xx/5xx beyond the intended ones.
2. **The kebab entry actually renders** — «История правок» appears for an admin on an edited post
   and is absent on an unedited one; absent entirely for a moderator and for a player. (The
   permission logic behind it is proven; only the rendering is unconfirmed.)
3. **The moderation-queue link** — «Показать историю правок» next to «Пост изменён: …» in the
   «Намерения» tab opens the same modal with the right `postId`.
4. **Layout at 360px** — the version list collapses to a horizontal chip scroller, the diff wraps,
   and the page does not scroll horizontally.
5. **Visual reading of the diff** — added runs green, removed runs struck through in red, and the
   formatting-only banner appearing on a colour-only edit.

Static evidence that these are wired in, short of a browser: the production bundle contains
«История правок» (3 occurrences), «Текст не изменился» (1), `posts:history` (2) and the `Segmenter`
reference; `GET /` through the gateway answers `200`.

#### Test data cleanup

Test posts 224 and 225, their 5 version rows and gate request 17 were deleted.
`SELECT COUNT(*) FROM post_versions` = **0**; `user_permissions WHERE permission_id = 94` = **0**;
temporary scripts removed from the `locations-service` and `frontend` containers. Nothing was
committed, and no repository file was modified except `docs/ISSUES.md` and this feature file.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-13 — PM: фича создана по запросу пользователя, требования уточнены
[LOG] 2026-09-13 — PM: старт отложен до закрытия FEAT-159 (фаза B) и бага с часовым поясом
[LOG] 2026-09-14 — Architect: начал проектирование, анализ кодовой базы веду сам
[LOG] 2026-09-14 — Architect: проверил edit_post (crud.py:1320-1594) — одна транзакция, один
      commit, SELECT ... FOR UPDATE не читает content. Запись версии ложится внутрь той же
      транзакции, перед UPDATE; SELECT расширяется, лишних запросов не нужно
[LOG] 2026-09-14 — Architect: решён открытый вопрос — различия считаем по ТЕКСТУ (пословно),
      а правку только оформления показываем отдельной плашкой плюс панель с экранированной
      разметкой. Посимвольный diff HTML для спора «кто что написал» бесполезен
[LOG] 2026-09-14 — Architect: выбрана библиотека diff (jsdiff) ^9.0.0 — ноль зависимостей,
      типы в комплекте, BSD-3-Clause, последняя публикация 2026-04-13; в package.json её нет
[LOG] 2026-09-14 — Architect: версия = текст ДО правки. Иначе оригинал — то самое, что
      цитировали, — теряется навсегда при первой же правке
[LOG] 2026-09-14 — Architect: post_versions.post_id = NOT NULL + ON DELETE CASCADE. Это не
      копия соглашения FEAT-158: там строки — решения модерации и переживают пост, здесь строка
      это копия самого поста, и после удаления она не архив, а уцелевший кусок удалённого
[LOG] 2026-09-14 — Architect: замерил объём — 118 постов, в среднем 598 символов, 0.07 МБ.
      Храним полные копии версий, без дельт и лимитов
[LOG] 2026-09-14 — Architect: первая редакция доступа — get_strict_admin_user (позже заменена). Разрешения
      moderation:read / moderation:review миграция 0027 выдала модераторам, переиспользовать их
      нельзя — это ровно та ловушка, что была в FEAT-162
[LOG] 2026-09-14 — Architect: первая версия плана — 9 задач, 3 вопроса к PM в разделе 3.11
[LOG] 2026-09-14 — PM: пользователь ответил на все три вопроса
[LOG] 2026-09-14 — Architect: доступ переведён с жёсткой проверки роли на разрешение posts:history,
      выданное ни одной роли — админ получает его автоматически, модератор нет,
      а конкретному человеку его можно выдать через user_permissions без выката.
      Это второй случай паттерна characters:teleport (FEAT-162)
[LOG] 2026-09-14 — Architect: имя разрешения — posts:history, а не moderation:post_history: плитка
      «Модерация постов» показывается по hasModuleAccess('moderation'), а маршрут требует
      moderation:read — имя внутри модуля moderation воскресило бы баг FEAT-158
[LOG] 2026-09-14 — Architect: ссылка из раздела модерации подтверждена пользователем — задача T9,
      больше не опциональная; откат к версии — сознательно вне скоупа, история только на чтение
[LOG] 2026-09-14 — Architect: план пересобран — 11 задач на два сервиса, миграция разрешения идёт
      первой, QA доказывает матрицу доступа (админ имеет, модератор нет), а не просто 403
[LOG] 2026-09-14 — Backend Dev: T1 готова — миграция 0029 регистрирует разрешение
      posts:history без единой записи в role_permissions. Проверено на dev MySQL:
      upgrade -> downgrade -1 -> upgrade head проходит чисто, version_table остался
      alembic_version_user, повторный прогон после stamp 0028 дубля не создаёт.
      Матрица доступа подтверждена через get_effective_permissions: админ — есть,
      модератор / редактор / игрок — нет, а точечная выдача через user_permissions
      модератору работает (проверено и откачено). Тесты user-service: 482 passed,
      1 failed (известный давний test_get_user_characters_success), 5 skipped
[LOG] 2026-09-14 — Frontend Dev: T7 готова — diff@9.0.0 поставлен внутри контейнера (ноль
      транзитивных зависимостей, типы в комплекте, @types/diff не нужен), package.json и
      package-lock.json обновлены. Создан src/utils/postText.ts: htmlToPlainText (DOMPurify +
      DOMParser + границы блоков как перевод строки + декодирование сущностей) и isFormattingOnlyChange.
      Намеренно НЕ переиспользует stripHtmlTags из gateConstants.ts — тот зеркалит счётчик
      сервера и склеивает абзацы; разница описана комментарием в postText.ts.
      Проверено: npx tsc --noEmit и npm run build в контейнере проходят, хелпер прогнан на
      реальных входах (многоабзацный пост, сущности, вложенное оформление, пустая строка, null)
[LOG] 2026-09-14 — Backend Dev: T2 готова — миграция 040 создаёт post_versions
      (post_id NOT NULL + ON DELETE CASCADE, uq_post_versions_post_version,
      is_original TINYINT(1) DEFAULT 1, content TEXT), в models.py добавлена
      модель PostVersion. В докстрингах зафиксировано, почему здесь CASCADE, а не
      SET NULL как в 037/039 (строка — копия контента поста, а не решение
      модерации), и что is_original осмыслен только на version_no = 1.
      Проверено на dev MySQL: head был 039, upgrade -> downgrade -1 -> upgrade head
      проходит чисто, повторный upgrade head — no-op, version_table остался
      alembic_version_locations. Каскад проверен фактическим удалением: под тестовый
      пост вставлены 2 версии, DELETE FROM posts убрал их обе (0 строк осталось),
      тестовые данные подчищены. py_compile обоих файлов проходит.
      Тесты locations-service: 1091 passed
[LOG] 2026-09-14 — Backend Dev: T3 готова — запись версии вшита в ту же транзакцию
      edit_post. Существующий SELECT ... FOR UPDATE теперь тянет ещё content,
      edited_at и edited_by_user_id — лишнего запроса и лишней блокировки нет.
      Версия хранит текст ДО правки: version_no = MAX + 1 считается под тем же
      локом, INSERT идёт непосредственно перед UPDATE posts, коммит остался
      один — правки без записи и записи без правки быть не может.
      is_original пишется как (posts.edited_at IS NULL): у поста,
      отредактированного до выката, самый ранний текст честно помечается как
      невосстановимый. Добавлен короткий выход на no-op: побайтово одинаковый
      текст не создаёт ни строки версии, ни фальшивого «изменено»; заявка на
      намерение при этом всё равно подаётся — это отдельное действие.
      Проверено вживую через api-gateway и подтверждено в MySQL: строки версий
      содержат именно ДО-текст (v1 = оригинал, v2 = текст после первой правки,
      posts.content = текст после второй).
[LOG] 2026-09-14 — Backend Dev: T4 готова — GET /locations/posts/{id}/versions под
      Depends(require_permission("posts:history")). Схемы PostVersionEntry /
      PostVersionHistory на Pydantic v1, сдвиг на единицу разворачивается один раз
      на сервере в crud.get_post_versions, имена редакторов берутся существующим
      _fetch_username_map. Живая проверка: админ 200 (версии по возрастанию,
      текущий текст последним, у каждой версии свой автор и своё время),
      модератор с moderation:read и moderation:review — 403 «Недостаточно прав»,
      обычный игрок — 403, без токена — 401, несуществующий пост — 404,
      точечная выдача через user_permissions не-админу — 200. Пост без правок —
      одна запись is_current с original_available = true; пост с edited_at,
      выставленным до появления истории, — original_available = false и
      created_at = null на первой версии. Маршрут не перекрывает существующие
      /posts/ (проверено по openapi.json). Тестовые данные удалены.
[LOG] 2026-09-14 — Backend Dev: ВНИМАНИЕ для QA и Reviewer — тест
      test_post_editing.py::TestGateSymbolBudget::test_exactly_the_required_length_is_accepted
      падает НЕ случайно: он отправляет побайтово тот же текст и ждёт
      edited_at is not None, а по 3.7 такая правка теперь no-op. Сознательно не
      правил его сам. Также PostEditResponse.edited_at стал Optional —
      иначе no-op над ни разу не правленным постом отдал бы 500 вместо 200;
      на фронте Post.edited_at уже nullable. В фикстуры test_post_editing.py и
      test_post_gate_requests.py добавлена таблица PostVersion (без изменения
      ассертов) — без неё падали 23 теста на «no such table».
      Итог прогона: 1090 passed, 1 failed (описанный выше).
[LOG] 2026-09-14 — QA: T5 готова — создан tests/test_posts_history_permission.py (26 тестов) и
      секция 11 в test_rbac_permissions.py (9 тестов). Матрица доступа доказана через
      get_effective_permissions: админ posts:history имеет, модератор — нет (модератору в сиде
      реально выданы moderation:read/review и characters:*, чтобы проверка не была пустой),
      редактор и игрок — нет. Делегирование через user_permissions зафиксировано: точечная
      выдача одному модератору работает, на других модераторов не протекает, granted=False
      снимает право. Содержимое миграции 0029 проверяется двумя слоями: константы и текст файла
      (ревизии 0029/0028, русское описание, отсутствие INSERT INTO role_permissions, порядок
      DELETE в downgrade) плюс РЕАЛЬНЫЙ запуск upgrade()/downgrade() самой миграции на тестовой
      SQLite — поэтому попытка выдать разрешение роли ломает тесты по факту, а не по тексту.
      Проверено мутацией в копии внутри контейнера (/tmp/mut, репозиторий не трогался): добавил
      грант модератору — упало 7 тестов, включая test_moderator_does_not_have_posts_history и
      test_inserts_zero_role_permissions_rows; копия удалена.
      Замечание: тест «админ получает все разрешения» (TestAdminAutoPermissions) работает на
      синтетическом сиде и миграции не читает — сам по себе новую строку он НЕ подхватывает,
      поэтому posts:history засеян явно в секции 11, как и у остальных модулей.
      Прогон: test_posts_history_permission.py — 26 passed; test_rbac_permissions.py — 83 passed;
      вся сюита user-service — 517 passed, 5 skipped, 1 failed (известный давний
      test_get_user_characters_success, единственный и не связан с фичей)
[LOG] 2026-09-14 — QA: T6 готова — создан app/tests/test_post_versions.py (42 теста, два слоя:
      реальный aiosqlite для фактов БД и TestClient с замоканным crud для маршрута).
      Покрыто: строка версии хранит текст ДО правки (в том числе цепочка из двух и трёх
      правок), version_no растёт и уникальный ключ отбивает дубль, is_original = 1 только
      когда пост до этого не правили, одна транзакция (сбой, подброшенный прямо на
      UPDATE posts, не оставляет ни строки версии — плюс контрольный тест, что без сбоя
      строка появляется), CASCADE проверен НАСТОЯЩИМ DELETE FROM posts, а не чтением FK,
      маппинг 3.6 с двумя и тремя разными редакторами (сдвиг на единицу разворачивается
      ровно один раз на сервере), no-op (побайтово тот же текст не пишет версию, не двигает
      edited_at, отдаёт 200 — а заявка на намерение при этом всё равно подаётся),
      original_available = false с created_at = null на первой версии, матрица доступа
      (аноним 401, игрок 403, редактор 403, МОДЕРАТОР 403 при наличии moderation:read и
      moderation:review, админ 200, делегированный через user_permissions не-админ 200),
      404 и 422 на нечисловой post_id.
[LOG] 2026-09-14 — QA: падавший test_exactly_the_required_length_is_accepted починен без
      потери смысла: он проверяет границу бюджета (1000 символов = пять combat-гейтов), а
      не «изменено». Отправляемый текст сделан ДРУГИМ на те же 1000 символов ("б" * 1000)
      вместо побайтовой копии — правка снова реальная, ассерт edited_at is not None остался
      на месте, проверка границы не сузилась.
[LOG] 2026-09-14 — QA: фикстуры сверены с реальной схемой — PostVersion.__table__ совпадает
      с SHOW CREATE TABLE post_versions на dev MySQL (post_id int NOT NULL,
      uq_post_versions_post_version, fk ... ON DELETE CASCADE, is_original tinyint(1)
      DEFAULT 1); проверка зафиксирована тестами TestTheFixtureMirrorsTheRealSchema, чтобы
      расхождение модели и миграции 040 ловилось автоматически.
[LOG] 2026-09-14 — QA: проверено мутациями в копии внутри контейнера (/tmp/mut, репозиторий
      не трогался): (а) сохранение ПОСЛЕ-текста вместо ДО-текста — упало 6 тестов;
      (б) снятие короткого выхода на no-op — упало 3 теста; (в) снятие сдвига на единицу в
      get_post_versions — упало 2 теста. Копия удалена.
[LOG] 2026-09-14 — QA: PostEditResponse.edited_at = Optional безопасен — единственный
      потребитель PUT-ответа (LocationPage.handleEditPost) читает только gate_request_id и
      перезапрашивает пост, Post.edited_at на фронте уже string | null, других сервисов,
      вызывающих этот эндпоинт, нет.
[LOG] 2026-09-14 — QA: прогон locations-service — 1133 passed, 0 failed (было 1090 passed /
      1 failed). Строк в post_versions на dev MySQL не осталось (0).
[LOG] 2026-09-14 — Backend Dev: T10 готова — документация. В docs/services/locations-service.md
      добавлен раздел «История версий поста (FEAT-160)»: хранится текст ДО правки (иначе
      оригинал теряется при первой же правке), сдвиг на единицу и то, что он
      разворачивается ровно один раз на сервере, is_original / original_available и
      честная плашка про пробел до выката, короткое замыкание на no-op вместе с
      сознательным исключением для заявки на гейт, запись внутри существующей
      транзакции edit_post под уже взятым локом, контракт GET
      /locations/posts/{id}/versions с таблицей кодов, и механика разрешения
      posts:history, выданного ни одной роли (второй случай после characters:teleport).
      В «Таблицы БД» добавлена post_versions с отдельным абзацем, почему здесь
      NOT NULL + CASCADE, а не SET NULL как в 037/039, и пометкой «не выравнивать под
      соседей». В docs/ARCHITECTURE.md таблица добавлена в список locations-service.
      Отмечено, что PostEditResponse.edited_at стал Optional и почему. Попутно
      исправлены устаревшие ссылки main.py:980 -> :981 и crud.py:1303 -> :1322.
      Все file:line сверены с реальным кодом.
[LOG] 2026-09-14 — Backend Dev: исправлено вводящее в заблуждение утверждение в CLAUDE.md
      §10.13 — тест «админ имеет все разрешения» (TestAdminAutoPermissions) работает на
      синтетическом сиде из 8 разрешений и миграции не читает, поэтому новое разрешение
      НЕ покрывается автоматически и его надо засеять явно. Долг занесён в docs/ISSUES.md
      (LOW) с предложением guard-теста, сканирующего дерево миграций.
[LOG] 2026-09-14 — Frontend Dev: T8 готова — создан PostVersionHistoryModal.tsx
      (самодостаточный: берёт postId и сам тянет GET /locations/posts/{id}/versions).
      Состояния: загрузка, ошибка с русским текстом и кнопкой «Повторить», список
      версий (новые сверху, «Версия N · автор · время», чип «текущая»), панель
      сравнения «предыдущая -> выбранная», по умолчанию выбрана самая свежая пара.
      Три вида по 3.1: пословный diff текста; плашка «Текст не изменился — правка
      коснулась только оформления» когда текст совпал, а HTML нет; всегда доступная
      свёрнутая панель с diff'ом СЫРОЙ разметки как экранированного текста.
      dangerouslySetInnerHTML в файле нет вообще — новой точки санитизации не
      появилось. Плашка «Более ранние версии не сохранились» на original_available =
      false и отдельный текст, когда сравнивать не с чем. Пункт «История правок» в
      кебабе PostCard и ссылка в модерации закрыты hasPermission(permissions,
      'posts:history') — не ролью: разрешение не выдано ни одной роли, админ имеет
      его неявно, а делегировать его человеку через user_permissions можно без
      выката; проверка роли это бы сломала. Модалка монтируется в LocationPage
      рядом с PostEditModal, типы PostVersionEntry / PostVersionHistory добавлены в
      types.ts и сверены с живым /openapi.json — расхождений нет (живой ответ на
      пост 95 под админом: 200, author_user_id = null у нетронутого оригинала,
      404 «Пост не найден» на несуществующем, 401 без токена).
[LOG] 2026-09-14 — Frontend Dev: ВАЖНО — diffWords из jsdiff по умолчанию для
      РУССКОГО текста работает как ПОСИМВОЛЬНЫЙ diff. Его токенайзер
      (node_modules/diff/libesm/diff/word.js) знает только латиницу, кириллица
      попадает в ветку «одиночный не-словесный символ». На реальном посте #95
      правка «непринужденно улыбался» -> «нервно усмехался» выдавала
      не[-п]р[-и][+в]н[-ужденн]о у[-лыб][+смех]ался — ровно та красно-зелёная каша,
      ради отказа от которой в 3.1 и выбран текстовый diff. Исправлено штатным для
      jsdiff способом: intlSegmenter = Intl.Segmenter('ru', {granularity:'word'}),
      создаётся один раз на модуль, при отсутствии Intl.Segmenter тихо откатывается
      на встроенный токенайзер. После правки тот же случай даёт два чистых прогона:
      [-непринужденно улыбался][+нервно усмехался]. Intl.Segmenter не типизирован
      при lib: ES2020 — типы объявлены локально, tsconfig проекта не трогал.
[LOG] 2026-09-14 — Frontend Dev: diff прогнан на РЕАЛЬНЫХ данных (пост #95 из
      fogdatabase, 3471 символ, через jsdom и настоящие модули postText.ts + diff).
      Пословная правка — 3 изменённых прогона; правка только оформления
      (цвет + em->strong) — isFormattingOnlyChange true, в текстовом diff 0
      изменений, панель разметки показывает rgb([-255][+120], [-153][+200],
      [-0][+255]) и <[-em][+strong]>; htmlToPlainText сохраняет границы абзацев.
      Худший РЕАЛЬНЫЙ случай (два разных поста по ~9000 символов, максимум в базе)
      считается за 439 мс. Замечание для Reviewer/PM: порог maxEditLength = 20000
      на реальных постах недостижим, а когда он всё же срабатывает (синтетика:
      по 12000 слов с каждой стороны) jsdiff доходит до порога ~34 секунды,
      блокируя вкладку, и только потом возвращает undefined. Сознательно не
      отступал от 3.2 — выношу как наблюдение, а не как самовольную правку.
[LOG] 2026-09-14 — Frontend Dev: T9 готова — в очереди модерации рядом со строкой
      «Пост изменён: …» появилась ссылка «Показать историю правок» (только при
      hasPermission 'posts:history', post_id !== null и post_edited_at). Открывает
      ту же модалку с нужным postId, нового API и дубля компонента нет. Замечание
      по контракту: post_edited_at есть только у PostGateRequestRead — у заявок на
      удаление и жалоб этого поля нет (сверено по /openapi.json), поэтому ссылка
      живёт именно во вкладке «Намерения», где строка «Пост изменён» и существует.
[LOG] 2026-09-14 — Frontend Dev: проверка — npx tsc --noEmit внутри контейнера
      frontend: 0 ошибок; npm run build: успешно (built in 35.34s). Tailwind без
      SCSS, React.FC не используется, весь текст русский, адаптив от 360px (список
      версий ниже sm превращается в горизонтальный скроллер чипов, diff переносится
      по break-words).
[LOG] 2026-09-14 — Reviewer: начал финальную проверку T11, всё перепроверяю сам, на слово
      предыдущим задачам не верю
[LOG] 2026-09-14 — Reviewer: автоматические проверки зелёные. npx tsc --noEmit — 0 ошибок,
      npm run build — успешно (35.89 s), py_compile всех изменённых файлов обоих сервисов —
      чисто, pytest locations-service — 1133 passed, pytest user-service — 517 passed,
      5 skipped, 1 failed (давний test_get_user_characters_success, единственный и не связан
      с фичей). docker compose config — валиден. alembic current: locations 040_post_versions
      (head), user 0029 (head), имена version_table не менялись. SHOW CREATE TABLE
      post_versions совпадает с миграцией 040 (post_id NOT NULL, ON DELETE CASCADE,
      uq_post_versions_post_version, is_original tinyint DEFAULT 1)
[LOG] 2026-09-14 — Reviewer: главное проверено вживую на отдельном тестовом посте (id 224):
      три правки ТРЕМЯ РАЗНЫМИ админами (4, 1, 3), причём текст каждой правки называет своего
      автора. В таблице лежит текст ДО правки, а в ответе API каждая версия приписана верному
      человеку: «ПРАВКА ОДИН от админа4» → пользователь 4, «ПРАВКА ДВА от админа1» →
      пользователь 1, «ПРАВКА ТРИ от админа3» → пользователь 3. Сдвиг на единицу развёрнут
      РОВНО ОДИН РАЗ — перепутать людей в споре нельзя
[LOG] 2026-09-14 — Reviewer: матрица доступа подтверждена вживую через api-gateway. Аноним —
      401, админ — 200, МОДЕРАТОР — 403 «Недостаточно прав», хотя в role_permissions у роли 3
      реально лежат moderation:read и moderation:review (это и был главный риск регрессии),
      обычный игрок — 403, несуществующий пост — 404. Точечная выдача posts:history игроку
      через user_permissions — 200 без выката и без правки кода; грант снят обратно.
      В permissions ровно одна строка module='posts' и НОЛЬ строк в role_permissions
[LOG] 2026-09-14 — Reviewer: no-op подтверждён: побайтово тот же текст даёт 200, не создаёт
      версию и не двигает edited_at, но заявка на гейт при этом всё равно заводится
      (post_gate_requests, status=pending). original_available = false и created_at = null на
      первой версии воспроизведены на посте с edited_at и без строк истории. CASCADE проверен
      НАСТОЯЩИМ DELETE FROM posts, а не чтением FK: строки версий удалённого поста ушли,
      у соседнего поста остались на месте
[LOG] 2026-09-14 — Reviewer: находку фронтендера про кириллицу проверил ИСПОЛНЕНИЕМ, а не
      чтением кода — прогнал настоящий русский diff в контейнере на установленном diff@9.
      Без сегментера «непринужденно улыбался» → «нервно усмехался» даёт 6 посимвольных
      прогонов (та самая красно-зелёная каша), с Intl.Segmenter('ru') — 2 чистых прогона.
      Запасной путь без Intl.Segmenter не падает и восстанавливает обе стороны без потерь —
      просто шумнее. Фикс правильный и нужный
[LOG] 2026-09-14 — Reviewer: замерил и порог maxEditLength — 14 748 символов считаются за
      415 мс, 59 205 — за 6,6 с, а 118 570 молотят 30,1 с и только потом отдают undefined.
      На реальных постах (максимум 5 597 символов) недостижимо, модалка undefined
      обрабатывает корректно. Занёс как латентный риск в docs/ISSUES.md (LOW) с замерами —
      фичу не блокирует, фронтендер правильно вынес это наблюдением, а не самовольной правкой
[LOG] 2026-09-14 — Reviewer: четвёртой конфигурации DOMPurify не появилось — обе точки рендера
      постов (PostCard, AdminModerationPage) зовут общий sanitizePostHtml, а в модалке
      dangerouslySetInnerHTML нет вообще. Доступ везде читается по РАЗРЕШЕНИЮ, не по роли.
      PostEditResponse.edited_at = Optional безопасен: других сервисов-потребителей нет,
      единственный клиент читает только gate_request_id. CSS/SCSS не добавлен, React.FC нет,
      весь текст русский, все пути ошибок видимы
[LOG] 2026-09-14 — Reviewer: браузерная проверка НЕ выполнена — расширение claude-in-chrome в
      этой сессии не подключено, ни одна страница не открывалась. Что осталось непроверенным
      глазами, перечислено в разделе 5 отдельным списком для ручного прогона: консоль без
      ошибок, отрисовка пункта кебаба и ссылки в модерации, вёрстка на 360px, цвета diff'а.
      Косвенно: собранный бандл содержит «История правок», «Текст не изменился»,
      posts:history и ссылку на Segmenter, GET / через gateway отдаёт 200
[LOG] 2026-09-14 — Reviewer: тестовые данные подчищены — посты 224 и 225, их 5 строк версий и
      заявка на гейт удалены, post_versions снова 0 строк, делегированный грант снят,
      временные скрипты из контейнеров удалены
[LOG] 2026-09-14 — Reviewer: проверка завершена, результат PASS. Блокирующих замечаний нет,
      фича готова к выкату
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

FEAT-159 дала игрокам править свои посты. Пометка «изменено» говорила, что правка была, но не что
именно изменилось — а в ролевой игре реплику могли процитировать до правки, и спор разрешить нечем.

Теперь админ видит историю: список версий с датами и авторами, и **различия** — что добавлено,
что убрано.

### Решения, которые определили результат

**Версия хранит текст ДО правки.** Если хранить «после», при первой же правке исходная
формулировка теряется навсегда — а именно её и цитируют.

**Сравнение по тексту, но правки оформления не прячутся.** Посимвольное сравнение разметки
окрашивает весь абзац, стоит появиться одному тегу курсива — бесполезно ровно в том случае, ради
которого фичу делали. Чистое сравнение текста наоборот скрыло бы правку цвета целиком. Поэтому:
сравнение слов по тексту, баннер «Текст не изменился — правка коснулась только оформления», когда
изменилось лишь оформление, и отдельная панель с разницей в самой разметке, показанной **как
текст**, а не как HTML.

**Правка, ничего не меняющая, не создаёт версию** и не двигает пометку «изменено» — подделать
факт правки нельзя. Исключение сделано сознательно: заявка на намерение при неизменном тексте
всё равно подаётся.

**Доступ — разрешение `posts:history`, не выданное ни одной роли.** Админ получает все разрешения
автоматически, модератор не получает, а при необходимости право можно выдать **одному человеку**
без выката. Второе применение этого приёма после `characters:teleport`.

**Каскадное удаление, вопреки соседним таблицам.** Записи модерации намеренно переживают удаление
поста — это решения сотрудников. Версия же это **копия содержимого поста**, и осиротевшая она
означала бы, что удалённый модератором текст остался лежать в базе.

### Что нашлось по ходу

**Библиотека сравнения считает словами только латиницу.** На кириллице каждая буква становилась
отдельным токеном — то есть получалось посимвольное сравнение, ровно то, от чего отказались при
проектировании. Поймано **исполнением**, а не чтением кода:

```
было:  не[-п]р[-и][+в]н[-ужденн]о у[-лыб][+смех]ался
стало: [-непринужденно улыбался][+нервно усмехался]
```

Если бы агент ограничился «типы сходятся, сборка зелёная», фича выехала бы бесполезной на том
единственном языке, на котором написана вся игра.

**Утверждение в CLAUDE.md оказалось неверным.** Там было сказано, что тест «у админа есть все
разрешения» подхватывает новые автоматически. Проверка показала: он работает со своим набором из
восьми разрешений и до миграций не добирается. Мы дважды за сессию полагались на эту фразу.
Формулировка исправлена.

### Проверка

- `locations-service` — 1133 теста (было 1091), `user-service` — 517. Сборки фронта зелёные.
- Три правки тремя разными админами: каждая версия приписана правильному автору — сдвиг на
  единицу в таком инструменте означал бы обвинение не того человека.
- Модератор получает отказ, хотя владеет всей модерацией; выданное персонально право открывает
  доступ без выката.
- Каскад доказан настоящим удалением, а не чтением внешнего ключа.
- Мутации: хранить текст «после», убрать защиту от пустой правки, убрать сдвиг в сопоставлении —
  все убиты. Причём мутация со сдвигом сначала убивалась одним тестом, и QA **дописал** тест на
  цепочку из трёх правок, а не удовлетворился зелёным.

### Оставшиеся риски / follow-up

- **В браузере не проверялось** — расширение Chrome не подключено. Проверить руками: пункт меню
  виден админу и не виден модератору, ссылка из модерации открывает нужный пост, переключение
  версий и панель разметки, вёрстка на 360px, чистая консоль.
- **Долг записан в `ISSUES.md`:** при очень длинных постах (118 тысяч символов) библиотека
  молотит 30 секунд перед отказом — ограничение задаёт предел ответу, но не ожиданию. Сейчас
  недостижимо, но станет реальным, если поднять предел длины поста.
- `docs/services/user-service.md` устарел целиком — там нет ни раздела про роли и разрешения, ни
  таблиц RBAC. Разрешение задокументировано в описании locations-service.

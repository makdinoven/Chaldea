# FEAT-159: Редактирование отправленных постов

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-09-13 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

**Зависит от FEAT-158** — заявки на гейты складываются в раздел модерации, который сейчас
недоступен и показывает пустые данные.

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас пост нельзя отредактировать вообще никак — в locations-service нет ни одного
PUT/PATCH на `/posts`. Опечатку, найденную после отправки, исправить невозможно.

Даём игроку возможность отредактировать **свой** пост в узком окне, когда это ещё никому
не мешает.

### Бизнес-правила

**Кто и когда:**
- Редактировать можно **только свой** пост.
- Только если **после него в локации никто не написал**.
- Только **в течение часа с момента публикации**. Час считается от публикации, а не от
  последней правки — иначе окно продлевается бесконечно.
- **Админы высшего уровня** (роль Admin, не модератор) могут править чужие посты в обход
  обоих ограничений.

**Опыт:**
- Опыт за пост **не пересчитывается**. Начислен при публикации — и всё. Иначе появляется
  способ фармить, дописывая текст.

**Видимость правки:**
- Факт редактирования должен быть **заметен** — пометка «изменено» на посту. В ролевой игре
  это принципиально: реплику могли процитировать до правки.

**Гейты (намерения) — ключевая часть:**
- Гейт, **уже стоящий** в посте, при редактировании **нельзя ни изменить, ни снять**.
  Сработавшую механику откатывать нечем, а подмена намерения задним числом — это абуз.
- Гейт, **добавленный при редактировании** (игрок забыл его при публикации), **не срабатывает
  сразу**. Он создаёт **заявку в раздел модерации** — по образцу существующих запросов на
  удаление поста. Механика открывается только после одобрения админом.
  - Одобрено → гейт становится активным.
  - Отклонено → гейт не выдаётся, права не появляются.
- Обоснование: без гейта механику не запустить вообще (с НПС не поговорить, моба не атаковать),
  поэтому «забыл гейт» = «пиши пост заново». Заявка снимает эту боль, не открывая дыру.

### UX / Пользовательский сценарий
1. Игрок видит на своём посту кнопку редактирования (пока выполняются условия).
2. Жмёт — открывается тот же редактор с текстом поста.
3. Правит текст, при необходимости отмечает забытый гейт.
4. Сохраняет. Текст обновляется, на посту появляется пометка «изменено».
5. Если был добавлен гейт — игрок видит, что заявка ушла на рассмотрение, и механика пока
   недоступна.
6. Админ в разделе модерации видит заявку с текстом поста и решает: разрешить или это абуз.

### Edge Cases
- Кто-то написал пост, пока игрок редактировал → сохранение должно отклониться с внятным
  сообщением, **а текст не должен пропасть** (см. урок FEAT-156).
- Час истёк во время редактирования → то же самое.
- Пост удалён модератором, пока игрок его редактировал.
- Игрок покинул локацию — гейты при выходе истекают (`main.py:1339`, `:1562`); что это значит
  для заявки, поданной до выхода?
- Заявка на гейт уже подана и ещё не рассмотрена → повторную по тому же посту не создавать.
- Пост с уже **потреблённым** (`consumed`) гейтом — редактирование текста разрешено, гейт нет.
- Правка сокращает текст ниже бюджета символов, которого хватало на уже выданные гейты.
- Админ правит чужой пост — пометка «изменено» должна это отражать честно.

### ⚠️ Жёсткое требование — бюджет символов

Гейты покупаются **длиной текста**: 200 знаков за цель для боя, 500 за остальное, минимум 300
(`crud.py:21-27`, `crud.py:55-62`). При редактировании бюджет обязан считаться **по всем гейтам
поста разом — старым и новым**.

Если проверять только новые, то пост на 1000 знаков с пятью уже выданными гейтами можно
отредактировать и «добавить» ещё пять за те же 1000 знаков — бюджет удваивается. Это самый
эксплуатируемый путь во всей фиче, и он целиком зависит от того, как написан эндпоинт.

### Вопросы к пользователю
- [x] Видно ли, что пост отредактирован? → **Да, должно быть заметно.**
- [x] Пересчитывать опыт? → **Нет, редактор просто по факту.**
- [x] Час от публикации или от последней правки? → **От публикации.**
- [x] Можно ли менять/снимать уже стоящий гейт? → **Нет.**
- [x] Что делать с забытым гейтом? → **Заявка в модерацию, админ решает.**
- [x] Кто может править чужое? → **Только админы высшего уровня.**
- [x] Запрещать ли цели, появившиеся в локации **позже** поста? Анализ предлагает это как защиту
      от «написал размыто, подождал час, решил кого имел в виду». Возможно избыточно, раз заявку
      и так смотрит админ. → **Решено на проектировании: НЕТ (раздел 3.9).**

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Key findings from the read-only gate analysis (verified against code):

- **No post edit path exists.** locations-service has no PUT/PATCH on `/posts`; posts are
  immutable once created.
- **Gates cost nothing but text length.** `create_action_gates` (`crud.py:969-990`) touches only
  its own table — no stamina, items, currency or cooldown. `_validate_intent_post`
  (`main.py:772-790`) checks only that every gate has ≥1 target and that the stripped content
  meets `required_symbols_for_gates` (`crud.py:55-62`).
- **`action_gates.created_at` is never read** by any query anywhere — no ORDER BY, no comparison.
  Gates do not reserve targets, do not block other players, and decide no race. Two characters can
  hold `combat` gates on the same mob simultaneously.
- **No target validation at post time** — nothing checks the target exists, is on the location,
  is a mob vs a player, or is alive. Combat and forced PvP have downstream checks in
  battle-service (`main.py:790-799`, `:1177-1180`); `gathering` / `dungeon` / `npc_dialogue`
  have none.
- **Gate consumers** are cross-service: mob combat and forced PvP (`battle-service/app/main.py`),
  dungeon entry (`dungeon-service/app/http_clients.py:67-81`, `gameplay.py:651`), gathering
  (in-process, `locations-service/app/main.py:3462`, `:3473`). Gates expire only on leaving the
  location (`main.py:1339-1343`, `:1562-1566`) — never by clock.
- **Forced PvP already has an admin approval flow** backed by Redis
  (`battle-service/app/main.py:1160-1244`, permission `battles:manage`) — a precedent worth
  reading before designing the gate-request flow, though note it consumes the gate *before*
  filing the request and does not refund on reject.
- **`posts.post_type` is vestigial** — written unvalidated (`crud.py:962`), `move_and_post`
  writes the literal `"gated"` (`main.py:1227`) which is not even in the documented enum, and
  **nothing reads it**. `action_gates` rows are the sole source of truth. Do not start trusting
  `post_type`.
- **Deleting a post does not revoke its gates** — `ON DELETE SET NULL` (`models.py:184`), rows
  survive as `open`. Tracked in FEAT-158; this feature depends on it being fixed, since a
  rejected gate request must leave no rights behind.
- **FEAT-145 design intent** (`features/FEAT-145-rp-post-gating.md`, status CONCEPT): gating is a
  friction/pacing mechanism and an audit trail. The spec explicitly states the system checks only
  length and target selection, and that **semantic abuse is caught by admins after the fact** —
  which is exactly what the moderation-request design for retro-added gates implements.

### Risks
- The character-budget exploit described in section 1 — highest severity, purely a function of
  endpoint implementation.
- Retro-added gates let a player name targets that arrived *after* the post was written. The
  moderation step is the intended mitigation; the architect should decide whether an additional
  `created_at` guard is warranted (it would be the first place `action_gates.created_at` is ever
  compared).
- An edit endpoint is a new write path on `posts`, which several services read. Check consumers
  before changing the shape of anything.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Re-verification of section 2 against current code (post FEAT-156/157/158)

Every file:line in section 2 was re-checked. All claims hold; line numbers drifted slightly, and
one claim is now stale.

| Claim in section 2 | Verified | Correction |
|---|---|---|
| No PUT/PATCH on `/posts` anywhere | **YES** | the only `router.put` on a post path are the two FEAT-158 moderation reviews (`main.py:2169`, `:2189`) and the draft slot (`main.py:465`). Posts are still immutable. |
| Gate cost table `crud.py:21-27` | YES | constants block is `crud.py:20-27` (`MIN_POST_LENGTH` 20, `GATED_POST_TYPES` 21, `GATE_SYMBOL_COST` 25-27) |
| `required_symbols_for_gates` `crud.py:55-62` | YES | unchanged |
| `_validate_intent_post` `main.py:772-790` | YES | body is `main.py:772-791` |
| `create_action_gates` `crud.py:969-990` | YES | unchanged |
| `post_type` written unvalidated `crud.py:962` | YES | unchanged |
| `move_and_post` writes literal `"gated"` | YES | now `main.py:1227` |
| Gates expire only on leaving `main.py:1339/1562` | YES | call sites are now `main.py:1341` and `main.py:1564` |
| `action_gates.post_id` is `ON DELETE SET NULL` `models.py:184` | YES | unchanged |
| Gathering gate consumed in-process | YES | check `main.py:3462`, consume `main.py:3473` |
| Cross-service consumers | YES | `battle-service/app/main.py:770-787` (`_consume_combat_gate`), `:1106-1119` (`_consume_pvp_gate`), `dungeon-service/app/http_clients.py:67-81` |
| Deleting a post leaves its gates `open` | **STALE** | FEAT-158 fixed it. `crud.expire_action_gates_for_post` (`crud.py:1091-1105`) is now called in both `review_deletion_request` (`crud.py:2735`) and `review_report` (`crud.py:2773`). This feature relies on that. |
| `action_gates.created_at` never read | YES | still no ORDER BY / comparison anywhere. See 3.9. |

Two additional facts found during design, both load-bearing:

1. **The frontend never calls `POST /locations/posts/`.** Every player post goes through
   `POST /locations/{id}/move_and_post` (`LocationPage.tsx:389-421`). `POST /posts/` is reachable
   but unused by the client. Both paths create gates, so **both** contribute to the budget a post
   has already spent — which is why the edit endpoint must read the budget from `action_gates`
   rather than from any request payload, and is thereby immune to which path created the post.
2. **There is no Redux slice for posts.** `LocationPage.tsx` holds `LocationData` in `useState`
   and re-fetches `GET /locations/{id}/client/details` after every mutation. The edit flow follows
   that pattern — no new slice.

### 3.1 Scope split — text edit first, gate requests second

The feature has two independently shippable halves, and section 4 is ordered so the first can
merge without the second:

- **Phase A (T1–T6)** — edit your own text, the «изменено» marker, the window and
  no-later-post checks. This is the common case and what the user asked for first.
- **Phase B (T7–T13)** — retro-added gates as moderation requests.

Phase A ships a `PUT` that accepts text only. Phase B adds an optional `gates` field to the same
endpoint. No Phase-A contract is broken by Phase B (additive request field, additive response and
`ClientPost` fields, all with defaults).

### 3.2 API contract — the edit endpoint

```
PUT /locations/posts/{post_id}
Auth: Depends(get_current_user_via_http)   (auth_http.py:24)
```

Request (`schemas.PostEditRequest`, Pydantic **v1**):

```python
class PostEditRequest(BaseModel):
    content: str
    # Phase B. Gates to ADD. Existing gates are never named here and can be
    # neither changed nor removed — see 3.6.
    gates: List[GateSpec] = []
```

Note the deliberate omissions: **no `post_type`, no `targets`**. The legacy single-gate shape
(the `crud.normalize_gates` fallback) is not accepted on this new path — there is no legacy client
to support, and accepting it would open a second, differently-validated way to name gates.

Response (`schemas.PostEditResponse`):

```python
class PostEditResponse(BaseModel):
    id: int
    content: str
    length: int
    created_at: datetime
    edited_at: datetime
    edited_by_admin: bool = False
    # Phase B — present only when the edit asked for new gates.
    gate_request_id: Optional[int] = None
    gate_request_status: Optional[str] = None   # always "pending" on creation

    class Config:
        orm_mode = True
```

Status codes:

| Code | Condition | Russian `detail` |
|---|---|---|
| 200 | edited | — |
| 400 | text shorter than `MIN_POST_LENGTH` | `Минимальная длина поста — 300 символов (сейчас: N)` |
| 400 | merged gate budget not met | `Для всех действий этого поста нужно минимум N символов (сейчас: M)` |
| 400 | a requested gate names a target the post already gates | `Гейт на эту цель уже есть в посте` |
| 400 | a requested gate has no targets / unknown type | reuses `_validate_intent_post` wording |
| 403 | not role `admin` and not the owner | `Вы можете редактировать только свои посты` |
| 403 | window expired (owner path) | `Редактировать пост можно в течение часа после публикации` |
| 403 | someone posted after it (owner path) | `После этого поста уже написали — редактирование недоступно` |
| 403 | gate requested but character is not in the post's location | `Чтобы добавить намерение, нужно находиться в этой локации` |
| 404 | post gone | `Пост не найден` |
| 409 | a pending gate request for this post already exists | `Заявка на намерение по этому посту уже на рассмотрении` |

**Every one of these is a rejection that must leave the player's text intact.** That is a frontend
contract (3.10), not a backend one — the backend simply must return a real status code with a
Russian `detail`, never a 200-with-error-body.

**Route registration:** add it next to the other `/posts/` routes (after `main.py:975`, the unlike
route). `PUT /posts/{post_id}` cannot be shadowed by `PUT /{location_id}/draft` (the literal
second segment differs), but the developer must confirm no shadowing after adding it.

### 3.3 Authorisation and the two limits

```
if current_user.role == "admin":
        admin path  -> both limits bypassed; edited_by_user_id records who
elif the post's character belongs to current_user:
        owner path  -> both limits enforced
else:   403
```

**Ruling of 2026-09-13 (user), superseding the original ordering.** The admin branch is tested
**first**, so role `admin` bypasses both limits **unconditionally** — on their own posts as well as
on other people's. The original design tested ownership first, which left an admin subject to both
limits on their own post; the user ruled: «Админ должен править и свои посты без ограничений.»

Two things the bypass deliberately does **not** change:

* the **minimum-length check still applies to admins** — the bypass covers the two editing limits,
  not content validation;
* `edited_by_admin` stays `edited_by_user_id != author`, so an admin editing their **own** post
  yields `false` (they *are* the author) and the post is marked plainly «изменено». That is correct
  and must not be "fixed".

Role `admin` only — **not** `get_admin_user`, which also admits moderators
(`auth_http.py:46-55`). The endpoint serves owners too, so the admin test is an `if` inside the
handler rather than a dependency; `get_strict_admin_user` (`auth_http.py:58-70`) is the documented
precedent for the "admin, not moderator" rule and its wording should be reused. Ownership uses the
existing `verify_character_ownership` (`main.py:116-126`) semantics.

No `moderation:*` permission is required to edit — editing someone else's post is a role-gated
staff power per section 1, not a granular permission. (Admin holds every permission automatically,
so adding one would change nothing while growing the RBAC surface.)

`check_not_in_battle` / `check_not_gathering` are deliberately **not** applied. They exist to stop
a player acting while occupied; fixing a typo is not an action, XP is not recomputed, and a
requested gate does not fire until an admin approves it.

### 3.4 The two limits, and concurrency

Both are re-checked **server-side at save time**, inside the same transaction as the UPDATE:

```sql
SELECT id, character_id, location_id, created_at FROM posts WHERE id = :pid FOR UPDATE;

-- limit 1: nobody posted after it in this location
SELECT 1 FROM posts WHERE location_id = :loc AND id > :pid LIMIT 1;

-- limit 2: within one hour of PUBLICATION
SELECT :created_at > NOW() - INTERVAL 1 HOUR;
```

Three deliberate choices:

- **`id >`, not `created_at >`.** `posts.id` is a monotonic autoincrement, so it orders posts
  exactly as the feed does (`get_posts_by_location`, `crud.py:1107-1109`, orders by `id DESC`) and
  is immune to two posts sharing a one-second `TIMESTAMP`.
- **The hour is evaluated by MySQL against `NOW()`.** `posts.created_at` is a naive MySQL
  `TIMESTAMP` written by the DB's own `NOW()`. Comparing it in Python against
  `datetime.now(timezone.utc)` is the classic naive/aware bug and would silently shift the window
  by the container's UTC offset. Comparing it to the same server's `NOW()` is self-consistent by
  construction. The window is measured from `created_at` and **never** consults `edited_at`, so
  repeated edits cannot extend it.
- **`FOR UPDATE` on the post row, not on the location.** Locking the location would serialise all
  posting there to protect a check only this endpoint reads. The residual race is one player
  pressing Save in the milliseconds while another's post commits; the consequence is cosmetic (an
  edit lands a moment after a reply). This is **accepted and documented**, not hidden — it must be
  stated in the endpoint docstring.

### 3.5 «Изменено» — storage and display

Migration 038 (locations-service) adds two nullable columns to `posts`:

```sql
ALTER TABLE posts
  ADD COLUMN edited_at TIMESTAMP NULL DEFAULT NULL,
  ADD COLUMN edited_by_user_id INT NULL DEFAULT NULL;
```

Rejected alternative: a generic `updated_at TIMESTAMP ... ON UPDATE CURRENT_TIMESTAMP`. It would
fire on *any* future write to the row — a backfill, an admin script, a column added later — and
turn the whole table into "изменено". `edited_at` is written by exactly one code path and means
exactly one thing.

`edited_by_user_id` is the audit trail. **No third `edited_by_admin` column is stored** — it is
derived for free in `get_post_details` (`crud.py:1774-1814`), which already fetches the author's
profile from character-service and receives `user_id` back:

```
edited_by_admin = edited_at is not None
                  and edited_by_user_id is not None
                  and edited_by_user_id != profile_data.get("user_id")
```

If the profile call fails, `user_id` degrades to `None`, the flag is `False`, and the UI falls back
to a plain «изменено». It never falsely accuses an admin, and it costs zero extra queries.

Surfaced additively on `schemas.ClientPost` (`schemas.py:525-541`):
`edited_at: Optional[datetime] = None`, `edited_by_admin: bool = False`. `LatestPostResponse`
inherits them. `PostResponse` (the raw-ORM shape returned by `GET /{location_id}/posts/`) is left
untouched — no consumer of it needs the marker.

**No edit history is stored** — see 3.13, Q1.

Rollback: `DROP COLUMN edited_at, edited_by_user_id`. No data loss beyond the marker itself.

### 3.6 The character budget — the hard requirement

This is the exploit named in section 1 and it is decided entirely here.

**Rule: the budget is always recomputed over the post's ENTIRE gate set — every row in
`action_gates` for that post regardless of status, plus every gate inside a `pending`
`post_gate_requests` row for that post, plus the gates being requested now.** The request payload
is never the source of truth for what the post already bought; `action_gates` is.

```
existing  = SELECT action_type, target_ref FROM action_gates WHERE post_id = :pid
            -- ALL statuses: open, consumed AND expired
pending   = gates JSON of any pending post_gate_requests row for :pid
requested = body.gates

merged    = crud.merge_gate_lists(existing, pending, requested)  # group by action_type,
                                                                 # union target sets
required  = crud.required_symbols_for_gates(merged)              # existing helper, unchanged
if char_count < required: 400
```

Four details, each closing a hole:

1. **All statuses count, including `expired`.** Gates expire when the character leaves the
   location (`crud.py:1079-1089`). Counting only `open` rows would mean: buy five gates, step next
   door and back (all five expire), edit, "add" five more against the same text. The post bought
   those gates; the budget stays spent.
2. **Pending requests count.** Otherwise two edits in a row, each filing a request, each validated
   against an unchanged `action_gates`, double the budget through the request queue instead of
   through the gate table.
3. **Union of targets, not concatenation.** `required_symbols_for_gates` charges
   `cost * max(1, len(targets))` per entry, so two entries of the same `action_type` do sum
   correctly — but a target named twice would be charged twice *and* would create a duplicate
   gate. Merging by `action_type` with a set union makes the sum exact.
4. **A requested target that already has a gate on this post is a 400, not a silent merge.** It is
   either a client bug or an attempt to "re-buy" a consumed gate. Reject it loudly.

**The same computation runs a second time, independently, at approval time** (3.7). Between the
request and the admin's click the post can be edited again and shortened. Validating only at
request time would let a player file a request against a 2000-char post, cut it to 300, and have
the admin approve gates the text no longer pays for.

`merge_gate_lists` is a new **pure** function in `crud.py`, placed next to `normalize_gates`. It
must be pure and separately unit-testable, because it is the single point where this entire class
of exploit is closed — QA tests it directly, not only through the endpoint.

The shortening edge case from section 1 («правка сокращает текст ниже бюджета уже выданных
гейтов») falls out of the same rule for free: the merged set includes the existing gates, so a text
cut below their cost is rejected with the same 400. Already-granted gates are never revoked by an
edit — the edit simply does not happen.

**Shipped in Phase A (review #1, issue #1).** That last paragraph was originally left to T8, which
would have shipped Phase A without the invariant at all. The existing-gate half of the rule is
therefore implemented now, in `crud.edit_post`:

* `crud.gate_list_for_post(session, post_id)` reads **every** `action_gates` row of the post —
  `open`, `consumed` **and** `expired` (rule 1) — inside the same transaction and under the same
  `FOR UPDATE` lock, one query, after the `MIN_POST_LENGTH` check.
* `crud.merge_gate_lists(*gate_lists)` is the pure grouping function of rule 3 (group by
  `action_type`, union the targets, a `None` target kept as a distinct member). Phase A passes one
  list; **T8 adds the pending-request list and `body.gates` as further arguments and changes
  nothing else** — it extends this code rather than replacing it.
* `crud.required_symbols_for_gates` is reused unchanged, so the server and the client mirror
  (`gateConstants.ts`) cannot drift.
* A post with no gate rows is untouched: only `MIN_POST_LENGTH` applies, with its own wording.
* The check applies to **admins too**, exactly like the minimum-length check — the 2026-09-13
  ruling bypasses the two editing limits, not content validation.

400 `detail`: `Для всех действий этого поста нужно минимум {required} символов (сейчас: {actual})`.

### 3.7 Retro-added gates — the moderation request flow

**A new table, not a reused one.** `post_deletion_requests` and `post_reports` have the right shape
but cannot carry a gate payload, and `review_deletion_request` **deletes the post** on approve.
Bolting a nullable `gates` JSON plus a `kind` discriminator onto that table would put a
"grant rights" branch inside the function whose other branch destroys a post — the single most
dangerous place in this service to add a conditional. Minimal diff means minimal *risk*, not
minimal table count.

What **is** reused: the moderation section itself, its permissions (`moderation:read` /
`moderation:review`, user-service migration `0027`), the request/review endpoint shape, the
enrichment helper `_enrich_moderation_items` (`crud.py:2587-2622`), the `post_id`-nullable
`ON DELETE SET NULL` policy from migration 037, and the admin page's card layout.

Migration 039 (locations-service):

```sql
CREATE TABLE post_gate_requests (
  id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  post_id             INT          NULL,      -- FK posts.id ON DELETE SET NULL (policy of 037)
  character_id        INT          NOT NULL,
  location_id         BIGINT       NOT NULL,  -- FK Locations.id ON DELETE CASCADE
  user_id             INT          NOT NULL,  -- requester
  gates               JSON         NOT NULL,  -- [{"action_type": "...", "targets": [...]}]
  status              VARCHAR(20)  NOT NULL DEFAULT 'pending',
                                              -- pending | approved | rejected | expired
  reviewed_by_user_id INT          NULL,
  created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at         TIMESTAMP    NULL,
  KEY idx_pgr_queue (status, created_at),
  KEY idx_pgr_post  (post_id)
);
```

`post_id` is nullable for the same reason as migration 037: a moderation decision must outlive the
post it is about. No unique index enforces "one pending per post" — MySQL has no partial unique
index, and `UNIQUE(post_id, status)` would forbid a second *rejected* row. The check is code-level
(409), which is adequate: it is a convenience guard, and rule 2 of 3.6 already counts pending
requests toward the budget, so even a duplicate that slipped through could not buy anything.

Rollback: `DROP TABLE post_gate_requests`. Phase A is unaffected.

**Admin endpoints** (mirroring `main.py:2151-2207` exactly):

```
GET /locations/admin/moderation/gate-requests
    Depends(require_permission("moderation:read"))
    -> List[schemas.PostGateRequestRead]

PUT /locations/admin/moderation/gate-requests/{request_id}/review
    Depends(require_permission("moderation:review"))
    body {action: "approve" | "reject"}
    -> schemas.PostGateRequestRead
```

`PostGateRequestRead` carries the moderation-card fields, in the same shape as
`PostDeletionRequestRead` (`schemas.py:723-741`) plus the gate payload:
`id, post_id, user_id, character_id, location_id, gates, status, created_at, reviewed_at,
post_content, post_character_id, post_character_name, post_created_at, post_edited_at,
post_location_name, requester_username, targets_resolved`.

`targets_resolved` is `{action_type: [{"id": n, "name": "..."}]}` — see 3.9. It is **enrichment,
not validation**: it never rejects, and it degrades to bare ids exactly the way
`_enrich_moderation_items` degrades to «Персонаж #id».

**On approve**, in one transaction, in this order:

1. `status == 'pending'`, else 400 `Заявка уже рассмотрена` (mirrors `crud.py:2723`).
2. `post_id IS NOT NULL` and the post still exists, else 409
   `Пост удалён — заявку можно только отклонить`.
3. The character is **still in `location_id`** (`SELECT current_location_id FROM characters`),
   else 409 `Персонаж покинул локацию — заявка больше не действительна`.
4. **Re-run the full merged budget check of 3.6** against the post's *current* content, else 409
   carrying the same required/actual numbers so the admin sees why.
5. `crud.create_action_gates(session, character_id, location_id, post_id, gates)` — the existing
   function, unchanged. This is the only place approval differs from a normal post.
6. `status='approved'`, `reviewed_by_user_id`, `reviewed_at`.

**On reject**: `status='rejected'`, reviewer and timestamp, **and nothing else**. No gate rows, no
partial rights — FEAT-158's rule.

### 3.8 Lifecycle of a pending request (the section-1 edge cases)

| Event | Effect on a pending request | Where |
|---|---|---|
| Player leaves the location | `status='expired'`, no gates | new `crud.expire_gate_requests(character_id, location_id)`, called next to the two existing `expire_action_gates` calls at `main.py:1341` and `main.py:1564` |
| Post deleted by moderation | `status='rejected'` (post gone → no rights) | extend `crud._close_sibling_moderation_rows` (`crud.py:2679-2710`), which both review paths already call **before** the delete nulls `post_id` |
| Admin approves after the player left | 409; the request stays `pending` for a human to reject | approve step 3 |
| Second request on the same post | 409 at request time | 3.7 |
| Post has a `consumed` gate | text edit allowed; the consumed gate still counts toward the budget | 3.6 rule 1 |
| Post deleted while the player is editing | 404 from the edit endpoint, text preserved client-side | 3.2 / 3.10 |

Leaving the location is the event that kills gates. A request that outlived it must not become a
way to resurrect one — hence both a proactive cancel and a defensive re-check. The proactive cancel
also keeps the queue free of dead work, which is precisely what
`_close_sibling_moderation_rows` was written for.

### 3.9 Ruling on the open question: NO `created_at` guard on targets

Section 1's last open question — forbid naming a target that entered the location *after* the post
was written. **Decision: do not implement it.** Three reasons, in order of weight.

1. **It is not implementable for most gate types, and a half-guard is worse than none.** The check
   needs the *target's* arrival time. `action_gates.created_at` is the gate's own creation time and
   cannot answer it. Searching the schema for arrival data:
   - `active_mobs.spawned_at` exists (`character-service/app/models.py:279`), so a `combat` target
     *could* be checked, via a new cross-service call.
   - Players and NPCs have **no arrival history at all**: `characters.current_location_id`
     (`character-service/app/models.py:60`) is a single mutable column, overwritten on every move,
     with nothing recording when. `pvp` and `npc_dialogue` are therefore uncheckable.
   - `gathering` nodes and `dungeon` entrances are fixtures of the location; the question does not
     arise.

   So the guard would cover exactly one intent — `combat`, the cheapest at 200 chars per target —
   and miss `pvp` and `npc_dialogue` at 500 entirely. That is a rule a player cannot reason about
   and a reviewer cannot trust, and it advertises a protection that does not exist. Making it real
   would require a location-arrival audit table written on every character move: a new write on one
   of the hottest paths in the game, for this.

2. **It would forbid the legitimate case far more often than the abusive one.** «Я оглядываю зал в
   поисках собеседника» → an NPC walks in → the player realises they forgot the gate. That is
   exactly the scenario the feature exists to serve, and the guard would reject it while catching
   nothing an admin cannot already see: the admin has the post text and the target in front of
   them.

3. **The path is already the narrowest in the system.** Owner only; within one hour; nobody posted
   after; the full merged budget recomputed twice; and a human approval. FEAT-145's own design
   states that semantic abuse is caught by admins after the fact
   (`features/FEAT-145-rp-post-gating.md`), and a retro-added gate is the one case where that
   review happens *before* the mechanic fires rather than after.

**What we do instead — enrich, don't block.** `targets_resolved` (3.7) shows the admin each
target's real name and current state: «Волк-падальщик #412 — жив, в этой локации», «Мирена #88 —
НПС», «#903 — цель не найдена». Resolution failure is *displayed*, never rejected — a mob
legitimately killed between the request and the review must not auto-deny a valid request. This
puts the judgement exactly where section 1 and FEAT-145 both say it belongs, at the cost of one
batch lookup on a queue page instead of a new table on the movement path.

Follow-up, **not** in this feature: `action_gates.created_at` remains unread, and target existence
is still unvalidated on the *create* path too (section 2). Recorded in `docs/ISSUES.md` as MEDIUM
so the asymmetry is documented rather than discovered later.

### 3.10 Frontend design

**A new `PostEditModal.tsx`, not an `editMode` prop on `PostCreateForm.tsx`.**
`PostCreateForm.tsx` is 771 lines wired end-to-end into the FEAT-156 draft system (`usePostDraft`
at L114-135, `markSent()` at L257, the drafts tab at L587-603), NPC posting, move-and-post
semantics and the XP preview. Editing needs none of those and must actively avoid the first:
reusing the form would have an edit session autosaving over the location's live draft — destroying
text, the exact bug FEAT-156 was built to fix. Threading a mode flag through all of it is a larger
and far riskier diff than a focused modal.

To keep the budget formula in one place on the client, extract from `PostCreateForm.tsx` into a new
`LocationPage/gateConstants.ts`: `GATE_COST` (L18-23), `GATE_LABEL` (L24-29), `GATE_STYLE`
(L31-36), `GATE_ORDER` (L37), `MIN_POST_LENGTH` (L16), `stripHtmlTags` (L77) and the `GateOption` /
`GateOptions` / `PostGate` types (L39-48). `PostCreateForm` imports them instead of declaring them;
no behaviour change. This matters: the client-side counter is the player's only preview of the rule
being enforced, and two copies of it would drift.

`PostEditModal` composes `WysiwygEditor` directly (the same component the form uses at L615-620)
inside the existing `modal-overlay` / `modal-content` classes. It shows:

- the counter `{charCount} / {requiredSymbols} символов`, where `requiredSymbols` is computed over
  **locked existing gates + newly ticked gates** — the client mirror of 3.6;
- **no XP preview**, replaced by the note «Опыт за пост не пересчитывается» — section 1's rule made
  visible rather than merely enforced;
- existing gates as **locked, checked, non-interactive** chips with
  `title="Уже объявленное намерение нельзя изменить или снять"`;
- Phase B only: newly ticked gates carry the hint «Появится после одобрения администратором»;
- an inline error area rendering the backend's Russian `detail` for **every** failure
  (400/403/404/409/5xx and network), which **keeps the modal open with the text untouched**.

The modal is only ever closed by an explicit user action or a 200. This is the FEAT-156 lesson
written as an invariant: **no code path that is not a confirmed success may unmount the editor.**

`PostCard.tsx`: the kebab menu (L277-319, already branching on `isAuthor` at L126) gains
«Редактировать». Visible when `isAuthor && isLatestPostInLocation && withinHour`, or when
`role === 'admin'` using the canonical bypass pattern (`AdminPage.tsx:82-84`). Client-side
visibility is a convenience only; the server re-decides (3.4). `isLatestPostInLocation` is derived
in `LocationPage.tsx` from the already-fetched `location.posts` (index 0 of the `id DESC` feed) —
no extra request.

The marker renders next to the relative time (L247-249), following the existing `(ред.)` precedent
in `Messenger/MessageBubble.tsx:117-121` but spelled out as section 1 requires: «изменено», or
«изменено администратором» when `edited_by_admin`, with a `title` carrying the exact timestamp.

`types.ts` `Post` (L21-38) gains `edited_at?: string | null`, `edited_by_admin?: boolean` and
(Phase B) `pending_gates?: Record<string, number>`. All optional, all additive.

`AdminModerationPage.tsx` gains a third tab «Заявки на намерения» alongside L256-259, reusing
`ModerationCard` (L96-171), `errorMessage` (L73-83) and `isPostMissing` (L59). Its card adds the
gate list and `targets_resolved`; its actions are `approve` / `reject`.

Mandatory rules: all new files `.tsx`/`.ts`; Tailwind only, no new SCSS; **no `React.FC`**
(`const PostEditModal = ({ ... }: PostEditModalProps) => {`); responsive from 360 px (the gate-chip
grid and the modal action row are the two places that break first); Russian strings throughout;
every error surfaced.

### 3.11 Data flow

```
Player  -> PUT /locations/posts/{id}  {content, gates?}
             |
             +- auth (user-service /users/me via auth_http)
             +- BEGIN
             |    SELECT post FOR UPDATE
             |    admin? -> skip both limits, record edited_by_user_id
             |    else owner? -> no later post (id >) ; created_at > NOW() - 1h
             |    char_count >= 300
             |    merged budget over action_gates + pending requests + body.gates
             |    UPDATE posts SET content, edited_at = NOW(), edited_by_user_id
             |    [Phase B] INSERT post_gate_requests (status = 'pending')
             +- COMMIT
             -> 200 PostEditResponse        (gates are NOT created here)

Frontend -> refetch GET /locations/{id}/client/details   (existing pattern)
             -> ClientPost now carries edited_at / edited_by_admin / pending_gates

Admin   -> GET  /locations/admin/moderation/gate-requests      [moderation:read]
             -> enrichment: character-service (names), user-service (usernames),
                character-service (mob/NPC target names) — all best-effort
        -> PUT  .../gate-requests/{id}/review {action}          [moderation:review]
             |
             +- approve: post alive? char still in location? budget still holds?
             |           -> crud.create_action_gates(...)  -> gate is live
             +- reject : status = 'rejected', nothing else
```

No new inter-service **contracts**: enrichment reuses `_fetch_character_brief_map` /
`_fetch_username_map`, already used by the moderation queue. No new queue, no Celery task, no
Redis. battle-service, dungeon-service and the in-process gathering check are untouched — they read
`action_gates`, and this feature only ever writes rows there through the existing
`create_action_gates`.

### 3.12 Security

| Concern | Decision |
|---|---|
| Authentication | required on the edit endpoint (`get_current_user_via_http`); the two admin endpoints additionally `require_permission` |
| Authorisation | owner-or-role-`admin` on edit; `moderation:read` / `moderation:review` on the queue — no new permissions, Admin gets them automatically (CLAUDE.md §10.13) |
| Input validation | `content` length-checked after HTML stripping; `gates` validated through the existing `_validate_intent_post` wording plus the merge rules of 3.6; `action_type` must be in `GATED_POST_TYPES`; targets coerced to `int` |
| XSS | unchanged — storage stays raw HTML, sanitisation stays client-side via `DOMPurify` (`PostCard.tsx:326-337`). The edit path writes the same column as the create path and adds no new rendering surface. `posts.content` is `TEXT`; the 64 KB truncation risk is already tracked in `ISSUES.md` and is not made worse here |
| SQL injection | all new SQL parameterised, consistent with the service |
| Rate limiting | new nginx limit on `PUT /locations/posts/*` in **both** `nginx.conf` and `nginx.prod.conf`, following the FEAT-156 autosave-limit pattern. The endpoint is cheap but is a write on a hot table holding a `FOR UPDATE` lock |
| Information leakage | error details name the rule, never another user; `edited_by_user_id` is never sent to clients — only the derived `edited_by_admin` boolean |
| Privilege escalation | the highest-value target is the budget rule; it is enforced twice (request and approval) and unit-tested as a pure function |

### 3.13 Open questions for PM

**Q1 — should the pre-edit text be kept?** Section 1's justification for the «изменено» marker is
that a line may have been quoted before the edit. That argument also supports keeping the original
somewhere an admin can read. This design **does not store an edit history** (assumption: the marker
alone satisfies the stated requirement, and a history table brings its own retention questions). If
the user wants the original recoverable it is a small addition — one `post_edit_history` table
written in the same transaction — but it should be its own feature, not smuggled in here.

**Q2 — should an edit be announced?** A post edited an hour after publication is invisible to
anyone not re-reading the location. No notification is designed (assumption: out of scope; the
marker is the notification). notification-service integration would be a separate task.

Neither blocks implementation; both are recorded so the decision is explicit rather than accidental.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Phase A — text-only editing (ships independently)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| **T1** | Alembic migration **038** adding `posts.edited_at TIMESTAMP NULL` and `posts.edited_by_user_id INT NULL`, plus the matching columns on the `Post` model. `down_revision` = `037_post_moderation_fk_set_null`. Follow the async env/`version_table` conventions already in the service. | Backend Developer | DONE | `services/locations-service/app/alembic/versions/038_post_edit_columns.py` (new), `services/locations-service/app/models.py` (`Post`, ~L158-172) | — | `alembic upgrade head` then `downgrade -1` both succeed against MySQL 8. Columns exist, are nullable, default NULL. `python -m py_compile` passes on both files. |
| **T2** | Implement `PUT /locations/posts/{post_id}` (text only — accept `content`, ignore/omit `gates` in this phase) per **3.2 / 3.3 / 3.4**. Add `crud.edit_post(...)`, schemas `PostEditRequest` / `PostEditResponse`. The owner path re-checks *both* limits at save time inside the transaction with `SELECT ... FOR UPDATE`; the hour is compared **in SQL** against `NOW()`; "later post" uses `id >`. Role `admin` bypasses both and is recorded in `edited_by_user_id`. XP is **not** recomputed and no XP background task is scheduled. Document the accepted residual race (3.4) in the docstring. | Backend Developer | DONE | `services/locations-service/app/main.py` (new route after L975), `services/locations-service/app/crud.py`, `services/locations-service/app/schemas.py` | T1 | Owner can edit within the hour when last; 403 with the correct Russian `detail` when not last / past the hour / not the owner; 404 when the post is gone; admin bypasses both. `edited_at` set, `created_at` unchanged, no XP awarded. Route reachable and not shadowed by `PUT /{location_id}/draft`. `python -m py_compile` passes. |
| **T3** | Surface the marker: `get_post_details` returns `edited_at` and the **derived** `edited_by_admin` (3.5 — compare `edited_by_user_id` against the profile's `user_id`, degrade to `False` on lookup failure); add both fields with defaults to `schemas.ClientPost`. Verify `LatestPostResponse` and `get_latest_posts_details` still serialise. Do **not** change `PostResponse`. | Backend Developer | DONE | `services/locations-service/app/crud.py` (`get_post_details` L1774-1814, `get_latest_posts_details`), `services/locations-service/app/schemas.py` (`ClientPost` L525-541) | T1 | `GET /locations/{id}/client/details` returns `edited_at` / `edited_by_admin` on every post; unedited posts return `null` / `false`; an admin-edited post returns `true`; a failing character-service profile call yields `false`, never a 500. `python -m py_compile` passes. |
| **T4** | **QA (mandatory).** pytest for T2 and T3 in the service's existing style (`app/tests/`, `conftest.py` mock-session fixture). Must cover: owner edit succeeds; someone posted after → 403; hour expired → 403; not the owner → 403; missing post → 404; admin bypasses both limits; `edited_at` written and `created_at` untouched; **no XP is awarded on edit**; `edited_by_admin` derivation including the degrade-to-`False` path. Plus security cases: editing another player's post as a plain user, and as a **moderator** (must be 403 — moderator is not admin). | QA Test | DONE | `services/locations-service/app/tests/test_post_editing.py` (new) | T2, T3 | All new tests pass; the full locations-service suite stays green. |
| **T5** | Frontend Phase A. (a) Extract the shared gate constants/types out of `PostCreateForm.tsx` into a new `gateConstants.ts` and import them back (no behaviour change). (b) New `PostEditModal.tsx` per **3.10** — `WysiwygEditor`, counter, the «Опыт за пост не пересчитывается» note, no drafts wiring, inline Russian error area, **modal never closes or clears on failure**. (c) «Редактировать» in `PostCard.tsx`'s kebab menu, visible for author+latest+within-hour or `role === 'admin'`. (d) «изменено» / «изменено администратором» next to the timestamp with a `title` carrying the exact time. (e) `Post` type gains `edited_at` / `edited_by_admin`. (f) Wire in `LocationPage.tsx`: `PUT ${BASE_URL}/locations/posts/{id}`, derive `isLatestPostInLocation` from `location.posts[0]`, refetch client details on success. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/LocationPage/gateConstants.ts` (new), `.../PostEditModal.tsx` (new), `.../PostCreateForm.tsx`, `.../PostCard.tsx`, `.../types.ts`, `.../LocationPage.tsx` | T2, T3 | Editing own latest post within the hour works end-to-end; the marker appears. Every failure (403/404/409/500/network) shows a Russian message **with the text still in the editor**. Tailwind only, no `React.FC`, layout intact at 360 px. `npx tsc --noEmit` **and** `npm run build` both pass. |
| **T6** | Rate-limit `PUT /locations/posts/*` in both nginx configs, following the FEAT-156 draft-autosave limit pattern. Keep dev and prod in sync (CLAUDE.md §8.1). | DevSecOps | DONE | `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` | T2 | `nginx -t` passes in both configs; a normal edit is unaffected; a burst is throttled with the service's existing error shape. |

### Phase B — retro-added gates as moderation requests

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| **T7** | Alembic migration **039** creating `post_gate_requests` exactly as specified in **3.7** (FKs, indexes, `post_id` nullable / `SET NULL`), plus the `PostGateRequest` model. `down_revision` = `038`. | Backend Developer | TODO | `services/locations-service/app/alembic/versions/039_post_gate_requests.py` (new), `services/locations-service/app/models.py` | T1 | `upgrade head` / `downgrade -1` both succeed. Deleting a post nulls `post_id` instead of removing the row. `python -m py_compile` passes. |
| **T8** | Accept `gates` on the edit endpoint. Add the **pure** helper `crud.merge_gate_lists(...)` and implement the budget rule of **3.6** in full: existing `action_gates` rows of **every** status + gates inside any `pending` request + the newly requested ones, merged by `action_type` with a **union** of targets; duplicate target → 400; one pending request per post → 409; gate requests require the character to be in the post's location → 403. Create the `post_gate_requests` row — **never** call `create_action_gates` here. Return `gate_request_id` / `gate_request_status`. | Backend Developer | TODO | `services/locations-service/app/main.py`, `services/locations-service/app/crud.py`, `services/locations-service/app/schemas.py` | T2, T7 | A 1000-char post with five existing gates **cannot** add a sixth; the 400 names the required and actual counts. No `action_gates` row is created by an edit. Second pending request → 409. Existing gates cannot be named, changed or removed through this endpoint. `python -m py_compile` passes. |
| **T9** | Admin side per **3.7 / 3.8**: `GET /locations/admin/moderation/gate-requests` (`moderation:read`) and `PUT .../gate-requests/{id}/review` (`moderation:review`). Approve re-checks, in order: still pending → post alive → character still in the location → **the full merged budget again** → then `create_action_gates`. Reject leaves **nothing** behind. Add `crud.expire_gate_requests(character_id, location_id)` and call it beside the existing `expire_action_gates` calls at `main.py:1341` and `main.py:1564`. Extend `_close_sibling_moderation_rows` to close pending gate requests as `rejected` when a post is deleted. Add `targets_resolved` enrichment (best-effort, never rejects, never 500s). | Backend Developer | TODO | `services/locations-service/app/main.py`, `services/locations-service/app/crud.py`, `services/locations-service/app/schemas.py` | T8 | Approve creates exactly the requested gates and they are then honoured by `check_action_gate`. Reject creates none. Leaving the location expires the pending request. Deleting the post rejects it. Approving a request whose post was shortened below the merged budget → 409. Enrichment failure degrades to bare ids. `python -m py_compile` passes. |
| **T10** | Surface `pending_gates` (`{action_type: count}`) on `ClientPost` via a batch query alongside `gates_for_posts` (`crud.py:1059-1076`), wired into the client-details assembly (`crud.py:1699-1704`) and the latest-posts widget. | Backend Developer | TODO | `services/locations-service/app/crud.py`, `services/locations-service/app/schemas.py` | T7 | A post with a pending request reports it; approved/rejected/expired requests do not appear. Additive, default `{}`. `python -m py_compile` passes. |
| **T11** | **QA (mandatory).** pytest for T8–T10. **The budget-doubling exploit is a named, explicit test case** — a post that has already spent its length on gates must not be able to buy more by editing, including via the `expired`-status path and via a second pending request. Also: `merge_gate_lists` tested **directly as a pure function** (union, duplicate detection, cost summation); approve creates gates, reject creates none; approve after the player left → 409; approve after the post was shortened → 409; post deleted → request rejected; leaving the location expires the request; `moderation:read` / `moderation:review` enforced (no permission → 403). | QA Test | TODO | `services/locations-service/app/tests/test_post_gate_requests.py` (new) | T8, T9, T10 | All new tests pass; the full locations-service suite stays green. The exploit test fails against a naive "validate only the new gates" implementation — verify that it does by temporarily breaking the rule. |
| **T12** | Frontend Phase B in the edit modal: existing gates as locked/checked/non-interactive chips with the Russian tooltip; new gates selectable with the «Появится после одобрения администратором» hint; the counter's `requiredSymbols` computed over locked **+** new; after a successful save with new gates, tell the player the request went to moderation; a «на рассмотрении» badge on `PostCard` driven by `pending_gates`. | Frontend Developer | TODO | `.../LocationPage/PostEditModal.tsx`, `.../PostCard.tsx`, `.../types.ts`, `.../LocationPage.tsx` | T5, T8, T10 | A locked gate cannot be unticked. The counter matches the server's required figure (no false "you may save"). The pending badge appears and disappears on approval. Tailwind only, no `React.FC`, 360 px intact. `npx tsc --noEmit` and `npm run build` pass. |
| **T13** | Third tab «Заявки на намерения» in `AdminModerationPage.tsx`, reusing `ModerationCard`, `errorMessage` and `isPostMissing`. Card shows post text, author, requested gates with `targets_resolved` names, and Одобрить / Отклонить. Handle the 409s from T9 by showing the server's Russian `detail` and refreshing the list. | Frontend Developer | TODO | `services/frontend/app-chaldea/src/components/AdminModerationPage/AdminModerationPage.tsx` | T9 | Tab lists pending requests with counts; approve and reject both work and remove the card; every error path shows a Russian message. Tailwind only, no `React.FC`, 360 px intact. `npx tsc --noEmit` and `npm run build` pass. |

### Closing

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| **T14a** | **Phase A documentation only** (split out of T14 per review #2's recommendation, so Phase A does not ship undocumented). In `docs/services/locations-service.md`: the `PUT /locations/posts/{post_id}` contract with every guard and its Russian `detail`, the `id >` / SQL-`NOW()` choices, XP not recomputed, the unconditional `admin` bypass of the two limits (not of the content checks) and moderator ≠ admin; the `posts.edited_at` / `edited_by_user_id` columns and why not `updated_at ON UPDATE`; `ClientPost.edited_at` / the derived `edited_by_admin` with its degrade-to-`false`; the gate symbol budget **as enforced today** (`gate_list_for_post` over **all** statuses + `merge_gate_lists` + the check in `edit_post`); the nginx rate limit. In `docs/ISSUES.md`: the §3.9 MEDIUM follow-up. **No Phase-B content.** | Backend Developer | DONE | `docs/services/locations-service.md` (sections «Посты», «Таблицы БД»), `docs/ISSUES.md` | T2, T3 | Doc matches the real code (every file:line re-verified against source, not against section 3); the ISSUES entry names service, files and priority and duplicates nothing. |
| **T14** | Documentation **(Phase B remainder)**: add `post_gate_requests`, the gate-request flow and the two moderation endpoints to the service doc. Extend the edit-endpoint section with the `gates` field, the merged budget over pending requests, and `ClientPost.pending_gates`. The Phase A half and the §3.9 `ISSUES.md` entry are already done in **T14a** — do not repeat them. | Backend Developer | TODO | `docs/services/locations-service.md` (sections «Посты», «Редактирование поста», «Таблицы БД», «Клиентские / Admin») | T9 | Doc reflects the shipped Phase B endpoints and the `post_gate_requests` table. |
| **T15** | **Reviewer.** Re-run `python -m py_compile`, the full locations-service pytest suite, `npx tsc --noEmit` and `npm run build`. Live-verify: edit a post inside the window; confirm the marker; confirm a rejection leaves the text in the editor; confirm the budget exploit is actually blocked against a running service; confirm the moderation tab approves and rejects. Check the security checklist of **3.12** and the cross-service contracts of **3.11**. | Reviewer | TODO | — | T1–T14 | All automated checks green **and** live verification recorded with evidence. A review without both is invalid. |

**Ordering note for PM:** T1–T6 are a complete, shippable feature on their own. If Phase B slips,
Phase A can merge and the user gets what they asked for first.

---

## 5. Review Log (filled by Reviewer — in English)

### Phase A (T1–T6) — Review #1 — 2026-09-13

**Result: FAIL** — one blocking issue (#1). Everything else in T1–T6 verified and correct.

Scope of this review is **Phase A only**. Phase B (T7–T13) is not implemented and was not
reviewed. T15 is **not** marked done — it covers the whole feature.

#### Automated Check Results

| Check | Command (run by Reviewer) | Result |
|---|---|---|
| TypeScript | `docker exec frontend sh -c "cd /app && npx tsc --noEmit"` | **PASS** — exit 0, no output |
| Frontend build | `docker exec frontend sh -c "cd /app && npm run build"` | **PASS** — `built in 36.33s` (pre-existing >500 kB chunk warning only) |
| `py_compile` | `main.py crud.py schemas.py models.py alembic/versions/038_post_edit_columns.py tests/test_post_editing.py` | **PASS** — `PY_COMPILE_OK` |
| pytest (full suite) | `docker exec locations-service sh -c "cd /app && python -m pytest tests/ -q"` | **PASS** — `959 passed, 3 warnings in 16.74s` (matches the expected figure) |
| Alembic | `docker exec locations-service alembic current` | **PASS** — `038_post_edit_columns (head)`; `version_table="alembic_version_locations"` unchanged (`alembic/env.py:61,72`) |
| `nginx -t` (dev) | `nginx -t` on `docker/api-gateway/nginx.conf` inside `api-gateway` | **PASS** — syntax ok / test successful |
| `nginx -t` (prod) | same, on `nginx.prod.conf`, with a throwaway self-signed cert at the Let's Encrypt paths (removed afterwards) | **PASS** — syntax ok / test successful |
| `docker compose config` | — | **PASS** |

#### Live Verification Results

The `claude-in-chrome` extension is **not connected** in this session, so **no step below ran in a
real browser**. Everything was driven through the api-gateway (`http://api-gateway`, i.e. the same
path the SPA uses) with real JWTs from `POST /users/login`, plus direct MySQL inspection.
**Not verified in a browser and therefore still open:** the modal's visual layout at 360 px, the
kebab-menu «Редактировать» visibility logic, the «изменено» marker rendering, the inline error area,
the "text survives a failure" behaviour as seen by a user, and the browser console being clean.
These were verified by code reading only.

Actors: a freshly registered plain user (id 35) + character 999801, a second registered user
promoted to `moderator` (id 36) + character 999802, and `chaldea@admin.com` (id 4, role `admin`,
character 214). A throwaway location 999901 was used so no live feed was touched. All rows removed
afterwards (see Cleanup).

| # | Scenario | Expected | Actual |
|---|---|---|---|
| 1 | owner edits own latest post, 5 min old | 200 | **200**, response keys exactly `id, content, length, created_at, edited_at, edited_by_admin`; `edited_by_admin=false` |
| 2 | owner, someone posted after it | 403 | **403** `После этого поста уже написали — редактирование недоступно` |
| 3 | owner, post 3 h old but still the latest | 403 | **403** `Редактировать пост можно в течение часа после публикации` |
| 4 | **moderator** on another player's post | 403 | **403** `Вы можете редактировать только свои посты` — `get_admin_user` correctly not used |
| 5 | admin on **their own** 3 h-old, already-answered post | 200 | **200**, `edited_by_admin=false` (admin is the author — the 2026-09-13 ruling) |
| 6 | admin on another player's post | 200 | **200**, `edited_by_admin=true` |
| 7 | admin sends an 8-char body | 400 | **400** `Минимальная длина поста — 300 символов (сейчас: 8)` — the bypass does not skip length validation |
| 8 | missing post | 404 | **404** `Пост не найден` |
| 9 | no token / body without `content` | 401 / 422 | **401** `Not authenticated`; **422** FastAPI validation shape |
| 10 | `GET /locations/{id}/client/details` | marker surfaced | **200**; edited posts carry `edited_at`, `edited_by_admin` (`true` only for the admin-on-another's-post case); untouched posts `null` / `false` |
| 11 | MySQL after the edits | `created_at` untouched, `edited_at` set, editor recorded | confirmed: every `created_at` unchanged to the second; `edited_at` written; `edited_by_user_id` = 4 (admin) and 35 (owner) |
| 12 | XP after two owner edits, the second adding ~1300 chars | unchanged | `character_attributes(999801)` stayed `active_experience=0, passive_experience=0` — no XP, no background task |
| 13 | nginx limiter: 40 × `PUT /locations/posts/{id}` | throttled | **11 × 404 (through) + 29 × 429** — 1 + `burst=10`, exactly as configured |
| 14 | the 429 body | HTML, no JSON `detail` | confirmed `<html>…429 Too Many Requests…` — the frontend's dedicated 429 branch in `LocationPage.tsx` is **required**, and is present |
| 15 | neighbour routes, 30 requests each: `/posts/latest`, `/posts/character-stats`, `/posts/{id}/like`, `/unlike`, `/request-deletion`, `/report`, `/posts/as-npc`, `/{id}/client/details` | never throttled | **0 × 429 on all eight** — `^/locations/posts/[0-9]+$` shadows nothing |
| 16 | **gate budget after shrinking an edited post** | 400 | **200 — see issue #1** |

The api-gateway image ships its nginx config baked in, so for checks 13–15 the new
`nginx.conf` was copied into the running container and reloaded, then the original was restored and
reloaded (verified: `grep -c post_edit_limit /etc/nginx/nginx.conf` → 0 again).

#### Verified by code review

- **T5a is a pure refactor.** `requiredSymbolsForGates` (`gateConstants.ts:80-88`) adds
  `?? 0` and `Math.max(1, …)` versus the inlined formula it replaced, but `activeGates`
  (`PostCreateForm.tsx:151-153`) is already filtered to `targets.length > 0` and typed to
  `GATE_ORDER`, so both are no-ops — and they now match the server
  (`crud.required_symbols_for_gates`) exactly. No other module imported these symbols; the
  re-export in `PostCreateForm.tsx:29` keeps its public surface intact.
- **`PostEditModal` is genuinely standalone.** No `usePostDraft`, no `markSent`, no drafts tab, no
  import of `PostCreateForm` — the only shared code is `gateConstants.ts` (pure data) and
  `WysiwygEditor` / `ConfirmDialog`. An edit session cannot touch the location's live draft.
- **No failure loses text.** `handleSave` (`PostEditModal.tsx:89-110`) calls `onClose()` only after
  `onSave` resolves; every rejection lands in `setError` with the text untouched, the overlay is
  deliberately not click-to-close, and «Отмена» with unsaved edits goes through `ConfirmDialog`.
  `handleEditPost` (`LocationPage.tsx:345-370`) maps string `detail` → verbatim, array `detail`
  (422) → generic Russian, no `response` (network) → Russian, 429 → Russian, anything else →
  Russian with the status. `fetchLocationData` swallows its own errors, so a failed post-save
  refetch cannot surface as a false save failure.
- **Rules agree across code, tests and section 3.** The admin branch is tested first
  (`crud.py:1176-1182`), `edited_by_admin = not is_owner`, minimum length still applies to admins,
  and section 3.3 documents the 2026-09-13 ruling with the superseded version clearly marked as
  history. No leftover asserts or docstrings claim the old ordering.
- Mandatory frontend rules: Tailwind only (no CSS/SCSS touched), all new files `.tsx`/`.ts`,
  no `React.FC`, `sm:` breakpoints and `break-words` throughout the modal, all strings Russian.
- Security: `edited_by_user_id` never leaves the service; all new SQL is parameterised; error
  details name the rule, never another user; auth required; rate limit present in both configs.

#### Issues Found

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/locations-service/app/crud.py` (`edit_post`, `gate_list_for_post`, `merge_gate_lists`) | **The gate budget was not re-checked on edit, so an edit could strip the text that paid for the post's gates.** Reproduced live before the fix: a post holding five `open` `combat` gates (1000 symbols at creation) edited to 307 plain characters returned **200**, and `client/details` still reported `gates: {combat: 5}`. **RESOLVED 2026-09-13.** `edit_post` now computes `required_symbols_for_gates` over `gate_list_for_post(post_id)` — every `action_gates` row of the post, **all statuses including `expired`** so that leaving and re-entering the location cannot refund the budget — in the same transaction and under the same `FOR UPDATE` lock, and rejects with 400 `Для всех действий этого поста нужно минимум N символов (сейчас: M)`. It applies to admins as well; a gateless post is unaffected. The grouping is the new pure `merge_gate_lists(*gate_lists)`, written so T8 merely passes the pending-request and newly-requested lists alongside the existing one. Re-verified live: exploit → **400** with the content and `edited_at` untouched in MySQL; same post edited back to 1000 chars → 200; 999 chars → 400; gates set to `expired` then shrunk → still 400; admin → same 400; gateless post → 300 OK / 299 the plain minimum-length 400. See section 3.6. | Backend Developer | **RESOLVED** |
| 2 | `docs/services/locations-service.md` | Documentation for the edit endpoint and the two new `posts` columns sits in **T14**, which depends on T9 (Phase B). If Phase A ships alone the endpoint ships undocumented. Suggest splitting the Phase-A part of T14 out. | PM / Backend Developer | NOTE |
| 3 | — | Not blocking, FYI: `/tmp/crud.py.bak` and `/tmp/probe.py` are left inside the `locations-service` container from QA's mutation testing. Container-local debris only; the repository and the running source are clean (full suite green, diff reviewed). | QA Test | NOTE |

No pre-existing bugs were found beyond the one the Frontend Developer already filed in
`docs/ISSUES.md` (`formatRelativeTime` reads naive server timestamps as local time) — that entry is
accurate and correctly scoped out of this feature.

#### Cleanup

All fixture rows removed: posts, `action_gates`, `post_deletion_requests`, `post_reports`,
`post_likes`, `character_attributes`, characters 999801/999802, location 999901 and users 35/36
(verified 0 rows remaining for each). The api-gateway config and `/etc/letsencrypt` were restored;
temporary scripts and certificates deleted.

### Phase A (T1–T6) — Review #2 — 2026-09-13

**Result: PASS** — issue #1 of review #1 is genuinely closed, nothing regressed, no new
blocking issue. Two non-blocking notes carried forward (one resolved, one still open).

Scope is **Phase A only**. Phase B (T7–T13) is not implemented and was not reviewed.
T15 is **not** marked done — it covers the whole feature.

Every check below was re-run by the Reviewer from scratch; none of the Backend Dev's or
QA's reported results were taken on trust.

#### Automated Check Results

| Check | Command (run by Reviewer) | Result |
|---|---|---|
| TypeScript | `docker exec frontend sh -c "cd /app && npx tsc --noEmit"` | **PASS** — exit 0, no output |
| Frontend build | `docker exec frontend sh -c "cd /app && npm run build"` | **PASS** — `built in 33.72s` (pre-existing >500 kB chunk warning only) |
| `py_compile` | `main.py crud.py schemas.py models.py alembic/versions/038_post_edit_columns.py tests/test_post_editing.py` | **PASS** — `PY_COMPILE_OK`, exit 0 |
| pytest (full suite) | `docker exec locations-service sh -c "cd /app && python -m pytest tests/ -q"` | **PASS** — `992 passed, 3 warnings in 15.52s` — exactly the reported figure, zero failures. Re-run after all live testing: `992 passed` again |
| Alembic | `docker exec locations-service alembic current` | **PASS** — `038_post_edit_columns (head)`; `version_table="alembic_version_locations"` unchanged (`alembic/env.py:61,72`) |
| `nginx -t` (dev) | `nginx -t -c` on `docker/api-gateway/nginx.conf` inside `api-gateway` | **PASS** — syntax is ok / test is successful |
| `nginx -t` (prod) | same, on `nginx.prod.conf`, with a throwaway self-signed cert at the Let's Encrypt paths | **PASS** — syntax is ok / test is successful |
| `docker compose config` | — | **PASS** |
| Source ↔ container parity | `md5sum` of `crud.py main.py schemas.py models.py tests/test_post_editing.py` inside `locations-service` vs the repo | **PASS** — identical; the suite ran against the real shipped source, not a leftover mutant |

#### Independent mutation check of the fix

QA reported an 8-mutant kill sweep. Rather than trust it, four mutants were re-applied by
the Reviewer to a **container-local copy** (`/rvwmut`; the repo and the running source were
never touched, and the copy was deleted afterwards). Every one is killed:

| Mutation | Result |
|---|---|
| `gate_list_for_post` filtered to `AND status = 'open'` (the subtle hole) | **4 failed**, incl. `test_expired_gates_still_count`, `test_mixed_statuses_are_all_charged`, `test_gate_list_for_post_reads_every_status` |
| budget check disabled (`if False:`) | **10 failed** |
| off-by-one (`char_count + 1 < required`) | **5 failed** |
| admin exempted from the budget (`and not is_admin`) | **2 failed** |

The tests would therefore have caught the original bug. `merge_gate_lists` is also tested
directly as a pure function (15 cases, `TestMergeGateLists`), as section 3.6 requires.

#### Live Verification Results

The `claude-in-chrome` extension is **not connected** in this session (confirmed by invoking
the skill: «Browser tools are not available in this session»), so **no step below ran in a
real browser**. Everything was driven through the api-gateway (`http://api-gateway`, the same
path the SPA uses) with real JWTs from `POST /users/login`, plus direct MySQL inspection.

**Still verified by code reading only, exactly as in review #1:** the modal's layout at
360 px, the kebab-menu «Редактировать» visibility, the «изменено» marker rendering, the
inline error area as a user sees it, the "text survives a failure" behaviour in the UI, and
the browser console being clean.

Actors: three freshly registered accounts — `rvw2_owner` (id 38, role `user`, character
999801), `rvw2_mod` (id 39, promoted to `moderator`, character 999802) and `rvw2_admin`
(id 40, promoted to `admin`, character 999803). Four throwaway locations (999901–999904) so
that each scenario's post could be the newest in its own feed and the limits would be reached
in the intended order. No live feed or existing account was touched. All rows removed
afterwards (see Cleanup).

**A. The gate budget — issue #1 of review #1, reproduced and confirmed closed**

Fixture: post 185, five `combat` gates (targets 9001–9005) → required 1000 characters.

| # | Scenario | Expected | Actual |
|---|---|---|---|
| A1 | **the exploit**: gates `open`, shrink to 307 | 400 | **400** `Для всех действий этого поста нужно минимум 1000 символов (сейчас: 307)` |
| A1-db | MySQL immediately after A1 | nothing changed | **confirmed** — `CHAR_LENGTH(content)` unchanged, `edited_at` still `NULL`, `edited_by_user_id` still `NULL`, all **five gate rows** still present with their statuses |
| A2 | **the `expired` path**: all five gates forced to `expired` (what leaving and re-entering a location does), shrink to 307 | 400 | **400**, same message — a status filter here would have reopened the hole; there is none |
| A3 | all five gates forced to `consumed`, shrink to 307 | 400 | **400**, same message |
| A4 | mixed statuses (2 `open`, 1 `expired`, 2 `consumed`), shrink to 307 | 400 | **400**, same message; post still untouched in MySQL |
| A5 | **admin** (`rvw2_admin`) shrinks the same gated post to 307 | 400 | **400**, same message — the 2026-09-13 ruling frees admins from the hour and the "someone posted after" limits, **not** from the gate budget |
| A6 | exact boundary: edit to exactly 1000 | 200 | **200**, `edited_by_admin=false`, `created_at` unchanged, `edited_at` set |
| A7 | exact boundary: 999, one character less | 400 | **400** `… нужно минимум 1000 символов (сейчас: 999)` |
| A8 | gateless post → 300 | 200 | **200** |
| A9 | gateless post → 299 | 400 | **400** `Минимальная длина поста — 300 символов (сейчас: 299)` — the **minimum-length** wording, not the gate wording |

**B. Phase A behaviour re-confirmed after the change**

| # | Scenario | Expected | Actual |
|---|---|---|---|
| B1 | owner edits own latest post inside the hour | 200 | **200**, `edited_by_admin=false` |
| B2 | owner, someone posted after it | 403 | **403** `После этого поста уже написали — редактирование недоступно` |
| B3 | owner, post 3 h old but still the latest | 403 | **403** `Редактировать пост можно в течение часа после публикации` |
| B4 | **moderator** on another player's post | 403 | **403** `Вы можете редактировать только свои посты` — `get_admin_user` still correctly not used |
| B5 | **admin on their own** 3 h-old, already-answered post | 200 | **200**, `edited_by_admin=false` (the admin is the author) |
| B6 | owner sends an 8-character body | 400 | **400** `Минимальная длина поста — 300 символов (сейчас: 8)` |
| B7 | admin on another player's stale post | 200 | **200**, `edited_by_admin=true` |
| B8 | missing post | 404 | **404** `Пост не найден` |
| B9 | no token | 401 | **401** `Not authenticated` |
| B10 | body without `content` | 422 | **422** FastAPI validation shape |
| B11 | MySQL after every edit | `created_at` untouched, `edited_at` set, real editor recorded | **confirmed** — stale posts still read `15:10:32`; `edited_by_user_id` = 38 (owner) / 40 (admin) |
| B12 | **no XP**: attributes zeroed, then three owner edits (400 → 1800 → 3000 chars, all 200) | unchanged | `character_attributes(999801)` stayed `passive_experience=0, active_experience=0`; no XP/award lines in the service log |
| B13 | `GET /locations/{id}/client/details` | marker surfaced | **200**; `edited_at` / `edited_by_admin` present on every post; `edited_by_admin=true` **only** for the admin-on-another's-post case; untouched posts `null` / `false` |

**C. Rate limit (T6), re-verified live** — the new `nginx.conf` was copied into the running
`api-gateway` and reloaded, then the original restored and reloaded (verified:
`grep -c post_edit_limit /etc/nginx/nginx.conf` → `0`, and `nginx -t` green afterwards).

| # | Scenario | Expected | Actual |
|---|---|---|---|
| C1 | 40 × `PUT /locations/posts/{id}` | throttled | **11 × 404 (through) + 29 × 429** — 1 + `burst=10`, exactly as configured |
| C2 | the 429 body | HTML, no JSON `detail` | confirmed `<html>…429 Too Many Requests…` — so the frontend's dedicated 429 branch in `handleEditPost` (`LocationPage.tsx`) is **required**, and it is present |
| C3 | eight neighbour routes, 30 requests each: `/posts/latest`, `/posts/character-stats`, `/posts/{id}/like`, `/unlike`, `/request-deletion`, `/report`, `/posts/as-npc`, `/{id}/client/details` | never throttled | **0 × 429 on all eight** — `^/locations/posts/[0-9]+$` shadows nothing |

#### Re-checked by code review (the two things review #1 scrutinised, since `crud.py` changed underneath them)

- **The edit modal still has no drafts wiring.** `PostEditModal.tsx` imports only
  `WysiwygEditor`, `ConfirmDialog`, `types` and `gateConstants` — no `usePostDraft`, no
  `markSent`, no `DraftsPanel`, no import of `PostCreateForm`. An edit session still cannot
  autosave over the location's live draft (the FEAT-156 bug).
- **No error path loses the player's text.** `handleSave` (`PostEditModal.tsx:90-111`) calls
  `onClose()` *only* after `onSave` resolves; every rejection lands in `setError` with the
  content state untouched and `saving` reset. `handleEditPost` (`LocationPage.tsx`) maps a
  string `detail` verbatim — so the **new 400 gate message reaches the player word for word** —
  while an array `detail` (422), a missing `response` (network), a 429 and any other status
  each get their own Russian message. The modal is rendered at page level, so a feed re-render
  cannot unmount it mid-edit.
- **The client mirror of the budget still matches the server.** `lockedGates` /
  `requiredSymbolsForGates` (`PostEditModal.tsx:66-86`) price `ClientPost.gates`, which
  `crud.gates_for_posts` builds from **every** `action_gates` row of the post regardless of
  status — the same set `crud.gate_list_for_post` reads. The only possible divergence is a
  duplicate `(action_type, target_ref)` pair, where the client would demand *more* than the
  server: a false "you may not save", never a false "you may". Safe direction.
- **`PostEditResponse.length`** is `len(raw content)`, matching `get_post_details`
  (`crud.py:2049`) — no new inconsistency introduced.
- Mandatory frontend rules re-checked: Tailwind only (no CSS/SCSS imported or touched), all
  new files `.tsx`/`.ts`, **no `React.FC`**, `sm:` breakpoints and `break-words` throughout the
  modal, every user-facing string Russian.
- Security: `edited_by_user_id` never leaves the service (only the derived boolean does); all
  new SQL parameterised; error details name the rule, never another user; auth required on the
  endpoint; the rate limit is present in **both** nginx configs.

#### Issues Found

None. No new blocking issue.

#### Notes carried over from review #1

| # | Item | Status |
|---|---|---|
| 3 | `/tmp/crud.py.bak` and `/tmp/probe.py` left in the `locations-service` container by QA's mutation testing | **RESOLVED** — verified: `/tmp` is empty and there is no `/mutant` directory. The Reviewer's own `/rvwmut` copy and scripts were removed too. |
| 2 | Phase A would ship **undocumented**: T14 covers the edit endpoint and the two new `posts` columns but depends on T9 (Phase B). Verified still true — `docs/services/locations-service.md` contains no mention of `PUT /locations/posts/{id}`, `edited_at` or `edited_by_user_id`, and `docs/ISSUES.md` carries no entry for the section-3.9 follow-up. | **OPEN — recommendation to PM below** |

**Recommendation on the documentation note (issue #2).** Split T14 in two and do the Phase-A
half now, before Phase A merges: a new **T14a** (Backend Developer, depends on T2/T3, no
Phase-B dependency) covering, in `docs/services/locations-service.md`, the
`PUT /locations/posts/{post_id}` contract with its status codes, the `posts.edited_at` /
`posts.edited_by_user_id` columns, the `ClientPost.edited_at` / `edited_by_admin` fields, the
gate-budget rule of 3.6 as it is actually enforced today, and the nginx rate limit; plus the
section-3.9 MEDIUM entry in `docs/ISSUES.md`. Leave the `post_gate_requests` table and the
moderation flow in T14 (Phase B). This is a short documentation task and it is the only thing
standing between Phase A and a clean ship. It is recorded as a **note, not a blocker** — it
changes no code, and PM may choose to ship Phase A and document it alongside Phase B.

#### Pre-existing issues noted (not blocking, not caused by this feature)

- `crud.gates_for_posts` (`crud.py:1096-1113`) counts gates of **every** status, so
  `ClientPost.gates` shows a post's `expired` and `consumed` gates as if still declared. This
  is FEAT-145 behaviour, untouched by FEAT-159, and it is what makes the client-side budget
  mirror correct; it is an audit mark of declared intent rather than a rights display. Noted
  only so it is not mistaken for a regression.
- The `formatRelativeTime` timezone bug the Frontend Developer filed in `docs/ISSUES.md`
  (`PostCard.tsx`) is still accurate and correctly scoped out of this feature.

#### Cleanup

All fixture rows removed and verified 0 remaining: posts, `action_gates`, `post_likes`,
`post_deletion_requests`, `post_reports`, `character_attributes`, characters 999801–999803,
locations 999901–999904 and users 38/39/40 (`rvw2_*`). No existing account or location was
modified at any point. The `api-gateway` config was restored and reloaded, the throwaway
certificates and `/etc/letsencrypt` deleted, and every temporary script removed from both
containers.

#### Verdict

**Phase A (T1–T6) is ready to ship.** The budget invariant is enforced for real — including
the `expired` path, at the exact boundary, and for admins; the Phase A behaviour matrix is
unchanged; 992 tests pass; and no failure path loses a player's text. The only outstanding
item is documentation (note #2), which is a PM scoping decision, not a code defect.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-13 — PM: фича создана по запросу пользователя
[LOG] 2026-09-13 — PM: требования уточнены, механика гейтов проанализирована
[LOG] 2026-09-13 — PM: найдено жёсткое требование по бюджету символов (удвоение при наивной реализации)
[LOG] 2026-09-13 19:45 — Architect: начал проектирование, перепроверил все ссылки раздела 2 по текущему коду
[LOG] 2026-09-13 19:45 — Architect: раздел 2 устарел в одном пункте — FEAT-158 уже отзывает гейты при удалении поста (crud.py:2735, :2773)
[LOG] 2026-09-13 19:50 — Architect: бюджет символов считается по ВСЕМ гейтам поста (любой статус) + висящие заявки + новые; проверка дублируется при одобрении
[LOG] 2026-09-13 19:50 — Architect: решение по открытому вопросу — проверку «цель появилась позже поста» НЕ делаем: данных о времени прихода игроков и НПС в схеме нет вообще, покрыть можно только мобов; вместо этого админу показываем имена целей
[LOG] 2026-09-13 19:55 — Architect: «изменено» хранится как posts.edited_at + edited_by_user_id, флаг «админом» выводится без третьей колонки и без лишних запросов
[LOG] 2026-09-13 19:55 — Architect: заявки на гейты — отдельная таблица post_gate_requests, а не перегрузка post_deletion_requests (там ветка approve удаляет пост)
[LOG] 2026-09-13 20:00 — Architect: спроектировано 15 задач (6 — Phase A, 7 — Phase B, 2 — закрытие), 3 API-контракта, 2 миграции; два вопроса вынесены в 3.13
[LOG] 2026-09-13 21:05 — Backend Dev: начал Phase A (T1–T3)
[LOG] 2026-09-13 21:15 — Backend Dev: T1 готова — миграция 038 добавляет posts.edited_at и posts.edited_by_user_id (обе nullable, DEFAULT NULL), колонки продублированы в модели Post; upgrade head -> downgrade -1 -> upgrade head проверены на MySQL 8, version_table alembic_version_locations не менялся
[LOG] 2026-09-13 21:35 — Backend Dev: T2 готова — PUT /locations/posts/{post_id} + crud.edit_post; оба лимита перепроверяются на сервере в одной транзакции с SELECT ... FOR UPDATE по строке поста, «после поста уже писали» считается через id >, час — в SQL через NOW() - INTERVAL 1 HOUR (created_at наивный TIMESTAMP, сравнивать в Python нельзя); роль admin проходит мимо обоих лимитов, модератор получает 403 (get_admin_user намеренно не используется); опыт не пересчитывается, фоновых задач не ставится
[LOG] 2026-09-13 21:35 — Backend Dev: остаточная гонка (чужой пост коммитится в те же миллисекунды, пока игрок жмёт «Сохранить») задокументирована в докстринге crud.edit_post — лок на всю локацию не берём, он сериализовал бы всё письмо в ней
[LOG] 2026-09-13 21:45 — Backend Dev: T3 готова — get_post_details отдаёт edited_at и производный edited_by_admin (сравнение edited_by_user_id с user_id автора из профиля; при сбое вызова character-service флаг падает в False, а не в 500); ClientPost получил оба поля с дефолтами, LatestPostResponse наследует их, PostResponse не тронут
[LOG] 2026-09-13 21:55 — Backend Dev: живая проверка через api-gateway на dev-стенде — владелец правит свой последний пост в окне (200), после чужого поста 403, спустя час 403, не владелец 403, модератор на чужом посту 403, админ обходит оба лимита (200, edited_by_admin=true), несуществующий пост 404, короткий текст 400; в MySQL edited_at проставлен, created_at не изменился, вызовов passive_experience в логах нет
[LOG] 2026-09-13 22:00 — Backend Dev: полный прогон pytest locations-service — 903 passed; тестовые строки (посты, персонаж, пользователи) удалены
[LOG] 2026-09-13 22:20 — QA: T4 готова — tests/test_post_editing.py, 51 тест в трёх слоях (crud на реальном aiosqlite, роут через TestClient с замоканным crud, вывод edited_by_admin с замоканным character-service)
[LOG] 2026-09-13 22:20 — QA: покрыто — владелец правит (200), после поста уже писали (403), час истёк (403), не владелец (403), поста нет (404), админ обходит оба лимита (200, edited_by_admin=true), edited_at проставлен и created_at не тронут, опыт не начисляется ни при какой правке (award_post_xp_and_log/calculate_post_xp не вызываются, исходящих HTTP нет)
[LOG] 2026-09-13 22:20 — QA: «после поста уже писали» проверено именно через id > — два поста с ОДИНАКОВЫМ created_at, отличаются только автоинкрементом; при подмене на created_at > тест падает (проверено мутацией на копии кода)
[LOG] 2026-09-13 22:20 — QA: час считается БД против NOW(), фикстуры пишут настоящие строки и не подсовывают готовый row; отдельный тест ловит перенос окна на edited_at
[LOG] 2026-09-13 22:20 — QA: безопасность — модератор на чужом посту 403 (роут передаёт is_admin=False; матрица admin/moderator/editor/user), права moderation:* не дают обхода, edited_by_user_id не утекает в ответ, SQL-инъекция в тексте сохраняется как есть и таблица цела
[LOG] 2026-09-13 22:20 — QA: закрыт непроверенный путь T3 — при падении character-service (обрыв связи, 500, ответ без user_id) edited_by_admin деградирует в False, пометка «изменено» остаётся, 500 не возникает
[LOG] 2026-09-13 23:10 — Backend Dev: исправлен блокер #1 из ревью Phase A — edit_post теперь пересчитывает бюджет символов по ВСЕМ гейтам поста (crud.gate_list_for_post: статусы open, consumed и expired, чтобы выход из локации не «возвращал» потраченные символы) и отклоняет правку с 400 «Для всех действий этого поста нужно минимум N символов (сейчас: M)»
[LOG] 2026-09-13 23:10 — Backend Dev: добавлена чистая функция crud.merge_gate_lists(*gate_lists) — группировка по action_type с объединением целей; в Phase A в неё передаётся один список, T8 просто добавит висящие заявки и новые гейты аргументами, переписывать ничего не нужно; формула не дублируется — используется существующая required_symbols_for_gates
[LOG] 2026-09-13 23:10 — Backend Dev: проверка распространяется и на админов (ограничение от 13.09 снимает только час и «после поста уже писали», но не валидацию контента); пост без гейтов ведёт себя как раньше — только MIN_POST_LENGTH
[LOG] 2026-09-13 23:15 — Backend Dev: живая проверка эксплойта ревьюера — пост на 1000 знаков с пятью combat-гейтами, правка до 307 знаков теперь 400, в MySQL content не изменился и edited_at остался NULL; правка обратно до 1000 — 200, до 999 — 400, гейты переведены в expired и правка до 307 всё равно 400, админ получает тот же 400, пост без гейтов: 300 — 200, 299 — обычный 400 про минимальную длину; тестовые строки удалены
[LOG] 2026-09-13 23:20 — Backend Dev: ВНИМАНИЕ QA — полный прогон locations-service даёт 944 passed, 15 failed вместо 959; все 15 падений в tests/test_post_editing.py с «no such table: action_gates»: фикстура на aiosqlite (tests/test_post_editing.py:152-159) создаёт только Location и Post. Нужно добавить ActionGate.__table__ в список создаваемых таблиц — тестовые файлы я не трогаю
[LOG] 2026-09-13 22:20 — QA: полный прогон pytest locations-service — 954 passed (903 базовых + 51 новый), багов в реализации не найдено
[LOG] 2026-09-13 22:20 — DevSecOps: T6 готова — в оба конфига (nginx.conf и nginx.prod.conf) добавлены зона post_edit_limit 20r/m и regex-локация ^/locations/posts/[0-9]+$ с burst=10 nodelay и limit_req_status 429, объявленная до префиксного блока /locations/
[LOG] 2026-09-13 22:20 — DevSecOps: лимит выбран как защита от абуза, а не как ограничение использования — редактирование это ручное действие (несколько раз за час), 20 запросов в минуту на IP оставляют запас для нескольких игроков за одним NAT
[LOG] 2026-09-13 22:25 — DevSecOps: nginx -t пройден для обоих конфигов внутри контейнера api-gateway; для prod-файла на время проверки сгенерирован временный самоподписанный сертификат по путям Let's Encrypt, после теста удалён вместе с /etc/letsencrypt
[LOG] 2026-09-13 22:30 — DevSecOps: живая проверка на dev — 30 PUT /locations/posts/999999 подряд дали 11 x 401 (прошли до сервиса) и 19 x 429 (лимит сработал); соседние маршруты /posts/latest, /posts/character-stats, /posts/{id}/like, /unlike, /request-deletion, /report и /posts/as-npc по 30 запросов — ни одного 429, маршрутизация не сломана; исходный конфиг в контейнере восстановлен
[LOG] 2026-09-13 22:10 — Frontend Dev: начал T5 (Phase A, фронтенд)
[LOG] 2026-09-13 22:20 — Frontend Dev: T5(a) — константы и типы гейтов вынесены в gateConstants.ts (MIN_POST_LENGTH, GATE_COST/LABEL/STYLE/ORDER, stripHtmlTags, isContentEmpty, GateOption/GateOptions/PostGate); PostCreateForm импортирует их и реэкспортирует типы, поведение не изменилось; формула бюджета оформлена как requiredSymbolsForGates и теперь одна на обе формы
[LOG] 2026-09-13 22:35 — Frontend Dev: T5(b) — создан отдельный PostEditModal.tsx (НЕ editMode у PostCreateForm): никакой привязки к черновикам, иначе автосейв правки затёр бы живой черновик локации — ровно тот баг, ради которого делалась FEAT-156
[LOG] 2026-09-13 22:35 — Frontend Dev: модалка не закрывается и не чистит текст ни на одной ошибке (403/404/409/5xx/сеть) — закрыть её может только «Отмена», крестик или подтверждённый 200; клик по оверлею намеренно НЕ закрывает, «Отмена» с несохранёнными правками спрашивает подтверждение через ConfirmDialog
[LOG] 2026-09-13 22:40 — Frontend Dev: в модалке — счётчик символов по формуле сервера с учётом уже объявленных гейтов (они заблокированы, показаны неактивными чипами с подсказкой «Уже объявленное намерение нельзя изменить или снять»), вместо превью опыта — заметка «Опыт за пост не пересчитывается»
[LOG] 2026-09-13 22:50 — Frontend Dev: T5(c,d) — в кебаб-меню PostCard добавлен пункт «Редактировать» (автор + последний пост + в пределах часа, либо role === 'admin'); рядом с временем поста появилась пометка «изменено» / «изменено администратором» с title и точным временем правки
[LOG] 2026-09-13 22:55 — Frontend Dev: T5(e,f) — тип Post получил edited_at / edited_by_admin; LocationPage делает PUT /locations/posts/{id}, выводит isLatestPostInLocation из location.posts[0], после успеха перезапрашивает client/details; обработчик бросает Error с русским текстом (detail сервера — дословно), модалка печатает его инлайн
[LOG] 2026-09-13 23:00 — Frontend Dev: обнаружен предсуществующий баг — formatRelativeTime читает наивный серверный таймстемп как локальное время (у игрока в UTC+3 всё «только что»); добавлен в ISSUES.md (MEDIUM), в самой задаче для проверки часового окна используется локальный parseServerDate с дочитыванием Z
[LOG] 2026-09-13 23:05 — Frontend Dev: контракт сверен с живым /openapi.json locations-service — PUT /locations/posts/{post_id} принимает {content}, ClientPost отдаёт edited_at/edited_by_admin; расхождений нет (edited_at в openapi без nullable — известное ограничение Pydantic v1)
[LOG] 2026-09-13 23:10 — Frontend Dev: npx tsc --noEmit — 0 ошибок, npm run build — успешно (оба внутри контейнера frontend); T5 завершена
[LOG] 2026-09-13 22:55 — Backend Dev: по решению пользователя роль admin обходит оба ограничения безусловно — и на чужих постах, и на своих; ветка admin теперь проверяется ПЕРВОЙ, до проверки владения (crud.edit_post)
[LOG] 2026-09-13 22:55 — Backend Dev: намеренно не изменено — проверка минимальной длины действует и на админа (обход касается только двух лимитов редактирования), edited_by_user_id по-прежнему пишет реального редактора, а edited_by_admin остаётся сравнением редактора с автором (админ правит свой пост -> false, пометка просто «изменено»), опыт не пересчитывается; модератор на чужом посту по-прежнему 403
[LOG] 2026-09-13 22:55 — Backend Dev: живая проверка через api-gateway — админ правит СВОЙ пост, которому 3 часа и после которого уже написали: 200, edited_by_admin=false; обычный владелец в той же ситуации 403; модератор на чужом посту 403; короткий текст от админа 400; админ на чужом устаревшем посту 200 с edited_by_admin=true; несуществующий пост 404; владелец на своём свежем последнем посту 200. В MySQL edited_at проставлен, created_at не изменился, edited_by_user_id=4
[LOG] 2026-09-13 22:55 — Backend Dev: полный прогон pytest locations-service — 953 passed, 1 failed; падает только test_post_editing.py::TestAdminBypass::test_admin_editing_their_own_post_takes_the_owner_path, который закреплял старое поведение (админ на своём устаревшем посту получал 403). Тест не трогал — обновляет QA. Тестовые строки (посты, персонаж, два пользователя) удалены
[LOG] 2026-09-13 23:30 — QA: тест под старое правило переписан — test_admin_edits_their_own_stale_and_answered_post: админ правит СВОЙ пост, которому 3 часа и после которого уже написали, получает 200; в докстринге зафиксировано, что это решение пользователя от 2026-09-13 («Админ должен править и свои посты без ограничений»), чтобы никто не «починил» обратно в 403
[LOG] 2026-09-13 23:30 — QA: проверен весь файл на тесты, молча закреплявшие старый порядок — падающий был один, но у test_a_stranger_is_refused_even_when_every_limit_would_pass докстринг утверждал «ownership is checked first»; формулировка исправлена (сам тест с is_admin=False корректен), остальные админские тесты правились на ЧУЖИХ постах и от порядка веток не зависят
[LOG] 2026-09-13 23:30 — QA: добавлены границы, которые сдвинуться не должны — контрольный тест «тот же свой пост обычному владельцу 403» (иначе обход мог бы проходить из-за сломанных лимитов), минимальная длина действует и на своём посту админа (400, текст не перезаписан), edited_by_user_id пишет реального редактора, админ на СВОЁМ посту даёт edited_by_admin=false (пометка просто «изменено» — это намеренно), опыт не пересчитывается и на новом админском пути (две правки подряд, award_post_xp_and_log/calculate_post_xp не вызываются, исходящих HTTP нет); модератор на чужом посту 403 закреплён на обоих слоях — на роуте (is_admin=False) и в crud
[LOG] 2026-09-13 23:30 — QA: мутационная проверка — при возврате старого порядка веток (if is_owner / elif is_admin) падают ровно три новых теста на «свой пост админа», на текущем коде все проходят
[LOG] 2026-09-13 23:35 — QA: pytest tests/test_post_editing.py — 56 passed; полный прогон pytest locations-service — 959 passed, 0 failed (было 953 passed + 1 failed = 954 теста; +5 новых)
[LOG] 2026-09-14 00:05 — Reviewer: начал проверку Phase A (T1–T6); Phase B не реализована и не проверялась, T15 закрывать рано — она про всю фичу
[LOG] 2026-09-14 00:10 — Reviewer: автопроверки прогнаны заново самостоятельно — npx tsc --noEmit 0 ошибок, npm run build успешно, py_compile по всем изменённым файлам, полный pytest locations-service 959 passed, alembic current = 038_post_edit_columns (head), version_table alembic_version_locations не изменён, nginx -t зелёный для обоих конфигов, docker compose config OK
[LOG] 2026-09-14 00:15 — Reviewer: расширение claude-in-chrome НЕ подключено — ни один шаг не выполнен в настоящем браузере; вся живая проверка сделана через api-gateway реальными JWT + прямой запрос в MySQL. Не проверено вживую: вёрстка модалки на 360px, видимость пункта «Редактировать» в кебабе, отрисовка пометки «изменено», инлайн-ошибка, чистота консоли
[LOG] 2026-09-14 00:20 — Reviewer: живая матрица подтверждена — владелец в окне 200, после него написали 403, час истёк 403, модератор на чужом посту 403, админ на СВОЁМ устаревшем отвеченном посту 200 с edited_by_admin=false, админ на чужом 200 с edited_by_admin=true, короткий текст от админа 400, нет поста 404, без токена 401, без content 422
[LOG] 2026-09-14 00:22 — Reviewer: в MySQL created_at не сдвинулся ни у одного поста, edited_at проставлен, edited_by_user_id пишет реального редактора (4 и 35), опыт персонажа после двух правок (вторая +1300 знаков) остался 0/0 — фарма нет
[LOG] 2026-09-14 00:28 — Reviewer: лимит nginx проверен на живом шлюзе (конфиг временно подложен и перезагружен, затем восстановлен) — 40 PUT дали 11 пропущенных и 29 x 429; тело 429 это HTML без JSON detail, то есть отдельная ветка 429 во фронтенде обязательна и она есть; соседние маршруты (latest, character-stats, like, unlike, request-deletion, report, as-npc, client/details) по 30 запросов — ни одного 429, регулярка ничего не перекрывает
[LOG] 2026-09-14 00:32 — Reviewer: PostEditModal действительно автономен — ни usePostDraft, ни markSent, ни импорта PostCreateForm; вынос констант в gateConstants.ts — чистый рефакторинг (?? 0 и Math.max(1, …) на отфильтрованных гейтах ни на что не влияют и вдобавок точнее совпадают с сервером)
[LOG] 2026-09-14 00:35 — Reviewer: ни один путь ошибки не теряет текст — модалка закрывается только по «Отмена», крестику или подтверждённому 200; оверлей не кликабелен; 400/403/404/429/5xx/сеть/422 дают русское сообщение инлайн
[LOG] 2026-09-14 00:40 — Reviewer: НАЙДЕНА БЛОКИРУЮЩАЯ ПРОБЛЕМА — crud.edit_post проверяет только MIN_POST_LENGTH и вообще не читает action_gates, поэтому бюджет символов под уже выданные гейты можно снять правкой. Воспроизведено вживую: пост с пятью combat-гейтами (1000 знаков при публикации) урезан до 307 знаков — 200 OK, гейты остались {combat: 5}. В разделе 3.6 этот случай закрыт объединённым правилом, но оно живёт в T8 (Phase B); если Phase A уезжает одна, инвариант пропадает. Фронт это правило уже зеркалит, дыра чисто серверная
[LOG] 2026-09-14 00:45 — Reviewer: тестовые данные удалены — посты, action_gates, заявки на удаление, жалобы, лайки, атрибуты, персонажи 999801/999802, локация 999901 и пользователи 35/36; конфиг api-gateway и /etc/letsencrypt восстановлены, временные скрипты и сертификаты стёрты
[LOG] 2026-09-14 00:47 — Reviewer: проверка Phase A завершена, результат FAIL — одна блокирующая проблема (бюджет гейтов при правке) и две заметки (документация T14 привязана к Phase B; в контейнере остался мусор от мутационных тестов QA)
[LOG] 2026-09-14 01:05 — QA: починена фикстура test_post_editing.py — после появления бюджета гейтов crud.edit_post читает action_gates, а in-memory SQLite её не создавал (944 passed, 15 failed, все — sqlite3.OperationalError: no such table: action_gates, ни одного упавшего assert). В кортеж создаваемых таблиц добавлена ActionGate.__table__: 56 passed
[LOG] 2026-09-14 01:25 — QA: написаны регрессии на дыру из ревью #1 — класс TestGateSymbolBudget (18 тестов): сам эксплойт (пять combat-гейтов, правка до 307 знаков → 400, и в БД не изменились ни content, ни edited_at, ни edited_by_user_id, ни сами гейты), гейты в статусе expired (выход из локации и возврат не возвращают бюджет) и consumed, смешанные статусы, точная граница 1000/999, дорогие интенты (npc_dialogue 500 + combat 2×200 = 900), гейт без цели, подсчёт длины после снятия HTML, тот же 400 для админа (правило от 2026-09-13 снимает час и «после вас написали», но не валидацию контента), пост без гейтов живёт только по MIN_POST_LENGTH, чужие и осиротевшие гейты не засчитываются
[LOG] 2026-09-14 01:35 — QA: добавлен слой 4 — чистая merge_gate_lists (15 тестов): группировка по action_type, объединение целей без дублей, None как отдельный участник, нормализация строковых id, поддержка и dict, и объектов (для GateSpec из Phase B), входные списки не мутируются
[LOG] 2026-09-14 01:50 — QA: мутационная проверка в контейнерной копии /mutant (репозиторий не трогался) — 8 мутантов, все убиты нужными тестами: снятие проверки бюджета (10 падений), учёт только status='open' (4, включая expired и consumed), послабление на символ (5), строгое неравенство на границе (2), освобождение админа (2), конкатенация вместо объединения (5), выброс None-целей (2), отказ от группировки по action_type (15). Оригинал восстановлен
[LOG] 2026-09-14 01:55 — QA: из контейнера locations-service удалён мусор прошлой мутационной проверки (/tmp/crud.py.bak, /tmp/probe.py) — заметка #3 из ревью закрыта
[LOG] 2026-09-14 02:00 — QA: тесты готовы — tests/test_post_editing.py 89 passed, полный набор locations-service 992 passed, 3 warnings (было 959 до фикса + 33 новых теста), падений нет
[LOG] 2026-09-14 03:00 — Reviewer: начал повторную проверку Phase A (ревью #2); Phase B по-прежнему не реализована и не проверялась, T15 не закрываю — она про всю фичу
[LOG] 2026-09-14 03:05 — Reviewer: все автопроверки прогнаны заново самостоятельно — npx tsc --noEmit 0 ошибок, npm run build успешно, py_compile по всем изменённым файлам, полный pytest locations-service 992 passed / 0 failed, alembic current = 038_post_edit_columns (head), version_table alembic_version_locations не изменён, nginx -t зелёный для обоих конфигов, docker compose config OK
[LOG] 2026-09-14 03:07 — Reviewer: md5 файлов crud.py/main.py/schemas.py/models.py/tests внутри контейнера совпадают с репозиторием — тесты гоняются по реальному коду, а не по остаткам мутанта
[LOG] 2026-09-14 03:15 — Reviewer: отчёт QA о мутационной проверке не принят на слово — четыре мутанта наложены самостоятельно на копию внутри контейнера (/rvwmut, репозиторий и рабочий код не тронуты, копия удалена): фильтр status='open' убивают 4 теста, снятие проверки бюджета — 10, послабление на символ — 5, освобождение админа — 2. Тесты действительно поймали бы исходную дыру
[LOG] 2026-09-14 03:25 — Reviewer: расширение claude-in-chrome НЕ подключено (проверено прямым вызовом) — ни один шаг не выполнен в настоящем браузере; вся живая проверка через api-gateway реальными JWT + прямой запрос в MySQL. По-прежнему не проверено вживую: вёрстка модалки на 360px, видимость «Редактировать» в кебабе, отрисовка пометки «изменено», инлайн-ошибка, чистота консоли
[LOG] 2026-09-14 03:30 — Reviewer: эксплойт из ревью #1 воспроизведён и закрыт — пост на 1000 знаков с пятью combat-гейтами, правка до 307 даёт 400 «Для всех действий этого поста нужно минимум 1000 символов (сейчас: 307)», в MySQL не изменились ни content, ни edited_at, ни edited_by_user_id, все пять строк гейтов на месте
[LOG] 2026-09-14 03:33 — Reviewer: проверена тонкая половина — гейты переведены в expired (то, что делает выход из локации и возврат), правка до 307 всё равно 400; то же для consumed и для смешанных статусов (2 open + 1 expired + 2 consumed). Фильтра по статусу в gate_list_for_post нет, и это правильно
[LOG] 2026-09-14 03:36 — Reviewer: точная граница — ровно 1000 знаков 200, 999 знаков 400; админ на том же посту получает тот же 400 (решение от 13.09 снимает час и «после вас написали», но не бюджет); пост без гейтов живёт только по MIN_POST_LENGTH — 300 это 200, 299 это 400 про минимальную длину, а не про гейты
[LOG] 2026-09-14 03:42 — Reviewer: матрица Phase A подтверждена заново — владелец в окне 200, после него написали 403, час истёк 403, модератор на чужом посту 403, админ на СВОЁМ устаревшем отвеченном посту 200 с edited_by_admin=false, админ на чужом 200 с edited_by_admin=true, короткий текст 400, нет поста 404, без токена 401, без content 422; created_at не сдвинулся, edited_at проставлен, edited_by_user_id пишет реального редактора
[LOG] 2026-09-14 03:45 — Reviewer: опыт не начисляется — атрибуты обнулены, три правки подряд (400 -> 1800 -> 3000 знаков, все 200), passive/active_experience так и остались 0/0, в логах сервиса ни одной записи про XP
[LOG] 2026-09-14 03:50 — Reviewer: лимит nginx перепроверен на живом шлюзе (конфиг подложен и перезагружен, затем восстановлен) — 40 PUT дали 11 пропущенных и 29 x 429, тело 429 это HTML без JSON detail; восемь соседних маршрутов по 30 запросов — ни одного 429
[LOG] 2026-09-14 03:55 — Reviewer: обе точки из ревью #1 перепроверены, потому что crud.py под ними изменился — в PostEditModal по-прежнему нет ни usePostDraft, ни markSent, ни импорта PostCreateForm; ни один путь ошибки не теряет текст, а новое сообщение про бюджет доходит до игрока дословно (строковый detail пробрасывается как есть)
[LOG] 2026-09-14 04:00 — Reviewer: заметка #3 закрыта — в контейнере locations-service /tmp пуст, каталога /mutant нет; свою копию /rvwmut и временные скрипты тоже удалил
[LOG] 2026-09-14 04:02 — Reviewer: заметка #2 подтверждена как открытая — в docs/services/locations-service.md нет ни слова про PUT /locations/posts/{id}, edited_at и edited_by_user_id, в ISSUES.md нет записи по 3.9. Рекомендация PM: выделить T14a (документация только для Phase A) и закрыть её до мержа; блокером не считаю
[LOG] 2026-09-14 04:05 — Reviewer: тестовые данные удалены (посты, гейты, лайки, заявки, жалобы, атрибуты, персонажи 999801–999803, локации 999901–999904, пользователи rvw2_*), ни один существующий аккаунт или локация не тронуты; конфиг api-gateway восстановлен, сертификаты и /etc/letsencrypt стёрты
[LOG] 2026-09-14 04:08 — Reviewer: повторная проверка Phase A завершена, результат PASS — Phase A (T1–T6) готова к отгрузке; единственный незакрытый пункт — документация (T14a), это решение PM, а не дефект кода
[LOG] 2026-09-14 05:10 — Backend Dev: задача T14a (только документация Phase A) выполнена. В docs/services/locations-service.md добавлен раздел «Редактирование поста (FEAT-159, Phase A)»: контракт PUT /locations/posts/{post_id}, все проверки с русскими сообщениями, id > вместо created_at >, час считается MySQL против NOW(), опыт не пересчитывается, безусловный обход двух лимитов ролью admin (но не проверок содержимого), модератор получает 403, принятая остаточная гонка. Описан бюджет символов ровно так, как он работает сейчас: gate_list_for_post читает гейты всех статусов (open/consumed/expired), merge_gate_lists объединяет цели и специально принимает произвольное число списков под Phase B. Добавлены колонки posts.edited_at / edited_by_user_id в раздел «Таблицы БД» с обоснованием отказа от updated_at ON UPDATE, и поля ClientPost.edited_at / производный edited_by_admin с деградацией в false при сбое профиля. Записан лимит nginx (20 r/m, burst 10, по IP, оба конфига). Phase B (post_gate_requests, заявки) не документирован — явно помечен как нереализованный
[LOG] 2026-09-14 05:12 — Backend Dev: в docs/ISSUES.md добавлена запись MEDIUM по разделу 3.9 — action_gates.created_at не читается ни одним запросом, цели гейта не валидируются на пути создания поста (существование, локация, моб/игрок, жив ли). Дубликатов не нашлось. Все file:line перепроверены по исходникам, а не по разделу 3 фичи
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

_TBD_

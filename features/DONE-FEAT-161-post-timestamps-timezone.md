# FEAT-161: Время постов показывается неправильно (часовой пояс)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-13 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Найдено при работе над FEAT-159 (Frontend Developer, задача T5).

Бэкенд отдаёт время постов **без часового пояса**: `"2026-03-23T10:23:58"`. Контейнеры работают
в UTC. Браузер, получив строку без пояса, трактует её как **местное время**.

Итог: при UTC+3 пост трёхчасовой давности показывается как «только что», а вся лента времени
врёт ровно на величину смещения игрока. Чем восточнее игрок, тем сильнее.

Это не косметика: по времени поста игроки ориентируются, кто когда писал и чья очередь.

### Где проявляется
- `formatRelativeTime` в ленте локации (основное место).
- Скорее всего везде, где показывается время, пришедшее с бэкенда — профиль, история постов,
  архив, уведомления, бои. **Нужен аудит, а не точечная правка.**

### Уже известно
FEAT-159 столкнулась с этим напрямую: проверка «прошёл ли час с публикации» не могла унаследовать
баг, иначе кнопка редактирования работала бы неправильно у всех восточнее UTC. Поэтому в
`PostCard.tsx` появился локальный `parseServerDate`, который дописывает `Z` к строкам без пояса.
**Это заплатка в одном файле** — она и есть кандидат на вынос в общее решение.

Похожая проблема уже решалась в FEAT-156: хук черновиков разбирает серверные отметки времени
через собственный `parseServerTimestamp`, дописывающий `Z`. То есть костыль в проекте уже
продублирован дважды.

### Бизнес-правила
- Время должно показываться в **часовом поясе игрока**, а не сервера.
- «Только что», «3 часа назад» и абсолютные даты должны быть согласованы между собой.
- Правка не должна сломать игровой календарь: игровое время — отдельная система
  (196 реальных дней = 1 игровой год), и его нельзя путать с реальными отметками времени.

### Edge Cases
- Существующие записи в БД — все без пояса, правка должна работать для них.
- Часть эндпоинтов может уже отдавать пояс — тогда двойное дописывание `Z` сломает время.
- Пользователь в UTC или западнее нуля — ошибка в другую сторону, «в будущем».
- Переход на летнее время, если у игрока такой пояс.

### Вопросы к пользователю
- [x] Чинить на **бэкенде** (отдавать время с поясом — правильно, но затрагивает все сервисы и
      всех потребителей) или на **фронтенде** (одна общая функция разбора — быстрее и локальнее,
      но лечит симптом)? → Решить на проектировании, с рекомендацией.
      **Решение Architect: фронтенд сейчас (Stage 1), бэкенд — отдельной фичей (Stage 2).
      Обоснование в разделе 3.**

---

## 2. Analysis Report (filled by Architect — in English)

### 2.1 Ground truth — verified live, not assumed

| Fact | How verified | Result |
|------|--------------|--------|
| No `TZ` env var in any compose file | `grep TZ docker-compose*.yml docker/mysql/*` | none — Docker default UTC |
| App containers run UTC | `docker exec mysql date -u` vs `date` | identical |
| MySQL session/global tz | `SELECT @@global.time_zone, NOW(), UTC_TIMESTAMP()` | `SYSTEM`; `NOW() == UTC_TIMESTAMP()` |
| Naive strings are really UTC | above | **yes — appending `Z` is correct** |
| No `json_encoders` anywhere | `grep -rn json_encoders services/` | 0 hits — every naive datetime serialises bare |
| Live payload | `GET /locations/posts/latest` | `"created_at":"2026-03-23T10:23:58"` — no offset |
| Live payload | `GET /locations/game-time` | `"epoch":"2026-01-01T20:00:00"`, `"server_time":"2026-09-13T19:56:36.407720"` — no offset |

This matters: both existing workarounds *assume* UTC. The assumption is now confirmed, so a shared
helper built on it is sound. **If a `TZ` env var is ever added to a container, this whole fix
silently breaks** — noted as a risk below.

### 2.2 Backend — which services serialise naive datetimes

**All of them.** `created_at`/`updated_at` columns are `TIMESTAMP`/`DateTime` with
`server_default=func.now()` (MySQL `NOW()`, UTC) or Python `datetime.utcnow()` (UTC, naive).
There is no `json_encoders`, so FastAPI/Pydantic v1 emit bare ISO-8601 with no offset.

Services carrying datetime fields in their schemas: `locations-service`, `character-service`,
`user-service`, `battle-service`, `inventory-service`, `character-attributes-service`,
`skills-service`, `notification-service`, `dungeon-service`, `battle-pass-service`.
(Note: `dungeon-service`, `battle-pass-service`, `party-service` are live containers not listed in
CLAUDE.md §1 — the service table is stale. Filed under Risks.)

Two serialisation paths, and this is the crux of the backend cost:

1. **Pydantic `response_model`** — the majority. A `json_encoders` fix would cover these, but
   there are ~160 `class Config:` blocks across the ten services that would need a common base.
2. **Hand-rolled `.isoformat()` into raw dicts** — **22 sites** that bypass Pydantic entirely and
   would NOT be fixed by any `json_encoders` change:
   `notification-service/app/messenger_routes.py:652,796`,
   `notification-service/app/messenger_ws_handler.py:221,325,327,342` (messenger over WebSocket),
   `inventory-service/app/crud.py:2089,2090,2448,2984`, `inventory-service/app/main.py:1120,1333,3437`,
   `character-service/app/main.py:424,1975,3674`, `battle-service/app/main.py:1665,2817,3795`,
   `battle-service/app/redis_state.py:133`, `dungeon-service/app/gameplay.py:3627`,
   `skills-service/app/crud.py:557`.

There is **no cheap global backend fix**. `default_response_class` cannot help: FastAPI's
`jsonable_encoder` turns datetimes into strings *before* the response class renders, so the
response class never sees a `datetime`. MySQL `DATETIME` has no timezone, so
`DateTime(timezone=True)` is a no-op on this driver.

### 2.3 Endpoints that ALREADY emit an offset — blind `Z`-appending would corrupt these

**Yes, they exist, and they are in the most time-critical feature in the game.**

`battle-service/app/main.py:614-615, 2480-2481, 3228-3229, 3526-3527` build the turn deadline as
`datetime.now(timezone.utc).astimezone(moscow_tz)` — **offset-aware, `+03:00`**. That value is
`.isoformat()`-ed into Redis (`redis_state.py:133`, `main.py:2817`) and served raw as
`runtime.deadline_at` over both REST (`main.py:1265, 1355, 1440, 3816`) and WebSocket
(`main.py:4579`, `_build_runtime`). So `deadline_at` reaches the client as `"...+03:00"`.

**The same field is also written naive.** The resume path at `main.py:1665` writes
`datetime.utcnow().isoformat()` — no offset. So `deadline_at` is *internally inconsistent*: aware
before a pause, naive after a resume.

Consequences found:
- **Latent 500 on pausing a battle.** `main.py:1607-1609`: `now = datetime.utcnow()` (naive) minus
  `datetime.fromisoformat(state["deadline_at"])` (aware `+03:00`) raises
  `TypeError: can't subtract offset-naive and offset-aware datetimes`.
- **`battle_turns.deadline_at` in MySQL holds Moscow wall-clock** while every other column in the
  database holds UTC, because aiomysql strips the tzinfo on write. Anything reading that column
  from the DB is 3 hours off. (Reviewer 2026-09-14: the column lives in `battle_turns`, not
  `battles` — this paragraph and §3.2 originally named the wrong table. Confirmed on the live DB:
  `TIMESTAMPDIFF(HOUR, submitted_at, deadline_at) = 27` on every existing row.)

Conclusion: **the shared parser must be offset-tolerant** — append `Z` only when no offset is
present. Both existing workarounds already do this; a naive "always append Z" would break the
turn timer. (`helpers.js:21` does exactly that and is already broken — see 2.5.)

### 2.4 Cross-service parsing — the risk the brief flagged is small

Complete enumeration of backend code that parses a datetime **string** (`fromisoformat`,
`strptime`, `dateutil`), production code only:

| Site | Parses | Cross-service? | Offset-tolerant? |
|------|--------|----------------|------------------|
| `locations-service/app/main.py:1194` | `travel_cooldown_until` from character-service | **yes** | **yes** — `.replace("Z","+00:00")` + `if tzinfo is None: replace(tzinfo=utc)` |
| `locations-service/app/main.py:1457` | same | **yes** | **yes**, same guard |
| `battle-service/app/main.py:1608` | its own Redis state | no | **no** — see 2.3 |

That is the entire surface. **Only one field crosses a service boundary as a parsed string, and
both of its parsers already handle naive *and* offset-carrying input.** So a future backend
migration would not break service-to-service logic — which removes the scariest objection to the
backend route, though not its cost.

Everything else crossing services is either passed straight through as an opaque string
(`user-service/main.py:1540` forwards locations-service `last_date` into
`last_rp_post_date: Optional[datetime]`, which Pydantic v1 parses in either form) or read from the
shared DB as a real `datetime` object, never as text.

### 2.5 Things that DEPEND on the current wrong behaviour

1. **The game calendar is currently correct only by accident.**
   `src/utils/gameTime.ts:72-73` parses **both** `epoch` and `server_time` with plain `new Date()`.
   Both shift by the same amount, so `serverMs - epochMs` cancels out. **Fixing only one of the two
   would break the in-game calendar by the player's offset.** See §3.4.
2. **`floatingStructuresSlice.ts:91-93`** derives a "client↔server clock offset" by subtracting a
   mis-parsed `server_now` from `Date.now()`. The number it computes *is* the browser's TZ offset.
   It is then fed to `FloatingStructuresLayer.tsx:78`, where it cancels the bug. **Fixing the
   parse without removing the offset subtraction would double-apply the correction.**
3. **`skills-service/app/tests/test_character_skill_reset.py:128`** does
   `datetime.fromisoformat(data["reset_available_at"]) - before` where `before` is naive. If the
   backend ever emits an offset, this test raises `TypeError`. (`battle-pass-service/app/tests/
   test_admin.py:35-36` parses two fields from the same source and subtracts them — safe.)
4. `MyRequestsPage.tsx:65` sorts by naive `created_at` — both sides shift equally, benign today.

### 2.6 Frontend — the true scope

`src/utils/` contains `articleSection.ts`, `formatLastActive.ts`, `gameTime.ts`, `htmlExcerpt.ts`,
`permissions.ts`. **There is no shared date helper.**

- **~55 buggy parse sites across ~45 files**, in every area of the game: location feed, homepage,
  profile, post history, archive, notifications, messenger, chat, tickets, battles, dungeons,
  auction, gathering, and 9 admin pages.
- **5 independent, divergent copies of `formatRelativeTime`**: `PostCard.tsx:33`,
  `LatestRoleplayPosts.tsx:13`, `ConversationItem.tsx:12`, `LogsTab.tsx:62`,
  `OnlineUsersPage.tsx:10`.
- **3 divergent workarounds**, only two of which are correct:
  - `PostCard.tsx:69-70` `parseServerDate` — correct, but its regex `[Z+]` is **unanchored**.
  - `usePostDraft.ts:138-143` `parseServerTimestamp` — correct, anchored, null-safe, `NaN`-safe.
    **Best base for consolidation.**
  - `helpers/helpers.js:21-32` `formatDateTime` — appends `Z` **unconditionally** after truncating
    at `.`; on an already-zoned string it produces `"...+03:00Z"` → `Invalid Date` →
    `NaN.NaN.NaN NaN:NaN`, and throws on `null`. Its one consumer is `BattlePageBar.tsx:903` on
    `log.timestamp`.
- **`PostCard.tsx` contradicts itself**: it defines the correct `parseServerDate` at line 69 and
  uses it for the edit window, yet its own `formatRelativeTime` at line 35 uses bare `new Date()`.
- **`formatLastActive.ts:12,39`** — online/offline status. East of UTC every player reads as
  permanently offline; west of UTC everyone reads as «Онлайн».
- **`GameTimeAdminPage.tsx:56-62,113`** — reads `epoch` with no offset applied, writes it back with
  a full offset applied (`new Date(epochInput).toISOString()` on a zoneless `datetime-local`).
  **Every open-and-save cycle shifts the game epoch by the admin's UTC offset**, permanently
  skewing the calendar for all players. This is the one place where a timezone bug corrupts
  persisted data rather than only display.

### 2.7 DB Changes

**None.** No schema change, no Alembic migration. Stored values are already correct UTC; only
their serialisation and interpretation are at issue.

### 2.8 Risks

| # | Risk | Mitigation |
|---|------|------------|
| R1 | A `TZ` env var added to any container later silently invalidates the whole "naive == UTC" assumption | Document the assumption in the helper's doc comment; DevSecOps task to assert no `TZ` is set |
| R2 | Fixing `gameTime.ts` inconsistently breaks the in-game calendar | Both inputs changed atomically in one task; acceptance criterion pins the computed value |
| R3 | Double correction in `floatingStructuresSlice` | Fix parse and remove the offset subtraction in the same task |
| R4 | 5 `formatRelativeTime` copies have different Russian wording/fallbacks | Canonical impl takes a `fallback` option; each call site's existing wording preserved |
| R5 | `battle-service` `deadline_at` is naive/aware inconsistent; in-flight Redis state survives deploys | Backend fix normalises *comparisons* tolerantly, not just writes — old `+03:00` state keeps working |
| R6 | CLAUDE.md §1 service table omits `dungeon-service`, `battle-pass-service`, `party-service` | Out of scope; filed to ISSUES.md |
| R7 | Touching a component tempts a Tailwind/TS migration under §10.8/§10.9 | This feature changes **logic only, never styles** → §10.8 does not trigger. §10.9 does: no `.jsx` file may gain new logic |

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Ruling: fix on the FRONTEND now (Stage 1); backend offsets are a separate, later feature (Stage 2)

This is **not** "treat the symptom because it is easier". The reasoning:

**Why not the backend now:**
- It is not one change, it is three: a shared Pydantic v1 base across ~160 `class Config:` blocks
  in 10 services, **plus** 22 hand-rolled `.isoformat()` sites that Pydantic never sees (§2.2),
  **plus** untangling `battle-service`'s Moscow/UTC mix. That is the opposite of a minimal diff,
  across every service in the platform, for a MEDIUM-priority display bug.
- It cannot be rolled out atomically. Ten containers deploy one at a time, so during any rollout
  some endpoints emit offsets and some do not. **The client must be offset-tolerant before the
  backend may safely change.**
- It would break `skills-service/app/tests/test_character_skill_reset.py:128` (§2.5).

**Why the frontend fix is the correct first step, not a stopgap:**
- The frontend is **already required** to be offset-tolerant regardless of what the backend does,
  because `battle-service` **already** emits `+03:00` on `deadline_at` and naive on the same field
  after a resume (§2.3). No backend change removes that requirement.
- The helper is **forward-compatible by construction**: it appends `Z` only when no offset is
  present. When Stage 2 lands and a service starts emitting `+00:00`, every call site keeps working
  with zero changes, and the helper degrades to a pass-through. Nothing has to be un-done.
- Therefore Stage 1 is a **prerequisite for** Stage 2, not an alternative to it.

**Why the "next component will get it wrong again" objection is answered:** today there is no
shared helper at all, five divergent `formatRelativeTime` copies and three divergent workarounds.
After Stage 1 there is exactly one exported helper, five copies collapse into one, and
`new Date(<server field>)` becomes a reviewable smell with a named alternative. The situation is
strictly better than it is now, and better than a backend-only fix would leave it (which would
leave the five duplicated formatters and the broken `helpers.js` in place).

**Stage 2 (out of scope here):** backend emits UTC offsets everywhere. To be filed in
`docs/ISSUES.md` as tech debt with the §2.2 site list, so the work is not lost.

### 3.2 Scope boundary — one narrow backend change IS included

`battle-service`'s naive/aware mix (§2.3) is in scope because it is a **live crash**
(`TypeError` on pausing a battle) and a **data inconsistency** (`battle_turns.deadline_at` stored in
Moscow wall-clock while the rest of the DB is UTC), not a display problem. It is one service, a
handful of lines, and it is squarely a timezone-correctness defect. Everything else backend-side
is Stage 2.

Because backend Python changes, QA pytest tasks are mandatory (CLAUDE.md §11) and are included
(T10).

### 3.3 API Contracts

**No API contract changes.** No endpoint's path, method, request body, or response field set
changes. No field's *type* changes. Response *values* change in exactly one place: `battle-service`
`deadline_at` stops carrying `+03:00` and carries UTC instead — the same absolute instant, so every
existing consumer (`BattlePage.tsx:298`, `AdminBattlesPage.tsx:131`, the ZSET sweeper) reads the
identical point in time.

### 3.4 The game calendar — explicitly UNAFFECTED in value, FIXED in consistency

Game time is computed by `locations-service/app/crud.py:2802-2846` (`DAYS_PER_YEAR = 196`,
`DAYS_PER_WEEK = 3`) from `(now - epoch).total_seconds()`, both naive UTC on the server. The
**server-side calculation is untouched by this feature** — no backend game-time code is modified,
and `GameTimePublicResponse.computed` keeps returning exactly what it returns today.

The client-side mirror in `src/utils/gameTime.ts` is a *difference* of two timestamps, so a uniform
parsing change to both inputs leaves the result **bit-identical**. That is the required invariant:

> `epoch` and `server_time` must be migrated to the shared parser **together, in one task, or not
> at all.** Migrating one without the other shifts in-game time by the player's UTC offset.

Two genuine game-calendar defects are fixed as a consequence, both pre-existing:
- `GameTimeWidget.tsx:53` feeds a real UTC `new Date().toISOString()` into `computeGameTime` on
  every 60 s tick while the first render uses the naive `server_time`. The two reference frames
  differ by the browser offset, so the displayed in-game day can jump by ±1 one minute after load.
  Uniform parsing makes both paths agree.
- `GameTimeAdminPage.tsx` epoch round-trip corrupts the stored epoch on every save (§2.6).

### 3.5 The shared helper — `src/utils/serverDate.ts` (new)

Single new module, TypeScript, no dependencies. Built on the `usePostDraft.ts` implementation
(anchored regex, null-safe, `NaN`-safe).

```
parseServerDate(raw: string | null | undefined): Date | null
serverDateMs(raw: string | null | undefined): number            // 0 when absent/invalid
formatRelativeTime(raw, opts?: { fallback?: 'full' | 'short' }): string
formatServerDateTime(raw, opts?): string                        // absolute, ru-RU
formatServerDate(raw): string                                   // date only, ru-RU
```

Contract, to be stated in the module's doc comment:
- A string carrying an offset (`Z`, `+HH:MM`, `+HHMM`, `-HH:MM`) is parsed **as-is**.
- A string with no offset is treated as **UTC** — verified in §2.1: all containers and MySQL run
  UTC and no `TZ` is set anywhere. **If a `TZ` env var is ever introduced, this breaks.**
- Detection regex must be **anchored to the end** (`/(?:Z|[+-]\d{2}:?\d{2})$/i`). The unanchored
  `[Z+]` in `PostCard.tsx` must not be carried forward.
- `null`/`undefined`/unparseable never throw: `null` / `0` / `'—'`.
- Rendering uses the browser's own locale conversion, so the player's timezone and DST are handled
  by the platform. No manual offset arithmetic anywhere.

### 3.6 Security Considerations

- **Authentication / authorization:** unchanged. No endpoint gains or loses a guard; no RBAC
  permission is added or altered.
- **Rate limiting:** not applicable — no new endpoint.
- **Input validation:** the helper is a parser fed by server responses. It must be **total**: never
  throw, never return `Invalid Date` to a renderer, on any input including `null`, `''`, and
  malformed strings. The current `helpers.js:21` violates this (throws on `null`) and is removed.
- **Information disclosure:** a corrected timestamp reveals a post's true age. That is the intended
  product behaviour and exposes nothing that was not already in the payload.
- **Error display (CLAUDE.md §11):** unchanged — this feature adds no API calls. Existing error
  handling on the touched components must not be weakened.

### 3.7 Frontend conventions that apply

- **§10.8 Tailwind:** this feature changes **logic only, never styles.** No component's CSS/SCSS
  may be touched, and therefore no Tailwind migration is triggered or permitted here. A developer
  who restyles a component "while in there" is out of scope and fails review.
- **§10.9 TypeScript:** all new code in `.ts`/`.tsx`. `helpers/helpers.js` is `.js`; rather than
  migrating the whole file (5 importers, 3 unrelated functions), **delete `formatDateTime` from it**
  and move `BattlePageBar.tsx` onto `formatServerDateTime`. Minimal diff, no new logic in `.js`.
  `CountdownTimer.jsx` and `CharacterResourcesList.jsx` import other helpers and must not be
  touched.
- **§10.11 no `React.FC`:** no component signatures change; none may be introduced.
- **§10.12 adaptivity:** no styles change, so no responsive work is triggered.
- Russian remains the language of all user-facing strings.

### 3.8 Data Flow

```
Backend (UTC, naive)  ──JSON "2026-03-23T10:23:58"──┐
Backend (battle-svc)  ──JSON "...T10:23:58+03:00"───┤
                                                    ▼
                                    src/utils/serverDate.ts
                                    offset present? parse as-is
                                    offset absent?  treat as UTC (+Z)
                                                    ▼
                                    Date object (absolute instant)
                                                    ▼
                    browser locale/DST ──> displayed in the player's timezone

Game calendar (unchanged in value):
  GET /locations/game-time → { epoch, server_time } ──both via serverDate──> computeGameTime
  difference of the two ⇒ result identical to today
```

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Ordering is deliberate: **T1+T2 alone already fix the reported bug** (the location feed and the
other relative times) and can ship on their own if the rest slips. T3–T8 widen the same fix;
T6 is isolated because it is the one that can break the game calendar; T9–T10 are the backend
crash fix.

All paths are relative to `services/frontend/app-chaldea/` unless stated otherwise.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Create the shared parser/formatter per §3.5. Single canonical `formatRelativeTime` with a `fallback` option so each call site keeps its current Russian wording. Doc comment must state the "naive == UTC" assumption and its dependency on no `TZ` being set. Anchored regex. Must never throw. | Frontend Developer | DONE | **new** `src/utils/serverDate.ts` | — | `npx tsc --noEmit` and `npm run build` pass. Helper returns `null`/`0`/`'—'` for `null`, `''`, `'garbage'`. `'2026-03-23T10:23:58'` and `'2026-03-23T10:23:58Z'` parse to the same instant. `'2026-03-23T13:23:58+03:00'` parses to that same instant and is **not** shifted again. |
| 2 | Migrate the 5 divergent `formatRelativeTime` copies and `formatLastActive` onto the helper; delete the local copies. This is the fix for the originally reported bug. | Frontend Developer | DONE | `src/utils/formatLastActive.ts`, `src/components/pages/LocationPage/PostCard.tsx`, `src/components/HomePage/LatestRoleplayPosts/LatestRoleplayPosts.tsx`, `src/components/Messenger/ConversationItem.tsx`, `src/components/ProfilePage/LogsTab/LogsTab.tsx`, `src/components/pages/OnlineUsersPage/OnlineUsersPage.tsx` | #1 | Zero local `formatRelativeTime` definitions remain (`grep -rn "const formatRelativeTime" src/` → only `serverDate.ts`). A post created 3 h ago reads «3 часа назад» in a UTC+3 browser, not «только что». Online/offline status in `FriendsSection`/`OnlineUsersPage` correct. Wording at each call site unchanged from before. tsc + build pass. |
| 3 | Remove the duplicated workarounds: `parseServerDate` (`PostCard.tsx:69-70`) and `parseServerTimestamp` (`usePostDraft.ts:138-143`) now call the shared helper. No behaviour change intended — the edit window and draft-freshness logic must keep working exactly as FEAT-159/FEAT-156 left them. | Frontend Developer | DONE | `src/components/pages/LocationPage/PostCard.tsx`, `src/hooks/usePostDraft.ts` | #1, #2 | `grep -rn "parseServerDate\|parseServerTimestamp" src/` returns no local definitions. The «Редактировать» button still appears for <1 h posts and disappears after. Draft newer-of-server-vs-local still picks correctly. tsc + build pass. |
| 4 | Migrate player-facing **absolute** date/time displays onto the helper. Display formats and Russian wording unchanged. | Frontend Developer | DONE | `src/components/Messenger/MessageArea.tsx` (:43, :286 — note :286 is the day-grouping key), `src/components/Messenger/MessageBubble.tsx`, `src/components/Chat/ChatMessage.tsx`, `src/components/Tickets/TicketMessage.tsx`, `src/components/Tickets/TicketListPage.tsx`, `src/components/CommonComponents/Header/NotificationBell.tsx`, `src/components/CommonComponents/Header/MobileHeader.tsx`, `src/components/pages/LocationPage/DraftsPanel.tsx`, `src/components/pages/PostHistoryPage/PostHistoryPage.tsx`, `src/components/ProfilePage/BattlesTab/BattlesTab.tsx`, `src/components/ProfilePage/PerksTab/PerkDetailModal.tsx`, `src/components/UserProfilePage/WallSection.tsx`, `src/components/UserProfilePage/UserProfilePage.tsx`, `src/components/UserProfilePage/CharactersSection.tsx`, `src/components/CommonComponents/CharacterPassport/CharacterPassport.tsx`, `src/components/pages/AllUsersPage/AllUsersPage.tsx`, `src/components/pages/ArchivePage/ArchivePage.tsx`, `src/components/pages/ArchivePage/ArchiveArticlePage.tsx`, `src/components/DungeonPage/DungeonRoom.tsx` | #1 | No `new Date(<server field>)` remains in these files. Messenger «Сегодня»/«Вчера» separators and day grouping land on the correct local day. No SCSS/CSS file modified by this task. tsc + build pass. |
| 5 | Migrate elapsed/expiry/countdown comparisons. **`floatingStructuresSlice.ts` must fix the parse AND drop the now-redundant client↔server offset subtraction in the same change** (§2.5 item 2) — otherwise the correction is applied twice. | Frontend Developer | DONE | `src/hooks/useGatheringLock.ts`, `src/components/pages/LocationPage/GatheringSection/GatheringNodeCard.tsx`, `src/components/pages/LocationPage/LocationPage.tsx` (:71 travel cooldown), `src/components/SkillTreeView/SkillUpgradeModal.tsx` (:28, :150), `src/redux/slices/floatingStructuresSlice.ts` (:91-93), `src/components/WorldPage/FloatingStructuresLayer.tsx` (:74-78) | #1 | Gathering countdown, travel cooldown and skill-reset cooldown show the same remaining time as the server enforces (cross-check against the 400 message from `locations-service/app/main.py:1194`). Floating structures sit at the same route position as before this change — **not** shifted by the browser offset. tsc + build pass. |
| 6 | **Game calendar — isolated, highest care.** Migrate `gameTime.ts` `epoch` **and** `server_time` to the helper **in the same change** (§3.4). Make `GameTimeWidget`'s 60 s tick use the same reference frame as its first render. Fix the `GameTimeAdminPage` epoch round-trip so loading and saving the epoch is lossless in any browser timezone. | Frontend Developer | DONE | `src/utils/gameTime.ts` (:72-73), `src/components/WorldPage/GameTimeWidget.tsx` (:48-62), `src/components/Admin/GameTimeAdminPage.tsx` (:53-64, :113, :173) | #1 | **Before/after, the widget shows the same in-game year/segment/week** as `computed` from `GET /locations/game-time` — verified live in a non-UTC browser. The value does **not** change one minute after load. Opening `GameTimeAdminPage` and saving without editing leaves `epoch` in the DB **byte-identical** (`SELECT epoch FROM game_time_config` before and after). tsc + build pass. |
| 7 | Migrate admin-page date displays. | Frontend Developer | DONE | `src/components/AdminModerationPage/AdminModerationPage.tsx`, `src/components/AdminLocationsPage/EditForms/EditLocationForm/GatheringNodesEditor/NodeRow.tsx`, `src/components/Admin/RbacAdminPage/UsersTab.tsx`, `src/components/Admin/DungeonsPage/AdminDungeonSessions.tsx`, `src/components/Admin/MobsPage/AdminActiveMobs.tsx`, `src/components/Admin/ArchiveAdminPage/ArchiveAdminPage.tsx`, `src/components/Admin/AdminBattlePass/SeasonsTab.tsx`, `src/components/Admin/BattlesPage/AdminBattlesPage.tsx`, `src/components/pages/MyRequestsPage/MyRequestsPage.tsx` (:65 sort) | #1 | No `new Date(<server field>)` remains in these files. `AdminBattlesPage` `runtime.deadline_at` renders correctly for **both** an offset-carrying and a naive value. tsc + build pass. |
| 8 | Remove the broken third workaround: delete `formatDateTime` from `helpers/helpers.js` (it corrupts already-zoned input and throws on `null`) and move its single consumer onto `formatServerDateTime`. Per §3.7 do **not** migrate the rest of `helpers.js`, and do not touch the two `.jsx` files that import other helpers from it. | Frontend Developer | DONE | `src/helpers/helpers.js`, `src/components/pages/BattlePage/BattlePageBar/BattlePageBar.tsx` (:903) | #1 | `formatDateTime` no longer exists; `grep -rn "formatDateTime" src/` clean. Battle log timestamps render correctly and show no `NaN`. `CountdownTimer.jsx` / `CharacterResourcesList.jsx` unmodified. tsc + build pass. |
| 9 | **Backend.** Normalise `battle-service` turn deadlines to UTC (§2.3, §3.2): stop building deadlines via `astimezone(moscow_tz)`; make every comparison that parses `state["deadline_at"]` tolerant of **both** a legacy `+03:00` string and a naive UTC one, so battles in flight across the deploy keep working. Fixes the `TypeError` on pause and stops `battles.deadline_at` being stored in Moscow wall-clock. Same absolute instants — no API contract change. | Backend Developer | DONE | `services/battle-service/app/main.py` (:614-615, :1607-1609, :1665, :2480-2481, :2817, :3228-3229, :3526-3527), `services/battle-service/app/redis_state.py` (:133, :174) | — | `python -m py_compile` passes on every modified file. Pausing and resuming a battle no longer raises `TypeError`. A battle created before the change (Redis state holding `+03:00`) still pauses, resumes and times out correctly. Turn duration is still `TURN_TIMEOUT_HOURS`. The ZSET deadline sweeper fires at the same wall-clock moment as before. |
| 10 | **QA (mandatory — backend Python changed).** pytest for T9: deadline is UTC and `TURN_TIMEOUT_HOURS` ahead; pause/resume with a **legacy offset-aware** state string does not raise; pause/resume with a **naive** state string does not raise; the value written to `battles.deadline_at` is UTC, not UTC+3; the ZSET score equals the correct absolute epoch for both string forms. | QA Test | DONE | `services/battle-service/app/tests/` (new `test_deadline_timezone.py`) | #9 | pytest passes inside the `battle-service` container. Tests fail if T9 is reverted. No existing battle-service test regresses. |
| 11 | Confirm no `TZ` env var is set for any service in either compose file and record the "containers are UTC" invariant so a future change cannot silently break §3.5 (R1). No functional change expected. | DevSecOps | DONE | `docker-compose.yml`, `docker-compose.prod.yml` | — | `grep -n "TZ" docker-compose.yml docker-compose.prod.yml` returns nothing; the invariant is written down where a future editor will see it. |
| 12 | Update `docs/ISSUES.md`: **remove** the now-fixed entry at line ~301 (relative post time / timezone) per CLAUDE.md §11 bug tracking. **Add**: (a) Stage 2 — backend should emit UTC offsets, with the §2.2 list of 22 hand-rolled `.isoformat()` sites and the ~160 `class Config:` blocks; (b) CLAUDE.md §1 service table is stale — `dungeon-service`, `battle-pass-service`, `party-service` are missing. | Reviewer | DONE | `docs/ISSUES.md` | #1–#10 | ISSUES.md reflects current reality: fixed entry gone, two new entries present with service/file/priority. |
| 13 | Final review. Re-run `npx tsc --noEmit` and `npm run build`; re-run battle-service pytest; **live-verify in a non-UTC browser** (CLAUDE.md §11): location feed relative times, messenger day separators, online status, battle turn timer, and the game-time widget one minute after load. Zero console errors. Verify §3.7: **no CSS/SCSS file was modified and no `.jsx` file gained logic**. | Reviewer | DONE (review #1 FAIL → review #2 **PASS**) | all | #1–#12 | All automated checks pass **and** live verification recorded in section 5. `grep -rn "new Date(" src/` shows no remaining server-field parse. A review without both automated results and live verification is invalid. |
| 14 | **Review fix (blocking).** `BattlePage.tsx:298` parses `runtime.deadline_at` with bare `new Date()`. T9 changed that field from offset-aware `+03:00` to naive UTC, so the player-facing turn countdown is now off by the viewer's UTC offset. Move it onto `utils/serverDate`. | Frontend Developer | DONE | `src/components/pages/BattlePage/BattlePage.tsx` (:298) | #1, #9 | `grep -rn "new Date(" src/` shows no server-field parse anywhere. The turn countdown matches the server's remaining time in a non-UTC browser, for a battle created both before and after the deploy. tsc + build pass. |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

### Questions for PM (assumptions stated, proceed unless corrected)

1. **Stage 2 scheduling.** Backend-wide UTC offsets are deliberately excluded here (§3.1).
   *Assumption:* it is filed as tech debt (T12) and scheduled separately. If the user wants the
   backend fixed in this feature, the task table roughly triples and every service needs QA.
2. **Game-time admin epoch round-trip (T6).** This is a data-corruption bug adjacent to, but not
   identical to, the reported post-time bug. *Assumption:* in scope, because it is the only
   timezone defect that corrupts stored data and it sits in the same file set. Say so if it should
   be split out.
3. **`formatRelativeTime` wording.** The five copies word things slightly differently.
   *Assumption:* each call site keeps its current Russian wording via the `fallback` option; no
   user-visible wording changes in this feature.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-14

**Result: FAIL** — two server-timestamp parse sites were missed by the migration sweep, one of
them a **regression this feature introduces** into the player-facing battle turn timer. Everything
else verified clean, including both flagged traps and the game calendar.

Every check below was run by the Reviewer; nothing was taken from the implementers' logs.

#### Automated Check Results

| Check | Command (where) | Result |
|-------|-----------------|--------|
| TypeScript | `npx tsc --noEmit` (container `frontend`, `/app`) | **PASS** — exit 0, zero diagnostic lines |
| Production build | `npm run build` (container `frontend`) | **PASS** — exit 0, `built in 49.74s` (re-run after the Reviewer's own fix: `built in 45.44s`) |
| Python syntax | `python -m py_compile app/main.py app/redis_state.py app/tests/test_deadline_timezone.py` (container `battle-service`) | **PASS** — exit 0 |
| pytest battle-service | `python -m pytest app/tests/ -q` (container `battle-service`) | **PASS** — `405 passed, 10 warnings in 18.11s` (expected 405) |
| pytest battle-service, new file | `python -m pytest app/tests/test_deadline_timezone.py -q` | **PASS** — `29 passed in 1.44s` |
| pytest locations-service | `python -m pytest app/tests/ -q` (container `locations-service`) | **PASS** — `1057 passed, 3 warnings in 26.74s` (expected 1057 — no regression from the other features shipping in this tree) |
| compose dev | `docker compose -f docker-compose.yml config -q` | **PASS** — exit 0 |
| compose prod | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q` | **PASS** — exit 0 |
| `TZ` invariant (T11) | `grep -n "TZ" docker-compose.yml docker-compose.prod.yml` | **PASS** — 8 hits, **all of them comments** warning against setting it; no `TZ` env var anywhere. Re-checked on live MySQL: `@@global.time_zone = SYSTEM`, `NOW() = UTC_TIMESTAMP() = 2026-09-13 21:17:39` |

#### Substance checks

**1. The helper is genuinely offset-tolerant, not `Z`-appending.** `parseServerDate` executed in
the `frontend` container under `TZ=Europe/Moscow` on 13 inputs:

```
"2026-03-23T10:23:58"        -> 2026-03-23T10:23:58.000Z  ms=1774261438000
"2026-03-23T10:23:58Z"       -> 2026-03-23T10:23:58.000Z  ms=1774261438000
"2026-03-23T13:23:58+03:00"  -> 2026-03-23T10:23:58.000Z  ms=1774261438000
"2026-03-23T05:23:58-05:00"  -> 2026-03-23T10:23:58.000Z  ms=1774261438000
"2026-03-23T13:23:58+0300"   -> 2026-03-23T10:23:58.000Z  ms=1774261438000
"2026-03-23 10:23:58"        -> 2026-03-23T10:23:58.000Z  ms=1774261438000
"2026-03-23T10:23:58.123456" -> 2026-03-23T10:23:58.123Z
"2026-03-23"                 -> 2026-03-23T00:00:00.000Z   (date-only also read as UTC)
"" / null / undefined / "garbage" / "2026-13-45T99:99:99" / "   "  -> null, ms=0
formatRelativeTime(null)="—"   formatRelativeTime(undefined,{invalid:""})=""   formatServerDateTime(null)="—"
```

Six syntactically different spellings of the same instant collapse to the **identical** epoch
value: an already-zoned string is not shifted again. Totality confirmed — nothing throws, nothing
leaks an `Invalid Date`. The detection regex is anchored; the unanchored `[Z+]` from `PostCard`
was not carried forward.

**2. Both `battle-service` forms render identically.** The backend now writes naive UTC on every
path (`redis_state.py:186` via `to_naive_utc`, and naive `new_deadline.isoformat()` at
`main.py:1665, 2816`), while `parse_deadline` accepts legacy `+03:00`, naive, and `Z`.
`test_deadline_timezone.py` pins exactly that — the three forms of one instant parse equal, and
`deadline_epoch(naive) == deadline_epoch(aware)`. 29/29 pass.

**3. No remaining server-field parse.** `grep -rn "new Date(" src/`, minus `new Date()` and
`new Date(<number>)`, left 6 hits. Four are legitimate:
`GameTimeAdminPage.tsx:142` parses a `<input type="datetime-local">` value, which is *deliberately*
local wall-clock; `PostCreateForm.tsx:46` and `GameTimeWidget.tsx:63` take a number;
`serverDate.ts:8` is a doc comment. The remaining two are defects — see Issues Found.

**4. Zero local copies / workarounds remain.** `grep -rn "const formatRelativeTime" src/` → only
`serverDate.ts`. `grep -rn "parseServerTimestamp\|formatDateTime" src/` → **no hits at all**:
`PostCard.parseServerDate`, `usePostDraft.parseServerTimestamp` and `helpers.js formatDateTime` are
gone. The five call sites pass `style` / `fallback` / `yesterday` / `invalid` and keep their
previous Russian wording.

**5. Trap A — `floatingStructuresSlice.ts` applies the correction exactly once. Verified.** The
`serverNowOffsetMs` state field, its selector, its thunk computation, the prop and the
`- serverNowOffsetMs` term at `FloatingStructuresLayer.tsx:78` are all removed in the same change
that fixed the `started_at` parse. Judgement on the trade-off below.

**6. Trap B — `gameTime.ts` changed both parses in one edit. Verified.** `epochMs` and `serverMs`
are both `parseServerDate(...)?.getTime() ?? NaN` on adjacent lines, with a comment forbidding
editing one without the other, plus a new `!Number.isFinite(elapsed) -> 0` guard the old code
lacked.

**7. The game calendar has not moved — verified independently, not accepted on trust.** 20 000
samples at 11-minute steps from the real epoch, run through the **new** `computeGameTime` inside
the `frontend` container once per timezone, then compared by MD5 against the same sweep through
the **backend** `locations-service/app/crud.py::compute_game_time`:

```
20c3a8238040074c9a317c8220eb5015  /tmp/py.txt                      <- backend algorithm
20c3a8238040074c9a317c8220eb5015  /tmp/js_UTC.txt
20c3a8238040074c9a317c8220eb5015  /tmp/js_Europe_Moscow.txt
20c3a8238040074c9a317c8220eb5015  /tmp/js_America_New_York.txt
20c3a8238040074c9a317c8220eb5015  /tmp/js_Australia_Sydney.txt
```

Byte-identical to the backend in every timezone, DST zones included. The **old** path's
elapsed-day series hashed the same in UTC / Moscow / Kathmandu / Kiritimati but **differed** in
America/New_York (`2f7ffb24`) and Australia/Sydney (`a9728a0c`) — exactly T6's claim: old and new
legitimately differ in DST zones, and new is the correct one. Live cross-check against the
server's own `computed` from `GET /locations/game-time` in five timezones: all `MATCH= true`
(`1787 imbolc null true`).

**8. The admin epoch round trip is lossless in any browser timezone.** DB value read before and
after this review: `epoch = 2026-01-01 20:00:00` — **unchanged**, identical to the value recorded
in section 2.1 before any work started, despite T6's three live PUTs (`updated_at` still reads
`2026-06-19 19:07:25`, i.e. those PUTs wrote the same value back). Both directions of
`GameTimeAdminPage`'s new helpers executed under four timezones:

```
UTC              | input 2026-01-01T20:00 | untouched -> 2026-01-01T20:00:00 | reserialised -> 2026-01-01T20:00:00
Europe/Moscow    | input 2026-01-01T23:00 | untouched -> 2026-01-01T20:00:00 | reserialised -> 2026-01-01T20:00:00
America/New_York | input 2026-01-01T15:00 | untouched -> 2026-01-01T20:00:00 | reserialised -> 2026-01-01T20:00:00
Asia/Kathmandu   | input 2026-01-02T01:45 | untouched -> 2026-01-01T20:00:00 | reserialised -> 2026-01-01T20:00:00
```

Lossless on **both** the untouched path (raw string replayed) and the re-serialised path
(`toNaiveUtcIso`), in every zone. The data-corruption bug is genuinely closed.

**9. `battle_turns.deadline_at` was UTC+3 and will now be UTC.** Live rows confirm the old skew:
`TIMESTAMPDIFF(HOUR, submitted_at, deadline_at) = 27` on all of ids 1120-1127. The new path is
pinned by `test_deadline_timezone.py` (`abs(hours_ahead - TURN_TIMEOUT_HOURS) < 0.01` and
`deadline.tzinfo is None`). No `moscow_tz` / `astimezone` survives in `battle-service` outside the
explanatory comment and `to_naive_utc` itself.

**10. Section 3.7 frontend conventions — clean.** `git status` shows **no `.css` / `.scss` file
modified**. The only `.js` file touched is `helpers/helpers.js`, and the change is a pure
**deletion** of `formatDateTime` (13 lines removed, 0 added) — no logic was added to any `.js` or
`.jsx` file. `CountdownTimer.jsx` and `CharacterResourcesList.jsx` are untouched. No `React.FC`
introduced (no component signature changed). No new `.jsx` files.

#### Live Verification Results

**The `claude-in-chrome` extension is not connected in this session** ("Browser tools are not
available: the Claude in Chrome extension is not set up"), so **no step ran in a real browser.**
Everything below ran against the live running stack instead: real HTTP against the live
`locations-service`, the real application modules executed under real IANA timezones inside the
`frontend` container, and the live MySQL.

- Live endpoints (via `httpx` inside `locations-service`): `GET /locations/game-time` → **200**,
  `GET /locations/posts/latest?limit=2` → **200**, `GET /locations/map/floating-structures` →
  **200**. The payloads confirm the naive serialisation the feature is built on:
  `"server_time":"2026-09-13T21:20:21.351996"`, `"created_at":"2026-09-13T15:07:31"`.
- **The originally reported bug, on live data** — `formatRelativeTime` on the newest real post:

```
post created_at 2026-09-13T15:07:31 | new label «6 ч. назад» | true age 6.2 h
   TZ=UTC               old parse said  6.2 h
   TZ=Europe/Moscow     old parse said  9.2 h   <- the reported bug
   TZ=America/New_York  old parse said  2.2 h
   TZ=Asia/Kathmandu    old parse said 12.0 h
```

  The label now reads «6 ч. назад» in every timezone. Fixed, on production-shaped data.
- Game-time widget reference frame, live: client `computeGameTime` equals server `computed` in
  five timezones (item 7 above).
- DB state after the whole review: `game_time_config.epoch = 2026-01-01 20:00:00`, unchanged. No
  rows written, no Redis keys created, all temporary files removed.

**Checks that could NOT run without a real browser, and are therefore NOT verified:**

1. Browser console cleanliness (zero `console.error`, no unhandled rejections) on any page.
2. Rendered DOM of the location feed, the messenger «Сегодня» / «Вчера» separators and the
   online-status badges — the underlying functions were executed and verified, the rendering was
   not.
3. The game-time widget's behaviour **one minute after load** (the 60 s `setInterval` tick).
4. The battle turn countdown as the player actually sees it — which is exactly where issue 1
   below lives, so this gap and that defect compound.
5. Floating structures sitting at the same route position as before the change.
6. Mobile / responsive rendering — not applicable, no styles changed.

PM should treat items 1-5 as outstanding manual verification even after the fix lands.

#### Issues Found

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/components/pages/BattlePage/BattlePage.tsx:298` | **Regression introduced by this feature.** `const turnEnd = new Date(runtime.deadline_at).getTime();` parses a server field with bare `new Date()`. Before T9 `deadline_at` reached the client offset-aware as `+03:00`, so this line was *correct*; T9 normalised it to **naive UTC** (`redis_state.py:186`, `main.py:1665, 2816`, served raw at `main.py:1263, 1353, 1438, 3813, 4576`), so the player-facing turn countdown is now wrong by the viewer's UTC offset — a UTC+3 player is shown **3 hours more** time than the server will actually grant. The file is named in section 3.3 as a known consumer but appears in no task's file list, so the sweep never opened it. Fix: `serverDateMs(runtime.deadline_at)` from `utils/serverDate`, then confirm the countdown live. | Frontend Developer | **DONE** — fixed 2026-09-14 (T14). The line now uses `parseServerDate` rather than `serverDateMs`: `serverDateMs` returns `0` for an absent/unparseable deadline, which as a countdown target would render an enormous elapsed time, so the `null` branch is taken explicitly and `timeLeft` falls back to `0` (the old code produced `NaN` there). The countdown was executed with both deadline shapes under four timezones and matches `redis_state.parse_deadline` exactly — output in «Post-fix verification» below. One correction to this row's wording: the skew runs the other way east of UTC — reading naive UTC as local wall-clock makes the deadline *earlier*, so a UTC+3 player was shown **less** time (a one-hour turn read as already expired), while a UTC-4 player was shown **more** (five hours). Wrong in both directions; measured below. |
| 2 | `services/frontend/app-chaldea/src/components/Tickets/AdminTicketsPage.tsx:50` | `formatDate` parsed `ticket.updated_at` with bare `new Date()`. Its sibling `TicketListPage.tsx:43` received exactly this migration in T4; this copy was missed, so admin ticket timestamps stayed wrong by the viewer's offset. **Fixed by the Reviewer** — trivially in scope, the identical two-line change already applied to the sibling file. `tsc` and `npm run build` re-run green afterwards. | Reviewer | DONE |

Issue 1 is the blocking one. It is a one-line change, but it alters live battle behaviour in a
file this feature never opened, so it belongs to the Frontend Developer together with a live check
of the countdown — not to a reviewer's drive-by edit.

#### Judgement on the floating-structures trade-off

The T5 agent removed the `serverNowOffsetMs` term outright rather than keeping it as a genuine
clock-skew correction. **I judge the shipped choice correct**, for a stronger reason than "smaller
diff":

The old term was never a clock-skew measurement. It was `Date.now() - new Date(server_now)` with
`server_now` mis-parsed as local, so on a perfectly synchronised clock it evaluated to exactly the
browser's UTC offset rather than to zero. Keeping it "fixed" would have meant keeping a term that
had never once measured the thing it was named after. Nothing real is lost by deleting it, because
nothing real was ever there. The alternative the agent noted (fix both parses and keep the term)
is defensible in principle and would additionally survive a badly-set client clock, but it buys
that robustness for a purely decorative map animation at the price of keeping a second correction
alive next to the first — precisely the double-correction shape this feature exists to remove.
Applying the correction exactly once, in one place, is the right call.

Two consequences worth recording, neither blocking:

- `server_now` is still emitted by `GET /locations/map/floating-structures` and still typed on
  `FloatingStructurePublic`, but now has **no consumer**. Harmless; a candidate for removal
  whenever that endpoint's contract is next revised.
- `FloatingStructuresLayer` now interpolates from the raw browser clock, while `GameTimeWidget`
  deliberately advances the *server* instant by elapsed real time. The two files end up with
  different philosophies about client clock skew. Both are defensible in context (decorative
  animation vs. the game calendar), but it is an inconsistency a future reader will trip over.

#### T12 — `docs/ISSUES.md` (done by the Reviewer)

- **Removed** the now-fixed entry «Баг: относительное время постов считается без учёта часового
  пояса» (was at line 301, MEDIUM). Per CLAUDE.md section 11 a stale entry for a fixed bug is
  itself a violation; the fix was verified real above, not assumed.
- **Added HIGH** «ZSET `battle:deadlines` никто не читает — таймаут хода не срабатывает сам по
  себе». Confirmed independently: `grep -rn "zrangebyscore|zpopmin|battle:deadlines" services/`
  yields only `zadd` / `zrem` and the constant declaration; the `zrange` at `redis_state.py:251`
  is a different key (`KEY_BATTLE_TURNS`), and no celery-beat schedule reads it either. So
  `TURN_TIMEOUT_HOURS` never actually fires and the set grows unbounded for abandoned battles.
  Pre-existing — this feature changed the score value, not the (absent) consumer — **not
  blocking**.
- **Added MEDIUM** «Долг (Stage 2): бэкенд отдаёт все временные метки без часового пояса», with
  the 22 hand-rolled `.isoformat()` sites and the ~160 `class Config:` blocks, the
  non-atomic-rollout argument, and the two side effects to watch
  (`skills-service/app/tests/test_character_skill_reset.py:128`,
  `locations-service/app/main.py:1194,1457`).
- **Added LOW** «Таблица сервисов в CLAUDE.md п.1 устарела» — `dungeon-service`,
  `battle-pass-service` and `party-service` are live in `docker ps` and unlisted.
- Also corrected sections 2.3 and 3.2 of this feature file: the column is
  `battle_turns.deadline_at`, not `battles.deadline_at`. The Backend Dev flagged this in the log
  but the prose still said `battles`.

#### Pre-existing issues noted (not blocking, no task filed)

- `MessageArea.tsx:301` — `serverDayKey` returns `null` for an unparseable timestamp while
  `lastDay` also starts at `null`, so a first message carrying a broken date would get no date
  separator. Cosmetic and needs a corrupt timestamp to trigger.
- `PostCard.tsx:33` — a stray double blank line left where the deleted local `formatRelativeTime`
  used to be.

#### Verdict

**FAIL.** One blocking defect (issue 1), which the feature itself introduces into the battle turn
timer. Everything else — the helper, the ~55-site sweep, both traps, the game calendar, the epoch
round trip, the backend deadline normalisation and its 29 new tests — is verified correct and
ready. Once issue 1 is fixed and the countdown is confirmed live, this ships.

---

### Post-fix verification — T14 (Frontend Developer, 2026-09-14)

Issue 1 is fixed. `BattlePage.tsx` imports `parseServerDate` and the countdown reads
`const turnEnd = parseServerDate(runtime.deadline_at)` with an explicit `null` branch.

**Dual-form countdown, executed** — `serverDate.ts` transpiled with `esbuild` and run under real
IANA zones inside the `frontend` container. Reference instant: server clock `2026-09-14T12:00:00`
UTC, deadline one hour later, spelled three ways. `new=` is the fixed line, `old=` the pre-fix
`new Date(...)` on the same input:

```
TZ = Europe/Moscow    | browser offset = 3 h
  legacy +03:00   2026-09-14T16:00:00+03:00   new=3600 s   old= 3600 s
  naive UTC       2026-09-14T13:00:00         new=3600 s   old=    0 s   <- the regression
  explicit Z      2026-09-14T13:00:00Z        new=3600 s   old= 3600 s
TZ = America/New_York | browser offset = -4 h
  legacy +03:00                               new=3600 s   old= 3600 s
  naive UTC                                   new=3600 s   old=18000 s   <- the regression
  explicit Z                                  new=3600 s   old= 3600 s
TZ = Asia/Kathmandu   | browser offset = 5.75 h
  naive UTC                                   new=3600 s   old=    0 s
TZ = UTC                                      new=3600 s   old= 3600 s  (all three forms)

absent/invalid  null | undefined | '' | 'garbage'  ->  parseServerDate=null, timeLeft=0 s
all shapes agree: true (3600 s) — in every timezone
```

**Cross-checked against the server's own arithmetic** (`redis_state.parse_deadline` /
`deadline_epoch`, executed in the `battle-service` container on the identical strings):

```
2026-09-14T16:00:00+03:00 -> naive UTC 2026-09-14 13:00:00  epoch=1789390800  server remaining=3600 s
2026-09-14T13:00:00       -> naive UTC 2026-09-14 13:00:00  epoch=1789390800  server remaining=3600 s
2026-09-14T13:00:00Z      -> naive UTC 2026-09-14 13:00:00  epoch=1789390800  server remaining=3600 s
```

Client and server agree on 3600 s for every form in every zone. A battle in flight across the
deploy (Redis state still holding `+03:00`) and a battle started after it now show the identical
countdown, which is the dual-correctness the offset-tolerant helper exists for.

**Straggler sweep.** `grep -rn "new Date(" src/ --include=*.ts --include=*.tsx --include=*.js
--include=*.jsx | grep -v "new Date()"` → **5 hits, none of them a server field**:
`GameTimeAdminPage.tsx:142` (a `datetime-local` input value, deliberately local wall-clock),
`PostCreateForm.tsx:46` and `GameTimeWidget.tsx:63` (both take a number), `serverDate.ts:8` (doc
comment) and `serverDate.ts:72` (the helper's own `new Date(ms)`). Widened to catch other parse
shapes: `Date.parse(` outside `serverDate.ts` → no hits; `new Date(` split across a line break →
no hits; `dayjs` / `moment(` → not used in this codebase. **No straggler of the
`AdminTicketsPage` kind remains.**

| Check | Command (where) | Result |
|-------|-----------------|--------|
| TypeScript | `npx tsc --noEmit` (container `frontend`, `/app`) | **PASS** — exit 0, no diagnostics |
| Production build | `npm run build` (container `frontend`) | **PASS** — exit 0, `✓ built in 47.80s` |

Still **not** covered, unchanged from the review above: the countdown was verified by executing the
real module against the real server arithmetic, **not** rendered in a browser — the
`claude-in-chrome` extension is still unavailable. Items 1-5 of the review's outstanding-manual-
verification list remain outstanding.

---


### Review #2 — 2026-09-14

**Result: PASS** — the blocking regression from review #1 is genuinely fixed, and nothing else
regressed. Every check below was re-run by this reviewer from scratch; **no figure is carried over
from review #1 or from the implementers' logs.** The one gap is unchanged and stated plainly at the
end: the `claude-in-chrome` extension is still unavailable, so nothing was rendered in a real
browser.

#### Automated Check Results

| Check | Command (where) | Result |
|-------|-----------------|--------|
| TypeScript | `npx tsc --noEmit` (container `frontend`, `/app`) | **PASS** — `TSC_EXIT=0`, zero diagnostic lines |
| Production build | `npm run build` (container `frontend`) | **PASS** — `BUILD_EXIT=0`, `built in 46.62s` |
| Python syntax | `python -m py_compile main.py redis_state.py tests/test_deadline_timezone.py` (container `battle-service`, WORKDIR `/app`) | **PASS** — `OK`, `PYC_EXIT=0` |
| pytest battle-service (full) | `python -m pytest tests/ -q` | **PASS** — `405 passed, 10 warnings in 15.43s` (expected 405) |
| pytest battle-service (new file) | `python -m pytest tests/test_deadline_timezone.py -q` | **PASS** — `29 passed, 4 warnings in 1.76s` |
| pytest locations-service (full) | `python -m pytest tests/ -q` | **PASS** — `1057 passed, 3 warnings in 23.27s` (expected 1057) |
| compose dev | `docker compose -f docker-compose.yml config -q` | **PASS** — `DEV_EXIT=0` |
| compose prod | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q` | **PASS** — `PROD_EXIT=0` |
| `TZ` invariant (T11) | `grep -nE "^[[:space:]]*-?[[:space:]]*TZ[=:]" docker-compose*.yml` | **PASS** — exit 1, no hits. Plain `grep -n "TZ"` now returns 8 lines, **all comments** warning against setting it. Live MySQL re-checked: `@@global.time_zone = SYSTEM`, `NOW() = UTC_TIMESTAMP() = 2026-09-13 21:43:54` |

#### 1. The fix itself, verified by execution (not by reading)

`serverDate.ts` transpiled with the project's own `esbuild` and executed under real IANA zones
inside the `frontend` container. `NOW` pinned to `2026-09-14T12:00:00Z`; the deadline is one hour
later, spelled three ways. `new=` is the shipped line (`parseServerDate` + explicit `null` branch),
`old=` the pre-fix bare `new Date(...)` on the identical input:

```
TZ=UTC               legacy +03:00 new=3600s old=3600s | naive UTC new=3600s old= 3600s | Z new=3600s old=3600s
TZ=Europe/Moscow     legacy +03:00 new=3600s old=3600s | naive UTC new=3600s old=    0s | Z new=3600s old=3600s
TZ=Asia/Kathmandu    legacy +03:00 new=3600s old=3600s | naive UTC new=3600s old=    0s | Z new=3600s old=3600s
TZ=America/New_York  legacy +03:00 new=3600s old=3600s | naive UTC new=3600s old=18000s | Z new=3600s old=3600s
TZ=Australia/Sydney  legacy +03:00 new=3600s old=3600s | naive UTC new=3600s old=    0s | Z new=3600s old=3600s
```

`TZ=UTC` is the only row where old and new agree on all three forms — as expected, since local == UTC
there. It is precisely why a developer testing in a UTC container would never see this defect.

Two things this establishes independently:

- **The fix is correct in both directions.** 3600 s in every zone for every spelling — a battle in
  flight across the deploy (Redis state still `+03:00`) and one started after it show the same
  countdown.
- **The Frontend Developer's correction to review #1's wording is right, and review #1 was wrong.**
  Reading naive UTC as local wall-clock makes the deadline *earlier*, so east of UTC the timer ran
  **short** — at UTC+3 and at UTC+5:45 a one-hour turn read as already expired (`old=0s`) — and west
  of UTC it ran **long** (`old=18000s` at UTC-4). Review #1's row claimed a UTC+3 player was shown
  *more* time; that was the wrong direction. The corrected text now standing in the Issues table is
  accurate.

**Cross-checked against the server's own arithmetic** — `redis_state.parse_deadline` /
`deadline_epoch` executed in the `battle-service` container on the identical strings:

```
2026-09-14T16:00:00+03:00 -> naive UTC 2026-09-14 13:00:00  epoch=1789390800  remaining=3600s
2026-09-14T13:00:00       -> naive UTC 2026-09-14 13:00:00  epoch=1789390800  remaining=3600s
2026-09-14T13:00:00Z      -> naive UTC 2026-09-14 13:00:00  epoch=1789390800  remaining=3600s
```

Client `NOW` 1789387200 + 3600 s = **1789390800** — the client and the server land on the same
absolute instant, not merely on the same duration.

**Absent / unparseable deadline yields 0, not `NaN` and not 1970.** `null`, `undefined`, `''`,
`'garbage'`, `'2026-13-45T99:99:99'` all give `parseServerDate = null`, `timeLeft = 0`,
`Number.isNaN(timeLeft) = false`, `serverDateMs = 0`, `formatRelativeTime = '—'`,
`formatServerDateTime = '—'` — in all five zones. The `parseServerDate`-over-`serverDateMs` choice
is the right one: `serverDateMs` would return `0` and render a 1970 countdown target.

#### 2. Straggler sweep — re-run, not accepted

`grep -rn "new Date(" src/ --include=*.ts --include=*.tsx --include=*.js --include=*.jsx | grep -v "new Date()"`
gives **5 hits, none a server field**, each opened and read:

| Hit | Verdict |
|-----|---------|
| `GameTimeAdminPage.tsx:142` | parses the `<input type="datetime-local">` value — deliberately local wall-clock, and guarded by `Number.isNaN(parsed.getTime())` |
| `PostCreateForm.tsx:46` | argument is `epochMs: number` |
| `GameTimeWidget.tsx:63` | argument is `serverBaseMs + elapsedMs`, a number |
| `serverDate.ts:8` | doc comment |
| `serverDate.ts:72` | the helper's own `new Date(ms)` |

Widened beyond the reported sweep, since this defect existed precisely because one consumer was
missed while its neighbours were migrated: `Date.parse(` — one hit, inside `serverDate.ts`.
`new Date(` broken across a line (multiline regex) — none. `dayjs` / `moment(` — not used in this
codebase. `Date(` without `new` — none. `.split('T')` / `.slice(0,10)` on a date string — none.
`toISOString()` — 16 hits, **all** of them `new Date().toISOString()` producing a genuine
`Z`-carrying instant for optimistic local updates (`useWebSocket.ts`, `messengerSlice.ts`,
`ticketSlice.ts`, the two admin floating-structure pages); the helper parses those as-is and does not
shift them.

**No straggler of the `AdminTicketsPage` kind remains.** The review #1 fix to
`AdminTicketsPage.tsx:50` is in the tree and correct (`parseServerDate` plus `if (!date) return ''`).

#### 3. Re-confirmed after the files changed under them

- **Helper still offset-tolerant, not `Z`-appending.** `OFFSET_SUFFIX_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i`
  — anchored to the end; the unanchored `[Z+]` from `PostCard` was not carried forward. Confirmed by
  the dual-form run above: a `+03:00` string is never shifted twice.
- **Zero local copies or workarounds.**
  `grep -rn "const formatRelativeTime\|function formatRelativeTime" src/` → only `serverDate.ts:195`.
  `grep -rn "parseServerTimestamp\|formatDateTime" src/` → **no hits at all**.
  `grep -rn "const parseServerDate" src/` → only `serverDate.ts:65`.
- **`gameTime.ts` still changes both parses together**, on adjacent lines, with a comment forbidding
  editing one without the other, plus the `!Number.isFinite(elapsed) -> 0` guard.
- **The game calendar still matches the backend — re-derived, not re-read.** 20 000 samples at
  11-minute steps from the real epoch, run through the **new** `computeGameTime` in the `frontend`
  container once per timezone, MD5-compared against the same sweep through
  `locations-service/app/crud.py::compute_game_time`:

```
6f52c1a179d7b80aaab9b6927946256d  backend (compute_game_time)
6f52c1a179d7b80aaab9b6927946256d  js UTC
6f52c1a179d7b80aaab9b6927946256d  js Europe/Moscow
6f52c1a179d7b80aaab9b6927946256d  js America/New_York
6f52c1a179d7b80aaab9b6927946256d  js Australia/Sydney
6f52c1a179d7b80aaab9b6927946256d  js Asia/Kathmandu
```

  Byte-identical in every zone, DST zones included. Live cross-check: `GET /locations/game-time`
  returns `computed = {year: 1787, segment_name: "imbolc", week: null, is_transition: true}`, and the
  client computes `1787|imbolc|null|true` in all four zones.
- **The widget's 60 s tick is stable** — simulated by advancing the reference by 0 / 60 s / 10 min
  from the live `server_time`: `first = +60s = +10m = 1787|imbolc|null|true`, `stable=true` in every
  zone. There is now exactly one code path (`compute()` is called immediately *and* by the interval),
  so first render and tick cannot diverge by construction.
- **Admin epoch round trip still lossless**, both directions executed in five zones:

```
UTC              | input 2026-01-01T20:00 | untouched -> 2026-01-01T20:00:00 | reserialised -> 2026-01-01T20:00:00
Europe/Moscow    | input 2026-01-01T23:00 | untouched -> 2026-01-01T20:00:00 | reserialised -> 2026-01-01T20:00:00
America/New_York | input 2026-01-01T15:00 | untouched -> 2026-01-01T20:00:00 | reserialised -> 2026-01-01T20:00:00
Asia/Kathmandu   | input 2026-01-02T01:45 | untouched -> 2026-01-01T20:00:00 | reserialised -> 2026-01-01T20:00:00
Australia/Sydney | input 2026-01-02T07:00 | untouched -> 2026-01-01T20:00:00 | reserialised -> 2026-01-01T20:00:00
```

  Live DB unchanged: `game_time_config.epoch = 2026-01-01 20:00:00`,
  `updated_at = 2026-06-19 19:07:25` — the same values recorded in section 2.1 before any work began.
- **`floatingStructuresSlice` applies the correction exactly once.** `serverNowOffsetMs`, its
  selector, the thunk computation, the prop and the `- serverNowOffsetMs` term are all gone
  (`grep -rn "serverNowOffset" src/` returns comments only). Verified by execution on the **live**
  structure (`id 1 «Цитадель»`, `started_at 2026-07-31T21:51:43`, `speed 1.28601e-07`, live
  `server_now`): `progress new = 0.48883488`, `progress old = 0.48883488`, `delta = 0.000e+0` in
  UTC / Moscow / New_York / Sydney. **Positions do not move** — exactly T5's acceptance criterion.
- **Backend deadline normalisation intact.** No `moscow_tz` and no `astimezone` survive in
  `battle-service` outside `to_naive_utc` and the explanatory comment; every `deadline` /
  `started_at` construction is `utc_now()`, every ZSET score is `deadline_epoch(...)`, and the pause
  path parses through `parse_deadline` with a `None` guard. Live rows still carry the old skew
  (`TIMESTAMPDIFF(HOUR, submitted_at, deadline_at) = 27` on ids 1123-1127), i.e. the defect was real
  and only new writes are corrected.

#### 4. Section 3.7 conventions — clean

`git status --porcelain | grep -iE "\.(css|scss|sass|less)$"` → **no hits**: not one style file
modified. The only `.js` / `.jsx` file in the diff is `helpers/helpers.js`, and `git diff --stat`
shows `1 file changed, 13 deletions(-)` — a pure deletion of `formatDateTime`, **zero lines added**.
`CountdownTimer.jsx` and `CharacterResourcesList.jsx` untouched. No new `.jsx`. `React.FC` appears
only inside six pre-existing comments, never in a component signature.

#### 5. The originally reported bug, re-verified on live data

`GET /locations/posts/latest` against the running stack, with the browser clock synced to the live
`server_time = 2026-09-13T21:44:37`:

```
post 142  2026-09-13T15:07:31   ageNew = 6.62h in every zone   | ageOld: 6.62 UTC / 9.62 Moscow / 2.62 New_York / 16.62 Sydney
                                rel = «6 часов назад» in every zone
post 136  2026-09-04T21:00:47   ageNew = 216.73h in every zone | ageOld: 216.73 / 219.73 / 212.73 / 226.73
```

The brief's complaint («пост трёхчасовой давности показывается как "только что"») is closed: the age
is now identical in every timezone and equals the true age, while the *absolute* rendering correctly
does differ per zone (`13 сентября в 15:07` UTC vs `18:07` Moscow vs `11:07` New York) — the intended
behaviour, not a bug.

Online status and messenger day grouping executed likewise: a 2-minute-old timestamp gives
`isOnline = true` / «Онлайн» and a 3-hour-old one «Был(а) 3 часа назад» in all four zones (before the
fix everyone east of UTC read as permanently offline); a 26-hour-old message lands one *local* day
back in every zone; `null` still yields «Никогда не заходил(а)».

#### Reviewer's own fix (trivially in scope)

`docs/ARCHITECTURE.md` — the new "Time & Timezones" section told the reader to verify the invariant
with `grep -n "TZ" docker-compose.yml docker-compose.prod.yml` and said it «должно не выводить
ничего». That became false inside this same feature: T11 added eight *comment* lines containing the
word `TZ` to those files, so the documented check now prints eight hits and reads as a violation of
the invariant it is meant to prove. Replaced with a grep for an actual assignment
(`^[[:space:]]*-?[[:space:]]*TZ[=:]`, verified to exit 1 with no output) plus one sentence explaining
why the naive grep no longer works. Documentation only — no behaviour, no code.

#### Live Verification Results

**The `claude-in-chrome` extension is still not connected in this session** ("Browser tools are not
available: the Claude in Chrome extension is not set up"), so — as in review #1 — **no step ran in a
real browser.** Everything above ran against the live running stack instead: real HTTP through
`api-gateway`, the real application modules executed under real IANA timezones inside the `frontend`
container, the real `battle-service` and `locations-service` modules in their own containers, and
live MySQL.

- Live endpoints via `http://api-gateway:80`: `GET /locations/game-time` → **200**,
  `GET /locations/posts/latest?limit=3` → **200**, `GET /locations/map/floating-structures` → **200**.
  Payloads confirm the naive serialisation the feature rests on
  (`"server_time":"2026-09-13T21:44:31.641008"`, `"created_at":"2026-09-13T15:07:31"`,
  `"started_at":"2026-07-31T21:51:43"`).
- Live MySQL: `NOW() = UTC_TIMESTAMP()`, `@@global.time_zone = SYSTEM`, `epoch` unchanged.
- No rows written, no Redis keys created; every temporary file created during this review, on the
  host and inside the containers, was deleted.

**Still NOT verified, for lack of a browser — a manual check-list for the user:**

1. **Browser console cleanliness** — zero `console.error`, zero unhandled promise rejections, no
   4xx/5xx — on the location page, the messenger, the world map and a battle page.
2. **Rendered location feed** — that the relative labels («6 часов назад», «4 сен») actually appear
   under the posts. The functions were executed and are correct; the DOM was not inspected.
3. **Messenger «Сегодня» / «Вчера» separators and the online badges** — the day keys and status
   strings were computed and are correct; their rendering was not observed.
4. **The game-time widget one minute after load** — the 60 s `setInterval` tick was *simulated* and
   is stable; the real timer was not watched.
5. **The battle turn countdown as the player sees it** — verified by executing the exact shipped
   expression against the server's own arithmetic in five timezones, but not seen ticking on screen.
   Best done on a battle whose Redis state predates the deploy (legacy `+03:00`) *and* a freshly
   started one.
6. **Floating structures on the world map** — positions proven numerically unchanged
   (`delta = 0.000e+0`); not observed on the map.

Items 1-6 are display-level confirmations of behaviour already verified at the code-execution level.
None is a reason to hold the feature, but PM should hand them to the user as a short manual pass
after deploy.

#### Issues Found

**None.** Issue 1 from review #1 (`BattlePage.tsx:298`) is fixed and independently verified above;
issue 2 (`AdminTicketsPage.tsx:50`) is fixed and still in the tree. No new issue was found.

The two cosmetic notes from review #1 stand unchanged and remain non-blocking: `MessageArea.tsx:301`
would render an empty-labelled date separator for a corrupt timestamp, and `PostCard.tsx:33` carries
a stray double blank line where the deleted local `formatRelativeTime` used to be.

#### Verdict

**PASS.** The regression is closed, the sweep is clean under six independent search shapes, and every
trap the architecture flagged — the double correction, the paired game-calendar parse, the epoch
round trip, the dual-form deadline — is verified by execution rather than by reading. The feature is
ready to ship, with the six browser-level confirmations above left as a short manual pass.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-13 — PM: фича создана, баг найден при работе над FEAT-159
[LOG] 2026-09-13 20:05 — Architect: начал проектирование, статус OPEN → IN_PROGRESS
[LOG] 2026-09-13 20:10 — Architect: проверено на живых контейнерах — TZ нигде не задан, MySQL NOW() == UTC_TIMESTAMP(). Допущение «наивное время = UTC» подтверждено, а не угадано
[LOG] 2026-09-13 20:15 — Architect: аудит бэкенда — наивные даты во всех 10 сервисах, json_encoders нет нигде; найдено 22 места с ручным .isoformat() в обход Pydantic
[LOG] 2026-09-13 20:20 — Architect: найдено, что battle-service УЖЕ отдаёт deadline_at со смещением +03:00, а после паузы — наивное. Слепое дописывание Z сломало бы таймер хода
[LOG] 2026-09-13 20:22 — Architect: там же обнаружен латентный TypeError при постановке боя на паузу (main.py:1607-1609) и хранение battles.deadline_at в московском времени вместо UTC
[LOG] 2026-09-13 20:28 — Architect: аудит фронтенда — ~55 мест разбора серверного времени в ~45 файлах, 5 разных копий formatRelativeTime, 3 разных костыля (один из них, helpers.js, сам сломан)
[LOG] 2026-09-13 20:32 — Architect: игровой календарь сейчас верен только по совпадению — epoch и server_time портятся одинаково и ошибка сокращается. Правку обоих полей нельзя разносить по задачам
[LOG] 2026-09-13 20:35 — Architect: найдена порча данных — GameTimeAdminPage сдвигает epoch на смещение админа при каждом сохранении
[LOG] 2026-09-13 20:40 — Architect: межсервисный разбор строк — всего 2 места, оба уже терпимы к смещению. Риск для связи сервисов минимален
[LOG] 2026-09-13 20:45 — Architect: решение — фронтенд сейчас (Stage 1), бэкенд отдельной фичей (Stage 2). Общий парсер терпим к смещению, поэтому он предпосылка для Stage 2, а не замена ему
[LOG] 2026-09-13 20:50 — Architect: спроектировано 13 задач, изменений API-контрактов нет, миграций БД нет. Включена узкая бэкенд-правка battle-service + обязательная задача QA
[LOG] 2026-09-13 21:05 — Frontend Dev: начал задачи #1 и #2
[LOG] 2026-09-13 21:20 — Frontend Dev: создан `src/utils/serverDate.ts` — единый парсер со смещением: строка с поясом (`Z`, `+03:00`, `+0300`) разбирается как есть, без пояса — как UTC. Регулярка привязана к концу строки
[LOG] 2026-09-13 21:25 — Frontend Dev: в док-комментарии зафиксировано допущение «наивное = UTC» и его зависимость от того, что TZ нигде не задан. Функции тотальны — ни одна не бросает исключение и не возвращает Invalid Date
[LOG] 2026-09-13 21:40 — Frontend Dev: 5 копий formatRelativeTime схлопнуты в одну (PostCard, LatestRoleplayPosts, ConversationItem, LogsTab, OnlineUsersPage). Формулировки каждого места сохранены через опции style/fallback/yesterday/invalid
[LOG] 2026-09-13 21:45 — Frontend Dev: formatLastActive и isOnline переведены на serverDateMs — статус «Онлайн» больше не зависит от пояса игрока
[LOG] 2026-09-13 21:47 — Frontend Dev: локальный parseServerDate в PostCard не трогал — это задача #3; gameTime.ts и floatingStructuresSlice.ts не трогал вообще
[LOG] 2026-09-13 21:55 — Frontend Dev: проверка в контейнере frontend: `npx tsc --noEmit` — 0 ошибок, `npm run build` — успешно (31.74s). Хелпер прогнан в node с TZ=Europe/Moscow на 13 входах: наивное, Z, +03:00, -05:00, микросекунды, форма MySQL, пустая строка, null, undefined, мусор — все три корректные формы дают один и тот же момент, мусор даёт «—»
[LOG] 2026-09-13 21:57 — Frontend Dev: задачи #1 и #2 завершены
[LOG] 2026-09-14 00:10 — Frontend Dev: начал задачу #6 (игровой календарь) — самая опасная в фиче, поэтому вынесена отдельно
[LOG] 2026-09-14 00:20 — Frontend Dev: в gameTime.ts epoch и server_time переведены на parseServerDate ОДНОЙ правкой; рядом оставлен комментарий, что эти две строки нельзя править по отдельности
[LOG] 2026-09-14 00:35 — Frontend Dev: доказано исполнением, что календарь не сдвинулся. Живой ответ GET /locations/game-time прогнан старым и новым путём в TZ=UTC, Europe/Moscow, America/New_York, Asia/Kathmandu, Australia/Sydney, Pacific/Kiritimati — везде year=1787, imbolc, transition, как и computed с сервера
[LOG] 2026-09-14 00:40 — Frontend Dev: свип на 20000 синтетических server_time (шаг 11 минут, 43 различных состояния календаря): новый путь даёт один и тот же хэш во ВСЕХ поясах и совпадает с алгоритмом бэкенда. Старый путь совпадает не везде — расходится в поясах с переходом на летнее время (New York, Sydney), потому что epoch и server_time попадают в разные смещения и ошибка перестаёт сокращаться. То есть правка убирает расхождение, а не вносит его
[LOG] 2026-09-14 00:50 — Frontend Dev: GameTimeWidget — тик теперь считает от серверного момента плюс реально прошедшее время с получения ответа, а не от часов браузера. Первый рендер = тик при elapsed=0. Замер на 20000 загрузок: раньше показания прыгали через минуту в 3.5% случаев (Москва), 5.3% (Нью-Йорк), 12.5% (Сидней); теперь 0.03% во всех поясах — и ровно столько же в UTC, где бага нет вообще (это настоящая смена игрового дня)
[LOG] 2026-09-14 01:05 — Frontend Dev: GameTimeAdminPage — порча данных устранена. Загрузка epoch идёт через parseServerDate, сохранение отдаёт наивный UTC без пояса (тот же формат, что шлёт бэкенд; смещённая строка сделала бы datetime aware, а compute_game_time считает наивно). Дополнительно запоминается исходная строка: если админ ничего не менял, назад уходит она же, байт в байт
[LOG] 2026-09-14 01:15 — Frontend Dev: круговой обход проверен вживую, реальными PUT на /locations/game-time/admin в трёх поясах (Europe/Moscow, America/New_York, Asia/Kathmandu). В БД до и после — 2026-01-01 20:00:00, без изменений. Старый код в тех же поясах отправил бы 2026-01-01T17:00:00.000Z / 2026-01-02T01:00:00.000Z / 2026-01-01T14:15:00.000Z
[LOG] 2026-09-14 01:20 — Frontend Dev: проверка в контейнере frontend: `npx tsc --noEmit` — 0 ошибок, `npm run build` — успешно (45.36s). CSS/SCSS не тронут, .jsx не тронут, изменены ровно 3 файла из строки #6
[LOG] 2026-09-14 01:22 — Frontend Dev: задача #6 завершена
[LOG] 2026-09-13 22:05 — Frontend Dev: начал задачи #7 и #8
[LOG] 2026-09-13 22:20 — Frontend Dev: 9 админ-мест переведены на общий хелпер (AdminModerationPage, NodeRow, RbacAdminPage/UsersTab, AdminDungeonSessions, AdminActiveMobs, ArchiveAdminPage, SeasonsTab, AdminBattlesPage, MyRequestsPage). Форматы и русские формулировки не менялись — изменился только момент времени
[LOG] 2026-09-13 22:25 — Frontend Dev: сортировка заявок в MyRequestsPage переведена на serverDateMs; `new Date(<серверное поле>)` в файлах задачи #7 не осталось
[LOG] 2026-09-13 22:35 — Frontend Dev: проверен именно спорный случай runtime.deadline_at в AdminBattlesPage — прогнал обе формы одного и того же момента (`...T22:56:36+03:00` и наивную `...T19:56:36`) при TZ=Europe/Moscow и TZ=America/New_York. Обе дают один и тот же эпох-таймстемп и одинаковую строку (13.09.2026, 22:56:36 в Москве; 15:56:36 в Нью-Йорке). Бои, начатые до деплоя, отрисуются верно
[LOG] 2026-09-13 22:45 — Frontend Dev: задача #8 — formatDateTime удалён из helpers/helpers.js, единственный потребитель (BattlePageBar.tsx:903) переведён на formatServerDateTime. Старый хелпер на строке со смещением давал NaN.NaN.NaN NaN:NaN — проверено прогоном; новый даёт 13.09.2026 22:56. Прежний вид `dd.mm.yyyy hh:mm` сохранён (у ru-RU убрана запятая между датой и временем)
[LOG] 2026-09-13 22:47 — Frontend Dev: остальной helpers.js не мигрировал (§3.7); CountdownTimer.jsx и CharacterResourcesList.jsx не тронуты, ни одного CSS/SCSS-файла не менял
[LOG] 2026-09-13 22:55 — Frontend Dev: проверка в контейнере frontend: `npx tsc --noEmit` — 0 ошибок, `npm run build` — успешно (42.52s). Задачи #7 и #8 завершены
[LOG] 2026-09-13 23:40 — Frontend Dev: начал задачу #5 — сравнения «сколько осталось» (сбор ресурсов, кулдаун перемещения, сброс навыка, плавающие структуры)
[LOG] 2026-09-13 23:48 — Frontend Dev: useGatheringLock и GatheringNodeCard переведены на parseServerDate — complete_at и restore_at читаются в серверной системе отсчёта, а не в местной
[LOG] 2026-09-13 23:52 — Frontend Dev: LocationPage travel_cooldown_until — сверено с сервером: locations-service/app/main.py:1194 читает наивную строку как UTC и сравнивает с datetime.now(timezone.utc). Клиент теперь делает ровно то же самое, поэтому таймер и 400-я ошибка больше не расходятся
[LOG] 2026-09-13 23:55 — Frontend Dev: SkillUpgradeModal — и обратный отсчёт, и условие доступности сброса переведены на общий парсер, чтобы кнопка разблокировалась ровно в тот момент, когда счётчик дошёл до нуля
[LOG] 2026-09-14 00:05 — Frontend Dev: плавающие структуры — убрана связка «двойной ошибки». Раньше и server_now, и started_at разбирались через new Date() и оба уезжали на смещение браузера, а вычитание serverNowOffsetMs гасило ошибку обратно. Теперь started_at разбирается правильно, а вычитание и всё состояние serverNowOffsetMs удалены: поправка применяется ровно один раз, структуры остаются на той же точке маршрута
[LOG] 2026-09-14 00:08 — Frontend Dev: проверка в контейнере frontend — `npx tsc --noEmit` 0 ошибок, `npm run build` успешно (40.98s). Отдельно сверено в node с TZ=Europe/Moscow: строка '2026-09-14T12:34:56' даёт 1789389296000 мс, столько же выдаёт Python в контейнере locations-service; старый new Date() давал на 3 часа меньше
[LOG] 2026-09-14 00:09 — Frontend Dev: задача #5 завершена
[LOG] 2026-09-14 00:10 — Frontend Dev: начал задачи #3 и #4
[LOG] 2026-09-14 00:20 — Frontend Dev: удалены локальные костыли — parseServerDate в PostCard.tsx и parseServerTimestamp в usePostDraft.ts. Оба места переведены на общий хелпер, поведение сохранено: окно редактирования по-прежнему закрывается при непригодной дате (serverDateMs даёт 0 = «старее всего»), а выбор «сервер или локальная копия» в черновиках сравнивает ровно те же числа
[LOG] 2026-09-14 00:35 — Frontend Dev: 19 файлов с абсолютными датами переведены на parseServerDate/formatServerDate/formatServerDateTime. Формат вывода и русские формулировки не менялись — меняется только момент времени
[LOG] 2026-09-14 00:38 — Frontend Dev: в MessageArea ключ группировки по дням вынесен в serverDayKey — дата берётся из общего парсера, а сами поля календаря остаются локальными, чтобы сообщение попадало в тот день, который видел игрок
[LOG] 2026-09-14 00:40 — Frontend Dev: где раньше при битой дате получался Invalid Date/NaN, теперь ветка на null — пустая строка, «—» или исходная строка, как было в каждом конкретном месте
[LOG] 2026-09-14 00:52 — Frontend Dev: проверка границы суток выполнена в контейнере с TZ=Europe/Moscow на реальном хелпере: наивное 2026-09-13T21:00:00 теперь даёт ключ 2026-8-14 (было 2026-8-13) — сообщение больше не уезжает во «Вчера». Три эквивалентные формы (наивная, Z, +03:00) дают один и тот же ключ; мусор и null дают null без исключений
[LOG] 2026-09-14 00:55 — Frontend Dev: в контейнере frontend: npx tsc --noEmit — 0 ошибок, npm run build — успешно (48.87s). CSS/SCSS не трогал, в .jsx логику не добавлял
[LOG] 2026-09-14 00:56 — Frontend Dev: задачи #3 и #4 завершены
[LOG] 2026-09-13 22:05 — Backend Dev: начал задачу #9 (battle-service, часовые пояса дедлайнов)
[LOG] 2026-09-13 22:15 — Backend Dev: в redis_state.py добавлены общие помощники utc_now / to_naive_utc / parse_deadline / deadline_epoch. Дедлайны теперь везде наивный UTC, как и остальные временные значения в общей БД
[LOG] 2026-09-13 22:18 — Backend Dev: parse_deadline терпим к обеим формам — legacy со смещением +03:00 и новой наивной UTC. Бои, живущие в Redis через выкат, продолжают работать. Функция тотальна: на None, пустой строке и мусоре возвращает None, не бросает исключение
[LOG] 2026-09-13 22:22 — Backend Dev: убраны все 4 места с astimezone(moscow_tz) (main.py:614, 2480, 3228, 3526) — вместо них utc_now() + TURN_TIMEOUT_HOURS. Переменной moscow_tz в сервисе больше нет
[LOG] 2026-09-13 22:25 — Backend Dev: исправлен латентный TypeError при постановке боя на паузу (main.py:1607) — сравнение шло между наивным utcnow и aware-дедлайном
[LOG] 2026-09-13 22:28 — Backend Dev: score в ZSET считается через deadline_epoch, а не через .timestamp() наивного значения — абсолютный момент теперь не зависит от TZ контейнера
[LOG] 2026-09-13 22:35 — Backend Dev: проверка в контейнере battle-service — py_compile на обоих файлах OK. Обе формы состояния (+03:00 и наивная) прогнаны через pause / resume / расчёт остатка: исключений нет, remaining одинаковый (3599.8 с), score в ZSET совпадает до секунды (1789336806.0). Новый дедлайн — ровно 24.000000 ч вперёд, tzinfo=None
[LOG] 2026-09-13 22:38 — Backend Dev: подтверждено на живой БД — в существующих строках battle_turns TIMESTAMPDIFF(submitted_at, deadline_at) = 27 ч вместо 24 (тот самый московский сдвиг). После правки будет 24. Уточнение к разделу 2.3: колонка deadline_at живёт в battle_turns, а не в battles
[LOG] 2026-09-13 22:42 — Backend Dev: полный прогон pytest в контейнере — 376 passed. Ни один существующий тест не кодировал старое московское поведение. Временные ключи в Redis удалены, в MySQL ничего не писалось
[LOG] 2026-09-13 22:43 — Backend Dev: задача #9 завершена, изменено 2 файла
[LOG] 2026-09-14 01:05 — QA: начал задачу #10 — тесты часовых поясов дедлайнов в battle-service
[LOG] 2026-09-14 01:20 — QA: написан `tests/test_deadline_timezone.py`, 29 тестов: помощники времени (utc_now / to_naive_utc / parse_deadline / deadline_epoch), новый дедлайн через реальный путь создания боя `_assemble_battle`, запись в `battle_turns.deadline_at` через `crud.write_turn`, пауза и возобновление на обеих формах состояния (legacy +03:00 и наивной)
[LOG] 2026-09-14 01:22 — QA: тотальность parse_deadline проверена на 9 входах — None, пустая строка, пробелы, табы/переводы строк, мусор, невозможная дата, невозможное время, битое смещение: везде None, исключений нет
[LOG] 2026-09-14 01:25 — QA: 27-часовой сдвиг с живой БД закодирован как проверка — разрыв между `submitted_at` (дефолт модели `datetime.utcnow`) и `deadline_at` обязан равняться TURN_TIMEOUT_HOURS, а не TURN_TIMEOUT_HOURS + 3
[LOG] 2026-09-14 01:35 — QA: проверка откатом (в копии /tmp/revert внутри контейнера, репозиторий не трогал). Откат только main.py — 7 падений: `TypeError: can't subtract offset-naive and offset-aware datetimes` на main.py:1609 при паузе (обе формы состояния, мусорная строка, просроченный дедлайн, возобновление после legacy-паузы) и aware-дедлайн `+03:00` при создании боя. Откат обоих файлов — файл вообще не собирается (нет helpers). Копия удалена
[LOG] 2026-09-14 01:40 — QA: прогон в контейнере battle-service — свой файл 29 passed; полный прогон tests/ — 405 passed (было 376, регрессий нет). Реального Redis/MySQL/Mongo тесты не касаются (AsyncMock), ключи `battle:777*` в Redis отсутствуют — чистить нечего
[LOG] 2026-09-14 01:41 — QA: задача #10 завершена, добавлен 1 файл, файлы реализации не изменялись
[LOG] 2026-09-14 02:05 — DevSecOps: начал задачу #11 — проверка TZ и фиксация инварианта «контейнеры в UTC»
[LOG] 2026-09-14 02:08 — DevSecOps: `grep -n "TZ" docker-compose.yml docker-compose.prod.yml` — пусто (exit 1). Расширенная проверка по docker/ и Dockerfile'ам: ENV TZ, монтирования /etc/localtime, default-time-zone отсутствуют. Единственные совпадения — служебные строки `SET TIME_ZONE='+00:00'` внутри дампов mysqldump в docker/mysql/backups/, это артефакты выгрузки, а не конфигурация, и они сами подтверждают UTC. В развёрнутом `docker compose config` (dev и dev+prod) переменной TZ тоже нет — то есть она не приходит и из .env
[LOG] 2026-09-14 02:15 — DevSecOps: инвариант записан в шапку обоих compose-файлов — именно туда полез бы тот, кто решит добавить TZ. Формулировка объясняет последствие, а не запрет: бэкенд отдаёт метки без пояса, клиент читает их как UTC, поэтому заданный TZ молча сдвинет возраст постов, онлайн-статус, кулдауны, таймер хода и игровой календарь — без исключений и без ошибок в логах. В prod-шапке отдельно снят соблазн «поставить TZ=Europe/Moscow, чтобы совпадало с реальным временем»
[LOG] 2026-09-14 02:20 — DevSecOps: добавлен раздел "Time & Timezones" в docs/ARCHITECTURE.md — комментарий в compose виден при правке, но не при чтении архитектуры. Там же расписано, почему колонки DATETIME верны только благодаря UTC, что база станет смесью UTC и местного времени, и как сделать правильно: сначала Stage 2 (бэкенд отдаёт смещение явно), только потом TZ. Отдельно отмечено, что игровой календарь к часовым поясам отношения не имеет
[LOG] 2026-09-14 02:25 — DevSecOps: проверка — `docker compose -f docker-compose.yml config -q` и `-f docker-compose.yml -f docker-compose.prod.yml config -q` обе успешны (exit 0). Изменены только комментарии, ни одной строки конфигурации; исходники, тесты и nginx не трогал
[LOG] 2026-09-14 02:26 — DevSecOps: задача #11 завершена
[LOG] 2026-09-14 03:05 — Reviewer: начал финальную проверку (задачи #12 и #13), все проверки перезапускаю сам, ничего не беру на веру
[LOG] 2026-09-14 03:12 — Reviewer: автоматические проверки — tsc 0 ошибок, npm run build успешно, py_compile на 3 файлах OK, pytest battle-service 405 passed, pytest locations-service 1057 passed (регрессий от соседних фич нет), docker compose config зелёный на обоих файлах
[LOG] 2026-09-14 03:18 — Reviewer: хелпер проверен исполнением на 13 входах при TZ=Europe/Moscow — шесть разных написаний одного момента дают один и тот же таймстемп, строка со смещением повторно не сдвигается, на мусоре и null исключений нет
[LOG] 2026-09-14 03:30 — Reviewer: игровой календарь проверен самостоятельно, а не принят на слово — 20000 выборок прогнаны через новый фронтовый путь в 4 поясах и через бэкендовый compute_game_time, все пять файлов совпали по md5. Старый путь расходится в Нью-Йорке и Сиднее, то есть правка убирает расхождение, а не вносит
[LOG] 2026-09-14 03:35 — Reviewer: круговой обход epoch лосслесный в четырёх поясах на обоих путях (нетронутый ввод и пересериализация). В БД epoch = 2026-01-01 20:00:00, не изменился
[LOG] 2026-09-14 03:40 — Reviewer: обе ловушки закрыты верно — во floatingStructuresSlice поправка применяется ровно один раз, в gameTime.ts epoch и server_time изменены одной правкой
[LOG] 2026-09-14 03:45 — Reviewer: живая проверка на реальных данных — свежий пост читается как «6 ч. назад» во всех поясах, старый разбор давал 9.2 ч в Москве и 2.2 ч в Нью-Йорке. Баг из брифа закрыт
[LOG] 2026-09-14 03:50 — Reviewer: НАЙДЕНА РЕГРЕССИЯ — BattlePage.tsx:298 разбирает runtime.deadline_at голым new Date(). До задачи #9 поле приходило со смещением +03:00 и строка была верной, после нормализации в наивный UTC таймер хода врёт игроку на величину его смещения. Файл не попал ни в один список задач. Отдано Frontend Developer
[LOG] 2026-09-14 03:52 — Reviewer: найдено второе пропущенное место — AdminTicketsPage.tsx:50 (соседний TicketListPage мигрировали, этот забыли). Исправлено самим ревьюером, tsc и build перезапущены, оба зелёные
[LOG] 2026-09-14 03:58 — Reviewer: задача #12 выполнена — из ISSUES.md удалена закрытая запись про относительное время, добавлены HIGH (у ZSET battle:deadlines нет ни одного читателя, таймаут хода не срабатывает сам), MEDIUM (Stage 2, бэкенд без смещений, с перечнем 22 ручных .isoformat()) и LOW (таблица сервисов в CLAUDE.md устарела). В разделах 2.3 и 3.2 фичи исправлено имя таблицы на battle_turns
[LOG] 2026-09-14 04:00 — Reviewer: расширение claude-in-chrome не подключено — ни один шаг не выполнен в настоящем браузере. Что осталось непроверенным, перечислено в разделе 5
[LOG] 2026-09-14 04:02 — Reviewer: проверка завершена, результат FAIL — одна блокирующая правка (#1). Всё остальное проверено и готово к выкату
[LOG] 2026-09-14 09:10 — Frontend Dev: начал задачу #14 — регрессия таймера хода в BattlePage.tsx:298
[LOG] 2026-09-14 09:14 — Frontend Dev: строка переведена на parseServerDate из utils/serverDate. Взял именно parseServerDate, а не serverDateMs: на отсутствующем или битом deadline_at serverDateMs вернёт 0, и обратный отсчёт показал бы дату 1970 года и гигантское прошедшее время. Ветка null теперь явная, timeLeft = 0. Старый код в этом случае давал NaN
[LOG] 2026-09-14 09:25 — Frontend Dev: обе формы deadline_at проверены исполнением, а не рассуждением — хелпер собран esbuild и запущен в контейнере frontend под реальными поясами. Legacy «+03:00» и наивный UTC дают одинаковые 3600 с в Europe/Moscow, America/New_York, Asia/Kathmandu и UTC. Сверено с сервером: parse_deadline и deadline_epoch в контейнере battle-service на тех же строках дают те же 3600 с
[LOG] 2026-09-14 09:27 — Frontend Dev: уточнение к описанию бага в разделе 5 — перекос шёл в обе стороны. Восточнее UTC наивная метка читалась как местная и оказывалась РАНЬШЕ, то есть часовой ход в UTC+3 показывался уже истёкшим (0 с), а западнее, в UTC-4, наоборот раздувался до 18000 с. Игрок терял ход в обоих случаях — просто по-разному
[LOG] 2026-09-14 09:32 — Frontend Dev: прочёсывание на «соседей» — grep по new Date( с аргументом даёт 5 совпадений, ни одного серверного поля: datetime-local в GameTimeAdminPage (там местное время намеренно), два вызова от числа и две строки внутри самого serverDate.ts. Дополнительно проверил Date.parse(, перенос new Date( на следующую строку и dayjs/moment — пусто. Пропусков уровня AdminTicketsPage больше нет
[LOG] 2026-09-14 09:40 — Frontend Dev: проверки в контейнере frontend — npx tsc --noEmit exit 0, npm run build exit 0 (built in 47.80s). Тронут один файл, стили и .jsx не затронуты
[LOG] 2026-09-14 09:41 — Frontend Dev: задача #14 завершена, готово к повторному ревью
[LOG] 2026-09-14 11:00 — Reviewer: начал ревью #2. Все проверки перезапускаю с нуля, ни одной цифры из ревью #1 и из логов разработчиков не переношу
[LOG] 2026-09-14 11:08 — Reviewer: автоматические проверки — tsc exit 0, npm run build exit 0 (built in 46.62s), py_compile на main.py, redis_state.py и test_deadline_timezone.py OK, pytest battle-service 405 passed, pytest locations-service 1057 passed, docker compose config зелёный на обоих файлах
[LOG] 2026-09-14 11:20 — Reviewer: правка #14 проверена исполнением, а не чтением — serverDate.ts собран esbuild и запущен в контейнере frontend под пятью реальными поясами. Три написания одного дедлайна дают 3600 с везде. Старый код на наивной метке давал 0 с в Москве, Катманду и Сиднее и 18000 с в Нью-Йорке
[LOG] 2026-09-14 11:22 — Reviewer: подтверждаю поправку Frontend Dev к формулировке ревью #1 — перекос действительно шёл в обратную сторону. Восточнее UTC таймер шёл КОРОЧЕ (часовой ход показывался истёкшим), западнее — длиннее. В ревью #1 направление было указано неверно
[LOG] 2026-09-14 11:25 — Reviewer: сверено с арифметикой самого сервера — parse_deadline и deadline_epoch в контейнере battle-service на тех же строках дают epoch 1789390800, ровно то же значение, что и клиент. Совпадает не только длительность, но и абсолютный момент
[LOG] 2026-09-14 11:27 — Reviewer: отсутствующий и битый deadline_at даёт 0, а не NaN и не 1970 год — проверено на null, undefined, пустой строке, мусоре и заведомо неверной дате во всех пяти поясах
[LOG] 2026-09-14 11:35 — Reviewer: прочёсывание перезапустил сам, а не принял на слово — именно так и появился этот дефект. grep по new Date( с аргументом даёт 5 совпадений, ни одного серверного поля. Дополнительно проверил Date.parse(, перенос new Date( на следующую строку, dayjs/moment, Date( без new, split('T') и slice(0,10) по датам, а также toISOString() — 16 совпадений, все от new Date() с настоящим Z. Пропусков уровня AdminTicketsPage не осталось
[LOG] 2026-09-14 11:45 — Reviewer: перепроверил всё, под чем поменялись файлы — хелпер по-прежнему терпим к смещению (регулярка привязана к концу строки), локальных formatRelativeTime и трёх старых костылей нет ни одного, gameTime.ts меняет обе метки одной правкой, круговой обход epoch лосслесный в пяти поясах, epoch в БД не изменился, во floatingStructuresSlice поправка применяется ровно один раз
[LOG] 2026-09-14 11:50 — Reviewer: игровой календарь пересчитан заново — 20000 выборок через новый фронтовый путь в пяти поясах и через бэкендовый compute_game_time, все шесть md5 совпали (6f52c1a1...). Живая сверка: сервер отдаёт 1787 imbolc, клиент считает то же
[LOG] 2026-09-14 11:55 — Reviewer: плавающие структуры проверены на живых данных («Цитадель», started_at 2026-07-31, скорость 1.28601e-07) — прогресс старого и нового кода совпадает до нуля (delta 0.000e+0) в четырёх поясах, то есть позиции на карте не сдвинулись
[LOG] 2026-09-14 12:00 — Reviewer: раздел 3.7 чистый — ни одного .css/.scss в диффе, единственный .js это helpers.js и там только удаление 13 строк без единой добавленной, .jsx не тронуты, React.FC нигде в сигнатурах
[LOG] 2026-09-14 12:05 — Reviewer: исходный баг перепроверен на живой ленте — свежий пост читается как «6 часов назад» во всех поясах, старый разбор давал 9.62 ч в Москве и 2.62 ч в Нью-Йорке. Онлайн-статус и разделители дней в мессенджере тоже считаются верно
[LOG] 2026-09-14 12:08 — Reviewer: сам поправил docs/ARCHITECTURE.md — команда проверки инварианта (grep -n "TZ" по compose-файлам) стала ложной внутри этой же фичи: задача #11 добавила туда восемь предупреждающих комментариев со словом TZ, и наивный grep теперь выводит их. Заменил на grep по присваиванию переменной, exit 1. Только документация
[LOG] 2026-09-14 12:10 — Reviewer: расширение claude-in-chrome по-прежнему не подключено — ни один шаг не выполнен в настоящем браузере. Шесть пунктов ручной проверки перечислены в разделе 5, PM надо передать их пользователю
[LOG] 2026-09-14 12:12 — Reviewer: ревью #2 завершено, результат PASS. Новых замечаний нет, фича готова к выкату
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

Бэкенды отдают время **без часового пояса**, контейнеры работают в UTC, а браузер такую строку
читает как **местное время**. Всё серверное время в игре было смещено ровно на часовой пояс игрока.

Симптом, с которого начали, — пост трёхчасовой давности показывался как «только что». Масштаб
оказался другим: **~55 мест разбора дат в ~45 файлах**, **пять копий** функции «сколько времени
назад» и **три** самописных костыля, один из которых был сломан — дописывал `Z` всегда и на данных
с поясом выдавал `NaN.NaN.NaN NaN:NaN` прямо в логе боя.

Сделана общая функция разбора, **терпимая к обоим форматам**: строку с `Z`, `+03:00` или `-05:00`
она не трогает, а дописывает пояс только по-настоящему «голой». У `battle-service` одно и то же
поле приходит то с поясом, то без, и наивное «всегда дописывать Z» сломало бы таймер хода.

### Что оказалось не косметикой

- **Кулдаун перехода врал на три часа.** Клиент показывал ноль, игрок жал переход и получал отказ
  сервера. Проверено измерением; теперь совпадает до миллисекунды.
- **Сообщения попадали под разделитель «Вчера»**, хотя отправлены сегодня.
- **Админка игрового времени портила данные при каждом сохранении** — читала эпоху без пояса, а
  записывала с ним, сдвигая на три часа назад. Теперь круговорот точный до байта, проверено в
  четырёх поясах против живой базы.
- **`battle_turns.deadline_at` хранился в московском времени** при UTC во всей остальной базе:
  на живых строках между ходом и дедлайном **27 часов вместо 24**.
- **Скрытая 500-я в боях** — вычитание времени с поясом из времени без пояса роняло паузу.

### Игровой календарь

Работал **по случайности**: точка отсчёта и текущее время разбирались одинаково неправильно, и
ошибки сокращались. Обе правки сделаны одной неделимой задачей — починка одной сдвинула бы
календарь у всех.

Проверено прогоном **20 000 значений по шести поясам** со сверкой против серверного алгоритма.
Новый путь совпадает с сервером везде. Старый — **не везде**: в поясах с переходом на летнее время
точка отсчёта (январь) и текущий момент (сентябрь) имеют разные смещения, сокращение не
срабатывало, и календарь уезжал на границе суток. Фикс убрал существовавшее расхождение.

Виджет перестал прыгать через минуту после загрузки: при UTC+3 это случалось в 3.5% загрузок,
в Сиднее — в 12.5%, теперь 0%.

### Что изменилось от первоначального плана

- **Бэкенд решено не трогать** (кроме боёв): 22 места пишут время вручную мимо Pydantic, плюс
  ~160 конфигов схем. Отложено. Клиент сделан терпимым к обоим форматам **именно затем**, чтобы
  будущая правка бэкенда прошла безопасно при выкате по одному контейнеру.
- **Первое ревью вернуло FAIL** — регрессия, внесённая самой фичей: нормализация дедлайнов сломала
  разбор на странице боя, который раньше был верным. Файл упоминался в анализе, но не попал ни в
  один список задач. Починено, фронтенд прочёсан заново дважды разными агентами.
- Инвариант «контейнеры работают в UTC» записан в оба compose-файла и в `ARCHITECTURE.md` — весь
  фикс на нём держится, а раньше он не был зафиксирован нигде.

### Проверка

- `battle-service` — 405 тестов (было 376), `locations-service` — 1057. Сборки фронта зелёные.
- Тесты на дедлайны проверены откатом: старый код валит 7 тестов настоящей ошибкой
  `TypeError: can't subtract offset-naive and offset-aware`.
- На живых данных: пост возрастом 6.6 часа показывает «6 часов назад» **в любом поясе**; раньше —
  9.6 часа в Москве и 2.6 в Нью-Йорке.

### Оставшиеся риски / follow-up

- **В браузере ничего не проверялось** — расширение Chrome не подключено. Проверить руками:
  консоль, подписи времени в ленте, разделители и значки «в сети» в мессенджере, виджет игрового
  времени через минуту после загрузки, счётчик хода в бою (в старом и новом бою) и положение
  плавающих структур на карте.
- **HIGH в `ISSUES.md`: очередь дедлайнов в Redis никем не читается.** Таймаут хода не срабатывает
  никогда — бой с ушедшим игроком висит бесконечно, множество в Redis растёт без ограничения.
- **MEDIUM: бэкенд должен отдавать время с поясом** — 22 ручных места, ~160 конфигов схем.
- **LOW: таблица сервисов в CLAUDE.md устарела** — `dungeon-service`, `battle-pass-service`,
  `party-service` работают, но не перечислены.
- Эпоха на проде — `2026-01-01 20:00:00`. Дальнейший сдвиг остановлен, но прошлые сохранения уже
  уехали (каждое на три часа назад). Нужное значение придётся выставить вручную, один раз.

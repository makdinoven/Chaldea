# FEAT-129: Bugfix — gathering countdown 00:00 + сессия не завершается

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-04-25 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Bugfix follow-up to FEAT-128 (DONE). On completion: rename to `DONE-FEAT-129-fix-gathering-countdown-and-finalize.md`.

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание

После релиза FEAT-128 пользователь сообщил два связанных симптома при попытке начать добычу на локации:

1. **Баннер показывает обратный отсчёт `00:00` сразу после старта добычи** — вместо настоящего времени до завершения сессии (например, 24:55 для 5-стаминовой ноды). Скриншот: «⚠ Идёт добыча: осталось 00:00».
2. **Сессия не завершается лениво** — даже после ожидания, добыча не финализируется, ресурс не падает в инвентарь, баннер не исчезает.

Эти два симптома вероятно связаны: если сервер вычисляет `complete_at` некорректно (например, равно `started_at`), то клиент сразу показывает 0 секунд, и lazy-finalize на следующих запросах ничего не делает (или делает мгновенно — но при этом ресурс не появляется и сессия живёт).

### Гипотезы (не для агентов — для контекста)

- **A.** Бэкенд устанавливает `complete_at = started_at` (effective_seconds=0), хотя минимум по формуле 30s — баг в формуле или в передаче.
- **B.** Бэкенд считает правильно, но клиент парсит `complete_at` как локальное время вместо UTC → отрицательная дельта → 00:00.
- **C.** Поле `complete_at` теряется по пути (slice не сохраняет, или поле не возвращается из start endpoint).
- **D.** Lazy-finalize на сервере не вызывается на этом пути — например, `client/details` его не дёргает для нового потока.

Аналитик должен проверить все четыре.

### UX / Пользовательский сценарий (текущий, баговый)

1. Игрок жмёт «Добыть» → выбирает инструмент → подтверждает.
2. Баннер появляется, но обратный отсчёт сразу `00:00`.
3. Игрок ждёт минуту, пять минут, час — ничего не меняется, ресурс не падает в инвентарь, кнопка «Отменить» работает (возвращает 50% стамины), но без отмены добыча застывает.

### UX / Пользовательский сценарий (ожидаемый)

1. После подтверждения баннер показывает корректный обратный отсчёт (например, 24:55, потом 24:54...).
2. По истечении времени lazy-finalize при следующем поллe (`GET active_gathering` или `GET client/details`): банк ноды уменьшается, ресурс в инвентаре, опыт в навыке, баннер сменяется на toast «Добыто N руды (+N опыта)».

### Связанные файлы (вероятно)

- Backend: `services/locations-service/app/crud.py::start_gathering`, `_compute_effective_gather_params`, `_finalize_one_session`, `finalize_due_sessions`
- Backend: `services/locations-service/app/main.py` — start endpoint и poll endpoint
- Frontend: `services/frontend/app-chaldea/src/hooks/useGatheringLock.ts`, `redux/slices/gatheringSlice.ts`, `api/gatheringApi.ts`
- Frontend: `services/frontend/app-chaldea/src/components/CommonComponents/GatheringLockBanner.tsx`

### Edge cases

- Если ноду уже истощили в момент старта — должно быть 400 «Истощена», а не 0-секундная сессия.
- Если стамина по формуле даёт 0 секунд — формула 3.6 имеет `max(effective_seconds, 30)`, проверить что floor работает.
- Часовые пояса: бэкенд может возвращать `complete_at` без таймзоны, фронт интерпретирует как локальное → расхождение.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### TL;DR

**Single root cause: timezone-naive `complete_at` returned from the poll endpoint.** Hypothesis B in the brief is correct. Hypotheses A, C, D are NOT the cause — backend math, schema field, and lazy-finalize wiring are all correct. The poll path `GET /locations/characters/{cid}/active_gathering` echoes `row.complete_at` straight from MySQL, which is a naive `datetime`. Pydantic v1 serialises naive datetimes as `"2026-04-25T10:26:00"` (no `Z`/offset). Browser `Date.parse` then interprets that as **local time**, which for a user east of UTC produces a parsed instant that is already in the past relative to `Date.now()` — so `remainingSeconds` clamps to 0 and the banner reads `00:00`.

### Trace — backend side

#### 1. Formula (`crud.py:5388-5436`)

`_compute_effective_gather_params(base_stamina=5, has_tool=False, rank_bonuses={}, tool_bonuses={})`:
- `base_seconds = 5 * 5 * 60 = 1500`
- `speed_total_pct = 0`; `seconds = floor(1500 * 1.0) = 1500`
- `not has_tool`: `seconds = 1500 * 2 = 3000`
- `seconds = max(3000, 30) = 3000`
- Returns `effective_seconds = 3000` ✅ matches FEAT-128 §3.6.

Hypothesis A is FALSE. Formula returns 3000s as expected.

#### 2. Session insert (`crud.py:5691-5707`)

```python
started_at_py = datetime.now(timezone.utc)                       # AWARE UTC
complete_at_py = started_at_py + timedelta(seconds=int(eff["effective_seconds"]))
new_session = GatheringSession(
    started_at=started_at_py,
    complete_at=complete_at_py,
    ...
)
```

`complete_at` is correctly stored as `started_at + 3000s`. The model column is `TIMESTAMP NOT NULL` (`models.py:590`) — a naive type from MySQL's perspective; aiomysql persists the UTC instant correctly. ✅

#### 3. Start response (`crud.py:5774`, route `main.py:3099-3134`)

The dict returned by `start_gathering` puts the **Python aware** datetime `complete_at_py` into the payload. Pydantic v1's default JSON encoder calls `.isoformat()`, producing `"2026-04-25T10:26:00+00:00"` — browser parses this correctly as UTC. ✅ The banner countdown briefly works after the start request… until the first poll fires.

#### 4. Poll response — **THE BUG** (`crud.py:6064-6101`)

```python
# Line 6085 — local var IS made aware (used only for server-side maths):
complete_at = _ensure_aware_utc(row.complete_at)
...
# Line 6101 — but the response payload uses the RAW row value:
"complete_at": row.complete_at,
```

`row.complete_at` is the value aiomysql returns for the `TIMESTAMP` column: a **naive** `datetime` (no tzinfo). Pydantic v1 then serialises it as `"2026-04-25T10:26:00.000000"` — no offset, no `Z`. The `_ensure_aware_utc` helper is only used to compute `remaining_seconds` server-side; the wire payload bypasses it.

`remaining_seconds` server-side IS computed correctly (line 6088-6090, both sides aware) — but the frontend ignores it (see step 7 below).

#### 5. Lazy-finalize wiring

- `main.py:790-791` — `client/details` calls `finalize_due_sessions` ✅
- `main.py:3242` (via `crud.get_active_gathering_for_character` line 6050) — poll endpoint calls it ✅
- `finalize_due_sessions` (`crud.py:4662-4742`) compares `complete_at <= NOW()` in **MySQL** (server-side, both naive in the same zone) — this is correct and unaffected by the wire bug.

Hypothesis D is FALSE. Once the server's wall-clock catches up to `complete_at`, finalize runs and commits.

### Trace — frontend side

#### 6. Redux slice (`gatheringSlice.ts:311-335` and `:360-374`)

- On `startGathering.fulfilled`: synthesises `activeSession.complete_at = r.complete_at` — string from start response (has offset, parses fine).
- On `loadActiveGathering.fulfilled`: `state.activeSession = payload` — wholesale overwrite with the poll payload, which has the **naive** `complete_at` string.

So `activeSession.complete_at` flips from "valid UTC string" to "naive string interpreted as local" the moment the first poll resolves.

#### 7. `useGatheringLock.ts:38-43`

```ts
const completeMs = Date.parse(completeAt);
return Math.max(0, Math.floor((completeMs - Date.now()) / 1000));
```

`Date.parse("2026-04-25T10:26:00")` (no Z) → browser interprets as **local**. For a player in MSK (UTC+3), that local 10:26 = 07:26 UTC. If `Date.now()` is currently around 10:01 UTC, the delta is `-2.5h` → clamped to 0. Banner shows `00:00`. The hook never reads server-computed `remaining_seconds`; it relies entirely on parsing `complete_at`.

The `useEffect` on `[completeAt]` (`:99-114`) re-runs the same broken parse every second.

### Symptom mapping — single root cause, both symptoms

1. **Banner shows 00:00** — directly caused by the naive-datetime parse in `useGatheringLock`. Briefly correct after `startGathering.fulfilled` (offset present), then permanently 00:00 after the first poll (~10s, often <1s if isGathering flips and effect dispatches immediately).
2. **"Never auto-finalizes"** — *this is a perception bug*, not a real one. Finalize DOES run server-side once the real `complete_at` (UTC) elapses. With a 5-stamina no-tool node that's 50 minutes away. The user sees `00:00` from second one and assumes finalize is broken; in reality they would need to keep the page open until real-UTC + 50 min for the next poll to pick up the toast. With a UTC+3 client, the user-perceived "wait an hour" is 60 min real time, which IS enough — but if they cancel before then (because UI looks stuck), it never reaches finalize. **No separate fix needed** for symptom #2; fixing the timezone serialization makes the countdown honest, and finalize will visibly trigger at the right moment.

(Caveat: if a player keeps the page open continuously past real `complete_at` and still no toast appears, that would be a separate bug. Current evidence in the brief is consistent with the perception explanation — user sees 00:00 immediately and waits "минуту, пять минут, час" — these are below the actual 50-min finalize horizon for 5-stamina nodes, except the "час" case which is borderline.)

### Fix recommendation

**Single-line server fix** in `services/locations-service/app/crud.py`:

- **Line 6101** in `get_active_gathering_for_character`: change

  ```python
  "complete_at": row.complete_at,
  ```

  to

  ```python
  "complete_at": _ensure_aware_utc(row.complete_at),
  ```

  And similarly **line 6100**:

  ```python
  "started_at": _ensure_aware_utc(row.started_at),
  ```

That's it. The local variable `complete_at` is already computed correctly on line 6085 — the dict just needs to use it (or call `_ensure_aware_utc` inline). With aware datetimes, Pydantic v1 emits `+00:00`, and `Date.parse` on the frontend yields the correct UTC instant.

**Verification after fix:**
- Curl the poll endpoint: `complete_at` field MUST end with `+00:00` (or `Z` if a JSON encoder normalises it).
- Frontend banner counts down from real remaining time (e.g. `49:53` for a fresh 5-stamina no-tool gather).
- Wait for `complete_at`; next poll returns `active=false` with `last_finished_session` populated; toast renders.

**Optional hardening (not strictly required):**
- Audit `ActiveGatherer` (`schemas.py:1442-1450`) used inside `client/details`. The same naive-datetime issue may be present in `_fetch_active_sessions_for_nodes` (`crud.py:5018-5045`) where `complete_at` is also surfaced for "other players' active sessions on a node". Verify whether that field is used by frontend countdowns; if so, apply the same `_ensure_aware_utc` treatment. Search shows `crud.py:5045` returns `"complete_at": row.complete_at` raw — same bug, lower-impact path.
- Consider switching `models.GatheringSession.complete_at` / `started_at` columns to `DateTime(timezone=True)` for a more durable fix; that's a wider change and out of scope here.

### Risks of the recommended fix

- **None for the wire format.** Going from `"2026-04-25T10:26:00"` to `"2026-04-25T10:26:00+00:00"` is a strict superset — the frontend's `Date.parse` handles both correctly (the offset version is just unambiguous).
- **No DB migration needed.** Column type unchanged, only the runtime serialisation.
- **No cross-service ripple.** No other service consumes the poll endpoint (it's player-facing only). `last_finished_session` already contains a `result_item_name` etc. but no datetime fields; unaffected.

### Confidence

**HIGH** — I traced from formula (correct) → DB write (correct) → poll read (naive string returned) → frontend parse (`Date.parse` without offset = local time) → `Math.max(0, negative) = 0`. All four hypotheses tested against code. The bug surfaces because the poll path uses `row.complete_at` directly (line 6101) while the start path uses `complete_at_py` (line 5774, aware). The two endpoints disagree on tz format — one of FastAPI's classic naive-datetime traps.

### Questions for PM

None — fix is unambiguous.

---

## 3. Tasks (filled by PM after analysis — in English)

### Task 1 — Backend: timezone-aware datetimes in gathering payloads — DONE

**Owner:** Backend Developer
**Status:** DONE
**Files:** `services/locations-service/app/crud.py`

Wrap `started_at` and `complete_at` with the existing `_ensure_aware_utc(...)` helper at the two response-builder sites identified by the Analyst, so Pydantic v1 emits ISO strings with `+00:00` and the browser parses them as UTC.

- `get_active_gathering_for_character` (around lines 6100-6101) — fixes the poll endpoint that drives the banner countdown. Without this fix, the first poll after start replaces the (correct) start-response `complete_at` with a naive string, the hook's `Date.parse` reads it as local time, and the countdown clamps to `00:00`.
- `_fetch_active_sessions_for_nodes` (around line 5045) — fixes the same naive-datetime leak for "other players gathering on this node" inside `client/details.gathering_nodes[].active_sessions[]`.

`last_finished_session` block contains no datetime fields, so no change there. `_ensure_aware_utc` itself is untouched. No DB migration. No frontend change.

**Verification:** `python -m py_compile app/crud.py` OK; `pytest tests/test_gathering.py` 72/72 PASS.

---

## 4. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-04-25
**Result:** PASS

All checks passed. The 4-line surgical fix is correctly applied at the two sites identified by the Analyst. Changes are ready for completion.

#### Automated Check Results
- [x] `py_compile services/locations-service/app/crud.py` — PASS
- [x] `pytest tests/test_gathering.py` (in `locations-service` container) — PASS, 72/72
- [ ] `npx tsc --noEmit` — N/A (no frontend changes)
- [ ] `npm run build` — N/A (no frontend changes)
- [ ] `docker-compose config` — N/A (no compose / nginx changes)
- [x] Live verification — STATIC REVIEW ONLY. The poll endpoint is JWT-protected (401 without auth), and per assignment ("If you can't do live, document this as 'static review only'") I did not bootstrap a token. The unit tests cover the response builder; the helper is trivially correct.

#### Diff scope confirmation
Inside `crud.py`, the only changes touching the two functions named in section 3 are:
- `_fetch_active_sessions_for_nodes` (`crud.py:5044-5045`) — `started_at` and `complete_at` wrapped in `_ensure_aware_utc(...)`.
- `get_active_gathering_for_character` (`crud.py:6100-6101`) — same wrap.

The wider `crud.py` diff also contains the entire FEAT-128 gathering implementation (still uncommitted in the working tree) — that is pre-existing and not part of FEAT-129. Nothing else got smuggled in by Backend Dev for this fix specifically.

#### Helper sanity check (`crud.py:4515-4521`)
```python
def _ensure_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None: return None
    if dt.tzinfo is None: return dt.replace(tzinfo=timezone.utc)
    return dt
```
Correct: passes `None` through, attaches UTC to naive, leaves aware values alone. Matches the contract used by `lazy_restore_depleted_nodes` and the `start_gathering` "bank not exhausted" check (`crud.py:5610`).

#### Standards
- [x] Pydantic <2.0 — unchanged
- [x] Sync/async — unchanged (locations-service is async)
- [x] No new SCSS / no `.jsx` migration needed (backend-only fix)
- [x] No `React.FC` (backend-only fix)
- [x] No new secrets / hardcoded URLs
- [x] No Alembic migration needed (no schema change)

#### QA Coverage
Backend code was modified. Existing `test_gathering.py` covers the affected response builders (72 tests, all green). Backend Dev did not add a new tz-specific assertion; that's acceptable for a fix this small — the existing tests at minimum prove no regression. Optional non-blocking improvement: a focused assertion that `started_at`/`complete_at` in poll JSON have `tzinfo is not None` would lock the contract. Logged here, not required for PASS.

#### Non-blocking observations / follow-ups
1. **Same naive-datetime pattern still leaks for `depleted_at` / `restore_at` in `client/details.gathering_nodes[]`** (`crud.py:5174-5175`). The frontend `GatheringNodeCard.tsx:74` does `Date.parse(node.restore_at)` for a live MM:SS countdown until restore — this is the same `Date.parse` pitfall the analyst diagnosed for `complete_at`. Once a node depletes, players in non-UTC timezones will see the same `00:00`-style miscount on the restore countdown. The Analyst flagged this hardening as "optional / lower-impact"; the live `Date.parse` consumption shows it's actually the same severity, just on a less common code path (only triggers after a node is fully depleted). Recommend a tiny follow-up FEAT or amendment that wraps lines 5174-5175 (and admin-side 4352-4353 for consistency) in `_ensure_aware_utc(...)`. NOT blocking FEAT-129 since (a) it's a separate symptom the user did not report, (b) it shipped naive in FEAT-128 and is unchanged by this PR.
2. `last_finished_session` block (`crud.py:6118-6135` area) genuinely contains no datetime fields — Analyst was correct, verified.
3. `models.GatheringSession.complete_at` / `started_at` are still `TIMESTAMP` (naive). A future hardening pass could move them to `DateTime(timezone=True)` so the Python wire layer doesn't need to defensively wrap. Out of scope here.

---

## 5. Logging (filled by all agents — in Russian)

```
[LOG] 2026-04-25 — PM: создан багфикс FEAT-129 после жалобы пользователя на 00:00 в баннере и зависание сессии. Запускаю Codebase Analyst.
[LOG] 2026-04-25 — Analyst: начал анализ FEAT-129, проследил путь данных start→DB→poll→hook.
[LOG] 2026-04-25 — Analyst: анализ завершён. Корневая причина — гипотеза B (наивный datetime в poll-ответе). Файл services/locations-service/app/crud.py, строки 6100-6101 (get_active_gathering_for_character) — payload отдаёт row.complete_at и row.started_at сырыми, без _ensure_aware_utc. Pydantic v1 сериализует наивный datetime без `+00:00`, браузерный Date.parse трактует строку как локальное время → отрицательная дельта → 00:00. Симптом «не финализируется» — производный от первого: пользователь видит 00:00 сразу, реальное серверное время до завершения 50 мин. Рекомендованный фикс — обернуть оба поля в _ensure_aware_utc(...) (две строки). Также возможна та же проблема в crud.py:5045 (_fetch_active_sessions_for_nodes) — отдельный путь, аналогичный фикс по желанию.
[LOG] 2026-04-25 — Backend Dev: начал FIX FEAT-129 — таймзоны в poll и client/details.active_sessions.
[LOG] 2026-04-25 — Backend Dev: FIX завершён. _ensure_aware_utc применён к started_at/complete_at в get_active_gathering_for_character (crud.py:6100-6101) и _fetch_active_sessions_for_nodes (crud.py:5044-5045). Блок last_finished_session datetime-полей не содержит — без изменений. Тесты: 72/72 PASS.
[LOG] 2026-04-25 17:42 — Reviewer: проверка FEAT-129 завершена, результат PASS. Тесты 72/72, py_compile OK, фикс точечный (4 строки в двух функциях, helper применён корректно). Замечен сопутствующий tz-naive-leak для depleted_at/restore_at в client/details.gathering_nodes[] (crud.py:5174-5175) — фронт делает Date.parse(node.restore_at) для отсчёта до восстановления ноды (GatheringNodeCard.tsx:74), та же ловушка что и с complete_at. Не блокирует FEAT-129 (это отдельный симптом, унаследован из FEAT-128), оформлен как нерелейзный follow-up в Section 4.
[LOG] 2026-04-25 18:35 — Backend Dev: добил оставшиеся naive datetimes — depleted_at/restore_at в client/details (crud.py:5174-5175) и в admin-payload (_serialize_gathering_node, crud.py:4352-4353), плюс заодно created_at/updated_at в admin-сериализаторе (crud.py:4355-4356) — те же gathering-respons-ы. Прочие *_at в gathering-путях уже завернуты (start_gathering — aware-now(), _fetch_active_sessions_for_nodes — wrap в FEAT-129 #1, get_active_gathering — wrap в FEAT-129 #1). Тесты 72/72 PASS.
```

---

## 6. Completion Summary (filled by PM on close — in Russian)

### Что сделано

Исправлен баг с обратным отсчётом добычи на фронте.

**Корневая причина:** Бэкенд (`locations-service`) возвращал `complete_at`/`started_at` как timezone-naive `datetime` из MySQL `TIMESTAMP` колонок. Pydantic v1 сериализовал их без таймзоны (`"2026-04-25T10:26:00"`), фронтенд `Date.parse(...)` интерпретировал такие строки как **локальное время**, давая отрицательную дельту → баннер сразу показывал `00:00`. На сервере финализация работала корректно (по MySQL `NOW()`), но игроку не было видно, когда это произойдёт.

**Применённый fix** — обернул в `_ensure_aware_utc(...)` все datetime-поля в response builder'ах для добычи в `services/locations-service/app/crud.py`:

| Локация | Поля |
|---|---|
| `_fetch_active_sessions_for_nodes` (~5044-5045) | `started_at`, `complete_at` (другие игроки на ноде в `client/details`) |
| `get_active_gathering_for_character` (~6100-6101) | `started_at`, `complete_at` (poll endpoint — основной баг) |
| `gathering_nodes[]` в client/details (~5174-5175) | `depleted_at`, `restore_at` (счётчик восстановления для депльтнутых нод) |
| `_serialize_gathering_node` admin (~4352-4353) | `depleted_at`, `restore_at` |
| `_serialize_gathering_node` admin (~4355-4356) | `created_at`, `updated_at` (для консистентности) |

Frontend, базовые формулы, инсёрт сессии — не тронуты, они изначально работали правильно (`datetime.now(timezone.utc)` на старте сессии).

**Тесты:** 72/72 PASS в `services/locations-service/app/tests/test_gathering.py` после fix.

### Как проверить

1. Зайти на локацию с активной нодой → начать добычу.
2. Баннер «Идёт добыча: осталось MM:SS» должен показывать корректное время и считать вниз.
3. По истечении времени lazy-finalize отработает на следующем `client/details` или `active_gathering` поллe — ресурс упадёт в инвентарь, баннер сменится на toast.
4. Истощить ноду → счётчик «Восстановится через MM:SS» в карточке должен показывать корректное время восстановления.

### Оставшиеся риски

- В других сервисах могут быть аналогичные tz-naive проблемы для других datetime-полей (за пределами этой фичи). Не сканировал — это вопрос проектной гигиены, отдельная задача.
- Frontend `Date.parse` без таймзоны — общая ловушка JS. Долгосрочно стоит унифицировать датавремя на фронте через `new Date(ms)` от бэкенда или явный парсер ISO с UTC. Тоже отдельная задача.

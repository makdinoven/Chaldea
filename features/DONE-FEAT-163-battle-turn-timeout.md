# FEAT-163: Таймаут хода в боях не срабатывает

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-14 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
`TURN_TIMEOUT_HOURS` (24 часа) сейчас декоративен. Дедлайн хода вычисляется и пишется
**в три места** — состояние Redis, отсортированное множество `battle:deadlines` и таблицу
`battle_turns` — и **не читается на предмет истечения ни одним из них**.

Проверено экспериментом (не рассуждением): бой создан, дедлайн состарен на час назад.
- 5.5 минут — ничего не произошло. Расписание Celery на живом контейнере пустое (`entries → {}`).
- Ход просроченным участником — **принят как обычно**, 200, назначен свежий дедлайн на 24 часа.

Косвенное подтверждение исходного замысла: статус `forfeit` существует в перечне и **проверяется**
в двух местах, но **не присваивается нигде**.

### Чем это грозит
Зависший бой блокирует **обоих** участников — и ушедшего, и его противника:
- нельзя покинуть локацию и нельзя собирать ресурсы;
- нельзя писать ролевые посты в локации;
- заблокированы **двенадцать** операций с инвентарём (экипировка, крафт, заточка, эссенции,
  трансмутация, камни, переплавка, опознание, использование предметов);
- нельзя начать новый бой и принять приглашение;
- в интерфейсе постоянная блокировка с баннером «Вернуться к бою».

Единственный выход сегодня — админ вручную через принудительное завершение боя.

Плюс утечка: при передаче хода запись предыдущего игрока из множества **не удаляется** —
множество растёт и никогда не чистится. Хуже того, после истечения состояния боя в Redis (48 часов)
даже принудительное завершение не сможет перечислить участников, и записи останутся навсегда.

### Бизнес-правила
- **Просрочил ход — выбываешь из боя.** Не пропуск хода: пропуск не решает исходную проблему,
  потому что при двух ушедших игроках ход передавался бы бесконечно и блокировка не снялась бы
  никогда.
- **Бой один на один:** выбывание просрочившего = его поражение, бой завершён.
- **Командный бой:** выбывает **только просрочивший**, остальные доигрывают своим составом.
  Один ушедший не должен наказывать союзников, которые ни при чём.
- **24 часа на ход остаются.** Обоснование пользователя: это фактически одни реальные сутки —
  человек должен успеть поспать и отработать день. Меньший срок наказывал бы за наличие работы.
  Но значение **выносится в настройку** (переменная окружения в обоих compose-файлах), чтобы
  менялось без правки кода — сейчас оно зашито прямо в коде.
- **Уборка множества:** при передаче хода запись предыдущего участника удаляется.

### UX / Пользовательский сценарий
1. Игрок не ходит сутки.
2. Система засчитывает ему выбывание.
3. Бой один на один — завершён, победа противнику. Командный — бой продолжается без выбывшего.
4. Обоим участникам снимается блокировка (или всем, если бой завершился).

### Edge Cases
- Бой на паузе — дедлайн не должен течь, пока бой стоит.
- Оба участника просрочили (возможно, если сервер лежал) — обработка не должна зависеть от порядка.
- Бой уже завершён, а запись в множестве осталась — обработчик должен её просто убрать.
- Состояние боя в Redis истекло (48 часов), а бой в базе всё ещё `in_progress` — участников
  перечислить неоткуда; надо решить на проектировании.
- Повторный проход обработчика по тому же бою не должен засчитать выбывание дважды.
- Командный бой, где выбыл последний участник команды — команда проиграла.
- Выбывание должно корректно снять блокировку, иначе чиним симптом и оставляем причину.

### Вопросы к пользователю
- [x] Пропуск хода или поражение? → **Выбывание просрочившего.**
- [x] Командный бой — вся команда или один? → **Выбывает только просрочивший, остальные играют.**
- [x] Уменьшать ли 24 часа? → **Нет.** Есть ночь и рабочий день; меньший срок бессмысленен.
      Вынести в настройку.
- [ ] Идея пользователя на будущее: «либо придумать другую логику для ночи» — возможно, не считать
      ночные часы. Не в объёме этой фичи, но зафиксировано.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Verified by a read-only investigation plus a live experiment (2026-09-14):

**Three write-only sinks.** Redis `battle:{id}:state.deadline_at` (`redis_state.py:186`,
`main.py:2816`, `:1665`) — echoed to clients (`main.py:1263,1353,1438,4576`) and compared exactly
once, on pause (`:1608-1609`). Redis ZSET `battle:deadlines` (`redis_state.py:227`,
`main.py:2826`, `:1672`) — **no reader**; only `zrem` at `:1617, 2554, 3909`.
MySQL `battle_turns.deadline_at` (`crud.py:56` via `crud.write_turn`) — the table is **never
SELECTed anywhere in the repo**.

**No sweeper, confirmed four ways.** No `zrangebyscore`/`zpopmin` anywhere (the one `zrange`,
`redis_state.py:251`, is a different key). Celery defines one task, `save_log` (`tasks.py:12`),
and sets no `beat_schedule` (`tasks.py:9`) — the live `celery-beat` shelve reads `entries → {}`
and its logs have no "Sending due task" lines. The only startup `asyncio.create_task`
(`main.py:4648`) is a WS fan-out subscriber; autobattle-service's loop is pub/sub only. No cron
anywhere.

**No lazy check.** `get_state` (`main.py:1307`), `get_state_internal` (`:1247`),
`_make_action_core` (`:1722`, validations at `:1734-1799`) and `battle_websocket` (`:4468`) are
all deadline-blind. The frontend clamps at zero (`BattlePage.tsx:309-312`) and does nothing.

**`BattleStatus.forfeit`** (`models.py:17`, migration `001_initial_baseline.py:32`) is read at
`main.py:3863, 4104` and **assigned nowhere** — the likely intended terminal state.

**The lock is a status test** — `b.status IN ('pending','in_progress')`
(`locations-service/app/main.py:129-141`). Blast radius enumerated in section 1.
Escape hatch: `POST /battles/admin/{id}/force-finish` (`main.py:3849`, permission `battles:manage`).

**ZSET leak:** `main.py:2826` `zadd`s the next actor without `zrem`ing the one who just acted.
Removal happens only on finish (`:2554`), pause (`:1617`) and admin force-finish (`:3909`), each of
which iterates `state["participants"]` — unreachable once the state key expires at 48 h
(`redis_state.py:26`).

### Risks
- The semantics, not the plumbing, are where the risk is concentrated.
- Anything that ends a battle must also release the lock, or the fix addresses the symptom only.
- A sweeper must be idempotent: two passes must not act twice.
- If battle-service is ever scaled past one replica, an in-process loop needs a Redis lock.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0. Re-verification of section 2 against current code (2026-09-14)

All references in section 2 re-checked and still accurate: `redis_state.py:26` (`STATE_TTL_HOURS`),
`:186` (`deadline_at` written into state), `:227` (ZADD in `init_battle_state`), `:251` (unrelated `zrange`);
`main.py:2816` (state deadline on turn advance), `:2825-2828` (ZADD next actor, **no ZREM**),
`:1665/:1672` (resume re-arms deadline), `:1608-1609` (the single comparison, on pause),
`:1617 / :2554 / :3909` (the three ZREM sites), `:3849` (admin force-finish), `:3863` and `:4104`
(the only two readers of `"forfeit"`), `models.py:17` (`BattleStatus.forfeit`),
`crud.py:56` (`write_turn` persists `deadline_at`), `locations-service/app/main.py:129-141` (the lock guard).
No `zrangebyscore` / `zpopmin` anywhere; `tasks.py` still defines one task and no `beat_schedule`.

Three corrections / additions to section 2:

1. **`TURN_TIMEOUT_HOURS` is already a `Settings` field** (`config.py:11`,
   `int(os.getenv("TURN_TIMEOUT_HOURS", 24))`) and is read from `settings` at
   `main.py:615, 2481, 3227, 3524`. It is *not* hardcoded in code — what is missing is the variable in
   `docker-compose.yml` / `docker-compose.prod.yml`, so in practice it can only ever be 24. The
   "extract to configuration" work is therefore a compose-only change. Same for
   `BATTLE_STATE_TTL_HOURS` (`redis_state.py:26`), also absent from both compose files.
2. **The lock is enforced in four places, not one.** Section 2 names locations-service only:
   - `services/locations-service/app/main.py:129-141` — `check_not_in_battle`
   - `services/character-service/app/main.py:809-820` — `_is_in_battle`
   - `services/inventory-service/app/crud.py:781-792` — `is_character_in_battle`
   - `services/battle-service/app/crud.py:82-95` — `get_active_battle_for_character`

   All four are the same predicate: `battles.status IN ('pending','in_progress')` joined to
   `battle_participants` by `character_id`. Releasing the lock for a dropped-out player in a
   **continuing** team battle requires all four to change — see 3.4.
3. **battle-service cannot currently be scaled**: `container_name: battle-service` is set in
   `docker-compose.yml:467` and inherited in prod. Relevant to the sweeper-placement ruling.

---

### 3.1. Ruling — where the sweeper lives: **in-process asyncio loop in battle-service**

Decision: a background task started from an `@app.on_event("startup")` handler in
`services/battle-service/app/main.py`, guarded by a Redis lease. **Not** a Celery beat entry.

Why Celery beat loses here, decisively:

- **celery-worker has no database credentials.** `docker-compose.yml:110-141` and
  `docker-compose.prod.yml:265-276` give the worker `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`,
  `REDIS_URL`, `MONGO_URI`, `BATTLE_SERVICE_URL` — and no `DB_HOST` / `DB_DATABASE` /
  `DB_USERNAME` / `DB_PASSWORD`. Dropping a participant needs MySQL (`battles`, `battle_participants`,
  `battle_history`, `character_attributes`). A beat task therefore cannot do the work itself; it could
  only POST to an internal battle-service endpoint — beat + a new schedule + a new authenticated
  internal endpoint + an HTTP hop, three new moving parts, to trigger a coroutine that already lives
  inside battle-service.
- **Sync/async mismatch.** Celery here is a sync process; `save_log` (`tasks.py:23-33`) already has to
  hand-roll an event loop. All battle logic (`redis_state`, `crud`, `battle_engine`, the async engine in
  `database.py`) is async. Running it under Celery means re-doing that loop plumbing for a far larger
  body of code.
- **Precedent already exists in this service.** `main.py:4645-4649` starts
  `_redis_state_update_subscriber` with `asyncio.create_task` at startup. The sweeper is the same shape.
- **Beat is currently inert.** Its live shelve reads `entries → {}`. Turning it on means it starts
  mattering operationally for the first time, for no gain.

**What happens on a second replica.** Today: impossible — `container_name` pins one container in both
compose files. If that is ever lifted, the loop stays correct because of a cluster-wide lease: each tick
tries `SET battle:deadline_sweeper:lock <uuid> NX EX <2 × interval>`; a replica that does not acquire it
sleeps and retries next tick. The lease is advisory, **not** load-bearing — correctness does not depend
on it, because the per-deadline claim in 3.2 is atomic on its own. The lease only stops two replicas
doing redundant Redis/MySQL reads.

**Kill switch.** `BATTLE_TIMEOUT_SWEEPER_ENABLED` (default `1`). If `0`, the startup hook returns
immediately — an off-switch without a code deploy.

**Never-die contract.** Each tick body is wrapped so any exception is logged and the loop continues.
A sweeper that dies silently reproduces the bug it fixes.

---

### 3.2. The sweep algorithm and its idempotency

Tick (every `BATTLE_TIMEOUT_SWEEP_INTERVAL_SECONDS`, default 60):

```
due = ZRANGEBYSCORE battle:deadlines -inf <now_epoch> LIMIT 0 50
for member in due:                       # member == "{battle_id}:{participant_id}"
    parse battle_id, participant_id      # unparsable -> ZREM, log, continue
    claimed = ZREM battle:deadlines member
    if claimed != 1: continue            # <- atomic claim: another pass already owns it
    async with per-battle lock SET battle:{battle_id}:timeout:lock <uuid> NX EX 60:
        handle_expired_turn(battle_id, participant_id)
```

**Idempotency is designed in three independent layers — any one alone prevents a double drop:**

1. **Atomic claim.** `ZREM` returns how many members were actually removed. Only the caller that gets `1`
   proceeds. Two concurrent passes over the same member: exactly one gets `1`. This is the primary
   guarantee and needs no lock at all.
2. **Per-battle mutex.** `SET battle:{id}:timeout:lock NX EX 60` serialises the handler against another
   sweeper pass touching the same battle. The player-action path does not take this lock, so this is a
   narrowing, not a guarantee — layer 3 closes it.
3. **State preconditions, re-read inside the handler.** The drop is abandoned (member stays removed,
   nothing else happens) if any hold:
   - battle row missing, or `status != in_progress` → stale member, just cleaned up (brief edge case 3);
   - `state.get("paused")` is true → pause owns the ZSET, do not interfere;
   - `state["next_actor"] != participant_id` → the player already moved; the member was stale;
   - `parse_deadline(state["deadline_at"])` is **not** in the past → authoritative state disagrees with
     the ZSET score; trust the state (this is what a re-armed deadline produces);
   - the participant already has `dropped_out`, or `hp <= 0`.

   Precondition (3) is what makes a second sweeper pass — or a pass racing a legitimate move — a no-op,
   and it covers brief edge case 5 ("повторный проход не должен засчитать выбывание дважды"). The
   comparison must go through `parse_deadline` (`redis_state.py:74`) and `utc_now()`
   (`redis_state.py:62`) — never `datetime.utcnow()` directly — because `parse_deadline` is what handles
   both the legacy `+03:00` and the naive-UTC forms still coexisting in live state (FEAT-161).

   The MySQL write is additionally idempotent on its own:
   `UPDATE battle_participants SET dropped_out_at = UTC_TIMESTAMP() WHERE id = :pid AND dropped_out_at IS NULL`.

**Both players overdue (brief edge case 2, e.g. after an outage).** Order-independent by construction:
the ZSET holds at most one member per battle at a time (only the current actor is armed), so a battle
yields one expiry per tick. Player A is dropped; the turn advances to B with a **fresh** deadline
(`utc_now() + TURN_TIMEOUT_HOURS`). B is not punished for the server's downtime — they get a full
window. In a 1v1, A's drop ends the battle before B is ever considered.

**Paused battles (brief edge case 1).** `pause_battle` (`main.py:1617`) already ZREMs every member and
`resume_battle_if_ready` (`main.py:1665-1672`) re-arms with the stored `remaining_deadline_seconds`, so
the clock genuinely does not run while paused — no change needed. The `paused` precondition above is
belt-and-braces for a member that survived a crash mid-pause.

---

### 3.3. Ruling — `BattleStatus.forfeit`: **do not use it; battle status stays `finished`**

`forfeit` is read in exactly two places (`main.py:3863, 4104`) and in both it means precisely the same
thing as `finished` — "Бой уже завершён". It carries no distinct behaviour anywhere.

Four reasons not to start assigning it:

1. **It cannot express the requirement.** In a team battle the battle is *not* forfeited — one player
   left and the fight continues. The dropout fact is per-participant, not per-battle. A battle-level enum
   value is the wrong granularity for the primary case.
2. **It would fan out into an audit.** `_make_action_core:1735` tests `status.value == "finished"` only;
   `crud.finish_battle` writes only `finished`; the admin list filters, `battle_history`, the
   by-location query and the frontend all treat `finished` as *the* terminal value. A second terminal
   status means auditing every one of them — a wide, risky diff, against the minimal-diff rule.
3. **It buys nothing for the lock.** All four guard predicates test
   `status IN ('pending','in_progress')`, so `finished` releases the lock exactly as `forfeit` would.
4. **The finish machinery already writes `finished`.** Reusing it (3.5) means reusing that write.

**Where the forfeit fact is recorded instead:** the new nullable column
`battle_participants.dropped_out_at`, a `participant_timed_out` event in the Mongo turn log, and
`battle_history.result = defeat` for the dropout — which the existing history code at
`main.py:2714-2719` already produces, since `hp <= 0` ⇒ not a winner. `BattleStatus.forfeit` is left
untouched: still defensively read, never written. It should be recorded in `docs/ISSUES.md` as a dead
enum value for a future cleanup, not expanded here.

---

### 3.4. DB change and the lock release — the part that is **not** free

```sql
ALTER TABLE battle_participants
    ADD COLUMN dropped_out_at DATETIME NULL DEFAULT NULL;
```

Nullable, no backfill, no index (the guard queries already filter on an indexed `character_id` and the
row count per character is tiny). Alembic migration in **battle-service**
(`services/battle-service/app/alembic/versions/`, `version_table = alembic_version_battle`,
auto-applied at container start by the existing `command:`). Rollback = `DROP COLUMN`; no data loss,
because a rollback also reverts the guard predicates that read it.

**The release itself.** In a 1v1 the lock releases for free: the battle becomes `finished` and all four
predicates stop matching for *both* characters. In a **team battle the battle stays `in_progress`**, so
the dropped-out player would remain locked — fixing the symptom and leaving the cause, exactly what the
brief forbids. Therefore every guard gains `AND bp.dropped_out_at IS NULL`:

| Service | File:line | Function | Unlocks |
|---|---|---|---|
| locations-service | `app/main.py:129-141` | `check_not_in_battle` | movement, gathering, RP posts |
| character-service | `app/main.py:809-820` | `_is_in_battle` | character-side guards |
| inventory-service | `app/crud.py:781-792` | `is_character_in_battle` | the twelve inventory operations |
| battle-service | `app/crud.py:82-95` | `get_active_battle_for_character` | new battle / join request / invite accept |

The fourth doubles as the "can I start a new battle" check, so a dropped-out player can immediately
enter a new fight — the intended outcome.

**Shared-DB deploy ordering (accepted risk, LOW).** The column is created by battle-service's
`alembic upgrade head` at startup, while the other three services read it on user request. A single
`docker compose up --build -d` brings everything up together, so there is a seconds-long window where an
inventory/movement request could hit `Unknown column 'bp.dropped_out_at'` → a 500. Transient,
self-healing on retry, no data risk. Mitigation is deploy-time only (bring battle-service up first when
deploying by hand); no code workaround, which would be uglier than the window it removes.

---

### 3.5. Ruling — reuse: express the dropout as a defeat and run the **existing** endings

Two extractions, both mechanical and behaviour-preserving. No parallel ending is written.

**Extraction A — `_finalize_battle(...)`.** The end-of-battle block currently inlined in
`_make_action_core` (`main.py:2489-2790`, from `if battle_finished:` through its `return ActionResponse`)
moves to a module-level coroutine:

```
async def _finalize_battle(db_session, battle_id, battle_state, winner_team,
                           turn_events, turn_number, by_timeout: bool = False)
    -> BattleRewards | None
```

It keeps, unchanged and in order: `finish_battle` (status → `finished`),
`_auto_reject_pending_join_requests`, resource sync to `character_attributes`, durability sync to
inventory-service, final `save_state` + 300 s expire, ZSET cleanup for every participant, the
`battle_finished` event, PvP consequences (`pvp_training` HP→1, `pvp_death` unlink + notification),
`_distribute_pve_rewards`, NPC death marking, `battle_history`, `_track_cumulative_stats`,
`save_log.delay`, and the two WS publishes. `_make_action_core` then calls it and builds its
`ActionResponse` from the return value. The action path's observable behaviour must be identical —
protected by the existing suites (`test_pvp_consequences.py`, `test_pve_rewards.py`,
`test_battle_history.py`, `test_cumulative_stats.py`, `test_rewards_in_state.py`) plus the explicit
regression check in task 8.

**Extraction B — `_force_finish_battle(db, battle_id, state, reason)`.** The body of
`admin_force_finish_battle` (`main.py:3849-3931`) moves to a module-level coroutine; the admin endpoint
becomes a thin wrapper that validates and calls it. It already tolerates `state is None` (its resource
sync and ZSET cleanup are both `if state:`). Two additions, both required by 3.6:
- when `state is None`, enumerate participants from **MySQL `battle_participants`** and ZREM
  `f"{battle_id}:{pid}"` for each — this is what finally closes the leak the brief describes
  ("после истечения состояния даже принудительное завершение не сможет перечислить участников");
- stamp `dropped_out_at` on all participants and notify each non-NPC participant's user with `reason`.

This also repairs the admin force-finish path, which today silently leaves ZSET members behind for any
battle whose state key has expired.

**The dropout handler then does almost nothing of its own:**

```
handle_expired_turn(battle_id, participant_id):
    preconditions (3.2 layer 3) -> else return
    p = state["participants"][str(participant_id)]
    p["dropped_out"] = True; p["hp"] = 0; p["defeated"] = True
    UPDATE battle_participants SET dropped_out_at = UTC_TIMESTAMP()
        WHERE battle_id = :bid AND id = :pid AND dropped_out_at IS NULL
    events = [participant_timed_out, participant_defeated]
    teams_alive = {team of p where hp > 0}                    # identical to main.py:2467-2476
    if len(teams_alive) <= 1:
        winner_team = the survivor or None
        await _finalize_battle(..., by_timeout=True)          # <- Extraction A
    else:
        advance next_actor along turn_order skipping hp <= 0  # identical to main.py:2792-2803
        new_deadline = utc_now() + TURN_TIMEOUT_HOURS
        save_state; ZADD next actor; publish your_turn; publish state_update; save_log.delay
```

Both business rules fall out of this one mechanism, with no special-casing:
- **1v1** → the opponent's team is the only one alive → `_finalize_battle` with `winner_team` = opponent.
  Full existing machinery: rewards, history, cumulative stats, resource sync, WS `battle_finished`,
  ZSET cleanup, status `finished` → **lock released for both**.
- **Team battle** → other teams still alive → the battle continues without the dropout; teammates keep
  their turns; the dropout's own lock is released by `dropped_out_at` (3.4).
- **Last member of a team drops out** (brief edge case 6) → that team has no `hp > 0` member, so it
  leaves `teams_alive`; if one team remains, the battle ends and it wins. No extra code.

---

### 3.6. The hard edge case — Redis state expired (48 h) while the row is still `in_progress`

Two sub-cases, and the ZSET member is **not** the only recovery key.

**(a) A ZSET member exists but `load_state` returns `None`.** The member itself carries both ids
(`"{battle_id}:{participant_id}"`), so *who* is always recoverable without Redis. What is unrecoverable
is the engine state: HP, teams, active effects, turn order — all gone. There is no honest way to award a
victory after 48 h of silence, and nothing left to continue. Ruling: **abandon-finish the whole battle**
via `_force_finish_battle(db, battle_id, state=None, reason="Бой завершён: истёк срок ожидания хода")`.
Status → `finished`, no winner, no rewards, no PvP consequences, all participants stamped
`dropped_out_at`, every ZSET member for that battle removed (enumerated from MySQL
`battle_participants`), all participants notified. Lock released for everyone. Fairest available
outcome, and it reuses machinery that already exists.

**(b) The battle is orphaned with *no* ZSET member at all** — e.g. it was paused when the state key
expired, so nothing was ever re-armed; or its member was lost. A ZSET-keyed sweeper is structurally
blind to this, and it is the state the battles already wedged on prod are in today. Covered by a
**low-frequency MySQL reconciliation pass** in the same loop, every `BATTLE_TIMEOUT_RECONCILE_EVERY`
ticks (default 60 → hourly):

```sql
SELECT id FROM battles
 WHERE status = 'in_progress'
   AND updated_at < UTC_TIMESTAMP() - INTERVAL :state_ttl_hours HOUR
```

then, per row, check `EXISTS(battle:{id}:state)` in Redis — and only if the key is **absent** call
`_force_finish_battle(..., state=None, ...)`. Two independent guards (age **and** missing state key), so
a healthy long battle can never be swept: a live battle rewrites its state key on every turn and its row
on every status change. `battles` is small and the pass is hourly, so the cost is negligible.

This pass is also the **retro-fix**: it clears the battles already stuck in production, which the
deadline sweeper alone would never reach. That is deliberate, not a side effect.

---

### 3.7. Configuration (DevSecOps) — compose only, no new code paths

| Variable | Default | Read at | Change |
|---|---|---|---|
| `TURN_TIMEOUT_HOURS` | `24` | `config.py:11` (exists) | add to `battle-service` env in **both** compose files |
| `BATTLE_STATE_TTL_HOURS` | `48` | `redis_state.py:26` (exists) | add to **both** (currently invisible/unsettable) |
| `BATTLE_TIMEOUT_SWEEPER_ENABLED` | `1` | new, `config.py` | add to **both** |
| `BATTLE_TIMEOUT_SWEEP_INTERVAL_SECONDS` | `60` | new, `config.py` | add to **both** |
| `BATTLE_TIMEOUT_RECONCILE_EVERY` | `60` (ticks) | new, `config.py` | add to **both** |

`TURN_TIMEOUT_HOURS` stays at **24**. The user's rationale — one real day, so a player can sleep and work
a shift — is the design intent and is recorded here so nobody "optimises" it later. The change is only
that it is now settable without a code edit.

New fields follow the existing Pydantic **v1** `BaseSettings` style already in `config.py` — no
`model_config`, no `pydantic-settings` import. **No new Python dependency** is introduced by this
feature: `redis.asyncio`, `httpx`, `asyncio` and Celery are all already in
`services/battle-service/app/requirements.txt`.

---

### 3.8. API contracts

**No new or modified public endpoints.** The sweeper is an internal background task calling in-process
coroutines; there is no HTTP hop, so there is no contract to version. The admin force-finish endpoint
keeps its exact path, method, request, response and permission — only its body is extracted.

One **additive, backward-compatible response-shape change** — participant payloads in `get_state`
(`main.py:1307`), `get_state_internal` (`:1247`), `_build_runtime` and the WS `battle_state` payload
(feeding `main.py:1263, 1353, 1438, 4576`) gain:

```json
{ "dropped_out": false }
```

Declared in `schemas.py` as `dropped_out: bool = False` (Pydantic v1). Optional and defaulting to
`false`, so in-flight battles from before the deploy and the current frontend both keep working
unchanged. **Consumer check (cross-service-validator):** the only HTTP consumer of battle-service state
is autobattle-service (`AUTOBATTLE_SERVICE_URL` → `GET /battles/{id}/state/internal`); it reads
`next_actor` and per-participant resources, and an extra key is inert for it. Adding a field is not a
breaking change for any caller.

New Mongo turn-log event (append-only, consumed only by the frontend battle log):

```json
{ "event": "participant_timed_out", "who": 42, "character_id": 17 }
```

**Security review of this feature:**
- *Authentication* — not applicable; no new endpoint is exposed. `POST /battles/admin/{id}/force-finish`
  keeps `require_permission("battles:manage")` unchanged.
- *Authorization* — unchanged. Nothing new is user-triggerable, so **no new RBAC permission** and no
  `permissions` / `role_permissions` migration is required.
- *Rate limiting* — not applicable (no request surface). The sweeper self-limits at 50 members per tick,
  bounding Redis and MySQL load even against the large ZSET backlog the leak has accumulated.
- *Input validation* — ZSET members are corruption-relevant: parse defensively
  (`member.rsplit(":", 1)`; non-integer → ZREM, log, continue). A malformed member must never be able to
  kill the loop. The per-battle lock value is a uuid so release can verify ownership.
- *Error messages / data leakage* — user-facing strings are the fixed Russian sentences in 3.9; no ids,
  no internal state, no exception text reaches a player. Full detail goes to the service log only.

---

### 3.9. What the players see

Follows exactly what the existing finish path does — `publish_notification`
(`rabbitmq_publisher.py:44`, as used at `main.py:2620` and `main.py:1690-1700`) for notifications,
`battle:{id}:state_update` pub/sub for WS, `save_log.delay` for the Mongo battle log.

| Audience | Channel | Russian text | `ws_type` |
|---|---|---|---|
| The dropped player | notification | «Вы не сделали ход за отведённое время и выбыли из боя.» | `battle_timeout_dropout` |
| Everyone else in the battle | notification | «{Имя} не успел сделать ход и выбыл из боя.» | `battle_participant_dropped` |
| All participants (abandon-finish, 3.6) | notification | «Бой завершён: истёк срок ожидания хода.» | `battle_force_finished` |
| Battle log (Mongo, all viewers) | `save_log.delay` | event `participant_timed_out` | — |
| WS, battle continues | `state_update` | `battle_state`, plus `your_turn` to the next actor | — |
| WS, battle ends | `state_update` | `battle_state` then `battle_finished` | — |

Notification queries must exclude NPCs (`AND c.is_npc = 0`), matching the existing pattern at
`main.py:1678-1685` and `main.py:4393-4400`. Names come from the cached snapshot the same way
`battle_history` resolves them (`main.py:2700-2712`), falling back to `Персонаж #{id}`.

**Frontend.** No change is *required*: `useBattleWebSocket.ts:169` already handles `battle_finished`
and `BattlePage.tsx:309-312` already clamps the timer at zero. But `BattlePageBar.tsx:473-620` renders
the battle log through an `if (event.event === ...)` chain and silently drops unknown events, so a
timeout would make a participant vanish with no explanation. One small task adds the branch. Those files
are already `.tsx` and Tailwind-styled, so no TS/Tailwind migration is triggered; no `React.FC`.

---

### 3.10. Data flow

```
battle-service startup
  └─ asyncio.create_task(_deadline_sweeper_loop)          # main.py, next to :4645
       every INTERVAL s:
         SET battle:deadline_sweeper:lock NX EX            # advisory, multi-replica only
         ZRANGEBYSCORE battle:deadlines -inf now LIMIT 50
           └─ ZREM member  ──(returns 1)──>  handle_expired_turn(battle_id, pid)
                 ├─ load_state(battle_id)
                 │    ├─ None ──> _force_finish_battle(state=None)            # 3.6(a)
                 │    │              ├─ MySQL battle_participants ──> ZREM every member
                 │    │              ├─ finish_battle → status 'finished'
                 │    │              ├─ dropped_out_at for all
                 │    │              └─ publish_notification × N ──RabbitMQ──> notification-service
                 │    └─ state ──> preconditions → mark dropped_out / hp = 0
                 │         ├─ MySQL: battle_participants.dropped_out_at = UTC_TIMESTAMP()
                 │         ├─ teams_alive <= 1 ──> _finalize_battle(...)       # the SAME path a
                 │         │     ├─ MySQL: battles.status = 'finished'         #  killing blow takes
                 │         │     ├─ MySQL: character_attributes resource sync
                 │         │     ├─ HTTP ──> inventory-service (durability)
                 │         │     ├─ HTTP ──> character-service (pvp_death unlink / NPC status)
                 │         │     ├─ MySQL: battle_history, cumulative stats
                 │         │     ├─ Celery save_log ──> Mongo
                 │         │     └─ Redis pub battle_finished ──> WS ──> frontend
                 │         └─ else ──> next_actor++, new deadline, ZADD, pub your_turn + state_update
                 └─ (every 60th tick) reconciliation: stale in_progress battles
                      with no Redis state ──> _force_finish_battle(state=None)   # 3.6(b)

lock release, read by four services over the shared DB:
  battles.status = 'finished'          → releases everyone (1v1 and any finish)
  battle_participants.dropped_out_at   → releases the dropout while a team battle continues
    ├─ locations-service  check_not_in_battle        (movement, gathering, RP posts)
    ├─ character-service  _is_in_battle
    ├─ inventory-service  is_character_in_battle     (12 operations)
    └─ battle-service     get_active_battle_for_character (new battle / join / invite)
```

---

### 3.11. Questions to PM — **answered 2026-09-14, closed**

1. **PvP-death timeout = permanent character loss?** → **Yes, the rule stands.** The user accepts that
   timing out of a death duel destroys the character, and asked for an **escape valve rather than a
   softening**: admins can *freeze* a battle when both players agree in advance. Designed in 3.12-3.15.
   `_finalize_battle` still takes `by_timeout: bool` (cheap reversibility), but the `pvp_death` unlink is
   **not** gated on it — a timeout is a loss like any other.
2. **PvE rewards for a dropout whose team wins?** → **No rewards.** Assumption confirmed; the existing
   `hp = 0` rule applies unchanged, same as a teammate who died normally. No code change.
3. Recorded, not blocking: the user's future idea of not counting night hours toward the deadline
   (section 1) is explicitly out of scope. Configurable `TURN_TIMEOUT_HOURS` is a prerequisite for it
   either way.

**Framing that shapes 3.12-3.15:** a battle normally takes ~15 minutes with both players present. The
24-hour deadline exists for exceptions, and the freeze is a **rare, deliberate, human-mediated act** —
a player warns the other side, they agree, an admin freezes until they return. It is not a routine
feature and needs no self-service path, no scheduling, no auto-expiry.

---

### 3.12. Admin freeze / unfreeze — reuse the existing pause machinery

PM is right that the machinery exists in full. Re-verified: `pause_battle` (`main.py:1590-1630`) sets
`battles.is_paused`, sets `state["paused"]`, stores `remaining_deadline_seconds`, **ZREMs every deadline
member** (`:1617`) and broadcasts `battle_paused`; `resume_battle_if_ready` (`:1632-1706`) restores
`deadline_at = now + remaining_deadline_seconds` and re-ZADDs (`:1659-1672`). Actions are refused while
paused (`:1746`). The frontend blocks input (`BattlePage.tsx:574`) and shows a banner (`:725`).

So the turn timer genuinely stops and resumes with the **remaining** time, not a fresh 24 hours. Nothing
about that needs rebuilding. Four gaps, each small:

**Gap 1 — `resume_battle_if_ready` has a gate, and it is the wrong one for an admin.** Its first act is
to count pending `battle_join_requests` and return `False` if any exist (`:1639-1650`). It is also
called unconditionally when a join request is approved or rejected (`:4211`, `:4275`). Consequence if
admin freeze simply reuses `pause_battle`: a player files a join request on a frozen battle, an admin
resolves it, and `resume_battle_if_ready` **silently cancels the admin freeze**. The freeze must
therefore be ownable.

**Ruling:** add `battles.paused_by_admin BOOLEAN NOT NULL DEFAULT 0`. `resume_battle_if_ready` returns
`False` early when it is set — an admin freeze outranks the join-request pause. Admin unfreeze clears
the flag and then calls `resume_battle_if_ready` itself, so if a join request happens to be pending the
battle correctly stays paused and downgrades to the join-request reason instead of resuming. That reuses
the existing resume path exactly as PM asked, with **no parallel resume function**.

**Gap 2 — the reason is hardcoded in four places, not three.** PM found `:1349`, `:1434` and `:1624`;
there is a fourth at `:4603` (`_build_runtime`, which feeds the WS `battle_state` payload). All four
would otherwise tell a frozen player their battle is paused for a join request.

**Ruling on storage:** `battles.pause_reason VARCHAR(255) NULL` in MySQL as the source of truth, echoed
into `state["pause_reason"]` in Redis. This mirrors how `is_paused` / `state["paused"]` are already
duplicated, so it introduces no new pattern. MySQL must hold it because the reason has to survive the
48 h Redis TTL — a freeze that outlives the state key is precisely the case this feature exists for.
The two DB-backed sites (`:1349`, `:1434`) already load `battle_record`, so they read
`battle_record.pause_reason` with **no extra query**; `:1624` uses the value passed into `pause_battle`;
`:4603` reads `state.get("pause_reason")`.

`pause_battle` gains `reason: str` and `by_admin: bool = False` parameters. The join-request caller
(`:4384`) passes the existing string, so its behaviour is unchanged.

**Yes, the admin should be able to type a reason** — the flow is social ("Игрок X в отъезде до
понедельника"), and a fixed string would lose exactly the information the other player needs. Optional;
default «Бой заморожен администратором».

**Gap 3 — the player-facing banner does not render the reason.** PM asked me to confirm rather than
assume, and the answer is **no**. `paused_reason` is already plumbed end to end
(`api/battles.ts:57` → `BattlePage.tsx:68` → `useBattleWebSocket.ts:183`), but the banner at
`BattlePage.tsx:725-731` **hardcodes** «Бой приостановлен — рассматриваются заявки на присоединение» and
ignores the prop. Without fixing this, an admin-typed reason is stored, transmitted, and then discarded
at the last step. This is a required frontend fix, not a confirmation.

**Gap 4 — no admin-facing entry point.** Two endpoints (3.13) and a control on the admin battles page,
next to the existing force-finish call at `AdminBattlesPage.tsx:235`.

---

### 3.13. Admin freeze API contracts

Both guarded by `require_permission("battles:manage")` — the same dependency as
`admin_force_finish_battle` (`main.py:3849`). **No new RBAC permission and therefore no
`permissions` / `role_permissions` migration**, per CLAUDE.md §10.13: the capability is an extension of
existing battle administration, not a new module.

#### `POST /battles/admin/{battle_id}/freeze`

**Request** (Pydantic v1, `reason` optional):
```json
{ "reason": "Игрок в отъезде до понедельника, противник согласен" }
```
**Response 200:**
```json
{ "ok": true, "battle_id": 42, "is_paused": true,
  "reason": "Игрок в отъезде до понедельника, противник согласен",
  "message": "Бой заморожен" }
```
- `404` «Бой не найден»; `400` «Бой уже завершён» if status is not `pending`/`in_progress`.
- Freezing a battle already paused by a join request is **allowed** — it upgrades the pause to
  admin-owned and replaces the reason. Harmless and useful.
- Validation: `reason` is `Optional[str]`, stripped, `max_length=255`, control characters rejected,
  empty → the default «Бой заморожен администратором». It is displayed verbatim to players, so the
  frontend must render it as text — confirmed safe: the banner uses a plain `{...}` expression, no
  `dangerouslySetInnerHTML` anywhere in `BattlePage.tsx`.

#### `POST /battles/admin/{battle_id}/unfreeze`

**Response 200:**
```json
{ "ok": true, "battle_id": 42, "is_paused": false, "reason": null,
  "message": "Бой разморожен" }
```
- Clears `paused_by_admin`, then calls `resume_battle_if_ready`. If a join request is still pending the
  battle stays paused and the response reports `is_paused: true` with the join-request reason and
  «Бой остаётся на паузе: рассматривается заявка на присоединение» — so the admin is told the truth
  instead of seeing a silent no-op.
- `404` if missing; `400` «Бой не приостановлен» if it was not paused at all.

Remaining time is restored by the existing resume path, **not** reset to a fresh 24 hours. One caveat
inherited from the current code: `state.get("remaining_deadline_seconds", 60)` (`:1659`) falls back to
60 seconds if the key is absent. That only happens if the state was missing at pause time; leave the
fallback as is, but QA asserts the normal path preserves the real remainder.

---

### 3.14. Freeze × sweeper — the interaction, verified rather than assumed

**Deadline sweep: safe, and doubly so.** `pause_battle` ZREMs every member for the battle (`:1617`), so a
frozen battle has nothing in `battle:deadlines` and the sweep cannot see it. Independently, precondition
layer 3 in 3.2 abandons the drop when `state.get("paused")` is true. Confirmed, not assumed.

**Reconciliation pass: NOT safe as designed — this is the real catch.** The pass in 3.6(b) selects
`status = 'in_progress' AND updated_at < now - ttl`, then abandon-finishes any battle with no Redis state
key. A battle frozen for a week matches on every count: `updated_at` is not bumped by the pause (the
pause writes raw SQL, `text("UPDATE battles SET is_paused = 1 ...")`, which does **not** trigger the
ORM-side `onupdate` on `models.py:59-63`, and the column has no MySQL `ON UPDATE CURRENT_TIMESTAMP`), and
after 48 h the state key has expired. A legitimately frozen battle would be destroyed by the very pass
meant to rescue orphans.

**Fix:** add `AND is_paused = 0` to the reconciliation SELECT. MySQL-based, so it keeps working after the
Redis state is gone — which is exactly when it matters.

**A deeper problem the freeze exposes, and the fix for it.** `battle:{id}:state` expires after
`BATTLE_STATE_TTL_HOURS` (48 h, `redis_state.py:26`). A freeze is meant to last *days*. When the key
expires mid-freeze, unfreeze does nothing useful: `resume_battle_if_ready` guards its whole restore
block with `if state:` (`:1657`), so it clears `is_paused`, re-arms **no** deadline, adds **no** ZSET
member, and leaves a battle that is unplayable *and* now invisible to the deadline sweeper. The freeze
feature would silently stop working past 48 hours — the only duration anyone would use it for.

**Fix, reusing the loop already being built:** each sweeper tick also runs a **frozen-battle keep-alive** —
`SELECT id FROM battles WHERE status = 'in_progress' AND is_paused = 1`, then `EXPIRE battle:{id}:state
<STATE_TTL>` for each. Frozen battles then survive indefinitely, which is what "freeze until they return"
has to mean. Cost is one small indexed query plus N `EXPIRE` calls per tick — negligible, and it needs no
new background task. A `pending`/finished battle is never touched.

Net effect: the sweeper gains one guard and one keep-alive, both inside the loop it already owns.

---

### 3.15. Freeze — DB, flow and player-visible strings

```sql
ALTER TABLE battles
    ADD COLUMN pause_reason VARCHAR(255) NULL DEFAULT NULL,
    ADD COLUMN paused_by_admin TINYINT(1) NOT NULL DEFAULT 0;
```
Folded into the **same** Alembic revision as `battle_participants.dropped_out_at` (task 4) so the whole
feature is one migration and one deploy window. Rollback drops all three columns.

```
Admin → POST /battles/admin/{id}/freeze {reason}
   └─ pause_battle(db, id, reason, by_admin=True)          # existing function, two new params
        ├─ MySQL: is_paused=1, pause_reason=…, paused_by_admin=1
        ├─ Redis: state["paused"]=True, state["pause_reason"]=…,
        │         state["remaining_deadline_seconds"]=<remainder>
        ├─ Redis: ZREM every battle:deadlines member        # ← timer stops, sweeper blind
        └─ WS battle_paused {is_paused:true, reason:<dynamic>}
   └─ notify each non-NPC participant

sweeper tick (3.14)
   ├─ reconciliation SELECT … AND is_paused = 0             # ← frozen battles excluded
   └─ keep-alive: EXPIRE battle:{id}:state for is_paused=1  # ← freeze outlives 48 h

Admin → POST /battles/admin/{id}/unfreeze
   └─ MySQL: paused_by_admin=0
   └─ resume_battle_if_ready(db, id)                        # existing function, existing gate
        ├─ pending join requests? → stay paused, reason ← join-request string, report it
        └─ else: deadline_at = now + remaining_deadline_seconds, ZADD, WS, notify
```

| Audience | Channel | Russian text |
|---|---|---|
| All participants, on freeze | notification + banner | «Бой заморожен администратором.» or the admin's text |
| All participants, on unfreeze | notification | «Бой продолжается!» (existing string, `:1694`) |
| Admin, unfreeze blocked | API `message` | «Бой остаётся на паузе: рассматривается заявка на присоединение» |

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Ordered so something correct and useful lands first: task 1 is the independent ZSET-hygiene fix and is
shippable on its own; tasks 2-5 are the foundations (config, compose, one migration, lock guards);
task 6 is a pure behaviour-preserving refactor; task 7 is the admin freeze; task 8 is the sweeper, which
depends on the freeze because it must know not to sweep a frozen battle.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **ZSET hygiene (independent, tiny).** On turn advance, remove the previous actor's deadline member before arming the next one: add a `ZREM ZSET_DEADLINES f"{battle_id}:{request.participant_id}"` immediately before the existing `zadd` at `main.py:2825-2828`. Nothing else in this task. | Backend Developer | DONE | `services/battle-service/app/main.py` | — | `battle:deadlines` holds at most one member per battle after any sequence of turns. `python -m py_compile` passes. No other line changed. |
| 2 | **Config fields.** Add `BATTLE_TIMEOUT_SWEEPER_ENABLED` (default `1`), `BATTLE_TIMEOUT_SWEEP_INTERVAL_SECONDS` (default `60`), `BATTLE_TIMEOUT_RECONCILE_EVERY` (default `60`) to `Settings`, in the existing Pydantic **v1** `os.getenv` style. Do not touch `TURN_TIMEOUT_HOURS` — it already exists. Add no new package to `requirements.txt`. | Backend Developer | DONE | `services/battle-service/app/config.py` | — | Fields readable as `settings.*`; defaults match the table in 3.7; `python -m py_compile` passes; `requirements.txt` unchanged. |
| 3 | **Compose env vars.** Add `TURN_TIMEOUT_HOURS: 24`, `BATTLE_STATE_TTL_HOURS: 48`, `BATTLE_TIMEOUT_SWEEPER_ENABLED: "1"`, `BATTLE_TIMEOUT_SWEEP_INTERVAL_SECONDS: 60`, `BATTLE_TIMEOUT_RECONCILE_EVERY: 60` to the `battle-service` `environment:` block in **both** compose files. No other service needs them (celery-worker does not run the sweeper). | DevSecOps | DONE | `docker-compose.yml` (battle-service block, ~:474-487), `docker-compose.prod.yml` (battle-service block, ~:197-216) | #2 | Both files list all five; `docker compose config` parses; values identical between dev and prod; no secret introduced. |
| 4 | **DB columns + migration (one revision for the whole feature).** Add to `BattleParticipant`: `dropped_out_at: Mapped[datetime \| None]` (`DateTime`, nullable). Add to `Battle`: `pause_reason: Mapped[str \| None]` (`String(255)`, nullable) and `paused_by_admin: Mapped[bool]` (`Boolean`, default `False`, `server_default="0"`, matching the existing `is_paused` style at `models.py:56-58`). One hand-written Alembic revision adding all three, downgrade dropping all three, on top of the current head. Do **not** add indexes. | Backend Developer | DONE | `services/battle-service/app/models.py`, `services/battle-service/app/alembic/versions/<new>.py` | — | `alembic upgrade head` then `downgrade -1` both succeed against a MySQL 8 test DB; `down_revision` points at the true current head; `version_table` remains `alembic_version_battle`; `python -m py_compile` passes. |
| 5 | **Lock-guard predicates.** Add `AND bp.dropped_out_at IS NULL` to all four active-battle guards. Change only the WHERE clause; no signature or behaviour change otherwise. | Backend Developer | DONE | `services/locations-service/app/main.py:129-141`, `services/character-service/app/main.py:809-820`, `services/inventory-service/app/crud.py:781-792`, `services/battle-service/app/crud.py:82-95` | #4 | All four queries contain the clause; a participant with `dropped_out_at` set is not reported as in battle by any of the four; a normal participant still is; `python -m py_compile` passes for all four services. |
| 6 | **Refactor: extract the two endings (no behaviour change).** Extraction A — move the `if battle_finished:` block from `_make_action_core` (`main.py:2489-2790`) into module-level `_finalize_battle(db_session, battle_id, battle_state, winner_team, turn_events, turn_number, by_timeout=False)`; `_make_action_core` calls it and builds its `ActionResponse` from the result. Extraction B — move the body of `admin_force_finish_battle` (`main.py:3849-3931`) into `_force_finish_battle(db, battle_id, state, reason)`, with the two additions in 3.5 (enumerate participants from MySQL when `state is None` to ZREM every member and stamp `dropped_out_at`; notify each non-NPC participant with `reason`). The admin endpoint keeps its exact path, method, response model and `require_permission("battles:manage")`. | Backend Developer | DONE | `services/battle-service/app/main.py` | #4 | Existing suites `test_pvp_consequences.py`, `test_pve_rewards.py`, `test_battle_history.py`, `test_cumulative_stats.py`, `test_rewards_in_state.py`, `test_admin_battles.py` pass **unchanged**; admin force-finish request/response byte-identical; force-finish on a battle with no Redis state now removes its ZSET members; `python -m py_compile` passes. |
| 7 | **Dynamic pause reason + admin freeze/unfreeze (3.12-3.13, 3.15).** Extend `pause_battle` with `reason: str` and `by_admin: bool = False` (join-request caller at `main.py:4384` passes the existing string — behaviour unchanged). Persist `pause_reason` / `paused_by_admin` in MySQL and echo `pause_reason` into the Redis state. Replace the hardcoded reason at **all four** sites — `main.py:1349`, `:1434`, `:1624`, `:4603`. Make `resume_battle_if_ready` return `False` early when `paused_by_admin` is set. Add `POST /battles/admin/{battle_id}/freeze` and `POST /battles/admin/{battle_id}/unfreeze` per 3.13, both `Depends(require_permission("battles:manage"))`, with Pydantic **v1** request/response schemas; unfreeze clears the flag then calls `resume_battle_if_ready` and reports honestly when it stays paused. No parallel resume function. Notify non-NPC participants on freeze. | Backend Developer | DONE | `services/battle-service/app/main.py`, `services/battle-service/app/schemas.py` | #4 | Join-request pause still shows its original reason; an admin-typed reason reaches all four render sites; resolving a join request on an admin-frozen battle does **not** resume it; unfreeze restores `remaining_deadline_seconds`, not a fresh 24 h; both endpoints 403 without `battles:manage`; `reason` over 255 chars rejected; `python -m py_compile` passes. |
| 8 | **The sweeper.** Implement `_deadline_sweeper_loop` (started from a new `@app.on_event("startup")` next to `main.py:4645`, gated by `BATTLE_TIMEOUT_SWEEPER_ENABLED`, advisory Redis lease, never-die try/except per tick), `handle_expired_turn` and the hourly reconciliation pass, exactly as specified in 3.2 / 3.5 / 3.6. **Freeze safety (3.14):** the reconciliation SELECT must carry `AND is_paused = 0`, and each tick must run the frozen-battle keep-alive (`SELECT id FROM battles WHERE status='in_progress' AND is_paused=1` → `EXPIRE battle:{id}:state <STATE_TTL>`). Use its own `AsyncSessionLocal()` session per tick (`database.py:23`). Time comparisons via `utc_now()` / `parse_deadline` only. Emit the notifications, WS publishes and `save_log` events in 3.9. Add `dropped_out: bool = False` to the participant schema in `schemas.py` and populate it in `_build_runtime`. | Backend Developer | DONE | `services/battle-service/app/main.py`, `services/battle-service/app/schemas.py`, `services/battle-service/app/redis_state.py` (helper only if needed) | #2, #4, #5, #6, #7 | A battle with a backdated deadline is swept within one interval; 1v1 → status `finished`, opponent wins, both characters unlocked; 3v3 → only the dropout gets `dropped_out_at`, teammates keep playing, dropout unlocked; a second pass is a no-op; expired-state battle is abandon-finished with all ZSET members removed; **a frozen battle is never swept and never reconciled, and its state key survives past `BATTLE_STATE_TTL_HOURS`**; loop survives a forced exception in one tick; `python -m py_compile` passes. |
| 9 | **Backend tests.** New `test_turn_timeout.py` covering, at minimum: (a) **backdated deadline** — a battle whose ZSET score is in the past is swept and the participant dropped; (b) **idempotency** — running the sweeper twice over the same state drops exactly once (assert `dropped_out_at` unchanged on the second pass and no second `battle_history` row); (c) 1v1 → `finished` + correct `winner_team`; (d) 3v3 → battle stays `in_progress`, only one `dropped_out_at`, `next_actor` advanced past the dropout; (e) last-member-of-team drop ends the battle; (f) preconditions: paused battle, already-finished battle, stale member whose `next_actor` moved on, deadline not actually past — each a no-op; (g) expired state (`load_state → None`) → abandon-finish, ZSET members enumerated from MySQL and removed; (h) reconciliation finds a stale `in_progress` battle with no state key; (i) **ZSET hygiene** (task 1) — after two turns `battle:deadlines` has exactly one member for the battle; (j) **lock release** — the four guard predicates return "not in battle" for a participant with `dropped_out_at` set; (k) a malformed ZSET member does not raise. Follow the existing fixture style in `tests/conftest.py` and `test_deadline_timezone.py`. | QA Test | DONE | `services/battle-service/app/tests/test_turn_timeout.py`, `services/battle-service/app/tests/conftest.py` (fixtures only if needed) | #8 | All new tests pass; the whole battle-service suite still passes; cases (a) and (b) present and explicitly named. |
| 10 | **Freeze tests (3.12-3.14).** New `test_admin_freeze.py`: (a) **a paused battle is never swept** — no ZSET member after freeze, and `handle_expired_turn` on a stale member is a no-op via the `paused` precondition; (b) **the reconciliation pass skips a frozen battle** even when it is old and its Redis state key is gone (the `is_paused = 0` guard); (c) **the keep-alive** refreshes `battle:{id}:state` TTL for a frozen battle; (d) **unfreeze restores the remaining time, not a fresh 24 h** — assert the new `deadline_at` ≈ `now + remaining_deadline_seconds`; (e) resolving a join request on an admin-frozen battle does **not** resume it; (f) unfreeze while a join request is pending leaves the battle paused and reports it; (g) the admin reason reaches all four render sites and the join-request pause keeps its own reason; (h) **permissions** — both endpoints 403 without `battles:manage`, 404 on a missing battle, 400 on a finished battle; (i) `reason` validation (>255 chars, empty → default). | QA Test | DONE | `services/battle-service/app/tests/test_admin_freeze.py` | #7, #8 | All new tests pass; the whole battle-service suite still passes; cases (a), (b) and (d) present and explicitly named. |
| 11 | **Regression test for the refactor.** Assert the extracted `_finalize_battle` produces the same observable outcome when reached from a killing blow as before (status, `battle_history` rows, rewards payload, WS `battle_finished`), and that `_force_finish_battle` with `state=None` cleans ZSET members and stamps `dropped_out_at`. | QA Test | DONE | `services/battle-service/app/tests/test_turn_timeout.py` or a new `test_finalize_extraction.py` | #6 | Tests pass; a deliberate behaviour change in `_finalize_battle` would fail them. |
| 12 | **Battle-log rendering.** Add a `participant_timed_out` branch to the event renderer so the log shows «{Имя} не успел сделать ход и выбыл из боя.» in Russian, styled with the existing Tailwind classes used by the neighbouring branches. Extend the event union type in `useBattleWebSocket.ts` if the type is declared there. TypeScript only, no `React.FC`, no new SCSS, must render correctly at 360px. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/BattlePage/BattlePageBar/BattlePageBar.tsx`, `services/frontend/app-chaldea/src/hooks/useBattleWebSocket.ts` (types only, if needed) | #8 | `npx tsc --noEmit` and `npm run build` both pass; the event renders in Russian; no `React.FC`; no SCSS added; layout intact at 360px. |
| 13 | **Pause banner must render the reason (bug fix, 3.12 Gap 3).** `BattlePage.tsx:725-731` hardcodes the join-request text and ignores the already-plumbed `paused_reason`. Render `runtimeData.paused_reason` with the current string as fallback when it is null. Keep the existing Tailwind classes and `sm:` breakpoints; render as text only (no `dangerouslySetInnerHTML`). | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/BattlePage/BattlePage.tsx` | #7 | An admin-typed reason appears in the banner; a join-request pause still reads «Бой приостановлен — рассматриваются заявки на присоединение»; `npx tsc --noEmit` and `npm run build` pass; banner intact at 360px; no `React.FC`, no SCSS added. |
| 14 | **Admin freeze/unfreeze control.** Add `freezeBattle(battleId, reason)` / `unfreezeBattle(battleId)` to the battles API module, and Freeze / Unfreeze buttons on the admin battles page beside the existing force-finish call (`AdminBattlesPage.tsx:235`), with a text input for the reason on freeze. Button state follows the row's `is_paused`. Show the API `message` on success (including the "stays paused" case) and a Russian error message on any failure — **every call must display errors, no silent failures**. Gate the control with `hasPermission('battles:manage')` from `utils/permissions.ts`. Use design-system classes per `docs/DESIGN-SYSTEM.md`; TypeScript only, no `React.FC`, no SCSS, usable at 360px. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/Admin/BattlesPage/AdminBattlesPage.tsx`, `services/frontend/app-chaldea/src/api/battles.ts` | #7 | Freeze with a reason pauses the battle and the reason shows in the player banner; unfreeze resumes it; a non-`battles:manage` user does not see the control; errors surface in Russian; `npx tsc --noEmit` and `npm run build` pass; layout intact at 360px. |
| 15 | **Bug-tracking hygiene.** Record `BattleStatus.forfeit` as a dead enum value (assigned nowhere, read at `main.py:3863, 4104` as a synonym for `finished`) in `docs/ISSUES.md` as LOW-priority cleanup, and remove/close any existing ISSUES entry about the unenforced turn timeout or the `battle:deadlines` leak now that they are fixed. | Backend Developer | DONE | `docs/ISSUES.md` | #8 | `docs/ISSUES.md` reflects the post-fix state: no stale entry for the timeout bug or the ZSET leak; the `forfeit` note present. |
| 16 | **Docs.** Update `docs/services/battle-service.md` with the two new admin endpoints, the three new columns, the sweeper and its env vars. | Backend Developer | DONE | `docs/services/battle-service.md` | #7, #8 | Endpoints, columns, sweeper and env vars documented; no secrets. |
| 17 | **Review.** Full checklist plus: re-run `python -m py_compile` on every modified Python file, the battle-service pytest suite, `npx tsc --noEmit` and `npm run build`; cross-service-validator over the four guard predicates and the additive `dropped_out` / `paused_reason` fields (autobattle-service is the only HTTP consumer of battle state); **live verification** — (a) create a battle, backdate its ZSET score, confirm the sweeper drops the participant within one interval, the battle resolves per 3.5, and the affected character can then move and use inventory; (b) freeze a battle with a typed reason, confirm the player banner shows that reason, confirm no ZSET member remains, then unfreeze and confirm the remaining time is restored rather than reset. A review without both automated results and live verification is invalid. | Reviewer | DONE | all | #1-#16 | Checklist in section 5 completed with actual command output; both live verifications recorded; zero console/500 errors. |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-14
**Result:** PASS

Every check below was executed by the Reviewer in this session; nothing is taken from the
implementers' reports. Live verification was done against the running dev stack (real MySQL,
Redis, Mongo, RabbitMQ and the real cross-service HTTP hops), with deadlines backdated rather
than waited out.

#### Automated Check Results

| Check | Command | Result |
|---|---|---|
| TypeScript | `docker exec frontend sh -lc 'cd /app && npx tsc --noEmit'` | **PASS** — no diagnostics, `TSC_EXIT=0` |
| Frontend build | `docker exec frontend sh -lc 'cd /app && npm run build'` | **PASS** — `built in 35.18s` |
| Python syntax | `python -m compileall -q app` in battle-, character-, inventory-, locations-, dungeon- and character-attributes-service | **PASS** — `compileall OK` in all six |
| pytest battle-service | `python -m pytest app/tests -q` | **PASS** — `490 passed, 4 skipped` (the 4 skips are the cross-service guard queries, which need the sibling repos mounted; verified live instead, see below) |
| pytest locations-service | `python -m pytest app/tests -q` | **PASS** — `1133 passed` |
| pytest character-service | `python -m pytest app/tests -q` | **PASS** — `953 passed, 1 skipped` |
| pytest inventory-service | `python -m pytest app/tests -q` | **PASS** — `466 passed` |
| pytest dungeon-service | `python -m pytest app/tests -q --junitxml` | **PASS** — junit attrs `{'tests': '123', 'failures': '0', 'errors': '0', 'skipped': '0'}` (its conftest calls `os._exit`, so the count is read from the XML, not the summary line) |
| FEAT-163 suites alone | `pytest app/tests/test_admin_freeze.py app/tests/test_turn_timeout.py app/tests/test_finalize_extraction.py -q` | **PASS** — `85 passed, 4 skipped` |
| Alembic | `docker exec battle-service alembic current` | **PASS** — `006_dropout_admin_freeze (head)`; `version_table="alembic_version_battle"` unchanged (`alembic/env.py:64,75`); live DB shows `battle_participants.dropped_out_at datetime NULL`, `battles.pause_reason varchar(255) NULL`, `battles.paused_by_admin tinyint(1) NOT NULL DEFAULT 0` |
| nginx (dev) | `docker exec api-gateway nginx -t` | **PASS** — `syntax is ok` / `test is successful` |
| nginx (prod) | `nginx.prod.conf` loaded as `/etc/nginx/nginx.conf` in a throwaway `nginx:alpine` on the compose network with stub certs | **PASS** — `syntax is ok` / `test is successful` |
| compose (dev) | `docker compose config -q` | **PASS** |
| compose (dev+prod) | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q` | **PASS** |
| compose env resolution | resolved JSON compared dev vs prod | **PASS** — battle-service carries all five (`TURN_TIMEOUT_HOURS=24`, `BATTLE_STATE_TTL_HOURS=48`, `BATTLE_TIMEOUT_SWEEPER_ENABLED=1`, `BATTLE_TIMEOUT_SWEEP_INTERVAL_SECONDS=60`, `BATTLE_TIMEOUT_RECONCILE_EVERY=60`) in **both** files with identical values; `INTERNAL_SERVICE_TOKEN` resolves for dungeon-service in **both** (prod redefines that service's whole environment block and still sets it). The set of services carrying `INTERNAL_SERVICE_TOKEN` is identical between dev and prod (8 services, `missing in prod: []`) |

#### Live Verification Results — the substance

The live sweeper is genuinely running inside the container:
`Turn-timeout sweeper started (interval=60s, reconcile every 60 ticks, timeout=24h, state TTL=48h)`.
Six throwaway characters (`900001`-`900006`) and four throwaway battles were used; every row, Redis
key and Mongo document created for these checks has been deleted (see Cleanup).

**1. A 1v1 timeout ends the battle and releases the lock for both.** Battle 194, deadline backdated
one hour. No manual call — the live loop picked it up on its own tick:
`Sweeper: battle 194 finished by timeout of participant 409 (winner_team=2)`.
- `battles.status = finished`
- `battle_participants`: `409 -> dropped_out_at 2026-09-14 03:09:21`, `410 -> NULL`
- `battle_history`: `900001 defeat`, `900002 victory`
- `battle:deadlines` empty for the battle
- Mongo turn log carries `{"event":"participant_timed_out","who":409,"character_id":900001}` followed by `participant_defeated` and `battle_finished`
- **Lock:** `inventory.is_character_in_battle` returned `False` for both 900001 and 900002 — the real predicate, not a proxy.

**2. A team battle keeps going and only the dropout is released.** Battle 195, 3v3, first actor
backdated. Live loop: `Sweeper: participant 411 dropped out of battle 195; next actor 412`.
- `battles.status` stayed `in_progress`, `battle_history` count `0`
- only `411` carries `dropped_out_at`; 412-416 are `NULL`
- `battle:deadlines` holds exactly one member, `195:412`
- **All four guard predicates queried directly in their own containers** (not a proxy, not a mock):

  | Service | Predicate | dropout 900001 | teammate 900002 | opponent 900004 |
  |---|---|---|---|---|
  | inventory-service | `crud.is_character_in_battle` | `False` | `True` | `True` |
  | locations-service | `main.check_not_in_battle` | allowed | 400 «Действие заблокировано во время боя» | 400 |
  | character-service | `main._is_in_battle` | `False` | `True` | `True` |
  | battle-service | `crud.get_active_battle_for_character` | `None` | `195` | `195` |

**3. Idempotency — two sweeps drop nobody twice.**
- `handle_expired_turn` called twice on an already-dropped member -> `not_current_actor` / `not_current_actor`; the full `battle_participants` snapshot before and after compared **identical**, `next_actor` and `turn_number` unchanged, `battle_history` still 0 rows.
- Stronger case: the same due member re-armed and `_sweep_due_deadlines` run twice back to back. Both passes reported `handled=1`, yet the stamp snapshots were identical (`412 -> 03:11:16` both times), `next_actor` stayed `413`, and the ZSET ended with exactly one member.

**4. A frozen battle is never swept, and the reconciliation pass skips it — same age, different outcome.**
Two battles created, both aged to `updated_at = now - 100h` (well past the 48 h TTL) and both with
their Redis state key deleted. One frozen (`is_paused=1`), one not. `_reconcile_stale_battles` ->
`recovered: 1`:
- frozen 196 -> still `in_progress`, participants unstamped
- wedged 197 -> `finished`, both participants stamped `dropped_out_at`

This is the guard that would otherwise destroy legitimate freezes, and it demonstrably holds.

**5. The keep-alive extends the frozen battle's state TTL.** `TTL before keep-alive: 60` ->
`_keep_alive_frozen_battles` -> `refreshed count: 1`, `TTL after keep-alive: 172800`
(= `BATTLE_STATE_TTL_HOURS * 3600`). Without it a freeze would silently stop working past 48 h.

**6. Unfreeze restores the remaining time, not a fresh 24 hours.** The remainder was set to a
distinctive `3600.0` s, then `POST /battles/admin/195/unfreeze` was called over the api-gateway:
`{"ok": true, "is_paused": false, "message": "Бой разморожен"}`; the new `deadline_at` was
**3600.1 s** from the call, not 86400. A reset would have looked like success; it did not happen.

**7. The admin-typed reason reaches every render site, and the endpoints are guarded.**
`POST /battles/admin/195/freeze {"reason": "Игрок в отъезде до понедельника, противник согласен"}`:
- MySQL `battles`: `is_paused=1, paused_by_admin=1, pause_reason='Игрок в отъезде до понедельника, противник согласен'` (correct UTF-8, verbatim)
- Redis state: `paused=True`, `pause_reason` identical, `remaining_deadline_seconds=86386.5`
- `battle:deadlines` **empty** — the timer genuinely stopped and the sweeper is blind to it
- `GET /battles/195/state` -> `runtime.is_paused=True`, `runtime.paused_reason` = the admin's text
- `GET /battles/195/spectate` -> same
- `_build_runtime(state)` (the WS `battle_state` payload) -> same
- the fourth site is `pause_battle`'s `battle_paused` publish, which sends `reason` (`main.py:1680`) and is consumed by `useBattleWebSocket.ts:174-184` into `runtime.paused_reason`
- **Permission:** unauthenticated `freeze` / `unfreeze` / `force-finish` all returned **401**. Both endpoints use `Depends(require_permission("battles:manage"))` (`main.py:4158`, `:4193`), the same dependency as force-finish; the 403-for-an-authenticated-user-without-the-permission case is covered by `test_admin_freeze.py::test_freeze_403_without_battles_manage` and `::test_unfreeze_403_without_battles_manage`. I did not reproduce that one live because the only way to do so here was to overwrite a real (prod-dump) user's password hash, which I declined to do.

**8. `/characters/internal/` behind `verify_internal_token` — the real callers still work.**
14 routes carry `Depends(verify_internal_token)` (`character-service/app/main.py`); a static scan of
every `characters/internal` call site outside character-service found **22 sites, 0 without the
token in scope**. Live, from inside each real caller container, using that caller's own header helper:

| Caller -> route | with header | without header |
|---|---|---|
| locations-service -> `try-spawn` (mob spawn) | `200 {"spawned":false}` | `401 Недействительный internal token` |
| battle-service -> `record-mob-kill` (mob kill) | `422` (reached the handler, body validation) | `401` |
| dungeon-service -> `spawn-dungeon-mobs` (dungeon entry) | `400 «шаблоны не найдены»` (reached the handler) | `401` |

The sweeper's own 1v1 finish also exercised this for real: its `GET /characters/internal/mob-reward-data/900001`
answered `404`, not `401` — the header is being sent on the live path.
Externally, nginx refuses both dev routes: `http://localhost/characters/internal/try-spawn -> 403`,
`.../mob-reward-data/1 -> 403`.

**9. Additive contract.** `dropped_out` appears on every participant in `GET /battles/{id}/state`
and in `GET /battles/internal/{id}/state` — the endpoint autobattle-service actually consumes
(`autobattle-service/app/clients.py:15`), which parses untyped JSON and reads only `next_actor` and
resources, so the extra key is inert. Verified live from inside the autobattle-service container:
participant keys `['character_id','cooldowns','dropped_out','energy','fast_slots','hp','mana','max_energy','max_hp','max_mana','max_stamina','stamina','team']`.

#### Code standards

- Pydantic **v1** throughout: `AdminFreezeRequest.reason: Optional[str] = Field(None, max_length=255)`, `dropped_out: bool = False`; no `model_config` anywhere in `schemas.py`.
- No `React.FC` in any touched frontend file; no new `.jsx`; no SCSS added — the pause banner, the log branch and the freeze control are all Tailwind with `sm:` breakpoints and `break-words`.
- Frontend errors are always surfaced: both `handleFreeze` and `handleUnfreeze` toast a Russian message on failure, and the "still paused, join request pending" 200 is shown with an info toast rather than treated as an error (`AdminBattlesPage.tsx:274-316`).
- The freeze control is gated on `hasPermission(permissions, 'battles:manage')`, not on a role (`AdminBattlesPage.tsx:225`).
- The admin reason is rendered as plain text; no `dangerouslySetInnerHTML` on that path. `_validate_pause_reason` strips, rejects control characters (`ch < " "` or DEL) and caps at 255.
- All changed Vite modules compile: `BattlePage.tsx`, `BattlePageBar.tsx`, `AdminBattlesPage.tsx`, `api/battles.ts`, `useBattleWebSocket.ts` -> HTTP 200 each from the dev server.
- QA coverage is present and real: tasks 9-11 are DONE, 89 new tests across `test_turn_timeout.py`, `test_admin_freeze.py` and `test_finalize_extraction.py`, including the explicitly named backdated-deadline and idempotency cases.
- `docs/ISSUES.md` reflects the post-fix state: the ZSET/timeout entry is marked DONE with the fix described, the `forfeit` dead-enum note is present as LOW, and a new honest LOW note records the bounded window where a lost ZSET member is only recovered after the state key expires.

#### Issues Found

None blocking.

#### Notes (non-blocking, recorded deliberately)

| # | File:line | Observation | Owner |
|---|---|---|---|
| N1 | `services/battle-service/app/main.py:3983-4072` | Task 6's acceptance text put "stamp `dropped_out_at`" and "notify each non-NPC participant with `reason`" **inside** `_force_finish_battle`; the implementation puts both **around** it, in `_abandon_finish_battle` (`main.py:5048-5070`). The feature's own player-facing contract (3.9) is therefore fully met on the timeout/abandon path. The only difference is that the admin *force-finish button* still sends no notification — exactly as before this feature, so there is no regression. Recorded rather than failed; if PM wants the notification on that path too it is a two-line follow-up. | Backend Developer |
| N2 | 3.4 | The accepted deploy-ordering window stands: during a single `docker compose up --build -d`, an inventory/movement/character request can briefly hit `Unknown column 'bp.dropped_out_at'` until battle-service's `alembic upgrade head` completes. Transient, self-healing, no data risk. Worth bringing battle-service up first on a hand deploy. | DevSecOps |
| N3 | 3.11 | A `pvp_death` battle lost by timeout still destroys the character, by explicit user ruling. The admin freeze is the escape valve. Restated here so it is not later mistaken for a bug. | — |

#### Not verified — no browser available

The `claude-in-chrome` skill reported that the extension is not set up, and no `chrome-devtools` MCP
is connected, so **no page was opened in a browser**. Everything reachable without one was checked
(`tsc`, `npm run build`, Vite compiling each changed module, the API payloads that feed the UI, and
the component source). The following need a human with a browser:

1. The pause banner on the battle page visually showing the admin's typed reason (the API field it
   reads was confirmed to carry that text; only the render was not observed).
2. The battle-log line «{Имя} не успел сделать ход и выбыл из боя.» rendering in `BattlePageBar`
   (the Mongo event and the render branch were both confirmed; the pixels were not).
3. The Freeze / Unfreeze controls on the admin battles page — visible for an admin, hidden for a
   user without `battles:manage`, the reason input, and the toast texts.
4. Zero console errors and no 4xx/5xx in the network tab on those two pages.
5. Layout at a 360 px viewport for the banner, the log line and the freeze form.

#### Cleanup

All test data removed: battles 194-197 and their `battle_participants`, `battle_history` and
`battle_join_requests` rows; characters 900001-900006 and their `character_attributes`; the
notifications those runs produced; Redis `battle:19*:state|snapshot|turns|timeout:lock` keys and every
`battle:deadlines` member (the ZSET is now empty); 3 Mongo `battle_logs` documents; all scratch
scripts inside the containers. Final counts verified: `battles>=194 -> 0`, `characters 900001-900006
-> 0`, `battle_history -> 0`.

**Verdict: the feature is ready to ship**, with the single caveat that the browser-side checks listed
above have not been performed and should be eyeballed once by a human.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-14 — PM: баг подтверждён экспериментом, не рассуждением
[LOG] 2026-09-14 — PM: требования уточнены у пользователя (выбывание, командные бои, 24 часа)
[LOG] 2026-09-14 — Architect: начал проектирование, статус → IN_PROGRESS
[LOG] 2026-09-14 — Architect: ссылки из раздела 2 перепроверены по текущему коду — совпадают; найдены две поправки: TURN_TIMEOUT_HOURS уже есть в config.py:11 (не хватает переменной в compose), блокировка проверяется в четырёх сервисах, а не в одном
[LOG] 2026-09-14 — Architect: решение по размещению обработчика — фоновый asyncio-цикл внутри battle-service, не Celery beat (у celery-worker нет доступа к MySQL, вся боевая логика асинхронна, прецедент уже есть в main.py:4645)
[LOG] 2026-09-14 — Architect: решение по forfeit — не использовать; статус боя остаётся finished, факт выбывания пишется в новую колонку battle_participants.dropped_out_at
[LOG] 2026-09-14 — Architect: выбывание выражено как поражение участника и прогоняется через СУЩЕСТВУЮЩИЕ завершения — два механических выноса (_finalize_battle и _force_finish_battle), параллельная ветка завершения не пишется
[LOG] 2026-09-14 — Architect: истёкшее состояние Redis решено двумя путями — принудительное завершение по записи из множества и почасовая сверка по MySQL (она же чинит уже зависшие бои на проде)
[LOG] 2026-09-14 — Architect: снятие блокировки спроектировано явно — status=finished для боя 1×1 и dropped_out_at для командного, четыре предиката в четырёх сервисах
[LOG] 2026-09-14 — Architect: идемпотентность — три независимых слоя (атомарный ZREM, отдельный лок на каждый бой, перепроверка состояния); тесты на просроченный дедлайн и повторный проход обязательны
[LOG] 2026-09-14 — Architect: проектирование завершено — 12 задач, 0 новых эндпоинтов, 1 миграция, 2 вопроса к PM (последствия pvp_death при просрочке, награды выбывшему)
[LOG] 2026-09-14 — PM: пользователь ответил — правило про смертельный бой остаётся, награды выбывшему не начисляются; добавлена заморозка боя администратором
[LOG] 2026-09-14 — Architect: механика паузы проверена — таймер действительно останавливается (ZREM при паузе, восстановление остатка при снятии), переписывать нечего
[LOG] 2026-09-14 — Architect: найдено, что причина паузы зашита в ЧЕТЫРЁХ местах (:1349, :1434, :1624 и ещё :4603), а не в трёх
[LOG] 2026-09-14 — Architect: resume_battle_if_ready действительно с условием — снятие админской заморозки решено флагом battles.paused_by_admin, отдельная функция снятия не пишется
[LOG] 2026-09-14 — Architect: проверено, а не предположено — баннер паузы на фронте игнорирует уже проброшенный paused_reason и печатает зашитый текст; это правка, а не подтверждение
[LOG] 2026-09-14 — Architect: взаимодействие со сборщиком — по множеству дедлайнов замороженный бой невидим (подтверждено), но сверка по MySQL его бы съела: добавлено условие is_paused = 0
[LOG] 2026-09-14 — Architect: найдена более глубокая проблема — заморозка дольше 48 часов теряла состояние в Redis и снятие ничего не восстанавливало; решено продлением TTL замороженных боёв на каждом такте сборщика
[LOG] 2026-09-14 — Architect: заморозка спроектирована — 2 админских эндпоинта на battles:manage, 3 колонки в одной миграции, задач стало 17
[LOG] 2026-09-14 01:20 — Backend Dev: задача #1 — добавлен ZREM предыдущего ходившего перед ZADD следующего (main.py); множество battle:deadlines больше не растёт
[LOG] 2026-09-14 01:20 — Backend Dev: задача #2 — в Settings добавлены BATTLE_TIMEOUT_SWEEPER_ENABLED=1, BATTLE_TIMEOUT_SWEEP_INTERVAL_SECONDS=60, BATTLE_TIMEOUT_RECONCILE_EVERY=60 (стиль Pydantic v1, requirements.txt не тронут)
[LOG] 2026-09-14 01:20 — Backend Dev: задача #3 — пять переменных добавлены в блок battle-service обоих compose-файлов; docker compose config проходит для dev и dev+prod, значения совпадают
[LOG] 2026-09-14 01:20 — Backend Dev: задача #4 — миграция 006_dropout_admin_freeze (battle_participants.dropped_out_at, battles.pause_reason, battles.paused_by_admin), down_revision = 005_battle_parties; прогон upgrade → downgrade -1 → upgrade выполнен на MySQL 8, version_table остался alembic_version_battle
[LOG] 2026-09-14 01:20 — Backend Dev: задача #5 — во все четыре предиката активного боя добавлено AND bp.dropped_out_at IS NULL (locations, character, inventory, battle); проверено на живом бою: выбывший разблокирован во всех четырёх сервисах, его напарник по-прежнему заблокирован
[LOG] 2026-09-14 01:45 — Backend Dev: новая колонка сломала 166 существующих тестов в character-service и inventory-service — их фикстуры создают собственные зеркала battle_participants в SQLite; в 15 CREATE TABLE добавлено dropped_out_at DATETIME (только схема, ни одного теста не написано и не изменено по смыслу)
[LOG] 2026-09-14 01:50 — Backend Dev: задачи #1-#5 завершены; прогоны: battle-service 405 passed, locations-service 1091 passed, character-service 925 passed + 1 skipped, inventory-service 466 passed (это же и базовый уровень); тестовые строки и ключи Redis убраны
[LOG] 2026-09-14 01:45 — Backend Dev: начал задачу #6 (чистый вынос двух завершений, поведение менять нельзя)
[LOG] 2026-09-14 01:46 — Backend Dev: вынос A — блок `if battle_finished:` (main.py:2494-2797) перенесён ПОСЛОВНО в модульную корутину `_finalize_battle(db_session, battle_id, battle_state, winner_team, turn_events, turn_number, by_timeout=False) -> BattleRewards | None`; переименован ровно один локальный `new_turn_number` → параметр `turn_number`; сверка diff'ом показала побайтовое совпадение перенесённых строк
[LOG] 2026-09-14 01:47 — Backend Dev: вынос B — тело `admin_force_finish_battle` перенесено в `_force_finish_battle(db, battle_id, state, reason=None)`; эндпоинт остался тонкой обёрткой (валидация, load_state, лог с именем админа, тот же ответ), путь/метод/права/схема ответа не тронуты
[LOG] 2026-09-14 01:48 — Backend Dev: единственное изменение поведения в выносе B — при `state=None` участники берутся из MySQL `battle_participants`, и записи из `battle:deadlines` наконец удаляются; раньше принудительное завершение боя с истёкшим состоянием оставляло их навсегда
[LOG] 2026-09-14 01:49 — Backend Dev: уведомления участникам и простановка `dropped_out_at` при abandon-finish НЕ добавлены — это часть задачи #8 (её критерии приёмки прямо включают уведомления из 3.9); задача #6 остаётся чистым выносом
[LOG] 2026-09-14 01:52 — Backend Dev: проверка не рассуждением — реальный бой прогнан до смертельного удара на СТАРОМ коде и на новом одним и тем же сценарием; вывод совпал полностью: status=finished, две строки battle_history (victory/defeat), синхронизация ресурсов (проигравший в pvp_training → HP 1), накопительная статистика, Redis TTL 300, ZSET пуст, события лога Mongo идентичны
[LOG] 2026-09-14 01:52 — Backend Dev: принудительное завершение проверено дважды — с живым состоянием Redis (вывод идентичен старому) и с удалённым ключом состояния (было: записи 181:377 и 181:378 остались в множестве; стало: множество пусто, в логе «2 participant(s) enumerated from MySQL»)
[LOG] 2026-09-14 01:53 — Backend Dev: задача #6 завершена; py_compile проходит, весь набор battle-service — 405 passed (базовый уровень), тестовые персонажи, бои, ключи Redis и документы Mongo убраны
[LOG] 2026-09-14 02:05 — Backend Dev: начал задачу #7 (динамическая причина паузы + админская заморозка)
[LOG] 2026-09-14 02:05 — Backend Dev: pause_battle получил параметры reason и by_admin — пишет battles.pause_reason / paused_by_admin в MySQL, зеркалит state["pause_reason"] в Redis рядом с существующим state["paused"], и отдаёт причину в WS-рассылке battle_paused
[LOG] 2026-09-14 02:05 — Backend Dev: зашитая причина убрана из всех ЧЕТЫРЁХ мест — get_state (battle_record.pause_reason, без лишнего запроса), spectate_battle (то же), pause_battle (переданное значение), _build_runtime (state.get("pause_reason")); у каждого есть запасной текст заявки для боёв, поставленных на паузу до появления колонки
[LOG] 2026-09-14 02:06 — Backend Dev: пятое место найдено и исправлено — отказ в действии (main.py:2072) говорил про заявки на присоединение даже замороженному игроку; теперь подставляется реальная причина, слово «приостановлен» в тексте сохранено
[LOG] 2026-09-14 02:06 — Backend Dev: resume_battle_if_ready первым делом читает battles.paused_by_admin и выходит с False — одобрение или отклонение заявки больше не снимает админскую заморозку; отдельной функции снятия не написано
[LOG] 2026-09-14 02:06 — Backend Dev: добавлены POST /battles/admin/{id}/freeze и /unfreeze на require_permission("battles:manage"), схемы AdminFreezeRequest/AdminFreezeResponse в стиле Pydantic v1; снятие сбрасывает флаг и вызывает тот же resume_battle_if_ready, а при висящей заявке честно отвечает «Бой остаётся на паузе…» и понижает причину до заявочной
[LOG] 2026-09-14 02:06 — Backend Dev: найдена и закрыта скрытая потеря времени — повторная пауза уже приостановленного боя пересчитывала остаток от устаревшего deadline_at и обнуляла его; теперь при повторной паузе остаток сохраняется (это же делает заморозку поверх заявочной паузы безопасной)
[LOG] 2026-09-14 02:07 — Backend Dev: живая проверка на бою 189 — заморозка с введённой админом причиной дошла до MySQL, состояния Redis, ответа runtime и WS-рассылки (все четыре места); действие отклонено с этой же причиной; множество battle:deadlines пусто
[LOG] 2026-09-14 02:07 — Backend Dev: живая проверка остатка — на заморозке сохранено 86371.18 с, после снятия дедлайн отстоит на 86371.34 с (а не на свежие 86400); второй цикл: заморозка на 5 с сдвинула дедлайн на 6 с, осталось 86358 с
[LOG] 2026-09-14 02:07 — Backend Dev: живая проверка стыка с заявками — бой заморожен, подана заявка, заявка отклонена админом: бой ОСТАЛСЯ заморожен (is_paused=1, paused_by_admin=1, причина админская); снятие заморозки при висящей заявке вернуло is_paused=true и сообщение «Бой остаётся на паузе: рассматривается заявка на присоединение»
[LOG] 2026-09-14 02:07 — Backend Dev: права и валидация проверены вживую — 403 обычному пользователю и 401 анониму на обоих эндпоинтах, 404 на несуществующем бою, 400 на завершённом, 422 на причине длиннее 255 символов, 400 на управляющих символах, пустая причина → «Бой заморожен администратором»
[LOG] 2026-09-14 02:08 — Backend Dev: задача #7 завершена; py_compile в контейнере проходит, весь набор battle-service — 405 passed (базовый уровень); в фикстуру _make_battle в test_spectate.py добавлены поля pause_reason/paused_by_admin (иначе MagicMock подставлял объект вместо строки), тестовый бой, ключи Redis, документ Mongo и временный пользователь удалены
[LOG] 2026-09-14 02:08 — Backend Dev: задаче #8 передано — сверка по MySQL должна нести AND is_paused = 0, а на каждом такте нужен EXPIRE battle:{id}:state для боёв с status='in_progress' AND is_paused=1, иначе заморозка дольше 48 часов теряет состояние; со стороны задачи #7 всё для этого готово: is_paused и pause_reason живут в MySQL и переживают истечение ключа
[LOG] 2026-09-14 02:10 — Backend Dev: начал задачу #8 (сборщик просроченных ходов)
[LOG] 2026-09-14 02:12 — Backend Dev: цикл `_deadline_sweeper_loop` поднят из нового startup-хука рядом с подписчиком WS, под выключателем BATTLE_TIMEOUT_SWEEPER_ENABLED, с совещательной арендой в Redis (свою же аренду процесс продлевает, чужую уважает) и с обёрткой «никогда не умирать» на каждом такте; такт открывает собственную сессию AsyncSessionLocal и делает три вещи — разбор просроченных дедлайнов, продление TTL замороженных боёв, и раз в BATTLE_TIMEOUT_RECONCILE_EVERY тактов сверку по MySQL
[LOG] 2026-09-14 02:12 — Backend Dev: выбывание выражено как поражение (hp=0 / defeated / dropped_out) и отдано штатному разбору после хода — параллельного завершения не написано ни строчки; один на один остаётся одна живая команда и работает `_finalize_battle`, в командном бою живых команд несколько и ход просто уходит дальше по очереди, а «выбыл последний из команды» не потребовал отдельного кода
[LOG] 2026-09-14 02:16 — Backend Dev: живая проверка боя один на один (бой 190, участники 395/209 и 396/211) — дедлайн состарен на час, сборщик сработал сам на ближайшем такте: status=finished, победа команде 2, battle_history — defeat персонажу 209 и victory персонажу 211, синхронизация ресурсов как при обычной победе (pvp_training опустил HP проигравшего до 1), в Mongo ход с событиями participant_timed_out + participant_defeated + battle_finished, множество battle:deadlines пусто, ключ состояния переведён на 300 с
[LOG] 2026-09-14 02:16 — Backend Dev: главное в фиче — блокировка снята с ОБОИХ: inventory-service, locations-service и character-service дружно отвечают «не в бою» для 209 и 211 (до срабатывания оба были заблокированы)
[LOG] 2026-09-14 02:17 — Backend Dev: живая проверка командного боя 3×3 (бой 191) — выбыл только просрочивший (участник 397, персонаж 11), бой остался in_progress, ход перешёл к следующему живому по очереди (участник 402), выставлен свежий дедлайн; dropped_out_at проставлен ровно одной строке из шести, выбывший разблокирован, пятеро остальных по-прежнему заблокированы
[LOG] 2026-09-14 02:17 — Backend Dev: идемпотентность в трёх независимых слоях и каждый доказан отдельно — (1) атомарная заявка ZREM: два одновременных прохода по одному элементу дали 1 и 0, выбывание ровно одно; (2) взаимное исключение по бою: два одновременных SET NX дали одного владельца; (3) предусловия внутри обработчика при полностью обойдённых слоях 1 и 2: `not_current_actor`, `already_out`, `deadline_not_passed` — ни одной новой строки dropped_out_at, ни одной новой строки battle_history
[LOG] 2026-09-14 02:17 — Backend Dev: сверка по MySQL несёт AND is_paused = 0, как и просила задача #7 — проверено на паре боёв с ОДИНАКОВЫМ возрастом (5 дней) и одинаково удалённым ключом состояния: незамороженный застрявший бой восстановлен (finished, всем шестерым проставлен dropped_out_at, множество вычищено, все уведомлены), замороженный не тронут вообще
[LOG] 2026-09-14 02:17 — Backend Dev: продление TTL замороженных боёв работает — TTL ключа состояния принудительно снижен до 120 с, один такт вернул его к 172800 с; заморозка теперь переживает BATTLE_STATE_TTL_HOURS
[LOG] 2026-09-14 02:17 — Backend Dev: замороженный бой не подметается дважды — заморозка убирает все записи из множества (проверено), а подброшенная вручную просроченная запись даёт `paused` и ничего не меняет
[LOG] 2026-09-14 02:18 — Backend Dev: живучесть — четыре подряд упавших такта не убили цикл (задача жива, отменяется чисто); упавший обработчик возвращает свою запись в множество с исходным счётом, следующий проход её доедает; битая запись вида «not-a-member» удаляется и не роняет такт
[LOG] 2026-09-14 02:18 — Backend Dev: уведомления по 3.9 доставлены вживую — выбывшему «Вы не сделали ход за отведённое время и выбыли из боя.», остальным «{Имя} не успел сделать ход и выбыл из боя.», при abandon-finish всем «Бой завершён: истёк срок ожидания хода.»; NPC исключены
[LOG] 2026-09-14 02:18 — Backend Dev: dropped_out добавлен в участников runtime (get_state, get_state_internal, spectate, _build_runtime → WS battle_state) и описан схемой BattleRuntimeParticipant в schemas.py; поле необязательное со значением False, старые бои и текущий фронт работают без изменений
[LOG] 2026-09-14 02:18 — Backend Dev: простановка dropped_out_at и уведомления при abandon-finish сделаны в обёртке сборщика, а не внутри `_force_finish_battle` — админская кнопка принудительного завершения осталась побайтово прежней (критерий приёмки задачи #6)
[LOG] 2026-09-14 02:19 — Backend Dev: задача #8 завершена; py_compile в контейнере проходит, весь набор battle-service — 405 passed (базовый уровень); тестовые бои 190-192, строки battle_history, ключи Redis, документы Mongo и уведомления убраны, HP персонажа 209 возвращён, множество battle:deadlines пусто
[LOG] 2026-09-14 — Frontend Dev: начал задачи #12, #13, #14
[LOG] 2026-09-14 — Frontend Dev: задача #12 — в BattlePageBar.tsx добавлена ветка `participant_timed_out` («{Имя} не успел сделать ход и выбыл из боя.»); проверено, что раньше событие падало в общий хвост и печаталось сырым именем, потому что в BATTLE_EVENTS_TRANSLATE его нет. Тип события в файле — `event: string` с индексной сигнатурой, объединения расширять не потребовалось, в useBattleWebSocket.ts правок нет
[LOG] 2026-09-14 — Frontend Dev: заодно добавлена ветка `participant_defeated` — событие эмитится в паре с выбыванием (main.py:5138), и без ветки лог этой самой фичи показывал бы «{Имя} participant_defeated» сразу под человеческой строкой
[LOG] 2026-09-14 — Frontend Dev: задача #13 (баг) — баннер паузы в BattlePage.tsx больше не игнорирует `paused_reason`. Сделан в два ряда: заголовок «Бой приостановлен» и причина отдельной строкой. Отступление от буквы критерия (единая фраза с «— рассматриваются заявки…»): подстановка произвольного админского текста в середину фразы давала «Бой приостановлен — Бой заморожен администратором». Старая фраза целиком сохранена как запасной вариант при `paused_reason === null`. Рендер только текстом, без dangerouslySetInnerHTML
[LOG] 2026-09-14 — Frontend Dev: обе ветки и баннер не описаны, а выполнены — реальные блоки вырезаны из исходников, собраны esbuild и отрисованы react-dom/server; вывод приложен в отчёте PM (админская причина, причина заявки, дефолт админа и null)
[LOG] 2026-09-14 — Frontend Dev: задача #14 — freezeBattle/unfreezeBattle в api/battles.ts и блок заморозки на админской странице боёв рядом с принудительным завершением; поле причины (maxLength 255) с подсказкой, что её увидят игроки. Ответ unfreeze с `is_paused: true` показывается как информация (toast с ℹ️), а не как ошибка; любая сетевая/4xx/5xx ошибка — toast.error с русским текстом. Контрол целиком скрыт без `battles:manage`
[LOG] 2026-09-14 — Frontend Dev: расхождение контракта — ни `AdminBattleListItem`, ни словарь `battle` в `GET /battles/admin/{id}/state` не отдают `is_paused`/`pause_reason` (сверено с живым /openapi.json, совпадает с кодом). Состояние кнопок взять неоткуда, поэтому до первого ответа freeze/unfreeze показываются обе кнопки, а поля типизированы как необязательные — как только бэкенд начнёт их отдавать, состояние подхватится само. Не адаптировал молча: нужен отдельный backend-фикс
[LOG] 2026-09-14 — Frontend Dev: проверка в контейнере frontend — `npx tsc --noEmit` без ошибок, `npm run build` успешен (✓ built in 34.86s); задачи #12, #13, #14 завершены
[LOG] 2026-09-14 — Backend Dev: задача #16 — `docs/services/battle-service.md` описан по РЕАЛЬНОМУ коду, не по разделу 3: свипер и три его дела за тик (`main.py:5225/5285/5310`, цикл `:5379`, старт `:5400`, аренда `:5351`), приём «выбывание = поражение → существующая резолюция» с явным предупреждением не добавлять ветки 1×1/командный, три слоя идемпотентности (и почему второй — сужение, а не гарантия), `AND is_paused = 0` в сверке с причиной (пауза не двигает `updated_at`: сырой SQL мимо ORM-`onupdate`, у колонки нет `ON UPDATE CURRENT_TIMESTAMP`), keep-alive замороженных боёв, оба админских эндпоинта, три колонки, миграция 006 и все пять переменных окружения
[LOG] 2026-09-14 — Backend Dev: все `file:line` в документации сверены с исходниками; расхождение с разделом 3 — `forfeit` читается на `main.py:4072` и `:4391` (в разделе 2/3 указано `:3863, 4104`), `resume_battle_if_ready` вызывается из обработки заявок на `:4498` и `:4562` (в разделе 3.12 — `:4211, :4275`); нумерация уехала после выносов задачи #6, поведение то же
[LOG] 2026-09-14 — Backend Dev: задача #15 — HIGH-запись про ZSET без читателя помечена DONE (FEAT-163) в `docs/ISSUES.md`; добавлены две LOW-записи: мёртвое значение `BattleStatus.forfeit` (с обоснованием, почему фича им не воспользовалась) и честно заявленное ограничение свипера — бой, потерявший запись в ZSET при живом ключе состояния, подхватится только после истечения этого ключа
[LOG] 2026-09-14 — Backend Dev: MEDIUM-запись про `is_paused`/`pause_reason` в админских эндпоинтах уже заведена Frontend Dev — не дублировал. Обновлены `docs/ARCHITECTURE.md` (свипер как фоновая задача, новые колонки) и таблица статистики в ISSUES.md, разошедшаяся с содержимым (было 15, фактически 62)
[LOG] 2026-09-14 — QA: начал задачи 9, 10 и 11 — тесты таймаута хода, заморозки и регрессия рефакторинга
[LOG] 2026-09-14 — QA: базовый прогон battle-service до правок — 405 passed
[LOG] 2026-09-14 — QA: добавлен общий харнесс tests/_feat163_harness.py — FakeRedis с настоящей семантикой ZSET/SET NX и FakeDB, который интерпретирует условия WHERE (is_paused, updated_at, dropped_out_at), а не сравнивает строки целиком; схема сверена с реальной MySQL через SHOW COLUMNS
[LOG] 2026-09-14 — QA: задача 9 — tests/test_turn_timeout.py, 40 тестов: просроченный дедлайн, 1×1 с зачётом победы и историей, командный бой с передачей хода, выбывание последнего в команде, три слоя идемпотентности порознь, все предусловия, истёкшее состояние, сверка по MySQL, битый элемент ZSET, падение обработчика, живучесть цикла, аренда, снятие блокировки по четырём настоящим предикатам
[LOG] 2026-09-14 — QA: снятие блокировки проверяется не косвенно — SQL всех четырёх охранных запросов вынимается из исходников сервисов через ast и выполняется по SQLite-схеме, созданной из models.py
[LOG] 2026-09-14 — QA: задача 10 — tests/test_admin_freeze.py, 40 тестов: замороженный бой не подметается и не попадает в сверку (недельная заморозка без ключа состояния), keep-alive продлевает TTL, разморозка возвращает остаток времени, а не новые 24 часа, заявка на присоединение не снимает заморозку, причина доходит до всех мест отрисовки, права 403/404/400 и валидация причины
[LOG] 2026-09-14 — QA: задача 11 — tests/test_finalize_extraction.py, 9 тестов: _finalize_battle после добивающего удара даёт тот же наблюдаемый результат (статус, история, награды, синхронизация ресурсов и прочности, очистка Redis и ZSET, WS, save_log, накопительная статистика), by_timeout ничего не меняет; _force_finish_battle без состояния перечисляет участников из MySQL и чистит ZSET
[LOG] 2026-09-14 — QA: мутационная проверка на копии внутри контейнера (репозиторий не трогался) — убито 10 мутантов: снятие AND is_paused = 0 в сверке (2 теста), неучтённый результат ZREM (1), снятие мьютекса (1), отключение keep-alive (2), teams_alive <= 1 в обе стороны (по 4), снятие предусловий next_actor и paused (по 2), свежие 24 часа вместо остатка (3), отказ от перечисления участников из MySQL (3), потеря ZREM при передаче хода (1), отказ от фильтрации битых элементов (2), снятие AND bp.dropped_out_at IS NULL в охранном запросе (3)
[LOG] 2026-09-14 — QA: задачи 9, 10 и 11 готовы — 89 новых тестов, полный набор battle-service 490 passed, 4 skipped (пропускаются только кросс-сервисные охранные запросы: внутри контейнера смонтирован лишь battle-service; при запуске из репозитория и в CI они выполняются и проходят)
[LOG] 2026-09-14 — QA: настоящих багов не найдено; реальные Redis, MySQL и Mongo тестами не затрагиваются, чистить нечего
[LOG] 2026-09-14 — Reviewer: начал проверку задачи 17
[LOG] 2026-09-14 — Reviewer: автоматические проверки прогнаны заново самостоятельно — tsc и npm run build зелёные; compileall во всех шести затронутых сервисах; pytest battle 490 passed / 4 skipped, locations 1133, character 953 / 1 skipped, inventory 466, dungeon 123 (счёт снят из junitxml, т.к. conftest вызывает os._exit)
[LOG] 2026-09-14 — Reviewer: alembic current = 006_dropout_admin_freeze (head), version_table = alembic_version_battle не менялся; три новые колонки подтверждены в живой БД
[LOG] 2026-09-14 — Reviewer: nginx -t зелёный на обоих конфигах (прод проверен в отдельном контейнере с заглушечными сертификатами, иначе тест шёл мимо файла); docker compose config -q зелёный на dev и dev+prod; все пять переменных battle-service и INTERNAL_SERVICE_TOKEN у dungeon-service резолвятся в обоих окружениях
[LOG] 2026-09-14 — Reviewer: живая проверка 1×1 — дедлайн состарен, живой свипер сам завершил бой, победа противнику, история записана, ZSET очищен, блокировка снята у ОБОИХ (проверено настоящим предикатом inventory-service, не косвенно)
[LOG] 2026-09-14 — Reviewer: живая проверка командного боя 3×3 — бой продолжается, отметка только у просрочившего, ход передан дальше; все ЧЕТЫРЕ охранных предиката опрошены прямо в своих контейнерах: выбывший свободен, союзники и противники заблокированы
[LOG] 2026-09-14 — Reviewer: идемпотентность подтверждена вживую — два прохода подряд по одному и тому же элементу: снимки battle_participants до и после совпадают, next_actor и номер хода не сдвинулись, второй строки истории нет
[LOG] 2026-09-14 — Reviewer: ключевая проверка заморозки — замороженный и зависший бои созданы ОДНОГО возраста и оба без ключа состояния: сверка подняла только зависший, замороженный не тронут (это и есть охрана AND is_paused = 0)
[LOG] 2026-09-14 — Reviewer: keep-alive подтверждён — TTL состояния замороженного боя 60 с → 172800 с; без него заморозка молча умирала бы после 48 часов
[LOG] 2026-09-14 — Reviewer: разморозка возвращает ОСТАТОК, а не новые сутки — остаток выставлен в 3600 с, после разморозки дедлайн оказался в 3600.1 с, а не в 86400
[LOG] 2026-09-14 — Reviewer: причина, введённая админом, дошла до всех мест отрисовки (get_state, spectate, _build_runtime, WS-публикация) и хранится в MySQL в верном UTF-8; без токена оба эндпоинта отвечают 401, права battles:manage закрыты тестами 403
[LOG] 2026-09-14 — Reviewer: внутренние маршруты /characters/internal/ проверены вживую из настоящих вызывающих контейнеров — спавн моба, убийство моба и вход в подземелье проходят с заголовком и получают 401 без него; снаружи nginx отдаёт 403
[LOG] 2026-09-14 — Reviewer: браузерная проверка НЕВОЗМОЖНА — расширение claude-in-chrome не подключено; список того, что осталось посмотреть глазами, записан в раздел 5
[LOG] 2026-09-14 — Reviewer: все тестовые данные убраны — бои 194-197, персонажи 900001-900006, строки истории и уведомлений, ключи Redis, документы Mongo, временные скрипты в контейнерах
[LOG] 2026-09-14 — Reviewer: проверка завершена, результат PASS; блокирующих замечаний нет, три непреграждающие заметки записаны в раздел 5

```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что было

`TURN_TIMEOUT_HOURS` был декоративен. Дедлайн хода писался **в три места** и ни одним из них не
читался на предмет истечения. Доказано экспериментом, а не рассуждением: дедлайн состарили на час,
подождали — ничего; сделали просроченный ход — **принят как обычно**, с новым сроком на сутки.

Зависший бой блокировал **обоих** участников — и ушедшего, и его противника: нельзя выйти из
локации, собирать ресурсы, писать посты, начать новый бой, и заблокированы двенадцать операций с
инвентарём. Единственным выходом был админ с принудительным завершением.

### Что сделано

**Просрочил ход — выбываешь.** Не пропуск: при двух ушедших игроках пропуск передавал бы ход
бесконечно, и блокировка не снялась бы никогда. В бою один на один выбывание завершает бой,
в командном выбывает только просрочивший, остальные доигрывают.

Ключевое решение, благодаря которому фича осталась маленькой: **выбывание выражено как поражение**,
после чего запускается собственное штатное разрешение боя. Оба правила получаются сами, без
отдельных веток для «один на один» и «команда», и случай «выбыл последний в команде» тоже.

**Админская заморозка.** Идея пользователя: игрок предупреждает об отъезде, договаривается с
противником, админ замораживает бой. Механизм паузы уже существовал целиком — не хватало только
входа для админа и живой причины вместо захардкоженной строки.

**24 часа остались.** Обоснование пользователя: это одни реальные сутки, человек должен успеть
поспать и отработать день. Значение вынесено в настройки.

### Что нашлось по пути

- **Мест с захардкоженной причиной паузы оказалось пять, а не четыре.** Пятое — отказ при попытке
  хода: замороженному игроку сообщали про заявки на присоединение.
- **Повторная постановка на паузу съедала остаток времени хода** — пересчитывала его от
  устаревшего дедлайна, вплоть до нуля.
- **Снятие паузы могло сорваться само**: игрок подавал заявку на присоединение в замороженный бой,
  админ её рассматривал — и заморозка тихо снималась.
- **Заморозка перестала бы работать дольше двух суток.** Состояние боя в Redis живёт 48 часов, а
  заморозка по смыслу длится днями. Снятие после этого сняло бы флаг, не восстановив ни дедлайна,
  ни записи в очереди — и **отрапортовало бы об успехе**. Закрыто продлением жизни состояния.
- **Проход по базе уничтожал бы замороженные бои.** Пауза не обновляет время изменения записи, так
  что недельная заморозка выглядит для него ровно как зависший бой.
- **Неизвестные события в логе боя печатаются сырым именем**, а не пропускаются — без правки игрок
  увидел бы в логе `Имя participant_timed_out`.
- **Админский список боёв не отдаёт признак паузы вообще** — кнопке заморозки неоткуда узнать
  состояние. Обработано мягко, записано как задача.

Попутно, под зонтиком этой же работы, закрыты **все 14 внутренних маршрутов** character-service:
к шести защищённым добавлено восемь. Сервис подземелий впервые получил токен — его не было, и
причина оказалась в том, что **самого сервиса нет в таблице сервисов в CLAUDE.md**. Таблица
дополнена тремя недостающими сервисами.

### Проверка

- `battle-service` — **490** тестов (было 405), `locations-service` 1133, `character-service` 953,
  `inventory-service` 466, `dungeon-service` 123. Сборки фронта зелёные.
- Живьём: бой один на один завершается по таймауту и **снимает блокировку с обоих**; командный
  продолжается, освобождая только выбывшего — проверено настоящими предикатами всех четырёх
  сервисов, а не их заменителями.
- Замороженный и зависший бои одного возраста: восстановлен только зависший.
- Снятие заморозки вернуло **3600.1 секунды** остатка вместо 86400 — сброс выглядел бы успехом.
- Защита от повторного срабатывания доказана **послойно**: каждый из трёх слоёв проверен при
  отключённых двух других.
- Мутации реализации — десять вариантов поломки, все убиты нужными тестами.

### Оставшиеся риски / follow-up

- **В браузере ничего не проверялось** — расширение Chrome не подключено ни в одном ревью за
  сессию. Проверить руками: баннер паузы показывает причину, введённую админом; строка о выбывании
  в логе боя; кнопки заморозки на админской странице и их видимость по правам; чистая консоль;
  вёрстка на 360px.
- **Окно при выкате**: пока миграция battle-service не прошла, остальные сервисы обращаются к
  новой колонке. Принято сознательно.
- **Дуэль насмерть**: просрочка хода означает безвозвратную потерю персонажа. Это решение
  пользователя, а страховка — админская заморозка.
- В `ISSUES.md`: мёртвое значение `forfeit`; админские эндпоинты не отдают признак паузы;
  бой, потерявший запись в очереди при живом состоянии, дождётся уборки только после истечения
  состояния; у двух эндпоинтов нет ни одного теста.

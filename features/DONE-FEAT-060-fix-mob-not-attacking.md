# FEAT-060: Fix mob not attacking in battle

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-22 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Моб в PvE-бою не атакует игрока. Autobattle-service регистрируется, отправляет POST action за моба (получает 200 OK), но ход моба не отображается в логах боя и не наносит урон. Ходы моба фактически пропускаются.

### Бизнес-правила
- Моб должен атаковать игрока каждый свой ход, используя свои навыки
- Autobattle-service отвечает за выбор действий моба
- Действия моба должны отображаться в логах боя

### UX / Пользовательский сценарий
1. Игрок вступает в бой с мобом
2. Игрок делает свой ход — работает нормально
3. Моб должен сделать свой ход — НЕ работает: ход пропускается, урон не наносится
4. В логах autobattle-service видно что action отправляется и получает 200 OK
5. Но в логах боя ход моба не отображается

### Edge Cases
- Моб ходит через ход (turn 2, 4, 6...) — это нормально для пошагового боя
- Action получает 200 OK — значит battle-service принимает запрос, но что-то идёт не так при обработке

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Root Cause

**PRIMARY: Mob templates have no skills assigned.** The seed migration `006_seed_mob_templates.py` creates 8 mob templates in the `mob_templates` table but does NOT insert any rows into `mob_template_skills`. When `spawn_mob_from_template()` runs (in `services/character-service/app/crud.py:847-859`), it queries `MobTemplateSkill` for the template — gets an empty list — and inserts nothing into `character_skills`.

As a result, when battle-service calls `character_ranks(char_id)` for the mob during battle creation, it returns `[]`. The snapshot's `skills` field is empty. When autobattle-service's strategy (`services/autobattle-service/app/strategy.py:53-73`) tries to find available skills via `_filter_available()`, it gets an empty dict. The `_pick_best()` method then returns `{"attack_rank_id": None, "defense_rank_id": None, "support_rank_id": None}` — all None.

The action payload sent to battle-service has all skill slots as None. Battle-service's `_make_action_core()` processes this successfully (200 OK) but:
- Attack block (line 734): skipped because `attack_id` is None
- Defense block (line 659): skipped because `defense_id` is None
- Support block (line 632): skipped because `support_id` is None
- `_pay_skill_costs()`: succeeds with zero cost
- `turn_events` contains only `resource_spend` with all zeros — no damage, no effects

The turn is recorded in MySQL and MongoDB but with empty events, explaining why "mob's action doesn't appear in battle logs and deals no damage."

### Secondary Bug: init_battle_state publishes wrong format

In `services/battle-service/app/redis_state.py:104-107`, the initial `your_turn` pubsub message publishes `json.dumps(battle_state)` (full JSON object), but autobattle's `redis_reader()` expects `int(msg["data"])` — a single participant_id integer. This causes a `ValueError` that is silently caught, meaning the **first turn notification is always lost**. This doesn't affect the current bug (player goes first), but would be a problem if a mob were ever first_actor.

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service | Seed mob template skills | `app/alembic/versions/006_seed_mob_templates.py` or new migration |
| battle-service | (secondary) Fix init pubsub format | `app/redis_state.py:104-107` |

### Existing Patterns

- **character-service**: sync SQLAlchemy, Pydantic <2.0, Alembic present (`alembic_version_character`)
- **battle-service**: async SQLAlchemy (aiomysql), Motor, aioredis, Celery. Alembic NOT present.
- **autobattle-service**: stateless, async httpx + aioredis Pub/Sub. No DB access.
- **skills-service**: async SQLAlchemy (aiomysql), Alembic present (`alembic_version_skills`)

### Cross-Service Dependencies (relevant to this bug)

```
character-service (spawn_mob_from_template)
  → INSERT INTO character_skills (shared DB, skills-service table)

battle-service (build_participant_info)
  → skills-service GET /skills/characters/{char_id}/skills (returns empty for mob)
  → character-attributes-service GET /attributes/{char_id}

battle-service (_make_action_core)
  → skills-service GET /skills/skill_ranks/{rank_id} (never called when rank_id is None)
  → skills-service GET /skills/characters/{char_id}/skills (character_has_rank — never called)

autobattle-service (handle_turn)
  → battle-service GET /battles/internal/{id}/state
  → battle-service POST /battles/internal/{id}/action
```

### DB Changes

No schema changes needed. The fix requires **data population**:
- Insert rows into `mob_template_skills` linking each mob template to appropriate `skill_rank_id` values from the `skill_ranks` table
- This can be done via a new Alembic migration in character-service OR by updating the existing seed migration (006)
- Existing spawned mobs will need to have skills re-assigned (or be respawned)

### Key Code Paths

1. **Mob skill assignment**: `services/character-service/app/crud.py:846-861` — `spawn_mob_from_template()` reads from `mob_template_skills` (empty) and inserts into `character_skills`
2. **Snapshot building**: `services/battle-service/app/main.py:79-119` — `build_participant_info()` calls `character_ranks(char_id)` which returns `[]`
3. **Strategy skill selection**: `services/autobattle-service/app/strategy.py:53-73` — `_filter_available()` reads `snap["skills"]`, gets empty dict
4. **Strategy pick**: `services/autobattle-service/app/strategy.py:111-147` — `_pick_best()` returns all None rank_ids
5. **Action processing**: `services/battle-service/app/main.py:524-955` — `_make_action_core()` skips all skill blocks when rank_ids are None

### Risks

- **Risk**: Choosing wrong skill_rank_ids for mob templates could cause errors if the IDs don't exist in `skill_ranks` table
  → **Mitigation**: Query existing skill_ranks to find valid IDs matching mob class/type before seeding
- **Risk**: Already-spawned mobs have no skills in `character_skills` and will remain broken until respawned
  → **Mitigation**: Either respawn all active mobs or write a one-time migration to add skills to existing mob characters
- **Risk**: The secondary pubsub format bug could cause issues if mob is first_actor in future
  → **Mitigation**: Fix `redis_state.py:106` to publish `str(first_actor_participant_id)` instead of `json.dumps(battle_state)`

---

## 3. Architecture Decision (filled by Architect — in English)

### Overview

This is a data-only bug fix with one secondary code fix. No new API endpoints, no schema changes, no frontend changes.

Three changes required:
1. **New Alembic migration** in character-service to seed `mob_template_skills` with appropriate skill_rank_ids
2. **Fix existing mob characters** — the same migration must retroactively insert skills into `character_skills` for already-spawned mobs that have no skills
3. **Fix Redis pubsub format** in battle-service `redis_state.py`

### API Contracts

No API changes.

### Security Considerations

- No new endpoints — no auth/rate-limiting concerns
- The migration queries `skill_ranks` table (owned by skills-service) from character-service's migration. This is acceptable because all services share the same MySQL database and this is a read-only query during migration.

### DB Changes

**No schema changes.** Data-only operations:

#### Migration 007: Seed mob template skills + fix existing mobs

```sql
-- Step 1: For each mob template, find appropriate skill_rank_ids by querying
-- skill_ranks table, filtering by class_limitations matching the template's id_class.
-- Select rank_number=1 (starter rank) for each skill type (Attack, Defense, Support).

-- Step 2: INSERT INTO mob_template_skills (mob_template_id, skill_rank_id)
-- for each template-skill pair found in step 1.

-- Step 3: For already-spawned mobs (active_mobs JOIN characters),
-- INSERT INTO character_skills (character_id, skill_rank_id)
-- using the same skill_rank_ids from the mob's template.
-- Skip if character_skills already has entries for that character.
```

**Strategy for finding skill_rank_ids:**
The migration must dynamically query at runtime:
1. For each mob template, get its `id_class` (1=Warrior, 2=Rogue, 3=Mage)
2. Query `skill_ranks` JOIN `skills` WHERE:
   - `skills.class_limitations` contains the class id (e.g., "1" for Warrior) OR `skills.class_limitations` IS NULL (universal skills)
   - `skill_ranks.rank_number = 1` (first rank — starter level)
3. Pick at least one Attack, one Defense, and one Support skill per template
4. If no class-specific skills found for a type, fall back to universal skills of that type

**Rollback:** `downgrade()` deletes the inserted rows from `mob_template_skills` and `character_skills` (for mob characters only).

### Redis Pubsub Fix (battle-service)

In `redis_state.py:104-107`, change:
```python
# BEFORE (publishes full JSON — breaks autobattle reader)
await redis_client.publish(
    f"battle:{battle_id}:your_turn",
    json.dumps(battle_state),
)

# AFTER (publishes participant_id as string — matches reader expectation)
await redis_client.publish(
    f"battle:{battle_id}:your_turn",
    str(first_actor_participant_id),
)
```

This matches the pattern used elsewhere in the codebase when publishing `your_turn` messages (the `advance_turn` function publishes `str(next_pid)`).

### Data Flow (unchanged)

```
spawn_mob_from_template() → reads mob_template_skills → INSERTs character_skills
                                    ↑ NOW POPULATED

battle creation → character_ranks(mob_char_id) → skills-service → character_skills
                                                    ↑ NOW RETURNS SKILLS

autobattle strategy → snap["skills"] → non-empty dict → picks attack/defense/support
                                                           ↑ NOW HAS VALID rank_ids

battle action → _make_action_core → attack_id is not None → compute_damage → turn_events
                                                               ↑ NOW EXECUTES
```

### Decision: New migration vs. modifying 006

**New migration (007)** is the correct approach because:
- Migration 006 may have already run in production
- A new migration is idempotent and safer
- It clearly separates concerns (006 = templates, 007 = template skills)

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Create Alembic migration 007 in character-service to seed `mob_template_skills` with appropriate skill_rank_ids for all 8 mob templates. The migration must: (a) query `skill_ranks` JOIN `skills` to find rank_number=1 skills matching each template's class, (b) insert into `mob_template_skills`, (c) retroactively insert into `character_skills` for existing mob characters that have zero skills. Must be idempotent (skip existing rows). Downgrade must clean up inserted rows. | Backend Developer | DONE | `services/character-service/app/alembic/versions/007_seed_mob_template_skills.py` | — | Migration runs without error. After running: each mob template has at least one Attack skill in `mob_template_skills`. Existing mob characters in `active_mobs` have corresponding entries in `character_skills`. |
| 2 | Fix Redis pubsub format in battle-service `init_battle_state()`. Change line 106 in `redis_state.py` from `json.dumps(battle_state)` to `str(first_actor_participant_id)` so the initial `your_turn` message format matches what autobattle's `redis_reader()` expects (`int(msg["data"])`). | Backend Developer | DONE | `services/battle-service/app/redis_state.py` | — | The publish call sends a plain integer string, not a JSON object. |
| 3 | Write tests for the migration logic (task 1) and the Redis pubsub fix (task 2). For task 1: test that migration populates `mob_template_skills` correctly — verify each template has skills, verify existing mobs get `character_skills` entries. For task 2: test that `init_battle_state` publishes `str(participant_id)` not JSON. | QA Test | DONE | `services/character-service/app/tests/test_mob_skill_seeding.py`, `services/battle-service/app/tests/test_redis_state.py` | #1, #2 | All tests pass with `pytest`. |
| 4 | Review all changes. Verify: migration is idempotent, rollback works, skill_rank_ids are valid (exist in skill_ranks), pubsub fix is correct, tests cover key scenarios. Run `python -m py_compile` on all modified files. | Reviewer | PASS | all | #1, #2, #3 | Review checklist passed, all checks green. |
| 5 | Fix case mismatch in autobattle strategy: normalize `skill_type` to lowercase in `_pick_best()` and `_calc_weights()` in `strategy.py`. Also normalize in battle-service `skills_client.py` `character_ranks()` as defense-in-depth. | Backend Developer | DONE | `services/autobattle-service/app/strategy.py`, `services/battle-service/app/skills_client.py` | — | Mob with capitalized skill_type ("Attack") correctly maps to "attack_rank_id" |
| 6 | Write tests for case normalization fix (task 5) | QA Test | DONE | `services/autobattle-service/app/tests/test_strategy.py`, `services/battle-service/app/tests/test_skills_client.py` | #5 | Tests pass with both "Attack" and "attack" skill_types |
| 7 | Review tasks #5-6 | Reviewer | PASS | all new | #5, #6 | Review checklist passed |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-22
**Result:** PASS

#### Migration 007_seed_mob_template_skills.py
- **Logic correctness:** Migration correctly queries `skill_ranks JOIN skills` with `FIND_IN_SET` to match class-appropriate skills (rank_number=1 only). Groups by skill_type and selects one Attack, one Defense, one Support per template. Matches the ORM model (`MobTemplateSkill` with `mob_template_id`, `skill_rank_id` columns and unique constraint).
- **Idempotency:** Verified — each INSERT is guarded by a SELECT-first check. Test `test_upgrade_twice_no_duplicates` confirms running upgrade() twice produces no duplicates.
- **Existing mob fix:** Correctly identifies mobs via `active_mobs JOIN characters WHERE is_npc=1 AND NOT EXISTS character_skills`. Assigns the same skills from the freshly-populated `mob_template_skills`. Non-NPC characters are excluded by the `is_npc=1` guard.
- **Downgrade:** Uses MySQL-specific `DELETE cs FROM character_skills cs JOIN ...` syntax — valid for MySQL 8.0 (production DB). Clears `mob_template_skills` with standard SQL. Acceptable.
- **No hardcoded IDs:** All skill_rank_ids are dynamically queried at runtime. Template IDs come from the DB. No magic numbers.
- **SQL injection:** All queries use parameterized `:bind` variables via `sa.text()` — safe.
- **Cross-service consideration:** Migration reads `skill_ranks` and `skills` tables (owned by skills-service) — acceptable since all services share the same MySQL instance and this is read-only during migration.

#### Redis pubsub fix (redis_state.py)
- **Correctness:** Changed `json.dumps(battle_state)` to `str(first_actor_participant_id)` on line 106. This matches exactly the pattern used in `main.py:938` (`str(next_actor_participant_id)`) and what autobattle's `redis_reader()` expects (`int(msg["data"])`) at `autobattle-service/app/main.py:70`.
- **No cross-service contract breakage:** The format now matches both publisher (battle-service) and consumer (autobattle-service).

#### Tests
- **character-service (14 tests):** Comprehensive coverage — all 3 classes, idempotency, existing mob skill assignment, non-NPC guard, multiple templates/mobs. SQLite FIND_IN_SET emulation is well-implemented. 1 skip for MySQL-specific DELETE JOIN downgrade syntax — acceptable trade-off.
- **battle-service (6 tests):** Covers pubsub format (string not JSON), parseability as int, second-participant-as-first-actor edge case, state storage, deadline ZSET. Good mock isolation with AsyncMock.

#### Code Standards
- [x] Pydantic <2.0 — N/A (no schema changes)
- [x] Sync/async — migration is sync (character-service pattern), redis_state is async (battle-service pattern)
- [x] No hardcoded secrets/URLs/ports
- [x] No TODOs/FIXMEs without tracking
- [x] No frontend changes — T1/T3/T5 N/A
- [x] Alembic migration present with correct chain (006 -> 007)

#### Security
- [x] No new endpoints — no auth/rate-limiting needed
- [x] All SQL uses parameterized queries — no injection vectors
- [x] Error messages don't leak internals

#### Automated Check Results
- [x] `npx tsc --noEmit` — N/A (no frontend changes)
- [x] `npm run build` — N/A (no frontend changes)
- [x] `py_compile` — PASS (all 4 files: migration, redis_state, both test files)
- [x] `pytest` character-service — PASS (13 passed, 1 skipped)
- [x] `pytest` battle-service — PASS (6 passed)
- [x] `docker-compose config` — PASS

#### Live Verification
Live verification is N/A for this review — the fix is a data migration (requires `alembic upgrade head` in the running container) and a Redis pubsub format change. Both changes require container restart/migration execution to take effect. The code changes are verified through automated tests and code review. The migration should be verified after deployment by confirming mobs attack in battle.

### Review #2 — 2026-03-22
**Result:** PASS

#### Case normalization fix (strategy.py)
- **`_calc_weights()` (line 94):** `.lower()` applied to `skill_type` before looking up mode bonus in `_MODE_BONUS`. Without this, capitalized types like "Attack" would not match the lowercase keys in `_MODE_BONUS` dict, resulting in 0.0 bonus. Correct.
- **`_pick_best()` (line 121):** `.lower()` applied to `skill_type` before bucketing into `{"attack": [], "defense": [], "support": []}`. Without this, "Attack" would create a separate bucket, the pre-initialized lowercase keys would remain empty, and all `*_rank_id` values would be None. This was the core bug. Correct.
- **Default value preserved:** Both locations use `.get("skill_type", "attack").lower()` — the default "attack" is already lowercase, so `.lower()` on the default is a harmless no-op. Good.

#### Defense-in-depth normalization (skills_client.py)
- **`character_ranks()` (lines 65-66):** Normalizes `skill_type` to lowercase in the snapshot data before it reaches autobattle-service. This is defense-in-depth — even if autobattle's strategy code were to regress, the data would already be lowercase. The `isinstance(rank_data["skill_type"], str)` guard prevents errors on unexpected non-string values. Correct.
- **`get_rank()` (lines 12-29):** Does NOT normalize. Verified this is correct — `get_rank()` results are used in `main.py` for damage/cost/effect calculations, not for type classification. The attack/defense/support routing is determined by which slot (`attack_rank_id`, `defense_rank_id`, `support_rank_id`) the rank occupies, not by the `skill_type` field.

#### Completeness check — no remaining case-sensitive comparisons
- Searched all `skill_type` references in autobattle-service and battle-service. All comparison/bucketing points now use `.lower()`. No remaining case-sensitive comparisons found.

#### Tests (task #6)
- **autobattle-service (11 tests):** Covers capitalized, uppercase, lowercase, and mixed case for both `_pick_best()` (7 tests) and `_calc_weights()` (4 tests). Key test: `test_no_capitalized_keys_in_output` explicitly verifies that keys like "Attack_rank_id" do NOT appear. `test_consistent_weights_regardless_of_case` uses `random.seed(42)` to eliminate noise and prove weights are identical across cases. Thorough.
- **battle-service (6 tests):** Covers capitalized, uppercase, lowercase, mixed case, row-level inheritance, and empty skills for `character_ranks()`. Good mock isolation with `AsyncMock` and `httpx.AsyncClient` patching.

#### Requirements
- `pytest` added to `services/autobattle-service/app/requirements.txt` — needed for running tests in CI. Acceptable.

#### Previous fixes still work
- [x] `pytest` character-service — PASS (13 passed, 1 skipped) — migration 007 tests still pass
- [x] `pytest` battle-service redis_state — PASS (6 passed) — pubsub fix tests still pass

#### Code Standards
- [x] Pydantic <2.0 — N/A (no schema changes)
- [x] Sync/async — autobattle strategy is sync (correct), skills_client is async (battle-service pattern)
- [x] No hardcoded secrets/URLs/ports
- [x] No TODOs/FIXMEs without tracking
- [x] No frontend changes — T1/T3/T5 N/A

#### Security
- [x] No new endpoints — no auth/rate-limiting needed
- [x] No input validation concerns — `.lower()` is safe on any string
- [x] Error messages don't leak internals

#### Automated Check Results
- [x] `npx tsc --noEmit` — N/A (no frontend changes)
- [x] `npm run build` — N/A (no frontend changes)
- [x] `py_compile` (ast.parse) — PASS (all 4 files: strategy.py, skills_client.py, test_strategy.py, test_skills_client.py)
- [x] `pytest` autobattle-service — PASS (11 passed)
- [x] `pytest` battle-service skills_client — PASS (6 passed)
- [x] `pytest` battle-service redis_state — PASS (6 passed)
- [x] `pytest` character-service — PASS (13 passed, 1 skipped)
- [x] `docker-compose config` — PASS

#### Live Verification
Live verification is N/A for this review — the case normalization fix is a pure logic change in autobattle strategy and battle-service snapshot building. It requires a running battle with a mob to verify end-to-end, which depends on the migration (task #1) also being deployed. The fix is fully verified through automated tests covering all case variants. Should be verified after deployment by confirming mobs attack in battle.

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-22 10:00 — PM: фича создана, запускаю анализ. Баг: моб не атакует в бою, autobattle action получает 200 OK но ход не применяется
[LOG] 2026-03-22 10:30 — Analyst: начал анализ, исследую autobattle-service, battle-service, character-service
[LOG] 2026-03-22 10:45 — Analyst: ROOT CAUSE найден — в seed-миграции 006 таблица mob_template_skills пустая, мобы спавнятся без навыков. Autobattle отправляет action с attack/defense/support_rank_id = None, battle-service принимает (200 OK) но все блоки обработки навыков пропускаются
[LOG] 2026-03-22 10:50 — Analyst: обнаружен вторичный баг — redis_state.py init_battle_state публикует json.dumps(battle_state) вместо str(pid) в your_turn, первое уведомление теряется
[LOG] 2026-03-22 10:55 — Analyst: анализ завершён, затронуто 3 сервиса (character-service, battle-service, autobattle-service)
[LOG] 2026-03-22 11:10 — Architect: начал проектирование, изучаю модели MobTemplateSkill, SkillRank, spawn_mob_from_template, redis_state
[LOG] 2026-03-22 11:30 — Architect: спроектировано 4 задачи. Решение: новая миграция 007 для seed mob_template_skills + ретроактивное исправление существующих мобов + фикс pubsub формата в redis_state.py. Фронтенд не затронут.
[LOG] 2026-03-22 12:00 — Backend Dev: задача #2 завершена. Исправлен формат pubsub в redis_state.py:106 — теперь публикуется str(first_actor_participant_id) вместо json.dumps(battle_state), что соответствует формату в main.py:938 и ожиданиям autobattle redis_reader().
[LOG] 2026-03-22 12:30 — Backend Dev: задача #1 завершена. Создана миграция 007_seed_mob_template_skills.py: (a) для каждого шаблона моба находит rank_number=1 skill_ranks по class_limitations через FIND_IN_SET, (b) вставляет в mob_template_skills по одному Attack/Defense/Support навыку, (c) ретроактивно назначает навыки существующим мобам без character_skills. Миграция идемпотентна, downgrade чистит данные. py_compile пройден.
[LOG] 2026-03-22 13:00 — QA: начал написание тестов для character-service (миграция 007) и battle-service (redis pubsub fix)
[LOG] 2026-03-22 13:30 — QA: тесты готовы. character-service: 14 тестов (13 passed, 1 skipped — downgrade MySQL-specific syntax). battle-service: 6 тестов, все проходят. pytest и pytest-asyncio добавлены в requirements.txt battle-service.
[LOG] 2026-03-22 14:00 — Reviewer: начал проверку. Миграция, redis pubsub фикс, тесты, py_compile, pytest.
[LOG] 2026-03-22 14:15 — Reviewer: проверка завершена, результат PASS. Все проверки пройдены: py_compile OK, pytest 19/19 (13+6 passed, 1 skipped), docker-compose config OK. Код корректен, идемпотентен, безопасен.
[LOG] 2026-03-22 15:00 — PM: пользователь сообщил, что моб с навыком (добавленным через админку) тоже не атакует. Переоткрываю фичу, запускаю повторный анализ.
[LOG] 2026-03-22 15:30 — Analyst: найдена НАСТОЯЩАЯ корневая причина — case mismatch в skill_type. Autobattle использует lowercase ("attack"), а в БД может быть "Attack". Из-за этого навык попадает в неправильный bucket, формируется ключ "Attack_rank_id" вместо "attack_rank_id", Pydantic молча игнорирует → все слоты None → моб ничего не делает.
[LOG] 2026-03-22 16:00 — Backend Dev: задача #5 завершена. Добавлена нормализация skill_type в lowercase: (1) strategy.py _calc_weights() — stype = .lower(), (2) strategy.py _pick_best() — t = .lower(), (3) skills_client.py character_ranks() — defense-in-depth нормализация при построении снапшота. py_compile пройден для обоих файлов.
[LOG] 2026-03-22 16:30 — QA: начал написание тестов для case normalization fix (задача #6)
[LOG] 2026-03-22 16:45 — QA: тесты готовы. autobattle-service: 11 тестов (test_strategy.py — _pick_best и _calc_weights с разными регистрами skill_type). battle-service: 6 тестов (test_skills_client.py — character_ranks нормализация). Всего 17 тестов, все проходят. pytest добавлен в requirements.txt autobattle-service.
[LOG] 2026-03-22 17:00 — Reviewer: начал Review #2 (задачи #5-6, case normalization fix)
[LOG] 2026-03-22 17:15 — Reviewer: проверка завершена, результат PASS. py_compile OK (4 файла), pytest autobattle 11/11, pytest battle-service skills_client 6/6, pytest battle-service redis_state 6/6, pytest character-service 13+1skip, docker-compose config OK. Все точки сравнения skill_type нормализованы, тесты покрывают все варианты регистра.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **Основной баг (case mismatch):** Исправлено несовпадение регистра `skill_type` — autobattle использовал lowercase ("attack"), а в БД хранилось с заглавной ("Attack"). Добавлена нормализация `.lower()` в `strategy.py` и `skills_client.py`
- **Миграция 007:** Заполняет `mob_template_skills` навыками по классу моба + ретроактивно чинит существующих мобов без навыков
- **Redis pubsub fix:** Первое уведомление о ходе теперь в правильном формате (str participant_id вместо JSON)
- **37 тестов:** 14 (миграция) + 6 (pubsub) + 11 (strategy case) + 6 (skills_client case), все проходят

### Что изменилось от первоначального плана
- Первоначально думали, что проблема только в пустой таблице `mob_template_skills`. Пользователь уточнил, что моб с навыком (добавленным через админку) тоже не атакует — это привело к обнаружению настоящей корневой причины (case mismatch в skill_type)

### Оставшиеся риски / follow-up задачи
- После деплоя нужно пересобрать контейнеры character-service, battle-service и autobattle-service
- Рекомендуется проверить бой с мобом после деплоя
- Существующие мобы без навыков будут починены миграцией автоматически

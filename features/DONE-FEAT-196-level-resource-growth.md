# FEAT-196: Рост ресурсов за уровень по классу

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-02 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Игроки свободно распределяют очки и могут уходить в один стат. Как защита от «стеклянных» билдов — каждый уровень сам по себе даёт прибавку к максимумам ресурсов в зависимости от класса. Строится поверх FEAT-195 (кап статов, ещё не закоммичен — общая рабочая копия).

### Бизнес-правила
- Прибавка к **максимуму** ресурса = `уровень × ставка` (уровень 1 уже даёт прибавку; 50 ур. → 750 / 500):
  - **Воин:** здоровье +15/ур, мана/энергия/выносливость +10/ур.
  - **Плут:** энергия +15/ур, здоровье/мана/выносливость +10/ур.
  - **Маг:** мана +15/ур, здоровье/энергия/выносливость +10/ур.
- Прибавка идёт **мимо капа FEAT-195** — это не стат, а надбавка к ресурсу. Кап режет только очки/статы.
- Зависит только от класса, подкласс не влияет.
- **Выносливость тоже растёт** (+10/ур всем, т.к. у всех классов она не основная).
- **Существующие персонажи** получают прибавку задним числом по текущему уровню — через полный пересчёт (`rebuild_derived_stats` / `recalculate_all` из FEAT-195).
- При повышении уровня (обычном и админском, в т.ч. понижении уровня админом) максимумы меняются на разницу.
- **Мобы** (у них есть уровень и класс) получают ту же прибавку.
- Текущие значения ресурсов при росте максимума: следовать существующему поведению при повышении максимума (не «долечивать» сверх того, как это делается сейчас при вложении очков); при понижении — обрезать текущее до нового максимума.

### UX
1. Игрок апает уровень — максимумы ресурсов растут по классу без вложения очков.
2. В профиле/подсказках видно, откуда берётся максимум (база + за уровень + за очки + шмот), хотя бы в подсказке.
3. При создании персонажа в объяснении статов/класса упомянуть рост ресурсов за уровень.

### Edge Cases
- Смена класса (если возможна админом) — пересчёт должен дать прибавку нового класса.
- Персонаж без класса / неизвестный класс — без прибавки, не падать.
- Повторный пересчёт идемпотентен.

### Вопросы к пользователю
- [x] Мимо капа → да
- [x] уровень × 15 (а не (уровень−1)) → да
- [x] Выносливость тоже → да
- [x] Задним числом → да
- [x] Мобы → да
- [x] Подкласс → не влияет

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Analysis done by the Architect directly (2026-11-02), on top of the uncommitted FEAT-195 working tree.

### Where level and class live
- `characters.level` (Integer, default 1) and `characters.id_class` (Integer, NOT NULL) — table owned by character-service (`character-service/app/models.py:46,61`). Classes (`classes` table, prod/seed): **1 = Воин, 2 = Ловкач (плут), 3 = Маг** — matches `CLASS_MAIN_ATTRIBUTE = {1: strength, 2: agility, 3: intelligence}` (`character-attributes-service/app/constants.py:98`, `battle-service/app/battle_engine.py:97`).
- character-attributes-service already reads the shared `characters` table with raw SQL (`crud.py:205` `SELECT id_class` at creation; `main.py:69` user_id; `regen.py:70,75` is_npc/sleep). Level is today only fetched over HTTP by the perk evaluator (`perk_evaluator.py:54` → character-service full_profile). So reading `level, id_class` directly is an established pattern; no HTTP needed for the pull.

### Where level changes (all in character-service)
1. `crud.check_and_update_level` (`crud.py:1317-1355`, sync) — the only natural level-up path (`level += 1`, `stat_points += 10`, commits). Callers: `_build_full_profile` (`main.py:2050`, async; already posts `/attributes/internal/{id}/reconcile-perks` after a level-up), mob/battle rewards (`crud.py:2584`, after commit), title XP (`crud.py:2964`). Every XP source funnels into one of these.
2. Admin `PUT /characters/admin/{id}` (`main.py:704-850`) — level up **or down** (validation only `>= 1`), commits, then syncs passive_experience via attributes HTTP.
3. Admin `PUT /characters/admin/npcs/{npc_id}` (`main.py:3070+`, `NpcUpdate`) — may change `level` **and** `id_class` (the only place a class can change).
4. Creation (level set on the new row): player approval (`main.py:~450-500`, level 1), admin NPC create (`main.py:2960-2995`, `NpcCreate.level`), mob spawn `crud.spawn_mob_from_template` (`crud.py:1729`, `level=template.level`, `id_class=template.id_class`). **In all three the `characters` row is only `flush()`ed (not committed) when `POST /attributes/` is called**, so the attributes service's separate connection cannot see it: today the `SELECT id_class` at creation returns nothing for mobs/NPCs/new players (harmless today because `class_id` is unused in `compute_derived_stats`). ⇒ Level and class must be passed **in the create body**.
- No other service writes `characters.level` / `id_class` (grepped).

### Resource max formula after FEAT-195
- `crud.resource_max(resource, value) = BASE_R + floor(m_R * eff(value))` (`crud.py:22`); `RESOURCE_STATS` in constants. Gear/food/perk resource bonuses are added to the **stat** column (`health`, `mana`…), not to `max_*` — no modifier key writes `max_*` (`FLAT_MODIFIER_KEYS`). So stored `max_R` is fully determined by (R total, level, class) — no flat part.
- Writers of `max_*`: `compute_derived_stats` (creation, absolute), `apply_attribute_modifiers` (delta `resource_max(new) - resource_max(old)`, current moves by the same delta, clamped `[0, max]`), `rebuild_derived_stats` (absolute, current only clamped down), admin raw `PUT /attributes/admin/{id}` (followed by `/recalculate` in the admin UIs). Nothing outside attributes computes max from stats (battle/dungeon/autobattle read stored values).
- A constant per-level term cancels in the `apply_attribute_modifiers` delta ⇒ that function needs **no change**.

### Mobs
- `mob_templates.level`, `mob_templates.id_class` exist; spawn copies them onto a real `characters` row (`is_npc=1, npc_role='mob'`) with its own `character_attributes` row ⇒ mobs are characters in the same tables; `recalculate_all` already iterates every `character_attributes` row (players, NPCs, mobs).
- Dungeon `mob_multiplier` scales base attributes only (`_scale_mob_attributes`, `crud.py:1830`).
- Admin UIs: `AdminMobTemplateForm.tsx:102-138` local `computeDerivedStats` preview (no level/class term); `MobStatsEditor.tsx` / `NpcStatsEditor.tsx` edit raw values then call `/recalculate` (rebuild ⇒ will include the bonus). Template edits don't touch already-spawned mobs (unchanged).

### Frontend mirrors
- `CommonComponents/CharacterPassport/derived.ts` `computeDerivedStats(stats)` — used by the passport adapters (wizard draft with `level: 1`, starting-stats snapshot, list/moderation) and by `StatExplainer.tsx` (Blood step — class not chosen yet; class is picked later in `StepPath`, `ClassCard.tsx`).
- Profile resource bars: `ProfilePage/CharacterInfoPanel/StatsPanel.tsx` (title = label only). Profile slice has `level` and `id_class`.
- `AdminMobTemplateForm.tsx` preview has `form.level` and `form.id_class`.

### Test-fixture risk (memory: silent-failure pattern)
- The attributes test DDL for `characters` has **no `level` column**: `tests/regen_shared_tables.py:42-48`, `tests/test_damage_from_class.py:59-75` (`_Character` model), `tests/test_endpoint_auth.py:76`, `tests/test_feat171_predicate_parity.py:84`. Fixtures must get `level` or the new SELECT fails / is silently mis-tested.
- character-service tests call `check_and_update_level` directly (`test_level_thresholds.py:96`) — a new outgoing HTTP call there must be patchable.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Rule and the one rate table
`max_R = BASE_R + floor(m_R · eff(R_total)) + level · rate(class, R)` — the level term is **outside** `eff` (not a stat, not capped). Integer, no flat part.

`character-attributes-service/app/constants.py` (the only backend copy — no other service computes max resources):
```python
# FEAT-196: per-level growth of resource maximums, by class (subclass ignored).
MAIN_RESOURCE_PER_LEVEL = 15
OTHER_RESOURCE_PER_LEVEL = 10
CLASS_MAIN_RESOURCE = {1: "health", 2: "energy", 3: "mana"}   # warrior, rogue, mage
# -> LEVEL_RESOURCE_GROWTH[class_id][resource] built from the two above for all 4 RESOURCE_STATS
```
`crud.level_resource_bonus(resource, class_id, level) -> int`: unknown/None class → 0; `level` None or < 1 → 0; else `level * rate`. `crud.resource_max(resource, value, level=None, class_id=None)` adds it (defaults keep every existing call identical).

Examples: warrior L50 → health +750, others +500; mage L1 → mana +15, others +10.

### 3.2 Where the bonus is applied (attributes service)
| Path | Change |
|---|---|
| `compute_derived_stats(attr, class_id=None, level=None)` (creation) | `max_R = resource_max(R, value, level, class_id)`; current = max (fresh row) |
| `create_character_attributes` | level/class from **body** (new optional fields), fallback `SELECT level, id_class FROM characters` (existing fallback, now for both), else no bonus |
| `apply_attribute_modifiers` | **unchanged** — the level term cancels in `resource_max(new) − resource_max(old)` |
| `rebuild_derived_stats` | reads `(level, id_class)` via new `crud.get_level_and_class(db, character_id)` (raw SQL on `characters`; missing row → `(None, None)` → no bonus); `max_R` absolute incl. bonus; current only clamped down (FEAT-195 convention). Not wrapped in try/except — an SQL error must surface (batch → `skipped`, single → 500), never silently drop the bonus. |
| new `crud.sync_level_resources(db, attr, level, class_id)` | absolute target `T = resource_max(R, attr.R, level, class_id)`, `diff = T − max_R`; `max_R = T`; `diff > 0` → `current += diff` (same as investing points — no extra top-up); `diff < 0` → `current = min(current, T)` (clamp, per brief); `diff == 0` → nothing. Idempotent. Also heals any drift in max. |

Pure absolute target (not "old level vs new level" delta) ⇒ idempotent, no stored "applied level" column, works for level up, admin down, multi-level jumps and class change (NPC) identically. **No DB schema change, no migration.**

### 3.3 Contract decision — character-service *notifies*, attributes *pulls*
character-service does not send level/class on change; it only tells attributes "level/class of X may have changed". attributes reads them from the shared `characters` table (single source of truth, committed by then).

#### `POST /attributes/internal/{character_id}/sync-level` (new, attributes)
- Auth: `Depends(verify_internal_token)`; `/attributes/internal/` is already 403 externally in both nginx configs — no nginx change. No body.
- Flow: `regen.lock_attributes` → 404 `"Атрибуты персонажа не найдены"` if none → `regen.settle_regen` (regen accrued under the old max first) → `get_level_and_class` → `sync_level_resources` → commit → if satiety expired, `regen.reconcile_perks_after_expiry` (same as `/recalculate`).
- Response 200: `{"character_id": 12, "level": 7, "id_class": 1, "max_health": 735, "max_mana": 245, "max_energy": 170, "max_stamina": 240}`.
- SQLAlchemyError → 500 `"Не удалось обновить ресурсы персонажа"`.

#### `POST /attributes/` (create, existing, internal token) — additive body fields
`CharacterAttributesCreate` gains `level: Optional[int] = None`, `id_class: Optional[int] = None` (Pydantic v1; not persisted on the attributes row, only used for the bonus). Backward compatible: old callers omit them → DB fallback. Response unchanged.

#### character-service callers
- New helper `crud.notify_level_changed(character_id)` (sync `httpx.post`, `X-Internal-Token`, timeout 5 s, any error/non-200 → `logger.warning`, never raises) + async twin or `await asyncio.to_thread` for async handlers (dev's choice, follow file style).
- `check_and_update_level`: after its `db.commit()` **only when `leveled_up`** → `notify_level_changed`. Covers full_profile, rewards, title XP. (Rare branch; a short blocking call inside async `_build_full_profile` is acceptable and guarantees the attributes read that follows already shows the new max.)
- Admin `PUT /characters/admin/{id}`: after commit, if `character.level != old_level` → notify.
- Admin `PUT /characters/admin/npcs/{id}`: after commit, if level or `id_class` changed → notify (after the existing subrace-preset/recalculate block).
- Creation: player approval, admin NPC create, `spawn_mob_from_template` add `"level"` and `"id_class"` to the attributes create dict (`send_attributes_request` / `_sync_send_attributes_request` payload).
- Failure of the notify is non-fatal: next level-up, `/recalculate` or `recalculate_all` repairs it (all absolute).

Rejected alternatives: (a) send level+class in the sync body — two sources of truth, and stale-body races on fast level-ups; (b) attributes polls level on every read — hot path cost; (c) a stored `level_bonus_applied` column — needs a migration and still a sync call.

### 3.4 Mobs
Mobs are `characters` rows with `level`/`id_class` from the template → creation body carries them (3.3) → same bonus. Existing mobs/NPCs get it from `recalculate_all` (iterates all `character_attributes`). Dungeon `mob_multiplier` does **not** scale the level bonus (it scales base stats only; the bonus is a function of level). Template edits still don't touch already-spawned mobs (unchanged behaviour).

### 3.5 Frontend
- New `src/utils/resourceGrowth.ts` — the single TS mirror (header comment → `character-attributes-service/app/constants.py`): `MAIN_RESOURCE_PER_LEVEL`, `OTHER_RESOURCE_PER_LEVEL`, `CLASS_MAIN_RESOURCE`, `levelResourceBonus(resource, classId, level)`, `classGrowthText(classId)` (e.g. «За уровень: здоровье +15, мана/энергия/выносливость +10»), `RESOURCE_GROWTH_NOTE` (generic, all 3 classes; «не зависит от вложенных очков и не режется капом»).
- `derived.ts`: `computeDerivedStats(stats, growth?: { level?: number | null; classId?: number | null })` adds the bonus to the 4 maxes; no `growth` → no bonus (old behaviour). Adapters pass `{ level: 1, classId }` where the class is known (wizard draft once a class is picked, starting-stats snapshot) — starting maxes then equal what the backend creates.
- `StatExplainer.tsx` (Blood step, class unknown): add `RESOURCE_GROWTH_NOTE` line; derived block stays class-less with a short caption that the class adds its per-level bonus from level 1.
- `StepPath/ClassCard.tsx`: one line `classGrowthText(id_class)`.
- `ProfilePage/CharacterInfoPanel/StatsPanel.tsx`: resource bar tooltip (`title`) with breakdown «База 100 + за уровень 12×15 = 180 + от здоровья (очки и снаряжение) 450 = 730»; if stored max differs from the sum, append «прочее ±N» (never hide the stored max). Uses `level`, `id_class`, the resource stat and `effectiveStat`.
- `AdminMobTemplateForm.tsx`: preview adds `levelResourceBonus(…, form.id_class, form.level)`.
- Rules: TS only, no `React.FC`, Tailwind/design-system classes, 360px+, Russian text; if a touched component still imports SCSS → migrate. No new API / Redux.

### 3.6 Security
- New endpoint: internal token only, nginx-blocked, path int only, no body; writes only the caller-identified row under a row lock. No new permissions (no admin endpoint added), no env vars (`ATTRIBUTES_SERVICE_URL`, `INTERNAL_SERVICE_TOKEN` already in character-service).

### 3.7 Rollout / rollback
- Deploy together with FEAT-195. The single post-deploy `POST /attributes/admin/recalculate_all` (already required by FEAT-195) applies the bonus to every player, NPC and mob (rebuild is absolute). Current resources are not topped up (rebuild only clamps down) — regen fills the new headroom (regen is % of max, so it also gets faster). Re-run is idempotent.
- Deploy order inside one push is irrelevant: old attributes ignore the extra create fields (Pydantic v1 ignores extras); a 404 from a not-yet-updated sync endpoint is logged and repaired by `recalculate_all`.
- Rollback: revert code + `recalculate_all` (removes the bonus).

### 3.8 Data flow
```
Level-up (XP): any XP source → character-service check_and_update_level → commit
   → POST attributes/internal/{id}/sync-level → SELECT level,id_class FROM characters
   → max_R = BASE + floor(m·eff(R)) + level·rate(class,R); current += diff (or clamp if down) → MySQL
Admin level / NPC level|class: character-service PUT → commit → same sync-level call
Creation (player/NPC/mob): character-service flush → POST attributes/ {…stats, level, id_class} → compute_derived_stats incl. bonus
Rebuild: /recalculate, /admin/recalculate_all → rebuild_derived_stats reads level,id_class → absolute max incl. bonus
Upgrade/gear/perks/food: apply_attribute_modifiers — unchanged (bonus constant, cancels in the delta)
```

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | character-attributes-service: rate constants (3.1); `level_resource_bonus`, `resource_max(…, level, class_id)`, `get_level_and_class`, `sync_level_resources` (3.2); bonus in `compute_derived_stats` + `create_character_attributes` (body fields → DB fallback); bonus in `rebuild_derived_stats`; new `POST /attributes/internal/{id}/sync-level` (3.3); `CharacterAttributesCreate.level/id_class` (+ response schema for sync if a model is added). `apply_attribute_modifiers` untouched. | Backend Developer | DONE | `services/character-attributes-service/app/constants.py`, `crud.py`, `main.py`, `schemas.py` | — | py_compile passes; warrior L1 fresh: max_health = 100+floor(10·eff(h))+15; sync is idempotent; level down clamps current; unknown class → 0 bonus, no error; existing FEAT-195 tests still green. |
| 2 | character-service: `notify_level_changed` helper (non-fatal); call it from `check_and_update_level` (only on level-up, after commit), admin character update (level changed), admin NPC update (level or id_class changed); add `level` + `id_class` to the attributes create payload in player approval, admin NPC create, `spawn_mob_from_template`. | Backend Developer | DONE | `services/character-service/app/crud.py`, `services/character-service/app/main.py` | #1 (contract only) | py_compile passes; no call when level unchanged; attributes down → level-up/admin update still succeed (warning logged); existing tests green. |
| 3 | Docs: rule, formula, rate table, sync-level endpoint, create fields, rollout note (one `recalculate_all` covers FEAT-195+196). | Backend Developer | DONE | `docs/services/character-attributes-service.md`, `docs/services/character-service.md` | #1, #2 | Docs match code. |
| 4 | Frontend: `utils/resourceGrowth.ts`; `derived.ts` growth param + adapters (level 1 + class where known); `StatExplainer.tsx` note; `ClassCard.tsx` growth line; `StatsPanel.tsx` max breakdown tooltip; `AdminMobTemplateForm.tsx` preview with level/class (3.5). | Frontend Developer | DONE | `src/utils/resourceGrowth.ts` (new), `src/components/CommonComponents/CharacterPassport/derived.ts`, `adapters.ts`, `src/components/CreateCharacterPage/StepBlood/StatExplainer.tsx`, `src/components/CreateCharacterPage/StepPath/ClassCard.tsx`, `src/components/ProfilePage/CharacterInfoPanel/StatsPanel.tsx`, `src/components/Admin/MobsPage/AdminMobTemplateForm.tsx` | — (formulas fixed here) | `npx tsc --noEmit` + `npm run build` pass in the container; profile tooltip sum equals stored max for a rebuilt char; mob preview L10 warrior shows +150 HP; 360px OK. |
| 5 | QA (character-attributes-service): add `level` column to every test `characters` DDL/model (`regen_shared_tables.py`, `test_damage_from_class.py`, `test_endpoint_auth.py`, `test_feat171_predicate_parity.py`); new `test_level_resource_growth.py`: rate table for classes 1/2/3, unknown/None class, level None/0; create with body level/class, create with DB fallback, create with no row → no bonus; sync-level: up (current += diff), admin down (clamp), multi-level jump, class change, idempotent, unknown class, 404, 401/403 without internal token, settle before change; upgrade of health across 100 with bonus present keeps `max = resource_max(…, level, class)`; rebuild includes bonus and is idempotent; rebuild == create + sync for the same state; `recalculate_all` covers a mob row (`is_npc=1`). Assert real column values. | QA Test | DONE | `services/character-attributes-service/app/tests/test_level_resource_growth.py` (new) + fixture files listed | #1 | pytest green in container (full attributes suite). |
| 6 | QA (character-service): `check_and_update_level` calls notify once per call that levels up, not when no level-up, failure non-fatal; admin update level up/down → notify, stat_points-only → no notify; NPC update level/class → notify; create payloads (approval, NPC create, mob spawn) contain `level` and `id_class` (template values for mobs). Patch the HTTP helper; existing `test_level_thresholds.py` must not hit the network. | QA Test | DONE | `services/character-service/app/tests/test_level_resource_sync.py` (new) | #2 | pytest green in container (full character-service suite). |
| 7 | Review: spec compliance, cross-service contract (create body extras, sync endpoint auth, nginx block), py_compile/tsc/build, pytest attributes + character-service, live check on localhost: level-up a char via admin (+1 and −1) and verify maxes ±rate and current rules; spawn a mob and check bonus; `recalculate_all` → `skipped` empty, bonus present, re-run identical; profile tooltip; zero console errors. Confirm no commit/push by agents. | Reviewer | DONE | all | #1–#6 | Checklist passed; results in section 5. |

**Post-deploy (PM):** the single `POST /attributes/admin/recalculate_all` from FEAT-195 also applies this bonus — run it once after deploy, check `skipped` is empty.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-03
**Result:** PASS (one fix applied by the Reviewer, see below)

#### Spec compliance (section 1)
- Rate table 15/10 by class (1 warrior health, 2 rogue energy, 3 mage mana), stamina +10 for all, level x rate from level 1, subclass ignored, outside the FEAT-195 cap (added after `eff`) — matches `constants.py` / `crud.level_resource_bonus` and the TS mirror `utils/resourceGrowth.ts`.
- Current-value rule: growth moves current by the same diff (no top-up), drop clamps (`sync_level_resources`); rebuild only clamps down. Unknown/None class or level -> 0, no error. Absolute target -> idempotent; class change (NPC) covered.
- Mobs: create body carries template `level`/`id_class` after the dungeon multiplier (multiplier never scales the level term); existing mobs via `recalculate_all`.
- Creation at level 1: approval / NPC create / mob spawn pass `level` + `id_class` in the `POST /attributes/` body (row only flushed); `starting_attributes` snapshot is a separate copy without them.

#### Cross-service contract
- `POST /attributes/internal/{id}/sync-level`: `verify_internal_token` (401 without token, live), 403 through the gateway (`/attributes/internal/` blocked in nginx, live). Error messages Russian, no leaks.
- `CharacterAttributesCreate.level/id_class` Optional — old callers fall back to `characters`; Pydantic v1 syntax.
- character-service URL `ATTRIBUTES_SERVICE_URL + "internal/{id}/sync-level"` matches (no `//internal`); non-200/exception -> WARNING, never raises.

#### Deadlock risk (reported) — confirmed and FIXED
- character-service runs ONE uvicorn worker (no `--workers` in Dockerfile, dev or prod compose). `check_and_update_level` is called **directly on the event-loop thread** from async handlers: `_build_full_profile` (main.py ~2059) and, via `_evaluate_titles_with_book -> grant_unlocked_titles -> _grant_title_xp`, from async `GET /{id}/titles`, `internal_evaluate_titles`, admin update. The blocking `httpx.post` therefore froze the whole service for the round trip on every level-up. Worse: `sync-level` calls `regen.reconcile_perks_after_expiry` when satiety has expired -> `perk_evaluator` -> `GET character-service /characters/internal/{id}/full_profile`, which cannot be served while the loop is blocked -> both sides wait up to the 5 s timeouts, all player requests to character-service stall ~5 s (per callback, the evaluator may make several).
- Sync `def` endpoints (`add_rewards`, guild economy) and the admin paths (`asyncio.to_thread`) run in worker threads — the loop stays free there, no deadlock.
- Fix (small, safe): `crud.notify_level_changed` now checks `asyncio.get_running_loop()`; on the loop thread it starts a daemon thread with the actual POST (`_post_sync_level`) and returns True (scheduled); off the loop it stays synchronous (unchanged behaviour and tests). Trade-off: in the full_profile path the response may come back a few ms before the max update lands — harmless, the next attributes read shows it; failure is still repaired by any later sync/recalculate. Added 2 tests (`test_on_event_loop_post_is_offloaded_to_a_thread`, `test_off_loop_post_stays_synchronous`) and a doc note in `docs/services/character-service.md`.

#### Automated Check Results
- [x] `py_compile` (all modified .py) — PASS
- [x] pytest character-attributes-service (`--asyncio-mode=auto`, repo mounted) — PASS, 915 passed / 2 skipped / 1 xpassed
- [x] pytest character-service — PASS, 7374 passed / 1 skipped (incl. the 2 new tests)
- [x] FEAT-195 confidence: battle + dungeon `-k "stat_caps or class_damage"` — PASS (83 battle; dungeon all green)
- [x] `npx tsc --noEmit` (frontend container) — PASS, 0 errors
- [x] `npm run build` — PASS
- [x] `docker compose config` — PASS

#### Live Verification Results (localhost)
- Admin `PUT /characters/admin/14` level 3->4 (mage): max mana +15, others +10, current moved by the same diff; 4->3 back: maxes return, current clamped. 0.44 s.
- Event-loop path: XP at threshold -> `GET /characters/14/full_profile` 200 in 0.36 s, level 4, max_mana 120->135 applied by the background thread. Char 14 restored to its original level/stat_points/xp afterwards.
- `recalculate_all` twice: count 843, skipped 0, all 788 character rows identical between runs; formula check BASE+floor(m*eff)+level*rate -> 0 mismatches over players, NPCs and 94 mobs (e.g. mob 759 warrior L4 health 25 -> 410).
- `/profile` (char 763, mage L30): tooltips «Максимум: база 100 + за уровень 30×10 = 300 + от очков и снаряжения 1200 = 1600» etc., all four sums equal stored max (no «прочее»). 360px iframe: no horizontal overflow.
- `/createCharacter`: Blood step shows the growth note; Path step class cards show «За уровень: …» for all 3 classes; 360px OK.
- Console errors: NONE.

#### Rollout notes
- Deploy together with FEAT-195; one `POST /attributes/admin/recalculate_all` after deploy (check `skipped` = 0). Current resources are not topped up — regen fills the new headroom. No migrations, no env vars, no nginx changes.
- No commits/pushes made by the Reviewer.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-02 — PM: фича создана, решения пользователя зафиксированы; запускаю архитектора (анализ + дизайн)
[LOG] 2026-11-02 23:10 — Architect: начал анализ поверх незакоммиченного FEAT-195; уровень и класс лежат в characters (1 воин, 2 плут, 3 маг), меняются только в character-service (левелап, админ, NPC)
[LOG] 2026-11-02 23:20 — Architect: найдено — при создании персонажа/NPC/моба строка characters ещё не закоммичена, атрибуты её не видят; уровень и класс надо передавать в теле создания. В тестовых таблицах characters нет колонки level — QA обязан добавить
[LOG] 2026-11-02 23:30 — Architect: решение — прибавка за уровень вне капа, максимум считается абсолютно (база + кап(очки) + уровень×ставка); character-service после смены уровня дёргает новый internal-эндпоинт sync-level, атрибуты сами читают уровень и класс; rebuild/recalculate_all тоже включают прибавку; миграций нет
[LOG] 2026-11-02 23:30 — Architect: спроектировано 7 задач (3 бэкенд/доки, 1 фронт, 2 QA, 1 ревью); статус IN_PROGRESS
[LOG] 2026-11-02 23:55 — Frontend Dev: добавлен utils/resourceGrowth.ts (ставки 15/10 по классу 1/2/3, неизвестный класс → 0); computeDerivedStats принимает уровень и класс, паспорт мастера и стартовый снимок считают прибавку 1-го уровня
[LOG] 2026-11-02 23:55 — Frontend Dev: подсказка о росте в «Что даёт кровь» и на карточках классов, разбивка максимума в подсказке полосок профиля, предпросмотр шаблона моба учитывает уровень и класс; tsc и build в контейнере проходят, задача #4 DONE
[LOG] 2026-11-03 00:20 — Backend Dev: задача #1 готова — ставки в constants.py, level_resource_bonus/resource_max(level, class)/get_level_and_class/sync_level_resources в crud.py, прибавка при создании (тело → фолбэк на characters) и в rebuild, новый internal-эндпоинт POST /attributes/internal/{id}/sync-level; apply_attribute_modifiers не тронут
[LOG] 2026-11-03 00:25 — Backend Dev: задача #2 готова — crud.notify_level_changed (не падает, WARNING), вызовы в check_and_update_level (только при левелапе), админском PUT персонажа (уровень изменился) и PUT NPC (уровень/класс); level+id_class в теле создания атрибутов (одобрение — копией, чтобы не попасть в слепок; моб — после множителя данжа)
[LOG] 2026-11-03 00:30 — Backend Dev: починены существующие тесты: в фикстуры characters (regen_shared_tables, test_damage_from_class, test_endpoint_auth, test_feat171_predicate_parity) добавлена колонка level (NULL → без прибавки), test_starting_attributes_snapshot сравнивает слепок без level/id_class
[LOG] 2026-11-03 00:35 — Backend Dev: pytest attributes 781 passed; character-service 7331 passed (после правки теста); живая проверка: sync идемпотентен, левелап мага +10/+15, понижение уровня обрезает текущее, recalculate игрока и моба (воин L4 +60 HP), recalculate_all skipped пуст и повторно идентичен, спавн моба с множителем 2 — прибавка от уровня шаблона
[LOG] 2026-11-03 00:40 — Backend Dev: задача #3 готова — docs/services/character-attributes-service.md и character-service.md обновлены
[LOG] 2026-11-03 01:10 — QA Test: задача #5 готова — test_level_resource_growth.py (134 теста): таблица ставок по классам, неизвестный класс/уровень 0/None, L50 = 750/500, прибавка мимо капа; создание (тело, фолбэк на characters, без строки), sync-level (401, 404, рост/понижение/скачок/смена класса, идемпотентность, settle до изменения), обратимость шмота с прибавкой, rebuild/recalculate/recalculate_all с мобами и NPC, SQL-ошибка → батч в skipped
[LOG] 2026-11-03 01:10 — QA Test: add_character в regen_shared_tables принимает level/id_class; страж схемы (test_regen) теперь проверяет characters.level и id_class у владельца
[LOG] 2026-11-03 01:15 — QA Test: задача #6 готова — test_level_resource_sync.py (41 тест): notify_level_changed (URL, токен, таймаут, не падает), левелап → один вызов после коммита, админ ±уровень, NPC уровень/класс, тела создания (одобрение, NPC, моб без множителя по уровню), слепок без level/id_class
[LOG] 2026-11-03 01:15 — QA Test: в conftest character-service добавлена autouse-заглушка notify_level_changed — раньше test_level_thresholds из контейнера реально дёргал sync-level у dev-сервиса атрибутов
[LOG] 2026-11-03 01:20 — QA Test: pytest attributes 905 passed / 12 skipped (скипы — стражи без полного репо; страж схемы прогнан отдельно с репо, зелёный); character-service 7372 passed / 1 skipped; багов в реализации не найдено
[LOG] 2026-11-03 00:05 — Reviewer: начал проверку FEAT-196 (поверх FEAT-195)
[LOG] 2026-11-03 00:15 — Reviewer: подтверждён риск зависания — check_and_update_level вызывается прямо в event loop async-ручек (full_profile, титулы), sync-запрос блокировал весь однопроцессный character-service, а атрибуты при истёкшей сытости зовут обратно full_profile → ожидание до 5 с
[LOG] 2026-11-03 00:15 — Reviewer: исправлено — notify_level_changed на потоке event loop отправляет запрос в фоновом daemon-потоке, вне loop остаётся синхронным; +2 теста, заметка в docs/services/character-service.md
[LOG] 2026-11-03 00:30 — Reviewer: py_compile, pytest (атрибуты 915, character-service 7374, бой/данжи FEAT-195), tsc и build — зелёные; живая проверка: админ ±уровень, левелап через full_profile, recalculate_all ×2 идемпотентен (0 расхождений, мобы с прибавкой), подсказки профиля и мастер создания на 360px, ошибок в консоли нет
[LOG] 2026-11-03 00:30 — Reviewer: проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Прибавка к максимумам ресурсов = уровень × ставка класса (основной ресурс 15, остальные 10), мимо капа FEAT-195.
- Новый internal-эндпоинт `POST /attributes/internal/{id}/sync-level`; character-service дёргает его при апе уровня, админской смене уровня, смене уровня/класса NPC; при создании персонажа/NPC/моба уровень и класс передаются в теле.
- Пересчёт (`/recalculate`, `recalculate_all`) учитывает прибавку, включая мобов.
- Ревьюер нашёл и исправил блокировку единственного воркера character-service при апе уровня (вызов уходит в фоновый поток).
- Фронт: `resourceGrowth.ts`, строка роста на карточках класса, разбивка максимума в подсказке профиля, превью мобов в админке.

### Оставшиеся риски / follow-up задачи
- Выкатывать вместе с FEAT-195; после деплоя один раз `recalculate_all`, проверить `skipped` пустой.
- Обновить статью «Навыки и характеристики» в Технобуке (кап + рост ресурсов за уровень).

```
[LOG] 2026-11-03 — PM: ревью PASS, фича закрыта
```

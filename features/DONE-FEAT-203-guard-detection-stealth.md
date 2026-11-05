# FEAT-203: Стража замечает не всегда — проход мимо стражи по скрытности

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-05 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Пользователь: «Нужно сделать систему, где игрок, приходя в локацию со стражником, не 100 % был им замечен. Тут должна играть скрытность, которая может позволять проходить локации скрытно от стражников, то бишь очередной шанс быть незамеченным.»
Сейчас (FEAT-198) разыскиваемый / «Вне закона» при входе в локацию с живым стражником ВСЕГДА получает встречу со стражей (`law_crud.evaluate_entry`). Строится поверх FEAT-201 «Скрытность» и FEAT-202 «Тюрьма страны» (оба готовы, ревью PASS, НЕ запушены — в рабочем дереве); выкатывается вместе с ними.

### Решения пользователя (2026-11-05, «как предлагаешь»)
1. При входе разыскиваемого (или «Вне закона») в локацию с живым стражником — **бросок обнаружения**. Заметили → встреча со стражей как сейчас. Не заметили → проходит, уведомление «Вы проскользнули мимо стражи».
2. **Шанс** = база по типу локации (как у свидетелей FEAT-201: поселение 100 %, ферма 70 %, опасная 40 %, данж 25 %) **+10 % за каждого лишнего стражника** в локации (мультипликативно: × (1 + 0.10 × (n − 1))) × (1 − снижение от скрытности, тот же расчёт эффективной скрытности с бонусом подкласса и капом) × множитель славы (узнаваемость) × множитель тяжести розыска; границы 5–100 %.
3. **Маска** («Скрывает личность») против стражи **снижает шанс на четверть** (× 0.75). На свидетелей преступлений не влияет (там маска = анонимность).
4. **Множитель тяжести розыска:** Подозреваемый ×0.6, Нарушитель ×0.8, Преступник ×1.0, Злодей ×1.2, Враг края ×1.4; «Вне закона» без розыска — как Преступник.
5. **Каждый вход — новый бросок**; стоя в локации, повторно не бросаем. Существующий 1 ч кулдаун после бегства (A7 FEAT-198) остаётся.
6. Уведомление игроку при удачном проходе — да.
7. Перемещение всегда по одному — бросок на каждого персонажа отдельно.
- Все числа — настройки в админке (раздел «Закон» или «Тень и слава»), права как у остальных настроек (`reputation:settings`).
- Бросок на сервере; телепорт у мастера тоже проходит через бросок (это вход); свиток домой — как раньше, без проверки.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Baseline = the working tree (FEAT-198 committed in `331e4b9`; FEAT-201 «Скрытность» and FEAT-202 «Тюрьма страны» uncommitted, migrations up to `042_country_prison`). Line numbers are of the working tree on 2026-11-05.

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service | pure formula, entry roll, settings (+ migration 043), log action, notification, response field | `app/law_core.py`, `app/law_crud.py`, `app/law_notify.py`, `app/main.py`, `app/crud.py`, `app/models.py`, `app/schemas.py`, `app/alembic/versions/043_guard_detection.py` (new), tests |
| locations-service | pass-through of an additive response field (move / quick move) | `app/main.py`, `app/schemas.py`, tests |
| frontend | «проскользнули» toast on move / quick move / teleport; admin settings fields; admin log label | `LocationPage.tsx`, `TeleportMenu.tsx`, `redux/slices/teleportSlice.ts`, `api/lawAdmin.ts`, `Admin/ReputationPage/LawSettingsTab.tsx`, `Admin/CharactersPage/tabs/LawPanel.tsx` |

### The entry check today (FEAT-198)
- `law_crud.evaluate_entry` — `services/character-service/app/law_crud.py:502-549`. Runs inside the moving transaction (character row already locked `FOR UPDATE`), never commits. Order of exits: NPC / no location (L508) → an open encounter already (`character.law_encounter_id`, L510) → jailed (L512-514) → no region (`reputation_crud.location_region`, L516-518) → **no live guard** (`guards_at`, L519-521) → **flee cooldown** (`_flee_cooldown_active`, L522-523; per character × location, `law_encounters.cooldown_until`, set in `law_crud.flee_roll` L891 = `law_core.FLEE_GUARD_COOLDOWN` 1 h, a constant) → `wanted <= 0 and not outlaw` (L524-528) → level = `lc.level_for(wanted)`, outlaw floored by `lc.level_at_least(level, settings.outlaw_min_level)` (L529-534; so an outlaw without wanted gets the `outlaw_min_level` level, default `criminal`) → `law_facility.resolve_jail` (has_jail, L535) → INSERT `law_encounters` (guard = `guards[0]`), `character.law_encounter_id`, `_log(... action=LOG_ENCOUNTER, key law:encounter:{id})` (L536-549). Returns the encounter or None.
- `guards_at(db, location_id, now)` — `law_crud.py:481-489`: `characters` with `is_npc=1, npc_role='guard', npc_status='alive', current_location_id=loc` and not unconscious; returns the ordered id list → **`len(guards)` is the guard count n** (dead / knocked-out guards are already excluded).
- Callers (only two):
  1. `PUT /characters/internal/{id}/update_location` — `main.py:2356-2431`. `moving = from_location_id is None or str(from) != str(new)` (L2398); `evaluate_entry` only when moving (L2403-2407) → **a post in the same location never rolls**. After the commit it builds `encounter_out` + `law_notify.publish([encounter_notice])` (L2414-2423); response `{detail, character_id, current_location_id, law_encounter}` (L2425-2431).
  2. `crud.execute_teleport` — `crud.py:3773…3925`; the teleport-master arrival calls `evaluate_entry(..., "teleport", from_location_id=previous)` only when the location changes (L3884-3887), commits, returns a dict with `law_encounter` + `law_encounter_id` (L3918-3925). The route `POST /characters/npcs/{npc_id}/teleport` (`main.py:4598-4617`) publishes the encounter notice after the commit and returns `schemas.TeleportResult` (`schemas.py:1579-1585`, has `law_encounter: Optional[dict]`).
  - Not evaluated (by design, unchanged): admin move, the home scroll, the flee move back (`law_flows`, A7), jail transfers; a jailed character exits early.
- locations-service: `_update_character_location` (`locations-service/app/main.py:278-303`) PUTs `{new_location_id, source}` and returns `_law_encounter_from(resp)` (L266-275); `_post_response(new_post, law_encounter)` (L306-312) adds `law_encounter` to `PostResponse` (`schemas.py:375-385`). Callers: `move_and_post` (L1378; update only when `post_outcome != POST_IN_PLACE`, L1530-1534) and `quick_move` (L1672; L1788-1790). Tests that pin this contract: `locations-service/app/tests/test_law_locations.py:315, 410-475`, `test_country_prison.py:593`.

### Stealth / fame / mask / location readers (FEAT-199/201, reuse as is)
- `law_crud.stealth_info(db, character_id, shadow_settings)` — `law_crud.py:194-213`: raw stealth (deploy-skew tolerant `stealth_agility_of` L174), subclass key (`subclass_of` L156), subclass points (`sc.subclass_stealth_points`), `effective = sc.effective_stealth` (bonus added BEFORE the FEAT-195 cap), `reduction_pct = sc.stealth_reduction_pct(effective, s)` = `min(stealth_max_reduction_pct, eff × stealth_pct_per_point)` (defaults 0.5 %/pt, max 90 %).
- `shadow_crud.location_marker(db, location_id)` — `shadow_crud.py:65-70` (`Locations.marker_type`: safe | farm | dangerous | dungeon | NULL).
- `shadow_crud.wears_mask(db, character_id)` — `shadow_crud.py:82-95` (worn `items.is_mask=1`; missing column → False + WARNING).
- `shadow_crud.fame_witness_pct(db, character_id, tiers)` — `shadow_crud.py:106-108` (fame tier `witness_pct` = «узнаваемость»; tiers via `renown_crud.load_renown_tiers(db, sc.SCALE_FAME)`).
- `shadow_core.base_pct` / `member_chance` (`shadow_core.py:208, 239`) — the witness analogue; the witness location bases live in `shadow_settings` (`witness_base_*_pct` 100/70/40/25, default 50).
- Import direction: `shadow_crud` imports `law_crud` at module level, so `law_crud` must import `shadow_crud` **locally inside the function** (precedent: `import law_notify` inside `encounter_notice`, L555). `law_core` is "pure, no project imports" (docstring L1) → marker codes must be duplicated as literals there (or the base passed in).

### Randomness seam
- `law_crud.rng()` (`law_crud.py:87-89`, `secrets.SystemRandom`) is THE seam for witness, reveal, flee and escape rolls; `lc.roll_succeeds(chance, rng)` (`law_core.py:351-357`) → `(roll < chance, roll)` with roll in [0, 100), 2 decimals. Tests patch it: `reputation_world.force_witnessed` (`_ZeroRng`, L105-119), `shadow_world.set_roll` / `no_roll` (L22-45). `law_world` (`tests/law_world.py:115`) patches nothing → **every existing entry test (`test_law_entry.py`, teleport/flee/choice tests that first create an encounter through a move) would become random** once a roll exists.

### Settings tables
- `law_settings` (singleton id=1, model `models.py:1229-1258`; core `LawSettings` `law_core.py:146-170`, `SETTINGS_FIELDS` L182-187, `_DECIMAL_FIELDS`/`_STRING_FIELDS` L188-193, no bool field yet; `settings_from_row` L212-225; `validate` L422-474). Admin: `law_crud.settings_out` / `update_settings` (`law_crud.py:1267-1335`) with `_OPTIONAL_SETTINGS` (L1275) = FEAT-202 fields an older client may omit (stored value kept). Schemas `LawSettingsFields` / `LawLevelOut` / `LawLevelIn` / `LawSettingsBody` (`schemas.py:3827-3877`).
- `law_levels` (5 fixed codes, model `models.py:1261-1271`, core `Level` + `DEFAULT_LEVELS` `law_core.py:136-180`, `SQL_SELECT_LEVELS` L199, `levels_from_rows` L228-231). The natural home of a per-level multiplier (like `fine`, `jail_hours`).
- `shadow_settings` (model `models.py:1408…`, core `ShadowSettings` `shadow_core.py:83-119`; `update_settings` requires ALL fields, no optional-field pattern) — admin tab «Тень и слава».
- Both edited under `reputation:settings` (`law_api.py` / `shadow_api.py` admin routers); no new permission needed.
- Migration head: `042_country_prison` (`alembic/versions/042_country_prison.py`); pattern = information_schema-guarded idempotent `ALTER` (041/042).
- `law_log` (`models.py:1380-1402`): `event_key` UNIQUE (191), `action` VARCHAR(30), `chance_pct`/`roll_pct` DECIMAL(5,2), `ref_id`. Admin reads the last 100 rows per character (`law_crud.admin_character` L1209-1216) → frontend `LawPanel.tsx:74…` maps action → Russian label.

### Notifications
- `law_notify` (`law_notify.py`): `Notice(user_id, message, ws_type, category, data)`, `publish()` after commit, best-effort. Categories: `system` (mandatory) for encounter/jail, `progress` (user-mutable) for wanted / unseen / masked hints (`WS_UNSEEN`, `MSG_UNSEEN`).
- Frontend: notification-service pushes `{type: 'notification', data}` → `useWebSocket.ts:212-218` → `addNotification` (bell) + `alertPlayer` popup (unless the category is in `bell` mode). No ws_type-specific handling exists for law types.

### Frontend touch points
- `LocationPage.tsx:511-548` (`handleSubmitPost` → `move_and_post`; toast «Стража остановила вас!» when `data.law_encounter`), `LocationPage.tsx:610-640` (`handleQuickMove`), `TeleportMenu.tsx:80-99` (teleport result), `redux/slices/teleportSlice.ts:28-36` (`TeleportResult`).
- Admin: `Admin/ReputationPage/LawSettingsTab.tsx` — `GROUPS` (L63-99: «Розыск», «Стража», «Тюрьма»), the levels table (≈L300-350: name / min_value / fine / jail_hours), validation ≈L190-230; `api/lawAdmin.ts:29-66` (`LawSettingsValues`, `LawLevel`). `Admin/CharactersPage/tabs/LawPanel.tsx:70-95` (log labels).

### Cross-Service Dependencies
```
locations-service ──HTTP PUT /characters/internal/{id}/update_location──> character-service   (response + law_slipped, additive)
frontend ──POST /locations/{id}/move_and_post | quick_move──> locations-service                 (PostResponse + law_slipped, additive)
frontend ──POST /characters/npcs/{npc_id}/teleport──> character-service                         (TeleportResult + law_slipped, additive)
character-service ──RabbitMQ general_notifications──> notification-service                      (new ws_type law_slipped, category progress)
character-service reads (raw SQL, shared DB): Locations.marker_type, items.is_mask/equipment_slots, character_attributes.stealth,
  character_tree_progress/tree_nodes, character_renown — all already read by FEAT-199/201 code.
```

### DB Changes
- No new tables. `law_settings` + new columns; `law_levels` + `detect_pct`. Alembic: yes, character-service `043_guard_detection` (auto-migration at container start).

### Risks
- **Existing tests become random** (no rng patch in `law_world`) → `law_world` must force «detected» by default via a dedicated seam (see §3.5).
- **Import cycle** law_crud ↔ shadow_crud → local import only.
- **Duplicate popup** (response toast + notification popup), the FEAT-198 encounter already does both → accepted pattern; see open question Q3.
- **locations-service contract change** of the private helper `_update_character_location` (tests pin its return value) → QA updates these tests.
- **Older admin client** saving settings without the new fields → optional-on-input pattern (FEAT-202 precedent).

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Settings storage — `law_settings` + `law_levels` (tab «Закон»)
Guards, encounters and wanted levels belong to the law module; the per-level multiplier sits naturally next to `fine` / `jail_hours`. The tab «Тень и слава» stays the witness/reveal/renown place; the shared ingredients (stealth reduction, subclass points, fame tier `witness_pct`) are **read from `shadow_settings` / `renown_tiers` unchanged** («тот же расчёт эффективной скрытности»). The guard location bases get **their own columns** (same initial values as the witness bases) so that tuning crime witnesses does not silently change guard detection (open question Q1).

Migration `043_guard_detection` (revises `042_country_prison`; revision id 19 chars; every step information_schema-guarded like 042; no ENUM, no FK):
```sql
ALTER TABLE law_settings ADD COLUMN detect_enabled           TINYINT(1)   NOT NULL DEFAULT 1;
ALTER TABLE law_settings ADD COLUMN detect_base_safe_pct      DECIMAL(5,2) NOT NULL DEFAULT 100.00;
ALTER TABLE law_settings ADD COLUMN detect_base_farm_pct      DECIMAL(5,2) NOT NULL DEFAULT 70.00;
ALTER TABLE law_settings ADD COLUMN detect_base_dangerous_pct DECIMAL(5,2) NOT NULL DEFAULT 40.00;
ALTER TABLE law_settings ADD COLUMN detect_base_dungeon_pct   DECIMAL(5,2) NOT NULL DEFAULT 25.00;
ALTER TABLE law_settings ADD COLUMN detect_base_default_pct   DECIMAL(5,2) NOT NULL DEFAULT 50.00;   -- marker NULL / unknown
ALTER TABLE law_settings ADD COLUMN detect_per_guard_pct      DECIMAL(5,2) NOT NULL DEFAULT 10.00;   -- per extra guard
ALTER TABLE law_settings ADD COLUMN detect_mask_factor_pct    DECIMAL(5,2) NOT NULL DEFAULT 75.00;   -- × for a worn mask
ALTER TABLE law_settings ADD COLUMN detect_min_pct            DECIMAL(5,2) NOT NULL DEFAULT 5.00;
ALTER TABLE law_settings ADD COLUMN detect_max_pct            DECIMAL(5,2) NOT NULL DEFAULT 100.00;
ALTER TABLE law_levels   ADD COLUMN detect_pct                DECIMAL(5,2) NOT NULL DEFAULT 100.00;  -- severity multiplier, %
-- seeded only when the column was just added (inside the same guarded branch):
UPDATE law_levels SET detect_pct = CASE code WHEN 'suspect' THEN 60 WHEN 'offender' THEN 80 WHEN 'criminal' THEN 100
                                             WHEN 'villain' THEN 120 WHEN 'enemy' THEN 140 ELSE 100 END;
```
Downgrade: drop the 11 columns (values lost — acceptable pre-beta). Models (`LawSettings`, `LawLevel`) get the same columns with `default` + `server_default` (SQLite test DBs are built from models).

`law_core`: `LawSettings` + the 10 fields (`detect_enabled: bool = True`, decimals as above); `SETTINGS_FIELDS` extended; new `_BOOL_FIELDS = {"detect_enabled"}` handled in `settings_from_row`; `_DECIMAL_FIELDS` extended. `Level` gets `detect_pct: Decimal = Decimal(100)` (last field, default → existing positional constructions stay valid); `DEFAULT_LEVELS` 60/80/100/120/140; `SQL_SELECT_LEVELS` + `detect_pct`; `levels_from_rows` reads `r[6]` (tolerate a 6-column row → 100 for old fixtures).

Validation (`lc.validate`, Russian texts): bases / per-guard / mask factor / min / max ∈ [0, 100]; `detect_min_pct ≤ detect_max_pct`; each level `detect_pct` ∈ [0, `MAX_DETECT_LEVEL_PCT` = 500]. Constants named, no magic numbers.

### 3.2 Pure formula (law_core)
```python
MARKER_SAFE, MARKER_FARM, MARKER_DANGEROUS, MARKER_DUNGEON = "safe", "farm", "dangerous", "dungeon"  # = shadow_core
def detection_base_pct(marker_type, s: LawSettings) -> Decimal            # unknown / None -> detect_base_default_pct
def detection_chance(base, n_guards: int, reduction_pct, fame_pct, masked: bool, level_pct,
                     s: LawSettings) -> Decimal:
    v = base
    v *= (100 + detect_per_guard_pct × max(0, n_guards − 1)) / 100        # +10 % per extra guard (multiplicative)
    v *= (100 − clamp(reduction_pct, 0, 100)) / 100                      # stealth (effective, subclass, cap) — shadow maths
    v *= (100 + max(0, fame_pct)) / 100                                  # fame tier witness_pct (recognisability)
    if masked: v *= detect_mask_factor_pct / 100                         # × 0.75
    v *= max(0, level_pct) / 100                                         # severity 60/80/100/120/140
    return quantize_2dp(clamp(v, detect_min_pct, detect_max_pct))       # 5..100
```
Worked examples (defaults): suspect, settlement, 1 guard, no stealth/fame/mask → 60.00; criminal, settlement, 2 guards, eff. stealth 100 (−50 %) → 55.00; enemy, settlement, 1 guard, nothing → 140 → **100.00**; masked enemy, eff. stealth 180 (−90 %), settlement → 10.50; anything tiny → **5.00**. The mask does NOT cancel fame here (decision 3 says only «× 0.75»; Q2).

### 3.3 The roll in the entry path (law_crud)
New result type + function; `evaluate_entry` kept as a thin wrapper (backward compatible for existing tests/callers):
```python
@dataclass(frozen=True)
class EntryResult:
    encounter: Optional[models.LawEncounter]
    slipped: bool = False
    chance_pct: Optional[Decimal] = None
    roll_pct: Optional[Decimal] = None

def detection_rng():            # THE seam of the guard-detection roll (tests patch it); default = rng()
    return rng()

def check_entry(db, character, location_id, source, now=None, *, from_location_id=None) -> EntryResult
def evaluate_entry(...) -> Optional[LawEncounter]:  return check_entry(...).encounter
def detection_chance_for(db, character_id, location_id, n_guards, level, settings) -> Decimal   # readers + lc.detection_chance
def slip_notice(db, character_id, location_id) -> law_notify.Notice
```
`check_entry` keeps **every existing exit in the same order** (NPC, open encounter, jailed, no region, no live guard, **flee cooldown**, not wanted and not outlaw, level None). Only after the level is known:
1. `settings.detect_enabled` false → detected (old behaviour, `chance/roll = None`).
2. else `chance = detection_chance_for(...)`: `shadow_crud.location_marker` (local import), `n = len(guards)`, `stealth_info(db, cid, renown_crud.load_shadow_settings(db)).reduction_pct`, `shadow_crud.wears_mask`, `shadow_crud.fame_witness_pct(db, cid, load_renown_tiers(db, SCALE_FAME))`, `level.detect_pct` (the **encounter level**, i.e. after the outlaw floor). `detected, roll = lc.roll_succeeds(chance, detection_rng())`.
3. **Not detected** → `_log(key=f"law:slip:{cid}:{location_id}:{now:%Y%m%d%H%M%S%f}:{secrets.token_hex(4)}", action=lc.LOG_SLIPPED ('slipped'), region_id, wanted_before=wanted_after=wanted, chance_pct, roll_pct, ref_id=location_id, reason=source)`; no encounter, no `law_encounter_id`, **no cooldown** (decision 5: every entry is a new roll); return `EntryResult(None, slipped=True, chance, roll)`.
4. **Detected** → today's code unchanged (resolve_jail, INSERT encounter, `law_encounter_id`), and the existing `LOG_ENCOUNTER` row now carries `chance_pct` / `roll_pct` (NULL when disabled).
- `resolve_jail` is only called when detected (saves queries on a slip).
- Rules confirmed: **no roll when not moving** (both callers already gate on a real location change; a same-location post never calls update_location's evaluation); **flee cooldown precedes the roll** (no roll, no slip notice while the 1 h cooldown is active — the guards «let you be», nothing to announce); **outlaw without wanted** → level `outlaw_min_level` (default «Преступник») → its `detect_pct` (×1.0 by default) — exactly decision 4 while the admin keeps the default; jailed / open encounter / NPC → no roll; home scroll, admin move, flee move-back → not evaluated (unchanged).
- Idempotency: a move is not a replayable request; each entry is one roll in the move's own transaction (character row locked → no parallel double roll for one character). The log key is unique per roll (timestamp µs + random suffix). A rollback of the move rolls the log back too.

### 3.4 Notification and response field
- `law_notify`: `WS_SLIPPED = "law_slipped"`, `slipped_message(location_name)` → **«Вы проскользнули мимо стражи в «{location}»»** (fallback «…мимо стражи»), category **`progress`** (user-mutable, like the FEAT-199 «никто не видел» hints; not `system`). `ws_data = {character_id, location_id}`. No chance / roll / wanted numbers in player text.
- `update_location` (`main.py`): call `check_entry`; response gets **`"law_slipped": bool`** (additive; false when not evaluated / detected); after the commit publish `slip_notice` (best-effort, same try/except as the encounter).
- `execute_teleport` (`crud.py`): `check_entry`; return dict + `"law_slipped": bool`; `schemas.TeleportResult` + `law_slipped: bool = False`; the route (`main.py:4612`) publishes `slip_notice` when `result["law_slipped"]`.
- locations-service: `_update_character_location` returns a small `LawArrival(encounter: Optional[dict], slipped: bool)` NamedTuple (`_law_slipped_from(resp)`: `data.get("law_slipped") is True`); `_post_response(new_post, arrival)` adds `law_encounter` and `law_slipped` when either is set; `PostResponse` + `law_slipped: Optional[bool] = None`. Callers `move_and_post` (POST_IN_PLACE → no call, arrival = empty) and `quick_move` updated.
- Frontend player: on `law_slipped === true` show `toast('Вы проскользнули мимо стражи', { icon: '🕶️' })` (move_and_post, quick move, teleport); nothing else changes (no lock, no refresh needed). This mirrors the FEAT-198 «Стража остановила вас!» toast + notification pair.

### 3.5 Tests seam
`law_world` fixture gets a default `monkeypatch.setattr(law_crud, "detection_rng", lambda: _ZeroRng())` (roll 0.00 < min 5 % → always detected), so the FEAT-198/202 suites keep their meaning; new tests override with `FixedRng(0.9999)` (roll 99.99 ≥ any chance < 100 → slipped) or exact values around a computed chance. Since `detection_rng()` delegates to `rng()` by default, tests that only patch `rng` still control it — QA must check flee tests that patch `rng` after a move-created encounter (the fixture's explicit `detection_rng` patch wins, which is what we want).

### 3.6 API contracts (all additive)
`PUT /characters/internal/{id}/update_location` → `{detail, character_id, current_location_id, law_encounter: dict|null, law_slipped: bool}`
`POST /locations/{id}/move_and_post`, `POST /locations/{id}/quick_move` → `PostResponse` + `law_slipped?: bool|null`
`POST /characters/npcs/{npc_id}/teleport` → `TeleportResult` + `law_slipped: bool`
`GET/PUT /characters/admin/law/settings` → `settings` + `detect_enabled: bool, detect_base_safe_pct, detect_base_farm_pct, detect_base_dangerous_pct, detect_base_dungeon_pct, detect_base_default_pct, detect_per_guard_pct, detect_mask_factor_pct, detect_min_pct, detect_max_pct` (floats); `levels[]` + `detect_pct: float`. On input all new fields are **Optional** (None → stored value kept; `_OPTIONAL_SETTINGS` extended; `LawLevelIn.detect_pct: Optional[float] = None` → keep the stored level value / default).

### 3.7 Admin UI
`LawSettingsTab.tsx`: new group **«Обнаружение стражей»** — checkbox «Стража может не заметить» (`detect_enabled`; off = замечает всегда), bases «Поселение / Угодья / Дикие места / Подземелье / Прочее, %», «За каждого лишнего стражника, %», «Маска: множитель, %» (hint «75 — шанс × 0,75; на свидетелей не влияет»), «Минимум, %», «Максимум, %»; a hint line with the formula. Levels table: new column **«Заметность, %»** (`detect_pct`, 0–500, hint «100 — без изменений»). Client validation mirrors §3.1. `LawPanel.tsx`: label `slipped: 'Проскользнул мимо стражи'` (chance/roll already rendered for log rows if present — verify). Tailwind + design system, 360 px adaptive, no `React.FC`, all errors shown.

### 3.8 Deploy skew
- Migration runs before uvicorn (fail-fast); new columns have defaults → old rows valid. Code reading `SQL_SELECT_SETTINGS` / `SQL_SELECT_LEVELS` only runs after the migration in the same container.
- Old locations-service + new character-service: `law_slipped` ignored → no toast, the notification still arrives. New locations-service + old character-service: field absent → `slipped=False`.
- Old admin bundle → optional fields keep stored values. Old player bundle → ignores the field; notification still shows.
- Ships together with the uncommitted FEAT-201/202 (migrations 041 → 042 → 043 in one deploy).

### 3.9 Security
- Roll server-side only (`secrets.SystemRandom`); no client input influences it (location comes from the authorised move path). Chance/roll are written only to `law_log` (staff view); player responses carry a boolean only.
- Internal endpoint stays behind `X-Internal-Token` / nginx 403; teleport behind JWT ownership (unchanged). Admin settings under `reputation:settings` (existing RBAC; **no new permission**, so no RBAC test change). Validation bounds on every new number (no negative / >100 % abuse). No new endpoints, no rate-limit changes.

### Data Flow Diagram
```
Player → Frontend → nginx → locations-service move_and_post / quick_move
        → PUT character-service /characters/internal/{id}/update_location (row FOR UPDATE)
            → law_crud.check_entry → guards_at → cooldown → wanted/outlaw/level
              → detect_enabled? → detection_chance (marker, n guards, stealth, fame, mask, level) → roll
                 detected → law_encounters + law_log(encounter, chance, roll)       → response law_encounter
                 slipped  → law_log(slipped, chance, roll)                          → response law_slipped=true
            → commit → law_notify (RabbitMQ general_notifications) → notification-service → WS popup + bell
        ← PostResponse{law_encounter|law_slipped} ← toast
Teleport: Frontend → character-service POST /characters/npcs/{id}/teleport → execute_teleport → check_entry (same)
```

### Open business questions (defaults applied unless the user says otherwise)
- **Q1** Guard location bases: separate settings (default, same 100/70/40/25/50) vs. reuse the witness bases of «Тень и слава». Default: **separate**.
- **Q2** Mask vs. fame against guards: decision 3 says only «× 0.75». Default: **fame still counts under a mask** (literal). Alternative: the mask also hides fame (as with witnesses).
- **Q3** Notice duplication: toast from the move response **and** a `progress` notification (popup + bell) — same pattern as the FEAT-198 encounter. Default: **both**; alternative: notification only.
- **Q4** Outlaw without wanted: the multiplier follows `outlaw_min_level` (default «Преступник» ×1.0). If the admin raises `outlaw_min_level` to «Злодей», an outlaw is detected at ×1.2. Default: **follow the encounter level**.
- **Q5** No cooldown after a slip: leaving and re-entering = a new roll (decision 5). Default: as decided; no anti-spam guard (movement already has stamina/travel cooldown).

---

### PM decisions on open questions (2026-11-05)
- Q1: separate guard location bases in law_settings (default) — accepted.
- Q2: **under a mask, fame does NOT count** (mask hides the face — consistent with FEAT-199/201 witness rule) AND the ×0.75 mask factor applies.
- Q3: toast + notification — accepted. Q4: outlaw multiplier follows outlaw_min_level — accepted. Q5: no cooldown after a slip — accepted.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**All dev / QA / docs tasks: do NOT commit, push, or `git add` — the user commits once at the end.**

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **character-service core + migration:** migration `043_guard_detection` (§3.1, guarded, seeds level multipliers only when the column is added; downgrade drops); models `LawSettings`/`LawLevel` columns; `law_core`: fields, `_BOOL_FIELDS`, `Level.detect_pct`, `DEFAULT_LEVELS`, `SQL_SELECT_LEVELS`, `levels_from_rows` (6-col tolerant), marker literals, `detection_base_pct`, `detection_chance` (§3.2), `LOG_SLIPPED`, `MAX_DETECT_LEVEL_PCT`, validation; schemas (`LawSettingsFields` optional new fields, `LawLevelOut/In.detect_pct`, `TeleportResult.law_slipped`); `law_crud.update_settings` (`_OPTIONAL_SETTINGS` + per-level optional `detect_pct`), `settings_out` with new fields. No commits/pushes/`git add`. | Backend Developer | DONE | `app/alembic/versions/043_guard_detection.py`, `app/models.py`, `app/law_core.py`, `app/law_crud.py`, `app/schemas.py` | — | `py_compile` OK; migration up/down/re-run idempotent on MySQL; old admin payload without new fields saves and keeps values. |
| 2 | **character-service entry roll:** `EntryResult`, `detection_rng`, `check_entry`, `evaluate_entry` wrapper, `detection_chance_for` (local `import shadow_crud`), slip log, chance/roll on the encounter log (§3.3); `law_notify.WS_SLIPPED` + `slipped_message`; `slip_notice`; `update_location` + `execute_teleport` + teleport route switch to `check_entry`, add `law_slipped`, publish the notice after commit (§3.4). No commits/pushes/`git add`. | Backend Developer | DONE | `app/law_crud.py`, `app/law_notify.py`, `app/main.py`, `app/crud.py` | 1 | Exit order unchanged (cooldown before roll); no roll when not moving; slip → no encounter, no lock, log row `slipped`; detected → today's behaviour + chance/roll in log; py_compile OK. |
| 3 | **locations-service pass-through:** `LawArrival`, `_law_slipped_from`, `_update_character_location` return, `_post_response(new_post, arrival)`, `PostResponse.law_slipped`; `move_and_post` / `quick_move` callers. No commits/pushes/`git add`. | Backend Developer | DONE | `locations-service/app/main.py`, `locations-service/app/schemas.py` | 2 (contract only) | Old character-service response (no field) → `law_slipped` absent/None; py_compile OK. |
| 4 | **Frontend player notice:** toast «Вы проскользнули мимо стражи» on `law_slipped === true` in `handleSubmitPost`, `handleQuickMove`, `TeleportMenu`; types (`teleportSlice.TeleportResult.law_slipped?: boolean`, move response generics). No commits/pushes/`git add`. | Frontend Developer | DONE | `LocationPage.tsx`, `TeleportMenu.tsx`, `redux/slices/teleportSlice.ts` | 2, 3 | TS only, no `React.FC`; `npx tsc --noEmit` + `npm run build` pass (in Docker). |
| 5 | **Frontend admin settings:** group «Обнаружение стражей» + levels column «Заметность, %» (§3.7), `api/lawAdmin.ts` types/constants, client validation mirroring the backend; `LawPanel.tsx` label `slipped` (+ show chance/roll if the panel does not already). No commits/pushes/`git add`. | Frontend Developer | DONE | `api/lawAdmin.ts`, `Admin/ReputationPage/LawSettingsTab.tsx`, `Admin/CharactersPage/tabs/LawPanel.tsx` | 1 | Tailwind + design system, adaptive at 360 px, Russian errors shown, tsc + build pass. |
| 6 | **QA character-service:** `law_world` default `detection_rng` → always detected (§3.5); unit tests of `detection_chance` (each factor, per-guard n=1/2/3, mask ×0.75, fame, level multipliers, clamp 5/100, worked examples of §3.2), `detection_base_pct` (markers, None/unknown → default), validation (bounds, min>max, level 0–500); migration 043 test (columns, seeded 60/80/100/120/140, idempotent); entry: slipped (FixedRng 0.9999) → no encounter / no `law_encounter_id` / log `slipped` with chance+roll / notice `law_slipped` progress; detected → encounter log has chance+roll; `detect_enabled=false` → always encounter; flee cooldown → no roll & no slip; same-location post → no roll; outlaw without wanted → criminal multiplier; guard count from `guards_at` (KO'd/dead excluded); stealth/subclass/mask/fame read through (equipped mask item, fame row); teleport path slipped → `TeleportResult.law_slipped` + notice; update_location response field; admin settings GET/PUT with and without new fields; full character-service suite green. No commits/pushes/`git add`. | QA Test | DONE | `character-service/app/tests/test_law_detection.py` (new), `tests/law_world.py`, adjust affected tests | 1, 2 | All new + existing tests pass in the container. |
| 7 | **QA locations-service:** update `test_law_locations.py` / `test_country_prison.py` to the `LawArrival` contract; `law_slipped` passes through move_and_post / quick_move; absent field → no `law_slipped`; POST_IN_PLACE → no call. No commits/pushes/`git add`. | QA Test | DONE | `locations-service/app/tests/test_law_locations.py`, `tests/test_country_prison.py` | 3 | locations-service suite green in the container. |
| 8 | **Docs:** `docs/services/character-service.md` (law: entry roll, formula, settings, log action, notice, response field, migration 043), `docs/services/locations-service.md` (`law_slipped` in PostResponse / update_location contract); `docs/ISSUES.md` only if something new found. No commits/pushes/`git add`. | QA Test | DONE | docs | 1–3 | Docs match code. |
| 9 | **Review:** code vs §3; py_compile; character-service + locations-service suites; tsc + build; migration on the dev DB. **Live verification on localhost** (Chrome allowed): a wanted character enters a guarded location repeatedly with stealth set high / detection min lowered → at least one «проскользнули» toast + bell notification and no lock; with `detect_enabled` off → always the encounter; teleport master into a guarded location → roll applies; post in the same location → no roll (law log unchanged); flee cooldown → no roll; admin tab saves the new fields, levels column, LawPanel shows «Проскользнул мимо стражи» with chance/roll; zero console errors; player responses carry no chance numbers. | Reviewer | DONE | all | 1–8 | PASS only with automated results + live verification recorded in §5. |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-05 (deploy gate for FEAT-201 + FEAT-202 + FEAT-203)
**Result:** PASS

#### Code vs §1 / §3 / PM decisions
- `law_core.detection_chance`: base by marker (own `detect_base_*` columns, unknown/None → default) × (1 + per_guard·(n−1)) × (1 − clamped stealth reduction) × fame (dropped under a mask — PM Q2) × mask factor × level `detect_pct`, clamped to `[detect_min, detect_max]`, 2 dp. Same multiplicative shape as `shadow_core.member_chance`. OK.
- `law_crud.check_entry`: exit order NPC → open encounter → jailed → no region → no live guard (`guards_at` excludes dead / KO'd) → **flee cooldown before the roll** → not wanted and not outlaw → level (outlaw floor) → roll. Stealth via `stealth_info` (subclass points, FEAT-195 cap); mask / fame / marker via `shadow_crud` (local import, no cycle). Slip: unique `law:slip:…` log row with chance/roll, no encounter, no `law_encounter_id`, no cooldown. Detected: unchanged FEAT-198 path, with chance/roll on the encounter log. `detect_enabled=false` → always detected, chance/roll NULL. `evaluate_entry` kept as a wrapper.
- `update_location`: roll only when `moving`; the slip notice is published after commit (best-effort). `execute_teleport`: roll only when the location changes; the route publishes the slip notice after commit; `TeleportResult.law_slipped`.
- `law_notify`: `law_slipped`, category `progress`, text without numbers.
- Settings: 10 `law_settings` fields + `law_levels.detect_pct`; all optional on input (an old client keeps stored values — verified live); validation 0–100, min ≤ max, level 0–500 (Russian messages).
- Migration `043_guard_detection` (revises 042, 19-char id, information_schema-guarded, seeds 60/80/100/120/140 only when the column is added, downgrade drops). Single head.
- locations-service: `LawArrival` NamedTuple, `_law_slipped_from` (`is True` only), `PostResponse.law_slipped`; POST_IN_PLACE never calls update_location.
- Frontend: toast on `law_slipped === true` (move_and_post, quick move, teleport); admin group «Обнаружение стражей» + «Заметность, %» column; client validation mirrors the backend; Tailwind / design-system classes, responsive grid, no `React.FC`; LawPanel label «Проскользнул мимо стражи» with chance/roll.
- Security: roll server-side (`secrets.SystemRandom` via `detection_rng`); player responses carry only a boolean (verified live: no chance/roll keys in move responses, notification text has no numbers); admin endpoints under the existing `reputation:settings`; no new endpoints / permissions.

#### Small fix applied by Reviewer
- `LawPanel.tsx`: a `slipped` log row showed the raw source code (`move` / `quick_move`) as its reason; now mapped through the existing `SOURCE_LABELS` («переход» / «быстрый переход» / «телепорт»). tsc + build re-run: PASS.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (re-run after the fix — PASS)
- [x] `npm run build` — PASS (re-run after the fix — PASS)
- [x] `py_compile` — PASS (all 53 modified/new .py files)
- [x] `pytest` (throwaway containers from the service images, `--network none`): character-service 8760 passed / 1 skipped; locations-service 2831 passed; battle-service 1859 passed; inventory-service 2448 passed; character-attributes-service 975 passed / 2 skipped / 1 xpassed; user-service 776 passed; dungeon-service econ tests + `test_feat175_entry` 476 passed — PASS
- [x] `scripts/check_econ_copies.sh` — PASS
- [x] `docker compose config` (dev, and dev + prod) — PASS
- [x] Alembic: single head per service and DB at head — attributes `009_add_stealth`, inventory `035_item_stealth_modifier`, locations `057_country_prison_district`, character `043_guard_detection`, battle `009_battle_law_encounter`, user `0033` — PASS
- [x] Live verification — PASS

#### Live Verification Results (http://localhost, admin, character Ашари 763)
- Setup: wanted 400 (Преступник) in region 14; start at «Пепельные Тропы» (353); target «Место Падения» (1618, dangerous, 1 live guard).
- Stealth 60 (−30 %), no mask: 8 entries via move_and_post → chance 28.00 each time (40 × 0.7 × 1.0): 3 slips, 5 encounters. Slip responses: `law_slipped: true`, no encounter, `law_encounter_id` stays NULL; notification «Вы проскользнули мимо стражи в «Место Падения»» delivered; no chance/roll in any player response.
- Mask worn (an item flagged `is_mask` temporarily): chance 21.00 (× 0.75): 4 slips, 1 encounter.
- `detect_enabled` off (saved through the admin UI checkbox): 4/4 entries → encounter, log chance/roll NULL.
- Stealth 300 + mask: chance clamped to 5.00; UI quick move → toast «Вы проскользнули мимо стражи» 🕶️ + notification popup; law_log `slipped`, reason `quick_move`.
- Post in the same location (POST_IN_PLACE): no `law_slipped` / `law_encounter`, no new law_log row.
- Admin «Закон»: group, checkbox, formula hint and the levels column render; client validation «Обнаружение стражей: минимум больше максимума»; server validation for min > max, level 600 %, base 101 % → 400 with Russian text; an old-client payload without the new fields → 200, stored values kept.
- Admin character → «Репутация» → «Журнал закона»: «Проскользнул мимо стражи» rows with «шанс 21%, бросок 38.12».
- FEAT-201: profile shows «Скрытность 300 / −87,5 % к шансу быть замеченным». FEAT-202: country prison configured temporarily; villain surrender → jailed in «Тюрьма страны «Шинзо»»; banner on the location page (no bail, escape 25 %).
- Console: zero errors on the location / admin / profile pages (including after reload).
- Teleport master: not exercised live; covered by `test_law_detection.py` (slip → `TeleportResult.law_slipped` + notice).
- Local data: mysqldump taken before and after; the pre-test dump was restored (character, wanted, law_log, mask flag, country prison and settings are back to the original).

#### Deploy readiness (201 + 202 + 203 on top of 331e4b9)
Ready. Migrations in one deploy: attributes 009, inventory 035, locations 057, character 041 → 042 → 043 (fail-fast at container start). All contract changes are additive and tolerate deploy skew (§3.8).

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `Admin/CharactersPage/tabs/LawPanel.tsx` (log reason) | Raw source code shown for `slipped` rows | Reviewer | FIXED |

---

## 6. Logging (filled by all agents — in Russian)

Running log of progress updates. Each agent writes brief Russian entries here.

```
[LOG] 2026-11-05 — PM: фича создана, решения пользователя зафиксированы; анализ и проектирование — одним агентом (небольшая доработка известного кода)
[LOG] 2026-11-05 — Аналитик: разобран путь входа (evaluate_entry и два вызова — update_location и телепорт), подсчёт стражников (guards_at), чтение скрытности/маски/славы/типа локации, настройки закона и тени, уведомления, точки фронтенда; риск — существующие тесты входа станут случайными без заглушки броска
[LOG] 2026-11-05 — Архитектор: настройки — в law_settings (+ множитель тяжести в law_levels), миграция 043; формула в law_core с границами 5–100 %; бросок после всех прежних проверок (кулдаун бегства раньше броска), отдельная точка подмены detection_rng; при проскальзывании — запись 'slipped' в журнал закона, уведомление law_slipped (категория «прогресс») и поле law_slipped в ответах; 9 задач, статус IN_PROGRESS; 5 открытых вопросов с решениями по умолчанию
[LOG] 2026-11-05 — Backend Developer: задачи 1–3 готовы. Миграция 043_guard_detection (10 полей в law_settings + detect_pct в law_levels с засевом 60/80/100/120/140), проверена на локальной MySQL: up / down / up и повторный прогон — без изменений; формула обнаружения в law_core (под маской слава не учитывается, ×0,75 — решение PM по Q2); check_entry с броском после кулдауна бегства, запись 'slipped' в журнал, уведомление law_slipped (категория «прогресс»), поле law_slipped в ответах update_location / телепорта / move_and_post / quick_move; новые поля настроек необязательны на входе. Тестовый мир law_world по умолчанию «всегда заметили». Подправлены закреплённые старым контрактом тесты (test_law_core — колонки миграций и строка настроек; locations: test_law_locations / test_country_prison — LawArrival; test_bp_tracking / test_post_drafts — у фиктивного поста-MagicMock явно law_encounter/law_slipped = None). Полные наборы зелёные: character-service 8608 passed, locations-service 2810 passed
[LOG] 2026-11-05 — Frontend Developer: задачи 4–5 готовы. Игрок: тост «Вы проскользнули мимо стражи» (🕶️) при law_slipped === true в move_and_post, быстром перемещении и телепорте (тип TeleportResult.law_slipped). Админка «Закон»: группа «Обнаружение стражей» — переключатель «Стража может не заметить», базы по типам локаций, за лишнего стражника, множитель маски, минимум/максимум, подсказка с формулой (слава не под маской); в таблице ступеней колонка «Заметность, %» (0–500); клиентская проверка как на бэкенде (min ≤ max). LawPanel: запись журнала 'slipped' — «Проскользнул мимо стражи» (шанс/бросок уже выводятся). tsc --noEmit и npm run build в контейнере — без ошибок
[LOG] 2026-11-05 — QA Test: задачи 6–8 готовы. Новый tests/test_law_detection.py (152 теста): формула обнаружения — примеры 60/55/100/10,5/5, базы по типу локации (включая «прочее»), +10 % за каждого лишнего стражника, скрытность с бонусом подкласса и капами, слава, маска (слава не считается + ×0,75), ступени 60–140, границы; порядок пропусков без броска (встреча, тюрьма, нет стражи, оглушённые/мёртвые не считаются, кулдаун бегства, нет розыска, NPC); проскальзывание — без встречи и блокировки, запись 'slipped' с шансом/броском и уникальным ключом, уведомление после коммита, law_slipped в ответах update_location и телепорта; каждый вход — новый бросок; пост на месте без броска; настройки — новые поля, необязательность, тексты ошибок; миграция 043 up/down/повтор на эмуляции MySQL (правки ступеней сохраняются). locations-service: +14 тестов law_slipped (move_and_post, quick_move, старый character-service, пост на месте). Документация character-service.md / locations-service.md обновлена. Полные наборы: character-service 8760 passed, locations-service 2827 passed. Багов не найдено
[LOG] 2026-11-05 — Reviewer: начал проверку FEAT-203 и общий допуск к выкатке 201+202+203
[LOG] 2026-11-05 — Reviewer: сессию прервало отключение света; контейнеры поднялись, локальные данные до сбоя не менялись — проверка продолжена
[LOG] 2026-11-05 — Reviewer: автоматические проверки зелёные (character 8760, locations 2831, battle 1859, inventory 2448, attributes 975, user 776, dungeon econ+вход 476; tsc, build, py_compile, compose, копии econ; по одной голове Alembic в каждом сервисе)
[LOG] 2026-11-05 — Reviewer: живая проверка: шанс 28 % без маски (3 прохода из 8), 21 % в маске, 5 % на минимуме — тост и уведомление «проскользнули», запись в журнале закона; с выключенным обнаружением — всегда встреча; пост на месте — без броска; настройки и проверки в админке работают; скрытность в профиле и баннер тюрьмы страны — ок; ошибок в консоли нет; локальная база восстановлена из дампа
[LOG] 2026-11-05 — Reviewer: мелкая правка — у записи «Проскользнул мимо стражи» в журнале закона вместо кода источника теперь «переход / быстрый переход / телепорт»
[LOG] 2026-11-05 — Reviewer: проверка завершена, результат PASS; 201+202+203 готовы к выкатке
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- ...

### Что изменилось от первоначального плана
- ...

### Оставшиеся риски / follow-up задачи
- ...

**Статус: DONE (2026-11-05), ревью PASS.** При входе разыскиваемого / «Вне закона» в локацию со стражником — бросок обнаружения: база места × (1 + 10 % за лишнего стражника) × (1 − скрытность) × слава (не под маской) × маска 0.75 × заметность ступени розыска (0.6–1.4), 5–100 %. Проскользнул — без встречи, тост + уведомление, запись в журнал закона; каждый вход — новый бросок. Всё настраивается во вкладке «Закон». Выкатывается вместе с FEAT-201 и FEAT-202.

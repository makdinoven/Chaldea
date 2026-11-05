# FEAT-202: Тюрьма страны (район) и отделения краёв

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-04 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас (FEAT-198, на проде 331e4b9) тюрьма — одна локация на край (`Regions.jail_location_id`). Пользователь: «Хотим сделать тюрьму как отдельный район. Конкретно тюрьма 1 на страну, куда попадают только худшие из худших. А вот в краях могут свои отделения для задержания более мелких преступников.»
Выкатывается вместе с FEAT-201 «Скрытность» (готова, ревью PASS, не запушена).

### Решения пользователя (2026-11-04, «как предлагаешь»)
1. **Тюрьма страны** — отдельный **район** (district, несколько локаций: камеры, двор и т.п.), **одна на страну**, назначается админом. Туда попадают тяжёлые преступники: уровни розыска **«Злодей» и «Враг края»** (сроки от 3 дней). Порог — настройка в админке (уровень, начиная с которого — тюрьма страны).
2. **Отделение края** — как сейчас, **одна локация** на край (существующий `Regions.jail_location_id`, в UI переименовать в «Отделение стражи» / «Участок»); туда — «Подозреваемый», «Нарушитель», «Преступник».
3. **Свобода внутри тюрьмы страны:** заключённый может **перемещаться между локациями района тюрьмы и писать там посты**; выйти за пределы района нельзя. В отделении края — как сейчас (одна локация).
4. **Тюрьма страны: залога нет**; **побег есть**, но шанс заметно ниже (по умолчанию ×0.5 к шансу отделения) и перезарядка длиннее (по умолчанию 12 ч вместо 6 ч) — настройки в админке.
5. **Отсутствие учреждений:** в крае нет отделения → мелкого везут в тюрьму страны; в стране нет тюрьмы → тяжёлого сажают в отделение края; «сдаться» недоступно, только если нет ни того, ни другого.
6. **После срока** персонаж остаётся там, где сидел (выход «у ворот»), дальше сам.

### Решения пользователя по вопросам аналитика (2026-11-05, «как предлагаешь»)
1. Побег из тюрьмы страны — тяжёлый розыск в **крае преступления** (`law_jail_terms.region_id`).
2. Свободные персонажи **могут заходить** в район тюрьмы как посетители.
3. **Быстрое перемещение** между локациями тюрьмы страны — разрешено (для заключённого — только внутри района).
4. Во вкладке «Залог» у банкира заключённые тюрьмы страны **скрыты**.

### Прочее
- Куда помещается заключённый в районе тюрьмы страны: в «камеру по умолчанию» — локация района, назначаемая админом (входная локация района), иначе первая локация района.
- Срок/залог/побег/стафф-освобождение/уведомления — как в FEAT-198, с учётом п.4.
- Игроку видно, где он сидит: «Тюрьма страны «X»» или «Отделение стражи края «Y»».

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Baseline: prod `331e4b9` (FEAT-198/199) + the uncommitted FEAT-201 working tree. Latest migrations: character-service `041_stealth` (uncommitted), locations-service `056_quest_fame`. Paths are relative to `services/`.

### 2.1 World model (locations-service owns it; character-service reads it by raw SQL)

- `locations-service/app/models.py`:
  - `Country` (:28). Fields: `id`, `name`, `description`, `leader_id`, `map_image_url`, `emblem_url`, `map_land_settings`, `area_id`, `x`, `y`, `is_hidden`, `recommended_level_min/max`. It has **no prison field**.
  - `Region` (:51). `country_id` NOT NULL FK CASCADE, `entrance_location_id`, `jail_location_id` (:63, FEAT-198, FK Locations SET NULL, indexed).
  - `District` (:81). `region_id` NOT NULL, **`parent_district_id`** (nested districts, FK CASCADE), `entrance_location_id` (FK Locations SET NULL), `marker_type` ENUM `safe|dangerous|dungeon|farm` (no `prison` marker), `sort_order`.
  - `Location` (:118). `district_id` (nullable), `region_id` (set for standalone locations), `parent_id` (location hierarchy), `type` ENUM `location|subdistrict`, `sort_order`, `no_quick_move`.
  - `LocationNeighbor` (:161): directed rows, created in both directions, with `energy_cost`.
- **Local data shape** (`fogdatabase`):
  - 2287 locations: 0 use `parent_id`, 0 `type='subdistrict'`.
  - 328 districts: **182 are nested** (depth ≤ 1 today; the parent is always in the same region).
  - **Only 1 district has `entrance_location_id` set.**
  - Every `Regions.jail_location_id` is NULL.
  - Consequences:
    - "Locations of the prison district" must be the **recursive subtree** over `parent_district_id`. Tolerate the `parent_id` chain too, like `SQL_RESOLVE_LOCATION`.
    - The "default cell" fallback (the first location by `sort_order, id`) will be the common case.
- **Location → region/country resolution:** `econ_core.SQL_RESOLVE_LOCATION` (locations `econ_core.py:691`, one of 4 copies). It is a recursive CTE over `parent_id`, then `COALESCE(district.region_id, location.region_id)` → `Regions.country_id`.
  - character-service: `reputation_crud.location_region` (:170) via `econ_ledger.resolve_location`.
  - character-service: `reputation_crud.region_infos` (:152) returns region + country id/name.
  - character-service: `reputation_crud.country_region_ids` (:163).
- **Admin editors (backend):**
  - Country:
    - `PUT /locations/countries/{id}/update` (`main.py:350`, `locations:update`) → `crud.update_country` (:449). A generic `setattr` over `CountryUpdate` (`schemas.py:49`), with no validation hook.
    - `CountryRead` (:60). `GET /countries/{id}/details` (`crud.get_country_details` :463) returns regions only, **no districts**.
  - Region: `crud.update_region` (:536) validates `jail_location_id` with `validate_region_jail_location` (:527: `econ_ledger.resolve_location` must equal this region, else 400 `REGION_JAIL_WRONG_REGION`). The region DTOs expose it at `crud.py:786` and `:2091`.
  - District list: `GET /locations/districts/lookup` (`main.py:316`) returns `{id, name}` of **all** districts (no region/country). There is no country-scoped district list.
- **Validation for the new country field:**
  - The district exists.
  - `Districts.region_id → Regions.country_id == this country` → else 400 (Russian message).
  - Optionally, the subtree has ≥ 1 location.
  - Re-check at sentencing: a district can be re-parented to another region (`PUT /districts/{id}/update`), and the FK only covers deletion.

### 2.2 Current jail flow (character-service, sync SQLAlchemy; foreign tables via raw `text()`)

- **Facility lookup = one function today:** `law_crud.region_jail_location(db, region_id)` (`law_crud.py:124`, `SELECT jail_location_id FROM Regions`). Every "has a jail" decision calls it:
  - `evaluate_entry` (:530, snapshot `law_encounters.has_jail`);
  - `encounter_options` (:580 → `law_core.options(is_outlaw, has_jail, flee_used)` :316);
  - `encounter_out` (:593);
  - `law_flows.send_to_jail` (:78, 409 `MSG_NO_JAIL`);
  - `law_flows.choose` (:248);
  - `law_flows` battle result "lost" (:363);
  - `law_flows.auto_resolve` (:384).
  - **All 7 must switch to one resolver**, e.g. `resolve_jail(db, region_id, level_code) -> JailTarget(kind 'station'|'country', location_id, district_id, country_id, display name) | None`, implementing decision 5:
    - level ≥ threshold → country prison, else the station;
    - the chosen one is missing → the other;
    - neither → None (no `surrender`; forced fine as today).
  - The level is `enc.level_code` (already snapshotted; it includes the outlaw raise to `outlaw_min_level`).
- **`law_flows.send_to_jail`** (`law_flows.py:66-113`):
  - Re-reads the facility → `db.rollback()`.
  - `await main._prepare_move(..., "jail")` (`main.py:929`: refuse in battle/dungeon, cancel gathering, `notify_character_left_location`).
  - Then, in one TX: `crud.apply_admin_move(commit=False, event_type="jail")` (`crud.py:4111`; works across regions) + `law_crud.jail_writes`.
  - Notification `law_notify.jailed_message(region_name, …)` (`law_notify.py:78`, «Стража края «X» заключила вас под стражу») → needs facility-specific text.
- **`law_crud.jail_writes`** (:820) writes:
  - `characters.jailed_until`;
  - `characters.jail_region_id = enc.region_id` (written, **read nowhere** — grep);
  - a `law_jail_terms` row (`region_id` = the **encounter/wanted region**, `location_id` = the jail location, `bail_price`, `next_escape_at=None`);
  - wanted → 0;
  - encounter `jailed`.
  - The country prison additionally needs the facility, country and district on the term, plus the movement snapshot on the character.
- **`law_jail_terms`** (`models.py:1342`, migration `039_law`) has no facility/district/country columns. `region_id` drives:
  - the bail ledger target (`_post_bail` :999, `AccountRef.region(term.region_id)`);
  - the escape crime region (`escape` :947, `register_crime(region_id=term.region_id, floor=heavy_wanted)`);
  - `region_name` in `jail_out`/`prisoners`.
  - Keep `region_id` = the wanted region.
- **Escape** (`law_crud.escape` :919):
  - Chance `escape_chance` (:228; FEAT-201: stealth only, `lc.chance(base, per_point, min, max, stealth)`).
  - Failure: `lc.extended_until` (never shortens, capped by `max_remaining_jail_hours`). Cooldown `next_escape_at = now + escape_cooldown_hours` (:956).
  - Country prison: the chance × `country_escape_multiplier` (the Architect picks before/after the min/max clamp; after is simpler and keeps "×0.5 of the station chance" literal) and cooldown = `country_escape_cooldown_hours`.
  - `jail_out` (:642, `escape_chance_pct`) must use the same facility-aware function.
- **Bail:**
  - `self_bail` (:977) and `bail_other` (:1024, banker in any region) → a country term must get a 409 («Из тюрьмы страны нельзя выйти под залог»).
  - `jail_out.bail_price`, `prisoners()` (:723, the bank «Залог» list) and `LawPrisonerOut` need `bail_available` (or a nullable price), or the list excludes country prisoners.
- **Facility-agnostic, unchanged:**
  - staff release `staff_release` (:1095);
  - `_end_term` (:910, clears `jailed_until`/`jail_region_id`; must also clear any new character column);
  - served terms `law_pass._served_terms` (:111);
  - `auto_resolve` retries.
- **Settings** (`law_settings` single row):
  - Code: `law_core.SETTINGS_FIELDS` (:172), `_DECIMAL_FIELDS`, `SQL_SELECT_SETTINGS`, the `LawSettings` dataclass (:141-160), `validate` (:372; `outlaw_min_level ∈ LEVEL_CODES` is the pattern for the new level threshold). `update_settings` is generic. Schema `LawSettingsFields` (`schemas.py:3817`).
  - New fields: `country_prison_min_level` (default `villain`), `country_escape_multiplier` (0.5), `country_escape_cooldown_hours` (12, 1..168).
- **Player DTOs** (`schemas.py`): `LawEncounterOut` (:3679, `has_jail`, `jail_hours`), `LawJailOut` (:3712), `LawPrisonerOut` (:3790). Additive fields:
  - `facility` (`station|country`);
  - a facility display name;
  - `district_id`/`district_name`;
  - allowed prison location ids (for the frontend move UI);
  - `bail_available`.

### 2.3 Movement inside the prison district

- **The lock:** reason `jail` (`jailed_until > now`) in `activity_lock.compute_lock`. Copies:
  - `character-service/app/activity_lock.py`, canonical;
  - `locations-service/app/activity_lock.py`, async;
  - `battle-service/app/activity_lock.py`, async;
  - `inventory-service/app/activity_lock.py`, sync.
  - The upper part is byte-identical, enforced by `locations-service/app/tests/test_law_locations.py:187-207` (split on the `# Shared-DB read` marker).
  - **Recommendation: leave the lock untouched** (same reason, same dict). Do the district check *next to* it in the two services that move characters. Battle, inventory and the 4 copies then do not change.
- **Authority = character-service `main.update_location`** (`main.py:2345`):
  - Today: row-locks the character, refuses reason `jail`/`law_encounter` with 409 (:2378-2381), then sets the location and calls `evaluate_entry`.
  - New: reason `jail` **and** a district snapshot on the character **and** `new_location_id` in the prison subtree → allow (house reset as usual; `evaluate_entry` already returns None for jailed characters, `law_crud.py:507`). Anything else → 409 as now.
  - The whitelist must come from a **snapshot** (e.g. new `characters.jail_district_id` + `law_jail_terms.district_id`), not live `Countries`: re-assigning the prison mid-term must not strand or free prisoners.
  - Membership query: a recursive CTE over `Districts.parent_district_id` from the prison district → `Locations.district_id IN (subtree)`. Valid on MySQL 8 and SQLite (character-service tests run on SQLite).
- **locations-service:**
  - `check_not_locked_for_post` (`main.py:184`): reason `jail` is allowed only when `location_id == characters.current_location_id` (returns True).
    - Extend: also allow when the destination is in the prisoner's prison subtree. Read `characters.jail_district_id` by raw SQL **outside** the shared lock part, with a skew fallback like `_is_missing_law_column` at `activity_lock.py:161`.
    - It must become tri-state (`no` / `same location` / `district move`), because `move_and_post` uses the True flag to **skip** `update_location` (:1453-1459). A district move must call `update_location`.
    - Callers: `create_new_post` (`/posts/`, :939; it still requires being physically there) and `move_and_post` (:1329).
  - `move_and_post` (:1306): the neighbor check (:1375), stamina, travel cooldown and `set_travel_cooldown` apply unchanged. **Neighbor edges between the district's locations must exist** (admin content; no auto-edges).
  - `quick_move` (:1597) calls plain `check_not_activity_locked` (:1611) and then `update_location` (:1713, `quick_move`). It needs the same exception if quick moves are allowed in the prison.
  - `_update_character_location` (:217) passes a 409 through unchanged, so leaving the district yields «Персонаж в тюрьме — осталось …».
- **Already blocked by the lock (no change):**
  - teleport master (`crud.execute_teleport` lock check at `crud.py:3797`);
  - home scroll (`main.internal_home_teleport` :1077 + the inventory lock copy);
  - battles, «Нападение», gathering, trade, auction, crafting, NPC dialogue, dungeons.
- **Not lock-checked:**
  - `POST /characters/admin/{id}/move` (`main.py:970`). Staff can move a prisoner out of the district, and the term continues. Same as today with the station. Acceptable; the Architect may block it or auto-release.
  - dungeon KO return;
  - approval.

### 2.4 Frontend (`services/frontend/app-chaldea/src/`)

- `components/pages/LocationPage/JailBanner.tsx` (193 lines): «Персонаж в тюрьме края «X»» (:111), bail button/confirm (:153/:183), escape. Needed: the facility title («Тюрьма страны «X»» / «Отделение стражи края «Y»»), no bail for the country prison.
- `components/CommonComponents/ActivityLockBanner.tsx:54`: reason `jail` → `JailBanner`. No change.
- `components/pages/LocationPage/LocationPage.tsx`:
  - `jailPostingAllowed` (:611) = `jail && isCharacterHere`.
  - `actionsLocked` (:77) dims `NeighborsSection` (:716) and hides the move/«написать пост» UI for neighbors (:813).
  - The lock card (:923-962) says «только в самой тюремной локации».
  - Country prison: take the allowed location ids from `GET …/law/jail` (`api/law.ts:155` `fetchLawJail`) to enable neighbors/move/post for locations in the set and to change the card text. Page `location.district_id` exists (`LocationPage/types.ts:104`), but neighbors carry no district, so a server-provided id list is simpler.
- `hooks/useActivityLock.ts`: no change if the lock is untouched.
- `components/ProfilePage/ReputationTab/ReputationTab.tsx:141-150`: «В тюрьме края … · залог N». Needs the facility title and no bail line for the country prison.
- `components/pages/LocationPage/GuardEncounterModal.tsx`: the surrender confirm (:165 «в тюрьму края… по залогу») and the option hint (:264). They need the facility in the encounter DTO.
- `components/pages/LocationPage/BankModal/BankBailTab.tsx`: the prisoner list. Hide or disable country prisoners.
- `api/law.ts` (`LawJailOut` :45 etc.), `api/lawAdmin.ts`: new fields.
- Admin:
  - `AdminLocationsPage/EditForms/EditRegionForm/EditRegionForm.tsx:276-283`: «ТЮРЬМА КРАЯ» → «Отделение стражи» plus the hint.
  - `AdminLocationsPage/EditForms/EditCountryForm/EditCountryForm.tsx` (371 lines; `handleSubmit` :137 → `onSuccess(formData)`): add «Тюрьма страны (район)».
    - `EntityPicker` (`Admin/DungeonsPage/editor/pickers.tsx:18`) has no `district` kind.
    - Options: add a `district` kind, or a `<select>` fed by a new `GET /locations/countries/{id}/districts` (or extend `/districts/lookup` with region/country).
  - `Admin/ReputationPage/LawSettingsTab.tsx:80-89` («Тюрьма» group): the 3 new settings (level select like `outlaw_min_level`).
  - `Admin/CharactersPage/tabs/LawPanel.tsx:321-326`: show the facility.
- Rules: `.tsx` + Tailwind + design system, 360 px+, no `React.FC`. If the Country/Region forms still have SCSS and their styles are touched → migrate (CLAUDE.md §10.8).

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service | migration 042, facility resolver, jail_writes/escape/bail/DTO/prisoners, send_to_jail target, notification texts, `update_location` district exception, settings | `alembic/versions/042_*.py`, `models.py`, `law_core.py`, `law_crud.py`, `law_flows.py`, `law_notify.py`, `main.py`, `schemas.py`; tests `tests/law_world.py` (needs `Countries`/`Districts` in the SQLite world) |
| locations-service | migration 057 `Countries.prison_district_id`, model/schemas, `update_country` validation, country-scoped district list, `check_not_locked_for_post` tri-state, `move_and_post`/`quick_move` | `alembic/versions/057_*.py`, `models.py`, `schemas.py`, `crud.py`, `main.py` |
| frontend | jail UI, moves/posts inside the district, admin forms/settings | see 2.4 |
| battle / inventory / user / notification | none (lock contract unchanged) | — |

### Existing Patterns
- character-service:
  - sync SQLAlchemy; raw `text()` for locations-owned tables; Pydantic v1;
  - Alembic `alembic_version_character`, idempotent `_has_column`-guarded steps (039/040/041);
  - tests on SQLite worlds (`tests/law_world.py`).
- locations-service:
  - async (aiomysql); Alembic `alembic_version_locations` (guarded add_column + index + FK, see `055_region_jail_location.py`);
  - admin = `require_permission("locations:update")`.
- Law RBAC unchanged (`reputation:settings|manage|read`). No new permission rows, so the RBAC test is unaffected.

### Cross-Service Dependencies
```
locations-service move_and_post / quick_move ──PUT──> character-service /characters/internal/{id}/update_location   (contract unchanged; 409 passthrough)
character-service send_to_jail ──HTTP──> locations-service (cancel gathering, notify_character_left_location) via main._prepare_move   (unchanged)
character-service ──raw SQL──> Countries.prison_district_id, Districts, Locations   (new reads)
locations-service ──raw SQL──> characters.jail_district_id   (new read, skew fallback)
```

### DB Changes
- **locations-service `057_country_prison_district`:**
  - `Countries.prison_district_id BIGINT NULL` (BIGINT = `Districts.id`), own index `ix_countries_prison_district_id`, FK `Districts.id ON DELETE SET NULL`. Guarded like 055.
  - The default cell reuses `Districts.entrance_location_id` (exists), else the first subtree location by `sort_order, id`. No extra column needed.
- **character-service `042_country_prison`:**
  - `law_settings` + `country_prison_min_level VARCHAR(20) NOT NULL DEFAULT 'villain'`, `country_escape_multiplier DECIMAL(5,2) NOT NULL DEFAULT 0.50`, `country_escape_cooldown_hours INT NOT NULL DEFAULT 12`.
  - `law_jail_terms` + `facility VARCHAR(10) NOT NULL DEFAULT 'station'`, `country_id INT NULL`, `district_id INT NULL`.
  - `characters` + `jail_district_id INT NULL` (the movement whitelist snapshot; cleared in `_end_term`/staff release; only consulted while reason = `jail`, so a lazily expired value is harmless).
  - MySQL gotchas (memory «Грабли миграций MySQL»): no FK to locations-owned tables (039 convention), VARCHAR not ENUM, revision id ≤ 32 chars, an index for every FK column.
- Deploy skew: locations-service reading `characters.jail_district_id` before 042 → catch "unknown column" → treat it as no district.
- Rollback: drop the columns (and the Countries FK + index).

### Risks
- **Existing prisoners at deploy:** terms get `facility='station'` via the default and `jail_district_id` stays NULL, so behaviour is unchanged. Locally no region has a jail (prod presumably the same). No backfill.
- **Released/escaped prisoner inside the district:**
  - wanted is cleared at sentencing, but an **outlaw** (reputation tier) is stopped again by the first guard in the district → re-jail loop (exists today with the station as well);
  - an escapee's heavy floor goes to `term.region_id` (the crime region, possibly not the prison's region), so the prison region's guards ignore them unless they are an outlaw.
- **Guards inside the prison district:** `evaluate_entry` skips jailed characters (`law_crud.py:507`), so no encounter while serving. Free visitors can walk in through any neighbor edge (no access model).
- **Prison district in another region of the same country:**
  - the cross-region move works (`apply_admin_move`/`_prepare_move` are location-agnostic);
  - the term keeps the wanted region;
  - player texts must show the country prison name, not «край».
- **Teleports/home scroll while jailed:** already refused by the lock. Staff admin move is not (2.3).
- **District with no locations / re-parented to another country / deleted (SET NULL)** → the resolver falls back (decision 5). A prisoner already serving keeps the snapshot. If the district is deleted, its locations cascade-delete (`Locations.district_id` CASCADE) and the prisoner's `current_location_id` dangles. Staff release fixes it; note it in the admin hint.
- **No neighbor edges between prison locations** → the prisoner cannot move (silent). Admin content; hint text.
- **activity_lock:** exposing the prison set inside the lock dict would change all 4 copies + the parity test. The recommendation keeps them untouched.

### Open questions (genuine user decisions; defaults proposed)
1. Escape from the **country prison**: does the heavy wanted floor go to the original crime region (current code, `term.region_id`) or to the prison's region? Default: the crime region.
2. May **free characters enter** the prison district (visitors)? Default: yes (no access model exists; hidden/closed locations are a future plan).
3. **Quick move** between prison locations: allowed (default) or only a move with a post?
4. Bank «Залог» list: hide country prisoners (default) or list them as «залог невозможен»?

---

## 3. Architecture Decision (filled by Architect — in English)

Baseline: prod `331e4b9` (FEAT-198/199) + the uncommitted FEAT-201 working tree (escape = stealth only; `escape_chance(db, cid, settings)` in `law_crud.py:228`). Latest migrations: character `041_stealth`, locations `056_quest_fame`. Paths are relative to `services/`. The user decisions in §1 (both blocks) are FINAL and are implemented exactly as written below.

### 3.0 Summary of key decisions

| # | Decision | Why |
|---|---|---|
| P1 | **Two facility kinds: `station` (отделение стражи края = the existing `Regions.jail_location_id`, one location) and `country` (тюрьма страны = a district subtree, `Countries.prison_district_id`).** The DB value of the kind is `station` / `country`. | Decisions 1–2. Reuses FEAT-198's region column unchanged; only the UI name changes. |
| P2 | **One facility resolver in character-service** (`law_facility.py`, sync, raw SQL) replaces every `law_crud.region_jail_location` call (6 direct + `choose` through `encounter_options`). The choice itself is a **pure** function in `law_core` (unit-testable): level ≥ `country_prison_min_level` → country, else station; the preferred one missing → the other; neither → None (no `surrender`, forced fine as today). | Decision 5; analyst §2.2. One place, so the snapshot, the options, the move and the term can never disagree. |
| P3 | **"Country prison is usable"** = the country has `prison_district_id`, the district still exists, its region still belongs to **that** country (re-checked at every resolve: a district can be re-parented), and its **subtree** (district + nested sub-districts over `parent_district_id`, + locations hanging off them via `Locations.parent_id`) has ≥ 1 location. Otherwise it counts as missing (→ fallback). | Analyst §2.1 (182/328 districts are nested; the FK covers only deletion). |
| P4 | **Cell** = `Districts.entrance_location_id` of the prison district **if it is in the subtree**, else the first subtree location by `(depth, sort_order, id)`. | §1 «Прочее»; only 1 district locally has an entrance. |
| P5 | **Snapshot at sentencing:** `law_jail_terms.facility/country_id/district_id` + `characters.jail_district_id`. Movement checks use the **snapshot**, never live `Countries`, so re-assigning the prison mid-term neither strands nor frees anyone. `_end_term`, staff release and the law pass clear `characters.jail_district_id`. | Analyst §2.3. |
| P6 | **`activity_lock` (4 copies) is untouched.** The prison-district exception lives next to it: character-service `update_location` is the **authority** (row lock; allows a jailed move only into the snapshot subtree); locations-service pre-checks with a **tri-state** result so `move_and_post` calls `update_location` for a prison move, and `quick_move` gets the same exception. | Analyst recommendation; the parity test (`test_law_locations.py:187-207`) stays green. |
| P7 | **Country prison: no bail** (409 everywhere; the term stores `bail_price = 0`; DTO `bail_available=false`, `bail_price=null`; hidden from the bank «Залог» list). **Escape**: chance = the station chance (FEAT-201 stealth formula, after its min/max clamp) **× `country_escape_multiplier`** (0.5), rounded to 2 decimals; cooldown `country_escape_cooldown_hours` (12). The failure extension and the cap are the same as the station. Wanted on a successful escape → the **crime region** (`term.region_id`, unchanged code). | Decision 4 + analyst answers 1, 4. Multiplying **after** the clamp keeps «×0.5 от шанса отделения» literally true (the station max 50 % → the country max 25 %). |
| P8 | `law_jail_terms.region_id` keeps meaning **the wanted/crime region** (escape crime, bail treasury of a station term, `region_name`). The facility's own location/country/district live in the new columns. | Analyst §2.2. |
| P9 | **Visitors** may walk into the prison district (no access model; decision 2 of the analyst block). **Quick move** inside the district is allowed for prisoners (decision 3). Neighbour edges between the prison locations are admin content; the admin hint says so. | §1. |
| P10 | **Player-facing names:** `facility_name` = «Тюрьма страны «{country}»» or «Отделение стражи края «{region}»», built server-side (one helper) and used in DTOs, notifications and UI. | §1 «Прочее». |
| P11 | **Deploy skew both ways is non-fatal:** character-service reading `Countries.prison_district_id` before locations `057` → WARNING + "no country prison"; locations-service reading `characters.jail_district_id` before character `042` → WARNING + "no prison district" (today's behaviour). Only the specific unknown-column error is caught; anything else re-raises. | Memory «тихие отказы»; analyst §2.3. |
| P12 | No new permissions (country admin = `locations:update`; law settings = `reputation:settings`). The RBAC test is unaffected. | FEAT-198 L10. |

### 3.1 DB changes

#### locations-service — Alembic `057_country_prison_district` (down_revision `056_quest_fame`; 27 chars ≤ 32)
```sql
ALTER TABLE Countries ADD COLUMN prison_district_id BIGINT NULL;            -- BIGINT = Districts.id
CREATE INDEX ix_countries_prison_district_id ON Countries (prison_district_id);
ALTER TABLE Countries ADD CONSTRAINT fk_countries_prison_district
  FOREIGN KEY (prison_district_id) REFERENCES Districts(id) ON DELETE SET NULL;
```
- Guarded exactly like `055_region_jail_location.py` (`_columns`/`_indexes`/`_fks` checks; idempotent re-run).
- Developer: verify the real type of `Districts.id` in `models.py` and match it (BIGINT expected); the FK fails on a type mismatch.
- ORM `Country.prison_district_id = Column(BigInteger, ForeignKey("Districts.id", ondelete="SET NULL"), nullable=True, index=True)`. No relationship needed.
- Rollback: drop the FK, the index, the column. No backfill (every country starts without a prison).

#### character-service — Alembic `042_country_prison` (down_revision `041_stealth`; 18 chars)
```sql
ALTER TABLE law_settings
  ADD COLUMN country_prison_min_level      VARCHAR(20)  NOT NULL DEFAULT 'villain',  -- level code from which the country prison applies
  ADD COLUMN country_escape_multiplier     DECIMAL(5,2) NOT NULL DEFAULT 0.50,       -- × the station escape chance (after its clamp)
  ADD COLUMN country_escape_cooldown_hours INT          NOT NULL DEFAULT 12;         -- instead of escape_cooldown_hours

ALTER TABLE law_jail_terms
  ADD COLUMN facility    VARCHAR(10) NOT NULL DEFAULT 'station',   -- station | country (VARCHAR, not ENUM)
  ADD COLUMN country_id  INT NULL,                                 -- country of the prison (country terms only)
  ADD COLUMN district_id INT NULL;                                 -- prison district snapshot (country terms only)

ALTER TABLE characters
  ADD COLUMN jail_district_id INT NULL;   -- movement whitelist snapshot; consulted only while the lock reason is 'jail'
```
- No FKs to locations-owned tables (039 convention) → no extra indexes required. Revision id ≤ 32 chars; every step guarded with `_has_column` (039/040/041 pattern).
- Existing rows: terms become `facility='station'` via the default; `jail_district_id` stays NULL → behaviour identical to today. No backfill.
- ORM: `LawSettings` (3 columns), `LawJailTerm` (`facility = Column(String(10), nullable=False, default="station", server_default="station")`, `country_id`, `district_id`), `Character.jail_district_id`.
- Rollback: drop the 7 columns.

### 3.2 character-service: pure parts (`law_core.py`)

- Constants: `FACILITY_STATION = "station"`, `FACILITY_COUNTRY = "country"`, `FACILITIES`.
- `LawSettings` dataclass + `SETTINGS_FIELDS` + `_DECIMAL_FIELDS` (`country_escape_multiplier`) + `SQL_SELECT_SETTINGS`: the 3 new fields with the defaults above.
- `validate(...)` additions (Russian messages):
  - `country_prison_min_level` ∈ `LEVEL_CODES` → «Порог тюрьмы страны должен быть одним из уровней розыска» (same pattern as `outlaw_min_level`);
  - `country_escape_multiplier` 0..1 → «Множитель побега из тюрьмы страны: от 0 до 1» (0 = escape impossible; allowed);
  - `country_escape_cooldown_hours` 1..168 → «Перезарядка побега из тюрьмы страны: от 1 до 168 ч».
- `is_heavy(level_code, threshold_code, levels) -> bool` = `sort_order(level) >= sort_order(threshold)` (unknown code → False).
- `pick_facility(level_code, threshold_code, levels, has_station: bool, has_country: bool) -> Optional[str]`:
  ```
  preferred = country if is_heavy(...) else station
  if preferred available -> preferred; elif the other available -> the other; else None
  ```
- `country_escape_chance(station_chance: Decimal, multiplier: Decimal) -> Decimal` = `q2(station_chance × multiplier)`, never below 0.
- `facility_title(facility, country_name, region_name) -> str`:
  - country → «Тюрьма страны «{country_name}»»;
  - station → «Отделение стражи края «{region_name}»».
  - A missing name → «—» inside the quotes (never `None` in text).
- `options(is_outlaw, has_jail, flee_used)` is **unchanged**; callers pass `has_jail = resolve_jail(...) is not None`.

### 3.3 character-service: the resolver (`law_facility.py`, new, sync, raw `text()`)

```python
@dataclass(frozen=True)
class JailTarget:
    facility: str                 # 'station' | 'country'
    location_id: int              # the station location / the default cell
    region_id: int                # the facility's own region (station: the encounter region; country: the district's region)
    country_id: Optional[int]
    district_id: Optional[int]    # country only
    name: str                     # facility_title(...)
    district_name: Optional[str]  # country only

def station_location(db, region_id) -> Optional[int]          # = today's region_jail_location (moved; law_crud keeps an alias only if tests import it)
def prison_location_ids(db, district_id) -> List[int]          # ordered subtree locations, see below; [] for an unknown district
def country_prison(db, country_id) -> Optional[JailTarget]     # P3 validity + P4 cell; None when unusable
def resolve_jail(db, region_id, level_code, *, settings=None, levels=None) -> Optional[JailTarget]
```
- **`prison_location_ids` SQL** (valid on MySQL 8 and SQLite — the tests run on SQLite):
  ```sql
  WITH RECURSIVE dtree(id, depth) AS (
      SELECT id, 0 FROM Districts WHERE id = :d
      UNION ALL
      SELECT c.id, t.depth + 1 FROM Districts c JOIN dtree t ON c.parent_district_id = t.id WHERE t.depth < 10
  ), ltree(id, depth, sort_order) AS (
      SELECT l.id, t.depth, l.sort_order FROM Locations l JOIN dtree t ON l.district_id = t.id
      UNION ALL
      SELECT l.id, t.depth, l.sort_order FROM Locations l JOIN ltree t ON l.parent_id = t.id   -- parent_id chain (district_id may be NULL)
  )
  SELECT DISTINCT id, depth, sort_order FROM ltree ORDER BY depth, sort_order, id
  ```
  The depth guard (10) protects against a cyclic `parent_district_id`; the developer adds an equivalent guard on the location branch (e.g. a depth column capped at 10) and uses `UNION` (not `UNION ALL`) where needed to stop cycles. `NULL` `sort_order` sorts like 0.
- **`country_prison(db, country_id)`:**
  1. `SELECT prison_district_id FROM Countries WHERE id=:c`. An unknown-column error mentioning `prison_district_id` → `logger.warning("Countries.prison_district_id is missing (locations migration 057 not applied?) — no country prison")` and return None; any other error re-raises (pattern of FEAT-201 `stealth_agility_of`, run inside `db.begin_nested()`).
  2. NULL → None.
  3. `SELECT d.name, d.region_id, d.entrance_location_id, r.country_id FROM Districts d JOIN Regions r ON r.id = d.region_id WHERE d.id=:d`; no row or `r.country_id != country_id` → None (log INFO once per resolve: "prison district X no longer belongs to country Y").
  4. `ids = prison_location_ids(...)`; empty → None.
  5. Cell = entrance if `entrance in ids` else `ids[0]`. Name = `facility_title(country, country_name, None)`.
- **`resolve_jail(db, region_id, level_code)`:** `region_infos(db,[region_id])` gives the region name + `country_id`/name (existing `reputation_crud.region_infos`). `station = station_location(db, region_id)`; `country = country_prison(db, country_id)` (only computed when it can matter, i.e. always — both are needed for the fallback). `facility = lc.pick_facility(level_code, settings.country_prison_min_level, levels, station is not None, country is not None)`. Build the `JailTarget`.
- **Call sites switched** (grep must show no remaining `region_jail_location` outside `law_facility.py`):
  - `law_crud.evaluate_entry` (:530) → `has_jail = resolve_jail(db, region_id, level.code) is not None` (after the outlaw raise; snapshot unchanged in meaning);
  - `law_crud.encounter_options` (:580) and `encounter_out` (:593) → `resolve_jail(db, enc.region_id, enc.level_code)`;
  - `law_flows.send_to_jail` (:78), the battle "lost" branch (:363), `auto_resolve` (:384) → the same.
  - `law_flows.choose` keeps using `encounter_options` (no direct change).

### 3.4 character-service: write and read paths

**`law_flows.send_to_jail`:**
- `target = law_facility.resolve_jail(db, enc.region_id, enc.level_code)`; None → `LawError(409, MSG_NO_JAIL)` (text becomes «Здесь некуда заключить под стражу: нет ни отделения стражи, ни тюрьмы страны»).
- `moving = from_location != target.location_id`; everything else (`_prepare_move`, `apply_admin_move(event_type="jail")`, one TX) unchanged. Cross-region moves already work.
- The journal description: «Заключён под стражу: «{from}» → «{to}» ({target.name})».
- `jail_writes(db, character, enc, target, *, key, action, now, settings)` (signature: `target` replaces `jail_location_id`):
  - `term.location_id = target.location_id`, `term.facility = target.facility`, `term.country_id = target.country_id`, `term.district_id = target.district_id`;
  - `term.bail_price = 0` for country, `lc.bail_price(...)` for station;
  - `character.jail_region_id = enc.region_id` (unchanged), `character.jail_district_id = target.district_id` (None for station — always overwritten).
- Notification: `law_notify.jailed_message(region_name, target.name, until, now)`:
  - station: «Стража края «{region}» заключила вас в отделение стражи — срок {remaining}»;
  - country: «Стража края «{region}» отправила вас в {target.name} — срок {remaining}. Залога нет, передвигаться можно только внутри тюрьмы».
  The scheduler path (auto-surrender) uses the same function.

**`_end_term`** and **`staff_release`** (:1114) → also `character.jail_district_id = None`. **`law_pass` served step** → `UPDATE characters SET jail_district_id = NULL, jail_region_id = NULL WHERE id=:c AND (jailed_until IS NULL OR jailed_until <= :now)` in the same item transaction (the guard keeps a fresh re-jail intact).

**Escape (`law_crud.escape`, `escape_chance`):**
- `escape_chance(db, character_id, settings, facility=FACILITY_STATION)`: the FEAT-201 value; for `country` → `lc.country_escape_chance(value, settings.country_escape_multiplier)`.
- `escape(...)` passes `term.facility`; cooldown hours = `country_escape_cooldown_hours` for country, `escape_cooldown_hours` otherwise. Success/failure/extension/crime (`term.region_id`, heavy floor) unchanged. `jail_out` uses the same facility-aware call.

**Bail:**
- `self_bail` and `bail_other`: after the term is locked, `term.facility == country` → `LawError(409, MSG_NO_BAIL_COUNTRY = "Из тюрьмы страны нельзя выйти под залог")`, before any ledger call.
- `prisoners()` adds `t.facility <> 'country'` to `where` (both COUNT and page).

**Read models (additive; Pydantic v1, `schemas.py`):**
- `LawEncounterOut` + `jail_facility: Optional[str]` (`station|country|null`), `jail_name: Optional[str]`. For `pending` the live resolve; for closed encounters both `null` (the snapshot `has_jail` keeps its meaning).
- `LawJailOut` + `facility: str`, `facility_name: str`, `country_id: Optional[int]`, `district_id: Optional[int]`, `district_name: Optional[str]`, `bail_available: bool`, `allowed_location_ids: List[int]`; `bail_price` becomes `Optional[int]` (null when `bail_available` is false).
  - `allowed_location_ids`: country → `prison_location_ids(db, term.district_id)` (the snapshot; [] if the district vanished); station → `[term.location_id]`.
  - `facility_name` for a country term = `facility_title(country, <country name of term.country_id>)`; station = region name of the **station's** region = `term.region_id` (a station is always the encounter region's own).
  - Staff variant (admin character law view) carries the same fields.
- `LawPrisonerOut`: unchanged (country prisoners are never listed).

**`main.update_location` (authority, :2378):**
```
lock = activity_lock.lock_for_character(character)
if lock.reason == law_encounter                          -> 409 (unchanged)
if lock.reason == jail:
    allowed = character.jail_district_id is not None
              and int(new_location_id) in law_facility.prison_location_ids(db, character.jail_district_id)
    if not allowed                                      -> 409 lock message (unchanged text)
    # allowed: fall through — house reset, set location; evaluate_entry already returns None for jailed characters
```
- The response shape is unchanged (`law_encounter` is always null for a prisoner move).
- Not changed: `POST /characters/admin/{id}/move` (staff may move a prisoner anywhere; the term continues — see Q2), home scroll / teleport (refused by the lock).

### 3.5 locations-service

**Country admin (`crud.py`, `schemas.py`, `main.py`):**
- `CountryUpdate.prison_district_id: Optional[int] = None`; `CountryRead.prison_district_id: Optional[int] = None`; `get_country_details` and whatever payload `EditCountryForm` loads from also return `prison_district_id` (additive). `CountryCreate` is not changed (assign the prison after the regions exist).
- `update_country`: `changes = data.dict(exclude_unset=True)`; if `changes.get("prison_district_id") is not None` → `validate_country_prison_district(session, country_id, district_id)`:
  - district missing → 400 «Район тюрьмы не найден»;
  - `Districts.region_id → Regions.country_id != country_id` → 400 «Район тюрьмы должен находиться в одном из краёв этой страны»;
  - subtree has no location → 400 «В районе тюрьмы нет ни одной локации».
  An explicit `null` clears the prison.
- `prison_location_ids(session, district_id) -> List[int]` (async) in `crud.py`: **the same SQL as §3.3** (keep the text identical; the reviewer compares).
- **New endpoint** `GET /locations/countries/{country_id}/districts` — `require_permission("locations:update")` (it exists only for the country edit form). 404 «Страна не найдена». 200:
  ```json
  [{"id": 41, "name": "Казематы", "region_id": 7, "region_name": "Северный край",
    "parent_district_id": null, "location_count": 4, "entrance_location_id": 512}]
  ```
  Every district of every region of the country (nested included), ordered by region name, then parent-first, then `sort_order, id`. `location_count` = the subtree count (`prison_location_ids` length; fine for an admin read) so the form can mark empty districts.

**Post / move checks (`main.py`):**
- `check_not_locked_for_post(db, cid, location_id, *, allow_prison_move: bool) -> str` returns one of:
  - `POST_FREE = "free"` — no lock (normal flow);
  - `POST_IN_PLACE = "in_place"` — jailed, `location_id == current_location_id` (today's `True`: post without moving);
  - `POST_PRISON_MOVE = "prison_move"` — jailed, `allow_prison_move`, `jail_district_id` set, `location_id != current` and in `crud.prison_location_ids(jail_district_id)`.
  - Anything else → 409 with the lock message (unchanged).
  - Reads `current_location_id, jail_district_id` in one `SELECT`; the unknown-column error mentioning `jail_district_id` → WARNING + retry `SELECT current_location_id` (district = None). The helper lives in `main.py` (or `crud.py`), **outside** the shared part of `activity_lock.py`.
- `create_new_post` (`/posts/`, :940): `allow_prison_move=False` (posting elsewhere still requires being there — unchanged behaviour).
- `move_and_post` (:1329): `allow_prison_move=True`; `if outcome != POST_IN_PLACE: _update_character_location(...)` (replaces `if not jail_post`). Neighbour check, stamina, travel cooldown, `set_travel_cooldown` unchanged.
- `quick_move` (:1611): replace `check_not_activity_locked` with `check_not_locked_for_move(db, cid, dest)` → allowed for no lock, or jail + destination in the prisoner's subtree and ≠ current; otherwise 409 lock message. All other quick-move checks (`no_quick_move`, neighbour, cooldown, double stamina) unchanged; `update_location(source="quick_move")` re-validates.
- `activity_lock.py` is **not** edited.

### 3.6 API contracts (summary)

| Endpoint | Change |
|---|---|
| `PUT /locations/countries/{id}/update` (`locations:update`) | body + `prison_district_id: int|null`; 400 per §3.5; response + `prison_district_id` |
| `GET /locations/countries/{id}/details` (+ the form's source) | + `prison_district_id` |
| **`GET /locations/countries/{id}/districts`** (`locations:update`) | new, §3.5 |
| `POST /locations/{dest}/move_and_post`, `POST …/quick_move` | a prisoner may move inside the prison subtree; responses unchanged |
| `PUT /characters/internal/{id}/update_location` | a jailed character may move only inside `jail_district_id`'s subtree; contract unchanged |
| `GET /characters/{id}/law`, `GET …/law/jail`, escape/bail responses (`LawJailOut`) | + `facility`, `facility_name`, `country_id`, `district_id`, `district_name`, `bail_available`, `allowed_location_ids`; `bail_price` nullable |
| `GET …/law/encounter`, choice responses (`LawEncounterOut`) | + `jail_facility`, `jail_name` |
| `POST …/law/jail/bail`, `POST /characters/law/bail` | 409 «Из тюрьмы страны нельзя выйти под залог» for a country term |
| `GET /characters/law/prisoners` | country prisoners excluded |
| `GET/PUT /characters/admin/law/settings` | + `country_prison_min_level`, `country_escape_multiplier`, `country_escape_cooldown_hours` (validated, §3.2) |
| `GET /characters/admin/law/characters/{id}` | jail block carries the facility fields |

All additive except `bail_price` becoming nullable (frontend shipped together).

### 3.7 Frontend (`.tsx`, Tailwind + design system, 360 px+, no `React.FC`, every API error shown in Russian)

**Player**
- `api/law.ts`: `LawJailOut` (+ facility fields, `bail_price: number | null`, `allowed_location_ids: number[]`), `LawEncounterOut` (+ `jail_facility`, `jail_name`).
- `LocationPage/JailBanner.tsx`: title = `jail.facility_name` (+ «· район «{district_name}»» for country); bail button/confirm only when `bail_available`, otherwise a muted line «Из тюрьмы страны нельзя выйти под залог»; escape unchanged (it shows the server chance and cooldown). For country add «Можно перемещаться между локациями тюрьмы».
- `LocationPage/LocationPage.tsx`: when the lock reason is `jail`, fetch `fetchLawJail` (reuse the JailBanner's data if it is lifted; avoid a second request per render) → `allowedIds`.
  - `jailPostingAllowed` = jail && (`isCharacterHere` || `allowedIds.includes(location.id)`);
  - neighbours whose id ∈ `allowedIds` are not dimmed and keep the move/«написать пост»/quick-move UI; others stay locked;
  - the lock card text: station unchanged; country «Вы в тюрьме страны: можно ходить и писать посты только в её локациях».
  - Server 409s on a move are shown (existing error display).
- `LocationPage/GuardEncounterModal.tsx`: surrender confirm and the option hint use `jail_name` («Вас отправят в {jail_name} на N ч»; country → «Залога нет, побег сложнее»; station → today's bail sentence). `null` → today's generic text.
- `ProfilePage/ReputationTab/ReputationTab.tsx`: «{facility_name} · осталось …» and «· залог N» only when `bail_available`.
- `LocationPage/BankModal/BankBailTab.tsx`: the backend hides country prisoners; make sure a 409 from paying is shown (likely already); type update for `bail_price` if it shares the type.

**Admin**
- `AdminLocationsPage/EditForms/EditCountryForm/EditCountryForm.tsx`: field «Тюрьма страны (район)» — a `<select>` from `GET /locations/countries/{id}/districts` (option label «{region_name} → {name}», sub-districts indented, «(нет локаций)» disabled), plus «нет». Hint: «Сюда попадают тяжёлые преступники (порог — в настройках закона). Заключённые могут ходить между локациями района — проверьте, что локации соединены. Камера по умолчанию — входная локация района, иначе первая». Saved with the form (`prison_district_id`, `null` to clear); show the 400 text. Hidden for a new (unsaved) country. If the touched block carries SCSS, migrate the component per CLAUDE.md §10.8.
- `EditRegionForm.tsx` (:276-283): label «ТЮРЬМА КРАЯ» → «ОТДЕЛЕНИЕ СТРАЖИ»; hint «Сюда попадают мелкие нарушители (ниже порога тюрьмы страны). Если отделения нет — их везут в тюрьму страны».
- `api/lawAdmin.ts` + `Admin/ReputationPage/LawSettingsTab.tsx` («Тюрьма» group): «Тюрьма страны — с уровня» (select of the 5 levels, like `outlaw_min_level`), «Множитель шанса побега из тюрьмы страны» (0–1, step 0.05), «Перезарядка побега из тюрьмы страны, ч» (1–168). Rename the existing station fields' labels where they say «тюрьма» → «отделение» only if ambiguous.
- `Admin/CharactersPage/tabs/LawPanel.tsx`: the jail block shows `facility_name` (+ district) and «залог невозможен» for country.
- The locations admin API/types used by EditCountryForm: `prison_district_id` + a `fetchCountryDistricts(countryId)` call.

### 3.8 Security
- New endpoint: JWT + `locations:update`; path id typed `int`; read-only; no rate limit needed (admin only).
- Country update: the district must exist, belong to that country and have locations — server-side; the client select is only a convenience.
- Movement: the server decides from the **snapshot** under the character row lock (`update_location`); the locations-service check is a pre-filter. A forged request to move outside the subtree → 409.
- Bail on a country term → 409 before the ledger (no money moves). Prisoner list cannot leak country prisoners.
- Escape chance stays server-side; chance and roll are logged as today.
- Only parameterised `text()`; the recursive CTE has a depth guard. Skew fallbacks catch only the specific unknown-column errors and log a WARNING.

### 3.9 Data flow
```
Sentencing: choice surrender / lost guard fight / timeout
  character-service: resolve_jail(enc.region_id, enc.level_code)
     ├─ SQL Regions.jail_location_id                       (station)
     └─ SQL Countries.prison_district_id → Districts/Regions check → subtree CTE → cell   (country)
     → pick_facility(level ≥ threshold ? country : station; fallback; none → no surrender)
  → _prepare_move (locations HTTP) → TX: apply_admin_move(cell) + jail_writes(term.facility/country/district,
       characters.jailed_until/jail_district_id, wanted 0) → COMMIT → pika «… тюрьму страны «X» …»
Prison move: Player → POST /locations/{dest}/move_and_post (or quick_move)
  locations: lock = jail → SELECT current_location_id, jail_district_id → dest ∈ subtree? → prison_move
     → post / neighbour / stamina / cooldown → PUT /characters/internal/{id}/update_location
  character-service: row lock → jail + dest ∈ subtree(snapshot) → set location → COMMIT (else 409)
Escape: POST …/law/jail/escape → chance = clamp(station formula) × 0.5 (country), cooldown 12 h → success: crime in term.region_id
Bail:   POST …/law/jail/bail | /characters/law/bail → country term → 409
Admin:  EditCountryForm → GET /locations/countries/{id}/districts → PUT /countries/{id}/update {prison_district_id} → validation
```

### 3.10 Rollout
- One deploy together with FEAT-201: locations `057` and character `042` auto-run at container start. Skew is non-fatal (P11).
- Live from deploy but inert until an admin assigns a country prison: without one, every term is a station term (as today, except the heavy levels now fall back to the station explicitly — same result).
- Existing serving terms: `station`, no district → unchanged.
- **Post-deploy (PM):** assign prison districts on prod (content; neighbour edges between their locations), update the Технобук article «Репутация, закон и тень» (id 16).

### 3.11 Open business questions (defaults applied — do not block)
- **Q1 — Escape multiplier after the clamp:** the country max is 25 % (50 × 0.5) and the min 1 % (2 × 0.5). Alternative: multiply before the clamp (the floor 2 % would then apply).
- **Q2 — Staff admin move of a prisoner** (`POST /characters/admin/{id}/move`) stays unrestricted; the term continues wherever staff put the character (as with the station today). Alternative: refuse or auto-release.
- **Q3 — Already serving at deploy / prison reassigned mid-term:** the snapshot rules (old prisoners stay station prisoners; a reassigned prison does not move anyone).
- **Q4 — Escapee still inside the prison district:** they walk out through the edges like a visitor; if the prison is in the crime region, its guards may stop them again at once (heavy wanted). Accepted as gameplay. Alternative: on escape, teleport to the district entrance or out of the district.
- **Q5 — Prison district deleted mid-term** (its locations cascade-delete): the prisoner's location dangles and `allowed_location_ids` is empty; staff release fixes it (admin hint). No automatic handling.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**All developer tasks: NO commits, NO pushes, NO `git add` (the user commits once at the end).** Backend: `python -m py_compile` on every modified file + the service test suite inside its container. Frontend: `npx tsc --noEmit` and `npm run build` inside the frontend container. User-facing text in Russian. The FEAT-201 changes in the working tree are not to be reverted or reformatted.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **locations-service** per §3.1/§3.5: migration `057_country_prison_district` (guarded like 055); `Country.prison_district_id`; `CountryUpdate`/`CountryRead` + details payload; `validate_country_prison_district` in `update_country`; async `prison_location_ids` (SQL identical to §3.3); `GET /locations/countries/{id}/districts` (`locations:update`); tri-state `check_not_locked_for_post` (+ unknown-column fallback for `characters.jail_district_id`), `/posts/` with `allow_prison_move=False`, `move_and_post` calls `update_location` unless `in_place`, `quick_move` prison exception. `activity_lock.py` NOT edited. No commits/pushes/`git add`. | Backend Developer | DONE | `locations-service/app/alembic/versions/057_country_prison_district.py`, `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py` | — | Migration up/down/re-run clean on MySQL; a district of another country / an empty district / unknown → 400 with the Russian text; `null` clears; nested sub-district locations are counted; a jailed station prisoner can still post only in place; a country prisoner's move/quick move to a subtree location reaches `update_location`, outside → 409; without the `jail_district_id` column → WARNING + today's behaviour; existing `test_law_locations.py` (lock parity) green; py_compile + service tests pass. |
| 2 | **character-service** per §3.1–§3.4: migration `042_country_prison`; ORM; `law_core` (settings fields + validate, `is_heavy`, `pick_facility`, `country_escape_chance`, `facility_title`, constants); new `law_facility.py` (`JailTarget`, `station_location`, `prison_location_ids`, `country_prison` with the skew fallback, `resolve_jail`); switch all `region_jail_location` callers; `jail_writes(target)`; `send_to_jail` (target, journal text, notification); `law_notify.jailed_message` with the facility; escape chance/cooldown by facility; bail 409 for country terms (self + banker); `prisoners()` excludes country; `jail_out`/`encounter_out`/staff jail DTO fields + schemas; `_end_term`, `staff_release`, law pass clear `jail_district_id`; `main.update_location` subtree exception; `MSG_NO_JAIL` text. No commits/pushes/`git add`. | Backend Developer | DONE | `character-service/app/alembic/versions/042_country_prison.py`, `app/models.py`, `app/law_core.py`, `app/law_facility.py` (new), `app/law_crud.py`, `app/law_flows.py`, `app/law_notify.py`, `app/law_pass.py`, `app/main.py`, `app/schemas.py` | — | `grep region_jail_location` finds only `law_facility.py` (or an alias); a heavy level goes to the country cell (entrance if in the subtree, else the first location), a light one to the station, each falls back to the other, neither → no `surrender`; the term/character snapshot columns are written and cleared; a country prisoner moves inside the subtree and gets 409 outside; country bail 409 and no ledger row; escape chance = station × 0.5, cooldown 12 h; skew fallback logs a WARNING; existing law/shadow/stealth tests still pass (update `law_world.py` schema: `Countries.prison_district_id`, `Districts.parent_district_id/entrance_location_id/sort_order`, `Locations.parent_id/sort_order`, the new law columns); py_compile passes. |
| 3 | **Frontend player** per §3.7: `api/law.ts` types; `JailBanner` (facility title, district, no bail for country, movement hint); `LocationPage` (allowed ids from `GET …/law/jail`: neighbours/move/post/quick move inside the prison, card text); `GuardEncounterModal` texts from `jail_name`/`jail_facility`; `ReputationTab` jail line; `BankBailTab` type/409 check. No commits/pushes/`git add`. | Frontend Developer | DONE | `src/api/law.ts`, `components/pages/LocationPage/JailBanner.tsx`, `components/pages/LocationPage/LocationPage.tsx`, `components/pages/LocationPage/GuardEncounterModal.tsx`, `components/ProfilePage/ReputationTab/ReputationTab.tsx`, `components/pages/LocationPage/BankModal/BankBailTab.tsx` | contracts of 1, 2 (§3.6) | A country prisoner sees «Тюрьма страны «X»», no bail button, can move/post into prison neighbours and nowhere else; a station prisoner's UI is unchanged except the title «Отделение стражи края «Y»»; every error shown in Russian; 360 px OK; no `React.FC`; tsc + build pass. |
| 4 | **Frontend admin** per §3.7: `EditCountryForm` prison district select (country-scoped endpoint, empty districts disabled, hint, 400 shown); `EditRegionForm` «Отделение стражи» + hint; `LawSettingsTab` + `api/lawAdmin.ts` 3 new settings; `LawPanel` facility; locations admin API types. No commits/pushes/`git add`. | Frontend Developer | DONE | `AdminLocationsPage/EditForms/EditCountryForm/EditCountryForm.tsx`, `AdminLocationsPage/EditForms/EditRegionForm/EditRegionForm.tsx`, `Admin/ReputationPage/LawSettingsTab.tsx`, `src/api/lawAdmin.ts`, `Admin/CharactersPage/tabs/LawPanel.tsx`, the locations admin API/types file used by EditCountryForm | contracts of 1, 2 (§3.6) | Assigning/clearing a country prison saves and reloads; a wrong district shows the server text; law settings save the 3 fields (no 422); tsc + build pass. |
| 5 | **QA character-service:** `law_core` (`is_heavy`, `pick_facility` full matrix incl. both fallbacks and none, `country_escape_chance`, `facility_title`, settings validation bounds); `law_facility` on the SQLite world (nested sub-districts + `parent_id` locations in the subtree, entrance in/out of the subtree, district re-parented to another country → None, empty district → None, prison NULL, unknown-column fallback logs a WARNING while other errors raise, cyclic parent guard); `evaluate_entry`/`encounter_options`/`encounter_out` with each facility; `send_to_jail` (moves to the cell, `_prepare_move` mocked, term facility/country/district, `characters.jail_district_id`, notification text); `update_location` (country prisoner inside → 200, outside → 409, station prisoner → 409 elsewhere, `law_encounter` still 409); bail self/banker 409 + no ledger row; `prisoners()` excludes country; escape chance × multiplier and 12 h cooldown, crime in `term.region_id`; `_end_term`/staff release/law pass clear the snapshot (and a re-jailed character keeps the new one); DTO fields (`bail_price` null, `allowed_location_ids`). | QA Test | DONE | `character-service/app/tests/test_law_facility.py` (new), `tests/law_world.py`, existing `test_law_*.py` as needed | 2 | The full character-service suite passes in the container. |
| 6 | **QA locations-service:** country update validation (other country, unknown, empty, nested child district OK, `null` clears; 401/403 without `locations:update`); `GET /countries/{id}/districts` (shape, nested, `location_count`, 404, 403); tri-state check (`free`/`in_place`/`prison_move`/409) incl. the missing-column fallback; `move_and_post` calls `update_location` for a prison move and skips it in place (HTTP mocked); `quick_move` allowed inside, 409 outside; `/posts/` unchanged for prisoners; `prison_location_ids` SQL text identical to character-service's (string compare test, like the lock parity test); lock parity test still green. | QA Test | DONE | `locations-service/app/tests/test_country_prison.py` (new) | 1 | All locations-service tests pass in the container. |
| 7 | **Docs:** `docs/services/character-service.md` (facilities, resolver, new settings/columns, DTO fields, bail/escape rules), `docs/services/locations-service.md` (`Countries.prison_district_id`, new endpoint, prison move exception), `docs/ARCHITECTURE.md` (columns, flow), `docs/ISSUES.md` (Q2/Q5 as LOW items if not accepted otherwise; nothing stale). No commits/pushes/`git add`. | Backend Developer | DONE | `docs/…` | 1, 2 | Docs match the implemented contracts. |
| 8 | **Final review:** code vs §3; cross-service contracts (locations ↔ character, both skew fallbacks); `activity_lock` copies untouched (diff = FEAT-201 only); the two `prison_location_ids` SQL texts identical; py_compile + character/locations suites; tsc + build. **Live verification on localhost** (Chrome allowed): create/choose a district with ≥ 2 connected locations (incl. a sub-district) in a region of country X and assign it as the country prison; give region A a station; Злодей-level wanted in A → surrender → in the country cell, banner «Тюрьма страны «X»», no bail; move + quick move between prison locations works, leaving → 409; post in another prison location works; escape shows the station chance × 0.5 and a 12 h cooldown; bank «Залог» does not list the prisoner, a direct bail call → 409; Нарушитель-level → the station (title «Отделение стражи края «A»», bail works); remove the station → light offender goes to the country prison; remove the country prison → heavy goes to the station; remove both → no surrender; a free character walks into the prison as a visitor; admin: a district from another country → 400; law settings save; zero console errors. | Reviewer | DONE | — | 1–7 | PASS only with automated results + live verification recorded in §5. |
| 9 | **Post-deploy (PM, after the user pushes):** update the Технобук article «Репутация, закон и тень» (id 16) on prod (country prison vs station, thresholds, no bail, escape, moving inside); remind the user to assign prison districts and connect their locations. | PM | TODO | prod DB content | deploy | The article describes both facilities correctly. |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-05
**Result:** PASS (deploy gate FEAT-201 + FEAT-202: READY)

#### Checks
- [x] Types match (Pydantic ↔ TS interfaces): `LawJailOut` (facility, facility_name, country/district ids + name, bail_available, allowed_location_ids, nullable bail_price), `LawEncounterOut` (jail_facility, jail_name), `CountryDistrictRead`, `prison_district_id`, the 3 new law settings — mirrored in `api/law.ts`, `api/lawAdmin.ts`, `api/countryPrison.ts`.
- [x] API contracts consistent (backend ↔ frontend ↔ tests). Cross-service: locations `move_and_post`/`quick_move` → character `update_location` (contract unchanged, 409 passthrough); both deploy-skew fallbacks catch only the specific unknown-column error and log a WARNING.
- [x] No stubs/TODO without tracking (Q2/Q5 are LOW items in ISSUES.md).
- [x] `python -m py_compile` — OK (every modified/new .py in the working tree).
- [x] `npx tsc --noEmit` — OK (frontend container; the host node_modules lacks `react-icons` — pre-existing, unrelated).
- [x] `npm run build` (`vite build`) — OK.
- [x] `pytest` — OK (see below).
- [x] Security: new `GET /locations/countries/{id}/districts` = JWT + `locations:update` (401 without a token, verified live); the country update is validated server-side; prisoner moves are decided by `update_location` under the row lock from the snapshot; bail on a country term → 409 before any ledger call; only parameterised `text()`, the recursive CTE is depth-guarded; Russian error texts without internals.
- [x] Frontend displays all errors (JailBanner / LocationPage / EditCountryForm toasts).
- [x] User-facing strings in Russian.

#### Correctness vs §1/§3 (code read)
- Facility choice: `law_core.pick_facility` (level ≥ `country_prison_min_level` → country, else station; preferred missing → the other; none → None) behind the single resolver `law_facility.resolve_jail`; `region_jail_location` is no longer referenced outside `law_facility` (6 call sites switched, `choose` via `encounter_options`).
- Country prison validity: the district exists, its region's `country_id` equals this country (re-checked at every resolve), the subtree is non-empty; cell = the entrance if in the subtree, else the first location by (depth, sort_order, id).
- Snapshot: term `facility/country_id/district_id` + `characters.jail_district_id`; cleared in `_end_term`, staff release and the law pass (guarded, so a fresh re-jail survives).
- `update_location`: `law_encounter` → 409; `jail` → allowed only into the snapshot subtree.
- locations: tri-state `check_not_locked_for_post` (`free` / `in_place` / `prison_move`); `/posts/` with `allow_prison_move=False`; `move_and_post` calls `update_location` unless `in_place`; `quick_move` uses `check_not_locked_for_move`.
- No bail (self + banker 409, `bail_price=0` stored, DTO null, hidden from `prisoners()`); escape = the clamped station chance × multiplier, cooldown `country_escape_cooldown_hours`; the crime on escape → `term.region_id` (crime region). Visitors are not restricted.
- `SQL_PRISON_LOCATIONS` is byte-identical in `character-service/app/law_facility.py` and `locations-service/app/crud.py` (programmatic compare).
- `activity_lock.py` ×4: no diff vs HEAD.
- Migrations: one head each — character `042_country_prison` (← `041_stealth`), locations `057_country_prison_district` (← `056_quest_fame`), attributes `009_add_stealth`, inventory `035_item_stealth_modifier`; all ids ≤ 32 chars. Live `downgrade -1` → `upgrade head` → `upgrade head` (re-run = no-op) is clean for 042 and 057 on the local MySQL.
- `scripts/check_econ_copies.sh` — all shared copies identical.

#### Fix applied by Reviewer
| # | File | Change |
|---|------|--------|
| 1 | `services/character-service/app/law_crud.py` (`escape`) | An escape chance ≤ 0 (country multiplier 0, or a station minimum of 0) now raises 409 `MSG_ESCAPE_IMPOSSIBLE = "Отсюда не сбежать"` before the roll: no attempt counted, no term extension, no cooldown, no log row. |
| 2 | `services/character-service/app/tests/test_law_facility.py` | `test_escape_multiplier_zero_never_succeeds` → `test_escape_multiplier_zero_refuses_the_attempt` (409 + text; `until` / `next_escape_at` / `escape_attempts` unchanged; no escape log rows). |

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (frontend container)
- [x] `npm run build` — PASS
- [x] `py_compile` — PASS
- [x] `pytest` — PASS: character 8607 passed / 1 skipped + the fixed test re-run (`test_law_facility.py` + `test_law_country_prison.py`: 299 passed); locations 2814 passed (`--asyncio-mode=auto`); battle 1859 passed (`--asyncio-mode=auto`); inventory 2448 passed; character-attributes 975 passed / 2 skipped / 1 xpassed; user 776 passed; dungeon econ + `test_feat175_entry` all passed (rc 0).
- [x] `scripts/check_econ_copies.sh` — PASS
- [x] `docker compose config` (dev, and dev + prod) — PASS
- [x] Live verification — PASS

#### Live Verification Results (http://localhost, admin, Chrome)
- Admin: `EditCountryForm` «Тюрьма страны (район)» lists the country's districts with the region, nested indent and location counts; assigned «Шепшир → ↳ Сияющий Маяк» (district 55, 5 connected locations) to Мидденгерд → saved. A direct PUT with another country's district → 400 «Район тюрьмы должен находиться в одном из краёв этой страны»; unknown → 400 «Район тюрьмы не найден»; `/countries/6/districts` without a token → 401. `EditRegionForm` «ОТДЕЛЕНИЕ СТРАЖИ» set to «Железная Тюрьма» (185) for Геттенхорн → saved.
- Heavy offender (Ашари, «Злодей» in Геттенхорн): quick move into the guarded station location → guard modal «Сдаться: Тюрьма страны «Мидденгерд» на 3 д — тюрьма страны, залога нет», correct confirm text → surrender → moved cross-region to the default cell 271 «Сияющая Аллея»; term `facility=country, country_id=6, district_id=55, region_id=11, bail_price=0`; `characters.jail_district_id=55`; notification and journal «… (Тюрьма страны «Мидденгерд»)».
- Banner «Тюрьма страны «Мидденгерд» · район «Сияющий Маяк»», «Залога нет — из тюрьмы страны нельзя выйти под залог», escape «шанс 2,5 %» (station 5 % × 0.5). Profile Reputation tab: «Тюрьма страны … — «Сияющая Аллея» · залога нет».
- Movement: neighbours inside the prison enabled, «Чёрная Улица» (outside) disabled; UI quick move 271→272 OK; move_and_post 272→271 200; post in place 200; quick move / move_and_post / post to 253 (outside) → 409 «Персонаж в тюрьме — …»; a prison neighbour page shows the move UI, an outside page shows «Вы в тюрьме страны: можно ходить и писать посты только в её локациях».
- Self bail → 409 «Из тюрьмы страны нельзя выйти под залог»; the bank prisoners list excludes the country prisoner. Escape (UI) failed → term extended, `next_escape_at` = +12 h.
- LawSettings tab: the 3 new fields shown; multiplier set to 0 and saved; escape → 409 «Отсюда не сбежать» (the reviewer fix, live).
- Light offender (Годрик, «Нарушитель»): encounter `jail_facility=station`, «Отделение стражи края «Геттенхорн»» → surrender → station 185, `bail_available=true`, bail 300, escape 5 %, listed in prisoners, quick move out → 409, self bail reaches the ledger (400 «Недостаточно марок для залога»).
- Fallbacks: station removed → the light offender's encounter resolves to the country prison; country prison also removed → options without `surrender`, surrender → 409 «Здесь некуда заключить под стражу…».
- Visitor (Аэлис, free) quick-moved into the prison cell — allowed.
- The admin character law view returns the facility fields. FEAT-201: the «Скрытность» line is present in the profile characteristics.
- Console errors: NONE on the location / profile pages; service logs: no tracebacks.
- Local data restored from the pre-review mysqldump afterwards.

#### Notes (non-blocking)
- 360 px layout not re-measured by the reviewer (developers verified; the changes are texts/flags inside already responsive components).
- Q1–Q5 defaults (§3.11) accepted as designed.
- Pre-existing (most likely) bug noted in `docs/ISSUES.md` (LOW): locations-service left 3 idle connections with an OPEN InnoDB transaction after quick moves during live testing (they blocked `DROP DATABASE` on restore until killed; on prod they would block a migration `ALTER`). Not introduced by FEAT-202 as far as the code shows (quick_move only swapped the lock check; session from `get_db`); not blocking.

#### Deploy readiness (FEAT-201 + FEAT-202 on top of 331e4b9)
READY. Migrations auto-run at container start: character 041 → 042, attributes 009, inventory 035, locations 057; one head each; deploy skew is non-fatal both ways. Post-deploy: PM task 9 (article id 16; assign prison districts on prod and connect their locations).

---

## 6. Logging (filled by all agents — in Russian)

Running log of progress updates. Each agent writes brief Russian entries here.

```
[LOG] 2026-11-04 — PM: фича создана, решения пользователя зафиксированы; выкатка вместе с FEAT-201; запускаю анализ
[LOG] 2026-11-05 — Codebase Analyst: анализ завершён (раздел 2). Решение «есть ли тюрьма» принимается в 7 местах через region_jail_location — их нужно перевести на общий выбор учреждения. Районы бывают вложенными (182 из 328), поэтому тюрьму страны надо считать вместе с подрайонами. Блокировку jail (4 копии) трогать не нужно: исключение для перемещения внутри района делается в update_location и в check_not_locked_for_post. Миграции: locations 057 (Countries.prison_district_id) и character 042 (настройки, учреждение в сроке, characters.jail_district_id). 4 открытых вопроса.
[LOG] 2026-11-05 — PM: пользователь принял предложения по 4 вопросам аналитика; запускаю архитектора
[LOG] 2026-11-05 00:08 — Architect: начал проектирование
[LOG] 2026-11-05 00:40 — Architect: спроектировано 9 задач (2 бэкенд, 2 фронтенд, 2 QA, документация, ревью, статья после деплоя), 1 новый эндпоинт (список районов страны) и доп. поля в 5 существующих контрактах. Выбор учреждения — один модуль law_facility в character-service вместо 7 вызовов; блокировку jail (4 копии) не трогаем; перемещение внутри района проверяют update_location (решает окончательно) и locations-service (три исхода). Миграции: locations 057, character 042. 5 открытых вопросов с ответами по умолчанию — работу не блокируют.
[LOG] 2026-11-05 — Backend Developer (задача 1): locations-service готов. Миграция 057_country_prison_district (Countries.prison_district_id BIGINT, индекс, FK на Districts SET NULL) — up/down/up на fogdatabase чисто. Валидация района тюрьмы в update_country (3 русских 400, null очищает), новый GET /locations/countries/{id}/districts (locations:update), prison_district_id в details/list. check_not_locked_for_post — три исхода (free/in_place/prison_move), move_and_post вызывает update_location для перемещения внутри тюрьмы, quick_move — исключение для района тюрьмы. Нет колонки characters.jail_district_id → WARNING и прежнее поведение (проверено на живой БД). SQL поддерева (crud.SQL_PRISON_LOCATIONS) байт в байт совпадает с character-service law_facility.SQL_PRISON_LOCATIONS. activity_lock.py не тронут; в test_law_locations.py поправлены только ассерты/мок под три исхода.
[LOG] 2026-11-05 — Backend Developer (задача 2): character-service готов. Миграция 042_country_prison (3 настройки закона, facility/country_id/district_id в law_jail_terms, characters.jail_district_id) — up/down/up и повторный прогон на локальной MySQL чисто. Новый модуль law_facility (resolve_jail, country_prison с проверкой страны и поддеревом районов, SQL поддерева совпадает с locations-service; нет колонки Countries.prison_district_id → WARNING). Все 6 вызовов region_jail_location переведены на resolve_jail. Тюрьма страны: залог 409, скрыта из списка у банкира, побег ×0.5 и перезарядка 12 ч; перемещение заключённого только внутри района (update_location); снимок района очищается при выходе. Новые поля в ответах (facility, facility_name, allowed_location_ids, bail_available, jail_facility/jail_name). Обновлены ожидания 4 старых тестов (текст «некуда заключить», уведомление, колонки миграции), добавлены дымовые тесты test_law_country_prison.py. Полный набор: 8317 passed, 1 skipped.
[LOG] 2026-11-05 — Frontend Developer (задача 3): игрок готов. api/law.ts — новые поля LawJailOut (facility, facility_name, район, bail_available, allowed_location_ids, bail_price может быть null) и LawEncounterOut (jail_facility, jail_name). JailBanner: заголовок «Тюрьма страны «X»» · район / «Отделение стражи края «Y»», для тюрьмы страны вместо кнопки залога — «Залога нет», подсказка про перемещение по тюрьме и камеру; побег как раньше. LocationPage: для узника тюрьмы страны грузится GET …/law/jail, соседние локации вне тюрьмы приглушены и некликабельны (NeighborsSection.enabledIds), перемещение постом/быстрое и форма поста доступны в локациях тюрьмы, текст карточки блокировки по типу учреждения; узник отделения — как раньше. GuardEncounterModal: текст сдачи и подсказка с jail_name, для тюрьмы страны «залога нет, побег сложнее». ReputationTab: название учреждения, «залога нет» для тюрьмы страны. BankBailTab: 409 уже показывается тостом, поправлен комментарий. tsc --noEmit и npm run build в контейнере frontend — чисто.
[LOG] 2026-11-05 — Backend Developer (задача 7): документация обновлена по коду. character-service.md — новый раздел «Тюрьма страны и отделение стражи (FEAT-202)» (миграция 042, law_facility/resolve_jail, pick_facility, правила: без залога, побег ×0.5 после зажима и перерыв 12 ч, снимок jail_district_id, перемещение в update_location, новые поля DTO и настроек, тексты уведомлений) + правки старых мест раздела «Law». locations-service.md — колонка Countries.prison_district_id (057), проверка района при обновлении страны, GET /countries/{id}/districts, три исхода check_not_locked_for_post, quick_move в тюрьме, копия SQL_PRISON_LOCATIONS. ARCHITECTURE.md — таблицы, поток, список общих копий. ISSUES.md — Q2 и Q5 как LOW.
[LOG] 2026-11-05 — Frontend Developer (задача 4): админка готова. EditCountryForm — поле «Тюрьма страны (район)»: список из GET /locations/countries/{id}/districts (край → район, подрайоны с отступом, число локаций, пустые районы недоступны), «нет» очищает (prison_district_id: null), 400 от сервера показывается тостом с текстом сервера (AdminLocationsPage); новый api/countryPrison.ts. EditRegionForm — «Отделение стражи» с подсказкой про мелких нарушителей. LawSettingsTab + api/lawAdmin.ts — порог тюрьмы страны (выбор из 5 ступеней), множитель побега (0–1), перерыв побега (1–168 ч), уточнены подсказки отделения. LawPanel — учреждение (+ район), «залога нет» для тюрьмы страны, «если сдастся» у встречи. tsc --noEmit и npm run build в контейнере проходят.
[LOG] 2026-11-05 — QA Test (задачи 5, 6): тесты написаны. character-service tests/test_law_facility.py (291 тест): полная матрица pick_facility (уровень × порог × отделение/тюрьма), resolve_jail (есть/нет/сломана), поддерево с вложенными районами и цепочками parent_id, циклы и ограничение глубины, район удалён / край ушёл в другую страну / пустой, камера по умолчанию, снимок в jail_writes, перемещение по снимку (переназначение тюрьмы не влияет), варианты и тексты стычки по учреждению, проигранный бой и авто-разрешение по учреждению, побег (клэмп × множитель, 0, своя перезарядка, преступление в крае преступления), залог 409 без движения денег, список заключённых, очистка снимка (проход закона не трогает свежий срок), миграция 042, настройки API. locations-service tests/test_country_prison.py (57): миграция 057, валидация страны 400/403/422, null очищает, GET районов страны (порядок, location_count, 401/403/404, цикл), три исхода проверки поста, move_and_post/quick_move/posts, откат при отсутствии колонки, совпадение SQL поддерева с character-service (проверено с подложенным файлом). Полные наборы: character 8608 passed, 1 skipped; locations 2810 passed, 4 skipped. Багов не найдено.
[LOG] 2026-11-05 00:50 — Reviewer: начал проверку FEAT-202 и общий допуск к выкатке FEAT-201+202
[LOG] 2026-11-05 01:00 — Reviewer: мелкая правка — при нулевом шансе побега (множитель 0) попытка отклоняется с 409 «Отсюда не сбежать» без продления срока; тест обновлён
[LOG] 2026-11-05 01:20 — Reviewer: все наборы тестов зелёные (character, locations, battle, inventory, attributes, user, dungeon), tsc и сборка чистые, SQL поддерева совпадает байт в байт, activity_lock не тронут, миграции откатываются и накатываются; живая проверка на localhost пройдена, локальная БД восстановлена из дампа
[LOG] 2026-11-05 01:24 — Reviewer: обнаружен баг (висящие открытые транзакции locations-service после быстрого перемещения), добавлен в ISSUES.md
[LOG] 2026-11-05 01:25 — Reviewer: проверка завершена, результат PASS; FEAT-201+202 готовы к выкатке
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- ...

### Что изменилось от первоначального плана
- ...

### Оставшиеся риски / follow-up задачи
- ...

**Статус: DONE (2026-11-05), ревью PASS.** Тюрьма страны — район (одна на страну, назначается в редакторе страны), туда «Злодей» и «Враг края»; отделения стражи краёв — одна локация для мелких; взаимные запасные варианты. В тюрьме страны: перемещение и посты внутри района, залога нет, побег ×0.5 и раз в 12 ч («Отсюда не сбежать», если шанс 0). Выкатывается вместе с FEAT-201.
Осталось: назначить районы тюрем странам и связать их локации переходами; обновить статью Технобука id 16. LOW в ISSUES: зависшие соединения locations-service после quick_move (не связано с фичей, проверить отдельно).

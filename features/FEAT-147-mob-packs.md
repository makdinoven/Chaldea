# FEAT-147: Стаи мобов (mob packs)

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-07-06 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-147-mob-packs.md` → `DONE-FEAT-147-mob-packs.md`

Связанные фичи: [[FEAT-059-mob-system]] (одиночные мобы — база), FEAT-143 (групповые бои,
команды в `_assemble_battle`), FEAT-144 §13 (концепт «стаи мобов»), FEAT-145 (боевой гейт).

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Полноценная сущность **«стая мобов»**: админ собирает именованную группу из **разных**
ранее созданных шаблонов мобов (с указанием количества каждого), размещает её на локацию
одним объектом. Игрок видит стаю **одной карточкой** и нападает на неё — в бой попадают
**все живые** мобы стаи (team 1) против игрока/отряда (team 0). Награды капают с каждого
убитого моба (существующий механизм суммируется сам).

### Бизнес-правила (зафиксировано с пользователем)
- Стая состоит из разных шаблонов мобов + количество каждого.
- Размещение — **только ручное** админом (случайный спавн стаи — отдельная будущая задача).
- Респавн — **одноразовая по умолчанию + опциональный** общий таймер на всю стаю
  (возрождается целиком, когда все мобы убиты).
- Лимит боя — как в обычных групповых боях (`BATTLE_MAX_TEAM_SIZE`). Если мобов в стае
  больше капа — сторона мобов **обрезается** до капа, в админке — предупреждение.
- Боевой гейт (FEAT-145): пост, назвавший стаю (через лид-моба), открывает бой со всей стаей.

### UX
1. Админ: раздел «Стаи мобов» → создать стаю (имя, состав из шаблонов×кол-во,
   опц. аватар/респавн) → разместить на локацию.
2. Игрок на локации видит карточку «Стая: <имя>» с составом и аватарками участников.
3. Боевой пост, назвавший стаю → кнопка «Атаковать» (соло / группой).
4. Бой: игрок(и) vs все живые мобы стаи. Победа/награды — по существующим правилам.

### Edge Cases
- Часть мобов стаи уже мертва (после недобитого боя) → в новый бой берём только живых.
- Все мобы стаи мертвы, respawn выключен → стая исчезает с локации.
- В стае мобов больше капа команды → обрезаем до капа (лид-моб входит всегда).
- Удаление стаи-шаблона → каскад на состав; активные экземпляры удаляются отдельной ручкой.

---

## 2. Analysis Report (Codebase Analyst — English)

### Existing architecture (reused, not modified at the core)
- `_assemble_battle(db, player_ids, teams, battle_type, location_id)` (battle-service
  `main.py:593`) is N-agnostic — feeding N mob ids on team 1 already works.
- Rewards are computed **per defeated mob character** in `_maybe_distribute_rewards`
  (battle-service `main.py`) — a heterogeneous pack sums naturally.
- Mob status on battle end already flows through
  `PUT /characters/internal/active-mob-status/{character_id}` (per character). We add
  **pack-level rollup** inside that handler so battle-service needs no pack awareness.
- Combat gate (FEAT-145): post names a target `character_id`; gate status returns
  `{combat: [character_id,...]}`. A pack is offered as a combat target via its **lead
  member character_id** — no new action_type, no FEAT-145 changes.

### Affected Services
| Service | Changes | Files |
|---------|---------|-------|
| character-service | pack models, migration, schemas, crud, endpoints, pack rollup, exclude packed mobs from single list | `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, `app/alembic/versions/018_add_mob_packs.py` |
| battle-service | `/pack-attack`, `/party/pack-attack` | `app/main.py`, `app/schemas.py` |
| frontend | admin pack pages, redux/api, location pack card, combat targets | `src/api/mobPacks.ts`, `src/redux/slices/mobPacksSlice.ts`, `src/components/Admin/MobPacksPage/*`, `src/components/Admin/AdminPage.tsx`, `src/components/App/App.tsx`, `src/components/LocationMobPacks.tsx`, `src/components/pages/LocationPage/LocationPage.tsx` |

RBAC: reuse existing `mobs:manage` permission (no new permission).

### DB Changes
- New: `mob_packs`, `mob_pack_members`, `active_mob_packs`.
- Alter: `active_mobs` + `pack_group_id INT NULL` (FK → `active_mob_packs.id`, SET NULL).
- Migration: character-service Alembic `018` (version table `alembic_version_character`).

---

## 3. Architecture Decision (Architect — English)

### Data model
```
mob_packs(id, name, description, avatar, respawn_enabled, respawn_seconds, created_at, updated_at)
mob_pack_members(id, pack_id FK, mob_template_id FK, quantity)
active_mob_packs(id, pack_id FK, location_id, status[alive|in_battle|dead], spawned_at, killed_at, respawn_at)
active_mobs.pack_group_id  -> active_mob_packs.id  (NULL = standalone mob)
```

### Placement (manual)
`place_pack_on_location(pack_id, location_id)`:
- create `active_mob_packs` row (status=alive)
- for each member × quantity: `spawn_mob_from_template(...)` then tag the created
  `active_mob.pack_group_id = active_pack.id`, `spawn_type='manual'`, individual
  `respawn_at=NULL` (pack-level respawn only).

### Player display
- `GET /characters/mob-packs/by_location?location_id=` → one entry per alive/in_battle
  pack: `active_pack_id`, `name`, `avatar`, `status`, `lead_character_id` (smallest
  living member id — the combat-gate handle), `members: [{name, tier, level, avatar, count-collapsed}]`.
- `get_mobs_at_location` modified to exclude `pack_group_id IS NOT NULL` so packed mobs
  never show as standalone.

### Battle
- `POST /battles/pack-attack {character_id, active_pack_id}` — solo vs whole pack.
- `POST /battles/party/pack-attack {leader_character_id, active_pack_id}` — party vs pack.
- battle-service reads pack roster via `GET /characters/internal/mob-pack/{active_pack_id}`
  → `{location_id, status, member_character_ids:[living]}`. team1 = living members
  (truncated to `BATTLE_MAX_TEAM_SIZE`, lead kept). Gate consumed on `lead_character_id`.

### Pack rollup (character-service `update_active_mob_status`)
After setting a member mob's status, if `pack_group_id` set: recompute pack status —
all members dead → pack dead (+killed_at, +respawn_at if enabled); any in_battle →
in_battle; else alive.

### Lazy pack respawn (`get_packs_at_location`)
Dead packs with `respawn_at<=now`: delete old member mobs+characters, respawn fresh
members, reset pack to alive. Mirrors single-mob lazy respawn.

---

## 4. Tasks

| # | Description | Agent | Status |
|---|-------------|-------|--------|
| 1 | character-service models + Alembic 018 | Backend | DONE |
| 2 | character-service schemas | Backend | DONE |
| 3 | character-service crud + endpoints (pack CRUD, place, active packs, by_location, rollup, internal roster) | Backend | DONE |
| 4 | battle-service pack-attack + party/pack-attack | Backend | DONE |
| 5 | frontend api (`api/mobPacks.ts`) | Frontend | DONE |
| 6 | frontend admin pack page + nav + routes | Frontend | DONE |
| 7 | frontend location pack card + combat targets | Frontend | DONE |
| 8 | QA pytest (character-service 18 + battle-service 6) | QA | DONE |
| 9 | Build verification (py_compile, migration, tsc, build, live) | Reviewer | DONE |

> Frontend uses direct API calls (`api/mobPacks.ts`), not a redux slice — the
> codebase mixes both styles (AdminPage, LocationMobs use direct calls). No redux
> slice was added; scope kept to one admin page + one location component.

---

## 5. Review Log

_(pending)_

---

## 6. Logging (Russian)

```
[LOG] 2026-07-06 — PM: заведён FEAT-147 по запросу пользователя (полноценные стаи из
      разных мобов). Решения: ручное размещение, одноразовая+опц.респавн, обрез до капа.
      Гейт — через лид-моба (без правок FEAT-145). Приступаю к backend.
[LOG] 2026-07-06 — Backend: character-service — 3 таблицы (mob_packs, mob_pack_members,
      active_mob_packs) + active_mobs.pack_group_id, миграция 018 (применена live).
      CRUD: создание/состав/размещение/ростер/rollup статуса/ленивый респавн. 7 эндпоинтов
      (+ internal ростер для battle-service). Пакованные мобы исключены из одиночного списка.
[LOG] 2026-07-06 — Backend: battle-service — /pack-attack и /party/pack-attack. team1 =
      живые члены стаи (обрез до BATTLE_MAX_TEAM_SIZE, лид всегда входит). Статусы стаи
      обновляются автоматически через существующий active-mob-status на смерть моба.
[LOG] 2026-07-06 — Frontend: api/mobPacks.ts, админ-страница «Стаи мобов» (шаблоны+активные,
      композитор состава, размещение по локации, предупреждение при >5 мобов), карточка стаи
      на локации (состав + соло/группой), лид-мобы стаи добавлены в combatTargets поста.
[LOG] 2026-07-06 — QA/Reviewer: py_compile (char+battle) OK; миграция 018 применена, таблицы
      и колонка проверены в БД; live-прогон полного цикла стаи (создание→размещение→ростер→
      rollup смерти→респавн→очистка) PASS. Тесты: character-service 18 новых (+114 старых mob),
      battle-service 6 новых — все зелёные. Frontend: 0 новых ошибок tsc (baseline 64), vite build OK.
[LOG] 2026-07-06 — QA/Reviewer: ИСПРАВЛЕНА предсуществующая проблема изоляции тестов
      battle-service. Причина: main.py:45 делает `from redis_state import get_redis_client`,
      имя привязывается при первом импорте main; test_pve_rewards.py настраивал
      get_redis_client → MagicMock (не-awaitable), и при совместном прогоне (pve раньше pvp
      по алфавиту) test_pvp_attack получал не-awaitable redis → падал `await rds.zadd(...)`
      (9 тестов). Фикс: autouse-фикстура в test_pvp_attack.py перепривязывает
      main.get_redis_client к AsyncMock перед каждым тестом (иммунитет к порядку импорта) +
      test_pve_rewards.py теперь возвращает AsyncMock. Весь набор battle-service: 358 passed.
```

---

## 7. Completion Summary (Russian)

Реализованы полноценные стаи мобов из **разных** шаблонов. Админ собирает стаю
(шаблон×количество), размещает на локацию одним объектом; игрок видит её одной
карточкой и нападает — в бой попадают все живые мобы стаи (team 1) против игрока/
отряда (team 0). Награды суммируются по каждому убитому мобу (существующий механизм).
Размещение ручное; респавн опциональный (вся стая целиком); при переборе сторона
мобов обрезается до лимита команды. Раздел админки — «Стаи мобов» (`/admin/mob-packs`).

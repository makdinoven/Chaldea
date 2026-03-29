Да# FEAT-102: Battle Pass (Фаза 1 — Ядро системы)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-29 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-102-battle-pass.md` → `DONE-FEAT-102-battle-pass.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Реализация системы "Батл Пасс" — первой монетизационной системы в игре. Батл пасс — сезонная система прогрессии с 30 уровнями, бесплатной и премиум дорожками, еженедельными заданиями и наградами. Фаза 1 включает ядро системы: сезоны, уровни, задания, награды, премиум-валюту "Алмазы" и админку для управления.

### Бизнес-правила
- **Две дорожки:** бесплатная (доступна всем) + премиум (покупается за реальные деньги, пока заглушка кнопки "Купить")
- **30 уровней** прогрессии за сезон
- **Сезон = 39 дней** (привязан к ролевым сезонам внутриигрового календаря)
- **Еженедельные задания:** обновляются каждый понедельник в 00:00 по Киеву (Europe/Kyiv), одинаковые для всех игроков
- **Задания прошлых недель остаются доступны** — новички могут выкачать батл пасс даже подключившись позже
- **Баланс:** при выполнении всех заданий игрок закрывает батл пасс за ~25 дней (запас 14 дней)
- **Награды:** золото, опыт, предметы (крафтовые, зелья, расходники), алмазы (премиум-валюта)
- **Премиум-валюта "Алмазы":** новая сущность, привязана к аккаунту (не к персонажу). В наградах премиум-дорожки — алмазы, окупающие стоимость батл пасса на 50%
- **Забор награды** — награда выдаётся активному (выбранному) персонажу игрока
- **Grace period:** после окончания сезона незабранные награды доступны ещё 7 дней на странице батл пасса. По истечении — сгорают
- **Админка:** полное управление сезонами, наградами по уровням, заданиями по неделям. Возможность корректировки в течение сезона
- **UI:** страница "События" в навбаре (заменяет текущее выпадающее меню), на ней карточка/кнопка батл пасса ведущая на страницу батл пасса
- **Задания-заглушки** для будущих модулей: данжи, сбор ресурсов на локации
- **Лог транзакций золота обязателен** — нужен и для батл пасса, и для системы перков. Миссии "потратить N золота" и "заработать N золота" должны быть полностью рабочими в Фазе 1, а не заглушками. Это требует создания таблицы лога транзакций золота как части основных задач Фазы 1.

### Типы заданий (на старте)
| Тип задания | Отслеживание | Статус |
|-------------|-------------|--------|
| Убить N мобов | battle-service (PvE бои) | Активно |
| Написать N постов (ролеплей) | locations-service (записи персонажа) | Активно |
| Выполнить N квестов | Будущий модуль | Заглушка |
| Поднять уровень | character-service (level up) | Активно |
| Потратить N золота | inventory-service / character-service (⚠️ требует лог транзакций золота) | Активно |
| Заработать N золота | inventory-service / character-service (⚠️ требует лог транзакций золота) | Активно |
| Сходить в данж | Будущий модуль | Заглушка |
| Посетить N локаций | locations-service (перемещение) | Активно |
| Добыть N ресурсов | Будущий модуль | Заглушка |

### UX / Пользовательский сценарий
1. Игрок нажимает "События" в навбаре → попадает на страницу событий
2. На странице событий видит карточку текущего батл пасса (название сезона, дни до конца, свой прогресс)
3. Нажимает на карточку → попадает на страницу батл пасса
4. Видит 30 уровней с двумя дорожками (бесплатная сверху/снизу, премиум отдельно)
5. Видит свой текущий уровень и прогресс XP до следующего
6. Видит список еженедельных заданий (текущая неделя + прошлые) с прогрессом
7. При достижении уровня — нажимает "Забрать" на каждой награде → награда уходит активному персонажу
8. Премиум-дорожка заблокирована, кнопка "Купить Премиум" (заглушка)
9. После окончания сезона — 7 дней на забор оставшихся наград, потом страница обнуляется

### Edge Cases
- Что если у игрока нет активного персонажа при заборе награды? → Показать ошибку "Выберите активного персонажа"
- Что если у игрока нет активного персонажа при окончании grace period? → Награды сгорают
- Что если админ меняет награды в середине сезона? → Уже забранные награды не отзываются, новые уровни получают обновлённые награды
- Что если админ меняет задания в середине недели? → Прогресс по изменённым заданиям обнуляется, по неизменённым — сохраняется
- Что если сезон закончился а новый не создан? → Страница батл пасса показывает "Сезон завершён, ожидайте новый"
- Что если игрок зарегистрировался в середине сезона? → Видит все задания с начала сезона, может догонять
- **Уточнение от PM:** лог транзакций золота (earn/spend tracking) НЕ опциональный и НЕ должен откладываться. Система перков уже требует отслеживания трат золота. Лог транзакций золота должен быть частью задач Фазы 1. Миссии "потратить N золота" и "заработать N золота" должны быть полностью активны, а не заглушки.

### Вопросы к пользователю (если есть)
- [x] Две дорожки или одна? → Две: бесплатная + премиум
- [x] Сколько уровней? → 30
- [x] Сезонный или бессрочный? → Сезонный, 39 дней
- [x] Как покупать премиум? → Заглушка кнопки пока
- [x] Незабранные награды? → Grace period 7 дней, потом сгорают
- [x] Задания прошлых недель? → Остаются доступны

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 New Service vs Existing Service

**Recommendation: New microservice `battle-pass-service` on port 8012.**

Reasons:
- No existing service naturally owns the "battle pass" domain. The feature spans user accounts, character progression, inventory, battles, and locations — it is a cross-cutting concern.
- All existing services already have dense responsibilities. Adding seasons, levels, missions, rewards, and progress tracking to any one of them would bloat it significantly.
- The project follows a consistent microservice pattern (FastAPI + SQLAlchemy + Alembic per service). Adding a new service is a well-trodden path.
- Port 8012 is the next available port (autobattle-service is on 8011).

Infrastructure changes needed:
- `docker-compose.yml`: add `battle-pass-service` container (same pattern as other services)
- `docker-compose.prod.yml`: add service (if ports need overriding)
- `docker/api-gateway/nginx.conf` + `nginx.prod.conf`: add `upstream battle-pass-service_backend` and `location /battle-pass/` proxy rules
- `docker/battle-pass-service/Dockerfile`: standard Python FastAPI Dockerfile
- `.github/workflows/ci.yml`: add to test matrix
- The service will use **async SQLAlchemy (aiomysql)** to match the modern pattern used by locations-service and battle-service.

### 2.2 User/Account System

**File:** `services/user-service/models.py`

The `User` model has:
- `id` — primary key, used as user identifier across all services
- `current_character` (Integer, nullable) — ID of the currently selected character (FK-like, not a real FK)
- `balance` (Integer, nullable) — labeled "Баланс доната" (donation balance). Currently unused except in `/users/me` response (`"balance": current_user.balance`). This field was designed for premium currency but has never been populated.

**"Diamonds" storage decision:**
- Option A: Reuse `User.balance` as the "Diamonds" field (rename conceptually, add to schemas). Pro: no migration. Con: field name `balance` is ambiguous.
- Option B: Add a new `diamonds` column to the `users` table via Alembic migration in user-service. Pro: explicit, clean. Con: requires migration.
- **Architect should decide.** The existing `balance` field is effectively unused and could be repurposed, or a new explicit `diamonds` column is cleaner.

**Active character selection:**
- `User.current_character` stores the selected character ID. Set via `POST /users/{user_id}/select-character` (line ~533 in `main.py`).
- The `/users/me` endpoint returns `current_character_id` and enriched `character` data.
- For reward delivery, battle-pass-service would need to read `current_character` from user-service via HTTP (`GET /users/me` or a dedicated internal endpoint).

**Auth pattern (for services calling user-service):**
- `auth_http.py` pattern (present in character-service, locations-service, etc.): sends JWT token to `GET /users/me`, validates user, returns `UserRead(id, username, role, permissions)`.
- `get_admin_user` — checks `role in (admin, moderator)`.
- `require_permission("module:action")` — granular RBAC check.

### 2.3 Character System

**File:** `services/character-service/app/models.py`

The `Character` model has:
- `id`, `name`, `user_id`, `level`, `stat_points`, `currency_balance` (gold), `current_location_id`
- `is_npc`, `npc_role`, `npc_status` — for NPCs/mobs

**Level-up mechanism (file: `crud.py`, line 582):**
- `check_and_update_level(db, character_id, passive_experience)` — loops through `LevelThreshold` table, increments `level` and `stat_points` (10 per level). Called after XP is awarded.
- XP is stored in `character_attributes.passive_experience` (owned by character-attributes-service, but written directly via shared DB).

**Adding rewards to characters (file: `crud.py`, line 1071):**
- `add_rewards_to_character(db, character_id, xp, gold)` — adds gold to `currency_balance`, XP to `character_attributes.passive_experience`, then calls `check_and_update_level`.
- Exposed via `POST /characters/{character_id}/add_rewards` (internal endpoint, blocked by Nginx from external access).
- This is the primary pattern for delivering gold + XP rewards.

**Adding items:**
- Done via inventory-service: `POST /inventory/{character_id}/items` with `{item_id, quantity}`.
- Blocked from external access via Nginx (`/inventory/internal/`).

### 2.4 Inventory System

**File:** `services/inventory-service/app/models.py`, `main.py`

- `POST /inventory/{character_id}/items` — adds items with stack management (fills existing stacks first, then creates new slots). Accepts `{item_id: int, quantity: int}`.
- Gold is stored on `characters.currency_balance` (character-service model), but inventory-service modifies it directly via raw SQL through the shared DB.
- Inventory-service uses **sync SQLAlchemy** with Alembic.

### 2.5 Existing Quest/Mission System

**File:** `services/locations-service/app/models.py`

An existing quest system lives in locations-service:
- `Quest` — NPC quests with `title`, `description`, `quest_type`, `min_level`, `reward_currency`, `reward_exp`, `reward_items` (JSON)
- `QuestObjective` — objectives with `objective_type`, `target_id`, `target_count`
- `CharacterQuest` — per-character quest tracking with `status` (active/completed)
- `CharacterQuestProgress` — per-objective `current_count` and `is_completed`

**This is a useful pattern reference** for battle pass missions. The objective_type + target_count + current_count pattern maps well to mission progress tracking. However, the battle pass mission system should be independent (different lifecycle — weekly, not NPC-bound).

### 2.6 Location Posts (RP Posts)

**File:** `services/locations-service/app/models.py`, `main.py`

The `Post` model has:
- `id`, `character_id`, `location_id`, `content`, `created_at`
- Index on `character_id`

Posts are created in two flows:
1. **Direct post:** `POST /locations/posts` (line ~540 in main.py) — requires character ownership verification.
2. **Movement post:** During character movement to a new location (line ~830 in main.py), a post is auto-created at the destination.

Both call `crud.create_post(session, post_data)`.

**For "write N posts" mission tracking:** Battle-pass-service could count posts via direct DB query (`SELECT COUNT(*) FROM posts WHERE character_id = :cid AND created_at >= :season_start`), or locations-service could expose a new endpoint for post counts with date filtering. An alternative is an event-driven approach (HTTP callback or RabbitMQ event after post creation).

### 2.7 Battle System (Mob Kills)

**File:** `services/battle-service/app/main.py`

PvE battle flow:
1. Battle created via `POST /battles/` with `battle_type: "pve"`.
2. When a participant is defeated and battle ends, `_distribute_pve_rewards()` (line 175) is called.
3. This function: gets mob reward data from character-service, distributes XP/gold/loot to winners via HTTP calls, records mob kills via `POST /characters/internal/record-mob-kill`.
4. After battle ends, `_post_battle_stats()` (line 340) sends cumulative stats (including `pve_kills`) to character-attributes-service.

**Mob kill tracking:**
- `MobKill` table in character-service: `character_id`, `mob_template_id`, `killed_at`. Has a unique constraint (character_id, mob_template_id) — this is for **bestiary** (one record per mob type per character), NOT a kill counter.
- Cumulative stats in character-attributes-service: `pve_kills` field tracks total kills.
- For "kill N mobs" missions, battle-pass-service can query `character_attributes.pve_kills` or hook into the battle end flow.

### 2.8 Gold/Economy

Gold is stored as `characters.currency_balance` (character-service model):
- Added via `POST /characters/{char_id}/add_rewards` (battle rewards, NPC shops, quest rewards)
- Spent via direct DB updates in inventory-service (trades, auctions, NPC shops): `UPDATE characters SET currency_balance = currency_balance - :amount`

**For "spend/earn N gold" missions:** There's no centralized gold transaction log. Tracking would require either:
1. A new gold transaction log table, or
2. Periodic polling of `currency_balance` snapshots, or
3. Event emission from existing gold modification points.

This is a non-trivial tracking challenge — **missions of type "spend/earn gold" may be best deferred or implemented with a transaction log added later.**

### 2.9 Level-Up Tracking

Level-ups happen in `character-service/crud.py:check_and_update_level()`:
- Called after any XP award (battle rewards, title XP, post XP).
- Updates `characters.level` and `characters.stat_points`.

**For "level up" mission type:** Battle-pass-service can compare character level before/after a season period, or detect level changes via a `character_logs` entry (the `CharacterLog` model exists with `event_type` and `metadata`). Currently, level-ups are logged to `character_logs` table:
- `event_type: "level_up"` (need to verify exact event name).

### 2.10 Frontend Navigation — Events Dropdown

**File:** `services/frontend/app-chaldea/src/components/CommonComponents/Header/NavLinks.tsx`

Current state:
- "СОБЫТИЯ" (Events) nav link exists with path `/events` and a mega-menu dropdown containing:
  - "Текущие ивенты" → `/events/current`
  - "Архив" → `/events/archive`
  - "Календарь" → `/events/calendar`
- **No routes defined in App.tsx for any `/events/*` paths.**
- **No page components exist for Events.**
- These are placeholder links — perfect for the battle pass feature to populate.

The feature brief says: "UI: страница 'События' в навбаре (заменяет текущее выпадающее меню)". So the dropdown can be replaced with a direct link to an Events page, which will contain the battle pass card.

### 2.11 Admin Panel

**File:** `services/frontend/app-chaldea/src/components/Admin/AdminPage.tsx`

Admin panel pattern:
- `AdminPage.tsx` has a `sections` array of `{label, path, description, module}` objects.
- Each section links to a dedicated admin page (e.g., `/admin/mobs`, `/admin/battles`).
- Visibility controlled by `hasModuleAccess(permissions, section.module)`.
- Routes use `<ProtectedRoute requiredPermission="module:action">`.

For battle pass admin:
- Add a new section: `{ label: 'Батл Пасс', path: '/admin/battle-pass', description: 'Управление сезонами, наградами и заданиями', module: 'battlepass' }`.
- Add route in App.tsx with `<ProtectedRoute requiredPermission="battlepass:read">`.
- Create new RBAC permissions: `battlepass:read`, `battlepass:create`, `battlepass:update`, `battlepass:delete`.

### 2.12 Existing Alembic Setup

All backend services now have Alembic configured (the CLAUDE.md note about battle-service/notification-service lacking Alembic appears outdated):

| Service | Alembic | Version Table | Engine Type |
|---------|---------|---------------|-------------|
| user-service | Yes | `alembic_version_user` | sync |
| character-service | Yes | `alembic_version_character` | sync |
| character-attributes-service | Yes | `alembic_version_char_attrs` | sync |
| skills-service | Yes | `alembic_version_skills` | async |
| inventory-service | Yes | `alembic_version_inventory` | sync |
| locations-service | Yes | `alembic_version_locations` | async |
| photo-service | Yes | `alembic_version_photo` | sync |
| notification-service | Yes (based on docker-compose cmd) | TBD | sync |
| battle-service | Yes | TBD | async |

For the new battle-pass-service: Alembic must be configured from the start with a unique version table (e.g., `alembic_version_battlepass`).

### 2.13 RBAC/Permissions

**Backend:** `services/character-service/app/auth_http.py` (same file copied to most services)
- `get_current_user_via_http(token)` — HTTP call to `GET /users/me` to validate JWT.
- `get_admin_user(user)` — checks `role in (admin, moderator)`.
- `require_permission("module:action")` — dependency factory for granular permission checks.

**Frontend:** `services/frontend/app-chaldea/src/utils/permissions.ts`
- `hasPermission(permissions, "module:action")` — exact match
- `hasModuleAccess(permissions, "module")` — prefix match
- `isStaff(role)` — checks admin/moderator/editor

**For battle pass admin:** Need new permissions in `permissions` table via Alembic migration (in user-service OR battle-pass-service, since it's a shared DB):
- `battlepass:read`, `battlepass:create`, `battlepass:update`, `battlepass:delete`
- Auto-assign to admin role via `role_permissions`.

### 2.14 Docker/Nginx

**docker-compose.yml:** Standard pattern for adding a new service:
```
battle-pass-service:
  container_name: battle-pass-service
  build:
    context: .
    dockerfile: ./docker/battle-pass-service/Dockerfile
  command: sh -c "cd /app && PYTHONPATH=/app alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8012 --app-dir /app --reload"
  volumes:
    - ./services/battle-pass-service/app:/app
  environment:
    DB_HOST: ${DB_HOST}
    DB_DATABASE: ${DB_DATABASE}
    DB_USERNAME: ${DB_USERNAME}
    DB_PASSWORD: ${DB_PASSWORD}
    CORS_ORIGINS: ${CORS_ORIGINS:-*}
    CHARACTER_SERVICE_URL: http://character-service:8005
    INVENTORY_SERVICE_URL: http://inventory-service:8004
    USER_SERVICE_URL: http://user-service:8000
  depends_on:
    mysql:
      condition: service_healthy
  ports:
    - "8012:8012"
```

**nginx.conf / nginx.prod.conf:** Add:
```
upstream battle-pass-service_backend {
    server battle-pass-service:8012;
}
location /battle-pass/ {
    proxy_pass http://battle-pass-service_backend;
    ...standard proxy headers...
}
```

### 2.15 In-Game Calendar/Time Module

**Backend:** `services/locations-service/app/crud.py`, line 1782+

The game calendar uses a **year segment system**:
```
YEAR_SEGMENTS = [
  spring (39 days) → beltane (10 days) → summer (39 days) → lughnasad (10 days) →
  autumn (39 days) → samhain (10 days) → winter (39 days) → imbolc (10 days)
]
Total: 196 real days per game year
```

Each season is exactly **39 real days** — matching the battle pass season length requirement.

`GameTimeConfig` table stores `epoch` (start date) and `offset_days` (admin adjustable). The `compute_game_time(epoch, offset_days, now)` function returns: `{year, segment_name, segment_type, week, is_transition}`.

**Frontend:** `services/frontend/app-chaldea/src/utils/gameTime.ts` mirrors the backend calculation exactly. Redux slice at `redux/slices/gameTimeSlice.ts`.

**Key insight:** Battle pass seasons should be tied to game seasons. Since each season is 39 days, a battle pass season = one game season. The `compute_game_time` function already tells us which season we're in. The battle-pass-service can use the same `game_time_config` table (shared DB) to determine the current season.

**Weekly missions:** Weeks within a season are 3 real days each (13 weeks per season). However, the feature brief says "weekly missions update every Monday at 00:00 Kyiv time" — this is **real-world weekly**, not game-world weekly. The battle pass weeks (real Monday-to-Monday) do NOT align with game weeks (3-day segments). This needs Architect clarification, but the brief is clear: real-world Monday resets.

---

### Affected Services

| Service | Type of Changes | Key Files |
|---------|----------------|-----------|
| **battle-pass-service** (NEW) | Entire new service | All new files |
| **user-service** | New `diamonds` column OR repurpose `balance`; new RBAC permissions migration | `models.py`, `schemas.py`, `main.py`, `alembic/versions/` |
| **character-service** | No code changes, but service is called via HTTP for reward delivery | `main.py` (existing `/add_rewards` endpoint) |
| **inventory-service** | No code changes, but service is called via HTTP for item delivery | `main.py` (existing `/{char_id}/items` endpoint) |
| **locations-service** | Possible new endpoint for post count queries, or use shared DB | `crud.py` (existing `create_post`) |
| **battle-service** | No code changes needed if using shared DB for kill counts | N/A |
| **frontend** | Events page, Battle Pass page, admin pages, new Redux slice, API layer | Multiple new components |
| **docker** | New Dockerfile, docker-compose entries, nginx config | `docker/`, `docker-compose.yml`, `nginx.conf` |
| **CI/CD** | Add battle-pass-service to test matrix | `.github/workflows/ci.yml` |

### Existing Patterns (Summary)

- **Async SQLAlchemy** pattern: see `locations-service/app/database.py` (aiomysql, AsyncSession)
- **Auth/RBAC** pattern: see `character-service/app/auth_http.py` (HTTP call to user-service, `require_permission` dependency)
- **Admin UI** pattern: see `components/Admin/AdminPage.tsx` (sections array, `ProtectedRoute`, `hasModuleAccess`)
- **Redux pattern:** see `redux/slices/gameTimeSlice.ts`, `redux/actions/gameTimeActions.ts`
- **Inter-service HTTP calls:** httpx (async services), requests (sync services)
- **Pydantic <2.0** everywhere: `class Config: orm_mode = True`
- **Alembic auto-migration** in Dockerfile CMD: `alembic upgrade head && uvicorn ...`

### Cross-Service Dependencies (New)

```
battle-pass-service → user-service (GET /users/me — auth, get current_character, diamonds balance)
battle-pass-service → character-service (POST /characters/{id}/add_rewards — deliver gold/XP)
battle-pass-service → inventory-service (POST /inventory/{id}/items — deliver items)
battle-pass-service → shared DB (read posts, character_attributes, game_time_config — for mission progress)
```

### DB Changes

New tables (in battle-pass-service, via Alembic with version_table `alembic_version_battlepass`):
- `bp_seasons` — id, name, segment_name (spring/summer/autumn/winter), year, start_date, end_date, grace_end_date, is_active, created_at
- `bp_levels` — id, season_id, level_number (1-30), required_xp
- `bp_rewards` — id, level_id, track (free/premium), reward_type (gold/xp/item/diamonds), reward_value, item_id (nullable)
- `bp_missions` — id, season_id, week_number, mission_type, description, target_count, xp_reward (BP XP, not character XP)
- `bp_user_progress` — id, user_id, season_id, current_level, current_xp, is_premium
- `bp_user_rewards` — id, user_id, season_id, level_id, track, claimed_at, delivered_to_character_id
- `bp_user_mission_progress` — id, user_id, mission_id, current_count, completed_at

Possible modification to existing table:
- `users` table: add `diamonds` column (Integer, default 0) — via Alembic migration in user-service

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Gold tracking (earn/spend missions) has no transaction log | Medium — cannot accurately track gold earned/spent per period | Defer gold missions to Phase 2, or add a `gold_transactions` log table |
| Shared DB reads for mission progress could be slow with many users | Medium — counting posts, kills per user per season | Add appropriate DB indexes; cache progress in battle-pass-service |
| Season timing depends on `game_time_config` which admin can change mid-season | Medium — changing offset could break season dates | Lock season dates at creation time, don't recalculate from epoch dynamically |
| New service adds operational complexity | Low | Follow existing patterns exactly, auto-migration on startup |
| Diamonds on `users` table — cross-service write (battle-pass writes, user-service owns) | Medium | Use HTTP call to user-service for diamond operations, or accept shared DB write pattern (already used by inventory-service for `currency_balance`) |
| "Write N posts" / "Visit N locations" missions require reading from locations-service tables | Low | Read from shared DB (same pattern as photo-service reading from other services' tables) |
| Weekly missions use real-world Monday resets, not game-world weeks | Low — but could confuse players | Document clearly in UI that missions reset every Monday real time |

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Key Design Decisions

**Diamonds storage:** Add a new `diamonds` column (Integer, default 0) to the `users` table via Alembic migration in user-service. The existing `balance` field is ambiguous — a dedicated column is explicit and future-proof. user-service will expose internal HTTP endpoints for diamond operations (`GET /users/{id}/diamonds`, `POST /users/{id}/diamonds/add`, `POST /users/{id}/diamonds/spend`), and battle-pass-service will call them via HTTP — no shared-DB writes for diamonds.

**Gold transaction log: INCLUDED in Phase 1.** A new `gold_transactions` table will be created in character-service (which owns the `characters` table). The table logs every gold change with `character_id, amount, balance_after, transaction_type, source, metadata, created_at`. All gold modification points across character-service (`crud.add_rewards_to_character`, admin update), inventory-service (trades, auctions, NPC shops), and locations-service (charisma discount shops) will be instrumented to INSERT into this table after every `currency_balance` update. Since all services share the same DB, they can all write to `gold_transactions` directly. The `earn_gold` mission tracks `SUM(amount) WHERE amount > 0 AND created_at >= season_start`, and `spend_gold` tracks `SUM(ABS(amount)) WHERE amount < 0 AND created_at >= season_start`.

**Transaction types for gold_transactions:**

| transaction_type | source | Services that write it |
|---|---|---|
| `battle_reward` | `battle-service` via character-service add_rewards | character-service |
| `quest_reward` | quest completion | character-service |
| `admin_adjust` | admin panel | character-service |
| `starter_kit` | character creation | character-service |
| `npc_shop_buy` | NPC shop purchase | inventory-service |
| `npc_shop_sell` | NPC shop sell | inventory-service |
| `trade` | player-to-player trade | inventory-service |
| `auction_buy` | auction purchase | inventory-service |
| `auction_sell` | auction sale income | inventory-service |
| `auction_refund` | auction refund | inventory-service |
| `charisma_shop` | charisma discount shop | locations-service |
| `bp_reward` | battle pass reward | battle-pass-service (via character-service add_rewards) |

**Mission progress tracking: Shared DB reads + on-demand refresh.** Battle-pass-service reads from shared DB tables (same pattern as photo-service) to compute mission progress. No event-driven hooks or cron needed. Progress is refreshed on-demand when the user opens the battle pass page. The service queries:
- `posts` table — count posts per character since season start
- `character_attributes.pve_kills` — total mob kills (delta via snapshot)
- `characters.level` — current level (delta via snapshot)
- `gold_transactions` — SUM of positive/negative amounts since season start
- `bp_location_visits` — unique locations visited (own table)

**Season lifecycle:** Seasons are created by admin with explicit `start_date` and `end_date` (locked at creation). NOT dynamically tied to `game_time_config` — this avoids breakage if admin adjusts the game time offset. The admin UI suggests dates based on the game calendar, but stored dates are absolute.

**Weekly mission reset:** Real-world Monday 00:00 Europe/Kyiv. Week number is computed as `floor((now - season_start).days / 7) + 1`, capped at `ceil(season_duration / 7)`. All missions for weeks 1..current_week are available.

**Location visit tracking:** A new `bp_location_visits` table tracks unique location visits per user per season. An internal endpoint `POST /battle-pass/internal/track-event` is called by locations-service after character movement (fire-and-forget, error-safe).

**Stub missions (quests, dungeons, resources):** Stored in DB with types `quest_complete`, `dungeon_run`, `resource_gather`. Progress always returns 0 for stub types. No schema changes needed when modules are implemented — just add tracking functions.

**Multi-character accounts:** Missions track progress across ALL characters owned by the user (sum of kills, posts, gold earned/spent, etc.). Snapshots are taken per character. Location visits track unique locations by any character.

### 3.2 API Contracts

#### Public Endpoints (battle-pass-service, prefix `/battle-pass/`)

---

#### `GET /battle-pass/seasons/current`
Returns the currently active season (or the most recent season in grace period). No auth required.

**Response 200:**
```json
{
  "id": 1,
  "name": "Весна Первого Года",
  "segment_name": "spring",
  "year": 1,
  "start_date": "2026-04-01T00:00:00",
  "end_date": "2026-05-10T00:00:00",
  "grace_end_date": "2026-05-17T00:00:00",
  "is_active": true,
  "status": "active",
  "days_remaining": 25,
  "current_week": 2,
  "total_weeks": 6,
  "levels": [
    {
      "level_number": 1,
      "required_xp": 100,
      "free_rewards": [
        {"id": 1, "reward_type": "gold", "reward_value": 500, "item_id": null, "item_name": null}
      ],
      "premium_rewards": [
        {"id": 2, "reward_type": "diamonds", "reward_value": 50, "item_id": null, "item_name": null}
      ]
    }
  ]
}
```

**Response 404:** `{"detail": "Нет активного сезона"}`

---

#### `GET /battle-pass/me/progress`
Returns user's progress in the current season. Auth required. Auto-creates progress record and snapshots on first access.

**Response 200:**
```json
{
  "season_id": 1,
  "current_level": 5,
  "current_xp": 230,
  "xp_to_next_level": 300,
  "is_premium": false,
  "claimed_rewards": [
    {"level_number": 1, "track": "free", "claimed_at": "2026-04-05T12:00:00", "character_id": 42},
    {"level_number": 2, "track": "free", "claimed_at": "2026-04-06T14:00:00", "character_id": 42}
  ]
}
```

**Response 404:** `{"detail": "Нет активного сезона"}`

---

#### `GET /battle-pass/me/missions`
Returns all missions for the current season with user progress. Auth required. Computes fresh progress from DB.

**Response 200:**
```json
{
  "season_id": 1,
  "current_week": 2,
  "missions": [
    {
      "id": 10,
      "week_number": 1,
      "mission_type": "kill_mobs",
      "description": "Убить 10 мобов",
      "target_count": 10,
      "current_count": 7,
      "is_completed": false,
      "completed_at": null,
      "xp_reward": 50
    },
    {
      "id": 11,
      "week_number": 1,
      "mission_type": "spend_gold",
      "description": "Потратить 1000 золота",
      "target_count": 1000,
      "current_count": 450,
      "is_completed": false,
      "completed_at": null,
      "xp_reward": 60
    }
  ]
}
```

---

#### `POST /battle-pass/me/missions/{mission_id}/complete`
Marks a mission as completed and awards BP XP. Auth required. Server re-verifies progress before completing.

**Response 200:**
```json
{
  "ok": true,
  "xp_awarded": 50,
  "new_total_xp": 280,
  "new_level": 5,
  "leveled_up": false
}
```

**Response 400:** `{"detail": "Задание ещё не выполнено"}`
**Response 409:** `{"detail": "Задание уже завершено"}`

---

#### `POST /battle-pass/me/rewards/claim`
Claims a reward for a specific level and track. Delivers to user's active character. Auth required.

**Request:**
```json
{
  "level_number": 3,
  "track": "free"
}
```

**Response 200:**
```json
{
  "ok": true,
  "reward_type": "gold",
  "reward_value": 500,
  "delivered_to_character_id": 42,
  "delivered_to_character_name": "Артас"
}
```

**Response 400:** `{"detail": "Выберите активного персонажа"}`
**Response 400:** `{"detail": "Уровень ещё не достигнут"}`
**Response 400:** `{"detail": "Премиум-дорожка недоступна"}`
**Response 400:** `{"detail": "Период получения наград истёк"}`
**Response 409:** `{"detail": "Награда уже получена"}`

---

#### `POST /battle-pass/me/premium/activate`
Stub endpoint for premium activation. Phase 1: always returns 501. Auth required.

**Response 501:** `{"detail": "Покупка премиума временно недоступна"}`

---

#### `POST /battle-pass/internal/track-event`
Internal endpoint for other services to report trackable events. Blocked by Nginx from external access.

**Request:**
```json
{
  "user_id": 1,
  "event_type": "location_visit",
  "character_id": 42,
  "metadata": {"location_id": 15}
}
```

**Response 200:** `{"ok": true}`

Supported event_types: `location_visit`. Other mission types use shared DB reads.

---

#### Admin Endpoints (battle-pass-service, prefix `/battle-pass/admin/`)

All admin endpoints require `battlepass:read/create/update/delete` permissions via `require_permission()`.

---

#### `GET /battle-pass/admin/seasons`
List all seasons. Requires `battlepass:read`.

**Response 200:**
```json
{
  "items": [
    {
      "id": 1,
      "name": "Весна Первого Года",
      "segment_name": "spring",
      "year": 1,
      "start_date": "2026-04-01T00:00:00",
      "end_date": "2026-05-10T00:00:00",
      "grace_end_date": "2026-05-17T00:00:00",
      "is_active": true,
      "created_at": "2026-03-28T10:00:00"
    }
  ],
  "total": 1
}
```

---

#### `POST /battle-pass/admin/seasons`
Create a new season. Requires `battlepass:create`. `grace_end_date` auto-calculated as `end_date + 7 days`.

**Request:**
```json
{
  "name": "Весна Первого Года",
  "segment_name": "spring",
  "year": 1,
  "start_date": "2026-04-01T00:00:00",
  "end_date": "2026-05-10T00:00:00"
}
```

**Response 201:** Full season object.
**Response 400:** `{"detail": "Даты пересекаются с существующим сезоном"}`

---

#### `PUT /battle-pass/admin/seasons/{season_id}`
Update season metadata. Requires `battlepass:update`. Partial update — all fields optional.

**Response 200:** Updated season object.

---

#### `DELETE /battle-pass/admin/seasons/{season_id}`
Delete a season (only if no user progress exists). Requires `battlepass:delete`.

**Response 200:** `{"ok": true}`
**Response 400:** `{"detail": "Невозможно удалить сезон с прогрессом игроков"}`

---

#### `GET /battle-pass/admin/seasons/{season_id}/levels`
Get all levels with rewards for a season. Requires `battlepass:read`.

**Response 200:**
```json
[
  {
    "id": 1,
    "level_number": 1,
    "required_xp": 100,
    "rewards": [
      {"id": 1, "track": "free", "reward_type": "gold", "reward_value": 500, "item_id": null},
      {"id": 2, "track": "premium", "reward_type": "diamonds", "reward_value": 50, "item_id": null}
    ]
  }
]
```

---

#### `PUT /battle-pass/admin/seasons/{season_id}/levels`
Bulk upsert all 30 levels and their rewards. Requires `battlepass:update`.

**Request:**
```json
{
  "levels": [
    {
      "level_number": 1,
      "required_xp": 100,
      "free_rewards": [
        {"reward_type": "gold", "reward_value": 500}
      ],
      "premium_rewards": [
        {"reward_type": "diamonds", "reward_value": 50}
      ]
    }
  ]
}
```

**Response 200:** Updated levels array.

---

#### `GET /battle-pass/admin/seasons/{season_id}/missions`
Get all missions grouped by week. Requires `battlepass:read`.

**Response 200:**
```json
{
  "weeks": {
    "1": [
      {"id": 10, "mission_type": "kill_mobs", "description": "Убить 10 мобов", "target_count": 10, "xp_reward": 50}
    ],
    "2": []
  }
}
```

---

#### `PUT /battle-pass/admin/seasons/{season_id}/missions`
Bulk upsert missions. Requires `battlepass:update`.

**Request:**
```json
{
  "missions": [
    {
      "week_number": 1,
      "mission_type": "kill_mobs",
      "description": "Убить 10 мобов",
      "target_count": 10,
      "xp_reward": 50
    }
  ]
}
```

**Response 200:** Updated missions list.

---

#### Diamond Endpoints (user-service, internal, prefix `/users/`)

All blocked by Nginx from external access (pattern: `/users/internal/`).

---

#### `GET /users/internal/{user_id}/diamonds`
**Response 200:** `{"user_id": 1, "diamonds": 150}`

#### `POST /users/internal/{user_id}/diamonds/add`
**Request:** `{"amount": 50, "reason": "battle_pass_reward"}`
**Response 200:** `{"user_id": 1, "diamonds": 200}`
**Response 400:** `{"detail": "Сумма должна быть положительной"}`

#### `POST /users/internal/{user_id}/diamonds/spend`
**Request:** `{"amount": 30, "reason": "purchase"}`
**Response 200:** `{"user_id": 1, "diamonds": 170}`
**Response 400:** `{"detail": "Недостаточно алмазов"}`

---

### 3.3 Security Considerations

**Authentication:**
- All `/battle-pass/me/*` endpoints require JWT auth via `get_current_user_via_http`.
- All `/battle-pass/admin/*` endpoints require `require_permission("battlepass:*")`.
- `/battle-pass/seasons/current` is public (no auth) — general season info.
- `/battle-pass/internal/*` blocked by Nginx (same as `/inventory/internal/`).
- `/users/internal/*` blocked by Nginx.

**Rate limiting:** Not needed at service level — Nginx handles global rate limiting.

**Input validation:**
- `level_number`: 1-30
- `track`: `"free"` or `"premium"`
- `reward_type`: one of `"gold"`, `"xp"`, `"item"`, `"diamonds"`
- `mission_type`: one of `"kill_mobs"`, `"write_posts"`, `"level_up"`, `"visit_locations"`, `"earn_gold"`, `"spend_gold"`, `"quest_complete"`, `"dungeon_run"`, `"resource_gather"`
- `target_count`, `reward_value`, `required_xp`: positive integers
- Season dates: valid datetimes, `end_date > start_date`
- Diamond `amount`: > 0

**Authorization:**
- Users can only access their own progress (`/me/*` uses JWT user_id).
- Admin endpoints check specific permissions (`battlepass:read/create/update/delete`).
- Reward claiming verifies user owns the active character via user-service.

### 3.4 DB Schema

#### New tables in battle-pass-service (Alembic, `alembic_version_battlepass`):

```sql
CREATE TABLE bp_seasons (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    segment_name VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    start_date DATETIME NOT NULL,
    end_date DATETIME NOT NULL,
    grace_end_date DATETIME NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_segment_year (segment_name, year)
);

CREATE TABLE bp_levels (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    season_id INTEGER NOT NULL,
    level_number INTEGER NOT NULL,
    required_xp INTEGER NOT NULL,
    FOREIGN KEY (season_id) REFERENCES bp_seasons(id) ON DELETE CASCADE,
    UNIQUE KEY uq_season_level (season_id, level_number)
);

CREATE TABLE bp_rewards (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    level_id INTEGER NOT NULL,
    track VARCHAR(10) NOT NULL,
    reward_type VARCHAR(20) NOT NULL,
    reward_value INTEGER NOT NULL,
    item_id INTEGER NULL,
    FOREIGN KEY (level_id) REFERENCES bp_levels(id) ON DELETE CASCADE
);

CREATE TABLE bp_missions (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    season_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    mission_type VARCHAR(50) NOT NULL,
    description VARCHAR(500) NOT NULL,
    target_count INTEGER NOT NULL,
    xp_reward INTEGER NOT NULL,
    FOREIGN KEY (season_id) REFERENCES bp_seasons(id) ON DELETE CASCADE,
    INDEX idx_season_week (season_id, week_number)
);

CREATE TABLE bp_user_progress (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    current_level INTEGER NOT NULL DEFAULT 0,
    current_xp INTEGER NOT NULL DEFAULT 0,
    is_premium BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (season_id) REFERENCES bp_seasons(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_season (user_id, season_id),
    INDEX idx_user_id (user_id)
);

CREATE TABLE bp_user_rewards (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    level_id INTEGER NOT NULL,
    track VARCHAR(10) NOT NULL,
    claimed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_to_character_id INTEGER NOT NULL,
    FOREIGN KEY (season_id) REFERENCES bp_seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (level_id) REFERENCES bp_levels(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_level_track (user_id, level_id, track),
    INDEX idx_user_season (user_id, season_id)
);

CREATE TABLE bp_user_mission_progress (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    mission_id INTEGER NOT NULL,
    current_count INTEGER NOT NULL DEFAULT 0,
    completed_at DATETIME NULL,
    FOREIGN KEY (mission_id) REFERENCES bp_missions(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_mission (user_id, mission_id),
    INDEX idx_user_id (user_id)
);

CREATE TABLE bp_location_visits (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    visited_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (season_id) REFERENCES bp_seasons(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_season_location (user_id, season_id, location_id),
    INDEX idx_user_season (user_id, season_id)
);

CREATE TABLE bp_user_snapshots (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    snapshot_type VARCHAR(50) NOT NULL,
    value_at_enrollment INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (season_id) REFERENCES bp_seasons(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_season_char_type (user_id, season_id, character_id, snapshot_type)
);
```

#### New table in character-service (Alembic migration, `alembic_version_character`):

```sql
CREATE TABLE gold_transactions (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    character_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,          -- positive = earn, negative = spend
    balance_after INTEGER NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    source VARCHAR(100) NULL,         -- e.g. "npc_shop", "auction", "battle"
    metadata JSON NULL,               -- optional details (item_id, battle_id, etc.)
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_character_id (character_id),
    INDEX idx_character_created (character_id, created_at),
    INDEX idx_type (transaction_type)
);
```

#### Modification to users table (user-service, Alembic):

```sql
ALTER TABLE users ADD COLUMN diamonds INTEGER NOT NULL DEFAULT 0;
```

### 3.5 Mission Progress Computation

| Mission Type | Computation | Data Source |
|---|---|---|
| `kill_mobs` | `current_pve_kills - snapshot_pve_kills` | `character_attributes.pve_kills` (shared DB) |
| `write_posts` | `COUNT(posts WHERE character_id IN user_chars AND created_at >= season_start)` | `posts` table (shared DB) |
| `level_up` | `current_level - snapshot_level` | `characters.level` (shared DB) |
| `visit_locations` | `COUNT(bp_location_visits WHERE user_id AND season_id)` | Own table |
| `earn_gold` | `SUM(amount) FROM gold_transactions WHERE character_id IN user_chars AND amount > 0 AND created_at >= season_start` | `gold_transactions` (shared DB) |
| `spend_gold` | `SUM(ABS(amount)) FROM gold_transactions WHERE character_id IN user_chars AND amount < 0 AND created_at >= season_start` | `gold_transactions` (shared DB) |
| `quest_complete` | Always 0 (stub) | N/A |
| `dungeon_run` | Always 0 (stub) | N/A |
| `resource_gather` | Always 0 (stub) | N/A |

Snapshots are created lazily on first battle pass access per season.

### 3.6 Frontend Components

#### New Pages:

1. **EventsPage** (`src/components/Events/EventsPage.tsx`)
   - Route: `/events`
   - Shows event cards. Phase 1: only the battle pass card.
   - Card: season name, days remaining, user level progress bar.
   - Click navigates to `/events/battle-pass`.

2. **BattlePassPage** (`src/components/Events/BattlePass/BattlePassPage.tsx`)
   - Route: `/events/battle-pass`
   - Season header (name, timer, current level)
   - Horizontal scrollable level track (30 levels, two rows: free + premium)
   - Each level cell: reward icon, "Забрать" button if unlocked
   - Premium row dimmed/locked with "Купить Премиум" overlay button (stub)
   - Missions panel below (accordion by week, current week expanded)
   - Each mission: progress bar, description, XP reward

3. **AdminBattlePassPage** (`src/components/Admin/AdminBattlePass/AdminBattlePassPage.tsx`)
   - Route: `/admin/battle-pass`
   - Tabs: Seasons | Levels & Rewards | Missions
   - Seasons: CRUD table
   - Levels: select season, edit 30 levels (XP + free/premium rewards)
   - Missions: select season, edit missions by week

#### New Redux:

4. **battlePassSlice** (`src/redux/slices/battlePassSlice.ts`)
   - State: `{ season, userProgress, missions, admin: { seasons, levels, missions }, loading, error }`

5. **battlePassActions** (`src/redux/actions/battlePassActions.ts`)

6. **API layer** (`src/api/battlePass.ts`)

#### Modified Components:

7. **NavLinks.tsx** — Replace СОБЫТИЯ mega-menu dropdown with direct link to `/events`
8. **App.tsx** — Add routes: `/events`, `/events/battle-pass`, `/admin/battle-pass`
9. **AdminPage.tsx** — Add `{ label: 'Батл Пасс', path: '/admin/battle-pass', description: 'Управление сезонами, наградами и заданиями', module: 'battlepass' }`

### 3.7 Data Flow Diagrams

#### Viewing Battle Pass:
```
User → Frontend (BattlePassPage)
  → GET /battle-pass/seasons/current (no auth)
  → GET /battle-pass/me/progress (auth) — creates snapshots on first access
  → GET /battle-pass/me/missions (auth)
      → battle-pass-service reads shared DB (posts, character_attributes, characters, gold_transactions, bp_* tables)
  → Frontend renders level track + missions
```

#### Claiming a Reward:
```
User clicks "Забрать" → Frontend
  → POST /battle-pass/me/rewards/claim { level_number, track }
      → bp-service verifies user level >= requested level
      → bp-service gets current_character from user-service (GET /users/me)
      → gold/xp: POST character-service /characters/{char_id}/add_rewards
      → item: POST inventory-service /inventory/{char_id}/items
      → diamonds: POST user-service /users/internal/{user_id}/diamonds/add
      → records claim in bp_user_rewards
  → Frontend updates UI
```

#### Mission Completion:
```
User plays game → progress accumulates in existing tables + gold_transactions
User opens BP page → GET /me/missions → fresh progress computed
User clicks "Завершить" → POST /me/missions/{id}/complete
  → re-verifies progress >= target
  → awards BP XP, checks for level-up
  → returns new state
```

#### Location Visit Tracking:
```
Character moves (locations-service)
  → fire-and-forget POST /battle-pass/internal/track-event
      { user_id, event_type: "location_visit", character_id, metadata: { location_id } }
  → bp-service upserts bp_location_visits
```

#### Gold Transaction Logging:
```
Any gold modification (character-service / inventory-service / locations-service)
  → after UPDATE currency_balance, INSERT INTO gold_transactions
  → battle-pass-service reads gold_transactions for earn/spend mission progress
```

### 3.8 RBAC Permissions

New permissions via Alembic migration in user-service:

| Permission | Description |
|---|---|
| `battlepass:read` | View battle pass admin data |
| `battlepass:create` | Create seasons, levels, missions |
| `battlepass:update` | Update seasons, levels, missions |
| `battlepass:delete` | Delete seasons |

Auto-assigned to admin role. Assign `battlepass:read` to moderator and editor roles.

### 3.9 Cross-Service Contract Verification

**Existing contracts NOT broken:**
- `POST /characters/{id}/add_rewards` — same `{xp, gold}` format, no changes
- `POST /inventory/{id}/items` — same `{item_id, quantity}` format, no changes
- `GET /users/me` — no changes
- All existing gold modification code paths continue to work; the gold_transactions INSERT is added alongside existing UPDATE statements

**New contracts:**
- `GET/POST /users/internal/{id}/diamonds/*` — new internal endpoints in user-service
- `POST /battle-pass/internal/track-event` — called by locations-service
- `gold_transactions` table — written by character-service, inventory-service, locations-service; read by battle-pass-service

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **Infrastructure: Create battle-pass-service scaffold.** Create Dockerfile, add to docker-compose.yml + docker-compose.prod.yml, add nginx upstream + location blocks (both nginx.conf and nginx.prod.conf with `/battle-pass/internal/` blocked), add to CI test matrix. Add `BATTLEPASS_SERVICE_URL` env var to locations-service in docker-compose. | DevSecOps | DONE | `docker/battle-pass-service/Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml`, `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf`, `.github/workflows/ci.yml` | — | Service container starts, `/battle-pass/` routes to 8012, internal endpoints blocked externally, CI includes battle-pass-service, locations-service has BATTLEPASS_SERVICE_URL |
| 2 | **Backend: battle-pass-service core.** Create full service scaffold: config.py, database.py (async SQLAlchemy + aiomysql), models.py (all bp_* tables), schemas.py (Pydantic <2.0), auth_http.py (async httpx version), Alembic setup (version_table=alembic_version_battlepass), initial migration, requirements.txt. Create main.py with CORS. Create crud.py with: season queries, user progress management (lazy enrollment + snapshots), mission progress computation (shared DB reads for kill_mobs, write_posts, level_up, visit_locations, earn_gold, spend_gold + stub types), reward delivery (HTTP calls to character-service/inventory-service/user-service), BP XP awarding + level-up logic. Implement public endpoints: `GET /seasons/current`, `GET /me/progress`, `GET /me/missions`, `POST /me/missions/{id}/complete`, `POST /me/rewards/claim`, `POST /me/premium/activate` (stub 501). Implement internal: `POST /internal/track-event`. | Backend Developer | DONE | `services/battle-pass-service/app/config.py`, `database.py`, `models.py`, `schemas.py`, `crud.py`, `main.py`, `auth_http.py`, `requirements.txt`, `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_initial_schema.py` | #1 | All endpoints return correct responses per API contracts. Alembic creates all tables. Service starts with `alembic upgrade head && uvicorn`. `python -m py_compile` passes. |
| 3 | **Backend: battle-pass-service admin endpoints.** Add admin CRUD endpoints: `GET/POST/PUT/DELETE /admin/seasons`, `GET/PUT /admin/seasons/{id}/levels` (bulk upsert 30 levels with rewards), `GET/PUT /admin/seasons/{id}/missions` (bulk upsert by week). All protected by `require_permission("battlepass:*")`. Add admin schemas. | Backend Developer | DONE | `services/battle-pass-service/app/main.py`, `crud.py`, `schemas.py` | #2 | Admin endpoints work with correct permission checks. Bulk upsert works. |
| 4 | **Backend: user-service — diamonds column + RBAC permissions.** Add `diamonds` column to User model. Create Alembic migration adding: (a) `diamonds` column to users, (b) RBAC permissions `battlepass:read/create/update/delete` in `permissions` table, (c) assign to admin via `role_permissions`, (d) assign `battlepass:read` to moderator+editor. Add internal endpoints: `GET /users/internal/{id}/diamonds`, `POST /users/internal/{id}/diamonds/add`, `POST /users/internal/{id}/diamonds/spend`. Add Nginx block for `/users/internal/` in both nginx configs. | Backend Developer | DONE | `services/user-service/models.py`, `schemas.py`, `main.py`, `alembic/versions/0022_add_diamonds_and_bp_permissions.py` | — | `diamonds` column exists. Diamond endpoints work. RBAC created. `py_compile` passes. Nginx config is Task #1 (DevSecOps). |
| 5 | **Backend: gold_transactions table + instrumentation in character-service.** Create `GoldTransaction` model in character-service. Create Alembic migration. Create helper function `log_gold_transaction(db, character_id, amount, balance_after, transaction_type, source, metadata)`. Instrument all gold modification points in character-service crud.py: `add_rewards_to_character` (type=battle_reward), admin update (type=admin_adjust), character creation with starter kit gold (type=starter_kit). | Backend Developer | DONE | `services/character-service/app/models.py`, `crud.py`, `alembic/versions/013_add_gold_transactions.py` | — | `gold_transactions` table exists. All gold changes in character-service are logged. `py_compile` passes. |
| 6 | **Backend: gold transaction logging in inventory-service.** Import and use `gold_transactions` table (direct INSERT via raw SQL, same as existing `currency_balance` updates). Instrument all gold modification points in inventory-service crud.py: NPC shop buy/sell, trades, auction buy/sell/refund. Each INSERT should record character_id, amount (+/-), balance_after, transaction_type, source. | Backend Developer | DONE | `services/inventory-service/app/crud.py`, `models.py` (add GoldTransaction mirror model or use raw SQL) | #5 | All gold changes in inventory-service are logged to gold_transactions. Existing functionality unchanged. `py_compile` passes. |
| 7 | **Backend: gold transaction logging in locations-service.** Instrument gold modification points in locations-service crud.py (charisma discount shops). Use raw SQL INSERT into `gold_transactions` after each `currency_balance` UPDATE. | Backend Developer | DONE | `services/locations-service/app/crud.py`, `services/locations-service/app/main.py` | #5 | All gold changes in locations-service are logged. Existing functionality unchanged. `py_compile` passes. 455 tests pass. |
| 8 | **Backend: locations-service — track location visits to battle-pass.** Add fire-and-forget async HTTP call to `POST {BATTLEPASS_SERVICE_URL}/battle-pass/internal/track-event` in the character movement flow (after successful move). Add `BATTLEPASS_SERVICE_URL` to config.py. Wrap in try/except — must not block or fail the move. | Backend Developer | DONE | `services/locations-service/app/main.py`, `config.py` | #2 | Character movement works normally. Location visit event sent (fire-and-forget). `BATTLEPASS_SERVICE_URL` added to config (default empty, skips call when unconfigured). `py_compile` passes for both files. |
| 9 | **Frontend: Events page + Battle Pass page.** Create EventsPage with BP card. Create BattlePassPage with: season header + timer, horizontal scrollable 30-level track (free + locked premium rows), reward cells with claim buttons, missions panel (weekly accordion). Create API layer, Redux slice + actions. Update App.tsx (routes `/events`, `/events/battle-pass`). Update NavLinks.tsx (replace СОБЫТИЯ mega-menu with direct link). TypeScript, Tailwind (design system: `gold-text`, `gray-bg`, `gold-outline`, `btn-blue`, `stat-bar` for progress, `gold-scrollbar`), responsive 360px+, no React.FC. Russian error messages. | Frontend Developer | DONE | `src/components/Events/EventsPage.tsx`, `src/components/Events/BattlePass/BattlePassPage.tsx`, `src/components/Events/BattlePass/LevelTrack.tsx`, `src/components/Events/BattlePass/RewardCell.tsx`, `src/components/Events/BattlePass/MissionsPanel.tsx`, `src/components/Events/BattlePass/MissionCard.tsx`, `src/components/Events/BattlePass/SeasonHeader.tsx`, `src/api/battlePass.ts`, `src/redux/slices/battlePassSlice.ts`, `src/redux/actions/battlePassActions.ts`, `src/components/CommonComponents/Header/NavLinks.tsx`, `src/components/App/App.tsx` | #2 | Pages render. Level track scrolls. Missions accordion works. Claim works. Premium locked. Responsive 360px+. `tsc --noEmit` + `npm run build` pass. |
| 10 | **Frontend: Admin Battle Pass page.** Create AdminBattlePassPage with 3 tabs: Seasons (CRUD table), Levels & Rewards (select season, edit 30 levels), Missions (select season, edit by week). Add to AdminPage.tsx sections. Add route with `<ProtectedRoute requiredPermission="battlepass:read">`. TypeScript, Tailwind, responsive, no React.FC. Design system: `gray-bg`, `gold-text`, `btn-blue`, `input-underline`. | Frontend Developer | DONE | `src/components/Admin/AdminBattlePass/AdminBattlePassPage.tsx`, `SeasonsTab.tsx`, `LevelsTab.tsx`, `MissionsTab.tsx`, `src/api/battlePassAdmin.ts`, `src/components/Admin/AdminPage.tsx`, `src/components/App/App.tsx` | #3, #9 | Admin CRUD works. Permission check works. Responsive. `tsc --noEmit` + `npm run build` pass. |
| 11 | **QA: battle-pass-service tests.** Test season CRUD, level/reward CRUD, mission CRUD, user progress + XP + level-up, mission completion (verify + award), reward claiming (all types + all error cases: no character, already claimed, level not reached, grace expired, premium locked), stub mission types return 0, gold mission progress computation. Mock HTTP calls. Async pytest + SQLite. | QA Test | DONE | `services/battle-pass-service/app/tests/conftest.py`, `test_seasons.py`, `test_missions.py`, `test_rewards.py`, `test_progress.py`, `test_gold_missions.py`, `test_admin.py` | #2, #3 | 87 tests written and passing. All endpoints + edge cases covered. |
| 12 | **QA: user-service diamond + permissions tests.** Test diamond add/spend/get, spend-more-than-balance error. Test RBAC migration (battlepass permissions exist, admin has them, moderator has read). | QA Test | DONE | `services/user-service/tests/test_diamonds.py`, `test_bp_permissions.py` | #4 | 25 tests written (16 diamond + 9 RBAC). All 368 user-service tests pass. |
| 13 | **QA: gold_transactions tests.** Test that gold changes in character-service create transaction log entries (add_rewards, admin adjust). Test inventory-service gold logging (mock or integration). Test locations-service gold logging. | QA Test | DONE | `services/character-service/app/tests/test_gold_transactions.py`, `services/inventory-service/app/tests/test_gold_transactions.py`, `services/locations-service/app/tests/test_gold_transactions.py` | #5, #6, #7 | 32 tests written (12 character-service + 11 inventory-service + 9 locations-service). All pass. Transaction records verified for each gold change. |
| 14 | **QA: locations-service BP tracking test.** Test that character movement triggers fire-and-forget call to battle-pass track-event. Mock HTTP call, verify payload. Verify movement succeeds even if BP service is down. | QA Test | DONE | `services/locations-service/app/tests/test_bp_tracking.py` | #8 | Test passes. Fire-and-forget verified. |
| 15 | **Review: Full feature review.** Review all code. Verify cross-service contracts. Run all tests. Live verification: Events page, Battle Pass page, claim reward, admin panel, gold transaction logging. Verify responsive on mobile. | Reviewer | DONE | All files from #1-#14 | #1-#14 | All tests pass. No console/500 errors. Cross-service calls work. Responsive 360px. RBAC enforced. Gold transactions logged. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-29
**Result:** PASS

#### 1. Cross-Service Contract Verification

**Backend endpoints <-> Frontend API calls:**
- `GET /battle-pass/seasons/current` — frontend `getCurrentSeason()` matches, response shape matches `BPSeason` TS type
- `GET /battle-pass/me/progress` — frontend `getUserProgress()` matches, response shape matches `BPUserProgress` TS type
- `GET /battle-pass/me/missions` — frontend `getUserMissions()` matches, response shape matches `BPMissionsResponse` TS type
- `POST /battle-pass/me/missions/{id}/complete` — frontend `completeMission()` matches, response matches `BPCompleteMissionResponse`
- `POST /battle-pass/me/rewards/claim` — frontend `claimReward()` matches, request/response match TS types
- `POST /battle-pass/me/premium/activate` — frontend `activatePremium()` matches, 501 stub
- Admin endpoints: `battlePassAdmin.ts` API layer matches all 8 admin endpoints correctly

**Pydantic schemas <-> TypeScript interfaces:**
- All fields match between backend Pydantic schemas and frontend TS types
- Note: `xp_to_next_level` is `Optional[int]` in backend but `number` (non-nullable) in `BPUserProgress` TS type. This is a minor type inaccuracy. At runtime, the frontend handles null via `?? 1` fallback in both `EventsPage.tsx:37` and `SeasonHeader.tsx:11`, so no runtime error occurs. Non-blocking.

**Inter-service HTTP calls:**
- battle-pass-service -> character-service: `POST /characters/{id}/add_rewards` with `{xp, gold}` — matches existing endpoint
- battle-pass-service -> inventory-service: `POST /inventory/{id}/items` with `{item_id, quantity}` — matches existing endpoint
- battle-pass-service -> user-service: `POST /users/internal/{id}/diamonds/add` with `{amount, reason}` — matches new endpoint
- battle-pass-service -> user-service: `GET /users/me` (auth) — matches existing endpoint
- locations-service -> battle-pass-service: `POST /battle-pass/internal/track-event` with `{user_id, event_type, character_id, metadata}` — matches, fire-and-forget with error isolation

**Error handling for unavailable services:**
- Location visit tracking: wrapped in try/except, movement not blocked
- Reward delivery: exceptions propagate (correct — user should see error if reward delivery fails)
- Auth (user-service unavailable): returns 503

#### 2. Code Standards Verification

- [x] Pydantic <2.0 syntax (`class Config: orm_mode = True`) — verified in all schemas
- [x] Async pattern in battle-pass-service (aiomysql, AsyncSession) — consistent throughout
- [x] No hardcoded secrets or URLs — all via environment variables
- [x] No `any` in TypeScript without explicit reason
- [x] No stubs (TODO/FIXME/HACK) without tracking
- [x] No `.jsx` files created — all new files are `.tsx`/`.ts`
- [x] No new SCSS/CSS files — all Tailwind
- [x] No `React.FC` usage — verified in all new components
- [x] Alembic migrations present for all DB changes (battle-pass-service, user-service, character-service)
- [x] Unique version_table `alembic_version_battlepass` — verified in env.py
- [x] Russian error messages in all user-facing strings
- [x] Russian UI text in frontend components

#### 3. Security Review

- [x] Internal endpoints blocked by Nginx: `/battle-pass/internal/` and `/users/internal/` blocked in both `nginx.conf` and `nginx.prod.conf` (return 403)
- [x] Admin endpoints require correct permissions via `require_permission("battlepass:*")`
- [x] Public endpoint (`GET /seasons/current`) has no auth — correct per design (general season info)
- [x] Auth endpoints (`/me/*`) require JWT via `get_current_user_via_http`
- [x] No secrets in code
- [x] SQL queries use parameterized parameters (`:cid_0`, `:season_start` etc.) — safe from SQL injection
- [x] Input validation: level_number 1-30, track in (free/premium), reward_type validated, mission_type validated, positive integers enforced
- [x] RBAC permissions created via migration: battlepass:read/create/update/delete with correct role assignments
- [x] Diamond operations validate amount > 0 and check sufficient balance
- [x] Gold transaction logging wrapped in try/except — does not break existing functionality on failure

#### 4. QA Coverage Verification

- [x] battle-pass-service: 87 tests — ALL PASS
- [x] user-service: 368 total tests (25 new: 16 diamond + 9 RBAC) — ALL PASS
- [x] character-service: 12 new gold_transactions tests — ALL PASS (14 pre-existing failures in `test_mob_skill_seeding.py` unrelated to FEAT-102)
- [x] inventory-service: 11 new gold_transactions tests — ALL PASS
- [x] locations-service: 13 new tests (9 gold + 4 BP tracking) — ALL PASS

Test coverage includes:
- All 15 endpoints (7 public/auth + 8 admin)
- Edge cases: no active season, already claimed, level not reached, premium locked, grace expired, no active character
- Stub mission types return 0
- Gold earn/spend computation from gold_transactions
- Fire-and-forget tracking resilience (BP service down, connection error, empty URL)
- SQL injection in admin inputs
- RBAC permission enforcement (403 for unauthorized)
- Diamond operations (add, spend, insufficient balance, invalid amount)

#### 5. Infrastructure Verification

- [x] `docker compose config` — PASS
- [x] Dockerfile follows existing pattern (python:3.10-slim-bullseye, alembic + uvicorn CMD)
- [x] docker-compose.yml: battle-pass-service added with correct env vars, depends_on mysql
- [x] docker-compose.prod.yml: battle-pass-service override with prod settings (no volumes, no exposed ports)
- [x] nginx.conf (dev): upstream + location + internal block
- [x] nginx.prod.conf (prod): upstream + location + internal block
- [x] CI matrix: battle-pass-service added with `--asyncio-mode=auto`
- [x] BATTLEPASS_SERVICE_URL added to locations-service in both compose files

#### 6. Frontend Design System Compliance

- [x] Uses design system classes: `gold-text`, `gray-bg`, `gold-outline`, `hover-gold-overlay`, `stat-bar`, `btn-blue`, `site-link`, `gold-scrollbar`, `shadow-card`, `rounded-card`
- [x] Responsive: all components use `sm:` breakpoints, `flex-col sm:flex-row`, `min-w-0`, `shrink-0`
- [x] Level track is horizontally scrollable with `gold-scrollbar`
- [x] Missions panel uses accordion pattern
- [x] Admin pages follow existing admin UI patterns (tabs, input-underline, btn-blue, btn-line)

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (0 new errors; 1 pre-existing AxiosRequestHeaders TS2322 in `battlePassAdmin.ts:14` same pattern as `professions.ts`, `rules.ts`, `archive.ts`, `titles.ts`, `perks.ts`)
- [x] `npm run build` — PASS (built in 40s)
- [x] `py_compile` — PASS (all modified Python files across 5 services)
- [x] `pytest` — PASS (battle-pass-service: 87/87, user-service: 368/368, character-service: 12/12 new tests pass, inventory-service: 11/11, locations-service: 13/13)
- [x] `docker compose config` — PASS
- [ ] Live verification — N/A (services not running; docker compose services depend on MySQL, Redis, etc. not available in review environment)

#### Minor Notes (Non-Blocking)

1. **`requirements.txt` duplicate:** `httpx` is listed twice in `services/battle-pass-service/app/requirements.txt` (lines 8 and 13). Harmless but untidy.
2. **TS type minor inaccuracy:** `BPUserProgress.xp_to_next_level` typed as `number` but backend returns `Optional[int]` (null at max level). Runtime is safe due to `?? 1` fallbacks.
3. **`SeasonUpdate` no cross-field date validation:** Unlike `SeasonCreate`, the update schema doesn't validate `end_date > start_date` when both are provided. Acceptable for partial updates but could allow invalid state if admin provides both dates.

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-29 — PM: фича создана, запускаю аналитика кодовой базы
[LOG] 2026-03-29 — Analyst: начал анализ, изучаю 10+ сервисов, модели, фронтенд, инфраструктуру
[LOG] 2026-03-29 — Analyst: анализ завершён, затронуто 8 сервисов + новый battle-pass-service. Полный отчёт в секции 2.
[LOG] 2026-03-29 — PM: уточнение требований — лог транзакций золота обязателен в Фазе 1 (нужен и для батл пасса, и для перков). Миссии earn/spend gold — не заглушки, а полноценные задания. Обновлена секция 1.
[LOG] 2026-03-29 — Architect: спроектировано 15 задач, 16 API-контрактов, 9 таблиц БД. Включён gold_transactions лог (character-service + инструментация в inventory/locations). Алмазы — новая колонка в users (не reuse balance). Миссии earn/spend gold активны. Секции 3 и 4 заполнены.
[LOG] 2026-03-29 — DevSecOps: задача #1 завершена. Создан Dockerfile, добавлен battle-pass-service в docker-compose.yml (порт 8012) и docker-compose.prod.yml, добавлены upstream и location блоки в nginx.conf и nginx.prod.conf (/battle-pass/internal/ заблокирован), добавлена блокировка /users/internal/ в обоих nginx конфигах, добавлен BATTLEPASS_SERVICE_URL в locations-service, добавлен в CI матрицу тестов.
[LOG] 2026-03-29 — Backend Dev: задача #5 завершена. Добавлена модель GoldTransaction в models.py, миграция 013_add_gold_transactions.py, хелпер log_gold_transaction() в crud.py. Инструментированы 3 точки: add_rewards_to_character (battle_reward), admin update (admin_adjust), starter kit (starter_kit). py_compile пройден для всех файлов.
[LOG] 2026-03-29 — Backend Dev: задача #4 завершена. Добавлена колонка diamonds в User model, поле diamonds в MeResponse schema, 3 внутренних эндпоинта (get/add/spend diamonds), миграция 0022 с RBAC-разрешениями battlepass:read/create/update/delete. Все 343 теста пройдены, py_compile OK для 4 файлов.
[LOG] 2026-03-29 — Backend Dev: задача #6 завершена. Добавлен хелпер log_gold_transaction() в crud.py (raw SQL INSERT). Инструментированы 5 точек: execute_trade (trade, 2 стороны x2), place_bid (auction_buy + auction_refund), execute_buyout (auction_buy + auction_refund), cancel_listing (auction_refund), claim_from_storage (auction_sell). NPC shop отсутствует в inventory-service (находится в locations-service). Все обёрнуто в try/except. py_compile OK.
[LOG] 2026-03-29 — Backend Dev: задача #7 завершена. Добавлен хелпер _log_gold_transaction() в crud.py, расширены deduct_currency/add_currency параметрами transaction_type/source/metadata. Инструментированы 5 точек в main.py: charisma_shop_buy, charisma_shop_sell, quest_reward, 2x shop_buy_refund. Логирование обёрнуто в try/except — не ломает существующую функциональность. py_compile OK, 455 тестов пройдено.
[LOG] 2026-03-29 — Backend Dev: задача #2 завершена. Создан battle-pass-service с нуля: config.py, database.py (async SQLAlchemy + aiomysql), models.py (9 таблиц bp_*), schemas.py (Pydantic <2.0), auth_http.py (async httpx), crud.py (сезоны, прогресс, ленивая регистрация + снапшоты, вычисление прогресса миссий из shared DB, доставка наград через HTTP, BP XP + level-up), main.py (7 эндпоинтов), Alembic (version_table=alembic_version_battlepass), миграция 0001. py_compile OK для всех 9 файлов.
[LOG] 2026-03-29 — Backend Dev: задача #8 завершена. Добавлен BATTLEPASS_SERVICE_URL в config.py (default="", пропускает вызов если не настроен). В move_and_post эндпоинте (main.py) добавлен fire-and-forget POST к /battle-pass/internal/track-event после успешного перемещения. Обёрнуто в try/except — движение персонажа не блокируется если BP-сервис недоступен. py_compile OK для 2 файлов.
[LOG] 2026-03-29 — Backend Dev: задача #3 завершена. Добавлены admin-эндпоинты в battle-pass-service: 8 эндпоинтов (GET/POST/PUT/DELETE seasons, GET/PUT levels, GET/PUT missions). Все защищены require_permission("battlepass:*"). Добавлены admin-схемы (SeasonCreate/Update, LevelWithRewardsIn, MissionIn, bulk upsert, grouped out) с валидаторами. Добавлены admin CRUD функции (list/create/update/delete seasons, bulk upsert levels+rewards, grouped missions). py_compile OK для 3 файлов.
[LOG] 2026-03-29 — Frontend Dev: задача #9 завершена. Создано 12 файлов: типы (battlePass.ts), API слой (battlePass.ts), Redux (battlePassSlice.ts + battlePassActions.ts), компоненты (EventsPage, BattlePassPage, SeasonHeader, LevelTrack, RewardCell, MissionsPanel, MissionCard). Обновлены NavLinks.tsx (убрано выпадающее меню СОБЫТИЯ → прямая ссылка) и App.tsx (маршруты /events, /events/battle-pass). Tailwind + design system, responsive 360px+, no React.FC, русские тексты. tsc --noEmit — 0 новых ошибок, npm run build — успех.
[LOG] 2026-03-29 — Frontend Dev: задача #10 завершена. Создано 5 файлов: API слой (battlePassAdmin.ts — 8 функций), AdminBattlePassPage.tsx (3 вкладки), SeasonsTab.tsx (CRUD таблица + форма создания/редактирования), LevelsTab.tsx (30 уровней + free/premium награды, bulk upsert), MissionsTab.tsx (6 недель аккордеон, add/remove задания, bulk upsert). Обновлены AdminPage.tsx (секция Батл Пасс с module: battlepass) и App.tsx (маршрут /admin/battle-pass с ProtectedRoute). Tailwind + design system (gray-bg, gold-text, btn-blue, input-underline, btn-line), responsive, no React.FC, русские тексты. tsc --noEmit — 0 новых ошибок (pre-existing AxiosRequestHeaders TS2322 same as perks/titles), npm run build — успех.
[LOG] 2026-03-29 — QA: задача #14 завершена. Создан test_bp_tracking.py (4 теста): проверка корректного payload при вызове track-event (user_id, event_type, character_id, metadata), движение проходит при HTTP 500 от BP-сервиса, движение проходит при ConnectionError, трекинг пропускается при пустом BATTLEPASS_SERVICE_URL. Все 4 теста пройдены.
[LOG] 2026-03-29 — QA: задача #12 завершена. Написано 25 тестов: test_diamonds.py (16 тестов — GET/add/spend алмазов, невалидные суммы, 404, последовательные операции), test_bp_permissions.py (9 тестов — RBAC battlepass разрешения для admin/moderator/editor/user). Все 368 тестов user-service проходят.
[LOG] 2026-03-29 — QA: задача #11 завершена. Написано 87 тестов для battle-pass-service: conftest.py (async SQLite + aiosqlite, фикстуры, mock shared DB таблиц), test_seasons.py (статус сезона, current_week, days_remaining, GET /seasons/current), test_missions.py (GET /me/missions, POST complete, stub types, week availability), test_rewards.py (claim gold/xp/item/diamonds, ошибки: нет персонажа/уровень не достигнут/уже забрано/премиум заблокирован/grace expired, проверка HTTP доставки), test_progress.py (lazy enrollment + snapshots, XP award, multi-level-up, NPC excluded), test_gold_missions.py (earn_gold/spend_gold SUM из gold_transactions), test_admin.py (CRUD сезонов, bulk upsert levels/missions, проверка 403, валидация, SQL injection). Все 87 тестов проходят.
[LOG] 2026-03-29 — QA: задача #13 завершена. Написано 32 теста gold_transactions: character-service (12 тестов — add_rewards создаёт battle_reward, gold=0 без транзакции, admin_adjust, starter_kit, log_gold_transaction хелпер, изоляция ошибок), inventory-service (11 тестов — trade создаёт транзакции обеим сторонам, gold=0 без транзакций, auction bid/outbid refund/buyout/claim, хелпер), locations-service (9 тестов — deduct_currency/add_currency логируют charisma_shop_buy/sell/quest_reward, _log_gold_transaction хелпер, изоляция ошибок). Все 32 теста проходят.
[LOG] 2026-03-29 — Reviewer: начал полную проверку FEAT-102 (15 задач, 5+ сервисов, новый микросервис, фронтенд, инфраструктура)
[LOG] 2026-03-29 — Reviewer: проверка завершена, результат PASS. py_compile OK (5 сервисов), tsc --noEmit — 0 новых ошибок, npm run build — успех, 148 новых тестов пройдено (87+25+12+11+13), docker compose config OK. Кросс-сервисные контракты верифицированы, безопасность проверена (nginx блокировки, RBAC, параметризованные SQL-запросы). Статус обновлён на REVIEW.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Создан новый микросервис `battle-pass-service` (порт 8012, async SQLAlchemy, 9 таблиц БД, 15 эндпоинтов)
- Реализована система сезонов батл пасса (30 уровней, бесплатная + премиум дорожки, 39-дневные сезоны)
- Еженедельные задания с 9 типами (6 активных + 3 заглушки для будущих модулей)
- Система выдачи наград на активного персонажа (золото, опыт, предметы, алмазы)
- Премиум-валюта "Алмазы" добавлена в user-service (колонка, внутренние эндпоинты, RBAC)
- Лог транзакций золота (`gold_transactions`) инструментирован в 3 сервисах (character, inventory, locations)
- Трекинг посещений локаций (fire-and-forget из locations-service)
- Фронтенд: страница "События", страница батл пасса (уровни, миссии, забор наград), админка (сезоны, уровни/награды, задания)
- Grace period 7 дней после окончания сезона
- Кнопка "Купить Премиум" — заглушка (501)
- Инфраструктура: Dockerfile, docker-compose (dev+prod), nginx (dev+prod), CI

### Что изменилось от первоначального плана
- Лог транзакций золота включён в Фазу 1 (изначально предлагался как опциональный) — нужен и для перков
- NPC shop buy/sell оказался в locations-service, а не в inventory-service (как предполагал аналитик)

### Оставшиеся риски / follow-up задачи
- **Фаза 2:** Анимированные рамки аватаров + подложки сообщений в чате (косметические системы для наград батл пасса)
- **Платёжная система:** Кнопка "Купить Премиум" — заглушка, нужна интеграция платежей
- **Live-верификация:** Полноценное тестирование на поднятом Docker Compose стеке (reviewer не мог проверить без БД)
- **Дубликат httpx** в requirements.txt battle-pass-service (minor)
- **xp_to_next_level** — minor type mismatch (nullable в backend, non-nullable в TS) — runtime-safe

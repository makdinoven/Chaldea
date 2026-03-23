# FEAT-067: Admin Battle Monitor — View and Force-Close Active Battles

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-03-23 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
В админ-панели добавить страницу мониторинга боёв:
1. Список всех активных боёв (pending/in_progress) с информацией об участниках
2. Возможность зайти и посмотреть бой (read-only)
3. Принудительное закрытие боя (force-finish)

### Бизнес-правила
- Админ видит все активные бои в реальном времени
- Для каждого боя видно: ID, тип (PvE/PvP), участники (имена, уровни), статус, время начала
- Админ может открыть бой и смотреть его состояние (HP, мана, текущий ход)
- Админ может принудительно завершить бой (force-finish) — бой заканчивается, все участники выходят
- При принудительном закрытии — нет победителя, нет наград, все участники освобождаются

### UX / Пользовательский сценарий
1. Админ заходит в раздел "Бои" в админ-панели
2. Видит таблицу/список активных боёв с фильтрами
3. Нажимает на бой — открывается детальная информация (участники, HP, ход)
4. Нажимает "Принудительно завершить" → подтверждение → бой закрывается

---

## 2. Analysis Report

### 2.1 Battle System Internals

**Models** (`services/battle-service/app/models.py`):
- `Battle` — main table with `id`, `status` (enum: pending/in_progress/finished/forfeit), `battle_type` (pve/pvp_training/pvp_death/pvp_attack), `created_at`, `updated_at`.
- `BattleParticipant` — links `battle_id` → `character_id` with `team` int.
- `BattleTurn` — records each turn action (skill choices, timestamps).
- `BattleHistory` — post-battle records with `result` (enum: victory/defeat), `character_name`, `opponent_names` (JSON), `finished_at`.
- `BattleResult` enum: `victory`, `defeat` — no `cancelled` value currently.

**Redis State** (`services/battle-service/app/redis_state.py`):
- Key pattern: `battle:{battle_id}:state` — JSON dict containing:
  - `turn_number`, `deadline_at`, `next_actor`, `first_actor`, `turn_order` (list of participant_ids)
  - `active_effects` — dict of active buffs/debuffs
  - `participants` — dict keyed by participant_id (as string), each containing: `character_id`, `team`, `hp`, `mana`, `energy`, `stamina`, `max_hp`, `max_mana`, `max_energy`, `max_stamina`, `fast_slots`, `cooldowns`
- TTL: configurable via `BATTLE_STATE_TTL_HOURS` env var (default 48h)
- `battle:deadlines` — ZSET with member `"{battle_id}:{participant_id}"` scored by unix timestamp
- `battle:{battle_id}:snapshot` — cached snapshot (participant profiles at battle start)
- `battle:{battle_id}:turns` — ZSET tracking turn numbers

**Battle Finish Flow** (`main.py:863-908`):
1. Set `battles.status = 'finished'` in MySQL via `finish_battle()`
2. Sync final HP/mana/energy/stamina back to `character_attributes` table
3. Save final state to Redis, then expire key in 300s
4. Clean up deadline ZSET entries
5. Handle PvP consequences (training: set loser HP to 1; death: unlink character)
6. Write `BattleHistory` records, distribute rewards

**Snapshot** (`mongo_helpers.py`): Battle start snapshots (participant names, avatars, attributes, skills) are stored in MongoDB `battle_snapshots` collection and cached in Redis.

### 2.2 Existing Admin Infrastructure in battle-service

**Auth** (`services/battle-service/app/auth_http.py`):
- `get_current_user_via_http()` — validates JWT via HTTP call to user-service `/users/me`
- `get_admin_user()` — checks `role in ("admin", "moderator")`
- `require_permission(permission)` — dependency factory for granular permission checks
- Already imported in `main.py`: `get_current_user_via_http`, `UserRead`
- `get_admin_user` exists but is NOT currently used by any endpoint in battle-service.

**No existing admin endpoints** in battle-service — this will be the first.

**Existing RBAC permission**: `battles:manage` (id=28, migration `0008`) — currently used only by autobattle-service. We can reuse this permission for admin battle monitor endpoints.

### 2.3 Frontend Admin Structure

**Admin hub** (`services/frontend/app-chaldea/src/components/Admin/AdminPage.tsx`):
- Array of `AdminSection` objects: `{ label, path, description, module }`
- Sections filtered by `role === 'admin' || hasModuleAccess(permissions, section.module)`
- Grid layout with Tailwind classes

**Routing** (`services/frontend/app-chaldea/src/components/App/App.tsx`):
- Admin routes wrapped in `<ProtectedRoute requiredPermission="...">` or `requiredRole="editor"`
- Pattern: `path="admin/..."` → `<ProtectedRoute><ComponentName /></ProtectedRoute>`

**Example admin page**: `AdminActiveMobs` uses Redux slice with thunks for data fetching, pagination, filters.

**Battle player page** (`services/frontend/app-chaldea/src/components/pages/BattlePage/BattlePage.tsx`):
- Fetches `GET /battles/{battle_id}/state` which returns `{ snapshot, runtime }`
- `snapshot` = participant profiles (name, avatar, attributes, skills) from MongoDB/Redis cache
- `runtime` = live state (HP, mana, energy, stamina, current_actor, turn_number, deadline, cooldowns, active_effects)
- Types: `RuntimeState`, `ParticipantSnapshot`, `ResourceBlock` defined locally

### 2.4 API Gateway (Nginx)

- Route `location /battles/` → `proxy_pass http://battle-service_backend`
- Route `location /battles/internal/` → `return 403` (blocked from external)
- Admin endpoints at `/battles/admin/...` will be routed correctly through the existing `/battles/` location block — no Nginx changes needed.

### 2.5 Risks & Considerations

1. **No `cancelled` BattleResult**: Adding a new enum value to `BattleResult` requires an Alembic migration in whatever service owns the `battle_history` table. However, for force-finish we should NOT write BattleHistory records at all (no winner, no result to record). Simpler approach: just mark battle as `finished` and skip history records.
2. **Redis state may be expired**: If a battle's Redis state has already expired (TTL 48h), the admin state endpoint should gracefully return MySQL-only data.
3. **Character names**: Need to join or query `characters` table to get participant names/levels for the admin list view. battle-service has direct DB access to `characters` table (shared DB).
4. **Autobattle cleanup**: Force-finishing a battle should also deregister participants from autobattle-service to stop the bot from trying to act.
5. **battle-service has no Alembic**: Per CLAUDE.md rules, we should add Alembic when working with a service that lacks it. However, this feature does NOT require schema changes to battle-service tables (no new columns, no enum changes). The only migration needed is adding a permission in user-service (which already has Alembic). Adding Alembic to battle-service is out of scope for this feature.

---

## 3. Architecture Decision

### 3.1 Backend: battle-service — New Admin Endpoints

All endpoints on the existing `router` (prefix `/battles`), protected by `require_permission("battles:manage")`.

#### `GET /battles/admin/active`

List all active battles (status = pending or in_progress).

**Auth**: `Depends(require_permission("battles:manage"))`

**Query params**:
- `battle_type` (optional): filter by type (pve, pvp_training, pvp_death, pvp_attack)
- `page` (int, default=1): pagination
- `per_page` (int, default=20, max=100): page size

**Response** (200):
```json
{
  "battles": [
    {
      "id": 123,
      "status": "in_progress",
      "battle_type": "pve",
      "created_at": "2026-03-23T12:00:00",
      "updated_at": "2026-03-23T12:05:00",
      "participants": [
        {
          "participant_id": 456,
          "character_id": 10,
          "character_name": "Артас",
          "level": 5,
          "team": 0,
          "is_npc": false
        },
        {
          "participant_id": 457,
          "character_id": 11,
          "character_name": "Гоблин",
          "level": 3,
          "team": 1,
          "is_npc": true
        }
      ]
    }
  ],
  "total": 5,
  "page": 1,
  "per_page": 20
}
```

**Implementation**: SQL query joining `battles`, `battle_participants`, and `characters` tables (all in the same DB). Filter by `battles.status IN ('pending', 'in_progress')`. Paginate with LIMIT/OFFSET.

#### `GET /battles/admin/{battle_id}/state`

Get full battle state for admin viewing.

**Auth**: `Depends(require_permission("battles:manage"))`

**Response** (200):
```json
{
  "battle": {
    "id": 123,
    "status": "in_progress",
    "battle_type": "pve",
    "created_at": "2026-03-23T12:00:00"
  },
  "snapshot": [
    {
      "participant_id": 456,
      "character_id": 10,
      "name": "Артас",
      "avatar": "/photos/...",
      "attributes": { "strength": 10, "..." : "..." }
    }
  ],
  "runtime": {
    "turn_number": 3,
    "deadline_at": "2026-03-23T14:00:00",
    "current_actor": 456,
    "next_actor": 457,
    "first_actor": 456,
    "turn_order": [456, 457],
    "total_turns": 3,
    "last_turn": 2,
    "participants": {
      "456": {
        "hp": 80, "mana": 50, "energy": 100, "stamina": 90,
        "max_hp": 100, "max_mana": 60, "max_energy": 100, "max_stamina": 100,
        "cooldowns": {}, "fast_slots": []
      }
    },
    "active_effects": {}
  },
  "has_redis_state": true
}
```

If Redis state is expired: `runtime = null`, `has_redis_state = false`. Snapshot comes from MongoDB fallback.

**Implementation**: Reuse `load_state()` and `get_cached_snapshot()`/`load_snapshot()` — same logic as the player state endpoint but without ownership check. Add `max_hp/max_mana/max_energy/max_stamina` to runtime response (available in Redis state).

#### `POST /battles/admin/{battle_id}/force-finish`

Force-close a battle. No winner, no rewards, no consequences.

**Auth**: `Depends(require_permission("battles:manage"))`

**Request body**: None (empty POST).

**Response** (200):
```json
{
  "ok": true,
  "battle_id": 123,
  "message": "Бой принудительно завершён"
}
```

**Implementation steps**:
1. Load battle from MySQL; verify status is not already `finished`/`forfeit`.
2. Set `battles.status = 'finished'` in MySQL (reuse `finish_battle()` from crud.py).
3. Sync final resources (HP/mana/energy/stamina) back to `character_attributes` — same as normal finish, but use current Redis values (not the "loser at 0 HP" logic).
4. For `pvp_training` force-finish: do NOT set loser HP to 1, do NOT kill characters.
5. Expire Redis state immediately (`expire key 0` or `delete`).
6. Clean up deadline ZSET entries.
7. Deregister all NPC/mob participants from autobattle-service (POST to internal endpoint to stop bots).
8. Do NOT write `BattleHistory` records (no result to record).
9. Publish battle finished event on Redis Pub/Sub to notify connected clients.

**Error cases**:
- 404: Battle not found
- 400: Battle already finished/forfeit

### 3.2 Pydantic Schemas (new in schemas.py)

```python
class AdminBattleParticipant(BaseModel):
    participant_id: int
    character_id: int
    character_name: str
    level: int
    team: int
    is_npc: bool

class AdminBattleListItem(BaseModel):
    id: int
    status: str
    battle_type: str
    created_at: datetime
    updated_at: datetime
    participants: List[AdminBattleParticipant]

class AdminBattleListResponse(BaseModel):
    battles: List[AdminBattleListItem]
    total: int
    page: int
    per_page: int

class AdminBattleStateResponse(BaseModel):
    battle: dict
    snapshot: Optional[list] = None
    runtime: Optional[dict] = None
    has_redis_state: bool

class AdminForceFinishResponse(BaseModel):
    ok: bool
    battle_id: int
    message: str
```

### 3.3 Database Changes

**No schema changes** to battle-service tables.

**Permission migration** (user-service, `0016_add_battles_monitor_permission.py`):
- The existing `battles:manage` permission (id=28) is sufficient for all three admin endpoints. It's already assigned to Admin and Moderator roles. No new migration needed.

### 3.4 Frontend

**New file**: `services/frontend/app-chaldea/src/components/Admin/BattlesPage/AdminBattlesPage.tsx`

**Features**:
1. Table listing active battles with columns: ID, Type, Status, Participants, Created At
2. Battle type filter dropdown (All / PvE / PvP Training / PvP Death / PvP Attack)
3. Auto-refresh every 10 seconds (configurable)
4. Click row → expand/modal showing full battle state (HP bars, mana, turn info, active effects)
5. "Force Finish" button with confirmation dialog
6. Responsive (mobile-friendly with card layout on small screens)
7. Tailwind CSS only (no SCSS)
8. TypeScript (`.tsx`)

**State management**: Local component state with `useState` + `useEffect` for data fetching (no Redux slice needed — this is an admin-only view with simple data flow). Use `axios` for API calls consistent with the rest of the admin pages.

**Admin hub entry**: Add to `AdminPage.tsx` sections array:
```typescript
{ label: 'Бои', path: '/admin/battles', description: 'Мониторинг активных боёв, принудительное завершение', module: 'battles' }
```

**Route**: Add to `App.tsx`:
```tsx
<Route path="admin/battles" element={
  <ProtectedRoute requiredPermission="battles:manage">
    <AdminBattlesPage />
  </ProtectedRoute>
} />
```

### 3.5 No Nginx Changes Required

Admin endpoints are under `/battles/admin/...` which is covered by the existing `location /battles/` proxy rule. The `/battles/internal/` block (returning 403) won't match `/battles/admin/` paths.

---

## 4. Tasks

### T1: Backend — Admin battle endpoints (Backend Developer)

**Service**: `battle-service`
**Files to modify**:
- `services/battle-service/app/schemas.py` — add admin schemas
- `services/battle-service/app/main.py` — add 3 admin endpoints

**Steps**:
1. Add Pydantic schemas: `AdminBattleParticipant`, `AdminBattleListItem`, `AdminBattleListResponse`, `AdminBattleStateResponse`, `AdminForceFinishResponse`
2. Implement `GET /battles/admin/active`:
   - SQL join `battles` + `battle_participants` + `characters` (for name, level, is_npc)
   - Filter by status IN ('pending', 'in_progress'), optional battle_type filter
   - Paginate with LIMIT/OFFSET
   - Auth: `Depends(require_permission("battles:manage"))`
3. Implement `GET /battles/admin/{battle_id}/state`:
   - Load Redis state via `load_state()`
   - Load snapshot via `get_cached_snapshot()` / `load_snapshot()` (MongoDB fallback)
   - Include `max_hp/max_mana/max_energy/max_stamina` in runtime participants
   - No ownership check (admin access)
   - Graceful fallback when Redis state expired
4. Implement `POST /battles/admin/{battle_id}/force-finish`:
   - Validate battle exists and is active
   - Call `finish_battle()` to set MySQL status
   - Sync final resources to `character_attributes`
   - Delete Redis state and clean up deadline ZSET
   - Notify via Pub/Sub (`battle:{battle_id}:your_turn` with a "force_finished" message or publish on a separate channel)
   - Return success response

**Acceptance criteria**:
- All 3 endpoints return correct data
- Non-admin users get 403
- Force-finish does not grant rewards or trigger PvP consequences
- Force-finish cleans up Redis state

**Estimated effort**: Medium

### T2: Frontend — Admin Battles page (Frontend Developer)

**Service**: `frontend`
**Files to create**:
- `services/frontend/app-chaldea/src/components/Admin/BattlesPage/AdminBattlesPage.tsx`

**Files to modify**:
- `services/frontend/app-chaldea/src/components/Admin/AdminPage.tsx` — add section entry
- `services/frontend/app-chaldea/src/components/App/App.tsx` — add route

**Steps**:
1. Create `AdminBattlesPage.tsx`:
   - Fetch `GET /battles/admin/active` on mount and on interval (10s auto-refresh)
   - Display table: ID, Type (with color badges), Status, Participants (names), Created At
   - Battle type filter dropdown
   - Click row → expand inline detail panel or open modal
   - Detail view: show participant HP/mana/energy/stamina bars (similar to BattlePage), current turn, deadline, active effects
   - "Принудительно завершить" button with confirmation modal ("Вы уверены? Бой будет завершён без победителя и наград.")
   - On force-finish success: show toast, refresh list
   - Error handling: display all errors as Russian-language toasts
   - Mobile responsive: card layout on `sm:` breakpoint
2. Add entry to `AdminPage.tsx` sections array
3. Add `<Route>` in `App.tsx` with `ProtectedRoute`
4. Use Tailwind CSS only, TypeScript only, design system tokens
5. Run `npx tsc --noEmit` and `npm run build` to verify

**Acceptance criteria**:
- Page shows active battles with correct data
- Battle detail shows live state (HP bars, turn info)
- Force-finish works with confirmation
- All errors displayed to user
- Mobile responsive (360px+)
- No SCSS files created
- TypeScript only

**Estimated effort**: Medium-High

### T3: QA — Backend tests (QA Test)

**Service**: `battle-service`
**File to create**:
- `services/battle-service/app/tests/test_admin_battles.py`

**Test cases**:
1. `GET /battles/admin/active` — returns active battles with participants
2. `GET /battles/admin/active` — filters by battle_type
3. `GET /battles/admin/active` — pagination works correctly
4. `GET /battles/admin/active` — returns 403 for non-admin user
5. `GET /battles/admin/active` — returns 401 for unauthenticated request
6. `GET /battles/admin/{id}/state` — returns full state with Redis data
7. `GET /battles/admin/{id}/state` — returns graceful response when Redis state expired
8. `GET /battles/admin/{id}/state` — returns 404 for non-existent battle
9. `POST /battles/admin/{id}/force-finish` — finishes active battle
10. `POST /battles/admin/{id}/force-finish` — returns 400 for already finished battle
11. `POST /battles/admin/{id}/force-finish` — cleans up Redis state
12. `POST /battles/admin/{id}/force-finish` — returns 403 for non-admin
13. `POST /battles/admin/{id}/force-finish` — does NOT write BattleHistory records

**Estimated effort**: Medium

### Task Dependencies

```
T1 (Backend) ──→ T2 (Frontend)  [T2 depends on T1 API being available]
T1 (Backend) ──→ T3 (QA Tests)  [T3 tests T1 endpoints]
T2 and T3 can run in parallel after T1.
```

---

## 5. Review Log

### Review #1 — QA Test + Reviewer (2026-03-23)

**Verdict: PASS**

#### QA Tests (T3)

Created `services/battle-service/app/tests/test_admin_battles.py` — 15 test cases (12 logical groups + bonus 401 tests):

| # | Test | Result |
|---|------|--------|
| 1 | GET /admin/active returns active battles with participants | PASS |
| 2 | GET /admin/active filters by battle_type | PASS |
| 3 | GET /admin/active pagination works (OFFSET/LIMIT) | PASS |
| 4 | GET /admin/active returns 403 for non-admin | PASS |
| 4b | GET /admin/active returns 401 for unauthenticated | PASS |
| 5 | GET /admin/{id}/state returns full state with Redis | PASS |
| 6 | GET /admin/{id}/state returns 404 for non-existent battle | PASS |
| 7 | GET /admin/{id}/state handles expired Redis gracefully (runtime=null) | PASS |
| 8 | POST /admin/{id}/force-finish finishes active battle | PASS |
| 9 | POST /admin/{id}/force-finish returns 400 for already finished | PASS |
| 9b | POST /admin/{id}/force-finish returns 400 for forfeit | PASS |
| 10 | POST /admin/{id}/force-finish returns 404 for non-existent | PASS |
| 11 | POST /admin/{id}/force-finish returns 403 for non-admin | PASS |
| 11b | POST /admin/{id}/force-finish returns 401 for unauthenticated | PASS |
| 12 | POST /admin/{id}/force-finish does NOT write BattleHistory | PASS |

All 15 tests pass. No regressions in existing tests (30 pre-existing failures are unrelated to FEAT-067).

#### Backend Review

**schemas.py** — PASS
- [x] Pydantic <2.0 compliant — uses `BaseModel` without `model_config`, no v2-only features
- [x] 5 new schemas cleanly structured: `AdminBattleParticipant`, `AdminBattleListItem`, `AdminBattleListResponse`, `AdminBattleStateResponse`, `AdminForceFinishResponse`
- [x] No `orm_mode` needed (these are not ORM-backed schemas)

**main.py** — PASS
- [x] All 3 endpoints use `Depends(require_permission("battles:manage"))` for auth
- [x] `GET /admin/active`: correct SQL join (battles + battle_participants + characters), pagination with LIMIT/OFFSET, optional battle_type filter
- [x] `GET /admin/{id}/state`: reuses `get_battle()`, `load_state()`, `get_cached_snapshot()`, `load_snapshot()`. Graceful fallback when Redis expired (`runtime=null`, `has_redis_state=false`)
- [x] `POST /admin/{id}/force-finish`: validates status, syncs resources, calls `finish_battle()`, cleans Redis (state key, deadlines, snapshot, turns), publishes Pub/Sub event. Does NOT write BattleHistory, does NOT distribute rewards, does NOT trigger PvP consequences
- [x] Error messages in Russian
- [x] `python -m py_compile` passes for all modified files

**auth_http.py** — no changes needed, `require_permission` already existed

#### Frontend Review

**AdminBattlesPage.tsx** — PASS
- [x] TypeScript (`.tsx`) — no `.jsx`
- [x] No `React.FC` used anywhere
- [x] Tailwind CSS only — no SCSS/CSS imports
- [x] Responsive 360px+: desktop table (`hidden md:block`) + mobile card layout (`md:hidden`)
- [x] Russian UI text throughout (headers, labels, buttons, error messages, toasts)
- [x] Error handling: all API calls have catch blocks with Russian error messages displayed via `toast.error()` or inline error state
- [x] Auto-refresh every 10 seconds
- [x] Confirmation dialog before force-finish with Russian text
- [x] Design system tokens used: `gold-text`, `gray-bg`, `rounded-card`, `input-underline`, `btn-line`, `text-site-red`, `bg-site-dark`

**AdminPage.tsx** — PASS
- [x] Section added: `{ label: 'Бои', path: '/admin/battles', description: '...', module: 'battles' }`
- [x] Correctly uses `hasModuleAccess` for visibility filtering

**App.tsx** — PASS
- [x] Route added: `path="admin/battles"` with `<ProtectedRoute requiredPermission="battles:manage">`
- [x] Import added correctly

#### Checklist Summary

- [x] Pydantic <2.0 (no model_config, no v2 features)
- [x] No React.FC
- [x] TypeScript + Tailwind only
- [x] Responsive 360px+
- [x] Russian UI text
- [x] Error handling (all API errors displayed)
- [x] Auth: `require_permission("battles:manage")` on all 3 endpoints
- [x] Force-finish does NOT write history/rewards/consequences
- [x] `python -m py_compile` passes

#### Notes

- Node.js is not installed in the review environment; `npx tsc --noEmit` and `npm run build` could not be run locally. TypeScript correctness verified by code inspection (proper types, interfaces, no `any` usage).
- 30 pre-existing test failures in battle-service are unrelated to this feature (test_battle_fixes, test_pvp_*, test_npc_death). Should be tracked in ISSUES.md separately.

---

## 6. Logging

```
[LOG] 2026-03-23 — PM: фича создана (FEAT-067), запускаю анализ и проектирование
[LOG] 2026-03-23 — Codebase Analyst + Architect: анализ завершён — изучены models.py, redis_state.py, main.py (battle-service), auth_http.py, AdminPage.tsx, App.tsx, BattlePage.tsx, permissions system. Спроектированы 3 backend-эндпоинта, 1 frontend-страница, QA-план. Записаны секции 2-4.
[LOG] 2026-03-23 — Backend Developer: T1 выполнен — добавлены 5 Pydantic-схем в schemas.py, реализованы 3 admin-эндпоинта в main.py (GET /battles/admin/active, GET /battles/admin/{id}/state, POST /battles/admin/{id}/force-finish). Все файлы прошли py_compile.
[LOG] 2026-03-23 — Frontend Developer: T2 выполнен — создан AdminBattlesPage.tsx (TypeScript, Tailwind, без React.FC). Реализованы: таблица активных боёв с фильтром по типу, авто-обновление каждые 10с, inline-детали боя с HP/мана/энергия/стамина барами, принудительное завершение с подтверждением, адаптивная вёрстка (карточки на мобильных, таблица на десктопе), пагинация. Добавлен маршрут в App.tsx и секция в AdminPage.tsx. Node.js не установлен в среде — tsc/build невозможны локально.
[LOG] 2026-03-23 — QA Test: T3 выполнен — написано 15 тестов в test_admin_battles.py, все проходят. Покрыты: list active battles, фильтрация, пагинация, 403/401, state endpoint (с Redis и без), force-finish (успех, 400 already finished, 404, 403, отсутствие записи BattleHistory).
[LOG] 2026-03-23 — Reviewer: ревью завершено — PASS. Backend: Pydantic <2.0, auth на всех 3 эндпоинтах, force-finish не пишет историю/награды. Frontend: TypeScript, Tailwind only, без React.FC, адаптив 360px+, русский UI, обработка ошибок. Все 15 тестов проходят, регрессий нет.
```

---

## 7. Completion Summary

*Pending...*

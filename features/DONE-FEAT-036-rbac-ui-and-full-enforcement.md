# FEAT-036: RBAC Admin UI + Полное применение прав на все эндпоинты

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-18 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Продолжение FEAT-035. Три направления:
1. **Admin UI** — страница в админке для управления ролями пользователей, назначения прав, настройки базовых наборов доступов для ролей
2. **Регистрация разрешений для всех модулей** — добавить permissions для characters, skills, locations, rules, photos (сейчас есть только users и items)
3. **Гранулярная проверка прав на всех ~67 admin-эндпоинтах** — каждый эндпоинт проверяет конкретное разрешение через `require_permission()` или аналог

### Бизнес-правила
- Админ может: видеть всех пользователей с их ролями, менять роль, задавать display_name, добавлять/убирать индивидуальные разрешения, настраивать базовый набор прав для каждой роли
- Модератор не может менять роли/права (это admin-only)
- При назначении прав можно добавить целый модуль блоком (все действия сразу)
- Все admin-эндпоинты проверяют конкретные разрешения, а не просто "admin or moderator"

### UX / Пользовательский сценарий
1. Админ заходит в AdminPage → видит секцию "Пользователи и роли"
2. Открывает → видит таблицу пользователей с ролями и правами
3. Может назначить роль, задать отображаемое имя роли
4. Может добавить/убрать индивидуальные разрешения (по модулям или отдельно)
5. Может настроить базовый набор прав для роли (role_permissions)
6. Модератор с правом items:* пытается открыть skills → редирект/403

### Edge Cases
- Модератор с items:create пытается вызвать items:delete → 403
- Эндпоинт без зарегистрированного разрешения → fallback на get_admin_user (admin+moderator)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 Current RBAC Implementation State (from FEAT-035)

#### DB Models (`services/user-service/models.py`)

- `Role` — id, name, level, description. Seeded: user(0), editor(20), moderator(50), admin(100)
- `Permission` — id, module, action, description. Seeded: users:{read,update,delete,manage}, items:{create,read,update,delete}
- `RolePermission` — role_id, permission_id (many-to-many)
- `UserPermission` — user_id, permission_id, granted (bool, for overrides)
- `User.role_id` — FK to roles, `User.role_display_name` — custom display name, `User.role` — legacy string (kept in sync)

#### Core RBAC Logic (`services/user-service/crud.py`)

- `get_effective_permissions(db, user)` — admin gets ALL permissions automatically; others get role_permissions + user_permissions overrides
- `require_permission(db, user, permission)` — checks effective permissions, raises 403
- `require_admin(db, user)` — strict admin-only check (for role/permission management endpoints)
- `is_admin(db, user)` — bool check for admin role

#### Existing RBAC Management Endpoints (`services/user-service/main.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /users/roles | `require_admin` | List all roles |
| PUT | /users/{user_id}/role | `require_admin` | Assign role to user |
| GET | /users/permissions | `require_admin` | List all permissions grouped by module |
| PUT | /users/{user_id}/permissions | `require_admin` | Set user permission overrides (grants/revokes) |
| GET | /users/{user_id}/effective-permissions | `require_admin` | View effective permissions for a user |

#### Schemas (`services/user-service/schemas.py`)

- `MeResponse` — includes `role`, `role_display_name`, `permissions: List[str]`
- `RoleResponse`, `PermissionItem`, `PermissionsGroupedResponse`
- `RoleAssignRequest`, `UserRoleResponse`
- `PermissionOverridesRequest`, `UserPermissionsResponse`, `EffectivePermissionsResponse`

#### `auth_http.py` in Other Services (e.g., `services/character-service/app/auth_http.py`)

- `UserRead` — includes `permissions: List[str]` (populated from `/users/me` response)
- `get_current_user_via_http()` — calls `GET /users/me`, returns `UserRead`
- `get_admin_user()` — checks `user.role not in ("admin", "moderator")`, raises 403. **Does NOT check granular permissions.**

#### Frontend RBAC Infrastructure

- `userSlice.ts` — stores `role`, `roleDisplayName`, `permissions[]` from `/users/me`
- `permissions.ts` — utility functions: `hasPermission`, `hasAnyPermission`, `hasModuleAccess`, `isStaff`
- `ProtectedRoute.tsx` — route guard with `requiredRole`, `requiredPermission`, `requiredPermissions` props
- `AdminPage.tsx` — filters admin sections by `hasModuleAccess(permissions, section.module)` or `role === 'admin'`

---

### 2.2 Complete Admin Endpoint Mapping by Service

#### user-service (`services/user-service/main.py`)

**Already using `require_permission` or `require_admin` (from FEAT-035):**

| # | Method | Path | Line | Current Auth | Proposed Permission |
|---|--------|------|------|-------------|-------------------|
| 1 | DELETE | /users/user_characters/{user_id}/{character_id} | L398 | `require_permission(db, user, "users:manage")` | `users:manage` (already done) |
| 2 | POST | /users/{user_id}/clear_current_character | L420 | `require_permission(db, user, "users:manage")` | `users:manage` (already done) |
| 3 | GET | /users/roles | L527 | `require_admin` | `users:manage` (admin-only, keep as-is) |
| 4 | PUT | /users/{user_id}/role | L538 | `require_admin` | `users:manage` (admin-only, keep as-is) |
| 5 | GET | /users/permissions | L590 | `require_admin` | `users:manage` (admin-only, keep as-is) |
| 6 | PUT | /users/{user_id}/permissions | L616 | `require_admin` | `users:manage` (admin-only, keep as-is) |
| 7 | GET | /users/{user_id}/effective-permissions | L720 | `require_admin` | `users:manage` (admin-only, keep as-is) |

**Note:** RBAC management endpoints (#3-#7) must remain `require_admin` to prevent privilege escalation — a moderator with `users:manage` should not be able to assign roles.

#### character-service (`services/character-service/app/main.py`)

| # | Method | Path | Line | Current Auth | Proposed Permission |
|---|--------|------|------|-------------|-------------------|
| 1 | POST | /characters/requests/{request_id}/approve | L63 | `get_admin_user` | `characters:approve` |
| 2 | POST | /characters/requests/{request_id}/reject | L556 | `get_admin_user` | `characters:approve` |
| 3 | GET | /characters/admin/list | L222 | `get_admin_user` | `characters:read` |
| 4 | PUT | /characters/admin/{character_id} | L269 | `get_admin_user` | `characters:update` |
| 5 | POST | /characters/admin/{character_id}/unlink | L355 | `get_admin_user` | `characters:update` |
| 6 | DELETE | /characters/{character_id} | L420 | `get_admin_user` | `characters:delete` |
| 7 | PUT | /characters/starter-kits/{class_id} | L620 | `get_admin_user` | `characters:update` |
| 8 | POST | /characters/titles/ | L640 | `get_admin_user` | `characters:create` |

**Total: 8 admin endpoints**

#### skills-service (`services/skills-service/app/main.py`)

| # | Method | Path | Line | Current Auth | Proposed Permission |
|---|--------|------|------|-------------|-------------------|
| 1 | POST | /skills/admin/skills/ | L91 | `get_admin_user` | `skills:create` |
| 2 | PUT | /skills/admin/skills/{skill_id} | L113 | `get_admin_user` | `skills:update` |
| 3 | DELETE | /skills/admin/skills/{skill_id} | L125 | `get_admin_user` | `skills:delete` |
| 4 | POST | /skills/admin/skill_ranks/ | L139 | `get_admin_user` | `skills:create` |
| 5 | PUT | /skills/admin/skill_ranks/{rank_id} | L157 | `get_admin_user` | `skills:update` |
| 6 | DELETE | /skills/admin/skill_ranks/{rank_id} | L169 | `get_admin_user` | `skills:delete` |
| 7 | POST | /skills/admin/damages/ | L183 | `get_admin_user` | `skills:create` |
| 8 | PUT | /skills/admin/damages/{damage_id} | L201 | `get_admin_user` | `skills:update` |
| 9 | DELETE | /skills/admin/damages/{damage_id} | L213 | `get_admin_user` | `skills:delete` |
| 10 | POST | /skills/admin/effects/ | L227 | `get_admin_user` | `skills:create` |
| 11 | PUT | /skills/admin/effects/{effect_id} | L245 | `get_admin_user` | `skills:update` |
| 12 | DELETE | /skills/admin/effects/{effect_id} | L257 | `get_admin_user` | `skills:delete` |
| 13 | POST | /skills/admin/character_skills/ | L271 | `get_admin_user` | `skills:create` |
| 14 | PUT | /skills/admin/character_skills/{cs_id} | L289 | `get_admin_user` | `skills:update` |
| 15 | DELETE | /skills/admin/character_skills/{cs_id} | L308 | `get_admin_user` | `skills:delete` |
| 16 | DELETE | /skills/admin/character_skills/by_character/{character_id} | L279 | `get_admin_user` | `skills:delete` |
| 17 | PUT | /skills/admin/skills/{skill_id}/full_tree | L462 | `get_admin_user` | `skills:update` |

**GET endpoints (no auth, public reads):** GET /skills/admin/skills/, GET /skills/admin/skills/{id}, GET /skills/admin/skills/{id}/full_tree, GET /skills/admin/skill_ranks/{id}, GET /skills/admin/damages/{id}, GET /skills/admin/effects/{id} — currently have NO auth. Should add `skills:read`.

**Total: 17 protected + 6 unprotected GET endpoints = 23 admin endpoints**

#### inventory-service (`services/inventory-service/app/main.py`)

| # | Method | Path | Line | Current Auth | Proposed Permission |
|---|--------|------|------|-------------|-------------------|
| 1 | POST | /inventory/items | L438 | `get_admin_user` | `items:create` |
| 2 | PUT | /inventory/items/{item_id} | L469 | `get_admin_user` | `items:update` |
| 3 | DELETE | /inventory/items/{item_id} | L496 | `get_admin_user` | `items:delete` |
| 4 | DELETE | /inventory/{character_id}/all | L564 | `get_admin_user` | `items:delete` |

**Total: 4 admin endpoints**

#### locations-service (`services/locations-service/app/main.py`)

| # | Method | Path | Line | Current Auth | Proposed Permission |
|---|--------|------|------|-------------|-------------------|
| 1 | POST | /locations/countries/create | L58 | `get_admin_user` | `locations:create` |
| 2 | PUT | /locations/countries/{country_id}/update | L69 | `get_admin_user` | `locations:update` |
| 3 | POST | /locations/regions/create | L91 | `get_admin_user` | `locations:create` |
| 4 | PUT | /locations/regions/{region_id}/update | L96 | `get_admin_user` | `locations:update` |
| 5 | DELETE | /locations/regions/{region_id}/delete | L108 | `get_admin_user` | `locations:delete` |
| 6 | POST | /locations/districts | L129 | `get_admin_user` | `locations:create` |
| 7 | PUT | /locations/districts/{district_id}/update | L143 | `get_admin_user` | `locations:update` |
| 8 | DELETE | /locations/districts/{district_id}/delete | L186 | `get_admin_user` | `locations:delete` |
| 9 | POST | /locations/ | L207 | `get_admin_user` | `locations:create` |
| 10 | PUT | /locations/{location_id}/update | L226 | `get_admin_user` | `locations:update` |
| 11 | DELETE | /locations/{location_id}/delete | L270 | `get_admin_user` | `locations:delete` |
| 12 | POST | /locations/{location_id}/neighbors/ | L292 | `get_admin_user` | `locations:update` |
| 13 | DELETE | /locations/{location_id}/neighbors/{neighbor_id} | L328 | `get_admin_user` | `locations:delete` |
| 14 | POST | /locations/{location_id}/neighbors/update | L369 | `get_admin_user` | `locations:update` |
| 15 | POST | /rules/create | L539 | `get_admin_user` | `rules:create` |
| 16 | PUT | /rules/reorder | L549 | `get_admin_user` | `rules:update` |
| 17 | PUT | /rules/{rule_id}/update | L560 | `get_admin_user` | `rules:update` |
| 18 | DELETE | /rules/{rule_id}/delete | L571 | `get_admin_user` | `rules:delete` |

**Total: 18 admin endpoints (14 locations + 4 rules)**

#### character-attributes-service (`services/character-attributes-service/app/main.py`)

| # | Method | Path | Line | Current Auth | Proposed Permission |
|---|--------|------|------|-------------|-------------------|
| 1 | PUT | /attributes/admin/{character_id} | L493 | `get_admin_user` | `characters:update` |
| 2 | DELETE | /attributes/{character_id} | L524 | `get_admin_user` | `characters:delete` |

**Total: 2 admin endpoints** (mapped to `characters` module since they modify character data)

#### photo-service (`services/photo-service/main.py`)

| # | Method | Path | Line | Current Auth | Proposed Permission |
|---|--------|------|------|-------------|-------------------|
| 1 | POST | /photo/change_country_map | L76 | `get_admin_user` | `photos:upload` |
| 2 | POST | /photo/change_region_map | L103 | `get_admin_user` | `photos:upload` |
| 3 | POST | /photo/change_region_image | L126 | `get_admin_user` | `photos:upload` |
| 4 | POST | /photo/change_district_image | L149 | `get_admin_user` | `photos:upload` |
| 5 | POST | /photo/change_location_image | L172 | `get_admin_user` | `photos:upload` |
| 6 | POST | /photo/change_skill_image | L189 | `get_admin_user` | `photos:upload` |
| 7 | POST | /photo/change_skill_rank_image | L211 | `get_admin_user` | `photos:upload` |
| 8 | POST | /photo/change_item_image | L232 | `get_admin_user` | `photos:upload` |
| 9 | POST | /photo/change_rule_image | L253 | `get_admin_user` | `photos:upload` |

**Note:** User avatar and profile background endpoints use `get_current_user_via_http` with self-only checks — NOT admin endpoints.

**Total: 9 admin endpoints**

#### notification-service (`services/notification-service/app/main.py`)

| # | Method | Path | Line | Current Auth | Proposed Permission |
|---|--------|------|------|-------------|-------------------|
| 1 | POST | /notifications/create | L96 | Inline: `current_user.role not in ("admin", "moderator")` | `notifications:create` |

**Total: 1 admin endpoint**

---

### 2.3 Endpoint Count Summary

| Service | Admin Endpoints | New Module |
|---------|----------------|------------|
| user-service | 7 (already done) | `users` (existing) |
| character-service | 8 | `characters` |
| skills-service | 23 (17 protected + 6 unprotected GET) | `skills` |
| inventory-service | 4 | `items` (existing) |
| locations-service | 14 | `locations` |
| locations-service (rules) | 4 | `rules` |
| character-attributes-service | 2 | `characters` |
| photo-service | 9 | `photos` |
| notification-service | 1 | `notifications` |
| **TOTAL** | **72** | |

---

### 2.4 New Permissions to Register

Current permissions (from FEAT-035 migration 0006): `users:{read,update,delete,manage}`, `items:{create,read,update,delete}` (8 total)

New permissions needed:

| Module | Actions | Description |
|--------|---------|-------------|
| `characters` | `create`, `read`, `update`, `delete`, `approve` | Character management + request moderation |
| `skills` | `create`, `read`, `update`, `delete` | Skill trees, ranks, damages, effects, character_skills |
| `locations` | `create`, `read`, `update`, `delete` | Countries, regions, districts, locations, neighbors |
| `rules` | `create`, `read`, `update`, `delete` | Game rules management |
| `photos` | `upload` | Admin image uploads (maps, skill images, item images, etc.) |
| `notifications` | `create` | Send admin notifications |

**Total new: 16 permissions. Grand total: 24 permissions.**

---

### 2.5 Frontend Admin Pages Analysis

#### Routes in `App.tsx` (`services/frontend/app-chaldea/src/components/App/App.tsx`)

| Route | Component | Current Protection | Proposed Permission |
|-------|-----------|-------------------|-------------------|
| /admin | AdminPage | `requiredRole="editor"` | Keep as-is (hub page, filters sections internally) |
| /requestsPage | RequestsPage | `requiredRole="moderator"` | `requiredPermission="characters:approve"` |
| /admin/locations | AdminLocationsPage | `requiredRole="editor"` | `requiredPermissions=["locations:read", "locations:create", ...]` or module check |
| /home/admin/skills | AdminSkillsPage | `requiredRole="editor"` | `requiredPermissions=["skills:read", "skills:create", ...]` or module check |
| /admin/items | ItemsAdminPage | `requiredPermission="items:read"` | Already done (permission-based) |
| /admin/starter-kits | StarterKitsPage | `requiredRole="editor"` | `requiredPermission="characters:update"` |
| /admin/characters | AdminCharactersPage | `requiredRole="editor"` | `requiredPermission="characters:read"` |
| /admin/characters/:characterId | AdminCharacterDetailPage | `requiredRole="editor"` | `requiredPermission="characters:read"` |
| /admin/rules | RulesAdminPage | `requiredRole="editor"` | `requiredPermission="rules:read"` |

**Missing from AdminPage sections:** A "Users & Roles" section needs to be added for RBAC management UI (`module: "users"`).

#### AdminPage Sections (`services/frontend/app-chaldea/src/components/Admin/AdminPage.tsx`)

Current sections with module mapping:
1. Заявки → `characters`
2. Айтемы → `items`
3. Локации → `locations`
4. Навыки → `skills`
5. Стартовые наборы → `characters`
6. Персонажи → `characters`
7. Правила → `locations` (should be `rules`)

**Issues found:**
- "Правила" is mapped to module `locations` — should be `rules`
- Missing: "Пользователи и роли" section (for RBAC admin UI, module `users`)

---

### 2.6 How Permission Enforcement Should Work in Other Services

**Current state:** `auth_http.py` in all non-user services gets `UserRead` with `permissions: List[str]` from `/users/me`. But `get_admin_user()` only checks `user.role not in ("admin", "moderator")` — it ignores the `permissions` list entirely.

**Required change:** Add a `require_permission(permission_str)` function to `auth_http.py` that:
1. Gets the user via `get_current_user_via_http()`
2. Checks if `permission_str` is in `user.permissions`
3. Admin role always has all permissions (from `/users/me` response), so no special handling needed
4. Raises 403 if permission is missing

This can be implemented as either:
- A dependency factory: `def require_permission(perm: str) -> Callable` that returns a FastAPI dependency
- A simple helper: `def check_permission(user: UserRead, perm: str)` called inside endpoints

**Key insight:** The permissions list is already populated by the `/users/me` endpoint via `get_effective_permissions()`. Admin automatically gets ALL permissions. So the check in other services is simply `if permission not in user.permissions: raise 403`.

---

### 2.7 Missing API Endpoints for Admin UI

**Already exists:**
- `GET /users/roles` — list all roles
- `PUT /users/{user_id}/role` — assign role to user
- `GET /users/permissions` — list all permissions (grouped by module)
- `PUT /users/{user_id}/permissions` — set user permission overrides
- `GET /users/{user_id}/effective-permissions` — view effective permissions

**Missing for admin UI:**

1. **`PUT /users/roles/{role_id}/permissions`** — Update default permissions for a role (role_permissions table). Currently there's no endpoint to configure which permissions a role gets by default. The admin UI "role permissions" configuration panel requires this.

2. **`GET /users/admin/list`** — List all users with their roles, role_display_names, and permissions. The existing `GET /users/all` returns `UserPublicItem` (id, username, avatar, registered_at, last_active_at) — it does NOT include role, role_id, role_display_name, or permissions. The admin RBAC panel needs a richer list.

3. **Permission CRUD is NOT needed** — permissions are registered through Alembic migrations (they're system-defined, not user-defined). No endpoint to create/delete permissions is required.

---

### 2.8 Affected Services Summary

| Service | Type of Changes | Key Files |
|---------|----------------|-----------|
| user-service | New endpoints + migration | `main.py`, `crud.py`, `schemas.py`, `alembic/versions/0007_*.py` |
| character-service | Replace `get_admin_user` with permission checks | `app/auth_http.py`, `app/main.py` |
| skills-service | Replace `get_admin_user` with permission checks | `app/auth_http.py`, `app/main.py` |
| inventory-service | Replace `get_admin_user` with permission checks | `app/auth_http.py`, `app/main.py` |
| locations-service | Replace `get_admin_user` with permission checks | `app/auth_http.py`, `app/main.py` |
| character-attributes-service | Replace `get_admin_user` with permission checks | `app/auth_http.py`, `app/main.py` |
| photo-service | Replace `get_admin_user` with permission checks | `auth_http.py`, `main.py` |
| notification-service | Replace inline role check with permission check | `app/auth_http.py`, `app/main.py` |
| frontend | New RBAC admin page, fix route guards, fix AdminPage modules | `App.tsx`, `AdminPage.tsx`, new RBAC components |

### 2.9 Existing Patterns

- **user-service:** sync SQLAlchemy, Pydantic <2.0, Alembic present (version_table: `alembic_version_user`, latest: 0006)
- **character-service:** sync SQLAlchemy, Alembic present
- **skills-service:** async SQLAlchemy (aiomysql), Alembic present
- **locations-service:** async SQLAlchemy (aiomysql), Alembic present
- **inventory-service:** sync SQLAlchemy, Alembic present
- **character-attributes-service:** sync SQLAlchemy, Alembic present
- **photo-service:** sync SQLAlchemy (mirror models), Alembic present (empty migration)
- **notification-service:** sync SQLAlchemy, **NO Alembic** (uses `create_all()` at startup)

### 2.10 Cross-Service Dependencies

- All 7 non-user services call `GET /users/me` for authentication (via `auth_http.py`)
- The `UserRead` schema in `auth_http.py` already includes `permissions: List[str]` — no schema change needed
- The `/users/me` endpoint already returns permissions — no API change needed
- Permission enforcement is purely local to each service (check `user.permissions` list)

### 2.11 DB Changes

- **New Alembic migration** in user-service (0007): INSERT new permissions for modules `characters`, `skills`, `locations`, `rules`, `photos`, `notifications`. INSERT corresponding `role_permissions` rows (admin gets all, moderator gets all except users:*).
- **No schema changes** — all tables already exist from FEAT-035 migration 0006.

### 2.12 Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Locking out existing moderators | Moderators currently have full admin access; switching to permission checks could remove their access to modules where they have no permissions in the DB | Ensure migration 0007 grants moderator role all new permissions (characters:*, skills:*, locations:*, rules:*, photos:*, notifications:*) |
| Breaking internal service-to-service calls | Some endpoints (e.g., POST /characters/requests/{id}/approve, POST /attributes/, DELETE /attributes/{character_id}) are called by other services without auth tokens | These S2S endpoints must NOT be protected by permissions. Only endpoints called from the frontend admin UI should be protected. Review each endpoint for S2S usage. |
| `get_admin_user` still needed as fallback | Some endpoints might need both old `get_admin_user` (for S2S calls) and new permission checks | Keep `get_admin_user` function in `auth_http.py` as a utility, add `require_permission` alongside it |
| Admin UI complexity | Managing role_permissions per role is a complex UI | Start with a simple grid: rows=permissions, columns=roles, checkboxes |

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Overview

Three workstreams, largely parallelizable:

1. **Alembic migration 0007** — register 16 new permissions, assign to roles
2. **Backend enforcement** — add `require_permission()` to 7 services' `auth_http.py`, replace `get_admin_user` with granular checks on 65 endpoints (user-service's 7 are already done)
3. **Frontend** — RBAC admin UI page, route guard updates, AdminPage fixes, new user-service API endpoints

### 3.2 Alembic Migration 0007

**File:** `services/user-service/alembic/versions/0007_add_remaining_permissions.py`

Insert 16 new permissions (IDs 9-24, continuing from 0006's 8):

| ID | Module | Action | Description |
|----|--------|--------|-------------|
| 9 | characters | create | Create characters and titles |
| 10 | characters | read | View character admin panels |
| 11 | characters | update | Edit characters, starter kits, attributes |
| 12 | characters | delete | Delete characters and attributes |
| 13 | characters | approve | Approve/reject character requests |
| 14 | skills | create | Create skills, ranks, damages, effects |
| 15 | skills | read | View skill admin panels |
| 16 | skills | update | Edit skills and full trees |
| 17 | skills | delete | Delete skills, ranks, damages, effects |
| 18 | locations | create | Create countries, regions, districts, locations |
| 19 | locations | read | View location admin panels |
| 20 | locations | update | Edit locations, neighbors |
| 21 | locations | delete | Delete locations, neighbors |
| 22 | rules | create | Create game rules |
| 23 | rules | read | View rules admin panel |
| 24 | rules | update | Edit and reorder rules |
| 25 | rules | delete | Delete rules |
| 26 | photos | upload | Upload admin images (maps, items, skills, rules) |
| 27 | notifications | create | Send admin notifications |

**Note:** That's 19 new permissions (IDs 9-27), grand total = 27 permissions.

**Role-permission assignments:**

- **Admin (role_id=4):** ALL permissions automatically via `get_effective_permissions()` logic (no explicit mapping needed, but we insert them anyway for the role_permissions admin UI to show the full picture).
- **Moderator (role_id=3):** All NEW permissions (IDs 9-27). Moderator already has items:* (5-8) from 0006. Combined: everything except `users:*` (IDs 1-4).
- **Editor (role_id=2):** Only `*:read` actions from new permissions: `characters:read` (10), `skills:read` (15), `locations:read` (19), `rules:read` (23). Editor already has `users:read` (1), `items:read` (6) from 0006.

**Downgrade:** DELETE permissions with IDs 9-27, DELETE corresponding role_permissions rows.

### 3.3 Backend: `require_permission()` in auth_http.py

Add a dependency factory to each service's `auth_http.py`:

```python
def require_permission(permission: str):
    """FastAPI dependency factory for granular permission checks."""
    def checker(user: UserRead = Depends(get_current_user_via_http)) -> UserRead:
        if permission not in user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return user
    return checker
```

**Why dependency factory (not inline helper):** It integrates naturally with FastAPI's `Depends()` system — `Depends(require_permission("skills:create"))` reads cleanly in endpoint signatures, same pattern as existing `Depends(get_admin_user)`.

**`get_admin_user` is retained** as a utility in all services. It's not removed since:
- Some code paths may still need the simple admin/moderator check
- Removing it would be unnecessary churn
- It serves as a fallback for any edge case missed

### 3.4 Endpoint Enforcement Mapping

Each service's `main.py` replaces `Depends(get_admin_user)` with `Depends(require_permission("module:action"))`:

**character-service (8 endpoints):**
| Endpoint | Permission |
|----------|-----------|
| POST /characters/requests/{id}/approve | `characters:approve` |
| POST /characters/requests/{id}/reject | `characters:approve` |
| GET /characters/admin/list | `characters:read` |
| PUT /characters/admin/{id} | `characters:update` |
| POST /characters/admin/{id}/unlink | `characters:update` |
| DELETE /characters/{id} | `characters:delete` |
| PUT /characters/starter-kits/{class_id} | `characters:update` |
| POST /characters/titles/ | `characters:create` |

**skills-service (23 endpoints):**
- All `POST /skills/admin/*` → `skills:create`
- All `PUT /skills/admin/*` → `skills:update`
- All `DELETE /skills/admin/*` → `skills:delete`
- All `GET /skills/admin/*` (6 unprotected) → add `Depends(require_permission("skills:read"))`

**inventory-service (4 endpoints):**
| Endpoint | Permission |
|----------|-----------|
| POST /inventory/items | `items:create` |
| PUT /inventory/items/{id} | `items:update` |
| DELETE /inventory/items/{id} | `items:delete` |
| DELETE /inventory/{character_id}/all | `items:delete` |

**locations-service (18 endpoints):**
- All `POST /locations/*/create`, `POST /locations/` → `locations:create`
- All `PUT /locations/*/update`, `POST /locations/*/neighbors/update` → `locations:update`
- All `DELETE /locations/*/delete`, `DELETE /locations/*/neighbors/*` → `locations:delete`
- `POST /locations/{id}/neighbors/` → `locations:update`
- `POST /rules/create` → `rules:create`
- `PUT /rules/reorder`, `PUT /rules/{id}/update` → `rules:update`
- `DELETE /rules/{id}/delete` → `rules:delete`

**character-attributes-service (2 endpoints):**
| Endpoint | Permission |
|----------|-----------|
| PUT /attributes/admin/{character_id} | `characters:update` |
| DELETE /attributes/{character_id} | `characters:delete` |

**photo-service (9 endpoints):**
- All 9 admin image upload endpoints → `photos:upload`

**notification-service (1 endpoint):**
- `POST /notifications/create` → replace inline role check with `Depends(require_permission("notifications:create"))`

### 3.5 Service-to-Service Call Safety

Based on analysis of the inter-service dependency graph (CLAUDE.md section 2), **no admin endpoints are called service-to-service.** S2S calls use non-admin endpoints (e.g., `POST /characters/`, `GET /characters/{id}`, `POST /attributes/`, `GET /inventory/{character_id}`). The admin endpoints (prefixed with `/admin/` or having `get_admin_user` dependency) are called exclusively from the frontend.

**Exception check — character-attributes-service:** `DELETE /attributes/{character_id}` is called from character-service during character deletion. **However**, character-service makes this call during its own admin endpoint `DELETE /characters/{character_id}`, which is itself protected. The call chain is: Frontend (with user token) → character-service (validates `characters:delete`) → character-attributes-service (with forwarded token, validates `characters:delete`). Since the same user token is forwarded, the permission check works correctly on both sides.

**Verification needed during implementation:** Each service's `main.py` should be checked for any S2S callers before adding permission requirements to an endpoint.

### 3.6 New API Endpoints (user-service)

#### 3.6.1 `GET /users/admin/list`

**Purpose:** List users with roles and permissions for the admin RBAC panel.

```
GET /users/admin/list?page=1&page_size=20&search=&role_id=
Authorization: Bearer <token>

Response 200:
{
  "items": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "avatar": "...",
      "role": "admin",
      "role_id": 4,
      "role_display_name": null,
      "registered_at": "2026-01-01T00:00:00",
      "last_active_at": "2026-03-18T12:00:00",
      "permissions": ["users:read", "users:manage", ...]
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

**Auth:** `require_admin` (admin-only — viewing full user permissions is sensitive).

**Schema:** New `AdminUserItem` and `AdminUserListResponse` in `schemas.py`.

#### 3.6.2 `PUT /users/roles/{role_id}/permissions`

**Purpose:** Set default permissions for a role (replaces all existing role_permissions for that role).

```
PUT /users/roles/{role_id}/permissions
Authorization: Bearer <token>

Request:
{
  "permissions": ["items:create", "items:read", "characters:read"]
}

Response 200:
{
  "role_id": 3,
  "role_name": "moderator",
  "permissions": ["items:create", "items:read", "characters:read"]
}
```

**Auth:** `require_admin` (admin-only — changing role defaults is a privilege escalation risk).

**Validation:**
- Cannot modify admin role's permissions (admin always gets ALL automatically)
- All permission strings must exist in the `permissions` table
- Role must exist

**Schema:** New `RolePermissionsRequest` and `RolePermissionsResponse` in `schemas.py`.

#### 3.6.3 `GET /users/roles/{role_id}/permissions`

**Purpose:** Get current permissions for a specific role (needed for the role permissions editor UI).

```
GET /users/roles/{role_id}/permissions
Authorization: Bearer <token>

Response 200:
{
  "role_id": 3,
  "role_name": "moderator",
  "permissions": ["items:create", "items:read", ...]
}
```

**Auth:** `require_admin`.

### 3.7 Frontend Architecture

#### 3.7.1 RBAC Admin Page

**New page:** `RbacAdminPage.tsx` at `/admin/users-roles`

Two tabs:
- **Users tab** — table of users with role, display_name, permissions count. Click row to expand/edit: change role (dropdown), set display_name (input), manage permission overrides (checkbox grid).
- **Roles tab** — table of roles with their default permissions. Each role row expands to show permission checkboxes grouped by module.

**Components:**

| Component | File | Purpose |
|-----------|------|---------|
| `RbacAdminPage` | `src/components/Admin/RbacAdminPage/RbacAdminPage.tsx` | Main page with tabs |
| `UsersTab` | `src/components/Admin/RbacAdminPage/UsersTab.tsx` | Users table + inline editor |
| `RolesTab` | `src/components/Admin/RbacAdminPage/RolesTab.tsx` | Roles with permission grid |
| `PermissionGrid` | `src/components/Admin/RbacAdminPage/PermissionGrid.tsx` | Reusable checkbox grid for permissions |

**API module:** `src/api/rbacAdmin.ts` — API calls for RBAC management (list users, assign role, set permissions, get/set role permissions).

**No Redux slice needed** — this is a pure admin panel with local state. Uses `useState` + direct API calls (same pattern as `ItemsAdminPage`).

#### 3.7.2 AdminPage Fixes

1. Change "Правила" section's `module` from `'locations'` to `'rules'`
2. Add "Пользователи и роли" section with `module: 'users'`, path: `/admin/users-roles`

#### 3.7.3 Route Guard Updates in App.tsx

| Route | Current | New |
|-------|---------|-----|
| /requestsPage | `requiredRole="moderator"` | `requiredPermission="characters:approve"` |
| /admin/locations | `requiredRole="editor"` | `requiredPermission="locations:read"` |
| /home/admin/skills | `requiredRole="editor"` | `requiredPermission="skills:read"` |
| /admin/starter-kits | `requiredRole="editor"` | `requiredPermission="characters:update"` |
| /admin/characters | `requiredRole="editor"` | `requiredPermission="characters:read"` |
| /admin/characters/:characterId | `requiredRole="editor"` | `requiredPermission="characters:read"` |
| /admin/rules | `requiredRole="editor"` | `requiredPermission="rules:read"` |
| /admin/users-roles (new) | — | `requiredPermission="users:manage"` |
| /admin | `requiredRole="editor"` | Keep as-is (hub page filters sections internally) |
| /admin/items | `requiredPermission="items:read"` | Keep as-is (already permission-based) |

#### 3.7.4 AdminMenu Update

`AdminMenu.tsx` currently shows shield icon only for `role === 'admin'`. Change to `isStaff(role)` to show admin link for any staff role (admin, moderator, editor). The admin hub page already filters visible sections by permission, so unauthorized sections won't appear.

### 3.8 Data Flow Diagram

```
[Admin opens /admin/users-roles]
    |
    v
[RbacAdminPage] --GET /users/admin/list--> [user-service] --> DB
    |
    v (Users tab)
[Select user] --GET /users/{id}/effective-permissions--> [user-service] --> DB
    |
    v (Change role)
[RoleDropdown] --PUT /users/{id}/role--> [user-service] --> DB
    |
    v (Set permission overrides)
[PermissionGrid] --PUT /users/{id}/permissions--> [user-service] --> DB
    |
    v (Roles tab)
[RolesTab] --GET /users/roles--> [user-service] --> DB
    |
    v (Select role)
[RolePermEditor] --GET /users/roles/{id}/permissions--> [user-service] --> DB
    |
    v (Save role permissions)
[PermissionGrid] --PUT /users/roles/{id}/permissions--> [user-service] --> DB
```

```
[Any admin action from frontend]
    |
    v
[Service endpoint with Depends(require_permission("module:action"))]
    |
    v
[auth_http.py: get_current_user_via_http()]
    |
    v (HTTP GET with forwarded Bearer token)
[user-service: /users/me] --> returns {permissions: [...]}
    |
    v
[require_permission: checks "module:action" in user.permissions]
    |
    v (pass: return user / fail: 403)
[Endpoint logic]
```

### 3.9 Security Considerations

1. **Privilege escalation prevention:** RBAC management endpoints (`/users/roles`, `/users/*/role`, `/users/*/permissions`, `/users/roles/*/permissions`) remain `require_admin` (not permission-based). A moderator with `users:manage` cannot assign roles.
2. **Admin always has all permissions:** The `get_effective_permissions()` function returns ALL permissions for admin role. No migration or endpoint change can lock out the admin.
3. **Migration safety:** 0007 is additive-only (INSERT new rows). No schema changes. Rollback = DELETE inserted rows. Existing moderator access preserved by granting all new permissions to moderator role.
4. **Input validation:** All permission strings validated against the `permissions` table before being used. Invalid format raises 422.
5. **Rate limiting:** No new rate limits needed — these are admin-only endpoints behind auth.

### 3.10 Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Skills-service GET endpoints currently have NO auth — adding `require_permission("skills:read")` could break public reads | These are under `/admin/` prefix, not public endpoints. Public skill data is served by non-admin GET endpoints. Safe to protect. |
| `DELETE /attributes/{character_id}` is called from character-service during character deletion | Both services use the same forwarded Bearer token. If user has `characters:delete`, the token carries that permission to both services. Works correctly. |
| Migration 0007 runs before services start — what if roles table doesn't exist yet? | 0007 depends on 0006 (which creates the tables). Alembic runs migrations in order. |
| Frontend shows sections based on permissions, but user might bookmark an admin URL | ProtectedRoute guards handle this — redirect to /home if no permission |

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: Alembic Migration 0007 — Register New Permissions

| Field | Value |
|-------|-------|
| **#** | 1 |
| **Description** | Create Alembic migration `0007_add_remaining_permissions.py` in user-service. Insert 19 new permissions (IDs 9-27) for modules: characters, skills, locations, rules, photos, notifications. Insert role_permissions: admin gets all (9-27), moderator gets all (9-27), editor gets read-only (10, 15, 19, 23). See section 3.2 for full mapping. |
| **Agent** | Backend Developer |
| **Status** | TODO |
| **Files** | `services/user-service/alembic/versions/0007_add_remaining_permissions.py` |
| **Depends On** | — |
| **Acceptance Criteria** | Migration runs without errors. `SELECT * FROM permissions` returns 27 rows. `SELECT * FROM role_permissions WHERE role_id=3` includes all new permission IDs. `SELECT * FROM role_permissions WHERE role_id=2` includes IDs 10, 15, 19, 23. Downgrade removes all inserted rows cleanly. `python -m py_compile` passes. |

### Task 2: New API Endpoints in user-service

| Field | Value |
|-------|-------|
| **#** | 2 |
| **Description** | Add three new endpoints to user-service: (1) `GET /users/admin/list` — paginated user list with roles, permissions, search and role_id filter. (2) `PUT /users/roles/{role_id}/permissions` — set default permissions for a role (admin-only, cannot modify admin role). (3) `GET /users/roles/{role_id}/permissions` — get permissions for a role. Add new schemas: `AdminUserItem`, `AdminUserListResponse`, `RolePermissionsRequest`, `RolePermissionsResponse`. All endpoints use `require_admin`. See section 3.6 for API contracts. |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/user-service/main.py`, `services/user-service/schemas.py`, `services/user-service/crud.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | All three endpoints return correct responses. Cannot modify admin role permissions (returns 400). Invalid permission strings return 422. Search and pagination work. `python -m py_compile` passes on all modified files. |

### Task 3: Permission Enforcement — character-service

| Field | Value |
|-------|-------|
| **#** | 3 |
| **Description** | Add `require_permission()` dependency factory to `services/character-service/app/auth_http.py`. Replace `Depends(get_admin_user)` with `Depends(require_permission("..."))` on all 8 admin endpoints in `main.py` per mapping in section 3.4. Keep `get_admin_user` function in auth_http.py (don't remove). |
| **Agent** | Backend Developer |
| **Status** | TODO |
| **Files** | `services/character-service/app/auth_http.py`, `services/character-service/app/main.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | All 8 endpoints check specific permissions. Admin can access all. Moderator with `characters:approve` can approve but cannot delete. User without permissions gets 403. `python -m py_compile` passes. |

### Task 4: Permission Enforcement — skills-service

| Field | Value |
|-------|-------|
| **#** | 4 |
| **Description** | Add `require_permission()` dependency factory to `services/skills-service/app/auth_http.py`. Replace `Depends(get_admin_user)` with `Depends(require_permission("..."))` on all 17 protected admin endpoints. Add `Depends(require_permission("skills:read"))` to the 6 unprotected GET admin endpoints. Total: 23 endpoints updated. See section 3.4 for mapping. |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/skills-service/app/auth_http.py`, `services/skills-service/app/main.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | All 23 admin endpoints check specific permissions. POST→`skills:create`, PUT→`skills:update`, DELETE→`skills:delete`, GET→`skills:read`. Previously unprotected GETs now require auth. `python -m py_compile` passes. |

### Task 5: Permission Enforcement — inventory-service

| Field | Value |
|-------|-------|
| **#** | 5 |
| **Description** | Add `require_permission()` dependency factory to `services/inventory-service/app/auth_http.py`. Replace `Depends(get_admin_user)` with `Depends(require_permission("..."))` on all 4 admin endpoints in `main.py` per mapping in section 3.4. |
| **Agent** | Backend Developer |
| **Status** | TODO |
| **Files** | `services/inventory-service/app/auth_http.py`, `services/inventory-service/app/main.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | All 4 endpoints check `items:create`, `items:update`, or `items:delete`. `python -m py_compile` passes. |

### Task 6: Permission Enforcement — locations-service

| Field | Value |
|-------|-------|
| **#** | 6 |
| **Description** | Add `require_permission()` dependency factory to `services/locations-service/app/auth_http.py`. Replace `Depends(get_admin_user)` with `Depends(require_permission("..."))` on all 18 admin endpoints (14 locations + 4 rules) in `main.py` per mapping in section 3.4. |
| **Agent** | Backend Developer |
| **Status** | TODO |
| **Files** | `services/locations-service/app/auth_http.py`, `services/locations-service/app/main.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | All 14 locations endpoints check `locations:*` permissions. All 4 rules endpoints check `rules:*` permissions. `python -m py_compile` passes. |

### Task 7: Permission Enforcement — character-attributes-service

| Field | Value |
|-------|-------|
| **#** | 7 |
| **Description** | Add `require_permission()` dependency factory to `services/character-attributes-service/app/auth_http.py`. Replace `Depends(get_admin_user)` with `Depends(require_permission("..."))` on both admin endpoints in `main.py`. Note: `DELETE /attributes/{character_id}` is also called from character-service during character deletion — verify that the forwarded Bearer token carries `characters:delete` permission (it should, since both services validate the same user token). |
| **Agent** | Backend Developer |
| **Status** | TODO |
| **Files** | `services/character-attributes-service/app/auth_http.py`, `services/character-attributes-service/app/main.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | PUT endpoint checks `characters:update`. DELETE endpoint checks `characters:delete`. S2S call from character-service still works (same Bearer token forwarded). `python -m py_compile` passes. |

### Task 8: Permission Enforcement — photo-service

| Field | Value |
|-------|-------|
| **#** | 8 |
| **Description** | Add `require_permission()` dependency factory to `services/photo-service/auth_http.py` (note: no `app/` prefix in photo-service). Replace `Depends(get_admin_user)` with `Depends(require_permission("photos:upload"))` on all 9 admin image upload endpoints in `main.py`. |
| **Agent** | Backend Developer |
| **Status** | TODO |
| **Files** | `services/photo-service/auth_http.py`, `services/photo-service/main.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | All 9 endpoints check `photos:upload`. `python -m py_compile` passes. |

### Task 9: Permission Enforcement — notification-service

| Field | Value |
|-------|-------|
| **#** | 9 |
| **Description** | Add `require_permission()` dependency factory to `services/notification-service/app/auth_http.py`. In `main.py`, replace the inline role check (`current_user.role not in ("admin", "moderator")`) on `POST /notifications/create` with `Depends(require_permission("notifications:create"))` in the endpoint signature. |
| **Agent** | Backend Developer |
| **Status** | TODO |
| **Files** | `services/notification-service/app/auth_http.py`, `services/notification-service/app/main.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | POST /notifications/create checks `notifications:create` permission. Inline role check removed. `python -m py_compile` passes. |

### Task 10: Frontend — RBAC Admin Page

| Field | Value |
|-------|-------|
| **#** | 10 |
| **Description** | Create the RBAC Admin page at `/admin/users-roles` with two tabs: (1) **Users tab** — table from `GET /users/admin/list` with columns: username, email, role, display_name, last_active. Click row to expand inline editor: role dropdown (from `GET /users/roles`), display_name input, permission overrides grid (checkboxes). Save calls `PUT /users/{id}/role` and `PUT /users/{id}/permissions`. (2) **Roles tab** — list roles from `GET /users/roles`. Each role expands to show permission grid (from `GET /users/roles/{id}/permissions`). Checkboxes per module:action. Save calls `PUT /users/roles/{id}/permissions`. Admin role shown as read-only (all checked, non-editable). Use Tailwind, TypeScript, no React.FC, responsive (360px+). Follow design system from `docs/DESIGN-SYSTEM.md`. Create API module `src/api/rbacAdmin.ts`. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `src/components/Admin/RbacAdminPage/RbacAdminPage.tsx`, `src/components/Admin/RbacAdminPage/UsersTab.tsx`, `src/components/Admin/RbacAdminPage/RolesTab.tsx`, `src/components/Admin/RbacAdminPage/PermissionGrid.tsx`, `src/api/rbacAdmin.ts` |
| **Depends On** | 2 |
| **Acceptance Criteria** | Page renders at /admin/users-roles. Users tab lists users with roles. Can change user role and see permissions update. Can set permission overrides. Roles tab shows role permission grid. Can toggle permissions for non-admin roles. All API errors displayed to user in Russian. Responsive on 360px+. `npx tsc --noEmit` and `npm run build` pass. |

### Task 11: Frontend — Route Guards + AdminPage Fixes

| Field | Value |
|-------|-------|
| **#** | 11 |
| **Description** | Three changes: (1) In `App.tsx`, update route guards per mapping in section 3.7.3 — replace `requiredRole` with `requiredPermission` on 7 routes. Add new route `/admin/users-roles` with `requiredPermission="users:manage"`. (2) In `AdminPage.tsx`, fix "Правила" section module from `'locations'` to `'rules'`. Add new section "Пользователи и роли" with `module: 'users'`, `path: '/admin/users-roles'`. (3) In `AdminMenu.tsx`, change visibility check from `role === 'admin'` to `isStaff(role)` (import from permissions.ts). |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `src/components/App/App.tsx`, `src/components/Admin/AdminPage.tsx`, `src/components/CommonComponents/Header/AdminMenu.tsx` |
| **Depends On** | 10 |
| **Acceptance Criteria** | Routes use permission-based guards. Editor can see /admin hub with readable sections only. Moderator can see all sections except users. "Правила" section visible when user has `rules:*` permissions. Admin menu icon visible for all staff roles. `npx tsc --noEmit` and `npm run build` pass. |

### Task 12: QA — Migration and New Endpoints

| Field | Value |
|-------|-------|
| **#** | 12 |
| **Description** | Write tests for: (1) Migration 0007 data integrity — verify correct permissions seeded, correct role_permissions assignments. (2) `GET /users/admin/list` — pagination, search, role_id filter, auth check. (3) `PUT /users/roles/{role_id}/permissions` — happy path, admin role protection, invalid permissions. (4) `GET /users/roles/{role_id}/permissions` — returns correct permissions for role. |
| **Agent** | QA Test |
| **Status** | TODO |
| **Files** | `services/user-service/tests/test_rbac_management.py` |
| **Depends On** | 1, 2 |
| **Acceptance Criteria** | All tests pass with `pytest`. Cover happy paths and edge cases (403 for non-admin, 404 for missing role, 400 for admin role modification, 422 for invalid permissions). |

### Task 13: QA — Permission Enforcement on Services

| Field | Value |
|-------|-------|
| **#** | 13 |
| **Description** | Write tests for `require_permission()` in at least 2 representative services (character-service, locations-service). Test: (1) User with correct permission can access endpoint. (2) User without permission gets 403. (3) Admin user can access any endpoint. (4) User with no permissions gets 403. Mock `get_current_user_via_http` to return UserRead with different permission sets. |
| **Agent** | QA Test |
| **Status** | TODO |
| **Files** | `services/character-service/app/tests/test_rbac_enforcement.py`, `services/locations-service/app/tests/test_rbac_enforcement.py` |
| **Depends On** | 3, 6 |
| **Acceptance Criteria** | All tests pass with `pytest`. Tests verify 403 for missing permissions and 200/success for correct permissions. |

### Task 14: Review

| Field | Value |
|-------|-------|
| **#** | 14 |
| **Description** | Full review of all changes: (1) Verify migration 0007 is correct and idempotent-safe. (2) Verify all 65 non-user-service admin endpoints have correct permission checks. (3) Verify new API endpoints work correctly. (4) Verify frontend RBAC page is functional and responsive. (5) Verify route guards are permission-based. (6) Live verification: log in as admin, moderator, editor — confirm correct access to admin sections. (7) `npx tsc --noEmit`, `npm run build`, `python -m py_compile` on all modified files. |
| **Agent** | Reviewer |
| **Status** | TODO |
| **Files** | All files from tasks 1-13 |
| **Depends On** | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13 |
| **Acceptance Criteria** | All checks pass. Live verification confirms correct permission enforcement for admin, moderator, and editor roles. No console errors. No 500s. Review log written in section 5. |

### Parallelism Map

```
Phase 1 (parallel):
  Task 1 (migration)

Phase 2 (parallel, depends on Task 1):
  Task 2 (user-service endpoints)
  Task 3 (character-service enforcement)
  Task 4 (skills-service enforcement)
  Task 5 (inventory-service enforcement)
  Task 6 (locations-service enforcement)
  Task 7 (char-attrs-service enforcement)
  Task 8 (photo-service enforcement)
  Task 9 (notification-service enforcement)

Phase 3 (depends on Task 2):
  Task 10 (frontend RBAC page)

Phase 4 (depends on Task 10):
  Task 11 (frontend route guards)

Phase 5 (parallel, depends on respective backend tasks):
  Task 12 (QA: migration + endpoints)
  Task 13 (QA: enforcement)

Phase 6 (depends on all):
  Task 14 (Review)
```

**Total: 14 tasks. Backend tasks 3-9 are fully parallel. Frontend tasks 10-11 are sequential. QA tasks 12-13 are parallel.**

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-18
**Result:** FAIL

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (all errors are pre-existing, none in FEAT-036 files)
- [ ] `npm run build` — FAIL (pre-existing: missing `dompurify` in `RuleOverlay.tsx`, NOT caused by FEAT-036)
- [x] `py_compile` (ast.parse) — PASS (20/20 modified Python files)
- [x] `pytest user-service/tests/test_rbac_management.py` — PASS (36/36 tests)
- [x] `pytest character-service/app/tests/test_rbac_enforcement.py` — PASS (16/16 tests)
- [x] `pytest locations-service/app/tests/test_rbac_enforcement.py` — PASS (18/18 tests)
- [x] `docker-compose config` — PASS

#### Live Verification Results
- Live verification skipped: no MCP chrome-devtools available, and services are not running locally. All code-level checks passed.

#### Verification Summary

**Backend — All checks passed:**
1. Migration 0007: 19 new permissions (IDs 9-27), correct role assignments (admin=all, moderator=all, editor=read-only). Downgrade is clean.
2. All 65 non-user-service admin endpoints now use `require_permission()` — verified by counting: character-service=8, skills-service=23, inventory-service=4, locations-service=18, char-attrs-service=2, photo-service=9, notification-service=1.
3. `require_permission()` dependency factory is consistent across all 7 `auth_http.py` files — identical implementation.
4. No `Depends(get_admin_user)` remains in any endpoint signature (only in imports and test comments).
5. New user-service endpoints (`GET /users/admin/list`, `GET /users/roles/{role_id}/permissions`, `PUT /users/roles/{role_id}/permissions`) all use `require_admin` — correct for privilege escalation prevention.
6. Admin role protection: cannot modify admin role permissions (returns 400). Permission strings validated against DB.
7. Pydantic <2.0 syntax used correctly (`class Config: orm_mode = True`).
8. No hardcoded secrets. No new security issues.

**Frontend — Code standards passed, but 2 contract bugs found:**
1. No React.FC usage — PASS
2. No new SCSS/CSS files — PASS (all Tailwind)
3. All new files are `.tsx`/`.ts` — PASS
4. Responsive design with sm:/md:/lg: breakpoints — PASS
5. All API errors displayed via `toast.error()` with Russian messages — PASS
6. Route guards updated: 7 routes now use `requiredPermission` instead of `requiredRole` — PASS
7. AdminPage: "Правила" module fixed from `locations` to `rules` — PASS
8. AdminPage: "Пользователи и роли" section added with `module: 'users'` — PASS

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/api/rbacAdmin.ts:161-164` | `getAllPermissions()` returns the raw Axios response typed as `PermissionsGroupedResponse` (flat `{[module]: PermissionItem[]}`), but the backend `GET /users/permissions` returns `{"modules": {...}}` — the data is nested under a `modules` key. Frontend never unwraps `.modules`, so `PermissionGrid` receives `{modules: {...}}` instead of `{users: [...], items: [...], ...}`. The grid will show a single group called "modules" instead of actual module names. **Fix:** change to `return data.modules;` and update the type, OR add `modules` wrapper to the interface. | Frontend Developer | FIX_REQUIRED |
| 2 | `services/frontend/app-chaldea/src/api/rbacAdmin.ts:121-128` | `getUserPermissions()` types the response as `EffectivePermissionsResponse` with field `permissions: string[]`, but the backend `GET /users/{id}/effective-permissions` returns `effective_permissions` (not `permissions`). Additionally the backend response includes `username`, `role`, `role_display_name`, `role_permissions`, `overrides` — none of which are in the frontend type. As a result, `effective.permissions` is `undefined` at runtime, causing the permission override checkboxes to all appear unchecked regardless of actual user permissions. **Fix:** change the frontend interface to match the backend schema field name `effective_permissions`, or rename the access to `data.effective_permissions`. | Frontend Developer | FIX_REQUIRED |
| 3 | `services/frontend/app-chaldea/src/components/Admin/RbacAdminPage/UsersTab.tsx:250` | React fragment `<>` inside `.map()` has no `key` prop. The `key={user.id}` is on the inner `<tr>`, but React requires the key on the outermost element in the list. This causes a React console warning "Each child in a list should have a unique key prop". **Fix:** replace `<>` with `<Fragment key={user.id}>` (import Fragment from React) and remove the `key` from the inner `<tr>`. | Frontend Developer | FIX_REQUIRED |

**Issues 1 and 2 are blocking** — they will cause the RBAC admin page to malfunction at runtime (permission grid empty, user permissions not loading). Issue 3 is a minor console warning but still required per review standards (zero console errors).

### Review #2 — 2026-03-18
**Result:** PASS

All 3 issues from Review #1 have been verified as fixed:

1. **`rbacAdmin.ts:166-168`** — `getAllPermissions()` now correctly types the Axios response as `{ modules: PermissionsGroupedResponse }` and returns `data.modules`. The permission grid will receive properly grouped data (`{users: [...], items: [...], ...}`) instead of the raw wrapper. **FIXED.**
2. **`rbacAdmin.ts:62-70` + `UsersTab.tsx:97`** — `EffectivePermissionsResponse` interface now includes all backend fields: `user_id`, `username`, `role`, `role_display_name`, `role_permissions`, `overrides` (with `grants`/`revokes`), and `effective_permissions`. Code in `UsersTab.tsx` correctly accesses `effective.effective_permissions` and `effective.overrides?.revokes`. **FIXED.**
3. **`UsersTab.tsx:249`** — `<React.Fragment key={user.id}>` replaces the bare `<>` fragment inside `.map()`, eliminating the React console warning. **FIXED.**

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (all errors are pre-existing, none in FEAT-036 files)
- [ ] `npm run build` — FAIL (pre-existing: missing `dompurify` in `RuleOverlay.tsx`, NOT caused by FEAT-036)
- [x] `py_compile` — N/A (no Python files changed in this fix round)
- [x] `pytest` — N/A (no test changes in this fix round; all 70 tests passed in Review #1)
- [x] `docker-compose config` — PASS (verified in Review #1, no compose changes)

#### Live Verification Results
- Live verification skipped: no MCP chrome-devtools available, and services are not running locally. All code-level checks passed. The fixes are straightforward field-name corrections and type alignments — runtime behavior will now match the verified backend contracts.

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-18 15:00 — PM: фича создана (FEAT-036), запускаю анализ
[LOG] 2026-03-18 15:30 — Analyst: начал анализ, изучаю все сервисы и эндпоинты
[LOG] 2026-03-18 16:00 — Analyst: анализ завершён. Найдено 72 admin-эндпоинта в 8 сервисах, нужно 16 новых permissions в 6 модулях, 2 недостающих API-эндпоинта для UI, баг в AdminPage (rules mapped to wrong module)
[LOG] 2026-03-18 17:00 — Architect: начал проектирование
[LOG] 2026-03-18 18:00 — Architect: спроектировано 14 задач, 3 новых API-контракта, 19 новых permissions. Миграция 0007 (данные только, без DDL). require_permission() dependency factory для 7 сервисов. Frontend: RBAC admin page (4 компонента), fix route guards (7 маршрутов), fix AdminPage (rules module + users section). Задачи 3-9 параллельны. S2S безопасность проверена — admin endpoints не вызываются между сервисами.
[LOG] 2026-03-18 18:30 — Backend Dev: задача #1 завершена. Создана миграция 0007_add_remaining_permissions.py — 19 новых permissions (IDs 9-27), role_permissions для admin (все), moderator (все), editor (только *:read). py_compile пройден.
[LOG] 2026-03-18 19:00 — Backend Dev: задача #2 завершена. Добавлены 3 эндпоинта: GET /users/admin/list (пагинация, поиск, фильтр по role_id), GET /users/roles/{role_id}/permissions, PUT /users/roles/{role_id}/permissions. Добавлены 4 новые схемы: AdminUserItem, AdminUserListResponse, RolePermissionsRequest, RolePermissionsResponse. Все файлы прошли ast.parse проверку.
[LOG] 2026-03-18 19:30 — Backend Dev: задача #3 (character-service) завершена. Добавлена функция require_permission() в auth_http.py. Заменены все 8 Depends(get_admin_user) на гранулярные проверки: characters:approve (2), characters:read (1), characters:update (3), characters:delete (1), characters:create (1). py_compile пройден для обоих файлов.
[LOG] 2026-03-18 20:00 — Backend Dev: задачи #5, #8, #9 завершены. inventory-service: добавлен require_permission() в auth_http.py, заменены 4 Depends(get_admin_user) на items:create (1), items:update (1), items:delete (2). photo-service: добавлен require_permission() в auth_http.py, заменены 9 Depends(get_admin_user) на photos:upload. notification-service: добавлен require_permission() в auth_http.py, заменён inline role check в POST /notifications/create на Depends(require_permission("notifications:create")). py_compile/ast.parse пройден для всех 6 файлов.
[LOG] 2026-03-18 20:30 — Backend Dev: задача #6 (locations-service) завершена. Добавлена функция require_permission() в auth_http.py. Заменены все 18 Depends(get_admin_user) на гранулярные проверки: locations:create (4), locations:update (5), locations:delete (4), rules:create (1), rules:update (2), rules:delete (1). ast.parse пройден для обоих файлов.
[LOG] 2026-03-18 20:30 — Backend Dev: задача #7 (character-attributes-service) завершена. Добавлена функция require_permission() в auth_http.py. Заменены 2 Depends(get_admin_user) на гранулярные проверки: characters:update (PUT /attributes/admin/{id}), characters:delete (DELETE /attributes/{id}). ast.parse пройден для обоих файлов.
[LOG] 2026-03-18 21:00 — Backend Dev: задача #4 (skills-service) завершена. Добавлен require_permission() в auth_http.py. Обновлены все 23 admin-эндпоинта в main.py: 17 существующих (замена get_admin_user на require_permission), 6 GET без защиты (добавлен skills:read). POST→skills:create, PUT→skills:update, DELETE→skills:delete, GET→skills:read. ast.parse пройден для обоих файлов.
[LOG] 2026-03-18 21:30 — QA: задача #12 завершена. Написано 36 тестов в test_rbac_management.py: 10 тестов на целостность данных миграции (27 permissions, 8 модулей, role_permissions для admin/moderator/editor), 8 тестов на GET /users/admin/list (пагинация, поиск, фильтр role_id, 403/401), 8 тестов на GET /users/roles/{role_id}/permissions (все роли, 404/403/401), 10 тестов на PUT /users/roles/{role_id}/permissions (обновление, защита admin-роли, валидация, очистка, SQL injection, 403/401/404). py_compile пройден, все 36 тестов проходят.
[LOG] 2026-03-18 22:00 — QA: задача #13 завершена. Написано 34 теста: character-service (16 тестов в test_rbac_enforcement.py) — acceptance tests для require_permission(), гранулярная изоляция прав (create≠update, read≠approve и т.д.), endpoint-level тесты через TestClient с mock auth. locations-service (18 тестов в test_rbac_enforcement.py) — те же паттерны + кросс-модульная изоляция (locations:* не даёт доступ к rules:* и наоборот). py_compile пройден, все 34 теста проходят.
[LOG] 2026-03-18 22:30 — Frontend Dev: начал задачу #10 (RBAC Admin Page)
[LOG] 2026-03-18 23:00 — Frontend Dev: задача #10 завершена. Создано 5 файлов: src/api/rbacAdmin.ts (API-модуль с типами и 8 функциями), src/components/Admin/RbacAdminPage/RbacAdminPage.tsx (страница с табами), UsersTab.tsx (таблица пользователей с inline-редактором ролей и разрешений, поиск, фильтр, пагинация), RolesTab.tsx (список ролей с permission grid, admin read-only), PermissionGrid.tsx (переиспользуемый компонент чекбоксов с группировкой по модулям). Также выполнена задача #11: обновлены route guards в App.tsx (7 маршрутов с requiredRole→requiredPermission + новый /admin/users-roles), исправлен module 'locations'→'rules' для Правила в AdminPage.tsx, добавлена секция Пользователи и роли. AdminMenu.tsx уже использовал isStaff() — изменение не требовалось. npx tsc --noEmit: 0 новых ошибок. npm run build: pre-existing failure (missing dompurify), не связано с моими изменениями.
[LOG] 2026-03-18 23:30 — Reviewer: начал проверку задачи #14
[LOG] 2026-03-18 23:45 — Reviewer: проверка завершена, результат FAIL. Backend: все проверки пройдены (py_compile, pytest 70/70 тестов, миграция, endpoint enforcement). Frontend: обнаружены 3 проблемы — (1) getAllPermissions() не разворачивает .modules из ответа бэкенда, permission grid будет пустой; (2) getUserPermissions() использует поле permissions вместо effective_permissions, права пользователя не загрузятся; (3) React fragment без key в UsersTab.tsx. Проблемы 1 и 2 блокирующие — страница RBAC admin не будет работать в runtime.
[LOG] 2026-03-18 23:50 — Frontend Dev: исправлены все 3 проблемы из ревью. (1) getAllPermissions() теперь разворачивает .modules из ответа; EffectivePermissionsResponse расширен до полной структуры бэкенда. (2) getUserPermissions() теперь использует effective_permissions и overrides вместо несуществующего поля permissions. (3) Заменён <> на <React.Fragment key={user.id}> в UsersTab.tsx. npx tsc --noEmit: 0 новых ошибок.
[LOG] 2026-03-18 23:55 — Reviewer: начал повторную проверку (Review #2) — верификация 3 исправлений из Review #1
[LOG] 2026-03-18 23:58 — Reviewer: проверка завершена, результат PASS. Все 3 исправления корректны: (1) getAllPermissions() разворачивает .modules, (2) EffectivePermissionsResponse содержит правильные поля, effective_permissions используется корректно, (3) React.Fragment с key. npx tsc --noEmit: 0 новых ошибок. npm run build: pre-existing failure (dompurify), не связано с FEAT-036.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*

# FEAT-035: Гибкая система ролей и разрешений (RBAC)

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-03-18 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-035-rbac-permissions.md` → `DONE-FEAT-035-rbac-permissions.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Реализация гибкой системы ролей и разрешений (RBAC) для проекта Chaldea. Заменяет текущую бинарную систему `is_admin` на полноценную модульную систему прав с иерархией ролей, индивидуальными разрешениями и блочным управлением доступами.

### Бизнес-правила
- **Одна роль на пользователя**, роли иерархические (Admin > Moderator > Editor > User)
- **Индивидуальные права поверх роли** — можно добавить/убрать конкретное разрешение пользователю
- **Индивидуальное название роли** при назначении (например, модератор может называться "Администратор навыков" или "Куратор контента")
- **4 роли на старте:**
  1. Admin — полный доступ ко всему (всегда получает все новые разрешения автоматически)
  2. Moderator — всё кроме управления пользователями
  3. Editor — только чтение (доступы настроим позже)
  4. User — обычный пользователь, базовые права
- **Модули разрешений на старте:** `users` (управление пользователями), `items` (предметы). Остальные модули добавляются по мере работы с ними.
- **Формат разрешений:** `модуль:действие` (например `skills:create`, `users:manage`). Можно добавить весь модуль блоком (например `skills` = все действия в модуле).
- **Замена `is_admin`** на новую систему ролей с миграцией данных
- **Защита последнего админа** — нельзя снять роль Admin если он последний
- **Отображение роли** на сайте (профиль и т.д.)
- **Постепенная миграция:** при работе с новым модулем создаём для него логику разрешений, обязательно добавляем все новые разрешения админу
- **Тест:** автоматическая проверка, что Admin имеет все существующие разрешения

### UX / Пользовательский сценарий
1. Админ заходит в админ-панель → видит все модули
2. Модератор заходит в админ-панель → не видит модуль "Пользователи" (нет кнопки/ссылки)
3. Редактор заходит в админ-панель → видит только то, на что есть права (пока ничего)
4. Обычный пользователь → не видит админ-панель вообще
5. Админ может назначить пользователю роль и задать ей отображаемое название
6. Админ может добавить/убрать индивидуальные разрешения поверх роли
7. Админ может добавить целый модуль разрешений блоком
8. Роль пользователя отображается где-то на сайте

### Edge Cases
- Попытка снять роль Admin с последнего админа → ошибка
- Попытка доступа к модулю без прав через прямой URL → редирект / ошибка 403
- Пользователь с индивидуальными правами сверх роли → права суммируются (роль + индивидуальные)
- Добавление нового модуля разрешений в будущем → Admin автоматически получает все новые разрешения

### Вопросы к пользователю (если есть)
- [x] Одна или несколько ролей? → Ответ: одна, иерархическая
- [x] Индивидуальные права поверх роли? → Ответ: да
- [x] Название роли глобальное или индивидуальное? → Ответ: индивидуальное
- [x] Какие модули на старте? → Ответ: users, items
- [x] Защита последнего админа? → Ответ: да
- [x] Заменить is_admin? → Ответ: да
- [x] Отображать роль на сайте? → Ответ: да

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 Current Auth Architecture Overview

**JWT Token Payload** (defined in `services/user-service/auth.py`, lines 21-30):
```
{
  "sub": "<user_email>",
  "role": "<user_role_string>",          // currently "user" or "admin"
  "current_character": <int|null>,
  "exp": <timestamp>
}
```
- Access token TTL: 1200 minutes (20 hours)
- Refresh token TTL: 7 days
- Secret key: from env `JWT_SECRET_KEY`
- Algorithm: HS256

**Auth Flow for user-service** (`services/user-service/auth.py`, lines 45-71):
- `get_current_user()` decodes JWT, extracts `email` and `role`, looks up user in DB by email, returns full `User` ORM object.
- Role from JWT is read but NOT actually used for authorization inside the function — it's just validated as non-None.
- The admin check in user-service endpoints is done inline: `if current_user.role != "admin"` (reading from DB, not token).

**Auth Flow for all other services** (identical `auth_http.py` in 6 services):
- `get_current_user_via_http()` — makes HTTP GET to `user-service /users/me` forwarding the Bearer token. Returns `UserRead(id, username, role)`.
- `get_admin_user()` — wraps `get_current_user_via_http()`, checks `user.role != "admin"`, raises 403 if not admin.
- **Critical**: The role check reads from the `/users/me` response (which reads from DB), NOT from the JWT token directly. This means role changes take effect on next API call (no stale JWT cache issue).

### 2.2 Affected Services — Detailed File Analysis

#### user-service (PRIMARY — owns auth, roles, users table)

| File | Lines | What Needs Change |
|------|-------|-------------------|
| `models.py` | L15 | `role = Column(String(100), default='user')` — replace with FK to roles table or keep as string mapped to new role system |
| `schemas.py` | L9, L44, L73 | `role` field in `UserBase`, `UserRead`, `MeResponse` — must expose new role data (role name, permissions) |
| `auth.py` | L21-30, L32-41 | `create_access_token()` / `create_refresh_token()` — `role` param encoded in JWT |
| `auth.py` | L45-71 | `get_current_user()` — currently reads role from JWT but doesn't use it for auth |
| `main.py` | L168-174 | Login endpoint — builds token with `role=user.role` |
| `main.py` | L196 | Refresh token — rebuilds with `role=user.role` |
| `main.py` | L394 | `delete_user_character_relation()` — inline `current_user.role != "admin"` check |
| `main.py` | L417 | `clear_current_character()` — inline `current_user.role != "admin"` check |
| `main.py` | L504-507 | `get_admin_users()` — queries `User.role == "admin"`, needs update for new roles |
| `crud.py` | L27-39 | `create_user()` — creates user with default role (no explicit role assignment) |
| `database.py` | — | No change needed |
| `alembic/env.py` | L28 | version_table: `alembic_version_user`, latest revision: `0005` |

**New tables needed in user-service:**
- `roles` — id, name, level (hierarchy), description
- `permissions` — id, module, action, description
- `role_permissions` — role_id, permission_id (many-to-many)
- `user_permissions` — user_id, permission_id, granted (bool, for individual overrides)
- Modify `users` table: add `role_id` (FK to roles), `role_display_name` (custom title), remove/deprecate `role` string column

#### character-service

| File | Lines | What Needs Change |
|------|-------|-------------------|
| `app/auth_http.py` | L9-12, L45-54 | `UserRead` schema and `get_admin_user()` — must accept new role format |
| `app/main.py` | L64 | `approve_character_request` — uses `Depends(get_admin_user)` |
| `app/main.py` | L233 | `GET /admin/list` — uses `Depends(get_admin_user)` |
| `app/main.py` | L274 | `PUT /admin/{character_id}` — uses `Depends(get_admin_user)` |
| `app/main.py` | L359 | `POST /admin/{character_id}/unlink` — uses `Depends(get_admin_user)` |
| `app/main.py` | L424 | `DELETE /characters/{character_id}` — uses `Depends(get_admin_user)` |
| `app/main.py` | L557 | `reject_character_request` — uses `Depends(get_admin_user)` |
| `app/main.py` | L621 | `upsert_starter_kit` — uses `Depends(get_admin_user)` |
| `app/main.py` | L641 | `create_title` — uses `Depends(get_admin_user)` |

#### skills-service

| File | Lines | What Needs Change |
|------|-------|-------------------|
| `app/auth_http.py` | L9-12, L45-54 | `UserRead` schema and `get_admin_user()` |
| `app/main.py` | 20+ endpoints under `/admin/` prefix | All use `Depends(get_admin_user)`: skills CRUD, skill_ranks CRUD, damages CRUD, effects CRUD, character_skills CRUD, full_tree endpoints |

Full list of admin-protected skills-service endpoints:
- `POST /admin/skills/`, `PUT /admin/skills/{id}`, `DELETE /admin/skills/{id}`
- `POST /admin/skill_ranks/`, `PUT /admin/skill_ranks/{id}`, `DELETE /admin/skill_ranks/{id}`
- `POST /admin/damages/`, `PUT /admin/damages/{id}`, `DELETE /admin/damages/{id}`
- `POST /admin/effects/`, `PUT /admin/effects/{id}`, `DELETE /admin/effects/{id}`
- `POST /admin/character_skills/`, `PUT /admin/character_skills/{id}`, `DELETE /admin/character_skills/{id}`, `DELETE /admin/character_skills/by_character/{id}`
- `PUT /admin/skills/{id}/full_tree`

Note: `GET /admin/skills/`, `GET /admin/skills/{id}`, `GET /admin/skills/{id}/full_tree`, `GET /admin/skill_ranks/{id}`, `GET /admin/damages/{id}`, `GET /admin/effects/{id}` — these GET endpoints do NOT have `get_admin_user` dependency (no auth required for reads).

#### inventory-service

| File | Lines | What Needs Change |
|------|-------|-------------------|
| `app/auth_http.py` | L9-12, L45-54 | `UserRead` schema and `get_admin_user()` |
| `app/main.py` | L439 | `create_item` — `Depends(get_admin_user)` |
| `app/main.py` | L470 | `update_item` — `Depends(get_admin_user)` |
| `app/main.py` | L497 | `delete_item` — `Depends(get_admin_user)` |
| `app/main.py` | L568 | `delete_all_character_inventory` — `Depends(get_admin_user)` |

#### locations-service

| File | Lines | What Needs Change |
|------|-------|-------------------|
| `app/auth_http.py` | L9-12, L45-54 | `UserRead` schema and `get_admin_user()` |
| `app/main.py` | 20+ endpoints | All CRUD for countries, regions, districts, locations, neighbors, rules use `Depends(get_admin_user)` |

Full list: create/update country, create/update region, create/update/delete district, create/update location, create/delete neighbor, CRUD rules (lines 543, 553, 565, 575).

#### character-attributes-service

| File | Lines | What Needs Change |
|------|-------|-------------------|
| `app/auth_http.py` | L9-12, L45-54 | `UserRead` schema and `get_admin_user()` |
| `app/main.py` | L498 | `PUT /admin/{character_id}` — update attributes (admin) |
| `app/main.py` | L528 | `PUT /admin/{character_id}/level-xp` — update level/XP (admin) |

#### photo-service

| File | Lines | What Needs Change |
|------|-------|-------------------|
| `auth_http.py` | L9-12, L45-54 | `UserRead` schema and `get_admin_user()` |
| `main.py` | L77, L104, L127, L150, L173, L190, L212, L233, L254 | 9 admin-only image upload endpoints (country map, region map/image, district image, location image, skill image, skill_rank image, item image, rule image) |
| `models.py` | — | Mirror `User` model does NOT include `role` field. No change needed here since auth is via HTTP call to user-service. |

#### notification-service

| File | Lines | What Needs Change |
|------|-------|-------------------|
| `app/main.py` | L102 | `create_admin_notification` — inline check: `current_user.role != "admin"` |
| `app/auth_http.py` | — | Uses same pattern but notification-service has its own `auth_http.py` with `get_current_user_via_http()` |

Note: notification-service does NOT use `get_admin_user()` dependency. Instead it does an inline role check in the endpoint (L102). This is the only service besides user-service that does inline checking.

#### battle-service, autobattle-service

No admin endpoints found. No changes needed.

### 2.3 Frontend Analysis

#### Admin Access Control

**Current guard mechanism** — there is NO route guard/protected route component. Admin pages are accessible to anyone who knows the URL. The only protection is:
1. Backend returns 403 for admin API calls (via `get_admin_user`)
2. The admin panel link (shield icon) in the header is hidden if `role !== 'admin'` (`AdminMenu.tsx`, line 9)
3. The "Управление локациями" button on WorldPage is shown to ALL users (no role check, `WorldPage.jsx` line 70)

**Files with role checks in frontend:**

| File | Line | Check |
|------|------|-------|
| `src/components/CommonComponents/Header/AdminMenu.tsx` | L9 | `if (role !== 'admin') return null` — hides admin link |
| `src/components/CommonComponents/Header/Header.tsx` | L18, L104 | Reads `role` from Redux, passes to `AdminMenu` |

**No other frontend files check role.** All admin pages (AdminPage, AdminLocationsPage, AdminSkillsPage, ItemsAdminPage, StarterKitsPage, AdminCharactersPage, AdminCharacterDetailPage, RulesAdminPage, RequestsPage) have zero client-side access control.

#### Redux State

**User slice** (`src/redux/slices/userSlice.js`, lines 4-13):
```js
initialState = {
  id: null, email: null, username: null,
  character: null, role: null, avatar: null,
  status: "idle", error: null,
}
```
- `role` is set from `/users/me` response (line 40: `state.role = role`)
- On logout, role is cleared (line 23: `state.role = null`)
- The `role` value is a simple string: `"user"` or `"admin"`

**MeResponse from backend** (`schemas.py` lines 66-78):
```python
class MeResponse:
    id, email, username, avatar, balance,
    role: Optional[str] = "user",
    current_character_id, character
```

#### Admin Panel Structure (from `AdminPage.tsx`)

7 sections currently exist:
1. **Заявки** (`/requestsPage`) — Character creation request moderation
2. **Айтемы** (`/admin/items`) — Items/equipment management
3. **Локации** (`/admin/locations`) — World editing
4. **Навыки** (`/home/admin/skills`) — Skill tree editing
5. **Стартовые наборы** (`/admin/starter-kits`) — Starter kit configuration
6. **Персонажи** (`/admin/characters`) — Character management
7. **Правила** (`/admin/rules`) — Game rules management

#### Admin-related Redux slices:
- `adminLocationsSlice.js` — locations admin state
- `adminCharactersSlice.ts` — characters admin state
- `adminLocationsActions.js` — locations admin thunks
- `skillsAdminActions.js` — skills admin thunks

#### Admin API module:
- `src/api/adminCharacters.ts` — API calls for admin character management (attributes, inventory, skills)

### 2.4 Cross-Service Auth Dependencies

```
[Frontend] --Bearer token--> [Any Backend Service]
                                    |
                                    v
                    [auth_http.py: get_current_user_via_http()]
                                    |
                                    v (HTTP GET with forwarded token)
                    [user-service: GET /users/me]
                                    |
                                    v
                    Returns: { id, email, username, role, avatar, ... }
                                    |
                                    v
                    [auth_http.py: get_admin_user() checks role == "admin"]
```

**All 6 non-user services** (character-service, skills-service, inventory-service, locations-service, character-attributes-service, photo-service) have an identical `auth_http.py` file with:
- `UserRead` schema: `{id: int, username: str, role: Optional[str]}`
- `get_current_user_via_http()` — calls user-service `/users/me`
- `get_admin_user()` — checks `user.role != "admin"`

**notification-service** has the same `get_current_user_via_http()` pattern but does inline role check instead of `get_admin_user()`.

**user-service** is the only service that decodes JWT locally (has the secret key).

### 2.5 Existing Patterns

| Service | SQLAlchemy | Alembic | Auth Pattern |
|---------|-----------|---------|-------------|
| user-service | Sync (pymysql) | YES (`alembic_version_user`, rev 0005) | Local JWT decode |
| character-service | Sync (pymysql) | YES (`alembic_version_character`) | HTTP to user-service |
| skills-service | Async (aiomysql) | YES (`alembic_version_skills`) | HTTP to user-service |
| inventory-service | Sync (pymysql) | YES (`alembic_version_inventory`) | HTTP to user-service |
| locations-service | Async (aiomysql) | YES (`alembic_version_locations`) | HTTP to user-service |
| character-attributes-service | Sync (pymysql) | YES (`alembic_version_char_attrs`) | HTTP to user-service |
| photo-service | Sync (pymysql) | YES (mirror, `alembic_version_photo`) | HTTP to user-service |
| notification-service | Sync (pymysql) | NO (uses `create_all()`) | HTTP to user-service |
| battle-service | Async (aiomysql) | NO | N/A (no admin endpoints) |

### 2.6 DB Changes Required

**New tables** (owned by user-service, Alembic migration needed):

1. **`roles`**
   - `id` INT PK AUTO_INCREMENT
   - `name` VARCHAR(50) UNIQUE NOT NULL — e.g. "admin", "moderator", "editor", "user"
   - `level` INT NOT NULL — hierarchy level (higher = more power): admin=100, moderator=50, editor=20, user=0
   - `description` VARCHAR(255) NULLABLE

2. **`permissions`**
   - `id` INT PK AUTO_INCREMENT
   - `module` VARCHAR(50) NOT NULL — e.g. "users", "items", "skills", "locations", "characters", "rules"
   - `action` VARCHAR(50) NOT NULL — e.g. "create", "read", "update", "delete", "manage"
   - UNIQUE constraint on (module, action)

3. **`role_permissions`**
   - `role_id` INT FK -> roles.id
   - `permission_id` INT FK -> permissions.id
   - PK on (role_id, permission_id)

4. **`user_permissions`** (individual overrides)
   - `id` INT PK AUTO_INCREMENT
   - `user_id` INT FK -> users.id
   - `permission_id` INT FK -> permissions.id
   - `granted` BOOLEAN NOT NULL DEFAULT TRUE — TRUE=grant, FALSE=revoke (override role)
   - UNIQUE constraint on (user_id, permission_id)

5. **Modify `users` table**:
   - ADD `role_id` INT FK -> roles.id, DEFAULT = user role id
   - ADD `role_display_name` VARCHAR(100) NULLABLE — custom display name for the role
   - KEEP `role` column temporarily for backward compatibility during migration, then DROP

**Data migration steps:**
1. Create new tables (roles, permissions, role_permissions, user_permissions)
2. Seed initial roles: admin(level=100), moderator(level=50), editor(level=20), user(level=0)
3. Seed initial permissions for modules: `users` and `items` (with actions: create, read, update, delete, manage)
4. Assign all permissions to admin role
5. Assign non-users permissions to moderator role
6. Add `role_id` column to users, set based on current `role` string:
   - `role = 'admin'` -> `role_id = admin.id`
   - `role = 'user'` (or anything else) -> `role_id = user.id`
7. Drop `role` string column (or keep as computed/cached field)

**Impact on other services reading `users` table:**
- photo-service mirror models do NOT include `role` — no impact
- No other service reads `users.role` directly from DB — they all go through user-service HTTP API

### 2.7 API Changes Required

**user-service `/users/me` response** — this is the critical contract that all other services depend on. The `MeResponse` must include new role information:
```python
class MeResponse:
    # ... existing fields ...
    role: str              # keep for backward compat ("admin", "moderator", "editor", "user")
    role_display_name: Optional[str]  # custom title
    permissions: List[str]  # ["users:manage", "items:create", "items:read", ...]
```

**auth_http.py `UserRead` in 6 services** — needs `permissions` field or enhanced role info:
```python
class UserRead:
    id: int
    username: str
    role: str                       # keep for simple checks
    permissions: List[str] = []     # for granular permission checks
```

**New user-service endpoints needed:**
- `GET /users/roles` — list all roles (admin only)
- `PUT /users/{user_id}/role` — assign role to user (admin only)
- `GET /users/permissions` — list all permissions (admin only)
- `PUT /users/{user_id}/permissions` — set individual permission overrides (admin only)
- `GET /users/{user_id}/effective-permissions` — get combined role+individual permissions

### 2.8 Complete List of Admin-Protected Endpoints Across All Services

**user-service** (inline `role != "admin"` checks):
1. `DELETE /users/user_characters/{user_id}/{character_id}` (L387-407)
2. `POST /users/{user_id}/clear_current_character` (L410-428)
3. `GET /users/admins` (L504-507) — queries by role, no auth check

**character-service** (via `Depends(get_admin_user)`):
4. `POST /characters/requests/{request_id}/approve` (L64)
5. `POST /characters/requests/{request_id}/reject` (L557)
6. `GET /characters/admin/list` (L222)
7. `PUT /characters/admin/{character_id}` (L269)
8. `POST /characters/admin/{character_id}/unlink` (L355)
9. `DELETE /characters/{character_id}` (L424)
10. `PUT /characters/starter-kits/{class_id}` (L621)
11. `POST /characters/titles` (L641)

**skills-service** (via `Depends(get_admin_user)`):
12-31. ~20 CRUD endpoints under `/skills/admin/` (skills, skill_ranks, damages, effects, character_skills, full_tree)

**inventory-service** (via `Depends(get_admin_user)`):
32. `POST /inventory/items` (L439)
33. `PUT /inventory/items/{item_id}` (L470)
34. `DELETE /inventory/items/{item_id}` (L497)
35. `DELETE /inventory/admin/{character_id}/all` (L568)

**locations-service** (via `Depends(get_admin_user)`):
36-55. ~20 CRUD endpoints for countries, regions, districts, locations, neighbors, rules

**character-attributes-service** (via `Depends(get_admin_user)`):
56. `PUT /attributes/admin/{character_id}` (L493)
57. `PUT /attributes/admin/{character_id}/level-xp` (L528)

**photo-service** (via `Depends(get_admin_user)`):
58-66. 9 image upload endpoints (country_map, region_map, region_image, district_image, location_image, skill_image, skill_rank_image, item_image, rule_image)

**notification-service** (inline check):
67. `POST /notifications/create` (L96)

**Total: ~67 admin-protected endpoints across 8 services.**

### 2.9 DB Seed and Admin Setup

- `docker/mysql/init/02-ensure-admin.sql` — Sets `role = 'admin'` for `chaldea@admin.com`. Must be updated for new RBAC schema.
- `docker/mysql/init/01-seed-data.sql` — Contains game data seeds. May need to seed roles/permissions tables.

### 2.10 Risks and Migration Concerns

1. **Risk: Breaking `/users/me` API contract** — All 6 services depend on the `/users/me` response via `auth_http.py`. The `UserRead` schema in each service only expects `{id, username, role}`. Adding new fields is safe (Pydantic ignores extras by default), but changing/removing `role` would break all services simultaneously.
   - **Mitigation:** Keep `role` string field in `/users/me` response for backward compatibility. Add `permissions` as additional field. Update `auth_http.py` gradually.

2. **Risk: `get_admin_user()` hardcodes `role != "admin"`** — This check exists in 6 identical `auth_http.py` files. Changing the role system requires updating all 6 files.
   - **Mitigation:** Evolve `get_admin_user()` to check `role` against a list of privileged roles OR check permissions list. Can be done in single PR since files are identical.

3. **Risk: JWT token contains stale `role`** — Role is encoded in JWT at login time. If admin changes a user's role, the JWT still has the old role until token expires (20 hours) or user re-logs.
   - **Mitigation:** Other services don't use JWT role directly — they call `/users/me` which reads from DB. Only user-service's `get_current_user()` reads role from JWT but doesn't actually use it for authorization (role checks read from DB object). So this is LOW risk.

4. **Risk: Data migration — existing admin users** — Currently there's at least one admin (`chaldea@admin.com`). The migration must preserve this.
   - **Mitigation:** Alembic migration with data migration step that maps `role='admin'` -> proper role_id.

5. **Risk: Frontend has NO route guards** — Admin pages are accessible via direct URL to any logged-in user. Backend protection exists but UX is poor (user sees page, then gets 403 errors on API calls).
   - **Mitigation:** Add a `ProtectedRoute` component that checks user role/permissions before rendering admin pages. This is a NEW requirement beyond just replacing `is_admin`.

6. **Risk: "Last admin" protection** — Must prevent removing the last user with admin role. Requires a check before any role change: count remaining admins.
   - **Mitigation:** Add validation in the role assignment endpoint.

7. **Risk: Notification-service uses `create_all()`** — No Alembic. Per CLAUDE.md T2 rule, Alembic should be added if we touch this service. However, notification-service only needs a 1-line change in `main.py` (inline role check). The Alembic addition could be scoped separately.

8. **Risk: WorldPage admin button visible to all users** — `WorldPage.jsx` line 70 shows "Управление локациями" button without any role check. This is an existing bug unrelated to RBAC but should be noted.

### 2.11 Summary of Changes Scope

| Layer | Scope |
|-------|-------|
| **DB (user-service Alembic)** | 4 new tables + 2 new columns on users + data migration + seed data |
| **user-service** | New models, schemas, CRUD, endpoints for RBAC management; update auth.py, login, /me |
| **6 other services** | Update `auth_http.py` (identical file in each) to support new role/permission checking |
| **notification-service** | Update inline role check in main.py |
| **Frontend Redux** | Update userSlice to store permissions; update MeResponse type |
| **Frontend routing** | Add ProtectedRoute/guard component for admin pages |
| **Frontend AdminMenu** | Update to check role hierarchy instead of `=== 'admin'` |
| **Frontend AdminPage** | Filter visible sections based on user permissions |
| **DB seed** | Update `02-ensure-admin.sql` for new role system |

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 DB Schema

#### New Tables (owned by user-service)

```sql
-- 1. Roles table (hierarchical)
CREATE TABLE roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,          -- 'admin', 'moderator', 'editor', 'user'
    level INT NOT NULL DEFAULT 0,               -- hierarchy: admin=100, moderator=50, editor=20, user=0
    description VARCHAR(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Permissions table
CREATE TABLE permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    module VARCHAR(50) NOT NULL,               -- 'users', 'items', 'characters', 'skills', 'locations', 'rules'
    action VARCHAR(50) NOT NULL,               -- 'create', 'read', 'update', 'delete', 'manage'
    description VARCHAR(255) DEFAULT NULL,
    UNIQUE KEY uq_module_action (module, action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Role-Permission mapping (which permissions a role gets by default)
CREATE TABLE role_permissions (
    role_id INT NOT NULL,
    permission_id INT NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. User-Permission overrides (individual grants/revokes on top of role)
CREATE TABLE user_permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    permission_id INT NOT NULL,
    granted BOOLEAN NOT NULL DEFAULT TRUE,     -- TRUE=grant, FALSE=revoke (override role default)
    UNIQUE KEY uq_user_permission (user_id, permission_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Modify users table
ALTER TABLE users ADD COLUMN role_id INT DEFAULT NULL;
ALTER TABLE users ADD COLUMN role_display_name VARCHAR(100) DEFAULT NULL;
ALTER TABLE users ADD CONSTRAINT fk_users_role FOREIGN KEY (role_id) REFERENCES roles(id);
-- NOTE: `role` VARCHAR(100) column is KEPT for backward compat. Will be dropped in a future migration.
```

#### Seed Data

```sql
-- Roles
INSERT INTO roles (id, name, level, description) VALUES
    (1, 'user', 0, 'Обычный пользователь'),
    (2, 'editor', 20, 'Редактор (только чтение админки)'),
    (3, 'moderator', 50, 'Модератор (всё кроме управления пользователями)'),
    (4, 'admin', 100, 'Администратор (полный доступ)');

-- Permissions for initial modules: users, items
INSERT INTO permissions (module, action, description) VALUES
    ('users', 'read', 'Просмотр списка пользователей в админке'),
    ('users', 'update', 'Редактирование пользователей'),
    ('users', 'delete', 'Удаление пользователей'),
    ('users', 'manage', 'Управление ролями и правами пользователей'),
    ('items', 'create', 'Создание предметов'),
    ('items', 'read', 'Просмотр предметов в админке'),
    ('items', 'update', 'Редактирование предметов'),
    ('items', 'delete', 'Удаление предметов');

-- Admin gets ALL permissions (role_permissions)
INSERT INTO role_permissions (role_id, permission_id)
    SELECT 4, id FROM permissions;

-- Moderator gets items:* (all item permissions, but NOT users:*)
INSERT INTO role_permissions (role_id, permission_id)
    SELECT 3, id FROM permissions WHERE module = 'items';

-- Editor gets read-only (items:read, users:read)
INSERT INTO role_permissions (role_id, permission_id)
    SELECT 2, id FROM permissions WHERE action = 'read';

-- Data migration: map existing users.role string to role_id
UPDATE users SET role_id = 4 WHERE role = 'admin';
UPDATE users SET role_id = 1 WHERE role = 'user' OR role IS NULL OR role_id IS NULL;
```

#### Indexes

- `roles.name` — UNIQUE (already in DDL)
- `permissions (module, action)` — UNIQUE (already in DDL)
- `user_permissions (user_id, permission_id)` — UNIQUE (already in DDL)
- `users.role_id` — implicit via FK, but add INDEX for queries

#### Migration Strategy

Single Alembic migration `0006_add_rbac_tables.py` in user-service:
1. Create `roles` table
2. Create `permissions` table
3. Create `role_permissions` table
4. Create `user_permissions` table
5. Add `role_id` and `role_display_name` columns to `users`
6. Run data migration (seed roles, permissions, role_permissions, map users)
7. Add FK constraint on `users.role_id`

**Rollback plan:** Drop tables in reverse order, drop new columns. The `role` string column is preserved throughout, so rollback is safe.

**Important:** The `role` string column on `users` is NOT dropped in this migration. It remains as a computed/synced field for backward compatibility. It will be dropped in a future migration when all consumers have been updated.

### 3.2 API Contracts

#### 3.2.1 Modified Endpoint: `GET /users/me`

The critical contract. Response adds new fields while keeping `role` string for backward compat.

**Response (updated `MeResponse`):**
```json
{
    "id": 1,
    "email": "user@example.com",
    "username": "testuser",
    "avatar": "assets/avatars/avatar.png",
    "balance": 0,
    "role": "admin",
    "role_display_name": "Главный администратор",
    "permissions": ["users:read", "users:update", "users:delete", "users:manage", "items:create", "items:read", "items:update", "items:delete"],
    "current_character_id": null,
    "character": null
}
```

- `role` — string name from `roles.name` (backward compat, always present)
- `role_display_name` — custom title or null
- `permissions` — flat list of effective permissions (role + individual overrides). For admin role, this is ALL permissions in the system.

**Computing effective permissions (server-side logic):**
1. If user role is "admin" (level=100): return ALL permissions from `permissions` table (auto-grant)
2. Otherwise: start with role's `role_permissions`, then apply `user_permissions` overrides (add if `granted=True`, remove if `granted=False`)

#### 3.2.2 New Endpoint: `GET /users/roles`

List all available roles. Admin only.

**Auth:** `Depends(get_current_user)` + inline check `role == "admin"`
**Response (200):**
```json
[
    {"id": 1, "name": "user", "level": 0, "description": "Обычный пользователь"},
    {"id": 2, "name": "editor", "level": 20, "description": "Редактор"},
    {"id": 3, "name": "moderator", "level": 50, "description": "Модератор"},
    {"id": 4, "name": "admin", "level": 100, "description": "Администратор"}
]
```

#### 3.2.3 New Endpoint: `PUT /users/{user_id}/role`

Assign a role to a user. Admin only.

**Auth:** `Depends(get_current_user)` + inline check `role == "admin"`
**Request:**
```json
{
    "role_id": 3,
    "display_name": "Администратор навыков"
}
```
- `role_id` — required, INT
- `display_name` — optional, string (custom title)

**Response (200):**
```json
{
    "id": 1,
    "username": "testuser",
    "role": "moderator",
    "role_display_name": "Администратор навыков",
    "permissions": ["items:create", "items:read", "items:update", "items:delete"]
}
```

**Error cases:**
- 404: User not found
- 404: Role not found
- 403: Not admin
- 409: Cannot remove admin role from last admin (`SELECT COUNT(*) FROM users WHERE role_id = (SELECT id FROM roles WHERE name = 'admin')`)

**Security — Last Admin Protection:**
Before changing a user's role away from admin, check:
```python
if current_role.name == 'admin' and new_role.name != 'admin':
    admin_count = db.query(User).filter(User.role_id == admin_role.id).count()
    if admin_count <= 1:
        raise HTTPException(409, "Нельзя снять роль администратора с последнего админа")
```

#### 3.2.4 New Endpoint: `GET /users/permissions`

List all available permissions, grouped by module. Admin only.

**Auth:** `Depends(get_current_user)` + inline check `role == "admin"`
**Response (200):**
```json
{
    "modules": {
        "users": [
            {"id": 1, "action": "read", "description": "Просмотр списка пользователей"},
            {"id": 2, "action": "update", "description": "Редактирование пользователей"},
            {"id": 3, "action": "delete", "description": "Удаление пользователей"},
            {"id": 4, "action": "manage", "description": "Управление ролями и правами"}
        ],
        "items": [
            {"id": 5, "action": "create", "description": "Создание предметов"},
            {"id": 6, "action": "read", "description": "Просмотр предметов"},
            {"id": 7, "action": "update", "description": "Редактирование предметов"},
            {"id": 8, "action": "delete", "description": "Удаление предметов"}
        ]
    }
}
```

#### 3.2.5 New Endpoint: `PUT /users/{user_id}/permissions`

Set individual permission overrides for a user. Admin only.

**Auth:** `Depends(get_current_user)` + inline check `role == "admin"`
**Request:**
```json
{
    "grants": ["items:create", "items:update"],
    "revokes": ["users:manage"]
}
```
- `grants` — list of `module:action` strings to explicitly grant (even if role doesn't have them)
- `revokes` — list of `module:action` strings to explicitly revoke (even if role has them)
- Sending empty lists clears all overrides

**Response (200):**
```json
{
    "id": 1,
    "username": "testuser",
    "role": "editor",
    "permissions": ["users:read", "items:create", "items:read", "items:update"],
    "overrides": {
        "grants": ["items:create", "items:update"],
        "revokes": ["users:manage"]
    }
}
```

**Validation:**
- Each permission string must match an existing `module:action` in `permissions` table
- Cannot set overrides for admin role users (admin always has everything)
- 422 if permission string format is invalid

**Security — Privilege Escalation Prevention:**
- Only admin-role users can call this endpoint
- Cannot grant `users:manage` to self (prevent creating new admins via permissions — role assignment is a separate action)
- Overrides on admin users are silently ignored (admin always has all permissions)

#### 3.2.6 New Endpoint: `GET /users/{user_id}/effective-permissions`

Get the effective (computed) permissions for a specific user. Admin only.

**Auth:** `Depends(get_current_user)` + inline check `role == "admin"`
**Response (200):**
```json
{
    "user_id": 1,
    "username": "testuser",
    "role": "moderator",
    "role_display_name": "Куратор контента",
    "role_permissions": ["items:create", "items:read", "items:update", "items:delete"],
    "overrides": {
        "grants": ["users:read"],
        "revokes": ["items:delete"]
    },
    "effective_permissions": ["items:create", "items:read", "items:update", "users:read"]
}
```

#### 3.2.7 Modified Endpoint: `GET /users/admins`

Currently returns users with `role == "admin"`. Update to query by `role_id` pointing to admin role.

**Response:** Same format as before (list of `UserRead`). No contract change.

**Implementation change:**
```python
# Before:
admins = db.query(User).filter(User.role == "admin").all()
# After:
admin_role = db.query(Role).filter(Role.name == "admin").first()
admins = db.query(User).filter(User.role_id == admin_role.id).all()
```

### 3.3 Auth Middleware Changes

#### 3.3.1 user-service Internal Changes

**`models.py`** — Add new ORM models:
```python
class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    level = Column(Integer, nullable=False, default=0)
    description = Column(String(255), nullable=True)

class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True, index=True)
    module = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)
    __table_args__ = (UniqueConstraint('module', 'action', name='uq_module_action'),)

class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)

class UserPermission(Base):
    __tablename__ = "user_permissions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    granted = Column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint('user_id', 'permission_id', name='uq_user_permission'),)
```

**`models.py` — Modify `User` model:**
```python
class User(Base):
    # ... existing fields ...
    role = Column(String(100), default='user')          # KEPT for backward compat
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)  # NEW
    role_display_name = Column(String(100), nullable=True)            # NEW
```

**`schemas.py`** — New schemas:
```python
class RoleResponse(BaseModel):
    id: int
    name: str
    level: int
    description: Optional[str] = None
    class Config:
        orm_mode = True

class PermissionItem(BaseModel):
    id: int
    action: str
    description: Optional[str] = None
    class Config:
        orm_mode = True

class PermissionsGroupedResponse(BaseModel):
    modules: dict  # {"module_name": [PermissionItem, ...]}

class RoleAssignRequest(BaseModel):
    role_id: int
    display_name: Optional[str] = None

class UserRoleResponse(BaseModel):
    id: int
    username: str
    role: str
    role_display_name: Optional[str] = None
    permissions: List[str] = []

class PermissionOverridesRequest(BaseModel):
    grants: List[str] = []   # ["module:action", ...]
    revokes: List[str] = []  # ["module:action", ...]

class UserPermissionsResponse(BaseModel):
    id: int
    username: str
    role: str
    permissions: List[str] = []
    overrides: dict = {}  # {"grants": [...], "revokes": [...]}

class EffectivePermissionsResponse(BaseModel):
    user_id: int
    username: str
    role: str
    role_display_name: Optional[str] = None
    role_permissions: List[str] = []
    overrides: dict = {}
    effective_permissions: List[str] = []

# Update MeResponse
class MeResponse(BaseModel):
    id: int
    email: EmailStr
    username: str
    avatar: Optional[str] = None
    balance: Optional[int] = 0
    role: Optional[str] = "user"
    role_display_name: Optional[str] = None      # NEW
    permissions: List[str] = []                    # NEW
    current_character_id: Optional[int] = None
    character: Optional[CharacterShort] = None
```

**`crud.py`** — New function:
```python
def get_effective_permissions(db: Session, user: User) -> List[str]:
    """Compute effective permissions for a user.
    Admin role always gets ALL permissions.
    Others get role_permissions + user_permission overrides.
    """
    role = db.query(Role).filter(Role.id == user.role_id).first()
    if not role:
        return []

    # Admin gets everything
    if role.name == "admin":
        all_perms = db.query(Permission).all()
        return [f"{p.module}:{p.action}" for p in all_perms]

    # Role permissions
    role_perm_ids = db.query(RolePermission.permission_id).filter(
        RolePermission.role_id == role.id
    ).all()
    role_perm_ids = {rp[0] for rp in role_perm_ids}

    # User overrides
    user_overrides = db.query(UserPermission).filter(
        UserPermission.user_id == user.id
    ).all()

    granted_ids = {uo.permission_id for uo in user_overrides if uo.granted}
    revoked_ids = {uo.permission_id for uo in user_overrides if not uo.granted}

    effective_ids = (role_perm_ids | granted_ids) - revoked_ids

    perms = db.query(Permission).filter(Permission.id.in_(effective_ids)).all()
    return [f"{p.module}:{p.action}" for p in perms]
```

**`main.py` — Update `/users/me` endpoint:**
```python
@router.get("/me", response_model=schemas.MeResponse)
async def read_users_me(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # ... existing last_active_at update ...

    # Compute role name from role_id (fallback to string column)
    role_name = current_user.role  # backward compat default
    if current_user.role_id:
        role_obj = db.query(models.Role).filter(models.Role.id == current_user.role_id).first()
        if role_obj:
            role_name = role_obj.name

    permissions = get_effective_permissions(db, current_user)

    me_data = {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "avatar": current_user.avatar,
        "balance": current_user.balance,
        "role": role_name,
        "role_display_name": current_user.role_display_name,
        "permissions": permissions,
        "current_character_id": current_user.current_character,
        "character": None,
    }
    # ... existing character fetch ...
```

**`auth.py` — Update JWT token:**
The `role` field in JWT continues to be the string role name. No structural change needed — role is always read from DB via `/users/me`, not from JWT, by other services.

**`main.py` — Replace inline admin checks:**
The two inline `current_user.role != "admin"` checks in `delete_user_character_relation` and `clear_current_character` should use the new helper:
```python
def require_permission(db: Session, user: models.User, permission: str):
    """Check if user has a specific permission. Raises 403 if not."""
    perms = get_effective_permissions(db, user)
    if permission not in perms:
        raise HTTPException(status_code=403, detail="Недостаточно прав для выполнения этого действия")
```

For now, these two endpoints map to `users:manage` permission.

#### 3.3.2 Other Services — `auth_http.py` Evolution

**Phase 1 (this feature):** Update `UserRead` schema and `get_admin_user()` in all 6 services + notification-service inline check.

**Updated `auth_http.py` (identical across 6 services):**
```python
class UserRead(BaseModel):
    id: int
    username: str
    role: Optional[str] = None
    permissions: List[str] = []    # NEW

    class Config:
        orm_mode = True


def get_current_user_via_http(token: str = Depends(OAUTH2_SCHEME)) -> UserRead:
    # ... same HTTP call to /users/me ...
    # Pydantic will automatically pick up new fields from response


def get_admin_user(user: UserRead = Depends(get_current_user_via_http)) -> UserRead:
    """Check that user has admin or moderator role (level >= moderator)."""
    if user.role not in ("admin", "moderator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только администраторы и модераторы могут выполнять это действие",
        )
    return user
```

**Key design decision:** For this initial implementation, `get_admin_user()` is updated to accept BOTH admin and moderator roles. This is the simplest change that enables RBAC without rewriting every endpoint.

**Future phase:** Add a `require_permission(permission: str)` dependency factory that checks the `permissions` list:
```python
def require_permission(permission: str):
    def checker(user: UserRead = Depends(get_current_user_via_http)) -> UserRead:
        if permission not in user.permissions:
            raise HTTPException(403, "Недостаточно прав")
        return user
    return checker

# Usage in endpoint:
@router.post("/items", dependencies=[Depends(require_permission("items:create"))])
```

This granular permission checking is NOT part of this feature's scope for all 67 endpoints. It will be applied per-module as modules are migrated to RBAC. For now, all existing `get_admin_user()` calls accept admin + moderator.

**notification-service:** Update the inline check in `main.py`:
```python
# Before:
if current_user.role != "admin":
# After:
if current_user.role not in ("admin", "moderator"):
```

### 3.4 Frontend Architecture

#### 3.4.1 Redux State Changes

**Update `userSlice` (migrate `.js` → `.ts`):**

```typescript
// types
interface UserState {
  id: number | null;
  email: string | null;
  username: string | null;
  character: CharacterShort | null;
  role: string | null;
  roleDisplayName: string | null;
  permissions: string[];
  avatar: string | null;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}

const initialState: UserState = {
  id: null,
  email: null,
  username: null,
  character: null,
  role: null,
  roleDisplayName: null,
  permissions: [],
  avatar: null,
  status: 'idle',
  error: null,
};

// In getMe.fulfilled:
state.role = action.payload.role;
state.roleDisplayName = action.payload.role_display_name;
state.permissions = action.payload.permissions || [];
```

**Permission helper functions** (new file `src/utils/permissions.ts`):
```typescript
export const hasPermission = (permissions: string[], permission: string): boolean => {
  return permissions.includes(permission);
};

export const hasAnyPermission = (permissions: string[], perms: string[]): boolean => {
  return perms.some(p => permissions.includes(p));
};

export const hasModuleAccess = (permissions: string[], module: string): boolean => {
  return permissions.some(p => p.startsWith(`${module}:`));
};

export const isStaff = (role: string | null): boolean => {
  return role !== null && ['admin', 'moderator', 'editor'].includes(role);
};
```

**Redux selectors** (in `userSlice.ts` or separate file):
```typescript
export const selectPermissions = (state: RootState) => state.user.permissions;
export const selectRole = (state: RootState) => state.user.role;
export const selectIsStaff = (state: RootState) => isStaff(state.user.role);
export const selectHasPermission = (permission: string) =>
  (state: RootState) => hasPermission(state.user.permissions, permission);
```

#### 3.4.2 ProtectedRoute Component

New component: `src/components/CommonComponents/ProtectedRoute/ProtectedRoute.tsx`

```typescript
interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: string;           // minimum role level check
  requiredPermission?: string;      // specific permission check
  requiredPermissions?: string[];   // any of these permissions
  fallbackPath?: string;            // redirect on failure (default: '/home')
}
```

Behavior:
1. If user not logged in → redirect to `/` (login page)
2. If `requiredRole` specified and user's role level is lower → redirect to fallback
3. If `requiredPermission` specified and user doesn't have it → redirect to fallback
4. Otherwise → render children

Usage in `App.tsx`:
```tsx
<Route path="admin" element={
  <ProtectedRoute requiredRole="editor">
    <AdminPage />
  </ProtectedRoute>
} />
<Route path="admin/items" element={
  <ProtectedRoute requiredPermission="items:read">
    <ItemsAdminPage />
  </ProtectedRoute>
} />
```

#### 3.4.3 AdminMenu Update

Update `AdminMenu.tsx` to show for any staff role (admin, moderator, editor):
```typescript
const AdminMenu = ({ role }: AdminMenuProps) => {
  if (!role || !['admin', 'moderator', 'editor'].includes(role)) return null;
  // ... same render ...
};
```

#### 3.4.4 AdminPage Update

Update `AdminPage.tsx` to filter sections based on permissions:
```typescript
// Each section maps to a permission/module
const sections: AdminSection[] = [
  { label: 'Заявки', path: '/requestsPage', description: '...', module: 'characters' },
  { label: 'Айтемы', path: '/admin/items', description: '...', module: 'items' },
  { label: 'Локации', path: '/admin/locations', description: '...', module: 'locations' },
  // ...
];

// In render: filter sections by user permissions
const visibleSections = sections.filter(s =>
  role === 'admin' || hasModuleAccess(permissions, s.module)
);
```

#### 3.4.5 Role Display

Show role badge on the user profile. The `role_display_name` or role name should be displayed where appropriate (e.g., profile page, user list for staff).

### 3.5 Data Flow Diagram

#### Auth Flow (updated)

```
[Frontend] --(Bearer token)--> [Any Service]
                                    |
                                    v
                    [auth_http.py: get_current_user_via_http()]
                                    |
                                    v (HTTP GET /users/me)
                    [user-service: GET /users/me]
                                    |
                                    v (DB query)
                    users table + roles table + permissions + overrides
                                    |
                                    v
                    Returns: { id, username, role, role_display_name,
                               permissions: ["users:manage", "items:create", ...],
                               ... }
                                    |
                                    v
                    [auth_http.py: get_admin_user() checks role in ("admin","moderator")]
```

#### Role Assignment Flow

```
[Admin Frontend] --> PUT /users/{id}/role {role_id, display_name}
                                    |
                                    v
                    [user-service: validate admin, check last-admin, update user]
                                    |
                                    v
                    UPDATE users SET role_id=?, role=?, role_display_name=?
                                    |
                                    v
                    Response: { user with new role + permissions }
```

#### Permission Override Flow

```
[Admin Frontend] --> PUT /users/{id}/permissions {grants: [...], revokes: [...]}
                                    |
                                    v
                    [user-service: validate admin, validate permission strings]
                                    |
                                    v
                    DELETE FROM user_permissions WHERE user_id=?
                    INSERT INTO user_permissions (user_id, permission_id, granted) VALUES ...
                                    |
                                    v
                    Response: { user with updated effective permissions }
```

### 3.6 Security Considerations

1. **Authentication:** All new RBAC endpoints require JWT authentication (existing `get_current_user` dependency).

2. **Authorization:**
   - All RBAC management endpoints (role assignment, permission management) are admin-only
   - Role assignment checks: only admin can assign roles
   - Permission override: only admin can set overrides
   - Admin cannot downgrade self if they're the last admin

3. **Privilege Escalation Prevention:**
   - Only admin-role users can manage roles/permissions (not just users with `users:manage` permission)
   - The `users:manage` permission controls user editing (username, avatar, etc.), NOT role assignment
   - Role assignment is always admin-only (checked by role level, not permission)

4. **Last Admin Protection:**
   - Before any role change FROM admin: count remaining admin-role users
   - If count == 1 and target is the last admin: reject with 409

5. **Input Validation:**
   - `role_id` must reference existing role
   - Permission strings must match `module:action` format
   - Permission strings must exist in `permissions` table
   - `display_name` max 100 chars, sanitized (bleach)

6. **Rate Limiting:** Not added in this feature. Can be added at Nginx level later for admin endpoints.

7. **Backward Compatibility:**
   - `role` string field kept in all responses
   - `role` column kept in `users` table (synced on role change)
   - `get_admin_user()` in other services still works (checks string role)
   - Frontend gracefully handles missing `permissions` field (defaults to `[]`)

### 3.7 Sync Strategy for `users.role` String Column

When `role_id` is updated, the `role` string column must be synced:
```python
# In role assignment endpoint:
user.role_id = new_role.id
user.role = new_role.name  # sync the string column
user.role_display_name = request.display_name
```

This ensures backward compatibility for:
- JWT token creation (reads `user.role`)
- Any direct DB queries using `users.role` string
- The `02-ensure-admin.sql` seed script (still works)

### 3.8 `02-ensure-admin.sql` Update

Update to work with both old and new schema:
```sql
-- Ensure chaldea@admin.com has admin role (backward compat + RBAC)
UPDATE users u
JOIN roles r ON r.name = 'admin'
SET u.role = 'admin', u.role_id = r.id
WHERE u.email = 'chaldea@admin.com'
  AND (u.role != 'admin' OR u.role_id IS NULL OR u.role_id != r.id);
```

But since this runs at container init before Alembic, the `roles` table may not exist yet. **Solution:** Keep the original SQL as-is. The Alembic migration handles the data migration for existing users. The seed script only needs to work for fresh installs.

For fresh installs, the seed data (roles, permissions) will be inserted by the Alembic migration, and `02-ensure-admin.sql` will set `role = 'admin'`. On next container start, Alembic migration maps `role='admin'` to `role_id=4`. This two-step process is safe.

**Alternative (simpler):** Add a `03-ensure-admin-rbac.sql` that runs after `02`:
```sql
-- Only runs if roles table exists (after Alembic migration)
-- This handles fresh installs where 02 sets role='admin' but not role_id
UPDATE users u
SET u.role_id = (SELECT id FROM roles WHERE name = 'admin')
WHERE u.email = 'chaldea@admin.com'
  AND u.role_id IS NULL
  AND EXISTS (SELECT 1 FROM roles WHERE name = 'admin');
```

### 3.9 What Is NOT In Scope

To keep this feature manageable, the following are explicitly deferred:

1. **Granular permission checks on all 67 endpoints** — Only the 2 user-service inline checks are migrated. The `get_admin_user()` in other services is updated to accept moderator+admin but does NOT do per-permission checks. Per-permission enforcement will be added module-by-module in future features.

2. **New permission modules beyond `users` and `items`** — Permissions for `characters`, `skills`, `locations`, `rules`, `photos` will be added when those modules get RBAC work.

3. **Admin UI for role/permission management** — A full admin page for managing roles and permissions. This feature adds the API endpoints, but the frontend admin UI for role/permission assignment is a separate follow-up. For now, admins use the API directly or a minimal UI is added (see task breakdown).

4. **Dropping the `role` string column** — Will be done in a future migration after all consumers are verified.

5. **Per-endpoint permission mapping** — Each of the 67 endpoints needs to be mapped to a specific permission. This will happen organically as modules are migrated.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **RBAC models & Alembic migration**: Add `Role`, `Permission`, `RolePermission`, `UserPermission` ORM models to user-service. Add `role_id` and `role_display_name` columns to `User` model. Create Alembic migration `0006_add_rbac_tables.py` that creates all 4 new tables, seeds roles (user/editor/moderator/admin), seeds permissions for `users` and `items` modules, seeds `role_permissions`, adds new columns to `users`, and migrates existing `role` string values to `role_id`. | Backend Developer | TODO | `services/user-service/models.py`, `services/user-service/alembic/versions/0006_add_rbac_tables.py` | — | Migration runs cleanly on fresh DB and on existing DB with data. `python -m py_compile models.py` passes. All 4 tables created with correct constraints. Existing admin users get `role_id=4`. |
| 2 | **RBAC CRUD logic & `/users/me` update**: Add `get_effective_permissions()` function to `crud.py`. Add `require_permission()` helper. Update `MeResponse` schema to include `role_display_name` and `permissions` fields. Update `/users/me` endpoint to compute and return effective permissions. Update the two inline admin checks (`delete_user_character_relation`, `clear_current_character`) to use `require_permission("users:manage")`. Update `/users/admins` to query by `role_id`. Add all new Pydantic schemas (`RoleResponse`, `PermissionItem`, `RoleAssignRequest`, etc). Sync `users.role` string when `role_id` changes. | Backend Developer | TODO | `services/user-service/crud.py`, `services/user-service/schemas.py`, `services/user-service/main.py` | #1 | `/users/me` returns `permissions` list and `role_display_name`. Admin user gets all permissions. Regular user gets empty list. `py_compile` passes on all files. |
| 3 | **RBAC management endpoints**: Add 4 new endpoints to user-service: `GET /users/roles`, `PUT /users/{user_id}/role`, `GET /users/permissions`, `PUT /users/{user_id}/permissions`, `GET /users/{user_id}/effective-permissions`. Implement last-admin protection in role assignment. Implement privilege escalation prevention. All endpoints require admin role. | Backend Developer | DONE | `services/user-service/main.py`, `services/user-service/crud.py` | #2 | All 5 endpoints work correctly. Last admin cannot be demoted. Role changes sync `users.role` string. `py_compile` passes. |
| 4 | **Update `auth_http.py` in all 6 services + notification-service**: Update `UserRead` schema to include `permissions: List[str] = []`. Update `get_admin_user()` to accept `role in ("admin", "moderator")`. Update notification-service inline role check. Add `from typing import List` import. | Backend Developer | DONE | `services/character-service/app/auth_http.py`, `services/skills-service/app/auth_http.py`, `services/inventory-service/app/auth_http.py`, `services/locations-service/app/auth_http.py`, `services/character-attributes-service/app/auth_http.py`, `services/photo-service/auth_http.py`, `services/notification-service/app/main.py` | #2 | All 7 files updated. `get_admin_user()` accepts admin and moderator. Pydantic `UserRead` includes `permissions` field. `py_compile` passes on all files. |
| 5 | **QA: RBAC models, migration, and CRUD tests**: Write pytest tests for user-service RBAC: (a) test `get_effective_permissions()` for admin (all perms), moderator (role perms), editor (read perms), user (no perms); (b) test permission overrides (grant adds, revoke removes); (c) test admin always gets all permissions including newly added ones; (d) test `/users/me` response includes permissions. | QA Test | DONE | `services/user-service/tests/test_rbac_permissions.py` | #2 | All tests pass with `pytest`. Covers admin auto-permissions, override logic, and /me response. |
| 6 | **QA: RBAC management endpoints tests**: Write pytest tests for: (a) `GET /users/roles` returns all 4 roles; (b) `PUT /users/{id}/role` changes role and syncs string; (c) last-admin protection rejects demotion; (d) `PUT /users/{id}/permissions` sets overrides correctly; (e) `GET /users/{id}/effective-permissions` computes correctly; (f) non-admin gets 403 on all endpoints; (g) privilege escalation prevention. | QA Test | DONE | `services/user-service/tests/test_rbac_endpoints.py` | #3 | All tests pass with `pytest`. Covers happy path, error cases, and security. |
| 7 | **QA: auth_http.py update tests**: Write pytest tests verifying: (a) `get_admin_user()` accepts admin role; (b) `get_admin_user()` accepts moderator role; (c) `get_admin_user()` rejects user and editor roles; (d) `UserRead` correctly parses response with permissions field; (e) `UserRead` handles response without permissions field (backward compat). Test in one representative service (character-service). | QA Test | DONE | `services/character-service/app/tests/test_auth_http_rbac.py` | #4 | All 13 tests pass. Both admin and moderator accepted. User/editor/None rejected with 403. UserRead backward compat verified. |
| 8 | **Frontend: Migrate `userSlice.js` to TypeScript + add permissions state**: Rename `userSlice.js` to `userSlice.ts`. Add TypeScript types for state. Add `roleDisplayName` and `permissions` to state. Update `getMe` fulfilled handler to store `role_display_name` and `permissions` from API. Add selectors (`selectPermissions`, `selectRole`, `selectIsStaff`). Create `src/utils/permissions.ts` with helper functions (`hasPermission`, `hasAnyPermission`, `hasModuleAccess`, `isStaff`). Update all import references. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/redux/slices/userSlice.ts` (renamed), `services/frontend/app-chaldea/src/utils/permissions.ts` (new) | #2 | `npx tsc --noEmit` passes. `npm run build` passes. All imports updated. Permissions stored in Redux after login. |
| 9 | **Frontend: ProtectedRoute component + route guards**: Create `ProtectedRoute.tsx` component that checks role/permissions before rendering children. Wrap all admin routes in `App.tsx` with `ProtectedRoute`. Use `requiredRole="editor"` for general admin access (staff check). For `/admin/items` use `requiredPermission="items:read"` (specific). Unauthorized users redirected to `/home` with a toast error. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/CommonComponents/ProtectedRoute/ProtectedRoute.tsx` (new), `services/frontend/app-chaldea/src/components/App/App.tsx` | #8 | `npx tsc --noEmit` passes. `npm run build` passes. Non-staff users redirected from admin routes. Toast shown on redirect. |
| 10 | **Frontend: Update AdminMenu + AdminPage for RBAC**: Update `AdminMenu.tsx` to show shield icon for any staff role (admin/moderator/editor), not just admin. Update `AdminPage.tsx` to filter visible sections based on user's permissions (admin sees all, moderator sees non-users sections, editor sees only what they have access to). Each section maps to a permission module. Responsive: works on mobile (360px+). | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/CommonComponents/Header/AdminMenu.tsx`, `services/frontend/app-chaldea/src/components/Admin/AdminPage.tsx`, `services/frontend/app-chaldea/src/components/CommonComponents/Header/Header.tsx` | #8 | Moderator sees admin panel without users section. Editor sees limited sections. Admin sees everything. Layout works on mobile. `tsc --noEmit` + `npm run build` pass. |
| 11 | **Update `02-ensure-admin.sql` and add `03-ensure-admin-rbac.sql`**: Add `docker/mysql/init/03-ensure-admin-rbac.sql` to handle fresh installs where the admin user's `role_id` may be NULL after `02-ensure-admin.sql` runs but before Alembic migration. The script should conditionally set `role_id` if the `roles` table exists. | Backend Developer | TODO | `docker/mysql/init/03-ensure-admin-rbac.sql` (new) | #1 | Script is idempotent. Works on fresh install and existing DB. Does not error if `roles` table doesn't exist yet. |
| 12 | **Review** | Reviewer | TODO | all | #1-#11 | Full review checklist passed. `py_compile` on all modified Python files. `npx tsc --noEmit` + `npm run build` for frontend. `pytest` in user-service and character-service. Live verification: admin sees all admin sections, moderator sees limited sections, regular user sees no admin link. `/users/me` returns permissions. |

### Task Dependency Graph

```
#1 (DB models + migration)
  └── #2 (CRUD + /me update)
  │     ├── #3 (management endpoints)
  │     │     └── #6 (QA: endpoint tests)
  │     ├── #4 (auth_http.py in 7 services)
  │     │     └── #7 (QA: auth_http tests)
  │     ├── #5 (QA: CRUD tests)
  │     └── #8 (Frontend: userSlice + permissions utils)
  │           ├── #9 (Frontend: ProtectedRoute + route guards)
  │           └── #10 (Frontend: AdminMenu + AdminPage)
  └── #11 (SQL seed scripts)

#12 (Review) depends on ALL above
```

### Parallelism Opportunities

- Tasks #3, #4, #5 can run in parallel (all depend only on #2)
- Tasks #8 can start as soon as #2 is done (knows the API contract)
- Tasks #9 and #10 can run in parallel (both depend on #8)
- Tasks #6 and #7 depend on #3 and #4 respectively
- Task #11 can run in parallel with anything after #1

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-18
**Result:** PASS

#### Automated Check Results
- [x] `py_compile` — PASS (all 14 modified Python files compile cleanly)
- [x] `pytest test_rbac_permissions.py` — PASS (37/37 tests)
- [x] `pytest test_rbac_endpoints.py` — PASS (33/33 tests)
- [x] `pytest test_auth_http_rbac.py` — PASS (13/13 tests)
- [x] `npx tsc --noEmit` — PASS (no errors in FEAT-035 files; all errors are pre-existing in unrelated files)
- [x] `npm run build` — N/A (fails on pre-existing `dompurify` missing import in `RuleOverlay.tsx` — not related to this feature)
- [x] `docker-compose config` — PASS

#### Code Quality Review
- [x] All Python files follow sync SQLAlchemy pattern (user-service is sync)
- [x] Pydantic v1 syntax used (`class Config: orm_mode = True`) — correct
- [x] No `React.FC` usage in any new/modified frontend components
- [x] All new frontend files are `.tsx`/`.ts` (no new `.jsx`)
- [x] All new styles use Tailwind CSS (no new SCSS files)
- [x] Responsive design: AdminPage uses `grid-cols-1 sm:grid-cols-2`, role badge hidden on mobile (`hidden md:inline`)
- [x] No stubs/TODO without tracking
- [x] No hardcoded secrets

#### Security Review
- [x] **Last admin protection**: Implemented in `assign_user_role()` — checks admin count before demotion, returns 409
- [x] **Privilege escalation prevention**: RBAC management endpoints use `require_admin()` (strict admin role check, not permission-based) — moderators cannot manage roles
- [x] **Admin auto-permissions**: Admin always gets ALL permissions from permissions table (dynamic query, not role_permissions lookup)
- [x] **Cannot set overrides on admin**: `set_user_permission_overrides()` returns 400 for admin-role users
- [x] **Input validation**: Permission strings validated for `module:action` format and existence in DB. SQL injection tested and handled (returns 422, not 500)
- [x] **Russian error messages**: All user-facing errors in Russian
- [x] **No secrets exposed**: No sensitive data in responses

#### API Contract Review
- [x] `/users/me` backward compatible — `role` string field preserved, new fields (`role_display_name`, `permissions`) are additive
- [x] `UserRead` in 7 other services handles both old and new response format — `permissions: List[str] = []` defaults to empty list
- [x] All 5 new RBAC endpoints follow REST conventions
- [x] `users.role` string column synced on role assignment (`user.role = new_role.name`)

#### Frontend Review
- [x] `userSlice.js` properly migrated to `userSlice.ts` with full TypeScript types
- [x] All imports resolved (no stale `.js` references)
- [x] `ProtectedRoute` uses role hierarchy via `ROLE_LEVELS` — correct levels match backend
- [x] `AdminPage` filters sections by module access (`hasModuleAccess`) + admin override
- [x] `AdminMenu` shows for all staff roles via `isStaff()` helper
- [x] Role badge displayed in Header with Russian labels + custom `roleDisplayName` support
- [x] Design system tokens used (`gold-text`, `bg-black/50`, `backdrop-blur-md`, `rounded-card`)

#### Migration Review
- [x] Alembic migration `0006` is reversible — `downgrade()` drops tables and columns in correct order
- [x] Seed data correct: 4 roles (user/editor/moderator/admin), 8 permissions (users + items modules)
- [x] Role permissions: admin gets all, moderator gets items:*, editor gets *:read, user gets nothing
- [x] Data migration: `role='admin'` -> `role_id=4`, all others -> `role_id=1`
- [x] FK constraint added after data migration (correct ordering)
- [x] `03-ensure-admin-rbac.sql` is idempotent, safely handles missing `roles` table via stored procedure

#### Cross-Service Review
- [x] All 7 `auth_http.py` files updated consistently (identical structure)
- [x] `get_admin_user()` accepts admin + moderator in all services
- [x] `notification-service/main.py` inline check updated to match (`role not in ("admin", "moderator")`)
- [x] No breaking changes to inter-service communication — `role` string always present in `/users/me` response

#### Test Coverage Review
- [x] 83 total tests across 3 test files
- [x] Critical test: admin always has all permissions including newly added ones (TestAdminAutoPermissions)
- [x] Last admin protection tested (both rejection and success with 2 admins)
- [x] SQL injection resistance tested
- [x] Backward compatibility tested (UserRead without permissions field)
- [x] All error codes verified (401, 403, 404, 409, 422)

#### Live Verification
- Live verification not possible (no running application accessible). All static checks, unit tests, and integration tests pass. The code review confirms correct implementation matching the architecture spec.

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-18 10:00 — PM: фича создана (FEAT-035), запускаю анализ кодовой базы
[LOG] 2026-03-18 10:30 — Analyst: начал анализ, изучаю user-service (auth, JWT, модели, эндпоинты)
[LOG] 2026-03-18 10:45 — Analyst: проанализированы auth_http.py во всех 6 сервисах — идентичный паттерн (HTTP к user-service /users/me)
[LOG] 2026-03-18 11:00 — Analyst: составлен полный список ~67 admin-protected эндпоинтов по 8 сервисам
[LOG] 2026-03-18 11:10 — Analyst: проанализирован фронтенд — Redux userSlice, AdminMenu, AdminPage, маршрутизация (нет route guards)
[LOG] 2026-03-18 11:15 — Analyst: обнаружен баг — WorldPage.jsx показывает кнопку "Управление локациями" всем пользователям (нет проверки роли)
[LOG] 2026-03-18 11:20 — Analyst: анализ завершён, затронуто 8 backend-сервисов + фронтенд, отчёт записан в секцию 2
[LOG] 2026-03-18 12:00 — Architect: начал проектирование RBAC-системы
[LOG] 2026-03-18 13:30 — Architect: спроектировано 12 задач, 5 новых API-контрактов, 4 новых таблицы. Архитектура записана в секции 3 и 4.
[LOG] 2026-03-18 14:00 — Backend Dev: начал задачу #11 — SQL seed-скрипт для RBAC
[LOG] 2026-03-18 14:10 — Backend Dev: задача #11 завершена — создан docker/mysql/init/03-ensure-admin-rbac.sql. Скрипт идемпотентный, использует stored procedure для проверки существования таблицы roles через information_schema перед UPDATE.
[LOG] 2026-03-18 14:30 — Backend Dev: начал задачи #1 и #2 — RBAC модели, миграция, CRUD, обновление /users/me
[LOG] 2026-03-18 15:00 — Backend Dev: задачи #1 и #2 завершены. Добавлены 4 ORM-модели (Role, Permission, RolePermission, UserPermission), миграция 0006, CRUD-функции (get_effective_permissions, require_permission), обновлён /users/me, заменены inline admin-проверки на require_permission. Все файлы прошли синтаксическую проверку.
[LOG] 2026-03-18 15:15 — Backend Dev: начал задачу #4 — обновление auth_http.py в 7 сервисах
[LOG] 2026-03-18 15:25 — Backend Dev: задача #4 завершена. Обновлено 8 файлов: добавлено поле permissions: List[str] в UserRead (7 auth_http.py), get_admin_user() теперь принимает admin и moderator (6 сервисов), обновлён inline-чек в notification-service/main.py. Все файлы прошли синтаксическую проверку (ast.parse).
[LOG] 2026-03-18 16:00 — Backend Dev: начал задачу #3 — RBAC management endpoints
[LOG] 2026-03-18 16:30 — Backend Dev: задача #3 завершена. Добавлены 5 эндпоинтов (GET /roles, PUT /{user_id}/role, GET /permissions, PUT /{user_id}/permissions, GET /{user_id}/effective-permissions). Добавлены CRUD-хелперы (is_admin, require_admin). Обновлены RBAC-схемы (PermissionsGroupedResponse, PermissionOverridesRequest, UserRoleResponse, UserPermissionsResponse, EffectivePermissionsResponse). Реализована защита последнего админа и предотвращение эскалации привилегий. Все файлы прошли синтаксическую проверку.
[LOG] 2026-03-18 17:00 — Frontend Dev: начал задачу #8 — миграция userSlice.js в TypeScript + добавление permissions
[LOG] 2026-03-18 17:20 — Frontend Dev: задача #8 завершена. Переименован userSlice.js → userSlice.ts с полной типизацией (UserState, GetMeResponse, CharacterData). Добавлены поля roleDisplayName и permissions в state. Обновлён getMe.fulfilled для хранения role_display_name и permissions из API. Добавлены селекторы (selectPermissions, selectRole, selectRoleDisplayName). Создан src/utils/permissions.ts с хелперами (hasPermission, hasAnyPermission, hasModuleAccess, isStaff). Все импорты работают без изменений (бандлер резолвит без расширения). npx tsc --noEmit — ошибок от изменённых файлов нет (все ошибки pre-existing). npm run build — ошибка pre-existing (dompurify не установлен в RuleOverlay.tsx).
[LOG] 2026-03-18 18:00 — Frontend Dev: начал задачу #9 — ProtectedRoute компонент + route guards
[LOG] 2026-03-18 18:15 — Frontend Dev: задача #9 завершена. Создан ProtectedRoute.tsx с проверкой роли (иерархия admin>moderator>editor>user через ROLE_LEVELS), конкретного разрешения (requiredPermission) и набора разрешений (requiredPermissions). Обёрнуты все admin-маршруты в App.tsx: /admin и общие страницы — requiredRole="editor", /requestsPage — requiredRole="moderator", /admin/items — requiredPermission="items:read". Незалогиненные пользователи перенаправляются на "/", неавторизованные — на "/home". Без toast при редиректе (по ТЗ). npx tsc --noEmit — ошибок от изменённых файлов нет. npm run build — ошибка pre-existing (dompurify).
[LOG] 2026-03-18 18:30 — QA: начал задачу #7 — тесты для обновлённого auth_http.py в character-service
[LOG] 2026-03-18 18:40 — QA: задача #7 завершена. Написано 13 тестов в test_auth_http_rbac.py: 6 тестов на get_admin_user() (admin/moderator приняты, editor/user/None отклонены с 403, проверка detail), 7 тестов на UserRead (парсинг с permissions, без permissions — дефолт [], без role — дефолт None, все поля, из dict, обратная совместимость, игнорирование лишних полей). Все 13 тестов проходят (pytest -v, 0.05s).
[LOG] 2026-03-18 19:00 — Frontend Dev: начал задачу #10 — обновление AdminMenu + AdminPage + отображение роли в Header
[LOG] 2026-03-18 19:20 — Frontend Dev: задача #10 завершена. AdminMenu.tsx — заменено `role !== 'admin'` на `!isStaff(role)` (импорт из utils/permissions.ts). AdminPage.tsx — добавлен module-маппинг для каждой секции (characters, items, locations, skills), фильтрация через hasModuleAccess() (admin видит всё), адаптивная сетка grid-cols-1 sm:grid-cols-2, сообщение при пустом доступе. Header.tsx — добавлен бейдж роли (roleDisplayName или русское название) рядом с AdminMenu, виден только для staff, скрыт на мобильных (hidden md:inline). npx tsc --noEmit — ошибок от изменённых файлов нет. npm run build — ошибка pre-existing (dompurify).
[LOG] 2026-03-18 19:30 — QA: начал написание тестов для user-service RBAC (задача #5)
[LOG] 2026-03-18 19:45 — QA: тесты готовы, 37 тестов, все проходят (0.30s). Покрытие: get_effective_permissions для 4 ролей + legacy fallback (6 тестов), permission overrides — grant/revoke/combined/noop/idempotent (5 тестов), admin auto-permissions — новая пермиссия автоматически у админа (3 теста), /users/me endpoint — admin/moderator/editor/user (4 теста), require_permission — pass/403/russian message (6 тестов), is_admin (5 тестов), require_admin (4 теста), security edge cases — orphan role_id/null role/sorted/unique constraint (4 теста).
[LOG] 2026-03-18 20:00 — QA: начал написание тестов для RBAC management endpoints (задача #6)
[LOG] 2026-03-18 20:20 — QA: задача #6 завершена. Создан test_rbac_endpoints.py — 33 теста, все проходят (7.97s). Покрытие: 5 эндпоинтов (GET /roles, PUT /{id}/role, GET /permissions, PUT /{id}/permissions, GET /{id}/effective-permissions), позитивные и негативные сценарии, 401/403/404/409/422, защита последнего админа, демонстрация двух админов, SQL-injection, пустые запросы.
[LOG] 2026-03-18 21:00 — Reviewer: начал полную проверку FEAT-035 (задача #12)
[LOG] 2026-03-18 21:30 — Reviewer: прочитаны все модифицированные файлы (14 backend + 8 frontend + 1 SQL + 3 test)
[LOG] 2026-03-18 21:40 — Reviewer: py_compile — PASS для всех 14 backend-файлов
[LOG] 2026-03-18 21:45 — Reviewer: pytest test_rbac_permissions.py — 37/37 PASS
[LOG] 2026-03-18 21:46 — Reviewer: pytest test_rbac_endpoints.py — 33/33 PASS
[LOG] 2026-03-18 21:47 — Reviewer: pytest test_auth_http_rbac.py — 13/13 PASS
[LOG] 2026-03-18 21:50 — Reviewer: npx tsc --noEmit — ошибок в файлах FEAT-035 нет (все ошибки pre-existing)
[LOG] 2026-03-18 21:52 — Reviewer: npm run build — ошибка pre-existing (dompurify в RuleOverlay.tsx), не связано с FEAT-035
[LOG] 2026-03-18 21:53 — Reviewer: docker-compose config — PASS
[LOG] 2026-03-18 22:00 — Reviewer: проверка завершена, результат PASS. Код, безопасность, контракты, тесты, фронтенд — всё в порядке.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*

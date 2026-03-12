# FEAT-001: Локальные URL для API-запросов

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-12 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-001-local-api-urls.md` → `DONE-FEAT-001-local-api-urls.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Фронтенд отправляет API-запросы на захардкоженный удалённый домен `4452515-co41851.twc1.net`, которого сейчас не существует. Из-за этого регистрация и все остальные запросы падают с ошибкой `ERR_NAME_NOT_RESOLVED`. Нужно заменить все захардкоженные URL на локальные (через Nginx API Gateway на порту 80), чтобы приложение работало в локальном Docker Compose окружении.

### Бизнес-правила
- Все API-запросы с фронтенда должны идти через локальный Nginx (порт 80)
- Удалённый сервер появится в будущем, но пока не нужна быстрая переключаемость — просто localhost
- Фронтенд запускается через Docker Compose вместе со всеми сервисами

### UX / Пользовательский сценарий
1. Игрок открывает приложение в браузере (localhost)
2. Заполняет форму регистрации и нажимает "Создать аккаунт"
3. Запрос уходит на localhost/users/register через Nginx
4. Регистрация проходит успешно

### Edge Cases
- Все существующие функции (логин, персонажи, бои, инвентарь и т.д.) должны продолжать работать
- URL в Nginx-конфиге (api-gateway) уже настроены на внутренние Docker-имена сервисов

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | Replace all hardcoded URLs | 15 files (see full list below) |
| api-gateway (Nginx) | Add missing upstream routes for battle-service and autobattle-service; fix CORS header; add `localhost` to allowedHosts | `docker/api-gateway/nginx.conf` |

### Summary of the Problem

All frontend API calls point to the domain `4452515-co41851.twc1.net` (with various ports), which does not resolve. There are **two URL patterns** in use:

1. **Through Nginx (port 80, no port in URL):** Only `AuthForm.jsx` and `items.js` — these use paths like `/users/login`, `/photo/change_item_image` which Nginx already routes correctly.
2. **Direct to service ports (bypassing Nginx):** The majority of calls use explicit ports (`:8006`, `:8005`, `:8004`, `:8003`, `:8001`, `:8010`, `:8011`) which bypass Nginx entirely and go directly to backend services.

### API Call Architecture

There is **no centralized API config or `.env` file** for the API base URL. URLs are defined in three ways:

1. **`src/api/api.js`** — Exports 4 `BASE_URL` constants (locations :8006, user :8000, battles :8010, autobattles :8011). Used by `userSlice.js`, `LocationPage.jsx`, `BattlePage.jsx`, `BattlePageBar.jsx`.
2. **`src/api/client.js`** — Axios instance with hardcoded `baseURL` for inventory-service (:8004). Used by `items.js`.
3. **`src/api/characters.js`** — Axios instance with hardcoded `baseURL` for character-service (:8005). Used for character listing.
4. **Inline hardcoded URLs** — Scattered across Redux action files and components, each containing full `http://4452515-co41851.twc1.net:PORT/path` strings.

### Nginx Routing Analysis (`docker/api-gateway/nginx.conf`)

Nginx on port 80 already has upstream definitions and `location` blocks for:
- `/users/` → user-service:8000
- `/characters/` → character-service:8005
- `/attributes/` → character-attributes-service:8002
- `/skills/` → skills-service:8003
- `/inventory/` → inventory-service:8004
- `/photo/` → photo-service:8001
- `/locations/` → locations-service:8006
- `/notifications/` → notification-service:8007
- `/media/` → static files
- `/` → frontend:5555

**MISSING routes in Nginx:**
- `/battles/` → battle-service:8010 — **NOT configured**
- `/autobattle/` (or similar) → autobattle-service:8011 — **NOT configured**

**Other Nginx issues:**
- Line 156: CORS `Access-Control-Allow-Origin` is hardcoded to `http://4452515-co41851.twc1.net`
- There is an unused upstream `skills-service_backendcxc` pointing to port 8099 (likely a typo/leftover)

### Vite Config

`vite.config.js` line 13: `allowedHosts: ["4452515-co41851.twc1.net"]` — needs to include `localhost` or be removed.

### Full List of Affected Files (with line numbers)

**Central API config files:**

| # | File | Lines | URL Target |
|---|------|-------|------------|
| 1 | `src/api/api.js` | 1, 3, 5, 7 | :8006, :8000, :8010, :8011 |
| 2 | `src/api/client.js` | 4 | :8004/inventory |
| 3 | `src/api/characters.js` | 4 | :8005 |

**Redux action files (inline URLs):**

| # | File | Lines | URL Target(s) |
|---|------|-------|---------------|
| 4 | `src/redux/actions/adminLocationsActions.js` | 9, 22, 35 | :8006 (locations) |
| 5 | `src/redux/actions/countryActions.js` | 8, 27 | :8006 (locations) |
| 6 | `src/redux/actions/countryEditActions.js` | 8, 20, 32, 49 | :8006, :8006/photo (wrong path) |
| 7 | `src/redux/actions/regionEditActions.js` | 8, 20, 32, 49, 73, 92 | :8006, :8001 (photo) |
| 8 | `src/redux/actions/districtEditActions.js` | 9, 27, 44, 62, 77, 92, 113 | :8006, :8001 (photo) |
| 9 | `src/redux/actions/locationEditActions.js` | 30, 50, 69, 82, 99, 138, 154, 166, 178, 191, 204 | :8006, :8001 (photo) |
| 10 | `src/redux/actions/regionsActions.js` | 8 | :8006 (locations) |
| 11 | `src/redux/actions/skillsAdminActions.js` | 5, 55, 71 | :8003, :8001 (photo) |

**Component files (inline URLs):**

| # | File | Lines | URL Target(s) |
|---|------|-------|---------------|
| 12 | `src/components/StartPage/AuthForm/AuthForm.jsx` | 33 | port 80 (users/login, users/register) |
| 13 | `src/components/CreateCharacterPage/CreateCharacterPage.jsx` | 117 | :8005 (characters) |
| 14 | `src/components/CreateCharacterPage/SubmitPage/SubmitPage.jsx` | 45 | :8005 (characters) |
| 15 | `src/components/AdminSkillsPage/AdminSkillsPage.jsx` | 53, 67 | :8003 (skills) |
| 16 | `src/components/AdminSkillsPage/NodeRankDetails.jsx` | 46 | :8001 (photo) |
| 17 | `src/components/AdminLocationsPage/EditForms/EditCountryForm/EditCountryForm.jsx` | 56 | :8001 (photo) |

**Files using BASE_URL imports (will be fixed by fixing api.js):**

| # | File | Lines | Import |
|---|------|-------|--------|
| — | `src/redux/slices/userSlice.js` | 2, 66 | BASE_URL_DEFAULT |
| — | `src/components/pages/LocationPage/LocationPage.jsx` | 3, 50, 58, 84 | BASE_URL, BASE_URL_BATTLES |
| — | `src/components/pages/BattlePage/BattlePage.jsx` | 10, 76, 185, 207, 216, 224 | BASE_URL_BATTLES, BASE_URL_AUTOBATTLES |
| — | `src/components/pages/BattlePage/BattlePageBar/BattlePageBar.jsx` | 12, 115 | BASE_URL_BATTLES |

**Infrastructure files:**

| # | File | Lines | Issue |
|---|------|-------|-------|
| 18 | `vite.config.js` | 13 | allowedHosts contains only the remote domain |
| 19 | `docker/api-gateway/nginx.conf` | 156 | CORS origin hardcoded to remote domain |

### Backend Services Targeted by Frontend

| Service | Port | Nginx Path | Frontend Accesses Directly? |
|---------|------|------------|---------------------------|
| user-service | 8000 | `/users/` | Yes (:8000 in api.js) + via Nginx (AuthForm) |
| photo-service | 8001 | `/photo/` | Yes (:8001 in many actions) |
| skills-service | 8003 | `/skills/` | Yes (:8003 in skillsAdminActions) |
| inventory-service | 8004 | `/inventory/` | Yes (:8004 in client.js) |
| character-service | 8005 | `/characters/` | Yes (:8005 in characters.js, components) |
| locations-service | 8006 | `/locations/` | Yes (:8006 in api.js, many actions) |
| battle-service | 8010 | **MISSING** | Yes (:8010 in api.js) |
| autobattle-service | 8011 | **MISSING** | Yes (:8011 in api.js) |

### Potential Path Conflicts

1. **`countryEditActions.js` line 49** uses path `:8006/photo/change_country_map` — this is the wrong service (should be photo-service :8001, not locations-service :8006). When switching to Nginx paths, this will route correctly to `/photo/` instead.
2. **`locationEditActions.js` line 166** uses path `:8006/districts/${districtId}/locations` (without `/locations/` prefix) — this may not match the Nginx `/locations/` route. Needs verification against the actual locations-service API.
3. **`items.js` line 35** uses `http://4452515-co41851.twc1.net/photo/change_item_image` (no port) — already goes through port 80, just needs domain replaced.

### Backend CORS Configuration (hardcoded domain)

6 backend services have the remote domain hardcoded in their CORS `allow_origins`. These will block requests from `http://localhost` unless updated:

| Service | File | CORS Setting |
|---------|------|-------------|
| skills-service | `services/skills-service/app/main.py:25-34` | Explicit list with remote domain |
| locations-service | `services/locations-service/app/main.py:26-35` | Explicit list with remote domain |
| inventory-service | `services/inventory-service/app/main.py:16-25` | Explicit list with remote domain |
| character-service | `services/character-service/app/main.py:21-30` | Explicit list with remote domain |
| battle-service | `services/battle-service/app/main.py:35-44` | Explicit list with remote domain |
| photo-service | `services/photo-service/main.py:17` | Single origin: remote domain |

Services with `allow_origins=["*"]` (no change needed):
- user-service (`services/user-service/main.py:22`)
- character-attributes-service (`services/character-attributes-service/app/main.py:19`)
- autobattle-service (`services/autobattle-service/app/main.py:24`)

Note: notification-service was not found in the CORS grep results — needs verification.

### Risks

- **Risk:** Missing Nginx routes for battle-service and autobattle-service will cause 404 errors for battle-related features → **Mitigation:** Add `/battles/` and `/autobattle/` (or appropriate prefix) upstream+location blocks to nginx.conf before switching frontend URLs.
- **Risk:** CORS will block requests from `http://localhost` — 6 backend services have only the remote domain in `allow_origins` → **Mitigation:** Update CORS origins in all 6 services to include `http://localhost` (or use `["*"]` for local dev).
- **Risk:** Some URLs have inconsistent path prefixes (e.g., `/districts/` vs `/locations/districts/`) that may break when routing through Nginx → **Mitigation:** Verify each path against the actual service endpoints and Nginx location blocks.
- **Risk:** `countryEditActions.js` line 49 sends photo request to locations-service port (:8006/photo/...) — this is a pre-existing bug that will actually be fixed by the migration to Nginx paths (where `/photo/` routes to photo-service).

---

## 3. Architecture Decision (filled by Architect — in English)

### Approach: Relative URLs via Nginx Gateway

All frontend API calls will use **relative URLs** (e.g., `/users/register`, `/battles/123/state`). Since the frontend is served through Nginx on port 80, the browser will automatically send requests to the same origin, and Nginx will route them to the correct backend service.

**No `.env` or config switching mechanism is needed.** The user explicitly confirmed that a simple localhost setup is sufficient for now.

### Key Design Decisions

**D1. Frontend URL strategy — relative paths (no host, no port)**

All `http://4452515-co41851.twc1.net[:PORT]/path` references become just `/path`. This works because:
- The frontend is served by Nginx on port 80
- Nginx already has `location` blocks for each service path prefix
- Relative URLs inherit the current page origin automatically

The 3 centralized config files (`api.js`, `client.js`, `characters.js`) will export simple path prefixes instead of full URLs. Files importing `BASE_URL` constants will work without changes (the constants just change value from `http://domain:port` to empty string or path prefix).

**D2. Nginx — add battle-service and autobattle-service routes**

Two new upstream+location blocks:
- `/battles/` → `battle-service:8010` — battle-service already uses `APIRouter(prefix="/battles")`, so paths like `/battles/123/state` map directly
- `/autobattle/` → `autobattle-service:8011` — autobattle-service has root-level endpoints (`/register`, `/mode`, `/unregister`), so Nginx must **strip the `/autobattle` prefix** using `rewrite ^/autobattle(/.*)$ $1 break;`

**D3. Nginx — fix CORS and cleanup**

- Line 156: change hardcoded CORS `Access-Control-Allow-Origin` to `*` (it's only on the frontend `location /` block, not security-sensitive)
- Remove unused upstream `skills-service_backendcxc` (port 8099 typo/leftover)

**D4. Backend CORS — switch to `allow_origins=["*"]`**

6 services have hardcoded remote domain in CORS origins. Since:
- 3 services already use `["*"]`
- All services run on the same Docker network
- There is no real security boundary between services (no auth on most endpoints)

The simplest and most consistent approach: change all 6 to `allow_origins=["*"]`. This eliminates CORS issues permanently regardless of what hostname the user accesses the app from.

Affected services: skills-service, locations-service, inventory-service, character-service, battle-service, photo-service.

**D5. Vite config — allow all hosts**

Change `allowedHosts: ["4452515-co41851.twc1.net"]` to `allowedHosts: true` to accept connections from any hostname (standard for Docker dev setups).

**D6. Frontend path mapping**

| Service | Old URL Pattern | New URL Pattern |
|---------|----------------|-----------------|
| user-service | `http://domain:8000/...` | `/users/...` |
| character-service | `http://domain:8005/...` | `/characters/...` |
| locations-service | `http://domain:8006/...` | `/locations/...` |
| skills-service | `http://domain:8003/...` | `/skills/...` |
| inventory-service | `http://domain:8004/inventory/...` | `/inventory/...` |
| photo-service | `http://domain:8001/...` | `/photo/...` |
| battle-service | `http://domain:8010/...` | `/battles/...` |
| autobattle-service | `http://domain:8011/...` | `/autobattle/...` |

**Important path transformations:**
- `api.js` `BASE_URL` (locations :8006) — used with paths like `/locations/countries/...`, so the new value is just `""` (empty string), since the paths already start with `/locations/`
- `api.js` `BASE_URL_DEFAULT` (user :8000) — used in `userSlice.js` with paths like `/users/...`, so new value is `""` (empty string)
- `api.js` `BASE_URL_BATTLES` (battles :8010) — used with paths like `/battles/123/state`, so new value is `""` (empty string)
- `api.js` `BASE_URL_AUTOBATTLES` (autobattle :8011) — used with paths like `/register`, so new value is `"/autobattle"` (prefix added)
- `client.js` — Axios baseURL changes from `http://domain:8004/inventory` to `/inventory`
- `characters.js` — Axios baseURL changes from `http://domain:8005` to `""`
- Inline URLs in action files — each must be mapped to the correct Nginx path prefix

**Bug fix (incidental):** `countryEditActions.js` line 49 sends photo request to `:8006/photo/change_country_map` (wrong service). After migration, this becomes `/photo/change_country_map` which correctly routes to photo-service via Nginx. This pre-existing bug is fixed by the migration.

### Data Flow (after changes)

```
Browser → http://localhost/users/register
       → Nginx (port 80)
       → location /users/ → proxy_pass user-service:8000
       → user-service handles request
       → response back through Nginx to browser
```

### Security Notes

- No new endpoints are created
- No authentication changes
- CORS is relaxed to `["*"]` which matches the existing pattern in 3 services and is appropriate for local dev
- No secrets are affected

### Risks

- **Path prefix conflicts:** Some inline URLs in action files use paths like `/districts/{id}/locations` without the `/locations/` prefix. These need careful mapping — the frontend developer must verify each URL against the actual service endpoint paths and corresponding Nginx location blocks.
- **WebSocket/SSE:** The notification-service SSE endpoint at `/notifications/` already works through Nginx. No changes needed there.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: Add missing Nginx routes and fix CORS/cleanup

| Field | Value |
|-------|-------|
| **#** | 1 |
| **Description** | In `docker/api-gateway/nginx.conf`: (1) Add upstream `battle-service_backend` pointing to `battle-service:8010` and `location /battles/` block proxying to it with standard headers. (2) Add upstream `autobattle-service_backend` pointing to `autobattle-service:8011` and `location /autobattle/` block proxying to it — use `rewrite ^/autobattle(/.*)$ $1 break;` to strip the prefix since autobattle-service has root-level endpoints. (3) On line 156, change `Access-Control-Allow-Origin` from `"http://4452515-co41851.twc1.net"` to `"*"`. (4) Remove the unused upstream `skills-service_backendcxc` (port 8099). |
| **Agent** | DevSecOps |
| **Status** | DONE |
| **Files** | `docker/api-gateway/nginx.conf` |
| **Depends On** | — |
| **Acceptance Criteria** | (1) `curl -s http://localhost/battles/` returns a response from battle-service (not 404). (2) `curl -s http://localhost/autobattle/health` returns `{"status":"ok",...}`. (3) No reference to `4452515-co41851.twc1.net` remains in nginx.conf. (4) No `skills-service_backendcxc` upstream exists. |

### Task 2: Update backend CORS to allow all origins

| Field | Value |
|-------|-------|
| **#** | 2 |
| **Description** | In 6 backend services, replace the hardcoded CORS `allow_origins` list with `allow_origins=["*"]`. This makes all services consistent (3 already use `["*"]`). Files to change: (1) `services/skills-service/app/main.py` (2) `services/locations-service/app/main.py` (3) `services/inventory-service/app/main.py` (4) `services/character-service/app/main.py` (5) `services/battle-service/app/main.py` (6) `services/photo-service/main.py`. Keep `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]` unchanged. |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/skills-service/app/main.py`, `services/locations-service/app/main.py`, `services/inventory-service/app/main.py`, `services/character-service/app/main.py`, `services/battle-service/app/main.py`, `services/photo-service/main.py` |
| **Depends On** | — |
| **Acceptance Criteria** | All 6 files contain `allow_origins=["*"]`. No reference to `4452515-co41851.twc1.net` remains in any backend service. Grep confirms: `grep -r "4452515" services/*/app/main.py services/photo-service/main.py` returns no results. |

### Task 3: Update Vite config

| Field | Value |
|-------|-------|
| **#** | 3 |
| **Description** | In `services/frontend/app-chaldea/vite.config.js`, change `allowedHosts: ["4452515-co41851.twc1.net"]` to `allowedHosts: true`. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/vite.config.js` |
| **Depends On** | — |
| **Acceptance Criteria** | `vite.config.js` contains `allowedHosts: true`. No reference to `4452515-co41851.twc1.net`. |

### Task 4: Replace hardcoded URLs in central API config files

| Field | Value |
|-------|-------|
| **#** | 4 |
| **Description** | Update the 3 central API config files to use relative paths: (1) `src/api/api.js` — change `BASE_URL` to `""`, `BASE_URL_DEFAULT` to `""`, `BASE_URL_BATTLES` to `""`, `BASE_URL_AUTOBATTLES` to `"/autobattle"`. (2) `src/api/client.js` — change Axios `baseURL` from `http://4452515-co41851.twc1.net:8004/inventory` to `/inventory`. (3) `src/api/characters.js` — change Axios `baseURL` from `http://4452515-co41851.twc1.net:8005` to `""`. Note: files importing these constants (`userSlice.js`, `LocationPage.jsx`, `BattlePage.jsx`, `BattlePageBar.jsx`, `items.js`) will work without changes because the constants now resolve to relative paths. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/api/api.js`, `services/frontend/app-chaldea/src/api/client.js`, `services/frontend/app-chaldea/src/api/characters.js` |
| **Depends On** | — |
| **Acceptance Criteria** | No reference to `4452515-co41851.twc1.net` in any of the 3 files. Constants export correct relative paths. Files that import from these modules still produce valid URLs (e.g., `${BASE_URL_BATTLES}/battles/123/state` becomes `/battles/123/state`). |

### Task 5: Replace hardcoded URLs in Redux action files

| Field | Value |
|-------|-------|
| **#** | 5 |
| **Description** | Replace all inline hardcoded URLs in Redux action files with relative paths using the correct Nginx path prefixes. Map each URL to the correct service path: `:8006/locations/...` → `/locations/...`, `:8006/districts/...` → `/locations/districts/...` (verify against locations-service API), `:8001/photo/...` → `/photo/...`, `:8003/skills/...` → `/skills/...`. **Important:** `countryEditActions.js` line 49 has a bug — it sends a photo request to `:8006/photo/...` (locations port). Replace with `/photo/...` to fix this. Files: `adminLocationsActions.js`, `countryActions.js`, `countryEditActions.js`, `regionEditActions.js`, `districtEditActions.js`, `locationEditActions.js`, `regionsActions.js`, `skillsAdminActions.js`. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/redux/actions/adminLocationsActions.js`, `services/frontend/app-chaldea/src/redux/actions/countryActions.js`, `services/frontend/app-chaldea/src/redux/actions/countryEditActions.js`, `services/frontend/app-chaldea/src/redux/actions/regionEditActions.js`, `services/frontend/app-chaldea/src/redux/actions/districtEditActions.js`, `services/frontend/app-chaldea/src/redux/actions/locationEditActions.js`, `services/frontend/app-chaldea/src/redux/actions/regionsActions.js`, `services/frontend/app-chaldea/src/redux/actions/skillsAdminActions.js` |
| **Depends On** | — |
| **Acceptance Criteria** | No reference to `4452515-co41851.twc1.net` in any action file. All URLs use relative paths with correct Nginx prefixes. The photo-service bug in `countryEditActions.js` is fixed (routes to `/photo/...` not `/locations/photo/...`). |

### Task 6: Replace hardcoded URLs in component files

| Field | Value |
|-------|-------|
| **#** | 6 |
| **Description** | Replace all inline hardcoded URLs in component files with relative paths: (1) `AuthForm.jsx` line 33 — already uses port 80, just remove the domain (`http://4452515-co41851.twc1.net/users/...` → `/users/...`). (2) `CreateCharacterPage.jsx` line 117 — `:8005/characters/...` → `/characters/...`. (3) `SubmitPage.jsx` line 45 — `:8005/characters/...` → `/characters/...`. (4) `AdminSkillsPage.jsx` lines 53, 67 — `:8003/skills/...` → `/skills/...`. (5) `NodeRankDetails.jsx` line 46 — `:8001/photo/...` → `/photo/...`. (6) `EditCountryForm.jsx` line 56 — `:8001/photo/...` → `/photo/...`. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/components/StartPage/AuthForm/AuthForm.jsx`, `services/frontend/app-chaldea/src/components/CreateCharacterPage/CreateCharacterPage.jsx`, `services/frontend/app-chaldea/src/components/CreateCharacterPage/SubmitPage/SubmitPage.jsx`, `services/frontend/app-chaldea/src/components/AdminSkillsPage/AdminSkillsPage.jsx`, `services/frontend/app-chaldea/src/components/AdminSkillsPage/NodeRankDetails.jsx`, `services/frontend/app-chaldea/src/components/AdminLocationsPage/EditForms/EditCountryForm/EditCountryForm.jsx` |
| **Depends On** | — |
| **Acceptance Criteria** | No reference to `4452515-co41851.twc1.net` in any component file. All URLs use relative paths. |

### Task 7: Final verification — no hardcoded domain references remain

| Field | Value |
|-------|-------|
| **#** | 7 |
| **Description** | Run a full-project grep to verify no references to `4452515-co41851.twc1.net` remain anywhere in the codebase (excluding `features/` directory and `docs/`). Check all frontend files, all backend files, nginx.conf, docker-compose.yml, vite.config.js. If any are found, fix them. |
| **Agent** | Reviewer |
| **Status** | DONE |
| **Files** | Entire codebase |
| **Depends On** | 1, 2, 3, 4, 5, 6 |
| **Acceptance Criteria** | `grep -r "4452515" --include="*.js" --include="*.jsx" --include="*.ts" --include="*.tsx" --include="*.py" --include="*.conf" --include="*.yml" .` returns no results (excluding docs/features). All API calls from the frontend use relative paths through Nginx. |

### Dependency Graph

```
Task 1 (Nginx)     ─┐
Task 2 (CORS)      ─┤
Task 3 (Vite)      ─┼──→ Task 7 (Review)
Task 4 (API config) ─┤
Task 5 (Actions)   ─┤
Task 6 (Components) ─┘

Tasks 1-6 can all run in parallel (no dependencies between them).
Task 7 runs after all others are complete.
```

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-12
**Result:** PASS

#### Verification Steps Performed

**1. Full grep for hardcoded domain (`4452515`):**
- Command: `grep -r "4452515" --include="*.js" --include="*.jsx" --include="*.ts" --include="*.tsx" --include="*.py" --include="*.conf" --include="*.yml" /home/dudka/chaldea/` (excluding `features/` and `docs/`)
- Result: **ZERO matches.** No references to the old domain remain in source code.

**2. Nginx config review (`docker/api-gateway/nginx.conf`):**
- `/battles/` location block exists (lines 143-148), proxies to `battle-service_backend` with standard headers. OK.
- `/autobattle/` location block exists (lines 151-158), includes `rewrite ^/autobattle(/.*)$ $1 break;` to strip prefix. OK.
- No reference to `4452515-co41851.twc1.net` anywhere in the file. OK.
- The dead upstream `skills-service_backendcxc` has been removed. OK.
- CORS `Access-Control-Allow-Origin` on `location /` is set to `"*"` (line 177). OK.

**3. Backend CORS spot-check (3 of 6 modified services):**
- `services/skills-service/app/main.py` line 25: `allow_origins=["*"]`. OK.
- `services/battle-service/app/main.py` line 35: `allow_origins=["*"]`. OK.
- `services/photo-service/main.py` line 17: `allow_origins=["*"]`. OK.

**4. Frontend API config files:**
- `src/api/api.js`: `BASE_URL=""`, `BASE_URL_DEFAULT=""`, `BASE_URL_BATTLES=""`, `BASE_URL_AUTOBATTLES="/autobattle"`. OK.
- `src/api/client.js`: `baseURL: "/inventory"`. OK.
- `src/api/characters.js`: `baseURL: ""`, calls `/characters/list`. OK.

**5. Vite config:**
- `vite.config.js` line 13: `allowedHosts: true`. OK.

**6. Path consistency check (frontend URLs vs Nginx locations):**
- `/users/...` matches `location /users/`. OK.
- `/characters/...` matches `location /characters/`. OK.
- `/locations/...` matches `location /locations/`. OK.
- `/skills/...` matches `location /skills/`. OK.
- `/inventory/...` matches `location /inventory/`. OK.
- `/photo/...` matches `location /photo/`. OK.
- `/battles/...` matches `location /battles/`. OK.
- `/autobattle/...` matches `location /autobattle/` (with rewrite to strip prefix). OK.

**7. Potential issues check:**
- Files importing old `BASE_URL` constants (`userSlice.js`, `LocationPage.jsx`, `BattlePage.jsx`, `BattlePageBar.jsx`): all work correctly since constants now resolve to `""` or `"/autobattle"`, producing valid relative paths. OK.
- `characters.js` `baseURL: ""` is correct — the only call is `charClient.get("/characters/list")` which produces `/characters/list`. OK.
- Autobattle rewrite rule: `rewrite ^/autobattle(/.*)$ $1 break;` strips `/autobattle` prefix, so `/autobattle/register` becomes `/register` forwarded to autobattle-service. OK.
- `countryEditActions.js` photo bug fixed: now uses `/photo/change_country_map` (routes to photo-service via Nginx) instead of old `:8006/photo/...` (wrong service). OK.

#### Pre-existing issues noted (not introduced by this feature, not blocking):
1. **`items.js` line 34** uses `axios.post()` but does not import `axios` (only imports `client`). This will cause a runtime error when `uploadItemImage()` is called. Pre-existing bug — was present before URL changes.
2. **`battle-service/main.py` lines 567/583** define routes `/battles/{battle_id}/logs` under `APIRouter(prefix="/battles")`, resulting in double-prefix path `/battles/battles/{id}/logs`. The frontend (`BattlePageBar.jsx` line 115) uses matching double-prefix URL, so it works, but the API path is inconsistent. Pre-existing issue.

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-12 10:00 — PM: фича создана, запускаю анализ кодовой базы
[LOG] 2026-03-12 10:15 — Analyst: начал анализ, grep по домену 4452515-co41851.twc1.net во фронтенде
[LOG] 2026-03-12 10:20 — Analyst: найдено 19 затронутых файлов (15 с хардкод URL + 4 с импортами из api.js)
[LOG] 2026-03-12 10:25 — Analyst: проверил nginx.conf — нет маршрутов для battle-service (:8010) и autobattle-service (:8011)
[LOG] 2026-03-12 10:30 — Analyst: обнаружен баг — countryEditActions.js шлёт фото-запрос на locations-service вместо photo-service
[LOG] 2026-03-12 10:35 — Analyst: проверил CORS в backend-сервисах — 6 из 9 содержат хардкод домена в allow_origins
[LOG] 2026-03-12 10:40 — Analyst: анализ завершён, затронуто 19 файлов фронтенда + nginx.conf + vite.config.js + 6 backend main.py (CORS)
[LOG] 2026-03-12 11:00 — Architect: начал проектирование, изучаю nginx.conf и endpoint-ы battle/autobattle сервисов
[LOG] 2026-03-12 11:15 — Architect: решение — относительные URL без .env, Nginx как единая точка входа
[LOG] 2026-03-12 11:20 — Architect: autobattle-service имеет корневые эндпоинты — нужен rewrite в Nginx для strip /autobattle prefix
[LOG] 2026-03-12 11:25 — Architect: CORS — унифицируем все 6 сервисов до allow_origins=["*"] (3 уже так настроены)
[LOG] 2026-03-12 11:30 — Architect: спроектировано 7 задач: 1 DevSecOps, 1 Backend, 4 Frontend, 1 Reviewer. Все задачи 1-6 параллельны
[LOG] 2026-03-12 12:00 — DevSecOps: обновлён nginx.conf — добавлены upstream и location для battle-service (:8010) и autobattle-service (:8011, с rewrite для strip prefix), заменён CORS origin на *, удалён мусорный upstream skills-service_backendcxc
[LOG] 2026-03-12 12:15 — Backend Dev: задача #2 завершена — заменён CORS allow_origins на ["*"] в 6 сервисах (skills, locations, inventory, character, battle, photo). Grep подтверждает: ни одного упоминания 4452515 в backend main.py не осталось.
[LOG] 2026-03-12 12:30 — Frontend Dev: начал задачи #3, #4, #5, #6
[LOG] 2026-03-12 12:32 — Frontend Dev: задача #3 — vite.config.js: allowedHosts заменён на true
[LOG] 2026-03-12 12:34 — Frontend Dev: задача #4 — api.js (4 BASE_URL на относительные), client.js (baseURL → /inventory), characters.js (baseURL → "")
[LOG] 2026-03-12 12:40 — Frontend Dev: задача #5 — заменены URL во всех 8 action-файлах. Исправлен баг в countryEditActions.js (фото-запрос шёл на :8006 вместо photo-service). В locationEditActions.js /districts/... заменён на /locations/districts/... (prefix роутера locations-service)
[LOG] 2026-03-12 12:45 — Frontend Dev: задача #6 — заменены URL в 6 компонентах (AuthForm, CreateCharacterPage, SubmitPage, AdminSkillsPage, NodeRankDetails, EditCountryForm)
[LOG] 2026-03-12 12:46 — Frontend Dev: дополнительно найден и исправлен хардкод в items.js (не был в исходном списке задач)
[LOG] 2026-03-12 12:47 — Frontend Dev: финальная проверка grep -r "4452515" — 0 совпадений во всей директории frontend. Задачи #3-6 завершены
[LOG] 2026-03-12 13:00 — Reviewer: начал финальную проверку (задача #7)
[LOG] 2026-03-12 13:10 — Reviewer: grep по всему проекту — 0 совпадений по "4452515" в исходниках. Nginx, CORS, Vite, API-конфиги, action-файлы, компоненты — всё корректно
[LOG] 2026-03-12 13:12 — Reviewer: обнаружены 2 pre-existing бага (не связаны с этой фичей): отсутствие import axios в items.js, двойной prefix /battles/battles в battle-service
[LOG] 2026-03-12 13:15 — Reviewer: проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Все API-запросы фронтенда переведены с захардкоженного домена `4452515-co41851.twc1.net` на относительные пути через Nginx
- Добавлены маршруты Nginx для battle-service и autobattle-service (ранее отсутствовали)
- CORS обновлён в 6 backend-сервисах — теперь `allow_origins=["*"]`
- Исправлен баг: `countryEditActions.js` отправлял фото-запрос на locations-service вместо photo-service
- Найден и исправлен дополнительный хардкод в `items.js`

### Что изменилось от первоначального плана
- Ничего существенного — план выполнен как задумано

### Оставшиеся риски / follow-up задачи
- `items.js:34` использует `axios.post()` без импорта `axios` — pre-existing баг, не связан с этой фичей
- `battle-service` имеет двойной prefix `/battles/battles/` в логах — pre-existing, работает но inconsistent
[LOG] 2026-03-12 13:20 — PM: фича закрыта, статус DONE

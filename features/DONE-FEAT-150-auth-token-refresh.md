# FEAT-150: Устойчивая авторизация — логин не слетает при перезагрузке сервера, refresh-токены

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-07-17 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-150-auth-token-refresh.md` → `DONE-FEAT-150-auth-token-refresh.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас при перезагрузке сервера (или после деплоя) авторизация пользователя слетает: запрос на `/me` возвращает 401, и чтобы всё снова заработало, приходится вручную выходить из аккаунта и логиниться заново. Нужно сделать механизм авторизации устойчивым:
- Логин не должен слетать при рестартах/деплоях сервера.
- Токен должен автоматически обновляться (refresh), либо сессия должна корректно восстанавливаться без ручного relogin.
- Пользователь заметить рестарт сервера не должен (максимум — кратковременная задержка).

### Бизнес-правила
- Пользователь остаётся залогиненным между перезагрузками/деплоями сервера.
- Если токен истёк или инвалидирован — фронтенд должен автоматически попытаться обновить его (refresh), а не выбрасывать пользователя.
- Полный logout происходит только: по явному действию пользователя, либо когда refresh невозможен (например, истёк refresh-токен).
- При невозможности восстановить сессию — корректный редирект на страницу логина с понятным сообщением на русском, без «зависшего» сломанного состояния.

### UX / Пользовательский сценарий
1. Игрок залогинен, играет.
2. Происходит деплой / рестарт backend-сервисов.
3. Игрок продолжает пользоваться сайтом: очередной запрос получает 401 → фронтенд прозрачно обновляет токен и повторяет запрос.
4. Игрок ничего не замечает, relogin не требуется.

### Edge Cases
- Несколько параллельных запросов одновременно получают 401 — refresh должен выполняться один раз, а не лавиной.
- Refresh-токен сам истёк/невалиден — аккуратный logout + редирект на логин.
- WebSocket-соединения (чат, бой) — переподключение с новым токеном.
- Пользователь открыл несколько вкладок.

### Вопросы к пользователю (если есть)
- [x] Менять ли JWT-секрет (сейчас на проде, вероятно, публично известный fallback `your-secret-key`)? → **Ответ: нет, отдельной задачей.** Зафиксировать как CRITICAL-issue в `docs/ISSUES.md`, в рамках этой фичи не трогать.
- [x] Stateless refresh-токены или с хранением в БД (отзыв сессий)? → **Ответ: простой stateless-вариант, без БД.**
- [x] Время жизни access-токена? → **Ответ: оставить 20 часов** (refresh — 7 дней, как сейчас).

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Root Cause

The initial hypothesis ("JWT secret is random per process start") is **NOT confirmed**. The secret is stable across restarts:

- `services/user-service/auth.py:13` — `SECRET_KEY = os.environ["JWT_SECRET_KEY"]` (fail-fast, covered by `tests/test_jwt_secret.py`).
- `docker-compose.yml:227` — `JWT_SECRET_KEY: ${JWT_SECRET_KEY:-your-secret-key}`. The local/server `.env` does **not** define `JWT_SECRET_KEY` (verified: repo `.env` has only MySQL/S3/PMA keys), so the deterministic fallback `your-secret-key` is used. Deterministic = tokens survive restarts cryptographically.
- Tokens are fully stateless JWTs — nothing is stored server-side (no Redis/DB/memory token store anywhere in user-service). A restart cannot invalidate them.

The **actual root cause is a combination of three frontend/lifecycle issues**:

1. **Short access-token TTL with no refresh flow.** `auth.py:15` — `ACCESS_TOKEN_EXPIRE_MINUTES = 1200` (20 hours); `auth.py:16` — refresh token lives 7 days. The backend already issues a refresh token at login/register (`main.py:196,214`) and already has a working `POST /users/refresh` endpoint (`main.py:218-238`). **The frontend stores `refreshToken` in localStorage at login (`AuthForm.tsx:94-96`) and then never reads it — `/users/refresh` is never called anywhere in the frontend** (verified by grep: the only `refresh_token` occurrence in `src/` is AuthForm). So any access token older than 20h → permanent 401 until manual re-login. Deploys typically happen more than 20h apart, which is why users associate the 401 with restarts.

2. **`getMe()` deletes the (still valid) access token on transient server errors.** `src/redux/slices/userSlice.ts:61-87` uses raw `fetch`; on **any** non-OK response — including 502/503 from Nginx while user-service is restarting during a deploy — it throws, and the `catch` block executes `localStorage.removeItem("accessToken")` (`userSlice.ts:83`). A user who reloads the page (or whose app bootstraps) during the deploy window loses a perfectly valid token and is logged out. It does not distinguish 401 from 5xx/network errors.

3. **The global 401 handler only shows a toast.** `src/api/axiosSetup.ts:24-38` — the axios response interceptor toasts "Сессия истекла…" on 401 but performs no refresh, no retry, no redirect, no state cleanup. The app stays in a half-broken state.

Secondary defects in the existing `/users/refresh` endpoint (relevant when wiring it up):
- `main.py:219` — `refresh_token: str` is a bare function param → FastAPI treats it as a **query parameter**. Refresh tokens in query strings end up in Nginx access logs (security issue). Should become a JSON body.
- `main.py:237` — the refreshed access token is built from `{"sub": user.email}` only, **dropping the `current_character` claim** that login adds (`main.py:210-211`). Currently harmless because `/users/me` reads `current_character` from the DB (`main.py:276-281`), but the asymmetry should be fixed or the claim retired.
- The endpoint does not rotate the refresh token (returns only a new `access_token`) — acceptable for stateless design, but the Architect should make this an explicit decision.
- No response schema / not returning `refresh_token`, and errors are English "Could not validate credentials" (project rule: user-facing errors in Russian).

**Security finding (in scope of this feature):** since `.env` lacks `JWT_SECRET_KEY`, dev — and very likely prod — runs on the publicly known fallback secret `your-secret-key`. Anyone can mint valid admin JWTs. Must be confirmed/fixed for prod during this feature (see Open Questions).

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| user-service | fix/extend `/users/refresh` (body param, `current_character` claim, optional rotation), possibly longer/configurable TTLs | `auth.py`, `main.py` (lines 179-238), `schemas.py` |
| frontend | refresh-on-401 interceptor with single-flight, retry of failed request, fix `getMe()` error discrimination, logout+redirect only when refresh fails, WS reconnect with fresh token | `src/api/axiosSetup.ts`, `src/api/client.js` (separate axios instance!), `src/redux/slices/userSlice.ts`, `src/components/StartPage/AuthForm/AuthForm.tsx`, `src/hooks/useWebSocket.ts`, `src/hooks/useBattleWebSocket.ts`, `src/hooks/useDungeonWebSocket.ts` |
| docker / env | ensure `JWT_SECRET_KEY` is set to a real secret in prod `.env`; optional TTL env vars | `docker-compose.yml:227`, `.env.example`, prod `.env` on VPS |
| all other backend services | **no changes** — they validate tokens by HTTP call to user-service `/users/me` (see Cross-Service Dependencies) | — |

### Existing Patterns

- **user-service:** sync SQLAlchemy, Pydantic <2.0, Alembic present (auto-migration on start, `alembic_version_user`, latest migration `0025_add_gathering_permissions.py`). JWT via `python-jose`, HS256. Flat layout (`auth.py`, `main.py` at service root, no `app/` package).
- **Token issuance:** `create_access_token` / `create_refresh_token` in `auth.py:21-41`; both embed `sub` (email), `role`, `exp`; login also embeds `current_character`.
- **Frontend token storage:** `localStorage` keys `accessToken` and `refreshToken` (AuthForm.tsx:92-96).
- **Frontend HTTP layers (all must be covered by the refresh flow):**
  1. Default axios instance + global interceptors in `src/api/axiosSetup.ts` (attaches Bearer from localStorage, toasts on 401/403) — used by most `src/api/*.ts` modules.
  2. **Separate axios instance** `src/api/client.js` (baseURL `/inventory`, own request interceptor, own response interceptor that swallows status codes by converting to `Error`) — global interceptors do NOT apply to it.
  3. Raw `fetch` call sites bypassing axios entirely: `src/redux/slices/userSlice.ts` (getMe), `src/components/pages/SelectCharacterPage/SelectCharacterPage.tsx`, `src/components/CommonComponents/Header/CharacterSwitchDropdown.tsx`, `src/api/spellcheck.ts`.
- **App bootstrap:** `App.tsx:78-90` — if `accessToken` exists dispatch `getMe()`, else `setAuthInitialized()`. `ProtectedRoute.tsx` waits for `authInitialized`, redirects to `/` when no role (this is the FEAT-055 pattern — do not regress it).
- **WebSocket auth:** token passed as `?token=` query param, read from localStorage at (re)connect time: `useWebSocket.ts:131,148` (notifications; has `UNAUTHORIZED_RECONNECT_DELAY` handling at :424-431 and re-reads token on reconnect), `useBattleWebSocket.ts:132`, `useDungeonWebSocket.ts:83` (these two have **no** unauthorized-close special handling).

### Cross-Service Dependencies

- **Only user-service decodes JWTs.** No other service imports the secret (verified by grep for `jwt.decode` / `JWT_SECRET` across `services/`).
- **12 services** carry an `auth_http.py` that validates tokens by calling `GET user-service /users/me` with the Bearer header: photo, dungeon, inventory, character-attributes, autobattle, battle, locations, skills, character, battle-pass, party, notification. WebSocket auth in notification-service (`app/auth_http.py:authenticate_websocket`), battle-service (`app/main.py:4355-4362`) and dungeon-service does the same HTTP call.
- **Consequence:** changing token TTLs, adding claims, or adding refresh logic requires **zero changes** in the other 12 services — as long as `/users/me` keeps accepting the access token, everything downstream keeps working. Changing the *secret* only requires that user-service itself restarts with the new value.
- Frontend → user-service: `POST /users/login`, `POST /users/register`, `POST /users/refresh` (exists, currently unused), `GET /users/me` (bootstrap via `getMe()`).
- Nginx routes `/users/*` to user-service in both `docker/api-gateway/nginx.conf` and `nginx.prod.conf` — `/users/refresh` is already reachable; no gateway changes needed unless rate-limiting the refresh endpoint is desired.

### DB Changes

- **None required** for the minimal stateless design — refresh tokens are already signed JWTs validated with the same secret; no persistence exists today.
- **If** the Architect opts for revocable/rotating refresh tokens: new table (e.g. `refresh_tokens`: id, user_id FK → users.id, token_hash, expires_at, revoked_at, created_at) in **user-service** via Alembic migration `0026_*` (Alembic present, sync, `alembic_version_user`). No other service reads user-service auth tables.
- Redis is available in the stack but user-service currently has **no Redis dependency** — adding one is possible but would be a new dependency (requires user decision per "Ask When in Doubt").

### Risks

- **Risk:** Users hold old tokens in localStorage at deploy time → Mitigation: keep the same secret and claims; old access tokens stay valid until `exp`, old refresh tokens (issued since login) work with `/users/refresh` immediately. If prod secret is rotated away from the insecure fallback, **all sessions drop exactly once** — must be communicated/coordinated.
- **Risk:** Refresh storm — N parallel requests all get 401 and each triggers a refresh → Mitigation: single-flight refresh (module-level shared promise), queue the failed requests, retry them once with the new token; explicitly required by the feature brief's edge cases.
- **Risk:** Multi-tab races — two tabs refresh simultaneously → With stateless non-rotating refresh tokens this is idempotent (both get valid access tokens). If token **rotation** is chosen, one-time refresh tokens break the second tab → needs storage event sync or reuse-window; flag to Architect.
- **Risk:** Coverage gaps — `client.js` axios instance and the four raw-`fetch` call sites bypass the global interceptor → Mitigation: refresh logic must be shared (helper) and wired into all three layers, or fetch call sites migrated to the intercepted client; per project rules any touched `.jsx`/`.js` logic files (`client.js`) must migrate to TS.
- **Risk:** `getMe()` treats 502/503 as auth failure and deletes the token → Mitigation: only clear tokens on real 401 (after a failed refresh); on network/5xx errors keep the token and surface a retry/loading state.
- **Risk:** WebSocket reconnect with expired token — hooks re-read localStorage on reconnect, which works only if the HTTP refresh flow has already updated it; battle/dungeon hooks lack unauthorized-close handling → Mitigation: on WS auth failure trigger the shared refresh, then reconnect (feature-brief edge case).
- **Risk:** Refresh token in URL query (`main.py:219` param and WS `?token=`) is logged by Nginx → Mitigation: move `/users/refresh` payload to JSON body; WS query-token is pre-existing behavior (out of scope, but note it).
- **Risk:** Refreshed access token silently loses `current_character` claim (`main.py:237`) → Mitigation: rebuild `token_data` the same way login does; currently mitigated because `/users/me` reads the DB column.
- **Risk:** Regressing FEAT-055 (F5 logout fix) — bootstrap/ProtectedRoute logic in `App.tsx` and `authInitialized` flow must keep working → Mitigation: keep `setAuthInitialized` semantics; logout+redirect only after refresh definitively fails.

### Prior Related Work

- `features/DONE-FEAT-028-fix-login-401.md` — prod login 401; root cause was bcrypt/passlib version conflict, not tokens. Introduced `config.py` Settings pattern. Not directly relevant, but confirms 401-vs-500 semantics of user-service auth.
- `features/DONE-FEAT-055-fix-admin-auth-persistence.md` — F5 logout bug; established the current bootstrap pattern (`App.tsx` getMe/setAuthInitialized + `ProtectedRoute` waiting on `authInitialized`) and removed StartPage's unconditional token clearing. The new refresh flow must build on, not replace, this pattern.

### Open Questions (for PM → user)

1. **Is `JWT_SECRET_KEY` set in the prod `.env` on the VPS (fallofgods.top)?** The repo `.env` does not set it, meaning the well-known fallback `your-secret-key` is likely live in prod — a critical security hole. Fixing it (rotating the secret) will log everyone out once. Do we rotate it as part of this feature?
2. Should refresh tokens be **revocable** (DB/Redis persistence, rotation on every refresh — more secure, enables "logout everywhere") or stay **stateless** (no DB changes, simpler, matches current design)? This determines whether an Alembic migration is needed.
3. Desired access-token TTL after the fix? Current 20h is long for an access token; with auto-refresh in place it could be shortened (e.g. 15-60 min) — or kept as-is to minimize change.

---

## 3. Architecture Decision (filled by Architect — in English)

### Summary of Explicit Decisions

| # | Decision | Choice | Justification |
|---|----------|--------|---------------|
| D1 | Refresh token storage | **Stateless JWT, no DB/Redis** | User decision. No new tables, no migrations. |
| D2 | Refresh token rotation | **Yes — stateless sliding window.** Every successful `/users/refresh` returns a **new refresh token** (7d from now) alongside the new access token. The old refresh token is NOT revoked (impossible statelessly) and stays valid until its original `exp`. | UX: active users are never force-logged-out (matches brief: "logout only on explicit action or when refresh is impossible"). Multi-tab safe: since nothing is revoked, two tabs refreshing concurrently both succeed; last-write-wins in localStorage and every stored token remains valid — no logout race. Accepted trade-off: a stolen refresh token can be extended indefinitely; revocation requires stateful storage, explicitly descoped by the user. |
| D3 | `current_character` claim on refresh | **Keep the claim; re-read from DB** (same `token_data` construction as login: `{"sub": user.email}` + `current_character` if not None). | Minimal diff, symmetric with login. DB re-read is actually *fresher* than login's snapshot (picks up character switches). Retiring the claim would touch login/`get_current_user` for zero gain. Correctness does not depend on it (`/users/me` reads the DB column), but asymmetry is removed. |
| D4 | Token type confusion | **New `type` claim** (`"access"` / `"refresh"`) added by `create_access_token` / `create_refresh_token`. Enforcement is *reject-known-wrong-type*: `get_current_user` rejects `type == "refresh"`; `/users/refresh` rejects `type == "access"`. Tokens **without** a `type` claim are accepted everywhere (legacy). | Backward compatible: all tokens issued before deploy lack `type` and keep working as before. Residual risk (legacy access/refresh tokens are interchangeable — they always were) self-expires within 7 days as legacy tokens age out. |
| D5 | TTLs | **Unchanged**: access 20h (`ACCESS_TOKEN_EXPIRE_MINUTES = 1200`), refresh 7d. | User decision. |
| D6 | JWT secret rotation | **Out of scope.** Recorded as CRITICAL issue #27 in `docs/ISSUES.md`. | User decision. |
| D7 | Frontend refresh mechanism | **One shared module** (`src/api/authToken.ts`) with a single-flight refresh promise; wired into BOTH axios instances via a shared `attachAuthInterceptors()` factory; raw-`fetch` call sites migrated to the default axios instance so they inherit coverage. | One implementation instead of three; raw fetch cannot be intercepted, so those call sites move to axios (they are plain JSON GET/PUT calls — trivial migration). |
| D8 | `src/api/client.js` | **Migrate to `src/api/client.ts`, keep the separate instance** (baseURL `/inventory`), attach the shared auth interceptors **before** its existing error-normalizing interceptor. | Folding it into the default axios instance would change error semantics for `items.ts` consumers (they rely on `Error(detail)` normalization). Keeping the instance + shared interceptor = minimal diff, zero duplication of refresh logic. Same basename → `items.ts` import path unchanged. |
| D9 | `spellcheck.ts` raw fetch | **Excluded from refresh coverage.** | It calls the external Yandex Speller API — no JWT is attached; a 401 there is not our auth. (Analyst listed it as a raw-fetch site; it is one, but out of auth scope.) |
| D10 | Rate limiting on `/users/refresh` | **None added in this feature.** | Consistent with `/users/login` and `/users/register`, which have no rate limiting today; the endpoint costs one JWT verify + one SELECT. A brute-force attack must forge an HS256 signature — rate limiting is not the effective control; the effective control is the real secret (issue #27). Gateway-wide rate limiting is pre-existing tech debt, not expanded here (avoids touching both nginx confs). |

### API Contracts

#### `POST /users/refresh` (modified — breaking change to the *parameter transport*, safe because no callers exist yet)

**Request** (JSON body — was a query param; query transport leaked tokens into Nginx access logs):
```json
{ "refresh_token": "<JWT string, required>" }
```

**Response 200:**
```json
{ "access_token": "<new JWT, 20h, type=access>", "refresh_token": "<new JWT, 7d, type=refresh>", "token_type": "bearer" }
```

**Errors:**
- `401 {"detail": "Недействительный или истёкший refresh-токен"}` — bad signature, expired, `type == "access"`, unknown user, missing `sub`. One generic message, no oracle about *why* it failed.
- `422` — FastAPI/Pydantic validation (missing/invalid body field).

**Pydantic <2.0 schemas** (`services/user-service/schemas.py`):
```python
class RefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
```
`response_model=schemas.TokenResponse` on `/users/refresh` only. Login/register responses are untouched (minimal diff; they already return `access_token` + `refresh_token`, and AuthForm reads exactly those keys).

#### JWT claim layout (issued after deploy)

| Claim | Access token | Refresh token |
|-------|-------------|---------------|
| `sub` | email | email |
| `role` | user role | user role |
| `current_character` | if set (login & refresh) | if set |
| `type` | `"access"` (**new**) | `"refresh"` (**new**) |
| `exp` | +20h | +7d |

### Backward Compatibility Checklist

- Old access tokens (no `type`) → accepted by `get_current_user` (only `type == "refresh"` is rejected). ✔
- Old refresh tokens (no `type`) → accepted by `/users/refresh`. ✔
- New tokens carry an extra claim → `jwt.decode` ignores unknown claims; the 12 downstream services validate via HTTP `GET /users/me` and never decode JWTs themselves → zero changes outside user-service. ✔
- Query-param → JSON-body change on `/users/refresh` → grep-verified: no existing caller anywhere (frontend never calls it). ✔
- Old frontend bundles cached in browsers keep working: they never call refresh (behavior unchanged: 401 after 20h until they pick up the new bundle). ✔

### Security Considerations

- **Authentication:** `/users/refresh` is intentionally unauthenticated — the refresh token in the body IS the credential, verified by HS256 signature + `exp` + user existence lookup.
- **Token transport:** refresh token moves from URL query to JSON body → no longer written to Nginx access logs. (WS `?token=` query transport is pre-existing, out of scope — noted, not changed.)
- **Type confusion:** blocked for all newly issued tokens via D4; legacy window ≤7 days.
- **Input validation:** Pydantic required-string; jose validates signature/exp; user re-fetched from DB on every refresh (deleted/banned users cannot refresh).
- **Error messages:** Russian, generic, non-enumerating (same message for all failure modes).
- **Rate limiting:** none (D10, justified above).
- **CRITICAL (out of scope, tracked):** prod almost certainly runs on fallback secret `your-secret-key` → `docs/ISSUES.md` issue #27.

### DB Changes

**None.** No migrations. (Stateless design, D1.)

### Frontend Components

**New: `src/api/authToken.ts`** — the single source of truth for tokens and refresh:
- `getAccessToken() / getRefreshToken() / setTokens(access, refresh) / clearTokens()` — localStorage wrappers, keys unchanged (`accessToken`, `refreshToken`).
- `refreshAccessToken(failedAccessToken?): Promise<RefreshResult>` where `RefreshResult = { status: 'ok'; token: string } | { status: 'fatal' } | { status: 'transient' }`:
  - **Single-flight:** module-level shared promise; concurrent callers await the same in-flight request. Promise cleared in `finally`.
  - **Multi-tab short-circuit:** before issuing the network call, re-read `accessToken` from localStorage; if it differs from `failedAccessToken`, another tab already refreshed → return `{status:'ok', token: current}` without a network call. (Combined with D2's non-revocation this makes multi-tab races harmless.)
  - Calls `POST /users/refresh` with JSON body via a **bare axios instance created with `axios.create()`** (no interceptors → no recursion). On 200: `setTokens(access, refresh)` → `'ok'`. On 401/403/422: `'fatal'`. On network error / 5xx: `'transient'` — tokens are NOT cleared.
  - No refresh token in storage → `'fatal'` without a network call.
- `handleAuthFailure()` — the ONLY place that deletes tokens: `clearTokens()`, Russian toast («Сессия истекла. Войдите снова.»), `window.location.assign('/')` (full reload naturally resets Redux; avoids store↔api circular imports). Idempotent guard so N parallel fatal failures fire one toast/redirect.

**Modified: `src/api/axiosSetup.ts`** — export `attachAuthInterceptors(instance: AxiosInstance)`:
- Request interceptor: attach Bearer from `getAccessToken()` (existing behavior).
- Response interceptor: on 401, if URL is not `/users/login|register|refresh` and `config._retried` is not set → `refreshAccessToken(tokenUsed)`; `'ok'` → set `_retried`, update Authorization header, replay via `instance(config)`; `'fatal'` → `handleAuthFailure()` and reject; `'transient'` → reject the ORIGINAL error (tokens intact, caller shows its normal error UI). Keep the existing 403 toast; the old bare 401 toast is replaced by this flow.
- Apply to the default `axios` (as today) — module still imported once from the entry point.

**Modified: `src/api/client.js` → `src/api/client.ts`** (D8) — typed, keeps `axios.create({ baseURL: "/inventory", ... })`, calls `attachAuthInterceptors(client)` FIRST, then re-registers its error-normalizing response interceptor (registration order guarantees the refresh interceptor sees the raw `AxiosError` with `response.status` before normalization converts it to a plain `Error`).

**Modified: `src/redux/slices/userSlice.ts`** — `getMe` thunk:
- Replace raw `fetch` with the default axios instance → inherits refresh-on-401 + retry automatically.
- **Remove `localStorage.removeItem("accessToken")` from the thunk entirely** — token deletion happens only in `handleAuthFailure()` after a *definitive* refresh failure.
- Error discrimination: axios error with `response.status === 401` (means refresh already failed or was fatal) → `rejectWithValue('unauthorized')`; network error / 5xx → bounded in-thunk retry (2 extra attempts, ~1.5s apart — rides out the deploy window) then `rejectWithValue('transient')`.
- Reducers: `getMe.rejected` keeps setting `authInitialized = true` (FEAT-055 pattern preserved: `App.tsx` bootstrap and `ProtectedRoute` waiting on `authInitialized` are untouched). On `'transient'` the user state clears in Redux (UI shows logged-out until next successful load) but **tokens survive**, so the next navigation/reload recovers the session.

**Modified raw-fetch call sites → default axios** (inherit coverage; all already `.tsx`/`.ts`):
- `src/components/pages/SelectCharacterPage/SelectCharacterPage.tsx` (`GET /users/{id}/characters`, `PUT/POST /users/{id}/update_character`)
- `src/components/CommonComponents/Header/CharacterSwitchDropdown.tsx` (`/users/{id}/update_character`)
- `src/api/spellcheck.ts` — NOT touched (D9).

**Modified: `src/components/StartPage/AuthForm/AuthForm.tsx`** — replace direct `localStorage.setItem` calls with `setTokens()` (keeps a single writer; keys/behavior identical).

**Modified WebSocket hooks** (token is passed as `?token=` at connect; all three must re-read localStorage inside `connect()` so reconnect picks up refreshed tokens):
- `src/hooks/useWebSocket.ts` (notifications): already re-reads token on reconnect and special-cases unauthorized close. Add: on unauthorized close code, `await refreshAccessToken()` before `scheduleReconnect()` (so the reconnect uses a fresh token instead of retrying a dead one).
- `src/hooks/useBattleWebSocket.ts`: has `WS_CLOSE_UNAUTHORIZED = 4001` detection (line ~202) but connects with a token captured once. Change: re-read token from localStorage inside `connect()`; on 4001 → `refreshAccessToken()` then reconnect.
- `src/hooks/useDungeonWebSocket.ts`: no unauthorized handling at all. Add the same 4001 branch as battle hook + re-read token in `connect()`.
- WS auth failures NEVER call `handleAuthFailure()` directly — logout is decided only by the HTTP refresh path (a `'fatal'` refresh result will log out via the next HTTP interaction; WS just keeps its backoff).

### Data Flow Diagram

```
[Any API call] → axios (default | client.ts) → 401
    → attachAuthInterceptors: refreshAccessToken()  ← single-flight (N parallel 401s → 1 refresh)
        → multi-tab short-circuit? → reuse token from localStorage (other tab refreshed)
        → POST /users/refresh {refresh_token} → user-service
              user-service: jwt.decode → type!=access → get_user_by_email(DB)
              → new access(20h, current_character from DB) + new refresh(7d)  [D2 rotation]
        → 200: setTokens() → retry original request once (_retried) → response to caller
        → 401 (fatal): handleAuthFailure() → clearTokens + toast(RU) + redirect "/"
        → 5xx/network (transient): reject original error, tokens KEPT

[Bootstrap] App.tsx → getMe() (axios) → covered by the same interceptor
[WS close 4001] → refreshAccessToken() → reconnect with fresh token from localStorage
```

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **user-service: token `type` claim + fix `POST /users/refresh`.** Add `type: "access"/"refresh"` in `create_access_token`/`create_refresh_token`; reject `type=="refresh"` in `get_current_user` and `type=="access"` in refresh (missing `type` = legacy, accepted). Refresh endpoint: JSON body `RefreshRequest`, `response_model=TokenResponse`, rebuild `token_data` like login (`sub` + `current_character` re-read from DB), issue new access AND new refresh token (D2 rotation), Russian 401 detail «Недействительный или истёкший refresh-токен». Update endpoint docs in `docs/services/user-service.md`. | Backend Developer | DONE | `services/user-service/auth.py`, `services/user-service/main.py`, `services/user-service/schemas.py`, `docs/services/user-service.md` | — | `python -m py_compile` OK on all modified files; existing user-service tests still pass; manual curl: body-refresh with a refresh token → 200 with 3 fields incl. rotated `refresh_token`; access token sent to `/users/refresh` → 401; new refresh token sent as Bearer to `/users/me` → 401; legacy token (no `type`) accepted on both endpoints. |
| 2 | **Frontend: shared token/refresh module + interceptor consolidation.** New `src/api/authToken.ts` (storage helpers, single-flight `refreshAccessToken` with multi-tab short-circuit and fatal/transient discrimination, idempotent `handleAuthFailure` with Russian toast + redirect). Rework `axiosSetup.ts` into exported `attachAuthInterceptors()` applied to default axios (401→refresh→single retry via `_retried`; fatal→logout; transient→propagate error, keep tokens; keep 403 toast). Migrate `client.js`→`client.ts` (D8), attach shared interceptors before its error-normalizer; `items.ts` import stays `./client`. | Frontend Developer | DONE | `src/api/authToken.ts` (new), `src/api/axiosSetup.ts`, `src/api/client.js` → `src/api/client.ts` | — (contract fixed in section 3; runs in parallel with #1) | `npx tsc --noEmit` OK; `npm run build` OK; refresh logic exists in exactly ONE module; N parallel 401s produce exactly 1 `/users/refresh` call (verify in devtools Network); on refresh 401 → tokens cleared, one Russian toast, redirect to `/`; on refresh 5xx/network → tokens remain in localStorage. |
| 3 | **Frontend: `getMe` rework + raw-fetch migration.** `userSlice.ts`: `getMe` via default axios, delete `localStorage.removeItem` from thunk, discriminate `'unauthorized'` vs `'transient'` (with 2 bounded retries ~1.5s for transient), keep `authInitialized` semantics (FEAT-055 — no regression in `App.tsx`/`ProtectedRoute`, neither file should need changes). Migrate raw `fetch` → axios in SelectCharacterPage and CharacterSwitchDropdown. `AuthForm.tsx`: use `setTokens()`. `spellcheck.ts` untouched (D9). | Frontend Developer | DONE | `src/redux/slices/userSlice.ts`, `src/components/pages/SelectCharacterPage/SelectCharacterPage.tsx`, `src/components/CommonComponents/Header/CharacterSwitchDropdown.tsx`, `src/components/StartPage/AuthForm/AuthForm.tsx` | #2 | `npx tsc --noEmit` OK; `npm run build` OK; simulated 503 on `/users/me` (devtools request blocking) does NOT remove `accessToken` from localStorage; F5 with valid token still restores session (FEAT-055 flow intact); definitive 401-after-failed-refresh → logout+redirect. |
| 4 | **Frontend: WS hooks refresh-aware reconnect.** All three hooks re-read the token from localStorage inside `connect()`; on unauthorized close (code 4001 / `WS_CLOSE_UNAUTHORIZED`) call `refreshAccessToken()` before scheduling reconnect. Notifications hook keeps its `UNAUTHORIZED_RECONNECT_DELAY` behavior; add the missing 4001 branch to the dungeon hook. WS failures never trigger logout directly. | Frontend Developer | DONE | `src/hooks/useWebSocket.ts`, `src/hooks/useBattleWebSocket.ts`, `src/hooks/useDungeonWebSocket.ts` | #2 (parallel with #3) | `npx tsc --noEmit` OK; `npm run build` OK; with an expired access token in localStorage and a valid refresh token, WS reconnects successfully after one refresh cycle; no logout/toast storm from WS closes. |
| 5 | **QA: user-service refresh tests.** New `test_refresh.py` (follow existing conftest pattern, SQLite in-memory, mock cross-service HTTP): (a) valid refresh token in body → 200, three fields, new tokens differ from input; (b) rotated refresh token from (a) works again (sliding window); (c) access token → `/users/refresh` = 401; (d) refresh token as Bearer → `/users/me` = 401; (e) legacy tokens without `type` claim (craft via jose directly) accepted on both endpoints; (f) expired/garbage/missing-user token → 401 with Russian detail; (g) `current_character` claim present in refreshed access token when user has one, absent when NULL; (h) missing body field → 422. | QA Test | DONE | `services/user-service/tests/test_refresh.py` | #1 (parallel with #2–#4) | `pytest services/user-service` — all pass, incl. pre-existing tests (`test_jwt_secret.py`, RBAC tests). |
| 6 | **Review + live verification.** Re-run `py_compile`, `pytest`, `npx tsc --noEmit`, `npm run build`. Live (chrome-devtools, test admin account): (1) put an expired/garbage access token + valid refresh token in localStorage → next API call transparently refreshes, page works, zero console errors; (2) both tokens garbage → single Russian toast + redirect to login; (3) two tabs open, force refresh in both → neither logs out; (4) block `/users/me` (simulate 503) → token NOT deleted; (5) restart user-service container mid-session → user recovers without relogin; (6) verify refresh request is a JSON body (no token in URL/query in Network tab). Verify ISSUES.md #27 recorded and no `.jsx`/SCSS rule violations. | Reviewer | DONE | all | #1, #2, #3, #4, #5 | Section 5 checklist fully PASS; live checks above documented in Review Log. |

**Parallelism:** #1 ∥ #2 (contract is fixed in section 3). After #1 → #5; after #2 → #3 ∥ #4. #6 last.
**DevSecOps:** not needed — no Docker/Nginx/env changes in this feature (secret rotation deferred to ISSUES.md #27).

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-07-17
**Result:** PASS

All checks passed. Changes are ready for completion.

#### Scope verification
- Working-tree change set matches the declared scope exactly (15 modified + 3 new files: `authToken.ts`, `client.ts`, `test_refresh.py`; `client.js` deleted). No unrelated files touched (`img.png` predates the feature).
- `docs/ISSUES.md` #27 (JWT secret fallback) recorded as CRITICAL, correctly NOT fixed in this feature (D6).
- Task #3 deviation (`Header.tsx` logout → `clearTokens()`) reviewed and **approved**: without it the leftover refreshToken would resurrect the session after explicit logout — live-verified.

#### Automated Check Results
- [x] `py_compile` (auth.py, main.py, schemas.py) — PASS
- [x] `pytest services/user-service/tests/` — PASS: **445 passed, 19 failed** — the 19 failures are exactly the documented pre-existing baseline (test_cosmetics, test_feat029_user_stats, test_pagination; local pydantic 2.x env mismatch, same set fails on clean HEAD). **Zero new failures.** All 19 new `test_refresh.py` tests pass.
- [x] `npx tsc --noEmit` — PASS
- [x] `npm run build` — PASS
- [x] `docker compose config` — PASS

#### Code Review vs Architecture (section 3)
- D2 rotation, D3 `current_character` re-read from DB, D4 `type` claim with legacy acceptance — implemented exactly as specified (`auth.py`, `main.py:/users/refresh`).
- Single-flight refresh + multi-tab short-circuit + fatal/transient discrimination in `authToken.ts`; `_retried` single-retry + auth-endpoint exclusion in `axiosSetup.ts`; `client.ts` attaches shared interceptors BEFORE its error normalizer (D8); `items.ts` import unchanged, no stale `client.js` imports anywhere (grep-verified).
- Token deletion sites (grep-verified): only `handleAuthFailure()`/`clearTokens()` (authToken.ts) + Header logout (approved deviation). `userSlice.ts` no longer touches localStorage. Pre-existing dead-code deletion branch found in `useNavigateTo.js:9` → recorded as ISSUES.md #28 (no current caller passes `'/'`; non-blocking).
- getMe: axios, 401→`'unauthorized'`, 5xx/network→2 bounded retries (1.5s)→`'transient'`; `authInitialized` semantics untouched (FEAT-055 preserved, App.tsx/ProtectedRoute unchanged).
- WS hooks: all three re-read token in `connect()`, 4001 → shared `refreshAccessToken()` then reconnect, never logout — as designed.
- Standards: Pydantic v1 syntax; no React.FC; no `any`; no new `.jsx`/SCSS; no TODO/FIXME; Russian user-facing messages; refresh token in JSON body only (never URL/logs); generic non-enumerating 401 detail.

#### Live Verification Results (chrome-devtools + curl, admin test account)
- **(a) curl:** login → `POST /users/refresh` (JSON body) → 200 with `access_token`/`refresh_token`/`token_type=bearer`, both rotated; new access works on `/users/me` (200); rotated refresh works again (sliding window, 200); access token → `/users/refresh` = 401 «Недействительный или истёкший refresh-токен»; refresh token as Bearer → `/users/me` = 401; token in query only = 422 (query ignored); garbage = 401. New tokens carry `type` + `current_character` claims (decoded).
- **(b) Transparent refresh:** garbage accessToken + valid refreshToken → page reload: two parallel 401s (`/users/me`, `/notifications/messenger/unread-count`) → **exactly ONE** `POST /users/refresh` [200] (single-flight confirmed in Network) → both requests retried → 200. Token replaced in localStorage, session intact, zero console errors.
- **(c) Deploy simulation:** `docker compose stop user-service` + reload: `/users/me` → 502 ×3 (initial + exactly 2 bounded retries, then stop), **tokens NOT deleted**; `start user-service` + reload → session restored without relogin, zero console errors. Also verified with `restart` mid-session.
- **(d) Fatal path:** both tokens garbage → refresh 401 → tokens cleared, redirect to `/` (login page shown), no refresh-loop. *Minor observation:* the Russian toast fires immediately before `window.location.assign('/')`, so it is visible only momentarily — this matches the approved architecture spec verbatim (full-reload redirect chosen deliberately); flagged as a UX question for PM, non-blocking.
- **(e) Logout:** Header «Выход» → both tokens null, redirect to `/`; navigating to `/home` afterwards bounces to `/`, zero `/users/refresh` calls — session does NOT resurrect (validates the approved Task #3 deviation).
- **(f) Multi-tab + WS:** two tabs refreshed independently during overlapping tests, neither logged out (D2 non-revocation confirmed); after refresh in tab A, tab B continued with 200s using the shared token, no extra refresh. notification-service logs: WS handshakes rejected 403 during outage (bounded reconnects, no logout/toast storm), then `[accepted] / connection open` with the refreshed token after user-service returned.
- Console across all tabs: only expected resource-load logs from deliberate fault injection (401/502/403); no JS exceptions, no unhandled rejections, no 500s.

#### Deploy note (non-blocking)
Deleting `src/api/client.js` while the Vite dev server keeps its old module graph causes a stale-import 404 (`/src/api/client.js`) and a blank page until the frontend container is restarted. **After pulling this change, dev machines must restart the `frontend` container** (`docker compose restart frontend`). Prod is unaffected (image rebuild). Verified: after restart the graph resolves `./client` → `client.ts` correctly.

#### Pre-existing issues noted (added to docs/ISSUES.md, non-blocking)
| # | Where | Description |
|---|-------|-------------|
| ISSUES #28 | `src/hooks/useNavigateTo.js:9` | Dead-code `accessToken` deletion on `navigateTo('/')` — contradicts the new single-writer invariant; no current caller triggers it |
| ISSUES #29 | AuthForm/Header | After UI login the header stays "logged-out" until next navigation/F5 (Header skips getMe on first mount); reproduced on clean HEAD — not a FEAT-150 regression |

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-07-17 — PM: фича создана, запускаю Codebase Analyst для выяснения причины 401 после рестарта сервера
[LOG] 2026-07-17 — PM: получены ответы пользователя: секрет JWT — отдельной задачей (в ISSUES.md), refresh — stateless без БД, access TTL — оставить 20 часов. Запускаю Architect
[LOG] 2026-07-17 — Analyst: анализ завершён. Секрет JWT стабилен между рестартами (гипотеза о случайном секрете не подтвердилась). Реальные причины: (1) access-токен живёт 20 часов, а фронтенд никогда не вызывает уже существующий бекенд-эндпоинт POST /users/refresh — refreshToken сохраняется при логине и больше не используется; (2) getMe() в userSlice.ts удаляет валидный accessToken из localStorage при любой ошибке, включая 502/503 во время деплоя; (3) axios-интерсептор на 401 только показывает toast, без refresh/retry. Дополнительно обнаружено: prod, вероятно, работает на публично известном fallback-секрете "your-secret-key" (JWT_SECRET_KEY отсутствует в .env) — критический вопрос безопасности, вынесен в Open Questions. Затронуты: user-service, frontend, docker/env. Остальные 12 сервисов валидируют токены через HTTP /users/me и изменений не требуют. Отчёт записан в секцию 2, есть 3 вопроса к пользователю.
[LOG] 2026-07-17 13:23 — Architect: начал проектирование
[LOG] 2026-07-17 13:35 — Architect: проектирование завершено. Ключевые решения: stateless refresh со скользящим окном (ротация refresh-токена без отзыва старого — безопасно для мультивкладочности), новый claim `type` (access/refresh) с обратной совместимостью для старых токенов, `current_character` перечитывается из БД при refresh, /users/refresh переведён на JSON body (токен больше не попадает в логи Nginx). Frontend: единый модуль authToken.ts с single-flight refresh, общие интерсепторы для обоих axios-инстансов, client.js мигрирует в client.ts, getMe переходит на axios и больше не удаляет токены при 5xx, три WS-хука переподключаются со свежим токеном. Спроектировано 6 задач (1 backend, 3 frontend, 1 QA, 1 review), 1 API-контракт, миграций БД нет. Статус фичи: IN_PROGRESS.
[LOG] 2026-07-17 13:35 — Architect: критическая проблема безопасности (публичный fallback JWT-секрет `your-secret-key`) зафиксирована в docs/ISSUES.md как issue #27 (CRITICAL), по решению пользователя — отдельной задачей.
[LOG] 2026-07-17 13:55 — Frontend Dev: задача #2 завершена. Создан src/api/authToken.ts (единый модуль токенов: single-flight refresh с мультивкладочным short-circuit, различение fatal/transient ошибок, идемпотентный handleAuthFailure — единственное место удаления токенов, русский toast + редирект на логин). axiosSetup.ts переработан: экспорт attachAuthInterceptors() (401 → refresh → один повтор через _retried; fatal → logout; transient → исходная ошибка, токены сохраняются; toast на 403 сохранён), применён к дефолтному axios. client.js мигрирован в client.ts (общие интерсепторы подключены ДО нормализатора ошибок, baseURL /inventory и семантика Error(detail) сохранены, импорт в items.ts не изменился). Проверки: npx tsc --noEmit — OK, npm run build — OK.
[LOG] 2026-07-17 13:56 — Backend Dev: задача #1 завершена. auth.py: добавлен claim `type` (access/refresh) в create_access_token/create_refresh_token, get_current_user отклоняет токены с type=refresh (токены без type — legacy, принимаются). main.py: /users/refresh переведён на JSON body (RefreshRequest), response_model=TokenResponse, ротация refresh-токена (D2), current_character перечитывается из БД как при логине, единая русская ошибка 401 «Недействительный или истёкший refresh-токен». schemas.py: добавлены RefreshRequest и TokenResponse (Pydantic v1). Обновлена документация docs/services/user-service.md. Проверки: py_compile OK (3 файла); pytest — 426 passed, 19 failed, но те же 19 тестов падают и на чистом HEAD (локальный pydantic 2.13 vs проектный <2.0 — pre-existing проблема окружения, к изменениям не относится); временный smoke-тест подтвердил все acceptance criteria (ротация refresh-токена, 401 на access-токен в /users/refresh и на refresh-токен как Bearer в /users/me, legacy-токены без type приняты на обоих эндпоинтах, 422 без body, claim current_character и type в новых токенах) и удалён.
[LOG] 2026-07-17 14:05 — Frontend Dev: задача #4 завершена. Все три WS-хука перечитывают токен из localStorage внутри connect() через getAccessToken() (переподключение всегда идёт со свежим токеном, а не с захваченным устаревшим). useWebSocket.ts (уведомления): при закрытии 4001 сохранён UNAUTHORIZED_RECONNECT_DELAY, но перед scheduleReconnect() теперь вызывается shared refreshAccessToken(). useBattleWebSocket.ts: на 4001 вместо мгновенного fallbackToPolling — refresh, затем reconnect; fallback только при fatal-результате refresh. useDungeonWebSocket.ts: добавлена отсутствовавшая ветка 4001 — refresh, затем reconnect; при fatal — остановка переподключений. WS-сбои никогда не удаляют токены и не вызывают logout/handleAuthFailure — это решает только HTTP-слой. Код 4001 сверен с бэкендом (notification/battle/dungeon сервисы закрывают unauthorized именно с 4001; 4003=Forbidden не тронут). Проверки: npx tsc --noEmit — OK, npm run build — OK.
[LOG] 2026-07-17 14:10 — Frontend Dev: задача #3 завершена. userSlice.ts: getMe переведён с raw fetch на дефолтный axios (наследует refresh-on-401 + retry из интерсептора), localStorage.removeItem полностью удалён из thunk (удаление токенов — только в handleAuthFailure). Различение ошибок: 401 → rejectWithValue('unauthorized'); network/5xx → до 2 повторов с паузой 1.5с (окно деплоя), затем rejectWithValue('transient') — токены сохраняются, logout не происходит. Семантика authInitialized (FEAT-055) не тронута: reducer'ы, App.tsx и ProtectedRoute без изменений. SelectCharacterPage.tsx и CharacterSwitchDropdown.tsx: raw fetch (GET characters, PUT update_character) мигрирован на дефолтный axios, ручная простановка Bearer-заголовка удалена (её делает интерсептор), русские сообщения об ошибках сохранены. AuthForm.tsx: запись токенов через setTokens(), удалён removeItem('accessToken') из catch (неудачная попытка логина больше не уничтожает действующую сессию). Дополнительно (отклонение от списка файлов, обосновано): Header.tsx handleLogout переведён на clearTokens() — старый код удалял только accessToken, и оставшийся refreshToken позволил бы интерсептору «воскресить» сессию после явного выхода. spellcheck.ts не тронут (D9). Проверки: npx tsc --noEmit — OK, npm run build — OK.
[LOG] 2026-07-17 14:40 — QA: задача #5 завершена. Написан tests/test_refresh.py — 19 тестов в 5 классах: happy path (200, три поля, новый access-токен работает на /users/me), ротация refresh-токена (входной токен с нестандартным expires_delta, чтобы exp гарантированно отличался; ротированный токен снова принимается — скользящее окно), type confusion (access-токен в /users/refresh → 401, refresh-токен как Bearer в /users/me → 401), legacy-токены без claim type (созданы напрямую через jose) приняты на обоих эндпоинтах, все режимы отказа (истёкший, мусор, пустая строка, чужой секрет, без sub, несуществующий пользователь) → 401 с единой русской ошибкой «Недействительный или истёкший refresh-токен», claims нового access-токена (type=access, current_character перечитан из БД: присутствует при установленном персонаже, отсутствует при NULL), 422 без поля/тела (токен в query игнорируется). Межсервисный вызов _fetch_character_short замокан. Результаты: tests/test_refresh.py — 19 passed; полный прогон user-service — 445 passed, 19 failed (те же 19 pre-existing падений из-за pydantic 2.x в окружении, что и на чистом HEAD — к фиче не относятся). Багов не обнаружено.
[LOG] 2026-07-17 16:40 — Reviewer: начал проверку, статус фичи переведён в REVIEW
[LOG] 2026-07-17 17:45 — Reviewer: проверка завершена, результат PASS. Автоматические проверки: py_compile OK, pytest 445 passed / 19 failed (ровно тот же pre-existing baseline из-за pydantic 2.x в окружении, ноль новых падений; все 19 тестов test_refresh.py прошли), tsc OK, npm run build OK, docker compose config OK. Live-проверка (curl + chrome-devtools, админ-аккаунт): refresh через JSON body с ротацией — 200; type confusion — 401 в обе стороны; legacy-токены приняты; мусорный accessToken прозрачно обновляется (2 параллельных 401 → ровно ОДИН /users/refresh → оба запроса повторены с 200); остановка user-service — токены НЕ удаляются (3 попытки getMe с bounded retry), после старта сессия восстановилась без relogin; оба токена мусорные — очистка и редирект на логин; logout чистит оба токена, сессия не «воскресает» (отклонение задачи #3 подтверждено как корректное); мультивкладочность — обе вкладки живы; WS переподключился со свежим токеном после рестарта user-service. Консоль без ошибок (кроме ожидаемых 401/502 от намеренных фейл-инъекций).
[LOG] 2026-07-17 17:45 — Reviewer: важно для деплоя на dev-машинах: после git pull необходимо перезапустить контейнер frontend (docker compose restart frontend) — Vite держит старый module graph и отдаёт 404 на удалённый client.js (белая страница). Prod не затронут (сборка образа).
[LOG] 2026-07-17 17:45 — Reviewer: обнаружены 2 pre-existing бага (не относятся к фиче, не блокируют): мёртвая ветка удаления accessToken в useNavigateTo.js и «разлогиненный» хедер сразу после логина через форму (воспроизводится на HEAD до фичи). Добавлены в docs/ISSUES.md как #28 и #29. Минорное наблюдение для PM: тост «Сессия истекла…» при fatal-разлогине виден лишь мгновение из-за немедленного window.location.assign — соответствует утверждённой архитектуре, но UX можно обсудить отдельно.
[LOG] 2026-07-17 — PM: ревью PASS с первой итерации. Баги #28 и #29 подтверждены в ISSUES.md. Фича закрыта, файл переименован в DONE-FEAT-150.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **Найдена настоящая причина «слетающего логина».** Дело было не в рестарте сервера: access-токен живёт 20 часов, а механизм обновления на фронтенде отсутствовал — токен просто истекал между деплоями. Вдобавок `getMe()` удалял ещё действующий токен при временных ошибках сервера (502/503 во время деплоя).
- **Backend (user-service):** `POST /users/refresh` переработан — refresh-токен передаётся в JSON body (не в URL/логи Nginx), ответ по схеме (access + refresh + type), stateless-ротация refresh-токена (скользящее окно 7 дней — пока игрок активен, сессия не истекает), claim `type` против подмены access/refresh, `current_character` перечитывается из БД, единая русская ошибка 401. Старые токены (без `type`) продолжают работать — обратная совместимость.
- **Frontend:** новый модуль `src/api/authToken.ts` — единая точка работы с токенами: single-flight refresh (N параллельных 401 → один запрос обновления), защита мультивкладочности, различение fatal/transient ошибок; удаление токенов — только в `handleAuthFailure()`. Интерсепторы refresh-on-401 + повтор запроса подключены к обоим axios-инстансам (`client.js` мигрирован в `client.ts`). `getMe()` переведён на axios, при 5xx/network делает до 2 повторов и не трогает токены. Raw-fetch вызовы (SelectCharacterPage, CharacterSwitchDropdown) мигрированы на axios. Все 3 WS-хука (чат, бой, подземелье) переподключаются со свежим токеном после refresh (код 4001); для подземелья ветка добавлена с нуля. Logout теперь чистит оба токена (иначе сессия «воскресала» из refresh-токена).
- **QA:** `tests/test_refresh.py` — 19 тестов (happy path, ротация, type confusion, legacy-токены, все режимы отказа, чужой секрет, claims). Все проходят; полный прогон — ноль новых падений.
- **Ревью:** PASS с первой итерации, включая живую проверку: прозрачный refresh при протухшем токене, рестарт user-service посреди сессии без разлогина, fatal-путь с редиректом, logout, две вкладки, WS-переподключение. Консоль чистая.

### Что изменилось от первоначального плана
- Смена JWT-секрета (публично известный fallback `your-secret-key`) — по решению пользователя вынесена в отдельную задачу: **docs/ISSUES.md #27 (CRITICAL)**.
- Обоснованное отклонение задачи #3: дополнительно исправлен `Header.tsx` (logout удалял только accessToken) — подтверждено ревьюером.

### Оставшиеся риски / follow-up задачи
- **ISSUES #27 (CRITICAL):** заменить JWT-секрет на проде (`openssl rand -hex 32` → prod `.env`), цена — однократный relogin всех игроков.
- **Деплой на dev-машинах:** после `git pull` перезапустить контейнер frontend (`docker compose restart frontend`) — Vite держит старый module graph удалённого `client.js` (белая страница до рестарта). Prod не затронут.
- ISSUES #28: мёртвая ветка удаления accessToken в `useNavigateTo.js` (pre-existing).
- ISSUES #29: хедер «разлогинен» сразу после логина до следующей навигации (pre-existing, воспроизводится до фичи).
- UX-мелочь: тост «Сессия истекла. Войдите снова.» виден мгновение из-за немедленного редиректа — можно обсудить отдельно.

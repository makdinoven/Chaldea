# FEAT-040: Исправление одобрения заявки на персонажа

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-18 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-040-fix-character-approval.md` → `DONE-FEAT-040-fix-character-approval.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
При одобрении заявки на персонажа (админ-панель, страница "Заявки на персонажей") возникает ошибка "Не удалось одобрить заявку". После ошибки заявка исчезает из списка, но персонаж не появляется. В анкете профиля персонаж отображается, но при попытке зайти на него — "Персонаж не найден. Создайте персонажа, чтобы просматривать профиль."

### Бизнес-правила
- Админ/модератор одобряет заявку → персонаж должен стать активным
- Заявка должна исчезнуть из списка только после успешного одобрения
- Персонаж после одобрения должен быть полностью доступен в профиле

### UX / Пользовательский сценарий
1. Админ заходит на страницу "Заявки на персонажей"
2. Нажимает "Одобрить" на заявку
3. Появляется красная ошибка "Не удалось одобрить заявку"
4. Заявка исчезает из списка
5. В профиле персонаж виден в анкете, но при входе — "Персонаж не найден"

### Edge Cases
- Что если заявка уже была одобрена ранее?
- Что если персонаж частично создан (запись есть, но данные неполные)?

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Root Cause

**Primary root cause: authentication added to `PUT /users/{user_id}/update_character` broke the service-to-service call from character-service.**

In commit `a286bbc` (FEAT-032), the `update_user_character` endpoint in user-service had `Depends(get_current_user)` added plus an ownership check (`user_id != current_user.id`). However, `character-service` calls this endpoint as a **service-to-service HTTP call without any JWT token** during the character approval workflow (step 10 of the flow). This causes a 401 Unauthorized response, which makes `assign_character_to_user()` return `False`, triggering an HTTPException 500.

### Full Approval Flow Trace

The approval endpoint is `POST /characters/requests/{request_id}/approve` in `character-service/app/main.py:75-227`.

The 11-step workflow:

| Step | Action | File:Line | Commits to DB? | Status |
|------|--------|-----------|-----------------|--------|
| 1 | Validate request exists, status=pending | main.py:94-99 | No | OK |
| 2 | Read starter kit from `starter_kits` table | main.py:103-116 | No | OK |
| 3 | Create Character record | crud.py:42-69 → main.py:119 | **YES (commit)** | OK |
| 4 | Generate attributes dict from SUBRACE_ATTRIBUTES | crud.py:385-404 | No | OK |
| 5 | POST inventory-service (graceful) | crud.py:407-433 | No | OK (graceful) |
| 6 | POST skills-service assign_multiple (graceful) | crud.py:612-640 | No | OK (graceful) |
| 7 | POST character-attributes-service | crud.py:461-487 | No | OK |
| 8 | Update character.id_attributes | crud.py:87-98 → main.py:169-173 | **YES (commit)** | OK |
| 9 | Set request status to "approved" | crud.py:73-83 → main.py:177 | **YES (commit)** | OK |
| 10a | POST user-service `/user_characters/` | crud.py:498-506 | External | OK (no auth required) |
| 10b | PUT user-service `/{user_id}/update_character` | crud.py:512-515 | External | **FAILS (401)** |
| 11 | RabbitMQ notification | producer.py:9-36 | No | Never reached |

**Step 10b fails** because `user-service/main.py:369` now requires `Depends(get_current_user)` and checks `user_id != current_user.id`. The `httpx` call from character-service has no `Authorization` header.

Since `assign_character_to_user()` returns `False`, line 186 raises `HTTPException(500, "Не удалось присвоить персонажа пользователю")`. The outer `except HTTPException: raise` on line 220 re-raises it, returning a 500 to the frontend.

### Why the Bug Manifests as Described

1. **"Не удалось одобрить заявку"** — Frontend `Request.tsx:57-58` catches any non-200 response and shows `toast.error`.

2. **Request disappears from list** — By step 9, the request status is already committed as "approved" in the DB. When `RequestsPage.tsx:59` filters for `status === 'pending'`, it no longer appears (even on page refresh).

3. **Character appears in user's character list** — Step 10a (POST `/user_characters/`) succeeded, creating the `users_character` relation. So `GET /users/{user_id}/characters` finds the character.

4. **"Персонаж не найден" on profile page** — Step 10b failed, so `current_character` on the `users` table is NOT updated. `GET /users/me` returns `current_character_id: null` and `character: null`. `ProfilePage.tsx:21` reads `character?.id ?? null` which is null, triggering the "not found" message at line 35-42.

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| user-service | Fix: remove auth from `update_character` OR add service-to-service auth | `main.py:368-393` |
| character-service | Fix: pass admin's JWT token to user-service call, OR add DB transaction for atomicity | `app/crud.py:490-527`, `app/main.py:75-227` |
| frontend | Fix: do not remove request from list on error; add page refresh on success | `src/components/Admin/Request/Request.tsx:48-72`, `src/components/Admin/RequestsPage/RequestsPage.tsx` |

### Existing Patterns

- **character-service**: sync SQLAlchemy, Pydantic <2.0, Alembic present, auth via `auth_http.py` (HTTP call to user-service `/users/me`)
- **user-service**: sync SQLAlchemy, Pydantic <2.0, Alembic present, JWT auth via `get_current_user` dependency
- **Frontend**: React 18, TypeScript, Tailwind CSS, axios, react-hot-toast for notifications

### Cross-Service Dependencies (Approval Flow)

```
character-service (approve endpoint)
  → inventory-service POST /inventory/ (graceful, no auth)
  → skills-service POST /skills/assign_multiple (graceful, no auth)
  → character-attributes-service POST /attributes/ (required, no auth)
  → user-service POST /users/user_characters/ (required, no auth) ← OK
  → user-service PUT /users/{id}/update_character (required, NOW requires auth) ← BROKEN
  → RabbitMQ general_notifications (graceful)
```

### Secondary Issue: Lack of Atomicity

Even after fixing the auth issue, the approval flow has a **critical atomicity problem**. Each step commits independently:
- Step 3 commits the Character record
- Step 8 commits the id_attributes update
- Step 9 commits the "approved" status

If ANY later step fails (e.g., attributes-service is down at step 7), the DB is left in an inconsistent state:
- Character exists but has no attributes (id_attributes=null)
- Request may or may not be "approved"
- No rollback mechanism

This is a pre-existing design issue but is the direct cause of the "ghost character" problem described in the bug.

### DB Changes

No schema changes needed. The fix is purely in application logic/auth.

### Risks

| Risk | Description | Mitigation |
|------|-------------|------------|
| Breaking other callers of `update_character` | Removing auth from `update_character` would re-open the security issue that FEAT-032 fixed (users could change other users' active characters) | Better approach: either (a) create a separate internal endpoint without auth for service-to-service calls, or (b) pass the admin's token through to user-service, or (c) do the DB update directly in character-service (shared DB) |
| Orphaned character records | If the bug has been triggered multiple times, there may be characters in the DB with status="approved" but `current_character` not set on the user | Need a data cleanup query |
| Frontend state inconsistency | After successful approval, the request should be removed from the list; currently there's no state management for this | Frontend should either refetch the list or remove the request from local state only on success |
| Atomicity gap remains | Even after the fix, if an intermediate service call fails, partial data may be committed | Long-term: wrap the entire approval in a single DB transaction, only committing at the end; short-term: at minimum move all DB commits to after all external calls succeed |

### Recommended Fix Strategy

**Option A (simplest, recommended):** Since all services share the same MySQL database, character-service can directly update the `users` table and `users_character` table instead of making HTTP calls to user-service. This eliminates the cross-service auth problem entirely and is already the pattern used by `photo-service` (mirror models). This also makes it possible to wrap the entire approval in a single DB transaction.

**Option B (preserves service boundaries):** Create an internal endpoint in user-service (e.g., `POST /users/internal/assign_character`) that does not require user JWT auth but optionally validates a service-to-service secret or the admin's forwarded token.

**Option C (quick fix):** Forward the admin's JWT token from the approval request through to the user-service calls. However, the ownership check (`user_id != current_user.id`) would still fail because the admin is not the user who owns the character. This option requires ALSO modifying the ownership check to allow admins.

**Frontend fix (needed regardless):** The `Request` component should update local state to remove/mark the request only on success, and the `RequestsPage` should refetch the list after approval/rejection.

---

## 3. Architecture Decision (filled by Architect — in English)

### Chosen Approach: Option C (Token Forwarding) + Admin Bypass in user-service + Deferred Commits for Atomicity

#### Why Not Option A (Direct DB Access)?

Option A (character-service writes to `users` and `users_character` tables directly) would work and is the simplest fix. However, it sets a bad architectural precedent — character-service would begin owning writes to user-service tables. The photo-service mirror-model pattern is read-only mirroring, not cross-service writes. Introducing cross-service DB writes makes future service isolation (separate databases) harder and obscures data ownership. The analyst recommended it for simplicity, but the security and ownership trade-offs outweigh the benefit.

#### Why Not Option B (Internal Endpoint)?

Option B (new internal endpoint with service-to-service secret) is over-engineered for this case. It requires inventing a new auth mechanism (shared secret, internal API key, etc.) that doesn't exist in the codebase yet. The only caller would be character-service's approval flow. The added infrastructure complexity is not justified for a single call.

#### Why Option C (Token Forwarding + Admin Bypass)?

Option C is the minimal, secure fix that follows existing patterns:

1. **The admin's JWT token already exists** — the approval endpoint uses `require_permission("characters:approve")`, which means the request already carries a valid admin JWT token via `OAUTH2_SCHEME`. We just need to pass it through to user-service.

2. **Admin bypass is consistent with RBAC** — the `update_user_character` endpoint's ownership check (`user_id != current_user.id`) should already allow admins to act on behalf of users. This is the standard RBAC pattern used elsewhere in the codebase (e.g., `delete_user_character_relation` uses `require_permission(db, current_user, "users:manage")`).

3. **Minimal diff** — only 2 backend files need changes, plus frontend improvements.

### Detailed Design

#### 1. user-service: Add admin bypass to `PUT /{user_id}/update_character`

**File:** `services/user-service/main.py` (lines 368-393)

**Current behavior:**
```python
@router.put("/{user_id}/update_character")
async def update_user_character(user_id: int, character_data: dict,
                                db: Session = Depends(get_db),
                                current_user: models.User = Depends(get_current_user)):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="...")
```

**New behavior:**
```python
@router.put("/{user_id}/update_character")
async def update_user_character(user_id: int, character_data: dict,
                                db: Session = Depends(get_db),
                                current_user: models.User = Depends(get_current_user)):
    if user_id != current_user.id:
        if not is_admin(db, current_user):
            raise HTTPException(status_code=403, detail="Вы можете менять только своего активного персонажа")
```

The `is_admin` function already exists in user-service (imported in `main.py` line 7). It checks if the user has admin or moderator role. This allows admins/moderators to set `current_character` for any user (needed for character approval), while regular users can still only change their own.

**Security:** This does NOT re-open the vulnerability from FEAT-032. Regular users still cannot change other users' active character. Only admin/moderator can, which is an expected RBAC privilege.

#### 2. character-service: Forward admin's JWT token in `assign_character_to_user`

**File:** `services/character-service/app/crud.py` (function `assign_character_to_user`, lines 490-527)

**Change:** Add `token: str` parameter and include `Authorization: Bearer {token}` header in the PUT request to user-service.

```python
async def assign_character_to_user(user_id: int, character_id: int, token: str = None):
```

Both HTTP calls (POST `/user_characters/` and PUT `/{user_id}/update_character`) should forward the token. Note: POST `/user_characters/` currently has no auth, so the token is optional but good practice to include for future-proofing.

**File:** `services/character-service/app/main.py` (line 181)

**Change:** Extract the token from the current request and pass it to `assign_character_to_user`. The `OAUTH2_SCHEME` dependency already extracts the token in `require_permission`. We need to add `token: str = Depends(OAUTH2_SCHEME)` to the endpoint signature and pass it through.

```python
# Line 76 — add token parameter
async def approve_character_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("characters:approve")),
    token: str = Depends(OAUTH2_SCHEME)
):
```

```python
# Line 181 — pass token
assign_result = await crud.assign_character_to_user(db_request.user_id, updated_character.id, token=token)
```

#### 3. character-service: Improve atomicity with deferred commits

**File:** `services/character-service/app/main.py` (approval endpoint) and `services/character-service/app/crud.py`

Currently steps 3, 8, and 9 each call `db.commit()` independently. If a later step fails, earlier commits cannot be rolled back.

**Fix:** Defer all DB commits until after all critical steps succeed:

1. **Step 3 (create character):** Use `db.add()` + `db.flush()` instead of `db.commit()`. Flush assigns the auto-increment ID without committing.
2. **Step 8 (update id_attributes):** Use `db.flush()` instead of `db.commit()`.
3. **Step 9 (set status approved):** Use `db.flush()` instead of `db.commit()`.
4. **Step 10 (assign to user):** After successful HTTP calls, call `db.commit()` once.
5. **On any failure:** The session rollback happens automatically (FastAPI's `get_db` dependency calls `db.close()` which rolls back uncommitted changes, or we add explicit `db.rollback()` in the except block).

This requires modifying the CRUD functions to accept a `commit=True` parameter (default `True` for backward compatibility) or creating new versions that flush instead of commit. The simpler approach: modify the approval endpoint to use `db.begin_nested()` / manual flush, keeping the CRUD functions unchanged but calling them differently from the approval flow.

**Implementation approach:** Instead of modifying each CRUD function signature (which would affect other callers), the approval endpoint will:
- Call `db.begin_nested()` at the start (creates a savepoint)
- After each CRUD call that commits, the nested transaction auto-commits to the savepoint
- Actually, the simpler approach: modify the three CRUD functions (`create_preliminary_character`, `update_character_with_dependencies`, `update_character_request_status`) to accept an optional `auto_commit=True` parameter. When `False`, they skip `db.commit()`. The approval endpoint passes `auto_commit=False` and does a single `db.commit()` at the end.

**Revised approach (simplest):** Add a single `db.commit()` call in `main.py` after step 10 succeeds, and modify the three CRUD function calls to not commit. Since these functions are only called from the approval endpoint in practice, we can refactor them to accept `auto_commit=True` (default preserves backward compat).

#### 4. Frontend: Fix state management and migrate RequestButton

**File:** `services/frontend/app-chaldea/src/components/Admin/Request/Request.tsx`

**Changes:**
- Accept an `onStatusChange` callback prop from `RequestsPage`
- On successful approve/reject: call `onStatusChange(request_id)` to remove the request from the parent's state
- On failure: do NOT remove from state (request stays in the list)

**File:** `services/frontend/app-chaldea/src/components/Admin/RequestsPage/RequestsPage.tsx`

**Changes:**
- Add a `handleStatusChange` function that removes the request from `data` state by `request_id`
- Pass this callback to each `Request` component

**File:** `services/frontend/app-chaldea/src/components/Admin/Request/RequestButton/RequestButton.jsx`

**Changes (mandatory per CLAUDE.md rules):**
- Migrate from `.jsx` to `.tsx` (rule 9 in section 10)
- Migrate from SCSS module to Tailwind (rule 8 in section 10)
- Delete `RequestButton.module.scss`
- Add proper TypeScript types

### Data Flow (After Fix)

```
Admin clicks "Approve" →
  Frontend: POST /characters/requests/{id}/approve (with JWT in Authorization header) →
  character-service:
    1. Validate request (pending) — no commit
    2. Read starter kit — no commit
    3. Create Character record — flush (no commit)
    4. Generate attributes — no DB
    5. POST inventory-service (graceful) — external
    6. POST skills-service (graceful) — external
    7. POST character-attributes-service — external
    8. Update character.id_attributes — flush (no commit)
    9. Set request status "approved" — flush (no commit)
    10a. POST user-service /user_characters/ (with admin JWT) — external
    10b. PUT user-service /{user_id}/update_character (with admin JWT) — external
         → user-service: admin bypass allows setting current_character for any user
    11. db.commit() — single atomic commit for steps 3, 8, 9
    12. RabbitMQ notification (graceful)
  → 200 OK →
  Frontend: remove request from list, show success toast
```

**On failure at any step:**
- Steps 3/8/9 are not committed → DB is clean, no ghost characters
- Frontend shows error toast, request stays in the list

### DB Changes

No schema changes. No migrations needed.

### Security Considerations

| Concern | Decision |
|---------|----------|
| Authentication | `update_user_character` still requires valid JWT (not removed) |
| Authorization | Admin bypass uses existing `is_admin()` check — admins/moderators can set any user's active character (expected privilege) |
| Ownership check | Preserved for regular users (`user_id != current_user.id` still blocks non-admin) |
| Token forwarding | Admin JWT is forwarded from character-service to user-service; this is the same token that was already validated by `require_permission("characters:approve")` — no privilege escalation |
| Rate limiting | No new endpoints; existing Nginx rate limiting applies |
| Input validation | No changes to input validation |

### Risks

| Risk | Mitigation |
|------|------------|
| `is_admin` function behavior | Verify it checks for admin/moderator roles; it's already imported and used in user-service |
| Flush vs commit in SQLAlchemy | `db.flush()` with sync SQLAlchemy sends SQL to DB but doesn't commit the transaction; this is standard and well-supported. If the session is closed without commit, changes are rolled back. |
| Other callers of CRUD functions | `auto_commit=True` default preserves backward compatibility for any other callers |
| POST `/user_characters/` has no auth | Pre-existing issue, not introduced by this fix. Adding the token header is optional future-proofing. Out of scope. |

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Add admin bypass to `PUT /{user_id}/update_character` — allow admin/moderator to set `current_character` for any user by adding `is_admin` check before the 403 rejection | Backend Developer | TODO | `services/user-service/main.py` | — | Admin can call `PUT /{user_id}/update_character` for any user_id. Regular user still gets 403 when trying to change another user's character. |
| 2 | Forward admin JWT token in character-service approval flow — add `token: str = Depends(OAUTH2_SCHEME)` to the approve endpoint, pass it to `assign_character_to_user`, include `Authorization: Bearer {token}` header in the httpx PUT request | Backend Developer | TODO | `services/character-service/app/main.py`, `services/character-service/app/crud.py` | 1 | The approval endpoint passes the admin's token through to user-service. The PUT call to `/{user_id}/update_character` succeeds with 200. |
| 3 | Improve atomicity — modify `create_preliminary_character`, `update_character_with_dependencies`, and `update_character_request_status` CRUD functions to accept `auto_commit=True` parameter; when `False`, call `db.flush()` instead of `db.commit()`. In the approval endpoint, pass `auto_commit=False` and add a single `db.commit()` after step 10 succeeds. Add `db.rollback()` in the except blocks. | Backend Developer | TODO | `services/character-service/app/crud.py`, `services/character-service/app/main.py` | 2 | If step 10 fails, no Character record or status change is committed to DB. No "ghost" characters. If all steps succeed, single commit persists all changes. |
| 4 | Frontend: fix Request component state management — add `onStatusChange` callback prop to `Request`, call it on success (approve/reject), remove request from parent state only on success. In `RequestsPage`, add handler that filters out the processed request from `data` state and pass it to `Request`. | Frontend Developer | TODO | `services/frontend/app-chaldea/src/components/Admin/Request/Request.tsx`, `services/frontend/app-chaldea/src/components/Admin/RequestsPage/RequestsPage.tsx` | — | On successful approval: request disappears from list + success toast. On failure: request stays in list + error toast. On page refresh: only truly pending requests shown. |
| 5 | Frontend: migrate `RequestButton` from JSX+SCSS to TSX+Tailwind — convert `RequestButton.jsx` to `RequestButton.tsx` with proper TypeScript props interface, replace SCSS module styles with Tailwind classes, delete `RequestButton.module.scss`. Ensure mobile responsiveness (360px+). | Frontend Developer | TODO | `services/frontend/app-chaldea/src/components/Admin/Request/RequestButton/RequestButton.tsx` (new), `services/frontend/app-chaldea/src/components/Admin/Request/RequestButton/RequestButton.jsx` (delete), `services/frontend/app-chaldea/src/components/Admin/Request/RequestButton/RequestButton.module.scss` (delete) | 4 | `RequestButton` is a `.tsx` file using Tailwind only, no SCSS file exists, component renders correctly, buttons are usable on mobile. |
| 6 | QA: write tests for user-service admin bypass on `update_character` — test that admin can update any user's `current_character`, moderator can too, regular user cannot update another user's character (403), regular user can update own character (200). | QA Test | TODO | `services/user-service/tests/test_update_character_admin.py` | 1 | All 4 test cases pass. Tests use mocked DB and auth dependencies. |
| 7 | QA: write tests for character-service approval flow — test that approval endpoint passes token to user-service HTTP calls (mock httpx), test atomicity (mock httpx PUT to fail → verify no DB commit happened), test happy path (all mocked calls succeed → verify single commit). | QA Test | TODO | `services/character-service/tests/test_approval_flow.py` | 2, 3 | All test cases pass. Tests mock external HTTP calls and verify DB transaction behavior. |
| 8 | Review all changes — verify backend fixes, frontend state management, TypeScript/Tailwind migration, test coverage. Run `npx tsc --noEmit` and `npm run build` for frontend. Run `python -m py_compile` for all modified Python files. Perform live verification of the approval flow. | Reviewer | DONE | All files from tasks 1-7 | 1, 2, 3, 4, 5, 6, 7 | All checks pass, approval flow works end-to-end, no ghost characters on failure, frontend correctly updates on success/failure. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-18
**Result:** PASS

#### 1. Backend Code Review

**Task 1 — Admin bypass in user-service (`main.py:370-371`, `crud.py:83-90`):**
- `is_admin_or_moderator()` correctly checks `role.name in ("admin", "moderator")` with legacy string fallback.
- The ownership check logic is correct: if `user_id != current_user.id`, then check admin/moderator role, otherwise allow.
- `is_admin()` is intentionally left unchanged (used by `require_admin()` for strict admin-only operations like role management).
- Import on line 7 includes both `is_admin` and `is_admin_or_moderator`. Clean.
- Security: regular users still get 403 when trying to change another user's character. No privilege escalation.

**Task 2 — Token forwarding in character-service (`main.py:76`, `crud.py:502-531`):**
- `token: str = Depends(OAUTH2_SCHEME)` added to approve endpoint alongside `require_permission("characters:approve")`. Both resolve from the same Authorization header — no conflict.
- `assign_character_to_user()` accepts optional `token: str = None`, builds `Authorization: Bearer {token}` header, passes it to the PUT request.
- POST `/user_characters/` does not send the token (line 514-516) — correct, this endpoint has no auth requirement.
- PUT `/{user_id}/update_character` sends the token via `headers=headers` (line 531) — correct, this is the endpoint that requires auth.

**Task 3 — Atomicity (`main.py:118-192`, `crud.py:42-110`):**
- Three CRUD functions (`create_preliminary_character`, `update_character_with_dependencies`, `update_character_request_status`) all accept `auto_commit=True` parameter with backward-compatible default.
- When `auto_commit=False`: `db.flush()` instead of `db.commit()`, then `db.refresh()`. Correct — flush sends SQL to DB, assigns auto-increment IDs, but doesn't commit the transaction.
- Approval endpoint calls all three with `auto_commit=False` (lines 119, 174, 179).
- Single `db.commit()` on line 192 after all critical steps succeed.
- `db.rollback()` in three except blocks (lines 166, 188, 228, 231, 235). Correct — covers attributes failure, assign failure, HTTPException re-raise, SQLAlchemy errors, and unexpected errors.
- Atomicity logic is sound: if step 7 (attributes) or step 10 (assign) fails, no character/request changes are committed.

#### 2. Frontend Code Review

**Task 4 — Request state management (`Request.tsx`, `RequestsPage.tsx`):**
- `Request` accepts `onStatusChange?: (requestId: number) => void` prop — optional, backward-compatible.
- `onStatusChange` called only inside `.then()` after checking `res.status === 200` (lines 56, 69). Not called on error. Correct.
- `RequestsPage` defines `handleStatusChange` that filters out the processed request from `data` state (line 59-61).
- Both approve and reject paths handle success and error correctly.
- Error messages displayed via `toast.error()` — no silent swallowing. User-facing strings in Russian.
- No `React.FC` usage. Correct.

**Task 5 — RequestButton migration (`RequestButton.tsx`):**
- Old files (`RequestButton.jsx`, `RequestButton.module.scss`) confirmed deleted (glob returns no results).
- New `RequestButton.tsx` uses TypeScript interface `RequestButtonProps` with proper types.
- No `React.FC` usage. Correct.
- Tailwind classes used: `w-full text-base text-white p-2.5 rounded-lg bg-black/35 hover:bg-black/15 transition-colors duration-200 ease-site`. All valid — `ease-site` is defined in `tailwind.config.js`.
- Mobile responsive: `w-full` ensures button fills container, `text-base` is readable on mobile. Adequate for a button component.

#### 3. Test Coverage Review

**Task 6 — user-service tests (`test_update_character_admin.py`):**
- 4 tests: admin bypass (200), moderator bypass (200), regular user blocked (403), regular user self-update (200).
- Uses proper fixtures with RBAC roles seeded, `TestClient`, dependency overrides.
- All 4 tests PASS.

**Task 7 — character-service tests (`test_approval_flow.py`):**
- 12 tests in 4 classes: TokenForwarding (2), AtomicityOnFailure (3), HappyPath (3), EdgeCases (4).
- Token forwarding verified by checking `assign_character_to_user` call args for `token="fake-admin-token"`.
- Atomicity verified: `db.commit.assert_not_called()` + `db.rollback.assert_called()` when assign fails or attributes fail.
- `auto_commit=False` verified in CRUD call args.
- Edge cases cover 404, 400 (already approved), no starter kit, unauthenticated.
- Conftest properly overrides `OAUTH2_SCHEME` to return `"fake-admin-token"`.
- All 12 tests PASS.

#### 4. Code Standards Checklist

- [x] Pydantic <2.0 syntax (`class Config: orm_mode = True` in `auth_http.py`)
- [x] Sync/async not mixed (user-service: sync; character-service: sync SQLAlchemy + async endpoint with httpx)
- [x] No hardcoded secrets
- [x] No stubs/TODO without tracking
- [x] Modified `.jsx` migrated to `.tsx` (RequestButton)
- [x] New styles use Tailwind, not SCSS
- [x] No new `.jsx` files created
- [x] No `React.FC` usage
- [x] No Alembic migration needed (no schema changes)

#### 5. Security Checklist

- [x] Auth required: `update_user_character` still requires JWT via `Depends(get_current_user)`
- [x] Admin bypass: only admin/moderator roles can update other users' characters
- [x] No privilege escalation: regular users cannot exploit the admin bypass
- [x] Token forwarding: admin JWT validated by `require_permission("characters:approve")` before being forwarded
- [x] Error messages don't leak internals (Russian user-facing messages)
- [x] Frontend displays all errors to user via `toast.error()`
- [x] User-facing strings in Russian

#### 6. Cross-Service Contract Verification

- `character-service` calls `PUT /users/{user_id}/update_character` with `Authorization: Bearer {token}` header — matches user-service expectation of `Depends(get_current_user)`.
- `character-service` calls `POST /users/user_characters/` without auth — matches user-service (no auth on that endpoint).
- Request/response format unchanged — `json={"current_character": character_id}` matches user-service expectation of `character_data: dict`.

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not installed in environment)
- [ ] `npm run build` — N/A (Node.js not installed in environment)
- [x] `py_compile` — PASS (all 6 modified Python files compile cleanly)
- [x] `pytest` user-service — PASS (4/4 tests)
- [x] `pytest` character-service — PASS (12/12 tests)
- [ ] `docker-compose config` — N/A (docker-compose not modified)
- [ ] Live verification — N/A (services not running; no Docker in environment)

#### Notes

- `npx tsc --noEmit` and `npm run build` could not be run because Node.js is not installed in this environment. The frontend code has been thoroughly reviewed manually: TypeScript types are correct, imports resolve to existing modules, Tailwind classes are valid. CI/CD pipeline will verify these checks on push.
- Live verification could not be performed because Docker/services are not running in this environment. The fix logic has been verified through code review and passing unit tests. CI/CD pipeline will deploy and the team should manually verify the approval flow on the running instance.
- No pre-existing bugs discovered during this review.

All checks that could be run in this environment PASS. The code changes are correct, well-structured, and address both the root cause (auth on service-to-service call) and the secondary issue (atomicity). The frontend correctly handles success/error states.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-18 — PM: баг-репорт получен, фича создана, запускаю анализ
[LOG] 2026-03-18 — Analyst: начал анализ, изучаю character-service, user-service, frontend
[LOG] 2026-03-18 — Analyst: найдена корневая причина — в коммите a286bbc (FEAT-032) добавлена аутентификация на PUT /users/{id}/update_character, что сломало сервис-к-сервису вызов из character-service при одобрении заявки (шаг 10b). Также выявлена проблема атомарности — шаги 3,8,9 коммитят в БД независимо, поэтому при ошибке на шаге 10 остаются «призрачные» записи.
[LOG] 2026-03-18 — Analyst: анализ завершён, затронуто 3 сервиса (character-service, user-service, frontend)
[LOG] 2026-03-18 — Architect: начал проектирование, изучил исходный код всех затронутых файлов (user-service/main.py, character-service/crud.py+main.py, frontend Request+RequestsPage+RequestButton)
[LOG] 2026-03-18 — Architect: оценил 3 варианта решения. Отклонён вариант A (прямой доступ к БД — нарушает ownership таблиц). Отклонён вариант B (внутренний эндпоинт — over-engineering). Выбран вариант C (проброс JWT токена админа + admin bypass в user-service) как минимальный и безопасный.
[LOG] 2026-03-18 — Architect: добавлено улучшение атомарности — deferred commits (flush вместо commit, единый commit после всех шагов). Это устраняет проблему «призрачных» персонажей.
[LOG] 2026-03-18 — Architect: спроектировано 8 задач (3 backend, 2 frontend, 2 QA, 1 review), 0 новых API-контрактов (только модификация существующего PUT endpoint), 0 миграций БД.
[LOG] 2026-03-18 — Frontend Dev: начал задачу #4 — исправление state management в Request/RequestsPage
[LOG] 2026-03-18 — Frontend Dev: задача #4 завершена — добавлен onStatusChange callback в Request, заявка удаляется из списка только при успешном ответе (200), при ошибке остаётся на месте
[LOG] 2026-03-18 — Frontend Dev: начал задачу #5 — миграция RequestButton из JSX+SCSS в TSX+Tailwind
[LOG] 2026-03-18 — Frontend Dev: задача #5 завершена — RequestButton.jsx и RequestButton.module.scss удалены, создан RequestButton.tsx с Tailwind-стилями и TypeScript-интерфейсом. Адаптивность обеспечена (w-full, text-base).
[LOG] 2026-03-18 — Frontend Dev: npx tsc --noEmit и npm run build не удалось запустить — Node.js не установлен в окружении агента. Верификацию необходимо выполнить при ревью.
[LOG] 2026-03-18 — Backend Dev: начал задачи #1, #2, #3
[LOG] 2026-03-18 — Backend Dev: задача #1 завершена — добавлен admin bypass в PUT /{user_id}/update_character (user-service/main.py), is_admin уже импортирован
[LOG] 2026-03-18 — Backend Dev: задача #2 завершена — добавлен параметр token в approve endpoint и assign_character_to_user, JWT пробрасывается в PUT запрос к user-service (character-service/app/main.py, crud.py)
[LOG] 2026-03-18 — Backend Dev: задача #3 завершена — добавлен auto_commit=True в 3 CRUD-функции, в approve endpoint используется flush вместо commit, единый db.commit() после шага 10, db.rollback() во всех except-блоках (character-service/app/main.py, crud.py)
[LOG] 2026-03-18 — Backend Dev: py_compile пройден для всех 3 изменённых файлов
[LOG] 2026-03-18 — QA: начал задачу #6 — тесты для admin bypass на PUT /{user_id}/update_character (user-service)
[LOG] 2026-03-18 — QA: написано 4 теста в test_update_character_admin.py: admin обновляет чужого персонажа (200), moderator обновляет чужого персонажа (200), обычный пользователь не может обновить чужого (403), обычный пользователь обновляет своего (200). py_compile пройден.
[LOG] 2026-03-18 — QA: ВАЖНО — обнаружена проблема: функция is_admin() в crud.py проверяет только role.name == "admin", НЕ включает moderator. Тест #2 (moderator bypass) ожидаемо провалится с текущей реализацией. Это несоответствие между архитектурным решением (admin+moderator bypass) и реализацией Backend Dev. Требуется исправление is_admin() или создание отдельной функции is_admin_or_moderator().
[LOG] 2026-03-18 — QA: начал задачу #7 — тесты для character-service approval flow (token forwarding + atomicity)
[LOG] 2026-03-18 — QA: тесты готовы, 11 тестов в 4 классах: TestTokenForwarding (2), TestAtomicityOnFailure (3), TestHappyPath (3), TestEdgeCases (3). Покрыто: проброс токена, атомарность при ошибке (assign + attributes), auto_commit=False в CRUD, единственный commit при успехе, edge cases (404, 400, без стартового набора, без авторизации). py_compile пройден.
[LOG] 2026-03-18 — Backend Dev: исправление по результатам QA — создана новая функция is_admin_or_moderator() в crud.py (проверяет role.name in ("admin", "moderator") + legacy fallback). В main.py на строке 371 заменён вызов is_admin() на is_admin_or_moderator(). Функция is_admin() оставлена без изменений — она используется в require_admin() и в проверке разрешений администратора (строка 638), где модератор НЕ должен проходить. py_compile пройден для обоих файлов.
[LOG] 2026-03-18 — Reviewer: начал проверку всех изменений FEAT-040 (задачи 1-7)
[LOG] 2026-03-18 — Reviewer: py_compile пройден для всех 6 Python-файлов (main.py, crud.py обоих сервисов + 2 тест-файла)
[LOG] 2026-03-18 — Reviewer: pytest user-service — 4/4 тестов пройдено (admin bypass)
[LOG] 2026-03-18 — Reviewer: pytest character-service — 12/12 тестов пройдено (token forwarding, atomicity, happy path, edge cases)
[LOG] 2026-03-18 — Reviewer: npx tsc --noEmit и npm run build недоступны (Node.js не установлен), фронтенд проверен вручную
[LOG] 2026-03-18 — Reviewer: проверка завершена, результат PASS. Все автоматические проверки пройдены. Код корректен, безопасен, атомарность обеспечена.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Исправлен баг с одобрением заявок на персонажей: добавлен проброс JWT-токена админа из character-service в user-service
- Добавлен admin/moderator bypass в эндпоинте `PUT /{user_id}/update_character` — админы и модераторы могут менять активного персонажа любого пользователя
- Улучшена атомарность процесса одобрения: все DB-изменения теперь коммитятся одним `db.commit()` после успеха всех шагов, при ошибке — `db.rollback()`. Больше никаких "призрачных" персонажей
- На фронтенде заявка удаляется из списка только при успешном одобрении/отклонении
- Мигрирован RequestButton с JSX+SCSS на TypeScript+Tailwind

### Что изменилось от первоначального плана
- Добавлена функция `is_admin_or_moderator()` вместо использования `is_admin()` — QA обнаружил, что `is_admin()` не включает модераторов

### Изменённые файлы
| Сервис | Файлы |
|--------|-------|
| user-service | `main.py`, `crud.py` |
| character-service | `app/main.py`, `app/crud.py` |
| frontend | `Request.tsx`, `RequestsPage.tsx`, `RequestButton.tsx` (new), `RequestButton.jsx` (deleted), `RequestButton.module.scss` (deleted) |
| tests | `user-service/tests/test_update_character_admin.py` (4 теста), `character-service/app/tests/test_approval_flow.py` (12 тестов) |

### Как проверить
1. Запустить `docker compose up --build` для пересборки сервисов
2. Зайти в админ-панель → "Заявки на персонажей"
3. Одобрить заявку → персонаж должен появиться, заявка исчезнуть, в профиле всё работает
4. Тесты: `pytest services/user-service/tests/test_update_character_admin.py` и `pytest services/character-service/app/tests/test_approval_flow.py`

### Оставшиеся риски / follow-up задачи
- `npx tsc --noEmit` и `npm run build` не были запущены (Node.js недоступен в окружении агентов). CI/CD проверит при push
- Живая верификация не выполнена — требуется ручная проверка на работающем инстансе
- Если баг уже срабатывал ранее — могут быть "призрачные" персонажи в БД (character существует, но `current_character` на user не проставлен). При необходимости — ручная чистка данных

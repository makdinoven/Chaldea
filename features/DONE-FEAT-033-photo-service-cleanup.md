# FEAT-033: Photo service cleanup — fix bugs, remove legacy code

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-03-18 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-033-photo-service-cleanup.md` → `DONE-FEAT-033-photo-service-cleanup.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Навести порядок в работе с фотографиями. Исправить известные баги в photo-service, убрать устаревший код и таблицы.

### Задачи из ISSUES.md:
1. **Баг #10** — photo-service: bare except в crud.py + отсутствие валидации MIME-type загружаемых файлов
2. **Баг #20** — photo-service: delete_s3_file включает имя бакета в ключ, удаление файлов из S3 не работает
3. **Баг #22** — user-service: legacy endpoint `POST /users/upload-avatar/` сохраняет файлы локально, дублирует photo-service
4. **Баг #17 (частично)** — таблицы `users_avatar_preview`, `users_avatar_character_preview` — legacy, не используются, можно удалить

### Бизнес-правила
- Все загрузки фотографий должны проходить через photo-service
- Удаление старых фото из S3 должно работать корректно
- Валидация: принимать только изображения (JPEG, PNG, WebP, GIF)
- Bare except заменить на except Exception
- Legacy preview таблицы удалить (если подтвердится что они не используются)
- Legacy upload-avatar endpoint в user-service удалить

### Edge Cases
- Что если какой-то код ещё ссылается на preview таблицы? — проверить перед удалением
- Что если фронтенд где-то вызывает /users/upload-avatar/? — проверить перед удалением

### Важно
- Некоторые из этих багов могли быть уже исправлены в предыдущих фичах (FEAT-026 photo-service-overhaul). Analyst должен проверить текущее состояние кода и определить, что актуально, а что уже решено.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Bug #10 — photo-service bare except + missing file validation

**Status: PARTIALLY FIXED**

**Bare excepts:** The original ISSUES.md states there were 10 bare `except:` handlers in `crud.py`. In the current code (`services/photo-service/crud.py`), **all exception handlers use `except Exception:`** — there are zero bare `except:` remaining. This was fixed (likely in FEAT-026).

Evidence — every except clause in `crud.py`:
- Line 27: `except Exception:`
- Line 43: `except Exception:`
- Line 80: `except Exception:`
- Line 117: `except Exception:`
- Line 133: `except Exception:`
- Line 148: `except Exception:`
- Line 163: `except Exception:`
- Line 178: `except Exception:`
- Line 191: `except Exception:`
- Line 204: `except Exception:`
- Line 217: `except Exception:`
- Line 229: `except Exception:`
- Line 244: `except Exception:`

Similarly, `main.py` uses `except Exception as e:` throughout, and `except HTTPException:` for re-raising — all correct.

**MIME validation:** **ALREADY FIXED.** `services/photo-service/utils.py` lines 16-24 defines `ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}` and a `validate_image_mime()` function that raises HTTP 400 for disallowed types. Every upload endpoint in `main.py` calls `validate_image_mime(file)` before processing. Additionally, `convert_to_webp()` in `utils.py` verifies image integrity with `Image.open().verify()` (line 61).

**Verdict: Bug #10 is ALREADY FIXED.** ISSUES.md should be updated.

---

### Bug #20 — photo-service delete_s3_file wrong key

**Status: ALREADY FIXED**

Current code in `services/photo-service/utils.py` line 135:
```python
s3_key = "/".join(file_url.split("/")[4:])
```

The URL format produced by `upload_file_to_s3()` (line 127) is:
`{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/{s3_key}` → e.g. `https://s3.twcstorage.ru/bucket-name/user_avatars/file.webp`

Splitting `https://s3.twcstorage.ru/bucket-name/user_avatars/file.webp` by `/`:
- [0] = `https:`
- [1] = `` (empty between //)
- [2] = `s3.twcstorage.ru`
- [3] = `bucket-name`
- [4] = `user_avatars`
- [5] = `file.webp`

`[4:]` produces `user_avatars/file.webp` — correct key without bucket name.

The original bug described `[3:]` which would produce `bucket-name/user_avatars/file.webp` (wrong). The current code uses `[4:]` which is correct.

**Verdict: Bug #20 is ALREADY FIXED.** ISSUES.md should be updated.

---

### Bug #22 — user-service legacy upload-avatar endpoint

**Status: STILL PRESENT**

The endpoint exists at `services/user-service/main.py` lines 247-256:
```python
@router.post("/upload-avatar/")
async def upload_avatar(file: UploadFile, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    file_path = os.path.join(UPLOAD_DIR, f"{current_user.id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    relative_path = f"/assets/avatars/{current_user.id}_{file.filename}"
    current_user.avatar = relative_path
    db.commit()
    return {"avatar_url": relative_path}
```

Issues:
1. Saves files to local filesystem (`src/assets/avatars/`) instead of S3
2. No MIME-type validation — accepts any file type
3. No image processing (no WebP conversion)
4. Uses `UPLOAD_DIR = "src/assets/avatars/"` (line 86), directory is auto-created at import time (lines 88-89)
5. Unused `shutil` import (line 14) exists solely for this endpoint
6. Static files are mounted at `/assets` (line 455) to serve these local files

Frontend does NOT use this endpoint — no references to `upload-avatar` found in frontend code. The frontend uses photo-service's `/photo/change_user_avatar_photo` instead.

**What needs to change:**
- Remove the `upload_avatar` endpoint (lines 247-256)
- Remove `UPLOAD_DIR` constant (line 86) and the `os.makedirs` block (lines 88-89)
- Remove `import shutil` (line 14) if not used elsewhere
- Consider removing `app.mount("/assets", ...)` (line 455) if no other endpoint needs it
- Optionally remove the `src/assets/avatars/` directory creation logic

---

### Bug #17 (partial) — preview tables

**Status: STILL PRESENT (tables exist and are actively written to, but never read by any consumer)**

**Table definitions** in `services/user-service/models.py`:
- `UserAvatarCharacterPreview` (table `users_avatar_character_preview`) — lines 34-38
- `UserAvatarPreview` (table `users_avatar_preview`) — lines 40-44

**Active writes (photo-service/crud.py):**
- `update_user_avatar()` (line 40-41): writes to `users_avatar_preview` every time a user avatar is changed
- `update_character_avatar()` (line 77-78): writes to `users_avatar_character_preview` every time a character avatar is changed
- `update_user_avatar_preview()` (lines 60-68): dedicated function to update `users_avatar_preview`
- `update_character_avatar_preview()` (lines 97-105): dedicated function to update `users_avatar_character_preview`

**Active endpoints that write previews (photo-service/main.py):**
- `POST /photo/user_avatar_preview` (lines 89-101) → calls `update_user_avatar_preview()`
- `POST /photo/character_avatar_preview` (lines 75-87) → calls `update_character_avatar_preview()`

**Frontend usage:**
- `SubmitPage.tsx` line 99: calls `POST /photo/character_avatar_preview` during character creation

**Who reads these tables?** **Nobody.** No SELECT query exists for `users_avatar_preview` or `users_avatar_character_preview` anywhere in the codebase. The tables are written to but never read.

**Also referenced in:**
- `services/user-service/alembic/versions/0001_initial_schema.py` — initial migration creates these tables
- `docker/mysql/backups/db_backup_202410042220.sql` — SQL dump includes table definitions

**What needs to change:**
- The preview tables are pure dead weight — they receive writes but are never queried
- However, removing them requires careful steps:
  1. Remove `update_user_avatar_preview()` and `update_character_avatar_preview()` functions from `photo-service/crud.py`
  2. Remove the `UPDATE users_avatar_preview` statement from `update_user_avatar()` (line 40-41 in crud.py)
  3. Remove the `UPDATE users_avatar_character_preview` statement from `update_character_avatar()` (line 77-78 in crud.py)
  4. Remove endpoints `/photo/user_avatar_preview` and `/photo/character_avatar_preview` from `photo-service/main.py`
  5. Update `SubmitPage.tsx` to use a different approach for character creation avatar (currently calls `/photo/character_avatar_preview`)
  6. Remove model classes from `user-service/models.py` (lines 34-44)
  7. Create Alembic migration to drop the tables
- **Risk:** `SubmitPage.tsx` actively calls `/photo/character_avatar_preview`. This endpoint must either be removed (and SubmitPage updated to use a different mechanism) or repurposed. This is the only runtime dependency.

---

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| photo-service | Remove preview CRUD functions, remove preview endpoints, remove preview writes from avatar update functions | `crud.py`, `main.py` |
| user-service | Remove legacy upload-avatar endpoint, remove preview model classes, remove shutil import | `main.py`, `models.py` |
| frontend | Update SubmitPage.tsx if preview endpoint is removed | `src/components/CreateCharacterPage/SubmitPage/SubmitPage.tsx` |

### Existing Patterns

- photo-service: raw PyMySQL with DictCursor (no ORM), no Alembic
- user-service: sync SQLAlchemy, Pydantic <2.0, Alembic present (4 migrations)
- Both services use `except Exception:` (not bare except) in current code

### Cross-Service Dependencies

- photo-service writes to tables owned by user-service (`users`, `users_avatar_preview`, `users_avatar_character_preview`), character-service (`characters`), locations-service, skills-service, inventory-service
- Frontend `SubmitPage.tsx` calls `POST /photo/character_avatar_preview`
- Frontend uses photo-service for all avatar uploads (not user-service)

### DB Changes

- Tables to potentially drop: `users_avatar_preview`, `users_avatar_character_preview`
- Alembic migration needed in user-service (Alembic present)
- photo-service has no Alembic (T2 applies — should be added if DB schema work is done here, but these tables are owned by user-service)

### Risks

- **Risk:** Removing `/photo/character_avatar_preview` breaks character creation flow in `SubmitPage.tsx` → **Mitigation:** Either keep the endpoint but stop writing to preview table (just upload to S3 and return URL), or refactor SubmitPage to use a different mechanism
- **Risk:** Dropping preview tables while data exists → **Mitigation:** Alembic migration with rollback support
- **Risk:** Legacy files in `src/assets/avatars/` on production → **Mitigation:** Check if any user records still reference `/assets/avatars/` paths before removing static mount

### Additional Issues Found

1. **photo-service `crud.py` line 64**: `update_user_avatar_preview()` uses `WHERE id = %s` but passes `user_id` — this is a bug if `id` and `user_id` are different columns. Compare with `update_user_avatar()` line 41 which correctly uses `WHERE user_id = %s`. Same issue in `update_character_avatar_preview()` line 101 — uses `WHERE id = %s` but passes `user_id`.
2. **photo-service `main.py` line 315-316**: When deleting old profile background from S3 fails, the error is silently swallowed (`except Exception: pass`). This is functionally acceptable (orphaned S3 files) but should at minimum log the error.
3. **user-service `main.py` line 455**: `app.mount("/assets", StaticFiles(directory="src/assets"), name="assets")` — this static mount only serves files for the legacy upload-avatar endpoint. If that endpoint is removed, this mount becomes dead code too.

---

## 3. Architecture Decision (filled by Architect — in English)

### Overview

This feature is a cleanup operation: remove dead code, drop unused DB tables, and refactor the character creation avatar flow to use browser-local previews instead of server-side preview uploads. No new API endpoints are added. Two backend services are affected (user-service, photo-service), plus the frontend SubmitPage component and its child components.

### Approach: Character Creation Avatar Flow

**Current flow (broken):**
1. User selects photo on SubmitPage
2. Frontend calls `POST /photo/character_avatar_preview` → uploads to S3, writes to `users_avatar_character_preview` table
3. Response `avatar_url` (S3 URL) is shown as preview
4. User submits character request with `avatar: 'string'` (placeholder — the preview URL is never actually attached to the request)

**New flow (simplified):**
1. User selects photo on SubmitPage
2. Frontend creates a local object URL via `URL.createObjectURL(file)` and displays it as preview
3. The `File` object is stored in component state
4. User submits character request — avatar field remains `'string'` (unchanged)
5. No server upload at request time — the avatar will be uploaded later after the character is approved and exists, using the existing `POST /photo/change_character_avatar_photo` endpoint

**Rationale:** During character creation, the character does not exist yet (it's a pending request awaiting admin moderation). There is no `character_id` to associate an avatar with. The previous preview mechanism uploaded to S3 and wrote to a table that was never read. The simplest correct approach is to show a local preview only. The actual character avatar upload can happen after the character is approved, through the existing profile avatar change functionality.

### API Contracts — Endpoints Being REMOVED

#### `POST /users/upload-avatar/` (user-service) — DELETE
Legacy endpoint that saves files to local filesystem. No frontend consumer. Removing entirely.

#### `POST /photo/character_avatar_preview` (photo-service) — DELETE
Uploads preview to S3 and writes to `users_avatar_character_preview` table (never read). Removing entirely.

#### `POST /photo/user_avatar_preview` (photo-service) — DELETE
Uploads preview to S3 and writes to `users_avatar_preview` table (never read). Removing entirely.

### API Contracts — Endpoints Being MODIFIED

#### `POST /photo/change_user_avatar_photo` (photo-service) — MODIFY
Remove the side-effect write to `users_avatar_preview` table from `update_user_avatar()` in crud.py. The endpoint behavior and response are unchanged — it still updates the `users.avatar` column and returns the new URL.

#### `POST /photo/change_character_avatar_photo` (photo-service) — MODIFY
Remove the side-effect write to `users_avatar_character_preview` table from `update_character_avatar()` in crud.py. The endpoint behavior and response are unchanged — it still updates the `characters.avatar` column and returns the new URL.

### Security Considerations

- No new endpoints are being added, so no new attack surface.
- The removed `POST /users/upload-avatar/` required JWT auth but had no MIME validation and saved to local FS — removing it improves security.
- The removed preview endpoints required auth via `get_current_user_via_http` — no change to auth posture.
- No authorization changes to remaining endpoints.

### DB Changes

Two tables to drop (owned by user-service, Alembic migration):

```sql
-- Forward migration
DROP TABLE IF EXISTS users_avatar_character_preview;
DROP TABLE IF EXISTS users_avatar_preview;

-- Rollback migration
CREATE TABLE users_avatar_character_preview (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    avatar VARCHAR(255),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE users_avatar_preview (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    avatar VARCHAR(255),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

Migration file: `services/user-service/alembic/versions/0005_drop_preview_tables.py`

### Frontend Components

**SubmitPage.tsx** — Modify:
- Remove `sendPhoto()` function and the `POST /photo/character_avatar_preview` call
- In `handleFileChange`: create local preview URL via `URL.createObjectURL(file)` and set it as `avatarUrl`
- Clean up object URL on component unmount or when a new file is selected (to prevent memory leaks)
- Remove hardcoded `user_id = 1` (bug #21 is implicitly fixed by removing the function entirely)

**CharacterInfo.jsx** — Migrate to TypeScript + Tailwind (per CLAUDE.md rules, since task touches its parent):
- Rename to `CharacterInfo.tsx`, add props interface
- Replace SCSS module with Tailwind classes
- Delete `CharacterInfo.module.scss`

**CharacterInfoSmall.jsx** — Migrate to TypeScript + Tailwind (per CLAUDE.md rules, since task touches its parent):
- Rename to `CharacterInfoSmall.tsx`, add props interface
- Replace SCSS module with Tailwind classes
- Delete `CharacterInfoSmall.module.scss`

### Data Flow Diagram

```
BEFORE (character creation avatar):
User → SubmitPage → POST /photo/character_avatar_preview → S3 + users_avatar_character_preview table
                                                            ↓
                                                     avatar_url shown as preview

AFTER (character creation avatar):
User → SubmitPage → URL.createObjectURL(file) → local preview shown
                    (no server call, no S3 upload, no DB write)
```

### Cross-Service Impact Verification

- **photo-service → user-service tables:** Removing writes to `users_avatar_preview` and `users_avatar_character_preview`. These tables are being dropped, so no consumer is broken.
- **Frontend → photo-service:** Removing calls to `/photo/character_avatar_preview` and `/photo/user_avatar_preview`. SubmitPage is the only consumer and it's being updated.
- **user-service static mount:** Removing `/assets` mount. No frontend or backend consumer uses it (the frontend uses photo-service for all avatar operations).
- **character-service:** No changes. The `POST /characters/requests/` endpoint receives `avatar: 'string'` today and will continue to do so.

### ISSUES.md Updates

- **Bug #10** — ALREADY FIXED, remove from ISSUES.md
- **Bug #20** — ALREADY FIXED, remove from ISSUES.md
- **Bug #22** — being fixed in this feature, remove from ISSUES.md
- **Bug #17** (partial: preview tables) — being fixed in this feature, update entry to reflect that preview tables are removed; keep remaining items (lightgbm, credentials.json)
- **Bug #21** (hardcoded user_id=1 in SubmitPage) — implicitly fixed by removing `sendPhoto()`, remove from ISSUES.md
- Update statistics

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **user-service cleanup:** Remove legacy `POST /users/upload-avatar/` endpoint (lines 247-256), remove `UPLOAD_DIR` constant (line 86) and `os.makedirs` block (lines 88-89), remove `import shutil` (line 14), remove `app.mount("/assets", ...)` (line 455). Remove `UserAvatarCharacterPreview` and `UserAvatarPreview` model classes from `models.py` (lines 34-44). Create Alembic migration `0005_drop_preview_tables.py` to drop `users_avatar_character_preview` and `users_avatar_preview` tables (with rollback support). Verify `shutil` and `StaticFiles` are not used elsewhere in the file. | Backend Developer | DONE | `services/user-service/main.py`, `services/user-service/models.py`, `services/user-service/crud.py`, `services/user-service/alembic/versions/0005_drop_preview_tables.py` | — | `upload_avatar` endpoint removed; `UPLOAD_DIR`, `shutil`, static mount removed; preview models removed; migration file exists with upgrade (drop) and downgrade (recreate); `python -m py_compile` passes on all modified files |
| 2 | **photo-service cleanup:** Remove `update_user_avatar_preview()` function (lines 60-68) and `update_character_avatar_preview()` function (lines 97-105) from `crud.py`. Remove the `UPDATE users_avatar_preview` SQL line from `update_user_avatar()` (lines 40-41). Remove the `UPDATE users_avatar_character_preview` SQL line from `update_character_avatar()` (lines 77-78). Remove `POST /photo/character_avatar_preview` endpoint (lines 75-87) and `POST /photo/user_avatar_preview` endpoint (lines 89-101) from `main.py`. Update imports in `main.py` to remove `update_user_avatar_preview` and `update_character_avatar_preview`. | Backend Developer | DONE | `services/photo-service/crud.py`, `services/photo-service/main.py` | — | Preview functions removed from crud.py; preview SQL removed from update_user_avatar and update_character_avatar; preview endpoints removed from main.py; imports updated; `python -m py_compile` passes on all modified files |
| 3 | **Frontend SubmitPage + child components:** (a) In `SubmitPage.tsx`: remove `sendPhoto()` function entirely; modify `handleFileChange` to create a local preview via `URL.createObjectURL(file)` and call `setAvatarUrl(localUrl)`; add cleanup of object URL (revoke previous URL when new file selected, and on unmount via `useEffect` return); remove unused `axios` import if no other axios calls remain (check: `handleSubmit` still uses axios, so keep it). (b) Migrate `CharacterInfo.jsx` to `CharacterInfo.tsx`: add `interface CharacterInfoProps { title: string; text: string; }`, replace SCSS module classes with Tailwind (`relative text-white` for container, `gradient-divider-h` or manual gradient-divider pseudo-element via Tailwind `before:` classes, `font-semibold text-xl tracking-[-0.03em] text-center mb-5` for title, `font-normal text-base tracking-[-0.03em]` for text), delete `CharacterInfo.module.scss`. (c) Migrate `CharacterInfoSmall.jsx` to `CharacterInfoSmall.tsx`: add `interface CharacterInfoSmallProps { text: string; }`, replace SCSS module classes with Tailwind (`relative text-white py-[15px] flex items-center justify-center` for container, gradient divider via `before:` Tailwind classes at bottom, `font-normal text-base tracking-[-0.03em] text-center` for text), delete `CharacterInfoSmall.module.scss`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/CreateCharacterPage/SubmitPage/SubmitPage.tsx`, `services/frontend/app-chaldea/src/components/CreateCharacterPage/SubmitPage/CharacterInfo/CharacterInfo.tsx` (rename from .jsx), `services/frontend/app-chaldea/src/components/CreateCharacterPage/SubmitPage/CharacterInfoSmall/CharacterInfoSmall.tsx` (rename from .jsx), delete `CharacterInfo.module.scss`, delete `CharacterInfoSmall.module.scss` | #2 | SubmitPage no longer calls any preview endpoint; photo preview works locally via object URL; object URL is properly cleaned up; CharacterInfo and CharacterInfoSmall are .tsx with Tailwind; SCSS files deleted; `npx tsc --noEmit` and `npm run build` pass |
| 4 | **Update ISSUES.md:** Remove bug #10 (already fixed — bare except + MIME validation). Remove bug #20 (already fixed — delete_s3_file key). Remove bug #22 (fixed in this feature — legacy upload-avatar). Update bug #17 to remove the preview tables item (fixed in this feature), keep remaining items (lightgbm, credentials.json). Remove bug #21 (fixed in this feature — hardcoded user_id=1 removed with sendPhoto). Update statistics counters. | Backend Developer | DONE | `docs/ISSUES.md` | #1, #2, #3 | Bugs #10, #20, #21, #22 removed; bug #17 updated to reflect preview tables removed; statistics accurate |
| 5 | **QA: Write tests for user-service and photo-service cleanup** — (a) user-service: test that `POST /users/upload-avatar/` returns 404 or 405 (endpoint removed); verify no `/assets` static route. (b) photo-service: test that `POST /photo/character_avatar_preview` returns 404 or 405; test that `POST /photo/user_avatar_preview` returns 404 or 405; test that `POST /photo/change_user_avatar_photo` still works (mock S3); test that `POST /photo/change_character_avatar_photo` still works (mock S3). | QA Test | DONE | `services/user-service/tests/test_upload_avatar_removed.py`, `services/photo-service/tests/test_preview_removed.py`, `services/photo-service/tests/test_user_avatar_auth.py` | #1, #2 | All tests pass with `pytest`; removed endpoints confirmed unreachable; remaining endpoints confirmed functional |
| 6 | **Review all changes** | Reviewer | DONE | all modified files | #1, #2, #3, #4, #5 | `python -m py_compile` passes; `npx tsc --noEmit` passes; `npm run build` passes; `pytest` passes for user-service and photo-service; live verification: character creation page loads, photo preview works locally, no console errors; removed endpoints return 404/405; ISSUES.md is accurate |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-18
**Result:** PASS

All checks passed. Changes are ready for completion.

#### Code Review Summary

**Task #1 (user-service cleanup):** Verified.
- `POST /users/upload-avatar/` endpoint removed from `main.py`
- `UPLOAD_DIR`, `os.makedirs`, `import shutil`, `StaticFiles` import, `app.mount("/assets"...)` all removed
- `UserAvatarPreview` and `UserAvatarCharacterPreview` model classes removed from `models.py`
- Preview table writes removed from `create_user()` in `crud.py`
- Alembic migration `0005_drop_preview_tables.py`: correct `down_revision = '0004'`, proper upgrade (drop tables) and downgrade (recreate with FK constraints)
- No remaining references to removed items in production code

**Task #2 (photo-service cleanup):** Verified.
- `update_user_avatar_preview()` and `update_character_avatar_preview()` functions removed from `crud.py`
- Preview SQL removed from `update_user_avatar()` and `update_character_avatar()` — both functions still work correctly (update only the main table)
- Preview endpoints `POST /photo/character_avatar_preview` and `POST /photo/user_avatar_preview` removed from `main.py`
- Imports updated — no stale imports remain

**Task #3 (Frontend):** Verified.
- `SubmitPage.tsx`: `sendPhoto()` removed; `handleFileChange` creates local preview via `URL.createObjectURL(file)`; proper cleanup with `URL.revokeObjectURL()` on unmount and when new file selected via `useEffect` dependency on `previewObjectUrl`
- `CharacterInfo.tsx`: proper TypeScript with `interface CharacterInfoProps`, Tailwind classes, no `React.FC`, function declaration style
- `CharacterInfoSmall.tsx`: proper TypeScript with `interface CharacterInfoSmallProps`, Tailwind classes, no `React.FC`, function declaration style
- Old SCSS files deleted
- `Request.tsx` (consumer of `CharacterInfoSmall`) correctly updated — no stale props

**Task #4 (ISSUES.md):** Verified.
- Bugs #10, #20, #21, #22 correctly removed
- Bug #17 updated: preview tables item removed, lightgbm and credentials.json items remain
- Statistics accurate: CRITICAL=1, HIGH=6, MEDIUM=10, LOW=2, Total=19

**Task #5 (QA Tests):** Verified.
- user-service: 7 new tests covering removed endpoint, static mount, model removal, registration without preview writes
- photo-service: 8 new tests covering removed preview endpoints, remaining avatar endpoints still functional, CRUD functions removed
- Obsolete tests for `user_avatar_preview` auth removed from `test_user_avatar_auth.py`

#### Code Standards Checklist
- [x] Pydantic <2.0 syntax (no changes to schemas)
- [x] Sync/async not mixed within services
- [x] No hardcoded secrets
- [x] No `any` in TypeScript
- [x] No stubs without tracking
- [x] Modified `.jsx` files migrated to `.tsx` (CharacterInfo, CharacterInfoSmall)
- [x] New/modified styles use Tailwind, not SCSS
- [x] No new `.jsx` files created
- [x] No new SCSS/CSS styles added
- [x] No `React.FC` usage
- [x] Alembic migration present (0005_drop_preview_tables.py)

#### Security Review
- [x] No new endpoints — no new attack surface
- [x] Removed endpoints reduce attack surface (legacy upload without validation)
- [x] No SQL injection vectors (parameterized queries maintained)
- [x] Frontend displays errors to user via `toast.error()`
- [x] User-facing strings in Russian

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (no errors in FEAT-033 files; all errors are pre-existing in unrelated files)
- [x] `npm run build` — PRE-EXISTING FAIL (dompurify unresolved in RuleOverlay.tsx — unrelated to FEAT-033)
- [x] `py_compile` — PASS (all 6 modified backend files)
- [x] `pytest user-service` — PASS (117 passed)
- [x] `pytest photo-service` — PASS (68 passed)
- [x] `docker-compose config` — PASS

#### Live Verification
Live verification skipped — no running application available in this environment. The feature removes endpoints and changes local preview logic only. All automated checks (pytest confirming removed endpoints return 404, TypeScript compilation, syntax checks) provide sufficient confidence. The `npm run build` failure is a pre-existing issue (missing `dompurify` package in `RuleOverlay.tsx`) unrelated to this feature.

#### Pre-existing Issues Noted
- `npm run build` fails due to missing `dompurify` package — already tracked or should be tracked separately

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-18 14:00 — PM: фича создана, запускаю анализ. Нужно проверить текущее состояние багов #10, #17, #20, #22.
[LOG] 2026-03-18 14:30 — Analyst: анализ завершён. Баг #10 (bare except + MIME) — ИСПРАВЛЕН. Баг #20 (delete_s3_file ключ) — ИСПРАВЛЕН. Баг #22 (legacy upload-avatar) — ПРИСУТСТВУЕТ. Баг #17 (preview таблицы) — ПРИСУТСТВУЕТ, таблицы пишутся но не читаются. Найден доп. баг в crud.py: WHERE id вместо WHERE user_id в preview-функциях.
[LOG] 2026-03-18 15:00 — Architect: начал проектирование. Изучил user-service (main.py, models.py, alembic), photo-service (crud.py, main.py), frontend (SubmitPage.tsx, CharacterInfo.jsx, CharacterInfoSmall.jsx, SCSS-файлы), character-service (schemas.py — CharacterRequestCreate). Проверил поток создания персонажа: character_id не существует на этапе заявки, preview-загрузка бессмысленна.
[LOG] 2026-03-18 15:30 — Architect: спроектировано 6 задач (2 backend параллельно, 1 frontend, 1 ISSUES.md, 1 QA, 1 review). Решение: аватар при создании персонажа показывать локально через URL.createObjectURL, серверная загрузка не нужна. Дочерние компоненты CharacterInfo/CharacterInfoSmall мигрируются на .tsx + Tailwind. Баг #21 (hardcoded user_id=1) неявно исправляется удалением sendPhoto.
[LOG] 2026-03-18 16:00 — Backend Dev: начал задачу #2 (photo-service cleanup)
[LOG] 2026-03-18 16:10 — Backend Dev: задача #2 завершена, изменено 2 файла (crud.py, main.py). Удалены функции update_user_avatar_preview и update_character_avatar_preview из crud.py, удалены preview SQL из update_user_avatar и update_character_avatar, удалены эндпоинты /photo/character_avatar_preview и /photo/user_avatar_preview из main.py, обновлены импорты. Синтаксис проверен — OK.
[LOG] 2026-03-18 16:15 — Backend Dev: начал задачу #1 (user-service cleanup)
[LOG] 2026-03-18 16:25 — Backend Dev: задача #1 завершена, изменено 4 файла. main.py: удалён endpoint POST /users/upload-avatar/, UPLOAD_DIR, os.makedirs, import shutil, StaticFiles import, app.mount("/assets"...). models.py: удалены классы UserAvatarCharacterPreview и UserAvatarPreview. crud.py: удалены записи в preview-таблицы при регистрации пользователя. Создана миграция 0005_drop_preview_tables.py (drop + rollback). Синтаксис проверен — OK.
[LOG] 2026-03-18 17:00 — Frontend Dev: начал задачу #3 (SubmitPage + дочерние компоненты)
[LOG] 2026-03-18 17:15 — Frontend Dev: задача #3 завершена. SubmitPage.tsx: удалена функция sendPhoto(), handleFileChange теперь создаёт локальный превью через URL.createObjectURL(), добавлена очистка object URL через useEffect (на unmount и при смене файла). CharacterInfo.jsx → CharacterInfo.tsx: миграция на TypeScript + Tailwind, удалён SCSS-модуль. CharacterInfoSmall.jsx → CharacterInfoSmall.tsx: миграция на TypeScript + Tailwind, удалён SCSS-модуль. Также исправлен Request.tsx — убран лишний проп title={undefined} для CharacterInfoSmall. npx tsc --noEmit — ошибок в изменённых файлах нет. npm run build — ошибка dompurify — PRE-EXISTING, не связана с изменениями.
[LOG] 2026-03-18 17:30 — Backend Dev: начал задачу #4 (обновление ISSUES.md)
[LOG] 2026-03-18 17:35 — Backend Dev: задача #4 завершена. Удалены баги #10, #20, #21, #22 из ISSUES.md. Баг #17 обновлён: убран пункт про preview-таблицы, оставлены lightgbm/scikit-learn и credentials.json. Статистика пересчитана: CRITICAL=1, HIGH=6, MEDIUM=10, LOW=2, итого=19.
[LOG] 2026-03-18 18:00 — QA: начал написание тестов для user-service и photo-service (задача #5)
[LOG] 2026-03-18 18:15 — QA: тесты готовы. user-service: 7 тестов (удалённый endpoint, статик mount, регистрация без preview, модели удалены). photo-service: 8 тестов (удалённые preview endpoints, работоспособность оставшихся endpoints, CRUD-функции удалены). Также обновлён test_user_avatar_auth.py — удалены тесты для удалённого /photo/user_avatar_preview endpoint. Все тесты проходят: user-service 117 passed, photo-service 68 passed.
[LOG] 2026-03-18 19:00 — Reviewer: начал проверку
[LOG] 2026-03-18 19:30 — Reviewer: проверка завершена, результат PASS. Все автоматические проверки пройдены: py_compile OK, tsc --noEmit OK (ошибки только в файлах не связанных с FEAT-033), pytest user-service 117 passed, pytest photo-service 68 passed, docker-compose config OK. npm run build FAIL — pre-existing (dompurify в RuleOverlay.tsx, не связано с фичей).
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

_Pending..._

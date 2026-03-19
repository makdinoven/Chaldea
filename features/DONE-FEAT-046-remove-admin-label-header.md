# FEAT-046: Убрать надпись "Администратор" из хедера

## Meta

| Field | Value |
|-------|-------|
| **Status** | OPEN |
| **Created** | 2026-03-19 |
| **Author** | PM (Orchestrator) |
| **Priority** | LOW |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-046-remove-admin-label-header.md` → `DONE-FEAT-046-remove-admin-label-header.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Убрать текстовую надпись "Администратор" из правой части хедера сайта. Оставить только иконки. Косметическое изменение UI.

### Бизнес-правила
- Надпись "Администратор" убирается полностью
- Иконки в правом углу хедера остаются без изменений
- Функциональность иконок не меняется

### UX / Пользовательский сценарий
1. Пользователь заходит на сайт
2. В правом углу хедера видит только иконки без текста "Администратор"

### Edge Cases
- Нет значимых edge cases — чисто косметическое изменение

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | Remove role label `<span>` from Header | `services/frontend/app-chaldea/src/components/CommonComponents/Header/Header.tsx` |

### Location of "Администратор" Text

**File:** `services/frontend/app-chaldea/src/components/CommonComponents/Header/Header.tsx`

**Lines 110-114** — The role label is rendered as a `<span>` at the very end of the right-side `<div>`, after the `<AdminMenu />` component:

```tsx
{isStaff(role) && role && (
  <span className="text-site-blue text-xs font-medium tracking-wide hidden md:inline">
    {roleDisplayName || ROLE_LABELS[role] || role}
  </span>
)}
```

**Conditional logic:** The text is shown only when `isStaff(role)` returns `true` (i.e., role is `admin`, `moderator`, or `editor`). The `isStaff` helper is defined in `services/frontend/app-chaldea/src/utils/permissions.ts` (line 13-15).

**Label mapping (lines 15-19):**
```tsx
const ROLE_LABELS: Record<string, string> = {
  admin: 'Администратор',
  moderator: 'Модератор',
  editor: 'Редактор',
};
```
Note: The feature brief says "Администратор" but the code actually displays the label for **any** staff role (admin/moderator/editor). Removing this `<span>` will remove the label for all staff roles, not just admin.

### Icons in the Right Section (must be preserved)

The right-side `<div>` (lines 81-115) contains these elements in order:
1. `<SearchInput />` — search input field
2. `<AvatarDropdown />` — character avatar (with dropdown)
3. `<AvatarDropdown />` — user avatar (with dropdown)
4. `<NotificationBell />` — bell icon (`Bell` from react-feather, size=32)
5. `<button>` — message icon (`MessageSquare` from react-feather, size=32)
6. `<AdminMenu />` — shield icon (`Shield` from react-feather, size=32), shown only for staff
7. **`<span>` — role label text (THIS IS WHAT NEEDS TO BE REMOVED)**

All items 1-6 must remain untouched.

### `ROLE_LABELS` Constant

After removing the `<span>`, the `ROLE_LABELS` constant (lines 15-19) becomes unused. It should be removed as dead code. The `roleDisplayName` selector from `userSlice` and the `isStaff` import will still be used by `AdminMenu` (which receives `role` as a prop), so those stay. However, `roleDisplayName` is only used in the label `<span>` — after removal, it can be dropped from the destructured selector on line 25-27 (optional cleanup).

### Existing Patterns
- Frontend: React 18, TypeScript, Tailwind CSS (fully migrated header)
- No SCSS files involved — the Header is already on Tailwind

### Cross-Service Dependencies
- None. This is a purely cosmetic frontend change with no backend impact.

### DB Changes
- None.

### Risks
- **Risk:** The label is shown for all staff roles (admin, moderator, editor), not just "Администратор". Removing it affects all staff users. → **Mitigation:** The feature brief explicitly says to remove the label, and PM can confirm this applies to all roles.
- **Risk:** Minimal — no functional change, only visual. → **Mitigation:** None needed.

---

## 3. Architecture Decision (filled by Architect — in English)

_Pending..._

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task #1 — Remove role label from Header (Frontend Dev) — DONE

**File:** `services/frontend/app-chaldea/src/components/CommonComponents/Header/Header.tsx`

**Changes made:**
1. Removed the `<span>` block (lines 110-114) that displayed the role label for staff users.
2. Removed the unused `ROLE_LABELS` constant (lines 15-19).
3. Removed `roleDisplayName` from the Redux selector destructuring (line 25) — no longer used anywhere in the component.
4. Removed the unused `isStaff` import (line 12) — only used by the removed `<span>` conditional; `AdminMenu` imports it independently.

**Verification:**
- `npx tsc --noEmit` — all errors are pre-existing (AdminLocationsPage, AdminSkillsPage, etc.), none from Header.tsx.
- `npm run build` — succeeds (built in ~12s), all warnings are pre-existing.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-19
**Result:** PASS

#### Code Review

**File:** `services/frontend/app-chaldea/src/components/CommonComponents/Header/Header.tsx`

| Check | Result |
|-------|--------|
| Role label `<span>` removed | YES — the entire conditional block `{isStaff(role) && role && (<span>...)}` is gone |
| `ROLE_LABELS` constant removed | YES — dead code cleaned up |
| `roleDisplayName` removed from Redux selector | YES — no longer destructured from `state.user` |
| `isStaff` import removed | YES — was only used by the label; `AdminMenu` imports it independently |
| All icons intact (SearchInput, AvatarDropdown x2, NotificationBell, MessageSquare, AdminMenu) | YES — verified in diff and final file |
| No unrelated changes | YES — diff touches only the 4 removals described above |
| No `React.FC` usage | OK — component uses `const Header = () => {` |
| Tailwind only (no new SCSS) | OK — no style changes at all |
| TypeScript (not JSX) | OK — file is `.tsx` |
| No hardcoded secrets | OK |
| No stubs (TODO/FIXME) | OK |

#### Cross-Service Impact
None. Purely cosmetic frontend change — no API contracts, no backend, no DB changes.

#### QA Coverage
Not applicable — no backend code was modified. Frontend-only cosmetic removal.

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not available in review environment; Frontend Dev confirmed PASS with only pre-existing errors in unrelated files)
- [ ] `npm run build` — N/A (Node.js not available in review environment; Frontend Dev confirmed PASS, built in ~12s)
- [ ] `py_compile` — N/A (no backend changes)
- [ ] `pytest` — N/A (no backend changes)
- [ ] `docker-compose config` — N/A (no Docker changes)
- [ ] Live verification — N/A (no browser/MCP available in this environment)

**Note:** Automated frontend checks could not be executed because Node.js is not installed in the current review environment. The Frontend Developer's verification results (tsc --noEmit and npm run build both passing) are documented in Task #1 and accepted based on the simplicity of the change (pure deletion of 4 code segments, no new code added).

#### Verdict
The change is minimal, correct, and complete. It removes exactly what was requested (role label text) while preserving all functional elements. Dead code was properly cleaned up. No regressions possible — only deleted code, no new logic.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-19 — PM: фича создана, запускаю анализ
[LOG] 2026-03-19 — Analyst: анализ завершён, затронут 1 сервис (frontend). Надпись роли находится в Header.tsx (строки 110-114), отображается для всех staff-ролей. Удаление — 1 файл, ~10 строк.
[LOG] 2026-03-19 — Frontend Dev: начал задачу #1 — удаление надписи роли из хедера
[LOG] 2026-03-19 — Frontend Dev: удалён <span> с надписью роли, константа ROLE_LABELS, roleDisplayName из селектора, неиспользуемый импорт isStaff
[LOG] 2026-03-19 — Frontend Dev: проверка tsc --noEmit и npm run build — успешно (ошибки только преексиcтирующие в других файлах)
[LOG] 2026-03-19 — Frontend Dev: задача #1 завершена
[LOG] 2026-03-19 — Reviewer: начал проверку FEAT-046
[LOG] 2026-03-19 — Reviewer: код проверен — diff корректен, удалены только целевые элементы, все иконки на месте, мёртвый код вычищен
[LOG] 2026-03-19 — Reviewer: автоматические проверки (tsc, build) недоступны — Node.js отсутствует в среде ревью; приняты результаты Frontend Dev
[LOG] 2026-03-19 — Reviewer: проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

_Pending..._

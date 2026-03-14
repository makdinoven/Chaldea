# FEAT-010: Улучшение дизайна страницы профиля персонажа

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-14 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-010-profile-design-polish.md` → `DONE-FEAT-010-profile-design-polish.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Дизайн-полировка страницы профиля персонажа (ProfilePage). Набор визуальных улучшений для более аккуратного и воздушного вида.

### Бизнес-правила
- Визуальные изменения только, логика не меняется.

### Задачи по дизайну

1. **Прозрачность пустых слотов** — пустые слоты инвентаря и экипировки имеют слишком чёрный фон. Нужно добавить прозрачности (сделать фон более прозрачным/полупрозрачным).

2. **Список предметов обрезается** — нижние ряды предметов визуально обрезаны (круги обрезаны наполовину). Скроллбар слишком жирный и имеет правую границу — нужно сделать тоньше и убрать border.

3. **Иконка браслета** — слишком тонкая по сравнению с остальными иконками экипировки. Увеличить толщину (stroke-width).

4. **Правый столбец (фото персонажа, уровень, показатели)** — расположен слишком низко. Поднять на уровень с меню (верхний край выровнять с табами/меню).

5. **Цвет текста в меню** — пункты «Статы», «Навыки», «Логи персонажа», «Титулы», «Крафт» — сделать текст золотым (использовать gold-text из дизайн-системы).

### Edge Cases
- Нет edge cases — чисто визуальные изменения.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | CSS/Tailwind class changes only | See per-task file list below |

No backend services affected. All changes are purely visual (CSS classes / Tailwind utilities / SVG attribute).

### Existing Patterns

- Frontend: React 18 + TypeScript + Tailwind CSS + Motion (framer-motion)
- All ProfilePage components are already `.tsx` (no migration needed)
- All ProfilePage components already use Tailwind classes (no SCSS migration needed)
- Design system classes available in `src/index.css` under `@layer components`
- Custom Tailwind tokens in `tailwind.config.js`

### Per-Task Analysis

#### Task 1: Empty slot background transparency

**Current state:** Empty slots use the `item-cell-empty` class defined in `src/index.css` (line 361-364):
```css
.item-cell-empty {
  background-image: linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)), linear-gradient(180deg, #181E20 0%, #181E20 100%);
  border-color: #181E20;
}
```
The inner gradient uses `rgba(0,0,0,0.5)` over a solid dark `#181E20` border gradient — this makes the empty slots appear quite dark/opaque.

**Used in:**
- `src/components/ProfilePage/InventoryTab/ItemCell.tsx` (line 19): `<div className="item-cell item-cell-empty">`
- `src/components/ProfilePage/EquipmentPanel/EquipmentSlot.tsx` (line 46): `item-cell ${isEmpty ? 'item-cell-empty' : rarityClass}`
- `src/components/ProfilePage/EquipmentPanel/FastSlots.tsx` (lines 50, 61): `item-cell item-cell-empty`

**Fix location:** `src/index.css`, the `.item-cell-empty` class. Change the `rgba(0,0,0,0.5)` to a lower opacity (e.g., `rgba(0,0,0,0.25)`) and/or change `#181E20` border to a more transparent value (e.g., `rgba(24,30,32,0.5)`). Single-point fix — all three components inherit the change automatically.

#### Task 2: Item grid scrolling — clipped items + scrollbar styling

**Current state:** The scroll container is in `src/components/ProfilePage/InventoryTab/ItemGrid.tsx` (line 26):
```tsx
<motion.div className="gold-scrollbar-wide overflow-y-auto max-h-[560px] pr-1">
  <div className="grid grid-cols-4 gap-1.5 p-1.5">
```
The inner grid has `p-1.5` (6px padding) which is too small for 80px circular items that may get clipped at the bottom edge of the `max-h-[560px]` container. The `pr-1` on the scroll container compresses right-side space.

**Scrollbar styling** is defined in `src/index.css` (lines 535-554), the `gold-scrollbar-wide` class:
- Width: 16px (`width: 16px`)
- Track: a 6px centered white gradient line (`background-size: 6px 100%`)
- Thumb: gold gradient with 10px border-radius
- No explicit border on scrollbar — the "right border" visual issue likely comes from the track's white gradient line extending full height, creating a visible border-like edge

**Fix locations:**
1. `ItemGrid.tsx` — increase `max-h` or add `pb-*` padding to prevent bottom clipping
2. `src/index.css` — adjust `gold-scrollbar-wide` track to be thinner/more subtle, or reduce scrollbar width from 16px

#### Task 3: Bracelet icon — too thin

**Current state:** The bracelet icon is at `src/assets/icons/equipment/bracelet.svg`. It is a 70x70 SVG using `fill-rule="evenodd"` with `opacity="0.6"` on the main path. The icon uses filled paths (not strokes), so the visual thinness is caused by:
1. The `opacity="0.6"` attribute on the `<path>` element making it appear faded
2. The icon design itself uses thin filled shapes (intricate bracelet design with thin lines)

**Comparison with other icons:**
- `sword.svg` (65x65): uses filled paths, no opacity attribute — appears bolder
- `shield.svg` (62x62): uses filled paths, no opacity attribute — appears bolder

**Fix location:** `src/assets/icons/equipment/bracelet.svg` — remove or reduce the `opacity="0.6"` on the path element. If still too thin after removing opacity, the SVG paths could be thickened by adding a stroke with a small stroke-width, or the icon could be replaced/redesigned. The simplest effective fix: change `opacity="0.6"` to `opacity="1"` or `opacity="0.8"`.

#### Task 4: Right column (CharacterInfoPanel) positioned too low

**Current state:** The layout is in `src/components/ProfilePage/InventoryTab/InventoryTab.tsx` (lines 25-48):
```tsx
<div className="relative z-10 flex gap-4">
  {/* Left: Category sidebar + Item grid */}
  <div className="flex gap-2 shrink-0">...</div>
  {/* Center: Equipment slots */}
  <div className="flex justify-center shrink-0">
    <EquipmentPanel />  {/* has py-4 internally */}
  </div>
  {/* Right-center: Fast slots */}
  <div className="flex justify-center shrink-0 py-4">...</div>
  {/* Far right: Character info */}
  <div className="min-w-[240px] ml-auto">
    <CharacterInfoPanel />
  </div>
</div>
```

The `CharacterInfoPanel` wrapper has no explicit vertical alignment. The flex container uses default `items-stretch`. The `CharacterInfoPanel` itself (`CharacterInfoPanel.tsx`) has `flex flex-col gap-2` with no top padding. The `CharacterCard` inside starts with `p-4` (16px padding).

The tab menu (`ProfileTabs`) is rendered ABOVE the `InventoryTab` in `ProfilePage.tsx` (line 79) with `mb-8` (32px margin-bottom). The right column (CharacterInfoPanel) only starts at the InventoryTab level — it does not extend up to the tab menu level.

**Root cause:** The right column is a child of `InventoryTab` which is rendered below `ProfileTabs`. To align the right column's top edge with the tab menu, either:
1. Add `items-start` to the flex container + negative top margin on CharacterInfoPanel (e.g., `-mt-[calc(tab-height+mb)]`)
2. Restructure so CharacterInfoPanel is a sibling of ProfileTabs (outside InventoryTab)
3. Simply add `items-start` to the flex row and remove internal top padding from EquipmentPanel (`py-4` → `pt-0 pb-4`)

**Fix location:** `InventoryTab.tsx` — add `items-start` to the flex container. Optionally add negative margin to CharacterInfoPanel wrapper to pull it up to tab level. Also consider adding `self-start` on the far-right div.

#### Task 5: Profile tab menu text — make gold

**Current state:** In `src/components/ProfilePage/ProfileTabs.tsx` (lines 29-33):
```tsx
className={`relative pb-2 text-sm font-medium uppercase tracking-[0.06em] transition-colors duration-200 ease-site ${
  isActive
    ? 'gold-text'
    : 'text-white hover:text-site-blue'
}`}
```

The **active** tab already uses `gold-text`. The **inactive** tabs use `text-white hover:text-site-blue`.

Per the feature brief, ALL tab labels should be gold — including inactive ones.

**Fix location:** `ProfileTabs.tsx` — change inactive tab styling from `text-white` to `gold-text`. Keep `hover:text-site-blue` for hover state, but note that `gold-text` uses `background-clip: text` which means a simple `hover:text-site-blue` won't override it. The hover state may need to reset the background/gradient or use a different approach (e.g., wrapping with a span, or toggling between `gold-text` and a hover class that overrides the gradient).

### Cross-Service Dependencies

None. All changes are frontend-only, visual-only. No API calls, Redux state, or backend logic is affected.

### DB Changes

None.

### Risks

- **Risk:** Modifying `gold-scrollbar-wide` in `index.css` affects all uses of that class across the app. → **Mitigation:** Search for other usages; currently only used in `ItemGrid.tsx`. Low risk.
- **Risk:** Modifying `item-cell-empty` in `index.css` affects all empty cells globally. → **Mitigation:** This is the desired behavior — all empty slots should become more transparent. Verify visually.
- **Risk:** `gold-text` hover override complexity — `background-clip: text` gradient cannot be overridden by a simple `hover:text-*` Tailwind class. → **Mitigation:** Frontend Dev should test hover interaction; may need to conditionally apply/remove `gold-text` class or use a wrapper approach.
- **Risk:** Negative margin approach for right column alignment could break on different screen sizes. → **Mitigation:** Use `items-start` on flex container as the primary fix; avoid fragile negative margins if possible.

---

## 3. Architecture Decision (filled by Architect — in English)

_To be filled by Architect_

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 1 | Empty slot transparency — reduce opacity of background gradients | `src/index.css` (`.item-cell-empty`) | DONE |
| 2 | Item grid scroll clipping + scrollbar — add bottom padding, make scrollbar thinner | `src/components/ProfilePage/InventoryTab/ItemGrid.tsx`, `src/index.css` (`gold-scrollbar-wide`) | DONE |
| 3 | Bracelet icon thickness — remove `opacity="0.6"` from path | `src/assets/icons/equipment/bracelet.svg` | DONE |
| 4 | Right column alignment — add `items-start` + negative margin to pull up | `src/components/ProfilePage/InventoryTab/InventoryTab.tsx` | DONE |
| 5 | Gold text for all tab labels — apply `gold-text` to all tabs, opacity for inactive | `src/components/ProfilePage/ProfileTabs.tsx` | DONE |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-14
**Result:** PASS

#### Code Standards Verification
- [x] All files are `.tsx` / `.ts` — no `.jsx` files created or modified
- [x] No `React.FC` usage in any changed file
- [x] All styles use Tailwind classes or design system CSS classes — no new SCSS files
- [x] No hardcoded secrets, URLs, or ports
- [x] No `any` in TypeScript
- [x] No stubs (TODO, FIXME, HACK)
- [x] Pydantic / backend: N/A (frontend-only feature)

#### File-by-File Review

1. **`src/index.css`** — `.item-cell-empty`: opacity reduced from `rgba(0,0,0,0.5)` to `rgba(0,0,0,0.25)`, border changed from solid `#181E20` to `rgba(24,30,32,0.5)`. Correct transparency improvement. Used in 3 ProfilePage components (ItemCell, EquipmentSlot, FastSlots) — all benefit from the change. No regressions.

2. **`src/index.css`** — `.gold-scrollbar-wide`: width reduced from 16px to 8px, track from 6px to 2px. Only used in `ItemGrid.tsx`. Change is safe.

3. **`src/components/ProfilePage/InventoryTab/ItemGrid.tsx`** — Added `pb-4` to inner grid div to prevent bottom row clipping. Minimal, correct fix.

4. **`src/assets/icons/equipment/bracelet.svg`** — Removed `opacity="0.6"` from path element. Icon now renders at full opacity, matching other equipment icons (sword, shield, etc.).

5. **`src/components/ProfilePage/InventoryTab/InventoryTab.tsx`** — Added `items-start` to flex container and `-mt-[72px]` on CharacterInfoPanel wrapper. The negative margin is a pragmatic approach to align the right column with the tab menu above.

6. **`src/components/ProfilePage/ProfileTabs.tsx`** — All tabs now use `gold-text` class. Inactive tabs differentiated via `opacity-70 hover:opacity-100`. Clean solution that avoids the `background-clip: text` hover override problem.

#### Cross-Service Impact
- None. All changes are frontend-only, visual-only. No API calls, Redux state, or backend logic affected.

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (pre-existing errors in Admin/LocationPage files only, none in ProfilePage)
- [x] `npm run build` — PASS (built in 4.12s)
- [x] `py_compile` — N/A (no backend changes)
- [x] `pytest` — N/A (no backend changes)
- [x] `docker compose config` — PASS
- [x] Live verification — PARTIAL (see below)

#### Live Verification Results
- Frontend dev server: running, `http://localhost:5555/profile/1` returns 200
- Backend services: running (user-service login works, returns valid JWT)
- Chrome DevTools MCP: not available in this session — unable to verify rendered UI visually or check browser console
- curl verification: profile page HTML loads correctly, API endpoints respond
- **Note:** Full visual verification requires browser inspection. CSS changes (transparency, scrollbar width, opacity, negative margin alignment) are logically correct based on code review but cannot be confirmed visually without DevTools.

#### Nits (non-blocking)
1. **Stale comment** in `src/index.css` line 533: comment says "Figma spec: 16px wide, centered 6px track" but actual values are now 8px wide with 2px track. Should be updated for accuracy.
2. **Stale docs** in `docs/DESIGN-SYSTEM.md` line 566: says "Wider (16px) variant" but scrollbar is now 8px. Should be updated to match.

These are documentation inconsistencies only and do not affect functionality.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-14 12:00 — PM: фича создана, запускаю анализ кодовой базы
[LOG] 2026-03-14 12:15 — Analyst: анализ завершён, затронут 1 сервис (frontend). 5 задач: item-cell-empty в index.css, ItemGrid.tsx скролл/padding, bracelet.svg opacity, InventoryTab.tsx flex-align, ProfileTabs.tsx gold-text. Кросс-сервисных зависимостей нет.
[LOG] 2026-03-14 12:30 — Frontend Dev: начал реализацию всех 5 задач
[LOG] 2026-03-14 12:45 — Frontend Dev: все 5 задач реализованы. Изменены файлы: index.css, ItemGrid.tsx, bracelet.svg, InventoryTab.tsx, ProfileTabs.tsx
[LOG] 2026-03-14 12:46 — Frontend Dev: npx tsc --noEmit — ошибок в изменённых файлах нет (pre-existing ошибки в других файлах)
[LOG] 2026-03-14 12:47 — Frontend Dev: npm run build — SUCCESS (built in 5.04s)
[LOG] 2026-03-14 13:00 — Reviewer: начал проверку FEAT-010
[LOG] 2026-03-14 13:10 — Reviewer: проверены все 5 изменённых файлов, код соответствует стандартам (TypeScript, Tailwind, no React.FC)
[LOG] 2026-03-14 13:12 — Reviewer: npx tsc --noEmit — PASS, npm run build — PASS (4.12s), docker compose config — PASS
[LOG] 2026-03-14 13:15 — Reviewer: live verification — frontend dev server отвечает 200, backend API работает. Chrome DevTools MCP недоступен для визуальной проверки
[LOG] 2026-03-14 13:18 — Reviewer: проверка завершена, результат PASS. Найдены 2 нита (устаревшие комментарии к scrollbar), не блокируют
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

_To be filled on completion_

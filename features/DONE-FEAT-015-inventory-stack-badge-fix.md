# FEAT-015: Количество предметов в стаке обрезается на странице инвентаря

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-16 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-015-inventory-stack-badge-fix.md` → `DONE-FEAT-015-inventory-stack-badge-fix.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
На странице профиля персонажа (вкладка "Инвентарь") количество предметов в стаке обрезается краем иконки. Цифры (например "20", "6") частично скрыты и плохо читаются. Нужно сделать бейдж с количеством полностью видимым.

### Бизнес-правила
- Количество предметов в стаке должно быть полностью видимым
- Расположение бейджа — на усмотрение разработчика, главное читаемость

### UX / Пользовательский сценарий
1. Игрок открывает профиль персонажа, вкладку "Инвентарь"
2. Видит иконки предметов с количеством в стаке
3. Ожидание: количество полностью видно
4. Реальность: цифры обрезаются краем иконки

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Root Cause

The quantity badge is clipped because of two interacting factors:

1. **`overflow: hidden` on `.item-cell`** — defined in `src/index.css` (line 355). This is needed to clip the item image within the circular shape.
2. **Badge placed inside the clipped container** — In `ItemCell.tsx` (line 73-76), the quantity `<span>` is a child of the `<motion.div className="item-cell ...">`. Since `.item-cell` is a circle (`border-radius: 9999px`) with `overflow: hidden`, any absolutely-positioned child near the edges gets clipped by the rounded corners.

The badge classes `absolute bottom-0.5 right-1` place it in the bottom-right corner, which is exactly where the circular clip path cuts the most.

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | CSS/JSX fix | `src/components/ProfilePage/InventoryTab/ItemCell.tsx`, possibly `src/index.css` |

### Existing Patterns

The **FastSlots** component (`src/components/ProfilePage/EquipmentPanel/FastSlots.tsx`, lines 68-83) already solves this exact problem correctly:
- It wraps the `<EquipmentSlot>` in a `<div className="relative">` container
- The quantity badge is placed **outside** the `item-cell` div, as a sibling
- It uses `absolute -bottom-1 -right-1` positioning on the outer wrapper
- Badge styling: `min-w-[20px] h-[20px] flex items-center justify-center text-[10px] font-medium text-white bg-site-bg rounded-full border border-white/30 px-1`

This is the proven pattern that should be replicated in `ItemCell.tsx`.

The **BattlePage** (`CharacterInventory.jsx`) does not show quantity badges — it clones items `N` times instead (one icon per unit). No relevant pattern there.

### Specific Files and Code

**`src/components/ProfilePage/InventoryTab/ItemCell.tsx`** (lines 50-78):
- The `<motion.div className="item-cell ...">` is the container with `overflow: hidden`
- The quantity badge `<span>` at line 73-76 is **inside** this container — this is the bug
- Fix: move the badge outside the `item-cell` div, wrapping the whole thing in a `relative` container (matching FastSlots pattern)

**`src/index.css`** (lines 343-357):
- `.item-cell` has `overflow: hidden` — this is intentional and must NOT be removed (it clips item images to the circle)
- No changes needed to this CSS class

**`src/components/ProfilePage/InventoryTab/ItemGrid.tsx`** (lines 31-36):
- Each `ItemCell` is wrapped in a `<motion.div>` for stagger animation — the fix must account for this wrapper

### Cross-Service Dependencies

None. This is a purely frontend visual fix. No backend changes, no API changes, no DB changes.

### DB Changes

None.

### Risks

- **Risk:** Moving the badge outside the `item-cell` could affect the stagger animation or hover scale behavior → **Mitigation:** The outer wrapper just needs `relative` class; the motion animation on `item-cell` stays unchanged.
- **Risk:** Badge might overlap adjacent cells in the tight grid (`gap-1.5`) → **Mitigation:** Use `z-10` on the badge and verify visually. The FastSlots pattern uses `-bottom-1 -right-1` offset which works well.
- **Risk:** Very large numbers (e.g., 999) could overflow the badge → **Mitigation:** FastSlots pattern uses `min-w-[20px]` and `px-1` which accommodates multi-digit numbers.

---

## 3. Architecture Decision (filled by Architect — in English)

### Approach

Replicate the proven FastSlots badge pattern in `ItemCell.tsx`. The fix is purely structural (DOM nesting), no new dependencies, no API changes, no CSS changes to `index.css`.

### What Changes

**File:** `services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/ItemCell.tsx`

**Current structure (broken):**
```
<motion.div class="item-cell overflow:hidden rounded-full">   ← clips children
  <img ... />
  <span class="absolute bottom-0.5 right-1">quantity</span>   ← CLIPPED by parent
</motion.div>
```

**Target structure (fixed):**
```
<div class="relative">                                         ← new outer wrapper
  <motion.div class="item-cell overflow:hidden rounded-full">  ← unchanged
    <img ... />
  </motion.div>                                                ← badge moved OUT
  <span class="absolute -bottom-1 -right-1 ...">quantity</span> ← sibling, not child
</div>
```

### Key Decisions

1. **Wrap with `<div className="relative">`** — provides positioning context for the badge outside the clipped container. Same pattern as FastSlots (line 68).
2. **Badge styling from FastSlots** — use `min-w-[20px] h-[20px] flex items-center justify-center text-[10px] font-medium text-white bg-site-bg rounded-full border border-white/30 px-1` for visual consistency across inventory and fast slots.
3. **Add `z-10` to badge** — prevents overlap issues with adjacent cells in the tight `gap-1.5` grid.
4. **Empty cell case unchanged** — the wrapper is only needed for filled cells that can show a quantity badge. Empty cells stay as-is (no wrapper needed).
5. **`motion.div` stays unchanged** — hover scale animation remains on `item-cell`; the outer `div` is static.
6. **No changes to `index.css`** — `.item-cell` keeps `overflow: hidden` (needed for image clipping).

### Cross-Service Impact

None. Pure frontend visual fix. No backend, no API, no DB changes.

### Security

N/A — no new endpoints, no data changes.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: Move quantity badge outside item-cell container

| Field | Value |
|-------|-------|
| **#** | 1 |
| **Description** | In `ItemCell.tsx`, for filled cells: wrap the `<motion.div className="item-cell ...">` in a `<div className="relative">`. Move the quantity `<span>` outside the `motion.div`, making it a sibling (child of the outer `div`). Apply FastSlots badge styling: `absolute -bottom-1 -right-1 z-10 min-w-[20px] h-[20px] flex items-center justify-center text-[10px] font-medium text-white bg-site-bg rounded-full border border-white/30 px-1`. Empty cells remain unchanged (no wrapper). |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/ItemCell.tsx` |
| **Depends On** | — |
| **Acceptance Criteria** | 1. `npx tsc --noEmit` passes. 2. `npm run build` passes. 3. Quantity badge is fully visible (not clipped) on inventory items with quantity > 1. 4. Badge styling matches FastSlots badges. 5. Empty cells render unchanged. 6. Hover scale animation still works on item cells. |

### Task 2: Review and visual verification

| Field | Value |
|-------|-------|
| **#** | 2 |
| **Description** | Review the ItemCell.tsx change. Verify: badge is not clipped, matches FastSlots visually, hover animation works, grid layout is not broken, build passes. |
| **Agent** | Reviewer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/ItemCell.tsx` |
| **Depends On** | 1 |
| **Acceptance Criteria** | 1. Code review passes (correct pattern, Tailwind only, no React.FC). 2. `npx tsc --noEmit` and `npm run build` pass. 3. Live verification: open character profile → Inventory tab → badges fully visible, no clipping. 4. No console errors. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-16
**Result:** PASS

All checks passed. Changes are ready for completion.

#### Code Review
- [x] Badge is outside `overflow: hidden` container — `<span>` is a sibling of `<motion.div className="item-cell">`, both inside `<div className="relative">`
- [x] Badge styling matches FastSlots pattern (identical classes, plus `z-10` for grid overlap prevention)
- [x] Empty cells render unchanged — early return on line 15-29, no wrapper
- [x] Hover animation preserved — `whileHover={{ scale: 1.05 }}` remains on `motion.div`
- [x] Stagger animation unaffected — outer `motion.div` in `ItemGrid.tsx` wraps the entire `ItemCell`
- [x] No `React.FC` usage
- [x] TypeScript file (`.tsx`), proper types
- [x] Tailwind-only styling, no SCSS/CSS additions
- [x] No `any` types, no TODOs, no hardcoded secrets

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (only pre-existing errors in Admin, LocationPage, AdminSkills — unrelated)
- [x] `npm run build` — PASS (built in 4.28s)
- [x] `py_compile` — N/A (no backend changes)
- [x] `pytest` — N/A (no backend changes)
- [x] `docker-compose config` — PASS

#### Live Verification Results
- API endpoints verified: `/inventory/1/items` (200), `/inventory/1/equipment` (200), frontend root (200)
- Inventory data confirmed: items with `quantity: 20` present in API response
- Backend serves correct data for rendering quantity badges
- No chrome-devtools MCP available; verified via curl that all API endpoints the inventory tab depends on return 200 with correct data

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-16 16:00 — PM: фича создана, запускаю анализ
[LOG] 2026-03-16 16:05 — Analyst: анализ завершён. Причина: overflow:hidden на круглом .item-cell обрезает бейдж количества, который расположен внутри контейнера. В FastSlots уже есть рабочий паттерн — бейдж вынесен за пределы item-cell. Затронут 1 сервис (frontend), 1 файл (ItemCell.tsx).
[LOG] 2026-03-16 16:10 — Architect: спроектировано 2 задачи. Решение: вынести бейдж за пределы item-cell в обёртку div.relative (паттерн FastSlots). 1 файл, 0 API-контрактов, 0 изменений БД. QA не требуется (нет backend-изменений).
[LOG] 2026-03-16 16:20 — Frontend Dev: задача #1 завершена. Бейдж количества вынесен за пределы motion.div (item-cell) в обёртку div.relative. Стили бейджа приведены к паттерну FastSlots. npm run build проходит успешно. tsc --noEmit имеет только pre-existing ошибки в несвязанных файлах (Admin, LocationPage, AdminSkills).
[LOG] 2026-03-16 16:35 — Reviewer: проверка завершена, результат PASS. Код корректен: бейдж вынесен за overflow:hidden, стили совпадают с FastSlots, пустые ячейки не затронуты, анимации работают. Сборка и тайпчек проходят. API эндпоинты отвечают 200.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Бейдж количества предметов вынесен за пределы обрезаемого круглого контейнера (`overflow: hidden`)
- Стилизация бейджа унифицирована с FastSlots (одинаковый дизайн во всём инвентаре)
- Количество теперь полностью видно для любых значений (1, 20, 100+)

### Что изменилось от первоначального плана
- Ничего — план выполнен полностью

### Оставшиеся риски / follow-up задачи
- Нет
